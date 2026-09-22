package org.vaani.app

import android.content.Context
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.Constraints
import androidx.work.workDataOf
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import javax.net.ssl.HttpsURLConnection

/**
 * Downloads only declared Android-compatible model assets. Every payload is
 * written to a private temporary file, SHA-256 checked, then atomically moved
 * into Vaani's files directory. The release manifest contains no user data.
 */
object ModelRelease {
    const val MANIFEST_URL = "https://github.com/SaptodeepSarkar/ArchFlow/releases/latest/download/android-models.json"
    private const val UNIQUE_WORK = "vaani-model-release"
    private const val PREFERENCES = "vaani_model_release"
    private const val KEY_STATUS = "status"
    const val PROGRESS_PHASE = "download_phase"
    const val PROGRESS_MODEL = "download_model"
    const val PROGRESS_DOWNLOADED_BYTES = "downloaded_bytes"
    const val PROGRESS_TOTAL_BYTES = "total_bytes"
    const val PROGRESS_PERCENT = "download_percent"
    const val PROGRESS_ETA_SECONDS = "download_eta_seconds"

    enum class Status {
        NOT_STARTED, QUEUED, DOWNLOADING, READY, WAITING_FOR_ANDROID_PACKAGE, FAILED,
    }

    fun enqueue(context: Context) {
        if (hasRequiredModels(context)) {
            WorkManager.getInstance(context).cancelUniqueWork(UNIQUE_WORK)
            update(context, Status.READY)
            return
        }
        update(context, Status.QUEUED)
        val request = OneTimeWorkRequestBuilder<ModelReleaseWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(UNIQUE_WORK, ExistingWorkPolicy.REPLACE, request)
    }

    fun status(context: Context): Status {
        if (hasRequiredModels(context)) return Status.READY
        return runCatching {
        Status.valueOf(context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .getString(KEY_STATUS, Status.NOT_STARTED.name) ?: Status.NOT_STARTED.name)
        }.getOrDefault(Status.NOT_STARTED)
    }

    fun isReady(context: Context): Boolean = hasRequiredModels(context)

    private fun hasRequiredModels(context: Context): Boolean =
        LocalModels(context).status().ready

    internal fun update(context: Context, status: Status) {
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .edit().putString(KEY_STATUS, status.name).apply()
    }
}

class ModelReleaseWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result = runCatching {
        ModelRelease.update(applicationContext, ModelRelease.Status.DOWNLOADING)
        val manifest = JSONObject(open(ModelRelease.MANIFEST_URL).bufferedReader().use { it.readText() })
        val models = manifest.optJSONArray("models") ?: error("The model release is missing its catalog.")
        val assets = buildList {
            for (index in 0 until models.length()) {
                val item = models.getJSONObject(index)
                if (!item.optBoolean("android_compatible", false)) continue
                val kind = when (item.getString("kind")) {
                    "stt" -> ModelKind.STT
                    "formatter" -> ModelKind.FORMATTER
                    "formatter_v6" -> ModelKind.FORMATTER_V6
                    else -> continue
                }
                add(ModelAsset(
                    kind = kind,
                    label = if (kind == ModelKind.STT) "Speech model" else "Cleanup model",
                    url = item.getString("url"),
                    sha256 = item.getString("sha256"),
                    expectedBytes = item.optLong("size_bytes", -1L),
                ))
            }
        }
        val knownTotalBytes = assets.map { it.expectedBytes }.takeIf { it.all { bytes -> bytes > 0L } }?.sum() ?: -1L
        val localModels = LocalModels(applicationContext)
        var completedBytes = 0L
        for (asset in assets) {
            if (localModels.modelFile(asset.kind) != null) {
                completedBytes += asset.expectedBytes.coerceAtLeast(0L)
                continue
            }
            completedBytes += downloadVerified(asset, completedBytes, knownTotalBytes)
        }
        if (assets.isEmpty()) {
            ModelRelease.update(applicationContext, ModelRelease.Status.WAITING_FOR_ANDROID_PACKAGE)
        } else if (localModels.status().ready) {
            ModelRelease.update(applicationContext, ModelRelease.Status.READY)
            notifyReady()
        } else {
            ModelRelease.update(applicationContext, ModelRelease.Status.FAILED)
        }
    }.fold(
        onSuccess = { Result.success() },
        onFailure = {
            if (runAttemptCount < 3) Result.retry() else {
                ModelRelease.update(applicationContext, ModelRelease.Status.FAILED)
                Result.failure()
            }
        },
    )

    private fun notifyReady() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(applicationContext, android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val manager = applicationContext.getSystemService(NotificationManager::class.java)
        val channel = "vaani-models"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(NotificationChannel(channel, "Vaani models", NotificationManager.IMPORTANCE_DEFAULT))
        }
        manager.notify(501, android.app.Notification.Builder(applicationContext, channel)
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle("Vaani is ready")
            .setContentText("Your private speech and cleanup models are ready on this device.")
            .setAutoCancel(true)
            .build())
    }

    private fun open(url: String) = (java.net.URL(url).openConnection() as HttpsURLConnection).apply {
        connectTimeout = 15_000
        readTimeout = 60_000
        instanceFollowRedirects = true
    }.inputStream

    private suspend fun downloadVerified(asset: ModelAsset, completedBytes: Long, knownTotalBytes: Long): Long {
        val destination = File(LocalModels(applicationContext).installPath(asset.kind), asset.kind.filename)
        val part = File(destination.parentFile, ".${destination.name}.part")
        val digest = MessageDigest.getInstance("SHA-256")
        var downloadedBytes = 0L
        var totalBytes = knownTotalBytes
        var lastPublishedAt = 0L
        var lastPublishedBytes = 0L
        val startedAt = System.nanoTime()

        suspend fun publish(phase: String, force: Boolean = false) {
            val now = System.nanoTime()
            if (!force && downloadedBytes - lastPublishedBytes < 512L * 1024L && now - lastPublishedAt < 250_000_000L) return
            val elapsedSeconds = (now - startedAt).coerceAtLeast(1L).toDouble() / 1_000_000_000.0
            val completeBytes = completedBytes + downloadedBytes
            val etaSeconds = if (totalBytes > 0L && downloadedBytes > 0L) {
                ((totalBytes - completeBytes).coerceAtLeast(0L) / (downloadedBytes / elapsedSeconds)).toLong()
            } else -1L
            val percent = if (totalBytes > 0L) ((completeBytes * 100L) / totalBytes).toInt().coerceIn(0, 100) else -1
            setProgress(workDataOf(
                ModelRelease.PROGRESS_PHASE to phase,
                ModelRelease.PROGRESS_MODEL to asset.label,
                ModelRelease.PROGRESS_DOWNLOADED_BYTES to completeBytes,
                ModelRelease.PROGRESS_TOTAL_BYTES to totalBytes,
                ModelRelease.PROGRESS_PERCENT to percent,
                ModelRelease.PROGRESS_ETA_SECONDS to etaSeconds,
            ))
            lastPublishedAt = now
            lastPublishedBytes = downloadedBytes
        }
        try {
            (java.net.URL(asset.url).openConnection() as HttpsURLConnection).apply {
                connectTimeout = 15_000
                readTimeout = 60_000
                instanceFollowRedirects = true
            }.let { connection ->
                val assetBytes = connection.contentLengthLong
                if (knownTotalBytes <= 0L && assetBytes > 0L) totalBytes = assetBytes
                connection.inputStream.use { input ->
                part.outputStream().use { output ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val read = input.read(buffer)
                        if (read < 0) break
                        output.write(buffer, 0, read)
                        digest.update(buffer, 0, read)
                        downloadedBytes += read
                        publish("Downloading")
                    }
                }
                }
            }
            publish("Verifying", force = true)
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            check(actual.equals(asset.sha256, ignoreCase = true)) { "Model checksum did not match the release manifest." }
            if (destination.exists()) check(destination.delete()) { "The incomplete model could not be replaced." }
            check(part.length() > 0L && part.renameTo(destination)) { "Model could not be activated." }
            publish("Verified", force = true)
            return downloadedBytes
        } finally {
            part.delete()
        }
    }

    private data class ModelAsset(
        val kind: ModelKind,
        val label: String,
        val url: String,
        val sha256: String,
        val expectedBytes: Long,
    )
}
