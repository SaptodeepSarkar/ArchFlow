package org.vaani.keyboard

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.util.Base64
import java.util.UUID

data class PersonalizationEntry(
    val id: String,
    val trigger: String,
    val value: String,
    val revision: Long = 0,
    val logicalClock: Long = 0,
    val writerDeviceId: String = "",
    val updatedAtMs: Long = 0,
    val deletedAtMs: Long? = null,
    val spokenAliases: List<String> = emptyList(),
)

/** Versioned, local-only repository for structured personalization records. */
class PersonalizationStore(context: Context) {
    private val appContext = context.applicationContext
    private val helper = StoreHelper(appContext)
    val deviceId: String by lazy {
        appContext.getSharedPreferences("vaani", Context.MODE_PRIVATE).let { prefs ->
            prefs.getString("device_id", null) ?: UUID.randomUUID().toString().also {
                prefs.edit().putString("device_id", it).apply()
            }
        }
    }

    init { migrateLegacyPreferences() }

    fun vocabulary(): List<PersonalizationEntry> = read(Kind.VOCABULARY)
    fun snippets(): List<PersonalizationEntry> = read(Kind.SNIPPET)
    fun replacements(): List<PersonalizationEntry> = read(Kind.REPLACEMENT)

    /** Includes tombstones for the optional sync provider, but never exposes them to rendering/UI. */
    fun syncEntries(kind: Kind): List<PersonalizationEntry> = read(kind, includeDeleted = true)

    /** Merge one cloud record without creating a new local edit. */
    fun mergeRemote(
        kind: Kind,
        id: String,
        trigger: String,
        value: String,
        revision: Long,
        logicalClock: Long,
        writerDeviceId: String,
        updatedAtMs: Long,
        deletedAtMs: Long?,
        spokenAliases: List<String> = emptyList(),
    ): Boolean {
        if (id.isBlank() || trigger.length > MAX_TEXT || value.length > MAX_VALUE) return false
        val db = helper.writableDatabase
        val current = db.query(TABLE, arrayOf("revision", "logical_clock", "writer_device_id", "updated_at_ms"), "id = ? AND kind = ?", arrayOf(id, kind.dbValue), null, null, null).use {
            if (!it.moveToFirst()) null else Version(it.getLong(0), it.getLong(1), it.getString(2), it.getLong(3))
        }
        if (current != null && compareVersion(revision, logicalClock, writerDeviceId, updatedAtMs, current.revision, current.logicalClock, current.writerDeviceId, current.updatedAtMs) <= 0) return false
        val values = ContentValues().apply {
            put("id", id); put("kind", kind.dbValue); put("trigger_text", trigger); put("value_text", value)
            put("aliases_text", encodeAliases(spokenAliases))
            put("revision", revision); put("logical_clock", logicalClock); put("writer_device_id", writerDeviceId); put("updated_at_ms", updatedAtMs)
            if (deletedAtMs == null) putNull("deleted_at_ms") else put("deleted_at_ms", deletedAtMs)
        }
        return db.insertWithOnConflict(TABLE, null, values, SQLiteDatabase.CONFLICT_REPLACE) != -1L
    }

    fun addVocabulary(term: String, spokenAliases: List<String> = emptyList()): Boolean {
        val clean = term.trim()
        if (clean.isEmpty() || clean.length > MAX_TEXT) return false
        val aliases = spokenAliases.map(String::trim).filter { it.isNotEmpty() && it.length <= MAX_TEXT }.distinct()
        return insert(Kind.VOCABULARY, clean, "", aliases)
    }

    fun addSnippet(trigger: String, expansion: String): Boolean = add(Kind.SNIPPET, trigger, expansion)
    fun addReplacement(trigger: String, replacement: String): Boolean = add(Kind.REPLACEMENT, trigger, replacement)

    fun remove(kind: Kind, id: String) {
        val now = System.currentTimeMillis()
        helper.writableDatabase.execSQL(
            "UPDATE $TABLE SET revision = revision + 1, logical_clock = logical_clock + 1, writer_device_id = ?, updated_at_ms = ?, deleted_at_ms = ? WHERE kind = ? AND id = ?",
            arrayOf(deviceId, now, now, kind.dbValue, id),
        )
    }

