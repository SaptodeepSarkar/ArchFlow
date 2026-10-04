package org.vaani.app

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

object VaaniColor {
    // Mirrors the semantic Vaani tokens in brand/brand-kit.html.
    val Ink = Color(0xFF202B36)
    val Plum = Color(0xFF226EA8)
    val Lilac = Color(0xFFE4F2FF)
    val Apricot = Color(0xFFFFE3CB)
    val Paper = Color(0xFFFAFAF7)
    val Cloud = Color(0xFFFFFDFB)
    val Surface = Paper
    val Text = Ink
    val Muted = Color(0xFF526474)
    val Line = Color(0xFFCFDFEA)

    // Transitional names keep existing native service and model screens
    // coherent while the Compose product shell moves to the brand tokens.
    val Cobalt = Plum
    val Coral = Apricot
    val Sky = Lilac
}

@Composable
fun VaaniTheme(content: @Composable () -> Unit) = MaterialTheme(
    colorScheme = lightColorScheme(
        primary = VaaniColor.Cobalt,
        secondary = VaaniColor.Coral,
        background = VaaniColor.Paper,
        surface = VaaniColor.Cloud,
        onPrimary = VaaniColor.Cloud,
        onBackground = VaaniColor.Ink,
        onSurface = VaaniColor.Ink,
    ),
    content = content,
)
