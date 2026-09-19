package org.vaani.keyboard

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import android.net.Uri
import android.view.Gravity
import android.view.View
import android.view.Window
import android.widget.FrameLayout
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Space
import android.widget.TextView
import android.text.InputType
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat

class MainActivity : Activity() {
    private val prefs by lazy { getSharedPreferences("vaani", 0) }
    private var activeTab = 0
    private var scrollY = 0
    private var activeScroll: ScrollView? = null
    private var onboardingView: OnboardingView? = null
    private var homeTestField: EditText? = null
    private var pendingHomeKeyboard = false
    private var hasResumedOnce = false
    private val personalization by lazy { PersonalizationStore(this) }
    private val syncClient by lazy { FirebaseSyncClient(personalization) }

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        activeTab = state?.getInt("active_tab") ?: 0
        if (!prefs.getBoolean("appearance_v3", false)) {
            prefs.edit().putBoolean("appearance_v3", true).putString("theme", "system").apply()
        }
        SyncScheduler.ensureScheduled(this)
        render()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putInt("active_tab", activeTab)
        super.onSaveInstanceState(outState)
    }

    override fun onResume() {
        super.onResume()
        if (!hasResumedOnce) {
            hasResumedOnce = true
            return
        }
        if (prefs.getBoolean("onboarding_v2", false)) {
            render()
            if (pendingHomeKeyboard) {
                pendingHomeKeyboard = false
                homeTestField?.let { showHomeImeWithRetry(it, 0) }
            }
        } else onboardingView?.refreshExternalState()
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
        val lightBackground = !Ui(this).isDark
        controller.isAppearanceLightStatusBars = lightBackground
        controller.isAppearanceLightNavigationBars = lightBackground
    }

    private fun checkMic() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun keyboardEnabled(): Boolean {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        return imm.enabledInputMethodList.any { it.packageName == packageName && it.serviceName == VaaniKeyboardService::class.java.name }
    }

    private fun keyboardSelected(): Boolean = Settings.Secure.getString(
        contentResolver,
        Settings.Secure.DEFAULT_INPUT_METHOD,
    ) == android.content.ComponentName(this, VaaniKeyboardService::class.java).flattenToShortString()

    private fun recognizerAvailable() = android.speech.SpeechRecognizer.isOnDeviceRecognitionAvailable(this)

    private fun readiness() = AppReadiness(recognizerAvailable(), checkMic(), keyboardEnabled() && keyboardSelected(), prefs.getBoolean("first_dictation_complete", false))

    private fun render() {
        configureWindow(window)
        scrollY = activeScroll?.scrollY ?: scrollY
        homeTestField = null
        if (!prefs.getBoolean("onboarding_v2", false)) {
            val ui = Ui(this)
            val scroll = ScrollView(this).apply {
                clipToPadding = false
                isFillViewport = true
                setBackgroundColor(ui.paper)
            }
            onboardingView = OnboardingView(this, ::openImeSettings, ::showKeyboardPicker, ::requestMic) {
                prefs.edit().putBoolean("onboarding_v2", true).putInt("onboarding_step", 0).apply()
                render()
            }
            scroll.addView(onboardingView)
            installInsets(scroll)
            setContentView(scroll)
            return
        }
        onboardingView = null
        val ui = Ui(this)
        val frame = FrameLayout(this).apply { setBackgroundColor(ui.paper) }
        val content = ScrollView(this).apply { clipToPadding = false }
        val page = when (activeTab) {
            1 -> personalize(ui)
            2 -> settings(ui)
            else -> home(ui)
        }
        content.addView(page)
        val nav = bottomNav(ui)
        frame.addView(content, FrameLayout.LayoutParams(-1, -1).apply { bottomMargin = ui.dp(76) })
        frame.addView(nav, FrameLayout.LayoutParams(-1, ui.dp(76), Gravity.BOTTOM))
        ViewCompat.setOnApplyWindowInsetsListener(frame) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            content.setPadding(0, bars.top, 0, 0)
            content.layoutParams = (content.layoutParams as FrameLayout.LayoutParams).apply {
                bottomMargin = ui.dp(76) + bars.bottom
            }
            nav.layoutParams = (nav.layoutParams as FrameLayout.LayoutParams).apply {
                height = ui.dp(76) + bars.bottom
            }
            nav.setPadding(ui.dp(12), ui.dp(8), ui.dp(12), ui.dp(8) + bars.bottom)
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
        listOf("Home" to 0, "Personalize" to 1, "Settings" to 2).forEachIndexed { index, (label, tab) ->
            val button = ui.key(if (activeTab == tab) "✓  $label" else label) { selectTab(tab) }.apply {
                contentDescription = if (activeTab == tab) "$label, selected" else label
            }
            addView(button, LinearLayout.LayoutParams(0, ui.dp(52), 1f).apply {
                if (index > 0) marginStart = ui.dp(4)
                if (index < 2) marginEnd = ui.dp(4)
            })
        }
    }

    private fun selectTab(tab: Int) {
        activeTab = tab
        scrollY = 0
        render()
    }

    private fun home(ui: Ui): LinearLayout {
        val root = ui.screenColumn()
        root.addView(ui.meta("CONTROL CENTER"))
        root.addView(ui.title("Speak. Vaani types.", 30f))
        root.addView(ui.label("A private voice layer for every text field on your device.", 17f, ui.palette.muted))
        val ready = readiness()
        val status = ui.surfaceCard()
        val statusHeader = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        statusHeader.addView(
            ui.pill(
                if (ready.ready) ui.palette.ready else ui.palette.surfaceRaised,
                if (ready.ready) 0xffffffff.toInt() else ui.ink,
                if (ready.ready) "READY TO SPEAK" else "SETUP NEEDED",
            ),
            LinearLayout.LayoutParams(0, ui.dp(30), 1f),
        )
        statusHeader.addView(ui.meta(selectedLanguageName()), LinearLayout.LayoutParams(-2, -2).apply { marginStart = ui.dp(12) })
        status.addView(statusHeader)
        status.addView(ui.label(if (ready.ready) "Ready to dictate" else blockerTitle(ready.nextBlocker), 22f).apply { typeface = android.graphics.Typeface.DEFAULT_BOLD })
        status.addView(ui.label(if (ready.ready) "${selectedLanguageName()} · device speech · Vaani keyboard" else blockerBody(ready.nextBlocker), 14f, ui.palette.muted))
        if (ready.ready) {
            status.addView(ui.label("Hold Send while you speak. Release to place the text; Cancel keeps the field unchanged.", 14f, ui.palette.muted), LinearLayout.LayoutParams(-1, -2).apply { topMargin = ui.dp(10) })
        }
        val testField = if (ready.ready) EditText(this).apply {
            hint = "Dictate something here"
            textSize = 16f
            setTextColor(ui.ink)
            setHintTextColor(ui.palette.muted)
            background = ui.shape(ui.palette.surfaceRaised, ui.palette.line, 16)
            setPadding(ui.dp(14), ui.dp(10), ui.dp(14), ui.dp(10))
            contentDescription = "Vaani test dictation field"
        } else null
        homeTestField = testField
        if (testField != null) {
            status.addView(testField, LinearLayout.LayoutParams(-1, ui.dp(56)).apply { topMargin = ui.dp(12) })
        }
        val action = if (ready.ready) ui.primaryButton("Choose Vaani and dictate") {
            testField?.let { field ->
                pendingHomeKeyboard = true
                field.requestFocus()
                showHomeImeWithRetry(field, 0)
                field.postDelayed({
                    showKeyboardPicker()
                    field.postDelayed({ showHomeImeWithRetry(field, 0) }, 700L)
                }, 180L)
            }
        } else ui.primaryButton(blockerAction(ready.nextBlocker)) { runBlocker(ready.nextBlocker) }
        status.addView(action, LinearLayout.LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(12) })
        root.addView(status, LinearLayout.LayoutParams(-1, -2).apply { topMargin = ui.dp(20) })
        val flow = ui.surfaceCard()
        flow.addView(ui.label("The Vaani rhythm", 17f).apply { typeface = android.graphics.Typeface.DEFAULT_BOLD })
        flow.addView(ui.label("Five seconds from thought to text.", 14f, ui.palette.muted))
        val steps = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        listOf("01" to "Focus", "02" to "Hold Send", "03" to "Release").forEachIndexed { index, (number, label) ->
            val step = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                addView(ui.meta(number))
                addView(ui.label(label, 13f).apply { typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL) })
            }
            steps.addView(step, LinearLayout.LayoutParams(0, -2, 1f))
            if (index < 2) steps.addView(ui.label("→", 16f, ui.palette.accent), LinearLayout.LayoutParams(ui.dp(20), -2))
        }
        flow.addView(steps, LinearLayout.LayoutParams(-1, -2).apply { topMargin = ui.dp(12) })
        root.addView(flow, LinearLayout.LayoutParams(-1, -2).apply { topMargin = ui.dp(12) })
        root.addView(ui.sectionTitle("Quick status"))
        root.addView(statusRow(ui, "Speech service", if (ready.recognizerAvailable) "Available on this device" else "Unavailable"))
        root.addView(statusRow(ui, "Microphone", if (ready.microphoneGranted) "Allowed" else "Needs access"))
        root.addView(statusRow(ui, "Vaani keyboard", when {
            keyboardSelected() -> "Selected"
            keyboardEnabled() -> "Enabled; choose it"
            else -> "Not enabled"
        }))
        root.addView(ui.sectionTitle("Privacy"))
        root.addView(ui.label("Audio is used by the device speech recognizer during an active dictation and is not stored by this app. Network access is used only for optional account sync.", 14f, ui.palette.muted))
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
        root.addView(ui.meta("Language availability is provided by Android's installed on-device speech service and may vary by device."))
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
        root.addView(ui.sectionTitle("Personalization"))
        root.addView(ui.label("Vocabulary, snippets, and replacements are managed on their own screen and remain available offline.", 14f, ui.palette.muted))
        root.addView(ui.secondaryButton("Open Personalize") { selectTab(1) }, LinearLayout.LayoutParams(-1, ui.dp(48)).apply { topMargin = ui.dp(6) })
        addAccountSection(root, ui)
        root.addView(ui.sectionTitle("About"))
        root.addView(ui.meta("Vaani Android 0.1.0 · local-first dictation"))
        return root
    }

    private fun personalize(ui: Ui): LinearLayout {
        val root = ui.screenColumn()
        root.addView(ui.meta("YOUR VOICE, YOUR RULES"))
        root.addView(ui.title("Personalize"))
        root.addView(ui.label("Teach Vaani the words and shortcuts that make your writing yours.", 16f, ui.palette.muted))
        root.addView(ui.label("These rules stay on this device and run before insertion. Word boundaries prevent accidental edits inside larger words.", 14f, ui.palette.muted), LinearLayout.LayoutParams(-1, -2).apply { topMargin = ui.dp(16) })
        root.addView(ui.sectionTitle("Build your dictionary"))
        addPersonalizationEditor(root, ui, "Vocabulary term", "Spoken aliases (comma-separated)", "Add vocabulary") { term, aliases ->
            personalization.addVocabulary(term, aliases.split(',').map(String::trim))
        }
        addPersonalizationEditor(root, ui, "Spoken shortcut", "Expansion", "Add snippet") { trigger, value -> personalization.addSnippet(trigger, value) }
        addPersonalizationEditor(root, ui, "Replace", "With", "Add replacement") { trigger, value -> personalization.addReplacement(trigger, value) }
        addPersonalizationRows(root, ui, "Vocabulary", personalization.vocabulary(), PersonalizationStore.Kind.VOCABULARY)
        addPersonalizationRows(root, ui, "Snippets", personalization.snippets(), PersonalizationStore.Kind.SNIPPET)
        addPersonalizationRows(root, ui, "Replacements", personalization.replacements(), PersonalizationStore.Kind.REPLACEMENT)
        root.addView(ui.sectionTitle("Sync"))
        root.addView(ui.label("Optional sync is available in Settings. Your local rules work without an account.", 14f, ui.palette.muted))
        root.addView(ui.secondaryButton("Open Settings") { selectTab(2) }, LinearLayout.LayoutParams(-1, ui.dp(48)).apply { topMargin = ui.dp(6) })
        return root
    }

    private fun addAccountSection(root: LinearLayout, ui: Ui) {
        root.addView(ui.sectionTitle("Optional sync"))
        root.addView(ui.label("Vaani works fully offline. Sign in only if you want vocabulary, snippets, and replacements on another device; audio and dictations are never synced.", 14f, ui.palette.muted))
        val email = EditText(this).apply {
            hint = "Email"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
            setSingleLine(true)
        }
        val password = EditText(this).apply {
            hint = "Password"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setSingleLine(true)
        }
        root.addView(email, LinearLayout.LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(8) })
        root.addView(password, LinearLayout.LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(6) })
        val status = ui.meta(syncClient.email()?.let { "Signed in as $it" } ?: "Not signed in")
        root.addView(status, LinearLayout.LayoutParams(-1, -2).apply { topMargin = ui.dp(8) })
        root.addView(ui.primaryButton("Sign in") {
            syncClient.signIn(email.text.toString(), password.text.toString()) { result ->
                status.text = if (result.isSuccess) "Signed in — personalization is ready to sync" else "Sign-in failed; check your details or connection"
                if (result.isSuccess) { SyncScheduler.ensureScheduled(this); render() }
            }
        }, LinearLayout.LayoutParams(-1, ui.dp(48)).apply { topMargin = ui.dp(6) })
        root.addView(ui.secondaryButton("Create account") {
            syncClient.createAccount(email.text.toString(), password.text.toString()) { result ->
                status.text = if (result.isSuccess) "Account created — personalization is ready to sync" else "Could not create account; check your details"
                if (result.isSuccess) { SyncScheduler.ensureScheduled(this); render() }
            }
        }, LinearLayout.LayoutParams(-1, ui.dp(48)).apply { topMargin = ui.dp(6) })
        root.addView(ui.secondaryButton("Sync personalization now") {
            syncClient.sync { result ->
                status.text = result.fold(
                    onSuccess = { "Synced ${it.uploaded} local records; merged ${it.downloaded} remote records" },
                    onFailure = { "Sync unavailable; local personalization is unchanged" },
                )
            }
        }, LinearLayout.LayoutParams(-1, ui.dp(48)).apply { topMargin = ui.dp(6) })
        if (syncClient.email() != null) root.addView(ui.secondaryButton("Sign out") { syncClient.signOut(); SyncScheduler.cancel(this); render() }, LinearLayout.LayoutParams(-1, ui.dp(48)).apply { topMargin = ui.dp(6) })
    }

    private fun addPersonalizationEditor(
        root: LinearLayout,
        ui: Ui,
        firstHint: String,
        secondHint: String,
        buttonText: String = secondHint,
        save: (String, String) -> Boolean,
    ) {
        val first = EditText(this).apply { hint = firstHint; textSize = 16f; setSingleLine(true) }
        val second = if (buttonText == secondHint) null else EditText(this).apply { hint = secondHint; textSize = 16f; setSingleLine(true) }
        val card = ui.surfaceCard()
        val sectionLabel = when (buttonText) {
            "Add vocabulary" -> "Names and terms"
            "Add snippet" -> "Shortcuts that expand"
            else -> "Words to replace"
        }
        val helper = when (buttonText) {
            "Add vocabulary" -> "Give the recognizer a reliable spelling for a name or product term."
            "Add snippet" -> "Say a short trigger and insert a longer phrase."
            else -> "Keep a predictable correction local to this device."
        }
        card.addView(ui.label(sectionLabel, 17f).apply { typeface = android.graphics.Typeface.DEFAULT_BOLD })
        card.addView(ui.meta(helper))
        listOfNotNull(first, second).forEach { field ->
            field.setTextColor(ui.ink)
            field.setHintTextColor(ui.palette.muted)
            field.background = ui.shape(ui.palette.surfaceRaised, ui.palette.line, 12)
            field.setPadding(ui.dp(12), ui.dp(8), ui.dp(12), ui.dp(8))
            card.addView(field, LinearLayout.LayoutParams(-1, ui.dp(52)).apply { topMargin = ui.dp(10) })
        }
        card.addView(ui.secondaryButton(buttonText) {
            if (save(first.text.toString(), second?.text?.toString().orEmpty())) render()
            else first.error = "Enter a value up to 500 characters"
        }, LinearLayout.LayoutParams(-1, ui.dp(48)).apply { topMargin = ui.dp(10) })
        root.addView(card, LinearLayout.LayoutParams(-1, -2).apply { topMargin = ui.dp(10) })
    }

    private fun addPersonalizationRows(root: LinearLayout, ui: Ui, title: String, entries: List<PersonalizationEntry>, kind: PersonalizationStore.Kind) {
        if (entries.isEmpty()) return
        root.addView(ui.label(title, 15f).apply { typeface = android.graphics.Typeface.DEFAULT_BOLD; setPadding(0, ui.dp(14), 0, ui.dp(4)) })
        entries.forEach { entry ->
            val row = LinearLayout(this).apply { gravity = android.view.Gravity.CENTER_VERTICAL }
            val label = if (entry.value.isEmpty()) entry.trigger else "${entry.trigger}  →  ${entry.value}"
            row.addView(ui.label(label, 14f), LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(ui.secondaryButton("Remove") { personalization.remove(kind, entry.id); render() }, LinearLayout.LayoutParams(ui.dp(96), ui.dp(44)))
            root.addView(row)
        }
    }

    private fun blockerTitle(blocker: ReadinessBlocker?) = when (blocker) {
        ReadinessBlocker.RECOGNIZER -> "Device speech is unavailable"
        ReadinessBlocker.MICROPHONE -> "Microphone access is off"
        ReadinessBlocker.KEYBOARD -> "Enable the Vaani keyboard"
        ReadinessBlocker.TEST -> "Complete one test dictation"
        null -> "Ready"
    }

    private fun selectedLanguageName() = when (prefs.getString("language", "en-IN")) {
        "hi-IN" -> "हिन्दी"
        "bn-IN" -> "বাংলা"
        else -> "English (India)"
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
        ReadinessBlocker.MICROPHONE -> if (microphoneNeedsSettings()) "Open app settings" else "Allow microphone"
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

    /** Android may drop focus while the IME picker is being dismissed. */
    private fun showHomeImeWithRetry(field: EditText, attempt: Int) {
        field.postDelayed({
            if (field !== homeTestField || !field.isAttachedToWindow) return@postDelayed
            if (!field.hasWindowFocus()) {
                if (attempt < 5) showHomeImeWithRetry(field, attempt + 1)
                return@postDelayed
            }
            field.requestFocus()
            ViewCompat.getWindowInsetsController(field)?.show(WindowInsetsCompat.Type.ime())
            val imm = getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
            if (!imm.showSoftInput(field, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT) && attempt < 5) {
                showHomeImeWithRetry(field, attempt + 1)
            }
        }, if (attempt == 0) 120L else 260L)
    }

    private fun microphoneNeedsSettings() = MicrophonePermissionPolicy.requiresAppSettings(
        prefs.getBoolean("microphone_requested", false),
        checkMic(),
        shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO),
    )

    private fun requestMic() {
        if (checkMic()) {
            render()
        } else if (microphoneNeedsSettings()) {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.parse("package:$packageName")
            })
        } else {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_MIC)
        }
    }

    companion object { private const val REQUEST_MIC = 42 }
}
