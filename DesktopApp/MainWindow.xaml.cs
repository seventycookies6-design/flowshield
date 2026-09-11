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
    private bool _reallyClosing;

    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

    public MainWindow()
    {
        InitializeComponent();
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
            _tray = new Forms.NotifyIcon
            {
                Icon = System.Drawing.SystemIcons.Shield,
                Visible = false,
                Text = "FlowShield",
            };

            var menu = new Forms.ContextMenuStrip();
            menu.Items.Add("Open FlowShield", null, (_, _) => RestoreFromTray());
            menu.Items.Add(new Forms.ToolStripSeparator());
            menu.Items.Add("Quit", null, (_, _) =>
            {
                _reallyClosing = true;
                Close();
            });

            _tray.ContextMenuStrip = menu;
            _tray.DoubleClick += (_, _) => RestoreFromTray();
        }
        catch (Exception ex)
        {
            Log.Error("tray icon setup failed", ex);
        }
    }

    private void RestoreFromTray()
    {
        Show();
        WindowState = WindowState.Normal;
        Activate();
        if (_tray is not null) _tray.Visible = false;
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

        try
        {
            Vm?.SaveSettings();
            if (_tray is not null)
            {
                _tray.Visible = false;
                _tray.Dispose();
                _tray = null;
            }
        }
        catch (Exception ex)
        {
            Log.Error("close cleanup failed", ex);
        }

        base.OnClosing(e);
        Application.Current.Shutdown();
    }
}
