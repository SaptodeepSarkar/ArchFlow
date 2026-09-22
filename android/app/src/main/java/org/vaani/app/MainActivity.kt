package org.vaani.app

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Build
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutLinearInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.BorderStroke
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.work.WorkManager
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.Observer
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        applyImmersiveMode()
        setContent { VaaniTheme { VaaniApp() } }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) applyImmersiveMode()
    }

    private fun applyImmersiveMode() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsetsCompat.Type.systemBars())
        }
    }
}

@Composable
private fun VaaniApp() {
    val context = LocalContext.current
    var page by remember { mutableIntStateOf(if (OnboardingState.isCompleted(context)) 17 else 0) }
    var overlayEnabled by remember { mutableStateOf(false) }
    val accountClient = remember { VaaniAccountClient(context) }
    val accountScope = rememberCoroutineScope()
    var accountMessage by remember { mutableStateOf<String?>(null) }
    fun beginModelPreparation() {
        ModelRelease.enqueue(context)
        page = 4
    }
    var micGranted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
    }
    val micPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        micGranted = it
        if (it) page = 9
    }
    val notificationPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        page = 14
    }
    when (page) {
        0 -> ProductIntroScreen(0, "The thought.\nWritten.", R.drawable.onboarding_v2_arrival) { page = 1 }
        1 -> ProductIntroScreen(1, "Your voice,\nyour language.", R.drawable.onboarding_v2_language) { page = 2 }
        2 -> ProductIntroScreen(2, "Wherever you\nwrite.", R.drawable.onboarding_v2_everywhere) { page = 3 }
        3 -> AccountGateScreen(
            message = accountMessage,
            onSkip = ::beginModelPreparation,
            onEmail = { email, password, create -> accountScope.launch {
                val result = if (create) accountClient.signUp(email, password) else accountClient.signIn(email, password)
                result.onSuccess { beginModelPreparation() }
                    .onFailure { accountMessage = it.message ?: "That account could not be opened." }
            } },
            onGoogle = { activity -> accountScope.launch {
                accountClient.signInWithGoogle(activity).onSuccess { beginModelPreparation() }
                    .onFailure { accountMessage = it.message ?: "Google sign-in could not be completed." }
            } },
        )
        4 -> ClearWordsScreen(onNext = { page = 5 })
        5 -> HowVaaniWorksScreen(onNext = { page = 6 })
        6 -> InFieldLessonScreen(onNext = { page = 7 })
        7 -> WritingLanguageScreen(onNext = { page = 8 })
        8 -> HoldToSpeakScreen(onNext = {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                micPermission.launch(Manifest.permission.RECORD_AUDIO)
            } else {
                page = 9
            }
        })
        9 -> FinishedTextScreen(onNext = { page = 10 })
        10 -> StepsOutScreen(onNext = { page = 11 })
        11 -> TextBoxAccessScreen(
            onOpenAccessibility = {
                context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)); page = 12
            },
            onSkip = { page = 12 },
        )
        12 -> PrivateByDefaultScreen(onNext = { page = 13 })
        13 -> ReadinessScreen(onNext = {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(context)) {
                context.startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${context.packageName}")))
            }
            page = 14
        })
        14 -> NotificationValueScreen(
            onNext = {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                    ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                ) {
                    notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                } else page = 15
            },
            onSkip = { page = 15 },
        )
        15 -> DiscoveryScreen(onNext = { page = 16 })
        16 -> ModelPreparationScreen(onReady = {
            OnboardingState.markCompleted(context)
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context)) {
                context.startService(Intent(context, VoiceOverlayService::class.java))
            }
            page = 17
        })
        else -> VaaniWorkspace(
            overlayEnabled = overlayEnabled,
            onToggleOverlay = {
                if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    micPermission.launch(Manifest.permission.RECORD_AUDIO)
                } else if (!AccessibilityBridge.isTextBoxAccessEnabled(context)) {
                    context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(context)) {
                    context.startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${context.packageName}")))
                } else {
                    context.startService(Intent(context, VoiceOverlayService::class.java))
                    overlayEnabled = true
                }
            },
        )
    }
}

@Composable
private fun ProductIntroScreen(step: Int, title: String, art: Int, onNext: () -> Unit) {
    Box(Modifier.fillMaxSize().background(VaaniColor.Ink)) {
        Image(
            painter = painterResource(art), contentDescription = null,
            modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop,
        )
        Box(
            Modifier.fillMaxSize().background(
                Brush.verticalGradient(
                    listOf(
                        VaaniColor.Ink.copy(alpha = 0.12f),
                        Color.Transparent,
                        VaaniColor.Ink.copy(alpha = 0.14f),
                    ),
                ),
            ),
        )
        Column(
            Modifier.fillMaxSize().imePadding().padding(horizontal = 28.dp, vertical = 40.dp),
        ) {
            // Keep navigation anchors visible on short screens and at large
            // font scales. Only the illustration rail below is scrollable.
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                    VaaniLockup()
                }
                Spacer(Modifier.height(32.dp))
                Text(title, color = VaaniColor.Cloud, fontSize = 46.sp, lineHeight = 50.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.Normal, textAlign = TextAlign.Center)
            }
            Spacer(Modifier.height(16.dp))
            Box(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState())) {
                Column(Modifier.fillMaxWidth().padding(bottom = 16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    if (step == 1) LanguageWords()
                    if (step == 2) WritingPlaces()
                }
            }
            Spacer(Modifier.height(14.dp))
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp)) {
                OnboardingDots(active = step)
                Button(
                    onClick = onNext,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).semantics { testTag = "onboarding_action" },
                    shape = RoundedCornerShape(14.dp),
                    border = BorderStroke(2.dp, Color(0xFF3B3348)),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE8DCFF), contentColor = Color(0xFF241F2C)),
                ) { Text(if (step == 0) "Get started" else "Next", fontWeight = FontWeight.Bold, fontSize = 16.sp) }
            }
        }
    }
}

@Composable
private fun VaaniLockup() {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Canvas(Modifier.size(27.dp)) {
            val stroke = 4.dp.toPx()
            val left = androidx.compose.ui.geometry.Offset(size.width * 0.18f, size.height * 0.25f)
            val bottom = androidx.compose.ui.geometry.Offset(size.width * 0.50f, size.height * 0.78f)
            val accentStart = androidx.compose.ui.geometry.Offset(size.width * 0.65f, size.height * 0.52f)
            val right = androidx.compose.ui.geometry.Offset(size.width * 0.82f, size.height * 0.25f)
            val ribbon = Color(0xFFFFFDFC)
            drawLine(ribbon, left, bottom, strokeWidth = stroke, cap = androidx.compose.ui.graphics.StrokeCap.Round)
            drawLine(ribbon, bottom, accentStart, strokeWidth = stroke, cap = androidx.compose.ui.graphics.StrokeCap.Round)
            drawLine(Color(0xFFFFD4A3), accentStart, right, strokeWidth = stroke, cap = androidx.compose.ui.graphics.StrokeCap.Round)
        }
        Text("Vaani", color = VaaniColor.Cloud, fontSize = 24.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.6).sp)
    }
}

