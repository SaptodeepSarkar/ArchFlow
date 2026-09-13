package org.vaani.keyboard

import android.Manifest
import android.content.pm.PackageManager
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.inputmethodservice.InputMethodService
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.View
import android.view.MotionEvent
import android.view.inputmethod.EditorInfo
import android.widget.*

private class Wave(context: Context) : View(context) {
    private val levels = FloatArray(40)
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Ui.ink; strokeCap = Paint.Cap.ROUND }
    fun push(level: Float) {
        for (i in 0 until levels.lastIndex) levels[i] = levels[i + 1]
        levels[levels.lastIndex] = ((level + 2f) / 12f).coerceIn(0f, 1f)
        invalidate()
    }
    override fun onDraw(canvas: Canvas) {
        val step = width / 42f
        paint.strokeWidth = step * .4f
        levels.forEachIndexed { i, level ->
            val half = 2f + level * height * .44f
            canvas.drawLine((i + 1) * step, height / 2f - half, (i + 1) * step, height / 2f + half, paint)
        }
    }
}

class VaaniKeyboardService : InputMethodService() {
    private val prefs by lazy { getSharedPreferences("vaani", 0) }
    private val ui by lazy { Ui(this) }
    private lateinit var root: LinearLayout
    private var shifted = false
    private var symbols = false
    private var voice = false
    private var released = false
    private var recognitionText: String? = null
    private var generation = 0
    private var engine: OnDeviceSttEngine? = null
    private val handler = Handler(Looper.getMainLooper())
    private var holdStart: Runnable? = null
    private lateinit var status: TextView
    private val timeout = Runnable { cancelVoice(); showKeys("Speech timed out. Hold Send to retry.") }

