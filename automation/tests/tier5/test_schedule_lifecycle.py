# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: schedule lifecycle."""

from __future__ import annotations
import re
import time
from html.parser import HTMLParser
from pathlib import Path
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from tests._split_support import all_test_sources, report_key



class TestSchedulePageKeepsTheSleepWindow:
    """F6 moves Sleep Blocking inside Schedule; nothing of the sleep window may be lost."""


    def test_the_tab_keeps_its_id_and_shortcut(self):
        xaml = (Path(DESKTOP_DIR) / "MainWindow.xaml").read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="Tab_SleepBlocking"' in xaml
        assert 'Key="D4" Command="{Binding NavigateCommand}" CommandParameter="SleepBlocking"' in xaml
        assert 'Text="Schedule"' in xaml

    def test_every_new_id_is_on_a_real_control(self):
        xaml = (Path(DESKTOP_DIR) / "Views" / "ScheduleView.xaml").read_text(encoding="utf-8")
        for match in re.finditer(r"<(\w+)[^>]*AutomationProperties\.AutomationId=", xaml):
            assert match.group(1) not in ("Border", "Grid", "StackPanel", "WrapPanel"), (
                f"an AutomationId on a {match.group(1)} is never surfaced (#134)")


class TestSchedulePageRefusesInTheViewModel:
    """
    A Sealed sprint makes the Schedule page read-only. The buttons go grey, but
    a disabled or covered control can still be reached (CLAUDE.md, "Covered
    controls"), so every method that changes a schedule or a template refuses
    on its own, not only through its command's CanExecute.
    """

    VM = Path(DESKTOP_DIR) / "ViewModels" / "ScheduleViewModel.cs"

    def _body(self, source: str, signature: str) -> str:
        start = source.index(signature)
        return source[start:source.index("\n    }\n", start)]

    @staticmethod
    def _first_statement(body: str) -> str:
        """The first line of code inside the braces, blanks and comments skipped."""
        for line in body[body.index("{") + 1:].splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("//"):
                return stripped
        return ""

    def test_every_change_checks_can_edit_first(self):
        """
        First, not merely somewhere: a guard after the change, or in a comment,
        would satisfy a substring check and refuse nothing.
        """
        source = self.VM.read_text(encoding="utf-8")
        for signature in ("private void OpenScheduleEditor(", "private void SaveSchedule(",
                          "private void DeleteSchedule(", "private void SetScheduleEnabled(",
                          "private void OpenTemplateEditor(", "private void SaveTemplate(",
                          "private void DeleteTemplate(", "private void RestoreTemplates("):
            first = self._first_statement(self._body(source, signature))
            assert first.startswith("if (") and "!EnsureCanEdit()" in first, (
                f"{signature.strip('(')} must refuse during a Sealed sprint before it does "
                f"anything else; its first statement is {first!r}")