@Composable
private fun LanguageWords() {
    val travel = remember { Animatable(0f) }
    val languages = listOf("অসমীয়া", "বাংলা", "ગુજરાતી", "हिन्दी", "ಕನ್ನಡ", "മലയാളം", "मराठी", "தமிழ்", "తెలుగు")
    val rowHeight = 66f
    val cycleHeight = languages.size * rowHeight
    LaunchedEffect(Unit) {
        // The first few pixels ease in, then the rail maintains one continuous pace.
        travel.animateTo(42f, animationSpec = tween(durationMillis = 900, easing = FastOutLinearInEasing))
        while (true) {
            travel.animateTo(cycleHeight, animationSpec = tween(durationMillis = ((cycleHeight - travel.value) / 76f * 1000f).toInt(), easing = LinearEasing))
            travel.snapTo(0f)
        }
    }
    Box(Modifier.fillMaxWidth().height(405.dp).padding(top = 42.dp).clipToBounds()) {
        for (virtualIndex in -languages.size..languages.size * 2) {
            val language = languages[(virtualIndex % languages.size + languages.size) % languages.size]
            val y = virtualIndex * rowHeight - travel.value
            val opacity = (1f - kotlin.math.abs(y - 145f) / 190f).coerceIn(0.18f, 1f)
            LanguageRailChip(
                language = language,
                modifier = Modifier.align(Alignment.TopCenter).offset(y = y.dp).graphicsLayer {
                    alpha = opacity
                    scaleX = 0.92f + opacity * 0.08f
                    scaleY = 0.92f + opacity * 0.08f
                },
            )
        }
    }
}

@Composable
private fun LanguageRailChip(language: String, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .background(VaaniColor.Cloud.copy(alpha = 0.16f), RoundedCornerShape(22.dp))
            .padding(horizontal = 28.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(language, color = VaaniColor.Cloud, fontSize = 18.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun WritingPlaces() {
    val travel = remember { Animatable(0f) }
    val destinations = listOf(
        AppDestination("Slack", R.drawable.brand_slack, Color(0xFFFFFBF4)),
        AppDestination("WhatsApp", R.drawable.brand_whatsapp, Color(0xFFFFFBF4)),
        AppDestination("Gmail", R.drawable.brand_gmail, Color(0xFFFFFBF4)),
        AppDestination("Notion", R.drawable.brand_notion, Color(0xFFFFFBF4)),
        AppDestination("Telegram", R.drawable.brand_telegram, Color(0xFFFFFBF4)),
        AppDestination("Canva", R.drawable.brand_canva, Color(0xFF7256D9)),
        AppDestination("X", R.drawable.brand_x, Color(0xFF121116)),
    )
    LaunchedEffect(Unit) {
        travel.animateTo(0.045f, animationSpec = tween(durationMillis = 900, easing = FastOutLinearInEasing))
        while (true) {
            travel.animateTo(1f, animationSpec = tween(durationMillis = ((1f - travel.value) * 8200f).toInt(), easing = LinearEasing))
            travel.snapTo(0f)
        }
    }
    BoxWithConstraints(Modifier.fillMaxWidth().height(405.dp).padding(top = 40.dp)) {
        // The intro column is inset by 28 dp. Let the ribbon deliberately escape that inset
        // so marks arrive at and leave through the physical screen edges.
        val edgeToEdgeWidth = maxWidth + 56.dp
        Box(Modifier.width(edgeToEdgeWidth).offset(x = (-28).dp)) {
            destinations.forEachIndexed { index, destination ->
                val progress = (index.toFloat() / destinations.size - travel.value + 1f) % 1f
                val (x, y) = destinationRibbonPoint(progress, edgeToEdgeWidth.value)
                AppLogoTile(
                    destination = destination,
                    modifier = Modifier.align(Alignment.TopStart).offset(x = (x - 30f).dp, y = (y - 30f).dp).graphicsLayer {
                        rotationZ = -14f + progress * 28f
                    },
                )
            }
        }
    }
}

private data class AppDestination(val name: String, val logo: Int, val surface: Color)

private fun destinationRibbonPoint(progress: Float, width: Float): Pair<Float, Float> {
    val x = -62f + (width + 124f) * progress
    // A single, continuous ribbon: it rises through the middle and twists as it exits.
    val y = 250f - kotlin.math.sin(progress * Math.PI).toFloat() * 160f -
        kotlin.math.sin(progress * Math.PI * 2f).toFloat() * 40f
    return x to y
}

@Composable
private fun AppLogoTile(destination: AppDestination, modifier: Modifier = Modifier) {
    Box(
        modifier.size(60.dp).background(destination.surface, RoundedCornerShape(18.dp)),
        contentAlignment = Alignment.Center,
    ) {
        Image(painter = painterResource(destination.logo), contentDescription = destination.name, modifier = Modifier.size(48.dp), contentScale = ContentScale.Fit)
    }
}

@Composable
private fun OnboardingDots(active: Int) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        repeat(3) { index ->
            Box(Modifier.size(if (index == active) 10.dp else 8.dp).background(if (index == active) VaaniColor.Cloud else VaaniColor.Cloud.copy(alpha = 0.48f), CircleShape))
        }
    }
}

@Composable
private fun ProductDemoScreen(onNext: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().background(VaaniColor.Surface).padding(horizontal = 28.dp, vertical = 56.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(22.dp)) {
            SetupProgress(active = 1)
            Text("A LITTLE DEMO", color = VaaniColor.Coral, fontSize = 13.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
            Text("Say it once.\nKeep your rhythm.", color = VaaniColor.Text, fontSize = 40.sp, lineHeight = 44.sp, fontFamily = FontFamily.Serif)
            Text("Vaani listens while you speak, then gives you a clean sentence that sounds like you.", color = VaaniColor.Muted, fontSize = 18.sp, lineHeight = 26.sp)
            Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(top = 6.dp)) {
                DemoBubble("I am here to help you.", VaaniColor.Cobalt, VaaniColor.Cloud)
                DemoBubble("I’m here to help you.", Color(0xFFE8ECE8), VaaniColor.Text)
            }
            KeyboardDemoCard()
            Text("The second line is the one you can use — polished, private, and ready for any text field.", color = VaaniColor.Muted, fontSize = 14.sp, lineHeight = 21.sp)
        }
        Button(onClick = onNext, modifier = Modifier.fillMaxWidth().height(56.dp), shape = RoundedCornerShape(18.dp), colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Cobalt, contentColor = VaaniColor.Cloud)) {
            Text("Show me how", fontWeight = FontWeight.Bold, fontSize = 17.sp)
        }
    }
}

