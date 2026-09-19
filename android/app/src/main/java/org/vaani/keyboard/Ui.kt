package org.vaani.keyboard

import android.annotation.SuppressLint
import android.content.Context
import android.content.res.ColorStateList
import android.content.res.Configuration
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import com.google.android.material.button.MaterialButton

/**
 * Button base used by the keyboard's touch-customized controls.
 *
 * Several keyboard controls add press-and-hold or cursor-scrub behavior with
 * an OnTouchListener. Keeping performClick explicit preserves the semantic
 * click path used by accessibility services and by keyboard automation.
 */
@SuppressLint("AppCompatCustomView")
class AccessibleButton(context: Context) : Button(context) {
    override fun performClick(): Boolean = super.performClick()
}

private class MaterialAccessibleButton(context: Context) : MaterialButton(context) {
    override fun performClick(): Boolean = super.performClick()
}

data class Palette(
    val paper: Int,
    val surface: Int,
    val surfaceRaised: Int,
    val ink: Int,
    val muted: Int,
    val line: Int,
    val accent: Int,
    val accentText: Int,
    val ready: Int,
    val warning: Int,
    val error: Int,
    val onError: Int,
)

/** Small semantic Views design system shared by the app and keyboard. */
class Ui(private val context: Context) {
    private val prefs = context.getSharedPreferences("vaani", 0)
    private val systemDark = context.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES
    val isDark = prefs.getString("theme", "system") == "dark" ||
        (prefs.getString("theme", "system") == "system" && systemDark)
    val palette: Palette = paletteFor(prefs.getString("theme", "system") ?: "system", systemDark)
    val paper get() = palette.paper
    val ink get() = palette.ink
    val accent get() = palette.accent

    fun dp(value: Int) = (value * context.resources.displayMetrics.density).toInt()

    fun screenColumn() = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(20), dp(16), dp(20), dp(32))
        setBackgroundColor(palette.paper)
    }

    fun column() = screenColumn()

    fun keyboardColumn() = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setBackgroundColor(palette.paper)
    }

    fun label(value: CharSequence, size: Float = 16f, color: Int = palette.ink) = TextView(context).apply {
        text = value
        textSize = size
        setTextColor(color)
        includeFontPadding = false
        setLineSpacing(0f, 1.12f)
        setPadding(0, dp(4), 0, dp(4))
    }

    fun title(value: CharSequence, size: Float = 30f) = label(value, size).apply {
        typeface = Typeface.create("sans-serif", Typeface.BOLD)
        setLineSpacing(0f, 1.02f)
        setPadding(0, dp(12), 0, dp(8))
    }

    fun sectionTitle(value: CharSequence) = label(value, 19f).apply {
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        setPadding(0, dp(24), 0, dp(6))
    }

    fun meta(value: CharSequence) = label(value, 13f, palette.muted)

    fun primaryButton(value: CharSequence, click: () -> Unit) = baseButton(value, click).apply {
        setTextColor(palette.accentText)
        if (this is MaterialButton) {
            backgroundTintList = ColorStateList.valueOf(palette.accent)
            strokeColor = ColorStateList.valueOf(palette.accent)
            strokeWidth = dp(1)
            cornerRadius = dp(16)
        } else background = shape(palette.accent, palette.accent, 16)
    }

    fun secondaryButton(value: CharSequence, click: () -> Unit) = baseButton(value, click).apply {
        setTextColor(palette.ink)
        if (this is MaterialButton) {
            backgroundTintList = ColorStateList.valueOf(palette.surface)
            strokeColor = ColorStateList.valueOf(palette.line)
            strokeWidth = dp(1)
            cornerRadius = dp(16)
        } else background = shape(palette.surface, palette.line, 16)
    }

    fun button(value: String, click: () -> Unit) = primaryButton(value, click)

    private fun baseButton(value: CharSequence, click: () -> Unit): Button =
        (if (context is VaaniKeyboardService) AccessibleButton(context) else MaterialAccessibleButton(context)).apply {
        text = value
        textSize = 15f
        isAllCaps = false
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        letterSpacing = 0f
        minHeight = dp(52)
        minimumHeight = dp(52)
        setPadding(dp(16), dp(10), dp(16), dp(10))
        stateListAnimator = null
        setOnClickListener { click() }
    }

    fun key(value: String, click: () -> Unit) = AccessibleButton(context).apply {
        text = value
        textSize = 16f
        isAllCaps = false
        setTextColor(palette.ink)
        minWidth = 0
        minimumWidth = 0
        minHeight = dp(48)
        minimumHeight = dp(48)
        setPadding(0, dp(6), 0, dp(6))
        stateListAnimator = null
        background = shape(palette.surface, palette.line, 12)
        isHapticFeedbackEnabled = true
        setOnClickListener {
            performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            click()
        }
    }

    fun controlKey(value: String, click: () -> Unit) = key(value, click).apply {
        background = shape(palette.surfaceRaised, palette.line, 12)
    }

    fun sendKey(value: String, click: () -> Unit) = key(value, click).apply {
        setTextColor(palette.accentText)
        background = shape(palette.accent, palette.accent, 14)
        compoundDrawableTintList = ColorStateList.valueOf(palette.accentText)
    }

    fun surfaceCard() = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(16), dp(14), dp(16), dp(14))
        background = shape(palette.surface, palette.line, 20)
    }

    fun divider(): View = View(context).apply { setBackgroundColor(palette.line) }

    fun shape(color: Int, line: Int = color, radius: Int = 16) = GradientDrawable().apply {
        setColor(color)
        setStroke(dp(1), line)
        cornerRadius = dp(radius).toFloat()
    }

    fun pill(color: Int, contentColor: Int, value: String) = label(value, 12f, contentColor).apply {
        gravity = Gravity.CENTER
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        setPadding(dp(12), dp(6), dp(12), dp(6))
        background = shape(color, color, 99)
    }

    companion object {
        const val BRAND_FOREST: Int = 0xff18352f.toInt()
        const val BRAND_CREAM: Int = 0xfffff9e8.toInt()
        const val BRAND_AMBER: Int = 0xffe7a43b.toInt()
        const val BRAND_SAGE: Int = 0xffb8c8ae.toInt()
        const val BRAND_CORAL: Int = 0xffcf705c.toInt()
        val brandInk = BRAND_FOREST
        val brandPaper = BRAND_CREAM
        val brandLime = BRAND_AMBER

        fun paletteFor(theme: String, systemDark: Boolean = false): Palette {
            val dark = theme == "dark" || (theme == "system" && systemDark)
            return if (dark) {
                Palette(0xff111816.toInt(), 0xff1b2522.toInt(), 0xff26312e.toInt(), 0xfff5f1e5.toInt(), 0xffb7c1bb.toInt(), 0xff3a4743.toInt(), 0xfff0b85f.toInt(), 0xff1b241f.toInt(), 0xff9bc6a8.toInt(), 0xfff0b85f.toInt(), 0xffffb4a5.toInt(), 0xff3f1008.toInt())
            } else {
                Palette(BRAND_CREAM, 0xfffffdf7.toInt(), 0xfff2eee2.toInt(), BRAND_FOREST, 0xff63736e.toInt(), 0xffd9ddd3.toInt(), BRAND_AMBER, 0xff2a2114.toInt(), 0xff397254.toInt(), 0xff8a5a13.toInt(), 0xffa64032.toInt(), 0xffffffff.toInt())
            }
        }
    }
}
