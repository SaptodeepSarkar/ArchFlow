package org.vaani.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Build
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.BorderStroke
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
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
import com.google.firebase.auth.FirebaseAuth
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        WindowCompat.getInsetsController(window, window.decorView).isAppearanceLightStatusBars = false
        WindowCompat.getInsetsController(window, window.decorView).isAppearanceLightNavigationBars = false
        setContent { VaaniTheme { VaaniApp() } }
    }
}

@Composable
private fun VaaniApp() {
    val context = LocalContext.current
    var page by remember { mutableIntStateOf(0) }
    var modelStatus by remember { mutableStateOf(LocalModels(context).status()) }
    var modelMessage by remember { mutableStateOf<String?>(null) }
    var overlayEnabled by remember { mutableStateOf(false) }
    val modelScope = rememberCoroutineScope()
    fun importModel(kind: ModelKind, uri: Uri) {
        modelScope.launch {
            val result = withContext(Dispatchers.IO) { ModelInstaller.install(context, kind, uri) }
            modelStatus = LocalModels(context).status()
            modelMessage = if (result.isSuccess) {
                if (kind == ModelKind.STT) "Whisper model installed locally." else "Llama cleanup model installed locally."
            } else "That model file could not be installed."
        }
    }
    val sttPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let { importModel(ModelKind.STT, it) } }
    val formatterPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let { importModel(ModelKind.FORMATTER, it) } }
    var micGranted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
    }
    val micPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        micGranted = it
        if (it) page = 8
    }
    when (page) {
        0 -> ProductIntroScreen(0, "4× faster\nthan typing", "Speak naturally. Vaani turns the thought in your head into clear words, without breaking your flow.", R.drawable.onboarding_arrival) { page = 1 }
        1 -> ProductIntroScreen(1, "100+\nlanguages", "From English to Hindi, Bengali, Spanish, and beyond — your voice can move the way you do.", R.drawable.onboarding_keyboard) { page = 2 }
        2 -> ProductIntroScreen(2, "Works in\nany app", "Messages, notes, search, email. If there is a text field, Vaani is already at home.", R.drawable.onboarding_ready) { page = 3 }
        3 -> AuthScreen(onSignedIn = { page = 4 }, onSkip = { page = 4 })
        4 -> ProductDemoScreen(onNext = { page = 5 })
        5 -> AccessibilitySetupScreen(onOpenAccessibility = {
            context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)); page = 6
        })
        6 -> FloatingSetupScreen(onEnableOverlay = {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context)) {
                context.startService(Intent(context, VoiceOverlayService::class.java)); page = 7
            } else {
                context.startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${context.packageName}")))
            }
        })
        7 -> MicSetupScreen(granted = micGranted, onRequestMicrophone = { if (micGranted) page = 8 else micPermission.launch(Manifest.permission.RECORD_AUDIO) })
        8 -> SafetyScreen(onNext = { page = 9 })
        9 -> SetupGuideScreen(onEnableOverlay = {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context)) {
                context.startService(Intent(context, VoiceOverlayService::class.java)); page = 10
            } else {
                context.startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${context.packageName}")))
            }
        })
        else -> HomeScreen(
            modelStatus = modelStatus,
            modelMessage = modelMessage,
            overlayEnabled = overlayEnabled,
            onToggleOverlay = {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(context)) {
                    context.startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${context.packageName}")))
                } else {
                    context.startService(Intent(context, VoiceOverlayService::class.java))
                    overlayEnabled = true
                }
            },
            onImportStt = { sttPicker.launch(arrayOf("*/*")) },
            onImportFormatter = { formatterPicker.launch(arrayOf("*/*")) },
        )
    }
}

private val introBackgrounds = listOf(
    Color(0xFFE8E9E5),
    Color(0xFFE6DDD2),
    Color(0xFFDDE5DE),
)

