package org.vaani.app

import android.app.Activity
import android.os.Bundle
import android.text.InputType
import android.widget.EditText
import android.widget.Button
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
            text = "Vaani overlay harness\nKeep your normal keyboard; the bubble pastes into the focused field."
            textSize = 18f
        }, LinearLayout.LayoutParams(-1, -2))
        root.addView(Button(this).apply {
            text = "Test Vaani paste"
            contentDescription = "Test Vaani paste into focused field"
            setOnClickListener {
                val inserted = AccessibilityBridge.paste(this@EditorHarnessActivity, "This came from Vaani.")
                text = if (inserted) "Paste sent to focused field" else "No editable field available"
            }
        }, LinearLayout.LayoutParams(-1, 120))
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
