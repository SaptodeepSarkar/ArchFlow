package org.vaani.app

import android.content.Context
import dev.ffmpegkit.llama.Llama
import dev.ffmpegkit.llama.LlamaConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Optional local cleanup model. The LLM is an editor, never an authority: its
 * output is accepted only when it preserves the dictated content in order.
 */
object LocalInference {
    suspend fun format(context: Context, source: String): String = withContext(Dispatchers.IO) {
        val modelPath = LocalModels(context).formatterModelFile() ?: return@withContext SafeFormatter.format(source)
        runCatching {
            val model = Llama.loadModel(
                modelPath.absolutePath,
                LlamaConfig(contextSize = 1024, threads = 2, gpuLayers = 0, temperature = 0.1f, topP = 0.9f, topK = 40, seed = 0),
            )
            try {
                val result = Llama.complete(
                    model,
                    prompt = "SOURCE:\n$source\n\nReturn only the same words with conservative casing and punctuation. Do not add, remove, reorder, or replace words.",
                    systemPrompt = "You are Vaani's deterministic text editor. Never invent content.",
                    maxTokens = 128,
                )
                val candidate = result.text.trim().removePrefix("OUTPUT:").trim()
                if (ModelOutputGuard.isSafeEdit(source, candidate)) candidate else SafeFormatter.format(source)
            } finally {
                Llama.releaseModel(model)
            }
        }.getOrElse { SafeFormatter.format(source) }
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
