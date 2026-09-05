package com.shadownav.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.util.AttributeSet
import android.view.View
import com.shadownav.core.GnssMode
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin

/**
 * Live track with a confidence ring.
 *
 * Colour language is taken from `demo/gnss-demo.html` so the presentation demo
 * and the running app read as the same system: cyan aided, amber degrading,
 * magenta dead reckoning.
 *
 * The ring is the **calibrated** 90% containment radius, not the filter's own.
 * Drawing the raw covariance would understate uncertainty by a factor of 15-22
 * -- offline, nominal 90% ellipses contained 17% of errors. A confidence
 * display that is wrong by that much is worse than none.
 */
class TrackView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null,
) : View(context, attrs) {

    private val trackAided = ArrayList<FloatArray>()
    private val trackDr = ArrayList<FloatArray>()
    private var current: FloatArray? = null
    private var headingRad = 0.0
    private var sigmaM = Double.NaN
    private var mode = GnssMode.AIDED

    /** Conformal inflation for the 90% ellipse, per horizon. Loaded from
     *  shared/conformal.json; 1.0 until then, which is honest rather than
     *  optimistic since it under-states rather than invents. */
    var conformalLambda = 1.0

    private val paintAided = stroke(0xFF4DE0E8.toInt(), 4f)
    private val paintDr = stroke(0xFFE24DBE.toInt(), 4f)
    private val paintRing = stroke(0xFFE8A33D.toInt(), 2f).apply { alpha = 150 }
    private val paintGrid = stroke(0xFF1B2530.toInt(), 1f)
    private val paintVehicle = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = 0xFF4DE0E8.toInt()
    }
    private val paintLabel = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF7C8A99.toInt()
        textSize = 26f
    }

    private fun stroke(colour: Int, width: Float) = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = colour
        strokeWidth = width
        strokeJoin = Paint.Join.ROUND
        strokeCap = Paint.Cap.ROUND
    }

    fun push(snapshot: NavigationEngine.Snapshot) {
        // The map is the primary visual and previously announced nothing at all.
        contentDescription = if (!snapshot.hasFix) {
            "track map, waiting for a first position fix"
        } else {
            "track map, %s, %.0f metres travelled, %d dead-reckoned points".format(
                snapshot.mode.name.replace('_', ' ').lowercase(),
                snapshot.tripDistanceM, trackDr.size,
            )
        }
        if (!snapshot.hasFix) return
        val p = floatArrayOf(snapshot.eastM.toFloat(), snapshot.northM.toFloat())
        val dr = snapshot.mode == GnssMode.DEAD_RECKONING ||
            snapshot.mode == GnssMode.REACQUIRING
        // Two separate polylines rather than one coloured per segment: the
        // break itself is the thing worth seeing.
        if (dr) trackDr.add(p) else trackAided.add(p)
        if (trackAided.size > 4000) trackAided.subList(0, 1000).clear()
        if (trackDr.size > 4000) trackDr.subList(0, 1000).clear()

        current = p
        headingRad = snapshot.headingRad
        sigmaM = snapshot.sigmaM
        mode = snapshot.mode
        invalidate()
    }

    fun clear() {
        trackAided.clear()
        trackDr.clear()
        current = null
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawColor(0xFF07090C.toInt())

        val here = current ?: run {
            canvas.drawText("waiting for first GNSS fix", 40f, height / 2f, paintLabel)
            return
        }

        // Auto-scale to the track's extent, floored so a stationary vehicle
        // does not zoom to absurdity.
        var minE = here[0]; var maxE = here[0]
        var minN = here[1]; var maxN = here[1]
        for (list in listOf(trackAided, trackDr)) {
            for (p in list) {
                if (p[0] < minE) minE = p[0]
                if (p[0] > maxE) maxE = p[0]
                if (p[1] < minN) minN = p[1]
                if (p[1] > maxN) maxN = p[1]
            }
        }
        val spanM = max(max(maxE - minE, maxN - minN), 60f)
        val pad = 60f
        val scale = (max(1, minOf(width, height)) - 2 * pad) / spanM
        val cx = (minE + maxE) / 2f
        val cy = (minN + maxN) / 2f

        fun sx(e: Float) = width / 2f + (e - cx) * scale
        fun sy(n: Float) = height / 2f - (n - cy) * scale

        // 100 m grid, so the scale is readable without a legend.
        val step = 100f * scale
        if (step > 24f) {
            var g = width / 2f % step
            while (g < width) { canvas.drawLine(g, 0f, g, height.toFloat(), paintGrid); g += step }
            g = height / 2f % step
            while (g < height) { canvas.drawLine(0f, g, width.toFloat(), g, paintGrid); g += step }
        }

        fun polyline(points: List<FloatArray>, paint: Paint) {
            if (points.size < 2) return
            val path = Path()
            path.moveTo(sx(points[0][0]), sy(points[0][1]))
            for (i in 1 until points.size) path.lineTo(sx(points[i][0]), sy(points[i][1]))
            canvas.drawPath(path, paint)
        }
        polyline(trackAided, paintAided)
        polyline(trackDr, paintDr)

        // Calibrated containment ring.
        if (!sigmaM.isNaN() && sigmaM.isFinite()) {
            // 90% of a 2D Gaussian lies within sqrt(-2 ln 0.1) = 2.146 sigma.
            val radius = (sigmaM * conformalLambda * 2.146).toFloat() * scale
            if (radius > 2f) canvas.drawCircle(sx(here[0]), sy(here[1]), radius, paintRing)
        }

        // Vehicle chevron, pointing along the estimated heading.
        paintVehicle.color = when (mode) {
            GnssMode.AIDED -> 0xFF4DE0E8.toInt()
            GnssMode.DEGRADED -> 0xFFE8A33D.toInt()
            else -> 0xFFE24DBE.toInt()
        }
        val h = headingRad
        val x = sx(here[0])
        val y = sy(here[1])
        val chevron = Path()
        val size = 22f
        // Heading is clockwise from north; screen y is inverted.
        val dx = sin(h).toFloat()
        val dy = -cos(h).toFloat()
        chevron.moveTo(x + dx * size, y + dy * size)
        chevron.lineTo(x - dy * size * 0.6f - dx * size * 0.5f,
                       y + dx * size * 0.6f - dy * size * 0.5f)
        chevron.lineTo(x + dy * size * 0.6f - dx * size * 0.5f,
                       y - dx * size * 0.6f - dy * size * 0.5f)
        chevron.close()
        canvas.drawPath(chevron, paintVehicle)

        canvas.drawText("grid 100 m", 24f, height - 24f, paintLabel)
        if (conformalLambda > 1.0) {
            canvas.drawText(
                "ring: 90%% calibrated (x%.1f)".format(conformalLambda),
                24f, height - 56f, paintLabel,
            )
        }
    }
}
