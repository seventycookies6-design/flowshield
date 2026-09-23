using System.Windows;
using System.Windows.Automation;

namespace FlowShield.Views;

/// <summary>
/// Settings → Your data → Delete everything (F23). One extra, explicit click
/// before an irreversible local wipe. The Schedule page reuses it, with its
/// own question, before deleting a template (F6).
/// </summary>
public partial class ConfirmDeleteDialog : Window
{
    public ConfirmDeleteDialog()
    {
        InitializeComponent();
        Owner = Application.Current?.MainWindow;
    }

    /// <summary>The same dialog asking <paramref name="question"/>, with <paramref name="confirmLabel"/> on the destructive button.</summary>
    public ConfirmDeleteDialog(string question, string confirmLabel) : this()
    {
        QuestionText.Text = question;
        DetailText.Visibility = Visibility.Collapsed;
        ConfirmButton.Content = confirmLabel;
        AutomationProperties.SetName(ConfirmButton, confirmLabel);
    }

    /// <summary>Shows the question and returns true only when the destructive button was pressed.</summary>
    public static bool Ask(string question, string confirmLabel) =>
        new ConfirmDeleteDialog(question, confirmLabel).ShowDialog() == true;

    // Cancel is IsCancel="True" in the XAML: it sets DialogResult false itself,
    // and Escape does the same (F21, DESIGN_SYSTEM.md §13).
    private void OnConfirm(object sender, RoutedEventArgs e) => DialogResult = true;
}
