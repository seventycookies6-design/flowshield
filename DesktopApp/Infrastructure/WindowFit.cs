namespace FlowShield.Infrastructure;

/// <summary>
/// Fits a window inside its monitor's work area (#296). The main window asks
/// for 1180 × 760, which is taller than the 720 px work area of a 1366 × 768
/// laptop and wider than a 1024 × 768 screen; Windows centres it against the
/// whole screen, so the title bar ends up above the top edge and the bottom
/// under the taskbar.
///
/// Shrinks to the work area, never below the window's minimum size, then
/// moves the window back inside it. When even the minimum doesn't fit, the
/// top-left corner wins, so the title bar (the one thing needed to move the
/// window) always stays on-screen. All values in device-independent pixels.
/// Pure, so tier 1 can mirror it.
/// </summary>
public static class WindowFit
{
    public static System.Windows.Rect Fit(
        System.Windows.Rect window, System.Windows.Rect workArea, double minWidth, double minHeight)
    {
        double width = Math.Max(minWidth, Math.Min(window.Width, workArea.Width));
        double height = Math.Max(minHeight, Math.Min(window.Height, workArea.Height));

        double left = Math.Max(workArea.Left, Math.Min(window.Left, workArea.Right - width));
        double top = Math.Max(workArea.Top, Math.Min(window.Top, workArea.Bottom - height));

        return new System.Windows.Rect(left, top, width, height);
    }
}
