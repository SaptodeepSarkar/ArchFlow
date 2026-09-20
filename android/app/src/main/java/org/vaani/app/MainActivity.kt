package org.vaani.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import com.google.firebase.auth.FirebaseAuth

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
    var micGranted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
    }
    val micPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        micGranted = it
        if (it) page = 3
    }
    when (page) {
        0 -> OnboardingScreen(R.drawable.onboarding_arrival, 0, "Vaani", "Speak.\nWrite clearly.", "Private dictation that stays on your device.", "Get started") { page = 1 }
        1 -> OnboardingScreen(R.drawable.onboarding_keyboard, 1, "Works where you write", "Your voice,\nin every text field.", "Enable Vaani Keyboard once. Hold to speak, release to write.", "Enable Vaani Keyboard") {
            context.startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)); page = 2
        }
        2 -> OnboardingScreen(R.drawable.onboarding_ready, 2, "One last thing", "Ready when\nyou are.", if (micGranted) "Microphone access is ready. Open Vaani Keyboard in any text field." else "Vaani needs microphone access only while you choose to dictate.", if (micGranted) "Continue" else "Allow microphone") {
            if (micGranted) page = 3 else micPermission.launch(Manifest.permission.RECORD_AUDIO)
        }
        3 -> AuthScreen(onSignedIn = { page = 4 })
        else -> HomeScreen { context.startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) }
    }
}

@Composable
private fun AuthScreen(onSignedIn: () -> Unit) {
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
            Text("Skip for now", color = VaaniColor.Text, fontSize = 15.sp, fontWeight = FontWeight.Medium, modifier = Modifier.fillMaxWidth(), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
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

@Composable private fun HomeScreen(onOpenKeyboard: () -> Unit) {
    Column(Modifier.fillMaxSize().background(VaaniColor.Surface).padding(horizontal = 28.dp, vertical = 56.dp), verticalArrangement = Arrangement.SpaceBetween) {
        Column(verticalArrangement = Arrangement.spacedBy(22.dp)) {
            Text("Vaani", color = VaaniColor.Ink, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Text("Ready to write\nwhen you speak.", color = VaaniColor.Text, fontSize = 40.sp, lineHeight = 45.sp, fontWeight = FontWeight.SemiBold)
            Text("Open Vaani Keyboard in any text field, then press and hold to dictate.", color = VaaniColor.Muted, fontSize = 18.sp, lineHeight = 26.sp)
        }
        Button(onClick = onOpenKeyboard, modifier = Modifier.fillMaxWidth().height(56.dp).semantics { testTag = "enable_keyboard" }, shape = RoundedCornerShape(16.dp), colors = ButtonDefaults.buttonColors(containerColor = VaaniColor.Cobalt, contentColor = VaaniColor.Cloud)) { Text("Open keyboard settings", fontWeight = FontWeight.Bold, fontSize = 17.sp) }
    }
}
