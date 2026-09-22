using System.Diagnostics;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using FlowShield.Models;
using System.Linq;

namespace FlowShield.Services;

public record LicenseResult(
    bool Ok,
    bool IsPro,
    string Status,
    string Message,
    string? Email = null,
    string? LicenseKey = null,
    bool Definitive = true)
{
    /// <summary>
    /// A transport failure, not a verdict.
    ///
    /// The distinction matters: an answer from the server is authoritative and
    /// may revoke Pro, whereas an unreachable server says nothing about the
    /// subscription and must never cost a paying user their features.
    /// </summary>
    public static LicenseResult Failure(string message) =>
        new(false, false, "error", message, Definitive: false);
}

/// <summary>
/// Talks to the license server's <c>POST /validate</c> and caches the verdict in
/// settings so the app opens in the right tier while offline.
/// </summary>
public class LicenseService
{
    private readonly SettingsService _settings;
    private readonly HttpClient _http;

    /// <summary>
    /// Generous because the licence server may be on a free tier that sleeps
    /// after inactivity; the first request then pays a cold start of roughly a
    /// minute. A short timeout here turns "the host was asleep" into "your
    /// licence is invalid", which is the worst possible way to be wrong.
    /// </summary>
    private static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(35);

    public LicenseService(SettingsService settings, HttpClient? http = null)
    {
        _settings = settings;
        _http = http ?? new HttpClient { Timeout = RequestTimeout };
    }

    /// <summary>
    /// Mutates the shared <see cref="AppSettings"/> and saves it as one step,
    /// on the UI thread.
    ///
    /// The UI thread is the only thread anything else in the app mutates
    /// settings from (TodayViewModel, BlockedAppsViewModel and friends all run
    /// on it), so <see cref="SettingsService.Save"/> can only be race-free if
    /// every other caller lands there too. App.OnStartup calls
    /// <see cref="RefreshAsync"/> without awaiting it, and today's default
    /// <c>await</c> continuations happen to resume back on the UI thread's
    /// captured <c>SynchronizationContext</c> — but nothing enforced that. A
    /// single <c>ConfigureAwait(false)</c> added anywhere in this chain, or a
    /// caller that starts this on a thread-pool thread, would have silently
    /// put a background thread back in the business of serializing the live
    /// settings object while the UI thread mutates it (#202: a background
    /// licence refresh raced <c>TodayViewModel.EndSprint</c>'s
    /// <c>Sessions.Add</c> and the sprint that had just finished was lost).
    /// Marshalling explicitly — the same pattern <c>MainViewModel.OnBlocked</c>
    /// already uses for the blocker's background timer — makes "settings is
    /// only ever touched from one thread" a real invariant instead of an
    /// accident of the current call graph.
    /// </summary>
    private void MutateAndSave(AppSettings settings, Action<AppSettings> mutate)
    {
        var dispatcher = System.Windows.Application.Current?.Dispatcher;
        if (dispatcher is null || dispatcher.CheckAccess())
        {
            // No WPF dispatcher (a headless caller, e.g. a future test), or
            // already on it — nothing to marshal.
            mutate(settings);
            _settings.Save(settings);
        }
        else
        {
            dispatcher.Invoke(() =>
            {
                mutate(settings);
                _settings.Save(settings);
            });
        }
    }

    private sealed class ValidateResponse
    {
        [JsonPropertyName("valid")] public bool Valid { get; set; }
        [JsonPropertyName("isPro")] public bool IsPro { get; set; }
        [JsonPropertyName("status")] public string? Status { get; set; }
        [JsonPropertyName("reason")] public string? Reason { get; set; }
        [JsonPropertyName("message")] public string? Message { get; set; }
        [JsonPropertyName("email")] public string? Email { get; set; }
        [JsonPropertyName("licenseKey")] public string? LicenseKey { get; set; }
        [JsonPropertyName("deviceCount")] public int? DeviceCount { get; set; }
        [JsonPropertyName("deviceLimit")] public int? DeviceLimit { get; set; }
    }