    override fun onEvaluateFullscreenMode() = false
    override fun onCreateInputView(): View {
        root = ui.column().apply { setPadding(ui.dp(4), ui.dp(6), ui.dp(4), ui.dp(8)) }
        showKeys()
        return root
    }
    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        cancelVoice()
        if (::root.isInitialized) showKeys()
    }
    private fun showKeys(message: String = "Vanni · hold Send to speak") {
        root.removeAllViews()
        root.addView(ui.label(message, 13f))
        if (!prefs.getBoolean("keyboard_guide", false)) {
            root.addView(ui.label("Hold Send while speaking. Release to clean and insert your text. Tap Cancel while recording to discard it.", 14f))
            root.addView(ui.button("Got it") { prefs.edit().putBoolean("keyboard_guide", true).apply(); showKeys() })
        }
        val rows = if (symbols) listOf("1234567890", "@#₹%&*()-", "!?/:;,.") else listOf("qwertyuiop", "asdfghjkl", "zxcvbnm")
        rows.forEach { chars ->
            val row = LinearLayout(this)
            chars.forEach { c -> key(row, if (shifted && !symbols) c.uppercase() else c.toString()) {
                currentInputConnection?.commitText(if (shifted && !symbols) c.uppercase() else c.toString(), 1)
            } }
            root.addView(row)
        }
        val row = LinearLayout(this)
        key(row, if (shifted) "⇧ ON" else "⇧") { shifted = !shifted; showKeys() }
        key(row, if (symbols) "ABC" else "?123") { symbols = !symbols; showKeys() }
        key(row, "Space", 2f) { currentInputConnection?.commitText(" ", 1) }
        key(row, "⌫") {
            val ic = currentInputConnection
            if (!ic?.getSelectedText(0).isNullOrEmpty()) ic?.commitText("", 1) else ic?.deleteSurroundingTextInCodePoints(1, 0)
        }
        val send = key(row, "Send") { }
        send.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    holdStart = Runnable { startVoice() }.also { handler.postDelayed(it, 220) }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    holdStart?.let(handler::removeCallbacks); holdStart = null
                    if (voice) releaseVoice() else normalSend()
                    true
                }
                MotionEvent.ACTION_CANCEL -> {
                    holdStart?.let(handler::removeCallbacks); holdStart = null
                    if (voice) cancelVoice(); showKeys()
                    true
                }
                else -> true
            }
        }
        root.addView(row)
        root.addView(ui.button("Switch keyboard") { (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).showInputMethodPicker() })
    }
    private fun key(row: LinearLayout, text: String, weight: Float = 1f, action: () -> Unit): Button {
        val button = ui.button(text, action).apply {
            textSize = 14f; minWidth = 0; minimumWidth = 0; setPadding(0, ui.dp(8), 0, ui.dp(8))
        }
        row.addView(button, LinearLayout.LayoutParams(0, -2, weight).apply { setMargins(ui.dp(2), ui.dp(2), ui.dp(2), ui.dp(2)) })
        return button
    }
    private fun startVoice() {
        if (voice) return
        val type = currentInputEditorInfo?.inputType ?: 0
        val variation = type and InputType.TYPE_MASK_VARIATION
        if ((type and InputType.TYPE_MASK_CLASS == InputType.TYPE_CLASS_TEXT && variation in listOf(InputType.TYPE_TEXT_VARIATION_PASSWORD, InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD, InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD)) ||
            (type and InputType.TYPE_MASK_CLASS == InputType.TYPE_CLASS_NUMBER && variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD)) {
            showKeys("Voice is disabled in password fields."); return
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            showKeys("Open Vanni settings and allow microphone access."); return
        }
        voice = true; released = false; recognitionText = null
        val token = ++generation
        root.removeAllViews()
        status = ui.label("Starting microphone…", 18f)
        root.addView(status)
        val wave = Wave(this)
        root.addView(wave, LinearLayout.LayoutParams(-1, ui.dp(140)))
        root.addView(ui.label("Keep holding Send and speak. Release to insert the cleaned text.", 14f))
        root.addView(ui.button("Cancel") { cancelVoice(); showKeys() })
        val lang = prefs.getString("language", "en-IN") ?: "en-IN"
        engine = OnDeviceSttEngine(this, lang, { if (token == generation) wave.push(it) },
            { if (token == generation) status.text = "Listening…" })
        engine?.start({ raw ->
            if (token == generation && voice) {
                handler.removeCallbacks(timeout)
                val finalText = LocalConservativeCleanup(prefs.getBoolean("cleanup", true)).clean(raw)
                recognitionText = finalText
                engine?.cancel(); engine = null
                if (released) deliver(finalText) else status.text = if (raw.isBlank()) "No speech detected" else "Finishing…"
            }
        }, { error -> if (token == generation) { cancelVoice(); showKeys(error) } })
        if (voice) handler.postDelayed(timeout, 120000)
    }
    private fun releaseVoice() {
        released = true
        status.text = "Finishing…"
        handler.removeCallbacks(timeout)
        handler.postDelayed(timeout, 15000)
        recognitionText?.let(::deliver) ?: engine?.stop()
    }
    private fun deliver(text: String) {
        val accepted = text.isEmpty() || currentInputConnection?.commitText(text, 1) == true
        if (accepted) { cancelVoice(); showKeys(if (text.isEmpty()) "No speech detected" else "Text inserted") }
        else { cancelVoice(); showKeys("Could not insert text") }
    }
    private fun normalSend() {
        val action = (currentInputEditorInfo?.imeOptions ?: 0) and EditorInfo.IME_MASK_ACTION
        if (action != EditorInfo.IME_ACTION_NONE && action != EditorInfo.IME_ACTION_UNSPECIFIED) currentInputConnection?.performEditorAction(action)
        else currentInputConnection?.commitText("\n", 1)
    }
    private fun cancelVoice() {
        generation++; handler.removeCallbacks(timeout); engine?.cancel(); engine = null
        voice = false; released = false; recognitionText = null
    }
    override fun onFinishInputView(finishingInput: Boolean) { cancelVoice(); super.onFinishInputView(finishingInput) }
    override fun onFinishInput() { cancelVoice(); super.onFinishInput() }
    override fun onDestroy() { cancelVoice(); super.onDestroy() }
}
