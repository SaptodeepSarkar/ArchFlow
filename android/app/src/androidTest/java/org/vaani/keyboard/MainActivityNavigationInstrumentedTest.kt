package org.vaani.keyboard

import android.content.Context
import android.content.Intent
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MainActivityNavigationInstrumentedTest {
    @Test
    fun topLevelNavigationReachesPersonalizeSurface() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val prefs = context.getSharedPreferences("vaani", Context.MODE_PRIVATE)
        val wasOnboardingComplete = prefs.getBoolean("onboarding_v2", false)
        prefs.edit().putBoolean("onboarding_v2", true).commit()

        val activity = instrumentation.startActivitySync(
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK),
        )
        try {
            instrumentation.waitForIdleSync()
            val buttons = buttons(activity.window.decorView)
            assertTrue(buttons.any { it.text.toString().contains("Home") })
            assertTrue(buttons.any { it.text.toString().contains("Personalize") })
            assertTrue(buttons.any { it.text.toString().contains("Settings") })

            val personalize = buttons.first { it.text.toString().contains("Personalize") }
            instrumentation.runOnMainSync { personalize.performClick() }
            instrumentation.waitForIdleSync()
            assertTrue(textViews(activity.window.decorView).any { it.text.toString() == "Personalize" })
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            prefs.edit().putBoolean("onboarding_v2", wasOnboardingComplete).commit()
        }
    }

    @Test
    fun onboardingContinueAdvancesFromIntroToMicrophonePage() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val prefs = context.getSharedPreferences("vaani", Context.MODE_PRIVATE)
        val previousComplete = prefs.getBoolean("onboarding_v2", false)
        val previousStep = prefs.getInt("onboarding_step", 0)
        prefs.edit()
            .putBoolean("onboarding_v2", false)
            .putInt("onboarding_step", 0)
            .commit()

        val activity = instrumentation.startActivitySync(
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK),
        )
        try {
            instrumentation.waitForIdleSync()
            val continueButton = buttons(activity.window.decorView)
                .first { it.text.toString() == "Continue" }
            instrumentation.runOnMainSync { continueButton.performClick() }
            // Onboarding swaps the content through a 400 ms fade/slide.
            SystemClock.sleep(500)
            instrumentation.waitForIdleSync()

            assertTrue(textViews(activity.window.decorView).any { it.text.toString() == "2 of 4" })
            assertTrue(textViews(activity.window.decorView).any { it.text.toString().contains("microphone", ignoreCase = true) })
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            prefs.edit()
                .putBoolean("onboarding_v2", previousComplete)
                .putInt("onboarding_step", previousStep)
                .commit()
        }
    }

    @Test
    fun finalOnboardingPageRequiresDictationBeforeFinishing() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val prefs = context.getSharedPreferences("vaani", Context.MODE_PRIVATE)
        val wasOnboardingComplete = prefs.getBoolean("onboarding_v2", false)
        val previousStep = prefs.getInt("onboarding_step", 0)
        val wasDictationComplete = prefs.getBoolean("first_dictation_complete", false)
        prefs.edit()
            .putBoolean("onboarding_v2", false)
            .putInt("onboarding_step", 3)
            .putBoolean("first_dictation_complete", false)
            .commit()
        val activity = instrumentation.startActivitySync(
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK),
        )
        try {
            instrumentation.waitForIdleSync()
            assertTrue(buttons(activity.window.decorView).none { it.text.toString() == "Skip rehearsal for now" })
            assertTrue(buttons(activity.window.decorView).none { it.text.toString() == "Finish setup" })
            assertTrue(textViews(activity.window.decorView).any { it.text.toString().contains("Complete the rehearsal") })
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            prefs.edit()
                .putBoolean("onboarding_v2", wasOnboardingComplete)
                .putInt("onboarding_step", previousStep)
                .putBoolean("first_dictation_complete", wasDictationComplete)
                .commit()
        }
    }

    private fun buttons(view: View): List<Button> = collect(view).filterIsInstance<Button>()

    private fun textViews(view: View): List<TextView> = collect(view).filterIsInstance<TextView>()

    private fun collect(view: View): List<View> {
        if (view !is ViewGroup) return listOf(view)
        return listOf(view) + (0 until view.childCount).flatMap { collect(view.getChildAt(it)) }
    }
}
