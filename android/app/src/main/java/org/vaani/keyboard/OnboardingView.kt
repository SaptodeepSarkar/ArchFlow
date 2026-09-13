package org.vaani.keyboard

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.view.animation.LinearInterpolator
import android.widget.*

private class OnboardingVisual(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var phase = 0f
    private var mode = 0
    private var animation: ValueAnimator? = null
    private fun dp(n: Float) = n * resources.displayMetrics.density
    fun setMode(value: Int) { mode = value; phase = 0f; invalidate() }
    override fun onAttachedToWindow() { super.onAttachedToWindow(); animation = ValueAnimator.ofFloat(0f, 1f).apply { duration = 1700; repeatCount = ValueAnimator.INFINITE; interpolator = LinearInterpolator(); addUpdateListener { phase = it.animatedValue as Float; invalidate() }; start() } }
    override fun onDetachedFromWindow() { animation?.cancel(); animation = null; super.onDetachedFromWindow() }
    private fun card(canvas: Canvas, rect: RectF) { paint.color = 0xffffffff.toInt(); canvas.drawRoundRect(rect, dp(20f), dp(20f), paint); paint.style = Paint.Style.STROKE; paint.strokeWidth = dp(1f); paint.color = 0xffd9d9cf.toInt(); canvas.drawRoundRect(rect, dp(20f), dp(20f), paint); paint.style = Paint.Style.FILL }
    private fun text(canvas: Canvas, value: String, x: Float, y: Float, size: Float, color: Int) { paint.color = color; paint.textSize = dp(size); paint.typeface = Typeface.DEFAULT_BOLD; canvas.drawText(value, x, y, paint) }
    override fun onDraw(canvas: Canvas) {
        val w = width.toFloat(); val h = height.toFloat(); val box = RectF(dp(6f), dp(10f), w - dp(6f), h - dp(10f)); card(canvas, box)
        when (mode) {
            0 -> {
                text(canvas, "1", dp(26f), dp(47f), 16f, 0xff20251f.toInt()); text(canvas, "Enable Vanni", dp(58f), dp(47f), 14f, 0xff20251f.toInt())
                text(canvas, "2", dp(26f), dp(87f), 16f, 0xff20251f.toInt()); text(canvas, "Allow microphone", dp(58f), dp(87f), 14f, 0xff20251f.toInt())
                text(canvas, "3", dp(26f), dp(127f), 16f, 0xff20251f.toInt()); text(canvas, "Choose Vanni", dp(58f), dp(127f), 14f, 0xff20251f.toInt())
                paint.color = 0xffd7f36f.toInt(); canvas.drawCircle(w - dp(42f), dp(42f), dp(13f), paint); text(canvas, "✓", w - dp(48f), dp(48f), 14f, 0xff20251f.toInt())
            }
            1 -> {
                text(canvas, "Hold", dp(26f), dp(42f), 12f, 0xff657063.toInt()); paint.color = 0xff20251f.toInt(); canvas.drawRoundRect(RectF(dp(26f), dp(56f), w - dp(26f), dp(105f)), dp(15f), dp(15f), paint)
                text(canvas, "SEND", w / 2f - dp(23f), dp(86f), 14f, 0xffd7f36f.toInt())
                paint.color = 0xffd7f36f.toInt(); for (i in 0..17) { val amp = dp(5f + ((i + (phase * 6).toInt()) % 5) * 4f); val x = dp(28f + i * 13f); canvas.drawRoundRect(RectF(x, dp(136f) - amp, x + dp(5f), dp(136f) + amp), dp(3f), dp(3f), paint) }
                text(canvas, "Speak while holding", dp(26f), h - dp(24f), 13f, 0xff657063.toInt())
            }
            else -> {
                text(canvas, "Listening", dp(26f), dp(42f), 12f, 0xff657063.toInt()); paint.color = 0xffe9bbb6.toInt(); canvas.drawRoundRect(RectF(dp(26f), dp(58f), dp(80f), dp(84f)), dp(13f), dp(13f), paint); text(canvas, "um", dp(40f), dp(76f), 12f, 0xff20251f.toInt())
                paint.color = 0xffe6cff9.toInt(); canvas.drawRoundRect(RectF(dp(88f), dp(58f), dp(155f), dp(84f)), dp(13f), dp(13f), paint); text(canvas, "send", dp(101f), dp(76f), 12f, 0xff20251f.toInt())
                paint.color = 0xffd7f36f.toInt(); canvas.drawRoundRect(RectF(dp(26f), dp(113f), w - dp(26f), dp(157f)), dp(16f), dp(16f), paint); text(canvas, "Send the note.", dp(45f), dp(141f), 16f, 0xff20251f.toInt()); text(canvas, "Release → inserts", dp(26f), h - dp(24f), 13f, 0xff657063.toInt())
            }
        }
    }
}

