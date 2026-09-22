using System.Windows;
using System.Windows.Controls;

namespace FlowShield.Views;

public partial class TodayView : UserControl
{
    /// <summary>Below this view width the stats stack under the timer (DESIGN_SYSTEM.md §4).</summary>
    public const double StackStatsBelow = 700;

    public TodayView() => InitializeComponent();

    /// <summary>
    /// Keyed on the view's own width, not the window's: the view responds to
    /// the space it actually has, whatever the rail is doing (#189).
    /// </summary>
    private void OnSizeChanged(object sender, SizeChangedEventArgs e)
    {
        bool narrow = e.NewSize.Width < StackStatsBelow;

        if (narrow)
        {
            // MinWidth first: a minimum would otherwise hold the column open.
            StatsColumn.MinWidth = 0;
            StatsColumn.Width = new GridLength(0);
            TimerRow.Height = GridLength.Auto;
            StatsRow.Height = GridLength.Auto;
            Grid.SetRow(StatsRail, 1);
            Grid.SetColumn(StatsRail, 0);
            Grid.SetColumnSpan(StatsRail, 2);
            TimerCard.Margin = new Thickness(0, 0, 0, 16);
        }
        else
        {
            // Proportional rather than a fixed 320px, so a wide window gives the
            // stats room too instead of all of it going to the timer card.
            StatsColumn.Width = new GridLength(0.4, GridUnitType.Star);
            StatsColumn.MinWidth = 300;
            TimerRow.Height = new GridLength(1, GridUnitType.Star);
            StatsRow.Height = new GridLength(0);
            Grid.SetRow(StatsRail, 0);
            Grid.SetColumn(StatsRail, 1);
            Grid.SetColumnSpan(StatsRail, 1);
            TimerCard.Margin = new Thickness(0, 0, 16, 0);
        }
    }
}
