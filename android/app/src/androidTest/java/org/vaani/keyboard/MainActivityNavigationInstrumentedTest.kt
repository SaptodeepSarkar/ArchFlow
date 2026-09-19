package org.vaani.keyboard

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.ScrollView
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
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
    fun longSurfaceRestoresTabAndScrollAfterRecreation() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val prefs = context.getSharedPreferences("vaani", Context.MODE_PRIVATE)
        val wasOnboardingComplete = prefs.getBoolean("onboarding_v2", false)
        prefs.edit().putBoolean("onboarding_v2", true).commit()

        var activity = instrumentation.startActivitySync(
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK),
        )
        try {
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                buttons(activity.window.decorView).first { it.text.toString().contains("Personalize") }.performClick()
            }
            instrumentation.waitForIdleSync()
            val scroll = collect(activity.window.decorView).filterIsInstance<ScrollView>().single()
            instrumentation.runOnMainSync { scroll.scrollTo(0, 600) }
            instrumentation.waitForIdleSync()
            assertTrue(scroll.scrollY > 0)

            instrumentation.runOnMainSync { activity.recreate() }
            instrumentation.waitForIdleSync()
            val restoredScroll = collect(activity.window.decorView).filterIsInstance<ScrollView>().single()
            assertTrue(textViews(activity.window.decorView).any { it.text.toString() == "Personalize" })
            assertTrue(restoredScroll.scrollY > 0)
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            prefs.edit().putBoolean("onboarding_v2", wasOnboardingComplete).commit()
        }
    }

    @Test
    fun personalizeSurfaceAddsVocabularyThroughItsEditor() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val prefs = context.getSharedPreferences("vaani", Context.MODE_PRIVATE)
        val wasOnboardingComplete = prefs.getBoolean("onboarding_v2", false)
        context.deleteDatabase("vaani_personalization.db")
        prefs.edit().putBoolean("onboarding_v2", true).commit()

        val activity = instrumentation.startActivitySync(
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK),
        )
        try {
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                buttons(activity.window.decorView).first { it.text.toString().contains("Personalize") }.performClick()
            }
            instrumentation.waitForIdleSync()
            val fields = collect(activity.window.decorView).filterIsInstance<EditText>()
            val term = fields.first { it.hint.toString() == "Vocabulary term" }
            val aliases = fields.first { it.hint.toString().contains("Spoken aliases") }
            instrumentation.runOnMainSync {
                term.setText("Vaani")
                aliases.setText("vaani")
                buttons(activity.window.decorView).first { it.text.toString() == "Add vocabulary" }.performClick()
            }
            instrumentation.waitForIdleSync()
            assertTrue(textViews(activity.window.decorView).any { it.text.toString().contains("Vaani") })
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            context.deleteDatabase("vaani_personalization.db")
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
        val device = UiDevice.getInstance(instrumentation)
        prefs.edit()
            .putBoolean("onboarding_v2", false)
            .putInt("onboarding_step", 0)
            .commit()

        val activity = instrumentation.startActivitySync(
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK),
        )
        try {
            instrumentation.waitForIdleSync()
            device.findObject(By.text("Continue")).click()
            device.waitForIdle()

            assertTrue(device.hasObject(By.text("2 of 4")))
            assertTrue(device.hasObject(By.textContains("Microphone")))
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
            val device = UiDevice.getInstance(instrumentation)
            assertTrue(!device.hasObject(By.text("Skip rehearsal for now")))
            assertTrue(device.hasObject(By.text("Finish setup")))
            assertTrue(device.hasObject(By.textContains("Hold Send")))
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            prefs.edit()
                .putBoolean("onboarding_v2", wasOnboardingComplete)
                .putInt("onboarding_step", previousStep)
                .putBoolean("first_dictation_complete", wasDictationComplete)
                .commit()
        }
    }

    @Test
    fun selectedVaaniImeRendersUsableKeyboardInRehearsalField() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        val prefs = context.getSharedPreferences("vaani", Context.MODE_PRIVATE)
        val previousComplete = prefs.getBoolean("onboarding_v2", false)
        val previousStep = prefs.getInt("onboarding_step", 0)
        val previousDefault = device.executeShellCommand("settings get secure default_input_method").trim()
        val previousEnabled = device.executeShellCommand("settings get secure enabled_input_methods").trim()
        prefs.edit().putBoolean("onboarding_v2", false).putInt("onboarding_step", 3).commit()
        var activity: Activity? = null
        try {
            device.executeShellCommand("ime enable org.vaani.keyboard/.VaaniKeyboardService")
            device.executeShellCommand("ime set org.vaani.keyboard/.VaaniKeyboardService")
            activity = instrumentation.startActivitySync(
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK),
            )
            instrumentation.waitForIdleSync()
            device.findObject(By.desc("Test dictation field")).click()
            assertTrue(device.wait(Until.hasObject(By.text("Space")), 4_000))
            assertTrue(device.hasObject(By.text("?123")))
            if (device.hasObject(By.text("Got it"))) device.findObject(By.text("Got it")).click()
            device.findObject(By.text("a")).click()
            device.findObject(By.text("b")).click()
            device.findObject(By.text("c")).click()
            assertTrue(device.findObject(By.desc("Test dictation field")).text == "abc")
        } finally {
            activity?.let { current -> instrumentation.runOnMainSync { current.finish() } }
            prefs.edit().putBoolean("onboarding_v2", previousComplete).putInt("onboarding_step", previousStep).commit()
            if (previousEnabled.isNotEmpty() && previousEnabled != "null") {
                device.executeShellCommand("settings put secure enabled_input_methods $previousEnabled")
            }
            if (previousDefault.isNotEmpty() && previousDefault != "null") device.executeShellCommand("ime set $previousDefault")
        }
    }

    private fun buttons(view: View): List<Button> = collect(view).filterIsInstance<Button>()

    private fun textViews(view: View): List<TextView> = collect(view).filterIsInstance<TextView>()

    private fun collect(view: View): List<View> {
        if (view !is ViewGroup) return listOf(view)
        return listOf(view) + (0 until view.childCount).flatMap { collect(view.getChildAt(it)) }
    }
}
