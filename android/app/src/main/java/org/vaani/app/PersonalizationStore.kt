package org.vaani.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * Android's local implementation of Vaani's portable personalization
 * contract. The field names intentionally match vaani-core's versioned
 * VocabularyEntry and Replacement records, so this store can be migrated to
 * Room or synchronized without changing user-visible behavior.
 */
class PersonalizationStore(context: Context) {
    data class Vocabulary(val id: String, val canonical: String, val aliases: List<String>, val category: String?)
    data class Snippet(val id: String, val trigger: String, val value: String)
    data class Replacement(val id: String, val source: String, val target: String)
    data class Snapshot(val vocabulary: List<Vocabulary>, val snippets: List<Snippet>, val replacements: List<Replacement>)

    private val preferences = context.getSharedPreferences("vaani_personalization_v1", Context.MODE_PRIVATE)

    fun snapshot(): Snapshot = Snapshot(readVocabulary(), readSnippets(), readReplacements())

    fun addVocabulary(canonical: String, spokenAlias: String = "", category: String? = "personal") {
        val spelling = valid(canonical, MAX_TERM)
        val alias = spokenAlias.trim().takeIf { it.isNotEmpty() }?.let { valid(it, MAX_TERM) }
        val now = System.currentTimeMillis()
        val items = vocabularyArray()
        items.put(JSONObject().apply {
            put("schema_version", 1)
            put("entity", "vocabulary")
            put("id", UUID.randomUUID().toString())
            put("canonical", spelling)
            put("spoken_aliases", JSONArray().apply { alias?.let { put(it) } })
            put("category", category?.take(MAX_CATEGORY))
            put("created_at_ms", now)
            put("updated_at_ms", now)
        })
        preferences.edit().putString(VOCABULARY_KEY, items.toString()).apply()
    }

    fun addReplacement(source: String, target: String) {
        val from = valid(source, MAX_SOURCE)
        val to = valid(target, MAX_TARGET)
        val now = System.currentTimeMillis()
        val items = replacementArray()
        items.put(JSONObject().apply {
            put("schema_version", 1)
            put("entity", "replacement")
            put("id", UUID.randomUUID().toString())
            put("source", from)
            put("target", to)
            put("created_at_ms", now)
            put("updated_at_ms", now)
        })
        preferences.edit().putString(REPLACEMENTS_KEY, items.toString()).apply()
    }

    fun removeVocabulary(id: String) = remove(VOCABULARY_KEY, vocabularyArray(), id)
    fun removeReplacement(id: String) = remove(REPLACEMENTS_KEY, replacementArray(), id)

    /** Versioned records whose JSON shape matches Rust PersonalizationRecord. */
    fun syncRecords(deviceId: String): List<JSONObject> = buildList {
        listOf(vocabularyArray(), snippetArray(), replacementArray()).forEach { items ->
            repeat(items.length()) { index ->
                val value = items.optJSONObject(index) ?: return@repeat
                val id = value.optString("id")
                val kind = value.optString("entity")
                if (id.isBlank() || kind !in setOf("vocabulary", "snippet", "replacement")) return@repeat
                val record = JSONObject().apply {
                    put("schema_version", 1)
                    put("entity", kind)
                    put("id", id)
                    put("revision", value.optLong("revision", 1))
                    put("logical_clock", value.optLong("logical_clock", value.optLong("updated_at_ms")))
                    put("writer_device_id", value.optString("writer_device_id", deviceId))
                    put("updated_at_ms", value.optLong("updated_at_ms"))
                    put("deleted_at_ms", value.opt("deleted_at_ms"))
                    put("value", if (value.has("deleted_at_ms")) JSONObject.NULL else value)
                }
                add(JSONObject().put(kind.replaceFirstChar(Char::uppercase), record))
            }
        }
    }

    /** Merge an authenticated, decrypted cross-device record. */
    fun mergeSyncedRecord(record: JSONObject) {
        val wrapper = when {
            record.has("Vocabulary") -> "Vocabulary"
            record.has("Snippet") -> "Snippet"
            record.has("Replacement") -> "Replacement"
            else -> return
        }
        val sync = record.optJSONObject(wrapper) ?: return
        val id = sync.optString("id")
        val value = sync.optJSONObject("value")
        val key = when (wrapper) {
            "Vocabulary" -> VOCABULARY_KEY
            "Snippet" -> SNIPPETS_KEY
            else -> REPLACEMENTS_KEY
        }
        val items = readArray(key)
        val existing = (0 until items.length()).firstOrNull { items.optJSONObject(it)?.optString("id") == id }
        if (existing != null && !remoteWins(sync, items.optJSONObject(existing)!!)) return
        val merged = value ?: JSONObject().apply {
            put("id", id); put("entity", wrapper.lowercase())
            put("updated_at_ms", sync.optLong("updated_at_ms")); put("deleted_at_ms", sync.optLong("deleted_at_ms"))
        }
        merged.put("revision", sync.optLong("revision", 1))
        merged.put("logical_clock", sync.optLong("logical_clock", merged.optLong("updated_at_ms")))
        merged.put("writer_device_id", sync.optString("writer_device_id"))
        if (existing != null) items.put(existing, merged) else items.put(merged)
        preferences.edit().putString(key, items.toString()).apply()
    }

