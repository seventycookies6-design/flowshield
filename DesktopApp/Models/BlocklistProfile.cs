using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json.Serialization;

namespace FlowShield.Models;

/// <summary>
/// A named blocklist (F9, roadmap 3.8).
///
/// Deliberately nothing more than a name and a list: a homework blocklist and
/// an exam blocklist differ in what is on them, not in a web of per-profile
/// rules. Time windows, nested rules and per-rule shields are what reviewers
/// call too complex, so a profile has none of them.
///
/// Implements INotifyPropertyChanged because a rename has to show up on the
/// switcher chip and in Today's caption while both are on screen.
/// </summary>
public class BlocklistProfile : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;

    private void Raise([CallerMemberName] string? name = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

    /// <summary>
    /// Stable identity, so renaming a profile never breaks what points at it —
    /// the active profile, a running sprint's record, and the templates F6 will
    /// attach to one.
    /// </summary>
    public string Id { get; set; } = NewId();

    private string _name = AppSettings.DefaultProfileName;
    public string Name
    {
        get => _name;
        set
        {
            if (_name == value) return;
            _name = value;
            Raise();
        }
    }

    public List<BlockedApp> Apps { get; set; } = new();

    private List<string> _sites = new();

    /// <summary>
    /// Websites on this list, as normalised hosts ("youtube.com"). Basalt
    /// cannot block them without a browser extension (F10, after launch), so
    /// during a sprint it shows its notice when a browser's title names one
    /// (<see cref="WebsiteTitleMatch"/>). Never null: an older settings file
    /// has no list, and a hand-edited one may say null.
    /// </summary>
    public List<string> Sites
    {
        get => _sites;
        set => _sites = value ?? new List<string>();
    }

    private bool _isActive;

    /// <summary>
    /// Whether this is the profile a sprint would use. Display only — the stored
    /// answer is <see cref="AppSettings.ActiveProfileId"/> — and it is what the
    /// switcher chips on Blocked Apps and Today bind their checked state to.
    /// </summary>
    [JsonIgnore]
    public bool IsActive
    {
        get => _isActive;
        set
        {
            if (_isActive == value) return;
            _isActive = value;
            Raise();
        }
    }

    [JsonIgnore]
    public string AppCountText => $"{Apps.Count} app{(Apps.Count == 1 ? "" : "s")}";

    public static string NewId() => Guid.NewGuid().ToString("N");

    /// <summary>A separate profile with the same apps, used by Duplicate.</summary>
    public BlocklistProfile Copy(string name) => new()
    {
        Id = NewId(),
        Name = name,
        Apps = Apps.Select(a => a.Copy()).ToList(),
        Sites = Sites.ToList(),
    };
}
