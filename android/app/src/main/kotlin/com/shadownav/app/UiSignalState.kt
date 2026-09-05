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
 *
 * `simulatedBlackout` is checked *before* `!hasFix` (real-device testing
 * during the map-upgrade task found the opposite order silently ate the
 * SIMULATE TUNNEL button's entire effect when tested indoors, where a real
 * fix never lands): holding that button is a deliberate, explicit user
 * action, and SIMULATED_BLACKOUT never asserts a real signal state the way
 * AIDED would, so there is no honesty reason to let "no fix yet" mask it.
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
    s.simulatedBlackout -> UiSignalState.SIMULATED_BLACKOUT
    !s.hasFix -> UiSignalState.ACQUIRING
    s.mode == GnssMode.AIDED -> UiSignalState.AIDED
    s.mode == GnssMode.DEGRADED -> UiSignalState.DEGRADED
    s.mode == GnssMode.REACQUIRING -> UiSignalState.REACQUIRING
    else -> UiSignalState.DEAD_RECKONING
}
