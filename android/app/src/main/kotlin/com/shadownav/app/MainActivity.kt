package com.shadownav.app

import android.Manifest
import android.content.pm.PackageManager
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
class MainActivity : AppCompatActivity(), SensorCapture.Listener, GnssCapture.Listener {

    private lateinit var track: TrackView
    private lateinit var modeLabel: TextView
    private lateinit var readout: TextView
    private lateinit var diagnostics: TextView

    private lateinit var sensors: SensorCapture
    private lateinit var gnss: GnssCapture
    private val engine = NavigationEngine()

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

        sensors = SensorCapture(
            getSystemService(SENSOR_SERVICE) as SensorManager, this,
        )
        gnss = GnssCapture(this, this)
        track.conformalLambda = loadConformalLambda()

        if (!sensors.hasRequiredSensors) {
            modeLabel.text = "UNUSABLE DEVICE"
            readout.text = sensors.describeSensors()
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
                engine.reset()
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
        val s = engine.snapshot()
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
            append("align q %.2f %s   fixes %d ok / %d rejected / %d override".format(
                s.alignmentQuality,
                if (s.aligned) "(car frame)" else "(device frame, NHC off)",
                s.gpsAccepted, s.gpsRejected, s.gateOverrides,
            ))
        }

        track.push(s)
        logPeriodically(s)
    }

    /**
     * One diagnostic line per second to logcat.
     *
     * Exists so a drive can be reviewed afterwards, and so the app can be
     * verified over adb without reading the screen. The IMU rate leads the line
     * deliberately: it is the variable every offline result depended on.
     */
    private fun logPeriodically(s: NavigationEngine.Snapshot) {
        val now = System.currentTimeMillis()
        if (now - lastLogMs < 1000) return
        lastLogMs = now
        val g = s.gnss
        // The whole concatenation must be parenthesised before .format():
        // in Kotlin `.format()` binds tighter than `+`, so without the parens
        // only the final literal is formatted and it receives all 18 arguments
        // -- a %d against a Double, which throws at runtime.
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
        sensors.start()
        gnss.start()
        ui.post(refresh)
    }

    override fun onDestroy() {
        super.onDestroy()
        running = false
        ui.removeCallbacks(refresh)
        if (this::sensors.isInitialized) sensors.stop()
        if (this::gnss.isInitialized) gnss.stop()
    }

    // ------------------------------------------------------------ callbacks

    override fun onImuSample(timestampNs: Long, accel: FloatArray?, gyro: FloatArray?) {
        if (accel == null || gyro == null) return
        engine.onImuSample(timestampNs, accel, gyro)
    }

    override fun onFix(location: Location) = engine.onFix(location)

    override fun onStatus(snapshot: GnssCapture.Snapshot) = engine.onStatus(snapshot)

    companion object {
        private const val REQ_LOCATION = 1001
        private const val TAG = "ShadowNav"
    }
}
