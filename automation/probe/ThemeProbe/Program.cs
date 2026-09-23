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
///
/// With the same real resources it also measures the break captions in the
/// app's Caption style and embedded Inter (#301), because whether a line fits
/// inside the timer ring is a question about pixels, not about source text.
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

            report["breakCaptions"] = BreakCaptions();

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

    /// <summary>
    /// Each break caption (#301) as the app lays it out: a TextBlock in the
    /// Caption style, measured at unlimited width. That is what the ring does
    /// too — the state line sits in a horizontal StackPanel, which measures its
    /// text at infinite width, so the caption never wraps. The font file is
    /// reported so a test can tell measured Inter from a silent fallback.
    /// </summary>
    private static List<Dictionary<string, object?>> BreakCaptions()
    {
        var style = Application.Current.TryFindResource("Caption") as Style;
        var captions = new List<Dictionary<string, object?>>();
        foreach (var inSleepWindow in new[] { false, true })
        {
            foreach (var resumed in new[] { false, true })
            {
                var text = BreakCopy.Caption(inSleepWindow, resumed);
                var block = new System.Windows.Controls.TextBlock { Text = text };
                if (style is not null) block.Style = style;
                block.Measure(new System.Windows.Size(double.PositiveInfinity, double.PositiveInfinity));

                var typeface = new Typeface(block.FontFamily, block.FontStyle, block.FontWeight, block.FontStretch);
                var font = typeface.TryGetGlyphTypeface(out var glyphs)
                    ? glyphs.FontUri.Segments.LastOrDefault()
                    : null;

                captions.Add(new Dictionary<string, object?>
                {
                    ["inSleepWindow"] = inSleepWindow,
                    ["resumed"] = resumed,
                    ["text"] = text,
                    ["styled"] = style is not null,
                    ["fontSize"] = block.FontSize,
                    ["font"] = font,
                    ["width"] = Math.Round(block.DesiredSize.Width, 1),
                });
            }
        }
        return captions;
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
