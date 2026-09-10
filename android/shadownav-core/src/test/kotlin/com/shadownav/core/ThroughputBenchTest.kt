package com.shadownav.core

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.util.Locale
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlin.random.Random

/**
 * Desktop JVM throughput proxy for the edge engine.
 *
 * The problem statement asks for an engine that can run on a phone at the
 * IMU's native rate; the moto g64 delivers 401 Hz. No benchmark existed, so
 * this feeds the same three components the app runs per IMU sample --
 * [KinematicEkf], [GnssFsm] and [StationaryDetector] -- a synthetic 401 Hz
 * stream for 60 simulated seconds with a GNSS position/speed/course update
 * every second and a 15 s blackout in the middle, and times it after a 5 s
 * warm-up.
 *
 * This is a measurement, not a pass/fail gate: the only assertion is that
 * it ran. The result is written to `eval/results/core_throughput_desktop.json`
 * and is labelled a desktop proxy there. A desktop JIT on an x86 core is not a
 * low-end ARM core; the number bounds the algorithmic cost, nothing more.
 */
class ThroughputBenchTest {

    private companion object {
        const val RATE_HZ = 401.0
        const val DT = 1.0 / RATE_HZ
        const val WARMUP_S = 5.0
        const val MEASURED_S = 60.0
        const val BLACKOUT_START_S = 30.0
        const val BLACKOUT_END_S = 45.0
        const val SPEED_MS = 12.0
        const val SEED = 20260905
    }

    /** One synthetic drive plus the three components, so warm-up and the
     *  measured run share exactly the same per-sample work. */
    private class Rig(seed: Int) {
        val ekf = KinematicEkf(0.0, 0.0, 0.0, SPEED_MS)
        val fsm = GnssFsm()
        val detector = StationaryDetector()
        val random = Random(seed)
        val gravity = doubleArrayOf(0.0, 0.0, 1.0)
        val accel = DoubleArray(3)
        val gyro = DoubleArray(3)
        var heading = 0.0
        var east = 0.0
        var north = 0.0
        var t = 0.0
        var sinceFix = 0.0
        var reacqPending = false
        var samples = 0L

        fun step() {
            t += DT
            // Slow S-bend so the Ackermann bound and the heading integration
            // both have something to do. Positive gyro z is a left turn.
            val yawRate = 0.15 * sin(2.0 * PI * t / 20.0)
            heading -= yawRate * DT
            east += SPEED_MS * sin(heading) * DT
            north += SPEED_MS * cos(heading) * DT

            accel[0] = -SPEED_MS * yawRate + 0.05 * random.nextDouble(-1.0, 1.0)
            accel[1] = 0.05 * random.nextDouble(-1.0, 1.0)
            accel[2] = StationaryDetector.GRAVITY + 0.05 * random.nextDouble(-1.0, 1.0)
            gyro[0] = 0.002 * random.nextDouble(-1.0, 1.0)
            gyro[1] = 0.002 * random.nextDouble(-1.0, 1.0)
            gyro[2] = yawRate + 0.002 * random.nextDouble(-1.0, 1.0)

            val atRest = detector.update(accel, gyro, t, gravity)
            ekf.propagate(gyro[2], null, DT)
            ekf.updateAckermann(gyro[2])
            if (atRest) ekf.updateSpeed(0.0, sigma = 0.05)

            val blackout = t >= BLACKOUT_START_S && t < BLACKOUT_END_S
            sinceFix += DT
            if (!blackout && sinceFix >= 1.0) {
                sinceFix = 0.0
                if (fsm.mode == GnssMode.DEAD_RECKONING || reacqPending) {
                    fsm.beginReacquisition(ekf.east, ekf.north, east, north)
                    ekf.reanchor(east, north)
                    reacqPending = false
                }
                val accepted = ekf.updatePosition(east, north, 4.0, 35.0)
                ekf.updateSpeed(SPEED_MS)
                ekf.updateCourse(heading)
                if (accepted) fsm.noteGoodFix(t, ekf.east, ekf.north)
            }
            val obs = GnssObservation(
                available = !blackout && sinceFix < 2.0, nSatsUsed = 12,
                cn0Mean = 35.0, accuracyM = 4.0,
            )
            val before = fsm.mode
            val mode = fsm.update(t, obs, DT)
            if (before == GnssMode.DEAD_RECKONING && mode == GnssMode.REACQUIRING) {
                reacqPending = true
            }
            if (!fsm.blend.settled) fsm.blend.step(DT)
            samples++
        }
    }