class TestSchedulePageNamesAndLabels:
    """
    After the PR A review: template names are unique because the page's
    AutomationIds are built from them, the range labels come from the constants
    Save checks, and the active-profile chip has an id no profile name can
    produce. The report's tier table must also know about the probe tests.
    """

    VM = Path(DESKTOP_DIR) / "ViewModels" / "ScheduleViewModel.cs"
    XAML = Path(DESKTOP_DIR) / "Views" / "ScheduleView.xaml"

    def test_the_editor_saves_a_unique_name(self):
        source = self.VM.read_text(encoding="utf-8")
        start = source.index("private void SaveTemplate(")
        body = source[start:source.index("\n    }\n", start)]
        assert "S.UniqueTemplateName(template.Name, except: template)" in body
        assert body.index("template.Normalize()") < body.index("UniqueTemplateName("), \
            "the number goes on the cleaned name, or a later Normalize could cut it off"

    def test_the_range_labels_are_bound_not_typed(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        assert 'Text="{Binding SprintMinutesLabel}"' in xaml
        assert 'Text="{Binding BreakMinutesLabel}"' in xaml
        assert "(5–240)" not in xaml and "(1–60)" not in xaml, "a typed limit can drift from the constant"
        vm = self.VM.read_text(encoding="utf-8")
        assert "SPRINT MINUTES ({StudyTemplate.MinSprintMinutes}" in vm
        assert "{StudyTemplate.MaxSprintMinutes})" in vm
        assert "BREAK MINUTES ({CycleState.MinBreakMinutes}" in vm
        assert "{CycleState.MaxBreakMinutes})" in vm

    def test_the_active_profile_chip_has_an_id_no_profile_name_can_produce(self):
        vm = self.VM.read_text(encoding="utf-8")
        assert 'AutomationId = "TemplateProfileActive"' in vm
        assert 'AutomationId = $"TemplateProfile_{p.Name}"' in vm
        xaml = self.XAML.read_text(encoding="utf-8")
        assert "TemplateProfile_{0}" not in xaml, "the prefix form would let a profile named Active collide"
        assert xaml.count('AutomationProperties.AutomationId="{Binding AutomationId}"') == 3, \
            "every chip (template, day, profile) takes its whole id from the view model"

    def test_every_tier_file_has_a_row_in_the_report(self):
        """make_report.py counts tests per tier by filename; a file with no row leaves the rows short of the total."""
        root = Path(DESKTOP_DIR).parent
        report = (root / "automation" / "make_report.py").read_text(encoding="utf-8")
        for path in all_test_sources(root / "automation" / "tests"):
            assert f'"{report_key(path)}":' in report, f"{path.name} has no tier row in make_report.py"


# ===================== scheduled sprints start through Start's gates (F6, PR C)

class TestScheduledSprintsGoThroughStart:
    """
    F6: a schedule starts a template by itself. That is a Start nobody pressed,
    so every rule a pressed Start obeys must hold for it too: terms, first run,
    the trial, one sprint at a time, and F7's open-apps question unless the
    heads-up already named the apps. Comments are stripped, so a call left only
    in a comment can't satisfy these.
    """

    TODAY = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    MAIN = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    APP = Path(DESKTOP_DIR) / "App.xaml.cs"
    TODAY_XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"

    @staticmethod
    def code(path: Path) -> str:
        return "\n".join(line.split("//")[0] for line in path.read_text(encoding="utf-8").splitlines())

    @staticmethod
    def member(code: str, signature: str) -> str:
        """One member's body, from its signature to the brace that closes it."""
        start = code.index(signature)
        depth = 0
        for index in range(code.index("{", start), len(code)):
            depth += {"{": 1, "}": -1}.get(code[index], 0)
            if depth == 0:
                return code[start:index + 1]
        raise AssertionError(f"no end to {signature}")

    def case(self, signature: str, kind: str) -> str:
        switch = self.member(self.code(self.MAIN), signature)
        return switch.split(f"case ScheduleActionKind.{kind}:", 1)[1].split("break;", 1)[0]

    def test_a_template_starts_through_start_sprint_not_a_copy_of_it(self):
        start = self.member(self.code(self.TODAY), "public bool StartTemplate(")
        assert "StartSprint();" in start
        for copied in ("TermsGateVisible", "FirstRun.IsVisible", "IsLocked", "S.ActiveSprint =",
                       "BeginRunning("):
            assert copied not in start, f"StartTemplate copies {copied}; it must go through StartSprint"

    def test_a_refused_template_start_leaves_nothing_for_the_next_start(self):
        """
        A gate can refuse inside StartSprint before F7's latch is spent. Left
        set, the next Start pressed by hand would skip the question and take
        the template's breaks.
        """
        start = self.member(self.code(self.TODAY), "public bool StartTemplate(")
        refused = start.split("if (!IsRunning && !RunningAppsPanelVisible)", 1)[1]
        assert "_runningAppsAnswered = false;" in refused
        assert "_startingTemplateBreak = null;" in refused
        assert "_startingAnnouncedName = null;" in refused, \
            "a hand Start afterwards would be announced as the template"

    def test_a_schedule_does_nothing_while_busy_or_behind_a_gate(self):
        on_action = self.member(self.code(self.MAIN), "private void OnScheduleAction(")
        guard = on_action.split("switch (action.Kind)", 1)[0]
        assert "if (IsSprintRunning" in guard, "OnScheduleAction must refuse before its switch"
        condition, block = guard[guard.index("if (IsSprintRunning"):].split("{", 1)
        assert "return;" in block
        for gate in ("IsSprintRunning", "Today.IsOnBreak", "IsLocked", "TermsGateVisible",
                     "FirstRun.IsVisible"):
            assert gate in condition, f"a schedule must do nothing while {gate}"

    def test_a_missed_start_is_only_ever_offered(self):
        """Spec 3.3: never start automatically after waking or launching."""
        missed = self.case("private void OnScheduleAction(", "OfferMissed")
        assert "Today.ShowHeadsUp(action, template);" in missed
        assert "StartTemplate(" not in missed

    def test_a_scheduled_start_asks_about_open_apps_unless_the_heads_up_named_them(self):
        """
        The heads-up names the open apps a Firm or Sealed template will close,
        so it stands in for F7's question. With no heads-up (Ask first off), or
        an app opened since, the question is asked as quick start asks it
        (#270): Today, brought to the front.
        """
        start = self.case("private void OnScheduleAction(", "Start")
        assert re.search(r"var named = Today\.HeadsUpNamedWhatWillClose\(action, template\);", start)
        assert "Today.StartTemplate(template, skipOpenAppsPanel: named," in start
        assert start.index("HeadsUpNamedWhatWillClose(") < start.index("Today.HideHeadsUp();"), \
            "read what the card named before the card goes"
        asked = start.split("&& Today.RunningAppsPanelVisible)", 1)[1]
        assert "CurrentPage = AppPage.Today;" in asked
        assert "OpenAppsQuestionRaised?.Invoke(this, EventArgs.Empty);" in asked
        window = self.code(self.WINDOW)
        assert "newVm.OpenAppsQuestionRaised += OnOpenAppsQuestionRaised;" in window
        assert "oldVm.OpenAppsQuestionRaised -= OnOpenAppsQuestionRaised;" in window
        assert "BringToFront()" in self.member(window, "private void OnOpenAppsQuestionRaised(")

    def test_a_scheduled_start_sends_one_notification(self):
        """
        Review of PR C: "Sprint started" is on by default, so a schedule with
        Ask first off sent it and then "Light study started", back to back.
        The named notice (spec 3.3) now stands in for the generic one, sent
        where the sprint starts, so a start that waited on F7's question and
        was answered names the template too. With the scheduled-sprint switch
        off, "Sprint started" still comes: Notify says whether it showed.
        """
        start_case = self.case("private void OnScheduleAction(", "Start")
        # Past the unasked offer (which starts nothing, see the next test),
        # the start's own notice is sent once, where the sprint starts.
        starting = start_case.split("return;", 1)[-1]
        assert "Notify(" not in starting, "a start's notice is sent once, where the sprint starts"
        assert "announceByName: !action.Schedule.AskFirst" in starting

        today = self.code(self.TODAY)
        assert "_startingAnnouncedName = announceByName ? template.Name : null;" in \
            self.member(today, "public bool StartTemplate(")

        start = self.member(today, "private void StartSprint()")
        taken = start.index("var announcedName = _startingAnnouncedName;")
        assert start.index("if (!_runningAppsAnswered)") < taken, \
            "kept while F7's question waits, so answering it names the template"
        assert "_startingAnnouncedName = null;" in start[taken:]
        assert re.search(r"var announced = announcedName is not null\s*&&\s*"
                         r"_main\.Notify\(NotificationKind\.ScheduledSprint, \$\"\{announcedName\} started\",",
                         start)
        assert re.search(r"if \(!announced\)\s*_main\.Notify\(NotificationKind\.SprintStarted,", start)
        assert start.count("_main.Notify(") == 2

    def test_an_ask_first_start_nobody_was_asked_about_is_offered_not_started(self):
        """
        Final review of PR C: the service remembers a heads-up as shown
        before the handler runs, and the handler refuses it while a sprint or
        break is running, so a 25-minute hand sprint ending between T-5 and T
        left the schedule's Start to pass the guard with no card up and no
        question asked. A clock set back past a start, or a westward zone
        change, reach the same place. Ask first is the one promise the switch
        makes: a Start with no card up for its schedule is offered on the
        card ("X is due now", Start now / Skip today), never taken.
        """
        start = self.case("private void OnScheduleAction(", "Start")
        assert "if (action.Schedule.AskFirst && !Today.HeadsUpIsFor(action))" in start
        assert "return;" in start, "the offer is the whole of that tick's work"
        offer, starting = start.split("return;", 1)
        assert offer.index("HeadsUpIsFor(") < offer.index("Today.ShowHeadsUp(action, template);")
        assert "NotifyHeadsUp($\"{template.Name} is due now\"," in offer
        assert "StartTemplate(" not in offer, "an unasked start is offered, never taken"
        assert "HideHeadsUp(" not in offer, "read whether a card is up before anything hides one"
        assert "Today.StartTemplate(template, skipOpenAppsPanel: named," in starting, \
            "a start whose card is up still starts as before"

        today = self.code(self.TODAY)
        # R23: the schedule and the start instant, so a card left up from an
        # earlier start of the same schedule never counts as asked.
        is_for = self.member(today, "public bool HeadsUpIsFor(ScheduleAction action)")
        assert "card.Schedule.Id == action.Schedule.Id" in is_for
        assert "card.StartUtc == action.StartUtc" in is_for
        show = self.member(today, "public void ShowHeadsUp(")
        assert "ScheduleActionKind.Start => $\"{template.Name} is due now\"" in show, \
            "the card says the start is due, not that it is coming"

    def test_the_heads_up_notification_names_what_will_close_and_opens_today(self):
        """
        Polish of PR C (R22a, item 7): with the window in the tray the card
        is the only place the apps were named and nobody saw it, so the
        notification's body carries the card's sentence ("Discord, Steam
        will be closed.") whenever there is one. Its title is the card's own
        time, not "in 5 minutes", which was untrue for a schedule saved two
        minutes ahead. Clicking any of the three opens Today, where the card
        is; the missed one says it was missed.
        """
        main = self.code(self.MAIN)
        assert "in 5 minutes" not in main
        notify = self.member(main, "private void NotifyHeadsUp(")
        assert "var closing = Today.HeadsUpClosingText;" in notify
        assert re.search(r"closing\.Length > 0 \? \$\"\{closing\} \{ask\}\" : ask", notify)
        assert "Notify(NotificationKind.ScheduledSprint, title, body, NotificationAction.OpenToday)" in notify
        assert re.search(r"if \(Notify\([^;]*\) && closing\.Length > 0\)\s*Today\.HeadsUpNamesWereNotified\(\);",
                         notify), "the names count as seen only when the notice with them was sent"

        heads_up = self.case("private void OnScheduleAction(", "HeadsUp")
        assert "NotifyHeadsUp($\"{template.Name} starts at {Today.HeadsUpTimeText}\"," in heads_up
        missed = self.case("private void OnScheduleAction(", "OfferMissed")
        assert "NotifyHeadsUp($\"You missed {template.Name}\"," in missed
        assert "It was due at {Today.HeadsUpTimeText}." in missed
        on_action = self.member(main, "private void OnScheduleAction(")
        assert on_action.count("NotifyHeadsUp(") == 3 and "Notify(NotificationKind" not in on_action, \
            "every card's notice goes through the one helper"

        notifications = Path(DESKTOP_DIR) / "Models" / "Notifications.cs"
        assert "OpenToday" in notifications.read_text(encoding="utf-8")
        clicked = self.member(self.code(self.WINDOW), "private void OnNotificationClicked(")
        assert re.search(r"case NotificationAction\.OpenToday:\s*Vm\.CurrentPage = AppPage\.Today;", clicked)

    def test_the_card_counts_as_having_named_the_apps_only_where_someone_could_see_it(self):
        """
        Polish of PR C (R22b): HeadsUpNamedWhatWillClose credited the card
        with naming the apps even when the window was in the tray and the
        notification named none, so an Ask-first Firm start could close an
        app the user never saw named. The card counts only if the window was
        up (not minimised or in the tray) when it was shown, or the
        notification with the names was actually sent; otherwise the start
        goes through F7's question as an unasked one does.
        """
        today = self.code(self.TODAY)
        show = self.member(today, "public void ShowHeadsUp(")
        assert "_headsUpNamesSeen = _main.IsWindowVisible;" in show
        named = self.member(today, "public bool HeadsUpNamedWhatWillClose(ScheduleAction action, StudyTemplate template)")
        assert "if (closing.Count == 0) return true;" in named
        assert re.search(r"return HeadsUpIsFor\(action\)\s*&&\s*_headsUpNamesSeen\s*&&", named)
        assert re.search(r"public void HeadsUpNamesWereNotified\(\)\s*=>\s*_headsUpNamesSeen = true;", today)
        hide = self.member(today, "public void HideHeadsUp(")
        assert "_headsUpNamesSeen = false;" in hide
        start_now = self.member(today, "private void StartNow(")
        assert start_now.index("_headsUpNamesSeen = true;") < start_now.index("HeadsUpNamedWhatWillClose("), \
            "Start now is pressed on the card itself, so what it names has been seen"

        main = self.code(self.MAIN)
        assert re.search(r"public bool IsWindowVisible\s*=>\s*WindowVisibility\?\.Invoke\(\) \?\? false;", main), \
            "with no window wired, nobody could have seen the card"
        window = self.code(self.WINDOW)
        assert "newVm.WindowVisibility = () => IsVisible && WindowState != WindowState.Minimized;" in window
        assert "oldVm.WindowVisibility = null;" in window

    def test_a_card_goes_when_its_start_is_handled_or_it_goes_stale(self):
        """
        Polish of PR C (R23): a heads-up card whose start was refused at the
        busy or gated guard stayed up saying "starts at 17:00"; a missed
        card never expired although a missed start is offered for 30
        minutes. Now a card is removed when its start is handled (started:
        BeginRunning; refused: the guard; skipped; its schedule switched off
        or deleted) and expires once LateWindow has passed since its start,
        checked on every scheduler tick.
        """
        on_action = self.member(self.code(self.MAIN), "private void OnScheduleAction(")
        guard = on_action.split("switch (action.Kind)", 1)[0]
        refused = guard[guard.index("if (IsSprintRunning"):]
        assert "if (action.Kind == ScheduleActionKind.Start && Today.HeadsUpIsFor(action)) Today.HideHeadsUp();" \
            in refused
        assert refused.index("Today.HideHeadsUp();") < refused.index("return;")

        ctor = self.member(self.code(self.MAIN), "public MainViewModel(")
        assert "Scheduler.Ticked += (_, now) => Today.DropStaleHeadsUp(now);" in ctor

        today = self.code(self.TODAY)
        drop = self.member(today, "public void DropStaleHeadsUp(DateTime nowUtc)")
        assert "SchedulePlanner.CardHasExpired(headsUp.StartUtc, nowUtc)" in drop
        assert "!headsUp.Schedule.Enabled" in drop and "!S.Schedules.Contains(headsUp.Schedule)" in drop
        assert "HideHeadsUp();" in drop

        schedule_vm = self.code(Path(DESKTOP_DIR) / "ViewModels" / "ScheduleViewModel.cs")
        for signature in ("private void DeleteSchedule(", "private void SetScheduleEnabled(",
                          "private void DeleteTemplate("):
            assert "_main.Today.DropStaleHeadsUp(DateTime.UtcNow);" in self.member(schedule_vm, signature), \
                f"{signature} must drop a card for a schedule that is off or gone"

    def test_the_missed_card_says_skip_like_its_button(self):
        """DESIGN_SYSTEM 9: one word for one thing. The button is Skip today; the toast and the page say skipped."""
        show = self.member(self.code(self.TODAY), "public void ShowHeadsUp(")
        assert "$\"It was due at {at}. Start it now, or skip it for today.\"" in show
        assert "leave it for today" not in show
        xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        assert re.search(r'<Button\b[^>]*Content="Skip today"[^>]*AutomationId="HeadsUpSkipButton"', xaml)

    def test_start_now_is_secondary_so_start_sprint_stays_the_one_primary(self):
        """
        DESIGN_SYSTEM 7 allows one Primary per view (Start sprint on Today).
        The card's Start now is Secondary (BtnGhost) and Skip today Quiet,
        mirroring the end panel's Keep going / End anyway pair.
        """
        xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        card = xaml.split("heads-up (F6)", 1)[1].split("timer card", 1)[0]
        assert "BtnPrimary" not in card
        assert re.search(r'<Button\b[^>]*Style="\{StaticResource BtnGhost\}"[^>]*AutomationId="HeadsUpStartNowButton"',
                         card)
        assert re.search(r'<Button\b[^>]*Style="\{StaticResource BtnQuiet\}"[^>]*AutomationId="HeadsUpSkipButton"',
                         card)

    def test_the_heads_up_names_what_the_templates_own_shield_and_list_will_close(self):
        today = self.code(self.TODAY)
        would_close = self.member(today, "private IReadOnlyList<string> AppsItWouldClose(")
        assert "_main.Blocker.RunningBlockedApps(S.ProfileFor(template))" in would_close
        assert "template.Shield >= ShieldLevel.Firm || S.HardKillModeEnabled" in would_close, \
            "the blocker's own rule for closing, so the card never promises less than happens"
        assert "AppsItWouldClose(template)" in self.member(today, "public void ShowHeadsUp(")

    def test_the_card_never_outlives_a_start(self):
        assert "HideHeadsUp();" in self.member(self.code(self.TODAY), "private void BeginRunning(")

    def test_skip_today_saves_the_starts_own_date(self):
        skip = self.member(self.code(self.TODAY), "private void SkipToday(")
        assert re.search(r"\.Skip\(TimeZoneInfo\.ConvertTimeFromUtc\(headsUp\.StartUtc, TimeZoneInfo\.Local\)\.Date\)", skip)
        assert "_main.SaveSettings();" in skip

    def test_short_schedules_is_a_launch_flag(self):
        app = self.code(self.APP)
        flag = app.split('"--short-schedules"', 1)[1].split("}", 1)[0]
        assert "Models.SchedulePlanner.UseShortSchedules = true;" in flag

    def test_the_scheduler_starts_after_the_resumed_sprint(self):
        ctor = self.member(self.code(self.MAIN), "public MainViewModel(")
        assert "Scheduler = new ScheduleService(Settings);" in ctor
        assert "Scheduler.Action += (_, action) => OnScheduleAction(action);" in ctor
        assert ctor.index("Today.ResumeInterruptedSprint();") < ctor.index("Scheduler.Start();")
        assert "Schedule.TemplatesChanged += (_, _) => Today.RefreshTemplates();" in ctor

    def test_the_templates_break_is_saved_restored_and_offered(self):
        today = self.code(self.TODAY)
        assert "TemplateBreakMinutes = _templateBreakMinutes," in self.member(today, "private void StartSprint()")
        resume = self.member(today, "public void ResumeInterruptedSprint(")
        assert "_templateBreakMinutes = saved.TemplateBreakMinutes;" in resume.split(
            "case SprintResume.Resume:", 1)[1].split("case SprintResume.RecordCompleted:", 1)[0]
        assert re.search(r"private int OfferedBreakMinutes\s*=>\s*_templateBreakMinutes\s*\?\?\s*"
                         r"CycleState\.BreakMinutes\(", today)
        assert today.count("CycleState.BreakMinutes(") == 1, "every break length goes through OfferedBreakMinutes"
        assert "var minutes = OfferedBreakMinutes;" in self.member(today, "private void StartBreak()")
        assert re.search(r"private bool OfferedBreakIsLong\s*=>\s*_templateBreakMinutes is null\s*&&", today), \
            "a template's break is its own length, not the fourth-in-a-row long one"

    def test_the_templates_break_rides_with_the_running_break_too(self):
        """
        PR C polish, item 8: a restart during a break inside a template cycle
        resumed the break but not the template's break length, so the cycle's
        later breaks fell back to Settings' lengths. RunningBreak carries it,
        written where the break starts and restored where it resumes.
        """
        today = self.code(self.TODAY)
        assert "TemplateBreakMinutes = _templateBreakMinutes," in self.member(today, "private void StartBreak()")
        resume = self.member(today, "public void ResumeInterruptedBreak(")
        assert "_templateBreakMinutes = saved.TemplateBreakMinutes;" in resume
        assert resume.index("_templateBreakMinutes = saved.TemplateBreakMinutes;") < resume.index("BeginBreakClock(")
        cycle_state = self.code(Path(DESKTOP_DIR) / "Models" / "CycleState.cs")
        assert "public int? TemplateBreakMinutes { get; set; }" in self.member(cycle_state, "public class RunningBreak")

    def test_a_chip_carries_the_templates_break_to_the_next_start(self):
        """
        PR C polish, item 9: a chip on Today fills in length, shield, cycle
        and profile, and now the template's break length with them, taken up
        by the next Start. A hand change of length, shield or cycle
        afterwards keeps it (the chip is a preset, and the rest of the preset
        survives such a change too); only another chip, or the start itself,
        replaces it.
        """
        today = self.code(self.TODAY)
        assert "_startingTemplateBreak = template.BreakMinutes;" in self.member(today, "public void ApplyTemplate(")
        assert "_startingTemplateBreak = template.BreakMinutes;" not in \
            self.member(today, "public bool StartTemplate("), "set once, where the chip and the schedule both go"
        # Set by the chip, consumed by the start, cleared by a refused template start; nowhere else.
        assert len(re.findall(r"_startingTemplateBreak = ", today)) == 3
        for setter in ("public int PresetMinutes", "public string CustomMinutesText", "public bool IsCustomSelected",
                       "public ShieldLevel SelectedShield", "public int CycleSprints"):
            assert "_startingTemplateBreak" not in self.member(today, setter), f"{setter} must keep the chip's break"

    def test_only_a_run_begun_from_a_template_takes_its_breaks(self):
        """
        A cycle's later sprints keep what the run began with; a run begun any
        other way (Start, Space, the tray) takes Settings' break lengths.
        """
        start = self.member(self.code(self.TODAY), "private void StartSprint()")
        after_cycle = start.split("_cycle = _cycle.OnSprintStarted(CycleSprints);", 1)[1]
        assert re.search(r"if \(_cycle\.SprintsDone == 0\)\s*_templateBreakMinutes = _startingTemplateBreak;",
                         after_cycle)
        assert "_startingTemplateBreak = null;" in after_cycle

    def test_the_card_and_the_chips_carry_ids_on_real_controls(self):
        xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        for control, automation_id in (("TextBlock", "HeadsUpCard"), ("TextBlock", "HeadsUpText"),
                                       ("Button", "HeadsUpStartNowButton"), ("Button", "HeadsUpSkipButton")):
            assert re.search(rf'<{control}\b[^>]*AutomationProperties\.AutomationId="{automation_id}"', xaml), \
                f"{automation_id} must sit on a {control} (#134)"
        assert re.search(r'<Button\b[^>]*AutomationProperties\.AutomationId="\{Binding Name, '
                         r'StringFormat=TemplateChip_\{0\}\}"', xaml)

    def test_the_chips_hide_while_a_sprint_or_break_runs(self):
        """Spec 3.5, and the card's twin: a chip mid-sprint would change a running sprint's settings."""
        today = self.code(self.TODAY)
        assert re.search(r"public bool TemplatesVisible\s*=>\s*!IsRunning && !IsOnBreak", today)
        assert "if (IsRunning || IsOnBreak || _main.IsLocked) return;" in \
            self.member(today, "public void ApplyTemplate(")
        assert 'Visibility="{Binding TemplatesVisible, Converter={StaticResource BoolVis}}"' in \
            self.TODAY_XAML.read_text(encoding="utf-8")

    def test_the_scheduled_sprint_notice_is_switchable_like_the_others(self):
        settings_vm = self.code(Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs")
        assert "NotificationKind.ScheduledSprint" in self.member(settings_vm, "public bool NotifyScheduledSprint")
        assert "Raise(nameof(NotifyScheduledSprint));" in self.member(settings_vm, "public bool NotificationsEnabled")
        xaml = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="NotifyScheduledSprintToggle"' in xaml

    def test_the_schedule_page_scroller_is_not_a_tab_stop(self):
        """Controller note (PR A): it drew a dashed focus rectangle round the whole page."""
        xaml = (Path(DESKTOP_DIR) / "Views" / "ScheduleView.xaml").read_text(encoding="utf-8")
        scroller = xaml.split("<ScrollViewer", 1)[1].split(">", 1)[0]
        assert 'AutomationProperties.AutomationId="SchedulePageScroll"' in scroller
        assert 'Focusable="False"' in scroller

    def test_the_new_copy_keeps_to_the_house_voice(self):
        """DESIGN_SYSTEM 9: no exclamation marks, and ASCII-only C# literals."""
        today = self.TODAY.read_text(encoding="utf-8")
        region = today.split("templates and schedules (F6)", 1)[1].split("what is already running (F7)", 1)[0]
        on_action = self.member(self.MAIN.read_text(encoding="utf-8"), "private void OnScheduleAction(")
        # StartSprint sends a scheduled start's "Light study started".
        start = self.member(today, "private void StartSprint()")
        for text in (region, on_action, start):
            for literal in re.findall(r'"[^"\n]*"', text):
                assert "!" not in literal, literal
                assert literal.isascii(), literal


# ===================== F6's chip row moved Today's controls (PR C regressions)

class TestTodayGrewARowAndItsControlsStayReachable:
    """
    PR C's row of template chips made Today's idle page about 56 px taller.
    Two things that had been clear of each other at the default window height
    then overlapped, and two tier 3 tests that pass on main failed on the
    branch alone (test_sealed_locks_the_profile_switcher and
    test_cancelling_a_sprint_clears_the_intention_input):

    - the toast ("Profile "School" added, starting from...") lay over the
      Sealed chip of the shield picker for its four seconds, and an opaque
      Border takes the click, so the sprint started at the default shield
      (Firm) and the switcher stayed enabled;
    - with the page scrolled down to the intention field, Start collapsed the
      chips and itself, the page kept its scroll offset, and the ring with its
      Cancel button slid up under the page header, where no click could reach
      them: the cancel never happened and the intention was never cleared.

    Neither is a test problem. A notice must never take a click meant for the
    page, and a sprint that has just started must show its countdown and the
    way to end it.
    """

    WINDOW_XAML = Path(DESKTOP_DIR) / "MainWindow.xaml"
    TODAY_XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"
    TODAY_CS = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml.cs"

    def test_the_toast_never_takes_a_click_meant_for_the_page(self):
        xaml = self.WINDOW_XAML.read_text(encoding="utf-8-sig")
        toast = xaml.split("<!-- toast -->", 1)[1].split("<Border", 1)[1].split(">", 1)[0]
        assert 'Visibility="{Binding ToastVisible' in toast, "the toast moved; update this test"
        assert 'IsHitTestVisible="False"' in toast, \
            "the toast must let the mouse (and UI Automation's hit test) through to the page under it"

    def test_a_sprint_starting_brings_the_ring_and_its_end_button_into_view(self):
        handler = TestScheduledSprintsGoThroughStart.member(
            TestScheduledSprintsGoThroughStart.code(self.TODAY_CS), "private void OnViewModelChanged(")
        assert "nameof(TodayViewModel.IsRunning)" in handler and "PageScroll.ScrollToTop()" in handler, \
            "Today must scroll back to the top when a sprint starts"
        assert '<ScrollViewer x:Name="PageScroll"' in self.TODAY_XAML.read_text(encoding="utf-8")

    @pytest.mark.ui
    def test_sealed_can_be_picked_while_the_profile_toast_is_up(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.new_profile("School")          # "Profile "School" added..." for four seconds
        fresh_app.navigate_to_tab("Today")
        assert fresh_app.toast_text(timeout=1.0), "the toast is not up, so this proves nothing"
        fresh_app.select_shield("Sealed")
        assert fresh_app.is_selected("Shield_Sealed"), "the toast took the click meant for the shield picker"

    @pytest.mark.ui
    def test_starting_from_the_intention_field_leaves_the_countdown_and_cancel_in_view(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        # The field is below the fold at the default height, so this scrolls the page down.
        fresh_app.set_text("IntentionInput", "write the report")
        fresh_app.start_sprint()
        time.sleep(1.0)
        assert fresh_app.is_on_screen("SprintTimerText"), \
            "the countdown was left scrolled up under the page header"
        fresh_app.cancel_sprint()
        time.sleep(0.8)
        assert "cancelled" in fresh_app.session_state().lower(), \
            "Cancel sprint could not be clicked where it was left"


# ============================ the taskbar Jump List starts like the tray (1.0.10, 5)

class TestTheJumpListStartsLikeTheTray:
    """
    Spec 5: the Jump List runs FlowShield.exe --start-sprint or
    --start-sprint=<templateId>, handed over at startup or through the
    single-instance pipe. It is a Start nobody pressed on Today, so it must
    reach the same gates as the tray's start (F2, the trial, terms, first run,
    F7's open-apps question), and a template deleted since the list was built
    must start nothing. Comments are stripped, so a call left only in a
    comment can't satisfy these.
    """

    MAIN = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    APP = Path(DESKTOP_DIR) / "App.xaml.cs"
    PROGRAM = Path(DESKTOP_DIR) / "Program.cs"
    SERVICE = Path(DESKTOP_DIR) / "Services" / "JumpListService.cs"
    ARG = Path(DESKTOP_DIR) / "Models" / "StartSprintArg.cs"

    @staticmethod
    def code(path: Path) -> str:
        return "\n".join(line.split("//")[0] for line in path.read_text(encoding="utf-8").splitlines())

    @staticmethod
    def member(code: str, signature: str) -> str:
        """One member's body, from its signature to the brace that closes it."""
        start = code.index(signature)
        depth = 0
        for index in range(code.index("{", start), len(code)):
            depth += {"{": 1, "}": -1}.get(code[index], 0)
            if depth == 0:
                return code[start:index + 1]
        raise AssertionError(f"no end to {signature}")

    def handler(self) -> str:
        return self.member(self.code(self.MAIN), "public void HandleStartSprintArg(IEnumerable<string> args)")

    def test_it_starts_only_through_quick_start_or_start_template(self):
        """
        No template: exactly the tray's "Start sprint (last settings)", which
        is MainWindow's QuickStart() since #270. A template: StartTemplate,
        which goes through StartSprint. Never a start of its own.
        """
        handler = self.handler()
        assert "StartSprintArg.TryFind(args, out var templateId)" in handler
        plain = handler.split("if (templateId is null)", 1)[1].split("return;", 1)[0]
        assert "QuickStartRequested?.Invoke(this, EventArgs.Empty);" in plain
        assert "Today.StartTemplate(template, skipOpenAppsPanel: false)" in handler
        for copied in ("StartCommand", "StartSprint(", "BeginRunning(", "ActiveSprint", "ApplyTemplate("):
            assert copied not in handler, f"HandleStartSprintArg uses {copied}; it must start like the tray"

        window = self.code(self.WINDOW)
        assert "newVm.QuickStartRequested += OnQuickStartRequested;" in window
        assert "oldVm.QuickStartRequested -= OnQuickStartRequested;" in window
        assert re.search(r"private void OnQuickStartRequested\(object\? sender, EventArgs e\)\s*=>\s*QuickStart\(\);",
                         window), "the Jump List's plain start is the tray's QuickStart(), not a copy"
        tray = self.member(window, "private void BuildTrayMenu(")
        assert "(_, _) => QuickStart());" in tray, "the tray's start item is the same QuickStart()"

    def test_a_template_waits_for_the_terms_and_the_welcome_and_brings_f7s_question_forward(self):
        """
        StartTemplate fills in Today (length, shield, profile) before Start's
        gates are asked, so under the terms gate or the welcome it would change
        what they are setting up. The guard sits before the template is even
        looked up: a stale entry after Delete everything must not switch the
        page and toast under the terms gate or the welcome either (review).
        And a start waiting on F7's question is brought forward the way quick
        start and a schedule bring it (#270).
        """
        handler = self.handler()
        guard = handler.index("if (TermsGateVisible || FirstRun.IsVisible)")
        assert guard < handler.index("Settings.FindTemplate("), "the gates come before the lookup"
        assert guard < handler.index("Today.StartTemplate(")
        assert "return;" in handler[guard:handler.index("Settings.FindTemplate(")]
        asked = handler.split("&& Today.RunningAppsPanelVisible)", 1)[1]
        assert "CurrentPage = AppPage.Today;" in asked
        assert "OpenAppsQuestionRaised?.Invoke(this, EventArgs.Empty);" in asked

    def test_a_template_that_is_gone_toasts_and_starts_nothing(self):
        """Review focus 5: a dangling Jump List entry falls back to Today with a calm toast."""
        handler = self.handler()
        assert "var template = Settings.FindTemplate(templateId);" in handler
        missing = handler.split("if (template is null)", 1)[1].split("return;", 1)[0]
        assert "CurrentPage = AppPage.Today;" in missing
        assert 'Toast("That template isn\'t here any more. Pick one on Today.");' in missing
        assert "StartTemplate(" not in missing and "QuickStart" not in missing

    def test_a_template_during_a_sprint_a_break_or_f7s_question_says_so_and_starts_nothing(self):
        """
        StartTemplate returns false while a sprint or a break runs, which left
        a taskbar click with nothing visible (review). A calm toast now says
        why. And with F7's question already up for a Start pressed by hand,
        the entry is refused as a schedule is (OnScheduleAction): the person
        is answering it, and a template would change what they asked for.
        The missing-template toast still comes first.
        """
        handler = self.handler()
        lookup, start = handler.index("var template = Settings.FindTemplate("), handler.index("Today.StartTemplate(")

        running = handler.split("if (IsSprintRunning)", 1)[1].split("return;", 1)[0]
        assert 'Toast("A sprint is already running.");' in running
        on_break = handler.split("if (Today.IsOnBreak)", 1)[1].split("return;", 1)[0]
        assert 'Toast("You\'re on a break. Start now from Today.");' in on_break
        asked = handler.split("if (Today.RunningAppsPanelVisible)", 1)[1].split("return;", 1)[0]
        assert "Log.Info(" in asked and "Toast(" not in asked, "refused quietly, as a schedule is"
        for block in (running, on_break, asked):
            assert "StartTemplate(" not in block and "QuickStart" not in block

        for check in ("if (IsSprintRunning)", "if (Today.IsOnBreak)", "if (Today.RunningAppsPanelVisible)"):
            assert lookup < handler.index(check) < start, f"{check} sits between the lookup and the start"

    def test_a_hand_over_mid_quit_cannot_reach_the_closed_window(self):
        """
        A second launch can arrive down the pipe while Quit is closing the
        window. OnClosing drops every handler a --start-sprint could reach:
        the quick start, F7's question (BringToFront, then Show on a closed
        window) and the start's notification (review).
        """
        closing = self.member(self.code(self.WINDOW), "protected override void OnClosing(CancelEventArgs e)")
        for handler in ("QuickStartRequested -= OnQuickStartRequested;",
                        "OpenAppsQuestionRaised -= OnOpenAppsQuestionRaised;",
                        "NotificationRequested -= OnNotificationRequested;"):
            assert f"currentVm.{handler}" in closing, handler
            assert closing.index(handler) < closing.index("base.OnClosing(e);")

    def test_app_hands_the_argument_over_at_startup_and_from_a_second_launch(self):
        app = self.code(self.APP)
        start = app.index("Instance?.Listen(") + len("Instance?.Listen")
        depth = 0
        for end in range(start, len(app)):
            depth += {"(": 1, ")": -1}.get(app[end], 0)
            if depth == 0:
                break
        listen, after = app[start:end], app[end:]
        assert "ViewModel.HandleStartSprintArg(launchArgs);" in listen, "a launch while Basalt runs"
        assert "ViewModel.HandleStartSprintArg(args);" in after, "a cold launch from the Jump List"
        assert app.index("window.Show();") < app.index("ViewModel.RebuildJumpList();")
        # #275's retry is for --reset; every other argument, --start-sprint
        # included, goes down the pipe exactly as it came.
        program = self.code(self.PROGRAM)
        assert "SingleInstance.SendToRunningInstance(args)" in program

    def test_the_list_follows_the_templates(self):
        main = self.code(self.MAIN)
        ctor = self.member(main, "public MainViewModel(")
        assert "Schedule.TemplatesChanged += (_, _) => RebuildJumpList();" in ctor
        rebuild = self.member(main, "public void RebuildJumpList()")
        assert "JumpListService.Rebuild(Settings.Templates, exe);" in rebuild

    def test_the_list_is_wpfs_jump_list_and_never_the_registry(self):
        """
        A per-user shell feature: no registry, no admin, and a machine without
        a taskbar (or a shell that refuses) costs the shortcut, never the app.
        """
        service = self.SERVICE.read_text(encoding="utf-8")
        code = self.code(self.SERVICE)
        assert "using System.Windows.Shell;" in code
        assert "new JumpList" in code and "new JumpTask" in code
        # SetJumpList applies the list itself; a second Apply() was one more
        # shell round-trip per template change (review).
        assert "JumpList.SetJumpList(Application.Current, list);" in code
        assert ".Apply();" not in code, "SetJumpList already applies the list"
        for registry in ("Registry", "Microsoft.Win32"):
            assert registry not in service, f"the Jump List must never touch {registry}"
        rebuild = self.member(code, "public static void Rebuild(")
        assert rebuild.index("try") < rebuild.index("new JumpList")
        assert "catch (Exception ex)" in rebuild and "Log.Warn(" in rebuild
        # The argument is written by the class that reads it back.
        assert "Arguments = StartSprintArg.Flag," in code
        assert "StartSprintArg.For(t.Id)" in code

    def test_the_list_leaves_a_trace_and_a_rejected_entry_is_not_silent(self):
        """
        The shell drops an entry it refuses (a path it cannot resolve, a bad
        icon) through JumpItemsRejected, which nothing handled, so an empty
        list on some machine left no trace. Now it is a Warn naming how many
        and why, and a healthy apply logs its entry count, which tier 3 reads
        back (templates + 1).
        """
        rebuild = self.member(self.code(self.SERVICE), "public static void Rebuild(")
        applied = rebuild.index("JumpList.SetJumpList(Application.Current, list);")
        rejected = rebuild.index("list.JumpItemsRejected +=")
        assert rejected < applied, "subscribe before the one apply, or the first rejection is missed"
        handler = rebuild[rejected:applied]
        assert "Log.Warn(" in handler and "e.RejectedItems.Count" in handler and "e.RejectionReasons" in handler
        assert 'Log.Info($"jump list: {list.JumpItems.Count} entries");' in rebuild[applied:]

    def test_an_ampersand_in_a_template_name_is_not_doubled(self):
        """
        A JumpTask title is drawn as written, so escaping & as && showed
        "Maths && Physics" on Windows 11 (VM, 1.0.11). The title comes from
        JumpListText, which tier 1 probes; the tooltip stays as typed.
        """
        code = self.code(self.SERVICE)
        assert "Title = JumpListText.Title(t.Name)," in code
        assert 'Description = $"{t.SprintMinutes} minutes at {t.Shield}",' in code
        text = self.code(Path(DESKTOP_DIR) / "Models" / "JumpListText.cs")
        assert '"&&"' not in self.member(text, "public static string Title(")

    def test_the_new_copy_keeps_to_the_house_voice(self):
        """DESIGN_SYSTEM 9: no exclamation marks, and ASCII-only C# literals."""
        texts = [self.handler(), self.SERVICE.read_text(encoding="utf-8"), self.ARG.read_text(encoding="utf-8"),
                 (Path(DESKTOP_DIR) / "Models" / "JumpListText.cs").read_text(encoding="utf-8")]
        for text in texts:
            for literal in re.findall(r'"[^"\n]*"', text):
                assert "!" not in literal, literal
                assert literal.isascii(), literal


# ================================ Delete everything clears the Jump List (#311)

class TestDeleteEverythingClearsTheJumpList:
    """
    #311: the Jump List puts each template's name and length in a file Windows
    keeps in the user profile, outside the encrypted settings. Delete
    everything removed the settings and logs and relaunched with --reset, so
    the old names went only if the relaunch rebuilt the list, and a relaunch
    can fail. Now the deleting process empties the list itself: after the
    delete, before the relaunch, and nothing rebuilds it from the in-memory
    settings before the process ends. Comments are stripped, so a call left
    only in a comment can't satisfy these.
    """

    SETTINGS_VM = Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs"
    MAIN = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    SERVICE = Path(DESKTOP_DIR) / "Services" / "JumpListService.cs"
    PRIVACY = Path(DESKTOP_DIR) / "Services" / "DataPrivacyService.cs"

    code = staticmethod(TestTheJumpListStartsLikeTheTray.code)
    member = staticmethod(TestTheJumpListStartsLikeTheTray.member)

    def test_the_delete_clears_the_list_after_the_files_go_and_before_the_relaunch(self):
        code = self.code(self.SETTINGS_VM)
        assert "JumpListService.Clear();" in code, "Delete everything must clear the Jump List"
        delete = self.member(code, "private async Task DeleteEverythingAsync()")
        assert delete.count("JumpListService.Clear();") == 1
        deleted = delete.index("await DataPrivacyService.DeleteEverythingAsync(")
        cleared = delete.index("JumpListService.Clear();")
        relaunch = delete.index("_main.RestartToFirstRun();")
        assert deleted < cleared < relaunch, "clear after the files are gone and before the relaunch"
        # Not in the catch: a failed delete keeps its list and says so, as before.
        failed = delete.index("catch (Exception ex)")
        assert delete.index("return;", failed) < cleared, "the clear runs only once the delete succeeded"
        # The WPF call stays out of the service that removes the files.
        privacy = self.code(self.PRIVACY)
        assert "System.Windows" not in privacy and "JumpList" not in privacy

    def test_the_clear_applies_an_empty_list_and_catches_its_own_failure(self):
        code = self.code(self.SERVICE)
        assert "public static void Clear()" in code, "JumpListService.Clear() is missing"
        clear = self.member(code, "public static void Clear()")
        applied = clear.index("JumpList.SetJumpList(Application.Current,")
        assert clear.index("try") < applied
        assert "new JumpList" in clear and "JumpItems" not in clear and "JumpTask" not in clear, \
            "the cleared list is empty"
        assert 'Log.Info("jump list: cleared");' in clear[applied:]
        failed = clear[clear.index("catch (Exception ex)"):]
        assert "Log.Warn(" in failed and "throw" not in clear, "a failure costs the shortcut, never the delete"

    def test_nothing_rebuilds_the_old_list_before_the_process_ends(self):
        """
        The list is rebuilt at startup and on TemplatesChanged, both through
        RebuildJumpList, which now refuses once local data is deleted.
        RestartToFirstRun sets that flag before asking WPF to shut down, and
        the clear and the relaunch run in one turn of the UI thread.
        """
        main = self.code(self.MAIN)
        rebuild = self.member(main, "public void RebuildJumpList()")
        assert "if (SkipSaveOnExit) return;" in rebuild, "no rebuild from the deleted settings"
        assert rebuild.index("if (SkipSaveOnExit) return;") < rebuild.index("JumpListService.Rebuild(")
        restart = self.member(main, "public void RestartToFirstRun()")
        assert restart.index("SkipSaveOnExit = true;") < restart.index("Application.Current.Shutdown();")

        # RebuildJumpList is the only way to Rebuild, so its guard covers them all.
        callers = [path.name for path in Path(DESKTOP_DIR).rglob("*.cs")
                   if not {"bin", "obj"} & set(path.relative_to(DESKTOP_DIR).parts)
                   and "JumpListService.Rebuild(" in self.code(path)]
        assert callers == ["MainViewModel.cs"], callers
        assert main.count("JumpListService.Rebuild(") == 1

    def test_the_confirmation_names_everything_it_removes(self):
        """
        The dialog listed sessions, journal, blocklist, momentum and licence,
        and left out the templates, schedules and profiles that go too, and
        now the taskbar list (owner ruling on #311). One calm sentence for
        what goes, no exclamation marks, and an id tier 3 can read it by.
        """
        xaml = (Path(DESKTOP_DIR) / "Views" / "ConfirmDeleteDialog.xaml").read_text(encoding="utf-8")
        detail = re.search(r'<TextBlock x:Name="DetailText" Text="([^"]*)"', xaml)
        assert detail, "the dialog's detail text is missing"
        removes = detail.group(1).split(". ")[0]
        assert removes.startswith("This removes your "), removes
        for what in ("sessions", "journal", "blocklist profiles", "templates", "schedules",
                     "momentum", "license", "taskbar Jump List"):
            assert what in removes, f"the confirmation doesn't say {what} goes: {removes}"
        assert "!" not in detail.group(1)
        assert 'AutomationProperties.AutomationId="ConfirmDeleteDetailText"' in xaml


# ==================== the scheduler's tick is not starved at Background priority (#316)

class TestTheSchedulerTickIsNotStarved316:
    """
    #316: on the 1.0.10 VM run a scheduled sprint started 57 s after its time,
    though the scheduler ticks every 15 s. Its DispatcherTimer ran at WPF's
    default Background priority, below input, rendering and the calls that
    serve UI Automation, so a busy UI thread held its ticks back. A stall past
    SchedulePlanner.OnTime (1 minute) turns the promised start into "You
    missed ...". Comments are stripped, so a call left only in a comment
    can't satisfy these.
    """

    SERVICE = Path(DESKTOP_DIR) / "Services" / "ScheduleService.cs"

    # Every DispatcherPriority that runs ahead of Background (WPF's order).
    ABOVE_BACKGROUND = ("Input", "Loaded", "Render", "DataBind", "Normal", "Send")

    code = staticmethod(TestTheJumpListStartsLikeTheTray.code)
    member = staticmethod(TestTheJumpListStartsLikeTheTray.member)

    def test_the_timer_runs_above_background_priority(self):
        code = self.code(self.SERVICE)
        made = re.findall(r"new(?:\s+DispatcherTimer)?\s*\(([^)]*)\)", code.split("_timer =", 1)[1].split(";", 1)[0])
        assert made, "ScheduleService's timer is not constructed where expected"
        priority = re.fullmatch(r"\s*DispatcherPriority\.(\w+)\s*", made[0])
        assert priority, "new DispatcherTimer() with no priority runs at Background, below input and UIA"
        assert priority.group(1) in self.ABOVE_BACKGROUND, f"the timer runs at {priority.group(1)}"
        assert code.count("DispatcherTimer") == 1, "one timer, the one pinned here"

    def test_a_clock_change_is_still_read_before_a_tick_already_due(self):
        """
        Before #316 the zone cache was cleared at Normal, ahead of the
        Background tick. With the tick at Normal too, that order holds only
        if the clear goes in at the one priority above it.
        """
        code = self.code(self.SERVICE)
        changed = code[code.index("private void OnTimeChanged(object? sender, EventArgs e)"):]
        changed = changed[:changed.index(";") + 1]
        assert "_timer.Dispatcher.BeginInvoke(DispatcherPriority.Send, ClockChanged)" in changed

    def test_a_late_tick_is_logged_once_and_on_time_ticks_are_quiet(self):
        """
        So the next VM run can tell a starved timer from a clock step: late is
        measured on the monotonic tick count the DispatcherTimer itself uses,
        which a clock step doesn't move, and only past 5 s.
        """
        code = self.code(self.SERVICE)
        assert "_timer.Tick += (_, _) => OnTimerTick();" in code, "the timer's tick goes through the lateness check"
        assert re.search(r"LateTickThreshold\s*=\s*TimeSpan\.FromSeconds\(5\);", code)

        fired = self.member(code, "private void OnTimerTick()")
        assert "Environment.TickCount64" in fired and "DateTime.UtcNow - " not in fired
        logged = re.search(r"if \(late > LateTickThreshold\)\s*Log\.Info\(\$\"schedule tick \{[^}]+\} s late\"\);", fired)
        assert logged, "one line, only when the tick is more than 5 s late"
        assert fired.count("Log.") == 1, "on-time ticks log nothing"
        assert fired.index("Log.Info(") < fired.index("Tick(DateTime.UtcNow);"), "logged before the tick acts"

        # The count restarts wherever the timer does, so the first tick isn't late by the whole launch.
        start = self.member(code, "public void Start()")
        assert start.index("_dueMs = ") < start.index("_timer.Start();")
        assert "_dueMs = " in fired[fired.index("Tick(DateTime.UtcNow);"):], "the next tick is due from this one's end"

        # The planner's own entry point stays silent per tick.
        assert "Log.Info(" not in self.member(code, "public void Tick(DateTime nowUtc)")


# ==================== the sprint clock is not starved at Background priority (#319)

class TestTheSprintClockIsNotStarved319:
    """
    #319, found while fixing #316: Today's one clock (the sprint's countdown,
    its heartbeat and time-up, the break's countdown) was a DispatcherTimer at
    WPF's default Background priority, below input, rendering and the calls
    that serve UI Automation. On a busy UI thread its ticks can be held back
    for a minute: a heartbeat gap past WatchedStretchCap under-counts watched
    time, and an End click handled before a late time-up tick records a
    finished sprint as ended early. Comments are stripped, so a call left only
    in a comment can't satisfy these.
    """

    VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"

    ABOVE_BACKGROUND = TestTheSchedulerTickIsNotStarved316.ABOVE_BACKGROUND

    code = staticmethod(TestTheJumpListStartsLikeTheTray.code)
    member = staticmethod(TestTheJumpListStartsLikeTheTray.member)

    def test_the_clock_runs_above_background_priority(self):
        code = self.code(self.VM)
        made = code.split("_tick = new", 1)
        assert len(made) == 2, "TodayViewModel's clock is not constructed where expected"
        args = re.match(r"(?:\s+DispatcherTimer)?\s*\(([^)]*)\)", made[1])
        assert args, "new DispatcherTimer { ... } with no priority runs at Background, below input and UIA"
        priority = re.fullmatch(r"\s*DispatcherPriority\.(\w+)\s*", args.group(1))
        assert priority, "the clock's priority must be given to its constructor"
        assert priority.group(1) in self.ABOVE_BACKGROUND, f"the clock runs at {priority.group(1)}"
        assert code.count("new DispatcherTimer") == 1, "one clock, the one pinned here"

    def test_a_late_tick_is_logged_once_and_on_time_ticks_are_quiet(self):
        """
        The same line #316 added for the scheduler: late is measured on the
        monotonic count the DispatcherTimer itself uses, so a clock step
        doesn't show as lateness, and only past 5 s.
        """
        code = self.code(self.VM)
        assert "_tick.Tick += (_, _) => OnTimerTick();" in code, "the clock's tick goes through the lateness check"
        assert re.search(r"LateTickThreshold\s*=\s*TimeSpan\.FromSeconds\(5\);", code)

        fired = self.member(code, "private void OnTimerTick()")
        assert "Environment.TickCount64" in fired and "DateTime.UtcNow" not in fired
        logged = re.search(r"if \(late > LateTickThreshold\)\s*Log\.Info\(\$\"sprint tick \{[^}]+\} s late\"\);", fired)
        assert logged, "one line, only when the tick is more than 5 s late"
        assert fired.count("Log.") == 1, "on-time ticks log nothing"
        assert fired.index("Log.Info(") < fired.index("OnTick();"), "logged before the tick acts"
        assert "_tickDueMs = " in fired[fired.index("OnTick();"):], "the next tick is due from this one's end"

        # Every start of the clock says when its first tick is due, so the
        # first tick isn't "late" by however long the clock was stopped.
        start = self.member(code, "private void StartClock()")
        assert start.index("_tickDueMs = ") < start.index("_tick.Start();")
        assert code.count("_tick.Start();") == 1, "the clock starts only through StartClock()"

        # The tick's own work stays silent per tick.
        assert "Log." not in self.member(code, "private void OnTick()")


class TestTheRenameToBasaltKeepsWhatCustomersHave321:
    """
    #321: an earlier Windows focus app already sold as FlowShield, so the
    product became Basalt. Customers see the new name; everything a customer's
    machine or a past purchase already depends on keeps the old one. Changing
    the settings entropy or folder would make every saved setting unreadable,
    the Run value or scheme would orphan a registration, the device salt would
    count each PC as a new seat, and the Stripe tag would stop a pre-rename
    purchase being found by "resend my key".
    """

    MAIN = Path(DESKTOP_DIR) / "MainWindow.xaml"
    MAIN_CODE = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    SERVICES = Path(DESKTOP_DIR) / "Services"
    SERVER = Path(SERVER_DIR) / "server.js"
    EMAIL = Path(SERVER_DIR) / "email.js"

    code = staticmethod(TestTheJumpListStartsLikeTheTray.code)

    def test_the_window_the_tray_and_the_nav_say_basalt(self):
        window = self.MAIN.read_text(encoding="utf-8")
        assert re.search(r'<Window\b[^>]*\bTitle="Basalt"', window)
        assert re.search(r'x:Name="NavBrandText" Text="Basalt"', window)
        tray = self.code(self.MAIN_CODE)
        assert 'Text = "Basalt",' in tray, "the tray icon's tooltip"
        assert 'ShowBalloonTip(2500, "Basalt",' in tray

    def test_no_text_on_screen_still_says_flowshield(self):
        shown = re.compile(r'\b(?:Text|Content|Title|ToolTip|AutomationProperties\.Name)="([^"]*)"')
        leftovers = []
        for path in Path(DESKTOP_DIR).rglob("*.xaml"):
            for value in shown.findall(path.read_text(encoding="utf-8")):
                if "FlowShield" in value:
                    leftovers.append(f"{path.name}: {value}")
        # A string literal with a space in it is prose: a toast, a dialog, a
        # log line. Identifiers ("FlowShield.v1", "FlowShield") have none.
        prose = re.compile(r'"([^"\n]*FlowShield[^"\n]*)"')
        for path in Path(DESKTOP_DIR).rglob("*.cs"):
            for value in prose.findall(self.code(path)):
                if " " in value:
                    leftovers.append(f"{path.name}: {value}")
        assert not leftovers, leftovers

    def test_the_site_says_basalt_outside_links_and_the_changelog_note(self):
        class Text(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts = []

            def handle_data(self, data):
                self.parts.append(data)

        for page in Path(WEBSITE_DIR).glob("*.html"):
            parser = Text()
            parser.feed(page.read_text(encoding="utf-8"))
            text = " ".join(parser.parts)
            if page.name == "changelog.html":
                # The one place the old name belongs: saying it changed.
                text = text.replace("Basalt was called FlowShield", "")
                text = text.replace("FlowShield is now called Basalt", "")
                text = text.split("1.0.10", 1)[0]
            assert "FlowShield" not in text, page.name
        assert "<title>Basalt" in (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")

    def test_what_a_customers_machine_depends_on_keeps_the_old_name(self):
        settings = (self.SERVICES / "SettingsService.cs").read_text(encoding="utf-8")
        assert 'EntropyLabel = "FlowShield.v1";' in settings, "saved settings must stay readable"
        assert settings.count('"FlowShield");') == 2, "the settings folder and its legacy path"
        assert 'ValueName = "FlowShield";' in (self.SERVICES / "StartupEntry.cs").read_text(encoding="utf-8")
        assert 'Salt = "FlowShield.device.v1";' in (self.SERVICES / "DeviceIdentity.cs").read_text(encoding="utf-8")
        assert 'Scheme = "flowshield";' in (self.SERVICES / "DeepLink.cs").read_text(encoding="utf-8")
        assert '"FlowShield", "logs"' in (self.SERVICES / "Log.cs").read_text(encoding="utf-8")
        assert r'KeyPath = @"Software\FlowShield\Trial";' in (self.SERVICES / "TrialRecord.cs").read_text(
            encoding="utf-8"
        ), "a new key would hand everyone a fresh trial"
        project = (Path(DESKTOP_DIR) / "FlowShield.csproj").read_text(encoding="utf-8")
        assert "<AssemblyName>FlowShield</AssemblyName>" in project, "the installed exe and the update feed"
        release = (Path(DESKTOP_DIR).parent / "tools" / "build_release.ps1").read_text(encoding="utf-8")
        assert "--packId FlowShield" in release, "a new id would strand every install on its old version"
        assert "--packTitle 'Basalt'" in release, "the Start menu and Installed apps show the new name"

    def test_the_server_names_basalt_but_still_finds_flowshield_purchases(self):
        server = self.SERVER.read_text(encoding="utf-8")
        assert "const APP_NAME = 'Basalt';" in server
        assert "const APP_ID = 'FlowShield';" in server
        assert "payment.metadata?.app !== APP_ID" in server
        tags = re.findall(r"\bapp: (\w+)", server)
        assert tags and set(tags) == {"APP_ID"}, f"every purchase is tagged with the old id: {tags}"
        assert "const APP_NAME = 'Basalt';" in self.EMAIL.read_text(encoding="utf-8")


# ============ Delete everything must not restart the free trial (1.0.11 VM run)

class TestDeleteEverythingKeepsTheTrialStart:
    """
    On the 1.0.11 VM run, Settings → Delete everything restarted the 7-day
    trial: the start date lived only in settings.json, which the delete
    removes, so the relaunch saw a first launch. A copy now lives in the
    registry (TrialRecord.cs), the earlier of the two wins (tier 1 runs that
    rule in .NET), and nothing that deletes local data touches the copy.
    Comments are stripped, so a call left only in a comment can't satisfy these.
    """

    MAIN = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    APP = Path(DESKTOP_DIR) / "App.xaml.cs"
    PRIVACY = Path(DESKTOP_DIR) / "Services" / "DataPrivacyService.cs"
    SETTINGS_SERVICE = Path(DESKTOP_DIR) / "Services" / "SettingsService.cs"
    RECORD = Path(DESKTOP_DIR) / "Services" / "TrialRecord.cs"
    DIALOG = Path(DESKTOP_DIR) / "Views" / "ConfirmDeleteDialog.xaml"

    code = staticmethod(TestTheJumpListStartsLikeTheTray.code)
    member = staticmethod(TestTheJumpListStartsLikeTheTray.member)

    def test_startup_reads_the_record_before_settling_the_trial_and_writes_it_back(self):
        ctor = self.member(self.code(self.MAIN), "public MainViewModel(")
        read = ctor.index("var recordedTrialStart = TrialRecord.Read();")
        ensure = ctor.index("Settings.EnsureTrialStarted(recordedTrialStart)")
        write = ctor.index("TrialRecord.Write(trialStart);")
        assert read < ensure < write, "read the record, settle the start, then write the copy back"

    def test_the_record_is_per_user_and_never_needs_admin(self):
        record = self.code(self.RECORD)
        assert "Registry.CurrentUser" in record and "Registry.LocalMachine" not in record, \
            "CLAUDE.md: no admin rights, so the record lives in HKCU"
        assert '@"Software\\FlowShield\\Trial"' in record, \
            "keep the internal name, or a rename resets everyone's trial"
        # A broken registry must never stop the app starting.
        for method in ("public static DateTime? Read()", "public static void Write("):
            body = self.member(record, method)
            assert "catch (Exception ex)" in body and "throw" not in body, method

    def test_nothing_that_deletes_local_data_removes_the_record(self):
        """Delete everything and --reset (its relaunch) must both leave it."""
        for path in (self.PRIVACY, self.SETTINGS_SERVICE, self.APP):
            code = self.code(path)
            assert "TrialRecord" not in code and "DeleteValue" not in code \
                and "DeleteSubKey" not in code, f"{path.name} must not remove the trial record"
        users = sorted(path.name for path in Path(DESKTOP_DIR).rglob("*.cs")
                       if not {"bin", "obj"} & set(path.relative_to(DESKTOP_DIR).parts)
                       and "TrialRecord." in self.code(path))
        assert users == ["MainViewModel.cs"], users

    def test_the_delete_dialog_says_the_trial_date_stays(self):
        xaml = self.DIALOG.read_text(encoding="utf-8")
        detail = re.search(r'<TextBlock x:Name="DetailText" Text="([^"]*)"', xaml).group(1)
        assert "free trial started stays" in detail, detail
        assert "never leaves this PC" in detail, detail

    def test_the_privacy_policy_discloses_the_record(self):
        legal = (Path(WEBSITE_DIR) / "legal.html").read_text(encoding="utf-8")
        stays = legal.split("What stays on your computer", 1)[1].split("<h3>", 1)[0]
        assert "free trial started" in stays and "Windows registry" in stays
        assert "Delete everything leaves it in place" in stays

    def test_clean_test_launches_clear_the_record_and_the_guard_restores_it(self):
        automation = Path(__file__).resolve().parents[2]
        controller = (automation / "desktop" / "app_controller.py").read_text(encoding="utf-8")
        clean = controller.split("if clean_state:", 1)[1].split("if not use_defaults:", 1)[0]
        assert "clear_trial_record()" in clean, "a clean install has no trial record either"
        guard = (automation / "core" / "settings_guard.py").read_text(encoding="utf-8")
        assert "_back_up_trial_record()" in guard.split("def back_up()", 1)[1].split("\ndef ", 1)[0]
        assert "_restore_trial_record()" in guard.split("def restore()", 1)[1].split("\ndef ", 1)[0]
