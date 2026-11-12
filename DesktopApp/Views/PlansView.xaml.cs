using System.Windows;
using System.Windows.Controls;
using FlowShield.ViewModels;

namespace FlowShield.Views;

/// <summary>
/// Plans (#433): the Blocklists, Schedules and Templates sections in one
/// scrolling page. Opening it at a section (Today's "Edit schedules", "Edit
/// templates", the setup panel's "Edit blocklists") scrolls that section to
/// the top of the page.
/// </summary>
public partial class PlansView : UserControl
{
    private MainViewModel? _main;

    public PlansView()
    {
        InitializeComponent();
        DataContextChanged += (_, e) =>
        {
            if (_main is not null) _main.PlansSectionRequested -= OnSectionRequested;
            _main = e.NewValue as MainViewModel;
            if (_main is not null) _main.PlansSectionRequested += OnSectionRequested;
        };
        // An editor opening scrolls itself into view (BlockedAppsView, ScheduleView).
        AddHandler(EditorOpenedEvent, new RoutedEventHandler(OnEditorOpened));
    }

    /// <summary>Raised by a section when one of its editors opens, so the page can show it.</summary>
    public static readonly RoutedEvent EditorOpenedEvent = EventManager.RegisterRoutedEvent(
        "EditorOpened", RoutingStrategy.Bubble, typeof(RoutedEventHandler), typeof(PlansView));

    private void OnSectionRequested(object? sender, PlansSection section)
    {
        // After layout: the page may only just have become visible.
        Dispatcher.BeginInvoke(() =>
        {
            FrameworkElement target = section switch
            {
                PlansSection.Schedules => SchedulesSection.SchedulesCard,
                PlansSection.Templates => SchedulesSection.TemplatesCard,
                _ => BlocklistsSection,
            };
            ScrollToTop(target);
        }, System.Windows.Threading.DispatcherPriority.Loaded);
    }

    private void OnEditorOpened(object sender, RoutedEventArgs e)
    {
        if (e.OriginalSource is not FrameworkElement editor) return;
        Dispatcher.BeginInvoke(() => editor.BringIntoView(),
            System.Windows.Threading.DispatcherPriority.Loaded);
    }

    /// <summary>Scrolls so the element's top sits at the top of the page, or as near as the page allows.</summary>
    private void ScrollToTop(FrameworkElement element)
    {
        if (!element.IsVisible) { PageScroll.ScrollToTop(); return; }
        var top = element.TransformToAncestor(PageScroll).Transform(new System.Windows.Point(0, 0)).Y;
        PageScroll.ScrollToVerticalOffset(PageScroll.VerticalOffset + top);
    }
}
