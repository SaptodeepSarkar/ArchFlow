package org.vaani.keyboard

import android.Manifest
import android.animation.ValueAnimator
import android.content.Context
import android.content.SharedPreferences
import android.content.res.Configuration
import android.graphics.Typeface
import android.provider.Settings
import android.view.Gravity
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.SizeTransform
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.res.vectorResource
import androidx.compose.ui.graphics.Color.Companion.Transparent
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

private val VaaniBackground = Color(0xFF091410)
private val VaaniSurface = Color(0xFF112019)
private val VaaniElevated = Color(0xFF172A22)
private val VaaniBorder = Color(0xFF2A4035)
private val VaaniText = Color(0xFFF5F0E6)
private val VaaniMuted = Color(0xFFACB9AF)
private val VaaniAmber = Color(0xFFF0B45E)
private val VaaniAmberPressed = Color(0xFFD69643)
private val VaaniSuccess = Color(0xFF8FC7A4)

private val VaaniColors: ColorScheme = darkColorScheme(
    primary = VaaniAmber,
    onPrimary = VaaniBackground,
    secondary = VaaniSuccess,
    onSecondary = VaaniBackground,
    background = VaaniBackground,
    onBackground = VaaniText,
    surface = VaaniSurface,
    onSurface = VaaniText,
    surfaceVariant = VaaniElevated,
    onSurfaceVariant = VaaniMuted,
    outline = VaaniBorder,
)

