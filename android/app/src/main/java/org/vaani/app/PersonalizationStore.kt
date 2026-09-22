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
    data class Replacement(val id: String, val source: String, val target: String)
    data class Snapshot(val vocabulary: List<Vocabulary>, val replacements: List<Replacement>)

    private val preferences = context.getSharedPreferences("vaani_personalization_v1", Context.MODE_PRIVATE)

    fun snapshot(): Snapshot = Snapshot(readVocabulary(), readReplacements())

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

    /** Same order and whole-word behavior as vaani-core::personalization::render. */
    fun render(text: String): String {
        var rendered = text
        snapshot().vocabulary
            .flatMap { entry -> entry.aliases.map { it to entry.canonical } }
            .sortedByDescending { it.first.length }
            .forEach { (alias, canonical) -> rendered = replaceBounded(rendered, alias, canonical) }
        snapshot().replacements
            .sortedByDescending { it.source.length }
            .forEach { rule -> rendered = replaceBounded(rendered, rule.source, rule.target) }
        return rendered
    }

    private fun remove(key: String, items: JSONArray, id: String) {
        val kept = JSONArray()
        repeat(items.length()) { index -> items.optJSONObject(index)?.takeIf { it.optString("id") != id }?.let(kept::put) }
        preferences.edit().putString(key, kept.toString()).apply()
    }

    private fun readVocabulary(): List<Vocabulary> = buildList {
        val items = vocabularyArray()
        repeat(items.length()) { index ->
            val item = items.optJSONObject(index) ?: return@repeat
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
            val source = item.optString("source").trim()
            val target = item.optString("target").trim()
            if (source.isNotEmpty() && target.isNotEmpty()) add(Replacement(item.optString("id"), source, target))
        }
    }

    private fun vocabularyArray() = readArray(VOCABULARY_KEY)
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
        const val REPLACEMENTS_KEY = "replacements"
        const val MAX_TERM = 120
        const val MAX_CATEGORY = 32
        const val MAX_SOURCE = 160
        const val MAX_TARGET = 512
    }
}
