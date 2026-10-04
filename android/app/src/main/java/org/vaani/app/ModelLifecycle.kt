package org.vaani.app

import android.app.Application
import android.content.ComponentCallbacks2
import android.content.Context
import android.content.res.Configuration
import dev.ffmpegkit.whisper.Whisper
import dev.ffmpegkit.whisper.WhisperModel
import dev.ffmpegkit.llama.Llama
import dev.ffmpegkit.llama.LlamaModel
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.io.File

/** Single-flight loads and operation leases; unloading cannot race native inference. */
internal class LazyModel<T>(private val release: (T) -> Unit) {
    private val mutex = Mutex()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var handle: T? = null
    private var identity: String? = null
    private var expiry: Job? = null
    suspend fun <R> use(key: String, ttl: Long, load: suspend () -> T, operation: suspend (T) -> R): R = mutex.withLock {
        expiry?.cancel()
        if (identity != key) { handle?.let(release); handle = null; identity = key }
        if (handle == null) handle = load()
        try { operation(handle!!) } finally {
            if (ttl == 0L) { handle?.let(release); handle = null; identity = null }
            else expiry = scope.launch { delay(ttl.coerceIn(1_000,120_000)); clear() }
        }
    }
    suspend fun clear() = mutex.withLock { expiry?.cancel(); expiry = null; handle?.let(release); handle = null; identity = null }
}

internal object ModelLifecycle {
    val stt = LazyModel<WhisperModel>(Whisper::releaseModel)
    val llm = LazyModel<LlamaModel>(Llama::releaseModel)
    val tagger = LazyModel<V6Tagger> { }
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    fun ttl(context: Context): Long = if (AppSettings.profile(context) == "balanced") AppSettings.retentionSeconds(context) * 1000L else 0L
    fun identity(file: File): String = "${file.absolutePath}:${file.length()}:${file.lastModified()}"
    fun unload() { scope.launch { stt.clear(); llm.clear(); tagger.clear() } }
}

class VaaniApplication : Application(), ComponentCallbacks2 {
    override fun onTrimMemory(level: Int) { super.onTrimMemory(level); ModelLifecycle.unload() }
    override fun onLowMemory() { super.onLowMemory(); ModelLifecycle.unload() }
}

object AppSettings {
    private fun prefs(context: Context) = context.getSharedPreferences("vaani_settings", Context.MODE_PRIVATE)
    fun profile(context: Context) = prefs(context).getString("profile", "economy") ?: "economy"
    fun retentionSeconds(context: Context) = prefs(context).getLong("retention", 30).coerceIn(1,120)
    fun formatterEnabled(context: Context) = prefs(context).getBoolean("formatter", true)
    fun update(context: Context, profile: String, seconds: Long, formatter: Boolean) {
        require(profile in setOf("economy","balanced") && seconds in 1..120)
        prefs(context).edit().putString("profile",profile).putLong("retention",seconds).putBoolean("formatter",formatter).apply()
        ModelLifecycle.unload()
    }
    fun portable(context: Context) = mapOf("recognition.language" to OnboardingState.writingLanguage(context), "general.residency_profile" to profile(context), "recognition.server_idle_secs" to retentionSeconds(context).toString())
    fun import(context: Context, values: Map<String,String>) {
        values["recognition.language"]?.let { OnboardingState.setWritingLanguage(context,it) }
        update(context, values["general.residency_profile"]?.let { if(it=="ready") "balanced" else it } ?: profile(context), values["recognition.server_idle_secs"]?.toLong()?.coerceIn(1,120) ?: retentionSeconds(context),formatterEnabled(context))
    }
}