    /// <summary>
    /// Validates against the server and, on success, writes the Pro flag into
    /// settings. A network failure never downgrades an already-Pro install —
    /// the user paid, and a flaky connection is not grounds for revocation.
    ///
    /// <paramref name="progress"/>, if given, is reported with the copy ladder
    /// message (<see cref="LicenseWaitCopy.MessageFor"/>) each time a wait
    /// begins, so a caller such as <c>SettingsViewModel</c> can show honest,
    /// time-aware status while a sleeping licence server wakes up.
    /// </summary>
    public async Task<LicenseResult> ValidateAsync(
        string licenseKey, string email, AppSettings settings, IProgress<string>? progress = null)
    {
        var key = (licenseKey ?? "").Trim();
        var mail = (email ?? "").Trim();

        if (key.Length == 0 && mail.Length == 0)
            return LicenseResult.Failure("Enter your license key (or the email you used at checkout).");

        var url = settings.LicenseServerUrl.TrimEnd('/') + "/validate";

        try
        {
            Log.Info($"validating license against {url}");

            // Retry on timeouts, dropped connections and 5xx responses — all
            // transport trouble, most likely a sleeping free-tier host waking
            // up — using LicenseWaitCopy's schedule: a generous first attempt
            // (long enough for a genuine cold start), shorter follow-ups (the
            // host should be awake by then), with short delays between so we
            // don't hammer a host that is still booting. A rejected key is not
            // retried; repeating that just makes the user wait longer for the
            // same answer.
            var stopwatch = Stopwatch.StartNew();
            HttpResponseMessage? response = null;
            Exception? transportError = null;

            for (var attempt = 1; attempt <= LicenseWaitCopy.TotalAttempts; attempt++)
            {
                progress?.Report(LicenseWaitCopy.MessageFor(stopwatch.Elapsed.TotalSeconds));

                using var cts = new CancellationTokenSource(
                    TimeSpan.FromSeconds(LicenseWaitCopy.TimeoutForAttempt(attempt)));
                try
                {
                    var attemptResponse = await _http.PostAsJsonAsync(url, new
                    {
                        licenseKey = key,
                        email = mail,
                        deviceId = DeviceIdentity.Id,
                        deviceName = DeviceIdentity.Name,
                    }, cts.Token);

                    if ((int)attemptResponse.StatusCode >= 500)
                    {
                        transportError = new HttpRequestException(
                            $"license server returned HTTP {(int)attemptResponse.StatusCode}");
                        Log.Warn($"license request got a server error (attempt {attempt}): "
                                 + $"HTTP {(int)attemptResponse.StatusCode}; the server may be waking up");
                        attemptResponse.Dispose();
                    }
                    else
                    {
                        response = attemptResponse;
                        break;
                    }
                }
                catch (Exception ex) when (ex is TaskCanceledException or OperationCanceledException or HttpRequestException)
                {
                    transportError = ex;
                    Log.Warn($"license request failed (attempt {attempt}): {ex.Message}; "
                             + "the server may be waking up");
                }

                if (attempt < LicenseWaitCopy.TotalAttempts)
                {
                    var delay = LicenseWaitCopy.RetryDelaysSeconds[attempt - 1];
                    await Task.Delay(TimeSpan.FromSeconds(delay));
                }
            }

            if (response is null)
            {
                // Transport failure across every attempt. This is never a
                // verdict on the key — see LicenseResult.Failure — so it must
                // never be worded like a rejected key.
                Log.Error("license server unreachable after retries",
                    transportError ?? new Exception("unknown transport failure"));
                return LicenseResult.Failure(
                    $"Couldn't reach the license server at {settings.LicenseServerUrl}. " +
                    "It may still be waking up — check it's running, then try again.");
            }

            using var _ = response;
            var body = await response.Content.ReadFromJsonAsync<ValidateResponse>();
            if (body is null)
                return LicenseResult.Failure("The license server returned an unreadable response.");

            // Anything from here on is the server's verdict, and is definitive.

            if (body.IsPro)
            {
                MutateAndSave(settings, s =>
                {
                    s.IsPro = true;
                    s.LicenseKey = body.LicenseKey ?? key;
                    s.LicenseEmail = body.Email ?? mail;
                    s.LicenseStatus = body.Status ?? "active";
                    s.LicenseCheckedUtc = DateTime.UtcNow;
                    s.DeviceCount = body.DeviceCount ?? 0;
                    s.DeviceLimit = body.DeviceLimit ?? 0;
                });

                Log.Info($"license activated: status={settings.LicenseStatus} "
                         + $"devices={settings.DeviceCount}/{settings.DeviceLimit}");
                return new LicenseResult(true, true, settings.LicenseStatus,
                    "FlowShield activated. Every feature is yours to keep.",
                    settings.LicenseEmail, settings.LicenseKey);
            }

            var reason = body.Reason ?? "invalid";
            var message = body.Message ?? reason switch
            {
                "malformed_key" => "That key isn't in the FS-XXXX-XXXX-XXXX-XXXX format.",
                "not_found" => "We couldn't find a purchase for those details.",
                "device_limit_reached" =>
                    "This licence is already active on the maximum number of devices.",
                "license_refunded" => "That purchase was refunded, so the licence is no longer active.",
                "license_pending" => "That purchase hasn't been paid yet.",
                _ when reason.StartsWith("license_") =>
                    $"That licence is {reason["license_".Length..]}.",
                // Licences from the old monthly plan still report this way.
                _ when reason.StartsWith("subscription_") =>
                    $"That subscription is {reason["subscription_".Length..]}.",
                _ => "That license could not be validated.",
            };

            // The subscription is fine; this machine simply has no seat. Say so,
            // rather than letting it read as a payment failure.
            if (reason == "device_limit_reached")
            {
                MutateAndSave(settings, s =>
                {
                    s.DeviceCount = body.DeviceCount ?? 0;
                    s.DeviceLimit = body.DeviceLimit ?? 0;
                });
            }

            Log.Warn($"license rejected: {reason}");
            return new LicenseResult(false, false, reason, message, Definitive: true);
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException)
        {
            Log.Error("license server unreachable", ex);
            return LicenseResult.Failure(
                $"Couldn't reach the license server at {settings.LicenseServerUrl}. " +
                "Check it's running, then try again.");
        }
        catch (Exception ex)
        {
            Log.Error("license validation failed", ex);
            return LicenseResult.Failure($"Validation failed: {ex.Message}");
        }
    }