    /** Applies vocabulary aliases, snippets, then replacements, longest trigger first. */
    fun render(raw: String): String {
        var text = raw
        vocabulary().flatMap { entry -> entry.spokenAliases.map { alias -> alias to entry.trigger } }
            .sortedByDescending { it.first.length }
            .forEach { (alias, canonical) -> text = replaceWholeWord(text, alias, canonical) }
        snippets().sortedByDescending { it.trigger.length }.forEach { text = replaceWholeWord(text, it.trigger, it.value) }
        replacements().sortedByDescending { it.trigger.length }.forEach { text = replaceWholeWord(text, it.trigger, it.value) }
        return text
    }

    private fun add(kind: Kind, trigger: String, value: String): Boolean {
        val cleanTrigger = trigger.trim()
        val cleanValue = value.trim()
        if (cleanTrigger.isEmpty() || cleanValue.isEmpty() || cleanTrigger.length > MAX_TEXT || cleanValue.length > MAX_VALUE) return false
        return insert(kind, cleanTrigger, cleanValue)
    }

    private fun insert(kind: Kind, trigger: String, value: String, spokenAliases: List<String> = emptyList()): Boolean {
        val db = helper.writableDatabase
        val count = db.query(TABLE, arrayOf("COUNT(*)"), "kind = ?", arrayOf(kind.dbValue), null, null, null).use { cursor -> cursor.moveToFirst(); cursor.getInt(0) }
        if (count >= MAX_ENTRIES) return false
        val now = System.currentTimeMillis()
        val values = ContentValues().apply {
            put("id", newId())
            put("kind", kind.dbValue)
            put("trigger_text", trigger)
            put("value_text", value)
            put("aliases_text", encodeAliases(spokenAliases))
            put("revision", 1L)
            put("logical_clock", 1L)
            put("writer_device_id", deviceId)
            put("updated_at_ms", now)
            putNull("deleted_at_ms")
        }
        return db.insert(TABLE, null, values) != -1L
    }

    private fun read(kind: Kind, includeDeleted: Boolean = false): List<PersonalizationEntry> = helper.readableDatabase.query(
        TABLE,
        arrayOf("id", "trigger_text", "value_text", "aliases_text", "revision", "logical_clock", "writer_device_id", "updated_at_ms", "deleted_at_ms"),
        if (includeDeleted) "kind = ?" else "kind = ? AND deleted_at_ms IS NULL",
        arrayOf(kind.dbValue), null, null, "rowid ASC"
    ).use { cursor ->
        buildList {
            while (cursor.moveToNext()) add(
                PersonalizationEntry(
                    cursor.getString(0), cursor.getString(1), cursor.getString(2),
                    cursor.getLong(4), cursor.getLong(5), cursor.getString(6), cursor.getLong(7),
                    if (cursor.isNull(8)) null else cursor.getLong(8), decodeAliases(cursor.getString(3)),
                ),
            )
        }
    }

    private fun migrateLegacyPreferences() {
        val legacy = appContext.getSharedPreferences(LEGACY_PREFS, Context.MODE_PRIVATE)
        if (legacy.getBoolean(MIGRATED_KEY, false)) return
        val db = helper.writableDatabase
        db.beginTransaction()
        try {
            migrateLines(db, Kind.VOCABULARY, legacy.getString(KEY_VOCABULARY, "").orEmpty(), vocabularyOnly = true)
            migrateLines(db, Kind.SNIPPET, legacy.getString(KEY_SNIPPETS, "").orEmpty())
            migrateLines(db, Kind.REPLACEMENT, legacy.getString(KEY_REPLACEMENTS, "").orEmpty())
            db.setTransactionSuccessful()
            legacy.edit().putBoolean(MIGRATED_KEY, true).apply()
        } finally { db.endTransaction() }
    }

    private fun migrateLines(db: SQLiteDatabase, kind: Kind, encoded: String, vocabularyOnly: Boolean = false) {
        encoded.lineSequence().filter(String::isNotBlank).forEach { line ->
            val parts = line.split('\t')
            if (parts.size != 3) return@forEach
            val trigger = runCatching { decode(parts[1]) }.getOrNull() ?: return@forEach
            val value = if (vocabularyOnly) "" else runCatching { decode(parts[2]) }.getOrNull() ?: return@forEach
            if (trigger.isEmpty() || trigger.length > MAX_TEXT || value.length > MAX_VALUE) return@forEach
            db.insert(TABLE, null, ContentValues().apply {
                put("id", parts[0]); put("kind", kind.dbValue); put("trigger_text", trigger); put("value_text", value); put("aliases_text", "")
                put("revision", 1L); put("logical_clock", 1L); put("writer_device_id", deviceId); put("updated_at_ms", System.currentTimeMillis()); putNull("deleted_at_ms")
            })
        }
    }

