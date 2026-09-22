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
        assertFalse(AccessibilityEventPolicy.shouldRefreshFocusedField(AccessibilityEvent.TYPE_ANNOUNCEMENT))
    }
}
