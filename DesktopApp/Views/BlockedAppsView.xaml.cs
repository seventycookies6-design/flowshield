using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Media;
using FlowShield.ViewModels;

namespace FlowShield.Views;

/// <summary>
/// Plans' Blocklists section (#433). The page scrolls, not this section: the
/// old side-by-side cards with their own scrolling are gone, and so is the
/// width breakpoint that stacked them (#189); the open blocklist's list and
/// picker stack through AdaptiveColumns instead.
/// </summary>
public partial class BlockedAppsView : UserControl
{
    private BlockedAppsViewModel? _vm;

    public BlockedAppsView()
    {
        InitializeComponent();
        DataContextChanged += (_, e) =>
        {
            if (_vm is not null) _vm.EditorOpened -= OnEditorOpened;
            _vm = e.NewValue as BlockedAppsViewModel;
            if (_vm is not null) _vm.EditorOpened += OnEditorOpened;
        };
    }

    /// <summary>
    /// A blocklist opened: once its editor is laid out, bring it into view and
    /// put the cursor where the button that opened it promised (Add an app:
    /// Find an app; New blocklist: the name).
    /// </summary>
    private void OnEditorOpened(object? sender, BlockedAppsViewModel.EditorFocus focus)
    {
        Dispatcher.BeginInvoke(() =>
        {
            var name = FindById<TextBox>(this, "ProfileNameInput");
            if (name is null) return;
            var editor = FindAncestor<ContentControl>(name) ?? (FrameworkElement)name;
            editor.RaiseEvent(new RoutedEventArgs(PlansView.EditorOpenedEvent, editor));

            var field = focus switch
            {
                BlockedAppsViewModel.EditorFocus.Name => name,
                BlockedAppsViewModel.EditorFocus.FindAnApp => FindById<TextBox>(this, "AppSearchInput"),
                _ => null,
            };
            if (field is { IsEnabled: true })
            {
                field.Focus();
                field.SelectAll();
            }
        }, System.Windows.Threading.DispatcherPriority.Loaded);
    }

    private static T? FindById<T>(DependencyObject root, string automationId) where T : FrameworkElement
    {
        var queue = new Queue<DependencyObject>();
        queue.Enqueue(root);
        while (queue.Count > 0)
        {
            var node = queue.Dequeue();
            if (node is T element && AutomationProperties.GetAutomationId(element) == automationId && element.IsVisible)
                return element;
            for (var i = 0; i < VisualTreeHelper.GetChildrenCount(node); i++)
                queue.Enqueue(VisualTreeHelper.GetChild(node, i));
        }
        return null;
    }

    private static T? FindAncestor<T>(DependencyObject node) where T : DependencyObject
    {
        for (var current = VisualTreeHelper.GetParent(node); current is not null; current = VisualTreeHelper.GetParent(current))
            if (current is T match) return match;
        return null;
    }
}
