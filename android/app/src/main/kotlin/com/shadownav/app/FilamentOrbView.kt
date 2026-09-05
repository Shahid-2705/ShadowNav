package com.shadownav.app

import android.content.Context
import android.util.AttributeSet
import android.view.Surface
import android.view.SurfaceView
import com.google.android.filament.Box
import com.google.android.filament.Camera
import com.google.android.filament.Colors
import com.google.android.filament.Engine
import com.google.android.filament.EntityManager
import com.google.android.filament.IndexBuffer
import com.google.android.filament.Material
import com.google.android.filament.MaterialInstance
import com.google.android.filament.RenderableManager
import com.google.android.filament.Renderer
import com.google.android.filament.Scene
import com.google.android.filament.Skybox
import com.google.android.filament.SwapChain
import com.google.android.filament.VertexBuffer
import com.google.android.filament.Viewport
import com.google.android.filament.android.ChoreographerHelper
import com.google.android.filament.android.DisplayHelper
import com.google.android.filament.android.FilamentHelper
import com.google.android.filament.android.UiHelper
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.cos
import kotlin.math.sin
import com.google.android.filament.View as FilamentView

/**
 * The status orb: a Filament-rendered icosphere whose colour tracks
 * [UiSignalState] -- the same state [StatusChip] announces, via the shared
 * [uiState] function, so the two can never disagree (blueprint Step 2,
 * FIX-6).
 *
 * Deliberately simplified relative to `demo/gnss-demo.html`'s full
 * shard-fracture animation: this pass proves the real rendering pipeline
 * end-to-end (procedural geometry, a runtime-compiled material, the
 * SurfaceView/Engine/Renderer lifecycle, verified on the connected device)
 * with a colour transition + gentle rotation/pulse per state. The full
 * per-shard fracture physics from the demo is follow-on polish (blueprint
 * Step 4), not silently dropped -- see `plans/shadownav-3d-mvp-web-deck.md`.
 *
 * [push] is the only way this view learns about navigation state, and it is
 * called from [MainActivity]'s existing 10 Hz `render()` loop -- never from
 * this view's own ~60 Hz frame callback, which must not touch
 * `NavigationEngine`/`Snapshot` at all (FIX-22: `Snapshot.snapshot()` shares
 * a lock with the ~400 Hz IMU callback, and driving it from a 60 Hz render
 * loop would meaningfully increase lock contention on the sensor-critical
 * path). Between 10 Hz pushes, [FrameCallback] interpolates locally.
 */