class OnboardingView(context: Context, private val done: () -> Unit) : LinearLayout(context) {
    private var page = 0
    private lateinit var title: TextView
    private lateinit var body: TextView
    private lateinit var progress: TextView
    private lateinit var next: Button
    private lateinit var back: Button
    private lateinit var visual: OnboardingVisual
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
    private fun label(value: String, size: Float, color: Int, bold: Boolean = false) = TextView(context).apply { text = value; textSize = size; setTextColor(color); typeface = if (bold) Typeface.DEFAULT_BOLD else Typeface.DEFAULT }
    init {
        orientation = VERTICAL; setBackgroundColor(Ui.brandPaper); setPadding(dp(22), dp(22), dp(22), dp(20)); build(); update()
    }
    private fun build() {
        val header = LinearLayout(context).apply { gravity = Gravity.CENTER_VERTICAL }
        header.addView(ImageView(context).apply { setImageResource(R.drawable.vaani_mark); contentDescription = "Vanni" }, LayoutParams(dp(42), dp(42)))
        header.addView(label("vanni", 22f, Ui.brandInk, true), LayoutParams(0, dp(42), 1f).apply { marginStart = dp(9) })
        progress = label("1 / 3", 11f, 0xff657063.toInt()); header.addView(progress); addView(header)
        title = label("", 30f, Ui.brandInk, true).apply { typeface = Typeface.create("serif", Typeface.NORMAL) }; addView(title, LayoutParams(-1, -2).apply { topMargin = dp(28) })
        body = label("", 16f, 0xff657063.toInt()); addView(body, LayoutParams(-1, -2).apply { topMargin = dp(10) })
        visual = OnboardingVisual(context); addView(visual, LayoutParams(-1, dp(190)).apply { topMargin = dp(18); bottomMargin = dp(18) })
        addView(Space(context), LayoutParams(1, 0, 1f))
        next = Button(context).apply { isAllCaps = false; textSize = 16f; setTextColor(Ui.brandInk); background = GradientDrawable().apply { setColor(Ui.brandLime); cornerRadius = dp(18).toFloat() }; setOnClickListener { if (page == 2) done() else { page++; update() } } }; addView(next, LayoutParams(-1, dp(54)))
        back = Button(context).apply { text = "Back"; isAllCaps = false; setTextColor(Ui.brandInk); background = null; setOnClickListener { page--; update() } }; addView(back, LayoutParams(-1, dp(48)))
    }
    private fun update() {
        progress.text = "${page + 1} / 3"; visual.setMode(page)
        title.text = listOf("Make Vanni\nyour keyboard.", "Hold Send.\nSpeak naturally.", "Release.\nText appears.")[page]
        body.text = listOf(
            "Enable Vanni in Android’s keyboard settings. Then choose it from the keyboard picker and allow microphone access.",
            "Type with the regular keyboard. Press and hold Send while you speak. The keyboard becomes a waveform so you can see the microphone responding.",
            "Release Send to finish speech recognition. Vanni lightly cleans the text and inserts it in the field you were typing in. Use Cancel before release to discard."
        )[page]
        next.text = if (page == 2) "Finish setup" else "Continue"
        back.visibility = if (page == 0) GONE else VISIBLE
    }
}
