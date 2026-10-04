package org.vaani.app
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import org.junit.Rule
import org.junit.Test
/** UI interaction only. Battery and native inference need hardware runs. */
class MainActivityTest {
 @get:Rule val compose=createAndroidComposeRule<MainActivity>()
 @Test fun feature_navigation_and_validated_settings() {
  compose.onNodeWithText("Your voice. Your device.").assertIsDisplayed()
  compose.onAllNodesWithText("Settings")[0].performClick()
  compose.onNodeWithText("Idle retention seconds (1–120)").performTextReplacement("999")
  compose.onNodeWithText("Save settings").performClick()
  compose.onNodeWithText("Enter retention between 1 and 120 seconds").assertIsDisplayed()
  compose.onNodeWithText("Devices").performClick()
  compose.onNodeWithText("Settings").performClick()
  compose.onNodeWithText("Unload models").assertIsDisplayed()
 }
}