class FilamentOrbView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null,
) : SurfaceView(context, attrs) {

    private var engine: Engine? = null
    private lateinit var uiHelper: UiHelper
    private lateinit var displayHelper: DisplayHelper
    private var renderer: Renderer? = null
    private var scene: Scene? = null
    private var filamentView: FilamentView? = null
    private var camera: Camera? = null
    private var material: Material? = null
    private var materialInstance: MaterialInstance? = null
    private var vertexBuffer: VertexBuffer? = null
    private var indexBuffer: IndexBuffer? = null
    private var indexCount = 0
    private var renderable = 0
    private var swapChain: SwapChain? = null
    private var ready = false

    private val frameScheduler = FrameCallback()

    private var currentState = UiSignalState.ACQUIRING
    private var displayedColour = floatArrayOf(0.51f, 0.57f, 0.63f) // Palette.SLATE, matched by hand once at init
    private var transitionStartNanos = 0L
    private var transitionFromColour = displayedColour.copyOf()

    /** Renders at [RenderTier.Reduced3D] with a coarser icosphere and no
     *  pulse animation, to keep the frame cheap on a mid device. */
    var reducedQuality: Boolean = false

    fun push(state: UiSignalState) {
        if (state != currentState) {
            transitionFromColour = displayedColour.copyOf()
            transitionStartNanos = System.nanoTime()
            currentState = state
        }
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        // Purely decorative: StatusChip is the accessible source of truth
        // ("colour reinforces; it does not encode" -- Ui.kt) and already
        // announces this exact state. A second contentDescription here
        // would make a screen reader announce the same text twice rather
        // than adding information, so this view is excluded entirely
        // instead (blueprint Step 2, FIX-6).
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
        val eng = FilamentHost.acquire()
        engine = eng
        displayHelper = DisplayHelper(context)
        uiHelper = UiHelper(UiHelper.ContextErrorPolicy.DONT_CHECK)
        uiHelper.renderCallback = SurfaceCallback()
        renderer = eng.createRenderer()
        frameScheduler.setRenderer(renderer!!)
        scene = eng.createScene()
        filamentView = eng.createView()
        camera = eng.createCamera(eng.entityManager.create())
        filamentView!!.camera = camera
        filamentView!!.scene = scene
        // "More stunning" pass: bloom is what actually makes an emissive
        // orb read as *glowing* rather than just brightly coloured -- a flat
        // colour pulse (the original implementation) can't produce that.
        // The view is 44dp and off-screen except when RenderTier warrants
        // 3D at all, so full post-processing is affordable here even though
        // it wasn't worth it for the (much larger) map route scene.
        filamentView!!.bloomOptions = filamentView!!.bloomOptions.apply {
            enabled = true
            strength = 1.2f
        }
        // Matches Ui.kt's Palette.BG (0xFF07090C): the orb sits directly on
        // the app's own header background, so a mismatched clear colour
        // would show a visible seam around this SurfaceView.
        scene!!.skybox = Skybox.Builder().color(0.027f, 0.035f, 0.047f, 1.0f).build(eng)

        material = OrbMaterial.load(eng, context)
        if (material != null) {
            buildRenderable(eng)
            ready = true
            uiHelper.attachTo(this)
            frameScheduler.post()
        }
        // If the material failed to compile, this view intentionally stays
        // blank rather than crashing -- the caller (MainActivity, per
        // RenderTier gating) is what should have kept this view out of the
        // layout in that case; this is a last-resort safety net, not the
        // primary gate.
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        frameScheduler.remove()
        if (ready) uiHelper.detach()
        val eng = engine ?: return
        renderable.takeIf { it != 0 }?.let { eng.destroyEntity(it); EntityManager.get().destroy(it) }
        vertexBuffer?.let { eng.destroyVertexBuffer(it) }
        indexBuffer?.let { eng.destroyIndexBuffer(it) }
        materialInstance?.let { eng.destroyMaterialInstance(it) }
        material?.let { eng.destroyMaterial(it) }
        renderer?.let { eng.destroyRenderer(it) }
        scene?.skybox?.let { eng.destroySkybox(it) }
        scene?.let { eng.destroyScene(it) }
        camera?.let { eng.destroyCameraComponent(it.entity) }
        filamentView?.let { eng.destroyView(it) }
        camera?.entity?.let { EntityManager.get().destroy(it) }
        FilamentHost.release()
        engine = null
        ready = false
    }

    private fun buildRenderable(engine: Engine) {
        val mat = material ?: return
        materialInstance = mat.createInstance()
        materialInstance!!.setParameter(
            "baseColor", Colors.RgbType.SRGB,
            displayedColour[0] * emissiveBoost, displayedColour[1] * emissiveBoost, displayedColour[2] * emissiveBoost,
        )

        val mesh = IcosphereGeometry.build(subdivisions = if (reducedQuality) 0 else 1)
        indexCount = mesh.indices.size

        val posBuffer = ByteBuffer.allocateDirect(mesh.positions.size * 4)
            .order(ByteOrder.nativeOrder())
            .apply { asFloatBuffer().put(mesh.positions); position(0) }

        vertexBuffer = VertexBuffer.Builder()
            .bufferCount(1)
            .vertexCount(mesh.positions.size / 3)
            .attribute(VertexBuffer.VertexAttribute.POSITION, 0, VertexBuffer.AttributeType.FLOAT3, 0, 12)
            .build(engine)
        vertexBuffer!!.setBufferAt(engine, 0, posBuffer)

        val idxBuffer = ByteBuffer.allocateDirect(mesh.indices.size * 2)
            .order(ByteOrder.nativeOrder())
            .apply { asShortBuffer().put(mesh.indices); position(0) }
        indexBuffer = IndexBuffer.Builder()
            .indexCount(mesh.indices.size)
            .bufferType(IndexBuffer.Builder.IndexType.USHORT)
            .build(engine)
        indexBuffer!!.setBuffer(engine, idxBuffer)

        renderable = EntityManager.get().create()
        val vb = requireNotNull(vertexBuffer)
        val ib = requireNotNull(indexBuffer)
        val mi = requireNotNull(materialInstance)
        RenderableManager.Builder(1)
            .boundingBox(Box(0.0f, 0.0f, 0.0f, 1.1f, 1.1f, 1.1f))
            .geometry(0, RenderableManager.PrimitiveType.TRIANGLES, vb, ib, 0, indexCount)
            .material(0, mi)
            .culling(false) // a status icon is small on screen; back-face cost isn't worth the risk of a hole showing
            .build(engine, renderable)
        scene!!.addEntity(renderable)
    }

    /** Pushes the UNLIT material's emitted colour past the tone mapper's
     *  displayable range so [View.BloomOptions]'s bright-pass actually has
     *  something to bloom -- a plain [0,1] sRGB colour is well within normal
     *  range and produces no visible bloom at all, tuned empirically on the
     *  connected device. */
    private val emissiveBoost = 2.5f

    /** Milliseconds for a colour transition to complete. Not the demo's 1.8 s
     *  shard-reassembly time -- this view has no shards yet (see file
     *  comment), so a snappier, simpler cross-fade is the honest choice. */
    private val transitionMs = 350.0

    private inner class FrameCallback : ChoreographerHelper() {
        private val startNanos = System.nanoTime()

        override fun onFrame(frameTimeNanos: Long) {
            if (!ready) return
            val eng = engine ?: return
            val elapsedS = (frameTimeNanos - startNanos) / 1e9

            val target = colourFloats(currentState.colour)
            val tFrac = ((System.nanoTime() - transitionStartNanos) / 1e6 / transitionMs).coerceIn(0.0, 1.0)
            for (i in 0..2) {
                displayedColour[i] = (transitionFromColour[i] + (target[i] - transitionFromColour[i]) * tFrac).toFloat()
            }
            // A slow, steady spin while locked/aided reads as "alive"; a
            // barely-perceptible one while dead-reckoning reads as "holding,
            // not gone." No shard physics yet -- see the file comment.
            val spinSpeed = if (currentState == UiSignalState.DEAD_RECKONING) 0.05 else 0.15
            val angle = (elapsedS * spinSpeed * 2.0 * Math.PI).toFloat()
            // A gentle brightness pulse only while genuinely locked, so the
            // orb doesn't read as "alive" during acquiring/blackout when it
            // shouldn't.
            val pulse = if (currentState == UiSignalState.AIDED) {
                (0.9 + 0.1 * sin(elapsedS * 2.0 * Math.PI * 0.4)).toFloat()
            } else {
                1.0f
            }
            val boost = pulse * emissiveBoost
            materialInstance?.setParameter(
                "baseColor", Colors.RgbType.SRGB,
                displayedColour[0] * boost, displayedColour[1] * boost, displayedColour[2] * boost,
            )

            val transform = FloatArray(16)
            android.opengl.Matrix.setIdentityM(transform, 0)
            android.opengl.Matrix.rotateM(transform, 0, Math.toDegrees(angle.toDouble()).toFloat(), 0f, 1f, 0.15f)
            eng.transformManager.setTransform(eng.transformManager.getInstance(renderable), transform)

            if (uiHelper.isReadyToRender) {
                val r = renderer ?: return
                val sc = swapChain ?: return
                val v = filamentView ?: return
                if (r.beginFrame(sc, frameTimeNanos)) {
                    r.render(v)
                    r.endFrame()
                }
            }
        }
    }

    private fun colourFloats(argb: Int): FloatArray = floatArrayOf(
        ((argb shr 16) and 0xFF) / 255f,
        ((argb shr 8) and 0xFF) / 255f,
        (argb and 0xFF) / 255f,
    )

    private inner class SurfaceCallback : UiHelper.RendererCallback {
        override fun onNativeWindowChanged(surface: Surface) {
            val eng = engine ?: return
            val r = renderer ?: return
            swapChain?.let { eng.destroySwapChain(it) }
            swapChain = eng.createSwapChain(surface)
            displayHelper.attach(r, display)
        }

        override fun onDetachedFromSurface() {
            displayHelper.detach()
            val eng = engine ?: return
            swapChain?.let {
                eng.destroySwapChain(it)
                eng.flushAndWait()
                swapChain = null
            }
        }

        override fun onResized(width: Int, height: Int) {
            val cam = camera ?: return
            val aspect = width.toDouble() / height.toDouble()
            cam.setProjection(28.0, aspect, 0.1, 10.0, Camera.Fov.VERTICAL)
            // Unit-radius sphere at distance 6 with a 28-degree vertical FOV:
            // asin(1/6) =~ 9.6 degrees of the 14-degree half-FOV, so the orb
            // fills about 70% of the view height with visible margin, rather
            // than overflowing it (distance 3.2 put the sphere's radius
            // *larger* than the half-frustum at that distance, so it filled
            // the whole SurfaceView edge-to-edge with no visible silhouette
            // -- caught by screenshotting the first real on-device render).
            cam.lookAt(0.0, 0.0, 6.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)
            filamentView?.viewport = Viewport(0, 0, width, height)
            engine?.let { FilamentHelper.synchronizePendingFrames(it) }
        }
    }
}
