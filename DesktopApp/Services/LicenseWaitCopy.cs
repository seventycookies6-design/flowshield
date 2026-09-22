namespace FlowShield.Services;

/// <summary>
/// Roadmap 5.2 — "honest waiting while the licence server wakes."
///
/// The Render free instance the licence server runs on sleeps after
/// inactivity; the first request after idle takes roughly 50 seconds. This
/// class is the pure, testable half of that fix: the copy ladder shown while
/// an activation is in flight, and the retry/backoff schedule
/// <see cref="LicenseService"/> uses to ride out the cold start without ever
/// turning "the host was asleep" into "your key is invalid".
///
/// No I/O, no <c>DateTime.Now</c>, no clock of its own — everything here is a
/// pure function of an elapsed duration or an attempt index, so it can be
/// tested without a server, a timer or the UI thread.
/// </summary>
public static class LicenseWaitCopy
{
    /// <summary>First line shown the moment Activate is pressed.</summary>
    public const string ContactingMessage = "Contacting the licence server…";

    /// <summary>
    /// Shown once the wait has gone on long enough that it is no longer a
    /// normal round trip — the free-tier host is very likely waking up.
    /// </summary>
    public const string WakingUpMessage = "The server is waking up. This can take up to a minute.";

    /// <summary>Seconds after which the copy switches from "contacting" to "waking up".</summary>
    public const double WakingUpAfterSeconds = 8.0;

    /// <summary>
    /// Delays, in seconds, inserted between retry attempts after a timeout, a
    /// dropped connection, or a 5xx response. The first attempt has no
    /// preceding delay. Three attempts total (one initial + two retries),
    /// chosen with <see cref="FirstAttemptTimeoutSeconds"/> and
    /// <see cref="RetryAttemptTimeoutSeconds"/> so the worst case stays inside
    /// <see cref="TotalBudgetSeconds"/>: the first attempt is given the most
    /// time, since a genuinely cold Render instance needs it, and later
    /// attempts — now most likely hitting an already-awake host — get a
    /// shorter leash.
    /// </summary>
    public static readonly IReadOnlyList<double> RetryDelaysSeconds = new[] { 2.0, 5.0 };

    /// <summary>Per-request timeout for the very first attempt.</summary>
    public const double FirstAttemptTimeoutSeconds = 35.0;

    /// <summary>Per-request timeout for every attempt after the first.</summary>
    public const double RetryAttemptTimeoutSeconds = 15.0;

    /// <summary>Total attempts made before giving up: one initial try plus one per configured delay.</summary>
    public static int TotalAttempts => RetryDelaysSeconds.Count + 1;

    /// <summary>
    /// The whole activation attempt's time budget, retries and delays
    /// included. 35 (first) + 2 + 15 + 5 + 15 = 72s, comfortably inside the
    /// ~75s the roadmap calls for while covering a ~50s cold start plus a
    /// slow-but-awake follow-up request.
    /// </summary>
    public const double TotalBudgetSeconds =
        FirstAttemptTimeoutSeconds + 2.0 + RetryAttemptTimeoutSeconds
        + 5.0 + RetryAttemptTimeoutSeconds;

    /// <summary>The per-attempt request timeout for a given 1-based attempt number.</summary>
    public static double TimeoutForAttempt(int attempt) =>
        attempt <= 1 ? FirstAttemptTimeoutSeconds : RetryAttemptTimeoutSeconds;

    /// <summary>Message to show, given how long the current activation has been waiting overall.</summary>
    public static string MessageFor(double elapsedSeconds) =>
        elapsedSeconds < WakingUpAfterSeconds ? ContactingMessage : WakingUpMessage;

    /// <summary>
    /// True when a result is a transport problem (timeout, no connection,
    /// 5xx, an unreadable response) rather than the server's verdict on the
    /// key itself. Callers must never show "invalid key" copy when this is
    /// true — <see cref="LicenseResult.Failure"/> sets <c>Definitive: false</c>
    /// for exactly this reason.
    /// </summary>
    public static bool IsTransportFailure(bool definitive) => !definitive;
}
