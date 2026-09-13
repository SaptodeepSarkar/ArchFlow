package org.vaani.keyboard

import android.Manifest
import android.content.pm.PackageManager
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.inputmethodservice.InputMethodService
import android.os.Handler
import android.os.Looper
import android.os.Build
import android.text.InputType
import android.text.SpannableString
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.text.style.RelativeSizeSpan
import android.view.View
import android.view.MotionEvent
import android.view.inputmethod.EditorInfo
import android.view.WindowInsets
import android.view.textservice.SpellCheckerSession
import android.view.textservice.SuggestionsInfo
import android.view.textservice.TextInfo
import android.view.textservice.TextServicesManager
import java.util.Locale
import android.widget.*

private class Wave(context: Context) : View(context) {
    private val levels = FloatArray(40)
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Ui(context).ink; strokeCap = Paint.Cap.ROUND }
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
    private lateinit var keyboardBody: LinearLayout
    private lateinit var suggestionBar: LinearLayout
    private var spellSession: SpellCheckerSession? = null
    private var requestedPrefix = ""
    private var deleteHold: Runnable? = null
    private val spellListener = object : SpellCheckerSession.SpellCheckerSessionListener {
        override fun onGetSuggestions(results: Array<SuggestionsInfo>) {
            val suggestions = results.flatMap { info ->
                (0 until info.suggestionsCount).map { info.getSuggestionAt(it) }
            }.filter { it.isNotBlank() && !it.equals(requestedPrefix, true) }.distinct().take(3)
            handler.post {
                if (::suggestionBar.isInitialized && requestedPrefix.isNotBlank() && suggestions.isNotEmpty()) renderSuggestionChips(suggestions)
            }
        }
        override fun onGetSentenceSuggestions(results: Array<android.view.textservice.SentenceSuggestionsInfo>) = Unit
    }
    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(TEXT_SERVICES_MANAGER_SERVICE) as TextServicesManager
        spellSession = manager.newSpellCheckerSession(null, Locale.getDefault(), spellListener, true)
    }
    private lateinit var wave: Wave
    private lateinit var cancel: Button
    private val timeout = Runnable { cancelVoice(); showKeys("Speech timed out. Hold Send to retry.") }

    override fun onEvaluateFullscreenMode() = false
    override fun onCreateInputView(): View {
        root = ui.keyboardColumn().apply {
            setPadding(ui.dp(6), ui.dp(6), ui.dp(6), ui.dp(8))
            setOnApplyWindowInsetsListener { view, insets ->
                val nav = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    insets.getInsets(WindowInsets.Type.navigationBars()).bottom
                } else {
                    @Suppress("DEPRECATION") insets.systemWindowInsetBottom
                }
                view.setPadding(ui.dp(6), ui.dp(6), ui.dp(6), ui.dp(8) + nav)
                insets
            }
        }
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
        status = TextView(this).apply {
            text = message; textSize = 12f; setTextColor(ui.palette.muted)
            gravity = android.view.Gravity.CENTER_VERTICAL
            setPadding(ui.dp(10), 0, ui.dp(10), 0)
        }
        root.addView(status, LinearLayout.LayoutParams(-1, ui.dp(26)))
        suggestionBar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        root.addView(suggestionBar, LinearLayout.LayoutParams(-1, 0))
        wave = Wave(this).apply { visibility = View.GONE }
        root.addView(wave, LinearLayout.LayoutParams(-1, ui.dp(88)))
        cancel = ui.key("Cancel") { cancelVoice(); showKeys("Dictation cancelled") }.apply { visibility = View.GONE }
        root.addView(cancel, LinearLayout.LayoutParams(-1, ui.dp(42)).apply { bottomMargin = ui.dp(4) })
        keyboardBody = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(keyboardBody)
        if (!prefs.getBoolean("keyboard_guide", false)) {
            keyboardBody.addView(ui.label("Hold Send while speaking. Release to clean and insert your text.", 13f))
            keyboardBody.addView(ui.key("Got it") { prefs.edit().putBoolean("keyboard_guide", true).apply(); showKeys() }, LinearLayout.LayoutParams(-1, ui.dp(40)))
        }
        val inputType = currentInputEditorInfo?.inputType ?: 0
        val numberField = (inputType and InputType.TYPE_MASK_CLASS) == InputType.TYPE_CLASS_NUMBER
        if (numberField) {
            listOf("123", "456", "789").forEach(::addCharacterRow)
        } else if (symbols) {
            listOf("1234567890", "@#₹%&*()-", "!?/:;,.\"'").forEach(::addCharacterRow)
        } else {
            addCharacterRow("qwertyuiop")
            addCharacterRow("asdfghjkl")
            val thirdRow = LinearLayout(this)
            iconControlKey(thirdRow, R.drawable.ic_shift, "Shift", 1.25f) { shifted = !shifted; showKeys() }
            "zxcvbnm".forEach { characterKey(thirdRow, it) }
            val backspace = controlKey(thirdRow, "⌫", 1.25f) { delete() }
            enableRepeatDelete(backspace)
            keyboardBody.addView(thirdRow)
        }
        val row = LinearLayout(this)
        if (numberField) {
            key(row, ".") { commit(".") }
            key(row, "0", 2f) { commit("0") }
        } else {
            controlKey(row, if (symbols) "ABC" else "?123", 1.25f) { symbols = !symbols; showKeys() }
            key(row, ",") { commit(",") }
            val space = key(row, "Space", 4f) { commit(" ") }
            enableCursorScrub(space)
            key(row, ".") { commit(".") }
        }
        if (numberField) {
            val backspace = controlKey(row, "⌫", 1.2f) { delete() }
            enableRepeatDelete(backspace)
        }
        else key(row, "⌨") { (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).showInputMethodPicker() }
        val send = sendKey(row, "↑", 1.25f) { }.apply {
            text = ""
            setCompoundDrawablesWithIntrinsicBounds(0, R.drawable.ic_send, 0, 0)
            gravity = android.view.Gravity.CENTER
            contentDescription = "Hold to dictate; release to insert"
        }
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
        keyboardBody.addView(row)
        showSuggestions()
    }
    private fun addCharacterRow(chars: String) {
        val row = LinearLayout(this)
        chars.forEach { characterKey(row, it) }
        keyboardBody.addView(row)
    }
    private fun delete() {
        val ic = currentInputConnection
        if (!ic?.getSelectedText(0).isNullOrEmpty()) ic?.commitText("", 1)
        else ic?.deleteSurroundingTextInCodePoints(1, 0)
        showSuggestions()
    }
    private fun enableRepeatDelete(button: Button) {
        button.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    delete()
                    deleteHold = object : Runnable {
                        override fun run() {
                            delete()
                            handler.postDelayed(this, 55)
                        }
                    }
                    handler.postDelayed(deleteHold!!, 360)
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    deleteHold?.let(handler::removeCallbacks)
                    deleteHold = null
                    true
                }
                else -> true
            }
        }
    }
    private fun enableCursorScrub(button: Button) {
        var downX = 0f
        var start = -1
        var moved = false
        button.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.x
                    start = currentInputConnection?.getExtractedText(null, 0)?.selectionStart ?: -1
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    if (start >= 0) {
                        val steps = ((event.x - downX) / ui.dp(14).toFloat()).toInt()
                        if (steps != 0) {
                            val length = currentInputConnection?.getExtractedText(null, 0)?.text?.length ?: start
                            currentInputConnection?.setSelection((start + steps).coerceIn(0, length), (start + steps).coerceIn(0, length))
                            moved = true
                        }
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!moved) commit(" ")
                    true
                }
                else -> true
            }
        }
    }
    private fun characterKey(row: LinearLayout, character: Char) {
        val number = "1234567890".getOrNull("qwertyuiop".indexOf(character.lowercaseChar()))
        val shown = if (shifted && !symbols) character.uppercaseChar().toString() else character.toString()
        val button = key(row, shown) { }
        if (number != null && !symbols) {
            val label = SpannableString("$shown  $number")
            label.setSpan(RelativeSizeSpan(.55f), shown.length + 2, label.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            label.setSpan(ForegroundColorSpan(ui.palette.muted), shown.length + 2, label.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            button.text = label
        }
        if (number == null || symbols) {
            button.setOnClickListener { commit(shown) }
            return
        }
        var longPressed = false
        var hold: Runnable? = null
        button.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    longPressed = false
                    hold = Runnable {
                        longPressed = true
                        commit(number.toString())
                    }.also { handler.postDelayed(it, 360) }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    hold?.let(handler::removeCallbacks)
                    if (!longPressed) commit(shown)
                    true
                }
                MotionEvent.ACTION_CANCEL -> { hold?.let(handler::removeCallbacks); true }
                else -> true
            }
        }
    }
    private fun commit(value: String) {
        currentInputConnection?.commitText(value, 1)
        handler.post { if (::suggestionBar.isInitialized) showSuggestions() }
    }
    private fun showSuggestions() {
        val before = currentInputConnection?.getTextBeforeCursor(72, 0)?.toString().orEmpty()
        val prefix = before.takeLastWhile { it.isLetter() || it == '\'' }.lowercase()
        if (prefix.isEmpty()) {
            requestedPrefix = ""
            suggestionBar.removeAllViews()
            suggestionBar.layoutParams = suggestionBar.layoutParams.apply { height = 0 }
            return
        }
        requestedPrefix = prefix
        val fallback = listOf("Vanni", "voice", "very", "please", "thanks", "tomorrow", "today", "message", "meeting", "because", "keyboard", "cleanup", "speech", "send", "write")
            .filter { it.startsWith(prefix, true) && !it.equals(prefix, true) }.take(3)
        renderSuggestionChips(fallback)
        spellSession?.getSuggestions(TextInfo(prefix), 3)
    }
    private fun renderSuggestionChips(candidates: List<String>) {
        suggestionBar.removeAllViews()
        suggestionBar.layoutParams = suggestionBar.layoutParams.apply { height = if (candidates.isEmpty()) 0 else ui.dp(38) }
        candidates.forEach { candidate ->
            val button = ui.key(candidate) {
                if (requestedPrefix.isNotEmpty()) currentInputConnection?.deleteSurroundingText(requestedPrefix.length, 0)
                commit("$candidate ")
            }.apply {
                textSize = 14f
                contentDescription = "Insert $candidate"
            }
            suggestionBar.addView(button, LinearLayout.LayoutParams(0, ui.dp(34), 1f).apply {
                setMargins(ui.dp(2), ui.dp(1), ui.dp(2), ui.dp(1))
            })
        }
    }
    private fun key(row: LinearLayout, text: String, weight: Float = 1f, action: () -> Unit): Button {
        val button = ui.key(text, action).apply {
            textSize = 16f; minWidth = 0; minimumWidth = 0; minHeight = ui.dp(40); minimumHeight = ui.dp(40); setPadding(0, 0, 0, 0)
        }
        row.addView(button, LinearLayout.LayoutParams(0, ui.dp(34), weight).apply { gravity = android.view.Gravity.CENTER_VERTICAL; setMargins(ui.dp(2), ui.dp(2), ui.dp(2), ui.dp(2)) })
        return button
    }
    private fun controlKey(row: LinearLayout, text: String, weight: Float = 1f, action: () -> Unit): Button {
        val button = ui.controlKey(text, action).apply {
            textSize = 15f; minWidth = 0; minimumWidth = 0; minHeight = ui.dp(40); minimumHeight = ui.dp(40); setPadding(0, 0, 0, 0)
        }
        row.addView(button, LinearLayout.LayoutParams(0, ui.dp(34), weight).apply { gravity = android.view.Gravity.CENTER_VERTICAL; setMargins(ui.dp(2), ui.dp(2), ui.dp(2), ui.dp(2)) })
        return button
    }
    private fun iconControlKey(row: LinearLayout, icon: Int, description: String, weight: Float = 1f, action: () -> Unit): Button {
        val button = controlKey(row, "", weight, action).apply {
            setCompoundDrawablesWithIntrinsicBounds(0, icon, 0, 0)
            gravity = android.view.Gravity.CENTER
            contentDescription = description
        }
        return button
    }
    private fun sendKey(row: LinearLayout, text: String, weight: Float = 1f, action: () -> Unit): Button {
        val button = ui.sendKey(text, action).apply {
            textSize = 19f; minWidth = 0; minimumWidth = 0; minHeight = ui.dp(40); minimumHeight = ui.dp(40); setPadding(0, 0, 0, 0)
        }
        row.addView(button, LinearLayout.LayoutParams(0, ui.dp(34), weight).apply { gravity = android.view.Gravity.CENTER_VERTICAL; setMargins(ui.dp(2), ui.dp(2), ui.dp(2), ui.dp(2)) })
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
        status.text = "Listening… keep holding Send"
        wave.visibility = View.VISIBLE
        cancel.visibility = View.VISIBLE
        keyboardBody.alpha = .16f
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
    override fun onDestroy() { cancelVoice(); spellSession?.close(); super.onDestroy() }
}
