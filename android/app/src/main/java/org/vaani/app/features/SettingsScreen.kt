package org.vaani.app.features
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import org.vaani.app.*
@Composable fun SettingsScreen(){
 val context=LocalContext.current;var language by remember {mutableStateOf(OnboardingState.writingLanguage(context))};var profile by remember {mutableStateOf(AppSettings.profile(context))};var seconds by remember {mutableStateOf(AppSettings.retentionSeconds(context).toString())};var formatter by remember {mutableStateOf(AppSettings.formatterEnabled(context))};var message by remember {mutableStateOf("")}
 Column(verticalArrangement=Arrangement.spacedBy(12.dp)){
  Text("Settings",style=MaterialTheme.typography.headlineMedium)
  Text("Writing language");Row {listOf("en","hi","bn").forEach {value->FilterChip(selected=language==value,onClick={language=value},label={Text(value)})}}
  Text("Model retention");Row {listOf("economy","balanced").forEach {value->FilterChip(selected=profile==value,onClick={profile=value},label={Text(value)})}}
  Text("Economy unloads after every operation. Balanced retains models briefly after use; nothing is loaded at launch.")
  OutlinedTextField(value=seconds,onValueChange={seconds=it},label={Text("Idle retention seconds (1–120)")},singleLine=true)
  Row {Text("Optional formatter");Switch(checked=formatter,onCheckedChange={formatter=it})}
  Button(onClick={runCatching {AppSettings.update(context,profile,seconds.toLong(),formatter);OnboardingState.setWritingLanguage(context,language)}.onSuccess {message="Settings saved"}.onFailure {message="Enter retention between 1 and 120 seconds"}}){Text("Save settings")}
  OutlinedButton(onClick={ModelLifecycle.unload();message="Unload requested; active inference finishes safely first"}){Text("Unload models")}
  Text(message)
 }
}
