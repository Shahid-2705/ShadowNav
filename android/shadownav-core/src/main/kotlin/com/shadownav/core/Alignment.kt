package com.shadownav.core

import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Device-to-car rotation, estimated from motion.
 *
 * A port of `shadownav/filter/alignment.py`. This is a prerequisite, not a
 * refinement: applying the nonholonomic constraint in the phone's frame rather
 * than the car's measured four times *worse* than no constraint at all.
 *
 * Vehicle up comes from the long-run mean specific force; vehicle forward from
 * the correlation between horizontal specific force and GNSS-derived
 * longitudinal acceleration. Right is `forward x up`.
 *
 * Freedom to operate: STMicroelectronics US11199410B2 is granted, in force,
 * covers phone-in-arbitrary-orientation misalignment and explicitly names
 * tunnels; its claim is tied to explicit axis determination. This is a
 * correlation-weighted estimate, and the intended long-term design-around is to
 * learn the misalignment. Do not describe it as novel.
 */
data class Alignment(
    /** Rows are `[right, forward, up]` expressed in device coordinates. */
    val rotDeviceToCar: Array<DoubleArray>,
    val quality: Double,
    val nSamples: Int,
) {
    /** Rotate a device-frame vector into the car frame. */
    fun apply(v: DoubleArray): DoubleArray = DoubleArray(3) { r ->
        rotDeviceToCar[r][0] * v[0] + rotDeviceToCar[r][1] * v[1] + rotDeviceToCar[r][2] * v[2]
    }

    override fun equals(other: Any?): Boolean =
        other is Alignment && quality == other.quality && nSamples == other.nSamples &&
            rotDeviceToCar.contentDeepEquals(other.rotDeviceToCar)

    override fun hashCode(): Int =
        rotDeviceToCar.contentDeepHashCode() * 31 + quality.hashCode()

    companion object {
        fun identity(): Alignment = Alignment(
            arrayOf(
                doubleArrayOf(1.0, 0.0, 0.0),
                doubleArrayOf(0.0, 1.0, 0.0),
                doubleArrayOf(0.0, 0.0, 1.0),
            ),
            0.0, 0,
        )
    }
}

object AlignmentEstimator {

    private fun norm(v: DoubleArray) = sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])

    private fun cross(a: DoubleArray, b: DoubleArray) = doubleArrayOf(
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )

    private fun dot(a: DoubleArray, b: DoubleArray) = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    /** Right-handed frame with rows `[right, forward, up]`, in device coords. */
    private fun orthonormalFrame(forwardIn: DoubleArray, upIn: DoubleArray): Array<DoubleArray> {
        val up = upIn.copyOf()
        val un = norm(up)
        for (i in 0..2) up[i] /= un

        var forward = DoubleArray(3) { forwardIn[it] - dot(forwardIn, up) * up[it] }
        var fn = norm(forward)
        if (fn < 1e-9) {
            // Forward unobservable; any axis perpendicular to up will do.
            val seed = if (abs(dot(doubleArrayOf(1.0, 0.0, 0.0), up)) > 0.9) {
                doubleArrayOf(0.0, 1.0, 0.0)
            } else {
                doubleArrayOf(1.0, 0.0, 0.0)
            }
            forward = DoubleArray(3) { seed[it] - dot(seed, up) * up[it] }
            fn = norm(forward)
        }
        for (i in 0..2) forward[i] /= fn

        val right = cross(forward, up)
        val rn = norm(right)
        for (i in 0..2) right[i] /= rn
        return arrayOf(right, forward, up)
    }

    /**
     * Recover the rotation from a window of aided driving.
     *
     * Returns [Alignment.identity] with quality 0 when there is too little
     * longitudinal excitation to observe the forward axis. A straight,
     * constant-speed approach is exactly that case, and reporting low quality
     * is the honest response rather than guessing an axis.
     *
     * Each interval's mean longitudinal acceleration is paired with the *mean*
     * horizontal specific force over the same interval. Pairing against a
     * single endpoint sample returned quality 0 on every offline sequence -- a
     * smoothed quantity compared against an unsmoothed one collapses the
     * correlation into noise.
     */
    fun estimate(
        acc: Array<DoubleArray>,
        gyr: Array<DoubleArray>,
        speedMs: DoubleArray,
        timeS: DoubleArray,
        minAccelMs2: Double = 0.12,
        minSamples: Int = 20,
    ): Alignment {
        if (acc.size < minSamples || speedMs.size != acc.size) return Alignment.identity()

        val up = DoubleArray(3)
        for (row in acc) for (i in 0..2) up[i] += row[i]
        for (i in 0..2) up[i] /= acc.size
        val upNorm = norm(up)
        if (upNorm < 1e-6) return Alignment.identity()
        for (i in 0..2) up[i] /= upNorm

        // Difference the speed column only where it actually changes: it is
        // held between fixes, so a naive gradient yields spikes and zeros.
        val valid = speedMs.indices.filter { speedMs[it].isFinite() }
        if (valid.size < 3) return Alignment.identity()
        val changed = ArrayList<Int>()
        changed.add(valid.first())
        for (k in 1 until valid.size) {
            if (speedMs[valid[k]] != speedMs[valid[k - 1]]) changed.add(valid[k])
        }
        if (changed.size < 3) return Alignment.identity()

        val aLong = ArrayList<Double>()
        val horiz = ArrayList<DoubleArray>()
        for (k in 0 until changed.size - 1) {
            val a = changed[k]
            val b = changed[k + 1]
            val dt = timeS[b] - timeS[a]
            if (dt <= 0.0) continue
            aLong.add((speedMs[b] - speedMs[a]) / dt)

            val mean = DoubleArray(3)
            for (i in a..b) for (c in 0..2) mean[c] += acc[i][c]
            val n = (b - a + 1).toDouble()
            for (c in 0..2) mean[c] /= n
            val vert = dot(mean, up)
            horiz.add(DoubleArray(3) { mean[it] - vert * up[it] })
        }
        if (aLong.size < 2) return Alignment.identity()

        val strongIdx = aLong.indices.filter { abs(aLong[it]) >= minAccelMs2 }
        if (strongIdx.size < 3) return Alignment.identity()

        // Weighting by a_long makes braking and acceleration agree on a sign
        // instead of cancelling.
        val forward = DoubleArray(3)
        for (i in strongIdx) for (c in 0..2) forward[c] += horiz[i][c] * aLong[i]
        if (norm(forward) < 1e-9) return Alignment.identity()

        val rot = orthonormalFrame(forward, up)

        var num = 0.0
        var den = 0.0
        for (i in strongIdx) {
            val proj = dot(horiz[i], rot[1])
            num += proj * proj
            val h = norm(horiz[i])
            den += h * h
        }
        val quality = if (den > 1e-12) (num / den).coerceIn(0.0, 1.0) else 0.0
        return Alignment(rot, quality, strongIdx.size)
    }
}
