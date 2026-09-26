package org.vaani.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SttEvidenceTest {
    @Test fun `segment evidence preserves actual backend timing without word confidence`() {
        val final = SttFinalEvidence(
            text = "hello vaani",
            backend = "whisper.cpp",
            segments = listOf(SttSegmentEvidence(0, 120, 840, " hello vaani")),
        )

        assertEquals("whisper.cpp", final.backend)
        assertEquals(120L, final.segments.single().startMs)
        assertEquals(840L, final.segments.single().endMs)
        // Missing word-level evidence remains absent; callers must not invent it.
        assertTrue(final.segments.single().text.isNotBlank())
    }
}
