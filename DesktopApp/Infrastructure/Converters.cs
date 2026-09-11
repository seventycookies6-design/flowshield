using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;

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
