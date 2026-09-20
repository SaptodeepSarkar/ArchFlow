package org.vaani.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.junit.Rule
import org.junit.Test

class MainActivityTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    @Test fun onboarding_renders_and_advances_to_keyboard_setup() {
        rule.onNodeWithText("Get started").assertIsDisplayed().performClick()
        rule.onNodeWithText("Enable Vaani Keyboard").assertIsDisplayed()
        rule.onNodeWithText("Your voice,\nin every text field.").assertIsDisplayed()
    }
}
