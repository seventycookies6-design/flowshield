using System.Text.RegularExpressions;

namespace FlowShield.Models;

/// <summary>
/// The website notice (launch checklist F10, the interim before the browser
/// extension): which blocked website, if any, a browser window's title names.
///
/// FlowShield cannot see inside a browser without an extension, and the timid
/// blocker rules out the hosts file and DNS. What it can read is the title of
/// the window in front, which browsers build from the page's own title and
/// their name: "Lofi beats - YouTube - Google Chrome". So this matches a site
/// by its name in that title. It is approximate on purpose and says so: a
/// search for "youtube tutorial" names YouTube too, and a page whose title
/// never says where it is will not be seen. A wrong guess costs one calm
/// notice, never a closed window: the notice is the whole intervention.
///
/// Kept free of Win32 so the matching can be tested on its own (tier 1).
/// </summary>
public static class WebsiteTitleMatch
{
    /// <summary>
    /// Browsers whose window titles are read, by process name. Anything else is
    /// never looked at: a document called "Reddit notes" in Word is not Reddit.
    /// </summary>
    public static readonly IReadOnlySet<string> Browsers = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
    {
        "chrome", "msedge", "firefox", "brave", "opera", "vivaldi", "chromium",
        "arc", "librewolf", "waterfox", "floorp", "zen", "thorium", "yandex",
    };

    /// <summary>How many sites one profile may hold. Plenty for a blocklist; keeps a sweep cheap.</summary>
    public const int MaxSites = 50;

    /// <summary>
    /// A browser's own name at the end of its window title, which is not part
    /// of the page. Stripped first so that blocking google.com does not match
    /// every "- Google Chrome" window.
    /// </summary>
    private static readonly Regex BrowserSuffix = new(
        @"\s+[-–—]\s+(Google Chrome|Microsoft Edge|Mozilla Firefox( Private Browsing)?|Firefox|"
        + @"Brave|Opera|Vivaldi|Chromium|Arc|LibreWolf|Waterfox|Floorp|Zen Browser|Thorium|Yandex Browser)\s*$",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly Regex HostShape = new(
        @"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$",
        RegexOptions.CultureInvariant);

    /// <summary>
    /// Second-level labels that sit under a country code, so bbc.co.uk is
    /// "bbc" and not "co".
    /// </summary>
    private static readonly HashSet<string> SecondLevel = new(StringComparer.OrdinalIgnoreCase)
    {
        "co", "com", "org", "net", "ac", "gov", "edu",
    };

    /// <summary>
    /// What the customer typed, as the site it means: "https://www.YouTube.com/watch?v=1"
    /// is "youtube.com". Null when it is not a website at all, so the page can
    /// say so instead of storing something that will never match.
    /// </summary>
    public static string? Normalize(string? input)
    {
        var s = (input ?? "").Trim().ToLowerInvariant();
        var scheme = s.IndexOf("://", StringComparison.Ordinal);
        if (scheme >= 0) s = s[(scheme + 3)..];

        var end = s.IndexOfAny(new[] { '/', '?', '#' });
        if (end >= 0) s = s[..end];

        var at = s.LastIndexOf('@');
        if (at >= 0) s = s[(at + 1)..];

        var port = s.IndexOf(':');
        if (port >= 0) s = s[..port];

        s = s.Trim('.');
        if (s.StartsWith("www.", StringComparison.Ordinal)) s = s[4..];

        return s.Length is > 0 and <= 253 && HostShape.IsMatch(s) ? s : null;
    }

    /// <summary>
    /// The name a site goes by in a title: youtube.com is "youtube",
    /// music.youtube.com is "youtube", bbc.co.uk is "bbc". A bare word is itself.
    /// </summary>
    public static string Keyword(string host)
    {
        var labels = host.Split('.');
        if (labels.Length == 1) return host;

        var take = labels.Length - 1;   // drop the top-level domain
        if (labels.Length >= 3 && labels[^1].Length == 2 && SecondLevel.Contains(labels[^2]))
            take--;                     // and the "co" of co.uk
        return labels[take - 1];
    }

    /// <summary>
    /// The blocked site a browser window's title names, as its normalised host,
    /// or null. Null for every process that is not a browser.
    ///
    /// A site matches when the title contains its whole host ("x.com"), or its
    /// name as a whole word ("YouTube", not "youtuber"). Names under three
    /// letters only match by host: "x" as a word is in far too many titles.
    /// </summary>
    public static string? Match(string? processName, string? windowTitle, IEnumerable<string> sites)
    {
        if (string.IsNullOrEmpty(processName) || !Browsers.Contains(processName)) return null;

        var title = PageTitle(windowTitle);
        if (title.Length == 0) return null;

        foreach (var site in sites)
        {
            var host = Normalize(site);
            if (host is null) continue;

            if (title.Contains(host, StringComparison.OrdinalIgnoreCase)) return host;

            var keyword = Keyword(host);
            if (keyword.Length < 3) continue;
            if (Regex.IsMatch(title,
                    $@"(?<![\p{{L}}\p{{N}}]){Regex.Escape(keyword)}(?![\p{{L}}\p{{N}}])",
                    RegexOptions.IgnoreCase | RegexOptions.CultureInvariant))
                return host;
        }
        return null;
    }

    /// <summary>
    /// The page's part of a window title: zero-width spaces removed (Edge puts
    /// one inside "Microsoft Edge") and the browser's own name taken off the end.
    /// </summary>
    public static string PageTitle(string? windowTitle)
    {
        var title = (windowTitle ?? "").Replace("​", "").Trim();
        return BrowserSuffix.Replace(title, "").Trim();
    }
}
