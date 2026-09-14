package org.vaani.keyboard

import android.Manifest
import android.content.Context
import android.content.SharedPreferences
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.Space
import android.widget.TextView

private class FlowMark(context: Context, private val ui: Ui) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var phase = 0f
    private var tick: Runnable? = null

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        if (!android.animation.ValueAnimator.areAnimatorsEnabled()) return
        val animator = android.animation.ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 2200
            repeatCount = android.animation.ValueAnimator.INFINITE
            addUpdateListener { phase = it.animatedValue as Float; invalidate() }
        }
        tick = Runnable { animator.start() }
        post(tick)
    }

    override fun onDetachedFromWindow() {
        tick?.let(::removeCallbacks)
        tick = null
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        val d = resources.displayMetrics.density
        val width = width.toFloat()
        val center = height / 2f
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = 3f * d
        paint.strokeCap = Paint.Cap.ROUND
        val colors = intArrayOf(ui.palette.accent, Ui.BRAND_SAGE, Ui.BRAND_CORAL)
        colors.forEachIndexed { index, color ->
            paint.color = color
            val offset = (index - 1) * 11f * d
            val wave = phase * 18f * d + index * 30f * d
            val path = android.graphics.Path().apply {
                moveTo(22f * d, center + offset)
                cubicTo(width * .28f, center - 16f * d + offset + kotlin.math.sin(wave.toDouble()).toFloat() * 4f * d, width * .48f, center + 16f * d + offset, width - 22f * d, center + offset)
            }
            canvas.drawPath(path, paint)
        }
        paint.style = Paint.Style.FILL
    }
}

