using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
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
/// It notices; it never closes anything. The blocked app is still running when
/// this window goes away, at either button — Soft's promise is that it only
/// notes distractions, and this screen must not quietly break it.
/// </summary>
public partial class SoftOverlayWindow : Window
{
    /// <summary>Back to work, or Escape, which is the same thing.</summary>
    public event EventHandler? BackToWork;

    /// <summary>Allow 5 minutes.</summary>
    public event EventHandler? AllowFiveMinutes;

    /// <summary>The blocked app's window, so the notice opens on its monitor.</summary>
    private IntPtr _anchor;

    /// <summary>Set once either button has been answered, so neither fires twice.</summary>
    private bool _answered;

    public SoftOverlayWindow()
    {
        InitializeComponent();
    }

    /// <summary>Fills in the one sentence and the time left. Called before Show.</summary>
    public void Configure(string sentence, string timeLeft, IntPtr anchor)
    {
        SentenceText.Text = sentence;
        TimeLeftText.Text = timeLeft;
        _anchor = anchor;
    }

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        PlaceOverTheDistraction();
        // The primary action has focus, so Space or Enter is Back to work and
        // nothing else on this screen can be reached by mistake.
        BackToWorkButton.Focus();
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

    private void OnBackToWork(object sender, RoutedEventArgs e) => Answer(BackToWork);

    private void OnAllowFiveMinutes(object sender, RoutedEventArgs e) => Answer(AllowFiveMinutes);

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
