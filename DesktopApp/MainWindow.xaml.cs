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

    // ------------------------------------------------------ global hotkey (F4)

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    private const int WM_HOTKEY = 0x0312;
    private const int GlobalHotkeyId = 0x4653; // arbitrary, app-local id ("FS")
    private const uint MOD_ALT = 0x0001;
    private const uint MOD_CONTROL = 0x0002;
    private const uint MOD_NOREPEAT = 0x4000;
    private const uint VK_F = 0x46;
    private bool _hotkeyRegistered;
    private HwndSource? _hotkeySource;

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

        SetUpGlobalHotkey();
    }

    /// <summary>
    /// Registers Ctrl+Alt+F to start the last sprint from anywhere (F4), if
    /// the setting is on. Re-run whenever that setting changes, so turning it
    /// on or off in Settings takes effect immediately, and on window close to
    /// unregister. No admin rights: RegisterHotKey is a per-user API.
    ///
    /// Always removes any hook it previously added before adding a new one —
    /// re-running this on every settings toggle without that would stack a
    /// WndProc hook per toggle, each one firing StartCommand again.
    /// </summary>
    private void SetUpGlobalHotkey()
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        if (hwnd == IntPtr.Zero) return; // not initialised yet; OnSourceInitialized retries

        if (_hotkeyRegistered)
        {
            UnregisterHotKey(hwnd, GlobalHotkeyId);
            _hotkeyRegistered = false;
        }
        if (_hotkeySource is not null)
        {
            _hotkeySource.RemoveHook(WndProc);
            _hotkeySource = null;
        }

        if (Vm?.Settings.GlobalHotkeyEnabled != true) return;

        if (RegisterHotKey(hwnd, GlobalHotkeyId, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_F))
        {
            _hotkeyRegistered = true;
            _hotkeySource = HwndSource.FromHwnd(hwnd);
            _hotkeySource?.AddHook(WndProc);
            Log.Info("global hotkey registered: Ctrl+Alt+F starts the last sprint");
        }
        else
        {
            // Another app already owns the combination. Leave the setting off
            // rather than silently doing nothing when the user presses it.
            Log.Warn("global hotkey Ctrl+Alt+F is already in use; leaving it off");
            if (Vm is { } vm)
            {
                vm.SettingsPage.GlobalHotkeyEnabled = false;
                vm.Toast("Ctrl+Alt+F is already used by another app, so the global hotkey stays off.");
            }
        }
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == WM_HOTKEY && wParam.ToInt32() == GlobalHotkeyId)
        {
            // The same command the tray's "Start sprint (last settings)" and
            // the Today button use — never a shortcut around CanStart's gates.
            Vm?.Today.StartCommand.Execute(null);
            handled = true;
        }
        return IntPtr.Zero;
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
            menu.Opening += (_, _) => BuildTrayMenu(menu);
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

    /// <summary>
    /// Rebuilds the tray menu just before it opens (F4), so the time-left
    /// item and the running/idle items are always current — a countdown that
    /// only refreshed on launch would go stale within a minute.
    /// </summary>
    private void BuildTrayMenu(Forms.ContextMenuStrip menu)
    {
        menu.Items.Clear();

        var running = Vm?.Today.IsRunning == true;
        if (running)
        {
            menu.Items.Add(new Forms.ToolStripMenuItem($"{Vm!.Today.RemainingText} left") { Enabled = false });
            menu.Items.Add(new Forms.ToolStripSeparator());
            menu.Items.Add("Open", null, (_, _) => RestoreFromTray());
            // Goes through the exact F2 flow the Today button uses: bring the
            // window forward and invoke StopCommand, never end it directly.
            menu.Items.Add("End sprint", null, (_, _) => EndSprintFromTray());
        }
        else
        {
            // Bound to the same StartCommand the Today button uses, with
            // whatever length and shield were last used — they already
            // persist as AppSettings.DefaultSprintMinutes/DefaultShield.
            menu.Items.Add("Start sprint (last settings)", null, (_, _) => Vm?.Today.StartCommand.Execute(null));
            menu.Items.Add("Start…", null, (_, _) => OpenToStartSprint());
            menu.Items.Add(new Forms.ToolStripSeparator());
            menu.Items.Add("Open FlowShield", null, (_, _) => RestoreFromTray());
        }

        menu.Items.Add(new Forms.ToolStripSeparator());
        menu.Items.Add("Quit", null, (_, _) => Quit());
    }

    /// <summary>Tray's "Start…": opens the window on Today without starting anything (F4).</summary>
    private void OpenToStartSprint()
    {
        if (Vm is not { } vm) return;
        BringToFront();
        vm.CurrentPage = AppPage.Today;
    }

    /// <summary>
    /// Tray's "End sprint" (F4): brings the window forward and triggers the
    /// same StopCommand the Today button uses, so Firm's confirmation and
    /// Sealed's countdown-and-phrase apply exactly as they do from the window
    /// — the tray is never a shortcut around the F2 flow.
    /// </summary>
    private void EndSprintFromTray()
    {
        if (Vm is not { } vm) return;
        BringToFront();
        vm.CurrentPage = AppPage.Today;
        vm.Today.StopCommand.Execute(null);
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
            oldVm.SettingsPage.PropertyChanged -= OnSettingsPageChanged;
            oldVm.SoftOverlayRequested -= OnSoftOverlayRequested;
            oldVm.SoftOverlayDismissRequested -= OnSoftOverlayDismissRequested;
        }

        if (e.NewValue is MainViewModel newVm)
        {
            newVm.Today.PropertyChanged += OnTodayChanged;
            newVm.Today.EndAbandoned += OnEndAbandoned;
            newVm.NotificationRequested += OnNotificationRequested;
            newVm.SettingsPage.PropertyChanged += OnSettingsPageChanged;
            newVm.SoftOverlayRequested += OnSoftOverlayRequested;
            newVm.SoftOverlayDismissRequested += OnSoftOverlayDismissRequested;
        }

        UpdateTrayIcon();
        SetUpGlobalHotkey();
    }

    /// <summary>Turning the F4 hotkey setting on or off takes effect immediately.</summary>
    private void OnSettingsPageChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(SettingsViewModel.GlobalHotkeyEnabled))
            SetUpGlobalHotkey();
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

    // -------------------------------------------- the Soft notice (F7, roadmap 1.7)

    /// <summary>The Soft notice, while one is on screen. At most one at a time.</summary>
    private Views.SoftOverlayWindow? _softOverlay;

    /// <summary>
    /// Puts the Soft notice over the blocked app, on that app's monitor.
    ///
    /// Neither button closes the blocked app: "Back to work" brings FlowShield
    /// forward, and "Allow 5 minutes" simply goes quiet. Soft closing something
    /// would break the promise on its own shield chip.
    /// </summary>
    private void OnSoftOverlayRequested(object? sender, MainViewModel.SoftOverlayRequest request)
    {
        try
        {
            CloseSoftOverlay();

            var overlay = new Views.SoftOverlayWindow();
            overlay.Configure(request.Sentence, request.TimeLeft, request.Window);
            overlay.BackToWork += (_, _) =>
            {
                CloseSoftOverlay();
                Vm?.SoftOverlayBackToWork(request.DisplayName);
                // Forward, not "the blocked app closed": the distraction is left
                // exactly where it was.
                BringToFront();
            };
            overlay.AllowFiveMinutes += (_, _) =>
            {
                CloseSoftOverlay();
                Vm?.SoftOverlayAllowFiveMinutes(request.DisplayName);
            };
            overlay.Closed += (_, _) =>
            {
                if (ReferenceEquals(_softOverlay, overlay)) _softOverlay = null;
            };

            _softOverlay = overlay;
            overlay.Show();
        }
        catch (Exception ex)
        {
            Log.Error("could not show the soft notice", ex);
        }
    }

    private void OnSoftOverlayDismissRequested(object? sender, EventArgs e) => CloseSoftOverlay();

    private void CloseSoftOverlay()
    {
        var overlay = _softOverlay;
        _softOverlay = null;
        if (overlay is null) return;
        try
        {
            overlay.Close();
        }
        catch (Exception ex)
        {
            Log.Warn($"could not close the soft notice: {ex.Message}");
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
            CloseSoftOverlay();
            if (Vm is { } currentVm)
            {
                currentVm.Today.PropertyChanged -= OnTodayChanged;
                currentVm.Today.EndAbandoned -= OnEndAbandoned;
                currentVm.SettingsPage.PropertyChanged -= OnSettingsPageChanged;
                currentVm.SoftOverlayRequested -= OnSoftOverlayRequested;
                currentVm.SoftOverlayDismissRequested -= OnSoftOverlayDismissRequested;
            }
            Vm?.SaveSettings();
            if (_hotkeyRegistered)
            {
                UnregisterHotKey(new WindowInteropHelper(this).Handle, GlobalHotkeyId);
                _hotkeyRegistered = false;
            }
            if (_hotkeySource is not null)
            {
                _hotkeySource.RemoveHook(WndProc);
                _hotkeySource = null;
            }
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
