package org.vaani.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONObject

/** Small encrypted repository with durable atomic writes and verified legacy migration. */
internal class EncryptedPreferences private constructor(context: Context) {
    private val file = AtomicFile(File(context.filesDir, "personalization.enc"))
    private val key: SecretKey
    private var values: JSONObject
    private var transaction = false

    init {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        key =
            (store.getKey("vaani.local.personalization.v1", null) as? SecretKey)
                ?: run {
                    check(!(file.baseFile.exists() || File(file.baseFile.path + ".bak").exists())) {
                        "The personalization key is missing. Preserve the data and restore a verified backup."
                    }
                    KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
                        .apply {
                            init(
                                KeyGenParameterSpec.Builder(
                                        "vaani.local.personalization.v1",
                                        KeyProperties.PURPOSE_ENCRYPT or
                                            KeyProperties.PURPOSE_DECRYPT,
                                    )
                                    .setKeySize(256)
                                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                                    .build()
                            )
                        }
                        .generateKey()
                }
        if (file.baseFile.exists() || File(file.baseFile.path + ".bak").exists())
            values = decrypt(file.readFully())
        else {
            val legacy =
                context.getSharedPreferences("vaani_personalization_v1", Context.MODE_PRIVATE)
            values =
                JSONObject().apply { legacy.all.forEach { (k, v) -> if (v is String) put(k, v) } }
            persist()
            check(decrypt(file.readFully()).toString() == values.toString()) {
                "Migration verification failed"
            }
            check(legacy.edit().clear().commit()) { "Legacy data could not be retired" }
        }
    }

    fun getString(key: String, fallback: String): String =
        synchronized(lock) { values.optString(key, fallback) }

    fun edit() = Editor()

    inner class Editor {
        private val edits = mutableMapOf<String, String>()

        fun putString(key: String, value: String): Editor {
            edits[key] = value
            return this
        }

        fun apply() =
            synchronized(lock) {
                edits.forEach { (k, v) -> values.put(k, v) }
                if (!transaction) persist()
            }
    }

    fun <T> transaction(action: () -> T): T =
        synchronized(lock) {
            val previous = values.toString()
            check(!transaction)
            transaction = true
            try {
                val result = action()
                persist()
                result
            } catch (error: Exception) {
                values = JSONObject(previous)
                throw error
            } finally {
                transaction = false
            }
        }

    private fun decrypt(bytes: ByteArray): JSONObject {
        check(bytes.size >= 28)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
        cipher.updateAAD("vaani-local-v1".toByteArray())
        return JSONObject(String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8))
    }

    private fun persist() {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key)
        cipher.updateAAD("vaani-local-v1".toByteArray())
        val encoded = cipher.iv + cipher.doFinal(values.toString().toByteArray(Charsets.UTF_8))
        val output = file.startWrite()
        try {
            output.write(encoded)
            file.finishWrite(output)
        } catch (error: Exception) {
            file.failWrite(output)
            throw error
        }
    }

    companion object {
        val lock = Any()
        private var instance: EncryptedPreferences? = null

        fun get(context: Context): EncryptedPreferences =
            synchronized(lock) {
                instance ?: EncryptedPreferences(context.applicationContext).also { instance = it }
            }
    }
}
