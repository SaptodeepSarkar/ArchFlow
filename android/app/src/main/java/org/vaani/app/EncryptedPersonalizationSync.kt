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
    private val auth = FirebaseAuth.getInstance()
    private val firestore = FirebaseFirestore.getInstance()
    private val keyStore = AndroidSyncKeyStore(context)

    /** A notification wake-up pulls only, preventing a write-notify loop. */
    suspend fun sync(pushLocal: Boolean = true): Result<Unit> = runCatching {
        val uid = auth.currentUser?.uid ?: error("Sign in before encrypted sync.")
        val key = keyStore.load() ?: error("Set up encrypted sync on this device first.")
        val store = PersonalizationStore(context)
        val deviceId = deviceId()
        val remote = firestore.collection("users").document(uid).collection("personalization").get().await()
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
                .set(encrypt(key, body.getString("id"), body.getLong("updated_at_ms"), record.toString()))
                .await()
        }
    }

    fun createRecoveryCode(): String {
        val key = ByteArray(32).also(SecureRandom()::nextBytes)
        keyStore.save(key)
        return "VSK1-" + Base64.encodeToString(key, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
    }

    fun importRecoveryCode(code: String) {
        val encoded = code.trim().removePrefix("VSK1-")
        val key = Base64.decode(encoded, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        require(key.size == 32) { "Invalid recovery code" }
        keyStore.save(key)
    }

    private fun encrypt(key: ByteArray, recordId: String, updatedAt: Long, clear: String): Map<String, Any> {
        val nonce = ByteArray(12).also(SecureRandom()::nextBytes)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.ENCRYPT_MODE, javax.crypto.spec.SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce))
            updateAAD("vaani-sync-envelope-v1:$recordId".toByteArray())
        }
        val compressed = ByteArrayOutputStream().use { bytes -> GZIPOutputStream(bytes).use { it.write(clear.toByteArray()) }; bytes.toByteArray() }
        return mapOf("schema_version" to 1L, "record_id" to recordId, "updated_at_ms" to updatedAt,
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
            updateAAD("vaani-sync-envelope-v1:$recordId".toByteArray())
        }
        val clear = GZIPInputStream(ByteArrayInputStream(cipher.doFinal(ciphertext))).readBytes().toString(Charsets.UTF_8)
        return JSONObject(clear)
    }

    private fun deviceId(): String {
        val preferences = context.getSharedPreferences("vaani_sync_device", Context.MODE_PRIVATE)
        return preferences.getString("id", null) ?: UUID.randomUUID().toString().also { preferences.edit().putString("id", it).apply() }
    }
}

/** Encrypts the recovery key at rest with a non-exportable Android Keystore key. */
private class AndroidSyncKeyStore(context: Context) {
    private val preferences = context.getSharedPreferences("vaani_sync_key", Context.MODE_PRIVATE)
    fun save(value: ByteArray) {
        val cipher = cipher(Cipher.ENCRYPT_MODE)
        preferences.edit().putString("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString("value", Base64.encodeToString(cipher.doFinal(value), Base64.NO_WRAP)).apply()
    }
    fun load(): ByteArray? {
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
