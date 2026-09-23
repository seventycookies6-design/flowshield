using System.Windows.Controls;
using System.Windows.Input;

namespace FlowShield.Views;

public partial class ScheduleView : UserControl
{
    public ScheduleView() => InitializeComponent();

    /// <summary>
    /// The embedded sleep view keeps its own ScrollViewer. Inside this page it
    /// never has anything to scroll, yet WPF's ScrollViewer marks every wheel
    /// turn it sees as handled, so the page would stop moving whenever the
    /// pointer is over the sleep window. Hand the turn to the page instead.
    /// </summary>
    private void OnSleepWindowPreviewMouseWheel(object sender, MouseWheelEventArgs e)
    {
        if (e.Handled) return;
        e.Handled = true;
        PageScroll.RaiseEvent(new MouseWheelEventArgs(e.MouseDevice, e.Timestamp, e.Delta)
        {
            RoutedEvent = MouseWheelEvent,
            Source = sender,
        });
    }
}
