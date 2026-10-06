using Microsoft.Win32;
using FlowShield.Models;

namespace FlowShield.Services;

/// <summary>
/// The copy of the trial's start date that lives outside <c>settings.json</c>,
/// so Delete everything (which removes that file) can't restart the trial.
/// See <see cref="TrialStart"/> for how the two copies are reconciled.
///
/// Per user, in HKCU, so it needs no admin rights, the same as the Run value
/// in <see cref="StartupEntry"/>. It holds one date and nothing else, and it
/// never leaves this PC. Someone who finds and deletes it gets a new trial;
/// for a one-off purchase that is accepted rather than fought.
///
/// The internal FlowShield name stays here, as it does for settings and
/// licences, so a rename never resets anyone's trial.
/// </summary>
public static class TrialRecord
{
    public const string KeyPath = @"Software\FlowShield\Trial";
    public const string ValueName = "StartedUtc";

    public static DateTime? Read()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(KeyPath, writable: false);
            return TrialStart.Parse(key?.GetValue(ValueName) as string);
        }
        catch (Exception ex)
        {
            Log.Warn($"trial record unreadable: {ex.Message}");
            return null;
        }
    }

    /// <summary>Best effort: a failure leaves the trial date in settings only, as before.</summary>
    public static void Write(DateTime startUtc)
    {
        try
        {
            using var key = Registry.CurrentUser.CreateSubKey(KeyPath, writable: true);
            key.SetValue(ValueName, TrialStart.Format(startUtc), RegistryValueKind.String);
        }
        catch (Exception ex)
        {
            Log.Warn($"could not write the trial record: {ex.Message}");
        }
    }
}
