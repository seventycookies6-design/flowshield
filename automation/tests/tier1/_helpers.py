# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 1:  helpers."""

from __future__ import annotations
import json
import re
import subprocess
from datetime import date, timedelta
from datetime import date
from pathlib import Path
from config import SERVER_DIR


NODE = r"C:\Program Files\nodejs\node.exe"
NODE_EXE = NODE if Path(NODE).exists() else "node"


def node_eval(script: str) -> dict:
    """Run a snippet inside the server package and parse its JSON output."""
    result = subprocess.run(
        [NODE_EXE, "-e", script],
        cwd=str(SERVER_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError(f"node failed: {result.stderr[:500]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


# ============================================================ sleep window

def within_sleep_window(now_minutes: int, start: int, end: int) -> bool:
    """Mirror of AppBlockerService.IsWithinSleepWindow (minutes since midnight)."""
    if start <= end:
        return start <= now_minutes < end
    return now_minutes >= start or now_minutes < end


# ======================================================== time parsing rule

def parse_time(text: str) -> tuple[int, int] | None:
    """Mirror of SleepBlockingViewModel.TryParse for the formats it accepts."""
    import re

    text = (text or "").strip().lower()
    if not text:
        return None

    match = re.fullmatch(r"(\d{1,2}):(\d{2})\s*(am|pm)?", text)
    if not match:
        match = re.fullmatch(r"(\d{2})(\d{2})", text)
        if match:
            hour, minute, meridiem = int(match.group(1)), int(match.group(2)), None
            return (hour, minute) if hour < 24 and minute < 60 else None
        match = re.fullmatch(r"(\d{1,2})\s*(am|pm)", text)
        if not match:
            return None
        hour, minute, meridiem = int(match.group(1)), 0, match.group(2)
    else:
        hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3)

    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return (hour, minute) if hour < 24 and minute < 60 else None


# =================================================== blocked-app normalising

def normalize_process_name(value: str) -> str:
    """Mirror of BlockedAppsViewModel.NormalizeProcessName."""
    text = (value or "").strip().strip('"')
    if "\\" in text or "/" in text:
        text = text.replace("/", "\\").split("\\")[-1]
    if text.lower().endswith(".exe"):
        text = text[:-4]
    return text.strip()


# ============================================================== free trial

TRIAL_DAYS = 7


def trial_active(start_days_ago: float | None, *, now_days: float = 0.0) -> bool:
    """Mirror of AppSettings.IsTrialActiveAt, in days relative to now."""
    if start_days_ago is None:
        return False
    start = now_days - start_days_ago
    return now_days >= start - 1 and now_days < start + TRIAL_DAYS


def trial_days_left(start_days_ago: float) -> int:
    """Mirror of AppSettings.TrialDaysLeftAt."""
    import math
    if not trial_active(start_days_ago):
        return 0
    return min(max(math.ceil(TRIAL_DAYS - start_days_ago), 1), TRIAL_DAYS)


# ==================================== a trial that never nags (F20, #9) =====

def maybe_notify_trial_ending(*, is_trial: bool, trial_days_left: int,
                               last_notified_date: date | None, today: date,
                               sprint_running: bool = False) -> tuple[bool, date | None]:
    """
    Mirror of MainViewModel.MaybeNotifyTrialEnding, folding in the sprint guard
    that Notify() applies through NotificationPolicy.ShouldShow. Returns
    (shown, the new value of TrialEndingNotifiedLocal).
    """
    if not is_trial or trial_days_left > 1:
        return False, last_notified_date
    if last_notified_date == today:
        return False, last_notified_date
    if sprint_running:
        # Suppressed by the sprint guard. Crucially, this must NOT be recorded
        # as sent — the whole point is that it is still owed afterwards.
        return False, last_notified_date
    return True, today


# ================================================================== momentum

def apply_momentum(score: float, completed: bool, planned_minutes: int) -> float:
    """Mirror of TodayViewModel.ApplyMomentum."""
    if completed:
        weight = min(max(planned_minutes / 25.0, 0.5), 3.0)
        return round(score + 10 * weight, 1)
    return round(max(0.0, score * 0.85 - 2), 1)


# ===================================================== sprints survive restarts

def resume_decision(started_min_ago: float, planned: int, last_seen_min_ago: float,
                    watched_minutes: float | None = None) -> str:
    """
    Mirror of RunningSprint.Decide, in minutes relative to now.

    watched_minutes is the accumulated WatchedMinutes; None stands for a
    settings file written before that field existed, where Decide falls back to
    the LastSeenUtc-minus-StartedUtc estimate.
    """
    if planned <= 0:
        return "Discard"
    started = -started_min_ago
    ends = started + planned
    if 0 < ends:
        return "Resume"
    watched = watched_minutes if watched_minutes is not None else min(-last_seen_min_ago, ends) - started
    return "RecordCompleted" if watched >= planned * 0.5 else "RecordInterrupted"


def watched_so_far(planned: float, started: float, last_seen: float,
                   ends: float, watched: float | None) -> float:
    """Mirror of RunningSprint.WatchedSoFar, with timestamps on one timeline."""
    estimate = watched if watched is not None else (min(last_seen, ends) - started)
    return max(0, min(planned, estimate))


def recorded_end(started: float, planned_end: float, watched: float, now: float,
                 completed: bool, interrupted: bool) -> float:
    """
    Mirror of RunningSprint.RecordedEnd, in minutes on one timeline: when a
    sprint that has just ended is recorded as ending, which is all
    FocusSession.ActualMinutes measures.
    """
    if interrupted:
        return started + watched
    return min(now, planned_end)


# ============================================== ending a sprint early (F2)

GRACE_SECONDS = 120


def end_flow(shield: str, elapsed_seconds: float) -> str:
    """Mirror of EndSprintPolicy.FlowFor with the real timers."""
    if elapsed_seconds < GRACE_SECONDS:
        return "Cancel"
    return {"Soft": "Immediate", "Firm": "Confirm"}.get(shield, "Sealed")


def momentum_after_ending(score: float, shield: str) -> float:
    """Mirror of EndSprintPolicy.MomentumAfterEndingEarly."""
    if shield == "Sealed":
        return round(max(0.0, score * 0.7 - 5), 1)
    return round(max(0.0, score * 0.85 - 2), 1)


def phrase_matches(typed: str) -> bool:
    """Mirror of EndSprintPolicy.PhraseMatches."""
    return " ".join((typed or "").split()).lower() == "end my sprint"


def notification_allowed(kind: str, *, master=True, kind_on=True, sprint_running=False) -> bool:
    """Mirror of NotificationPolicy.ShouldShow."""
    interrupts_focus = {"TrialEnding"}
    return master and kind_on and not (sprint_running and kind in interrupts_focus)


def picker_filter(entries: list[dict], query: str) -> list[str]:
    """Mirror of AppPicker.Filter: name-prefix first, then suggested, installed, running."""
    q = query.strip()
    if q.lower().endswith(".exe"):
        q = q[:-4]
    order = {"Suggested": 0, "Installed": 1, "Running": 2}
    ql = q.lower()
    matches = [e for e in entries if not q
               or ql in e["name"].lower() or any(ql in p.lower() for p in e["processes"])]
    matches.sort(key=lambda e: (0 if q and e["name"].lower().startswith(ql) else 1,
                                order[e["source"]],
                                "" if e["source"] == "Suggested" else e["name"].lower()))
    return [e["name"] for e in matches]


def first_run_shows(*, completed=False, blocked=0, sessions=0, active=False,
                    has_access=True, running=False, skip_flag=False) -> bool:
    """Mirror of FirstRunPolicy.ShouldShow."""
    existing = blocked > 0 or sessions > 0 or active
    return not skip_flag and not completed and not existing and has_access and not running


def terms_accepted(recorded: str, current: str) -> bool:
    """Mirror of LegalTerms.Accepted: an exact version match, nothing looser."""
    return recorded == current


def activation_key(link: str) -> str | None:
    """Mirror of DeepLink.ParseActivationKey."""
    import re
    from urllib.parse import unquote, urlsplit

    try:
        parts = urlsplit(link.strip())
    except ValueError:
        return None
    if parts.scheme.lower() != "flowshield":
        return None
    if (parts.netloc + parts.path).strip("/").lower() != "activate":
        return None
    key = None
    for pair in filter(None, parts.query.split("&")):
        name, _, value = pair.partition("=")
        if _ and name.lower() == "key":
            key = unquote(value).strip().upper()
    shape = r"^FS-(?:[0-9A-HJKMNP-TV-Z]{4}-){3}[0-9A-HJKMNP-TV-Z]{4}$"
    return key if key and re.match(shape, key) else None


# ================= Roadmap 5.2 — honest waiting while the licence server wakes

def wait_message_for(elapsed_seconds: float) -> str:
    """Mirror of LicenseWaitCopy.MessageFor."""
    waking_up_after = 8.0
    if elapsed_seconds < waking_up_after:
        return "Contacting the license server…"
    return "The server is waking up. This can take up to a minute."


def timeout_for_attempt(attempt: int) -> float:
    """Mirror of LicenseWaitCopy.TimeoutForAttempt."""
    first, retry = 35.0, 15.0
    return first if attempt <= 1 else retry


# ============================================= sprint summary card (F12)

def summary_title(completed: bool, start_momentum: float, end_momentum: float) -> str:
    """Mirror of TodayViewModel.UpdateSummaryCard's title rule."""
    if completed:
        return "Sprint complete"
    delta = round(end_momentum - start_momentum)
    if delta < 0:
        return f"Ended early — momentum −{abs(delta)}. It'll recover."
    return "Ended early. It'll recover."


def distraction_summary(closed: int, nudged: int, total: int) -> str:
    """Mirror of TodayViewModel.DistractionSummary."""
    if closed or nudged:
        nudges = "1 nudge" if nudged == 1 else f"{nudged} nudges"
        return f"{closed} closed · {nudges}"
    if total:
        word = "1 distraction" if total == 1 else f"{total} distractions"
        return f"{word} caught"
    return "No distractions caught"


# ================================================== sprint intention (F13)

def journal_prompt_title(intention: str | None) -> str:
    """Mirror of TodayViewModel.JournalPromptTitle."""
    if intention is None or not intention.strip():
        return "What moved?"
    return f"You planned: {intention.strip()}. What moved?"


# ============================================ custom sprint lengths (roadmap 2.3)

CUSTOM_MIN = 5
CUSTOM_MAX = 240


def custom_minutes_valid(value: int) -> bool:
    """Mirror of TodayViewModel.IsCustomMinutesValid."""
    return CUSTOM_MIN <= value <= CUSTOM_MAX


# ============================================================ daily goal (F15)

GOAL_NONE, GOAL_MINUTES, GOAL_SPRINTS = 0, 1, 2

SKIPS_PER_WEEK = 1
SKIP_WINDOW_DAYS = 7


class Goal:
    """
    Mirror of DesktopApp/Models/DailyGoal.cs.

    Days are plain date objects; sessions are (date, minutes, completed).
    """

    def __init__(self, kind=GOAL_NONE, target=0, sessions=None, skips=None,
                 streak=0, settled=None, met_day=None):
        self.kind = kind
        self.target = target
        self.sessions = sessions or []
        self.skips = set(skips or [])
        self.streak = streak
        self.settled = settled
        self.met_day = met_day

    # ---- rules

    def is_set(self) -> bool:
        return self.kind != GOAL_NONE and self.target > 0

    def progress_on(self, day):
        if not self.is_set():
            return (0, 0)
        todays = [s for s in self.sessions if s[0] == day]
        if self.kind == GOAL_MINUTES:
            done = round(sum(s[1] for s in todays))
        else:
            done = sum(1 for s in todays if s[2])
        return (done, self.target)

    def met_on(self, day) -> bool:
        if not self.is_set():
            return False
        done, target = self.progress_on(day)
        return done >= target

    def had_completed_sprint_on(self, day) -> bool:
        return any(s[0] == day and s[2] for s in self.sessions)

    def is_skipped(self, day) -> bool:
        return day in self.skips

    def skips_used_in_window(self, day) -> int:
        start = day - timedelta(days=SKIP_WINDOW_DAYS - 1)
        return sum(1 for d in self.skips if start <= d <= day)

    def can_skip(self, day) -> bool:
        return (self.is_set() and not self.is_skipped(day)
                and self.skips_used_in_window(day) < SKIPS_PER_WEEK)

    def judge(self, day) -> str:
        if self.is_skipped(day):
            return "skipped"
        counted = self.met_on(day) if self.is_set() else self.had_completed_sprint_on(day)
        return "counted" if counted else "missed"

    def count_day_if_newly_counted(self, day) -> bool:
        """Mirror of DailyGoal.CountDayIfNewlyCounted: once per day, ever."""
        if self.met_day == day:
            return False
        if self.judge(day) != "counted":
            return False
        self.met_day = day
        self.streak += 1
        return True

    def settle(self, today):
        if self.settled is None:
            self.settled = today
            self.count_day_if_newly_counted(today)
            return
        if today <= self.settled:
            if today == self.settled:
                self.count_day_if_newly_counted(today)
            return

        day = self.settled + timedelta(days=1)
        while day <= today:
            verdict = self.judge(day)
            if day == today:
                self.count_day_if_newly_counted(today)
                break
            if verdict == "counted":
                self.streak += 1
            elif verdict == "missed":
                self.streak = 0
            day += timedelta(days=1)
        self.settled = today

    def note_progress(self, today) -> bool:
        """Mirror of DailyGoal.NoteProgress."""
        met_before = self.met_day
        self.settle(today)
        return met_before != today and self.met_day == today


DAY = date(2026, 9, 18)


# ======================================================= journal export (F17)

def defuse(value: str) -> str:
    """Mirror of JournalExport.Defuse."""
    if not value:
        return value
    return "'" + value if value[0] in "=+-@\t\r" else value


def escape_csv(value: str) -> str:
    """Mirror of JournalExport.EscapeCsv."""
    text = defuse(value or "")
    if not any(c in text for c in ',"\r\n'):
        return text
    return '"' + text.replace('"', '""') + '"'


def escape_markdown(value: str) -> str:
    """Mirror of JournalExport.EscapeMarkdown."""
    text = (value or "").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return text
    return "\\" + text if text[0] in "#-*>+|`" else text


def suggested_name(start: date, end: date, fmt: str) -> str:
    """Mirror of JournalExport.SuggestedFileName."""
    if end < start:
        start, end = end, start
    ext = "csv" if fmt == "csv" else "md"
    return f"Basalt journal {start:%Y-%m-%d} to {end:%Y-%m-%d}.{ext}"

# ==================== when the Soft notice appears (F7 / roadmap 1.7)

class SoftOverlayPolicy:
    """
    Python mirror of Models/SoftOverlayPolicy.cs.

    Times are plain seconds here; the C# version takes UTC instants. Only the
    two rules matter: once per sighting, and a per-app quiet window. 1.0.10
    adds two counters, tries and turned back, which the probe tests in
    test_tier1_models.py run against the real C#.
    """

    ALLOW_WINDOW = 5 * 60
    BACK_TO_WORK_QUIET = 5

    def __init__(self):
        self.quiet_until: dict[str, float] = {}
        self.sighting: str | None = None
        self.showing = False
        self.tries = 0
        self.turned_back = 0

    def should_show(self, app: str, now: float) -> bool:
        is_new = self.sighting is None or self.sighting.lower() != app.lower()
        self.sighting = app
        if not is_new:
            return False
        if self.is_quiet(app, now):
            return False
        self.showing = True
        self.tries += 1
        return True

    def left_the_foreground(self) -> bool:
        self.sighting = None
        was_showing = self.showing
        self.showing = False
        return was_showing

    def allow_five_minutes(self, app: str, now: float) -> None:
        self._quieten(app, now, self.ALLOW_WINDOW)

    def back_to_work(self, app: str, now: float) -> None:
        self.turned_back += 1
        self._quieten(app, now, self.BACK_TO_WORK_QUIET)

    def close_it(self, app: str, now: float) -> None:
        # Answered, not cleared: the app may stay in front with its own save
        # prompt up, and the notice must not come back over it. Only leaving
        # the foreground clears the sighting.
        self.turned_back += 1
        self.quiet_until[app.lower()] = now + self.BACK_TO_WORK_QUIET
        self.showing = False

    def _quieten(self, app: str, now: float, window: float) -> None:
        self.quiet_until[app.lower()] = now + window
        self.sighting = None
        self.showing = False

    def is_quiet(self, app: str, now: float) -> bool:
        return now < self.quiet_until.get(app.lower(), float("-inf"))

    def reset(self) -> None:
        self.quiet_until.clear()
        self.sighting = None
        self.showing = False
        self.tries = 0
        self.turned_back = 0


# ================================================ breaks and cycles (F5)

LONG_BREAK_EVERY = 4

CYCLE_MODEL = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "CycleState.cs"


def cycle_source() -> str:
    """
    The model the mirrors below stand for.

    Every mirror class anchors itself to a line of this file. Without that, the
    Python mirror keeps passing after someone changes — or deletes — the C# it
    is supposed to be describing, which is the one way a unit-by-source test can
    quietly become fiction.
    """
    assert CYCLE_MODEL.exists(), "CycleState.cs is what these tests describe"
    return CYCLE_MODEL.read_text(encoding="utf-8")


def break_minutes(in_a_row: int, short_minutes: int, long_minutes: int) -> int:
    """Mirror of CycleState.BreakMinutes."""
    return long_minutes if in_a_row > 0 and in_a_row % LONG_BREAK_EVERY == 0 else short_minutes


def offers_break(completed: bool) -> bool:
    """Mirror of CycleState.OffersBreak: only a sprint that finished earns one."""
    return completed


class Cycle:
    """Mirror of CycleState: where a cycle is, and nothing else."""

    def __init__(self, planned=0, done=0, phase="idle"):
        self.phase = phase
        self.planned = planned
        self.done = done

    # ---- the properties the view binds to
    @property
    def in_cycle(self) -> bool:
        return self.planned > 1

    @property
    def sprint_number(self) -> int:
        return min(self.done + 1, max(self.planned, 1))

    @property
    def label(self) -> str:
        return f"Sprint {self.sprint_number} of {self.planned}" if self.in_cycle else ""

    @property
    def cycle_finished(self) -> bool:
        return self.in_cycle and self.done >= self.planned

    @property
    def starts_next_sprint(self) -> bool:
        return self.in_cycle and self.done < self.planned

    # ---- transitions
    def sprint_started(self, chooser: int) -> "Cycle":
        if self.in_cycle and not self.cycle_finished:
            self.phase = "sprint"
            return self
        return Cycle(max(chooser, 0), 0, "sprint")

    def sprint_completed(self) -> "Cycle":
        return Cycle(self.planned, self.done + 1, "idle")

    def sprint_abandoned(self) -> "Cycle":
        return Cycle()

    def break_started(self) -> "Cycle":
        self.phase = "break"
        return self

    def break_ended(self) -> "Cycle":
        self.phase = "idle"
        return self

    def cycle_done(self) -> "Cycle":
        return Cycle(0, 0, "idle")


class Today:
    """
    The handful of TodayViewModel decisions the cycle drives, and nothing else.

    `momentum` and `goal_days` stand in for the two things a break must never
    touch: they are only ever changed by a sprint ending.
    """

    def __init__(self, chooser=0, short_break=5, long_break=15):
        self.cycle = Cycle()
        self.chooser = chooser
        self.short_break = short_break
        self.long_break = long_break
        self.offer_visible = False
        self.on_break = False
        self.break_minutes_running = 0
        self.enforcing = False
        self.momentum = 0
        self.goal_days = 0
        self.sprints_run = 0
        # AppSettings.CompletedSprintsInARow: what earns the long break.
        self.in_a_row = 0

    def start_sprint(self):
        self.end_break()
        self.cycle = self.cycle.sprint_started(self.chooser)
        self.offer_visible = False
        self.enforcing = True
        self.sprints_run += 1

    def end_sprint(self, completed: bool):
        self.enforcing = False
        if completed:
            self.momentum += 10
            self.goal_days += 1
            self.in_a_row += 1
            self.cycle = self.cycle.sprint_completed()
        else:
            self.momentum -= 5
            self.in_a_row = 0
            self.cycle = self.cycle.sprint_abandoned()

        if offers_break(completed):
            self.offer_visible = True
            if self.cycle.starts_next_sprint:
                self.start_break()
        else:
            self.offer_visible = False

        if self.cycle.cycle_finished:
            self.cycle = self.cycle.cycle_done()

    def start_break(self):
        if not self.offer_visible or self.on_break:
            return
        self.break_minutes_running = break_minutes(
            self.in_a_row, self.short_break, self.long_break)
        self.cycle = self.cycle.break_started()
        self.offer_visible = False
        self.on_break = True

    def end_break(self):
        self.offer_visible = False
        if not self.on_break:
            return
        self.on_break = False
        self.cycle = self.cycle.break_ended()

    def skip_break(self):
        self.end_break()
        self.continue_or_idle()

    def break_ran_out(self):
        self.end_break()
        self.continue_or_idle()

    def continue_or_idle(self):
        if self.cycle.starts_next_sprint:
            self.start_sprint()


def decide_break(ends_at, now) -> str:
    """Mirror of RunningBreak.Decide."""
    return "end quietly" if ends_at <= now else "resume"


# ================ what a break says inside the nightly sleep window (#272, #301)

BREAK_COPY_MODEL = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "BreakCopy.cs"


def break_panel_text(in_window: bool, on_break: bool, is_long: bool, minutes, ends,
                     long_every=LONG_BREAK_EVERY) -> str:
    """
    Mirror of BreakCopy.PanelText: the break card's line, as the offer and
    while the break runs. Inside the sleep window the sprint's shield is down
    but the nightly one still closes blocked apps, so no line there may say
    the shield is down without saying which shield is still up.
    """
    if on_break:
        if in_window:
            return ("The sprint's shield is down, but your nightly sleep shield is still up — "
                    f"blocked apps are still closed until it ends at {ends}.")
        return "The shield is down. Blocked apps are allowed until the break ends."
    if is_long:
        if in_window:
            return (f"{long_every} sprints in a row, so this break is {minutes} minutes. "
                    "The sprint's shield comes down, but your nightly sleep shield stays up "
                    f"until {ends}, so blocked apps are still closed.")
        return (f"{long_every} sprints in a row, so this break is {minutes} minutes. "
                "The shield stays down while it runs.")
    if in_window:
        return (f"{minutes} minutes with the sprint's shield down, but your nightly sleep "
                f"shield stays up until {ends}, so blocked apps are still closed.")
    return f"{minutes} minutes with the shield down. It changes nothing about your momentum."


def break_caption(in_window: bool, resumed: bool) -> str:
    """
    Mirror of BreakCopy.Caption: the state line under the ring while a break
    runs. Since #304 it may take two lines inside the ring (tier 5 lays each
    one out), so the resumed pair is parallel again, and each breaks after
    its dash rather than wherever the width runs out.
    """
    if in_window:
        return "Break resumed —\nsleep shield still up" if resumed else "Break — sleep shield still up"
    return "Break resumed —\nthe shield is down" if resumed else "Break — the shield is down"


#: Inside or outside the window × running or offered × long or short.
BREAK_COPY_CASES = [(in_window, on_break, is_long)
                    for in_window in (True, False)
                    for on_break in (True, False)
                    for is_long in (True, False)]


def picker_merge(suggestions: list[dict], discovered: list[dict]) -> list[str]:
    """Mirror of AppPicker.Merge: a suggestion is listed only when something
    found on this PC runs one of its processes; other finds follow, once each."""
    covered, result, seen = set(), [], {p.lower() for s in suggestions for p in s["processes"]}
    for d in discovered:
        process = d["processes"][0]
        hit = next((s for s in suggestions
                    if process.lower() in (p.lower() for p in s["processes"])), None)
        if hit is not None:
            covered.add(hit["name"])
        elif process.lower() not in seen:
            seen.add(process.lower())
            result.append(d["name"])
    return [s["name"] for s in suggestions if s["name"] in covered] + result


JUNK_NAME_WORDS = ("uninstall", "update", "installer", "installation", "setup", "redistributable",
                   "runtime", "sdk", "shared framework", "driver", "plugin", "module docs",
                   "documentation", "readme", "release notes")
JUNK_PROCESS_WORDS = ("unins", "uninstall", "setup", "install", "update", "redist", "runtime",
                      "sdk-", "bundle", "download", "-amd64")


def picker_is_not_an_app(name: str, process: str) -> bool:
    """Mirror of AppPicker.IsNotAnApp: updaters, installers, runtimes and docs aren't apps anyone blocks."""
    n, p = name.lower(), process.lower()
    return any(w in n for w in JUNK_NAME_WORDS) or any(w in p for w in JUNK_PROCESS_WORDS)


# ============================================ the window fits small screens (#296)

def fit_window(window, work, min_w, min_h):
    """Mirror of Infrastructure/WindowFit.Fit. Rects are (left, top, width, height)."""
    left, top, w, h = window
    wl, wt, ww, wh = work
    width = max(min_w, min(w, ww))
    height = max(min_h, min(h, wh))
    return (max(wl, min(left, wl + ww - width)), max(wt, min(top, wt + wh - height)), width, height)
