package org.vaani.app

import android.content.Context
import android.view.accessibility.AccessibilityNodeInfo
import java.util.concurrent.atomic.AtomicReference

/** Focused text-box authority used by the overlay without replacing the IME. */
object AccessibilityBridge {
    private val focused = AtomicReference<AccessibilityNodeInfo?>(null)

    fun observe(node: AccessibilityNodeInfo?) {
        if (node == null || !node.isEditable) return
        val copy = AccessibilityNodeInfo.obtain(node)
        focused.getAndSet(copy)?.recycle()
    }

    fun clear() {
        focused.getAndSet(null)?.recycle()
    }

    fun paste(context: Context, text: String): Boolean {
        val source = focused.get() ?: return false
        val node = AccessibilityNodeInfo.obtain(source)
        if (!node.refresh() || !node.isEditable || node.isPassword) {
            node.recycle()
            return false
        }
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
        clipboard.setPrimaryClip(android.content.ClipData.newPlainText("Vaani dictation", text))
        val pasted = node.performAction(AccessibilityNodeInfo.ACTION_PASTE)
        if (pasted) {
            node.recycle()
            return true
        }
        // Some editors expose SET_TEXT but not PASTE. Keep this fallback
        // limited to safe editable, non-password fields.
        val existing = node.text?.toString().orEmpty()
        val value = if (existing.isBlank()) text else "$existing $text"
        val args = android.os.Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value)
        }
        val set = node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
        node.recycle()
        return set
    }
}
