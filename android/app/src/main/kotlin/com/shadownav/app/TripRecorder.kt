package com.shadownav.app

import android.content.Context
import java.io.File
import java.io.Writer
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Records a drive to CSV so it can be replayed against the offline pipeline.
 *
 * Without this there is no way to check an on-device claim: the app has no
 * ground truth, the offline evaluation has all the metrics, and nothing
 * connected the two. A recorded trip closes that loop -- the same trace can be
 * scored with `python/scripts/run_mvp.py` and compared like for like.
 *
 * The column set is deliberately a superset of what IO-VNBD provides, and uses
 * the same canonical names as `shadownav/data/schema.py` wherever they overlap,
 * so the existing loader needs a thin adapter rather than a rewrite.
 *
 * Writes are buffered and flushed periodically rather than per row: at 10 Hz
 * over an hour that is 36,000 rows, and an fsync per row would both burn
 * battery and add jitter to the very thread the estimator runs on.
 */
class TripRecorder(private val context: Context) {

    private var writer: Writer? = null
    private var file: File? = null
    private var rows = 0L
    private var startedAtMs = 0L
    private var sinceFlush = 0

    val isRecording: Boolean get() = writer != null
    val rowCount: Long get() = rows
    val currentFile: File? get() = file

    val elapsedS: Double
        get() = if (startedAtMs == 0L) 0.0 else (System.currentTimeMillis() - startedAtMs) / 1000.0

    fun start(): File {
        stop()
        val dir = File(context.getExternalFilesDir(null), "trips").apply { mkdirs() }
        val stamp = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date())
        val f = File(dir, "shadownav-$stamp.csv")
        val w = f.bufferedWriter()
        w.write(HEADER)
        w.write("\n")
        writer = w
        file = f
        rows = 0
        sinceFlush = 0
        startedAtMs = System.currentTimeMillis()
        return f
    }

    fun stop(): File? {
        val w = writer ?: return null
        runCatching {
            w.flush()
            w.close()
        }
        writer = null
        val done = file
        startedAtMs = 0L
        return done
    }

    /** Append one sample. Cheap enough to call at the UI's 10 Hz. */
    fun record(
        s: NavigationEngine.Snapshot,
        imuHz: Double,
        latDeg: Double,
        lonDeg: Double,
        simulatedBlackout: Boolean,
    ) {
        val w = writer ?: return
        runCatching {
            w.write(
                buildString {
                    append(FMT.format(elapsedS)).append(',')
                    append(s.mode.name).append(',')
                    append(if (s.hasFix) 1 else 0).append(',')
                    append(if (simulatedBlackout) 1 else 0).append(',')
                    append(FMT7.format(latDeg)).append(',')
                    append(FMT7.format(lonDeg)).append(',')
                    append(FMT.format(s.eastM)).append(',')
                    append(FMT.format(s.northM)).append(',')
                    append(FMT.format(s.speedMs)).append(',')
                    append(FMT.format(Math.toDegrees(s.headingRad))).append(',')
                    append(FMT.format(s.sigmaM)).append(',')
                    append(FMT.format(s.timeSinceFixS)).append(',')
                    append(FMT.format(s.distanceSinceLossM)).append(',')
                    append(s.gnss.satellitesUsed).append(',')
                    append(s.gnss.satellitesVisible).append(',')
                    append(FMT.format(s.gnss.meanCn0)).append(',')
                    append(s.gnss.navicVisible).append(',')
                    append(s.gnss.navicUsed).append(',')
                    append(FMT.format(s.gnss.agcDb)).append(',')
                    append(FMT.format(s.alignmentQuality)).append(',')
                    append(if (s.aligned) 1 else 0).append(',')
                    append(if (s.stationary) 1 else 0).append(',')
                    append(FMT.format(imuHz)).append(',')
                    append(s.gpsAccepted).append(',')
                    append(s.gpsRejected).append(',')
                    append(s.gateOverrides).append('\n')
                }
            )
            rows++
            // Flush about once a second at 10 Hz. Frequent enough that a crash
            // or a battery pull loses almost nothing, rare enough that the
            // sensor thread is not stalled on IO.
            if (++sinceFlush >= 10) {
                w.flush()
                sinceFlush = 0
            }
        }
    }

    /** Trips on disk, newest first. */
    fun listTrips(): List<File> {
        val dir = File(context.getExternalFilesDir(null), "trips")
        return dir.listFiles()?.sortedByDescending { it.lastModified() } ?: emptyList()
    }

    companion object {
        /** Names match `shadownav/data/schema.py` where they overlap, so the
         *  offline loader needs an adapter rather than a rewrite. */
        const val HEADER =
            "time_s,mode,has_fix,simulated_blackout,est_lat_deg,est_lon_deg," +
                "east_m,north_m,speed_ms,heading_deg,sigma_m,time_since_fix_s," +
                "dr_distance_m,gps_sats_used,gps_sats_visible,cn0_mean," +
                "navic_visible,navic_used,agc_db,alignment_quality,aligned," +
                "stationary,imu_hz,gps_accepted,gps_rejected,gate_overrides"

        private val FMT = object : ThreadLocal<java.text.DecimalFormat>() {
            override fun initialValue() =
                java.text.DecimalFormat("0.###", java.text.DecimalFormatSymbols(Locale.US))
        }.get()!!

        private val FMT7 = object : ThreadLocal<java.text.DecimalFormat>() {
            override fun initialValue() =
                java.text.DecimalFormat("0.#######", java.text.DecimalFormatSymbols(Locale.US))
        }.get()!!
    }
}
