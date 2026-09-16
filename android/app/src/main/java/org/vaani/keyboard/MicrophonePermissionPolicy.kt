package org.vaani.keyboard


/** Pure permission-state decision; Android owns the actual permission UI. */
object MicrophonePermissionPolicy {
    fun requiresAppSettings(requestedBefore: Boolean, granted: Boolean, canAskAgain: Boolean): Boolean =
        requestedBefore && !granted && !canAskAgain

    fun appSettingsPackageUri(packageName: String): String = "package:$packageName"
}
