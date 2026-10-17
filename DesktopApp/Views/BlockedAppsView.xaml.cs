using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;

namespace FlowShield.Views;

public partial class BlockedAppsView : UserControl
{
    /// <summary>
    /// Below this view width the picker stacks under the list (DESIGN_SYSTEM.md
    /// §4). Side by side any narrower, the picker cut app names short and the
    /// list clipped its Remove buttons (#189).
    /// </summary>
    public const double StackPickerBelow = 780;

    public BlockedAppsView() => InitializeComponent();

    // In the stacked layout the page owns scrolling. The card has no scroll
    // range there, but its ScrollViewer would still swallow wheel input.
    private void OnBlocklistPreviewMouseWheel(object sender, MouseWheelEventArgs e)
    {
        if (e.Handled || PageScroll.VerticalScrollBarVisibility != ScrollBarVisibility.Auto) return;
        e.Handled = true;
        PageScroll.RaiseEvent(new MouseWheelEventArgs(e.MouseDevice, e.Timestamp, e.Delta)
        {
            RoutedEvent = MouseWheelEvent,
            Source = sender,
        });
    }

    /// <summary>Keyed on the view's own width, like TodayView.</summary>
    private void OnSizeChanged(object sender, SizeChangedEventArgs e)
    {
        bool narrow = e.NewSize.Width < StackPickerBelow;

        if (narrow)
        {
            // MinWidth first: a minimum would otherwise hold the column open.
            PickerColumn.MinWidth = 0;
            PickerColumn.Width = new GridLength(0);
            // Natural heights, with the page scrolling; the picker keeps a cap so
            // its long list still scrolls inside the card instead of the page.
            PageScroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto;
            ListRow.Height = GridLength.Auto;
            PickerRow.Height = GridLength.Auto;
            PickerCard.MaxHeight = 440;
            Grid.SetRow(PickerCard, 1);
            Grid.SetColumn(PickerCard, 0);
            Grid.SetColumnSpan(PickerCard, 2);
            Grid.SetColumnSpan(ListCard, 2);
            ListCard.Margin = new Thickness(0, 0, 0, 16);
        }
        else
        {
            PickerColumn.Width = new GridLength(0.65, GridUnitType.Star);
            PickerColumn.MinWidth = 260;
            // Disabled, not Auto: each card gets the page's real height and
            // scrolls its own content.
            PageScroll.VerticalScrollBarVisibility = ScrollBarVisibility.Disabled;
            PickerCard.MaxHeight = double.PositiveInfinity;
            ListRow.Height = new GridLength(1, GridUnitType.Star);
            PickerRow.Height = new GridLength(0);
            Grid.SetRow(PickerCard, 0);
            Grid.SetColumn(PickerCard, 1);
            Grid.SetColumnSpan(PickerCard, 1);
            Grid.SetColumnSpan(ListCard, 1);
            ListCard.Margin = new Thickness(0, 0, 16, 0);
        }
    }
}
