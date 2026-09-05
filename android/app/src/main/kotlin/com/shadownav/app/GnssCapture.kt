package com.shadownav.app

import android.annotation.SuppressLint
import android.content.Context
import android.location.GnssMeasurementsEvent
import android.location.GnssStatus
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Handler
import android.os.Looper

/**
 * GNSS capture: fixes, per-satellite C/N0, NavIC visibility, and AGC where the
 * device offers it.
 *
 * Three deliberate positions, each recorded because the offline work could not
 * settle them:
 *
 * **C/N0 is the primary degradation signal, not AGC.** The offline dataset has
 * no carrier-to-noise column at all, so the degradation handler could not be
 * validated there. On device it is available from API 24 and universally
 * populated, so it carries the work.
 *
 * **AGC is opportunistic and never required.** It needs API 33, and Google's
 * own documentation says it is not reported when a signal is too weak to
 * acquire -- which is precisely inside a tunnel, the primary target scenario.
 * This class reports whether it was ever seen so a claim can be qualified
 * honestly rather than assumed.
 *
 * **NavIC is instrumentation, not accuracy.** Enumerating IRNSS satellites is
 * genuinely useful and uniquely relevant, but a phone typically sees 1-3
 * against the 4 needed for a fix. Never claim a positioning improvement from
 * this panel.
 */
class GnssCapture(
    context: Context,
    private val listener: Listener,
) {

    interface Listener {
        fun onFix(location: Location)
        fun onStatus(snapshot: Snapshot)
    }

    /** Everything the receiver is telling us at one instant. */
    data class Snapshot(
        val satellitesUsed: Int,
        val satellitesVisible: Int,
        val meanCn0: Double,
        val navicVisible: Int,
        val navicUsed: Int,
        val agcDb: Double,
        val agcSupported: Boolean,
    )

    private val locationManager =
        context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    private val handler = Handler(Looper.getMainLooper())

    /** True once AGC has actually been observed. Distinguishes "unsupported"
     *  from "supported but currently silent", which matters in a tunnel. */
    var agcEverSeen = false
        private set

    private var lastAgc = Double.NaN

    private val locationListener = LocationListener { listener.onFix(it) }

    private val statusCallback = object : GnssStatus.Callback() {
        override fun onSatelliteStatusChanged(status: GnssStatus) {
            var used = 0
            var cn0Sum = 0.0
            var cn0Count = 0
            var navicVisible = 0
            var navicUsed = 0

            for (i in 0 until status.satelliteCount) {
                val inFix = status.usedInFix(i)
                if (inFix) used++
                val cn0 = status.getCn0DbHz(i)
                if (cn0 > 0f) {
                    cn0Sum += cn0
                    cn0Count++
                }
                // CONSTELLATION_IRNSS is API 29, which is why 29 is the floor.
                if (status.getConstellationType(i) == GnssStatus.CONSTELLATION_IRNSS) {
                    navicVisible++
                    if (inFix) navicUsed++
                }
            }

            listener.onStatus(
                Snapshot(
                    satellitesUsed = used,
                    satellitesVisible = status.satelliteCount,
                    meanCn0 = if (cn0Count > 0) cn0Sum / cn0Count else Double.NaN,
                    navicVisible = navicVisible,
                    navicUsed = navicUsed,
                    agcDb = lastAgc,
                    agcSupported = agcEverSeen,
                )
            )
        }
    }

    private val measurementsCallback = object : GnssMeasurementsEvent.Callback() {
        override fun onGnssMeasurementsReceived(event: GnssMeasurementsEvent) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
            // Event-level AGC (API 33). The older per-measurement
            // getAutomaticGainControlLevelDb() is deprecated as of API 34.
            val agcs = event.gnssAutomaticGainControls
            if (agcs.isNullOrEmpty()) return
            lastAgc = agcs.map { it.levelDb }.average()
            agcEverSeen = true
        }
    }

    @SuppressLint("MissingPermission")
    fun start() {
        locationManager.registerGnssStatusCallback(statusCallback, handler)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            runCatching {
                locationManager.registerGnssMeasurementsCallback(
                    { it.run() }, measurementsCallback,
                )
            }
        }
        runCatching {
            locationManager.requestLocationUpdates(
                LocationManager.GPS_PROVIDER,
                // Ask for every fix the receiver produces. The offline dataset
                // held fixes for a median of 9 s, which crippled evaluation;
                // on device we take whatever the receiver will give.
                0L, 0f, locationListener, Looper.getMainLooper(),
            )
        }
    }

    fun stop() {
        locationManager.unregisterGnssStatusCallback(statusCallback)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            runCatching { locationManager.unregisterGnssMeasurementsCallback(measurementsCallback) }
        }
        runCatching { locationManager.removeUpdates(locationListener) }
    }

    /** Honest one-line status for the AGC feature, for the UI and for a pitch. */
    fun agcStatusText(): String = when {
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ->
            "AGC unavailable (needs API 33, this device is ${Build.VERSION.SDK_INT})"
        agcEverSeen -> "AGC ${"%.1f".format(lastAgc)} dB"
        else -> "AGC supported by API but not yet reported"
    }
}
