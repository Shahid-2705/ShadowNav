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
    // Contrast is measured, not eyeballed. Every foreground below clears
    // WCAG AA (4.5:1) against both BG and PANEL; the figures in comments are
    // against PANEL, which is the tighter of the two.
    //
    // SLATE was #6E7C8C and measured 4.27:1 -- a fail, and it carried the
    // idle ACQUIRING chip, which is the first thing a user ever sees.
    const val BG = 0xFF07090C.toInt()
    const val PANEL = 0xFF10161D.toInt()
    const val PANEL_EDGE = 0xFF1D2733.toInt()
    const val CYAN = 0xFF4DE0E8.toInt()    // 11.38:1
    const val AMBER = 0xFFE8A33D.toInt()   // 8.43:1
    const val MAGENTA = 0xFFE24DBE.toInt() // 5.23:1
    const val SLATE = 0xFF8492A1.toInt()   // 5.72:1
    const val TEXT = 0xFFDCE6F0.toInt()    // 14.40:1
    const val DIM = 0xFF7C8A99.toInt()     // 5.16:1
    const val GOOD = 0xFF5BD98A.toInt()    // 10.17:1
}

fun Context.dp(value: Float): Int = TypedValue.applyDimension(
    TypedValue.COMPLEX_UNIT_DIP, value, resources.displayMetrics,
).toInt()

/** Android minimum touch target. The controls here exceed it deliberately:
 *  they are pressed in a moving vehicle, where 48 dp is a floor, not a
 *  target. */
const val MIN_TOUCH_DP = 48f
const val DRIVING_TOUCH_DP = 60f

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
    // 13sp rather than 11sp. Small caps at arm length in a moving car is
    // the wrong economy, and sp scales with the user font-size setting.
    textSize = 13f
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

fun Context.mono(size: Float = 14f): TextView = TextView(this).apply {
    typeface = Typeface.MONOSPACE
    textSize = size
    setTextColor(Palette.DIM)
    // 1.25 line height: the telemetry block is dense and scanned, not read.
    setLineSpacing(dp(4f).toFloat(), 1.25f)
}

/** A big number with a caption. The three that matter while moving. */
class Metric(context: Context, private val caption: String) : LinearLayout(context) {
    private val valueView = context.value("--", 30f)
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
        // Colour never carries meaning on its own: the caption is announced with
        // the value, so a screen-reader or colour-blind user gets exactly what a
        // sighted one does.
        contentDescription = "$caption $text"
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
        set(v) {
            field = v
            contentDescription = if (v.isFinite()) {
                "confidence radius ${v.toInt()} metres"
            } else {
                "confidence unavailable"
            }
            invalidate()
        }

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
        // The chip is the primary state indicator, so it states the mode in
        // words. Colour reinforces; it does not encode.
        contentDescription = "navigation state: $text"
        setTextColor(colour)
        shape.setStroke(context.dp(1.5f), colour)
        shape.setColor((colour and 0x00FFFFFF) or 0x18000000)
    }
}

/**
 * Filled or outlined action button.
 *
 * Three things here are requirements rather than polish, because this control
 * is pressed inside a moving vehicle:
 *
 * - **Size.** 60 dp minimum height, above the 48 dp floor. A target sized for a
 *   stationary thumb is not sized for a moving one.
 * - **Pressed feedback.** A ripple bounded by the shape, so a press that did not
 *   register is distinguishable from one that did. Without it the only signal is
 *   the app behaving differently, which during a blackout demo is precisely the
 *   thing being observed.
 * - **Focus.** A visible focus ring, so the app is operable from a keyboard or
 *   switch device and not by touch alone.
 */
fun Context.actionButton(
    text: String,
    filled: Boolean,
    colour: Int,
    description: String = text,
): TextView =
    TextView(this).apply {
        this.text = text
        textSize = 14f
        letterSpacing = 0.08f
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        gravity = Gravity.CENTER
        isClickable = true
        isFocusable = true
        contentDescription = description
        minHeight = dp(DRIVING_TOUCH_DP)
        minimumHeight = dp(DRIVING_TOUCH_DP)
        setPadding(dp(18f), dp(14f), dp(18f), dp(14f))
        setTextColor(if (filled) Palette.BG else colour)

        val shape = GradientDrawable().apply {
            cornerRadius = dp(14f).toFloat()
            if (filled) setColor(colour) else {
                setColor(0x00000000)
                setStroke(dp(1.5f), colour)
            }
        }
        background = android.graphics.drawable.RippleDrawable(
            android.content.res.ColorStateList.valueOf(
                (colour and 0x00FFFFFF) or 0x66000000,
            ),
            shape,
            GradientDrawable().apply {
                cornerRadius = dp(14f).toFloat()
                setColor(0xFFFFFFFF.toInt())
            },
        )
        setOnFocusChangeListener { v, hasFocus ->
            shape.setStroke(
                if (hasFocus) dp(3f) else dp(1.5f),
                if (hasFocus) Palette.TEXT else colour,
            )
            v.invalidate()
        }

        layoutParams = LinearLayout.LayoutParams(
            0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f,
        ).apply { marginEnd = dp(8f) }
    }
