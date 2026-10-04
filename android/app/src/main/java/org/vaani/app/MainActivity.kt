package org.vaani.app

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.vaani.app.features.*

class MainActivity : ComponentActivity() {
    private val microphone=registerForActivityResult(ActivityResultContracts.RequestPermission()) { }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Retire old queued Firebase work without erasing user vocabulary or recovery material.
        androidx.work.WorkManager.getInstance(this).cancelUniqueWork("vaani-encrypted-sync")
        setContent { VaaniTheme {
            var page by rememberSaveable { mutableStateOf("Home") }
            Surface(color=VaaniColor.Paper) {
                Column(Modifier.fillMaxSize().padding(16.dp)) {
                    Text("Vaani",style=MaterialTheme.typography.headlineLarge,color=VaaniColor.Cobalt)
                    Text("Your voice. Your device.",style=MaterialTheme.typography.bodyMedium)
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
                        listOf("Home","Models","Words","Settings","Devices").forEach { target -> TextButton(onClick={page=target}) {Text(target)} }
                    }
                    when(page) {
                        "Home"->HomeScreen(
                            onMicrophone={microphone.launch(Manifest.permission.RECORD_AUDIO)},
                            onOverlay={startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,Uri.parse("package:$packageName")))},
                            onAccessibility={startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))},
                            onShow={startService(Intent(this@MainActivity,VoiceOverlayService::class.java))},
                            onHide={stopService(Intent(this@MainActivity,VoiceOverlayService::class.java))})
                        "Models"->ModelsScreen()
                        "Words"->PersonalizationScreen()
                        "Settings"->SettingsScreen()
                        "Devices"->DevicesScreen()
                    }
                }
            }
        } }
    }
}
