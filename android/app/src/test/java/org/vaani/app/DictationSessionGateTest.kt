package org.vaani.app

import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class DictationSessionGateTest {
    @Test fun switching_entry_points_cancels_previous_capture_or_formatting() {
        val owners = DictationOwnership()
        var cancelled = 0
        var first: Long? = null
        first = owners.claim { cancelled++; owners.release(first) }
        var secondCancelled = 0
        val second = owners.claim { secondCancelled++ }
        assertEquals(1, cancelled)
        owners.release(first)
        owners.claim { }
        assertEquals(1, secondCancelled)
        owners.release(second)
    }

    @Test fun completed_owner_is_not_retained_or_cancelled_by_next_session() {
        val owners = DictationOwnership()
        var cancelled = false
        val token = owners.claim { cancelled = true }
        owners.release(token)
        owners.claim { }
        assertFalse(cancelled)
    }

    @Test fun delivery_target_is_invalid_after_a_switch_away_and_back() {
        val targets = FocusTargetLease<String>()
        targets.observe("editor-a")
        val token = targets.capture()
        assertTrue(targets.matches(token))
        targets.observe("editor-b")
        assertFalse(targets.matches(token))
        targets.observe("editor-a")
        assertFalse(targets.matches(token))
    }

    @Test fun repeated_focus_observation_does_not_invalidate_delivery() {
        val targets = FocusTargetLease<String>()
        targets.observe("editor-a")
        val token = targets.capture()
        assertFalse(targets.observe("editor-a"))
        assertTrue(targets.matches(token))
        targets.observe(null)
        assertNull(targets.capture())
        assertFalse(targets.matches(token))
        assertFalse(targets.matches(null))
    }

    @Test fun cancellation_during_formatting_rejects_late_delivery() {
        val sessions = DictationSessionGate()
        val token = sessions.begin()
        assertTrue(sessions.acceptResult(token))
        sessions.invalidate()
        assertFalse(sessions.isCurrent(token))
        assertFalse(sessions.acceptResult(token))
    }

    @Test fun new_session_rejects_old_ready_error_result_and_ui_reset() {
        val sessions = DictationSessionGate()
        val old = sessions.begin()
        val current = sessions.begin()
        assertFalse(sessions.isListening(old))
        assertFalse(sessions.isCurrent(old))
        assertFalse(sessions.acceptResult(old))
        assertTrue(sessions.isListening(current))
    }

    @Test fun duplicate_result_cannot_format_or_deliver_twice() {
        val sessions = DictationSessionGate()
        val token = sessions.begin()
        assertTrue(sessions.acceptResult(token))
        assertFalse(sessions.acceptResult(token))
        assertFalse(sessions.isListening(token))
        assertTrue(sessions.isCurrent(token))
    }

    @Test fun concurrent_cancel_and_finally_dispose_resource_once() {
        val count = AtomicInteger()
        val owned = OwnedResource(Any()) { count.incrementAndGet() }
        val pool = Executors.newFixedThreadPool(2)
        val start = CountDownLatch(1)
        try {
            val tasks = (1..2).map { pool.submit { start.await(); owned.close() } }
            start.countDown()
            tasks.forEach { it.get(2, TimeUnit.SECONDS) }
            assertEquals(1, count.get())
            assertNull(owned.useIfOpen { fail("use after release") })
        } finally { pool.shutdownNow() }
    }

    @Test fun disposal_waits_for_an_inflight_operation() {
        val entered = CountDownLatch(1)
        val finish = CountDownLatch(1)
        val count = AtomicInteger()
        val pool = Executors.newFixedThreadPool(2)
        val owned = OwnedResource(Any()) { count.incrementAndGet() }
        try {
            val read = pool.submit { owned.useIfOpen { entered.countDown(); finish.await() } }
            assertTrue(entered.await(2, TimeUnit.SECONDS))
            val close = pool.submit { owned.close() }
            assertEquals(0, count.get())
            finish.countDown()
            read.get(2, TimeUnit.SECONDS)
            close.get(2, TimeUnit.SECONDS)
            assertEquals(1, count.get())
        } finally { finish.countDown(); pool.shutdownNow() }
    }

    @Test fun throwing_disposer_does_not_allow_double_release() {
        var count = 0
        val owned = OwnedResource(Any()) { count++; error("release failed") }
        runCatching { owned.close() }
        owned.close()
        assertEquals(1, count)
    }
}