/** Compose Material 3 onboarding surface. System intents and preference state stay in MainActivity. */
class OnboardingComposeView(
    context: Context,
    private val enableKeyboard: () -> Unit,
    private val chooseKeyboard: () -> Unit,
    private val requestMicrophone: () -> Unit,
    private val openAppSettings: () -> Unit,
    private val done: () -> Unit,
) : android.widget.FrameLayout(context), SharedPreferences.OnSharedPreferenceChangeListener {
    private val prefs = context.getSharedPreferences("vaani", Context.MODE_PRIVATE)
    private var page by mutableIntStateOf(prefs.getInt("onboarding_step", 0).coerceIn(0, 3))
    private var refreshToken by mutableIntStateOf(0)
    private var permissionRequesting by mutableStateOf(false)
    private var rehearsalField: EditText? = null
    private val composeView = ComposeView(context)

    init {
        composeView.setViewCompositionStrategy(androidx.compose.ui.platform.ViewCompositionStrategy.DisposeOnDetachedFromWindow)
        addView(composeView, LayoutParams(-1, -1))
        composeView.setContent {
            VaaniTheme {
                val refresh = refreshToken
                if (refresh < 0) return@VaaniTheme
                OnboardingScaffold(
                    page = page,
                    microphoneReady = hasMicrophone(),
                    microphoneDenied = microphoneWasDenied(),
                    microphoneRequesting = permissionRequesting,
                    keyboardEnabled = keyboardEnabled(),
                    keyboardSelected = keyboardSelected(),
                    rehearsalComplete = prefs.getBoolean("first_dictation_complete", false),
                    dictationStatus = prefs.getString("dictation_ui_state", "hidden") ?: "hidden",
                    onContinue = ::next,
                    onBack = ::previous,
                    onRequestMicrophone = {
                        permissionRequesting = true
                        requestMicrophone()
                    },
                    onOpenAppSettings = openAppSettings,
                    onEnableKeyboard = enableKeyboard,
                    onChooseKeyboard = chooseKeyboard,
                    onShowKeyboard = ::openKeyboardForTest,
                    onFieldReady = { rehearsalField = it },
                    onFinish = done,
                )
            }
        }
        prefs.registerOnSharedPreferenceChangeListener(this)
    }

    override fun onDetachedFromWindow() {
        prefs.unregisterOnSharedPreferenceChangeListener(this)
        rehearsalField = null
        super.onDetachedFromWindow()
    }

    override fun onSharedPreferenceChanged(sharedPreferences: SharedPreferences?, key: String?) {
        if (key == "first_dictation_complete" || key == "microphone_granted" || key == "microphone_requested" || key == "dictation_ui_state") {
            post { permissionRequesting = false; refreshToken++ }
        }
    }

    fun refreshExternalState() {
        permissionRequesting = false
        refreshToken++
        if (page == 3) showRehearsalKeyboardIfReady()
    }

    fun showRehearsalKeyboardIfReady() {
        if (page != 3 || !keyboardSelected() || prefs.getBoolean("first_dictation_complete", false)) return
        val field = rehearsalField ?: return
        field.postDelayed({
            if (field.isAttachedToWindow) requestRehearsalIme(field, 0)
        }, 180L)
    }

    private fun requestRehearsalIme(field: EditText, attempt: Int) {
        field.postDelayed({
            if (!field.isAttachedToWindow) return@postDelayed
            if (!field.hasWindowFocus()) {
                if (attempt < 5) requestRehearsalIme(field, attempt + 1) else chooseKeyboard()
                return@postDelayed
            }
            val imm = context.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
            imm.restartInput(field)
            field.requestFocus()
            (context as? android.app.Activity)?.window?.setSoftInputMode(
                WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE or WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE,
            )
            ViewCompat.getWindowInsetsController(field)?.show(WindowInsetsCompat.Type.ime())
            if (!imm.showSoftInput(field, InputMethodManager.SHOW_IMPLICIT) && attempt < 5) requestRehearsalIme(field, attempt + 1)
        }, if (attempt == 0) 120L else 260L)
    }

    private fun next() {
        when (page) {
            0 -> moveTo(1)
            1 -> if (hasMicrophone()) moveTo(2) else requestMicrophone()
            2 -> when {
                !keyboardEnabled() -> enableKeyboard()
                !keyboardSelected() -> chooseKeyboard()
                else -> moveTo(3)
            }
            3 -> if (prefs.getBoolean("first_dictation_complete", false)) done() else openKeyboardForTest()
        }
    }

    private fun previous() {
        if (page > 0) moveTo(page - 1)
    }

    private fun moveTo(nextPage: Int) {
        page = nextPage.coerceIn(0, 3)
        prefs.edit().putInt("onboarding_step", page).apply()
    }

    private fun hasMicrophone() = context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED

    private fun microphoneWasDenied() = prefs.getBoolean("microphone_requested", false) && !hasMicrophone()

    private fun keyboardEnabled() = (context.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager)
        .enabledInputMethodList.any { it.packageName == context.packageName && it.serviceName == VaaniKeyboardService::class.java.name }

    private fun keyboardSelected(): Boolean {
        val selected = Settings.Secure.getString(context.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        return InputMethodSelection.matches(selected, context.packageName, VaaniKeyboardService::class.java.name)
    }

    private fun openKeyboardForTest() {
        val field = rehearsalField ?: return
        when {
            keyboardSelected() -> showRehearsalKeyboardIfReady()
            keyboardEnabled() -> { field.requestFocus(); postDelayed(chooseKeyboard, 180L) }
            else -> { field.requestFocus(); postDelayed(enableKeyboard, 180L) }
        }
    }
}

@Composable
private fun VaaniTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = VaaniColors, content = content)
}