    /** Must match vaani-core's (logical_clock, writer, revision, updated_at) merge key. */
    private fun remoteWins(remote: JSONObject, local: JSONObject): Boolean {
        val remoteClock = remote.optLong("logical_clock", remote.optLong("updated_at_ms"))
        val localClock = local.optLong("logical_clock", local.optLong("updated_at_ms"))
        if (remoteClock != localClock) return remoteClock > localClock
        val writer = remote.optString("writer_device_id").compareTo(local.optString("writer_device_id"))
        if (writer != 0) return writer > 0
        val revision = remote.optLong("revision", 1).compareTo(local.optLong("revision", 1))
        if (revision != 0) return revision > 0
        return remote.optLong("updated_at_ms") > local.optLong("updated_at_ms")
    }

    /** Same order and whole-word behavior as vaani-core::personalization::render. */
    fun render(text: String): String {
        var rendered = text
        snapshot().vocabulary
            .flatMap { entry -> entry.aliases.map { it to entry.canonical } }
            .sortedByDescending { it.first.length }
            .forEach { (alias, canonical) -> rendered = replaceBounded(rendered, alias, canonical) }
        snapshot().snippets
            .sortedByDescending { it.trigger.length }
            .forEach { rule -> rendered = replaceBounded(rendered, rule.trigger, rule.value) }
        snapshot().replacements
            .sortedByDescending { it.source.length }
            .forEach { rule -> rendered = replaceBounded(rendered, rule.source, rule.target) }
        return rendered
    }

    private fun remove(key: String, items: JSONArray, id: String) {
        repeat(items.length()) { index ->
            items.optJSONObject(index)?.takeIf { it.optString("id") == id }?.apply {
                put("deleted_at_ms", System.currentTimeMillis())
                put("updated_at_ms", System.currentTimeMillis())
            }
        }
        preferences.edit().putString(key, items.toString()).apply()
    }

    private fun readVocabulary(): List<Vocabulary> = buildList {
        val items = vocabularyArray()
        repeat(items.length()) { index ->
            val item = items.optJSONObject(index) ?: return@repeat
            if (item.has("deleted_at_ms")) return@repeat
            val canonical = item.optString("canonical").trim()
            if (canonical.isEmpty()) return@repeat
            val aliases = item.optJSONArray("spoken_aliases")?.let { array ->
                buildList { repeat(array.length()) { i -> array.optString(i).trim().takeIf(String::isNotEmpty)?.let(::add) } }
            }.orEmpty()
            add(Vocabulary(item.optString("id"), canonical, aliases, item.optString("category").takeIf(String::isNotEmpty)))
        }
    }

    private fun readReplacements(): List<Replacement> = buildList {
        val items = replacementArray()
        repeat(items.length()) { index ->
            val item = items.optJSONObject(index) ?: return@repeat
            if (item.has("deleted_at_ms")) return@repeat
            val source = item.optString("source").trim()
            val target = item.optString("target").trim()
            if (source.isNotEmpty() && target.isNotEmpty()) add(Replacement(item.optString("id"), source, target))
        }
    }

    private fun readSnippets(): List<Snippet> = buildList {
        val items = snippetArray()
        repeat(items.length()) { index ->
            val item = items.optJSONObject(index) ?: return@repeat
            if (item.has("deleted_at_ms")) return@repeat
            val trigger = item.optString("trigger").trim()
            val value = item.optString("value").trim()
            if (trigger.isNotEmpty() && value.isNotEmpty()) add(Snippet(item.optString("id"), trigger, value))
        }
    }

    private fun vocabularyArray() = readArray(VOCABULARY_KEY)
    private fun snippetArray() = readArray(SNIPPETS_KEY)
    private fun replacementArray() = readArray(REPLACEMENTS_KEY)
    private fun readArray(key: String) = runCatching { JSONArray(preferences.getString(key, "[]")) }.getOrDefault(JSONArray())

    private fun valid(value: String, max: Int): String {
        val clean = value.trim()
        require(clean.isNotEmpty() && clean.length <= max && !clean.contains('\n') && !clean.contains('\r') && !clean.contains('\u0000'))
        return clean
    }

    private fun replaceBounded(text: String, source: String, target: String): String {
        val pattern = Regex("(?i)(?<![\\p{L}\\p{N}_])${Regex.escape(source)}(?![\\p{L}\\p{N}_])")
        return pattern.replace(text, Regex.escapeReplacement(target))
    }

    private companion object {
        const val VOCABULARY_KEY = "vocabulary"
        const val SNIPPETS_KEY = "snippets"
        const val REPLACEMENTS_KEY = "replacements"
        const val MAX_TERM = 120
        const val MAX_CATEGORY = 32
        const val MAX_SOURCE = 160
        const val MAX_TARGET = 512
    }
}
