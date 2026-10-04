package org.vaani.app

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Color
import android.inputmethodservice.InputMethodService
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class VaaniImeService : InputMethodService() {
    private var stt: SttSession? = null
    private lateinit var status: TextView
    private var active = false
    private val sessions = DictationSessionGate()
    private var formatting: Job? = null
    private var ownership: Long? = null
    private val formatScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    override fun onEvaluateInputViewShown(): Boolean {
        super.onEvaluateInputViewShown()
        return true
    }

    override fun onCreateInputView(): View {
        val root = LinearLayout(this).apply {
            // Some Android surfaces allocate only a 48dp input strip. Keep
            // the status and action side-by-side so neither is clipped.
            orientation = LinearLayout.HORIZONTAL
            // Android may give an IME only a compact strip above navigation;
            // keep both status and the primary action inside that strip.
            setPadding(dp(12), dp(6), dp(12), dp(6))
            setBackgroundColor(Color.rgb(250, 250, 247))
        }
        status = TextView(this).apply {
            text = "Vaani is ready"
            setTextColor(Color.rgb(32, 43, 54))
            textSize = 15f
            gravity = Gravity.CENTER
        }
        val dictate = Button(this).apply {
            text = "Hold to speak"
            setTextColor(Color.rgb(32, 43, 54))
            setBackgroundColor(Color.rgb(228, 242, 255))
            contentDescription = "Hold to speak, release to insert"
            setOnTouchListener { _, event ->
                when (event.actionMasked) {
                    MotionEvent.ACTION_DOWN -> startDictation()
                    MotionEvent.ACTION_UP -> stopDictation()
                    MotionEvent.ACTION_CANCEL -> cancelDictation()
                }
                true
            }
        }
        root.addView(status, LinearLayout.LayoutParams(0, -1, 1f))
        root.addView(dictate, LinearLayout.LayoutParams(dp(170), -1))
        return root
    }

    private fun startDictation() {
        if (active) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            status.text = "Microphone permission is required in Vaani"
            return
        }
        cancelSession()
        ownership = ActiveDictation.ownership.claim {
            cancelSession()
            if (::status.isInitialized) status.text = "Cancelled"
        }
        val token = sessions.begin()
        val connection = currentInputConnection
        val delivery = FieldPolicy.deliveryFor(currentInputEditorInfo)
        active = true
        status.text = "Listening… release to finish"
        fun failed(message: String) {
            status.post {
                if (sessions.isListening(token)) {
                    cancelSession()
                    status.text = message
                }
            }
        }
        try {
            val engine = SttFactory.create(this)
            stt = engine
            engine.start(
                onReady = { status.post {
                    if (sessions.isListening(token)) status.text = "Listening… release to finish"
                } },
                onResult = { raw -> status.post {
                    if (!sessions.acceptResult(token)) return@post
                    stt?.cancel()
                    stt = null
                    formatting = formatScope.launch {
                        val text = PersonalizationStore(this@VaaniImeService).render(LocalInference.format(this@VaaniImeService, raw))
                        if (!sessions.isCurrent(token)) return@launch
                        deliver(text, delivery) { value ->
                            connection != null && connection === currentInputConnection && connection.commitText(value, 1)
                        }
                    }
                } },
                onError = { message -> failed(message) },
            )
        } catch (_: Exception) { failed("Speech input could not start") }
    }

    private fun stopDictation() { if (active) stt?.stop() }

    private fun cancelSession() {
        sessions.invalidate()
        formatting?.cancel()
        formatting = null
        stt?.cancel()
        stt = null
        active = false
        ActiveDictation.ownership.release(ownership)
        ownership = null
    }

    private fun cancelDictation() { cancelSession(); status.text = "Cancelled" }

    private fun deliver(text: String, delivery: Delivery, commit: (String) -> Boolean) {
        active = false
        ActiveDictation.ownership.release(ownership)
        ownership = null
        val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
        val result = TextDelivery.deliver(
            text = text,
            delivery = delivery,
            commit = commit,
            copy = { value -> clipboard.setPrimaryClip(ClipData.newPlainText("Vaani dictation", value)) },
        )
        status.text = when (result) {
                DeliveryResult.INSERTED -> "Inserted"
                DeliveryResult.COPIED -> "Copied — paste into this field"
                DeliveryResult.EMPTY -> "No speech detected"
            }
    }

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        cancelSession()
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        cancelSession()
        super.onFinishInputView(finishingInput)
    }

    override fun onFinishInput() {
        cancelSession()
        super.onFinishInput()
    }

    override fun onDestroy() {
        cancelSession()
        formatScope.cancel()
        super.onDestroy()
    }
}
