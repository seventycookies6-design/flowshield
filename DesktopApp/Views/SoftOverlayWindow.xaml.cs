using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media.Animation;
using System.Windows.Threading;
using FlowShield.Infrastructure;
using FlowShield.Models;
using FlowShield.Services;
using Forms = System.Windows.Forms;

namespace FlowShield.Views;

/// <summary>
/// The Soft shield's full-screen notice (launch checklist F7, roadmap 1.7),
/// redesigned as a band across the screen in #432.
///
/// A separate topmost window rather than a panel inside MainWindow: the whole
/// point is that it appears over the distraction, on the monitor the
/// distraction is on, when Basalt's own window is behind everything.
///
/// It never closes anything on its own. Back to work and Allow leave the
/// blocked app running. Close (1.0.10) is the user's choice: this window only
/// raises <see cref="CloseIt"/>, and MainWindow hands it to the view model,
/// which asks the app to close and never kills it. Soft's promise is that
/// nothing is closed unless you choose to, and this screen must not quietly
/// break it.
///
/// <para><b>The input guard</b> (DESIGN_SYSTEM.md Part A, Interruptions). The
/// notice lands up to one blocker sweep after the blocked app came to the
/// front, while the user may still be typing in it, so it can't be answered by
/// accident:</para>
/// <list type="bullet">
/// <item>No button is the default or the cancel button, and focus starts on the
/// band, not a button.</item>
/// <item>Enter does nothing: <see cref="OnPreviewKeyDown"/> swallows it.</item>
/// <item>For <see cref="SoftOverlayPolicy.InputLock"/> (about 1.5 s) every button
/// ignores input: clicks, Space and Enter. They stay enabled, so their labels
/// keep full contrast, but aren't focusable, and the lock bar shows the
/// wait. The gate also sits in each Click handler, where a UI Automation
/// Invoke lands too (CLAUDE.md, "covered controls").</item>
/// <item>After that, a click works, and so does a deliberate Tab then Space.</item>
/// </list>
/// </summary>
public partial class SoftOverlayWindow : Window
{
    /// <summary>Back to work, or Escape once the buttons have unlocked.</summary>
    public event EventHandler? BackToWork;

    /// <summary>Allow 5 minutes, once its wait has run out.</summary>
    public event EventHandler? AllowFiveMinutes;

    /// <summary>"Close Discord": the user's choice. MainWindow passes it to the view model, which asks the blocker.</summary>
    public event EventHandler? CloseIt;

    /// <summary>How much of the sprint is left, 0 to 1: the ring's arc.</summary>
    public static readonly DependencyProperty RingRemainingProperty = DependencyProperty.Register(
        nameof(RingRemaining), typeof(double), typeof(SoftOverlayWindow), new PropertyMetadata(1.0));

    public double RingRemaining
    {
        get => (double)GetValue(RingRemainingProperty);
        set => SetValue(RingRemainingProperty, value);
    }

    /// <summary>The blocked app's window, so the notice opens on its monitor.</summary>
    private IntPtr _anchor;

    /// <summary>A website's notice (F10 interim), which has no Close.</summary>
    private bool _isWebsite;

    /// <summary>Set once any button has been answered, so none fires twice.</summary>
    private bool _answered;

    /// <summary>
    /// True while every button ignores input (#432). Cleared once, by
    /// <see cref="UpdateGuard"/>, when the lock's tick deadline passes.
    /// </summary>
    private bool _locked = true;

    /// <summary>
    /// When the buttons unlock, and when Allow becomes pressable, as tick
    /// counts: the monotonic clock, so a wall-clock change during the wait
    /// (an hour back) cannot stretch either.
    /// </summary>
    private long _unlockAtTick;
    private long _allowAtTick;

    /// <summary>Reduced motion, read once: the lock bar then stays still and is hidden.</summary>
    private bool _reducedMotion;

    /// <summary>Counts down the lock and Allow's wait.</summary>
    private DispatcherTimer? _guardTimer;

    /// <summary>
    /// Keeps the ring's time left current while the notice is up (#347). It
    /// read the time left once, so a notice left open said "25 minutes left"
    /// for as long as it stayed.
    /// </summary>
    private DispatcherTimer? _timeLeftTimer;

    public SoftOverlayWindow()
    {
        InitializeComponent();
        SizeChanged += (_, _) => FitTextColumn();
        foreach (var button in Buttons)
        {
            // While a button ignores input, a press never reaches it: no pressed
            // look and no click. A press that began during the lock and ends
            // after it is not a click either.
            var pressed = button;
            pressed.PreviewMouseLeftButtonDown += (_, e) =>
            {
                if (!Accepts(pressed)) e.Handled = true;
            };
            button.Focusable = false;
        }
    }

    private IEnumerable<Button> Buttons => new[] { BackToWorkButton, CloseButton, AllowButton };

