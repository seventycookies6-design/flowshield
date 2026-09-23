using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Threading;
using FlowShield.Models;
using FlowShield.Services;
using Forms = System.Windows.Forms;

namespace FlowShield.Views;

/// <summary>
/// The Soft shield's full-screen notice (launch checklist F7, roadmap 1.7).
///
/// A separate topmost window rather than a panel inside MainWindow: the whole
/// point is that it appears over the distraction, on the monitor the
/// distraction is on, when FlowShield's own window is behind everything.
///
/// It never closes anything on its own. Back to work and Allow leave the
/// blocked app running. Close (1.0.10) is the user's choice: this window only
/// raises <see cref="CloseIt"/>, and MainWindow hands it to the view model,
/// which asks the app to close and never kills it. Soft's promise is that
/// nothing is closed unless you choose to, and this screen must not quietly
/// break it.
/// </summary>
public partial class SoftOverlayWindow : Window
{
    /// <summary>Back to work, or Escape, which is the same thing.</summary>
    public event EventHandler? BackToWork;

    /// <summary>Allow 5 minutes, once its wait has run out.</summary>
    public event EventHandler? AllowFiveMinutes;

    /// <summary>"Close Discord": the user's choice. MainWindow passes it to the view model, which asks the blocker.</summary>
    public event EventHandler? CloseIt;

    /// <summary>The blocked app's window, so the notice opens on its monitor.</summary>
    private IntPtr _anchor;

    /// <summary>Set once any button has been answered, so none fires twice.</summary>
    private bool _answered;

    /// <summary>Counts down the wait before Allow can be pressed.</summary>
    private DispatcherTimer? _allowTimer;

    /// <summary>When Allow becomes pressable.</summary>
    private DateTime _allowAtUtc;

    public SoftOverlayWindow()
    {
        InitializeComponent();
    }

    /// <summary>Fills in the notice. Called before Show.</summary>
    public void Configure(string displayName, string sentence, string timeLeft, IntPtr anchor,
                          string intention, string tryLine, TimeSpan allowWait)
    {
        SentenceText.Text = sentence;
        TimeLeftText.Text = timeLeft;
        IntentionText.Text = intention;
        IntentionText.Visibility = intention.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
        TryLineText.Text = tryLine;
        CloseButton.Content = $"Close {displayName}";
        AutomationProperties.SetName(CloseButton, $"Close {displayName}");
        _anchor = anchor;

        // The wait before Allow (1.0.10). Text only, so reduced motion changes nothing.
        _allowAtUtc = DateTime.UtcNow + allowWait;
        AllowButton.IsEnabled = false;
        AllowButton.Content = SoftOverlayCopy.AllowLabel(allowWait);
        _allowTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(250) };
        _allowTimer.Tick += (_, _) => UpdateAllow();
        _allowTimer.Start();
    }

    private void UpdateAllow()
    {
        var left = _allowAtUtc - DateTime.UtcNow;
        AllowButton.Content = SoftOverlayCopy.AllowLabel(left);
        if (left > TimeSpan.Zero) return;
        AllowButton.IsEnabled = true;
        _allowTimer?.Stop();
    }

    protected override void OnClosed(EventArgs e)
    {
        _allowTimer?.Stop();
        base.OnClosed(e);
    }

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        PlaceOverTheDistraction();
        // The primary action has focus, so Enter is Close; Escape is Back to work.
        CloseButton.Focus();
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(IntPtr window, IntPtr insertAfter,
                                            int x, int y, int cx, int cy, uint flags);

    private static readonly IntPtr HWND_TOPMOST = new(-1);
    private const uint SWP_NOACTIVATE = 0x0010;

    /// <summary>
    /// Fills the monitor the blocked app's window is on.
    ///
    /// Placed with <c>SetWindowPos</c> in the monitor's own physical pixels
    /// rather than through WPF's <c>Left</c>/<c>Top</c>/<c>Width</c>/<c>Height</c>.
    /// Those are device-independent units scaled by the DPI of the monitor the
    /// window is on *at the time* — which, before the move, is whichever monitor
    /// Windows first opened it on. On a 150%/100% pair that left the scrim
    /// covering two thirds of the second screen, with the desktop showing round
    /// the edges. Physical pixels need no conversion and cannot be scaled by the
    /// wrong monitor's factor.
    /// </summary>
    private void PlaceOverTheDistraction()
    {
        try
        {
            var screen = _anchor == IntPtr.Zero
                ? Forms.Screen.PrimaryScreen
                : Forms.Screen.FromHandle(_anchor);
            if (screen is null) return;

            var handle = new WindowInteropHelper(this).Handle;
            if (handle == IntPtr.Zero) return;

            var bounds = screen.Bounds;
            if (!SetWindowPos(handle, HWND_TOPMOST, bounds.Left, bounds.Top,
                              bounds.Width, bounds.Height, SWP_NOACTIVATE))
            {
                Log.Warn("could not place the soft notice over the blocked app's monitor");
            }
        }
        catch (Exception ex)
        {
            // A notice in the wrong place is still a notice; a crash is not.
            Log.Warn($"could not place the soft notice on the right monitor: {ex.Message}");
        }
    }

    private void OnCloseIt(object sender, RoutedEventArgs e) => Answer(CloseIt);

    private void OnBackToWork(object sender, RoutedEventArgs e) => Answer(BackToWork);

    /// <summary>
    /// Refuses until the wait has run out. The disabled button already can't be
    /// clicked; the gate also sits where the click lands, not only in how the
    /// button looks (CLAUDE.md, "covered controls").
    /// </summary>
    private void OnAllowFiveMinutes(object sender, RoutedEventArgs e)
    {
        if (!AllowButton.IsEnabled) return;
        Answer(AllowFiveMinutes);
    }

    /// <summary>
    /// Escape is Back to work. Button.IsCancel already does this for a dialog;
    /// this window is shown, not dialogued, so the key is handled here too — and
    /// <see cref="_answered"/> makes the duplicate harmless.
    /// </summary>
    protected override void OnPreviewKeyDown(KeyEventArgs e)
    {
        base.OnPreviewKeyDown(e);
        if (e.Key != Key.Escape) return;
        e.Handled = true;
        Answer(BackToWork);
    }

    private void Answer(EventHandler? handler)
    {
        if (_answered) return;
        _answered = true;
        handler?.Invoke(this, EventArgs.Empty);
    }
}
