package org.vaani.app

import android.app.Service
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.RectF
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * An in-field dictation control. The process remains idle until Accessibility
 * reports a focused editable field; the user never has a permanent bubble
 * following them around the screen.
 */
class VoiceOverlayService : Service() {
    private lateinit var manager: WindowManager
    private lateinit var bubble: VoiceBubbleView
    private var attached = false
    private var stt: SttSession? = null
    private var touchStartedAt = 0L
    private var tapRecording = false
    private var overlayWidth = IDLE_WIDTH_DP
    private val formatScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val mainHandler = Handler(Looper.getMainLooper())
    // Do not post this to bubble: while it is detached Android retains the
    // callback in that View's run queue forever. The main handler is alive
    // regardless of whether the overlay has been attached yet.
    private val focusListener: (Boolean) -> Unit = { active -> mainHandler.post { setFieldActive(active) } }
    private val keyboardListener: (Int) -> Unit = { mainHandler.post { refreshOverlayPosition() } }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!ModelRelease.isReady(this)) {
            detach()
            stopSelf(startId)
            return START_NOT_STICKY
        }
        if (::bubble.isInitialized) {
            setFieldActive(AccessibilityBridge.hasEditableFocus())
        }
        return START_NOT_STICKY
    }

    override fun onCreate() {
        super.onCreate()
        manager = getSystemService(WINDOW_SERVICE) as WindowManager
        bubble = VoiceBubbleView(this).apply {
            elevation = dp(10).toFloat()
            isClickable = true
            isLongClickable = true
            contentDescription = "Vaani appears when an editable text field is focused."
            setOnTouchListener { _, event ->
                when (event.actionMasked) {
                    MotionEvent.ACTION_DOWN -> startTouch(event.eventTime)
                    MotionEvent.ACTION_UP -> finishTouch(event.eventTime)
                    MotionEvent.ACTION_CANCEL -> cancelTouch()
                }
                true
            }
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            stopSelf()
            return
        }
        AccessibilityBridge.addFocusListener(focusListener)
        AccessibilityBridge.addKeyboardListener(keyboardListener)
        setFieldActive(AccessibilityBridge.hasEditableFocus())
    }

    private fun setFieldActive(active: Boolean) {
        if (!active || !AccessibilityBridge.hasEditableFocus() || !ModelRelease.isReady(this)) {
            stt?.cancel()
            tapRecording = false
            bubble.state = VoiceBubbleView.State.IDLE
            detach()
            return
        }
        if (attached) return
        runCatching {
            manager.addView(bubble, layoutParams(IDLE_WIDTH_DP))
            attached = true
            overlayWidth = IDLE_WIDTH_DP
            bubble.state = VoiceBubbleView.State.IDLE
            bubble.contentDescription = "Vaani. Hold to dictate, or tap once to start and tap again to finish."
        }.onFailure { stopSelf() }
    }

    private fun detach() {
        if (attached) runCatching { manager.removeViewImmediate(bubble) }
        attached = false
        overlayWidth = IDLE_WIDTH_DP
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun refreshOverlayPosition() {
        if (attached) runCatching { manager.updateViewLayout(bubble, layoutParams(overlayWidth)) }
    }

    private fun layoutParams(width: Int) = WindowManager.LayoutParams(
        dp(width), dp(70),
        WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE, PixelFormat.TRANSLUCENT,
    ).apply {
        gravity = Gravity.END or Gravity.BOTTOM
        x = 20
        // WindowManager's bottom gravity measures y upward from the display
        // bottom.  Lift the pill above the IME instead of leaving it over
        // the keyboard; retain the old low idle position when no IME exists.
        y = maxOf(dp(190), AccessibilityBridge.currentKeyboardHeight() + dp(16))
    }

    private fun resizeOverlay(width: Int) {
        if (!attached || overlayWidth == width) return
        runCatching { manager.updateViewLayout(bubble, layoutParams(width)) }
        overlayWidth = width
    }

    private fun startTouch(eventTime: Long) {
        if (!attached) return
        if (tapRecording && bubble.state == VoiceBubbleView.State.LISTENING) {
            tapRecording = false
            bubble.tapMode = false
            stt?.stop()
            return
        }
        if (bubble.state == VoiceBubbleView.State.LISTENING || bubble.state == VoiceBubbleView.State.PROCESSING) return
        touchStartedAt = eventTime
        tapRecording = false
        resizeOverlay(LISTENING_WIDTH_DP)
        bubble.tapMode = false
        bubble.state = VoiceBubbleView.State.LISTENING
        begin()
    }

    private fun finishTouch(eventTime: Long) {
        if (bubble.state != VoiceBubbleView.State.LISTENING || touchStartedAt == 0L) return
        if (eventTime - touchStartedAt <= TAP_TIMEOUT_MS) {
            tapRecording = true
            bubble.tapMode = true
            bubble.contentDescription = "Vaani is listening. Tap the pill again to finish."
        } else {
            tapRecording = false
            bubble.tapMode = false
            stt?.stop()
        }
        touchStartedAt = 0L
    }

    private fun cancelTouch() {
        tapRecording = false
        touchStartedAt = 0L
        bubble.tapMode = false
        stt?.cancel()
        bubble.state = VoiceBubbleView.State.IDLE
        resizeOverlay(IDLE_WIDTH_DP)
    }

    private fun begin() {
        stt = SttFactory.create(this).also { engine ->
            engine.start(
                onReady = { bubble.post { bubble.state = VoiceBubbleView.State.LISTENING } },
                onRms = { level -> bubble.post { bubble.level = level } },
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
                        tapRecording = false
                        bubble.tapMode = false
                        bubble.state = if (result == DeliveryResult.INSERTED) VoiceBubbleView.State.SENT else VoiceBubbleView.State.COPIED
                        bubble.contentDescription = if (result == DeliveryResult.INSERTED) "Vaani sent the text to the focused field." else "Vaani copied the text to the clipboard."
                        bubble.postDelayed({
                            bubble.state = VoiceBubbleView.State.IDLE
                            resizeOverlay(IDLE_WIDTH_DP)
                            bubble.contentDescription = "Vaani bubble. Hold to speak; your result is pasted or copied."
                        }, 1500L)
                    }
                }
                },
                onError = { bubble.post {
                    tapRecording = false
                    bubble.tapMode = false
                    bubble.state = VoiceBubbleView.State.ERROR
                    bubble.contentDescription = "Vaani could not finish that phrase. Hold to try again."
                    bubble.postDelayed({
                        bubble.state = VoiceBubbleView.State.IDLE
                        resizeOverlay(IDLE_WIDTH_DP)
                        bubble.contentDescription = "Vaani bubble. Hold to speak; your result is pasted or copied."
                    }, 1500L)
                } },
            )
        }
    }

    override fun onDestroy() {
        stt?.cancel()
        formatScope.cancel()
        AccessibilityBridge.removeFocusListener(focusListener)
        AccessibilityBridge.removeKeyboardListener(keyboardListener)
        detach()
        super.onDestroy()
    }

    private companion object {
        const val IDLE_WIDTH_DP = 70
        const val LISTENING_WIDTH_DP = 238
        const val TAP_TIMEOUT_MS = 220L
    }
}

