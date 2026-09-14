package org.vaani.keyboard

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.Window
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Space
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat

class MainActivity : Activity() {
    private val prefs by lazy { getSharedPreferences("vaani", 0) }
    private var activeTab = 0
    private var scrollY = 0
    private var activeScroll: ScrollView? = null

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        activeTab = state?.getInt("active_tab") ?: 0
        configureWindow(window)
        if (!prefs.getBoolean("appearance_v3", false)) {
            prefs.edit().putBoolean("appearance_v3", true).putString("theme", "system").apply()
        }
        render()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putInt("active_tab", activeTab)
        super.onSaveInstanceState(outState)
    }

    override fun onResume() {
        super.onResume()
        if (prefs.getBoolean("onboarding_v2", false)) render()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, results)
        if (requestCode == REQUEST_MIC) {
            prefs.edit().putBoolean("microphone_requested", true).putBoolean("microphone_granted", checkMic()).apply()
            render()
        }
    }

    private fun configureWindow(window: Window) {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.statusBarColor = android.graphics.Color.TRANSPARENT
        window.navigationBarColor = android.graphics.Color.TRANSPARENT
        val controller = WindowCompat.getInsetsController(window, window.decorView)
        controller.isAppearanceLightStatusBars = true
        controller.isAppearanceLightNavigationBars = true
    }

    private fun checkMic() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun keyboardEnabled(): Boolean {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        return imm.enabledInputMethodList.any { it.packageName == packageName && it.serviceName == VaaniKeyboardService::class.java.name }
    }

    private fun recognizerAvailable() = android.speech.SpeechRecognizer.isOnDeviceRecognitionAvailable(this)

    private fun readiness() = AppReadiness(recognizerAvailable(), checkMic(), keyboardEnabled(), prefs.getBoolean("first_dictation_complete", false))

    private fun render() {
        scrollY = activeScroll?.scrollY ?: scrollY
        if (!prefs.getBoolean("onboarding_v2", false)) {
            val scroll = ScrollView(this).apply { clipToPadding = false }
            scroll.addView(OnboardingView(this, ::openImeSettings, ::showKeyboardPicker, ::requestMic) {
                prefs.edit().putBoolean("onboarding_v2", true).apply()
                render()
            })
            installInsets(scroll)
            setContentView(scroll)
            return
        }
        val ui = Ui(this)
        val frame = FrameLayout(this).apply { setBackgroundColor(ui.paper) }
        val content = ScrollView(this).apply { clipToPadding = false }
        val page = if (activeTab == 0) home(ui) else settings(ui)
        content.addView(page)
        frame.addView(content, FrameLayout.LayoutParams(-1, -1).apply { bottomMargin = ui.dp(76) })
        frame.addView(bottomNav(ui), FrameLayout.LayoutParams(-1, ui.dp(76), Gravity.BOTTOM))
        ViewCompat.setOnApplyWindowInsetsListener(frame) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            content.setPadding(0, bars.top, 0, bars.bottom)
            view.setPadding(0, 0, 0, 0)
            insets
        }
        activeScroll = content
        setContentView(frame)
        content.post { content.scrollTo(0, scrollY) }
    }

    private fun installInsets(view: View) {
        ViewCompat.setOnApplyWindowInsetsListener(view) { target, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            target.setPadding(0, bars.top, 0, bars.bottom)
            insets
        }
    }

    private fun bottomNav(ui: Ui) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER
        setPadding(ui.dp(12), ui.dp(8), ui.dp(12), ui.dp(8))
        setBackgroundColor(ui.palette.surface)
        val home = ui.key(if (activeTab == 0) "Home" else "Home") { activeTab = 0; render() }
        val settings = ui.key("Settings") { activeTab = 1; render() }
        addView(home, LinearLayout.LayoutParams(0, ui.dp(52), 1f).apply { marginEnd = ui.dp(6) })
        addView(settings, LinearLayout.LayoutParams(0, ui.dp(52), 1f).apply { marginStart = ui.dp(6) })
    }

    private fun home(ui: Ui): LinearLayout {
        val root = ui.screenColumn()
        root.addView(ui.title("Vaani"))
        root.addView(ui.label("System-wide dictation, kept close to the text field.", 17f, ui.palette.muted))
        val ready = readiness()
        val status = ui.surfaceCard()
        status.addView(ui.meta(if (ready.ready) "READY" else "SETUP"))
        status.addView(ui.label(if (ready.ready) "Ready to dictate" else blockerTitle(ready.nextBlocker), 22f).apply { typeface = android.graphics.Typeface.DEFAULT_BOLD })
        status.addView(ui.label(if (ready.ready) "English · device speech · Vaani keyboard" else blockerBody(ready.nextBlocker), 14f, ui.palette.muted))
        val action = if (ready.ready) ui.primaryButton("Start a test dictation") { showKeyboardPicker() } else ui.primaryButton(blockerAction(ready.nextBlocker)) { runBlocker(ready.nextBlocker) }
        status.addView(action, LinearLayout.LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(12) })
        root.addView(status, LinearLayout.LayoutParams(-1, -2).apply { topMargin = ui.dp(20) })
        val flow = ui.surfaceCard()
        flow.addView(ui.label("The working path", 17f).apply { typeface = android.graphics.Typeface.DEFAULT_BOLD })
        flow.addView(ui.label("Focus a text field → choose Vaani → hold Send → speak → release. Vaani inserts text and stays out of the way.", 14f, ui.palette.muted))
        root.addView(flow, LinearLayout.LayoutParams(-1, -2).apply { topMargin = ui.dp(12) })
        root.addView(ui.sectionTitle("Quick status"))
        root.addView(statusRow(ui, "Speech service", if (ready.recognizerAvailable) "Available on this device" else "Unavailable"))
        root.addView(statusRow(ui, "Microphone", if (ready.microphoneGranted) "Allowed" else "Needs access"))
        root.addView(statusRow(ui, "Vaani keyboard", if (ready.keyboardEnabled) "Enabled" else "Not enabled"))
        root.addView(ui.sectionTitle("Privacy"))
        root.addView(ui.label("Vaani has no network permission. Audio is used by the device speech recognizer during an active dictation and is not stored by this app.", 14f, ui.palette.muted))
        return root
    }

    private fun statusRow(ui: Ui, label: String, value: String): LinearLayout = LinearLayout(this).apply {
        gravity = Gravity.CENTER_VERTICAL
        setPadding(0, ui.dp(10), 0, ui.dp(10))
        addView(ui.label(label, 15f), LinearLayout.LayoutParams(0, -2, 1f))
        addView(ui.meta(value))
    }

    private fun settings(ui: Ui): LinearLayout {
        val root = ui.screenColumn()
        root.addView(ui.title("Settings"))
        root.addView(ui.label("Keep the defaults quiet and change only what affects your writing.", 16f, ui.palette.muted))
        root.addView(ui.sectionTitle("Dictation"))
        root.addView(ui.label("Speech language", 15f))
        listOf("English (India)" to "en-IN", "हिन्दी" to "hi-IN", "বাংলা" to "bn-IN").forEach { (name, code) ->
            root.addView(ui.secondaryButton((if (prefs.getString("language", "en-IN") == code) "✓  " else "") + name) { prefs.edit().putString("language", code).apply(); render() }, LinearLayout.LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(6) })
        }
        root.addView(ui.sectionTitle("Formatting"))
        root.addView(android.widget.Switch(this).apply {
            text = getString(R.string.settings_cleanup)
            textSize = 16f
            setTextColor(ui.ink)
            isChecked = prefs.getBoolean("cleanup", true)
            setPadding(0, ui.dp(8), 0, ui.dp(8))
            setOnCheckedChangeListener { _, checked -> prefs.edit().putBoolean("cleanup", checked).apply() }
        })
        root.addView(ui.meta("Vaani applies conservative local cleanup: fillers, capitalization, punctuation, explicit lists, and supported emoji cues. It does not rewrite content or execute dictated commands."))
        root.addView(ui.sectionTitle("Appearance"))
        listOf("System" to "system", "Light" to "light", "Dark" to "dark").forEach { (name, key) ->
            root.addView(ui.secondaryButton((if (prefs.getString("theme", "system") == key) "✓  " else "") + name) { prefs.edit().putString("theme", key).apply(); render() }, LinearLayout.LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(6) })
        }
        root.addView(ui.sectionTitle("Keyboard"))
        root.addView(ui.secondaryButton("Open Android keyboard settings") { openImeSettings() }, LinearLayout.LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(6) })
        root.addView(ui.secondaryButton("Choose keyboard now") { showKeyboardPicker() }, LinearLayout.LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(6) })
        root.addView(ui.sectionTitle("Not available yet"))
        root.addView(ui.label("Vocabulary, snippets, replacements, history, downloadable Vaani models, and coexisting overlay invocation are not wired in this build. They will appear only when their local backend contracts are ready.", 14f, ui.palette.muted))
        root.addView(ui.sectionTitle("About"))
        root.addView(ui.meta("Vaani Android 0.1.0 · local-first dictation"))
        return root
    }

    private fun blockerTitle(blocker: ReadinessBlocker?) = when (blocker) {
        ReadinessBlocker.RECOGNIZER -> "Device speech is unavailable"
        ReadinessBlocker.MICROPHONE -> "Microphone access is off"
        ReadinessBlocker.KEYBOARD -> "Enable the Vaani keyboard"
        ReadinessBlocker.TEST -> "Complete one test dictation"
        null -> "Ready"
    }

    private fun blockerBody(blocker: ReadinessBlocker?) = when (blocker) {
        ReadinessBlocker.RECOGNIZER -> "This device has no available on-device speech recognizer."
        ReadinessBlocker.MICROPHONE -> "Vaani asks for the microphone only when you choose to dictate."
        ReadinessBlocker.KEYBOARD -> "The keyboard is how Vaani currently reaches text fields safely."
        ReadinessBlocker.TEST -> "Try the hold → speak → release path once before daily use."
        null -> ""
    }

    private fun blockerAction(blocker: ReadinessBlocker?) = when (blocker) {
        ReadinessBlocker.RECOGNIZER -> "Check speech settings"
        ReadinessBlocker.MICROPHONE -> "Allow microphone"
        ReadinessBlocker.KEYBOARD -> "Enable keyboard"
        ReadinessBlocker.TEST -> "Choose Vaani keyboard"
        null -> "Continue"
    }

    private fun runBlocker(blocker: ReadinessBlocker?) = when (blocker) {
        ReadinessBlocker.RECOGNIZER -> startActivity(Intent(Settings.ACTION_VOICE_INPUT_SETTINGS))
        ReadinessBlocker.MICROPHONE -> requestMic()
        ReadinessBlocker.KEYBOARD -> openImeSettings()
        ReadinessBlocker.TEST -> showKeyboardPicker()
        null -> Unit
    }

    private fun openImeSettings() = startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))

    private fun showKeyboardPicker() = (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).showInputMethodPicker()

    private fun requestMic() = requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_MIC)

    companion object { private const val REQUEST_MIC = 42 }
}
