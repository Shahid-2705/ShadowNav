package com.shadownav.app

import android.location.Location
import com.shadownav.core.Alignment
import com.shadownav.core.AlignmentEstimator
import com.shadownav.core.Features
import com.shadownav.core.Geo
import com.shadownav.core.GnssFsm
import com.shadownav.core.GnssMode
import com.shadownav.core.GnssObservation
import com.shadownav.core.KinematicEkf
import com.shadownav.core.StationaryDetector
import kotlin.math.hypot
import kotlin.math.sqrt

/**
 * Ties sensor capture, GNSS and the estimator into one live pipeline.
 *
 * Mirrors `shadownav/pipeline_kinematic.py`. The estimator itself lives in
 * `shadownav-core`, which is proved numerically identical to the Python
 * implementation by the parity tests, so what this class contributes is only
 * plumbing and the alignment bootstrap.
 *
 * Thread model: [onImuSample] arrives on the sensor HandlerThread and
 * [onFix]/[onStatus] on the main thread, so all mutable state is guarded by
 * [lock]. Reads for the UI take a snapshot rather than holding the lock.
 */
class NavigationEngine {

    private val lock = Any()

    private var ekf: KinematicEkf? = null
    private val fsm = GnssFsm()

    private var refLat = Double.NaN
    private var refLon = Double.NaN

    private var lastImuNs = 0L
    private val stationary = StationaryDetector()
    private var alignment: Alignment = Alignment.identity()
    private var gravity = doubleArrayOf(0.0, 0.0, 1.0)
    private var gravityEstablished = false

    /** Rolling buffers used only to bootstrap the alignment, then trimmed.
     *  Bounded so a long drive cannot grow them without limit. */
    private val bufAcc = ArrayDeque<DoubleArray>()
    private val bufGyr = ArrayDeque<DoubleArray>()
    private val bufSpeed = ArrayDeque<Double>()
    private val bufTime = ArrayDeque<Double>()
    private var bufferSeconds = 0.0

    private var lastGnss = GnssCapture.Snapshot(0, 0, Double.NaN, 0, 0, Double.NaN, false)
    private var lastFixSpeed = Double.NaN
    private var lastFixBearing = Double.NaN
    private var elapsedS = 0.0

    private var distanceSinceLossM = 0.0
    private var lastEast = Double.NaN
    private var lastNorth = Double.NaN

    var minAlignmentQuality = 0.25

    private companion object {
        /** ~1 s at 400 Hz: enough for the vehicle's own accelerations to
         *  average out of the mean. */
        const val GRAVITY_MIN_SAMPLES = 400
        /** Re-estimate roughly every 2 s. The mounting can shift. */
        const val GRAVITY_REFRESH_SAMPLES = 800
    }

    data class Snapshot(
        val hasFix: Boolean,
        val mode: GnssMode,
        val eastM: Double,
        val northM: Double,
        val headingRad: Double,
        val speedMs: Double,
        val sigmaM: Double,
        val timeSinceFixS: Double,
        val distanceSinceLossM: Double,
        val alignmentQuality: Double,
        val aligned: Boolean,
        val stationary: Boolean,
        val stationaryDebug: String,
        val gnss: GnssCapture.Snapshot,
        val gpsAccepted: Int,
        val gpsRejected: Int,
        val gateOverrides: Int,
    )

    fun snapshot(): Snapshot = synchronized(lock) {
        val f = ekf
        val cov = f?.positionCovariance()
        // 1-sigma radius from the position covariance trace. Reported raw here;
        // the conformal inflation from shared/conformal.json is applied by the
        // UI so the number the user sees is the calibrated one.
        val sigma = if (cov != null) sqrt(0.5 * (cov[0, 0] + cov[1, 1])) else Double.NaN
        Snapshot(
            hasFix = f != null,
            mode = fsm.mode,
            eastM = f?.east ?: 0.0,
            northM = f?.north ?: 0.0,
            headingRad = f?.headingRad ?: 0.0,
            speedMs = f?.speedMs ?: 0.0,
            sigmaM = sigma,
            timeSinceFixS = fsm.timeSinceFixS,
            distanceSinceLossM = distanceSinceLossM,
            alignmentQuality = alignment.quality,
            aligned = alignment.quality >= minAlignmentQuality,
            stationary = stationary.isStationary,
            stationaryDebug = "std=%.3f mag=%.3f gyr=%.4f tilt=%.4f blk=%s held=%.1f".format(
                stationary.lastAccelStd, stationary.lastMeanMag,
                stationary.lastGyroMag, stationary.lastTiltRad,
                stationary.lastBlocker, stationary.heldForS,
            ),
            gnss = lastGnss,
            gpsAccepted = f?.diagnostics?.gpsAccepted ?: 0,
            gpsRejected = f?.diagnostics?.gpsRejected ?: 0,
            gateOverrides = f?.diagnostics?.gateOverrides ?: 0,
        )
    }

