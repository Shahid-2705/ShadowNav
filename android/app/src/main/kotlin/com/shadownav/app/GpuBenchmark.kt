package com.shadownav.app

import android.opengl.EGL14
import android.opengl.EGLConfig
import android.opengl.EGLContext
import android.opengl.EGLDisplay
import android.opengl.EGLSurface
import android.opengl.GLES20
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer

/**
 * Measures GPU work per frame on an off-screen pbuffer surface -- deliberately
 * NOT tied to the display's Choreographer/vsync.
 *
 * A naive "render N frames to the screen, measure wall-clock ms/frame" is
 * vsync-limited: on a 60 Hz display every *presented* frame is ~16.7 ms
 * whether the GPU has 2 ms or 15 ms of headroom, so it cannot discriminate a
 * capable device from a weak one. `demo/README.md`'s own auto-degrade rule
 * hits exactly this failure mode from the other direction (a 30 Hz mirrored
 * output trips it on healthy hardware). A pbuffer has no swap chain and no
 * compositor, so [GLES20.glFinish] genuinely blocks until the GPU work is
 * done, which is what makes the timing here meaningful.
 *
 * Must be called from a thread with no other EGL context current -- it
 * creates and tears down its own context and pbuffer, and is blocking, so
 * call it off the main thread. See `plans/shadownav-3d-mvp-web-deck.md`
 * Step 1, task 6 (FIX-8).
 */
object GpuBenchmark {

    private const val SURFACE_SIZE = 256
    private const val WARMUP_ITERATIONS = 5
    private const val TIMED_ITERATIONS = 60

