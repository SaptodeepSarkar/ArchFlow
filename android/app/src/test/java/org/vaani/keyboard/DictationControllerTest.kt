package org.vaani.keyboard

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import android.text.InputType
import android.view.inputmethod.EditorInfo

class DictationControllerTest {
    @Test
    fun editorActionLabelsFollowFocusedField() {
        assertEquals("Search", EditorActionPolicy.label(EditorInfo.IME_ACTION_SEARCH))
        assertEquals("Done", EditorActionPolicy.label(EditorInfo.IME_ACTION_DONE))
        assertEquals("Enter", EditorActionPolicy.label(EditorInfo.IME_ACTION_NONE))
    }

    @Test
    fun passwordFieldsAreNeverDictatedInto() {
        assertTrue(InputFieldSafety.isPassword(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD))
        assertTrue(InputFieldSafety.isPassword(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD))
        assertTrue(InputFieldSafety.isPassword(InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD))
        assertTrue(!InputFieldSafety.isPassword(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_NORMAL))
    }

    @Test
    fun permanentlyDeniedMicrophoneRoutesToAppSettings() {
        assertTrue(MicrophonePermissionPolicy.requiresAppSettings(true, false, false))
        assertTrue(!MicrophonePermissionPolicy.requiresAppSettings(false, false, false))
        assertTrue(!MicrophonePermissionPolicy.requiresAppSettings(true, false, true))
        assertTrue(!MicrophonePermissionPolicy.requiresAppSettings(true, true, false))
    }

    @Test
    fun staleResultCannotMutateNewSession() {
        val controller = DictationController()
        val old = controller.start()!!
        controller.cancel()
        controller.hide()
        val current = controller.start()!!

        assertTrue(!controller.result(old, "stale"))
        assertEquals(DictationState.Starting, controller.state)
        assertTrue(controller.ready(current))
    }

    @Test
    fun releaseBeforeResultMovesThroughEndpointing() {
        val controller = DictationController()
        val token = controller.start()!!
        controller.ready(token)

        assertNull(controller.release(token))
        assertEquals(DictationState.Endpointing, controller.state)
        assertTrue(controller.finishEndpoint(token))
        assertEquals(DictationState.Finalizing, controller.state)
        assertTrue(controller.result(token, "hello"))
        assertEquals(DictationState.Inserting("hello"), controller.state)
    }

    @Test
    fun insertionFailureRetainsTextForRecovery() {
        val controller = DictationController()
        val token = controller.start()!!
        controller.ready(token)
        controller.result(token, "Hyprland notes")
        assertEquals("Hyprland notes", controller.release(token))

        assertTrue(controller.insertionFailed(token, "Insertion failed", "Hyprland notes"))
        assertEquals(
            DictationState.Failure(FailureKind.INSERTION, "Insertion failed", "Hyprland notes"),
            controller.state,
        )
    }

    @Test
    fun retryCreatesFreshInsertionSession() {
        val controller = DictationController()
        val token = controller.start()!!
        controller.ready(token)
        controller.result(token, "recover me")
        controller.release(token)
        controller.insertionFailed(token, "Insertion failed", "recover me")

        val retryToken = controller.retry("recover me")!!
        assertTrue(retryToken != token)
        assertEquals(DictationState.Inserting("recover me"), controller.state)
    }
}
