package com.shadownav.core

import com.shadownav.core.GoldenJson.arr
import com.shadownav.core.GoldenJson.bool
import com.shadownav.core.GoldenJson.doubles
import com.shadownav.core.GoldenJson.int
import com.shadownav.core.GoldenJson.matrix
import com.shadownav.core.GoldenJson.num
import com.shadownav.core.GoldenJson.obj
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Proves the Kotlin estimator is numerically identical to the Python one.
 *
 * shared/README.md makes this a hard requirement: "Verify the Kotlin path
 * reproduces the Python path numerically on a fixed replay before trusting any
 * on-device number."
 *
 * The reason is that this port has no ground truth on a phone. A sign error, a
 * transposed Jacobian or a wrong wrap produces a trajectory that looks entirely
 * plausible on screen. These tests are the only thing standing between "it
 * runs" and "it is right".
 *
 * Regenerate the vectors with, from `python/`:
 *     PYTHONPATH=. python scripts/export_golden.py
 */
class ParityTest {

    private val tol = 1e-9

    private fun assertArrayClose(
        expected: DoubleArray, actual: DoubleArray, tolerance: Double = tol, label: String = "",
    ) {
        assertEquals("$label length", expected.size, actual.size)
        for (i in expected.indices) {
            assertEquals("$label index $i", expected[i], actual[i], tolerance)
        }
    }

    // ------------------------------------------------------------------ geo

    @Test
    fun `geodesy matches python`() {
        val g = GoldenJson.load("geo")
        val lat = g.doubles("lat_deg")
        val lon = g.doubles("lon_deg")

        val (east, north) = Geo.llaToEnu(lat, lon)
        assertArrayClose(g.doubles("east_m"), east, 1e-8, "east")
        assertArrayClose(g.doubles("north_m"), north, 1e-8, "north")

        val (m, n) = Geo.curvatureRadii(53.0)
        assertArrayClose(
            g.doubles("curvature_radii_53deg"), doubleArrayOf(m, n), 1e-6, "radii",
        )
        assertEquals(g.num("path_length_m"), Geo.pathLength(east, north), 1e-8)
        assertArrayClose(
            g.doubles("heading_from_track_rad"),
            Geo.headingFromTrack(east, north), 1e-9, "heading",
        )
    }

    // ------------------------------------------------------------ propagation

    @Test
    fun `propagation matches python over ninety steps`() {
        val g = GoldenJson.load("propagate")
        val init = g.obj("init")
        val f = KinematicEkf(
            init.num("east"), init.num("north"), init.num("heading"), init.num("speed"),
        )
        val dt = g.num("dt")
        for (gz in g.doubles("gyro_z")) f.propagate(gz, null, dt)

        assertArrayClose(g.doubles("state"), f.x, tol, "state")
        assertArrayClose(g.doubles("cov_diag"), f.cov.diagonal(), 1e-12, "cov diag")
    }

    @Test
    fun `propagation with forward acceleration matches python`() {
        val g = GoldenJson.load("propagate_accel")
        val init = g.obj("init")
        val f = KinematicEkf(
            init.num("east"), init.num("north"), init.num("heading"), init.num("speed"),
        )
        val gyro = g.doubles("gyro_z")
        val accel = g.doubles("accel_forward")
        val dt = g.num("dt")
        for (i in gyro.indices) f.propagate(gyro[i], accel[i], dt)

        assertArrayClose(g.doubles("state"), f.x, tol, "state")
        assertArrayClose(g.doubles("cov_diag"), f.cov.diagonal(), 1e-12, "cov diag")
    }

    // --------------------------------------------------------------- updates

    @Test
    fun `every measurement type matches python`() {
        val g = GoldenJson.load("updates")
        val init = g.obj("init")
        val f = KinematicEkf(
            init.num("east"), init.num("north"), init.num("heading"), init.num("speed"),
        )
        val expectedLog = g.arr("log")
        var logIndex = 0

        for (i in 0 until 30) {
            f.propagate(0.05, null, 0.1)
            if (i % 10 == 0) {
                val accepted = f.updatePosition(i.toDouble(), -i.toDouble() * 0.5)
                f.updateSpeed(9.0)
                f.updateCourse(0.2)
                val expected = expectedLog[logIndex++] as Map<*, *>
                assertEquals(
                    "position accepted at step $i",
                    expected.bool("position_accepted"), accepted,
                )
            }
        }
        f.updateCentripetal(-8.0 * 0.05, 0.05)
        val ackApplied = f.updateAckermann(0.5)

        assertEquals(g.bool("ackermann_applied"), ackApplied)
        assertArrayClose(g.doubles("state"), f.x, tol, "state")
        assertArrayClose(g.doubles("cov_diag"), f.cov.diagonal(), 1e-12, "cov diag")
        assertEquals(g.int("n_gps_accepted"), f.diagnostics.gpsAccepted)
        assertEquals(g.int("n_gps_rejected"), f.diagnostics.gpsRejected)
        assertEquals(g.int("n_centripetal"), f.diagnostics.centripetal)
        assertEquals(g.int("n_ackermann"), f.diagnostics.ackermann)
    }