@Composable
private fun KeyboardDemoCard() {
    Box(
        modifier = Modifier.fillMaxWidth().height(226.dp).background(VaaniColor.Ink, RoundedCornerShape(26.dp)).padding(14.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("Message", color = VaaniColor.Cloud.copy(alpha = 0.55f), fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                Text("Vaani demo", color = VaaniColor.Coral, fontSize = 11.sp, fontWeight = FontWeight.Bold)
            }
            Box(Modifier.fillMaxWidth().height(54.dp).background(VaaniColor.Cloud, RoundedCornerShape(15.dp)).padding(horizontal = 13.dp, vertical = 9.dp)) {
                Text("I’m here to help you.", color = VaaniColor.Text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End, verticalAlignment = Alignment.CenterVertically) {
                Text("Hold the bubble to speak", color = VaaniColor.Cloud.copy(alpha = 0.72f), fontSize = 11.sp, modifier = Modifier.padding(end = 8.dp))
                Box(Modifier.size(38.dp).background(VaaniColor.Cobalt, RoundedCornerShape(13.dp)), contentAlignment = Alignment.Center) {
                    Text("▮▮▮", color = VaaniColor.Cloud, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp), modifier = Modifier.fillMaxWidth()) {
                listOf("Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P").forEach { key ->
                    Box(Modifier.weight(1f).height(30.dp).background(Color(0xFF2B3041), RoundedCornerShape(7.dp)), contentAlignment = Alignment.Center) {
                        Text(key, color = VaaniColor.Cloud.copy(alpha = 0.82f), fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

@Composable
private fun DemoBubble(text: String, color: Color, contentColor: Color) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(10.dp).background(VaaniColor.Coral, CircleShape))
        Box(Modifier.fillMaxWidth().background(color, RoundedCornerShape(18.dp)).padding(horizontal = 16.dp, vertical = 14.dp)) {
            Text(text, color = contentColor, fontSize = 17.sp, lineHeight = 23.sp)
        }
    }
}

@Composable
private fun FloatingSetupScreen(onEnableOverlay: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().background(VaaniColor.Surface).padding(horizontal = 28.dp, vertical = 56.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(22.dp)) {
            SetupProgress(active = 3)
            Text("ONE SMALL SETTING", color = VaaniColor.Cobalt, fontSize = 13.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
            Text("Keep your\nkeyboard.", color = VaaniColor.Text, fontSize = 40.sp, lineHeight = 44.sp, fontFamily = FontFamily.Serif)
            Text("Vaani floats above the app you already use. Your default keyboard stays exactly where it is — Vaani only appears when you choose to speak.", color = VaaniColor.Muted, fontSize = 18.sp, lineHeight = 26.sp)
            GuideStep("01", "Allow a floating button", "Android asks for permission so Vaani can sit above your current app.")
            GuideStep("02", "Hold to speak", "Press and hold the bubble, then release when your sentence is done.")
        }
        Button(onClick = onEnableOverlay, modifier = Modifier.fillMaxWidth().height(56.dp).semantics { testTag = "setup_enable_overlay" }, shape = RoundedCornerShape(18.dp), colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Cobalt, contentColor = VaaniColor.Cloud)) {
            Text("Enable floating button", fontWeight = FontWeight.Bold, fontSize = 17.sp)
        }
    }
}

@Composable
private fun AccessibilitySetupScreen(onOpenAccessibility: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().background(VaaniColor.Surface).padding(horizontal = 28.dp, vertical = 56.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(22.dp)) {
            SetupProgress(active = 2)
            Text("FOR TEXT BOXES", color = VaaniColor.Cobalt, fontSize = 13.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
            Text("Let Vaani\nfind your cursor.", color = VaaniColor.Text, fontSize = 40.sp, lineHeight = 44.sp, fontFamily = FontFamily.Serif)
            Text("This optional Android setting lets the floating bubble recognize the text field you are using and paste the finished sentence there. Your default keyboard stays unchanged.", color = VaaniColor.Muted, fontSize = 18.sp, lineHeight = 26.sp)
            GuideStep("01", "Open Accessibility settings", "Find Vaani under downloaded services.")
            GuideStep("02", "Turn on text-box access", "Vaani only uses the focused editable field for the current phrase.")
        }
        Button(onClick = onOpenAccessibility, modifier = Modifier.fillMaxWidth().height(56.dp).semantics { testTag = "setup_open_accessibility" }, shape = RoundedCornerShape(18.dp), colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Cobalt, contentColor = VaaniColor.Cloud)) {
            Text("Open Accessibility settings", fontWeight = FontWeight.Bold, fontSize = 17.sp)
        }
    }
}

@Composable
private fun MicSetupScreen(granted: Boolean, onRequestMicrophone: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().background(VaaniColor.Surface).padding(horizontal = 28.dp, vertical = 56.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(22.dp)) {
            SetupProgress(active = 4)
            Text("YOUR VOICE, YOUR CHOICE", color = VaaniColor.Coral, fontSize = 13.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
            Text(if (granted) "Your microphone\nis ready." else "Give Vaani\na microphone.", color = VaaniColor.Text, fontSize = 40.sp, lineHeight = 44.sp, fontFamily = FontFamily.Serif)
            Text(if (granted) "Vaani will only listen after you choose to dictate. You control every phrase." else "Vaani only listens after you choose to dictate. Audio is used for the current phrase and is not uploaded as a recording.", color = VaaniColor.Muted, fontSize = 18.sp, lineHeight = 26.sp)
            Box(Modifier.fillMaxWidth().background(Color(0xFFE8ECE8), RoundedCornerShape(20.dp)).padding(18.dp)) {
                Text("You stay in control — press and hold to speak, release to finish.", color = VaaniColor.Text, fontSize = 16.sp, lineHeight = 23.sp, fontWeight = FontWeight.SemiBold)
            }
        }
        Button(onClick = onRequestMicrophone, modifier = Modifier.fillMaxWidth().height(56.dp).semantics { testTag = "allow_microphone" }, shape = RoundedCornerShape(18.dp), colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Cobalt, contentColor = VaaniColor.Cloud)) {
            Text(if (granted) "Continue" else "Allow microphone", fontWeight = FontWeight.Bold, fontSize = 17.sp)
        }
    }
}

@Composable
private fun SafetyScreen(onNext: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().background(VaaniColor.Surface).padding(horizontal = 28.dp, vertical = 56.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(22.dp)) {
            SetupProgress(active = 4)
            Text("BUILT AROUND TRUST", color = VaaniColor.Cobalt, fontSize = 13.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
            Text("Your words\nstay yours.", color = VaaniColor.Text, fontSize = 40.sp, lineHeight = 44.sp, fontFamily = FontFamily.Serif)
            Text("Vaani is designed for the moments you need to move quickly, without giving up the feeling of privacy.", color = VaaniColor.Muted, fontSize = 18.sp, lineHeight = 26.sp)
            GuideStep("01", "Local by default", "Speech and cleanup can run on this device.")
            GuideStep("02", "Nothing happens by accident", "You choose when to listen, write, and paste.")
        }
        Button(onClick = onNext, modifier = Modifier.fillMaxWidth().height(56.dp), shape = RoundedCornerShape(18.dp), colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Cobalt, contentColor = VaaniColor.Cloud)) {
            Text("Continue", fontWeight = FontWeight.Bold, fontSize = 17.sp)
        }
    }
}

@Composable
private fun SetupProgress(active: Int) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
        repeat(4) { index -> Box(Modifier.weight(1f).height(4.dp).background(if (index <= active) VaaniColor.Cobalt else VaaniColor.Line, RoundedCornerShape(4.dp))) }
    }
}

@Composable
private fun SetupGuideScreen(onEnableOverlay: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().background(VaaniColor.Surface).padding(horizontal = 28.dp, vertical = 56.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(28.dp)) {
            Text("FIRST DICTATION", color = VaaniColor.Coral, fontSize = 13.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
            Text("Three seconds\nto clear writing.", color = VaaniColor.Text, fontSize = 40.sp, lineHeight = 45.sp, fontWeight = FontWeight.SemiBold)
            Text("Keep your usual keyboard. Vaani listens through the floating button, then places the finished words on your clipboard so you can paste them anywhere.", color = VaaniColor.Muted, fontSize = 18.sp, lineHeight = 26.sp)
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                GuideStep("01", "Open any text field", "Messages, notes, search, and email all work normally.")
                GuideStep("02", "Hold the Vaani bubble", "Speak naturally while the bubble shows that it is listening.")
                GuideStep("03", "Release and paste", "Vaani cleans the phrase locally and copies it for your default keyboard.")
            }
        }
        Button(
            onClick = onEnableOverlay,
            modifier = Modifier.fillMaxWidth().height(56.dp).semantics { testTag = "setup_enable_overlay" },
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Cobalt, contentColor = VaaniColor.Cloud),
        ) { Text("Turn on Vaani bubble", fontWeight = FontWeight.Bold, fontSize = 17.sp) }
    }
}

@Composable
private fun GuideStep(number: String, title: String, body: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.Top) {
        Text(number, color = VaaniColor.Cobalt, fontSize = 14.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 2.dp))
        Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(title, color = VaaniColor.Text, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
            Text(body, color = VaaniColor.Muted, fontSize = 15.sp, lineHeight = 21.sp)
        }
    }
}