    /// <summary>Silent re-check at startup. Leaves cached state alone on any error.</summary>
    public async Task RefreshAsync(AppSettings settings)
    {
        if (string.IsNullOrWhiteSpace(settings.LicenseKey) && string.IsNullOrWhiteSpace(settings.LicenseEmail))
            return;

        try
        {
            var result = await ValidateAsync(settings.LicenseKey, settings.LicenseEmail, settings);

            // Trust any definitive answer rather than matching against a list
            // of "bad" statuses. That list was missing incomplete_expired and
            // paused, so those subscriptions kept Pro forever; Stripe can add
            // new statuses at any time, and an allow-list of one ("isPro")
            // cannot fall behind in the same way.
            if (result.Definitive && !result.IsPro && settings.IsPro)
            {
                Log.Warn($"background refresh downgraded license: {result.Status}");
                MutateAndSave(settings, s =>
                {
                    s.IsPro = false;
                    s.LicenseStatus = result.Status;
                });
            }
        }
        catch (Exception ex)
        {
            Log.Warn($"background license refresh skipped: {ex.Message}");
        }
    }

    /// <summary>
    /// Deactivate on this machine, releasing its seat on the server first.
    ///
    /// The release is attempted before the local key is cleared, because once
    /// it is gone we no longer know which licence to free — and a seat that is
    /// never released turns the device limit into a slow lockout for someone
    /// who is still paying.
    /// </summary>
    public async Task DeactivateAsync(AppSettings settings)
    {
        var key = settings.LicenseKey;
        var url = settings.LicenseServerUrl.TrimEnd('/') + "/devices";

        if (!string.IsNullOrWhiteSpace(key))
        {
            try
            {
                using var response = await _http.PostAsJsonAsync(url, new
                {
                    licenseKey = key,
                    action = "release",
                    deviceId = DeviceIdentity.Id,
                });
                Log.Info($"device seat release: HTTP {(int)response.StatusCode}");
            }
            catch (Exception ex)
            {
                // Deactivating locally must still work offline. The seat is
                // recoverable from the website or by support.
                Log.Warn($"could not release the device seat: {ex.Message}");
            }
        }

        MutateAndSave(settings, s =>
        {
            s.IsPro = false;
            s.LicenseKey = "";
            s.LicenseEmail = "";
            s.LicenseStatus = "";
            s.LicenseCheckedUtc = null;
            s.DeviceCount = 0;
            s.DeviceLimit = 0;
        });
        Log.Info("license deactivated locally");
    }

