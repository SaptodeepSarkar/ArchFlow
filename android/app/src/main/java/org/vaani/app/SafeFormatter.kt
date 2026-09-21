package org.vaani.app

/**
 * Deterministic local fallback for the optional embedded GGUF formatter.
 * It cannot substitute, delete, reorder, or invent source words.
 */
object SafeFormatter {
    fun format(raw: String): String {
        val compact = raw.trim().replace(Regex("\\s+"), " ")
            .replace(Regex("(?i)\\b(uh|um|erm|hmm)\\b\\s*"), "").trim()
        if (compact.isEmpty()) return ""
        val capitalized = compact.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
        return if (capitalized.last() in ".!?") capitalized else "$capitalized."
    }
}
