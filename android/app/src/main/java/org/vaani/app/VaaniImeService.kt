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
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class VaaniImeService : InputMethodService() {
    private var stt: SttSession? = null
    private lateinit var status: TextView
    private var active = false
    private val sttFence = SttSessionFence()
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
            setBackgroundColor(Color.rgb(12, 16, 32))
        }
        status = TextView(this).apply {
            text = "Vaani is ready"
            setTextColor(Color.rgb(255, 247, 241))
            textSize = 15f
            gravity = Gravity.CENTER
        }
        val dictate = Button(this).apply {
            text = "Hold to speak"
            setTextColor(Color.rgb(255, 247, 241))
            setBackgroundColor(Color.rgb(82, 107, 255))
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
        stt?.cancel()
        val session = sttFence.begin()
        active = true
        status.text = "Listening… release to finish"
        stt = SttFactory.create(this).also { engine ->
            engine.start(
                onReady = {
                    status.post {
                        if (active && sttFence.isCurrent(session)) {
                            status.text = "Listening… release to finish"
                        }
                    }
                },
                onResult = result@{ final ->
                    if (!active || !sttFence.isCurrent(session)) return@result
                    formatScope.launch {
                        val text = PersonalizationStore(this@VaaniImeService)
                            .render(LocalInference.format(this@VaaniImeService, final.text))
                        if (active && sttFence.isCurrent(session)) deliver(text)
                    }
                },
                onError = error@{ message ->
                    status.post {
                        if (sttFence.isCurrent(session)) {
                            endSttSession()
                            status.text = message
                        }
                    }
                },
            )
        }
    }

    private fun stopDictation() { if (active) stt?.stop() }
    private fun cancelDictation() { endSttSession(); status.text = "Cancelled" }

    private fun deliver(text: String) {
        val completed = endSttSession()
        val delivery = FieldPolicy.deliveryFor(currentInputEditorInfo)
        val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
        val result = TextDelivery.deliver(
            text = text,
            delivery = delivery,
            commit = { value -> currentInputConnection?.commitText(value, 1) == true },
            copy = { value -> clipboard.setPrimaryClip(ClipData.newPlainText("Vaani dictation", value)) },
        )
        status.post {
            if (sttFence.isCurrent(completed)) {
                status.text = when (result) {
                    DeliveryResult.INSERTED -> "Inserted"
                    DeliveryResult.COPIED -> "Copied — paste into this field"
                    DeliveryResult.EMPTY -> "No speech detected"
                }
            }
        }
    }

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        endSttSession()
    }

    override fun onDestroy() {
        endSttSession()
        formatScope.cancel()
        super.onDestroy()
    }

    private fun endSttSession(): Long {
        val completed = sttFence.invalidate()
        stt?.cancel()
        stt = null
        active = false
        return completed
    }
}