@Composable
private fun OnboardingScaffold(
    page: Int,
    microphoneReady: Boolean,
    microphoneDenied: Boolean,
    microphoneRequesting: Boolean,
    keyboardEnabled: Boolean,
    keyboardSelected: Boolean,
    rehearsalComplete: Boolean,
    dictationStatus: String,
    onContinue: () -> Unit,
    onBack: () -> Unit,
    onRequestMicrophone: () -> Unit,
    onOpenAppSettings: () -> Unit,
    onEnableKeyboard: () -> Unit,
    onChooseKeyboard: () -> Unit,
    onShowKeyboard: () -> Unit,
    onFieldReady: (EditText) -> Unit,
    onFinish: () -> Unit,
) {
    val compact = LocalView.current.resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
    val scroll = rememberScrollState()
    Surface(modifier = Modifier.fillMaxSize(), color = VaaniBackground) {
        Column(
            modifier = Modifier.fillMaxSize().padding(horizontal = if (compact) 22.dp else 24.dp),
        ) {
            Header(page = page, compact = compact)
            StepProgress(page)
            Column(
                modifier = Modifier.weight(1f).verticalScroll(scroll),
                verticalArrangement = Arrangement.spacedBy(if (compact) 10.dp else 14.dp),
            ) {
                AnimatedContent(
                    targetState = page,
                    transitionSpec = {
                        (slideInHorizontally { it / 8 } + fadeIn()).togetherWith(slideOutHorizontally { -it / 8 } + fadeOut()) using SizeTransform(clip = false)
                    },
                    label = "onboarding step",
                ) { step ->
                    when (step) {
                        0 -> WelcomeStep(compact)
                        1 -> MicrophoneStep(microphoneReady, microphoneDenied, microphoneRequesting, onRequestMicrophone, onOpenAppSettings, compact)
                        2 -> KeyboardStep(keyboardEnabled, keyboardSelected, onEnableKeyboard, onChooseKeyboard, onShowKeyboard, compact)
                        else -> RehearsalStep(rehearsalComplete, dictationStatus, keyboardEnabled, keyboardSelected, onShowKeyboard, onFieldReady, compact)
                    }
                }
                Spacer(Modifier.height(if (compact) 4.dp else 12.dp))
            }
            BottomActionArea(
                page = page,
                microphoneReady = microphoneReady,
                microphoneRequesting = microphoneRequesting,
                keyboardEnabled = keyboardEnabled,
                keyboardSelected = keyboardSelected,
                rehearsalComplete = rehearsalComplete,
                onContinue = onContinue,
                onBack = onBack,
                onFinish = onFinish,
            )
        }
    }
}

@Composable
private fun Header(page: Int, compact: Boolean) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = if (compact) 12.dp else 22.dp, bottom = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        VaaniLogo()
        Text("Vaani", modifier = Modifier.padding(start = 12.dp), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.weight(1f))
        Text("${page + 1} of 4", style = MaterialTheme.typography.labelLarge, color = VaaniMuted)
    }
}

@Composable
private fun VaaniLogo() {
    val reducedMotion = !ValueAnimator.areAnimatorsEnabled()
    var visible by remember { mutableStateOf(reducedMotion) }
    LaunchedEffect(Unit) {
        if (!reducedMotion) {
            kotlinx.coroutines.delay(40)
            visible = true
        }
    }
    val alpha = if (visible) 1f else 0f
    Canvas(Modifier.size(48.dp).scale(if (visible) 1f else .96f).semantics { contentDescription = "Vaani logo" }) {
        val center = Offset(size.width / 2f, size.height / 2f)
        drawCircle(VaaniAmber.copy(alpha = .12f * alpha), radius = size.minDimension * .45f, center = center)
        drawArc(VaaniAmber.copy(alpha = alpha), -92f, if (visible) 300f else 0f, false, style = Stroke(1.5.dp.toPx(), cap = StrokeCap.Round))
        drawCircle(Brush.radialGradient(listOf(Color(0xFFFFDEA0), VaaniAmber, Color(0xFF5B7A62))), size.minDimension * .29f, center)
        drawLine(VaaniText.copy(alpha = alpha), Offset(size.width * .40f, size.height * .38f), Offset(size.width * .50f, size.height * .66f), 2.dp.toPx(), StrokeCap.Round)
        drawLine(VaaniText.copy(alpha = alpha), Offset(size.width * .60f, size.height * .38f), Offset(size.width * .50f, size.height * .66f), 2.dp.toPx(), StrokeCap.Round)
    }
}

@Composable
private fun StepProgress(page: Int) {
    Row(Modifier.fillMaxWidth().padding(bottom = 18.dp), verticalAlignment = Alignment.CenterVertically) {
        repeat(4) { index ->
            Box(Modifier.weight(1f).height(4.dp).background(if (index <= page) VaaniAmber else VaaniBorder, RoundedCornerShape(2.dp)))
            if (index < 3) Spacer(Modifier.width(5.dp))
        }
    }
}

