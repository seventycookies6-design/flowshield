using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;
using FlowShield.Models;
using Microsoft.Win32;

namespace FlowShield.Services;

/// <summary>
/// Mica on the main window, with the solid fallback (DESIGN_SYSTEM.md Part A,
/// Depth; design/redesign-2026-11/README.md; #430).
///
/// How it is built:
///
/// * Once the window has a handle, DWM is asked for Mica
///   (<c>DWMWA_SYSTEMBACKDROP_TYPE</c> = <c>DWMSBT_MAINWINDOW</c>, or
///   <c>DWMWA_MICA_EFFECT</c> on Windows 11 21H2), the frame is extended into the
///   whole client area, and WPF's own composition background is made clear, so
///   the material can show behind the content. The standard title bar stays,
///   with Snap Layouts, the system menu and keyboard access; Mica covers it too.
/// * Whether it does show is <see cref="BackdropPolicy"/>'s decision. When it
///   says Mica, the window's background is the clear <c>BackdropClear</c>; when
///   it says Solid, the <c>MicaFallback</c> token; in high contrast, the system's
///   window colour. Everything else (surfaces, controls, text) is the same in
///   all three.
/// * The decision is re-made live: on activation and deactivation, on
///   <c>WM_SETTINGCHANGE</c> (transparency effects, high contrast), on
///   <c>WM_POWERBROADCAST</c> (battery saver), on <c>WM_DWMCOMPOSITIONCHANGED</c>
///   and when WPF's rendering tier changes.
///
/// It never writes a Windows setting: transparency and battery saver are read.
/// </summary>
public sealed class WindowBackdrop
{
    private const int DWMWA_SYSTEMBACKDROP_TYPE = 38;
    private const int DWMSBT_MAINWINDOW = 2;
    private const int DWMSBT_NONE = 1;
    private const int DWMWA_MICA_EFFECT = 1029;

    private const int WM_SETTINGCHANGE = 0x001A;
    private const int WM_POWERBROADCAST = 0x0218;
    private const int WM_DWMCOMPOSITIONCHANGED = 0x031E;

    private const string PersonalizeKey =
        @"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize";

    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

    [StructLayout(LayoutKind.Sequential)]
    private struct Margins
    {
        public int Left, Right, Top, Bottom;
    }

    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmExtendFrameIntoClientArea(IntPtr hwnd, ref Margins margins);

    [StructLayout(LayoutKind.Sequential)]
    private struct SystemPowerStatus
    {
        public byte ACLineStatus, BatteryFlag, BatteryLifePercent, SystemStatusFlag;
        public int BatteryLifeTime, BatteryFullLifeTime;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetSystemPowerStatus(out SystemPowerStatus status);

    private readonly Window _window;
    private IntPtr _hwnd;
    private bool _requested;
    private bool _applied;
    private Backdrop? _current;

    /// <summary>The backdrop in force, for tests and the log.</summary>
    public Backdrop? Current => _current;

    /// <summary>What the last DWM request returned (0 is S_OK), or null if none was made.</summary>
    public int? LastResult { get; private set; }

    public WindowBackdrop(Window window)
    {
        _window = window;
    }

    /// <summary>Call from <c>OnSourceInitialized</c>, once the window has a handle.</summary>
    public void Attach()
    {
        _hwnd = new WindowInteropHelper(_window).Handle;
        if (_hwnd == IntPtr.Zero) return;

        HwndSource.FromHwnd(_hwnd)?.AddHook(WndProc);
        _window.Activated += (_, _) => Update("activated");
        _window.Deactivated += (_, _) => Update("deactivated");
        RenderCapability.TierChanged += (_, _) => Update("rendering tier changed");
        ThemeService.Changed += (_, _) => OnThemeChanged();

        Request();
        Update("window created");
    }

