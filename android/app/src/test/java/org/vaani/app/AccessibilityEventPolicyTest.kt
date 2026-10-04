package org.vaani.app

import android.view.accessibility.AccessibilityEvent
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AccessibilityEventPolicyTest {
    @Test fun events_from_the_overlay_package_never_replace_external_focus() {
        assertTrue(AccessibilityEventPolicy.shouldIgnoreOwnEvent("org.vaani.keyboard", "org.vaani.keyboard"))
        assertFalse(AccessibilityEventPolicy.shouldIgnoreOwnEvent("com.google.android.googlequicksearchbox", "org.vaani.keyboard"))
        assertFalse(AccessibilityEventPolicy.shouldIgnoreOwnEvent(null, "org.vaani.keyboard"))
    }

    @Test fun all_focus_changing_events_recheck_the_active_input() {
        assertTrue(AccessibilityEventPolicy.shouldRefreshFocusedField(AccessibilityEvent.TYPE_VIEW_FOCUSED))
        assertTrue(AccessibilityEventPolicy.shouldRefreshFocusedField(AccessibilityEvent.TYPE_VIEW_CLICKED))
        assertTrue(AccessibilityEventPolicy.shouldRefreshFocusedField(AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED))
        assertTrue(AccessibilityEventPolicy.shouldRefreshFocusedField(AccessibilityEvent.TYPE_WINDOWS_CHANGED))
        assertFalse(AccessibilityEventPolicy.shouldRefreshFocusedField(AccessibilityEvent.TYPE_ANNOUNCEMENT))
    }

    @Test fun typing_and_content_events_do_not_scan_all_interactive_windows() {
        assertFalse(AccessibilityEventPolicy.shouldRefreshKeyboardBounds(AccessibilityEvent.TYPE_VIEW_TEXT_SELECTION_CHANGED))
        assertFalse(AccessibilityEventPolicy.shouldRefreshKeyboardBounds(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED))
        assertFalse(AccessibilityEventPolicy.shouldRefreshKeyboardBounds(AccessibilityEvent.TYPE_VIEW_CLICKED))
        assertTrue(AccessibilityEventPolicy.shouldRefreshKeyboardBounds(AccessibilityEvent.TYPE_WINDOWS_CHANGED))
        assertTrue(AccessibilityEventPolicy.shouldRefreshKeyboardBounds(AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED))
    }
}
