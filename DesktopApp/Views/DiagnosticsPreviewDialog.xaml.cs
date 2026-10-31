using System.IO;
using System.Text;
using System.Windows;
using FlowShield.Services;

namespace FlowShield.Views;

/// <summary>
/// Settings → About → Get help → Create diagnostics (Roadmap 4.3, #400).
/// Shows the whole bundle, read-only, before anything is copied or saved.
/// It never sends anything: Copy goes to the clipboard and Save as writes
/// where the customer says.
/// </summary>
public partial class DiagnosticsPreviewDialog : Window
{
    private readonly string _text;

    public DiagnosticsPreviewDialog(string text)
    {
        InitializeComponent();
        _text = text;
        PreviewText.Text = text;
        Owner = Application.Current?.MainWindow;
    }

    private void OnCopy(object sender, RoutedEventArgs e)
    {
        try
        {
            Clipboard.SetText(_text);
            StatusText.Text = "Copied. Paste it into an email if you want to share it.";
        }
        catch
        {
            // The clipboard can be held by another process.
            StatusText.Text = "Couldn't copy. Try Save as instead.";
        }
    }

    private void OnSave(object sender, RoutedEventArgs e)
    {
        var dialog = new Microsoft.Win32.SaveFileDialog
        {
            FileName = $"basalt-diagnostics-{DateTime.Now:yyyy-MM-dd}.txt",
            Filter = "Text file|*.txt",
            AddExtension = true,
            OverwritePrompt = true,
        };

        // No default folder: the file goes where the customer says, and
        // nowhere else.
        if (dialog.ShowDialog(this) != true) return;

        try
        {
            File.WriteAllText(dialog.FileName, _text, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
            StatusText.Text = "Saved. You can attach that file to an email.";
        }
        catch (Exception ex)
        {
            Log.Info($"diagnostics save failed: {ex.Message}");
            StatusText.Text = "Could not save that file. Try another folder.";
        }
    }

    // Close is IsDefault/IsCancel in the XAML, so WPF closes the dialog itself —
    // by click, by Enter, or by Escape (§13).
}
