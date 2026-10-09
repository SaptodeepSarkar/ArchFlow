package org.vaani.app

import org.junit.Assert.assertEquals
import org.junit.Test

class V6TokenizerTest {
    @Test
    fun separatesSentencePunctuationAndPreservesDottedVersions() {
        assertEquals(
            listOf("URL", ".", "Build", "v1.2.3", "."),
            V6Tokenizer.tokenize("URL. Build v1.2.3."),
        )
    }

    @Test
    fun separatesUrlTerminalPeriod() {
        assertEquals(
            listOf("see", "https://example.org/path", "."),
            V6Tokenizer.tokenize("see https://example.org/path."),
        )
    }
}
