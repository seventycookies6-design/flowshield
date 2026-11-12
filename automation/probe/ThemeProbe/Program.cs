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
            report["ringCaptions"] = RingCaptions();

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

    /// <summary>
    /// Every status line the view model can put beside "Now" (#304, moved out
    /// of the ring by #431), laid out in the real TodayView with the app's own
    /// resources and font, and the lines that stay inside the ring: the
    /// countdown, "ends …" or "until …", "if you start now" and a cycle's
    /// "Sprint 4 of 4". Nothing is shown; the view is measured and arranged
    /// offscreen. Status boxes are in the Now card's coordinates and ring
    /// boxes in the ring's own, as [x, y, width, height].
    /// </summary>
    private static List<Dictionary<string, object?>> RingCaptions()
    {
        var view = new FlowShield.Views.TodayView();
        var ring = (FrameworkElement)view.FindName("TimerRing");
        var card = (FrameworkElement)view.FindName("NowCard");
        var caption = Find<System.Windows.Controls.TextBlock>(view, "SessionStateText");
        var timer = Find<System.Windows.Controls.TextBlock>(view, "SprintTimerText");
        var ends = Find<System.Windows.Controls.TextBlock>(view, "RingEndsText");
        var cycle = Find<System.Windows.Controls.TextBlock>(view, "CycleProgressText");
        var hint = Find<System.Windows.Controls.TextBlock>(view, "RingEndsHint");
        var stroke = ((System.Windows.Shapes.Ellipse)((System.Windows.Controls.Panel)ring).Children[0]).StrokeThickness;

        // Nothing is bound: the probe sets each piece the view model would.
        // Under an hour the timer reads MM:SS in tabular digits, so every
        // such time is as wide, and as tall, as this one; longer ones shrink.
        timer.Text = "25:00";
        ends.Text = "until 10:49 PM";
        hint.Text = "if you start now";
        cycle.Text = "Sprint 4 of 4";

        var typeface = new Typeface(caption.FontFamily, caption.FontStyle, caption.FontWeight, caption.FontStretch);
        var font = typeface.TryGetGlyphTypeface(out var glyphs) ? glyphs.FontUri.Segments.LastOrDefault() : null;

        var results = new List<Dictionary<string, object?>>();
        foreach (var (text, running) in RingCaption.Every())
        {
            foreach (var below in new[] { "none", "cycle" })
            {
                caption.Text = text;
                hint.Visibility = running ? Visibility.Collapsed : Visibility.Visible;
                cycle.Visibility = below == "cycle" ? Visibility.Visible : Visibility.Collapsed;

                // The smallest Today the window allows (800 wide less the
                // compact rail and margins); the ring is laid out at 222 and
                // scaled as a whole, so its own boxes don't depend on it.
                view.Measure(new System.Windows.Size(660, 1600));
                view.Arrange(new Rect(0, 0, 660, 1600));
                view.UpdateLayout();

                var lineHeight = caption.LineHeight > 0 ? caption.LineHeight : caption.FontSize * 1.4;
                results.Add(new Dictionary<string, object?>
                {
                    ["text"] = text,
                    ["running"] = running,
                    ["below"] = below,
                    ["styled"] = caption.Style is not null,
                    ["fontSize"] = caption.FontSize,
                    ["font"] = font,
                    ["lines"] = (int)Math.Round(caption.ActualHeight / lineHeight),
                    ["cardWidth"] = card.ActualWidth,
                    ["caption"] = Box(caption, card),
                    ["ringDiameter"] = ring.ActualWidth,
                    ["ringStroke"] = stroke,
                    ["ends"] = Box(ends, ring),
                    ["hint"] = running ? null : Box(hint, ring),
                    ["cycle"] = below == "cycle" ? Box(cycle, ring) : null,
                    ["timerText"] = timer.Text,
                    ["timer"] = Box(timer, ring),
                });
            }
        }
        return results;
    }

    private static T Find<T>(DependencyObject root, string automationId) where T : DependencyObject =>
        Search<T>(root, automationId)
        ?? throw new InvalidOperationException($"TodayView has no {typeof(T).Name} with AutomationId {automationId}");

    private static T? Search<T>(DependencyObject root, string automationId) where T : DependencyObject
    {
        foreach (var child in LogicalTreeHelper.GetChildren(root).OfType<DependencyObject>())
        {
            if (child is T match && System.Windows.Automation.AutomationProperties.GetAutomationId(child) == automationId)
                return match;
            if (Search<T>(child, automationId) is { } found)
                return found;
        }
        return null;
    }

    /// <summary>An element's rendered box in the ring's coordinates, rounded to a tenth.</summary>
    private static double[] Box(FrameworkElement element, FrameworkElement ring)
    {
        var box = element.TransformToAncestor(ring)
            .TransformBounds(new Rect(0, 0, element.ActualWidth, element.ActualHeight));
        return new[] { Math.Round(box.X, 1), Math.Round(box.Y, 1), Math.Round(box.Width, 1), Math.Round(box.Height, 1) };
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
