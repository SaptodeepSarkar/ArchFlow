package org.vaani.keyboard

import android.content.Context
import android.graphics.Typeface
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.BitmapFactory
import android.graphics.Rect
import android.graphics.drawable.GradientDrawable
import android.widget.*

data class Palette(val paper: Int, val surface: Int, val ink: Int, val muted: Int, val line: Int, val accent: Int, val accentText: Int)

private class GrainLayout(context: Context, private val palette: Palette) : LinearLayout(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = palette.ink; alpha = 9 }
    init { setWillNotDraw(false) }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val step = (resources.displayMetrics.density * 9).toInt().coerceAtLeast(6)
        for (y in 3 until height step step) for (x in 3 until width step step) {
            val seed = (x * 37 + y * 19) % 17
            if (seed < 5) canvas.drawCircle(x.toFloat(), y.toFloat(), if (seed == 0) 1.2f else .65f, paint)
        }
    }
}

/** The illustration is deliberately subtle: it is a personal theme backdrop, not content. */
private class ImageLayout(context: Context, private val palette: Palette) : LinearLayout(context) {
    private val bitmap = BitmapFactory.decodeResource(resources, R.drawable.vaani_hero)
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    init { setWillNotDraw(false) }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val scale = maxOf(width.toFloat() / bitmap.width, height.toFloat() / bitmap.height)
        val drawWidth = (bitmap.width * scale).toInt()
        val drawHeight = (bitmap.height * scale).toInt()
        val left = (width - drawWidth) / 2
        val top = (height - drawHeight) / 2
        canvas.drawBitmap(bitmap, null, Rect(left, top, left + drawWidth, top + drawHeight), paint)
        paint.color = palette.paper
        paint.alpha = if (palette.paper == Ui.brandPaper) 190 else 210
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)
        paint.alpha = 255
    }
}

class Ui(private val context: Context) {
    private val prefs = context.getSharedPreferences("vaani", 0)
    val palette: Palette = paletteFor(prefs.getString("theme", "light") ?: "light", prefs.getInt("accent", 0))
    val paper get() = palette.paper
    val ink get() = palette.ink
    val accent get() = palette.accent
    fun dp(n: Int) = (n * context.resources.displayMetrics.density).toInt()
    fun column(): LinearLayout {
        val background = prefs.getString("background", "image")
        val layout: LinearLayout = when (background) {
            "image" -> ImageLayout(context, palette)
            "grain" -> GrainLayout(context, palette)
            else -> LinearLayout(context)
        }
        return layout.apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(28), dp(24), dp(28))
            setBackgroundColor(palette.paper)
        }
    }
    fun keyboardColumn() = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setBackgroundColor(palette.paper)
    }
    fun label(value: String, size: Float = 16f) = TextView(context).apply { text = value; textSize = size; setTextColor(palette.ink); setPadding(0, dp(8), 0, dp(12)) }
    fun title(value: String, size: Float = 32f) = label(value, size).apply { typeface = Typeface.create("serif", Typeface.NORMAL); setPadding(0, dp(22), 0, dp(8)) }
    fun button(value: String, click: () -> Unit) = Button(context).apply {
        text = value; textSize = 16f; isAllCaps = false; setTextColor(palette.accentText); minHeight = dp(52); minimumHeight = dp(52); setPadding(dp(12), dp(10), dp(12), dp(10))
        background = shape(palette.accent, palette.accent, 16); layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8); bottomMargin = dp(4) }; setOnClickListener { click() }
    }
    fun key(value: String, click: () -> Unit) = Button(context).apply {
        text = value; textSize = 15f; isAllCaps = false; setTextColor(palette.ink); minWidth = 0; minimumWidth = 0; minHeight = dp(48); minimumHeight = dp(48); setPadding(0, dp(7), 0, dp(7))
        background = shape(palette.surface, palette.line, 12); setOnClickListener { click() }
    }
    fun controlKey(value: String, click: () -> Unit) = key(value, click).apply {
        background = shape(palette.line, palette.line, 12)
    }
    fun sendKey(value: String, click: () -> Unit) = key(value, click).apply {
        setTextColor(palette.accentText)
        background = shape(palette.accent, palette.accent, 14)
    }
    fun shape(color: Int, line: Int, radius: Int) = GradientDrawable().apply { setColor(color); setStroke(dp(1), line); cornerRadius = dp(radius).toFloat() }
    companion object {
        val brandInk = 0xff20251f.toInt(); val brandPaper = 0xfff7f6ef.toInt(); val brandLime = 0xffd7f36f.toInt()
        fun paletteFor(theme: String, savedAccent: Int): Palette {
            val base = when (theme) {
                "dark" -> Palette(0xff111311.toInt(), 0xff20251f.toInt(), 0xfff4f6ef.toInt(), 0xffb8beb1.toInt(), 0xff3b4339.toInt(), brandLime, brandInk)
                "forest" -> Palette(0xff18231c.toInt(), 0xff25352a.toInt(), 0xfff3f5ed.toInt(), 0xffc1cbbd.toInt(), 0xff435646.toInt(), 0xffe6cff9.toInt(), brandInk)
                "blush" -> Palette(0xfffff7f4.toInt(), 0xffffffff.toInt(), brandInk, 0xff6d655f.toInt(), 0xffeadbd4.toInt(), 0xffe9bbb6.toInt(), brandInk)
                else -> Palette(brandPaper, 0xffffffff.toInt(), brandInk, 0xff657063.toInt(), 0xffd9d9cf.toInt(), brandLime, brandInk)
            }
            return if (savedAccent == 0) base else base.copy(accent = savedAccent, accentText = brandInk)
        }
    }
}
