using System.Windows.Controls;

namespace FlowShield.Views;

/// <summary>
/// History (F16). No code behind the view: the page is read-only, its layout
/// adapts through <see cref="Infrastructure.AdaptiveColumns"/> rather than a
/// size handler, and everything it shows comes from
/// <see cref="ViewModels.HistoryViewModel"/>.
/// </summary>
public partial class HistoryView : UserControl
{
    public HistoryView() => InitializeComponent();
}
