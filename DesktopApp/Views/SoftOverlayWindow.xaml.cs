using System.Windows;
using System.Windows.Input;
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

    /// <summary>
    /// Fills the monitor the blocked app's window is on.
    ///
    /// Screen coordinates are physical pixels and WPF's are device-independent,
    /// so they go through this window's own transform. A machine with two
    /// monitors at different scale factors can be a few pixels out at the edges;
    /// the panel is centred, so nothing important lands there.
    /// </summary>
    private void PlaceOverTheDistraction()
    {
        try
        {
            var screen = _anchor == IntPtr.Zero
                ? Forms.Screen.PrimaryScreen
                : Forms.Screen.FromHandle(_anchor);
            if (screen is null) return;

            var source = PresentationSource.FromVisual(this);
            var transform = source?.CompositionTarget?.TransformFromDevice;

            var topLeft = new System.Windows.Point(screen.Bounds.Left, screen.Bounds.Top);
            var size = new System.Windows.Point(screen.Bounds.Width, screen.Bounds.Height);
            if (transform is { } matrix)
            {
                topLeft = matrix.Transform(topLeft);
                size = matrix.Transform(size);
            }

            Left = topLeft.X;
            Top = topLeft.Y;
            Width = size.X;
            Height = size.Y;
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
