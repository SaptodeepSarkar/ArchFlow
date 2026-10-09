package org.vaani.app

import android.content.Context
import android.net.Uri
import java.io.File

data class ModelStatus(val sttAvailable: Boolean, val formatterAvailable: Boolean) {
    val ready: Boolean get() = sttAvailable
}

enum class ModelKind(val directory: String, val filename: String, val runtime: String) {
    STT("stt", "ggml-base.bin", "whisper-ggml"),
    /** Staged separately from Base; selection remains gated on V6 qualification. */
    STT_V6("stt", "ggml-v6.bin", "whisper-ggml"),
    FORMATTER("formatter", "model.gguf", "llama-gguf"),
    FORMATTER_V6("formatter", "model.v6tg", "vaani-v6-tagger"),
}

/** Models are user-installed local files; weights are deliberately never bundled in Git. */
class LocalModels(context: Context) {
    private val root = File(context.filesDir, "models").also { it.mkdirs() }
    fun sttModelFile(): File? = modelFile(ModelKind.STT)

    /** A downloaded V6 Whisper candidate is never silently promoted over Base. */
    fun v6SttModelFile(): File? = modelFile(ModelKind.STT_V6)

    fun formatterModelFile(): File? = modelFile(ModelKind.FORMATTER)

    /** Optional V6 package; callers must still keep the V5 fallback available. */
    fun v6FormatterFile(): File? = File(root, "formatter/model.v6tg")
        .takeIf { it.isFile && it.length() > 0L }

    fun modelFile(kind: ModelKind): File? = when (kind) {
        ModelKind.STT -> listOf(
            File(root, "stt/ggml-base.bin"),
            File(root, "stt/model.bin"),
        )
        ModelKind.STT_V6 -> listOf(File(root, "stt/ggml-v6.bin"))
        ModelKind.FORMATTER -> listOf(
            File(root, "formatter/model.gguf"),
            File(root, "formatter/model.bin"),
        )
        ModelKind.FORMATTER_V6 -> listOf(File(root, "formatter/model.v6tg"))
    }.firstOrNull { it.isFile && it.length() > 0L }

    fun status() = ModelStatus(sttModelFile() != null, formatterModelFile() != null || v6FormatterFile() != null)
    fun installPath(kind: ModelKind): File = File(root, kind.directory).also { it.mkdirs() }
}

object ModelInstaller {
    fun install(context: Context, kind: ModelKind, uri: Uri): Result<File> = runCatching {
        val destination = File(LocalModels(context).installPath(kind), kind.filename)
        val temporary = File(destination.parentFile, ".${destination.name}.part")
        context.contentResolver.openInputStream(uri)?.use { input ->
            temporary.outputStream().use { output -> val buffer=ByteArray(DEFAULT_BUFFER_SIZE); var total=0L
                while(true) { val count=input.read(buffer);if(count<0) break;total+=count;require(total<=4L*1024*1024*1024) { "Model exceeds supported size" };output.write(buffer,0,count) } }
        } ?: error("The selected file could not be opened")
        check(temporary.length() in 4..4L*1024*1024*1024) { "Invalid model size" }
        val magic=temporary.inputStream().use {input ->ByteArray(4).also {check(input.read(it)==4)}}
        when(kind) {
            ModelKind.STT, ModelKind.STT_V6 -> check(String(magic) in setOf("lmgg","ggml")) { "Expected whisper.cpp GGML" }
            ModelKind.FORMATTER -> check(String(magic)=="GGUF") { "Expected GGUF" }
            ModelKind.FORMATTER_V6 -> V6Tagger.load(temporary.readBytes())
        }
        if(destination.exists()) destination.copyTo(File(destination.parentFile,"${destination.name}.previous"),overwrite=true)
        ModelLifecycle.unload()
        check(temporary.renameTo(destination)) { "The selected model file could not be installed" }
        destination
    }.onFailure {
        File(LocalModels(context).installPath(kind), ".${kind.filename}.part").delete()
    }

    private const val DEFAULT_BUFFER_SIZE = 64 * 1024
}
