package com.shadownav.core

import kotlin.math.sqrt

/**
 * Rotation-invariant IMU features for the learned speed front end.
 *
 * A port of `shadownav/models/features.py`. Raw device axes are deliberately
 * not the input: a phone sits at an arbitrary orientation, and there are only
 * ~14,000 speed labels in the training data, far too few to learn a 3-D
 * rotation group. These six channels depend on the device frame only through
 * the gravity direction, which the long-run mean specific force gives reliably.
 *
 * Last-known GNSS speed is deliberately absent. Feeding it lets the network
 * minimise its loss by echoing its input, which scores well in training and
 * does nothing during the blackout it exists to survive.
 */
object Features {

    const val N_CHANNELS = 6

    val CHANNEL_NAMES = arrayOf(
        "acc_mag", "acc_vertical", "acc_horizontal",
        "gyr_mag", "gyr_yaw", "gyr_horizontal",
    )

    /**
     * Unit vertical in device coordinates, from the long-run mean.
     *
     * Short windows do not work: on a turning vehicle a centripetal 1.04 m/s^2
     * tilts the estimate by 6 degrees, which mis-projects gravity by
     * 1.03 m/s^2. Fix this once per drive from aided data.
     */
    fun gravityDirection(acc: Array<DoubleArray>): DoubleArray {
        val mean = DoubleArray(3)
        for (row in acc) for (i in 0..2) mean[i] += row[i]
        for (i in 0..2) mean[i] /= acc.size
        val n = sqrt(mean[0] * mean[0] + mean[1] * mean[1] + mean[2] * mean[2])
        if (n < 1e-6) return doubleArrayOf(0.0, 0.0, 1.0)
        return DoubleArray(3) { mean[it] / n }
    }

    /** `(N, 6)` feature block for one window. */
    fun invariant(
        acc: Array<DoubleArray>, gyr: Array<DoubleArray>, upIn: DoubleArray,
    ): Array<DoubleArray> {
        val n = sqrt(upIn[0] * upIn[0] + upIn[1] * upIn[1] + upIn[2] * upIn[2])
        val up = DoubleArray(3) { upIn[it] / maxOf(n, 1e-9) }

        return Array(acc.size) { i ->
            val a = acc[i]
            val g = gyr[i]
            val aVert = a[0] * up[0] + a[1] * up[1] + a[2] * up[2]
            val gVert = g[0] * up[0] + g[1] * up[1] + g[2] * up[2]

            var aH = 0.0
            var gH = 0.0
            for (c in 0..2) {
                val ah = a[c] - aVert * up[c]
                val gh = g[c] - gVert * up[c]
                aH += ah * ah
                gH += gh * gh
            }
            doubleArrayOf(
                sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]),
                aVert,
                sqrt(aH),
                sqrt(g[0] * g[0] + g[1] * g[1] + g[2] * g[2]),
                gVert,
                sqrt(gH),
            )
        }
    }
}
