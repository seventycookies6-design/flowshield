using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using FlowShield.ViewModels;

namespace FlowShield.Views;

/// <summary>
/// History (F16). Almost no code behind the view: the page is read-only, its
/// layout adapts through <see cref="Infrastructure.AdaptiveColumns"/> rather
/// than a size handler, and everything it shows comes from
/// <see cref="HistoryViewModel"/>. The one exception is scrolling the
/// momentum card into view when Today's "How momentum works" opens it (#147).
/// </summary>
public partial class HistoryView : UserControl
{
    private HistoryViewModel? _vm;

    public HistoryView()
    {
        InitializeComponent();
        DataContextChanged += OnDataContextChanged;
        // The request arrives while History is still collapsed (the link asks
        // first, then switches page), so it is acted on once the page shows.
        IsVisibleChanged += (_, _) => ScrollToExplainerIfAsked();
    }

    private void OnDataContextChanged(object sender, DependencyPropertyChangedEventArgs e)
    {
        if (_vm is not null) _vm.PropertyChanged -= OnViewModelChanged;
        _vm = e.NewValue as HistoryViewModel;
        if (_vm is not null) _vm.PropertyChanged += OnViewModelChanged;
    }

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(HistoryViewModel.ExplainerScrollPending)) ScrollToExplainerIfAsked();
    }

    private void ScrollToExplainerIfAsked()
    {
        if (_vm is not { ExplainerScrollPending: true } || !IsVisible) return;
        _vm.ExplainerScrollPending = false;
        // After layout, so the card has its place and the opened rule its height.
        Dispatcher.BeginInvoke(() => MomentumCard.BringIntoView(), DispatcherPriority.Loaded);
    }
}
