package org.vaani.app

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
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
            SyncWork.enqueue(applicationContext)
        }
    }

    companion object {
        /** Registers the existing FCM token immediately after account sign-in. */
        fun registerCurrentDevice(context: Context) {
            if (FirebaseRuntime.app(context) == null) return
            FirebaseMessaging.getInstance().token.addOnSuccessListener { token ->
                registerDevice(context.applicationContext, token)
            }
        }

        private fun registerDevice(context: Context, token: String) {
            val app = FirebaseRuntime.app(context) ?: return
            val uid = FirebaseAuth.getInstance(app).currentUser?.uid ?: return
            val prefs = context.getSharedPreferences("vaani_sync_device", Context.MODE_PRIVATE)
            val id = prefs.getString("id", null) ?: UUID.randomUUID().toString().also { prefs.edit().putString("id", it).apply() }
            FirebaseFirestore.getInstance(app).collection("users").document(uid).collection("devices").document(id)
                .set(mapOf("schema_version" to 1L, "device_id" to id, "platform" to "android", "push_token" to token, "updated_at_ms" to System.currentTimeMillis()))
        }
    }
}

class EncryptedSyncWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = EncryptedPersonalizationSync(applicationContext).sync(pushLocal = false)
        .fold(
            onSuccess = { Result.success() },
            // FCM wakeups can be duplicated and invalid account/recovery-key
            // state will not become valid by retrying forever.  WorkManager's
            // exponential retry remains useful for short network outages, but
            // stop after a small bounded number of attempts; the next FCM
            // wakeup or explicit Sync starts a fresh cycle.
            onFailure = { if (SyncWork.shouldRetry(runAttemptCount)) Result.retry() else Result.failure() },
        )
}

internal object SyncWork {
    private const val UNIQUE_WORK = "vaani-encrypted-sync"
    private const val MAX_RETRIES = 3

    fun enqueue(context: Context) {
        val request = OneTimeWorkRequestBuilder<EncryptedSyncWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        // One pull is enough: FCM signals availability, not individual
        // records. Coalescing prevents a burst from keeping the app awake.
        WorkManager.getInstance(context).enqueueUniqueWork(UNIQUE_WORK, ExistingWorkPolicy.KEEP, request)
    }

    internal fun shouldRetry(runAttemptCount: Int): Boolean = runAttemptCount < MAX_RETRIES
}
