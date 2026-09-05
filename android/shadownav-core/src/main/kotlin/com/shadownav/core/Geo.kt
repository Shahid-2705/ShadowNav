package com.shadownav.core

import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * WGS84 to a local tangent plane.
 *
 * A direct port of `shadownav/geo.py`. The two proper radii of curvature are
 * used rather than one spherical radius: at 53 deg N they are 6376234 m and
 * 6391797 m, a 0.24% difference, which over a 5 km drive is 12 m -- larger than
 * the drift being resolved. Both also exceed the 6371 km mean radius, so a
 * single radius is wrong in the same direction for both axes.
 */
object Geo {

    const val WGS84_A = 6378137.0
    const val WGS84_F = 1.0 / 298.257223563
    val WGS84_E2 = WGS84_F * (2.0 - WGS84_F)

    /** `(meridional, normal)` radii of curvature in metres. */
    fun curvatureRadii(latDeg: Double): Pair<Double, Double> {
        val s = sin(Math.toRadians(latDeg))
        val denom = 1.0 - WGS84_E2 * s * s
        val meridional = WGS84_A * (1.0 - WGS84_E2) / (denom * sqrt(denom))
        val normal = WGS84_A / sqrt(denom)
        return meridional to normal
    }

    /** Local east/north metres relative to a reference. */
    fun llaToEnu(
        latDeg: DoubleArray,
        lonDeg: DoubleArray,
        refLatDeg: Double = latDeg[0],
        refLonDeg: Double = lonDeg[0],
    ): Pair<DoubleArray, DoubleArray> {
        val (mRad, nRad) = curvatureRadii(refLatDeg)
        val cosRef = cos(Math.toRadians(refLatDeg))
        val east = DoubleArray(latDeg.size)
        val north = DoubleArray(latDeg.size)
        for (i in latDeg.indices) {
            north[i] = Math.toRadians(latDeg[i] - refLatDeg) * mRad
            east[i] = Math.toRadians(lonDeg[i] - refLonDeg) * nRad * cosRef
        }
        return east to north
    }

    /** Single-point convenience form of [llaToEnu]. */
    fun pointToEnu(
        latDeg: Double, lonDeg: Double, refLatDeg: Double, refLonDeg: Double,
    ): DoubleArray {
        val (mRad, nRad) = curvatureRadii(refLatDeg)
        return doubleArrayOf(
            Math.toRadians(lonDeg - refLonDeg) * nRad * cos(Math.toRadians(refLatDeg)),
            Math.toRadians(latDeg - refLatDeg) * mRad,
        )
    }

    fun pathLength(east: DoubleArray, north: DoubleArray): Double {
        var total = 0.0
        for (i in 1 until east.size) {
            total += hypot(east[i] - east[i - 1], north[i] - north[i - 1])
        }
        return total
    }

    /** Wrap radians to `(-pi, pi]`. */
    fun wrap(a: Double): Double {
        var x = (a + Math.PI) % (2.0 * Math.PI)
        if (x < 0) x += 2.0 * Math.PI
        return x - Math.PI
    }

    /**
     * Course over ground, radians clockwise from north.
     *
     * Consecutive differencing is unusable on held GNSS positions: a fix that
     * repeats for scores of samples makes `atan2(0, 0)` return 0, a due-north
     * course for a vehicle heading anywhere, which silently zeroes every
     * cross-track error. The course is taken between successive *distinct*
     * positions at least [minStepM] apart and held forward across repeats.
     */
    fun headingFromTrack(
        east: DoubleArray, north: DoubleArray, minStepM: Double = 0.5,
    ): DoubleArray {
        val n = east.size
        if (n < 2) return DoubleArray(n)

        val moved = ArrayList<Int>()
        for (i in 1 until n) {
            if (hypot(east[i] - east[i - 1], north[i] - north[i - 1]) >= minStepM) {
                moved.add(i - 1)
            }
        }
        if (moved.isEmpty()) return DoubleArray(n)

        val head = DoubleArray(n)
        for (k in 0 until moved.size - 1) {
            val a = moved[k]
            val b = moved[k + 1]
            val h = atan2(east[b] - east[a], north[b] - north[a])
            for (i in a until b) head[i] = h
        }
        val first = moved.first()
        val last = moved.last()
        val tail = if (moved.size == 1) {
            atan2(east[last] - east[first], north[last] - north[first])
        } else {
            head[last - 1]
        }
        for (i in last until n) head[i] = tail
        val lead = if (first < n) head[first] else 0.0
        for (i in 0 until first) head[i] = lead
        return head
    }

    fun approxEquals(a: Double, b: Double, tol: Double = 1e-9): Boolean = abs(a - b) <= tol
}