    @Test
    fun `gate escape matches python`() {
        val g = GoldenJson.load("gate_escape")
        val f = KinematicEkf(0.0, 0.0, 0.0, 10.0)
        val expected = g.arr("accepted").map { it as Boolean }
        for (k in expected.indices) {
            assertEquals(
                "rejection $k", expected[k], f.updatePosition(5000.0, 5000.0),
            )
        }
        assertArrayClose(g.doubles("state"), f.x, tol, "state")
        assertEquals(g.int("n_gate_overrides"), f.diagnostics.gateOverrides)
    }

    @Test
    fun `ackermann bounds match python`() {
        val g = GoldenJson.load("ackermann")
        for (row in g.arr("cases")) {
            val c = row as Map<*, *>
            val f = KinematicEkf(0.0, 0.0, 0.0, c.num("speed_in"))
            val applied = f.updateAckermann(c.num("gyro_z"))
            val label = "speed=${c.num("speed_in")} gyro=${c.num("gyro_z")}"
            assertEquals("applied, $label", c.bool("applied"), applied)
            assertEquals("speed out, $label", c.num("speed_out"), f.speedMs, tol)
        }
    }

    // ----------------------------------------------------------------- blend

    @Test
    fun `reacquisition blend matches python`() {
        val g = GoldenJson.load("blend")
        val initial = g.doubles("initial_error")
        val b = BlendState(g.num("omega"))
        b.start(initial[0], initial[1])
        val dt = g.num("dt")

        val wanted = g.doubles("sample_indices").map { it.toInt() }
        val expected = g.arr("samples")
        var k = 0
        for (i in 0 until 200) {
            val e = b.step(dt)
            if (k < wanted.size && i == wanted[k]) {
                val want = (expected[k] as List<*>).map { (it as Number).toDouble() }
                assertArrayClose(want.toDoubleArray(), e, 1e-10, "blend step $i")
                k++
            }
        }
        assertEquals(g.bool("settled"), b.settled)
    }

    // ------------------------------------------------------------- alignment

    @Test
    fun `alignment matches python`() {
        val g = GoldenJson.load("alignment")
        val out = AlignmentEstimator.estimate(
            g.matrix("acc"), g.matrix("gyr"), g.doubles("speed_ms"), g.doubles("time_s"),
        )
        assertEquals("quality", g.num("quality"), out.quality, 1e-9)
        assertEquals("n samples", g.int("n_samples"), out.nSamples)
        val expected = g.matrix("rot_device_to_car")
        for (r in 0..2) {
            assertArrayClose(expected[r], out.rotDeviceToCar[r], 1e-9, "rot row $r")
        }
    }

    // -------------------------------------------------------------- features

    @Test
    fun `invariant features match python`() {
        val g = GoldenJson.load("features")
        val acc = g.matrix("acc")
        val gyr = g.matrix("gyr")
        val up = Features.gravityDirection(acc)
        assertArrayClose(g.doubles("up"), up, 1e-9, "up")

        val feat = Features.invariant(acc, gyr, up)
        val expected = g.matrix("features")
        assertEquals(expected.size, feat.size)
        for (r in expected.indices) {
            assertArrayClose(expected[r], feat[r], 1e-9, "feature row $r")
        }
    }

    // ----------------------------------------------------- guards, not parity

    @Test
    fun `chi square quantile is exact for two degrees of freedom`() {
        // The CDF for 2 dof is 1 - exp(-x/2), so the quantile is -2 ln(1 - p).
        assertEquals(11.618285980628052, KinematicEkf.chiSquare2dof(0.997), 1e-12)
    }

    @Test
    fun `covariance stays symmetric and positive definite over a long run`() {
        val f = KinematicEkf(0.0, 0.0, 0.3, 10.0)
        for (i in 0 until 2000) {
            f.propagate(0.02, null, 0.1)
            if (i % 90 == 0) {
                f.updatePosition(f.east + 1.0, f.north - 1.0)
                f.updateSpeed(10.0)
            }
        }
        for (r in 0 until KinematicEkf.DIM) {
            for (c in 0 until KinematicEkf.DIM) {
                assertEquals("asymmetry at $r,$c", f.cov[r, c], f.cov[c, r], 1e-12)
            }
            assertTrue("diagonal $r not positive", f.cov[r, r] > 0.0)
        }
    }

    @Test
    fun `positive gyro z is a left turn`() {
        // ENU is right-handed about up, so +omega_z decreases a clockwise
        // heading. Getting this backwards mirrors every turn and is invisible
        // on a straight road, which is most of any drive.
        val f = KinematicEkf(0.0, 0.0, 0.0, 10.0)
        repeat(10) { f.propagate(0.1, null, 0.1) }
        assertTrue("heading should decrease, got ${f.headingRad}", f.headingRad < 0)
    }
}
