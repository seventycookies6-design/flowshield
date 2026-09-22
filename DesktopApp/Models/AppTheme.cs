namespace FlowShield.Models;

/// <summary>
/// Which colour theme FlowShield draws in (F21, DESIGN_SYSTEM.md §12).
///
/// Persisted in <see cref="AppSettings.Theme"/> as its numeric value, so
/// <see cref="System"/> has to stay 0: that keeps every settings file written
/// before F21 on the default, following Windows, rather than reading as Dark.
/// </summary>
public enum AppTheme
{
    /// <summary>Follow Windows' own app theme, and change with it. The default.</summary>
    System = 0,

    /// <summary>Always dark, whatever Windows is set to.</summary>
    Dark = 1,

    /// <summary>Always light, whatever Windows is set to.</summary>
    Light = 2,
}
