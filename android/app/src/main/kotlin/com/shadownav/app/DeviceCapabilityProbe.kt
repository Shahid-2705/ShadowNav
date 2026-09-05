package com.shadownav.app

import android.app.ActivityManager
import android.content.Context
import android.os.Handler
import android.os.Looper

/**
 * Measures device capability once, persists the result, and exposes a manual
 * override for on-device tuning (blueprint Step 1 / Step 5).
 *
 * The decision itself ([decideRenderTier]) is a pure function with no
 * dependency on this class or on Android -- that's what makes it unit
 * testable without Robolectric (see [RenderTierTest]). This class only does
 * the Android-specific measurement and persistence, which is exercised for
 * real on-device rather than unit tested, matching how `shadownav-core`
 * keeps its logic pure-JVM and pushes platform I/O to the edges.
 *
 * [GpuBenchmark.measureFrameMs] blocks (it calls `glFinish()`), so
 * [resolveTier] always does its work on a background thread and delivers the
 * result on the main thread.
 */
class DeviceCapabilityProbe(private val context: Context) {

    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val mainHandler = Handler(Looper.getMainLooper())

    /** A tier the user or a developer pinned by hand (e.g. Step 5's on-device
     *  tuning, or `?tier=` equivalent). Takes precedence over any measurement. */
    var manualOverride: RenderTier?
        get() = RenderTier.fromStoredName(prefs.getString(KEY_OVERRIDE, null))
        set(value) {
            prefs.edit().apply {
                if (value == null) remove(KEY_OVERRIDE) else putString(KEY_OVERRIDE, RenderTier.storedName(value))
            }.apply()
        }

    private var cachedMeasuredTier: RenderTier?
        get() = RenderTier.fromStoredName(prefs.getString(KEY_MEASURED, null))
        set(value) {
            prefs.edit().apply {
                if (value == null) remove(KEY_MEASURED) else putString(KEY_MEASURED, RenderTier.storedName(value))
            }.apply()
        }

    /**
     * Resolves the tier to use right now: the manual override if one is set,
     * otherwise a cached prior measurement, otherwise a fresh measurement
     * (computed once, persisted, then handed back). [onResult] is always
     * called on the main thread.
     */
    fun resolveTier(onResult: (RenderTier) -> Unit) {
        manualOverride?.let { onResult(it); return }
        cachedMeasuredTier?.let { onResult(it); return }
        measure(onResult)
    }

    /** Forces a fresh measurement regardless of any cached value -- used by
     *  Step 5's on-device validation to re-check after tuning thresholds. */
    fun measure(onResult: (RenderTier) -> Unit) {
        Thread {
            val measurements = takeMeasurements()
            val tier = decideRenderTier(measurements)
            cachedMeasuredTier = tier
            mainHandler.post { onResult(tier) }
        }.start()
    }

    private fun takeMeasurements(): CapabilityMeasurements {
        val activityManager = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memoryInfo = ActivityManager.MemoryInfo()
        activityManager.getMemoryInfo(memoryInfo)
        val totalRamMb = memoryInfo.totalMem / (1024 * 1024)
        val cpuCores = Runtime.getRuntime().availableProcessors()
        // A null benchmark (EGL/GLES setup failed) is treated as "worse than
        // any real threshold" rather than skipped, so decideRenderTier still
        // lands on Canvas2D instead of crashing or defaulting upward.
        val frameMs = GpuBenchmark.measureFrameMs() ?: Double.MAX_VALUE
        return CapabilityMeasurements(
            offscreenFrameMs = frameMs,
            totalRamMb = totalRamMb,
            cpuCores = cpuCores,
        )
    }

    private companion object {
        const val PREFS_NAME = "shadownav_render_tier"
        const val KEY_OVERRIDE = "manual_override"
        const val KEY_MEASURED = "measured_tier"
    }
}
