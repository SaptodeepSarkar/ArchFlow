package org.vaani.app

import org.junit.Assert.assertEquals
import org.junit.Test

class SafeFormatterTest {
    @Test fun formatter_removes_fillers_and_preserves_words() {
        assertEquals("Please send the notes.", SafeFormatter.format(" um please send the notes "))
    }

    @Test fun formatter_never_invents_a_rewrite() {
        assertEquals("Blue whale.", SafeFormatter.format("blue whale"))
    }
}
