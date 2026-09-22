using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;

// System.Drawing is in scope through the tray code's global usings, and it has a
// Color of its own; this file means the WPF one.
using MediaColor = System.Windows.Media.Color;

namespace FlowShield.Infrastructure;

public class InverseBooleanConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c) => !(value is true);
    public object ConvertBack(object value, Type t, object p, CultureInfo c) => !(value is true);
}

public class BoolToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c) =>
        value is true ? Visibility.Visible : Visibility.Collapsed;

    public object ConvertBack(object value, Type t, object p, CultureInfo c) =>
        value is Visibility.Visible;
}

public class InverseBoolToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c) =>
        value is true ? Visibility.Collapsed : Visibility.Visible;

    public object ConvertBack(object value, Type t, object p, CultureInfo c) =>
        value is not Visibility.Visible;
}

/// <summary>Binds a radio/toggle to "does this enum property equal ConverterParameter?".</summary>
public class EnumEqualsConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c)
    {
        if (value is null || p is null) return false;
        return string.Equals(value.ToString(), p.ToString(), StringComparison.OrdinalIgnoreCase);
    }

    public object ConvertBack(object value, Type t, object p, CultureInfo c)
    {
        if (value is not true || p is null) return Binding.DoNothing;
        try { return Enum.Parse(Nullable.GetUnderlyingType(t) ?? t, p.ToString()!, ignoreCase: true); }
        catch { return Binding.DoNothing; }
    }
}

/// <summary>Same idea for ints (sprint-length buttons).</summary>
public class IntEqualsConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c) =>
        value is int i && p is not null && int.TryParse(p.ToString(), out var target) && i == target;

    public object ConvertBack(object value, Type t, object p, CultureInfo c)
    {
        if (value is not true || p is null) return Binding.DoNothing;
        return int.TryParse(p.ToString(), out var target) ? target : Binding.DoNothing;
    }
}

/// <summary>
/// Turns a 0→1 progress value into a StrokeDashArray for the timer ring.
/// Dash units are multiples of StrokeThickness, so the arc length is
/// (circumference × progress) ÷ thickness, followed by a gap long enough to
/// swallow the remainder of the circle.
/// </summary>
public class ProgressToDashConverter : IValueConverter
{
    public double Radius { get; set; } = 92;
    public double Thickness { get; set; } = 12;

    public object Convert(object value, Type t, object p, CultureInfo c)
    {
        var progress = value is double d ? Math.Clamp(d, 0, 1) : 0;
        var circumference = 2 * Math.PI * Radius;
        var on = circumference * progress / Thickness;
        var off = circumference / Thickness;
        return new DoubleCollection(new[] { on, off });
    }

    public object ConvertBack(object value, Type t, object p, CultureInfo c) => Binding.DoNothing;
}

/// <summary>
/// Hides the progress arc at zero. A zero-length dash with a round cap still
/// paints a dot at the 12 o'clock position, which reads as a bug.
/// </summary>
public class PositiveToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c) =>
        value is double d && d > 0.0005 ? Visibility.Visible : Visibility.Hidden;

    public object ConvertBack(object value, Type t, object p, CultureInfo c) => Binding.DoNothing;
}

/// <summary>Greys out a row when the blocked app is toggled off.</summary>
public class BoolToOpacityConverter : IValueConverter
{
    public double WhenFalse { get; set; } = 0.45;

    public object Convert(object value, Type t, object p, CultureInfo c) => value is true ? 1.0 : WhenFalse;
    public object ConvertBack(object value, Type t, object p, CultureInfo c) => Binding.DoNothing;
}

public class ShieldRomanConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c) => value?.ToString() switch
    {
        "Soft" => "Shield I · Soft",
        "Firm" => "Shield II · Firm",
        "Sealed" => "Shield III · Sealed",
        _ => "Shield",
    };

    public object ConvertBack(object value, Type t, object p, CultureInfo c) => Binding.DoNothing;
}

/// <summary>
/// Looks up a brush resource by name, e.g. MainViewModel.TierBadgeDotKey
/// ("Primary", "Green" or "Amber") for the tier badge's status dot
/// (DESIGN_SYSTEM.md §7 "Tier badge").
/// </summary>
public class ResourceKeyToBrushConverter : IValueConverter
{
    public object? Convert(object value, Type t, object p, CultureInfo c) =>
        value is string key ? Application.Current.TryFindResource(key) : null;

    public object ConvertBack(object value, Type t, object p, CultureInfo c) => Binding.DoNothing;
}

/// <summary>Shows an element only when its bound text has something in it.</summary>
public class NonEmptyToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c) =>
        string.IsNullOrWhiteSpace(value as string) ? Visibility.Collapsed : Visibility.Visible;

    public object ConvertBack(object value, Type t, object p, CultureInfo c) => Binding.DoNothing;
}

/// <summary>
/// One of the heatmap's five steps as a brush (History, F16).
///
/// DESIGN_SYSTEM.md §7 asks for "five steps from surface-2 to primary", so the
/// ramp is mixed from those two tokens at run time rather than written out as
/// five more colours: the generated Tokens.xaml stays the only place a colour
/// is defined (§14), and the light theme (F21) recolours the heatmap by
/// changing those two values and nothing else.
///
/// Because it reads the tokens itself rather than binding to them, a theme
/// change has to tell it to look again: ThemeService.RefreshConverterBindings
/// re-evaluates every binding that runs a converter once the swap is done.
///
/// Step 0 is plain surface-2 — a day with no focus at all.
/// </summary>
public class HeatStepToBrushConverter : IValueConverter
{
    public int Steps { get; set; } = 5;

    public object Convert(object value, Type t, object p, CultureInfo c)
    {
        var step = value is int i ? Math.Clamp(i, 0, Steps - 1) : 0;
        // No hard-coded fallback: a missing token leaves the cell transparent
        // (it keeps its border), rather than pinning one colour into the code.
        FlowShield.Services.ThemeService.TryColour("Surface2Color", out var from);
        FlowShield.Services.ThemeService.TryColour("PrimaryColor", out var to);
        var mix = Steps <= 1 ? 0 : step / (double)(Steps - 1);
        return new SolidColorBrush(Lerp(from, to, mix));
    }

    private static MediaColor Lerp(MediaColor from, MediaColor to, double mix) => MediaColor.FromRgb(
        (byte)Math.Round(from.R + (to.R - from.R) * mix),
        (byte)Math.Round(from.G + (to.G - from.G) * mix),
        (byte)Math.Round(from.B + (to.B - from.B) * mix));

    public object ConvertBack(object value, Type t, object p, CultureInfo c) => Binding.DoNothing;
}

/// <summary>
/// Maps a <see cref="Models.ShieldLevel"/> to its glyph, built once in
/// ShieldGlyphs.xaml (DESIGN_SYSTEM.md §6) and shared by the shield chips and
/// the timer ring, at whatever size the Image using it is given.
/// </summary>
public class ShieldLevelToGlyphConverter : IValueConverter
{
    public object? Convert(object value, Type t, object p, CultureInfo c)
    {
        var key = value?.ToString() switch
        {
            "Soft" => "ShieldGlyphSoft",
            "Firm" => "ShieldGlyphFirm",
            "Sealed" => "ShieldGlyphSealed",
            _ => null,
        };
        return key is null ? null : Application.Current.TryFindResource(key);
    }

    public object ConvertBack(object value, Type t, object p, CultureInfo c) => Binding.DoNothing;
}
