package org.vaani.app

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

object VaaniColor {
    // Mirrors the semantic Vaani tokens in brand/brand-kit.html.
    val Ink = Color(0xFF243D4A)
    val Blue = Color(0xFF286D9F)
    val Plum = Blue
    val Sky = Color(0xFFDDEEFF)
    val Lilac = Sky
    val Apricot = Color(0xFFFFCFAB)
    val Paper = Color(0xFFFFFCF7)
    val Cloud = Color(0xFFFFFDFB)
    val Surface = Paper
    val Text = Ink
    val Muted = Color(0xFF586B76)
    val Line = Color(0xFFD9E1E3)

    // Transitional names keep existing native service and model screens
    // coherent while the Compose product shell moves to the brand tokens.
    val Cobalt = Plum
    val Coral = Apricot
}

@Composable
fun VaaniTheme(content: @Composable () -> Unit) =
    MaterialTheme(
        colorScheme =
            lightColorScheme(
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
