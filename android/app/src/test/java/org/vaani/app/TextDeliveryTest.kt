package org.vaani.app

import org.junit.Assert.assertEquals
import org.junit.Test

class TextDeliveryTest {
    @Test fun safe_single_line_field_receives_text() {
        var inserted = ""
        val result = TextDelivery.deliver("  Hello there.  ", Delivery.INSERT, { inserted = it; true }, {})
        assertEquals(DeliveryResult.INSERTED, result)
        assertEquals("Hello there.", inserted)
    }

    @Test fun failed_insert_falls_back_to_clipboard() {
        var copied = ""
        val result = TextDelivery.deliver("Hello there.", Delivery.INSERT, { false }, { copied = it })
        assertEquals(DeliveryResult.COPIED, result)
        assertEquals("Hello there.", copied)
    }

    @Test fun copy_only_and_blank_are_explicit() {
        var copied = ""
        assertEquals(DeliveryResult.COPIED, TextDelivery.deliver("Notes", Delivery.COPY_ONLY, { true }, { copied = it }))
        assertEquals("Notes", copied)
        assertEquals(DeliveryResult.EMPTY, TextDelivery.deliver("  ", Delivery.COPY_ONLY, { true }, { copied = it }))
    }
}
