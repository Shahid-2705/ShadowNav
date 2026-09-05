package com.shadownav.core

import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Detects that the vehicle is standing still, so dead reckoning can be told to
 * stop moving.
 *
 * Why this exists: on the first hardware run the phone sat on a desk, took a
 * weak 3-satellite indoor fix that reported 4.1 m/s, lost the fix, and then
 * dead-reckoned at 4.1 m/s indefinitely. Position ran away while sigma grew
 * honestly from 24 m to 33 m. The estimate was wrong and the filter had no way
 * to know, because with speed held and no GNSS there is nothing to contradict
 * it.
 *
 * The IMU knew. A phone at rest has specific-force magnitude pinned at g with
 * almost no variance and essentially zero angular rate. That is a free,
 * always-available observation and it is the vehicle-domain equivalent of the
 * foot-stance ZUPT that pedestrian systems use -- not the same mechanism, but
 * the same idea: exploit the moments when velocity is known exactly.
 *
 * Deliberately conservative. A false "stationary" during slow creeping traffic
 * would freeze the estimate and lose real distance, which is worse than the
 * drift it prevents. So it requires *both* quiet accelerometer and quiet
 * gyroscope, sustained for a dwell, and it releases immediately on the first
 * sign of motion.
 *
 * This is not the classical strapdown ZUPT that zeroes a full velocity vector;
 * the kinematic filter has a single scalar speed, so the update is a speed
 * measurement of zero with a tight sigma.
 */
