package org.vaani.keyboard

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Canvas
import android.graphics.Paint
import android.inputmethodservice.InputMethodService
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.text.InputType
import android.text.SpannableString
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.text.style.RelativeSizeSpan
import android.view.Gravity
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.WindowInsets
import android.view.inputmethod.EditorInfo
import android.view.textservice.SpellCheckerSession
import android.view.textservice.SuggestionsInfo
import android.view.textservice.TextInfo
import android.view.textservice.TextServicesManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import java.util.Locale

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
    private val personalization by lazy { PersonalizationStore(this) }
    private lateinit var ui: Ui
    private lateinit var root: LinearLayout
    private lateinit var wave: Wave
    private lateinit var cancel: Button
    private lateinit var status: TextView
    private lateinit var keyboardBody: LinearLayout
    private lateinit var suggestionBar: LinearLayout
    private var shifted = false
    private var symbols = false
    private val dictationController = DictationController()
    private var engine: SttEngine? = null
    private val handler = Handler(Looper.getMainLooper())
    private var holdStart: Runnable? = null
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

    private val timeout = Runnable {
        val token = dictationController.currentToken()
        val active = dictationController.state is DictationState.Starting ||
            dictationController.state is DictationState.Listening ||
            dictationController.state is DictationState.Endpointing ||
            dictationController.state is DictationState.Finalizing
        if (token != null && active) {
            fail(token, FailureKind.TIMEOUT, getString(R.string.status_timed_out))
        }
    }

    override fun onCreate() {
        super.onCreate()
        ui = Ui(this)
        val manager = getSystemService(TEXT_SERVICES_MANAGER_SERVICE) as TextServicesManager
        spellSession = manager.newSpellCheckerSession(null, Locale.getDefault(), spellListener, true)
    }

    override fun onEvaluateFullscreenMode() = false

    // Emulator and tablet profiles may advertise a hardware keyboard. Vaani
    // is still an explicitly selected soft keyboard, so do not let that
    // hardware capability suppress the IME input view.
    override fun onEvaluateInputViewShown(): Boolean {
        super.onEvaluateInputViewShown()
        return true
    }

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        // An InputConnection can change without recreating the input view.
        // Invalidate any recognizer callback before accepting the new editor.
        cancelVoice()
        shifted = false
        symbols = false
    }

    override fun onUnbindInput() {
        cancelVoice()
        super.onUnbindInput()
    }

    override fun onCreateInputView(): View {
        // Theme changes made while the IME process survives take effect the
        // next time Android asks for an input view.
        ui = Ui(this)
        root = ui.keyboardColumn().apply {
            setPadding(ui.dp(6), ui.dp(6), ui.dp(6), ui.dp(8))
            setOnApplyWindowInsetsListener { view, insets ->
                val nav = insets.getInsets(WindowInsets.Type.navigationBars()).bottom
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

    private fun transition(next: DictationState, message: String? = null) {
        if (!::status.isInitialized) return
        when (next) {
            DictationState.Hidden -> {
                wave.visibility = View.GONE
                cancel.visibility = View.GONE
                keyboardBody.alpha = 1f
                status.text = message ?: getString(R.string.status_ready)
            }
            DictationState.Starting -> {
                wave.visibility = View.VISIBLE
                cancel.visibility = View.VISIBLE
                keyboardBody.alpha = .18f
                status.text = message ?: getString(R.string.status_starting)
            }
            is DictationState.Listening -> {
                wave.visibility = View.VISIBLE
                cancel.visibility = View.VISIBLE
                keyboardBody.alpha = .18f
                status.text = if (next.finalText == null) getString(R.string.status_listening) else "Release to insert"
            }
            DictationState.Endpointing, DictationState.Finalizing -> {
                wave.visibility = View.VISIBLE
                cancel.visibility = View.VISIBLE
                keyboardBody.alpha = .18f
                status.text = getString(R.string.status_finishing)
            }
            is DictationState.Inserting -> {
                wave.visibility = View.GONE
                cancel.visibility = View.GONE
                keyboardBody.alpha = .45f
                status.text = getString(R.string.status_finishing)
            }
            DictationState.Success, DictationState.Cancelled -> {
                wave.visibility = View.GONE
                cancel.visibility = View.GONE
                keyboardBody.alpha = 1f
                status.text = message ?: if (next is DictationState.Success) getString(R.string.status_inserted) else getString(R.string.status_cancelled)
            }
            is DictationState.Failure -> {
                wave.visibility = View.GONE
                cancel.visibility = View.GONE
                keyboardBody.alpha = 1f
                status.text = next.message
            }
        }
    }

    private fun showKeys(message: String? = null, recoveryAction: (() -> Unit)? = null) {
        dictationController.hide()
        transition(DictationState.Hidden, message)
        root.removeAllViews()
        status = ui.label(message ?: getString(R.string.status_ready), 12f, ui.palette.muted).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(ui.dp(10), 0, ui.dp(10), 0)
        }
        root.addView(status, LinearLayout.LayoutParams(-1, ui.dp(28)))
        recoveryAction?.let { action ->
            root.addView(
                ui.secondaryButton("Open microphone settings", action),
                LinearLayout.LayoutParams(-1, ui.dp(46)).apply { bottomMargin = ui.dp(4) },
            )
        }
        suggestionBar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        root.addView(suggestionBar, LinearLayout.LayoutParams(-1, 0))
        wave = Wave(this).apply { visibility = View.GONE; contentDescription = "Live microphone level" }
        root.addView(wave, LinearLayout.LayoutParams(-1, ui.dp(52)))
        cancel = ui.key(getString(R.string.dictation_cancel)) { cancelVoice(); showKeys(getString(R.string.status_cancelled)) }.apply {
            visibility = View.GONE
            contentDescription = getString(R.string.dictation_cancel)
        }
        root.addView(cancel, LinearLayout.LayoutParams(-1, ui.dp(48)).apply { bottomMargin = ui.dp(4) })
        keyboardBody = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(keyboardBody)
        if (!prefs.getBoolean("keyboard_guide", false)) {
            keyboardBody.addView(ui.label("Hold Send while speaking. Release to insert; Cancel keeps the field unchanged.", 13f))
            keyboardBody.addView(ui.key("Got it") { prefs.edit().putBoolean("keyboard_guide", true).apply(); showKeys() }, LinearLayout.LayoutParams(-1, ui.dp(48)))
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
            val space = key(row, "Space", 3.5f) { commit(" ") }
            enableCursorScrub(space)
            key(row, ".") { commit(".") }
            if (symbols) {
                val backspace = controlKey(row, "⌫", 1.1f) { delete() }
                enableRepeatDelete(backspace)
            }
            controlKey(row, "↵", 1.1f) { editorAction() }.apply {
                contentDescription = editorActionDescription()
            }
        }
        if (numberField) {
            val backspace = controlKey(row, "⌫", 1.2f) { delete() }
            enableRepeatDelete(backspace)
            controlKey(row, "↵", 1.1f) { editorAction() }.apply {
                contentDescription = editorActionDescription()
            }
        } else key(row, "⌨") { (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).showInputMethodPicker() }
        val send = sendKey(row, "", 1.25f) { normalSend() }.apply {
            setCompoundDrawablesWithIntrinsicBounds(0, R.drawable.ic_send, 0, 0)
            gravity = Gravity.CENTER
            contentDescription = getString(R.string.dictation_hold_description)
        }
        send.setOnTouchListener { view, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    holdStart = Runnable { startVoice() }.also { handler.postDelayed(it, 220) }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    holdStart?.let(handler::removeCallbacks); holdStart = null
                    if (dictationController.state is DictationState.Listening || dictationController.state is DictationState.Starting || dictationController.state is DictationState.Endpointing || dictationController.state is DictationState.Finalizing) {
                        releaseVoice()
                    } else view.performClick()
                    true
                }
                MotionEvent.ACTION_CANCEL -> {
                    holdStart?.let(handler::removeCallbacks); holdStart = null
                    if (dictationController.state !is DictationState.Hidden) {
                        cancelVoice()
                        showKeys(getString(R.string.status_cancelled))
                    }
                    true
                }
                else -> true
            }
        }
        keyboardBody.addView(row)
        showSuggestions()
    }

    private fun showFailure(failure: DictationState.Failure) {
        root.removeAllViews()
        val wrap = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(ui.dp(12), ui.dp(8), ui.dp(12), ui.dp(8))
        }
        wrap.addView(ui.label(getString(R.string.dictation_recovery_title), 16f).apply { typeface = android.graphics.Typeface.DEFAULT_BOLD })
        wrap.addView(ui.label(getString(R.string.dictation_recovery_body), 13f, ui.palette.muted))
        wrap.addView(ui.label(failure.recoverableText.orEmpty(), 15f))
        wrap.addView(ui.primaryButton(getString(R.string.dictation_copy)) { copyRecovered(failure.recoverableText.orEmpty()) }, LinearLayout.LayoutParams(-1, ui.dp(48)).apply { topMargin = ui.dp(4) })
        wrap.addView(ui.secondaryButton(getString(R.string.dictation_retry)) { deliver(failure.recoverableText.orEmpty()) }, LinearLayout.LayoutParams(-1, ui.dp(48)).apply { topMargin = ui.dp(4) })
        wrap.addView(ui.secondaryButton(getString(R.string.dictation_dismiss)) { showKeys() }, LinearLayout.LayoutParams(-1, ui.dp(48)).apply { topMargin = ui.dp(4) })
        root.addView(wrap)
    }

    private fun copyRecovered(text: String) {
        getSystemService(CLIPBOARD_SERVICE).let { it as ClipboardManager }.setPrimaryClip(ClipData.newPlainText("Vaani dictation", text))
        showKeys(getString(R.string.dictation_copied))
    }

    private fun addCharacterRow(chars: String) {
        val row = LinearLayout(this)
        chars.forEach { characterKey(row, it) }
        keyboardBody.addView(row)
    }

    private fun delete() {
        val ic = currentInputConnection
        if (!ic?.getSelectedText(0).isNullOrEmpty()) ic?.commitText("", 1) else ic?.deleteSurroundingTextInCodePoints(1, 0)
        showSuggestions()
    }

    private fun editorActionDescription(): String = EditorActionPolicy.label(currentInputEditorInfo?.imeOptions ?: 0)

    private fun editorAction() {
        val connection = currentInputConnection ?: return
        val action = currentInputEditorInfo?.imeOptions?.and(EditorInfo.IME_MASK_ACTION) ?: EditorInfo.IME_ACTION_NONE
        if (action != EditorInfo.IME_ACTION_NONE && action != EditorInfo.IME_ACTION_UNSPECIFIED) {
            if (connection.performEditorAction(action)) return
        }
        val now = SystemClock.uptimeMillis()
        connection.sendKeyEvent(KeyEvent(now, now, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER, 0, 0))
        connection.sendKeyEvent(KeyEvent(now, now, KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ENTER, 0, 0))
    }

    private fun enableRepeatDelete(button: Button) {
        button.setOnTouchListener { view, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    view.performClick()
                    deleteHold = object : Runnable {
                        override fun run() { delete(); handler.postDelayed(this, 55) }
                    }
                    handler.postDelayed(deleteHold!!, 360)
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> { deleteHold?.let(handler::removeCallbacks); deleteHold = null; true }
                else -> true
            }
        }
    }

    private fun enableCursorScrub(button: Button) {
        var downX = 0f
        var start = -1
        var moved = false
        button.setOnTouchListener { view, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> { downX = event.x; start = currentInputConnection?.getExtractedText(null, 0)?.selectionStart ?: -1; moved = false; true }
                MotionEvent.ACTION_MOVE -> {
                    if (start >= 0) {
                        val steps = ((event.x - downX) / ui.dp(14).toFloat()).toInt()
                        if (steps != 0) {
                            val length = currentInputConnection?.getExtractedText(null, 0)?.text?.length ?: start
                            currentInputConnection?.setSelection((start + steps).coerceIn(0, length), (start + steps).coerceIn(0, length)); moved = true
                        }
                    }
                    true
                }
                MotionEvent.ACTION_UP -> { if (!moved) view.performClick(); true }
                else -> true
            }
        }
    }

    private fun characterKey(row: LinearLayout, character: Char) {
        val number = "1234567890".getOrNull("qwertyuiop".indexOf(character.lowercaseChar()))
        val shown = if (shifted && !symbols) character.uppercaseChar().toString() else character.toString()
        val button = key(row, shown) { commit(shown) }
        if (number != null && !symbols) {
            val label = SpannableString("$shown  $number")
            label.setSpan(RelativeSizeSpan(.55f), shown.length + 2, label.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            label.setSpan(ForegroundColorSpan(ui.palette.muted), shown.length + 2, label.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            button.text = label
        }
        if (number == null || symbols) return
        var longPressed = false
        var hold: Runnable? = null
        button.setOnTouchListener { view, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> { longPressed = false; hold = Runnable { longPressed = true; commit(number.toString()) }.also { handler.postDelayed(it, 360) }; true }
                MotionEvent.ACTION_UP -> { hold?.let(handler::removeCallbacks); if (!longPressed) view.performClick(); true }
                MotionEvent.ACTION_CANCEL -> { hold?.let(handler::removeCallbacks); true }
                else -> true
            }
        }
    }

    private fun commit(value: String) {
        currentInputConnection?.commitText(value, 1)
        if (!symbols && shifted && value.length == 1 && value[0].isLetter()) shifted = false
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
        val fallback = listOf("Vaani", "voice", "very", "please", "thanks", "tomorrow", "today", "message", "meeting", "because", "keyboard", "cleanup", "speech", "send", "write")
            .filter { it.startsWith(prefix, true) && !it.equals(prefix, true) }.take(3)
        renderSuggestionChips(fallback)
        spellSession?.getSuggestions(TextInfo(prefix), 3)
    }

    private fun renderSuggestionChips(candidates: List<String>) {
        suggestionBar.removeAllViews()
        suggestionBar.layoutParams = suggestionBar.layoutParams.apply { height = if (candidates.isEmpty()) 0 else ui.dp(44) }
        candidates.forEach { candidate ->
            val button = ui.key(candidate) {
                if (requestedPrefix.isNotEmpty()) currentInputConnection?.deleteSurroundingText(requestedPrefix.length, 0)
                commit("$candidate ")
            }.apply { textSize = 14f; contentDescription = "Insert $candidate" }
            suggestionBar.addView(button, LinearLayout.LayoutParams(0, ui.dp(42), 1f).apply { setMargins(ui.dp(2), ui.dp(1), ui.dp(2), ui.dp(1)) })
        }
    }

    private fun key(row: LinearLayout, text: String, weight: Float = 1f, action: () -> Unit): Button {
        val button = ui.key(text, action).apply { textSize = 16f; minWidth = 0; minimumWidth = 0; minHeight = ui.dp(48); minimumHeight = ui.dp(48); setPadding(0, 0, 0, 0) }
        row.addView(button, LinearLayout.LayoutParams(0, ui.dp(48), weight).apply { gravity = Gravity.CENTER_VERTICAL; setMargins(ui.dp(2), ui.dp(2), ui.dp(2), ui.dp(2)) })
        return button
    }

    private fun controlKey(row: LinearLayout, text: String, weight: Float = 1f, action: () -> Unit) = key(row, text, weight, action).apply { background = ui.shape(ui.palette.surfaceRaised, ui.palette.line, 12) }

    private fun iconControlKey(row: LinearLayout, icon: Int, description: String, weight: Float = 1f, action: () -> Unit) = controlKey(row, "", weight, action).apply {
        setCompoundDrawablesWithIntrinsicBounds(0, icon, 0, 0)
        gravity = Gravity.CENTER
        contentDescription = description
    }

    private fun sendKey(row: LinearLayout, text: String, weight: Float = 1f, action: () -> Unit) = key(row, text, weight, action).apply {
        setTextColor(ui.palette.accentText)
        background = ui.shape(ui.palette.accent, ui.palette.accent, 14)
    }

    private fun startVoice() {
        if (dictationController.state !is DictationState.Hidden) return
        val type = currentInputEditorInfo?.inputType ?: 0
        if (InputFieldSafety.isPassword(type)) {
            showKeys(getString(R.string.status_password)); return
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            showKeys(getString(R.string.status_permission_off), ::openMicrophoneSettings); return
        }
        val token = dictationController.start() ?: return
        transition(dictationController.state)
        val lang = prefs.getString("language", "en-IN") ?: "en-IN"
        engine = OnDeviceSttEngine(this, lang, { level ->
            if (dictationController.isActive(token) && dictationController.state is DictationState.Listening) {
                dictationController.level(token, level)
                wave.push(level)
            }
        }, { if (dictationController.ready(token)) transition(dictationController.state) })
        handler.removeCallbacks(timeout)
        handler.postDelayed(timeout, 120000)
        engine?.start({ raw ->
            if (!dictationController.isActive(token)) return@start
            handler.removeCallbacks(timeout)
            val personalized = personalization.render(raw)
            val finalText = LocalConservativeCleanup(prefs.getBoolean("cleanup", true)).clean(personalized)
            engine?.cancel(); engine = null
            val deliverNow = dictationController.result(token, finalText)
            if (deliverNow) deliver(finalText, token) else transition(dictationController.state)
        }, { error ->
            fail(token, FailureKind.RECOGNITION, error)
        })
    }

    private fun releaseVoice() {
        val current = dictationController.state
        val token = dictationController.currentToken() ?: return
        val finalText = dictationController.release(token)
        if (finalText != null) {
            deliver(finalText, token)
            return
        }
        if (current !is DictationState.Listening && current !is DictationState.Starting) return
        transition(dictationController.state)
        handler.removeCallbacks(timeout)
        handler.postDelayed({ if (dictationController.finishEndpoint(token)) transition(dictationController.state) }, 150)
        handler.postDelayed(timeout, 15000)
        engine?.stop()
    }

    private fun deliver(text: String, token: Long? = dictationController.currentToken()) {
        if (text.isEmpty()) {
            cancelVoice()
            showKeys(getString(R.string.status_no_speech))
            return
        }
        val insertToken = if (dictationController.state is DictationState.Failure) {
            dictationController.retry(text)
        } else {
            token
        } ?: return
        if (dictationController.state !is DictationState.Inserting) return
        transition(dictationController.state)
        val accepted = currentInputConnection?.commitText(text, 1) == true
        if (accepted) {
            prefs.edit().putBoolean("first_dictation_complete", true).apply()
            engine?.cancel(); engine = null
            dictationController.inserted(insertToken)
            transition(dictationController.state, getString(R.string.status_inserted))
            handler.postDelayed({ if (dictationController.state is DictationState.Success) { dictationController.hide(); showKeys() } }, 350)
        } else {
            engine?.cancel(); engine = null
            dictationController.insertionFailed(insertToken, getString(R.string.dictation_recovery_title), text)
            val failure = dictationController.state as DictationState.Failure
            transition(failure)
            showFailure(failure)
        }
    }

    private fun fail(token: Long, kind: FailureKind, message: String, recoverableText: String? = null) {
        handler.removeCallbacks(timeout)
        engine?.cancel(); engine = null
        if (!dictationController.failed(token, kind, message, recoverableText)) return
        val failure = dictationController.state as DictationState.Failure
        transition(failure)
        if (failure.recoverableText != null) showFailure(failure) else showKeys(failure.message)
    }

    private fun normalSend() {
        val action = (currentInputEditorInfo?.imeOptions ?: 0) and EditorInfo.IME_MASK_ACTION
        if (action != EditorInfo.IME_ACTION_NONE && action != EditorInfo.IME_ACTION_UNSPECIFIED) currentInputConnection?.performEditorAction(action) else currentInputConnection?.commitText("\n", 1)
    }

    private fun openMicrophoneSettings() {
        startActivity(
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                .setData(Uri.parse(MicrophonePermissionPolicy.appSettingsPackageUri(packageName)))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
    }

    private fun cancelVoice() {
        handler.removeCallbacks(timeout)
        engine?.cancel(); engine = null
        dictationController.abort()
    }

    override fun onFinishInputView(finishingInput: Boolean) { cancelVoice(); super.onFinishInputView(finishingInput) }
    override fun onFinishInput() { cancelVoice(); super.onFinishInput() }
    override fun onDestroy() { cancelVoice(); spellSession?.close(); super.onDestroy() }
}
