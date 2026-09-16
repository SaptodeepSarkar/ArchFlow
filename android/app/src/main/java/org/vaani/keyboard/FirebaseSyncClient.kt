package org.vaani.keyboard

import com.google.android.gms.tasks.Task
import com.google.android.gms.tasks.Tasks
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.SetOptions

data class SyncSummary(val uploaded: Int, val downloaded: Int)

/**
 * Optional Firestore bridge for personalization only. Dictation never calls
 * this class, and no audio, raw transcript, or password-field content enters
 * its payloads.
 */
class FirebaseSyncClient(private val store: PersonalizationStore) {
    private val auth: FirebaseAuth? = runCatching { FirebaseAuth.getInstance() }.getOrNull()
    private val firestore: FirebaseFirestore? = runCatching { FirebaseFirestore.getInstance() }.getOrNull()

    fun email(): String? = auth?.currentUser?.email

    fun signIn(email: String, password: String, done: (Result<String>) -> Unit) {
        val auth = auth ?: return done(Result.failure(offlineConfigError()))
        auth.signInWithEmailAndPassword(email.trim(), password).addOnCompleteListener { task ->
            if (task.isSuccessful) done(Result.success(auth.currentUser?.email.orEmpty()))
            else done(Result.failure(task.exception ?: IllegalStateException("Sign-in failed")))
        }
    }

    fun createAccount(email: String, password: String, done: (Result<String>) -> Unit) {
        val auth = auth ?: return done(Result.failure(offlineConfigError()))
        auth.createUserWithEmailAndPassword(email.trim(), password).addOnCompleteListener { task ->
            if (task.isSuccessful) done(Result.success(auth.currentUser?.email.orEmpty()))
            else done(Result.failure(task.exception ?: IllegalStateException("Account creation failed")))
        }
    }

    fun signOut() = auth?.signOut()

    fun sync(done: (Result<SyncSummary>) -> Unit) = syncTask().addOnCompleteListener { task ->
        if (task.isSuccessful) done(Result.success(task.result))
        else done(Result.failure(task.exception ?: IllegalStateException("Sync failed")))
    }

    /** Blocking entry point for a bounded background worker; never called by dictation. */
    fun syncBlocking(): SyncSummary = Tasks.await(syncTask())

    private fun syncTask(): Task<SyncSummary> {
        val user = auth?.currentUser
        requireNotNull(user) { "Sign in to sync personalization" }
        val firestore = firestore ?: throw offlineConfigError()
        val collection = firestore.collection("users").document(user.uid).collection("personalization")
        val local = PersonalizationStore.Kind.entries.flatMap { kind ->
            store.syncEntries(kind).map { entry -> payload(kind, entry) }
        }
        var chain: Task<Void> = Tasks.forResult(null)
        local.chunked(450).forEach { chunk ->
            chain = chain.continueWithTask {
                val batch = firestore.batch()
                chunk.forEach { item ->
                    @Suppress("UNCHECKED_CAST")
                    batch.set(collection.document(item.first), item.second as Map<String, Any?>, SetOptions.merge())
                }
                batch.commit()
            }
        }
        return chain.continueWithTask { collection.get() }.continueWith { task ->
            if (!task.isSuccessful) throw task.exception ?: IllegalStateException("Sync failed")
            var downloaded = 0
            task.result.documents.forEach { document ->
                if (merge(document)) downloaded++
            }
            SyncSummary(local.size, downloaded)
        }
    }

    private fun payload(kind: PersonalizationStore.Kind, entry: PersonalizationEntry): Pair<String, Map<String, Any?>> {
        val entity = when (kind) {
            PersonalizationStore.Kind.VOCABULARY -> "vocabulary"
            PersonalizationStore.Kind.SNIPPET -> "snippet"
            PersonalizationStore.Kind.REPLACEMENT -> "replacement"
        }
        val value: Map<String, Any?>? = if (entry.deletedAtMs == null) when (kind) {
            PersonalizationStore.Kind.VOCABULARY -> mapOf("id" to entry.id, "canonical" to entry.trigger, "spoken_aliases" to entry.spokenAliases, "category" to null, "created_at_ms" to entry.updatedAtMs, "updated_at_ms" to entry.updatedAtMs)
            PersonalizationStore.Kind.SNIPPET -> mapOf("id" to entry.id, "trigger" to entry.trigger, "value" to entry.value, "created_at_ms" to entry.updatedAtMs, "updated_at_ms" to entry.updatedAtMs)
            PersonalizationStore.Kind.REPLACEMENT -> mapOf("id" to entry.id, "source" to entry.trigger, "target" to entry.value, "created_at_ms" to entry.updatedAtMs, "updated_at_ms" to entry.updatedAtMs)
        } else null
        return entry.id to mapOf(
            "schema_version" to 1,
            "entity" to entity,
            "id" to entry.id,
            "revision" to entry.revision,
            "logical_clock" to entry.logicalClock,
            "writer_device_id" to entry.writerDeviceId.ifBlank { store.deviceId },
            "updated_at_ms" to entry.updatedAtMs,
            "deleted_at_ms" to entry.deletedAtMs,
            "value" to value,
        )
    }

    private fun merge(document: com.google.firebase.firestore.DocumentSnapshot): Boolean {
        val entity = document.getString("entity") ?: return false
        val kind = when (entity) {
            "vocabulary" -> PersonalizationStore.Kind.VOCABULARY
            "snippet" -> PersonalizationStore.Kind.SNIPPET
            "replacement" -> PersonalizationStore.Kind.REPLACEMENT
            else -> return false
        }
        val id = document.getString("id") ?: document.id
        val revision = document.getLong("revision") ?: return false
        val updated = document.getLong("updated_at_ms") ?: return false
        val deleted = document.getLong("deleted_at_ms")
        val value = document.get("value") as? Map<*, *>
        val trigger: String
        val replacement: String
        val aliases: List<String>
        if (deleted != null || value == null) {
            trigger = ""
            replacement = ""
            aliases = emptyList()
        } else when (kind) {
            PersonalizationStore.Kind.VOCABULARY -> {
                trigger = value["canonical"] as? String ?: return false
                replacement = ""
                aliases = (value["spoken_aliases"] as? List<*>)?.filterIsInstance<String>().orEmpty()
            }
            PersonalizationStore.Kind.SNIPPET -> {
                trigger = value["trigger"] as? String ?: return false
                replacement = value["value"] as? String ?: return false
                aliases = emptyList()
            }
            PersonalizationStore.Kind.REPLACEMENT -> {
                trigger = value["source"] as? String ?: return false
                replacement = value["target"] as? String ?: return false
                aliases = emptyList()
            }
        }
        val logicalClock = document.getLong("logical_clock") ?: revision
        val writerDeviceId = document.getString("writer_device_id") ?: return false
        return store.mergeRemote(kind, id, trigger, replacement, revision, logicalClock, writerDeviceId, updated, deleted, aliases)
    }

    private fun offlineConfigError() = IllegalStateException("Firebase sync is not configured for this build")
}
