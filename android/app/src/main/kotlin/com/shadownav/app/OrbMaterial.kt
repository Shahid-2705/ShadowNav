package com.shadownav.app

import android.content.Context
import com.google.android.filament.Engine
import com.google.android.filament.Material
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Loads the orb's material from the precompiled `assets/materials/orb.filamat`
 * binary -- a small UNLIT material with one `baseColor` (FLOAT3) uniform
 * parameter, source: `void material(inout MaterialInputs material) {
 * prepareMaterial(material); material.baseColor.rgb = materialParams.baseColor; }`.
 *
 * That binary was generated once via Filament's runtime `MaterialBuilder`
 * API (`filamat-android`, Google's own `sample-material-builder` pattern),
 * on-device, then extracted and committed here -- see `PLAN.md`'s Step 2
 * note. `filamat-android` is deliberately **not** a dependency of the
 * shipped app: it bundles the full shader cross-compiler toolchain and
 * measured ~8.9 MB, an unreasonable cost to carry permanently just to
 * compile one ~80 KB material at every app launch. There is still no
 * build-time `matc`/`filament-tools` step anywhere in this project (see
 * `IcosphereGeometry`'s file comment) -- this is a one-time, already-done
 * runtime compile, not a build pipeline.
 */
object OrbMaterial {

    /**
     * Returns `null` if the asset is missing or Filament rejects it,
     * matching [GpuBenchmark]'s "fail soft to Canvas2D" treatment of an EGL
     * failure -- a missing material must not crash the app.
     */
    fun load(engine: Engine, context: Context): Material? = runCatching {
        val bytes = context.assets.open("materials/orb.filamat").use { it.readBytes() }
        val buffer = ByteBuffer.allocateDirect(bytes.size)
            .order(ByteOrder.nativeOrder())
            .apply { put(bytes); position(0) }
        Material.Builder().payload(buffer, buffer.remaining()).build(engine)
    }.getOrNull()
}