    @Test
    fun `engine throughput on this JVM`() {
        val rig = Rig(SEED)
        val warmupSamples = (WARMUP_S * RATE_HZ).toInt()
        repeat(warmupSamples) { rig.step() }

        val measuredSamples = (MEASURED_S * RATE_HZ).toInt()
        val t0 = System.nanoTime()
        repeat(measuredSamples) { rig.step() }
        val elapsedNs = System.nanoTime() - t0

        val elapsedS = elapsedNs / 1e9
        val samplesPerSecond = measuredSamples / elapsedS
        val usPerSample = elapsedNs / 1e3 / measuredSamples
        val realtimeRatio = samplesPerSecond / RATE_HZ

        val report = String.format(
            Locale.US,
            "core throughput (desktop JVM proxy): %d samples in %.3f s = " +
                "%.0f samples/s, %.2f us/sample, %.0fx the %.0f Hz real-time budget",
            measuredSamples, elapsedS, samplesPerSecond, usPerSample, realtimeRatio, RATE_HZ,
        )
        println(report)
        println("final state: mode=${rig.fsm.mode} east=${rig.ekf.east} north=${rig.ekf.north}")

        writeJson(measuredSamples, elapsedS, samplesPerSecond, usPerSample, realtimeRatio)

        assertTrue("engine produced no samples", rig.samples == (warmupSamples + measuredSamples).toLong())
        assertTrue("state is not finite", rig.ekf.east.isFinite() && rig.ekf.north.isFinite())
    }

    private fun writeJson(
        samples: Int, elapsedS: Double, samplesPerSecond: Double,
        usPerSample: Double, realtimeRatio: Double,
    ) {
        val out = resultsDir()?.resolve("core_throughput_desktop.json")
        if (out == null) {
            println("eval/results not found above ${File("").absolutePath}; JSON not written")
            return
        }
        val cpu = System.getenv("PROCESSOR_IDENTIFIER") ?: System.getProperty("os.arch")
        val json = """
            |{
            |  "note": "desktop JVM proxy, not on-device",
            |  "components": ["KinematicEkf", "GnssFsm", "StationaryDetector"],
            |  "stream": "synthetic 401 Hz IMU, GNSS position/speed/course every 1 s, 15 s blackout",
            |  "rate_hz": ${fmt(RATE_HZ)},
            |  "warmup_s": ${fmt(WARMUP_S)},
            |  "simulated_s": ${fmt(MEASURED_S)},
            |  "samples": $samples,
            |  "elapsed_s": ${fmt(elapsedS)},
            |  "samples_per_second": ${fmt(samplesPerSecond)},
            |  "us_per_sample": ${fmt(usPerSample)},
            |  "realtime_ratio": ${fmt(realtimeRatio)},
            |  "budget_us_per_sample": ${fmt(1e6 / RATE_HZ)},
            |  "jvm": "${esc(System.getProperty("java.vm.name"))} ${esc(System.getProperty("java.version"))}",
            |  "jvm_vendor": "${esc(System.getProperty("java.vendor"))}",
            |  "os": "${esc(System.getProperty("os.name"))} ${esc(System.getProperty("os.version"))}",
            |  "cpu": "${esc(cpu)}",
            |  "cpu_arch": "${esc(System.getProperty("os.arch"))}",
            |  "available_processors": ${Runtime.getRuntime().availableProcessors()},
            |  "threads": 1,
            |  "seed": $SEED
            |}
            |""".trimMargin()
        out.writeText(json)
        println("wrote ${out.absolutePath}")
    }

    /** Gradle runs tests with the module directory as the working directory;
     *  walk up until the repository's `eval/results` appears. */
    private fun resultsDir(): File? {
        var dir: File? = File("").absoluteFile
        while (dir != null) {
            val candidate = File(dir, "eval/results")
            if (candidate.isDirectory) return candidate
            dir = dir.parentFile
        }
        return null
    }

    private fun fmt(v: Double): String = String.format(Locale.US, "%.6f", v)

    private fun esc(s: String?): String =
        (s ?: "unknown").replace("\\", "\\\\").replace("\"", "\\\"")
}
