package org.vaani.app

import java.io.File
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * JVM uses the same Android pairing implementation; physical Android TLS remains a separate gate.
 */
class LocalPairingInteropTest {
    @Test
    fun java_sender_to_rust_receiver() = runBlocking {
        val path = System.getenv("VAANI_INTEROP_INVITATION")
        assumeTrue("Run with the disposable Rust receiver harness", path != null)
        val value =
            JSONObject()
                .put("id", "interop-word")
                .put("canonical", "Vaani")
                .put("spoken_aliases", JSONArray())
                .put("category", JSONObject.NULL)
                .put("created_at_ms", 1)
                .put("updated_at_ms", 1)
        val record =
            JSONObject()
                .put("schema_version", 1)
                .put("entity", "vocabulary")
                .put("id", "interop-word")
                .put("revision", 1)
                .put("logical_clock", 1)
                .put("writer_device_id", "jvm-test")
                .put("updated_at_ms", 1)
                .put("deleted_at_ms", JSONObject.NULL)
                .put("value", value)
        val bundle =
            JSONObject()
                .put("schema_version", 1)
                .put("records", JSONArray().put(JSONObject().put("Vocabulary", record)))
                .put("preferences", JSONObject().put("recognition.language", "en"))
        LocalPairing().send(File(path!!).readText(), bundle)
    }
}
