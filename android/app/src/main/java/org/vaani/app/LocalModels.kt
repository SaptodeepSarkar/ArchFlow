package org.vaani.app

import android.content.Context
import java.io.File

data class ModelStatus(val sttAvailable: Boolean, val formatterAvailable: Boolean)

/** Models are user-installed local files; weights are deliberately never bundled in Git. */
class LocalModels(context: Context) {
    private val root = File(context.filesDir, "models").also { it.mkdirs() }
    fun status() = ModelStatus(File(root, "stt/model.bin").isFile, File(root, "formatter/model.gguf").isFile)
    fun installPath(kind: String) = File(root, kind).also { it.mkdirs() }
}
