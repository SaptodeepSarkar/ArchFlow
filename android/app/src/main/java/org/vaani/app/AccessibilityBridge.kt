package org.vaani.app

import android.content.Context
import android.accessibilityservice.AccessibilityServiceInfo
import android.view.accessibility.AccessibilityManager
import android.view.accessibility.AccessibilityNodeInfo
import java.util.concurrent.atomic.AtomicReference
import java.util.concurrent.CopyOnWriteArraySet
import java.util.concurrent.atomic.AtomicInteger

/** Focused text-box authority used by the overlay without replacing the IME. */
object AccessibilityBridge {
    private val focused = AtomicReference<AccessibilityNodeInfo?>(null)
    private val focusListeners = CopyOnWriteArraySet<(Boolean) -> Unit>()
    private val keyboardHeight = AtomicInteger(0)
    private val keyboardListeners = CopyOnWriteArraySet<(Int) -> Unit>()
    private val targets = FocusTargetLease<AccessibilityNodeInfo>()

    /** A field switch (including away and back) invalidates the original target. */
    fun captureTarget(): Long? = if (hasEditableFocus()) targets.capture() else null

    fun observe(node: AccessibilityNodeInfo?) {
        if (node == null || !node.isEditable || !node.isFocused || node.isPassword) {
            clear()
            return
        }
        val copy = AccessibilityNodeInfo.obtain(node)
        val previous = focused.getAndSet(copy)
        val changed = targets.observe(copy)
        previous?.recycle()
        if (changed) {
            notifyFocus(true)
        }
    }

    fun clear() {
        val previous = focused.getAndSet(null)
        targets.observe(null)
        previous?.recycle()
        if (previous != null) {
            notifyFocus(false)
        }
    }

    fun hasEditableFocus(): Boolean {
        val node = focused.get() ?: return false
        return node.refresh() && node.isFocused && node.isEditable && !node.isPassword
    }

    fun addFocusListener(listener: (Boolean) -> Unit) {
        focusListeners += listener
        listener(hasEditableFocus())
    }

    /** Android requires this service to be enabled by the person using the device. */
    fun isTextBoxAccessEnabled(context: Context): Boolean {
        val manager = context.getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
        return manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK).any { service ->
            val info = service.resolveInfo?.serviceInfo
            info?.packageName == context.packageName && info.name == VaaniAccessibilityService::class.java.name
        }
    }

    fun removeFocusListener(listener: (Boolean) -> Unit) {
        focusListeners -= listener
    }

    fun setKeyboardHeight(height: Int) {
        val value = height.coerceAtLeast(0)
        if (keyboardHeight.getAndSet(value) != value) keyboardListeners.forEach { it(value) }
    }

    fun currentKeyboardHeight(): Int = keyboardHeight.get()

    fun addKeyboardListener(listener: (Int) -> Unit) {
        keyboardListeners += listener
        listener(currentKeyboardHeight())
    }

    fun removeKeyboardListener(listener: (Int) -> Unit) {
        keyboardListeners -= listener
    }

    private fun notifyFocus(active: Boolean) {
        focusListeners.forEach { it(active) }
    }

    fun paste(context: Context, text: String, target: Long? = captureTarget()): Boolean {
        if (!targets.matches(target)) return false
        val source = focused.get() ?: return false
        val node = AccessibilityNodeInfo.obtain(source)
        if (!node.refresh() || !node.isFocused || !node.isEditable || node.isPassword) {
            node.recycle()
            return false
        }
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
        clipboard.setPrimaryClip(android.content.ClipData.newPlainText("Vaani dictation", text))
        return try {
            // ACTION_PASTE honors the editor's selection. SET_TEXT replaced the
            // complete document and appended at the end; use copy fallback instead.
            node.performAction(AccessibilityNodeInfo.ACTION_PASTE)
        } finally {
            node.recycle()
        }
    }
}
