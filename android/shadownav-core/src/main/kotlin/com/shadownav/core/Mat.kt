package com.shadownav.core

/**
 * Minimal dense matrix, row-major, backed by a [DoubleArray].
 *
 * The filter is 5 states with measurement blocks of 1 or 2 rows, so a general
 * linear algebra dependency would be a large amount of machinery for matrices
 * that fit in a cache line. Everything here is deliberately small enough to
 * read in one sitting, because a transposed index in this file produces a
 * trajectory that looks plausible on a phone screen and is wrong.
 *
 * Correctness is not argued, it is asserted: the parity tests replay golden
 * vectors exported from the Python implementation and require agreement to
 * 1e-9.
 */
class Mat(val rows: Int, val cols: Int, val data: DoubleArray = DoubleArray(rows * cols)) {

    init {
        require(data.size == rows * cols) {
            "expected ${rows * cols} elements for ${rows}x$cols, got ${data.size}"
        }
    }

    operator fun get(r: Int, c: Int): Double = data[r * cols + c]

    operator fun set(r: Int, c: Int, v: Double) {
        data[r * cols + c] = v
    }

    fun copy(): Mat = Mat(rows, cols, data.copyOf())

    operator fun times(other: Mat): Mat {
        require(cols == other.rows) { "$rows x $cols cannot multiply ${other.rows} x ${other.cols}" }
        val out = Mat(rows, other.cols)
        for (i in 0 until rows) {
            for (k in 0 until cols) {
                val a = this[i, k]
                if (a == 0.0) continue
                for (j in 0 until other.cols) {
                    out.data[i * other.cols + j] += a * other[k, j]
                }
            }
        }
        return out
    }

    operator fun plus(other: Mat): Mat {
        require(rows == other.rows && cols == other.cols)
        val out = Mat(rows, cols, data.copyOf())
        for (i in data.indices) out.data[i] += other.data[i]
        return out
    }

    operator fun minus(other: Mat): Mat {
        require(rows == other.rows && cols == other.cols)
        val out = Mat(rows, cols, data.copyOf())
        for (i in data.indices) out.data[i] -= other.data[i]
        return out
    }

    fun transpose(): Mat {
        val out = Mat(cols, rows)
        for (r in 0 until rows) for (c in 0 until cols) out[c, r] = this[r, c]
        return out
    }

    /** Average with the transpose. Kills asymmetry that accumulates over
     *  thousands of updates and eventually breaks positive-definiteness. */
    fun symmetrised(): Mat {
        require(rows == cols)
        val out = Mat(rows, cols)
        for (r in 0 until rows) for (c in 0 until cols) {
            out[r, c] = 0.5 * (this[r, c] + this[c, r])
        }
        return out
    }

    fun diagonal(): DoubleArray = DoubleArray(minOf(rows, cols)) { this[it, it] }

    /**
     * Inverse for 1x1 and 2x2 only.
     *
     * Those are the only innovation-covariance shapes the filter produces, and
     * restricting to them keeps this exact and branch-free rather than pulling
     * in a general solver whose pivoting would have to be validated too.
     */
    fun inverseSmall(): Mat {
        require(rows == cols) { "not square" }
        return when (rows) {
            1 -> {
                val d = data[0]
                require(kotlin.math.abs(d) > 1e-300) { "singular 1x1" }
                Mat(1, 1, doubleArrayOf(1.0 / d))
            }
            2 -> {
                val det = data[0] * data[3] - data[1] * data[2]
                require(kotlin.math.abs(det) > 1e-300) { "singular 2x2" }
                val inv = 1.0 / det
                Mat(2, 2, doubleArrayOf(data[3] * inv, -data[1] * inv,
                                        -data[2] * inv, data[0] * inv))
            }
            else -> throw IllegalArgumentException(
                "inverseSmall handles 1x1 and 2x2; got ${rows}x$cols"
            )
        }
    }

    companion object {
        fun identity(n: Int): Mat {
            val m = Mat(n, n)
            for (i in 0 until n) m[i, i] = 1.0
            return m
        }

        fun diag(values: DoubleArray): Mat {
            val m = Mat(values.size, values.size)
            for (i in values.indices) m[i, i] = values[i]
            return m
        }

        fun column(values: DoubleArray): Mat = Mat(values.size, 1, values.copyOf())

        fun rowVector(values: DoubleArray): Mat = Mat(1, values.size, values.copyOf())
    }
}