    // ------------------------------------------------------------------ IMU

    fun onImuSample(timestampNs: Long, accel: FloatArray, gyro: FloatArray) {
        synchronized(lock) {
            if (lastImuNs == 0L) {
                lastImuNs = timestampNs
                return
            }
            val dt = (timestampNs - lastImuNs) / 1e9
            lastImuNs = timestampNs
            // Reject absurd steps rather than integrating them: a suspended app
            // resuming produces a multi-second "dt" that would teleport the
            // estimate.
            if (dt <= 0.0 || dt > 0.5) return
            elapsedS += dt

            val a = doubleArrayOf(
                accel[0].toDouble(), accel[1].toDouble(), accel[2].toDouble(),
            )
            val g = doubleArrayOf(
                gyro[0].toDouble(), gyro[1].toDouble(), gyro[2].toDouble(),
            )
            pushBuffer(a, g, dt)

            // Gravity direction comes from the IMU alone and needs no fix.
            // It was previously only set in onFix, leaving the tilt reference
            // hardcoded to (0,0,1); unless the phone happened to lie perfectly
            // flat that rejected every sample and the detector never fired.
            if (bufAcc.size >= GRAVITY_MIN_SAMPLES &&
                (bufAcc.size % GRAVITY_REFRESH_SAMPLES == 0 || !gravityEstablished)
            ) {
                gravity = Features.gravityDirection(bufAcc.toTypedArray())
                gravityEstablished = true
            }

            // Whether the vehicle is standing still is a property of the IMU,
            // not of the filter, so this runs before the early return. Putting
            // it after meant it never ran until the first GNSS fix arrived --
            // and "no fix yet" is exactly when a stale speed does the damage.
            //
            // No reference is passed until gravity has actually been measured:
            // a guessed vertical would reject good samples, and reporting
            // "moving" when at rest is the failure this whole detector exists
            // to prevent.
            val atRest = stationary.update(
                a, g, elapsedS, if (gravityEstablished) gravity else null,
            )

            val f = ekf ?: return

            // Yaw rate needs only the gravity direction, not a full alignment,
            // so heading integration keeps working on a straight constant-speed
            // approach where the forward axis is unobservable.
            val yawRate = if (alignment.quality >= minAlignmentQuality) {
                alignment.apply(g)[2]
            } else {
                g[0] * gravity[0] + g[1] * gravity[1] + g[2] * gravity[2]
            }

            // Forward acceleration is off by default: measured to hurt at 10 Hz
            // offline. Re-enable only after the ablation is re-run on device.
            f.propagate(yawRate, null, dt)
            f.updateAckermann(yawRate)

            // Zero-velocity update. Without this a phone at rest holding a bad
            // speed from a weak fix dead-reckons away forever: observed on
            // hardware running at 4.1 m/s on a desk while sigma grew from 24 m
            // to 33 m. The IMU knew all along.
            if (atRest) f.updateSpeed(0.0, sigma = 0.05)

            if (!lastEast.isNaN() && fsm.deadReckoning) {
                distanceSinceLossM += hypot(f.east - lastEast, f.north - lastNorth)
            }
            lastEast = f.east
            lastNorth = f.north

            val obs = GnssObservation(
                available = fsm.timeSinceFixS < 2.0,
                nSatsUsed = lastGnss.satellitesUsed,
                cn0Mean = lastGnss.meanCn0,
                accuracyM = Double.NaN,
            )
            val before = fsm.mode
            val mode = fsm.update(elapsedS, obs, dt)
            if (before == GnssMode.DEAD_RECKONING && mode != GnssMode.REACQUIRING) {
                distanceSinceLossM = 0.0
            }
            if (mode == GnssMode.REACQUIRING) fsm.blend.step(dt)
        }
    }

