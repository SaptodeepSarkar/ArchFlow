package org.vaani.app

/**
 * The final handoff boundary for dictated text. It keeps editor authority in
 * the IME while making the insert/copy fallback deterministic and testable.
 */
enum class DeliveryResult { INSERTED, COPIED, EMPTY }

object TextDelivery {
    fun deliver(
        text: String,
        delivery: Delivery,
        commit: (String) -> Boolean,
        copy: (String) -> Unit,
    ): DeliveryResult {
        val clean = text.trim()
        if (clean.isEmpty()) return DeliveryResult.EMPTY
        if (delivery == Delivery.INSERT && commit(clean)) return DeliveryResult.INSERTED
        copy(clean)
        return DeliveryResult.COPIED
    }
}
