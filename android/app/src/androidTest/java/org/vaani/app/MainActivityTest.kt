package org.vaani.app

import android.content.Context
import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.rules.ActivityScenarioRule
import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain

class MainActivityTest {
    private val activityRule = ActivityScenarioRule<MainActivity>(
        Intent(Intent.ACTION_MAIN).setComponent(
            ComponentName("org.vaani.keyboard", MainActivity::class.java.name),
        ),
    )
    private val composeRule = createEmptyComposeRule()
    // Compose must be installed before the activity calls setContent().
    @get:Rule val rule: RuleChain = RuleChain.outerRule(composeRule).around(activityRule)

    @Before fun freezeDecorativeAnimations() {
        // Language and destination rails intentionally animate forever in the
        // product. A test must not wait for those decorative frames to settle.
        composeRule.mainClock.autoAdvance = false
    }

    @Test fun onboarding_introduces_product_before_setup() {
        composeRule.onNodeWithText("The thought.\nWritten.").assertIsDisplayed()
        composeRule.onNodeWithText("Get started").assertIsDisplayed().performClick()
        composeRule.onNodeWithText("Your voice,\nyour language.").assertIsDisplayed()
        composeRule.onNodeWithText("Next").assertIsDisplayed().performClick()
        composeRule.onNodeWithText("Wherever you\nwrite.").assertIsDisplayed()
        composeRule.onNodeWithText("Next").assertIsDisplayed().performClick()
        composeRule.onNodeWithText("Keep your\nwriting setup close.").assertIsDisplayed()
    }

    @Test fun model_importer_copies_a_private_model_pack() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val source = File(context.cacheDir, "test-whisper.bin").apply { writeText("test model") }
        val installed = ModelInstaller.install(context, ModelKind.STT, Uri.fromFile(source)).getOrThrow()
        assertTrue(installed.isFile)
        installed.delete()
        source.delete()
    }

    @Test fun post_login_demo_keeps_the_keyboard_and_shows_the_bubble() {
        composeRule.onNodeWithText("Get started").assertIsDisplayed().performClick()
        composeRule.onNodeWithText("Next").assertIsDisplayed().performClick()
        composeRule.onNodeWithText("Next").assertIsDisplayed().performClick()
        composeRule.onNodeWithText("Skip for now").assertIsDisplayed().performClick()
        composeRule.onNodeWithText("A LITTLE DEMO").assertIsDisplayed()
        composeRule.onNodeWithText("Vaani demo").assertIsDisplayed()
        composeRule.onNodeWithText("Hold the bubble to speak").assertIsDisplayed()
        composeRule.onNodeWithText("Show me how").assertIsDisplayed()
    }
}
