using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Interop;
using FlowShield.Models;
using FlowShield.Services;
using FlowShield.ViewModels;
using Forms = System.Windows.Forms;

namespace FlowShield;

public partial class MainWindow : Window
{
    private const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;

    private Forms.NotifyIcon? _tray;
    private System.Drawing.Icon? _trayIdleIcon;
    private System.Drawing.Icon? _trayRunningIcon;
    private bool _reallyClosing;

    /// <summary>Quit was asked for during a Firm or Sealed sprint; quit once that sprint ends (F2).</summary>
    private bool _quitWhenSprintEnds;

    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

    public MainWindow()
    {
        InitializeComponent();
        DataContextChanged += OnDataContextChanged;
        SetUpTray();
    }

    /// <summary>Below this client width the rail compacts to icons (DESIGN_SYSTEM.md §4).</summary>
    public const double CompactRailBelow = 1000;

    /// <summary>
    /// Handled on the root grid, not the window: the grid's width is the space
    /// the layout actually has, which is also what an offscreen render of the
    /// window's content sees (#189).
    /// </summary>
    private void OnSizeChanged(object sender, SizeChangedEventArgs e)
    {
        bool narrow = e.NewSize.Width < CompactRailBelow;
        // 240 and 16 match the XAML (the §4 rail and 4-based spacing); 72 leaves
        // each tab 56px, room for a 20px icon inside its 16px side padding.
        NavColumn.Width = new GridLength(narrow ? 72 : 240);
        NavDockPanel.Margin = narrow ? new Thickness(8, 24, 8, 16) : new Thickness(16, 24, 16, 16);
        foreach (var tab in NavTabs.Children.OfType<Button>())
        {
            // Icons only: centre the icon, and keep the name available on hover.
            tab.HorizontalContentAlignment = narrow ? HorizontalAlignment.Center : HorizontalAlignment.Left;
            tab.ToolTip = narrow ? AutomationProperties.GetName(tab) : null;
        }
        NavBrand.HorizontalAlignment = narrow ? HorizontalAlignment.Center : HorizontalAlignment.Left;
        NavBrand.Margin = narrow ? new Thickness(0, 0, 0, 24) : new Thickness(8, 0, 0, 24);
        NavBrandText.Visibility = narrow ? Visibility.Collapsed : Visibility.Visible;
        NavBottomPanel.Visibility = narrow ? Visibility.Collapsed : Visibility.Visible;
        NavTodayLabel.Visibility = narrow ? Visibility.Collapsed : Visibility.Visible;
        NavHistoryLabel.Visibility = narrow ? Visibility.Collapsed : Visibility.Visible;
        NavBlockedAppsLabel.Visibility = narrow ? Visibility.Collapsed : Visibility.Visible;
        NavSleepBlockingLabel.Visibility = narrow ? Visibility.Collapsed : Visibility.Visible;
        NavSettingsLabel.Visibility = narrow ? Visibility.Collapsed : Visibility.Visible;
    }

