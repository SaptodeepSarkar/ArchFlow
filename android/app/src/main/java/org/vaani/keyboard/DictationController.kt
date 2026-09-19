package org.vaani.keyboard

/**
 * Pure dictation orchestration state. Android views and recognizers are
 * adapters around this reducer; callbacks from an old editor/session are
 * ignored by token validation.
 */
class DictationController {
    var state: DictationState = DictationState.Hidden
        private set

    private var nextToken = 0L
    private var activeToken: Long? = null

    fun start(): Long? {
        if (state !is DictationState.Hidden && state !is DictationState.Cancelled && state !is DictationState.Success) return null
        val token = ++nextToken
        activeToken = token
        state = DictationState.Starting
        return token
    }

    fun ready(token: Long): Boolean = accept(token) {
        if (state is DictationState.Starting) state = DictationState.Listening()
    }

    fun level(token: Long, level: Float): Boolean = accept(token) {
        val current = state
        if (current is DictationState.Listening) state = current.copy(level = level.coerceIn(0f, 1f))
    }

    /** Returns true when a final result should be delivered immediately. */
    fun result(token: Long, text: String): Boolean {
        if (!isActive(token)) return false
        val current = state
        return when (current) {
            is DictationState.Listening -> {
                state = current.copy(finalText = text)
                false
            }
            DictationState.Endpointing, DictationState.Finalizing -> {
                state = DictationState.Inserting(text)
                true
            }
            DictationState.Starting -> {
                state = DictationState.Listening(finalText = text)
                false
            }
            else -> false
        }
    }

    fun release(token: Long): String? {
        if (!isActive(token)) return null
        val current = state
        if (current is DictationState.Listening && current.finalText != null) {
            state = DictationState.Inserting(current.finalText)
            return current.finalText
        }
        if (current is DictationState.Starting || current is DictationState.Listening) {
            state = DictationState.Endpointing
        }
        return null
    }

    fun finishEndpoint(token: Long): Boolean = accept(token) {
        if (state is DictationState.Endpointing) state = DictationState.Finalizing
    }

    fun inserted(token: Long): Boolean = accept(token) {
        if (state is DictationState.Inserting) state = DictationState.Success
    }

    fun insertionFailed(token: Long, message: String, text: String): Boolean = accept(token) {
        if (state is DictationState.Inserting) state = DictationState.Failure(FailureKind.INSERTION, message, text)
    }

    fun failed(token: Long, kind: FailureKind, message: String, recoverableText: String? = null): Boolean = accept(token) {
        state = DictationState.Failure(kind, message, recoverableText)
    }

    fun isActive(token: Long): Boolean = isActiveToken(token)

    fun currentToken(): Long? = activeToken

    fun retry(text: String): Long? {
        if (state !is DictationState.Failure || text.isEmpty()) return null
        val token = ++nextToken
        activeToken = token
        state = DictationState.Inserting(text)
        return token
    }

    fun abort() {
        activeToken = null
        state = DictationState.Hidden
    }

    fun cancel() {
        activeToken = null
        state = DictationState.Cancelled
    }

    fun hide() {
        activeToken = null
        state = DictationState.Hidden
    }

    private fun isActiveToken(token: Long): Boolean = activeToken == token && state !is DictationState.Cancelled && state !is DictationState.Hidden

    private inline fun accept(token: Long, action: () -> Unit): Boolean {
        if (!isActiveToken(token)) return false
        action()
        return true
    }
}
