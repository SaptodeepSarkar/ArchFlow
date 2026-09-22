package org.vaani.app

/**
 * Deterministic local fallback for the optional embedded GGUF formatter.
 * It cannot substitute, delete, reorder, or invent source words.
 */
object SafeFormatter {
    fun format(raw: String): String {
        val compact = raw.trim().replace(Regex("\\s+"), " ")
        explicitCue(compact)?.let { return it }
        val cleaned = compact.replace(Regex("(?i)\\b(uh|um|erm|hmm)\\b\\s*"), "").trim()
        if (cleaned.isEmpty()) return ""
        val capitalized = cleaned.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
        return if (capitalized.last() in ".!?") capitalized else "$capitalized."
    }

    /** Closed, source-grounded cues shared with the Linux fallback boundary. */
    private fun explicitCue(text: String): String? {
        val lower = text.lowercase()
        val emojis = mapOf("laughing emoji" to "😂", "laugh emoji" to "😂", "thumbs up emoji" to "👍", "heart emoji" to "❤️", "celebration emoji" to "🎉", "smiley emoji" to "🙂")
        val prefixes = listOf("add ", "add a ", "insert ", "insert a ", "use ", "use a ", "put ", "put a ", "include ", "include a ", "send ", "send a ", "give ", "give a ")
        emojis.entries.firstOrNull { (cue, _) -> lower == cue || prefixes.any { lower.endsWith(it + cue) } }?.let { return it.value }

        val words = text.split(" ")
        val markers = setOf("first", "second", "third", "fourth", "fifth")
        val positions = words.mapIndexedNotNull { index, word -> if (word.lowercase() in markers) index else null }
        if (positions.size >= 2) {
            val items = positions.mapIndexed { number, start ->
                val end = positions.getOrNull(number + 1) ?: words.size
                words.subList(start + 1, end).joinToString(" ").trim(',', '.', ';', ':').replaceFirstChar { it.titlecase() }.let { "${number + 1}. $it" }
            }
            return if (items.any { it == "${items.indexOf(it) + 1}. " }) null else items.joinToString("\n")
        }
        return null
    }
}
