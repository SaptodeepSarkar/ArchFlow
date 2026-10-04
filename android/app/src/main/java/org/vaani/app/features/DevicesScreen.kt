package org.vaani.app.features

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.google.zxing.BarcodeFormat
import com.google.zxing.MultiFormatWriter
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.*
import org.json.JSONObject
import org.vaani.app.*

@Composable
fun DevicesScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val pairing = remember { LocalPairing() }
    var busy by remember { mutableStateOf(false) }
    var host by remember { mutableStateOf(LocalPairing.addresses().firstOrNull().orEmpty()) }
    var invite by remember { mutableStateOf("") }
    var shown by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var pending by remember { mutableStateOf<JSONObject?>(null) }
    var include by remember { mutableStateOf(false) }
    DisposableEffect(Unit) { onDispose { pairing.close() } }
    val scanner =
        rememberLauncherForActivityResult(ScanContract()) { result ->
            result.contents?.let {
                invite = it
                message = "Invitation scanned. Compare the certificate fingerprint before sending."
            }
        }
    val image =
        remember(shown) {
            if (shown.isEmpty()) null
            else
                runCatching {
                        val matrix =
                            MultiFormatWriter().encode(shown, BarcodeFormat.QR_CODE, 480, 480)
                        android.graphics.Bitmap.createBitmap(
                                480,
                                480,
                                android.graphics.Bitmap.Config.ARGB_8888,
                            )
                            .apply {
                                for (y in 0..479) for (x in 0..479) setPixel(
                                    x,
                                    y,
                                    if (matrix[x, y]) android.graphics.Color.BLACK
                                    else android.graphics.Color.WHITE,
                                )
                            }
                    }
                    .getOrNull()
        }
    Column(
        Modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Devices", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Open both apps on the same reachable local network. Receive invitations expire after two minutes and are single-use. No cloud account or background discovery."
        )
        OutlinedTextField(
            value = host,
            onValueChange = { host = it },
            label = { Text("This device's local IPv4 address") },
            singleLine = true,
        )
        Button(
            enabled = !busy,
            onClick = {
                busy = true
                scope.launch {
                    runCatching {
                            val invitation = withContext(Dispatchers.IO) { pairing.prepare(host) }
                            shown = invitation.encode()
                            message =
                                "Compare fingerprint ${invitation.fingerprint.take(16)} on both devices"
                            pending = pairing.receive(invitation)
                            message =
                                "Received ${pending!!.getJSONArray("records").length()} records. Review and approve the merge."
                        }
                        .onFailure {
                            message =
                                "Receive failed: check network reachability, invitation and local permissions."
                        }
                    busy = false
                }
            },
        ) {
            Text("Receive / show QR")
        }
        image?.let {
            Image(it.asImageBitmap(), "Single-use pairing invitation", Modifier.size(240.dp))
        }
        if (shown.isNotEmpty())
            OutlinedTextField(
                value = shown,
                onValueChange = {},
                readOnly = true,
                label = { Text("Desktop pairing code — copy securely") },
            )
        OutlinedTextField(
            value = invite,
            onValueChange = { invite = it },
            label = { Text("Other device's invitation") },
        )
        Button(
            onClick = {
                scanner.launch(
                    ScanOptions()
                        .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                        .setPrompt("Scan Vaani's pairing QR")
                        .setBeepEnabled(false)
                )
            }
        ) {
            Text("Scan QR")
        }
        if (invite.isNotEmpty())
            Text(
                runCatching {
                        "Peer fingerprint: ${LocalPairing.parse(invite).fingerprint.take(16)}"
                    }
                    .getOrDefault("Invalid or expired invitation")
            )
        Row {
            Checkbox(checked = include, onCheckedChange = { include = it })
            Text("Include / apply portable language and retention preferences")
        }
        Button(
            enabled = !busy,
            onClick = {
                busy = true
                scope.launch {
                    runCatching { pairing.send(invite, LocalPairing.bundle(context, include)) }
                        .onSuccess { message = "Delivered; receiver approval is still required" }
                        .onFailure {
                            message =
                                "Transfer failed. Check the invitation, fingerprint and network."
                        }
                    busy = false
                }
            },
        ) {
            Text("Send personalization")
        }
        pending?.let { bundle ->
            Button(
                onClick = {
                    runCatching {
                            LocalPairing.validateBundle(bundle)
                            val records = bundle.getJSONArray("records")
                            PersonalizationStore(context)
                                .mergeBatch(
                                    (0 until records.length()).map { records.getJSONObject(it) }
                                )
                            if (include)
                                bundle.optJSONObject("preferences")?.let { prefs ->
                                    AppSettings.import(
                                        context,
                                        prefs.keys().asSequence().associateWith {
                                            prefs.getString(it)
                                        },
                                    )
                                }
                            pending = null
                            message = "Personalization merged"
                        }
                        .onFailure { message = "Import rejected; local data was preserved" }
                }
            ) {
                Text("Approve received merge")
            }
        }
        OutlinedButton(
            onClick = {
                pairing.close()
                shown = ""
                pending = null
                message = "Session closed"
            }
        ) {
            Text("Close session")
        }
        Text(message)
    }
}
