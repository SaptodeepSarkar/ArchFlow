package org.vaani.app.features
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.*
import org.vaani.app.*
@Composable fun ModelsScreen(){val context=LocalContext.current;val scope=rememberCoroutineScope();var slot by remember {mutableStateOf(ModelKind.STT)};var message by remember {mutableStateOf("")};var status by remember {mutableStateOf(LocalModels(context).status())};val picker=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()){uri->if(uri!=null)scope.launch {val result=withContext(Dispatchers.IO){ModelInstaller.install(context,slot,uri)};message=result.fold({"Imported model format checked. User-selected files have no release authenticity guarantee."},{"Model import failed; your previous model was preserved."});status=LocalModels(context).status()}}
 Column(verticalArrangement=Arrangement.spacedBy(12.dp)) {Text("Models",style=MaterialTheme.typography.headlineMedium);Text("Installed files stay on disk. Model weights load only during dictation or formatting.");Text("Speech installed: ${status.sttAvailable} · Formatter installed: ${status.formatterAvailable}")
 Row {ModelKind.entries.forEach {kind->FilterChip(selected=slot==kind,onClick={slot=kind},label={Text(kind.name)})}}
 Button(onClick={picker.launch(arrayOf("application/octet-stream","*/*"))}){Text("Import offline model")}
 Button(onClick={ModelRelease.enqueue(context);message="Download queued for unmetered Wi-Fi; checksums will be verified."}){Text("Download verified speech pack")}
 OutlinedButton(onClick={ModelRelease.enqueue(context,true);message="Optional formatter download queued"}){Text("Download speech and formatter packs")}
 OutlinedButton(onClick={androidx.work.WorkManager.getInstance(context).cancelUniqueWork("vaani-model-release");message="Download cancelled"}){Text("Cancel download")}
 Text(message);Text("Release state: ${ModelRelease.status(context)}");OutlinedButton(onClick={status=LocalModels(context).status();message="Status refreshed"}){Text("Refresh")}
 }}
