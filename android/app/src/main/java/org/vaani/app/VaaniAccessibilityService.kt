package org.vaani.app

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent

/** Tracks the focused editable text box while the user keeps their normal IME. */
class VaaniAccessibilityService : AccessibilityService() {
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        val source = event?.source
        if (source?.isEditable == true) AccessibilityBridge.observe(source)
        source?.recycle()
    }

    override fun onInterrupt() = AccessibilityBridge.clear()
    override fun onDestroy() { AccessibilityBridge.clear(); super.onDestroy() }
}