    /**
     * Returns the average milliseconds of GPU-bound work per iteration, or
     * `null` if EGL/GLES setup failed (e.g. no GPU driver available, which
     * itself is a signal to fall back to [RenderTier.Canvas2D] -- callers
     * should treat `null` that way, not retry).
     */
    fun measureFrameMs(): Double? {
        var display: EGLDisplay? = null
        var context: EGLContext? = null
        var surface: EGLSurface? = null
        try {
            display = EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY)
            if (display == EGL14.EGL_NO_DISPLAY) return null

            val version = IntArray(2)
            if (!EGL14.eglInitialize(display, version, 0, version, 1)) return null

            val configAttribs = intArrayOf(
                EGL14.EGL_RENDERABLE_TYPE, EGL14.EGL_OPENGL_ES2_BIT,
                EGL14.EGL_SURFACE_TYPE, EGL14.EGL_PBUFFER_BIT,
                EGL14.EGL_RED_SIZE, 8,
                EGL14.EGL_GREEN_SIZE, 8,
                EGL14.EGL_BLUE_SIZE, 8,
                EGL14.EGL_ALPHA_SIZE, 8,
                EGL14.EGL_NONE,
            )
            val configs = arrayOfNulls<EGLConfig>(1)
            val numConfigs = IntArray(1)
            if (!EGL14.eglChooseConfig(display, configAttribs, 0, configs, 0, 1, numConfigs, 0) ||
                numConfigs[0] == 0
            ) {
                return null
            }
            val config = configs[0] ?: return null

            val contextAttribs = intArrayOf(
                EGL14.EGL_CONTEXT_CLIENT_VERSION, 2,
                EGL14.EGL_NONE,
            )
            context = EGL14.eglCreateContext(display, config, EGL14.EGL_NO_CONTEXT, contextAttribs, 0)
            if (context == EGL14.EGL_NO_CONTEXT) return null

            val pbufferAttribs = intArrayOf(
                EGL14.EGL_WIDTH, SURFACE_SIZE,
                EGL14.EGL_HEIGHT, SURFACE_SIZE,
                EGL14.EGL_NONE,
            )
            surface = EGL14.eglCreatePbufferSurface(display, config, pbufferAttribs, 0)
            if (surface == EGL14.EGL_NO_SURFACE) return null

            if (!EGL14.eglMakeCurrent(display, surface, surface, context)) return null

            val program = buildProgram() ?: return null
            val quad = fullScreenQuad()
            GLES20.glViewport(0, 0, SURFACE_SIZE, SURFACE_SIZE)
            GLES20.glUseProgram(program)
            val posLoc = GLES20.glGetAttribLocation(program, "aPosition")
            GLES20.glEnableVertexAttribArray(posLoc)
            GLES20.glVertexAttribPointer(posLoc, 2, GLES20.GL_FLOAT, false, 0, quad)
            val iterLoc = GLES20.glGetUniformLocation(program, "uComplexity")

            fun drawOnce(complexity: Float) {
                GLES20.glUniform1f(iterLoc, complexity)
                GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)
                GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)
                GLES20.glFinish() // Block until the GPU has actually finished this draw.
            }

            // Fixed, deliberately nontrivial per-pixel workload (see the
            // fragment shader) so a weak GPU takes measurably longer, not just
            // a different queue depth.
            val complexity = 400f
            repeat(WARMUP_ITERATIONS) { drawOnce(complexity) }

            val start = System.nanoTime()
            repeat(TIMED_ITERATIONS) { drawOnce(complexity) }
            val elapsedNs = System.nanoTime() - start

            GLES20.glDeleteProgram(program)
            return (elapsedNs / 1e6) / TIMED_ITERATIONS
        } catch (e: RuntimeException) {
            // Any EGL/GLES failure here means "cannot measure," which the
            // caller should treat as a reason to prefer Canvas2D, not a crash.
            return null
        } finally {
            if (display != null) {
                EGL14.eglMakeCurrent(display, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_CONTEXT)
                if (surface != null) EGL14.eglDestroySurface(display, surface)
                if (context != null) EGL14.eglDestroyContext(display, context)
                EGL14.eglTerminate(display)
            }
        }
    }

    private fun fullScreenQuad(): FloatBuffer {
        val verts = floatArrayOf(-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f)
        return ByteBuffer.allocateDirect(verts.size * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .apply { put(verts); position(0) }
    }

    private fun buildProgram(): Int? {
        val vertexSrc = """
            attribute vec2 aPosition;
            varying vec2 vUv;
            void main() {
                vUv = aPosition * 0.5 + 0.5;
                gl_Position = vec4(aPosition, 0.0, 1.0);
            }
        """.trimIndent()

        // Per-pixel trig loop: cheap to author, expensive enough on a weak GPU
        // to separate device tiers, and has no dependence on any texture or
        // asset -- this benchmark must not need anything beyond a GL context.
        val fragmentSrc = """
            precision mediump float;
            varying vec2 vUv;
            uniform float uComplexity;
            void main() {
                vec2 p = vUv;
                float acc = 0.0;
                for (int i = 0; i < 400; i++) {
                    if (float(i) >= uComplexity) break;
                    p = vec2(sin(p.y * 12.9898 + float(i)), cos(p.x * 78.233 + float(i)));
                    acc += p.x * p.y;
                }
                gl_FragColor = vec4(vec3(fract(acc)), 1.0);
            }
        """.trimIndent()

        val vertexShader = compileShader(GLES20.GL_VERTEX_SHADER, vertexSrc) ?: return null
        val fragmentShader = compileShader(GLES20.GL_FRAGMENT_SHADER, fragmentSrc) ?: return null

        val program = GLES20.glCreateProgram()
        if (program == 0) return null
        GLES20.glAttachShader(program, vertexShader)
        GLES20.glAttachShader(program, fragmentShader)
        GLES20.glLinkProgram(program)
        val linked = IntArray(1)
        GLES20.glGetProgramiv(program, GLES20.GL_LINK_STATUS, linked, 0)
        if (linked[0] == 0) {
            GLES20.glDeleteProgram(program)
            return null
        }
        GLES20.glDeleteShader(vertexShader)
        GLES20.glDeleteShader(fragmentShader)
        return program
    }

    private fun compileShader(type: Int, src: String): Int? {
        val shader = GLES20.glCreateShader(type)
        if (shader == 0) return null
        GLES20.glShaderSource(shader, src)
        GLES20.glCompileShader(shader)
        val compiled = IntArray(1)
        GLES20.glGetShaderiv(shader, GLES20.GL_COMPILE_STATUS, compiled, 0)
        if (compiled[0] == 0) {
            GLES20.glDeleteShader(shader)
            return null
        }
        return shader
    }
}
