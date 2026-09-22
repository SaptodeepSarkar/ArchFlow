package org.vaani.app

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

object VaaniColor {
    // Mirrors the semantic Vaani tokens in brand/brand-kit.html.
    val Ink = Color(0xFF19161C)
    val Plum = Color(0xFF6B3A85)
    val Lilac = Color(0xFFE8DCFF)
    val Apricot = Color(0xFFFFD4A3)
    val Paper = Color(0xFFFDFBF8)
    val Cloud = Color(0xFFFFFDFB)
    val Surface = Paper
    val Text = Ink
    val Muted = Color(0xFF827B87)
    val Line = Color(0xFFE8E2E7)

    // Transitional names keep existing native service and model screens
    // coherent while the Compose product shell moves to the brand tokens.
    val Cobalt = Plum
    val Coral = Apricot
    val Sky = Lilac
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
