package org.vaani.app

import org.junit.Assert.assertThrows
import org.junit.Test

class V6TaggerTest {
    @Test
    fun rejects_bad_package_magic() {
        assertThrows(IllegalArgumentException::class.java) { V6Tagger.load(ByteArray(8)) }
    }
}
