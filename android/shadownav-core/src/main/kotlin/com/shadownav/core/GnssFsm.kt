package com.shadownav.core

import kotlin.math.hypot

/**
 * GNSS availability state machine with fiducial re-anchoring.
 *
 * A port of `shadownav/filter/fsm.py`.
 *
 *     GNSS_AIDED --degrading--> DEGRADED --lost--> DEAD_RECKONING
 *          ^                        |                    |
 *          +----------------- REACQUIRING <--------------+
 *
 * The four-mode machine itself is not novel; a competitor shipped an equivalent
 * one first. What is defensible here is the fiducial re-anchor and the
 * DEGRADED path -- in an urban canyon GNSS is never lost, so a lost/found
 * machine never leaves GNSS_AIDED while the receiver reports fixes that are
 * tens of metres wrong.
 */
enum class GnssMode { AIDED, DEGRADED, DEAD_RECKONING, REACQUIRING }

data class FsmConfig(
    val minSatsForFix: Int = 4,
    val degradedSats: Int = 6,
    val degradedCn0: Double = 28.0,
    val degradedAccuracyM: Double = 15.0,

    val enterDwellS: Double = 1.0,
    val exitDwellS: Double = 2.0,
    /** Entering REACQUIRING is deliberately fast: it is a safe state, and
     *  waiting the full exit dwell delays the blend the PS grades on. */
    val reacquireDwellS: Double = 0.3,

    /** Critically damped; omega = 2.3 rad/s settles in about 1.8 s, matching
     *  the presentation demo so live and offline behaviour agree. */
    val blendOmega: Double = 2.3,
    val blendSettleM: Double = 0.15,
)

data class GnssObservation(
    val available: Boolean,
    val nSatsUsed: Int = 0,
    val cn0Mean: Double = Double.NaN,
    val accuracyM: Double = Double.NaN,
)

/**
 * Position error driven to zero by a critically damped second-order spring.
 *
 * The *error* is the state, not the position. Two other formulations were tried
 * during the demo work and are wrong: springing the position toward a moving
 * target lags by 2v/omega, and recomputing the error after the truth advances
 * lags and then snaps at lock.
 */
class BlendState(private val omega: Double) {
    var error = doubleArrayOf(0.0, 0.0)
        private set
    private var rate = doubleArrayOf(0.0, 0.0)

    fun start(errorEast: Double, errorNorth: Double) {
        error = doubleArrayOf(errorEast, errorNorth)
        rate = doubleArrayOf(0.0, 0.0)
    }

    /** Advance and return the residual still to absorb. */
    fun step(dt: Double): DoubleArray {
        for (i in 0..1) {
            val accel = -2.0 * omega * rate[i] - omega * omega * error[i]
            rate[i] += accel * dt
            error[i] += rate[i] * dt
        }
        return error
    }

    val settled: Boolean get() = hypot(error[0], error[1]) < 0.15
}

class GnssFsm(val config: FsmConfig = FsmConfig()) {

    var mode: GnssMode = GnssMode.AIDED
        private set

    val blend = BlendState(config.blendOmega)

    private var pending: GnssMode? = null
    private var pendingSince = 0.0

    var timeSinceFixS = 0.0
        private set

    /** Last position accepted while healthy: the fiducial a blackout is
     *  re-anchored against. */
    var fiducialEast: Double? = null
        private set
    var fiducialNorth: Double? = null
        private set
    var fiducialTimeS: Double? = null
        private set

    val transitions = ArrayList<Pair<Double, GnssMode>>()

    private fun classify(obs: GnssObservation): GnssMode {
        if (!obs.available || obs.nSatsUsed < config.minSatsForFix) {
            return GnssMode.DEAD_RECKONING
        }
        val degraded = obs.nSatsUsed < config.degradedSats ||
            (obs.cn0Mean.isFinite() && obs.cn0Mean < config.degradedCn0) ||
            (obs.accuracyM.isFinite() && obs.accuracyM > config.degradedAccuracyM)
        return if (degraded) GnssMode.DEGRADED else GnssMode.AIDED
    }

    fun update(t: Double, obs: GnssObservation, dt: Double): GnssMode {
        var target = classify(obs)

        timeSinceFixS = if (obs.available && obs.nSatsUsed >= config.minSatsForFix) {
            0.0
        } else {
            timeSinceFixS + dt
        }

        // Leaving a blackout always goes through REACQUIRING, never straight to
        // AIDED: a direct jump is what produces the visible position snap.
        if (mode == GnssMode.DEAD_RECKONING &&
            (target == GnssMode.AIDED || target == GnssMode.DEGRADED)
        ) {
            target = GnssMode.REACQUIRING
        }

        if (mode == GnssMode.REACQUIRING) {
            if (target == GnssMode.DEAD_RECKONING) {
                commit(t, GnssMode.DEAD_RECKONING)
            } else if (blend.settled) {
                commit(t, if (target == GnssMode.REACQUIRING) GnssMode.AIDED else target)
            }
            return mode
        }

        if (target == mode) {
            pending = null
            return mode
        }

        val dwell = when (target) {
            GnssMode.DEAD_RECKONING -> config.enterDwellS
            GnssMode.REACQUIRING -> config.reacquireDwellS
            else -> config.exitDwellS
        }
        if (pending != target) {
            pending = target
            pendingSince = t
        } else if (t - pendingSince >= dwell) {
            commit(t, target)
        }
        return mode
    }

    private fun commit(t: Double, next: GnssMode) {
        if (next == mode) return
        mode = next
        pending = null
        transitions.add(t to next)
    }

    fun noteGoodFix(t: Double, east: Double, north: Double) {
        fiducialEast = east
        fiducialNorth = north
        fiducialTimeS = t
    }

    fun beginReacquisition(estEast: Double, estNorth: Double, fixEast: Double, fixNorth: Double) {
        blend.start(estEast - fixEast, estNorth - fixNorth)
    }

    val deadReckoning: Boolean
        get() = mode == GnssMode.DEAD_RECKONING || mode == GnssMode.REACQUIRING
}
