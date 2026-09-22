using System.Collections.ObjectModel;
using FlowShield.Infrastructure;
using FlowShield.Models;

namespace FlowShield.ViewModels;

/// <summary>
/// One day of the focus heatmap, as the grid binds it (F16).
///
/// <see cref="Name"/> is what a screen reader reads out and what the tooltip
/// shows, because DESIGN_SYSTEM.md §7 says a heatmap must never rely on colour
/// alone: every cell states its own value.
/// </summary>
public class HeatCell
{
    public HeatCell(HistoryStats.Cell cell)
    {
        Step = cell.Step;
        Name = $"{cell.Day:ddd d MMM}: "
            + (cell.Minutes == 1 ? "1 focus minute" : $"{cell.Minutes} focus minutes");
    }

    public int Step { get; }
    public string Name { get; }
}

/// <summary>One sprint in the History list (F16, and F17's journal read-back).</summary>
public class HistoryRow
{
    public HistoryRow(FocusSession session)
    {
        var started = session.StartedUtc.ToLocalTime();
        Shield = session.Shield;

        WhenText = $"{started:ddd d MMM} · {started:HH:mm}";

        // Planned as well as actual, so "25 min planned, 12 min run" is visible
        // rather than looking like a sprint that was always meant to be short.
        var actual = (int)Math.Round(session.ActualMinutes);
        LengthText = actual == session.PlannedMinutes
            ? $"{actual} min"
            : $"{actual} of {session.PlannedMinutes} min";

        // JournalExport already names the outcomes, for the CSV and the Markdown
        // export. One spelling, in one place (§9's "ended early", never "failed").
        OutcomeText = JournalExport.Outcome(session);
        ShieldText = JournalExport.ShieldName(session.Shield);

        IntentionText = string.IsNullOrWhiteSpace(session.Intention)
            ? "" : $"Planned: {session.Intention.Trim()}";
        JournalText = (session.Journal ?? "").Trim();

        AccessibleName =
            $"{WhenText}, {LengthText}, {ShieldText}, {OutcomeText}";
    }

    public ShieldLevel Shield { get; }
    public string WhenText { get; }
    public string LengthText { get; }
    public string ShieldText { get; }
    public string OutcomeText { get; }
    public string IntentionText { get; }
    public string JournalText { get; }
    public string AccessibleName { get; }
}

/// <summary>
/// The History page (launch checklist F16, roadmap 3.1 and 3.6): this week's
/// figures, a 30-day heatmap of focus minutes, and every sprint with its
/// intention and journal line — which is also F17's promised read-back.
///
/// It only ever reads. Every number comes from <see cref="AppSettings.Sessions"/>
/// through the pure <see cref="HistoryStats"/>, and nothing on this page writes
/// settings or sends anything anywhere: the page is a view of what FlowShield
/// already stored on this PC.
/// </summary>
public class HistoryViewModel : ViewModelBase
{
    private readonly MainViewModel _main;

    public HistoryViewModel(MainViewModel main)
    {
        _main = main;
        ExportJournalCommand = new RelayCommand(() =>
        {
            // The export card itself lives on Settings, where its date range
            // belongs with the rest of the preferences; History is where you
            // realise you want it. Navigating keeps one export UI and every
            // AutomationId F17 shipped.
            _main.CurrentPage = AppPage.Settings;
        });
        Refresh();
    }

    private AppSettings S => _main.Settings;

    /// <summary>Settings → Export your journal, reached from here (F17).</summary>
    public RelayCommand ExportJournalCommand { get; }

    // ------------------------------------------------------------- this week

    private string _weekRangeText = "";
    public string WeekRangeText { get => _weekRangeText; private set => Set(ref _weekRangeText, value); }

    private string _weekFocusText = "0.0";
    public string WeekFocusText { get => _weekFocusText; private set => Set(ref _weekFocusText, value); }

    private string _weekSprintsText = "0";
    public string WeekSprintsText { get => _weekSprintsText; private set => Set(ref _weekSprintsText, value); }

