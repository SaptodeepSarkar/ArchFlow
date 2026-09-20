package org.vaani.app

import android.text.InputType
import android.view.inputmethod.EditorInfo

enum class Delivery { INSERT, COPY_ONLY }

/** A focused editor is the only authority for automatic text delivery. */
object FieldPolicy {
    fun deliveryFor(info: EditorInfo?): Delivery {
        if (info == null) return Delivery.COPY_ONLY
        val type = info.inputType
        val password = type and InputType.TYPE_MASK_VARIATION in setOf(
            InputType.TYPE_TEXT_VARIATION_PASSWORD,
            InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
            InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD,
        )
        val multiLine = type and InputType.TYPE_TEXT_FLAG_MULTI_LINE != 0
        val text = type and InputType.TYPE_MASK_CLASS == InputType.TYPE_CLASS_TEXT
        return if (text && !password && !multiLine) Delivery.INSERT else Delivery.COPY_ONLY
    }
}
