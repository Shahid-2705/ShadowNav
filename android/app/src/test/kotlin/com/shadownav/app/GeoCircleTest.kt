package com.shadownav.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

class GeoCircleTest {

    @Test
    fun `ring is closed`() {
        val r = GeoCircle.ring(43.7384, 7.4246, 50.0, points = 16)
        assertEquals(17, r.size) // 16 vertices + the closing repeat
        assertEquals(r.first()[0], r.last()[0], 1e-12)
        assertEquals(r.first()[1], r.last()[1], 1e-12)
    }

    @Test
    fun `ring points sit at approximately the requested radius`() {
        val centerLat = 43.7384
        val centerLon = 7.4246
        val radiusM = 25.0
        val r = GeoCircle.ring(centerLat, centerLon, radiusM, points = 32)

        val earthRadiusM = 6_371_000.0
        for (p in r.dropLast(1)) {
            val dLatRad = Math.toRadians(p[0] - centerLat)
            val dLonRad = Math.toRadians(p[1] - centerLon)
            // Equirectangular distance, consistent with GeoCircle's own
            // approximation -- this checks the math is self-consistent, not
            // an independent projection.
            val x = dLonRad * cos(Math.toRadians(centerLat))
            val y = dLatRad
            val distM = sqrt(x * x + y * y) * earthRadiusM
            assertTrue("expected ~${radiusM}m, got ${distM}m", Math.abs(distM - radiusM) < 0.5)
        }
    }

    @Test(expected = IllegalArgumentException::class)
    fun `rejects degenerate point counts`() {
        GeoCircle.ring(0.0, 0.0, 10.0, points = 2)
    }
}
