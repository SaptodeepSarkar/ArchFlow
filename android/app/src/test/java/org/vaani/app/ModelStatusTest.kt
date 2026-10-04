package org.vaani.app
import org.junit.Assert.*
import org.junit.Test
class ModelStatusTest {
 @Test fun stt_only_is_ready_and_formatter_is_optional() {assertTrue(ModelStatus(true,false).ready);assertTrue(ModelStatus(true,true).ready);assertFalse(ModelStatus(false,true).ready)}
}
