package org.vaani.app

import android.content.Context
import android.net.Uri
import java.io.File

data class ModelStatus(val sttAvailable: Boolean, val formatterAvailable: Boolean)

enum class ModelKind(val directory: String, val filename: String) {
    STT("stt", "ggml-base.bin"),
    FORMATTER("formatter", "model.gguf"),
}

/** Models are user-installed local files; weights are deliberately never bundled in Git. */
class LocalModels(context: Context) {
    private val root = File(context.filesDir, "models").also { it.mkdirs() }
    fun sttModelFile(): File? = listOf(
        File(root, "stt/ggml-base.bin"),
        File(root, "stt/model.bin"),
    ).firstOrNull(File::isFile)

    fun formatterModelFile(): File? = listOf(
        File(root, "formatter/model.gguf"),
        File(root, "formatter/model.bin"),
    ).firstOrNull(File::isFile)

    fun status() = ModelStatus(sttModelFile() != null, formatterModelFile() != null)
    fun installPath(kind: ModelKind): File = File(root, kind.directory).also { it.mkdirs() }
}

object ModelInstaller {
    fun install(context: Context, kind: ModelKind, uri: Uri): Result<File> = runCatching {
        val destination = File(LocalModels(context).installPath(kind), kind.filename)
        val temporary = File(destination.parentFile, ".${destination.name}.part")
        context.contentResolver.openInputStream(uri)?.use { input ->
            temporary.outputStream().use { output -> input.copyTo(output, DEFAULT_BUFFER_SIZE) }
        } ?: error("The selected file could not be opened")
        check(temporary.length() > 0L) { "The selected model file is empty" }
        check(temporary.renameTo(destination)) { "The selected model file could not be installed" }
        destination
    }.onFailure {
        File(LocalModels(context).installPath(kind), ".${kind.filename}.part").delete()
    }

    private const val DEFAULT_BUFFER_SIZE = 64 * 1024
}
