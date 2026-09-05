package com.shadownav.app

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Plain-JUnit tests for the tier decision only -- no Android framework
 * dependency, no Robolectric, per `plans/shadownav-3d-mvp-web-deck.md`
 * Step 1 (FIX-9). The measurement side ([DeviceCapabilityProbe]) is
 * exercised on-device instead; see Step 5.
 */
class RenderTierTest {

    @Test
    fun `capable device gets full 3D`() {
        val m = CapabilityMeasurements(offscreenFrameMs = 4.0, totalRamMb = 6000, cpuCores = 8)
        assertEquals(RenderTier.Full3D, decideRenderTier(m))
    }

    @Test
    fun `mid device gets reduced 3D`() {
        val m = CapabilityMeasurements(offscreenFrameMs = 12.0, totalRamMb = 3000, cpuCores = 8)
        assertEquals(RenderTier.Reduced3D, decideRenderTier(m))
    }

    @Test
    fun `weak gpu falls back to canvas 2D even with plenty of ram`() {
        val m = CapabilityMeasurements(offscreenFrameMs = 40.0, totalRamMb = 8000, cpuCores = 8)
        assertEquals(RenderTier.Canvas2D, decideRenderTier(m))
    }

    @Test
    fun `low ram falls back to canvas 2D even with a fast gpu`() {
        val m = CapabilityMeasurements(offscreenFrameMs = 3.0, totalRamMb = 800, cpuCores = 8)
        assertEquals(RenderTier.Canvas2D, decideRenderTier(m))
    }

    @Test
    fun `few cores keeps a fast-frame device at reduced rather than full`() {
        val m = CapabilityMeasurements(offscreenFrameMs = 4.0, totalRamMb = 6000, cpuCores = 4)
        assertEquals(RenderTier.Reduced3D, decideRenderTier(m))
    }

    @Test
    fun `boundary values are inclusive`() {
        val exact = CapabilityMeasurements(
            offscreenFrameMs = RenderTierThresholds.FULL_3D_MAX_FRAME_MS,
            totalRamMb = RenderTierThresholds.FULL_3D_MIN_RAM_MB,
            cpuCores = RenderTierThresholds.FULL_3D_MIN_CORES,
        )
        assertEquals(RenderTier.Full3D, decideRenderTier(exact))
    }

    @Test
    fun `stored name round trips through RenderTier companion helpers`() {
        for (tier in listOf(RenderTier.Full3D, RenderTier.Reduced3D, RenderTier.Canvas2D)) {
            val name = RenderTier.storedName(tier)
            assertEquals(tier, RenderTier.fromStoredName(name))
        }
    }

    @Test
    fun `unknown stored name resolves to null so callers can fall back to a fresh probe`() {
        assertEquals(null, RenderTier.fromStoredName("something-old-and-unrecognised"))
        assertEquals(null, RenderTier.fromStoredName(null))
    }
}
