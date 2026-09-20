package org.vaani.app

import android.content.Context
import java.io.File

data class ModelStatus(val sttAvailable: Boolean, val formatterAvailable: Boolean)

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
    fun installPath(kind: String) = File(root, kind).also { it.mkdirs() }
}
