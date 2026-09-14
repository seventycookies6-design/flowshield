namespace FlowShield.Models;

/// <summary>How ending a running sprint works at a given moment.</summary>
public enum EndFlow
{
    /// <summary>Inside the grace period: ends with no penalty and nothing recorded.</summary>
    Cancel,

    /// <summary>Soft: ends straight away, recorded as ended early.</summary>
    Immediate,

    /// <summary>Firm: a confirmation whose "End anyway" unlocks after a short countdown.</summary>
    Confirm,

    /// <summary>Sealed: a longer countdown, then the phrase has to be typed.</summary>
    Sealed,
}

/// <summary>
/// The rules for getting out of a sprint (launch checklist F2).
///
/// If ending a sprint is effortless the shield is pointless, but a lock with no
/// way out is how people end up locked out of something they need. So the way
/// out gets harder as the shield gets stronger, and there's always one.
/// Kept free of UI so the rules can be tested on their own.
/// </summary>
public static class EndSprintPolicy
{
    /// <summary>The literal phrase a Sealed sprint needs before it can be ended.</summary>
    public const string SealedPhrase = "end my sprint";

    /// <summary>
    /// Shrinks every wait to a few seconds so the UI test suite doesn't sit
    /// through them. Set only by the --short-timers launch flag; it never skips
    /// a step, only shortens the waits.
    /// </summary>
    public static bool UseShortTimers { get; set; }

    /// <summary>Time after starting in which a sprint can be cancelled without penalty.</summary>
    public static TimeSpan GracePeriod => UseShortTimers ? TimeSpan.FromSeconds(3) : TimeSpan.FromMinutes(2);

    /// <summary>How long Firm's "End anyway" stays disabled.</summary>
    public static TimeSpan FirmConfirmDelay => UseShortTimers ? TimeSpan.FromSeconds(2) : TimeSpan.FromSeconds(5);

    /// <summary>How long Sealed makes you wait before the phrase can confirm.</summary>
    public static TimeSpan SealedCountdown => UseShortTimers ? TimeSpan.FromSeconds(3) : TimeSpan.FromSeconds(30);

    public static EndFlow FlowFor(ShieldLevel shield, TimeSpan elapsed) =>
        elapsed < GracePeriod
            ? EndFlow.Cancel
            : shield switch
            {
                ShieldLevel.Soft => EndFlow.Immediate,
                ShieldLevel.Firm => EndFlow.Confirm,
                _ => EndFlow.Sealed,
            };

    /// <summary>The wait before "End anyway" can be pressed, for the flows that have one.</summary>
    public static TimeSpan DelayFor(EndFlow flow) => flow switch
    {
        EndFlow.Confirm => FirmConfirmDelay,
        EndFlow.Sealed => SealedCountdown,
        _ => TimeSpan.Zero,
    };

    /// <summary>
    /// Momentum after ending a sprint early. Abandoning decays it rather than
    /// resetting it; giving up on a Sealed sprint, which you chose because you
    /// wanted it to hold, costs more.
    /// </summary>
    public static double MomentumAfterEndingEarly(double score, ShieldLevel shield) =>
        shield == ShieldLevel.Sealed
            ? Math.Round(Math.Max(0, score * 0.7 - 5), 1)
            : Math.Round(Math.Max(0, score * 0.85 - 2), 1);

    /// <summary>Forgiving about case and spacing, strict about the words.</summary>
    public static bool PhraseMatches(string? typed) =>
        string.Join(' ', (typed ?? "").Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries))
            .Equals(SealedPhrase, StringComparison.OrdinalIgnoreCase);
}
