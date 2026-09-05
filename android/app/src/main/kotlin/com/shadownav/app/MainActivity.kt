package com.shadownav.app

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.hardware.SensorManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.MotionEvent
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.shadownav.core.GnssMode
import org.json.JSONObject

/**
 * Live dead-reckoning display.
 *
 * Every readout here exists because some claim in this project depends on it
 * being true, and the two controls are the two things a demo actually needs:
 * force a blackout anywhere, and record the drive so it can be checked against
 * the offline pipeline afterwards.
 *
 * The Activity owns no capture. It binds to [NavigationService], which keeps
 * running when this screen is gone -- losing a drive because the screen turned
 * off was a real failure on the first hardware test.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var track: TrackView
    private lateinit var chip: StatusChip
    private lateinit var subtitle: TextView
    private lateinit var speed: Metric
    private lateinit var heading: Metric
    private lateinit var confidence: Metric
    private lateinit var confidenceBar: ConfidenceBar
    private lateinit var tripStats: TextView
    private lateinit var diagnostics: TextView
    private lateinit var blackoutButton: TextView
    private lateinit var recordButton: TextView

    private var service: NavigationService? = null
    private var recorder: TripRecorder? = null

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

    private val refresh = object : Runnable {
        override fun run() {
            render()
            if (running) ui.postDelayed(this, 100)   // 10 Hz, matching the PS
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        recorder = TripRecorder(this)
        setContentView(buildUi())
        track.conformalLambda = loadConformalLambda()

        val probe = SensorCapture(getSystemService(SENSOR_SERVICE) as SensorManager) { _, _, _ -> }
        if (!probe.hasRequiredSensors) {
            chip.set("UNUSABLE DEVICE", Palette.MAGENTA)
            subtitle.text = probe.describeSensors()
            return
        }
        requestPermissionIfNeeded()
    }

    // ------------------------------------------------------------------ UI

    private fun buildUi(): ViewGroup {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Palette.BG)
        }
        // Without this the header renders under the status bar clock.
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(0, bars.top, 0, bars.bottom)
            insets
        }

        // -- header ------------------------------------------------------
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(18f), dp(14f), dp(18f), dp(8f))
        }
        val titles = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        }
        titles.addView(TextView(this).apply {
            text = "ShadowNav"
            textSize = 20f
            typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
            setTextColor(Palette.TEXT)
        })
        subtitle = TextView(this).apply {
            text = "starting"
            textSize = 12f
            setTextColor(Palette.DIM)
        }
        titles.addView(subtitle)
        chip = StatusChip(this).apply { set("ACQUIRING", Palette.SLATE) }
        header.addView(titles)
        header.addView(chip)
        root.addView(header)

        val scroll = ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f,
            )
            isFillViewport = true
        }
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14f), 0, dp(14f), dp(14f))
        }

        // -- primary metrics --------------------------------------------
        val metrics = card().apply {
            orientation = LinearLayout.VERTICAL
        }
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        speed = Metric(this, "KM/H")
        heading = Metric(this, "HEADING")
        confidence = Metric(this, "90% RADIUS")
        row.addView(speed); row.addView(heading); row.addView(confidence)
        metrics.addView(row)
        confidenceBar = ConfidenceBar(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = dp(12f) }
        }
        metrics.addView(confidenceBar)
        column.addView(metrics, cardParams())

        // -- map ---------------------------------------------------------
        track = TrackView(this)
        val mapCard = card().apply { setPadding(dp(4f), dp(4f), dp(4f), dp(4f)) }
        mapCard.addView(track, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(300f),
        ))
        column.addView(mapCard, cardParams())

        // -- controls -----------------------------------------------------
        val controls = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        blackoutButton = actionButton(
            "SIMULATE TUNNEL", filled = false, colour = Palette.MAGENTA,
            description = "Press and hold to simulate a GNSS blackout",
        )
        // Press and hold rather than toggle: a blackout is a thing you are
        // doing, and holding makes the demo impossible to leave switched on by
        // accident, which would silently invalidate everything after it.
        blackoutButton.setOnTouchListener { v, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    service?.engine?.simulateBlackout = true
                    v.performClick(); true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    service?.engine?.simulateBlackout = false; true
                }
                else -> false
            }
        }
        recordButton = actionButton(
            "RECORD", filled = true, colour = Palette.CYAN,
            description = "Start recording this trip to a CSV file",
        )
        recordButton.setOnClickListener { toggleRecording() }
        controls.addView(blackoutButton)
        controls.addView(recordButton)
        column.addView(controls, cardParams())

        // -- trip summary -------------------------------------------------
        val trip = card()
        trip.addView(label("TRIP"))
        tripStats = mono(12f).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = dp(6f) }
        }
        trip.addView(tripStats)
        column.addView(trip, cardParams())

        // -- diagnostics ---------------------------------------------------
        val diag = card()
        diag.addView(label("DIAGNOSTICS"))
        diagnostics = mono(11.5f).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = dp(6f) }
        }
        diag.addView(diagnostics)
        column.addView(diag, cardParams())

        scroll.addView(column)
        root.addView(scroll)
        return root
    }

    private fun cardParams() = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
    ).apply { topMargin = dp(10f) }

    // -------------------------------------------------------------- render

    private fun render() {
        val svc = service ?: return
        val sensors = svc.sensors
        val gnss = svc.gnss
        val s = svc.engine.snapshot()

        // Before the first fix the filter has not started, so the state machine
        // still reads its initial value. Showing AIDED there would assert GNSS
        // aiding with zero satellites.
        val (chipText, chipColour) = when {
            !s.hasFix -> "ACQUIRING" to Palette.SLATE
            s.simulatedBlackout -> "SIMULATED BLACKOUT" to Palette.MAGENTA
            s.mode == GnssMode.AIDED -> "GNSS AIDED" to Palette.CYAN
            s.mode == GnssMode.DEGRADED -> "DEGRADED" to Palette.AMBER
            s.mode == GnssMode.REACQUIRING -> "REACQUIRING" to Palette.AMBER
            else -> "DEAD RECKONING" to Palette.MAGENTA
        }
        chip.set(chipText, chipColour)

        subtitle.text = when {
            !s.hasFix -> "waiting for a fix  ·  %d satellites visible".format(
                s.gnss.satellitesVisible,
            )
            s.stationary -> "stationary  ·  speed held at zero"
            s.timeSinceFixS > 2.0 -> "no fix for %.0f s  ·  %.0f m dead reckoned".format(
                s.timeSinceFixS, s.distanceSinceLossM,
            )
            else -> "%d satellites in fix  ·  %.0f dB-Hz".format(
                s.gnss.satellitesUsed, s.gnss.meanCn0,
            )
        }

        speed.set(if (s.hasFix) "%.0f".format(s.speedMs * 3.6) else "--")
        heading.set(
            if (s.hasFix) "%.0f°".format((Math.toDegrees(s.headingRad) + 360) % 360) else "--",
        )
        // The calibrated radius, never the raw covariance: raw understates by
        // 15-22x, and a confidence display that wrong is worse than none.
        val radius = s.sigmaM * track.conformalLambda * 2.146
        confidence.set(
            if (radius.isFinite()) "%.0f m".format(radius) else "--",
            when {
                !radius.isFinite() -> Palette.TEXT
                radius < 15 -> Palette.GOOD
                radius < 45 -> Palette.AMBER
                else -> Palette.MAGENTA
            },
        )
        confidenceBar.sigmaM = radius

        val rec = recorder
        tripStats.text = buildString {
            append("distance      %.0f m over %.0f s\n".format(s.tripDistanceM, s.tripDurationS))
            append("dead reckoned %.0f s  ·  longest run %.0f m\n".format(
                s.tripTimeInDrS, s.tripMaxDrDistanceM,
            ))
            append(
                if (rec?.isRecording == true) {
                    "recording     %d rows  ·  %.0f s".format(rec.rowCount, rec.elapsedS)
                } else {
                    "not recording"
                }
            )
        }

        val g = s.gnss
        diagnostics.text = buildString {
            append("IMU %.0f Hz measured (claims %.0f)  max gap %.0f ms%s\n".format(
                sensors.measuredAccelHz, sensors.advertisedAccelHz, sensors.maxGapMs,
                if (sensors.degraded) "  [RATE DEGRADED]" else "",
            ))
            append("sats %d/%d in fix   mean C/N0 %.1f dB-Hz\n".format(
                g.satellitesUsed, g.satellitesVisible, g.meanCn0,
            ))
            // Instrumentation only: a phone sees 1-3 NavIC satellites against
            // the 4 needed for a fix. Never a positioning claim.
            append("NavIC %d visible / %d in fix   (instrumentation only)\n".format(
                g.navicVisible, g.navicUsed,
            ))
            append(gnss.agcStatusText()).append('\n')
            append("alignment %.2f %s\n".format(
                s.alignmentQuality,
                if (s.aligned) "(car frame)" else "(device frame, NHC off)",
            ))
            append("fixes %d ok / %d gated / %d override".format(
                s.gpsAccepted, s.gpsRejected, s.gateOverrides,
            ))
        }

        track.push(s)
        if (rec?.isRecording == true) {
            val ll = svc.engine.estimateLatLon()
            rec.record(
                s, sensors.measuredAccelHz,
                ll?.get(0) ?: Double.NaN, ll?.get(1) ?: Double.NaN,
                s.simulatedBlackout,
            )
        }
    }

    // ----------------------------------------------------------- recording

    private fun toggleRecording() {
        val rec = recorder ?: return
        if (rec.isRecording) {
            val file = rec.stop()
            recordButton.text = "RECORD"
            recordButton.contentDescription = "Start recording this trip to a CSV file"
            if (file != null && file.exists()) shareTrip(file)
        } else {
            val file = rec.start()
            recordButton.text = "STOP & SHARE"
            recordButton.contentDescription = "Stop recording and share the trip file"
            Toast.makeText(this, "recording to ${file.name}", Toast.LENGTH_SHORT).show()
        }
    }

    /** Hand the CSV to whatever the user wants: the point is getting it off the
     *  phone and into `python/scripts/run_mvp.py`. */
    private fun shareTrip(file: java.io.File) {
        val uri = runCatching {
            FileProvider.getUriForFile(this, "$packageName.trips", file)
        }.getOrNull() ?: run {
            Toast.makeText(this, "saved ${file.name}", Toast.LENGTH_LONG).show()
            return
        }
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "text/csv"
            putExtra(Intent.EXTRA_STREAM, uri)
            putExtra(Intent.EXTRA_SUBJECT, file.name)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(Intent.createChooser(send, "Share trip"))
    }

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
        } else if (requestCode == REQ_LOCATION) {
            chip.set("NO PERMISSION", Palette.MAGENTA)
            subtitle.text = "location access is required"
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
        maybeRequestBackgroundLocation()
    }

    /** Background location is a separate second-stage grant on Android 10+ and
     *  can only be asked for once foreground location is held. Declining is
     *  survivable: the service still runs while the app is visible. */
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

    private fun loadConformalLambda(): Double = runCatching {
        assets.open("conformal.json").bufferedReader().use { reader ->
            JSONObject(reader.readText()).getJSONObject("factors").optDouble("60.0", 1.0)
        }
    }.getOrDefault(1.0)

    override fun onDestroy() {
        super.onDestroy()
        running = false
        ui.removeCallbacks(refresh)
        recorder?.stop()
        // Unbind only. The service keeps running deliberately: closing the
        // screen mid-tunnel must not end the drive.
        runCatching { unbindService(connection) }
    }

    companion object {
        private const val REQ_LOCATION = 1001
        private const val REQ_BACKGROUND = 1002
    }
}
