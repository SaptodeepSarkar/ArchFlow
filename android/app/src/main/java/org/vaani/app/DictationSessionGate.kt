package org.vaani.app

/** Tokens stay valid during formatting, but each session accepts only one STT result. */
internal class DictationSessionGate {
    private var generation = 0L
    private var current: Long? = null
    private var resultAccepted = false

    @Synchronized fun begin(): Long {
        resultAccepted = false
        return (++generation).also { current = it }
    }

    @Synchronized fun invalidate() { current = null }
    @Synchronized fun isCurrent(token: Long): Boolean = current == token
    @Synchronized fun isListening(token: Long): Boolean = current == token && !resultAccepted
    @Synchronized fun acceptResult(token: Long): Boolean {
        if (!isListening(token)) return false
        resultAccepted = true
        return true
    }
}

/** Equality identifies an editor, while the generation detects away-and-back changes. */
internal class FocusTargetLease<T> {
    private var current: T? = null
    private var generation = 0L

    @Synchronized fun observe(target: T?): Boolean {
        if (current == target) return false
        current = target
        generation++
        return true
    }

    @Synchronized fun capture(): Long? = if (current == null) null else generation
    @Synchronized fun matches(token: Long?): Boolean = token != null && token == capture()
}

/** Main-thread entry points share one capture/formatting owner in this process. */
internal class DictationOwnership {
    private var generation = 0L
    private var owner: Long? = null
    private var cancelOwner: (() -> Unit)? = null

    fun claim(cancel: () -> Unit): Long {
        val previous = cancelOwner
        val token = ++generation
        owner = token
        cancelOwner = cancel
        previous?.invoke()
        return token
    }

    fun release(token: Long?) {
        if (token == null || owner != token) return
        owner = null
        cancelOwner = null
    }
}

internal object ActiveDictation {
    val ownership = DictationOwnership()
}

/** Serializes short resource operations with disposal; close is idempotent. */
internal class OwnedResource<T>(resource: T, private val dispose: (T) -> Unit) {
    private var resource: T? = resource

    @Synchronized fun <R> useIfOpen(operation: (T) -> R): R? = resource?.let(operation)

    @Synchronized fun close() {
        val owned = resource ?: return
        resource = null
        dispose(owned)
    }
}
