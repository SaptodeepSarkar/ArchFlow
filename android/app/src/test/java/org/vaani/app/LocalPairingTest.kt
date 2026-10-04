package org.vaani.app

import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class LocalPairingTest {
    @Test
    fun pinned_tls_delivers_once_and_waits_for_explicit_merge() = runBlocking {
        val receiver = LocalPairing()
        val invitation = receiver.prepare("127.0.0.1")
        assertEquals(invitation, LocalPairing.parse(invitation.encode()))
        val task = async(Dispatchers.IO) { receiver.receive(invitation) }
        val bundle =
            JSONObject()
                .put("schema_version", 1)
                .put("records", JSONArray())
                .put("preferences", JSONObject())
        LocalPairing().send(invitation.encode(), bundle)
        assertEquals(1, task.await().getInt("schema_version"))
        assertTrue(runCatching { LocalPairing().send(invitation.encode(), bundle) }.isFailure)
        receiver.close()
    }

    @Test
    fun expired_public_address_and_bad_schema_are_rejected() {
        val invite =
            LocalPairing.Invitation(
                "127.0.0.1",
                1234,
                "00".repeat(32),
                "a".repeat(43),
                System.currentTimeMillis() + 60_000,
            )
        assertTrue(runCatching { LocalPairing.parse(invite.copy(expires = 0).encode()) }.isFailure)
        assertTrue(
            runCatching { LocalPairing.parse(invite.copy(host = "8.8.8.8").encode()) }.isFailure
        )
        assertTrue(
            runCatching {
                    LocalPairing.validateBundle(
                        JSONObject().put("schema_version", 2).put("records", JSONArray())
                    )
                }
                .isFailure
        )
    }
}
