package org.vaani.app

import androidx.test.ext.junit.rules.ActivityScenarioRule
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class MainActivityTest {
    @get:Rule val rule = ActivityScenarioRule(MainActivity::class.java)

    @Test fun onboarding_activity_reaches_resumed_state() {
        rule.scenario.onActivity { activity ->
            assertTrue(activity.window.decorView.isShown)
        }
    }
}
