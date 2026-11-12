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
    /// <summary>
    /// Below this view width Up next and Momentum leave the Now card's side
    /// and sit in a row under it, as in the small-window mockup (#431).
    /// </summary>
    public const double StackStatsBelow = 900;

    /// <summary>Below this view width the side cards stack in one column.</summary>
    public const double OneColumnBelow = 600;

    /// <summary>
    /// Below this view height the cards tighten their spacing, so the small
    /// window (1092 × 614) shows the Now card, Up next, Momentum and
    /// Templates without scrolling, as app-today-ready-small-dark.png does.
    /// </summary>
    public const double CompactBelow = 600;

    /// <summary>Below this Now-card width the ring sits above the rest of the card.</summary>
    public const double RingAboveBelow = 560;

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
        if (e.NewValue is TodayViewModel vm)
        {
            ShowProgress(vm.Progress, glide: false);
            PlaceBreakSection(vm);
            OrderSideCards(vm);
        }
    }

    /// <summary>
    /// A sprint starting brings the page back to the top, so the ring and its
    /// End button are never left scrolled up out of sight; and the break's
    /// section and the side cards follow the Now card's state.
    /// </summary>
    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (sender is not TodayViewModel vm) return;
        switch (e.PropertyName)
        {
            case nameof(TodayViewModel.Progress):
                ShowProgress(vm.Progress, glide: true);
                break;
            case nameof(TodayViewModel.IsRunning):
                if (vm.IsRunning) PageScroll.ScrollToTop();
                PlaceBreakSection(vm);
                break;
            case nameof(TodayViewModel.JournalPromptVisible):
                PlaceBreakSection(vm);
                OrderSideCards(vm);
                break;
            case nameof(TodayViewModel.BreakPanelVisible):
            case nameof(TodayViewModel.IsOnBreak):
                PlaceBreakSection(vm);
                break;
        }
    }

    /// <summary>Puts keyboard focus back on Set up when the setup panel closes, if it is showing.</summary>
    public void FocusSetUp()
    {
        if (SetUpButton.IsVisible) SetUpButton.Focus();
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
    /// Where the break's section goes. While the end of a sprint is on the Now
    /// card, the break sits under it as its own card (the mockup); once a break
    /// runs with nothing else on the card, it moves into the card's right-hand
    /// side, beside the break's countdown, rather than leaving that side empty.
    /// One element moved between two hosts, so each button exists once.
    /// </summary>
    private void PlaceBreakSection(TodayViewModel vm)
    {
        var inCard = vm.IsOnBreak && !vm.JournalPromptVisible;
        var host = inCard ? BreakHostInCard : BreakHostBelow;
        if (!ReferenceEquals(host.Content, BreakSection))
        {
            BreakHostInCard.Content = null;
            BreakHostBelow.Content = null;
            host.Content = BreakSection;
        }

        // In the card the buttons go under the words; under it, beside them.
        Grid.SetRow(BreakButtons, inCard ? 1 : 0);
        Grid.SetColumn(BreakButtons, inCard ? 0 : 1);
        BreakButtons.Margin = inCard ? new Thickness(0, 16, 0, 0) : new Thickness(0);
        BreakCard.Visibility = !inCard && vm.BreakPanelVisible ? Visibility.Visible : Visibility.Collapsed;
    }

    /// <summary>The space between cards: 24, or 12 when the page is short.</summary>
    private double _gap = 24;

    /// <summary>Spacing for the space the page has: the mockups' at full size, tighter when short.</summary>
    private void ApplyDensity(bool compact)
    {
        var gap = _gap;
        NowCard.Padding = compact ? new Thickness(22, 12, 22, 14) : new Thickness(28, 22, 28, 28);
        NowBody.Margin = new Thickness(0, compact ? 6 : 18, 0, 0);
        ShieldLabel.Margin = compact ? new Thickness(0, 8, 0, 4) : new Thickness(0, 20, 0, 8);
        PlanLabel.Margin = compact ? new Thickness(0, 8, 0, 4) : new Thickness(0, 20, 0, 8);
        ShieldExplanation.Margin = new Thickness(0, compact ? 6 : 8, 0, 0);
        SetUpButton.Height = StartButton.Height = PlanInput.Height = compact ? 36 : 40;
        UpNextWhenText.FontSize = compact ? 20 : 22;
        UpNextWhenText.LineHeight = compact ? 26 : 30;
        UpNextWhenText.Margin = new Thickness(0, compact ? 4 : 8, 0, 0);
        SideRowGap.Height = new GridLength(SideRowGap.Height.Value > 0 ? gap : 0);
        if (SideCards.Margin.Top > 0) SideCards.Margin = new Thickness(0, gap, 0, 0);
        TemplatesCard.Margin = new Thickness(0, gap, 0, 0);
        BreakCard.Margin = new Thickness(0, gap, 0, 0);
        TemplatesCard.Padding = compact ? new Thickness(16, 10, 16, 12) : new Thickness(20, 16, 20, 20);
        TemplateList.Margin = new Thickness(0, compact ? 8 : 14, 0, 0);
        TemplateList.Resources["TemplateCardHeight"] = compact ? 52.0 : 56.0;
        UpNextCard.Padding = compact ? new Thickness(16, 8, 16, 10) : new Thickness(20, 18, 20, 22);
        MomentumCard.Padding = compact ? new Thickness(16, 8, 16, 10) : new Thickness(20, 18, 20, 20);
        MomentumNumbers.Margin = new Thickness(0, compact ? 4 : 8, 0, 0);
        TrendBox.Height = compact ? 18 : 52;
        TrendPanel.Margin = new Thickness(0, compact ? 4 : 16, 0, 0);
        // At this size the line is a sparkline under the number, without its
        // range and peak; the chart's spoken description is also on the
        // number's help text, so it is never lost.
        TrendCaptions.Visibility = compact ? Visibility.Collapsed : Visibility.Visible;
    }

    /// <summary>At the end of a sprint Momentum comes first, since that is what just moved.</summary>
    private void OrderSideCards(TodayViewModel vm)
    {
        var momentumFirst = vm.JournalPromptVisible;
        var stacked = SideCol1.Width.Value > 0 || SideCol1.Width.IsStar;
        if (stacked) return;   // side by side under the card, the order is left to right and stays
        Grid.SetRow(UpNextCard, momentumFirst ? 2 : 0);
        Grid.SetRow(MomentumCard, momentumFirst ? 0 : 2);
        SideRow0.Height = momentumFirst ? new GridLength(1, GridUnitType.Star) : GridLength.Auto;
        SideRow1.Height = momentumFirst ? GridLength.Auto : new GridLength(1, GridUnitType.Star);
    }

    /// <summary>
    /// Keyed on the view's own size, not the window's: the view responds to
    /// the space it actually has, whatever the rail is doing (#189).
    /// </summary>
    private void OnSizeChanged(object sender, SizeChangedEventArgs e)
    {
        var width = e.NewSize.Width;
        _gap = e.NewSize.Height < CompactBelow ? 10 : 24;
        RingScale.Width = RingScale.Height = TimerRingSize.For(e.NewSize.Height);
        Glow.Width = Glow.Height = RingScale.Width * 1.45;

        if (width >= StackStatsBelow)
        {
            // Now beside a column of Up next over Momentum.
            SideColumn.MinWidth = 300;
            SideColumn.Width = new GridLength(0.46, GridUnitType.Star);
            GapColumn.Width = new GridLength(_gap);
            Grid.SetRow(SideCards, 1);
            Grid.SetColumn(SideCards, 2);
            Grid.SetColumnSpan(SideCards, 1);
            Grid.SetColumnSpan(NowCard, 1);
            SideCards.Margin = new Thickness(0);
            SideColGap.Width = new GridLength(0);
            SideCol1.Width = new GridLength(0);
            SideRowGap.Height = new GridLength(_gap);
            Grid.SetColumn(UpNextCard, 0);
            Grid.SetColumn(MomentumCard, 0);
            if (DataContext is TodayViewModel vm) OrderSideCards(vm);
            else
            {
                Grid.SetRow(UpNextCard, 0);
                Grid.SetRow(MomentumCard, 2);
            }
        }
        else
        {
            // Now across the page, with the side cards under it: side by side
            // while there is room, one above the other below that.
            SideColumn.MinWidth = 0;
            SideColumn.Width = new GridLength(0);
            GapColumn.Width = new GridLength(0);
            Grid.SetColumnSpan(NowCard, 3);
            Grid.SetRow(SideCards, 2);
            Grid.SetColumn(SideCards, 0);
            Grid.SetColumnSpan(SideCards, 3);
            SideCards.Margin = new Thickness(0, _gap, 0, 0);
            SideRow0.Height = GridLength.Auto;
            SideRow1.Height = GridLength.Auto;

            bool oneColumn = width < OneColumnBelow;
            SideColGap.Width = new GridLength(oneColumn ? 0 : _gap);
            SideCol1.Width = oneColumn ? new GridLength(0) : new GridLength(1, GridUnitType.Star);
            SideRowGap.Height = new GridLength(oneColumn ? _gap : 0);
            Grid.SetRow(UpNextCard, 0);
            Grid.SetColumn(UpNextCard, 0);
            Grid.SetRow(MomentumCard, oneColumn ? 2 : 0);
            Grid.SetColumn(MomentumCard, oneColumn ? 0 : 2);
        }

        ApplyDensity(e.NewSize.Height < CompactBelow);

        // Inside the Now card: the ring beside the rest, or above it when narrow.
        var side = Math.Clamp((width - 24) * 0.46 / 1.46, 300, 400);
        var cardWidth = width >= StackStatsBelow ? width - 24 - side : width;
        bool ringAbove = cardWidth < RingAboveBelow;
        Grid.SetRow(NowSide, ringAbove ? 1 : 0);
        Grid.SetColumn(NowSide, ringAbove ? 0 : 2);
        Grid.SetColumnSpan(NowSide, ringAbove ? 3 : 1);
        NowSide.Margin = ringAbove ? new Thickness(0, 20, 0, 0) : new Thickness(0);
        RingGapColumn.Width = new GridLength(ringAbove ? 0 : 36);
        Grid.SetColumnSpan(RingArea, ringAbove ? 3 : 1);
    }
}