@Composable
private fun ProductIntroScreen(step: Int, title: String, body: String, art: Int, onNext: () -> Unit) {
    val transition = rememberInfiniteTransition(label = "intro-flow-$step")
    val drift by transition.animateFloat(
        initialValue = -22f,
        targetValue = 22f,
        animationSpec = infiniteRepeatable(tween(3600, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "drift",
    )
    val ink = Color(0xFF20231F)
    Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(introBackgrounds[step], introBackgrounds[step].copy(alpha = 0.76f), Color(0xFFF6F2EC))))) {
        Image(
            painter = painterResource(art), contentDescription = null,
            modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Fit, alpha = 0.10f,
        )
        FlowCharacter(step = step, drift = drift)
        Column(Modifier.fillMaxSize().padding(horizontal = 28.dp, vertical = 52.dp), verticalArrangement = Arrangement.SpaceBetween) {
            Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("Vaani", color = ink, fontSize = 25.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp)
                    Text("${step + 1} / 3", color = ink.copy(alpha = 0.56f), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                }
                Box(Modifier.fillMaxWidth().height(1.dp).background(ink.copy(alpha = 0.12f)))
                Text(title, color = ink, fontSize = 47.sp, lineHeight = 48.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.Normal)
                Text(body, color = ink.copy(alpha = 0.72f), fontSize = 18.sp, lineHeight = 27.sp, modifier = Modifier.fillMaxWidth(0.9f))
            }
            Column(verticalArrangement = Arrangement.spacedBy(22.dp)) {
                if (step == 0) VoicePill(drift = drift, ink = ink) else IntroChips(step, ink, drift)
                Button(
                    onClick = onNext,
                    modifier = Modifier.fillMaxWidth().height(56.dp).semantics { testTag = "onboarding_action" },
                    shape = RoundedCornerShape(18.dp),
                    border = BorderStroke(1.dp, ink.copy(alpha = 0.20f)),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE9E4FF), contentColor = ink),
                ) { Text(if (step == 0) "Meet Vaani" else "Keep going", fontWeight = FontWeight.Bold, fontSize = 17.sp) }
            }
        }
    }
}

@Composable
private fun VoicePill(drift: Float, ink: Color) {
    Box(
        Modifier.fillMaxWidth().height(116.dp).background(Color.White.copy(alpha = 0.68f), RoundedCornerShape(58.dp)).padding(horizontal = 22.dp, vertical = 18.dp),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.matchParentSize()) {
            val barColor = ink.copy(alpha = 0.22f)
            val count = 24
            val gap = size.width / (count + 1)
            for (index in 0 until count) {
                val wave = (kotlin.math.sin(index * 0.8 + drift / 10f).toFloat() + 1f) / 2f
                val barHeight = size.height * (0.18f + wave * 0.30f)
                drawRoundRect(barColor, topLeft = androidx.compose.ui.geometry.Offset(gap * (index + 1), (size.height - barHeight) / 2f), size = androidx.compose.ui.geometry.Size(3.dp.toPx(), barHeight), cornerRadius = androidx.compose.ui.geometry.CornerRadius(4.dp.toPx(), 4.dp.toPx()))
            }
        }
        Text("I am here to help you.", color = ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.offset(x = (drift / 2).dp).background(Color.White.copy(alpha = 0.78f), RoundedCornerShape(14.dp)).padding(horizontal = 12.dp, vertical = 8.dp))
    }
}

