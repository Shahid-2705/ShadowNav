package com.shadownav.app

import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Handler
import android.os.HandlerThread

/**
 * Accelerometer and gyroscope capture at the highest rate the device offers.
 *
 * The sample rate is the single most consequential number in this project. Every
 * negative result in the offline work traces to IO-VNBD logging at 10 Hz: the
 * 21-state strapdown diverged, the centripetal observation hurt rather than
 * helped, and the learned speed head barely beat a constant -- because road and
 * engine vibration lives well above 5 Hz and is aliased away at 10 Hz.
 *
 * So this class does not assume it gets 200 Hz. It requests the fastest rate and
 * then **measures what it actually receives**, exposing that so the UI can show
 * it and so a claim made on a given phone can state the rate it was made at.
 * A phone advertising SENSOR_DELAY_FASTEST may still deliver 50 Hz.
 *
 * Delivery runs on a dedicated HandlerThread: sensor callbacks on the main
 * thread would be dropped whenever the UI does layout work, and a dropped IMU
 * sample is an unrecoverable gap in a dead-reckoning integral.
 */
class SensorCapture(
    private val sensorManager: SensorManager,
    private val listener: Listener,
) : SensorEventListener {

    interface Listener {
        /**
         * @param timestampNs the sensor's own event timestamp, not wall clock.
         *        Wall clock is subject to NTP steps mid-drive.
         */
        fun onImuSample(
            timestampNs: Long,
            accel: FloatArray?,
            gyro: FloatArray?,
        )
    }

    private val accelSensor: Sensor? = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroSensor: Sensor? = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

    private var thread: HandlerThread? = null

    private val latestAccel = FloatArray(3)
    private val latestGyro = FloatArray(3)
    private var haveAccel = false
    private var haveGyro = false

    // -- measured, not assumed -------------------------------------------

    private var accelCount = 0L
    private var gyroCount = 0L
    private var firstAccelNs = 0L
    private var lastAccelNs = 0L
    private var maxGapNs = 0L

    /** Achieved accelerometer rate in Hz, or 0 before enough samples. */
    val measuredAccelHz: Double
        get() {
            val span = lastAccelNs - firstAccelNs
            return if (accelCount > 10 && span > 0) {
                (accelCount - 1) * 1e9 / span
            } else {
                0.0
            }
        }

    /** Largest gap between consecutive accelerometer samples, in milliseconds.
     *  A large value means samples were dropped, which is a silent integration
     *  error rather than a visible fault. */
    val maxGapMs: Double get() = maxGapNs / 1e6

    /** What the device says it can do, before measurement contradicts it. */
    val advertisedAccelHz: Double
        get() = accelSensor?.let {
            if (it.minDelay > 0) 1e6 / it.minDelay else 0.0
        } ?: 0.0

    val hasRequiredSensors: Boolean get() = accelSensor != null && gyroSensor != null

    fun describeSensors(): String = buildString {
        append(accelSensor?.let { "${it.name} (${"%.0f".format(advertisedAccelHz)} Hz max)" }
            ?: "NO ACCELEROMETER")
        append(" | ")
        append(gyroSensor?.name ?: "NO GYROSCOPE")
    }

    fun start() {
        if (thread != null) return
        val t = HandlerThread("shadownav-imu").also { it.start() }
        thread = t
        val handler = Handler(t.looper)
        // SENSOR_DELAY_FASTEST is a request, not a contract. measuredAccelHz
        // reports what was actually delivered.
        accelSensor?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_FASTEST, handler)
        }
        gyroSensor?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_FASTEST, handler)
        }
    }

    fun stop() {
        sensorManager.unregisterListener(this)
        thread?.quitSafely()
        thread = null
    }

    override fun onSensorChanged(event: SensorEvent) {
        when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> {
                System.arraycopy(event.values, 0, latestAccel, 0, 3)
                haveAccel = true
                if (firstAccelNs == 0L) {
                    firstAccelNs = event.timestamp
                } else {
                    val gap = event.timestamp - lastAccelNs
                    if (gap > maxGapNs) maxGapNs = gap
                }
                lastAccelNs = event.timestamp
                accelCount++
                // Emit on the accelerometer, pairing with the most recent gyro:
                // the two sensors are not synchronised, and waiting for a
                // matched pair would halve the effective rate.
                if (haveGyro) {
                    listener.onImuSample(event.timestamp, latestAccel, latestGyro)
                }
            }
            Sensor.TYPE_GYROSCOPE -> {
                System.arraycopy(event.values, 0, latestGyro, 0, 3)
                haveGyro = true
                gyroCount++
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        // Deliberately ignored. Android's accuracy enum for IMU is coarse and
        // vendor-defined; the filter's own covariance is the honest measure.
    }
}
