package org.vaani.app

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

object VaaniColor {
    val Ink = Color(0xFF0C1020)
    val Cobalt = Color(0xFF526BFF)
    val Coral = Color(0xFFFF6B4A)
    val Cloud = Color(0xFFFFF7F1)
    val Sky = Color(0xFF78C7FF)
    val Surface = Color(0xFFF7F8FC)
    val Text = Color(0xFF171A26)
    val Muted = Color(0xFF72788B)
    val Line = Color(0xFFD9DDE8)
}

@Composable
fun VaaniTheme(content: @Composable () -> Unit) = MaterialTheme(
    colorScheme = darkColorScheme(
        primary = VaaniColor.Cobalt,
        secondary = VaaniColor.Coral,
        background = VaaniColor.Ink,
        surface = VaaniColor.Ink,
        onPrimary = VaaniColor.Cloud,
        onBackground = VaaniColor.Cloud,
        onSurface = VaaniColor.Cloud,
    ),
    content = content,
)
