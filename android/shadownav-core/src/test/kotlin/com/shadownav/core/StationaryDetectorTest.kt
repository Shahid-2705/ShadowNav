package com.shadownav.core

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.sin
import kotlin.random.Random

/**
 * Guards the fix for an observed on-device failure: a phone at rest, holding a
 * bad 4.1 m/s speed from a weak indoor fix, dead-reckoning away indefinitely
 * while its own accelerometer sat pinned at g.
 */
class StationaryDetectorTest {

    private val dt = 1.0 / 400.0   // the rate actually measured on hardware

    private fun feed(
        detector: StationaryDetector,
        seconds: Double,
        accel: (Int) -> DoubleArray,
        gyro: (Int) -> DoubleArray,
        startT: Double = 0.0,
    ): Double {
        val n = (seconds / dt).toInt()
        var t = startT
        for (i in 0 until n) {
            t += dt
            detector.update(accel(i), gyro(i), t)
        }
        return t
    }

    private fun restingAccel(rng: Random) =
        { _: Int -> doubleArrayOf(rng.nextDouble(-0.02, 0.02),
                                  rng.nextDouble(-0.02, 0.02),
                                  9.80665 + rng.nextDouble(-0.02, 0.02)) }

    private fun restingGyro(rng: Random) =
        { _: Int -> doubleArrayOf(rng.nextDouble(-0.001, 0.001),
                                  rng.nextDouble(-0.001, 0.001),
                                  rng.nextDouble(-0.001, 0.001)) }

    @Test
    fun `a phone at rest is detected after the dwell`() {
        val d = StationaryDetector()
        val rng = Random(1)
        feed(d, 3.0, restingAccel(rng), restingGyro(rng))
        assertTrue("a resting phone must read stationary", d.isStationary)
    }

    @Test
    fun `not declared before the dwell has elapsed`() {
        val d = StationaryDetector()
        val rng = Random(2)
        feed(d, 0.8, restingAccel(rng), restingGyro(rng))
        assertFalse("declared stationary too early", d.isStationary)
    }

    @Test
    fun `driving vibration is not stationary`() {
        val d = StationaryDetector()
        val rng = Random(3)
        // Road vibration: a few m/s^2 of broadband content on top of gravity.
        feed(d, 5.0,
            { i -> doubleArrayOf(
                0.8 * sin(i * 0.7) + rng.nextDouble(-0.4, 0.4),
                0.6 * sin(i * 0.3),
                9.80665 + 0.9 * sin(i * 1.1)) },
            { _ -> doubleArrayOf(0.0, 0.0, 0.01) })
        assertFalse("driving must not read stationary", d.isStationary)
    }

    @Test
    fun `turning is not stationary even when smooth`() {
        val d = StationaryDetector()
        val rng = Random(4)
        // A smooth constant-radius turn: quiet accelerometer, busy gyro.
        feed(d, 5.0, restingAccel(rng), { _ -> doubleArrayOf(0.0, 0.0, 0.3) })
        assertFalse("a turn must not read stationary", d.isStationary)
    }

    @Test
    fun `sustained smooth horizontal acceleration is caught by the tilt check`() {
        // The case magnitude alone cannot see: a steady 1.5 m/s^2 forward push
        // is perpendicular to gravity, so it lifts |a| only from 9.807 to
        // 9.921. Against a trusted vertical it tilts the apparent up by
        // 8.7 degrees, which is unmistakable.
        val up = doubleArrayOf(0.0, 0.0, 1.0)
        val d = StationaryDetector()
        var t = 0.0
        repeat((5.0 / dt).toInt()) {
            t += dt
            d.update(doubleArrayOf(0.0, 1.5, 9.80665), doubleArrayOf(0.0, 0.0, 0.0), t, up)
        }
        assertFalse("smooth horizontal acceleration must not read stationary", d.isStationary)
    }

    @Test
    fun `magnitude alone is documented as blind to horizontal acceleration`() {
        // States the limitation as a fact rather than leaving it implicit: with
        // no reference vertical supplied, this case does read as stationary.
        val d = StationaryDetector()
        feed(d, 5.0,
            { _ -> doubleArrayOf(0.0, 1.5, 9.80665) },
            { _ -> doubleArrayOf(0.0, 0.0, 0.0) })
        assertTrue(
            "if this ever fails, magnitude-only detection improved and the " +
                "docs should say so",
            d.isStationary,
        )
    }

    @Test
    fun `a resting phone still reads stationary with a reference vertical`() {
        val up = doubleArrayOf(0.0, 0.0, 1.0)
        val d = StationaryDetector()
        val rng = Random(9)
        var t = 0.0
        repeat((3.0 / dt).toInt()) {
            t += dt
            d.update(restingAccel(rng)(0), restingGyro(rng)(0), t, up)
        }
        assertTrue("the tilt check must not reject a genuinely resting phone", d.isStationary)
    }

    @Test
    fun `releases immediately when motion resumes`() {
        val d = StationaryDetector()
        val rng = Random(5)
        val t = feed(d, 3.0, restingAccel(rng), restingGyro(rng))
        assertTrue(d.isStationary)
        // One clear motion sample must drop it: a late release loses real
        // distance, which is worse than the drift it prevents.
        d.update(doubleArrayOf(0.0, 3.0, 9.80665), doubleArrayOf(0.0, 0.0, 0.2), t + dt)
        assertFalse("must release on the first sign of motion", d.isStationary)
    }

    @Test
    fun `zeroing speed while stationary stops a runaway`() {
        // Reproduces the observed failure end to end: a bad 4.1 m/s initial
        // speed, no GNSS, phone at rest.
        val bad = KinematicEkf(0.0, 0.0, 0.0, 4.1)
        repeat(600) { bad.propagate(0.0, null, 0.1) }
        val runaway = bad.north
        assertTrue("expected a runaway to reproduce, got $runaway m", runaway > 200.0)

        val fixed = KinematicEkf(0.0, 0.0, 0.0, 4.1)
        repeat(600) {
            fixed.propagate(0.0, null, 0.1)
            fixed.updateSpeed(0.0, sigma = 0.05)     // the stationary update
        }
        assertTrue(
            "stationary update should hold position, drifted ${fixed.north} m",
            fixed.north < 5.0,
        )
    }
}