@Composable
private fun FlowCharacter(step: Int, drift: Float) {
    val accent = when (step) { 0 -> Color(0xFFFF7656); 1 -> Color(0xFF5C72D9); else -> Color(0xFF4B8E78) }
    Box(Modifier.fillMaxSize().offset(y = 92.dp).offset(x = (drift / 3).dp), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(230.dp)) {
            val center = androidx.compose.ui.geometry.Offset(size.width / 2f, size.height / 2f)
            drawCircle(accent.copy(alpha = 0.13f), radius = size.minDimension * 0.48f, center = center)
            drawCircle(accent.copy(alpha = 0.22f), radius = size.minDimension * 0.37f, center = center)
            drawRoundRect(Color.White.copy(alpha = 0.9f), topLeft = androidx.compose.ui.geometry.Offset(size.width * 0.29f, size.height * 0.26f), size = androidx.compose.ui.geometry.Size(size.width * 0.42f, size.height * 0.42f), cornerRadius = androidx.compose.ui.geometry.CornerRadius(42f, 42f))
            drawCircle(accent, radius = size.minDimension * 0.035f, center = androidx.compose.ui.geometry.Offset(size.width * 0.42f, size.height * 0.42f))
            drawCircle(accent, radius = size.minDimension * 0.035f, center = androidx.compose.ui.geometry.Offset(size.width * 0.58f, size.height * 0.42f))
            drawArc(accent, startAngle = 25f, sweepAngle = 130f, useCenter = false, topLeft = androidx.compose.ui.geometry.Offset(size.width * 0.41f, size.height * 0.40f), size = androidx.compose.ui.geometry.Size(size.width * 0.18f, size.height * 0.15f), style = androidx.compose.ui.graphics.drawscope.Stroke(width = 5f, cap = StrokeCap.Round))
            drawRoundRect(accent.copy(alpha = 0.9f), topLeft = androidx.compose.ui.geometry.Offset(size.width * 0.36f, size.height * 0.68f), size = androidx.compose.ui.geometry.Size(size.width * 0.28f, size.height * 0.16f), cornerRadius = androidx.compose.ui.geometry.CornerRadius(28f, 28f))
            drawLine(accent, androidx.compose.ui.geometry.Offset(size.width * 0.28f, size.height * 0.71f), androidx.compose.ui.geometry.Offset(size.width * 0.16f, size.height * 0.78f), strokeWidth = 9f, cap = StrokeCap.Round)
            drawLine(accent, androidx.compose.ui.geometry.Offset(size.width * 0.72f, size.height * 0.71f), androidx.compose.ui.geometry.Offset(size.width * 0.84f, size.height * 0.64f), strokeWidth = 9f, cap = StrokeCap.Round)
        }
        Box(Modifier.offset(y = (-112).dp).background(Color.White.copy(alpha = 0.76f), RoundedCornerShape(18.dp)).padding(horizontal = 14.dp, vertical = 9.dp)) {
            Text(if (step == 0) "Hi, I’m Vaani" else if (step == 1) "Say hello in any language" else "I’m here wherever you write", color = Color(0xFF20231F), fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun IntroChips(step: Int, ink: Color, drift: Float) {
    val labels = when (step) {
        0 -> listOf("listen", "understand", "write")
        1 -> listOf("English", "हिन्दी", "বাংলা", "Español")
        else -> listOf("Messages", "Notes", "Email", "Search")
    }
    if (step == 2) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                AppBadge("Messages", "M", Color(0xFF6B7CFF), ink, -2f + drift / 14f, Modifier.weight(1f))
                AppBadge("Notes", "N", Color(0xFFFF9B62), ink, 3f - drift / 16f, Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                AppBadge("Email", "@", Color(0xFF54A78B), ink, 2f - drift / 16f, Modifier.weight(1f))
                AppBadge("Search", "⌕", Color(0xFFB56CF2), ink, -3f + drift / 14f, Modifier.weight(1f))
            }
        }
    } else {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            labels.take(4).forEachIndexed { index, label ->
                Box(
                    Modifier.offset(x = (drift / 18f * if (index % 2 == 0) 1f else -1f).dp)
                        .background(Color.White.copy(alpha = 0.66f), RoundedCornerShape(16.dp))
                        .padding(horizontal = 11.dp, vertical = 10.dp)
                ) {
                    Text(label, color = ink.copy(alpha = 0.78f), fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@Composable
private fun AppBadge(label: String, glyph: String, accent: Color, ink: Color, bob: Float, modifier: Modifier) {
    Row(
        modifier = modifier
            .offset(y = bob.dp)
            .background(Color.White.copy(alpha = 0.72f), RoundedCornerShape(18.dp))
            .padding(horizontal = 11.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(9.dp),
    ) {
        Box(Modifier.size(34.dp).background(accent.copy(alpha = 0.18f), CircleShape), contentAlignment = Alignment.Center) {
            Text(glyph, color = accent, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }
        Text(label, color = ink.copy(alpha = 0.82f), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
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
            Text("The second line is the one you can use — polished, private, and ready for any text field.", color = VaaniColor.Muted, fontSize = 14.sp, lineHeight = 21.sp)
        }
        Button(onClick = onNext, modifier = Modifier.fillMaxWidth().height(56.dp), shape = RoundedCornerShape(18.dp), colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Cobalt, contentColor = VaaniColor.Cloud)) {
            Text("Show me how", fontWeight = FontWeight.Bold, fontSize = 17.sp)
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
private fun AuthScreen(onSignedIn: () -> Unit, onSkip: () -> Unit) {
    var message by remember { mutableStateOf("Sign in to keep your Vaani preferences ready when you need them.") }
    var working by remember { mutableStateOf(false) }
    Column(
        modifier = Modifier.fillMaxSize().background(VaaniColor.Surface).padding(horizontal = 28.dp, vertical = 56.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(32.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                repeat(4) { index -> Box(Modifier.weight(1f).height(3.dp).background(if (index == 3) VaaniColor.Cobalt else VaaniColor.Line)) }
            }
            Text("VAANI ACCOUNT", color = VaaniColor.Cobalt, fontSize = 13.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.1.sp)
            Text("Your settings,\nwhen you need them.", color = VaaniColor.Text, fontSize = 40.sp, lineHeight = 45.sp, fontWeight = FontWeight.SemiBold)
            Text(message, color = VaaniColor.Muted, fontSize = 18.sp, lineHeight = 26.sp, modifier = Modifier.fillMaxWidth(0.9f))
            Text("No recordings are uploaded. Vaani only creates a private account identity for future settings sync.", color = VaaniColor.Muted, fontSize = 14.sp, lineHeight = 21.sp)
        }
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Button(
                onClick = {
                    working = true
                    FirebaseAuth.getInstance().signInAnonymously().addOnCompleteListener { result ->
                        working = false
                        if (result.isSuccessful) onSignedIn() else message = "Could not sign in right now. Check your connection and try again."
                    }
                },
                enabled = !working,
                modifier = Modifier.fillMaxWidth().height(56.dp).semantics { testTag = "firebase_continue" },
                shape = RoundedCornerShape(16.dp),
                colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Cobalt, contentColor = VaaniColor.Cloud),
            ) { Text(if (working) "Connecting…" else "Continue securely", fontWeight = FontWeight.Bold, fontSize = 17.sp) }
            Text("Skip for now", color = VaaniColor.Text, fontSize = 15.sp, fontWeight = FontWeight.Medium, modifier = Modifier.fillMaxWidth().clickable(onClick = onSkip), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        }
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
        Column(Modifier.fillMaxSize().padding(horizontal = 28.dp, vertical = 52.dp), verticalArrangement = Arrangement.SpaceBetween) {
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

@Composable
private fun HomeScreen(
    modelStatus: ModelStatus,
    modelMessage: String?,
    overlayEnabled: Boolean,
    onToggleOverlay: () -> Unit,
    onImportStt: () -> Unit,
    onImportFormatter: () -> Unit,
) {
    Column(Modifier.fillMaxSize().background(VaaniColor.Surface).padding(horizontal = 28.dp, vertical = 56.dp), verticalArrangement = Arrangement.SpaceBetween) {
        Column(verticalArrangement = Arrangement.spacedBy(22.dp)) {
            Text("Vaani", color = VaaniColor.Ink, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Text("Ready to write\nwhen you speak.", color = VaaniColor.Text, fontSize = 40.sp, lineHeight = 45.sp, fontWeight = FontWeight.SemiBold)
            Text("Keep your normal keyboard. Hold the Vaani bubble above any text field, speak, then release to paste.", color = VaaniColor.Muted, fontSize = 18.sp, lineHeight = 26.sp)
            Text(if (modelStatus.sttAvailable) "Local Whisper model ready" else "Android offline speech fallback ready", color = VaaniColor.Cobalt, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            Text(if (modelStatus.formatterAvailable) "Local Llama cleanup enabled" else "Deterministic cleanup enabled", color = VaaniColor.Muted, fontSize = 14.sp)
            modelMessage?.let { Text(it, color = VaaniColor.Cobalt, fontSize = 14.sp) }
        }
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(onClick = onToggleOverlay, modifier = Modifier.fillMaxWidth().height(56.dp).semantics { testTag = "floating_button" }, shape = RoundedCornerShape(16.dp), colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Cobalt, contentColor = VaaniColor.Cloud)) { Text(if (overlayEnabled) "Floating button active" else "Enable floating button", fontWeight = FontWeight.Bold, fontSize = 17.sp) }
            OutlinedButton(onClick = onImportStt, modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, VaaniColor.Line), colors = ButtonDefaults.outlinedButtonColors(contentColor = VaaniColor.Ink)) { Text(if (modelStatus.sttAvailable) "Replace Whisper model" else "Install Whisper model", fontWeight = FontWeight.SemiBold) }
            OutlinedButton(onClick = onImportFormatter, modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, VaaniColor.Line), colors = ButtonDefaults.outlinedButtonColors(contentColor = VaaniColor.Ink)) { Text(if (modelStatus.formatterAvailable) "Replace Llama cleanup model" else "Install Llama cleanup model", fontWeight = FontWeight.SemiBold) }
        }
    }
}
