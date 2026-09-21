using System.Windows;
using System.Windows.Controls;

namespace FlowShield.Infrastructure;

/// <summary>
/// Rounds a <see cref="Border"/> all the way: its corner radius is half its
/// smaller side, kept up to date as it resizes. DESIGN_SYSTEM.md §4's "fully
/// round" — pills, the tier badge, toggle tracks, the scrollbar thumb.
///
/// This has to be computed. CSS clamps an oversized border-radius, but WPF
/// does not: it scales the corner curves proportionally instead, so
/// <c>CornerRadius="9999"</c> draws an ellipse — the tier badge became a lozenge
/// and the 5 px scrollbar thumb a spike. Set <c>inf:Pill.IsRound="True"</c>
/// on the Border, or in a style Setter, instead of a radius.
/// </summary>
public static class Pill
{
    public static readonly DependencyProperty IsRoundProperty = DependencyProperty.RegisterAttached(
        "IsRound", typeof(bool), typeof(Pill), new PropertyMetadata(false, OnIsRoundChanged));

    public static bool GetIsRound(DependencyObject element) => (bool)element.GetValue(IsRoundProperty);

    public static void SetIsRound(DependencyObject element, bool value) => element.SetValue(IsRoundProperty, value);

    /// <summary>The radius that makes a box of this size a stadium (or a circle when square).</summary>
    public static double RadiusFor(double width, double height)
    {
        var smaller = Math.Min(width, height);
        return double.IsNaN(smaller) || smaller <= 0 ? 0 : smaller / 2;
    }

    private static void OnIsRoundChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is not Border border) return;
        border.SizeChanged -= OnSizeChanged;
        if (e.NewValue is true)
        {
            border.SizeChanged += OnSizeChanged;
            Apply(border);
        }
    }

    private static void OnSizeChanged(object sender, SizeChangedEventArgs e) => Apply((Border)sender);

    private static void Apply(Border border) =>
        border.CornerRadius = new CornerRadius(RadiusFor(border.ActualWidth, border.ActualHeight));
}
