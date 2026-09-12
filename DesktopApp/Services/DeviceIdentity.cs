using System.Security.Cryptography;
using System.Text;
using Microsoft.Win32;

namespace FlowShield.Services;

/// <summary>
/// A stable, anonymous identifier for this machine, used to enforce the
/// per-licence device limit.
///
/// What leaves the machine is a salted SHA-256 hash, never the underlying
/// values. The licence server only needs to answer "is this the same machine
/// as last time?", and a hash answers that without telling it anything about
/// the hardware or who is sitting at it.
///
/// Inputs are the Windows MachineGuid and the user name, so two accounts on a
/// shared PC count as two devices — which matches how the licence is actually
/// being used.
/// </summary>
public static class DeviceIdentity
{
    /// <summary>
    /// Fixed salt. Not a secret — it exists so the hash is specific to
    /// FlowShield and cannot be compared against an identifier produced by
    /// some other application from the same MachineGuid.
    /// </summary>
    private const string Salt = "FlowShield.device.v1";

    private static string? _cached;

    /// <summary>A 32-character hex identifier, stable across restarts and updates.</summary>
    public static string Id => _cached ??= Compute();

    /// <summary>A human-readable name so the customer can tell their seats apart.</summary>
    public static string Name
    {
        get
        {
            try
            {
                return $"{Environment.MachineName} ({Environment.UserName})";
            }
            catch
            {
                return "Windows PC";
            }
        }
    }

    private static string Compute()
    {
        var parts = new List<string> { Salt };

        try
        {
            using var key = Registry.LocalMachine.OpenSubKey(
                @"SOFTWARE\Microsoft\Cryptography", writable: false);
            var guid = key?.GetValue("MachineGuid") as string;
            if (!string.IsNullOrWhiteSpace(guid)) parts.Add(guid);
        }
        catch (Exception ex)
        {
            Log.Warn($"MachineGuid unavailable: {ex.Message}");
        }

        try
        {
            parts.Add(Environment.MachineName);
            parts.Add(Environment.UserName);
        }
        catch
        {
            // Fall through — the salt alone still yields a usable constant.
        }

        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(string.Join("|", parts)));

        // 128 bits is far more than enough to distinguish machines and keeps
        // the value short enough to display in a support conversation.
        return Convert.ToHexString(bytes, 0, 16).ToLowerInvariant();
    }
}
