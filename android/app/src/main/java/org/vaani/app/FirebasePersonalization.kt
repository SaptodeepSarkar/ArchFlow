package org.vaani.app

import android.content.Context
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.tasks.await

/**
 * The only Android Firestore surface. The document path and envelope match
 * firestore.rules exactly; there is intentionally no API for recordings,
 * raw dictations, clipboard content, tokens, or arbitrary profile documents.
 */
class FirebasePersonalization(private val context: Context) {
    private val auth = FirebaseAuth.getInstance()
    private val firestore = FirebaseFirestore.getInstance()

    suspend fun read(): Result<List<Map<String, Any?>>> = runCatching {
        val uid = auth.currentUser?.uid ?: error("Sign in before syncing preferences.")
        firestore.collection("users").document(uid).collection("personalization")
            .limit(MAX_RECORDS.toLong())
            .get()
            .await()
            .documents
            .mapNotNull { it.data }
    }

    suspend fun saveVocabulary(
        id: String,
        canonical: String,
        aliases: List<String>,
        category: String?,
        revision: Long,
        logicalClock: Long,
        writerDeviceId: String,
        nowMs: Long = System.currentTimeMillis(),
    ): Result<Unit> = save(
        id = id,
        entity = "vocabulary",
        revision = revision,
        logicalClock = logicalClock,
        writerDeviceId = writerDeviceId,
        value = mapOf(
            "id" to id,
            "canonical" to canonical.take(MAX_WORD),
            "spoken_aliases" to aliases.map { it.take(MAX_WORD) },
            "category" to category?.take(MAX_WORD),
            "created_at_ms" to nowMs,
            "updated_at_ms" to nowMs,
        ),
        nowMs = nowMs,
    )

    private suspend fun save(
        id: String,
        entity: String,
        revision: Long,
        logicalClock: Long,
        writerDeviceId: String,
        value: Map<String, Any?>,
        nowMs: Long,
    ): Result<Unit> = runCatching {
        val uid = auth.currentUser?.uid ?: error("Sign in before syncing preferences.")
        require(id.isNotBlank() && id.length <= 128)
        require(writerDeviceId.isNotBlank() && writerDeviceId.length <= 128)
        firestore.collection("users").document(uid).collection("personalization").document(id)
            .set(
                mapOf(
                    "schema_version" to 1L,
                    "entity" to entity,
                    "id" to id,
                    "revision" to revision.coerceAtLeast(0),
                    "logical_clock" to logicalClock.coerceAtLeast(0),
                    "writer_device_id" to writerDeviceId,
                    "updated_at_ms" to nowMs,
                    "deleted_at_ms" to null,
                    "value" to value,
                ),
            )
            .await()
    }

    private companion object {
        const val MAX_RECORDS = 500
        const val MAX_WORD = 500
    }
}
