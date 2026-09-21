package org.vaani.app

import android.content.Context
import android.net.Uri
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class MainActivityTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    @Test fun onboarding_introduces_product_before_setup() {
        rule.onNodeWithText("4× faster\nthan typing").assertIsDisplayed()
        rule.onNodeWithText("Meet Vaani").assertIsDisplayed().performClick()
        rule.onNodeWithText("100+\nlanguages").assertIsDisplayed()
        rule.onNodeWithText("Keep going").assertIsDisplayed().performClick()
        rule.onNodeWithText("Works in\nany app").assertIsDisplayed()
        rule.onNodeWithText("Keep going").assertIsDisplayed().performClick()
        rule.onNodeWithText("Your settings,\nwhen you need them.").assertIsDisplayed()
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
        rule.onNodeWithText("Meet Vaani").assertIsDisplayed().performClick()
        rule.onNodeWithText("Keep going").assertIsDisplayed().performClick()
        rule.onNodeWithText("Keep going").assertIsDisplayed().performClick()
        rule.onNodeWithText("Skip for now").assertIsDisplayed().performClick()
        rule.onNodeWithText("A LITTLE DEMO").assertIsDisplayed()
        rule.onNodeWithText("Vaani demo").assertIsDisplayed()
        rule.onNodeWithText("Hold the bubble to speak").assertIsDisplayed()
        rule.onNodeWithText("Show me how").assertIsDisplayed()
    }
}
