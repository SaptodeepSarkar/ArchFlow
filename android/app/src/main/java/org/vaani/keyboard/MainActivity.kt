package org.vaani.keyboard

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import android.widget.*
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.core.view.doOnLayout

class MainActivity : Activity() {
    private val prefs by lazy { getSharedPreferences("vaani", 0) }
    private var scrollY = 0
    private var activeScroll: ScrollView? = null
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        if (!prefs.getBoolean("appearance_v2", false)) {
            prefs.edit().putBoolean("appearance_v2", true).putString("background", "image").apply()
        }
        hideBars(); render()
    }
    override fun onWindowFocusChanged(focused: Boolean) {
        super.onWindowFocusChanged(focused)
        if (focused) hideBars()
    }
    private fun hideBars() = WindowCompat.getInsetsController(window, window.decorView).apply {
        systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        hide(WindowInsetsCompat.Type.systemBars())
    }
    private fun keyboardEnabled(): Boolean {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        return imm.enabledInputMethodList.any { it.packageName == packageName && it.serviceName == VaaniKeyboardService::class.java.name }
    }
    private fun render() {
        scrollY = activeScroll?.scrollY ?: scrollY
        if (!prefs.getBoolean("onboarding_v2", false)) {
            val scroll = ScrollView(this)
            scroll.addView(OnboardingView(this) { prefs.edit().putBoolean("onboarding_v2", true).apply(); render() })
            setContentView(scroll)
            return
        }
        val ui = Ui(this)
        val root = ui.column()
        root.addView(ui.title("Vanni"))
        root.addView(ui.label("Your keyboard, your voice.", 18f))
        fun section(title: String, detail: String) {
            root.addView(ui.title(title, 22f)); root.addView(ui.label(detail))
        }
        val enabled = keyboardEnabled()
        section("Keyboard", if (enabled) "Vanni is enabled. Choose it whenever you want to dictate or type." else "Enable Vanni in Android settings, then choose it in the keyboard picker.")
        if (!enabled) root.addView(ui.button("Enable Vanni") { startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) })
        root.addView(ui.button("Choose keyboard") { (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).showInputMethodPicker() })
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            root.addView(ui.button("Allow microphone") { requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 42) })
        }
        section("Speech language", "Choose the language you will dictate. Availability depends on your phone's installed speech models.")
        listOf("English" to "en-IN", "हिन्दी" to "hi-IN", "বাংলা" to "bn-IN").forEach { (name, code) ->
            root.addView(ui.button((if (prefs.getString("language", "en-IN") == code) "✓  " else "") + name) {
                prefs.edit().putString("language", code).apply(); render()
            })
        }
        section("Light cleanup", "Capitalization, spacing and a final period. This version does not include an LLM.")
        root.addView(Switch(this).apply {
            text = "Clean up dictated text"; textSize = 16f; setTextColor(ui.ink)
            isChecked = prefs.getBoolean("cleanup", true)
            setPadding(0, ui.dp(12), 0, ui.dp(12))
            setOnCheckedChangeListener { _, checked -> prefs.edit().putBoolean("cleanup", checked).apply() }
        })
        section("Appearance", "Choose a theme, an accent, and the background texture used in Vanni and its keyboard.")
        listOf("Light" to "light", "Dark" to "dark", "Forest" to "forest", "Blush" to "blush").forEach { (name, key) ->
            root.addView(ui.button((if (prefs.getString("theme", "light") == key) "✓  " else "") + name) {
                prefs.edit().putString("theme", key).apply(); render()
            })
        }
        section("Accent colour", "A small personal touch for actions and the Send key.")
        listOf("Vanni lime" to 0, "Lilac" to 0xffe6cff9.toInt(), "Coral" to 0xffe9bbb6.toInt()).forEach { (name, color) ->
            root.addView(ui.button((if (prefs.getInt("accent", 0) == color) "✓  " else "") + name) {
                prefs.edit().putInt("accent", color).apply(); render()
            })
        }
        section("Background", "This is only visual. It never changes what Vanni hears or sends.")
        listOf("Plain paper" to "paper", "Fine grain" to "grain", "Vanni artwork" to "image").forEach { (name, key) ->
            root.addView(ui.button((if (prefs.getString("background", "image") == key) "✓  " else "") + name) {
                prefs.edit().putString("background", key).apply(); render()
            })
        }
        section("Hold Send to speak", "Hold Send while speaking. Release to finish and insert your cleaned text. Cancel only if you want to discard it.")
        val scroll = ScrollView(this).apply {
            setBackgroundColor(ui.paper)
            addView(root)
            setOnScrollChangeListener { _, _, y, _, _ -> scrollY = y }
        }
        activeScroll = scroll
        setContentView(scroll)
        scroll.doOnLayout { scroll.scrollTo(0, scrollY) }
    }
}
