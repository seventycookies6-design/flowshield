using System.Diagnostics;
using System.Windows;
using FlowShield.Services;

namespace FlowShield.Views;

/// <summary>
/// Shown on an unhandled UI exception. The raw exception stays in the log;
/// the user gets a calm message, a way to copy the details, and a help link.
/// </summary>
public partial class FriendlyErrorDialog : Window
{
    private const string SupportUrl =
        "https://seventycookies6-design.github.io/flowshield/support.html";

    private readonly string _diagnostic;

    public FriendlyErrorDialog(Exception exception)
    {
        InitializeComponent();
        _diagnostic = $"{exception.GetType().Name}: {exception.Message}\nLog: {Log.Path}";
        Owner = Application.Current?.MainWindow;
    }

    private void OnCopyDetails(object sender, RoutedEventArgs e)
    {
        try
        {
            Clipboard.SetText(_diagnostic);
        }
        catch
        {
            // The clipboard can be held by another process; the dialog must still close.
        }
    }

    private void OnGetHelp(object sender, RoutedEventArgs e)
    {
        try
        {
            Process.Start(new ProcessStartInfo(SupportUrl) { UseShellExecute = true });
        }
        catch
        {
            // Opening a browser can fail on locked-down machines; OK still closes.
        }
    }

    // OK is IsDefault/IsCancel in the XAML, so WPF closes the dialog itself —
    // by click, by Enter, or by Escape (F21, DESIGN_SYSTEM.md §13).
}