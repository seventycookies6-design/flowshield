using System.Windows;
using System.Windows.Controls;

namespace FlowShield.Views;

public partial class SettingsView : UserControl
{
    public SettingsView()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        DevOnlyFields.Visibility = App.Current?.DevMode == true
            ? Visibility.Visible
            : Visibility.Collapsed;
    }
}
