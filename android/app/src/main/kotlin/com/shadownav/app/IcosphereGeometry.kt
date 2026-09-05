package com.shadownav.app

import kotlin.math.sqrt

/**
 * Procedurally generates an icosphere -- an icosahedron with each face
 * optionally subdivided and re-projected onto the unit sphere.
 *
 * Generated at runtime rather than loaded from a `.filamesh` asset because
 * the filamesh format needs Filament's `filament-tools` Gradle plugin (which
 * needs a locally-built Filament C++ toolchain to run `matc`/mesh
 * converters) -- see `plans/shadownav-3d-mvp-web-deck.md` Step 2 for why
 * this project avoids that entirely, the same way [OrbMaterial] avoids it
 * for materials via the runtime `MaterialBuilder` API instead of `.filamat`
 * assets.
 */
object IcosphereGeometry {

    data class Mesh(
        /** Flattened x,y,z per vertex, unit-sphere positions. */
        val positions: FloatArray,
        val indices: ShortArray,
    )

    /**
     * @param subdivisions 0 gives the plain 20-face icosahedron; each
     *   additional level roughly quadruples the face count. 1 (80 faces) is
     *   plenty for a small header widget; keep 0 available for the
     *   [RenderTier.Reduced3D] tier.
     */
    fun build(subdivisions: Int = 1): Mesh {
        val golden = (1.0 + sqrt(5.0)) / 2.0
        val verts = mutableListOf(
            normalize(-1.0, golden, 0.0), normalize(1.0, golden, 0.0),
            normalize(-1.0, -golden, 0.0), normalize(1.0, -golden, 0.0),
            normalize(0.0, -1.0, golden), normalize(0.0, 1.0, golden),
            normalize(0.0, -1.0, -golden), normalize(0.0, 1.0, -golden),
            normalize(golden, 0.0, -1.0), normalize(golden, 0.0, 1.0),
            normalize(-golden, 0.0, -1.0), normalize(-golden, 0.0, 1.0),
        )

        var faces = listOf(
            intArrayOf(0, 11, 5), intArrayOf(0, 5, 1), intArrayOf(0, 1, 7),
            intArrayOf(0, 7, 10), intArrayOf(0, 10, 11),
            intArrayOf(1, 5, 9), intArrayOf(5, 11, 4), intArrayOf(11, 10, 2),
            intArrayOf(10, 7, 6), intArrayOf(7, 1, 8),
            intArrayOf(3, 9, 4), intArrayOf(3, 4, 2), intArrayOf(3, 2, 6),
            intArrayOf(3, 6, 8), intArrayOf(3, 8, 9),
            intArrayOf(4, 9, 5), intArrayOf(2, 4, 11), intArrayOf(6, 2, 10),
            intArrayOf(8, 6, 7), intArrayOf(9, 8, 1),
        )

        val midpointCache = HashMap<Long, Int>()
        fun midpoint(a: Int, b: Int): Int {
            val key = if (a < b) (a.toLong() shl 32) or b.toLong() else (b.toLong() shl 32) or a.toLong()
            midpointCache[key]?.let { return it }
            val pa = verts[a]
            val pb = verts[b]
            val mid = normalize((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0, (pa[2] + pb[2]) / 2.0)
            verts.add(mid)
            val idx = verts.size - 1
            midpointCache[key] = idx
            return idx
        }

        repeat(subdivisions) {
            val next = ArrayList<IntArray>(faces.size * 4)
            for (f in faces) {
                val a = midpoint(f[0], f[1])
                val b = midpoint(f[1], f[2])
                val c = midpoint(f[2], f[0])
                next.add(intArrayOf(f[0], a, c))
                next.add(intArrayOf(f[1], b, a))
                next.add(intArrayOf(f[2], c, b))
                next.add(intArrayOf(a, b, c))
            }
            faces = next
        }

        val positions = FloatArray(verts.size * 3)
        for (i in verts.indices) {
            positions[i * 3] = verts[i][0].toFloat()
            positions[i * 3 + 1] = verts[i][1].toFloat()
            positions[i * 3 + 2] = verts[i][2].toFloat()
        }

        val indices = ShortArray(faces.size * 3)
        var cursor = 0
        for (f in faces) {
            indices[cursor++] = f[0].toShort()
            indices[cursor++] = f[1].toShort()
            indices[cursor++] = f[2].toShort()
        }

        return Mesh(positions, indices)
    }

    private fun normalize(x: Double, y: Double, z: Double): DoubleArray {
        val len = sqrt(x * x + y * y + z * z)
        return doubleArrayOf(x / len, y / len, z / len)
    }
}