class OnboardingView(
    context: Context,
    private val enableKeyboard: () -> Unit,
    private val chooseKeyboard: () -> Unit,
    private val requestMicrophone: () -> Unit,
    private val done: () -> Unit,
) : LinearLayout(context), SharedPreferences.OnSharedPreferenceChangeListener {
    private val prefs = context.getSharedPreferences("vaani", 0)
    private val ui = Ui(context)
    private var page = prefs.getInt("onboarding_step", 0).coerceIn(0, 3)
    private lateinit var progress: TextView
    private lateinit var title: TextView
    private lateinit var body: TextView
    private lateinit var visualHost: LinearLayout
    private lateinit var next: android.widget.Button
    private lateinit var back: android.widget.Button

    init {
        orientation = VERTICAL
        setBackgroundColor(ui.paper)
        setPadding(ui.dp(20), ui.dp(12), ui.dp(20), ui.dp(20))
        build()
        update()
        prefs.registerOnSharedPreferenceChangeListener(this)
    }

    override fun onDetachedFromWindow() {
        prefs.unregisterOnSharedPreferenceChangeListener(this)
        super.onDetachedFromWindow()
    }

    override fun onSharedPreferenceChanged(sharedPreferences: SharedPreferences?, key: String?) {
        if (key in setOf("first_dictation_complete", "theme", "onboarding_step")) post { update() }
    }

    private fun build() {
        val header = LinearLayout(context).apply { gravity = Gravity.CENTER_VERTICAL }
        header.addView(ImageView(context).apply { setImageResource(R.drawable.vaani_mark); contentDescription = "Vaani" }, LinearLayout.LayoutParams(ui.dp(40), ui.dp(40)))
        header.addView(ui.label("Vaani", 20f).apply { typeface = Typeface.DEFAULT_BOLD }, LinearLayout.LayoutParams(0, ui.dp(40), 1f).apply { marginStart = ui.dp(10) })
        progress = ui.meta("1 of 4")
        header.addView(progress)
        addView(header)
        title = ui.title("")
        addView(title, LayoutParams(-1, -2).apply { topMargin = ui.dp(22) })
        body = ui.label("", 16f, ui.palette.muted)
        addView(body, LayoutParams(-1, -2).apply { bottomMargin = ui.dp(14) })
        visualHost = LinearLayout(context).apply { orientation = VERTICAL; gravity = Gravity.CENTER_VERTICAL }
        addView(visualHost, LayoutParams(-1, ui.dp(176)).apply { bottomMargin = ui.dp(14) })
        addView(Space(context), LayoutParams(1, 0, 1f))
        next = ui.primaryButton(context.getString(R.string.onboarding_continue)) { next() }
        addView(next, LayoutParams(-1, ui.dp(52)))
        back = ui.secondaryButton(context.getString(R.string.onboarding_back)) { if (page > 0) { page--; persistPage(); update() } }
        addView(back, LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(8) })
    }

    private fun persistPage() = prefs.edit().putInt("onboarding_step", page).apply()

    private fun next() {
        when (page) {
            0 -> { page = 1; persistPage(); update() }
            1 -> if (prefs.getBoolean("microphone_granted", false) || hasMic()) { page = 2; persistPage(); update() } else requestMicrophone()
            2 -> if (keyboardEnabled()) { page = 3; persistPage(); update() } else enableKeyboard()
            3 -> if (prefs.getBoolean("first_dictation_complete", false)) done() else chooseKeyboard()
        }
    }

    private fun hasMic() = context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED

    private fun keyboardEnabled(): Boolean {
        val imm = context.getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        return imm.enabledInputMethodList.any { it.packageName == context.packageName }
    }

    private fun update() {
        val mic = hasMic()
        val ime = keyboardEnabled()
        val tested = prefs.getBoolean("first_dictation_complete", false)
        progress.text = context.getString(R.string.onboarding_progress, page + 1)
        title.text = listOf("Speak naturally.\nKeep your hands moving.", "Microphone, only when you ask.", "Keep your keyboard.", "Try one real dictation.")[page]
        body.text = listOf(
            "Vaani turns a spoken thought into clean text in the field you are already using. It stays quiet until you hold Send.",
            "Vaani listens only during dictation. Audio is handed to the device speech recognizer; it is not saved by this app.",
            "Vaani works as an Android keyboard today. Your usual keyboard can remain available as a fallback while we build the coexisting invocation layer.",
            "Focus the field below, choose Vaani from the keyboard picker, then hold Send and speak. The test is what completes setup."
        )[page]
        visualHost.removeAllViews()
        when (page) {
            0 -> visualHost.addView(ImageView(context).apply {
                setImageResource(R.drawable.vaani_onboarding_banner)
                scaleType = ImageView.ScaleType.CENTER_CROP
                contentDescription = "A warm sunlit path through a garden courtyard"
            }, LayoutParams(-1, -1))
            1 -> {
                visualHost.addView(FlowMark(context, ui), LayoutParams(-1, ui.dp(74)))
                val label = if (mic) "Microphone ready" else "Microphone permission needed"
                visualHost.addView(ui.pill(if (mic) ui.palette.ready else ui.palette.surfaceRaised, if (mic) 0xffffffff.toInt() else ui.ink, label), LayoutParams(-2, ui.dp(32)).apply { gravity = Gravity.CENTER_HORIZONTAL; topMargin = ui.dp(8) })
            }
            2 -> {
                visualHost.addView(ImageView(context).apply { setImageResource(R.drawable.vaani_flow_ribbon); scaleType = ImageView.ScaleType.CENTER_INSIDE; contentDescription = "Three paper ribbons settling into aligned lines" }, LayoutParams(-1, ui.dp(100)))
                visualHost.addView(ui.meta(if (ime) "Vaani is enabled" else "One Android settings step"), LayoutParams(-1, ui.dp(28)).apply { gravity = Gravity.CENTER_HORIZONTAL })
            }
            3 -> {
                val field = EditText(context).apply {
                    hint = "Your dictated text will appear here"
                    textSize = 16f
                    setTextColor(ui.ink)
                    setHintTextColor(ui.palette.muted)
                    background = ui.shape(ui.palette.surface, ui.palette.line, 16)
                    setPadding(ui.dp(14), ui.dp(12), ui.dp(14), ui.dp(12))
                    minHeight = ui.dp(56)
                    contentDescription = "Test dictation field"
                }
                visualHost.addView(field, LayoutParams(-1, ui.dp(64)))
                visualHost.addView(ui.secondaryButton(if (tested) "Test complete" else "Choose Vaani keyboard") { if (tested) update() else chooseKeyboard() }, LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(8) })
            }
        }
        next.text = when {
            page == 3 && tested -> context.getString(R.string.onboarding_finish)
            page == 3 -> "Open keyboard picker"
            page == 1 && !mic -> "Allow microphone"
            page == 2 && !ime -> "Enable Vaani keyboard"
            else -> context.getString(R.string.onboarding_continue)
        }
        back.visibility = if (page == 0) GONE else VISIBLE
    }
}
