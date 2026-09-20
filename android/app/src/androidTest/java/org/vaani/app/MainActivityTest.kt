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

    @Test fun onboarding_renders_and_advances_to_keyboard_setup() {
        rule.onNodeWithText("Get started").assertIsDisplayed().performClick()
        rule.onNodeWithText("Enable Vaani Keyboard").assertIsDisplayed()
        rule.onNodeWithText("Your voice,\nin every text field.").assertIsDisplayed()
    }

    @Test fun model_importer_copies_a_private_model_pack() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val source = File(context.cacheDir, "test-whisper.bin").apply { writeText("test model") }
        val installed = ModelInstaller.install(context, ModelKind.STT, Uri.fromFile(source)).getOrThrow()
        assertTrue(installed.isFile)
        installed.delete()
        source.delete()
    }
}