    private fun pushBuffer(a: DoubleArray, g: DoubleArray, dt: Double) {
        bufAcc.addLast(a)
        bufGyr.addLast(g)
        bufSpeed.addLast(lastFixSpeed)
        bufTime.addLast(elapsedS)
        bufferSeconds += dt
        // Two minutes is enough to observe the forward axis and bounded enough
        // that memory stays flat on a low-end device.
        while (bufferSeconds > 120.0 && bufAcc.size > 2) {
            bufAcc.removeFirst(); bufGyr.removeFirst()
            bufSpeed.removeFirst()
            val t0 = bufTime.removeFirst()
            bufferSeconds = elapsedS - (bufTime.firstOrNull() ?: t0)
        }
    }

    // ----------------------------------------------------------------- GNSS

    fun onStatus(snapshot: GnssCapture.Snapshot) {
        synchronized(lock) { lastGnss = snapshot }
    }

    fun onFix(location: Location) {
        synchronized(lock) {
            if (refLat.isNaN()) {
                refLat = location.latitude
                refLon = location.longitude
            }
            val en = Geo.pointToEnu(location.latitude, location.longitude, refLat, refLon)
            lastFixSpeed = if (location.hasSpeed()) location.speed.toDouble() else Double.NaN
            lastFixBearing = if (location.hasBearing()) {
                Math.toRadians(location.bearing.toDouble())
            } else {
                Double.NaN
            }

            val f = ekf
            if (f == null) {
                ekf = KinematicEkf(
                    en[0], en[1],
                    if (lastFixBearing.isNaN()) 0.0 else lastFixBearing,
                    if (lastFixSpeed.isNaN()) 0.0 else lastFixSpeed,
                )
                gravity = Features.gravityDirection(bufAcc.toTypedArray())
                return
            }

            if (fsm.mode == GnssMode.DEAD_RECKONING) {
                fsm.beginReacquisition(f.east, f.north, en[0], en[1])
            }

            val accuracy = if (location.hasAccuracy()) {
                location.accuracy.toDouble()
            } else {
                null
            }
            val accepted = f.updatePosition(en[0], en[1], accuracy, lastGnss.meanCn0)
            if (!lastFixSpeed.isNaN()) f.updateSpeed(lastFixSpeed)
            if (!lastFixBearing.isNaN()) f.updateCourse(lastFixBearing)
            if (accepted) fsm.noteGoodFix(elapsedS, f.east, f.north)

            refreshAlignment()
        }
    }

    /**
     * Re-estimate the device-to-car rotation from buffered aided driving.
     *
     * Applying the nonholonomic constraint or reading forward/lateral
     * accelerometer channels in the phone's frame rather than the car's was
     * measured four times *worse* than not doing it at all, so this gates them.
     */
    private fun refreshAlignment() {
        if (bufAcc.size < 200) return
        gravity = Features.gravityDirection(bufAcc.toTypedArray())
        val speeds = bufSpeed.toDoubleArray()
        if (speeds.count { !it.isNaN() } < 30) return
        alignment = AlignmentEstimator.estimate(
            bufAcc.toTypedArray(), bufGyr.toTypedArray(), speeds, bufTime.toDoubleArray(),
        )
    }

    private fun ArrayDeque<Double>.toDoubleArray(): DoubleArray =
        DoubleArray(size) { this.elementAt(it) }

    fun reset() {
        synchronized(lock) {
            ekf = null
            refLat = Double.NaN
            refLon = Double.NaN
            lastImuNs = 0L
            elapsedS = 0.0
            distanceSinceLossM = 0.0
            lastEast = Double.NaN
            lastNorth = Double.NaN
            alignment = Alignment.identity()
            gravityEstablished = false
            stationary.reset()
            bufAcc.clear(); bufGyr.clear(); bufSpeed.clear(); bufTime.clear()
            bufferSeconds = 0.0
        }
    }
}
