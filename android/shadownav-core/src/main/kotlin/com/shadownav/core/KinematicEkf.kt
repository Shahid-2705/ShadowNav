package com.shadownav.core

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Five-state 2D vehicle dead-reckoning filter: east, north, heading, speed,
 * gyro bias.
 *
 * A direct port of `shadownav/filter/kinematic.py`. It never double-integrates
 * acceleration -- heading comes from integrating the gyroscope and speed is
 * held. On the phone the IMU runs at 100-200 Hz rather than the 10 Hz of the
 * offline dataset, so the 21-state strapdown becomes viable again; until that
 * is measured on hardware this is the estimator that has evidence behind it.
 *
 * Sign convention, stated because getting it wrong mirrors every turn and is
 * invisible on straight roads: ENU is right-handed about up and `psi` is
 * clockwise from north, so a positive gyro z (counter-clockwise seen from
 * above) *decreases* psi.
 */
class KinematicEkf(
    east: Double,
    north: Double,
    headingRad: Double,
    speedMs: Double,
    val config: KinematicConfig = KinematicConfig(),
) {

    /** `[east, north, heading, speed, gyroBias]`. */
    val x: DoubleArray = doubleArrayOf(east, north, Geo.wrap(headingRad), speedMs, 0.0)

    var cov: Mat = Mat.diag(
        doubleArrayOf(
            config.p0Pos * config.p0Pos,
            config.p0Pos * config.p0Pos,
            config.p0Psi * config.p0Psi,
            config.p0Speed * config.p0Speed,
            config.p0BiasGyro * config.p0BiasGyro,
        )
    )
        private set

    val diagnostics = Diagnostics()

    val east: Double get() = x[I_E]
    val north: Double get() = x[I_N]
    val headingRad: Double get() = x[I_PSI]
    val speedMs: Double get() = x[I_V]
    val gyroBias: Double get() = x[I_BW]

    /** Top-left 2x2 of the covariance: horizontal position uncertainty. */
    fun positionCovariance(): Mat = Mat(
        2, 2, doubleArrayOf(cov[0, 0], cov[0, 1], cov[1, 0], cov[1, 1])
    )

    // ---------------------------------------------------------------- propagate

    /** One step. [accelForward] is null when the device-to-car alignment is
     *  not observable, in which case speed is held. */
    fun propagate(gyroZ: Double, accelForward: Double?, dt: Double) {
        if (dt <= 0.0) return
        val psi = x[I_PSI]
        val v = x[I_V]
        val rate = -(gyroZ - x[I_BW])

        val f = Mat.identity(DIM)
        f[I_E, I_PSI] = v * cos(psi) * dt
        f[I_E, I_V] = sin(psi) * dt
        f[I_N, I_PSI] = -v * sin(psi) * dt
        f[I_N, I_V] = cos(psi) * dt
        f[I_PSI, I_BW] = dt

        x[I_E] += v * sin(psi) * dt
        x[I_N] += v * cos(psi) * dt
        x[I_PSI] = Geo.wrap(psi + rate * dt)
        if (accelForward != null && accelForward.isFinite()) {
            x[I_V] = maxOf(0.0, v + accelForward * dt)
        }

        val q = Mat.diag(
            doubleArrayOf(
                config.sigmaPos * config.sigmaPos * dt,
                config.sigmaPos * config.sigmaPos * dt,
                config.sigmaGyro * config.sigmaGyro * dt,
                config.sigmaAccel * config.sigmaAccel * dt,
                config.sigmaBiasGyro * config.sigmaBiasGyro * dt,
            )
        )
        cov = (f * cov * f.transpose() + q).symmetrised()
    }

    // ------------------------------------------------------------------ update

    private fun update(innovation: DoubleArray, h: Mat, r: Mat): Double {
        val ht = h.transpose()
        val s = h * cov * ht + r
        val sInv = s.inverseSmall()

        val innov = Mat.column(innovation)
        val nis = (innov.transpose() * sInv * innov)[0, 0]

        val k = cov * ht * sInv
        val dx = k * innov
        for (i in 0 until DIM) x[i] += dx[i, 0]
        x[I_PSI] = Geo.wrap(x[I_PSI])
        x[I_V] = maxOf(0.0, x[I_V])

        // Joseph form. Repeated small updates over a three-minute outage break
        // positive-definiteness under the simple (I - KH)P form.
        val a = Mat.identity(DIM) - k * h
        cov = (a * cov * a.transpose() + k * r * k.transpose()).symmetrised()
        return nis
    }

    fun updateSpeed(speedMs: Double, sigma: Double = config.sigmaGpsSpeed) {
        val h = Mat(1, DIM)
        h[0, I_V] = 1.0
        update(doubleArrayOf(speedMs - x[I_V]), h, Mat(1, 1, doubleArrayOf(sigma * sigma)))
    }

    /**
     * Zero Angular Rate Update (ZARU) for continuous gyro bias estimation at rest.
     * When stationary, vehicle yaw rate is 0. Any measured angular rate about vertical is pure bias:
     * `y = gyroZ - x[I_BW]`.
     */
    fun updateZeroAngularRate(gyroZ: Double, sigma: Double = 0.001) {
        val h = Mat(1, DIM)
        h[0, I_BW] = 1.0
        update(doubleArrayOf(gyroZ - x[I_BW]), h, Mat(1, 1, doubleArrayOf(sigma * sigma)))
    }

    /** Heading from GNSS course. Ignored at low speed, where a receiver
     *  reports an essentially random course. */
    fun updateCourse(courseRad: Double, sigma: Double = config.sigmaGpsCourse) {
        if (x[I_V] < config.minSpeedForCourse) return
        val h = Mat(1, DIM)
        h[0, I_PSI] = 1.0
        update(
            doubleArrayOf(Geo.wrap(courseRad - x[I_PSI])), h,
            Mat(1, 1, doubleArrayOf(sigma * sigma)),
        )
    }

    /**
     * The centripetal observation: `a_lat = -v * (omega_z - bias)`.
     *
     * Every turn becomes an independent observation of speed that does not
     * involve integrating accelerometer noise. Skipped in near-straight
     * driving, where the Jacobian with respect to speed vanishes and the update
     * is pure noise.
     *
     * Measured to *hurt* on 10 Hz offline data, where the lateral channel is
     * aliased; kept off by default until re-measured at 100-200 Hz.
     */
    fun updateCentripetal(
        accelLateral: Double, gyroZ: Double, sigma: Double = config.sigmaCentripetal,
    ) {
        val rate = gyroZ - x[I_BW]
        if (abs(rate) < 0.02) return
        val v = x[I_V]
        val h = Mat(1, DIM)
        h[0, I_V] = -rate
        h[0, I_BW] = v
        update(
            doubleArrayOf(accelLateral - (-v * rate)), h,
            Mat(1, 1, doubleArrayOf(sigma * sigma)),
        )
        diagnostics.centripetal++
    }

    /**
     * Bound speed by what a road vehicle can do while turning. Neither bound
     * needs a wheelbase, which a phone cannot know.
     *
     * The two are gated differently on purpose. The slip gate applies to the
     * *curvature* bound, a steering-geometry statement. Applying it to the
     * *friction* bound is circular -- that bound says lateral acceleration
     * cannot exceed mu*g = 7.85 m/s^2 while the gate rejects anything above
     * 0.5 g = 4.9 m/s^2, so every violation would be filtered out before the
     * bound could fire. Friction is the physics that defines the slip limit and
     * applies unconditionally.
     */
    fun updateAckermann(gyroZ: Double, sigma: Double = config.sigmaAckermann): Boolean {
        val rate = abs(gyroZ - x[I_BW])
        if (rate < 0.05) return false
        val v = x[I_V]
        val lateral = abs(v * rate)

        var target: Double? = null
        val upper = config.frictionMu * GRAVITY / rate
        if (v > upper) {
            target = upper
        } else if (lateral <= config.ackermannMaxLateralG * GRAVITY) {
            val lower = rate / config.curvatureMax
            if (lower <= upper && v < lower) target = lower
        }
        if (target == null) return false

        val h = Mat(1, DIM)
        h[0, I_V] = 1.0
        update(doubleArrayOf(target - v), h, Mat(1, 1, doubleArrayOf(sigma * sigma)))
        diagnostics.ackermann++
        return true
    }

    /**
     * Chi-square gated position update with C/N0 de-weighting.
     *
     * The gate is the urban-canyon defence: there GNSS is never lost, it lies,
     * so an outage state machine never fires and a filter that trusts every fix
     * inherits tens of metres of NLOS error.
     */
    fun updatePosition(
        eastM: Double, northM: Double, sigmaM: Double? = null, cn0Mean: Double? = null,
    ): Boolean {
        var s = maxOf(sigmaM ?: config.sigmaGpsPos, config.sigmaGpsPos)
        if (cn0Mean != null && cn0Mean.isFinite()) {
            s *= (1.0 + (35.0 - cn0Mean) / 10.0).coerceIn(1.0, 6.0)
        }

        val h = Mat(2, DIM)
        h[0, I_E] = 1.0
        h[1, I_N] = 1.0
        val innovation = doubleArrayOf(eastM - x[I_E], northM - x[I_N])
        val r = Mat.diag(doubleArrayOf(s * s, s * s))

        val sMat = h * cov * h.transpose() + r
        val innov = Mat.column(innovation)
        val nis = (innov.transpose() * sMat.inverseSmall() * innov)[0, 0]
        diagnostics.lastNis = nis

        if (nis > chiSquare2dof(config.gateConfidence)) {
            diagnostics.gpsRejected++
            diagnostics.consecutiveRejections++
            if (diagnostics.consecutiveRejections >= config.maxConsecutiveRejections) {
                // Persistent rejection means the filter is wrong, not the fix.
                // Without this escape a diverged filter rejects every fix
                // forever -- a shipped competitor bug that trapped their engine
                // in dead reckoning for over two hours.
                reanchor(eastM, northM)
                diagnostics.gateOverrides++
                diagnostics.consecutiveRejections = 0
            }
            return false
        }

        update(innovation, h, r)
        diagnostics.gpsAccepted++
        diagnostics.consecutiveRejections = 0
        return true
    }

    fun reanchor(eastM: Double, northM: Double) {
        x[I_E] = eastM
        x[I_N] = northM
        val p = config.p0Pos * config.p0Pos
        cov[0, 0] = p
        cov[1, 1] = p
        cov[0, 1] = 0.0
        cov[1, 0] = 0.0
    }

    class Diagnostics {
        var gpsAccepted = 0
        var gpsRejected = 0
        var gateOverrides = 0
        var consecutiveRejections = 0
        var centripetal = 0
        var ackermann = 0
        var lastNis = 0.0
    }

    companion object {
        const val DIM = 5
        const val I_E = 0
        const val I_N = 1
        const val I_PSI = 2
        const val I_V = 3
        const val I_BW = 4
        const val GRAVITY = 9.80665

        /**
         * Chi-square quantile with 2 degrees of freedom, in closed form.
         *
         * For 2 dof the CDF is `1 - exp(-x/2)`, so the quantile is
         * `-2 ln(1 - p)`. No statistics dependency needed, and it is exact
         * rather than tabulated. At p = 0.997 this is 11.62.
         */
        fun chiSquare2dof(p: Double): Double = -2.0 * ln(1.0 - p)
    }
}