@Composable
private fun OnboardingScreen(art: Int, step: Int, eyebrow: String, title: String, body: String, action: String, onAction: () -> Unit) {
    Box(Modifier.fillMaxSize().background(VaaniColor.Ink)) {
        Image(
            painter = painterResource(art), contentDescription = null,
            modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop, alpha = 0.72f,
        )
        Box(Modifier.fillMaxSize().background(VaaniColor.Ink.copy(alpha = 0.36f)))
        Column(
            Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(horizontal = 28.dp, vertical = 52.dp),
            verticalArrangement = Arrangement.spacedBy(28.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(40.dp)) {
                Wordmark()
                Column(verticalArrangement = Arrangement.spacedBy(20.dp)) {
                    Text(eyebrow.uppercase(), color = VaaniColor.Cloud.copy(alpha = 0.74f), fontSize = 13.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.2.sp)
                    Text(title, color = VaaniColor.Cloud, fontSize = 44.sp, lineHeight = 48.sp, fontWeight = FontWeight.SemiBold)
                    Text(body, color = VaaniColor.Cloud.copy(alpha = 0.88f), fontSize = 18.sp, lineHeight = 26.sp, modifier = Modifier.fillMaxWidth(0.86f))
                }
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(24.dp)) {
                PagerDots(step)
                Button(
                    onClick = onAction,
                    modifier = Modifier.fillMaxWidth().height(56.dp).semantics { testTag = if (step == 2) "allow_microphone" else "onboarding_action" }.drawBehind {
                        drawRoundRect(Color(0x660C1020), style = Stroke(width = 2.dp.toPx()), cornerRadius = androidx.compose.ui.geometry.CornerRadius(16.dp.toPx()))
                    },
                    shape = RoundedCornerShape(16.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Cloud, contentColor = VaaniColor.Ink),
                ) {
                    Text(action, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                }
            }
        }
    }
}

@Composable private fun Wordmark() {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("∨", color = VaaniColor.Coral, fontSize = 34.sp, fontWeight = FontWeight.Bold)
        Text("Vaani", color = VaaniColor.Cloud, fontSize = 24.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable private fun PagerDots(active: Int) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) { repeat(3) { index -> Box(Modifier.size(if (index == active) 9.dp else 8.dp).background(if (index == active) VaaniColor.Cloud else VaaniColor.Cloud.copy(alpha = 0.45f), CircleShape)) } }
}

// Product-introduction screens. Their sequence is documented in
// docs/references/whisperflow-product-flow-study.md and uses only Vaani's own
// brand tokens, language, mark, and Android behavior.

@Composable
private fun VaaniFlowScaffold(
    step: Int,
    title: String,
    body: String,
    action: String,
    onAction: () -> Unit,
    actionEnabled: Boolean = true,
    secondary: String? = null,
    onSecondary: (() -> Unit)? = null,
    visual: @Composable () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxSize().background(VaaniColor.Paper).imePadding().padding(horizontal = 24.dp, vertical = 40.dp),
    ) {
        // The progress, title, and action area are navigation anchors. Only
        // the illustration/list in the middle moves, even at large font sizes.
        Column {
            FlowProgress(step)
            Spacer(Modifier.height(24.dp))
            Text(title, color = VaaniColor.Ink, fontFamily = FontFamily.Serif, fontSize = 37.sp, lineHeight = 40.sp, letterSpacing = (-1.3).sp)
            Spacer(Modifier.height(8.dp))
            Text(body, color = VaaniColor.Muted, fontSize = 16.sp, lineHeight = 23.sp, modifier = Modifier.fillMaxWidth(0.94f))
        }
        Spacer(Modifier.height(16.dp))
        Box(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState())) {
            Column(Modifier.fillMaxWidth().padding(bottom = 16.dp)) { visual() }
        }
        Spacer(Modifier.height(12.dp))
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            VaaniPrimaryButton(action, onAction, actionEnabled)
            if (secondary != null && onSecondary != null) VaaniSecondaryButton(secondary, onSecondary)
        }
    }
}

@Composable
private fun FlowProgress(step: Int) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        repeat(12) { index ->
            Box(
                Modifier.weight(1f).height(3.dp).background(
                    if (index <= step) VaaniColor.Plum else VaaniColor.Line,
                    RoundedCornerShape(3.dp),
                ),
            )
        }
    }
}

@Composable
private fun VaaniPrimaryButton(label: String, onClick: () -> Unit, enabled: Boolean = true) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(2.dp, VaaniColor.Ink),
        colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Lilac, contentColor = VaaniColor.Ink),
    ) { Text(label, fontSize = 16.sp, fontWeight = FontWeight.Bold) }
}

@Composable
private fun VaaniSecondaryButton(label: String, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp),
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(1.dp, VaaniColor.Ink),
        colors = ButtonDefaults.outlinedButtonColors(containerColor = VaaniColor.Paper, contentColor = VaaniColor.Ink),
    ) { Text(label, fontSize = 15.sp, fontWeight = FontWeight.SemiBold) }
}

