package org.vaani.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalInferenceTest {
    @Test
    fun model_edit_may_change_case_and_punctuation() {
        assertTrue(ModelOutputGuard.isSafeEdit("open the browser", "Open the browser."))
    }

    @Test
    fun model_edit_rejects_invented_or_reordered_words() {
        assertFalse(ModelOutputGuard.isSafeEdit("open the browser", "Open Chrome browser."))
        assertFalse(ModelOutputGuard.isSafeEdit("open the browser", "Browser the open."))
    }

    @Test
    fun filler_removal_is_allowed_but_empty_output_is_not() {
        assertTrue(ModelOutputGuard.isSafeEdit("uh open the browser", "Open the browser."))
        assertFalse(ModelOutputGuard.isSafeEdit("uh um", ""))
    }
}
