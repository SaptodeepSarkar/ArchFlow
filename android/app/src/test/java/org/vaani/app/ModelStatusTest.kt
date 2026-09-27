package org.vaani.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelStatusTest {
    @Test fun readiness_requires_both_local_model_files() {
        assertTrue(ModelStatus(sttAvailable = true, formatterAvailable = true).ready)
        assertFalse(ModelStatus(sttAvailable = true, formatterAvailable = false).ready)
    }

    @Test fun background_sync_retries_are_bounded() {
        assertTrue(SyncWork.shouldRetry(0))
        assertTrue(SyncWork.shouldRetry(2))
        assertFalse(SyncWork.shouldRetry(3))
    }
}
