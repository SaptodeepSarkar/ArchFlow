package org.vaani.app

import android.view.accessibility.AccessibilityEvent

/** Events that may change which input owns focus in the active application. */
internal object AccessibilityEventPolicy {
    /**
     * The bubble is owned by this package.  Its accessibility events do not
     * describe the external app's editor, even when Android reports a window
     * change while the user is holding the control.
     */
    fun shouldIgnoreOwnEvent(eventPackage: CharSequence?, servicePackage: String): Boolean =
        eventPackage?.toString() == servicePackage

    fun shouldRefreshFocusedField(eventType: Int): Boolean = when (eventType) {
        AccessibilityEvent.TYPE_VIEW_FOCUSED,
        AccessibilityEvent.TYPE_VIEW_CLICKED,
        AccessibilityEvent.TYPE_VIEW_TEXT_SELECTION_CHANGED,
        AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED,
        AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> true
        else -> false
    }
}