    /// <summary>Fills in the notice. Called before Show.</summary>
    /// <remarks>
    /// <paramref name="plan"/> is the customer's plan for this sprint, the
    /// headline; empty when none was typed, and the sentence takes its place.
    /// <paramref name="tryNumber"/> is this notice's try this sprint; the
    /// count shows from the second.
    /// <paramref name="isWebsite"/> (F10 interim): the name is a site in a
    /// browser tab. There is no Close for it, because asking the browser to
    /// close would close every tab, so the button is collapsed rather than
    /// disabled and nothing can raise <see cref="CloseIt"/>.
    /// </remarks>
    public void Configure(string displayName, string sentence, Func<TimeSpan> remaining, Func<double> ringRemaining,
                          IntPtr anchor, string plan, int tryNumber, TimeSpan allowWait, bool isWebsite = false)
    {
        var hasPlan = plan.Length > 0;
        ShowEyebrow(SoftOverlayCopy.Eyebrow(hasPlan, isWebsite));
        IntentionText.Text = plan;
        IntentionText.Visibility = hasPlan ? Visibility.Visible : Visibility.Collapsed;
        if (hasPlan)
        {
            SentenceText.Text = sentence + ".";
        }
        else
        {
            // No plan: the sentence is the headline, said once (Part A: the
            // same fact is not stated twice on one screen).
            SentenceText.Text = SoftOverlayCopy.Headline(plan, sentence);
            SentenceText.Style = (Style)FindResource("H1");
            SentenceText.FontSize = 52;
            SentenceText.LineHeight = 60;
            SentenceText.Margin = new Thickness(0, 6, 0, 10);
        }

        TryLineText.Text = SoftOverlayCopy.TryLine(tryNumber) + ".";
        TryLineText.Visibility = SoftOverlayCopy.ShowsTryLine(tryNumber) ? Visibility.Visible : Visibility.Collapsed;

        ShowTimeLeft(remaining(), ringRemaining());
        _timeLeftTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _timeLeftTimer.Tick += (_, _) => ShowTimeLeft(remaining(), ringRemaining());
        _timeLeftTimer.Start();

        CloseButton.Content = $"Close {displayName}";
        AutomationProperties.SetName(CloseButton, $"Close {displayName}");
        _isWebsite = isWebsite;
        if (isWebsite)
        {
            CloseButton.Visibility = Visibility.Collapsed;
            NoteText.Text = SoftOverlayCopy.WebsiteNote;
            AutomationProperties.SetName(this, "Blocked website notice");
        }
        _anchor = anchor;

        // The lock (#432) and Allow's own longer wait (1.0.10) start together.
        var now = Environment.TickCount64;
        _unlockAtTick = now + (long)SoftOverlayPolicy.InputLock.TotalMilliseconds;
        _allowAtTick = now + (long)Math.Max(allowWait.TotalMilliseconds, SoftOverlayPolicy.InputLock.TotalMilliseconds);
        _reducedMotion = !Motion.AnimationsEnabled;
        AllowButton.Content = SoftOverlayCopy.AllowLabel(allowWait);
        StartLockBar();
        UpdateGuard();
        _guardTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(100) };
        _guardTimer.Tick += (_, _) => UpdateGuard();
        _guardTimer.Start();
    }

    /// <summary>"Basalt" at full contrast, then the rest of the line muted.</summary>
    private void ShowEyebrow(string text)
    {
        EyebrowText.Inlines.Clear();
        var brand = SoftOverlayCopy.Brand;
        if (text.StartsWith(brand, StringComparison.Ordinal))
        {
            var run = new Run(brand);
            run.SetResourceReference(TextElement.ForegroundProperty, "Ink");
            EyebrowText.Inlines.Add(run);
            EyebrowText.Inlines.Add(new Run(text[brand.Length..]));
        }
        else
        {
            EyebrowText.Inlines.Add(new Run(text));
        }
    }

    private void ShowTimeLeft(TimeSpan remaining, double ring)
    {
        TimeLeftText.Text = SoftOverlayCopy.Clock(remaining);
        AutomationProperties.SetName(TimeLeftText, SoftOverlayCopy.TimeLeft(remaining));
        RingRemaining = Math.Clamp(ring, 0, 1);
    }

    /// <summary>
    /// The bar fills over the lock. Under reduced motion it is hidden, not
    /// animated, and the text says the wait still applies.
    /// </summary>
    private void StartLockBar()
    {
        if (_reducedMotion)
        {
            LockTrack.Visibility = Visibility.Collapsed;
            return;
        }
        LockFillScale.BeginAnimation(System.Windows.Media.ScaleTransform.ScaleXProperty,
            new DoubleAnimation(0, 1, SoftOverlayPolicy.InputLock));
    }

    /// <summary>
    /// Whether a button takes input right now: never during the lock, and
    /// Allow only once its own wait has run out too.
    /// </summary>
    private bool Accepts(Button button)
    {
        if (_locked) return false;
        if (ReferenceEquals(button, AllowButton)) return AllowReady;
        return true;
    }

    private bool AllowReady => !_locked && Environment.TickCount64 >= _allowAtTick;

    private void UpdateGuard()
    {
        var now = Environment.TickCount64;
        if (_locked)
        {
            var left = TimeSpan.FromMilliseconds(_unlockAtTick - now);
            if (left > TimeSpan.Zero)
            {
                WaitText.Text = SoftOverlayCopy.LockWait(left, _reducedMotion);
                AllowButton.Content = SoftOverlayCopy.AllowLabel(TimeSpan.FromMilliseconds(_allowAtTick - now));
                return;
            }
            Unlock();
        }

        var allowLeft = TimeSpan.FromMilliseconds(_allowAtTick - now);
        AllowButton.Content = SoftOverlayCopy.AllowLabel(allowLeft);
        if (allowLeft > TimeSpan.Zero) return;
        AllowButton.Style = (Style)FindResource("NoticeButton");
        AllowButton.ClearValue(CursorProperty);
        AllowButton.Focusable = true;
        _guardTimer?.Stop();
    }

    /// <summary>
    /// The lock is over: Back to work becomes Primary (never the default), the
    /// buttons rise and can be tabbed to, and the bar gives way to how to
    /// answer. Focus stays on the band, so a key still does nothing until Tab.
    /// </summary>
    private void Unlock()
    {
        _locked = false;
        BackToWorkButton.Style = (Style)FindResource("NoticePrimary");
        BackToWorkButton.Focusable = true;
        CloseButton.Style = (Style)FindResource("NoticeButton");
        CloseButton.Focusable = true;
        // Allow rises with the others but stays unfocusable, its countdown in
        // its label, until its own wait runs out (UpdateGuard).
        AllowButton.Style = (Style)FindResource("NoticeButton");
        AllowButton.Cursor = Cursors.Arrow;
        LockIcon.Visibility = Visibility.Collapsed;
        LockTrack.Visibility = Visibility.Collapsed;
        WaitText.Text = SoftOverlayCopy.Unlocked;
    }

    /// <summary>Keeps the words inside the screen on a narrow or scaled display.</summary>
    private void FitTextColumn()
    {
        var room = ActualWidth - BandContent.Margin.Left - BandContent.Margin.Right - 148 - 48;
        TextColumn.MaxWidth = Math.Max(240, Math.Min(1000, room));
    }

    protected override void OnClosed(EventArgs e)
    {
        _guardTimer?.Stop();
        _timeLeftTimer?.Stop();
        base.OnClosed(e);
    }

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        PlaceOverTheDistraction();
        // Focus starts on the band, not a button (#432): with no button
        // focused and none the default, Enter, Space and stray typing do
        // nothing. Tab moves to Back to work once the lock is over.
        Band.Focus();
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

    /// <summary>
    /// Refuses during the lock, and for a website, where the button is
    /// collapsed: the gate sits where the click lands, not only in what is
    /// drawn (CLAUDE.md, "covered controls").
    /// </summary>
    private void OnCloseIt(object sender, RoutedEventArgs e)
    {
        if (_locked) return;
        if (_isWebsite) return;
        Answer(CloseIt);
    }

    /// <summary>Refuses during the lock, like every button.</summary>
    private void OnBackToWork(object sender, RoutedEventArgs e)
    {
        if (_locked) return;
        Answer(BackToWork);
    }

    /// <summary>
    /// Refuses during the lock and until Allow's own wait has run out. The
    /// button is unfocusable and swallows presses until then; the gate also
    /// sits where the click lands, not only in how the button looks
    /// (CLAUDE.md, "covered controls").
    /// </summary>
    private void OnAllowFiveMinutes(object sender, RoutedEventArgs e)
    {
        if (!AllowReady) return;
        Answer(AllowFiveMinutes);
    }

    /// <summary>
    /// Enter does nothing, ever (#432): no button is the default, and a
    /// focused button doesn't take it either, so an Enter meant for a chat
    /// line or a game can't answer the notice. Space on a button works once
    /// the lock is over and the button has been tabbed to; the buttons aren't
    /// focusable before then. Escape is Back to work, but only after the lock,
    /// so a stray Escape meant for a game's menu does nothing either.
    /// </summary>
    protected override void OnPreviewKeyDown(KeyEventArgs e)
    {
        base.OnPreviewKeyDown(e);
        var key = e.Key == Key.System ? e.SystemKey : e.Key;
        if (key is Key.Enter)
        {
            e.Handled = true;
            return;
        }
        if (key is Key.Space && (_locked || Keyboard.FocusedElement is not Button))
        {
            e.Handled = true;
            return;
        }
        if (key != Key.Escape) return;
        e.Handled = true;
        if (_locked) return;
        Answer(BackToWork);
    }

    private void Answer(EventHandler? handler)
    {
        if (_answered) return;
        _answered = true;
        handler?.Invoke(this, EventArgs.Empty);
    }
}
