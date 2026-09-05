package com.shadownav.app

/**
 * The three rendering tiers a device can be placed in, mirroring
 * `demo/gnss-demo.html`'s HIGH / LOW / Canvas2D-fallback shape (see
 * `demo/README.md`, "Performance and fallbacks").
 *
 * [CANVAS_2D] is not a degraded mode to apologise for -- it is today's exact,
 * already-shipping [TrackView] and [StatusChip] behaviour, unmodified. Nothing
 * in this project regresses below it.
 */
sealed interface RenderTier {
    data object Full3D : RenderTier
    data object Reduced3D : RenderTier
    data object Canvas2D : RenderTier

    companion object {
        fun fromStoredName(name: String?): RenderTier? = when (name) {
            Full3D.javaClass.simpleName -> Full3D
            Reduced3D.javaClass.simpleName -> Reduced3D
            Canvas2D.javaClass.simpleName -> Canvas2D
            else -> null
        }

        fun storedName(tier: RenderTier): String = tier.javaClass.simpleName
    }
}

/**
 * Raw inputs to the tier decision. Deliberately a plain data class with no
 * Android imports: the *measurement* of these values needs the framework
 * (see [DeviceCapabilityProbe]), but the *decision* does not, and keeping it
 * separate is what makes [decideRenderTier] testable with plain JUnit -- no
 * Robolectric, matching how `shadownav-core` stays pure-JVM on purpose.
 *
 * [offscreenFrameMs] must come from an unthrottled, off-screen render of a
 * fixed amount of GPU work, not a displayed frame's wall-clock interval: on
 * a 60 Hz display every *presented* frame is ~16.7 ms whether the GPU has 2 ms
 * or 15 ms of headroom, which would make this measurement useless for
 * discriminating devices. See `plans/shadownav-3d-mvp-web-deck.md` Step 1,
 * task 6 (FIX-8) for why this distinction matters.
 */
data class CapabilityMeasurements(
    val offscreenFrameMs: Double,
    val totalRamMb: Long,
    val cpuCores: Int,
)

/**
 * Thresholds are a starting estimate, not a calibrated result -- Step 5 of
 * the blueprint (on-device validation) tunes them against real measurements
 * on the connected device. They exist here, in one place, so tuning is a
 * one-line change rather than a hunt through rendering code.
 */
object RenderTierThresholds {
    const val FULL_3D_MAX_FRAME_MS = 8.0
    const val FULL_3D_MIN_RAM_MB = 3000L
    const val FULL_3D_MIN_CORES = 6

    const val REDUCED_3D_MAX_FRAME_MS = 20.0
    const val REDUCED_3D_MIN_RAM_MB = 2000L
}

/**
 * Pure decision function: no Android framework dependency, unit-testable
 * directly. See [CapabilityMeasurements] for why the inputs must be an
 * unthrottled off-screen measurement, not a displayed-frame interval.
 */
fun decideRenderTier(m: CapabilityMeasurements): RenderTier {
    val t = RenderTierThresholds
    return when {
        m.offscreenFrameMs <= t.FULL_3D_MAX_FRAME_MS &&
            m.totalRamMb >= t.FULL_3D_MIN_RAM_MB &&
            m.cpuCores >= t.FULL_3D_MIN_CORES -> RenderTier.Full3D

        m.offscreenFrameMs <= t.REDUCED_3D_MAX_FRAME_MS &&
            m.totalRamMb >= t.REDUCED_3D_MIN_RAM_MB -> RenderTier.Reduced3D

        else -> RenderTier.Canvas2D
    }
}
