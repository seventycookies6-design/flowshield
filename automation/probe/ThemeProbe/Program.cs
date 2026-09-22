using System.Text.Json;
using System.Windows;
using System.Windows.Media;
using FlowShield.Models;
using FlowShield.Services;

// FlowShield's global usings pull System.Drawing in for the tray code, and it
// has an Application and a Brush of its own; this file means the WPF ones.
using Application = System.Windows.Application;
using Brush = System.Windows.Media.Brush;

namespace ThemeProbe;

/// <summary>
/// Loads FlowShield's real App.xaml, switches theme, and prints what each
/// colour resource resolves to, as JSON on stdout.
///
/// No window is created and nothing is shown. <c>new App()</c> sets
/// <see cref="Application.Current"/>, and <c>InitializeComponent()</c> merges
/// exactly the dictionaries App.xaml merges, in exactly the way it spells them
/// — which is the part a hand-built probe gets wrong and a source test cannot
/// see at all.
/// </summary>
internal static class Program
{
    /// <summary>Resources the probe reports, and the test asserts on.</summary>
    private static readonly string[] Brushes =
    {
        "Bg", "BgSoft", "Surface", "Surface2", "Ink", "InkDim", "InkFaint",
        "Primary", "PrimaryHover", "PrimaryInk", "Green", "Amber", "Rose",
        "FocusRing", "Scrim",
    };

    [STAThread]
    private static int Main()
    {
        try
        {
            var app = new FlowShield.App();
            app.InitializeComponent();

            var report = new Dictionary<string, object>
            {
                ["start"] = Snapshot(),
            };

            ThemeService.Apply(AppTheme.Light);
            report["light"] = Snapshot();

            ThemeService.Apply(AppTheme.Dark);
            report["dark"] = Snapshot();

            Console.WriteLine(JsonSerializer.Serialize(report));
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"{ex.GetType().Name}: {ex.Message}");
            return 1;
        }
    }

    private static Dictionary<string, object?> Snapshot()
    {
        var snapshot = new Dictionary<string, object?>
        {
            ["isLight"] = ThemeService.IsLight,
        };

        foreach (var key in Brushes)
        {
            snapshot[key] = (Application.Current.TryFindResource(key) as SolidColorBrush)
                ?.Color.ToString();
        }

        // The shield glyphs live inside DrawingImages, which is the case a
        // DynamicResource cannot serve; the dictionary is reloaded instead.
        snapshot["glyphSoft"] = GlyphColour("ShieldGlyphSoft");
        snapshot["glyphFirm"] = GlyphColour("ShieldGlyphFirm");

        // The heatmap ramp is mixed in code from two tokens, not bound to them.
        snapshot["heatTop"] = HeatStep(4);

        return snapshot;
    }

    private static string? GlyphColour(string key)
    {
        if (Application.Current.TryFindResource(key) is not DrawingImage image) return null;
        if (image.Drawing is not DrawingGroup group) return null;
        if (group.Children.FirstOrDefault() is not GeometryDrawing drawing) return null;
        var brush = (drawing.Pen?.Brush ?? drawing.Brush) as SolidColorBrush;
        return brush?.Color.ToString();
    }

    private static string? HeatStep(int step)
    {
        if (Application.Current.TryFindResource("HeatStep")
            is not System.Windows.Data.IValueConverter converter) return null;
        var value = converter.Convert(step, typeof(Brush), null!,
            System.Globalization.CultureInfo.InvariantCulture);
        return (value as SolidColorBrush)?.Color.ToString();
    }
}
