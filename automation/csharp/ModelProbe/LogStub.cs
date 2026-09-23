namespace FlowShield.Services;

/// <summary>
/// The probe compiles DesktopApp/Models alone. One model (AppPicker) logs a
/// failure through Services.Log; this silent stand-in lets it build.
/// </summary>
internal static class Log
{
    public static void Info(string message) { }
    public static void Warn(string message) { }
    public static void Error(string message) { }
    public static void Error(string message, Exception ex) { }
}
