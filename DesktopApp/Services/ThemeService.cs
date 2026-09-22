using System.Windows;
using System.Windows.Data;
using System.Windows.Media;
using FlowShield.Models;
using Microsoft.Win32;

// System.Drawing is in scope through the tray code's global usings, and it has
// a Color of its own; this file means the WPF one.
using Color = System.Windows.Media.Color;

namespace FlowShield.Services;

/// <summary>
/// Swaps the app between the dark and light colour tokens while it runs
/// (F21, DESIGN_SYSTEM.md §12 "Theme").
///
/// How it works, and why it is done this way:
///
/// * <c>App.xaml</c> merges <c>Styles/Tokens.xaml</c> as its own entry, ahead of
///   everything else. A theme change replaces that one entry with
///   <c>Tokens.Light.xaml</c> (or back). Nothing else may merge a Tokens file:
///   a later merge shadows the swapped one and the app stays dark for ever.
/// * Every colour reference in XAML is a <c>DynamicResource</c>, so it
///   re-resolves through that slot the moment it is replaced.
/// * A <c>DynamicResource</c> inside a Freezable — the brushes in the shield
///   glyphs' <c>DrawingImage</c>s — resolves once and then never again, so
///   <c>ShieldGlyphs.xaml</c> is reloaded from scratch after the swap instead.
/// * C# that reads a colour through <c>FindResource</c> (the heatmap ramp, the
///   tier badge dot, the tray countdown icon) re-reads on <see cref="Changed"/>;
///   bindings that run such a converter are re-evaluated by
///   <see cref="RefreshConverterBindings"/>.
///
/// Following Windows is read-only: the app theme is read from
/// <c>HKCU\…\Themes\Personalize\AppsUseLightTheme</c> and re-read whenever
/// Windows says a user preference changed. FlowShield never writes there.
/// </summary>
public static class ThemeService
{
    private const string PersonalizeKey =
        @"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize";

    private static readonly Uri DarkTokens =
        new("pack://application:,,,/FlowShield;component/Styles/Tokens.xaml");

    private static readonly Uri LightTokens =
        new("pack://application:,,,/FlowShield;component/Styles/Tokens.Light.xaml");

    private static readonly Uri ShieldGlyphs =
        new("pack://application:,,,/FlowShield;component/Styles/ShieldGlyphs.xaml");

    private static bool _listening;

    /// <summary>Raised after the resources have been swapped, on the UI thread.</summary>
    public static event EventHandler? Changed;

    /// <summary>What the user chose: System, Dark or Light.</summary>
    public static AppTheme Preference { get; private set; } = AppTheme.System;

    /// <summary>Whether the light tokens are the ones in force right now.</summary>
    public static bool IsLight { get; private set; }

    /// <summary>
    /// Applies the stored preference at startup and starts following Windows.
    /// Safe to call more than once.
    /// </summary>
    public static void Initialise(AppSettings settings)
    {
        Apply(settings.Theme);

        if (_listening) return;
        try
        {
            SystemEvents.UserPreferenceChanged += OnUserPreferenceChanged;
            _listening = true;
        }
        catch (Exception ex)
        {
            // Not fatal: the app still honours an explicit Dark or Light choice,
            // it just will not notice Windows changing under it.
            Log.Warn($"cannot follow the Windows theme: {ex.Message}");
        }
    }

    /// <summary>Switches to <paramref name="preference"/> and redraws.</summary>
    public static void Apply(AppTheme preference)
    {
        Preference = preference;
        var light = preference switch
        {
            AppTheme.Light => true,
            AppTheme.Dark => false,
            _ => WindowsPrefersLight(),
        };
        Swap(light);
    }

