package org.vaani.app

import android.app.Activity
import android.os.Bundle
import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

/** Debug-only editor used by emulator smoke tests for the real InputMethodService. */
class EditorHarnessActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 64, 48, 48)
        }
        root.addView(TextView(this).apply {
            text = "Vaani injection harness\nFocus the field, switch to Vaani Keyboard, then hold to speak."
            textSize = 18f
        }, LinearLayout.LayoutParams(-1, -2))
        root.addView(EditText(this).apply {
            hint = "Safe single-line text field"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            contentDescription = "Safe single-line text field"
        }, LinearLayout.LayoutParams(-1, 160))
        root.addView(EditText(this).apply {
            hint = "Multiline field copies instead"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            minLines = 3
            contentDescription = "Multiline field copies instead"
        }, LinearLayout.LayoutParams(-1, 240))
        setContentView(root)
    }
}