@Composable
private fun WelcomeStep(compact: Boolean) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Typing less\nis the point.", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.SemiBold, lineHeight = 42.sp)
        Text("A calm voice layer for the text fields you already use. Vaani keeps the final say with you.", style = MaterialTheme.typography.bodyLarge, color = VaaniMuted, lineHeight = 25.sp)
        VoiceOrb(Modifier.fillMaxWidth().height(if (compact) 150.dp else 205.dp), stage = 0)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            InfoChip("Local-first")
            InfoChip("Never auto-sends")
        }
        InteractiveCard {
            Text("A small, private rhythm", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text("Focus a field. Hold Send. Release when the thought is complete.", color = VaaniMuted, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun MicrophoneStep(
    ready: Boolean,
    denied: Boolean,
    requesting: Boolean,
    request: () -> Unit,
    settings: () -> Unit,
    compact: Boolean,
) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Your voice stays\nin the room.", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.SemiBold, lineHeight = 42.sp)
        Text("Microphone access is used only while you hold Send. Vaani does not save recordings or send dictations to its servers.", style = MaterialTheme.typography.bodyLarge, color = VaaniMuted, lineHeight = 25.sp)
        InteractiveCard {
            WaveformIllustration(active = ready, modifier = Modifier.fillMaxWidth().height(if (compact) 82.dp else 108.dp))
            PermissionStatus(ready = ready, denied = denied)
        }
        if (denied) {
            InteractiveCard {
                Text("Microphone access is still off", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Text("Allow it in Android settings, then return here to continue.", color = VaaniMuted, style = MaterialTheme.typography.bodyMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SecondaryButton("Try again", request, Modifier.weight(1f))
                    SecondaryButton("Open settings", settings, Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun KeyboardStep(
    enabled: Boolean,
    selected: Boolean,
    enable: () -> Unit,
    choose: () -> Unit,
    tryIt: () -> Unit,
    compact: Boolean,
) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Android has\none small form.", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.SemiBold, lineHeight = 42.sp)
        Text("Vaani adds a keyboard; it does not replace your usual one. You can switch keyboards anytime.", style = MaterialTheme.typography.bodyLarge, color = VaaniMuted, lineHeight = 25.sp)
        InteractiveCard {
            KeyboardStepper(enabled, selected, enable, choose, tryIt)
        }
        InfoChip("Your usual keyboard stays available")
    }
}

@Composable
private fun KeyboardStepper(enabled: Boolean, selected: Boolean, enable: () -> Unit, choose: () -> Unit, tryIt: () -> Unit) {
    val active = when { !enabled -> 0; !selected -> 1; else -> 2 }
    val labels = listOf("Enable" to "Allow Vaani in Android settings", "Choose" to "Select Vaani from the system picker", "Try it" to "Return here and rehearse safely")
    labels.forEachIndexed { index, (title, body) ->
        Row(verticalAlignment = Alignment.Top) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Box(Modifier.size(30.dp).background(if (index < active) VaaniSuccess else if (index == active) VaaniAmber else VaaniElevated, RoundedCornerShape(15.dp)), contentAlignment = Alignment.Center) {
                    Text(if (index < active) "✓" else "${index + 1}", color = if (index <= active) VaaniBackground else VaaniMuted, fontWeight = FontWeight.Bold)
                }
                if (index < 2) Box(Modifier.width(1.dp).height(38.dp).background(if (index < active) VaaniSuccess else VaaniBorder))
            }
            Column(Modifier.padding(start = 12.dp, bottom = if (index < 2) 8.dp else 0.dp)) {
                Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = if (index == active) VaaniText else VaaniMuted)
                Text(body, style = MaterialTheme.typography.bodySmall, color = VaaniMuted)
                if (index == active) {
                    val action = when (index) { 0 -> "Enable Vaani keyboard"; 1 -> "Choose Vaani keyboard"; else -> "Try Vaani" }
                    SecondaryButton(action, if (index == 0) enable else if (index == 1) choose else tryIt, Modifier.padding(top = 8.dp))
                }
            }
        }
    }
}

@Composable
private fun RehearsalStep(
    complete: Boolean,
    dictationStatus: String,
    enabled: Boolean,
    selected: Boolean,
    showKeyboard: () -> Unit,
    onFieldReady: (EditText) -> Unit,
    compact: Boolean,
) {
    var fieldText by remember { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("A three-second\nrehearsal.", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.SemiBold, lineHeight = 42.sp)
        Text("Try the complete hold → speak → release path. Text is inserted, never auto-sent.", style = MaterialTheme.typography.bodyLarge, color = VaaniMuted, lineHeight = 25.sp)
        InteractiveCard {
            if (!enabled || !selected) {
                Text("One last keyboard step", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Text(if (!enabled) "Enable Vaani to bring the rehearsal field to life." else "Choose Vaani from the system picker, then return here.", style = MaterialTheme.typography.bodyMedium, color = VaaniMuted)
            }
            AndroidView(
                modifier = Modifier.fillMaxWidth().height(if (compact) 58.dp else 64.dp).semantics { contentDescription = "Test dictation field" },
                factory = { context ->
                    EditText(context).apply {
                        hint = "Your dictated text will appear here"
                        textSize = 16f
                        setTextColor(android.graphics.Color.WHITE)
                        setHintTextColor(android.graphics.Color.rgb(172, 185, 175))
                        setSingleLine(false)
                        setPadding(16, 12, 16, 12)
                        contentDescription = "Test dictation field"
                        onFieldReady(this)
                    }
                },
                update = { editText ->
                    onFieldReady(editText)
                    editText.setOnKeyListener { _, _, _ -> fieldText = editText.text.toString(); false }
                },
            )
            SecondaryButton(if (complete) "Try again" else if (selected) "Show Vaani keyboard" else "Choose Vaani keyboard", showKeyboard, Modifier.fillMaxWidth())
            when {
                complete -> {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("✓", color = VaaniSuccess, fontWeight = FontWeight.Bold, fontSize = 20.sp)
                    Text("Rehearsal complete. Your words stay under your control.", style = MaterialTheme.typography.bodyMedium, color = VaaniSuccess)
                }
                }
                dictationStatus == "starting" || dictationStatus == "listening" -> Text("Listening… release Send when you are done.", style = MaterialTheme.typography.bodySmall, color = VaaniAmber)
                dictationStatus == "processing" -> Text("Turning your voice into text…", style = MaterialTheme.typography.bodySmall, color = VaaniAmber)
                dictationStatus == "failure" -> Text("Couldn’t complete that rehearsal. Try again.", style = MaterialTheme.typography.bodySmall, color = VaaniAmber)
                else -> Text("Hold Send while speaking; release to insert.", style = MaterialTheme.typography.bodySmall, color = VaaniMuted)
            }
        }
    }
}

@Composable
private fun BottomActionArea(
    page: Int,
    microphoneReady: Boolean,
    microphoneRequesting: Boolean,
    keyboardEnabled: Boolean,
    keyboardSelected: Boolean,
    rehearsalComplete: Boolean,
    onContinue: () -> Unit,
    onBack: () -> Unit,
    onFinish: () -> Unit,
) {
    val label = when {
        page == 3 -> "Finish setup"
        page == 1 && !microphoneReady -> "Allow microphone"
        else -> "Continue"
    }
    val finishEnabled = page != 3 || rehearsalComplete
    Column(Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        PrimaryButton(
            label = label,
            onClick = if (page == 3) onFinish else onContinue,
            modifier = Modifier.fillMaxWidth(),
            loading = microphoneRequesting,
            enabled = finishEnabled,
        )
        if (page == 3 && !rehearsalComplete) {
            Text("Complete the rehearsal above to unlock Finish setup.", Modifier.fillMaxWidth(), style = MaterialTheme.typography.labelMedium, color = VaaniMuted, textAlign = TextAlign.Center)
        }
        if (page > 0) SecondaryButton("Back", onBack, Modifier.fillMaxWidth())
    }
}

@Composable
private fun PrimaryButton(label: String, onClick: () -> Unit, modifier: Modifier = Modifier, loading: Boolean = false, enabled: Boolean = true) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    Button(
        onClick = onClick,
        enabled = enabled && !loading,
        interactionSource = interaction,
        modifier = modifier.height(54.dp).scale(if (pressed) .985f else 1f),
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(containerColor = VaaniAmber, contentColor = VaaniBackground, disabledContainerColor = VaaniAmber.copy(alpha = .45f)),
    ) {
        if (loading) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = VaaniBackground) else Text(label, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun SecondaryButton(label: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    OutlinedButton(onClick, modifier.height(48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, VaaniBorder), colors = ButtonDefaults.outlinedButtonColors(contentColor = VaaniText)) { Text(label) }
}

@Composable
private fun InfoChip(label: String) {
    Surface(color = VaaniElevated, shape = RoundedCornerShape(50), modifier = Modifier.semantics { contentDescription = label }) { Text(label, Modifier.padding(horizontal = 12.dp, vertical = 7.dp), style = MaterialTheme.typography.labelMedium, color = VaaniMuted) }
}

@Composable
private fun InteractiveCard(content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxWidth().background(VaaniSurface, RoundedCornerShape(16.dp)).border(1.dp, VaaniBorder, RoundedCornerShape(16.dp)).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp), content = content)
}

@Composable
private fun PermissionStatus(ready: Boolean, denied: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.size(9.dp).background(if (ready) VaaniSuccess else VaaniAmber, RoundedCornerShape(5.dp)))
        Text(if (ready) "Microphone ready" else if (denied) "Permission needed" else "Permission not requested", style = MaterialTheme.typography.labelLarge, color = if (ready) VaaniSuccess else VaaniMuted)
    }
}

