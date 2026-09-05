package com.shadownav.app

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.IBinder
import android.graphics.Color
import android.graphics.Typeface
import android.hardware.SensorManager
import android.location.Location
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.shadownav.core.GnssMode
import org.json.JSONObject

/**
 * Live dead-reckoning display.
 *
 * The UI is built in code rather than XML deliberately: it is a diagnostic
 * instrument, and every readout on it exists because some claim in this project
 * depends on it being true. The measured IMU rate in particular is not a
 * curiosity -- every negative result in the offline work traced to 10 Hz
 * logging, so a number produced on a phone is only meaningful alongside the
 * rate it was produced at.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var track: TrackView
    private lateinit var modeLabel: TextView
    private lateinit var readout: TextView
    private lateinit var diagnostics: TextView

    /** The Activity owns none of the capture. It binds to the service, which
     *  keeps running when this screen is gone. */
    private var service: NavigationService? = null

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            service = (binder as? NavigationService.LocalBinder)?.service
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            service = null
        }
    }

    private val ui = Handler(Looper.getMainLooper())
    private var running = false

    /** Wall-clock of the last diagnostic log line. The UI refreshes at 10 Hz;
     *  logging at that rate would flood logcat and change the thing being
     *  measured. Once a second is enough to see a rate settle or a mode flip. */
    private var lastLogMs = 0L

    private val refresh = object : Runnable {
        override fun run() {
            render()
            if (running) ui.postDelayed(this, 100)   // 10 Hz, matching the PS
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildUi())

        track.conformalLambda = loadConformalLambda()

        val probe = SensorCapture(getSystemService(SENSOR_SERVICE) as SensorManager) { _, _, _ -> }
        if (!probe.hasRequiredSensors) {
            modeLabel.text = "UNUSABLE DEVICE"
            readout.text = probe.describeSensors()
            return
        }
        requestPermissionIfNeeded()
    }

    // ------------------------------------------------------------------ UI

    private fun buildUi(): ViewGroup {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xFF07090C.toInt())
        }
        // Without this the mode label renders underneath the status bar and is
        // unreadable against the clock. Observed on a moto g64.
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(0, bars.top, 0, bars.bottom)
            insets
        }

        modeLabel = TextView(this).apply {
            textSize = 22f
            setTypeface(Typeface.MONOSPACE, Typeface.BOLD)
            setTextColor(0xFF4DE0E8.toInt())
            setPadding(28, 36, 28, 8)
            text = "STARTING"
        }
        readout = TextView(this).apply {
            textSize = 15f
            typeface = Typeface.MONOSPACE
            setTextColor(0xFFD8E2EC.toInt())
            setPadding(28, 0, 28, 12)
        }
        track = TrackView(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f,
            )
        }
        diagnostics = TextView(this).apply {
            textSize = 13f
            typeface = Typeface.MONOSPACE
            setTextColor(0xFF7C8A99.toInt())
            setPadding(28, 12, 28, 12)
        }
        val reset = Button(this).apply {
            text = "RESET"
            setOnClickListener {
                service?.engine?.reset()
                track.clear()
            }
        }
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setPadding(28, 0, 28, 24)
            addView(reset)
        }

        root.addView(modeLabel)
        root.addView(readout)
        root.addView(track)
        root.addView(diagnostics)
        root.addView(bar)
        return root
    }

    private fun render() {
        val svc = service ?: run {
            modeLabel.text = "STARTING"
            return
        }
        val sensors = svc.sensors
        val gnss = svc.gnss
        val s = svc.engine.snapshot()
        // Before the first fix the filter has not started, so the state machine
        // has not run either and still reads AIDED. Showing that would claim
        // GNSS aiding while there is no fix at all, which is exactly the kind
        // of confident-and-wrong display this project exists to avoid.
        modeLabel.text = if (s.hasFix) s.mode.name.replace('_', ' ') else "ACQUIRING"
        modeLabel.setTextColor(
            when {
                !s.hasFix -> 0xFF7C8A99.toInt()
                s.mode == GnssMode.AIDED -> 0xFF4DE0E8.toInt()
                s.mode == GnssMode.DEGRADED -> 0xFFE8A33D.toInt()
                else -> 0xFFE24DBE.toInt()
            }
        )

        val drift = if (s.distanceSinceLossM > 1.0 && !s.sigmaM.isNaN()) {
            "  drift %.1f%%".format(100.0 * s.sigmaM / s.distanceSinceLossM)
        } else {
            ""
        }
        readout.text = buildString {
            append("speed  %5.1f m/s   (%4.1f km/h)\n".format(s.speedMs, s.speedMs * 3.6))
            append("head   %5.0f deg\n".format(Math.toDegrees(s.headingRad)))
            append("sigma  %5.1f m  90%% ring%s\n".format(s.sigmaM, drift))
            append("no fix for %.1f s".format(s.timeSinceFixS))
            if (s.distanceSinceLossM > 1.0) {
                append("   DR %.0f m".format(s.distanceSinceLossM))
            }
        }

        val g = s.gnss
        diagnostics.text = buildString {
            // The rate is the headline diagnostic, not a footnote: it is the
            // variable every offline negative result depended on.
            append("IMU %.0f Hz measured (device claims %.0f)  max gap %.0f ms\n".format(
                sensors.measuredAccelHz, sensors.advertisedAccelHz, sensors.maxGapMs,
            ))
            append("sats %d/%d used  mean C/N0 %.1f dB-Hz\n".format(
                g.satellitesUsed, g.satellitesVisible, g.meanCn0,
            ))
            // Instrumentation only. A phone sees 1-3 NavIC satellites against
            // the 4 needed for a fix; this is never a positioning claim.
            append("NavIC %d visible / %d in fix   (instrumentation only)\n".format(
                g.navicVisible, g.navicUsed,
            ))
            append(gnss.agcStatusText()).append('\n')
            if (s.stationary) {
                // Zero-velocity update active: worth showing, because it is the
                // difference between a parked phone holding position and one
                // dead-reckoning away at a stale speed.
                append("STATIONARY  speed held at zero")
                append('\n')
            }
            append("align q %.2f %s   fixes %d ok / %d rejected / %d override".format(
                s.alignmentQuality,
                if (s.aligned) "(car frame)" else "(device frame, NHC off)",
                s.gpsAccepted, s.gpsRejected, s.gateOverrides,
            ))
        }

        track.push(s)
    }

    /** Read the conformal inflation shipped from the Python calibration. */
    private fun loadConformalLambda(): Double = runCatching {
        assets.open("conformal.json").bufferedReader().use { reader ->
            val factors = JSONObject(reader.readText()).getJSONObject("factors")
            // A 60 s horizon is the middle of the range the calibration covers
            // and a reasonable default for a live display, which has no notion
            // of how long the current outage will last.
            factors.optDouble("60.0", 1.0)
        }
    }.getOrDefault(1.0)

    // --------------------------------------------------------- permissions

    private fun requestPermissionIfNeeded() {
        val granted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) startCapture() else {
            ActivityCompat.requestPermissions(
                this, arrayOf(Manifest.permission.ACCESS_FINE_LOCATION), REQ_LOCATION,
            )
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_LOCATION &&
            grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
        ) {
            startCapture()
        } else {
            modeLabel.text = "LOCATION PERMISSION REQUIRED"
        }
    }

    private fun startCapture() {
        if (running) return
        running = true
        NavigationService.start(this)
        bindService(
            Intent(this, NavigationService::class.java), connection, Context.BIND_AUTO_CREATE,
        )
        ui.post(refresh)
        // Background location is a separate, second-stage grant on Android 10+
        // and can only be asked for once foreground location is already held.
        maybeRequestBackgroundLocation()
    }

    /** Ask for background location so the service keeps receiving fixes when
     *  the screen is off. Declined is survivable: the service still runs, and
     *  Android delivers fixes while the app is visible. */
    private fun maybeRequestBackgroundLocation() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return
        val held = ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_BACKGROUND_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (!held) {
            ActivityCompat.requestPermissions(
                this, arrayOf(Manifest.permission.ACCESS_BACKGROUND_LOCATION), REQ_BACKGROUND,
            )
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        running = false
        ui.removeCallbacks(refresh)
        // Unbind only. The service deliberately keeps running: closing the
        // screen mid-tunnel must not end the drive. Stop it from the
        // notification, or with `adb shell am stopservice`.
        runCatching { unbindService(connection) }
    }

    companion object {
        private const val REQ_LOCATION = 1001
        private const val REQ_BACKGROUND = 1002
    }
}
