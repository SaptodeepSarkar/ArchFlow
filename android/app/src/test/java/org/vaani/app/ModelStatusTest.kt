package org.vaani.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelStatusTest {
    @Test fun readiness_requires_both_local_model_files() {
        assertTrue(ModelStatus(sttAvailable = true, formatterAvailable = true).ready)
        assertFalse(ModelStatus(sttAvailable = true, formatterAvailable = false).ready)
    }
}
