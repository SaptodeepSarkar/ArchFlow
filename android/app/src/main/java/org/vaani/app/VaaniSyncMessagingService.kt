package org.vaani.app

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.tasks.await
import java.util.UUID

/** Receives an opaque wake-up signal only; no vocabulary or dictation travels in FCM. */
class VaaniSyncMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) { registerDevice(applicationContext, token) }
    override fun onMessageReceived(message: RemoteMessage) {
        if (message.data["kind"] == "sync_available") {
            WorkManager.getInstance(applicationContext).enqueue(OneTimeWorkRequestBuilder<EncryptedSyncWorker>().build())
        }
    }

    companion object {
        /** Registers the existing FCM token immediately after account sign-in. */
        fun registerCurrentDevice(context: Context) {
            FirebaseMessaging.getInstance().token.addOnSuccessListener { token ->
                registerDevice(context.applicationContext, token)
            }
        }

        private fun registerDevice(context: Context, token: String) {
            val uid = FirebaseAuth.getInstance().currentUser?.uid ?: return
            val prefs = context.getSharedPreferences("vaani_sync_device", Context.MODE_PRIVATE)
            val id = prefs.getString("id", null) ?: UUID.randomUUID().toString().also { prefs.edit().putString("id", it).apply() }
            FirebaseFirestore.getInstance().collection("users").document(uid).collection("devices").document(id)
                .set(mapOf("schema_version" to 1L, "device_id" to id, "platform" to "android", "push_token" to token, "updated_at_ms" to System.currentTimeMillis()))
        }
    }
}

class EncryptedSyncWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = EncryptedPersonalizationSync(applicationContext).sync(pushLocal = false)
        .fold(onSuccess = { Result.success() }, onFailure = { Result.retry() })
}
