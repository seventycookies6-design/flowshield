package com.basaltfocus.app.ui

import android.content.Context
import android.content.res.Configuration
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.*
import androidx.compose.ui.unit.*
import androidx.compose.foundation.shape.RoundedCornerShape
import com.basaltfocus.app.R
import org.json.JSONObject

class TokenPalette(context: Context, dark: Boolean) {
    private val source = JSONObject(context.assets.open("tokens.json").bufferedReader().use { it.readText() })
        .getJSONObject("themes").getJSONObject(if (dark) "dark" else "light")
    fun color(name: String): Color {
        val value = source.get(name)
        return if (value is String) Color(android.graphics.Color.parseColor(value))
        else (value as JSONObject).let { color(it.getString("ref")).copy(alpha = it.getDouble("alpha").toFloat()) }
    }
    fun native(name: String): Int = color(name).let { android.graphics.Color.argb((it.alpha * 255).toInt(), (it.red * 255).toInt(), (it.green * 255).toInt(), (it.blue * 255).toInt()) }
    companion object {
        fun system(context: Context) = TokenPalette(context,
            context.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES)
    }
}

private val Inter = FontFamily(Font(R.font.inter_regular), Font(R.font.inter_medium, FontWeight.Medium), Font(R.font.inter_semibold, FontWeight.SemiBold))
// Tabular figures only where numbers tick (timer, momentum); in prose they space out hyphens.
private fun type(size: Int, height: Int, weight: FontWeight = FontWeight.Normal, tracking: Float = 0f, tabular: Boolean = false) =
    TextStyle(fontFamily = Inter, fontSize = size.sp, lineHeight = height.sp, fontWeight = weight,
        letterSpacing = tracking.sp, fontFeatureSettings = if (tabular) "tnum" else null)

@Composable
fun BasaltTheme(content: @Composable () -> Unit) {
    val context = LocalContext.current
    val dark = isSystemInDarkTheme()
    val p = remember(context, dark) { TokenPalette(context, dark) }
    val scheme = (if (dark) darkColorScheme() else lightColorScheme()).copy(
        primary = p.color("primary"), onPrimary = p.color("primary-ink"),
        primaryContainer = p.color("surface-2"), onPrimaryContainer = p.color("text"),
        secondary = p.color("primary"), onSecondary = p.color("primary-ink"),
        secondaryContainer = p.color("surface-2"), onSecondaryContainer = p.color("text"),
        tertiary = p.color("primary"), onTertiary = p.color("primary-ink"),
        background = p.color("bg"), onBackground = p.color("text"),
        surface = p.color("surface"), onSurface = p.color("text"),
        surfaceVariant = p.color("surface-2"), onSurfaceVariant = p.color("text-muted"),
        surfaceContainer = p.color("surface"), surfaceContainerHigh = p.color("surface-2"),
        surfaceContainerHighest = p.color("surface-2"), surfaceContainerLow = p.color("surface"),
        surfaceContainerLowest = p.color("bg"), surfaceDim = p.color("bg-soft"), surfaceBright = p.color("surface-2"),
        outline = p.color("text-faint"), outlineVariant = p.color("border"),
        error = p.color("danger"), onError = p.color("bg"),
        scrim = p.color("scrim"), inverseSurface = p.color("text"), inverseOnSurface = p.color("bg"),
    )
    MaterialTheme(colorScheme = scheme,
        typography = Typography(
            displayLarge = type(64, 64, FontWeight.SemiBold, -1.28f, tabular = true),
            displayMedium = type(36, 40, FontWeight.SemiBold, -.36f, tabular = true),
            headlineLarge = type(30, 36, FontWeight.SemiBold, -.6f),
            headlineSmall = type(18, 24, FontWeight.SemiBold, -.18f),
            titleLarge = type(18, 24, FontWeight.SemiBold, -.18f),
            titleMedium = type(18, 24, FontWeight.SemiBold, -.18f),
            bodyLarge = type(14, 21), bodyMedium = type(14, 21), bodySmall = type(12, 17),
            labelLarge = type(13, 18, FontWeight.Medium), labelMedium = type(13, 18, FontWeight.Medium),
            labelSmall = type(11, 14, FontWeight.SemiBold, .66f)),
        shapes = Shapes(extraSmall = RoundedCornerShape(6.dp), small = RoundedCornerShape(10.dp),
            medium = RoundedCornerShape(14.dp), large = RoundedCornerShape(14.dp), extraLarge = RoundedCornerShape(14.dp)),
        content = content)
}
