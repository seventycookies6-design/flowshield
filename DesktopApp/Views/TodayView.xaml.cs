using System.Windows;
using System.Windows.Controls;

namespace FlowShield.Views;

public partial class TodayView : UserControl
{
    public TodayView() => InitializeComponent();

    private void OnSizeChanged(object sender, SizeChangedEventArgs e)
    {
        double windowWidth = Window.GetWindow(this)?.ActualWidth ?? ActualWidth;
        bool narrow = windowWidth < 1000;

        if (narrow)
        {
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
            StatsColumn.Width = new GridLength(320);
            TimerRow.Height = new GridLength(1, GridUnitType.Star);
            StatsRow.Height = new GridLength(0);
            Grid.SetRow(StatsRail, 0);
            Grid.SetColumn(StatsRail, 1);
            Grid.SetColumnSpan(StatsRail, 1);
            TimerCard.Margin = new Thickness(0, 0, 18, 0);
        }
    }
}
