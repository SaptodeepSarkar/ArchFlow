package org.vaani.app

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo

/** Tracks the focused editable text box while the user keeps their normal IME. */
class VaaniAccessibilityService : AccessibilityService() {
    override fun onServiceConnected() {
        super.onServiceConnected()
        refreshKeyboardBounds()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        refreshKeyboardBounds()
        val source = event?.source
        if (AccessibilityEventPolicy.shouldIgnoreOwnEvent(event?.packageName, packageName)) {
            // The non-focusable overlay can generate click, content, and
            // window events.  None of those changes the editor in the app
            // behind it, so never turn them into a blur.
            Unit
        } else if (source?.isEditable == true) {
            AccessibilityBridge.observe(source)
        } else if (AccessibilityEventPolicy.shouldRefreshFocusedField(event?.eventType ?: 0)) {
            // A real external blur has no editable input here, while a new
            // focused editor can be resolved from the active app window.
            refreshFocusedField()
        }
        source?.recycle()
    }

    private fun refreshKeyboardBounds() {
        val displayHeight = resources.displayMetrics.heightPixels
        var height = 0
        windows.orEmpty().forEach { window ->
            if (window.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD) {
                val bounds = android.graphics.Rect()
                window.getBoundsInScreen(bounds)
                if (bounds.height() > 0 && bounds.top < displayHeight) {
                    height = maxOf(height, displayHeight - bounds.top)
                }
            }
            window.recycle()
        }
        AccessibilityBridge.setKeyboardHeight(height)
    }

    private fun refreshFocusedField() {
        val activeField = rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
        try {
            if (activeField?.isEditable == true && !activeField.isPassword) {
                AccessibilityBridge.observe(activeField)
            } else {
                AccessibilityBridge.clear()
            }
        } finally {
            activeField?.recycle()
        }
    }

    override fun onInterrupt() = AccessibilityBridge.clear()
    override fun onDestroy() {
        AccessibilityBridge.setKeyboardHeight(0)
        AccessibilityBridge.clear()
        super.onDestroy()
    }
}
