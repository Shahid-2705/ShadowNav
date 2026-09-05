package com.shadownav.app

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * Small-scale metres-to-degrees circle approximation (equirectangular,
 * accurate to well under a metre at the confidence-ring radii this project
 * ever draws -- tens of metres, never planet-scale) -- used to draw the
 * calibrated confidence ring as an actual geographic polygon rather than a
 * screen-space [MapLibre `circle-radius`], which is fixed in pixels and
 * would not shrink/grow correctly as the map is zoomed. No Android
 * dependency, so it's plain-JUnit testable like [decideRenderTier].
 */
object GeoCircle {

    private const val EARTH_RADIUS_M = 6_371_000.0

    /**
     * Returns a closed ring (first point repeated as the last, per GeoJSON
     * polygon convention) of `(lat, lon)` pairs, `points` vertices around
     * the circle plus the closing repeat.
     */
    fun ring(centerLat: Double, centerLon: Double, radiusM: Double, points: Int = 48): List<DoubleArray> {
        require(points >= 3) { "a circle needs at least 3 points" }
        val latRad = Math.toRadians(centerLat)
        val out = ArrayList<DoubleArray>(points + 1)
        for (i in 0..points) {
            val theta = 2.0 * PI * i / points
            val dLat = (radiusM * cos(theta)) / EARTH_RADIUS_M
            val dLon = (radiusM * sin(theta)) / (EARTH_RADIUS_M * cos(latRad))
            out.add(doubleArrayOf(centerLat + Math.toDegrees(dLat), centerLon + Math.toDegrees(dLon)))
        }
        return out
    }
}
