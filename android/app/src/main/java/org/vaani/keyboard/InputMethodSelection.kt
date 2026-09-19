package org.vaani.keyboard

/** Compares Android IME ids without depending on their abbreviated spelling. */
object InputMethodSelection {
    fun matches(selectedId: String?, expectedPackageName: String, expectedClassName: String): Boolean {
        val id = selectedId.orEmpty()
        val separator = id.indexOf('/')
        if (separator <= 0 || separator == id.lastIndex) return false
        val packageName = id.substring(0, separator)
        val rawClassName = id.substring(separator + 1)
        val className = if (rawClassName.startsWith('.')) packageName + rawClassName else rawClassName
        return packageName == expectedPackageName && className == expectedClassName
    }
}
