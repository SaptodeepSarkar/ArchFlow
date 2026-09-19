package org.vaani.keyboard

import android.content.Context
import androidx.work.Worker
import androidx.work.WorkerParameters

/** Uploads and merges only structured personalization; audio and dictations never enter this worker. */
class PersonalizationSyncWorker(context: Context, params: WorkerParameters) : Worker(context, params) {
    override fun doWork(): Result {
        val client = FirebaseSyncClient(PersonalizationStore(applicationContext))
        if (client.email() == null) return Result.success()
        return runCatching { client.syncBlocking(); Result.success() }
            .getOrElse { if (runAttemptCount < 3) Result.retry() else Result.failure() }
    }
}