class StationaryDetector(
    private val config: Config = Config(),
) {

    data class Config(
        /** Standard deviation of specific-force magnitude, m/s^2. Road
         *  vibration at idle is well above this on a running engine, so this
         *  detects "not moving", not "engine off". */
        val accelStdMax: Double = 0.35,
        /** How far the mean specific-force magnitude may sit from g.
         *
         *  Magnitude alone is a weak discriminator for *horizontal*
         *  acceleration, and it is worth being explicit about why: a 1.5 m/s^2
         *  forward push is perpendicular to gravity, so it lifts the magnitude
         *  only from 9.807 to 9.921. Magnitude catches vertical motion and
         *  large accelerations; the tilt check below is what catches the
         *  horizontal ones. */
        val gravityDeviationMax: Double = 0.5,
        /** Maximum tilt, in radians, between the current mean specific force
         *  and the reference vertical, when a reference is supplied.
         *
         *  This is the horizontal-acceleration detector. A forward acceleration
         *  a_h tilts the apparent vertical by atan(a_h / g), so 1.5 m/s^2 is
         *  8.7 degrees -- large and unambiguous against a trustworthy
         *  reference. 0.035 rad is 2 degrees, i.e. about 0.34 m/s^2. */
        val tiltMaxRad: Double = 0.035,
        /** Angular rate magnitude, rad/s. About 2.9 deg/s. */
        val gyroMax: Double = 0.05,
        /** Seconds the quiet condition must hold before declaring stationary.
         *  Long enough to reject a stop at traffic lights being confused with
         *  a smooth cruise, short enough to catch a real halt. */
        val dwellS: Double = 1.5,
        /** Samples retained for the variance estimate. At 400 Hz this is about
         *  0.5 s, which is a meaningful window without unbounded memory. */
        val window: Int = 200,
    )

    private val accelMag = DoubleArray(config.window)
    private val accelSum = DoubleArray(3)
    private val accelHistory = Array(config.window) { DoubleArray(3) }
    private var count = 0
    private var head = 0
    private var quietSinceS = Double.NaN

    var isStationary: Boolean = false
        private set

    /** Seconds the current stationary condition has held, or 0. */
    var heldForS: Double = 0.0
        private set

    // Last computed values, exposed so a field failure can be diagnosed from a
    // log rather than guessed at. Cheap, and this detector has already been
    // wrong twice for reasons that were invisible from its boolean output.
    var lastAccelStd: Double = Double.NaN
        private set
    var lastMeanMag: Double = Double.NaN
        private set
    var lastGyroMag: Double = Double.NaN
        private set
    var lastTiltRad: Double = Double.NaN
        private set

    /** Which condition blocked the last decision, for logging. */
    var lastBlocker: String = "warmup"
        private set

    /**
     * Feed one IMU sample.
     *
     * @param timeS monotonic seconds, from the sensor clock rather than wall
     *        clock, which is subject to NTP steps mid-drive.
     */
    fun update(
        accel: DoubleArray,
        gyro: DoubleArray,
        timeS: Double,
        referenceUp: DoubleArray? = null,
    ): Boolean {
        val mag = sqrt(accel[0] * accel[0] + accel[1] * accel[1] + accel[2] * accel[2])
        // Maintain a running vector sum so the mean direction is available
        // without rescanning the window.
        for (c in 0..2) accelSum[c] += accel[c] - accelHistory[head][c]
        accelHistory[head] = accel.copyOf()
        accelMag[head] = mag
        head = (head + 1) % config.window
        if (count < config.window) count++

        val gyroMag = sqrt(gyro[0] * gyro[0] + gyro[1] * gyro[1] + gyro[2] * gyro[2])

        if (count < config.window) {
            // Not enough history to judge variance. Report moving rather than
            // stationary: wrongly freezing the estimate is the worse error.
            isStationary = false
            heldForS = 0.0
            return false
        }

        var mean = 0.0
        for (i in 0 until count) mean += accelMag[i]
        mean /= count
        var variance = 0.0
        for (i in 0 until count) {
            val d = accelMag[i] - mean
            variance += d * d
        }
        val std = sqrt(variance / count)
        lastAccelStd = std
        lastMeanMag = mean
        lastGyroMag = gyroMag
        lastTiltRad = Double.NaN

        var quiet = true
        lastBlocker = "none"
        if (std > config.accelStdMax) {
            quiet = false
            lastBlocker = "accelStd"
        } else if (abs(mean - GRAVITY) > config.gravityDeviationMax) {
            quiet = false
            lastBlocker = "gravityMag"
        } else if (gyroMag > config.gyroMax) {
            quiet = false
            lastBlocker = "gyro"
        }

        // Tilt against a trusted vertical. This is what sees horizontal
        // acceleration, which the magnitude test above is nearly blind to.
        if (quiet && referenceUp != null) {
            val n = sqrt(accelSum[0] * accelSum[0] + accelSum[1] * accelSum[1] +
                accelSum[2] * accelSum[2])
            val rn = sqrt(referenceUp[0] * referenceUp[0] +
                referenceUp[1] * referenceUp[1] + referenceUp[2] * referenceUp[2])
            if (n > 1e-9 && rn > 1e-9) {
                val cosTilt = (accelSum[0] * referenceUp[0] +
                    accelSum[1] * referenceUp[1] +
                    accelSum[2] * referenceUp[2]) / (n * rn)
                val tilt = kotlin.math.acos(cosTilt.coerceIn(-1.0, 1.0))
                lastTiltRad = tilt
                if (tilt > config.tiltMaxRad) {
                    quiet = false
                    lastBlocker = "tilt"
                }
            }
        }

        if (!quiet) {
            // Blocker already recorded above.
            // Release immediately: the cost of a late release is real distance
            // lost, and motion is unambiguous when it appears.
            quietSinceS = Double.NaN
            isStationary = false
            heldForS = 0.0
            return false
        }

        if (quietSinceS.isNaN()) quietSinceS = timeS
        heldForS = timeS - quietSinceS
        isStationary = heldForS >= config.dwellS
        return isStationary
    }

    fun reset() {
        count = 0
        head = 0
        accelSum.fill(0.0)
        for (row in accelHistory) row.fill(0.0)
        quietSinceS = Double.NaN
        isStationary = false
        heldForS = 0.0
    }

    companion object {
        const val GRAVITY = 9.80665
    }
}
