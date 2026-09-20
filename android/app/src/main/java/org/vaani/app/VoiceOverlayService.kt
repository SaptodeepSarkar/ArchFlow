package org.vaani.app

import android.app.Service
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.IBinder
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.TextView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/** Optional overlay: it never claims to know a foreground app's text field, so it copies only. */
class VoiceOverlayService : Service() {
    private lateinit var manager: WindowManager
    private lateinit var bubble: TextView
    private var stt: SttSession? = null
    private val formatScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        manager = getSystemService(WINDOW_SERVICE) as WindowManager
        bubble = TextView(this).apply {
            text = "∨"
            textSize = 25f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(255, 247, 241))
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.rgb(82, 107, 255))
                setStroke(2, Color.rgb(255, 247, 241))
            }
            elevation = 12f
            contentDescription = "Vaani floating dictate button. Hold to dictate; result is pasted or copied."
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
            dp(64), dp(64),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE, PixelFormat.TRANSLUCENT,
        ).apply { gravity = Gravity.END or Gravity.CENTER_VERTICAL; x = 24 })
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun begin() {
        bubble.text = "…"
        stt = SttFactory.create(this).also { engine ->
            engine.start(
                onReady = { bubble.post { bubble.text = "●" } },
                onResult = { raw -> formatScope.launch {
                    val text = LocalInference.format(this@VoiceOverlayService, raw)
                    val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                    val result = TextDelivery.deliver(
                        text = text,
                        delivery = Delivery.INSERT,
                        commit = { value -> AccessibilityBridge.paste(this@VoiceOverlayService, value) },
                        copy = { value -> clipboard.setPrimaryClip(ClipData.newPlainText("Vaani dictation", value)) },
                    )
                    bubble.post { bubble.text = if (result == DeliveryResult.INSERTED) "✓" else "C" }
                }
                },
                onError = { bubble.post { bubble.text = "!" } },
            )
        }
    }

    override fun onDestroy() { stt?.cancel(); formatScope.cancel(); manager.removeView(bubble); super.onDestroy() }
}
