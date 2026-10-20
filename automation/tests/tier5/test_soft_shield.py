# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: soft shield."""

from __future__ import annotations
import re
from pathlib import Path
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR



# ==================== the Soft notice stays a notice (F7 / roadmap 1.7, #143)

class TestSoftOverlayNeverCloses:
    """
    Soft's promise, on its own shield chip, is that it notes distractions and
    nudges. 1.7 gives that nudge a real screen — a topmost full-screen window
    over the blocked app — and the danger of a new surface with two buttons on
    it is that one of them quietly starts closing things.

    Everything here is read from the source, because the alternative is a UI
    test that can only prove the button exists, not what it does.
    """

    BLOCKER = Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs"
    POLICY = Path(DESKTOP_DIR) / "Models" / "SoftOverlayPolicy.cs"
    OVERLAY_XAML = Path(DESKTOP_DIR) / "Views" / "SoftOverlayWindow.xaml"
    OVERLAY_CS = Path(DESKTOP_DIR) / "Views" / "SoftOverlayWindow.xaml.cs"
    MAIN_VM = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    MAIN_WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    SETTINGS = Path(DESKTOP_DIR) / "Models" / "AppSettings.cs"
    SETTINGS_VIEW = Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml"

    def test_the_overlay_never_closes_or_kills_anything(self):
        for path in (self.OVERLAY_XAML, self.OVERLAY_CS, self.POLICY):
            source = path.read_text(encoding="utf-8")
            code = "\n".join(line for line in source.splitlines()
                             if not line.strip().startswith(("///", "//", "<!--", "*")))
            for forbidden in ("CloseMainWindow", ".Kill("):
                assert forbidden not in code, (
                    f"{path.name} can close the blocked app; Soft must not"
                )

    def test_the_soft_branch_of_the_sweep_still_closes_nothing(self):
        """The regression this guards: a foreground check that grew teeth."""
        source = self.BLOCKER.read_text(encoding="utf-8")
        soft = source.split("if (!terminate)", 1)[1].split("continue;", 1)[0]
        for forbidden in ("CloseMainWindow", "Kill(", "_closingAt["):
            assert forbidden not in soft, f"the Soft branch must not {forbidden}"

    def test_the_notice_is_only_looked_for_while_soft_is_the_shield(self):
        """
        Firm and Sealed close the blocked app. Putting a full-screen panel over
        a window that is about to disappear is noise, and it would also cover
        the seconds someone has to save.
        """
        source = self.BLOCKER.read_text(encoding="utf-8")
        # Since the website notice (F10 interim, #325) the foreground is also
        # read above Soft when the profile has websites, but blocked *apps*
        # are only reported behind the same !terminate gate that separates
        # Soft from Firm, Sealed and hard kill.
        assert "ReportForeground(targets, sites, reportApps: !terminate);" in source, (
            "blocked apps must only be looked for in front while Soft is the shield"
        )
        body = source.split("private void ReportForeground", 1)[1].split("\n    }", 1)[0]
        assert "if (reportApps && !CriticalProcesses.Contains(name) && targets.TryGetValue(name, out var app))" in body

    def test_the_foreground_check_stays_timid(self):
        """
        CLAUDE.md: no hooks into other processes, no admin rights. Reading which
        window has focus and which process owns it is user-level and enough.
        """
        source = self.BLOCKER.read_text(encoding="utf-8")
        body = source.split("private void ReportForeground", 1)[1].split("\n    }", 1)[0]
        assert "GetForegroundWindow()" in body
        assert "GetWindowThreadProcessId(" in body
        for forbidden in ("SetWindowsHookEx", "WriteProcessMemory", "CreateRemoteThread",
                          "SetForegroundWindow", "OpenProcess"):
            assert forbidden not in source, f"the blocker must never call {forbidden}"

    def test_flowshields_own_windows_are_never_the_distraction(self):
        """
        Without this the notice takes focus, sees itself in the foreground, and
        closes itself — a box that flickers once and is gone.
        """
        source = self.BLOCKER.read_text(encoding="utf-8")
        body = source.split("private void ReportForeground", 1)[1].split("\n    }", 1)[0]
        assert "pid == (uint)Environment.ProcessId" in body

    def test_the_notice_never_opens_over_another_panel(self):
        source = self.MAIN_VM.read_text(encoding="utf-8")
        gate = source.split("public bool ModalPanelVisible =>", 1)[1].split(";", 1)[0]
        for panel in ("TermsGateVisible", "IsLocked", "FirstRun.IsVisible",
                      "ActivationPromptVisible", "Today.EndPanelVisible",
                      "Today.JournalPromptVisible", "Today.RunningAppsPanelVisible"):
            assert panel in gate, f"{panel} must keep the Soft notice away"

        handler = source.split("private void OnSoftForeground", 1)[1].split("\n    }", 1)[0]
        assert "if (ModalPanelVisible) return;" in handler
        assert "if (!Settings.ShowSoftOverlayEnabled) return;" in handler

    def test_back_to_work_brings_flowshield_forward_and_leaves_the_app_alone(self):
        source = self.MAIN_WINDOW.read_text(encoding="utf-8")
        block = source.split("overlay.BackToWork +=", 1)[1].split("};", 1)[0]
        assert "BringToFront()" in block
        assert "SoftOverlayBackToWork" in block
        for forbidden in ("Kill", "CloseMainWindow"):
            assert forbidden not in block

    def test_escape_is_back_to_work(self):
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        assert 'IsCancel="True"' in xaml
        code = self.OVERLAY_CS.read_text(encoding="utf-8")
        assert "Key.Escape" in code, (
            "this window is shown, not dialogued, so Escape is handled here too"
        )

    def test_the_soft_notice_is_visible_over_its_target(self):
        # Topmost is the promise: a notice that can open under the blocked
        # app is never seen. The window's chrome and style are design choices.
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        assert 'Topmost="True"' in xaml, "the notice must stay above the blocked app"
        code = self.OVERLAY_CS.read_text(encoding="utf-8")
        assert "Screen.FromHandle(_anchor)" in code, (
            "the notice must locate the blocked app's monitor")
        assert "screen.Bounds" in code and "SetWindowPos" in code, (
            "the notice must be placed over the target display")

    def test_it_covers_a_second_monitor_at_a_different_scale_factor(self):
        """
        WPF's Left/Top/Width/Height are device-independent units, scaled by the
        DPI of the monitor the window is on *at the time* -- before the move,
        whichever one Windows happened to open it on. On a 150%/100% pair that
        left the scrim over two thirds of the second screen with the desktop
        showing round the edges. Physical pixels need no conversion.
        """
        body = self.OVERLAY_CS.read_text(encoding="utf-8")
        body = body.split("private void PlaceOverTheDistraction", 1)[1].split("\n    }", 1)[0]
        assert "SetWindowPos(" in body, (
            "placement must go through SetWindowPos in the target monitor's own "
            "physical pixels"
        )
        assert "bounds.Width, bounds.Height" in body
        assert "TransformFromDevice" not in body, (
            "this is the bug: the current monitor's transform applied to another "
            "monitor's bounds"
        )
        for wpf_property in ("Left =", "Top =", "Width =", "Height ="):
            assert wpf_property not in body, (
                f"{wpf_property} is a device-independent unit and re-introduces the "
                f"mixed-DPI bug"
            )

    def test_soft_notice_has_no_motion_when_reduced_motion_is_enabled(self):
        """DESIGN_SYSTEM.md §8: motion stops when the OS reduced-motion setting is on."""
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        motion = (Path(DESKTOP_DIR) / "Infrastructure" / "Motion.cs").read_text(
            encoding="utf-8")
        assert "Motion." in xaml, "the notice must use a reduced-motion-aware duration"
        assert "SystemParameters.ClientAreaAnimation" in motion
        assert re.search(r"AnimationsEnabled\s*\?.*?:\s*0", motion, re.S), (
            "the notice's motion must stop when animations are disabled")

    def test_nothing_on_it_is_alarming(self):
        """§7: no red, no alarm icons. Strength never escalates through colour."""
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        for forbidden in ("Rose", "Amber", "Red", "IconWarning", "IconAlert"):
            assert forbidden not in xaml, f"the Soft notice must not use {forbidden}"
        assert "ShieldGlyphSoft" in xaml, "§7 asks for the shield glyph"

    def test_its_controls_carry_automation_ids_on_real_controls(self):
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        for automation_id in ("SoftOverlayText", "SoftOverlayTimeLeft",
                              "SoftOverlayBackToWorkButton", "SoftOverlayAllowButton",
                              "SoftOverlayCloseButton", "SoftOverlayIntention",
                              "SoftOverlayTryLine"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml

        # #134: an id on a layout panel is never surfaced, so it can never be found.
        for tag in re.finditer(r'<(\w+)\b((?:(?!/?>).)*?)/?>', xaml, re.S):
            element, attrs = tag.group(1), tag.group(2)
            if element in ("Grid", "StackPanel", "WrapPanel", "Border", "DockPanel", "Image") \
                    and 'AutomationId="' in attrs:
                raise AssertionError(
                    f"<{element}> has an AutomationId -- never surfaced to UI Automation")

    def test_the_setting_exists_and_is_on_by_default(self):
        settings = self.SETTINGS.read_text(encoding="utf-8")
        assert "public bool ShowSoftOverlayEnabled { get; set; } = true;" in settings, (
            "Soft's only visible intervention has to be on unless it is turned off"
        )
        view = self.SETTINGS_VIEW.read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="SoftOverlayToggle"' in view
        assert "Show a full-screen notice at Soft" in view

    def test_a_notice_cannot_outlive_the_sprint_that_raised_it(self):
        """
        The sighting is taken on the blocker's thread and handled on the
        dispatcher, so a sprint can be cancelled in between. Enforcement has
        stopped by then, so no later sighting arrives -- a notice shown here
        would stay on screen with nothing left to take it down, over whatever
        the user did next.
        """
        source = self.MAIN_VM.read_text(encoding="utf-8")
        handler = source.split("private void OnSoftForeground", 1)[1].split("\n    }", 1)[0]
        guard = " ".join(handler.split())
        assert "if (!IsSprintRunning || !Blocker.IsEnforcing)" in guard, (
            "the handler must re-check that the sprint is still running, on the "
            "dispatcher, before showing anything"
        )
        # And it has to come before the decision to show, not after it.
        assert handler.index("!Blocker.IsEnforcing") < handler.index("_softOverlay.ShouldShow")
        # The stale notice is closed, not merely skipped.
        stale = handler.split("!Blocker.IsEnforcing", 1)[1].split("return;", 1)[0]
        assert "SoftOverlayDismissRequested" in stale

    def test_an_allowance_does_not_outlive_the_sprint(self):
        source = self.MAIN_VM.read_text(encoding="utf-8")
        block = source.split("public void OnSprintStateChanged()", 1)[1].split("\n    }", 1)[0]
        assert "_softOverlay.Reset();" in block
        assert "SoftOverlayDismissRequested" in block, (
            "a notice must never outlive the shield that raised it"
        )

    def test_allowing_five_minutes_does_not_undo_the_distraction_count(self):
        """#140 counts one distraction per app per sighting; the notice changes nothing."""
        source = self.MAIN_VM.read_text(encoding="utf-8")
        block = source.split("public void SoftOverlayAllowFiveMinutes", 1)[1].split("\n    }", 1)[0]
        for forbidden in ("BlockCount", "RecordBlock", "BlocksToday"):
            assert forbidden not in block, (
                "the sighting was counted when it happened; the notice must not "
                "add to or subtract from it"
            )


class TestSoftCloseNeverKills:
    """
    1.0.10 gives Soft a Close button. Soft still never closes anything on its
    own, and a user-chosen close asks politely (CloseMainWindow) and never kills,
    so the app's own "save changes?" prompt still appears.
    """

    BLOCKER = Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs"

    def _ask_to_close(self) -> str:
        source = self.BLOCKER.read_text(encoding="utf-8")
        assert "public int AskToClose(string displayName, AppSettings settings)" in source
        return source.split("public int AskToClose(", 1)[1].split("\n    }", 1)[0]

    def test_it_only_asks(self):
        body = self._ask_to_close()
        assert "CloseMainWindow()" in body
        for forbidden in ("Kill(", "KillAll(", "_closingAt["):
            assert forbidden not in body, f"AskToClose must never {forbidden}"

    def test_it_never_touches_a_critical_process(self):
        assert "CriticalProcesses.Contains(" in self._ask_to_close()

    def test_it_is_only_reached_from_the_close_button(self):
        callers = [p for p in Path(DESKTOP_DIR).rglob("*.cs")
                   if "AskToClose(" in p.read_text(encoding="utf-8")]
        names = sorted(p.name for p in callers)
        assert names == ["AppBlockerService.cs", "MainViewModel.cs"], names

    def test_the_sweep_still_closes_nothing_at_soft(self):
        source = self.BLOCKER.read_text(encoding="utf-8")
        soft = source.split("if (!terminate)", 1)[1].split("continue;", 1)[0]
        assert "AskToClose" not in soft

    def test_zero_asked_is_explained_not_treated_as_a_failure(self):
        """
        AskToClose counts processes whose CloseMainWindow accepted the ask. An
        app hidden in the tray, or sitting behind its own save prompt, has no
        main window to close and gives 0, which is not a failure; the log says
        what it means, and a warning names the pid like the sibling lines do.
        """
        body = self._ask_to_close()
        assert "Safe(() => process.Id)" in body.split("catch (Exception ex)", 1)[1]
        caller = (Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs").read_text(encoding="utf-8") \
            .split("public void SoftOverlayCloseIt(string displayName)", 1)[1].split("\n    }", 1)[0]
        assert "asked == 0" in caller
        assert "nothing to ask" in caller


class TestSoftNoticeFriction:
    """
    1.0.10's notice (spec 4.1): Close first and primary, Back to work the
    default and keyboard action, and Allow only after a wait that grows with
    each try. The wait is enforced where the click lands, not only by how the
    button looks.
    """

    MAIN_VM = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    MAIN_WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    OVERLAY_XAML = Path(DESKTOP_DIR) / "Views" / "SoftOverlayWindow.xaml"
    OVERLAY_CS = Path(DESKTOP_DIR) / "Views" / "SoftOverlayWindow.xaml.cs"
    POLICY = Path(DESKTOP_DIR) / "Models" / "SoftOverlayPolicy.cs"

    def _button(self, automation_id: str) -> str:
        """The attributes of one button on the notice, up to its AutomationId."""
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        return xaml.split(f'AutomationProperties.AutomationId="{automation_id}"')[0].rsplit("<Button", 1)[1]

    def test_close_is_deliberate_and_back_to_work_is_the_keyboard_default(self):
        """
        The notice lands up to one blocker sweep (about 2 s) after the blocked
        app came to the front, while the user may still be typing in it. An
        Enter or Space meant for a game or a chat line must never become "the
        user chose to close it", so Close is reached by mouse or by Tab only.
        """
        close = self._button("SoftOverlayCloseButton")
        back = self._button("SoftOverlayBackToWorkButton")
        assert 'IsDefault="True"' not in close, "Enter must never choose Close"
        assert 'IsCancel="True"' not in close, "Escape must never choose Close"
        assert 'IsDefault="True"' in back, "Back to work is the safe Enter default"
        assert 'IsCancel="True"' in back, "Back to work is the safe Escape action"

    def test_back_to_work_is_the_default_the_cancel_and_the_focused_button(self):
        """Enter, Space on the focused button and Escape all mean Back to work."""
        back = self._button("SoftOverlayBackToWorkButton")
        assert "BtnPrimary" not in back
        assert 'IsDefault="True"' in back, "Enter is Back to work"
        assert 'IsCancel="True"' in back, "Escape is still Back to work"
        opened = self.OVERLAY_CS.read_text(encoding="utf-8") \
            .split("protected override void OnSourceInitialized", 1)[1].split("\n    }", 1)[0]
        assert "BackToWorkButton.Focus();" in opened, "Back to work takes the initial focus"
        assert "CloseButton.Focus()" not in opened, "a focused Close would make Space close the app"

    def test_allow_waits_before_it_can_be_pressed(self):
        code = self.OVERLAY_CS.read_text(encoding="utf-8")
        assert "AllowButton.IsEnabled = false" in code
        assert "SoftOverlayCopy.AllowLabel(" in code
        assert "DispatcherTimer" in code
        # A gate refuses where the click lands, not only by how the button
        # looks (CLAUDE.md, "covered controls"), so the handler checks too.
        handler = code.split("private void OnAllowFiveMinutes", 1)[1].split("\n    }", 1)[0]
        assert handler.index("if (!AllowButton.IsEnabled) return;") < handler.index("Answer(AllowFiveMinutes)")

    def test_the_countdown_runs_on_the_monotonic_clock(self):
        """
        A deadline on DateTime.UtcNow moves with the wall clock: set back an
        hour during the wait and Allow stays disabled for an hour. The tick
        count only ever goes forward.
        """
        code = self.OVERLAY_CS.read_text(encoding="utf-8")
        countdown = code.split("public void Configure(", 1)[1].split("protected override void OnClosed", 1)[0]
        assert "Environment.TickCount64" in countdown
        for wall_clock in ("DateTime.UtcNow", "DateTime.Now"):
            assert wall_clock not in countdown, f"the Allow deadline must not follow {wall_clock}"

    def test_the_countdown_moves_nothing(self):
        """
        Sharing a WrapPanel with Close and Back to work, Allow jumped up a row
        (and the sentence re-wrapped) the moment its countdown ended and the
        label got shorter -- a button moving just as it becomes pressable.
        """
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        row = xaml.split("<WrapPanel", 1)[1].split("</WrapPanel>", 1)[0]
        assert 'AutomationId="SoftOverlayCloseButton"' in row
        assert 'AutomationId="SoftOverlayBackToWorkButton"' in row
        assert 'AutomationId="SoftOverlayAllowButton"' not in row, "Allow sits on a line of its own"

    def test_the_notice_copy_preserves_softs_no_close_promise(self):
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        policy = self.POLICY.read_text(encoding="utf-8")
        copy = (xaml + " " + policy).lower()
        assert "closed unless you choose" in copy, (
            "Soft must explain that apps stay open unless the user chooses Close")

    def test_disabling_the_soft_notice_preserves_enforcement_and_explains_effect(self):
        """
        The switch's caption said "Nothing is closed." -- untrue once the notice
        has Close. It now reads the notice's own note, so the two can't drift.
        """
        view = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(encoding="utf-8")
        toggle = re.search(
            r'<CheckBox\b(?=[^>]*AutomationProperties\.AutomationId="SoftOverlayToggle")[^>]*>',
            view, re.S)
        assert toggle and 'IsChecked="{Binding ShowSoftOverlayEnabled}"' in toggle.group(0), (
            "the setting must control whether the notice appears")
        assert "SoftOverlayCaption" in view, "the setting must explain its effect"
        vm = (Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs").read_text(encoding="utf-8")
        assert "public bool ShowSoftOverlayEnabled" in vm
        assert "SoftOverlayCaption" in vm
        main_vm = (Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs").read_text(
            encoding="utf-8")
        assert re.search(r"if \(!Settings\.ShowSoftOverlayEnabled\) return;[\s\S]{0,200}ShouldShow", main_vm), (
            "disabling the setting must suppress the notice, not change blocker enforcement")

    def test_the_close_handler_asks_through_the_view_model_only(self):
        block = self.MAIN_WINDOW.read_text(encoding="utf-8").split("overlay.CloseIt +=", 1)[1].split("};", 1)[0]
        assert "SoftOverlayCloseIt" in block
        for forbidden in ("Kill", "CloseMainWindow", "Process"):
            assert forbidden not in block

    def test_the_view_model_counts_it_and_asks_the_blocker(self):
        source = self.MAIN_VM.read_text(encoding="utf-8")
        body = source.split("public void SoftOverlayCloseIt(string displayName)", 1)[1].split("\n    }", 1)[0]
        assert "_softOverlay.CloseIt(displayName, DateTime.UtcNow);" in body
        assert "Blocker.AskToClose(displayName, Settings)" in body

    def test_the_request_carries_intention_try_and_wait(self):
        handler = self.MAIN_VM.read_text(encoding="utf-8").split("private void OnSoftForeground", 1)[1].split("\n    }", 1)[0]
        for piece in ("SoftOverlayCopy.Intention(", "SoftOverlayCopy.TryLine(_softOverlay.Tries)",
                      "SoftOverlayPolicy.AllowWait(_softOverlay.Tries)",
                      "SoftOverlayCopy.Sentence(e.DisplayName, Today.EndsAtUtc.ToLocalTime(), _softOverlay.Tries)"):
            assert piece in handler, piece


# ============================ turned back, recorded and shown (1.0.10, spec 4.3)

class TestTurnedBackIsRecordedAndShown:
    """
    Close and Back to work on the Soft notice each count as one turned back
    (SoftOverlayPolicy.TurnedBack). The count is saved with the sprint, shown
    on its summary card and summed on History. It is a count and nothing else:
    which app was turned back from is never stored.
    """

    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    HISTORY_VM = Path(DESKTOP_DIR) / "ViewModels" / "HistoryViewModel.cs"
    MAIN_VM = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    SETTINGS = Path(DESKTOP_DIR) / "Models" / "AppSettings.cs"
    STATS = Path(DESKTOP_DIR) / "Models" / "HistoryStats.cs"
    TODAY_XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"
    HISTORY_XAML = Path(DESKTOP_DIR) / "Views" / "HistoryView.xaml"

    RECORD = "_current.TurnedBack = _main.SoftTurnedBackThisSprint;"

    def _end_sprint(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8") \
            .split("private void EndSprint(bool completed, bool interrupted = false)", 1)[1] \
            .split("\n    /// <summary>", 1)[0]

    def test_the_count_is_read_before_the_sprint_state_resets_it(self):
        """
        OnSprintStateChanged resets the Soft policy, count and all, so a read
        after it would save 0 for every sprint. Read before StopEnforcing too,
        with the other per-sprint counts, while the sprint is still the one
        that was running.
        """
        assert "_softOverlay.Reset();" in self.MAIN_VM.read_text(encoding="utf-8") \
            .split("public void OnSprintStateChanged()", 1)[1].split("\n    }", 1)[0], \
            "the reason for the order below has moved; re-check it"

        body = self._end_sprint()
        assert body.count(self.RECORD) == 1, "EndSprint must record TurnedBack exactly once"
        at = body.index(self.RECORD)
        assert at < body.index("_main.Blocker.StopEnforcing();")
        assert at < body.index("_main.OnSprintStateChanged();")
        assert at < body.index("S.Sessions.Add(_current);"), "read before the sprint is saved"

    def test_every_path_that_records_a_sprint_records_the_count(self):
        """
        Finished, ended early, and judged interrupted after a sleep (#203) all
        go through EndSprint; the count sits with the other per-sprint counts,
        before any branch, so none of them can skip it.
        """
        body = self._end_sprint()
        start = body.index("_current.Completed = completed;")
        between = body[start:body.index(self.RECORD)]
        assert "if (" not in between and "return" not in between, \
            "TurnedBack must be recorded unconditionally, on every path through EndSprint"

    def test_the_card_shows_the_line_only_above_zero(self):
        card = self.TODAY_VM.read_text(encoding="utf-8") \
            .split("private void UpdateSummaryCard(", 1)[1].split("\n    }", 1)[0]
        assert "SummaryTurnedBackText = HistoryStats.TurnedBackText(session.TurnedBack);" in card
        assert "SummaryTurnedBackVisible = session.TurnedBack > 0;" in card

    def test_history_sums_it_from_the_sessions_in_one_wording(self):
        stats = self.STATS.read_text(encoding="utf-8")
        week = stats.split("public static Week ForWeek", 1)[1].split("\n    }", 1)[0]
        assert "inWeek.Sum(s => s.TurnedBack)" in week
        vm = self.HISTORY_VM.read_text(encoding="utf-8")
        assert "WeekTurnedBackText = HistoryStats.TurnedBackText(week.TurnedBack);" in vm

    def test_only_a_count_is_stored_never_which_app(self):
        """
        The existing design choice in HistoryStats.MostBlocked: a sprint
        records how many, never which app. So TurnedBack is an int, and
        FocusSession gains no text or list that could hold an app's name.
        """
        model = self.SETTINGS.read_text(encoding="utf-8")
        session = model.split("public class FocusSession", 1)[1].split("\n}", 1)[0]
        assert "public int TurnedBack { get; set; }" in session
        stored = re.findall(r"public\s+([\w<>?,\[\] ]+?)\s+(\w+)\s*\{\s*get;", session)
        text_or_lists = {name for type_, name in stored
                         if re.search(r"string|List|\[\]|IEnumerable|Dictionary|Set<", type_)}
        assert text_or_lists == {"Intention", "Journal"}, (
            f"FocusSession stores text or a list beyond the intention and journal: {sorted(text_or_lists)}"
        )

    def test_both_lines_are_ids_on_real_text_blocks_and_hidden_at_zero(self):
        today = self.TODAY_XAML.read_text(encoding="utf-8")
        card = today[today.find("sprint summary"):]
        card = card[:card.find("journal prompt")]
        assert 'AutomationProperties.AutomationId="SummaryTurnedBackText"' in card, \
            "the summary card has no turned-back line"
        line = card.split('AutomationProperties.AutomationId="SummaryTurnedBackText"', 1)[0].rsplit("<", 1)[1]
        assert line.startswith("TextBlock"), "the id must sit on the TextBlock itself (#134)"
        assert 'Text="{Binding SummaryTurnedBackText}"' in line
        assert 'Visibility="{Binding SummaryTurnedBackVisible, Converter={StaticResource BoolVis}}"' in line
        assert card.index("SummaryDistractionsValue") < card.index("SummaryTurnedBackText"), \
            "the line sits under the distractions line"

        history = self.HISTORY_XAML.read_text(encoding="utf-8")
        distractions = history.split('Text="DISTRACTIONS CAUGHT"', 1)[1].split("</Border>", 1)[0]
        assert 'AutomationProperties.AutomationId="HistoryTurnedBackText"' in distractions, \
            "History's distractions card has no turned-back line"
        line = distractions.split('AutomationProperties.AutomationId="HistoryTurnedBackText"', 1)[0] \
            .rsplit("<", 1)[1]
        assert line.startswith("TextBlock"), "the id must sit on the TextBlock itself (#134)"
        assert 'Text="{Binding WeekTurnedBackText}"' in line
        assert 'Visibility="{Binding WeekTurnedBackText, Converter={StaticResource NonEmptyVis}}"' in line