/** Product-facing in-field control: a compact hold-to-dictate button. */
private class VoiceBubbleView(context: android.content.Context) : View(context) {
    enum class State { IDLE, LISTENING, PROCESSING, SENT, COPIED, ERROR }

    var state: State = State.IDLE
        set(value) { field = value; invalidate() }

    var level: Float = 0f
        set(value) { field = value.coerceIn(0f, 1f); invalidate() }

    var tapMode: Boolean = false
        set(value) { field = value; invalidate() }

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val density = resources.displayMetrics.density
    private fun dp(value: Float) = value * density

    override fun onDraw(canvas: android.graphics.Canvas) {
        super.onDraw(canvas)
        val listening = state == State.LISTENING || state == State.PROCESSING
        val bubbleSize = if (listening) dp(62f) else dp(58f)
        val idleLeft = (width - bubbleSize) / 2f
        val left = if (listening) dp(4f) else idleLeft
        val top = (height - bubbleSize) / 2f
        // Matches the Linux Quickshell overlay: dark graphite surface,
        // lilac activity mark, and a muted slate outline.
        val surface = when (state) {
            State.ERROR -> Color.rgb(49, 30, 38)
            State.SENT, State.COPIED -> Color.rgb(31, 34, 48)
            else -> Color.rgb(16, 18, 24)
        }
        val icon = when (state) {
            State.ERROR -> Color.rgb(255, 180, 171)
            else -> Color.rgb(195, 180, 255)
        }

        if (listening) {
            paint.color = Color.rgb(16, 18, 24)
            canvas.drawRoundRect(RectF(dp(2f), top - dp(8f), width - dp(2f), top + bubbleSize + dp(8f)), dp(28f), dp(28f), paint)
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = dp(1f)
            paint.color = Color.rgb(61, 64, 80)
            canvas.drawRoundRect(RectF(dp(2f), top - dp(8f), width - dp(2f), top + bubbleSize + dp(8f)), dp(28f), dp(28f), paint)
            paint.style = Paint.Style.FILL
        }

        paint.color = surface
        canvas.drawRoundRect(RectF(left, top, left + bubbleSize, top + bubbleSize), dp(21f), dp(21f), paint)
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = dp(1f)
        paint.color = Color.rgb(61, 64, 80)
        canvas.drawRoundRect(RectF(left, top, left + bubbleSize, top + bubbleSize), dp(21f), dp(21f), paint)
        paint.style = Paint.Style.FILL
        paint.color = icon
        val centerX = left + bubbleSize / 2f
        val centerY = top + bubbleSize / 2f
        val bars = floatArrayOf(0.34f, 0.58f, 0.88f, 0.52f, 0.30f)
        val phase = (android.os.SystemClock.uptimeMillis() % 900L).toFloat() / 900f * (Math.PI * 2.0).toFloat()
        for (index in bars.indices) {
            val pulse = if (listening) {
                val motion = 0.14f * kotlin.math.sin(phase + index * 0.9f)
                (0.62f + motion + level * (0.42f + index * 0.06f)).coerceAtLeast(0.28f)
            } else 0.82f
            val barHeight = dp(23f) * bars[index] * pulse
            val x = centerX + (index - 2) * dp(7f)
            canvas.drawRoundRect(RectF(x - dp(2f), centerY - barHeight, x + dp(2f), centerY + barHeight), dp(2f), dp(2f), paint)
        }

        if (listening) {
            paint.color = Color.rgb(240, 240, 247)
            paint.textSize = dp(12f)
            paint.typeface = android.graphics.Typeface.create(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD)
            canvas.drawText(
                if (state == State.PROCESSING) "Finishing…" else if (tapMode) "Listening · tap to finish" else "Listening · release to finish",
                dp(78f), centerY + dp(4f), paint,
            )
            postInvalidateOnAnimation()
        } else if (state == State.SENT || state == State.COPIED || state == State.ERROR) {
            paint.color = Color.rgb(240, 240, 247)
            paint.textSize = dp(11f)
            paint.typeface = android.graphics.Typeface.DEFAULT_BOLD
            canvas.drawText(when (state) { State.SENT -> "Sent"; State.COPIED -> "Copied"; else -> "Try again" }, dp(7f), top - dp(8f), paint)
        }
    }
}
