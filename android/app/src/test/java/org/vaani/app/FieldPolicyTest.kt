package org.vaani.app

import android.text.InputType
import android.view.inputmethod.EditorInfo
import org.junit.Assert.assertEquals
import org.junit.Test

class FieldPolicyTest {
    @Test fun single_line_text_can_insert() {
        assertEquals(Delivery.INSERT, FieldPolicy.deliveryFor(EditorInfo().apply { inputType = InputType.TYPE_CLASS_TEXT }))
    }

    @Test fun password_and_multiline_are_copy_only() {
        assertEquals(Delivery.COPY_ONLY, FieldPolicy.deliveryFor(EditorInfo().apply { inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD }))
        assertEquals(Delivery.COPY_ONLY, FieldPolicy.deliveryFor(EditorInfo().apply { inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE }))
    }
}
