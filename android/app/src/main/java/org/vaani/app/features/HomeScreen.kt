package org.vaani.app.features
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import org.vaani.app.*
@Composable fun HomeScreen(onMicrophone:()->Unit,onOverlay:()->Unit,onAccessibility:()->Unit,onShow:()->Unit,onHide:()->Unit) {
    val context=LocalContext.current;val access=OnboardingState.access(context);val models=LocalModels(context).status()
    Column(Modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(14.dp)) {
        Text("Speak naturally. Vaani writes.",style=MaterialTheme.typography.headlineMedium)
        Text("Hold the floating control to dictate. Release to finish. Audio and formatting stay on this device.")
        Text(access.summary)
        Text(if(models.sttAvailable) "Speech model installed" else "Install a speech model, or use an available Android offline recognizer.")
        Text(if(models.formatterAvailable) "Formatter installed — loaded only when needed" else "Formatter optional — conservative text formatting available")
        Button(onClick=onMicrophone){Text("Microphone permission")}
        OutlinedButton(onClick=onOverlay){Text("Floating control permission")}
        OutlinedButton(onClick=onAccessibility){Text("Text-box access")}
        Button(onClick=onShow,enabled=access.microphone&&access.overlay&&access.textBoxAccess){Text("Show floating control")}
        OutlinedButton(onClick=onHide){Text("Hide floating control")}
    }
}
