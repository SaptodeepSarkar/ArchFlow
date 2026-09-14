package org.vaani.keyboard

sealed interface DictationState {
    data object Hidden : DictationState
    data object Starting : DictationState
    data class Listening(val level: Float = 0f, val finalText: String? = null) : DictationState
    data object Endpointing : DictationState
    data object Finalizing : DictationState
    data class Inserting(val text: String) : DictationState
    data object Success : DictationState
    data object Cancelled : DictationState
    data class Failure(
        val kind: FailureKind,
        val message: String,
        val recoverableText: String? = null,
    ) : DictationState
}

enum class FailureKind {
    PERMISSION,
    MICROPHONE,
    RECOGNIZER_UNAVAILABLE,
    RECOGNITION,
    TIMEOUT,
    INSERTION,
}

data class AppReadiness(
    val recognizerAvailable: Boolean,
    val microphoneGranted: Boolean,
    val keyboardEnabled: Boolean,
    val testCompleted: Boolean,
) {
    val ready: Boolean
        get() = recognizerAvailable && microphoneGranted && keyboardEnabled && testCompleted

    val nextBlocker: ReadinessBlocker?
        get() = when {
            !recognizerAvailable -> ReadinessBlocker.RECOGNIZER
            !microphoneGranted -> ReadinessBlocker.MICROPHONE
            !keyboardEnabled -> ReadinessBlocker.KEYBOARD
            !testCompleted -> ReadinessBlocker.TEST
            else -> null
        }
}

enum class ReadinessBlocker { RECOGNIZER, MICROPHONE, KEYBOARD, TEST }
