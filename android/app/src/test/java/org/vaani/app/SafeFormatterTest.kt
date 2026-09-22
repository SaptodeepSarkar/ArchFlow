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

    @Test fun explicit_emoji_is_rendered_without_model_knowledge() {
        assertEquals("😂", SafeFormatter.format("please add a laughing emoji"))
    }

    @Test fun explicit_numbered_list_is_rendered_source_grounded() {
        assertEquals("1. Launch VSCode\n2. Inspect logs", SafeFormatter.format("first launch VSCode second inspect logs"))
    }
}
