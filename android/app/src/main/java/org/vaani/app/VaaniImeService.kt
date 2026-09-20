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

class VaaniImeService : InputMethodService() {
    private var stt: SttSession? = null
    private lateinit var status: TextView
    private var active = false

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    override fun onEvaluateInputViewShown(): Boolean {
        super.onEvaluateInputViewShown()
        return true
    }

    override fun onCreateInputView(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(14), dp(18), dp(18))
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
        root.addView(status, LinearLayout.LayoutParams(-1, dp(48)))
        root.addView(dictate, LinearLayout.LayoutParams(-1, dp(64)))
        return root
    }

    private fun startDictation() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            status.text = "Microphone permission is required in Vaani"
            return
        }
        active = true
        status.text = "Listening… release to finish"
        stt = OnDeviceStt(this).also { engine ->
            engine.start(
                onReady = { status.post { status.text = "Listening… release to finish" } },
                onResult = { raw -> deliver(SafeFormatter.format(raw)) },
                onError = { message -> status.post { status.text = message; active = false } },
            )
        }
    }

    private fun stopDictation() { if (active) stt?.stop() }
    private fun cancelDictation() { stt?.cancel(); active = false; status.text = "Cancelled" }

    private fun deliver(text: String) {
        stt?.cancel(); active = false
        if (text.isBlank()) { status.post { status.text = "No speech detected" }; return }
        val delivery = FieldPolicy.deliveryFor(currentInputEditorInfo)
        val inserted = delivery == Delivery.INSERT && currentInputConnection?.commitText(text, 1) == true
        if (!inserted) {
            (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("Vaani dictation", text))
        }
        status.post { status.text = if (inserted) "Inserted" else "Copied — paste into this field" }
    }

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        stt?.cancel(); active = false
    }
}
