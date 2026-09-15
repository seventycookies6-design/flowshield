using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
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
        }

        if (e.NewValue is MainViewModel newVm)
        {
            newVm.Today.PropertyChanged += OnTodayChanged;
            newVm.Today.EndAbandoned += OnEndAbandoned;
        }

        UpdateTrayIcon();
    }

    private void OnEndAbandoned(object? sender, EventArgs e) => _quitWhenSprintEnds = false;

    private void UpdateTrayIcon()
    {
        if (_tray is not null)
        {
            _tray.Icon = Vm?.Today.IsRunning == true ? _trayRunningIcon : _trayIdleIcon;
        }
    }

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
        if (e.PropertyName != nameof(TodayViewModel.IsRunning)) return;

        UpdateTrayIcon();
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
        if (_tray is not null) _tray.Visible = false;
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
        }
        catch (Exception ex)
        {
            Log.Error("close cleanup failed", ex);
        }

        base.OnClosing(e);
        Application.Current.Shutdown();
    }
}
