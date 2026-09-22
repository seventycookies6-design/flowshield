using System.Windows;
using System.Windows.Controls;
using Size = System.Windows.Size;

namespace FlowShield.Infrastructure;

/// <summary>
/// Lays its children out in as many columns as the width allows, from one up
/// to <see cref="MaxColumns"/>, each at least <see cref="MinColumnWidth"/>
/// wide. DESIGN_SYSTEM.md §4: a settings-like page fills the window as two
/// columns on a wide screen and stacks into one on a narrow one, rather than
/// sitting in a fixed-width column in the middle of it.
///
/// Children keep their order. Each goes into whichever column is currently
/// shortest, so the columns stay balanced: in one column this is a plain
/// stack, in the original order. Put the gaps in <see cref="Spacing"/>, not
/// in the children's margins, so a stacked layout and a column layout space
/// alike.
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

    private int _columns = 1;
    private double _columnWidth;
    private double _measuredWidth = double.NaN;
    private readonly List<(int Column, double Top)> _slots = new();

    protected override Size MeasureOverride(Size available)
    {
        _measuredWidth = available.Width;
        _columns = ColumnsFor(available.Width, MinColumnWidth, MaxColumns, Spacing);
        _columnWidth = double.IsInfinity(available.Width)
            ? double.PositiveInfinity
            : Math.Max(0, (available.Width - Spacing * (_columns - 1)) / _columns);

        var heights = new double[_columns];
        _slots.Clear();
        double widest = 0;
        foreach (UIElement child in InternalChildren)
        {
            child.Measure(new Size(_columnWidth, double.PositiveInfinity));
            if (child.Visibility == Visibility.Collapsed)
            {
                _slots.Add((0, 0));
                continue;
            }
            var column = Shortest(heights);
            var top = heights[column] > 0 ? heights[column] + Spacing : 0;
            _slots.Add((column, top));
            heights[column] = top + child.DesiredSize.Height;
            widest = Math.Max(widest, child.DesiredSize.Width);
        }

        var width = double.IsInfinity(available.Width) ? widest : available.Width;
        return new Size(width, heights.Length == 0 ? 0 : heights.Max());
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

        for (var i = 0; i < InternalChildren.Count; i++)
        {
            var child = InternalChildren[i];
            var (column, top) = _slots[i];
            child.Arrange(new Rect(column * (columnWidth + Spacing), top, columnWidth, child.DesiredSize.Height));
        }
        return final;
    }

    private static int Shortest(double[] heights)
    {
        var best = 0;
        for (var i = 1; i < heights.Length; i++)
            if (heights[i] < heights[best]) best = i;
        return best;
    }
}
