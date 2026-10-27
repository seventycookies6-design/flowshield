using System.Windows;
using System.Windows.Controls;
using Size = System.Windows.Size;

namespace FlowShield.Infrastructure;

/// <summary>
/// Lays its children out as a grid of as many columns as the width allows,
/// from one up to <see cref="MaxColumns"/>, each at least
/// <see cref="MinColumnWidth"/> wide. DESIGN_SYSTEM.md §4: a settings-like
/// page fills its width in columns on a wide screen and stacks into one on a
/// narrow one.
///
/// Children keep their reading order, left to right and then down. Every
/// child in a row is as tall as the row's tallest, so cards beside each other
/// share their top and bottom edges (#406: the earlier masonry layout put
/// each card in the shortest column, which left neighbours at different
/// heights). The column count is then balanced across the rows, so five cards
/// that would fit four abreast are laid out three and two rather than four and
/// one. Put the gaps in <see cref="Spacing"/>, not in the children's margins,
/// so a stacked layout and a grid space alike.
/// </summary>
public class AdaptiveColumns : Panel
{
    public static readonly DependencyProperty MinColumnWidthProperty = DependencyProperty.Register(
        nameof(MinColumnWidth), typeof(double), typeof(AdaptiveColumns),
        new FrameworkPropertyMetadata(420.0, FrameworkPropertyMetadataOptions.AffectsMeasure));

    public static readonly DependencyProperty MaxColumnsProperty = DependencyProperty.Register(
        nameof(MaxColumns), typeof(int), typeof(AdaptiveColumns),
        new FrameworkPropertyMetadata(2, FrameworkPropertyMetadataOptions.AffectsMeasure));

    public static readonly DependencyProperty SpacingProperty = DependencyProperty.Register(
        nameof(Spacing), typeof(double), typeof(AdaptiveColumns),
        new FrameworkPropertyMetadata(16.0, FrameworkPropertyMetadataOptions.AffectsMeasure));

    /// <summary>The narrowest a column may get before the panel drops a column.</summary>
    public double MinColumnWidth
    {
        get => (double)GetValue(MinColumnWidthProperty);
        set => SetValue(MinColumnWidthProperty, value);
    }

    public int MaxColumns
    {
        get => (int)GetValue(MaxColumnsProperty);
        set => SetValue(MaxColumnsProperty, value);
    }

    /// <summary>The gap between columns, and between children in a column.</summary>
    public double Spacing
    {
        get => (double)GetValue(SpacingProperty);
        set => SetValue(SpacingProperty, value);
    }

    /// <summary>
    /// How many columns fit in <paramref name="width"/>: as many as keep each
    /// column at least <paramref name="minColumnWidth"/> wide, between one and
    /// <paramref name="maxColumns"/>. Infinite or unusable widths get one.
    /// </summary>
    public static int ColumnsFor(double width, double minColumnWidth, int maxColumns, double spacing)
    {
        if (double.IsNaN(width) || double.IsInfinity(width) || width <= 0 || minColumnWidth <= 0)
            return 1;
        var fit = (int)Math.Floor((width + spacing) / (minColumnWidth + spacing));
        return Math.Clamp(fit, 1, Math.Max(1, maxColumns));
    }

    /// <summary>
    /// The columns to use for <paramref name="count"/> children when
    /// <paramref name="fit"/> would fit: the fewest that still needs no more
    /// rows, so the last row is as full as it can be.
    /// </summary>
    public static int BalancedColumns(int count, int fit)
    {
        if (count <= 0 || fit <= 1) return Math.Max(1, fit);
        var rows = (int)Math.Ceiling(count / (double)fit);
        return (int)Math.Ceiling(count / (double)rows);
    }

    private int _columns = 1;
    private double _measuredWidth = double.NaN;
    private readonly List<(int Column, int Row)> _slots = new();
    private readonly List<double> _rowHeights = new();

    protected override Size MeasureOverride(Size available)
    {
        _measuredWidth = available.Width;
        var visible = InternalChildren.Cast<UIElement>().Count(c => c.Visibility != Visibility.Collapsed);
        _columns = BalancedColumns(visible, ColumnsFor(available.Width, MinColumnWidth, MaxColumns, Spacing));
        var columnWidth = double.IsInfinity(available.Width)
            ? double.PositiveInfinity
            : Math.Max(0, (available.Width - Spacing * (_columns - 1)) / _columns);

        _slots.Clear();
        _rowHeights.Clear();
        double widest = 0;
        var index = 0;
        foreach (UIElement child in InternalChildren)
        {
            child.Measure(new Size(columnWidth, double.PositiveInfinity));
            if (child.Visibility == Visibility.Collapsed)
            {
                _slots.Add((0, -1));
                continue;
            }
            var row = index / _columns;
            _slots.Add((index % _columns, row));
            if (row == _rowHeights.Count) _rowHeights.Add(0);
            _rowHeights[row] = Math.Max(_rowHeights[row], child.DesiredSize.Height);
            widest = Math.Max(widest, child.DesiredSize.Width);
            index++;
        }

        var width = double.IsInfinity(available.Width) ? widest : available.Width;
        var height = _rowHeights.Sum() + Spacing * Math.Max(0, _rowHeights.Count - 1);
        return new Size(width, height);
    }

    protected override Size ArrangeOverride(Size final)
    {
        // Arrange normally runs at the width Measure saw. If the parent changed
        // its mind, measure again at the final width: a different column width
        // wraps text differently, so the heights measured before no longer hold.
        if (Math.Abs(final.Width - _measuredWidth) > 0.5 || double.IsNaN(_measuredWidth)
            || _slots.Count != InternalChildren.Count)
        {
            MeasureOverride(new Size(final.Width, double.PositiveInfinity));
        }
        var columnWidth = Math.Max(0, (final.Width - Spacing * (_columns - 1)) / _columns);

        var tops = new double[_rowHeights.Count];
        for (var r = 1; r < tops.Length; r++)
            tops[r] = tops[r - 1] + _rowHeights[r - 1] + Spacing;

        for (var i = 0; i < InternalChildren.Count; i++)
        {
            var child = InternalChildren[i];
            var (column, row) = _slots[i];
            if (row < 0)
            {
                child.Arrange(new Rect(0, 0, 0, 0));
                continue;
            }
            child.Arrange(new Rect(column * (columnWidth + Spacing), tops[row], columnWidth, _rowHeights[row]));
        }
        return final;
    }
}