    private string _weekDistractionsText = "0";
    public string WeekDistractionsText
    {
        get => _weekDistractionsText;
        private set => Set(ref _weekDistractionsText, value);
    }

    private string _mostBlockedText = "";
    public string MostBlockedText { get => _mostBlockedText; private set => Set(ref _mostBlockedText, value); }

    /// <summary>
    /// Says out loud that the most-blocked app is the whole time you have been
    /// blocking, not this week — the per-app count is the only figure on this
    /// page that is not derived from the week's sprints, and a stat card that
    /// quietly mixed scopes would be a small lie.
    /// </summary>
    public string MostBlockedNoteText => MostBlockedText.Length == 0
        ? "Nothing has needed blocking yet."
        : "All the time you have been blocking, not just this week.";

    // --------------------------------------------------------------- heatmap

    public ObservableCollection<HeatCell> Heatmap { get; } = new();

    private string _heatmapRangeText = "";
    public string HeatmapRangeText
    {
        get => _heatmapRangeText;
        private set => Set(ref _heatmapRangeText, value);
    }

    private string _heatmapPeakText = "";
    public string HeatmapPeakText { get => _heatmapPeakText; private set => Set(ref _heatmapPeakText, value); }

    /// <summary>The whole chart in one sentence, for a screen reader.</summary>
    private string _heatmapDescription = "";
    public string HeatmapDescription
    {
        get => _heatmapDescription;
        private set => Set(ref _heatmapDescription, value);
    }

    /// <summary>The legend's five swatches, lightest to darkest (§7).</summary>
    public IReadOnlyList<int> LegendSteps { get; } =
        Enumerable.Range(0, HistoryStats.Steps).ToList();

    // ---------------------------------------------------------- sprint list

    public ObservableCollection<HistoryRow> Rows { get; } = new();

    private bool _hasRows;
    public bool HasRows { get => _hasRows; private set => Set(ref _hasRows, value); }

    public bool HasNoRows => !HasRows;

    /// <summary>Held for F14's milestones (#133), which are listed here once they exist.</summary>
    public string MilestonesPlaceholderText =>
        "Milestones will be listed here once they land — a first Sealed sprint, "
        + "ten hours focused, a week of hitting your goal.";

    // -------------------------------------------------------------- refresh

    /// <summary>Recomputes the page. Called every time History is navigated to.</summary>
    public void Refresh()
    {
        var now = DateTime.Now;
        var week = HistoryStats.ForWeek(S.Sessions, now);

        WeekRangeText = $"{week.Start:d MMM} – {week.End:d MMM}";
        WeekFocusText = (week.FocusMinutes / 60).ToString("0.0");
        WeekSprintsText = week.SprintsCompleted.ToString("0");
        WeekDistractionsText = week.Distractions.ToString("0");
        // Every profile, not only the active one: "all the time you have been
        // blocking" would otherwise change its answer when a profile is
        // switched, which is the scope-mixing the note below warns against.
        MostBlockedText = HistoryStats.MostBlocked(S.Profiles.SelectMany(p => p.Apps));
        Raise(nameof(MostBlockedNoteText));

        var cells = HistoryStats.Heatmap(S.Sessions, now);
        Heatmap.Clear();
        foreach (var cell in cells) Heatmap.Add(new HeatCell(cell));

        var peak = cells.Count == 0 ? 0 : cells.Max(c => c.Minutes);
        HeatmapRangeText = cells.Count == 0
            ? ""
            : $"{cells[0].Day:d MMM} – {cells[^1].Day:d MMM}";
        HeatmapPeakText = $"best day {peak} min";
        HeatmapDescription =
            $"Focus minutes over the last {cells.Count} days, "
            + $"{HeatmapRangeText}. The busiest day was {peak} minutes. "
            + "Each square gives its own day and minutes.";

        Rows.Clear();
        foreach (var session in S.Sessions.OrderByDescending(s => s.StartedUtc))
            Rows.Add(new HistoryRow(session));

        HasRows = Rows.Count > 0;
        Raise(nameof(HasNoRows));
    }
}
