package org.vaani.keyboard

import android.view.inputmethod.EditorInfo

/** Maps an editor's action flags to a stable accessible label for the IME. */
object EditorActionPolicy {
    fun label(imeOptions: Int): String = when (imeOptions and EditorInfo.IME_MASK_ACTION) {
        EditorInfo.IME_ACTION_GO -> "Go"
        EditorInfo.IME_ACTION_SEARCH -> "Search"
        EditorInfo.IME_ACTION_SEND -> "Send"
        EditorInfo.IME_ACTION_NEXT -> "Next"
        EditorInfo.IME_ACTION_DONE -> "Done"
        else -> "Enter"
    }
}
