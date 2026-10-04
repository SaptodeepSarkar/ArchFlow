package org.vaani.app

import android.content.Context
import dev.ffmpegkit.llama.Llama
import dev.ffmpegkit.llama.LlamaConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import kotlin.coroutines.coroutineContext

/**
 * Optional local cleanup model. The LLM is an editor, never an authority: its
 * output is accepted only when it preserves the dictated content in order.
 */
object LocalInference {
    suspend fun format(context: Context, source: String): String = withContext(Dispatchers.IO) {
        formatChunks(context, source)
    }

    private suspend fun formatChunks(context: Context, source: String): String {
        if (source.isBlank()) return ""
        if (!AppSettings.formatterEnabled(context)) return source
        val chunks = source.split(Regex("\\s+")).filter(String::isNotBlank).chunked(MAX_WORDS_PER_CHUNK)
        val models = LocalModels(context)
        val ttl = ModelLifecycle.ttl(context)
        try {
            models.v6FormatterFile()?.let { file ->
                return ModelLifecycle.tagger.use(ModelLifecycle.identity(file), ttl, { V6Tagger.load(file.readBytes()) }) { model ->
                    chunks.joinToString(" ") { formatV6(model, it.joinToString(" ")) }
                }
            }
            val file = models.formatterModelFile() ?: return SafeFormatter.format(source)
            return ModelLifecycle.llm.use(ModelLifecycle.identity(file), ttl, {
                Llama.loadModel(file.absolutePath, LlamaConfig(contextSize = 1024, threads = 2, gpuLayers = 0, temperature = 0.1f, topP = 0.9f, topK = 40, seed = 0))
            }) { model ->
                val output = mutableListOf<String>()
                for (words in chunks) {
                    coroutineContext.ensureActive()
                    val chunk = words.joinToString(" ")
                    val result = Llama.complete(model, prompt = "SOURCE:\n$chunk\n\nReturn only the same words with conservative casing and punctuation.", systemPrompt = "Never invent or reorder content.", maxTokens = 256)
                    coroutineContext.ensureActive()
                    val candidate = result.text.trim().removePrefix("OUTPUT:").trim()
                    output.add(if (ModelOutputGuard.isSafeEdit(chunk, candidate)) candidate else SafeFormatter.format(chunk))
                }
                output.joinToString(" ")
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { coroutineContext.ensureActive(); return SafeFormatter.format(source) }
    }

    private const val MAX_WORDS_PER_CHUNK = 72

    private fun formatV6(model: V6Tagger, source: String): String {
        val tokens = Regex("https?://[^\\s]+|/[^\\s]+|[\\p{L}\\p{N}_][\\p{L}\\p{N}_.-]*|[^\\w\\s]")
            .findAll(source).map { it.value }.toList()
        if (tokens.isEmpty()) return ""
        val prediction = model.predict(tokens)
        val rendered = buildString {
            tokens.indices.forEach { index ->
                if (prediction.tokenLabels[index] == 1 || prediction.tokenLabels[index] == 2 || prediction.tokenLabels[index] == 3) return@forEach
                val token = if (prediction.tokenLabels[index] == 4) tokens[index].replaceFirstChar { it.uppercase() } else tokens[index]
                if (isNotEmpty() && token.firstOrNull()?.isLetterOrDigit() == true) append(' ')
                append(token)
                when (prediction.punctuation[index]) {
                    1 -> append(','); 2 -> append('.'); 3 -> append('?'); 4 -> append('!'); 5 -> append(':'); 6 -> append(';')
                }
            }
        }.trim()
        return if (ModelOutputGuard.isSafeEdit(source, rendered)) rendered else SafeFormatter.format(source)
    }

}

internal object ModelOutputGuard {
    fun isSafeEdit(source: String, candidate: String): Boolean {
        if (candidate.isBlank() || candidate.length > source.length * 3 + 32) return false
        val sourceWords = words(source).filterNot { it in setOf("uh", "um", "erm", "hmm") }
        val candidateWords = words(candidate)
        if (sourceWords.isEmpty() || candidateWords.isEmpty()) return false
        // Formatting may change case/punctuation and remove known fillers, but
        // no new, deleted, substituted, or reordered content is permitted.
        return candidateWords == sourceWords
    }

    private fun words(value: String): List<String> = Regex("[\\p{L}\\p{N}']+")
        .findAll(value.lowercase())
        .map { it.value }
        .toList()
}
