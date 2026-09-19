package org.vaani.keyboard

/**
 * The complete UI state for onboarding.  External Android state (permission,
 * IME selection, and dictation progress) is folded into one immutable value so
 * Compose never has to coordinate several independent flags.
 */
sealed interface OnboardingState {
    val page: Int

    data class Welcome(override val page: Int = 0) : OnboardingState

    data class Microphone(
        val ready: Boolean,
        val denied: Boolean,
        val requesting: Boolean,
        override val page: Int = 1,
    ) : OnboardingState

    data class Keyboard(
        val enabled: Boolean,
        val selected: Boolean,
        override val page: Int = 2,
    ) : OnboardingState

    data class Rehearsal(
        val enabled: Boolean,
        val selected: Boolean,
        val complete: Boolean,
        val dictationStatus: String,
        override val page: Int = 3,
    ) : OnboardingState
}
