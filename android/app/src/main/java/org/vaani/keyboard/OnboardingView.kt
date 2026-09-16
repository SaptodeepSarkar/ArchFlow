package org.vaani.keyboard

import android.Manifest
import android.content.Context
import android.content.SharedPreferences
import android.provider.Settings
import android.animation.ValueAnimator
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Typeface
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.view.animation.DecelerateInterpolator
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.Space
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

private class FlowMark(context: Context, private val ui: Ui) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val paths = Array(3) { Path() }
    private var phase = 0f
    private var animator: ValueAnimator? = null

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        if (!ValueAnimator.areAnimatorsEnabled()) return
        animator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 2200
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener { phase = it.animatedValue as Float; invalidate() }
            start()
        }
    }

    override fun onDetachedFromWindow() {
        animator?.cancel()
        animator = null
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
            val path = paths[index].apply {
                reset()
                moveTo(22f * d, center + offset)
                cubicTo(width * .28f, center - 16f * d + offset + kotlin.math.sin(wave.toDouble()).toFloat() * 4f * d, width * .48f, center + 16f * d + offset, width - 22f * d, center + offset)
            }
            canvas.drawPath(path, paint)
        }
        paint.style = Paint.Style.FILL
    }
}

/** A restrained readiness pulse; it is visual feedback, never simulated audio. */
private class ReadinessPulse(context: Context, private val ui: Ui) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var phase = 0f
    private var animator: ValueAnimator? = null

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        if (!ValueAnimator.areAnimatorsEnabled()) return
        animator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 1800
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener { phase = it.animatedValue as Float; invalidate() }
            start()
        }
    }

    override fun onDetachedFromWindow() {
        animator?.cancel()
        animator = null
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        paint.color = ui.palette.accent
        paint.style = Paint.Style.FILL
        val widths = floatArrayOf(.30f, .62f, .42f, .82f, .52f, .70f, .36f)
        val gap = width / 10f
        widths.forEachIndexed { index, base ->
            val pulse = (kotlin.math.sin((phase * Math.PI * 2 + index * .8)).toFloat() + 1f) * .08f
            val barHeight = height * (base + pulse).coerceAtMost(.95f)
            canvas.drawRoundRect(index * gap + gap * .35f, height - barHeight, index * gap + gap * .65f, height.toFloat(), gap * .15f, gap * .15f, paint)
        }
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
    private lateinit var progressTrack: LinearLayout
    private lateinit var title: TextView
    private lateinit var body: TextView
    private lateinit var visualHost: LinearLayout
    private lateinit var next: android.widget.Button
    private lateinit var back: android.widget.Button
    private var testField: EditText? = null
    private var testAction: android.widget.Button? = null

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
        if (key == "first_dictation_complete") post {
            if (page == 3) updateTestCompletion() else update()
        }
    }

    /** Refreshes permission/IME state after returning from Android settings. */
    fun refreshExternalState() {
        if (page == 3) {
            updateTestCompletion()
            showRehearsalKeyboardIfReady()
        } else update()
    }

    /** Reopens the focused rehearsal field after the IME picker dismisses. */
    fun showRehearsalKeyboardIfReady() {
        if (page != 3 || !keyboardSelected() || prefs.getBoolean("first_dictation_complete", false)) return
        val field = testField ?: return
        field.requestFocus()
        field.postDelayed({
            val imm = context.getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
            imm.restartInput(field)
            // This is an explicit user action (the rehearsal button).  Some
            // Android 15 IME implementations reject SHOW_IMPLICIT while the
            // picker is dismissing, leaving the selected keyboard invisible.
            (context as? android.app.Activity)?.window?.setSoftInputMode(
                WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE or
                    WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE,
            )
            val shown = imm.showSoftInput(field, android.view.inputmethod.InputMethodManager.SHOW_FORCED)
            if (!shown) imm.toggleSoftInput(android.view.inputmethod.InputMethodManager.SHOW_FORCED, 0)
            // Android 11+ routes IME visibility through window insets; this
            // complements the legacy manager call after an IME-picker return.
            ViewCompat.getWindowInsetsController(field)?.show(WindowInsetsCompat.Type.ime())
        }, 120L)
    }

    private fun build() {
        val header = LinearLayout(context).apply { gravity = Gravity.CENTER_VERTICAL }
        header.addView(ImageView(context).apply { setImageResource(R.drawable.vaani_v); contentDescription = "Vaani green V" }, LinearLayout.LayoutParams(ui.dp(40), ui.dp(40)))
        header.addView(ui.label("Vaani", 20f).apply { typeface = Typeface.DEFAULT_BOLD }, LinearLayout.LayoutParams(0, ui.dp(40), 1f).apply { marginStart = ui.dp(10) })
        progress = ui.meta("1 of 4")
        header.addView(progress)
        addView(header)
        progressTrack = LinearLayout(context).apply { orientation = HORIZONTAL; setPadding(0, ui.dp(12), 0, ui.dp(4)) }
        repeat(4) { index ->
            progressTrack.addView(View(context), LinearLayout.LayoutParams(0, ui.dp(3), 1f).apply {
                if (index > 0) marginStart = ui.dp(4)
            })
        }
        addView(progressTrack)
        title = ui.title("")
        addView(title, LayoutParams(-1, -2).apply { topMargin = ui.dp(22) })
        body = ui.label("", 16f, ui.palette.muted)
        addView(body, LayoutParams(-1, -2).apply { bottomMargin = ui.dp(14) })
        visualHost = LinearLayout(context).apply { orientation = VERTICAL; gravity = Gravity.CENTER_VERTICAL }
        addView(visualHost, LayoutParams(-1, ui.dp(176)).apply { bottomMargin = ui.dp(14) })
        addView(Space(context), LayoutParams(1, 0, 1f))
        next = ui.primaryButton(context.getString(R.string.onboarding_continue)) { next() }
        addView(next, LayoutParams(-1, ui.dp(52)))
        back = ui.secondaryButton(context.getString(R.string.onboarding_back)) { if (page > 0) { page--; persistPage(); update(animated = true) } }
        addView(back, LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(8) })
    }

    private fun persistPage() = prefs.edit().putInt("onboarding_step", page).apply()

    private fun next() {
        when (page) {
            0 -> { page = 1; persistPage(); update(animated = true) }
            1 -> if (prefs.getBoolean("microphone_granted", false) || hasMic()) { page = 2; persistPage(); update(animated = true) } else requestMicrophone()
            2 -> when {
                !keyboardEnabled() -> enableKeyboard()
                !keyboardSelected() -> chooseKeyboard()
                else -> { page = 3; persistPage(); update(animated = true) }
            }
            3 -> if (prefs.getBoolean("first_dictation_complete", false)) done() else openKeyboardForTest()
        }
    }

    private fun hasMic() = context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED

    private fun microphoneNeedsSettings() = MicrophonePermissionPolicy.requiresAppSettings(
        prefs.getBoolean("microphone_requested", false),
        hasMic(),
        (context as? android.app.Activity)?.shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO) == true,
    )

    private fun keyboardEnabled(): Boolean {
        val imm = context.getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        return imm.enabledInputMethodList.any {
            it.packageName == context.packageName && it.serviceName == VaaniKeyboardService::class.java.name
        }
    }

    private fun keyboardSelected(): Boolean = Settings.Secure.getString(
        context.contentResolver,
        Settings.Secure.DEFAULT_INPUT_METHOD,
    ) == android.content.ComponentName(context, VaaniKeyboardService::class.java).flattenToShortString()

    private fun update(animated: Boolean = false) {
        if (animated && isLaidOut && ValueAnimator.areAnimatorsEnabled()) {
            val animatedViews = listOf(title, body, visualHost)
            animatedViews.forEach { view ->
                view.animate().cancel()
                view.animate().alpha(0f).translationX(-ui.dp(14).toFloat()).setDuration(140).setInterpolator(DecelerateInterpolator()).start()
            }
            visualHost.animate().setDuration(140).withEndAction {
                renderContent()
                animatedViews.forEach { view ->
                    view.alpha = 0f
                    view.translationX = ui.dp(14).toFloat()
                    view.animate().alpha(1f).translationX(0f).setDuration(260).setInterpolator(DecelerateInterpolator()).start()
                }
            }.start()
            return
        }
        renderContent()
    }

    private fun renderContent() {
        val mic = hasMic()
        val ime = keyboardEnabled()
        val selected = keyboardSelected()
        val tested = prefs.getBoolean("first_dictation_complete", false)
        progress.text = context.getString(R.string.onboarding_progress, page + 1)
        for (index in 0 until progressTrack.childCount) {
            progressTrack.getChildAt(index).setBackgroundColor(if (index <= page) ui.palette.accent else ui.palette.line)
        }
        title.text = listOf(
            "Typing less\nis the point.",
            "Your voice stays\nin the room.",
            "Android has\none small form.",
            "A three-second\nrehearsal."
        )[page]
        body.text = listOf(
            "Vaani turns a thought into text in the field you already use. It never sends the message for you.",
            "Audio is captured only while you hold Send and handed to Android's speech service. Vaani stores no recording; network access is only for optional personalization sync.",
            "Enabling Vaani adds a keyboard; it does not replace your usual one. Switch keyboards anytime from Android's picker.",
            "Focus the field, choose Vaani, hold Send for about 220 ms, speak, then release. Text is inserted—never auto-sent."
        )[page]
        testField = null
        testAction = null
        visualHost.background = null
        visualHost.setPadding(0, 0, 0, 0)
        visualHost.removeAllViews()
        when (page) {
            0 -> {
                visualHost.background = ui.shape(ui.palette.surface, ui.palette.line, 20)
                visualHost.setPadding(ui.dp(16), ui.dp(10), ui.dp(16), ui.dp(10))
                visualHost.addView(ImageView(context).apply {
                    setImageResource(R.drawable.vaani_v)
                    scaleType = ImageView.ScaleType.CENTER_INSIDE
                    contentDescription = "Large pine-green Vaani V mark"
                }, LayoutParams(-1, 0, 1f))
                visualHost.addView(ui.meta("LOCAL AUDIO PIPELINE · READY"), LayoutParams(-1, ui.dp(24)).apply { gravity = Gravity.CENTER_HORIZONTAL })
                visualHost.addView(ReadinessPulse(context, ui), LayoutParams(-1, ui.dp(44)))
            }
            1 -> {
                visualHost.addView(FlowMark(context, ui), LayoutParams(-1, ui.dp(74)))
                val label = if (mic) "Microphone ready" else "Microphone permission needed"
                visualHost.addView(ui.pill(if (mic) ui.palette.ready else ui.palette.surfaceRaised, if (mic) 0xffffffff.toInt() else ui.ink, label), LayoutParams(-2, ui.dp(32)).apply { gravity = Gravity.CENTER_HORIZONTAL; topMargin = ui.dp(8) })
            }
            2 -> {
                val paperwork = LinearLayout(context).apply {
                    orientation = HORIZONTAL
                    gravity = Gravity.CENTER
                    setPadding(ui.dp(8), ui.dp(10), ui.dp(8), ui.dp(4))
                }
                listOf("1  ENABLE" to (if (ime) "Done" else "Android settings"), "2  CHOOSE" to "Keyboard picker", "3  SWITCH" to "Anytime").forEachIndexed { index, item ->
                    val card = ui.surfaceCard().apply {
                        setPadding(ui.dp(10), ui.dp(10), ui.dp(10), ui.dp(8))
                        rotation = if (index == 0) -1.2f else if (index == 2) 1.2f else 0f
                        contentDescription = "${item.first}: ${item.second}"
                    }
                    card.addView(ui.meta(item.first))
                    card.addView(ui.label(item.second, 12f))
                    paperwork.addView(card, LinearLayout.LayoutParams(0, ui.dp(78), 1f).apply {
                        marginStart = if (index == 0) 0 else ui.dp(4)
                    })
                }
                visualHost.addView(paperwork, LayoutParams(-1, ui.dp(100)))
                visualHost.addView(ui.meta(if (ime) "Vaani is enabled · your keyboard stays yours" else "One Android settings step"), LayoutParams(-1, ui.dp(28)).apply { gravity = Gravity.CENTER_HORIZONTAL })
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
                testField = field
                visualHost.addView(field, LayoutParams(-1, ui.dp(64)))
                testAction = ui.secondaryButton(when {
                    tested -> "Test complete"
                    selected -> "Show Vaani keyboard"
                    else -> "Choose Vaani keyboard"
                }) {
                    if (!prefs.getBoolean("first_dictation_complete", false)) openKeyboardForTest()
                }
                visualHost.addView(testAction, LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(8) })
                if (!tested) {
                    visualHost.addView(ui.secondaryButton("Skip rehearsal for now") {
                        done()
                    }, LayoutParams(-1, ui.dp(48)).apply { topMargin = ui.dp(6) })
                }
                if (selected && !tested) post { showRehearsalKeyboardIfReady() }
            }
        }
        next.text = when {
            page == 3 && tested -> context.getString(R.string.onboarding_finish)
            page == 3 && !ime -> "Enable Vaani keyboard"
            page == 3 && !selected -> "Choose Vaani keyboard"
            page == 3 -> "Show Vaani keyboard"
            page == 1 && !mic -> if (microphoneNeedsSettings()) "Open app settings" else "Allow microphone"
            page == 2 && !ime -> "Enable Vaani keyboard"
            page == 2 && !selected -> "Choose Vaani keyboard"
            else -> context.getString(R.string.onboarding_continue)
        }
        back.visibility = if (page == 0) GONE else VISIBLE
    }

    private fun updateTestCompletion() {
        val tested = prefs.getBoolean("first_dictation_complete", false)
        val ime = keyboardEnabled()
        val selected = keyboardSelected()
        testAction?.text = when {
            tested -> "Test complete"
            selected -> "Show Vaani keyboard"
            else -> "Choose Vaani keyboard"
        }
        next.text = when {
            tested -> context.getString(R.string.onboarding_finish)
            !ime -> "Enable Vaani keyboard"
            selected -> "Show Vaani keyboard"
            else -> "Choose Vaani keyboard"
        }
        if (tested) {
            testAction?.isEnabled = false
            testAction?.announceForAccessibility("Test dictation complete. Finish setup is available.")
        }
    }

    private fun openKeyboardForTest() {
        val field = testField ?: return
        if (keyboardSelected()) {
            showRehearsalKeyboardIfReady()
        } else if (keyboardEnabled()) {
            field.requestFocus()
            field.postDelayed(chooseKeyboard, 180)
        } else {
            // If the service is not enabled yet, send the user to Android's
            // input-method settings before attempting the picker.
            field.requestFocus()
            field.postDelayed(enableKeyboard, 180)
        }
    }
}
