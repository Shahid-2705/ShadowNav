package com.shadownav.app

import com.shadownav.core.GnssMode
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Covers every branch of [uiState] -- the function [StatusChip] and
 * [FilamentOrbView] both consume so they can't disagree (blueprint Step 2,
 * FIX-6). No Android dependency: [NavigationEngine.Snapshot] is a plain
 * data class, so this is plain JUnit like [RenderTierTest].
 */
class UiSignalStateTest {

    private fun snapshot(
        hasFix: Boolean = true,
        mode: GnssMode = GnssMode.AIDED,
        simulatedBlackout: Boolean = false,
    ) = NavigationEngine.Snapshot(
        hasFix = hasFix,
        mode = mode,
        eastM = 0.0,
        northM = 0.0,
        headingRad = 0.0,
        speedMs = 0.0,
        sigmaM = Double.NaN,
        timeSinceFixS = 0.0,
        distanceSinceLossM = 0.0,
        alignmentQuality = 0.0,
        aligned = false,
        stationary = false,
        stationaryDebug = "",
        simulatedBlackout = simulatedBlackout,
        tripDistanceM = 0.0,
        tripMaxDrDistanceM = 0.0,
        tripTimeInDrS = 0.0,
        tripDurationS = 0.0,
        gnss = GnssCapture.Snapshot(0, 0, Double.NaN, 0, 0, Double.NaN, false),
        gpsAccepted = 0,
        gpsRejected = 0,
        gateOverrides = 0,
    )

    @Test
    fun `no fix yet is ACQUIRING even though mode defaults to AIDED`() {
        // The exact case FIX-6 exists for: mode reads its initial AIDED value
        // before any fix has ever landed, and must not be shown as locked.
        assertEquals(UiSignalState.ACQUIRING, uiState(snapshot(hasFix = false, mode = GnssMode.AIDED)))
    }

    @Test
    fun `simulated blackout wins over the underlying mode`() {
        assertEquals(
            UiSignalState.SIMULATED_BLACKOUT,
            uiState(snapshot(hasFix = true, mode = GnssMode.AIDED, simulatedBlackout = true)),
        )
    }

    @Test
    fun `aided mode with a fix is GNSS AIDED`() {
        assertEquals(UiSignalState.AIDED, uiState(snapshot(mode = GnssMode.AIDED)))
    }

    @Test
    fun `degraded mode maps through`() {
        assertEquals(UiSignalState.DEGRADED, uiState(snapshot(mode = GnssMode.DEGRADED)))
    }

    @Test
    fun `reacquiring mode maps through`() {
        assertEquals(UiSignalState.REACQUIRING, uiState(snapshot(mode = GnssMode.REACQUIRING)))
    }

    @Test
    fun `dead reckoning mode maps through`() {
        assertEquals(UiSignalState.DEAD_RECKONING, uiState(snapshot(mode = GnssMode.DEAD_RECKONING)))
    }
}
