package org.vaani.app

import android.app.Service
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.IBinder
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.TextView

/** Optional overlay: it never claims to know a foreground app's text field, so it copies only. */
class VoiceOverlayService : Service() {
    private lateinit var manager: WindowManager
    private lateinit var bubble: TextView
    private var stt: SttSession? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        manager = getSystemService(WINDOW_SERVICE) as WindowManager
        bubble = TextView(this).apply {
            text = "V"
            textSize = 22f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(255, 247, 241))
            setBackgroundColor(Color.rgb(82, 107, 255))
            contentDescription = "Vaani floating dictate button. Hold to dictate; result is copied."
            setPadding(28, 20, 28, 20)
            setOnTouchListener { _, event ->
                when (event.actionMasked) {
                    MotionEvent.ACTION_DOWN -> begin()
                    MotionEvent.ACTION_UP -> stt?.stop()
                    MotionEvent.ACTION_CANCEL -> stt?.cancel()
                }
                true
            }
        }
        manager.addView(bubble, WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE, PixelFormat.TRANSLUCENT,
        ).apply { gravity = Gravity.END or Gravity.CENTER_VERTICAL; x = 24 })
    }

    private fun begin() {
        bubble.text = "…"
        stt = OnDeviceStt(this).also { engine ->
            engine.start(
                onReady = { bubble.post { bubble.text = "●" } },
                onResult = { raw ->
                    val text = SafeFormatter.format(raw)
                    if (text.isNotBlank()) (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager)
                        .setPrimaryClip(ClipData.newPlainText("Vaani dictation", text))
                    bubble.post { bubble.text = "✓" }
                },
                onError = { bubble.post { bubble.text = "!" } },
            )
        }
    }

    override fun onDestroy() { stt?.cancel(); manager.removeView(bubble); super.onDestroy() }
}
