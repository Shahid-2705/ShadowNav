package com.shadownav.app

import android.content.Context
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import com.shadownav.core.Features
import org.json.JSONObject
import java.nio.FloatBuffer
import kotlin.math.exp

/**
 * On-device forward-speed network: `assets/speednet.onnx` through ONNX Runtime.
 *
 * This is the Android end of the contract in `shared/README.md`. The graph
 * holds only the network; everything around it is reproduced here from the
 * sidecar `speednet.onnx.json` that `scripts/export_onnx.py` writes next to
 * the model, so the constants can never drift from the checkpoint by a
 * hand-copy:
 *
 *   1. six rotation-invariant channels over the last `window` samples
 *      ([Features.invariant], the port of `models/features.py`), with the
 *      vertical fixed once per drive from aided data;
 *   2. standardisation by `feature_mean` / `feature_std` (fitted on train);
 *   3. the graph -> `(speed, log_var)`;
 *   4. `sigma = exp(0.5 * log_var) * sigma_scale`, clamped to [0.4, 8.0] m/s.
 *      `sigma_scale` is the val-fitted 3.27x that takes 1-sigma coverage from
 *      0.27 to 0.64. It is not optional.
 *
 * What this class does NOT do: the confidence gate (`models/gate.py`), which
 * is the policy that lets the network correct the filter without dominating
 * it. Until that is ported and the parity suite covers it, nothing in the
 * live pipeline reads this class -- [USE_SPEED_NET] is false and
 * [NavigationEngine] never constructs it. No on-device latency or accuracy
 * number exists yet; the desktop proxy in `eval/results/inference_latency.json`
 * is not one.
 */
class SpeedNetOnnx private constructor(
    private val env: OrtEnvironment,
    private val session: OrtSession,
    val window: Int,
    private val featureMean: DoubleArray,
    private val featureStd: DoubleArray,
    val sigmaScale: Double,
) : AutoCloseable {

    /** Speed in m/s and its calibrated 1-sigma, both as the filter consumes them. */
    data class Prediction(val speedMs: Double, val sigmaMs: Double)

    /**
     * `acc` and `gyr` are device-frame rows, oldest first; `up` is the unit
     * vertical from [Features.gravityDirection] over a long aided run. Returns
     * null when fewer than [window] samples are available -- "no opinion",
     * the same contract as the Python estimator returning NaN.
     */
    fun predict(acc: Array<DoubleArray>, gyr: Array<DoubleArray>, up: DoubleArray): Prediction? {
        if (acc.size < window || gyr.size < window) return null
        val tailAcc = acc.copyOfRange(acc.size - window, acc.size)
        val tailGyr = gyr.copyOfRange(gyr.size - window, gyr.size)
        val feat = Features.invariant(tailAcc, tailGyr, up)

        val buf = FloatBuffer.allocate(window * Features.N_CHANNELS)
        for (row in feat) for (c in 0 until Features.N_CHANNELS) {
            buf.put(((row[c] - featureMean[c]) / featureStd[c]).toFloat())
        }
        buf.rewind()

        OnnxTensor.createTensor(env, buf, longArrayOf(1, window.toLong(), Features.N_CHANNELS.toLong()))
            .use { input ->
                session.run(mapOf(INPUT_NAME to input)).use { out ->
                    val speed = (out[0].value as FloatArray)[0].toDouble()
                    val logVar = (out[1].value as FloatArray)[0].toDouble()
                    val sigma = (exp(0.5 * logVar) * sigmaScale).coerceIn(SIGMA_FLOOR, SIGMA_CEILING)
                    return Prediction(speed, sigma)
                }
            }
    }

    override fun close() {
        session.close()
    }

    companion object {
        /**
         * Master switch. False: the class is never instantiated by the live
         * pipeline and the APK behaves exactly as before the dependency was
         * added. Flip only together with a ported gate and a parity test.
         */
        const val USE_SPEED_NET = false

        const val MODEL_ASSET = "speednet.onnx"
        const val SIDECAR_ASSET = "speednet.onnx.json"
        const val INPUT_NAME = "features"

        /** Same clamp as `models/inference.py`: a diverging head must not emit
         *  a sigma the filter either blindly trusts or entirely ignores. */
        const val SIGMA_FLOOR = 0.4
        const val SIGMA_CEILING = 8.0

        /** Builds a session from the bundled assets. Throws on a malformed
         *  asset rather than returning a silently wrong estimator. */
        fun fromAssets(context: Context): SpeedNetOnnx {
            val sidecar = context.assets.open(SIDECAR_ASSET).bufferedReader().use { reader ->
                JSONObject(reader.readText())
            }
            val mean = sidecar.getJSONArray("feature_mean").let { a -> DoubleArray(a.length()) { a.getDouble(it) } }
            val std = sidecar.getJSONArray("feature_std").let { a -> DoubleArray(a.length()) { a.getDouble(it) } }
            val window = sidecar.getJSONObject("input").getJSONArray("shape").getInt(1)
            require(mean.size == Features.N_CHANNELS && std.size == Features.N_CHANNELS) {
                "sidecar declares ${mean.size} channels, Features has ${Features.N_CHANNELS}"
            }
            require(std.all { it > 0.0 }) { "feature_std must be positive" }

            val bytes = context.assets.open(MODEL_ASSET).use { it.readBytes() }
            val env = OrtEnvironment.getEnvironment()
            val options = OrtSession.SessionOptions().apply {
                setIntraOpNumThreads(1)   // one core: the low-end budget is per update, not per device
            }
            val session = env.createSession(bytes, options)
            return SpeedNetOnnx(env, session, window, mean, std, sidecar.getDouble("sigma_scale"))
        }
    }
}