@Composable
private fun AccountGateScreen(
    message: String?,
    onSkip: () -> Unit,
    onEmail: (String, String, Boolean) -> Unit,
    onGoogle: (Activity) -> Unit,
) {
    val context = LocalContext.current
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var create by remember { mutableStateOf(false) }
    Column(
        Modifier.fillMaxSize().background(VaaniColor.Paper).imePadding().padding(horizontal = 24.dp, vertical = 40.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("VAANI ACCOUNT", color = VaaniColor.Plum, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            Text("Keep your\nwriting setup close.", color = VaaniColor.Ink, fontFamily = FontFamily.Serif, fontSize = 37.sp, lineHeight = 40.sp)
            Text("Sign in to sync selected preferences across your devices. You can also stay local. Either choice starts preparing Vaani’s private on-device models.", color = VaaniColor.Muted, fontSize = 16.sp, lineHeight = 23.sp)
        }
        Spacer(Modifier.height(16.dp))
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            OutlinedTextField(email, { email = it }, label = { Text("Email") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(password, { password = it }, label = { Text("Password (8+ characters)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Text(if (create) "New account" else "Existing account", color = VaaniColor.Muted, fontSize = 13.sp, modifier = Modifier.clickable { create = !create })
            message?.let { Text(it, color = VaaniColor.Plum, fontSize = 13.sp, lineHeight = 18.sp) }
        }
        Spacer(Modifier.height(12.dp))
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            VaaniPrimaryButton(if (create) "Create account" else "Sign in", { onEmail(email, password, create) })
            VaaniSecondaryButton("Continue with Google") {
                (context as? Activity)?.let(onGoogle)
            }
            Text("Continue without an account", color = VaaniColor.Ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().clickable(onClick = onSkip))
        }
    }
}

@Composable
private fun ModelPreparationScreen(onReady: () -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current
    val liveWork = remember(context) { WorkManager.getInstance(context).getWorkInfosForUniqueWorkLiveData("vaani-model-release") }
    var work by remember { mutableStateOf(emptyList<androidx.work.WorkInfo>()) }
    var textBoxAccessEnabled by remember { mutableStateOf(AccessibilityBridge.isTextBoxAccessEnabled(context)) }
    DisposableEffect(liveWork, lifecycle) {
        val observer = Observer<List<androidx.work.WorkInfo>> { work = it ?: emptyList() }
        liveWork.observe(lifecycle, observer)
        onDispose { liveWork.removeObserver(observer) }
    }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                textBoxAccessEnabled = AccessibilityBridge.isTextBoxAccessEnabled(context)
            }
        }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer) }
    }
    val status = ModelRelease.status(context)
    LaunchedEffect(status, textBoxAccessEnabled) {
        if (status == ModelRelease.Status.READY && textBoxAccessEnabled &&
            (Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context))
        ) {
            context.startService(Intent(context, VoiceOverlayService::class.java))
        }
    }
    val progress = work.firstOrNull { !it.state.isFinished }?.progress ?: work.firstOrNull()?.progress
    val percent = progress?.getInt(ModelRelease.PROGRESS_PERCENT, -1) ?: -1
    val downloadedBytes = progress?.getLong(ModelRelease.PROGRESS_DOWNLOADED_BYTES, 0L) ?: 0L
    val totalBytes = progress?.getLong(ModelRelease.PROGRESS_TOTAL_BYTES, -1L) ?: -1L
    val etaSeconds = progress?.getLong(ModelRelease.PROGRESS_ETA_SECONDS, -1L) ?: -1L
    val phase = progress?.getString(ModelRelease.PROGRESS_PHASE).orEmpty()
    val modelLabel = progress?.getString(ModelRelease.PROGRESS_MODEL).orEmpty()
    val waiting = status == ModelRelease.Status.QUEUED || status == ModelRelease.Status.DOWNLOADING ||
        work.any { !it.state.isFinished }
    val title: String
    val body: String
    when {
        status == ModelRelease.Status.READY -> {
            title = "Vaani is\nready to write."
            body = "Speech and cleanup now run from this device. You’ll also get a notification when a future model update is ready."
        }
        status == ModelRelease.Status.WAITING_FOR_ANDROID_PACKAGE -> {
            title = "Your Android\nmodel is next."
            body = "A compatible model catalog is waiting to be published. Vaani stays locked until both private Android packages verify."
        }
        status == ModelRelease.Status.FAILED -> {
            title = "Model download\nneeds attention."
                body = "Vaani could not verify both local model packages. Keep a connection and reopen the app to retry safely."
        }
        waiting -> {
            title = "Preparing Vaani\nfor this device."
            body = "Your private speech and cleanup models are downloading securely. You can finish reading the setup while Vaani prepares itself."
        }
        else -> {
            title = "Preparing Vaani\nfor this device."
            body = "The secure model job is starting. Vaani becomes available only after both local packages verify."
        }
    }
    VaaniFlowScaffold(
        step = 11,
        title = title,
        body = body,
        action = if (status == ModelRelease.Status.READY && !textBoxAccessEnabled) "Enable text-box access" else "Start using Vaani",
        onAction = {
            if (status == ModelRelease.Status.READY && !textBoxAccessEnabled) {
                context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            } else onReady()
        },
        actionEnabled = status == ModelRelease.Status.READY,
        secondary = null,
    ) {
        Box(Modifier.fillMaxWidth().height(224.dp).background(if (status == ModelRelease.Status.READY) VaaniColor.Lilac else VaaniColor.Apricot, RoundedCornerShape(26.dp)).padding(22.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(11.dp), modifier = Modifier.fillMaxSize()) {
                Text(if (status == ModelRelease.Status.READY) "MODELS VERIFIED" else "MODEL PREPARATION", color = VaaniColor.Plum, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                if (status == ModelRelease.Status.READY) {
                    Text("On this device.\nReady in your fields.", color = VaaniColor.Ink, fontFamily = FontFamily.Serif, fontSize = 25.sp, lineHeight = 29.sp)
                    Text("Both packages passed their integrity checks.", color = VaaniColor.Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                } else {
                    Text("Your local models\nare on their way.", color = VaaniColor.Ink, fontFamily = FontFamily.Serif, fontSize = 25.sp, lineHeight = 29.sp)
                    ModelDownloadProgress(
                        waiting = waiting,
                        phase = phase,
                        modelLabel = modelLabel,
                        percent = percent,
                        downloadedBytes = downloadedBytes,
                        totalBytes = totalBytes,
                        etaSeconds = etaSeconds,
                    )
                }
            }
        }
    }
}

@Composable
private fun ModelDownloadProgress(
    waiting: Boolean,
    phase: String,
    modelLabel: String,
    percent: Int,
    downloadedBytes: Long,
    totalBytes: Long,
    etaSeconds: Long,
) {
    val hasMeasuredProgress = percent >= 0 && totalBytes > 0L
    val headline = when {
        !waiting -> "Preparing the secure download…"
        phase == "Verifying" -> "Verifying ${modelLabel.ifBlank { "model" }.lowercase()}…"
        phase == "Verified" -> "Model verified — preparing the next one…"
        hasMeasuredProgress -> "${modelLabel.ifBlank { "Model" }}  ·  $percent%"
        else -> "Connecting to the model release…"
    }
    Text(headline, color = VaaniColor.Ink, fontSize = 14.sp, fontWeight = FontWeight.Bold)
    if (hasMeasuredProgress) {
        Box(
            Modifier.fillMaxWidth().height(7.dp)
                .background(VaaniColor.Cloud.copy(alpha = 0.58f), RoundedCornerShape(7.dp)),
        ) {
            Box(
                Modifier.fillMaxWidth(percent / 100f).height(7.dp)
                    .background(VaaniColor.Cobalt, RoundedCornerShape(7.dp)),
            )
        }
        Text(
            "${formatModelBytes(downloadedBytes)} of ${formatModelBytes(totalBytes)}  ·  ${formatEta(etaSeconds)}",
            color = VaaniColor.Ink,
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
        )
    } else {
        Text(
            if (waiting) "We’ll show the size and remaining time as soon as the connection starts." else "Vaani remains locked until both files verify.",
            color = VaaniColor.Ink,
            fontSize = 12.sp,
            lineHeight = 17.sp,
        )
    }
}

private fun formatModelBytes(bytes: Long): String = when {
    bytes >= 1_000_000_000L -> "%.1f GB".format(bytes / 1_000_000_000.0)
    bytes >= 1_000_000L -> "%.1f MB".format(bytes / 1_000_000.0)
    else -> "${bytes / 1_000L} KB"
}

private fun formatEta(seconds: Long): String = when {
    seconds < 0L -> "estimating time left"
    seconds < 60L -> "about ${seconds.coerceAtLeast(1)} sec left"
    seconds < 3_600L -> "about ${seconds / 60} min left"
    else -> "about ${seconds / 3_600} hr left"
}

@Composable
private fun ClearWordsScreen(onNext: () -> Unit) = VaaniFlowScaffold(
    step = 0,
    title = "Clear words,\nwherever you write.",
    body = "Vaani turns a spoken thought into clean text, then gets out of your way.",
    action = "Continue",
    onAction = onNext,
) {
    Box(Modifier.fillMaxWidth().height(300.dp).background(VaaniColor.Lilac, RoundedCornerShape(26.dp)).padding(28.dp)) {
        Column(verticalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxSize()) {
            Text("SAY IT YOUR WAY", color = VaaniColor.Plum, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
            Text("A thought becomes a sentence you can keep moving with.", color = VaaniColor.Ink, fontFamily = FontFamily.Serif, fontSize = 30.sp, lineHeight = 33.sp)
            VaaniRibbonSketch(Modifier.align(Alignment.End).size(112.dp))
        }
    }
}

@Composable
private fun HowVaaniWorksScreen(onNext: () -> Unit) = VaaniFlowScaffold(
    step = 1,
    title = "Three small\nmovements.",
    body = "Hold the Vaani control, speak naturally, and release. The finished text arrives in the field you chose.",
    action = "Show me",
    onAction = onNext,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        FlowStep("01", "Hold", "Start only when you want to dictate.")
        FlowStep("02", "Speak", "Use the words and language that feel natural.")
        FlowStep("03", "Release", "Vaani formats the final sentence and writes it.")
        Box(Modifier.fillMaxWidth().height(88.dp).background(VaaniColor.Apricot, RoundedCornerShape(22.dp)), contentAlignment = Alignment.Center) {
            VaaniRibbonSketch(Modifier.size(58.dp))
        }
    }
}

@Composable
private fun FlowStep(number: String, title: String, body: String) {
    Row(Modifier.fillMaxWidth().background(VaaniColor.Cloud, RoundedCornerShape(18.dp)).padding(16.dp), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        Text(number, color = VaaniColor.Plum, fontSize = 12.sp, fontWeight = FontWeight.Bold)
        Column {
            Text(title, color = VaaniColor.Ink, fontSize = 16.sp, fontWeight = FontWeight.Bold)
            Text(body, color = VaaniColor.Muted, fontSize = 13.sp, lineHeight = 18.sp)
        }
    }
}

@Composable
private fun InFieldLessonScreen(onNext: () -> Unit) = VaaniFlowScaffold(
    step = 2,
    title = "See it in a\ntext box.",
    body = "Vaani keeps your normal keyboard. The temporary control appears only while you are dictating.",
    action = "Try the flow",
    onAction = onNext,
) {
    MessageRehearsal(listening = false, finished = true)
}

@Composable
private fun WritingLanguageScreen(onNext: () -> Unit) {
    var selected by remember { mutableStateOf("English") }
    VaaniFlowScaffold(
        step = 3,
        title = "Choose your\nwriting language.",
        body = "This helps Vaani prepare the right local recognition model. You can change it later.",
        action = "Continue",
        onAction = onNext,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            listOf("English", "Hindi", "Bengali").forEach { language ->
                VaaniChoiceRow(language, selected == language) { selected = language }
            }
        }
    }
}

