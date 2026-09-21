using System;
using System.Windows;

namespace FlowShield.Infrastructure;

/// <summary>
/// Single duration provider for every animation in the app (DESIGN_SYSTEM.md
/// §8): 120 ms for hovers and presses, 200 ms for panels and selection
/// changes, 300 ms for page transitions. Every one of those collapses to
/// zero when Windows' own "Animation effects" setting is off, so nothing
/// else in the app should read <see cref="SystemParameters.ClientAreaAnimation"/>
/// directly — read it here, once, and every Storyboard binds its Duration to
/// one of the properties below.
/// </summary>
public static class Motion
{
    /// <summary>
    /// Test seam. <see cref="SystemParameters.ClientAreaAnimation"/> reads the
    /// live OS setting, which a test can't flip on the host machine — set
    /// this instead and reset it to null when done.
    /// </summary>
    public static Func<bool>? AnimationsEnabledOverride;

    public static bool AnimationsEnabled =>
        AnimationsEnabledOverride?.Invoke() ?? SystemParameters.ClientAreaAnimation;

    /// <summary>120 ms — hovers and presses.</summary>
    public static Duration Hover => Of(120);

    /// <summary>200 ms — panels and selection changes (chip selection, the
    /// disabled-state opacity change when a sprint starts or ends).</summary>
    public static Duration Selection => Of(200);

    /// <summary>300 ms — page transitions.</summary>
    public static Duration Page => Of(300);

    private static Duration Of(int ms) =>
        new(TimeSpan.FromMilliseconds(AnimationsEnabled ? ms : 0));
}