    private MainViewModel? Vm => DataContext as MainViewModel;

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);

        // Ask DWM for the dark title bar so the standard chrome matches the app.
        try
        {
            var hwnd = new WindowInteropHelper(this).Handle;
            int enabled = 1;
            DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ref enabled, sizeof(int));
        }
        catch (Exception ex)
        {
            Log.Warn($"dark title bar unavailable: {ex.Message}");
        }
    }

    private void SetUpTray()
    {
        try
        {
            _trayIdleIcon = LoadIcon("FlowShield.ico");
            _trayRunningIcon = LoadIcon("FlowShield.Running.ico");
            _tray = new Forms.NotifyIcon
            {
                Icon = _trayIdleIcon,
                Visible = false,
                Text = "FlowShield",
            };

            var menu = new Forms.ContextMenuStrip();
            menu.Items.Add("Open FlowShield", null, (_, _) => RestoreFromTray());
            menu.Items.Add(new Forms.ToolStripSeparator());
            menu.Items.Add("Quit", null, (_, _) => Quit());

            _tray.ContextMenuStrip = menu;
            _tray.DoubleClick += (_, _) => RestoreFromTray();
            _tray.BalloonTipClicked += OnNotificationClicked;
        }
        catch (Exception ex)
        {
            _trayIdleIcon?.Dispose();
            _trayIdleIcon = null;
            _trayRunningIcon?.Dispose();
            _trayRunningIcon = null;
            Log.Error("tray icon setup failed", ex);
        }
    }

    private static System.Drawing.Icon LoadIcon(string name)
    {
        var uri = new Uri($"pack://application:,,,/Assets/{name}", UriKind.Absolute);
        using var stream = Application.GetResourceStream(uri)?.Stream
            ?? throw new InvalidOperationException($"missing icon resource: {name}");
        using var icon = new System.Drawing.Icon(stream);
        return (System.Drawing.Icon)icon.Clone();
    }

    private void OnDataContextChanged(object sender, DependencyPropertyChangedEventArgs e)
    {
        if (e.OldValue is MainViewModel oldVm)
        {
            oldVm.Today.PropertyChanged -= OnTodayChanged;
            oldVm.Today.EndAbandoned -= OnEndAbandoned;
            oldVm.NotificationRequested -= OnNotificationRequested;
        }

        if (e.NewValue is MainViewModel newVm)
        {
            newVm.Today.PropertyChanged += OnTodayChanged;
            newVm.Today.EndAbandoned += OnEndAbandoned;
            newVm.NotificationRequested += OnNotificationRequested;
        }

        UpdateTrayIcon();
    }

    private void OnEndAbandoned(object? sender, EventArgs e) => _quitWhenSprintEnds = false;

    // ------------------------------------------------------ notifications (F19)

    private Notification? _lastNotification;

    private void OnNotificationRequested(object? sender, Notification notification)
    {
        if (_tray is null) return;
        try
        {
            _lastNotification = notification;
            // A hidden NotifyIcon can't raise a balloon, so show it for the
            // duration — the tray is where a minimised FlowShield lives anyway.
            _tray.Visible = true;
            _tray.ShowBalloonTip(5000, notification.Title, notification.Message, Forms.ToolTipIcon.None);
        }
        catch (Exception ex)
        {
            Log.Warn($"could not show a notification: {ex.Message}");
        }
    }

    private void OnNotificationClicked(object? sender, EventArgs e)
    {
        var notification = _lastNotification;
        RestoreFromTray();
        if (Vm is null || notification is null) return;

        switch (notification.Action)
        {
            case NotificationAction.OpenJournal:
                Vm.CurrentPage = AppPage.Today;
                break;
            case NotificationAction.OpenSettingsLicense:
                Vm.CurrentPage = AppPage.Settings;
                break;
        }
    }

    /// <summary>
    /// The tray icon, its tooltip and the taskbar progress bar, refreshed every
    /// tick of a running sprint: the notification area itself becomes the timer.
    /// </summary>
    private void UpdateTrayIcon()
    {
        var running = Vm?.Today.IsRunning == true;
        var remaining = Vm?.Today.Remaining ?? TimeSpan.Zero;

        if (_tray is not null)
        {
            // While a sprint runs the tray icon stays visible even with the
            // window open: it is the countdown.
            if (running) _tray.Visible = true;

            _tray.Text = NotificationPolicy.TrayText(running, Vm?.Today.SelectedShield ?? ShieldLevel.Firm, remaining);

            var countdown = running ? NotificationPolicy.TrayIconText(remaining) : null;
            if (countdown is null)
            {
                _tray.Icon = _trayIdleIcon;
                _countdownText = null;
            }
            else if (countdown != _countdownText)
            {
                _countdownText = countdown;
                var icon = CountdownIcon(countdown);
                if (icon is not null)
                {
                    _tray.Icon = icon;
                    _countdownIcon?.Dispose();
                    _countdownIcon = icon;
                }
                else
                {
                    _tray.Icon = _trayRunningIcon;
                }
            }
        }

        // Windows 11 hides new tray icons in the overflow until the user drags
        // one out, so the countdown also goes in the title: the taskbar button's
        // tooltip and thumbnail then show the time left without any setup.
        Title = running ? $"FlowShield — {Vm?.Today.RemainingText}" : "FlowShield";

        // Taskbar button: a progress bar for as long as the sprint runs.
        if (TaskbarItemInfo is not null)
        {
            TaskbarItemInfo.ProgressState = running
                ? System.Windows.Shell.TaskbarItemProgressState.Normal
                : System.Windows.Shell.TaskbarItemProgressState.None;
            TaskbarItemInfo.ProgressValue = Vm?.Today.Progress ?? 0;
        }
    }

    private string? _countdownText;
    private System.Drawing.Icon? _countdownIcon;

    /// <summary>Draws the minutes left as the tray icon. Null if drawing fails.</summary>
    private static System.Drawing.Icon? CountdownIcon(string text)
    {
        try
        {
            using var bitmap = new System.Drawing.Bitmap(32, 32);
            using (var g = System.Drawing.Graphics.FromImage(bitmap))
            {
                g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
                g.Clear(System.Drawing.Color.Transparent);

                using var background = new System.Drawing.SolidBrush(System.Drawing.Color.FromArgb(0xFF, 0x3A, 0xA8, 0x92));
                g.FillEllipse(background, 0, 0, 31, 31);

                var size = text.Length >= 3 ? 13f : 17f;
                using var font = new System.Drawing.Font("Segoe UI", size, System.Drawing.FontStyle.Bold,
                    System.Drawing.GraphicsUnit.Pixel);
                using var ink = new System.Drawing.SolidBrush(System.Drawing.Color.FromArgb(0xFF, 0x0E, 0x14, 0x12));
                using var format = new System.Drawing.StringFormat
                {
                    Alignment = System.Drawing.StringAlignment.Center,
                    LineAlignment = System.Drawing.StringAlignment.Center,
                };
                g.DrawString(text, font, ink, new System.Drawing.RectangleF(0, 0, 32, 32), format);
            }

            var handle = bitmap.GetHicon();
            try
            {
                // Clone, then free the handle GetHicon created — otherwise every
                // minute of every sprint leaks a GDI icon handle.
                using var shared = System.Drawing.Icon.FromHandle(handle);
                return (System.Drawing.Icon)shared.Clone();
            }
            finally
            {
                DestroyIcon(handle);
            }
        }
        catch (Exception ex)
        {
            Log.Warn($"countdown tray icon unavailable: {ex.Message}");
            return null;
        }
    }

    [System.Runtime.InteropServices.DllImport("user32.dll", SetLastError = true)]
    private static extern bool DestroyIcon(IntPtr handle);

    /// <summary>
    /// Really exit. During a Firm or Sealed sprint (past its grace period) the
    /// window opens on that sprint's end flow instead, and FlowShield quits
    /// only once the sprint has actually ended; otherwise Quit would be a
    /// one-click way around the countdown and phrase.
    /// </summary>
    private void Quit()
    {
        if (Vm is { } vm && NeedsEndFlowToQuit(vm))
        {
            RestoreFromTray();
            vm.CurrentPage = AppPage.Today;
            if (!vm.Today.RequestEnd())
            {
                _quitWhenSprintEnds = true;
                vm.Toast("End the sprint to quit FlowShield.");
                Log.Info("quit deferred until the running sprint ends");
                return;
            }
        }

        _reallyClosing = true;
        Close();
    }

    private static bool NeedsEndFlowToQuit(MainViewModel vm) =>
        vm.Today.IsRunning && vm.Blocker.ActiveShield >= Models.ShieldLevel.Firm;

    private void OnTodayChanged(object? sender, PropertyChangedEventArgs e)
    {
        // Remaining ticks every second while a sprint runs; it is what keeps the
        // countdown in the notification area current.
        if (e.PropertyName is nameof(TodayViewModel.Remaining) or nameof(TodayViewModel.IsRunning))
            UpdateTrayIcon();

        if (e.PropertyName != nameof(TodayViewModel.IsRunning)) return;

        if (_quitWhenSprintEnds && Vm?.Today.IsRunning == false)
        {
            _quitWhenSprintEnds = false;
            _reallyClosing = true;
            Close();
        }
    }

    /// <summary>
    /// Shows this window on top when FlowShield is opened again (roadmap 1.3).
    /// Leaves the page and any running sprint or end panel exactly as they are.
    /// </summary>
    public void BringToFront()
    {
        RestoreFromTray();
        // Windows won't hand focus to a background process on request; a brief
        // Topmost flip reliably puts the window in front anyway.
        Topmost = true;
        Topmost = false;
        Focus();
    }

    private void RestoreFromTray()
    {
        Show();
        WindowState = WindowState.Normal;
        Activate();
        // The countdown stays in the tray during a sprint; otherwise the icon goes.
        if (_tray is not null) _tray.Visible = Vm?.Today.IsRunning == true;
    }

    /// <summary>
    /// Starts the already-initialized application without displaying its main
    /// window. Returns false when the shell tray icon is unavailable so startup
    /// can fall back to a normal visible window.
    /// </summary>
    public bool StartInTray()
    {
        if (_tray is null) return false;

        try
        {
            _tray.Visible = true;
            Hide();
            Log.Info("started in tray");
            return true;
        }
        catch (Exception ex)
        {
            Log.Error("could not start in tray", ex);
            return false;
        }
    }

    protected override void OnClosing(CancelEventArgs e)
    {
        // Closing hides to tray by default; the tray menu's Quit really exits.
        if (!_reallyClosing && Vm?.Settings.MinimizeToTrayOnClose == true && _tray is not null)
        {
            e.Cancel = true;
            Hide();
            _tray.Visible = true;
            _tray.ShowBalloonTip(2500, "FlowShield", "Still guarding. Double-click to reopen.",
                Forms.ToolTipIcon.Info);
            Log.Info("minimised to tray on close");
            return;
        }

        // Closing for real (minimise-to-tray is off) goes through the same
        // end flow as the tray's Quit.
        if (!_reallyClosing && Vm is { } vm && NeedsEndFlowToQuit(vm))
        {
            e.Cancel = true;
            // Close() can't be called again from inside Closing, so run after it.
            Dispatcher.BeginInvoke(Quit);
            return;
        }

        try
        {
            if (Vm is { } currentVm)
            {
                currentVm.Today.PropertyChanged -= OnTodayChanged;
                currentVm.Today.EndAbandoned -= OnEndAbandoned;
            }
            Vm?.SaveSettings();
            if (_tray is not null)
            {
                _tray.Visible = false;
                _tray.Dispose();
                _tray = null;
            }
            _trayIdleIcon?.Dispose();
            _trayIdleIcon = null;
            _trayRunningIcon?.Dispose();
            _trayRunningIcon = null;
            _countdownIcon?.Dispose();
            _countdownIcon = null;
        }
        catch (Exception ex)
        {
            Log.Error("close cleanup failed", ex);
        }

        base.OnClosing(e);
        Application.Current.Shutdown();
    }
}
