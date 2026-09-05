package com.shadownav.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.hardware.SensorManager
import android.location.Location
import android.os.Binder
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log

/**
 * Keeps the estimator running when the app is not on screen.
 *
 * This exists because the first hardware test failed without it. Sensor capture
 * and the filter lived in the Activity, so the moment the user switched apps
 * Android froze the process and collection stopped dead after two minutes. For
 * an app whose entire purpose is to survive a tunnel, losing state because the
 * screen turned off is not a limitation, it is a defect.
 *
 * A foreground service is the only reliable way to keep sensor and location
 * callbacks alive on modern Android. The notification is not decoration -- it is
 * the platform's required, and reasonable, price for background location, and it
 * doubles as a live readout the user can see without unlocking.
 */
class NavigationService : Service(), SensorCapture.Listener, GnssCapture.Listener {

    private val binder = LocalBinder()

    lateinit var sensors: SensorCapture
        private set
    lateinit var gnss: GnssCapture
        private set

    val engine = NavigationEngine()

    private val ui = Handler(Looper.getMainLooper())
    private var started = false
    private var lastLogMs = 0L
    private var lastNotifyMs = 0L

    inner class LocalBinder : Binder() {
        val service: NavigationService get() = this@NavigationService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onCreate() {
        super.onCreate()
        sensors = SensorCapture(getSystemService(SENSOR_SERVICE) as SensorManager, this)
        gnss = GnssCapture(this, this)
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        startForeground(NOTIFICATION_ID, buildNotification("starting"))
        if (!started) {
            started = true
            sensors.start()
            gnss.start()
            ui.post(tick)
        }
        // START_STICKY so a low-memory kill mid-drive is recovered from rather
        // than silently ending the log.
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        started = false
        ui.removeCallbacks(tick)
        if (this::sensors.isInitialized) sensors.stop()
        if (this::gnss.isInitialized) gnss.stop()
    }

    /**
     * Logging and notification refresh.
     *
     * Runs at 1 Hz rather than the UI's 10 Hz: the estimator is driven by sensor
     * callbacks, not by this, so this loop only has to keep the record and the
     * notification current. Anything faster would burn battery for no
     * information.
     */
    private val tick = object : Runnable {
        override fun run() {
            val s = engine.snapshot()
            logLine(s)
            updateNotification(s)
            if (started) ui.postDelayed(this, 1000)
        }
    }

    private fun logLine(s: NavigationEngine.Snapshot) {
        val now = System.currentTimeMillis()
        if (now - lastLogMs < 1000) return
        lastLogMs = now
        val g = s.gnss
        // The whole concatenation is parenthesised before .format(): in Kotlin
        // `.format()` binds tighter than `+`, so without the parens only the
        // final literal is formatted and receives every argument.
        Log.i(
            TAG,
            ("imu=%.0fHz gap=%.0fms mode=%s fix=%b v=%.1f hdg=%.0f sigma=%.1f " +
                "tsf=%.1f dr=%.0fm sats=%d/%d cn0=%.1f navic=%d/%d alignQ=%.2f " +
                "gps=%d/%d ovr=%d").format(
                    sensors.measuredAccelHz, sensors.maxGapMs, s.mode.name, s.hasFix,
                    s.speedMs, Math.toDegrees(s.headingRad), s.sigmaM,
                    s.timeSinceFixS, s.distanceSinceLossM,
                    g.satellitesUsed, g.satellitesVisible, g.meanCn0,
                    g.navicVisible, g.navicUsed, s.alignmentQuality,
                    s.gpsAccepted, s.gpsRejected, s.gateOverrides,
                ),
        )
    }

    private fun updateNotification(s: NavigationEngine.Snapshot) {
        val now = System.currentTimeMillis()
        if (now - lastNotifyMs < 2000) return
        lastNotifyMs = now
        val text = if (!s.hasFix) {
            "ACQUIRING  sats %d  IMU %.0f Hz".format(
                s.gnss.satellitesUsed, sensors.measuredAccelHz,
            )
        } else {
            "%s  %.0f km/h  sats %d  IMU %.0f Hz".format(
                s.mode.name.replace('_', ' '), s.speedMs * 3.6,
                s.gnss.satellitesUsed, sensors.measuredAccelHz,
            )
        }
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }

    private fun createChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID, "Navigation", NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Keeps dead reckoning alive while the app is not on screen"
            setShowBadge(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun buildNotification(text: String): Notification {
        val open = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("ShadowNav")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentIntent(open)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
    }

    // ------------------------------------------------------------ callbacks

    override fun onImuSample(timestampNs: Long, accel: FloatArray?, gyro: FloatArray?) {
        if (accel == null || gyro == null) return
        engine.onImuSample(timestampNs, accel, gyro)
    }

    override fun onFix(location: Location) = engine.onFix(location)

    override fun onStatus(snapshot: GnssCapture.Snapshot) = engine.onStatus(snapshot)

    companion object {
        private const val TAG = "ShadowNav"
        private const val CHANNEL_ID = "shadownav.navigation"
        private const val NOTIFICATION_ID = 1
        const val ACTION_STOP = "com.shadownav.app.STOP"

        fun start(context: Context) {
            val intent = Intent(context, NavigationService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, NavigationService::class.java))
        }
    }
}