@Composable
private fun VaaniChoiceRow(label: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().height(62.dp).background(if (selected) Color(0xFFF7F1FF) else VaaniColor.Cloud, RoundedCornerShape(16.dp))
            .border(if (selected) 2.dp else 1.dp, if (selected) VaaniColor.Plum else VaaniColor.Line, RoundedCornerShape(16.dp))
            .clickable(onClick = onClick).padding(horizontal = 18.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, color = VaaniColor.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        if (selected) Box(Modifier.size(22.dp).background(VaaniColor.Plum, CircleShape), contentAlignment = Alignment.Center) {
            Text("✓", color = VaaniColor.Cloud, fontSize = 13.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun HoldToSpeakScreen(onNext: () -> Unit) = VaaniFlowScaffold(
    step = 4,
    title = "Hold to speak.",
    body = "The text field remains yours. Vaani is listening only while you hold the control.",
    action = "I understand",
    onAction = onNext,
) { MessageRehearsal(listening = true, finished = false) }

@Composable
private fun FinishedTextScreen(onNext: () -> Unit) = VaaniFlowScaffold(
    step = 5,
    title = "Release to\nwrite clearly.",
    body = "Vaani writes the cleaned final sentence, while keeping the original phrase available for recovery.",
    action = "Next",
    onAction = onNext,
) { MessageRehearsal(listening = false, finished = true) }

@Composable
private fun MessageRehearsal(listening: Boolean, finished: Boolean) {
    Column(Modifier.fillMaxWidth().background(VaaniColor.Ink, RoundedCornerShape(26.dp)).padding(18.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("Message", color = VaaniColor.Cloud.copy(alpha = 0.65f), fontSize = 12.sp, fontWeight = FontWeight.Bold)
        Box(Modifier.fillMaxWidth().height(74.dp).background(VaaniColor.Cloud, RoundedCornerShape(17.dp)).padding(14.dp)) {
            Text(
                if (finished) "Could we move it to Friday?" else "",
                color = VaaniColor.Ink,
                fontSize = 16.sp,
                lineHeight = 22.sp,
            )
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text(if (listening) "Listening…" else if (finished) "Cleaned locally" else "Hold to dictate", color = VaaniColor.Cloud.copy(alpha = 0.8f), fontSize = 12.sp)
            Box(Modifier.size(50.dp).background(if (listening) VaaniColor.Plum else VaaniColor.Lilac, RoundedCornerShape(17.dp)), contentAlignment = Alignment.Center) {
                Text(if (listening) "▮▮▮" else "∨", color = if (listening) VaaniColor.Cloud else VaaniColor.Ink, fontSize = 16.sp, fontWeight = FontWeight.Bold)
            }
        }
        if (listening) Row(horizontalArrangement = Arrangement.spacedBy(5.dp), modifier = Modifier.align(Alignment.CenterHorizontally)) {
            listOf(12, 23, 34, 19, 28, 14).forEach { height -> Box(Modifier.width(4.dp).height(height.dp).background(VaaniColor.Apricot, RoundedCornerShape(4.dp))) }
        }
    }
}

@Composable
private fun StepsOutScreen(onNext: () -> Unit) = VaaniFlowScaffold(
    step = 6,
    title = "Then Vaani\nsteps out.",
    body = "No permanent chat bubble. No changed keyboard. Just a compact control for the moment you choose to speak.",
    action = "Set up Vaani",
    onAction = onNext,
) {
    Box(Modifier.fillMaxWidth().height(250.dp).background(Color(0xFFF4EFF7), RoundedCornerShape(26.dp))) {
        repeat(5) { index -> Box(Modifier.width((160 - index * 16).dp).height(10.dp).offset(x = 28.dp, y = (36 + index * 28).dp).background(VaaniColor.Cloud, RoundedCornerShape(8.dp))) }
        Box(Modifier.align(Alignment.BottomEnd).padding(22.dp).size(62.dp).background(VaaniColor.Ink, RoundedCornerShape(21.dp)), contentAlignment = Alignment.Center) {
            VaaniRibbonSketch(Modifier.size(38.dp), main = VaaniColor.Cloud)
        }
    }
}

@Composable
private fun TextBoxAccessScreen(onOpenAccessibility: () -> Unit, onSkip: () -> Unit) = VaaniFlowScaffold(
    step = 7,
    title = "Find the field\nyou chose.",
    body = "Android needs Accessibility permission to let Vaani insert text into the editable field currently in focus. Vaani does not read your screen as a history.",
    action = "Open Accessibility settings",
    onAction = onOpenAccessibility,
    secondary = "Not now",
    onSecondary = onSkip,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        FlowStep("01", "Open settings", "Find Vaani under downloaded apps.")
        FlowStep("02", "Allow text-box access", "Vaani uses only the focused editable field for this phrase.")
        FlowStep("03", "Return here", "You can change this choice later in Settings.")
    }
}

@Composable
private fun PrivateByDefaultScreen(onNext: () -> Unit) {
    var localOnly by remember { mutableStateOf(true) }
    VaaniFlowScaffold(
        step = 8,
        title = "Your phrases\nstay private.",
        body = "Local-only is the default. Future optional sync stores preferences, never raw dictation history by default.",
        action = "Continue",
        onAction = onNext,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            VaaniChoiceRow("Keep everything on this device", localOnly) { localOnly = true }
            VaaniChoiceRow("Help improve Vaani later", !localOnly) { localOnly = false }
        }
    }
}

@Composable
private fun ReadinessScreen(onNext: () -> Unit) = VaaniFlowScaffold(
    step = 9,
    title = "Keep Vaani\nready?",
    body = "Allow the small floating control so dictation is close at hand. It never listens until you press it.",
    action = "Enable Vaani control",
    onAction = onNext,
    secondary = "Not now",
    onSecondary = onNext,
) {
    Box(Modifier.fillMaxWidth().height(190.dp).background(VaaniColor.Apricot, RoundedCornerShape(26.dp)).padding(24.dp)) {
        Column(verticalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxSize()) {
            Text("READY WHEN YOU ASK", color = VaaniColor.Plum, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            Text("A small control.\nYour normal keyboard.", color = VaaniColor.Ink, fontFamily = FontFamily.Serif, fontSize = 27.sp, lineHeight = 30.sp)
            Text("No always-on microphone", color = VaaniColor.Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun NotificationValueScreen(onNext: () -> Unit, onSkip: () -> Unit) = VaaniFlowScaffold(
    step = 10,
    title = "Know when Vaani\nneeds you.",
    body = "Notifications are optional. They can tell you when a model needs attention or a dictation could not be completed.",
    action = "Allow notifications",
    onAction = onNext,
    secondary = "Skip",
    onSecondary = onSkip,
) {
    Box(Modifier.fillMaxWidth().height(230.dp).background(Color(0xFFF7F1FF), RoundedCornerShape(26.dp)), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Box(Modifier.size(78.dp).background(VaaniColor.Apricot, CircleShape), contentAlignment = Alignment.Center) { Text("∨", color = VaaniColor.Ink, fontSize = 44.sp, fontWeight = FontWeight.Bold) }
            Text("Only useful updates.\nNo dictated text in notifications.", color = VaaniColor.Ink, fontSize = 15.sp, lineHeight = 21.sp, textAlign = TextAlign.Center)
        }
    }
}

@Composable
private fun DiscoveryScreen(onNext: () -> Unit) {
    var selected by remember { mutableStateOf<String?>(null) }
    VaaniFlowScaffold(
        step = 11,
        title = "How did you\nfind Vaani?",
        body = "Optional — it helps us understand where the project is reaching people.",
        action = "Finish setup",
        onAction = onNext,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
            listOf("A friend", "Open-source community", "Social media", "AI tools", "Something else").forEach { source ->
                VaaniChoiceRow(source, selected == source) { selected = source }
            }
        }
    }
}

@Composable
private fun VaaniWorkspace(
    overlayEnabled: Boolean,
    onToggleOverlay: () -> Unit,
) {
    val context = LocalContext.current
    val accountClient = remember { VaaniAccountClient(context) }
    val scope = rememberCoroutineScope()
    val lifecycle = LocalLifecycleOwner.current
    var access by remember { mutableStateOf(OnboardingState.access(context)) }
    var account by remember { mutableStateOf(accountClient.current()) }
    var accountOpen by remember { mutableStateOf(false) }
    var accountMessage by remember { mutableStateOf<String?>(null) }
    var tab by remember { mutableStateOf("Dictionary") }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) access = OnboardingState.access(context)
        }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer) }
    }
    if (accountOpen) {
        AccountWorkspace(
            account = account,
            message = accountMessage,
            onClose = { accountOpen = false },
            onCreateSync = {
                val sync = EncryptedPersonalizationSync(context)
                val code = sync.createRecoveryCode()
                accountMessage = "Save this recovery code before adding another device: $code"
                scope.launch {
                    sync.sync().onFailure { accountMessage = it.message ?: "Recovery code created; encrypted sync could not finish." }
                }
            },
            onImportSync = { code ->
                runCatching { EncryptedPersonalizationSync(context).importRecoveryCode(code) }
                    .onSuccess { scope.launch { EncryptedPersonalizationSync(context).sync(); accountMessage = "Encrypted sync complete." } }
                    .onFailure { accountMessage = "That recovery code is invalid." }
            },
            onSync = { scope.launch { EncryptedPersonalizationSync(context).sync().onSuccess { accountMessage = "Encrypted sync complete." }.onFailure { accountMessage = it.message ?: "Encrypted sync could not finish." } } },
            onEmail = { email, password, create ->
                scope.launch {
                    val result = if (create) accountClient.signUp(email, password) else accountClient.signIn(email, password)
                    result.onSuccess {
                        account = it
                        accountMessage = "Account connected. Preparing your local models on Wi-Fi."
                        ModelRelease.enqueue(context)
                        VaaniSyncMessagingService.registerCurrentDevice(context)
                        EncryptedPersonalizationSync(context).sync().onFailure {
                            accountMessage = "Account connected. Create or add your recovery code to enable private sync."
                        }
                    }.onFailure { accountMessage = it.message ?: "That account could not be opened." }
                }
            },
            onGoogle = {
                val activity = context as? Activity
                if (activity == null) accountMessage = "Google sign-in needs the Vaani activity."
                else scope.launch {
                    accountClient.signInWithGoogle(activity).onSuccess {
                        account = it
                        accountMessage = "Account connected. Preparing your local models on Wi-Fi."
                        ModelRelease.enqueue(context)
                        VaaniSyncMessagingService.registerCurrentDevice(context)
                        EncryptedPersonalizationSync(context).sync().onFailure {
                            accountMessage = "Account connected. Create or add your recovery code to enable private sync."
                        }
                    }.onFailure { accountMessage = it.message ?: "Google sign-in could not be completed." }
                }
            },
            onSignOut = {
                accountClient.signOut()
                account = null
                accountMessage = "Signed out. Your local text stays on this device."
            },
        )
        return
    }
    Column(
        Modifier.fillMaxSize().background(VaaniColor.Paper).imePadding().padding(horizontal = 20.dp, vertical = 34.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("☰", color = VaaniColor.Ink, fontSize = 20.sp, modifier = Modifier.clickable { accountOpen = true })
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                VaaniRibbonSketch(Modifier.size(22.dp))
                Text("Vaani", color = VaaniColor.Ink, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            }
            Text("◦◦", color = VaaniColor.Plum, fontSize = 18.sp)
        }
        Text(access.summary, color = if (access.microphone && access.textBoxAccess && access.overlay) VaaniColor.Plum else VaaniColor.Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(16.dp))
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Box(Modifier.fillMaxWidth().heightIn(min = 48.dp).background(VaaniColor.Cloud, RoundedCornerShape(14.dp)).padding(horizontal = 15.dp), contentAlignment = Alignment.CenterStart) {
                Text("Search", color = VaaniColor.Muted, fontSize = 14.sp)
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                listOf("Dictionary", "Style", "Snippets").forEach { label ->
                    Box(Modifier.weight(1f).heightIn(min = 38.dp).background(if (tab == label) VaaniColor.Lilac else VaaniColor.Cloud, RoundedCornerShape(12.dp)).clickable { tab = label }, contentAlignment = Alignment.Center) {
                        Text(label, color = VaaniColor.Ink, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center)
                    }
                }
            }
            when (tab) {
                "Dictionary" -> PersonalizationWorkspace()
                "Style" -> StyleWorkspace()
                else -> WorkspaceEmpty("Saved snippets will appear here.")
            }
        }
        Spacer(Modifier.height(12.dp))
        Text(
            if (account == null) "Sign in from the menu to prepare local models." else "Preparing local models securely on Wi-Fi.",
            color = VaaniColor.Muted,
            fontSize = 12.sp,
        )
        Spacer(Modifier.height(12.dp))
        VaaniPrimaryButton(if (overlayEnabled) "Vaani control is active" else "Enable Vaani control", onToggleOverlay)
    }
}

