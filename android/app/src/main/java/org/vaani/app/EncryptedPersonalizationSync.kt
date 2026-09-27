package org.vaani.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.tasks.await
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.security.KeyStore
import java.security.SecureRandom
import java.util.UUID
import java.util.zip.GZIPInputStream
import java.util.zip.GZIPOutputStream
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Android half of the same gzip + AES-256-GCM envelope used by desktop. */
class EncryptedPersonalizationSync(private val context: Context) {
    private val keyStore = AndroidSyncKeyStore(context)

    private companion object {
        const val MAX_REMOTE_RECORDS = 2_000
        const val MAX_DECOMPRESSED_RECORD_BYTES = 64 * 1024
    }

    /** A notification wake-up pulls only, preventing a write-notify loop. */
    suspend fun sync(pushLocal: Boolean = true): Result<Unit> = runCatching {
        val auth = FirebaseRuntime.auth(context) ?: error(FirebaseRuntime.unavailableMessage())
        val firestore = FirebaseRuntime.app(context)?.let(FirebaseFirestore::getInstance)
            ?: error(FirebaseRuntime.unavailableMessage())
        val uid = auth.currentUser?.uid ?: error("Sign in before encrypted sync.")
        // Recovery keys are account-bound on a shared device.  A sign-out
        // followed by a different sign-in must not silently reuse the first
        // account's sync domain.
        val key = keyStore.load(uid) ?: error("Set up encrypted sync on this device first.")
        val store = PersonalizationStore(context)
        val deviceId = deviceId()
        val remote = firestore.collection("users").document(uid).collection("personalization").get().await()
        require(remote.size() <= MAX_REMOTE_RECORDS) { "Encrypted sync record limit exceeded." }
        remote.documents.forEach { document ->
            val record = decrypt(key, document.id, document.data ?: return@forEach)
            store.mergeSyncedRecord(record)
        }
        if (!pushLocal) return@runCatching
        store.syncRecords(deviceId).forEach { record ->
            val wrapper = record.keys().next()
            val body = record.getJSONObject(wrapper)
            firestore.collection("users").document(uid).collection("personalization")
                .document(body.getString("id"))
                .set(encrypt(
                    key, body.getString("id"), body.getLong("updated_at_ms"),
                    body.getLong("logical_clock"), body.getString("writer_device_id"),
                    body.getLong("revision"), record.toString(),
                ))
                .await()
        }
    }

