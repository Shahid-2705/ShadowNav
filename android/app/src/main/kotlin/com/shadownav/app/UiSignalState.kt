package com.shadownav.app

import com.shadownav.core.GnssMode

/**
 * The six states the UI actually distinguishes -- one more than
 * [com.shadownav.core.GnssMode] has, because [uiState] also covers "no fix
 * yet" and the simulated-blackout demo affordance.
 *
 * This used to be inlined as a `when` block inside [MainActivity.render]
 * that only [StatusChip] consumed. Extracting it here means the Filament
 * status orb ([FilamentOrbView], blueprint Step 2) reads the exact same
 * state instead of re-deriving its own -- the chip and the orb can no longer
 * disagree about what's currently true, which matters because
 * `!s.hasFix -> "ACQUIRING"` exists specifically to avoid asserting a GNSS
 * lock before any fix has ever arrived (see the comment this replaced).
 */
enum class UiSignalState(val label: String, val colour: Int) {
    ACQUIRING("ACQUIRING", Palette.SLATE),
    SIMULATED_BLACKOUT("SIMULATED BLACKOUT", Palette.MAGENTA),
    AIDED("GNSS AIDED", Palette.CYAN),
    DEGRADED("DEGRADED", Palette.AMBER),
    REACQUIRING("REACQUIRING", Palette.AMBER),
    DEAD_RECKONING("DEAD RECKONING", Palette.MAGENTA),
}

fun uiState(s: NavigationEngine.Snapshot): UiSignalState = when {
    !s.hasFix -> UiSignalState.ACQUIRING
    s.simulatedBlackout -> UiSignalState.SIMULATED_BLACKOUT
    s.mode == GnssMode.AIDED -> UiSignalState.AIDED
    s.mode == GnssMode.DEGRADED -> UiSignalState.DEGRADED
    s.mode == GnssMode.REACQUIRING -> UiSignalState.REACQUIRING
    else -> UiSignalState.DEAD_RECKONING
}