@Composable
private fun PersonalizationWorkspace() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val store = remember { PersonalizationStore(context) }
    var snapshot by remember { mutableStateOf(store.snapshot()) }
    var spelling by remember { mutableStateOf("") }
    var heardAs by remember { mutableStateOf("") }
    var source by remember { mutableStateOf("") }
    var target by remember { mutableStateOf("") }
    var message by remember { mutableStateOf<String?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Personal vocabulary", color = VaaniColor.Ink, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Text("Names and places guide recognition; “heard as” corrects a phonetic spelling.", color = VaaniColor.Muted, fontSize = 13.sp)
        OutlinedTextField(value = spelling, onValueChange = { spelling = it }, label = { Text("Exact spelling") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(value = heardAs, onValueChange = { heardAs = it }, label = { Text("Heard as (optional)") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedButton(onClick = {
            runCatching { store.addVocabulary(spelling, heardAs); snapshot = store.snapshot(); spelling = ""; heardAs = ""; scope.launch { EncryptedPersonalizationSync(context).sync() } }
                .onFailure { message = "Enter a short personal term." }
        }, enabled = spelling.isNotBlank()) { Text("Add term") }
        snapshot.vocabulary.forEach { item ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(item.canonical, color = VaaniColor.Ink, fontWeight = FontWeight.SemiBold)
                    Text(item.aliases.takeIf { it.isNotEmpty() }?.joinToString(prefix = "Heard as: ") ?: "Recognition spelling", color = VaaniColor.Muted, fontSize = 12.sp)
                }
                OutlinedButton(onClick = { store.removeVocabulary(item.id); snapshot = store.snapshot(); scope.launch { EncryptedPersonalizationSync(context).sync() } }) { Text("Remove") }
            }
        }
        Text("Text replacements", color = VaaniColor.Ink, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Text("Replace a complete phrase once final dictation is ready—for example, “my github” → your link.", color = VaaniColor.Muted, fontSize = 13.sp)
        OutlinedTextField(value = source, onValueChange = { source = it }, label = { Text("When Vaani writes this") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(value = target, onValueChange = { target = it }, label = { Text("Replace it with") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedButton(onClick = {
            runCatching { store.addReplacement(source, target); snapshot = store.snapshot(); source = ""; target = ""; scope.launch { EncryptedPersonalizationSync(context).sync() } }
                .onFailure { message = "Enter a short source and replacement." }
        }, enabled = source.isNotBlank() && target.isNotBlank()) { Text("Add replacement") }
        snapshot.replacements.forEach { item ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("${item.source} → ${item.target}", color = VaaniColor.Ink, fontSize = 13.sp, modifier = Modifier.weight(1f))
                OutlinedButton(onClick = { store.removeReplacement(item.id); snapshot = store.snapshot(); scope.launch { EncryptedPersonalizationSync(context).sync() } }) { Text("Remove") }
            }
        }
        message?.let { Text(it, color = VaaniColor.Muted, fontSize = 12.sp) }
    }
}

@Composable
private fun WorkspaceEmpty(message: String) {
    Box(Modifier.fillMaxWidth().height(460.dp)) {
        Column(Modifier.align(Alignment.Center), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(15.dp)) {
            VaaniRibbonSketch(Modifier.size(48.dp))
            Text(message, color = VaaniColor.Muted, fontSize = 15.sp, textAlign = TextAlign.Center)
        }
        Box(
            Modifier.align(Alignment.BottomEnd).size(56.dp).background(VaaniColor.Ink, CircleShape)
                .clickable { },
            contentAlignment = Alignment.Center,
        ) { Text("+", color = VaaniColor.Cloud, fontSize = 28.sp, fontWeight = FontWeight.Normal) }
    }
}

@Composable
private fun StyleWorkspace() {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Box(Modifier.fillMaxWidth().background(VaaniColor.Apricot, RoundedCornerShape(22.dp)).padding(20.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
                Text("MAKE VAANI SOUND LIKE YOU", color = VaaniColor.Plum, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                Text("Style your clean text for the places you write.", color = VaaniColor.Ink, fontFamily = FontFamily.Serif, fontSize = 24.sp, lineHeight = 27.sp)
                Text("Your selected account prepares the private on-device model in the background.", color = VaaniColor.Ink, fontSize = 13.sp, lineHeight = 18.sp)
            }
        }
        FlowStep("A", "Current style", "Clear, direct, and ready to edit.")
    }
}

@Composable
private fun AccountWorkspace(
    account: VaaniAccount?,
    message: String?,
    onClose: () -> Unit,
    onCreateSync: () -> Unit,
    onImportSync: (String) -> Unit,
    onSync: () -> Unit,
    onEmail: (String, String, Boolean) -> Unit,
    onGoogle: () -> Unit,
    onSignOut: () -> Unit,
) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var recoveryCode by remember { mutableStateOf("") }
    var create by remember { mutableStateOf(false) }
    Column(
        Modifier.fillMaxSize().background(VaaniColor.Paper).imePadding().padding(horizontal = 24.dp, vertical = 38.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("‹  Back", color = VaaniColor.Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.clickable { onClose() })
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Spacer(Modifier.height(8.dp))
            Text("Your Vaani account", color = VaaniColor.Ink, fontFamily = FontFamily.Serif, fontSize = 36.sp, lineHeight = 39.sp)
            Text(
                "Only vocabulary, snippets, and replacements can sync. Recordings and raw dictation are never put in Firestore.",
                color = VaaniColor.Muted, fontSize = 15.sp, lineHeight = 22.sp,
            )
            if (account != null) {
                Box(Modifier.fillMaxWidth().background(VaaniColor.Lilac, RoundedCornerShape(18.dp)).padding(18.dp)) {
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("SIGNED IN", color = VaaniColor.Plum, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                        Text(account.label, color = VaaniColor.Ink, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                        Text("Your model download starts on unmetered Wi-Fi.", color = VaaniColor.Ink, fontSize = 13.sp)
                    }
                }
                Text("Encrypted sync", color = VaaniColor.Ink, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text("Your personal words and links are encrypted before they leave this device.", color = VaaniColor.Muted, fontSize = 13.sp)
                OutlinedTextField(recoveryCode, { recoveryCode = it }, label = { Text("Recovery code for this device") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onCreateSync) { Text("Create recovery code") }
                    OutlinedButton(onClick = { onImportSync(recoveryCode) }, enabled = recoveryCode.isNotBlank()) { Text("Add this device") }
                }
                OutlinedButton(onClick = onSync) { Text("Sync encrypted data") }
            } else {
                OutlinedTextField(email, { email = it }, label = { Text("Email") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(password, { password = it }, label = { Text("Password (8+ characters)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            }
        }
        if (account != null) {
            VaaniSecondaryButton("Sign out", onSignOut)
        } else {
            VaaniPrimaryButton(if (create) "Create account" else "Sign in", { onEmail(email, password, create) })
            VaaniSecondaryButton(if (create) "I already have an account" else "Create with email", { create = !create })
            VaaniSecondaryButton("Continue with Google", onGoogle)
        }
        message?.let { Text(it, color = VaaniColor.Plum, fontSize = 13.sp, lineHeight = 19.sp) }
    }
}

@Composable
private fun VaaniRibbonSketch(modifier: Modifier = Modifier, main: Color = VaaniColor.Plum) {
    Canvas(modifier) {
        val stroke = size.minDimension * 0.12f
        val left = androidx.compose.ui.geometry.Offset(size.width * 0.18f, size.height * 0.25f)
        val bottom = androidx.compose.ui.geometry.Offset(size.width * 0.50f, size.height * 0.78f)
        val accentStart = androidx.compose.ui.geometry.Offset(size.width * 0.65f, size.height * 0.52f)
        val right = androidx.compose.ui.geometry.Offset(size.width * 0.82f, size.height * 0.25f)
        drawLine(main, left, bottom, strokeWidth = stroke, cap = androidx.compose.ui.graphics.StrokeCap.Round)
        drawLine(main, bottom, accentStart, strokeWidth = stroke, cap = androidx.compose.ui.graphics.StrokeCap.Round)
        drawLine(VaaniColor.Apricot, accentStart, right, strokeWidth = stroke, cap = androidx.compose.ui.graphics.StrokeCap.Round)
    }
}