    fun createRecoveryCode(): String {
        val uid = signedInUid()
        val key = ByteArray(32).also(SecureRandom()::nextBytes)
        keyStore.save(uid, key)
        return "VSK1-" + Base64.encodeToString(key, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
    }

    fun importRecoveryCode(code: String) {
        val uid = signedInUid()
        val encoded = code.trim().removePrefix("VSK1-")
        val key = Base64.decode(encoded, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        require(key.size == 32) { "Invalid recovery code" }
        keyStore.save(uid, key)
    }

    fun isConfiguredForCurrentAccount(): Boolean = FirebaseRuntime.auth(context)?.currentUser?.uid
        ?.let(keyStore::load) != null

    private fun signedInUid(): String = FirebaseRuntime.auth(context)?.currentUser?.uid
        ?: error("Sign in before setting up encrypted sync.")

    private fun encrypt(
        key: ByteArray, recordId: String, updatedAt: Long, logicalClock: Long,
        writerDeviceId: String, revision: Long, clear: String,
    ): Map<String, Any> {
        val nonce = ByteArray(12).also(SecureRandom()::nextBytes)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.ENCRYPT_MODE, javax.crypto.spec.SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce))
            updateAAD(associatedData(recordId, logicalClock, writerDeviceId, revision))
        }
        val compressed = ByteArrayOutputStream().use { bytes -> GZIPOutputStream(bytes).use { it.write(clear.toByteArray()) }; bytes.toByteArray() }
        return mapOf("schema_version" to 1L, "record_id" to recordId, "updated_at_ms" to updatedAt,
            "logical_clock" to logicalClock, "writer_device_id" to writerDeviceId, "revision" to revision,
            "compression" to "gzip", "cipher" to "aes-256-gcm",
            "nonce" to Base64.encodeToString(nonce, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING),
            "ciphertext" to Base64.encodeToString(cipher.doFinal(compressed), Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING))
    }

    private fun decrypt(key: ByteArray, recordId: String, fields: Map<String, Any>): JSONObject {
        require(fields["schema_version"] == 1L && fields["record_id"] == recordId && fields["compression"] == "gzip" && fields["cipher"] == "aes-256-gcm")
        val nonce = Base64.decode(fields["nonce"] as String, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        val ciphertext = Base64.decode(fields["ciphertext"] as String, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, javax.crypto.spec.SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce))
            updateAAD(associatedData(
                recordId,
                fields["logical_clock"] as Long,
                fields["writer_device_id"] as String,
                fields["revision"] as Long,
            ))
        }
        val clear = GZIPInputStream(ByteArrayInputStream(cipher.doFinal(ciphertext))).use { input ->
            val output = ByteArrayOutputStream()
            val buffer = ByteArray(8 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                require(output.size() + read <= MAX_DECOMPRESSED_RECORD_BYTES) { "Encrypted sync record is too large." }
                output.write(buffer, 0, read)
            }
            output.toString(Charsets.UTF_8.name())
        }
        return JSONObject(clear)
    }

    private fun deviceId(): String {
        val preferences = context.getSharedPreferences("vaani_sync_device", Context.MODE_PRIVATE)
        return preferences.getString("id", null) ?: UUID.randomUUID().toString().also { preferences.edit().putString("id", it).apply() }
    }

    private fun associatedData(recordId: String, logicalClock: Long, writerDeviceId: String, revision: Long) =
        "vaani-sync-envelope-v1:$recordId:$logicalClock:$writerDeviceId:$revision".toByteArray()
}

/** Encrypts the recovery key at rest with a non-exportable Android Keystore key. */
private class AndroidSyncKeyStore(private val context: Context) {
    fun save(uid: String, value: ByteArray) {
        val preferences = preferences(uid)
        val cipher = cipher(Cipher.ENCRYPT_MODE)
        preferences.edit().putString("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString("value", Base64.encodeToString(cipher.doFinal(value), Base64.NO_WRAP)).apply()
    }
    fun load(uid: String): ByteArray? {
        val preferences = preferences(uid)
        load(preferences)?.let { return it }
        // v1 stored one device-wide key. Bind it to the first account that
        // explicitly uses sync after upgrade, then erase the unscoped copy.
        // This preserves existing enrollment without leaving a reusable key
        // behind for a later account on the same device.
        val legacy = context.getSharedPreferences("vaani_sync_key", Context.MODE_PRIVATE)
        val value = load(legacy) ?: return null
        save(uid, value)
        legacy.edit().clear().apply()
        return value
    }
    private fun preferences(uid: String) = context.getSharedPreferences(
        "vaani_sync_key_${Base64.encodeToString(uid.toByteArray(), Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)}",
        Context.MODE_PRIVATE,
    )
    private fun load(preferences: android.content.SharedPreferences): ByteArray? {
        val iv = preferences.getString("iv", null) ?: return null
        val value = preferences.getString("value", null) ?: return null
        return cipher(Cipher.DECRYPT_MODE, Base64.decode(iv, Base64.NO_WRAP)).doFinal(Base64.decode(value, Base64.NO_WRAP))
    }
    private fun cipher(mode: Int, iv: ByteArray? = null): Cipher {
        val key = key()
        return Cipher.getInstance("AES/GCM/NoPadding").apply { init(mode, key, iv?.let { GCMParameterSpec(128, it) }) }
    }
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        return (store.getKey("vaani.sync.recovery", null) as? SecretKey) ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder("vaani.sync.recovery", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
}