    private fun replaceWholeWord(text: String, needle: String, replacement: String): String {
        val pattern = Regex("(?<![\\p{L}\\p{N}_])${Regex.escape(needle)}(?![\\p{L}\\p{N}_])", RegexOption.IGNORE_CASE)
        return pattern.replace(text) { replacement }
    }

    private fun compareVersion(leftRevision: Long, leftClock: Long, leftDevice: String, leftTime: Long, rightRevision: Long, rightClock: Long, rightDevice: String, rightTime: Long): Int {
        return compareValues(leftClock, rightClock).takeIf { it != 0 }
            ?: compareValues(leftDevice, rightDevice).takeIf { it != 0 }
            ?: compareValues(leftRevision, rightRevision).takeIf { it != 0 }
            ?: compareValues(leftTime, rightTime)
    }

    private data class Version(val revision: Long, val logicalClock: Long, val writerDeviceId: String, val updatedAtMs: Long)

    private fun newId() = UUID.randomUUID().toString()
    private fun decode(value: String) = String(Base64.decode(value, Base64.NO_WRAP or Base64.URL_SAFE), Charsets.UTF_8)
    private fun encodeAliases(values: List<String>) = values.joinToString("|") { Base64.encodeToString(it.toByteArray(Charsets.UTF_8), Base64.NO_WRAP or Base64.URL_SAFE) }
    private fun decodeAliases(value: String) = value.split('|').filter(String::isNotEmpty).mapNotNull { runCatching { decode(it) }.getOrNull() }

    enum class Kind(val dbValue: String) { VOCABULARY("vocabulary"), SNIPPET("snippet"), REPLACEMENT("replacement") }

    private class StoreHelper(context: Context) : SQLiteOpenHelper(context, DB_NAME, null, DB_VERSION) {
        override fun onCreate(db: SQLiteDatabase) {
            db.execSQL("CREATE TABLE $TABLE (id TEXT NOT NULL PRIMARY KEY, kind TEXT NOT NULL, trigger_text TEXT NOT NULL, value_text TEXT NOT NULL, aliases_text TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 1, logical_clock INTEGER NOT NULL DEFAULT 1, writer_device_id TEXT NOT NULL DEFAULT '', updated_at_ms INTEGER NOT NULL DEFAULT 0, deleted_at_ms INTEGER)")
            db.execSQL("CREATE INDEX personalization_kind_idx ON $TABLE(kind)")
        }
        override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
            if (oldVersion < 1) onCreate(db)
            if (oldVersion < 2) {
                db.execSQL("ALTER TABLE $TABLE ADD COLUMN revision INTEGER NOT NULL DEFAULT 1")
                db.execSQL("ALTER TABLE $TABLE ADD COLUMN updated_at_ms INTEGER NOT NULL DEFAULT 0")
                db.execSQL("ALTER TABLE $TABLE ADD COLUMN deleted_at_ms INTEGER")
            }
            if (oldVersion < 3) {
                db.execSQL("ALTER TABLE $TABLE ADD COLUMN logical_clock INTEGER NOT NULL DEFAULT 1")
                db.execSQL("ALTER TABLE $TABLE ADD COLUMN writer_device_id TEXT NOT NULL DEFAULT ''")
            }
            if (oldVersion < 4) db.execSQL("ALTER TABLE $TABLE ADD COLUMN aliases_text TEXT NOT NULL DEFAULT ''")
        }
    }

    companion object {
        private const val DB_NAME = "vaani_personalization.db"
        private const val DB_VERSION = 4
        private const val TABLE = "personalization"
        private const val LEGACY_PREFS = "vaani_personalization"
        private const val MIGRATED_KEY = "sqlite_migrated_v1"
        private const val KEY_VOCABULARY = "vocabulary"
        private const val KEY_SNIPPETS = "snippets"
        private const val KEY_REPLACEMENTS = "replacements"
        private const val MAX_ENTRIES = 500
        private const val MAX_TEXT = 500
        private const val MAX_VALUE = 5000
    }
}
