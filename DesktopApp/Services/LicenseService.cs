using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using FlowShield.Models;

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

    public LicenseService(SettingsService settings, HttpClient? http = null)
    {
        _settings = settings;
        _http = http ?? new HttpClient { Timeout = TimeSpan.FromSeconds(20) };
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
    }

    /// <summary>
    /// Validates against the server and, on success, writes the Pro flag into
    /// settings. A network failure never downgrades an already-Pro install —
    /// the user paid, and a flaky connection is not grounds for revocation.
    /// </summary>
    public async Task<LicenseResult> ValidateAsync(string licenseKey, string email, AppSettings settings)
    {
        var key = (licenseKey ?? "").Trim();
        var mail = (email ?? "").Trim();

        if (key.Length == 0 && mail.Length == 0)
            return LicenseResult.Failure("Enter your license key (or the email you used at checkout).");

        var url = settings.LicenseServerUrl.TrimEnd('/') + "/validate";

        try
        {
            Log.Info($"validating license against {url}");
            using var response = await _http.PostAsJsonAsync(url, new { licenseKey = key, email = mail });

            var body = await response.Content.ReadFromJsonAsync<ValidateResponse>();
            if (body is null)
                return LicenseResult.Failure("The license server returned an unreadable response.");

            // Anything from here on is the server's verdict, and is definitive.

            if (body.IsPro)
            {
                settings.IsPro = true;
                settings.LicenseKey = body.LicenseKey ?? key;
                settings.LicenseEmail = body.Email ?? mail;
                settings.LicenseStatus = body.Status ?? "active";
                settings.LicenseCheckedUtc = DateTime.UtcNow;
                _settings.Save(settings);

                Log.Info($"license activated: status={settings.LicenseStatus}");
                return new LicenseResult(true, true, settings.LicenseStatus,
                    "Pro unlocked. Every shield level is now available.",
                    settings.LicenseEmail, settings.LicenseKey);
            }

            var reason = body.Reason ?? "invalid";
            var message = body.Message ?? reason switch
            {
                "malformed_key" => "That key isn't in the FS-XXXX-XXXX-XXXX-XXXX format.",
                "not_found" => "We couldn't find a subscription for those details.",
                _ when reason.StartsWith("subscription_") =>
                    $"That subscription is {reason["subscription_".Length..]}.",
                _ => "That license could not be validated.",
            };

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
                settings.IsPro = false;
                settings.LicenseStatus = result.Status;
                _settings.Save(settings);
            }
        }
        catch (Exception ex)
        {
            Log.Warn($"background license refresh skipped: {ex.Message}");
        }
    }

    public void Deactivate(AppSettings settings)
    {
        settings.IsPro = false;
        settings.LicenseKey = "";
        settings.LicenseEmail = "";
        settings.LicenseStatus = "";
        settings.LicenseCheckedUtc = null;
        _settings.Save(settings);
        Log.Info("license deactivated locally");
    }
}
