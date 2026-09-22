using System;
using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media.Animation;
using FlowShield.Infrastructure;
using FlowShield.ViewModels;

namespace FlowShield.Views;

public partial class TodayView : UserControl
{
    /// <summary>Below this view width the stats stack under the timer (DESIGN_SYSTEM.md §4).</summary>
    public const double StackStatsBelow = 700;

    public TodayView()
    {
        InitializeComponent();
        DataContextChanged += OnDataContextChanged;
    }

    /// <summary>
    /// The fraction of the sprint or break still to run, 1 at the start and 0
    /// at the end: the ring counts down, so it drains. Animated between the
    /// view model's once-a-second Progress ticks so the arc glides instead of
    /// stepping (DESIGN_SYSTEM.md §7).
    /// </summary>
    public static readonly DependencyProperty RingRemainingProperty = DependencyProperty.Register(
        nameof(RingRemaining), typeof(double), typeof(TodayView), new PropertyMetadata(1.0));

    public double RingRemaining
    {
        get => (double)GetValue(RingRemainingProperty);
        set => SetValue(RingRemainingProperty, value);
    }

    /// <summary>A tick moves the ring by far less than this; anything bigger (a
    /// new sprint, a restored one, the end) jumps rather than sweeping.</summary>
    private const double GlideAtMost = 0.1;

    private void OnDataContextChanged(object sender, DependencyPropertyChangedEventArgs e)
    {
        if (e.OldValue is INotifyPropertyChanged old) old.PropertyChanged -= OnViewModelChanged;
        if (e.NewValue is INotifyPropertyChanged now) now.PropertyChanged += OnViewModelChanged;
        if (e.NewValue is TodayViewModel vm) ShowProgress(vm.Progress, glide: false);
    }

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(TodayViewModel.Progress) && sender is TodayViewModel vm)
            ShowProgress(vm.Progress, glide: true);
    }

    private void ShowProgress(double progress, bool glide)
    {
        var target = Math.Clamp(1 - progress, 0, 1);
        var from = RingRemaining;
        if (glide && Motion.AnimationsEnabled && target < from && from - target <= GlideAtMost)
        {
            // Linear over the second until the next tick lands exactly where
            // this one ends, so the sweep never speeds up or pauses.
            BeginAnimation(RingRemainingProperty, new DoubleAnimation(from, target, TimeSpan.FromSeconds(1)));
            return;
        }
        BeginAnimation(RingRemainingProperty, null);
        RingRemaining = target;
    }

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