    /// <summary>Asks DWM for Mica, or withdraws the request in high contrast.</summary>
    private void Request()
    {
        var build = Environment.OSVersion.Version.Build;
        var want = BackdropPolicy.RequestsMica(build, SystemParameters.HighContrast);
        if (want == _requested && LastResult is not null) return;

        try
        {
            int hr;
            switch (BackdropPolicy.ApiFor(build))
            {
                case MicaApi.SystemBackdrop:
                    var type = want ? DWMSBT_MAINWINDOW : DWMSBT_NONE;
                    hr = DwmSetWindowAttribute(_hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ref type, sizeof(int));
                    break;
                case MicaApi.MicaEffect:
                    var on = want ? 1 : 0;
                    hr = DwmSetWindowAttribute(_hwnd, DWMWA_MICA_EFFECT, ref on, sizeof(int));
                    break;
                default:
                    _requested = false;
                    _applied = false;
                    Log.Info($"backdrop: Windows build {build} has no Mica; solid colours");
                    return;
            }

            LastResult = hr;
            _requested = want;
            _applied = want && hr == 0;

            // The frame reaches over the whole client area only while Mica is
            // requested, so DWM draws it behind the content; WPF then leaves the
            // pixels it doesn't paint clear instead of black.
            var margins = _applied ? new Margins { Left = -1, Right = -1, Top = -1, Bottom = -1 } : new Margins();
            var extend = DwmExtendFrameIntoClientArea(_hwnd, ref margins);
            if (_applied && HwndSource.FromHwnd(_hwnd)?.CompositionTarget is { } target)
                target.BackgroundColor = System.Windows.Media.Colors.Transparent;

            Log.Info($"backdrop: DWM {(want ? "Mica" : "no backdrop")} request returned 0x{hr:X8}, " +
                     $"frame extend 0x{extend:X8} (build {build})");
        }
        catch (Exception ex)
        {
            _applied = false;
            Log.Warn($"backdrop: Mica unavailable: {ex.Message}");
        }
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

    private const uint SWP_NOSIZE = 0x0001, SWP_NOMOVE = 0x0002, SWP_NOZORDER = 0x0004,
                       SWP_NOACTIVATE = 0x0010, SWP_FRAMECHANGED = 0x0020;

    /// <summary>
    /// A light/dark switch while the app runs. MainWindow has already told DWM
    /// the new title-bar theme, but DWM keeps drawing the material it drew
    /// under the clear client area until the frame is redrawn, so a window
    /// switched to light stayed dark underneath (found by tier 3's
    /// TestLightTheme on the VM). The request is renewed and the frame
    /// redrawn, so the material follows the theme straight away.
    /// </summary>
    private void OnThemeChanged()
    {
        if (_applied)
        {
            try
            {
                var build = Environment.OSVersion.Version.Build;
                if (BackdropPolicy.ApiFor(build) == MicaApi.SystemBackdrop)
                {
                    var none = DWMSBT_NONE;
                    DwmSetWindowAttribute(_hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ref none, sizeof(int));
                    var mica = DWMSBT_MAINWINDOW;
                    LastResult = DwmSetWindowAttribute(_hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ref mica, sizeof(int));
                }
                SetWindowPos(_hwnd, IntPtr.Zero, 0, 0, 0, 0,
                             SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
            }
            catch (Exception ex)
            {
                Log.Warn($"backdrop: could not redraw the frame after a theme change: {ex.Message}");
            }
        }
        Update("theme changed");
    }

    /// <summary>Re-reads every condition and repaints the window's base if it changed.</summary>
    public void Update(string why)
    {
        if (_hwnd == IntPtr.Zero) return;
        var conditions = Read();
        var (backdrop, reason) = BackdropPolicy.Explain(conditions);
        if (backdrop == _current) return;

        _current = backdrop;
        switch (backdrop)
        {
            case Backdrop.Mica:
                _window.SetResourceReference(Control.BackgroundProperty, "BackdropClear");
                break;
            case Backdrop.HighContrast:
                _window.SetResourceReference(Control.BackgroundProperty, System.Windows.SystemColors.WindowBrushKey);
                break;
            default:
                _window.SetResourceReference(Control.BackgroundProperty, "MicaFallback");
                break;
        }
        Log.Info($"backdrop: {backdrop.ToString().ToLowerInvariant()} ({reason}; after {why})");
    }

    private BackdropConditions Read() => new(
        OsBuild: Environment.OSVersion.Version.Build,
        TransparencyEnabled: TransparencyEnabled(),
        BatterySaver: BatterySaverOn(),
        WindowActive: _window.IsActive,
        HighContrast: SystemParameters.HighContrast,
        HardwareRendering: (RenderCapability.Tier >> 16) > 0,
        BackdropApplied: _applied);

    /// <summary>Windows' transparency-effects switch, read-only. On when unreadable, as Windows defaults.</summary>
    private static bool TransparencyEnabled()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(PersonalizeKey);
            return key?.GetValue("EnableTransparency") is not int value || value != 0;
        }
        catch (Exception ex)
        {
            Log.Warn($"backdrop: cannot read the transparency setting: {ex.Message}");
            return true;
        }
    }

    /// <summary>Battery (energy) saver, from GetSystemPowerStatus's SystemStatusFlag.</summary>
    private static bool BatterySaverOn() =>
        GetSystemPowerStatus(out var status) && status.SystemStatusFlag == 1;

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        switch (msg)
        {
            case WM_SETTINGCHANGE:
                // High contrast changes what is requested, not only what is painted.
                _window.Dispatcher.BeginInvoke(() =>
                {
                    Request();
                    Update("a Windows setting changed");
                });
                break;
            case WM_POWERBROADCAST:
                _window.Dispatcher.BeginInvoke(() => Update("power status changed"));
                break;
            case WM_DWMCOMPOSITIONCHANGED:
                _window.Dispatcher.BeginInvoke(() => Update("DWM composition changed"));
                break;
        }
        return IntPtr.Zero;
    }
}
