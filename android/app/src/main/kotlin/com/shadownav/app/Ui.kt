package com.shadownav.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.util.AttributeSet
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Small view vocabulary shared by the main screen.
 *
 * Built in code rather than XML on purpose: the palette and the state colours
 * are the same ones the estimator reasons about, so keeping them next to the
 * code that reads them stops the two drifting apart. There is no design system
 * to inherit from here, only `demo/gnss-demo.html`, and matching it exactly is
 * the point -- the pitch demo and the running app should read as one product.
 */
object Palette {
    const val BG = 0xFF07090C.toInt()
    const val PANEL = 0xFF10161D.toInt()
    const val PANEL_EDGE = 0xFF1D2733.toInt()
    const val CYAN = 0xFF4DE0E8.toInt()
    const val AMBER = 0xFFE8A33D.toInt()
    const val MAGENTA = 0xFFE24DBE.toInt()
    const val SLATE = 0xFF6E7C8C.toInt()
    const val TEXT = 0xFFDCE6F0.toInt()
    const val DIM = 0xFF7C8A99.toInt()
    const val GOOD = 0xFF5BD98A.toInt()
}

fun Context.dp(value: Float): Int = TypedValue.applyDimension(
    TypedValue.COMPLEX_UNIT_DIP, value, resources.displayMetrics,
).toInt()

/** Rounded panel with a hairline edge. The app is read at a glance while
 *  driving, so grouping matters more than decoration. */
fun Context.card(): LinearLayout = LinearLayout(this).apply {
    orientation = LinearLayout.VERTICAL
    background = GradientDrawable().apply {
        cornerRadius = dp(14f).toFloat()
        setColor(Palette.PANEL)
        setStroke(dp(1f), Palette.PANEL_EDGE)
    }
    setPadding(dp(14f), dp(12f), dp(14f), dp(12f))
}

fun Context.label(text: String): TextView = TextView(this).apply {
    this.text = text
    textSize = 11f
    letterSpacing = 0.12f
    typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
    setTextColor(Palette.DIM)
}

fun Context.value(text: String, size: Float = 26f, colour: Int = Palette.TEXT): TextView =
    TextView(this).apply {
        this.text = text
        textSize = size
        typeface = Typeface.create("sans-serif", Typeface.NORMAL)
        setTextColor(colour)
    }

fun Context.mono(size: Float = 12f): TextView = TextView(this).apply {
    typeface = Typeface.MONOSPACE
    textSize = size
    setTextColor(Palette.DIM)
    setLineSpacing(dp(3f).toFloat(), 1f)
}

/** A big number with a caption. The three that matter while moving. */
class Metric(context: Context, caption: String) : LinearLayout(context) {
    private val valueView = context.value("--", 26f)
    private val unitView = context.label(caption)

    init {
        orientation = VERTICAL
        layoutParams = LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f)
        addView(valueView)
        addView(unitView)
    }

    fun set(text: String, colour: Int = Palette.TEXT) {
        valueView.text = text
        valueView.setTextColor(colour)
    }
}

/**
 * Confidence bar. Shows the calibrated containment radius against a scale, not
 * a raw covariance, because the raw number understates by 15-22x.
 */
class ConfidenceBar @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null,
) : View(context, attrs) {

    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF161E27.toInt() }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val rect = RectF()

    /** Metres. The bar saturates at [maxM], which is deliberately generous:
     *  the honest message at 100 m is "do not trust this", not a full bar. */
    var sigmaM: Double = Double.NaN
        set(v) { field = v; invalidate() }

    var maxM: Double = 100.0

    override fun onMeasure(w: Int, h: Int) {
        setMeasuredDimension(
            MeasureSpec.getSize(w),
            context.dp(6f),
        )
    }

    override fun onDraw(canvas: Canvas) {
        val r = height / 2f
        rect.set(0f, 0f, width.toFloat(), height.toFloat())
        canvas.drawRoundRect(rect, r, r, track)
        if (sigmaM.isNaN() || !sigmaM.isFinite()) return

        val frac = (sigmaM / maxM).coerceIn(0.0, 1.0).toFloat()
        // Green while tight, amber as it opens, magenta once it is wide enough
        // that the estimate should not be trusted for a turn.
        fill.color = when {
            sigmaM < 15 -> Palette.GOOD
            sigmaM < 45 -> Palette.AMBER
            else -> Palette.MAGENTA
        }
        rect.set(0f, 0f, width * frac.coerceAtLeast(0.02f), height.toFloat())
        canvas.drawRoundRect(rect, r, r, fill)
    }
}

/** Pill-shaped state chip: the mode, readable at a glance. */
class StatusChip(context: Context) : TextView(context) {
    private val shape = GradientDrawable().apply {
        cornerRadius = context.dp(20f).toFloat()
        setColor(0x00000000)
        setStroke(context.dp(1.5f), Palette.SLATE)
    }

    init {
        background = shape
        setPadding(context.dp(14f), context.dp(6f), context.dp(14f), context.dp(6f))
        textSize = 13f
        letterSpacing = 0.1f
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        setTextColor(Palette.SLATE)
        gravity = Gravity.CENTER
    }

    fun set(text: String, colour: Int) {
        this.text = text
        setTextColor(colour)
        shape.setStroke(context.dp(1.5f), colour)
        shape.setColor((colour and 0x00FFFFFF) or 0x18000000)
    }
}

/** Filled or outlined action button, without pulling in a theme dependency. */
fun Context.actionButton(text: String, filled: Boolean, colour: Int): TextView =
    TextView(this).apply {
        this.text = text
        textSize = 13f
        letterSpacing = 0.08f
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        gravity = Gravity.CENTER
        isClickable = true
        isFocusable = true
        setPadding(dp(18f), dp(13f), dp(18f), dp(13f))
        setTextColor(if (filled) Palette.BG else colour)
        background = GradientDrawable().apply {
            cornerRadius = dp(12f).toFloat()
            if (filled) setColor(colour) else {
                setColor(0x00000000)
                setStroke(dp(1.5f), colour)
            }
        }
        layoutParams = LinearLayout.LayoutParams(
            0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f,
        ).apply { marginEnd = dp(8f) }
    }
