using System.Windows;

namespace FlowShield.Views;

/// <summary>
/// Settings → Your data → Delete everything (F23). One extra, explicit click
/// before an irreversible local wipe.
/// </summary>
public partial class ConfirmDeleteDialog : Window
{
    public ConfirmDeleteDialog()
    {
        InitializeComponent();
        Owner = Application.Current?.MainWindow;
    }

    // Cancel is IsCancel="True" in the XAML: it sets DialogResult false itself,
    // and Escape does the same (F21, DESIGN_SYSTEM.md §13).
    private void OnConfirm(object sender, RoutedEventArgs e) => DialogResult = true;
}