data class KinematicConfig(
    // Process noise, per sqrt(second).
    val sigmaGyro: Double = 3.0e-3,
    val sigmaAccel: Double = 0.35,
    val sigmaBiasGyro: Double = 2.0e-5,
    val sigmaPos: Double = 0.05,

    // Measurements.
    val sigmaGpsPos: Double = 4.0,
    val sigmaGpsSpeed: Double = 0.5,
    val sigmaGpsCourse: Double = 0.09,
    val sigmaLearnedSpeed: Double = 1.0,
    val sigmaCentripetal: Double = 0.6,
    val sigmaAckermann: Double = 1.5,

    // Initial uncertainty.
    val p0Pos: Double = 5.0,
    val p0Psi: Double = 0.15,
    val p0Speed: Double = 1.5,
    val p0BiasGyro: Double = 0.01,

    /** 0.28 /m is a 3.6 m turning radius, which covers cars. */
    val curvatureMax: Double = 0.28,
    /** Dry asphalt. */
    val frictionMu: Double = 0.8,
    /** Past this the bicycle model breaks down as the tyres slip. */
    val ackermannMaxLateralG: Double = 0.5,

    val gateConfidence: Double = 0.997,
    val maxConsecutiveRejections: Int = 3,
    val minSpeedForCourse: Double = 2.0,
)
