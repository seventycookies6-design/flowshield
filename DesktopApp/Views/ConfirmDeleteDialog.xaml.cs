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

    private void OnCancel(object sender, RoutedEventArgs e) => DialogResult = false;

    private void OnConfirm(object sender, RoutedEventArgs e) => DialogResult = true;
}