    /// <summary>
    /// Updates the cached device count/limit shown on the licence card
    /// (DeviceText) after a fresh <see cref="ListDevicesAsync"/> or
    /// <see cref="ReleaseDeviceAsync"/> call, through the same
    /// <see cref="MutateAndSave"/> path every other settings mutation uses
    /// (#202) rather than writing the fields directly from the view model.
    /// </summary>
    public void SaveDeviceCounts(AppSettings settings, int deviceCount, int deviceLimit) =>
        MutateAndSave(settings, s =>
        {
            s.DeviceCount = deviceCount;
            s.DeviceLimit = deviceLimit;
        });

    private sealed class DeviceRow
    {
        [JsonPropertyName("name")] public string? Name { get; set; }
        [JsonPropertyName("lastSeen")] public long? LastSeen { get; set; }
        [JsonPropertyName("isCurrent")] public bool IsCurrent { get; set; }
        [JsonPropertyName("deviceToken")] public string? DeviceToken { get; set; }
    }

    private sealed class DevicesResponse
    {
        [JsonPropertyName("ok")] public bool Ok { get; set; }
        [JsonPropertyName("deviceCount")] public int DeviceCount { get; set; }
        [JsonPropertyName("deviceLimit")] public int DeviceLimit { get; set; }
        [JsonPropertyName("devices")] public List<DeviceRow>? Devices { get; set; }
        [JsonPropertyName("message")] public string? Message { get; set; }
    }

    /// <summary>
    /// Roadmap 5.7 — the licence's "Your devices" list. Fetched on demand
    /// only (the Settings card calls this when it's expanded, or on its
    /// Refresh button) — never polled.
    /// </summary>
    public async Task<DeviceListResult> ListDevicesAsync(AppSettings settings)
    {
        var key = settings.LicenseKey;
        if (string.IsNullOrWhiteSpace(key))
            return new DeviceListResult(false, Array.Empty<DeviceInfo>(), 0, 0,
                "No licence key to look up.");

        var url = settings.LicenseServerUrl.TrimEnd('/') + "/devices";
        try
        {
            using var response = await _http.PostAsJsonAsync(url, new
            {
                licenseKey = key,
                deviceId = DeviceIdentity.Id,
            });
            var body = await response.Content.ReadFromJsonAsync<DevicesResponse>();
            if (body is null || !body.Ok)
            {
                return new DeviceListResult(false, Array.Empty<DeviceInfo>(), 0, 0,
                    body?.Message ?? "Couldn't load your devices.");
            }

            var devices = (body.Devices ?? new List<DeviceRow>())
                .Select(d => new DeviceInfo(
                    string.IsNullOrWhiteSpace(d.Name) ? "Unnamed device" : d.Name!,
                    d.DeviceToken ?? "",
                    d.IsCurrent,
                    d.LastSeen is { } seconds
                        ? DateTimeOffset.FromUnixTimeSeconds(seconds).UtcDateTime
                        : null))
                .ToList();

            return new DeviceListResult(true, devices, body.DeviceCount, body.DeviceLimit);
        }
        catch (Exception ex)
        {
            Log.Warn($"could not list devices: {ex.Message}");
            return new DeviceListResult(false, Array.Empty<DeviceInfo>(), 0, 0,
                "Couldn't reach the licence server.");
        }
    }

    /// <summary>
    /// Releases one *other* device's seat by the opaque token its row in
    /// <see cref="ListDevicesAsync"/> carried — never by a raw device id,
    /// which the server does not hand back (Roadmap 5.7). Releasing this
    /// machine's own seat instead goes through <see cref="DeactivateAsync"/>,
    /// which already knows its own id.
    /// </summary>
    public async Task<bool> ReleaseDeviceAsync(AppSettings settings, string deviceToken)
    {
        var key = settings.LicenseKey;
        if (string.IsNullOrWhiteSpace(key) || string.IsNullOrWhiteSpace(deviceToken))
            return false;

        var url = settings.LicenseServerUrl.TrimEnd('/') + "/devices";
        try
        {
            using var response = await _http.PostAsJsonAsync(url, new
            {
                licenseKey = key,
                action = "release",
                releaseToken = deviceToken,
            });
            Log.Info($"device release by token: HTTP {(int)response.StatusCode}");
            return response.IsSuccessStatusCode;
        }
        catch (Exception ex)
        {
            Log.Warn($"could not release device: {ex.Message}");
            return false;
        }
    }
}
