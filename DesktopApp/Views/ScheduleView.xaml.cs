using System.Windows;
using System.Windows.Controls;
using FlowShield.ViewModels;

namespace FlowShield.Views;

/// <summary>Plans' Schedules and Templates sections (#433).</summary>
public partial class ScheduleView : UserControl
{
    private ScheduleViewModel? _vm;

    public ScheduleView()
    {
        InitializeComponent();
        DataContextChanged += (_, e) =>
        {
            if (_vm is not null) _vm.EditorOpened -= OnEditorOpened;
            _vm = e.NewValue as ScheduleViewModel;
            if (_vm is not null) _vm.EditorOpened += OnEditorOpened;
        };
    }

    /// <summary>The Templates section's ⋯: its menu opens under the button, keyboard or mouse alike.</summary>
    private void OnTemplatesMoreClick(object sender, RoutedEventArgs e)
    {
        TemplatesMenu.PlacementTarget = TemplatesMoreButton;
        TemplatesMenu.DataContext = DataContext;
        TemplatesMenu.IsOpen = true;
    }

    /// <summary>An editor opened under the rows: once it is laid out, the page brings it into view.</summary>
    private void OnEditorOpened(object? sender, ScheduleViewModel.PlansEditor editor)
    {
        FrameworkElement target = editor switch
        {
            ScheduleViewModel.PlansEditor.Sleep => SleepEditor,
            ScheduleViewModel.PlansEditor.Schedule => ScheduleEditor,
            _ => TemplateEditor,
        };
        Dispatcher.BeginInvoke(() => target.RaiseEvent(new RoutedEventArgs(PlansView.EditorOpenedEvent, target)),
            System.Windows.Threading.DispatcherPriority.Loaded);
    }
}
