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
    internal const val MAX_MODEL_BYTES = 1_073_741_824L
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
            // These are large local model packages.  Deferring them until an
            // unmetered, non-low-battery window avoids an onboarding action
            // unexpectedly becoming a cellular or low-power background load.
            .setConstraints(Constraints.Builder()
                .setRequiredNetworkType(NetworkType.UNMETERED)
                .setRequiresBatteryNotLow(true)
                .setRequiresStorageNotLow(true)
                .build())
            .build()
        // Re-opening onboarding/settings must not cancel a running transfer
        // and start its network work over again.
        WorkManager.getInstance(context).enqueueUniqueWork(UNIQUE_WORK, ExistingWorkPolicy.KEEP, request)
    }

    fun status(context: Context): Status {
        if (hasRequiredModels(context)) return Status.READY
        val saved = runCatching {
            Status.valueOf(context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
                .getString(KEY_STATUS, Status.NOT_STARTED.name) ?: Status.NOT_STARTED.name)
        }.getOrDefault(Status.NOT_STARTED)
        return if (saved == Status.READY) Status.FAILED else saved
    }

    fun isReady(context: Context): Boolean = hasRequiredModels(context)

    private fun hasRequiredModels(context: Context): Boolean =
        isVerified(context, ModelKind.STT) && isVerified(context, ModelKind.FORMATTER)

    internal fun isVerified(context: Context, kind: ModelKind): Boolean {
        val file = LocalModels(context).modelFile(kind) ?: return false
        val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
        val prefix = "verified_${kind.name.lowercase()}_"
        return preferences.getString("${prefix}path", null) == file.absolutePath &&
            preferences.getLong("${prefix}length", -1L) == file.length() &&
            preferences.getLong("${prefix}modified", -1L) == file.lastModified() &&
            preferences.getString("${prefix}sha256", null)?.matches(Regex("[0-9a-fA-F]{64}")) == true
    }

    internal fun recordVerified(context: Context, kind: ModelKind, file: File, sha256: String) {
        val prefix = "verified_${kind.name.lowercase()}_"
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).edit()
            .putString("${prefix}path", file.absolutePath)
            .putLong("${prefix}length", file.length())
            .putLong("${prefix}modified", file.lastModified())
            .putString("${prefix}sha256", sha256)
            .apply()
    }

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
        val assets = mutableListOf<ModelAsset>()
        for (index in 0 until models.length()) {
            val item = models.getJSONObject(index)
            if (!item.optBoolean("android_compatible", false)) continue
            val kind = when (item.getString("kind")) {
                "stt" -> ModelKind.STT
                "stt_v6" -> ModelKind.STT_V6
                "formatter" -> ModelKind.FORMATTER
                "formatter_v6" -> ModelKind.FORMATTER_V6
                else -> continue
            }
            check(item.optString("runtime") == kind.runtime) {
                "Model runtime does not match its declared Android slot."
            }
            check(assets.none { asset -> asset.kind == kind }) {
                "The model release declares more than one asset for an Android slot."
            }
            assets += ModelAsset(
                kind = kind,
                label = when (kind) {
                    ModelKind.STT -> "Speech model"
                    ModelKind.STT_V6 -> "V6 speech candidate"
                    else -> "Cleanup model"
                },
                url = item.getString("url"),
                sha256 = item.getString("sha256"),
                expectedBytes = item.optLong("size_bytes", -1L),
            )
            check(assets.last().expectedBytes in 1L..MAX_MODEL_BYTES) {
                "Model size is missing or exceeds the Android download limit."
            }
            check(assets.last().sha256.matches(Regex("[0-9a-fA-F]{64}"))) {
                "Model checksum is invalid."
            }
            check(java.net.URL(assets.last().url).protocol.equals("https", ignoreCase = true)) {
                "Model downloads must use HTTPS."
            }
        }
        val knownTotalBytes = assets.map { it.expectedBytes }.takeIf { it.all { bytes -> bytes > 0L } }?.sum() ?: -1L
        var completedBytes = 0L
        for (asset in assets) {
            if (isVerified(applicationContext, asset.kind, asset.expectedBytes, asset.sha256)) {
                completedBytes += asset.expectedBytes.coerceAtLeast(0L)
                continue
            }
            completedBytes += downloadVerified(asset, completedBytes, knownTotalBytes)
        }
        if (assets.isEmpty()) {
            ModelRelease.update(applicationContext, ModelRelease.Status.WAITING_FOR_ANDROID_PACKAGE)
        } else if (ModelRelease.isReady(applicationContext)) {
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

    private fun open(url: String) = httpsConnection(url).inputStream

    private fun httpsConnection(address: String): HttpsURLConnection {
        var url = java.net.URL(address)
        repeat(MAX_REDIRECTS + 1) { redirectCount ->
            check(url.protocol.equals("https", ignoreCase = true)) { "Model downloads must use HTTPS." }
            val connection = url.openConnection() as HttpsURLConnection
            connection.connectTimeout = 15_000
            connection.readTimeout = 60_000
            connection.instanceFollowRedirects = false
            val response = connection.responseCode
            if (response !in REDIRECT_CODES) return connection
            val location = connection.getHeaderField("Location")
            connection.disconnect()
            check(redirectCount < MAX_REDIRECTS && !location.isNullOrBlank()) { "Model download redirect is invalid." }
            url = java.net.URL(url, location)
        }
        error("Too many model download redirects.")
    }

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
            httpsConnection(asset.url).let { connection ->
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
                        check(downloadedBytes <= asset.expectedBytes && downloadedBytes <= ModelRelease.MAX_MODEL_BYTES) {
                            "Model download exceeded its declared size."
                        }
                        publish("Downloading")
                    }
                }
                }
            }
            publish("Verifying", force = true)
            check(downloadedBytes == asset.expectedBytes) { "Model size did not match the release manifest." }
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            check(actual.equals(asset.sha256, ignoreCase = true)) { "Model checksum did not match the release manifest." }
            if (destination.exists()) check(destination.delete()) { "The incomplete model could not be replaced." }
            check(part.length() > 0L && part.renameTo(destination)) { "Model could not be activated." }
            ModelRelease.recordVerified(applicationContext, asset.kind, destination, actual)
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

    private fun isVerified(context: Context, kind: ModelKind, expectedBytes: Long, expectedSha256: String): Boolean {
        if (!ModelRelease.isVerified(context, kind)) return false
        val preferences = context.getSharedPreferences("vaani_model_release", Context.MODE_PRIVATE)
        val prefix = "verified_${kind.name.lowercase()}_"
        val file = LocalModels(context).modelFile(kind) ?: return false
        return file.length() == expectedBytes &&
            preferences.getString("${prefix}sha256", null).equals(expectedSha256, ignoreCase = true)
    }

    private companion object {
        const val MAX_REDIRECTS = 5
        val REDIRECT_CODES = setOf(301, 302, 303, 307, 308)
    }
}
