using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Threading;

namespace FlowShield.Views;

public partial class SettingsView : UserControl
{
    // F22: the section rail's groups, top to bottom — used both to build
    // JumpTo's target name and to walk the page in OnScrollChanged.
    private static readonly string[] Groups = { "Licence", "Focus", "App", "Notifications", "Data", "About" };
    private bool _jumping;

    // F22: below this width the rail collapses from a left-hand column into a
    // horizontal, wrapping chip row above the groups (constraints.md: must
    // still work at 800x540).
    private const double RailBreakpoint = 900;

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

        ApplyRailLayout(ActualWidth);
    }

    private void OnRootSizeChanged(object sender, SizeChangedEventArgs e)
    {
        ApplyRailLayout(e.NewSize.Width);
    }

    /// <summary>
    /// Switches the rail between its two layouts. Narrow: a horizontal,
    /// wrapping chip row spanning both columns in a new top row, with the
    /// scroll area moved below it. At or above the breakpoint: the rail is
    /// restored to its left-hand column, spanning both rows.
    /// </summary>
    private void ApplyRailLayout(double width)
    {
        if (width < RailBreakpoint)
        {
            Rail.Orientation = Orientation.Horizontal;
            Rail.Margin = new Thickness(0, 0, 0, 12);
            Grid.SetRow(Rail, 0);
            Grid.SetColumn(Rail, 0);
            Grid.SetColumnSpan(Rail, 2);
            RailColumn.Width = new GridLength(0);

            Grid.SetRow(SettingsScroll, 1);
        }
        else
        {
            Rail.Orientation = Orientation.Vertical;
            Rail.Margin = new Thickness(0, 0, 16, 0);
            Grid.SetRow(Rail, 0);
            Grid.SetColumn(Rail, 0);
            Grid.SetColumnSpan(Rail, 1);
            RailColumn.Width = new GridLength(180);

            Grid.SetRow(SettingsScroll, 0);
        }
    }

    private void OnNavClick(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement { Tag: string g }) JumpTo(g);
    }

    // WPF RadioButtons don't reliably raise Click on Enter (only Space toggles
    // the selection), so Enter is handled explicitly here to satisfy the
    // keyboard requirement that every rail link activates with Enter or Space.
    private void OnNavKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.Enter) return;
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
        }
        finally
        {
            Dispatcher.BeginInvoke(() => _jumping = false, DispatcherPriority.Background);
        }
    }

    private void OnScrollChanged(object sender, ScrollChangedEventArgs e)
    {
        if (_jumping) return;

        string? current = null;
        if (SettingsScroll.VerticalOffset >= SettingsScroll.ScrollableHeight - 1)
        {
            current = Groups[^1];            // bottom reached: last group wins
        }
        else
        {
            foreach (var g in Groups)
            {
                if (FindName("Group_" + g) is not FrameworkElement el) continue;
                double top;
                try
                {
                    top = el.TransformToAncestor(GroupsPanel).Transform(new System.Windows.Point(0, 0)).Y;
                }
                catch (InvalidOperationException)
                {
                    continue;                 // not in the visual tree yet: skip this group
                }
                if (top <= SettingsScroll.VerticalOffset + 24) current = g;
            }
        }

        if (current is null) return;          // no position could be computed: leave selection alone
        if (FindName("SettingsNav_" + current) is RadioButton rb) rb.IsChecked = true;
    }
}
