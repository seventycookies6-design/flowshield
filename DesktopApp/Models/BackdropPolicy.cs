namespace FlowShield.Models;

/// <summary>What the main window's base (E0) is drawn with.</summary>
public enum Backdrop
{
    /// <summary>Windows' Mica material shows through a clear window background.</summary>
    Mica,

    /// <summary>The solid <c>mica-fallback</c> token colour.</summary>
    Solid,

    /// <summary>High contrast: the system's own window colour, never a token.</summary>
    HighContrast,
}

/// <summary>Which DWM call, if any, asks for Mica on this build of Windows.</summary>
public enum MicaApi
{
    /// <summary>Windows 10 and earlier: no Mica.</summary>
    None,

    /// <summary>
    /// Windows 11 21H2 (builds 22000 to 22620): the undocumented
    /// <c>DWMWA_MICA_EFFECT</c> (1029) = 1, the only switch that build has.
    /// </summary>
    MicaEffect,

    /// <summary>
    /// Windows 11 22H2 on (build 22621 and later): the documented
    /// <c>DWMWA_SYSTEMBACKDROP_TYPE</c> (38) = <c>DWMSBT_MAINWINDOW</c> (2).
    /// </summary>
    SystemBackdrop,
}

/// <summary>Everything the backdrop decision depends on, read fresh each time.</summary>
/// <param name="OsBuild">Windows' build number (22000 is the first Windows 11).</param>
/// <param name="TransparencyEnabled">
/// Settings, Personalisation, Colours, "Transparency effects"
/// (<c>HKCU\…\Themes\Personalize\EnableTransparency</c>).
/// </param>
/// <param name="BatterySaver">Battery or energy saver is on.</param>
/// <param name="WindowActive">The window is the active (foreground) one.</param>
/// <param name="HighContrast">A high-contrast theme is on.</param>
/// <param name="HardwareRendering">
/// WPF is drawing on the GPU. In software rendering a clear window background
/// is not reliably composited with the backdrop, so the solid colour is safer.
/// </param>
/// <param name="BackdropApplied">DWM accepted the Mica request (the call returned S_OK).</param>
public readonly record struct BackdropConditions(
    int OsBuild,
    bool TransparencyEnabled,
    bool BatterySaver,
    bool WindowActive,
    bool HighContrast,
    bool HardwareRendering,
    bool BackdropApplied);

/// <summary>
/// When the main window shows Mica and when it falls back (DESIGN_SYSTEM.md
/// Part A, Depth; #430): with transparency effects off, on Windows 10, in
/// battery saver or while the window is inactive, Mica becomes the solid token
/// surface and nothing else changes. High contrast uses system colours only.
///
/// Pure, so tier 1 can check every case through ModelProbe; the window code
/// (<c>Services/WindowBackdrop.cs</c>) only gathers the conditions and paints.
/// </summary>
public static class BackdropPolicy
{
    /// <summary>The first Windows 11 build. Below it there is no Mica.</summary>
    public const int FirstMicaBuild = 22000;

    /// <summary>The first build with the documented system-backdrop attribute.</summary>
    public const int FirstSystemBackdropBuild = 22621;

    /// <summary>The DWM switch for Mica on <paramref name="osBuild"/>.</summary>
    public static MicaApi ApiFor(int osBuild) => osBuild switch
    {
        >= FirstSystemBackdropBuild => MicaApi.SystemBackdrop,
        >= FirstMicaBuild => MicaApi.MicaEffect,
        _ => MicaApi.None,
    };

    /// <summary>
    /// Whether to ask DWM for Mica at all. Asked once the window has a handle
    /// and again when high contrast changes. Inactivity, battery saver and the
    /// transparency setting don't withdraw the request: DWM already draws the
    /// title bar's own fallback for those, and the client area is covered by
    /// the solid colour instead (<see cref="Decide"/>), so nothing flickers.
    /// </summary>
    public static bool RequestsMica(int osBuild, bool highContrast) =>
        !highContrast && ApiFor(osBuild) != MicaApi.None;

    /// <summary>What the window's base is drawn with under <paramref name="c"/>.</summary>
    public static Backdrop Decide(BackdropConditions c) => Explain(c).Backdrop;

    /// <summary>The decision and, for the log, the reason for it.</summary>
    public static (Backdrop Backdrop, string Reason) Explain(BackdropConditions c)
    {
        if (c.HighContrast) return (Backdrop.HighContrast, "high contrast is on");
        if (c.OsBuild < FirstMicaBuild) return (Backdrop.Solid, $"Windows build {c.OsBuild} has no Mica");
        if (!c.TransparencyEnabled) return (Backdrop.Solid, "transparency effects are off");
        if (c.BatterySaver) return (Backdrop.Solid, "battery saver is on");
        if (!c.HardwareRendering) return (Backdrop.Solid, "WPF is rendering in software");
        if (!c.BackdropApplied) return (Backdrop.Solid, "DWM did not accept the Mica request");
        if (!c.WindowActive) return (Backdrop.Solid, "the window is inactive");
        return (Backdrop.Mica, "Mica");
    }
}
