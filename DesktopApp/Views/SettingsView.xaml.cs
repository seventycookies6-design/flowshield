using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;

namespace FlowShield.Views;

public partial class SettingsView : UserControl
{
    // F22: the section rail's groups, top to bottom — used both to build
    // JumpTo's target name and to walk the page in OnScrollChanged.
    private static readonly string[] Groups = { "Licence", "Focus", "App", "Notifications", "Data", "About" };
    private bool _jumping;

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

    private void OnNavClick(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement { Tag: string g }) JumpTo(g);
    }

    /// <summary>
    /// Scrolls a group's header to the top of the viewport and moves focus to
    /// it. Uses ScrollToVerticalOffset (not BringIntoView) for exact top
    /// alignment; BringIntoView is only a fallback for the rare case where
    /// TransformToAncestor throws because the target isn't in the visual tree
    /// yet.
    /// </summary>
    public void JumpTo(string group)
    {
        if (FindName("Group_" + group) is not FrameworkElement target) return;
        var header = FindName("Header_" + group) as UIElement;

        _jumping = true;
        try
        {
            var y = target.TransformToAncestor(GroupsPanel).Transform(new System.Windows.Point(0, 0)).Y;
            SettingsScroll.ScrollToVerticalOffset(y);
        }
        catch (InvalidOperationException)
        {
            target.BringIntoView();
        }
        header?.Focus();
        Dispatcher.BeginInvoke(() => _jumping = false, DispatcherPriority.Background);
    }

    private void OnScrollChanged(object sender, ScrollChangedEventArgs e)
    {
        if (_jumping) return;

        string current = Groups[0];
        if (SettingsScroll.VerticalOffset >= SettingsScroll.ScrollableHeight - 1)
        {
            current = Groups[^1];            // bottom reached: last group wins
        }
        else
        {
            foreach (var g in Groups)
            {
                if (FindName("Group_" + g) is not FrameworkElement el) continue;
                var top = el.TransformToAncestor(GroupsPanel).Transform(new System.Windows.Point(0, 0)).Y;
                if (top <= SettingsScroll.VerticalOffset + 24) current = g;
            }
        }

        if (FindName("SettingsNav_" + current) is RadioButton rb) rb.IsChecked = true;
    }
}
