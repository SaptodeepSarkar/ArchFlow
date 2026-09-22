package org.vaani.app

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import androidx.core.content.ContextCompat

data class DeviceAccess(
    val microphone: Boolean,
    val notifications: Boolean,
    val textBoxAccess: Boolean,
    val overlay: Boolean,
) {
    val summary: String
        get() = when {
            !microphone -> "Microphone needs permission"
            !textBoxAccess -> "Text-box access needs permission"
            !overlay -> "Floating control needs permission"
            else -> "Vaani is ready in text fields"
        }
}

/** Small durable product state; permission grants are always queried live. */
object OnboardingState {
    private const val PREFERENCES = "vaani_onboarding"
    private const val COMPLETED = "completed"

    fun isCompleted(context: Context): Boolean =
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).getBoolean(COMPLETED, false)

    fun markCompleted(context: Context) {
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .edit().putBoolean(COMPLETED, true).apply()
    }

    fun access(context: Context): DeviceAccess = DeviceAccess(
        microphone = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED,
        notifications = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED,
        textBoxAccess = AccessibilityBridge.isTextBoxAccessEnabled(context),
        overlay = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context),
    )
}
