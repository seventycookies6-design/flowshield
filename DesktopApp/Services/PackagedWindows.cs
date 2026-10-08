using System.Runtime.InteropServices;
using System.Text;

namespace FlowShield.Services;

/// <summary>
/// Finds the real app behind a classic Store app's window (#348).
///
/// A classic Store (UWP) app draws its content in a <c>CoreWindow</c> owned by
/// its own process, but the top-level window around it, the one with the
/// title bar and the one <c>GetForegroundWindow</c> returns, belongs to
/// <c>ApplicationFrameHost</c>, which frames every Store app at once. So the
/// app's own process has no main window to ask to close, and the window in
/// front names the frame host rather than the app.
///
/// Read-only user-level calls, the same restraint as the Soft notice: list
/// windows, read their class and owning process. The one write is
/// <see cref="CloseFramesOf"/>, which posts the WM_CLOSE the frame's own close
/// button sends. Nothing here ever closes <c>ApplicationFrameHost</c> itself.
/// </summary>
public static class PackagedWindows
{
    private const string FrameClass = "ApplicationFrameWindow";
    private const string CoreClass = "Windows.UI.Core.CoreWindow";
    private const uint WM_CLOSE = 0x0010;

    private delegate bool EnumWindowsProc(IntPtr window, IntPtr data);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr data);

    [DllImport("user32.dll")]
    private static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc callback, IntPtr data);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr window, StringBuilder name, int maxCount);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr window);

    [DllImport("user32.dll")]
    private static extern bool PostMessage(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);

    /// <summary>
    /// The process of the app inside <paramref name="window"/> when it is a
    /// Store app's frame; null for any other window, and for a frame whose
    /// app has detached (a suspended or minimised Store app).
    /// </summary>
    public static uint? AppProcessBehind(IntPtr window)
    {
        try
        {
            if (window == IntPtr.Zero || ClassOf(window) != FrameClass) return null;
            GetWindowThreadProcessId(window, out var framePid);

            uint? app = null;
            EnumChildWindows(window, (child, _) =>
            {
                if (ClassOf(child) != CoreClass) return true;
                GetWindowThreadProcessId(child, out var pid);
                // The frame keeps a CoreWindow of its own for the title bar;
                // only one owned by another process is the app.
                if (pid == 0 || pid == framePid) return true;
                app = pid;
                return false;
            }, IntPtr.Zero);
            return app;
        }
        catch
        {
            return null;
        }
    }

    /// <summary>Visible Store app frames on screen now, with the app process inside each.</summary>
    public static List<(IntPtr Frame, uint AppProcessId)> Frames()
    {
        var frames = new List<(IntPtr, uint)>();
        try
        {
            EnumWindows((window, _) =>
            {
                if (IsWindowVisible(window) && AppProcessBehind(window) is { } pid) frames.Add((window, pid));
                return true;
            }, IntPtr.Zero);
        }
        catch
        {
            // Nothing found is the safe answer.
        }
        return frames;
    }

    /// <summary>
    /// Asks the Store app running as <paramref name="processId"/> to close,
    /// the way its frame's close button does, so it can save first. Returns
    /// false when it has no frame on screen; the caller's grace period and
    /// kill handle that case as they always have.
    /// </summary>
    public static bool CloseFramesOf(int processId)
    {
        var asked = false;
        foreach (var (frame, pid) in Frames())
        {
            if (pid != (uint)processId) continue;
            asked |= PostMessage(frame, WM_CLOSE, IntPtr.Zero, IntPtr.Zero);
        }
        return asked;
    }

    private static string ClassOf(IntPtr window)
    {
        var name = new StringBuilder(64);
        return GetClassName(window, name, name.Capacity) > 0 ? name.ToString() : "";
    }
}