    /// <summary>
    /// Windows' own app theme, from HKCU. Read-only, and dark when the value is
    /// missing or unreadable — that is both Windows' default for this key's
    /// absence on older builds and FlowShield's own default.
    /// </summary>
    public static bool WindowsPrefersLight()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(PersonalizeKey);
            return key?.GetValue("AppsUseLightTheme") is int value && value != 0;
        }
        catch (Exception ex)
        {
            Log.Warn($"cannot read the Windows app theme: {ex.Message}");
            return false;
        }
    }

    private static void Swap(bool light)
    {
        var app = Application.Current;
        if (app is null) return;

        // Re-merging an unchanged theme would still rebuild the glyphs and walk
        // every window; a no-op stays a no-op.
        if (_applied && IsLight == light) return;

        var merged = app.Resources.MergedDictionaries;
        var tokens = merged.FirstOrDefault(d => IsTokens(d.Source));
        if (tokens is null)
        {
            Log.Warn("theme not switched: no Tokens dictionary is merged in App.Resources");
            return;
        }

        try
        {
            merged[merged.IndexOf(tokens)] = new ResourceDictionary { Source = light ? LightTokens : DarkTokens };

            var glyphs = merged.FirstOrDefault(d => d.Source == ShieldGlyphs);
            if (glyphs is not null)
                merged[merged.IndexOf(glyphs)] = new ResourceDictionary { Source = ShieldGlyphs };
        }
        catch (Exception ex)
        {
            Log.Error("theme switch failed", ex);
            return;
        }

        IsLight = light;
        _applied = true;
        Log.Info($"theme applied: {(light ? "light" : "dark")} (preference {Preference})");

        foreach (var window in app.Windows.OfType<Window>())
            RefreshConverterBindings(window);

        Changed?.Invoke(null, EventArgs.Empty);
    }

    private static bool _applied;

    private static bool IsTokens(Uri? source) =>
        source is not null && (source == DarkTokens || source == LightTokens);

    /// <summary>
    /// Re-evaluates every bound property whose binding runs a converter, on
    /// <paramref name="root"/> and everything under it.
    ///
    /// A converter that looks a colour up itself — HeatStepToBrushConverter's
    /// ramp, ResourceKeyToBrushConverter's tier dot, ShieldLevelToGlyphConverter
    /// — produced its value before the swap, and nothing tells WPF to ask again.
    /// Converters that have nothing to do with colour are re-run too; they are
    /// pure functions of their source, so the value simply comes back the same.
    /// </summary>
    public static void RefreshConverterBindings(DependencyObject? root)
    {
        if (root is null) return;

        var values = root.GetLocalValueEnumerator();
        while (values.MoveNext())
        {
            if (values.Current.Value is BindingExpression { ParentBinding.Converter: not null } binding)
                binding.UpdateTarget();
        }

        if (root is not Visual && root is not System.Windows.Media.Media3D.Visual3D) return;
        var children = VisualTreeHelper.GetChildrenCount(root);
        for (var i = 0; i < children; i++)
            RefreshConverterBindings(VisualTreeHelper.GetChild(root, i));
    }

    /// <summary>
    /// A themed colour for code that has to draw rather than bind — the tray's
    /// countdown icon, the heatmap ramp. False when the resource is missing, so
    /// callers degrade rather than reach for a hard-coded colour of their own
    /// (DESIGN_SYSTEM.md §2: every colour comes from a token).
    /// </summary>
    public static bool TryColour(string key, out Color colour)
    {
        if (Application.Current?.TryFindResource(key) is Color found)
        {
            colour = found;
            return true;
        }

        colour = Colors.Transparent;
        return false;
    }

    private static void OnUserPreferenceChanged(object? sender, UserPreferenceChangedEventArgs e)
    {
        if (Preference != AppTheme.System) return;
        if (e.Category is not (UserPreferenceCategory.General or UserPreferenceCategory.Color
            or UserPreferenceCategory.VisualStyle)) return;

        // Windows raises this on its own thread.
        Application.Current?.Dispatcher.BeginInvoke(() => Apply(AppTheme.System));
    }
}
