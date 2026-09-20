package org.vaani.app

import android.app.Service
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.RectF
import android.os.SystemClock
import android.os.IBinder
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/** Optional overlay: it never claims to know a foreground app's text field, so it copies only. */
class VoiceOverlayService : Service() {
    private lateinit var manager: WindowManager
    private lateinit var bubble: VoiceBubbleView
    private var stt: SttSession? = null
    private val formatScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (::bubble.isInitialized) {
            bubble.state = VoiceBubbleView.State.IDLE
            bubble.contentDescription = "Vaani bubble. Hold to speak; your result is pasted or copied."
        }
        return START_NOT_STICKY
    }

    override fun onCreate() {
        super.onCreate()
        manager = getSystemService(WINDOW_SERVICE) as WindowManager
        bubble = VoiceBubbleView(this).apply {
            elevation = dp(10).toFloat()
            contentDescription = "Vaani bubble. Hold to speak; your result is pasted or copied."
            setOnTouchListener { _, event ->
                when (event.actionMasked) {
                    MotionEvent.ACTION_DOWN -> { state = VoiceBubbleView.State.LISTENING; begin() }
                    MotionEvent.ACTION_UP -> { stt?.stop(); true }
                    MotionEvent.ACTION_CANCEL -> { stt?.cancel(); state = VoiceBubbleView.State.IDLE; true }
                }
                true
            }
        }
        manager.addView(bubble, WindowManager.LayoutParams(
            dp(184), dp(104),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE, PixelFormat.TRANSLUCENT,
        ).apply { gravity = Gravity.END or Gravity.CENTER_VERTICAL; x = 24 })
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun begin() {
        stt = SttFactory.create(this).also { engine ->
            engine.start(
                onReady = { bubble.post { bubble.state = VoiceBubbleView.State.LISTENING } },
                onResult = { raw -> formatScope.launch {
                    bubble.post { bubble.state = VoiceBubbleView.State.PROCESSING }
                    val text = LocalInference.format(this@VoiceOverlayService, raw)
                    val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                    val result = TextDelivery.deliver(
                        text = text,
                        delivery = Delivery.INSERT,
                        commit = { value -> AccessibilityBridge.paste(this@VoiceOverlayService, value) },
                        copy = { value -> clipboard.setPrimaryClip(ClipData.newPlainText("Vaani dictation", value)) },
                    )
                    bubble.post {
                        bubble.state = if (result == DeliveryResult.INSERTED) VoiceBubbleView.State.SENT else VoiceBubbleView.State.COPIED
                        bubble.contentDescription = if (result == DeliveryResult.INSERTED) "Vaani sent the text to the focused field." else "Vaani copied the text to the clipboard."
                        bubble.postDelayed({
                            bubble.state = VoiceBubbleView.State.IDLE
                            bubble.contentDescription = "Vaani bubble. Hold to speak; your result is pasted or copied."
                        }, 1500L)
                    }
                }
                },
                onError = { bubble.post { bubble.state = VoiceBubbleView.State.ERROR } },
            )
        }
    }

    override fun onDestroy() { stt?.cancel(); formatScope.cancel(); manager.removeView(bubble); super.onDestroy() }
}

/** Product-facing overlay control: a quiet halo when idle, a listening card while held. */
private class VoiceBubbleView(context: android.content.Context) : View(context) {
    enum class State { IDLE, LISTENING, PROCESSING, SENT, COPIED, ERROR }

    var state: State = State.IDLE
        set(value) { field = value; invalidate() }

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val density = resources.displayMetrics.density
    private fun dp(value: Float) = value * density

    override fun onDraw(canvas: android.graphics.Canvas) {
        super.onDraw(canvas)
        val now = SystemClock.uptimeMillis()
        val listening = state == State.LISTENING || state == State.PROCESSING
        val bubbleSize = dp(62f)
        val idleLeft = width - bubbleSize - dp(10f)
        val left = if (listening) dp(7f) else idleLeft
        val top = (height - bubbleSize) / 2f
        val accent = when (state) {
            State.ERROR -> Color.rgb(205, 75, 65)
            State.SENT -> Color.rgb(68, 147, 112)
            State.COPIED -> Color.rgb(82, 107, 255)
            else -> Color.rgb(82, 107, 255)
        }

        if (!listening) {
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = dp(1.5f)
            paint.color = Color.argb(105, 255, 247, 241)
            canvas.drawCircle(left + bubbleSize / 2f, top + bubbleSize / 2f, bubbleSize / 2f + dp(7f), paint)
            paint.style = Paint.Style.FILL
        }

        if (listening) {
            paint.color = Color.argb(238, 255, 247, 241)
            canvas.drawRoundRect(RectF(dp(2f), top - dp(8f), width - dp(2f), top + bubbleSize + dp(8f)), dp(28f), dp(28f), paint)
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = dp(1f)
            paint.color = Color.argb(150, 82, 107, 255)
            canvas.drawRoundRect(RectF(dp(2f), top - dp(8f), width - dp(2f), top + bubbleSize + dp(8f)), dp(28f), dp(28f), paint)
            paint.style = Paint.Style.FILL
        }

        paint.color = accent
        canvas.drawRoundRect(RectF(left, top, left + bubbleSize, top + bubbleSize), dp(21f), dp(21f), paint)
        paint.color = Color.argb(255, 255, 247, 241)
        val centerX = left + bubbleSize / 2f
        val centerY = top + bubbleSize / 2f
        val bars = floatArrayOf(0.34f, 0.58f, 0.88f, 0.52f, 0.30f)
        for (index in bars.indices) {
            val pulse = if (listening) 0.55f + 0.45f * kotlin.math.abs(kotlin.math.sin(now / 220.0 + index).toFloat()) else 0.82f
            val barHeight = dp(23f) * bars[index] * pulse
            val x = centerX + (index - 2) * dp(7f)
            canvas.drawRoundRect(RectF(x - dp(2f), centerY - barHeight, x + dp(2f), centerY + barHeight), dp(2f), dp(2f), paint)
        }

        if (listening) {
            paint.color = Color.rgb(23, 26, 38)
            paint.textSize = dp(12f)
            paint.typeface = android.graphics.Typeface.create(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD)
            canvas.drawText(if (state == State.PROCESSING) "Finishing" else "Listening", dp(80f), centerY + dp(4f), paint)
            postInvalidateOnAnimation()
        } else if (state == State.SENT || state == State.COPIED || state == State.ERROR) {
            paint.color = Color.rgb(23, 26, 38)
            paint.textSize = dp(11f)
            paint.typeface = android.graphics.Typeface.DEFAULT_BOLD
            canvas.drawText(when (state) { State.SENT -> "Sent"; State.COPIED -> "Copied"; else -> "Try again" }, dp(7f), top - dp(8f), paint)
        }
    }
}