@Composable
private fun VoiceOrb(modifier: Modifier, stage: Int) {
    Canvas(modifier.semantics { contentDescription = "Vaani voice orb" }) {
        val center = Offset(size.width / 2f, size.height / 2f)
        val radius = minOf(size.width, size.height) * .30f
        drawOval(Color.Black.copy(alpha = .28f), topLeft = Offset(center.x - radius * .72f, center.y + radius * .8f), size = Size(radius * 1.44f, radius * .28f))
        drawCircle(Brush.radialGradient(listOf(Color(0xFFFFE3A8), VaaniAmber, Color(0xFF45624E))), radius, center)
        drawArc(VaaniAmber, -85f, 110f, false, topLeft = Offset(center.x - radius - 6.dp.toPx(), center.y - radius - 6.dp.toPx()), size = Size((radius + 6.dp.toPx()) * 2, (radius + 6.dp.toPx()) * 2), style = Stroke(2.dp.toPx(), cap = StrokeCap.Round))
        drawArc(VaaniSuccess, 110f, 65f, false, topLeft = Offset(center.x - radius - 10.dp.toPx(), center.y - radius - 10.dp.toPx()), size = Size((radius + 10.dp.toPx()) * 2, (radius + 10.dp.toPx()) * 2), style = Stroke(1.dp.toPx(), cap = StrokeCap.Round))
        drawLine(VaaniText, Offset(center.x - radius * .24f, center.y - radius * .26f), Offset(center.x, center.y + radius * .42f), 4.dp.toPx(), StrokeCap.Round)
        drawLine(VaaniText, Offset(center.x + radius * .24f, center.y - radius * .26f), Offset(center.x, center.y + radius * .42f), 4.dp.toPx(), StrokeCap.Round)
    }
}

@Composable
private fun WaveformIllustration(active: Boolean, modifier: Modifier) {
    val heights = listOf(.26f, .48f, .34f, .72f, .43f, .84f, .38f, .60f, .30f, .50f, .25f)
    Canvas(modifier.semantics { contentDescription = if (active) "Microphone ready waveform" else "Microphone access waveform" }) {
        val gap = size.width / (heights.size * 1.7f)
        heights.forEachIndexed { index, height ->
            val bar = size.width / (heights.size * 2.8f)
            val x = gap * (index + .4f)
            val h = size.height * height
            drawRoundRect(if (active) VaaniSuccess else VaaniAmber.copy(alpha = .72f), Offset(x, (size.height - h) / 2), Size(bar, h), CornerRadius(bar / 2, bar / 2))
        }
    }
}
