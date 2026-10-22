# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 3: breaks schedule."""

from __future__ import annotations
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
import pytest
from core import state_verifier as verify
from desktop.app_controller import _automation_id_condition, _uia
from ._helpers import flowshield_pids, launch_again

pytestmark = pytest.mark.ui



# ==================================================== breaks and cycles (F5)
#
# Written for F5 but NOT run in this session: UI tests take over the screen,
# only one can run at a time on this machine, and the orchestrator schedules
# them. See the PR description.

class TestBreaksAndCycles:
    """
    A two-sprint cycle, end to end, with five-second sprints and three-second
    breaks (--short-sprints and --short-timers).

    The point of the test is the one thing only a real run can show: that a
    blocked app launched *during* the break is left alone, and closed again as
    soon as the next sprint starts. Everything else about the state machine is
    tier 1's job.
    """

    TARGET = "flowshield-test-target"

    @staticmethod
    def _start(logger, **launch):
        from config import APP_EXE
        from desktop.app_controller import DesktopController

        if not Path(APP_EXE).exists():
            pytest.skip(f"{APP_EXE} not built")

        ctrl = DesktopController(logger)
        ctrl.launch_app(clean_state=True, **launch)
        ctrl.connect_window()
        time.sleep(1.0)
        ctrl.focus(force=True)
        return ctrl

    @pytest.fixture
    def cycle_app(self, logger):
        """Five-second sprints and three-second breaks: a whole cycle in seconds."""
        ctrl = self._start(logger, extra_args=["--short-sprints"])
        yield ctrl
        ctrl.close_app()

    @pytest.fixture
    def long_break_app(self, logger):
        """
        Five-second sprints, but a real five-minute break.

        use_defaults drops the launcher's own --short-timers, which is what
        makes the break long enough to watch a blocked app live through it.
        """
        ctrl = self._start(logger, use_defaults=True, extra_args=["--short-sprints"])
        yield ctrl
        ctrl.close_app()

    def _decoy(self, tmp_path, suffix=""):
        """A quiet blocked app: a copy of ping, as the tests above do."""
        import shutil
        exe = tmp_path / f"{self.TARGET}{suffix}.exe"
        if not exe.exists():
            shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "PING.EXE", exe)
        return subprocess.Popen(
            [str(exe), "-n", "300", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_a_completed_sprint_offers_a_break(self, cycle_app):
        cycle_app.navigate_to_tab("Today")
        cycle_app.select_sprint_length(15)
        cycle_app.start_sprint()

        # Five seconds later the sprint finishes on its own.
        assert cycle_app.exists("BreakPanelTitle", timeout=20), \
            "a completed sprint must offer a break"
        assert cycle_app.text_of("BreakPanelTitle") == "Take a break"
        assert "5 minutes" in cycle_app.text_of("BreakPanelText")
        for control in ("StartBreakButton", "SkipBreakButton", "StartNextSprintButton"):
            assert cycle_app.exists(control, timeout=3), f"{control} is missing from the card"

    def test_a_sprint_ended_early_offers_no_break(self, fresh_app):
        """A normal 15-minute sprint, ended by hand after its grace period."""
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_sprint_length(15)
        fresh_app.start_sprint()
        fresh_app.stop_sprint()
        time.sleep(1.0)

        assert fresh_app.exists("SummaryTitle", timeout=5), "the summary card should be up"
        assert not fresh_app.exists("StartBreakButton", timeout=2), \
            "ending early must not be rewarded with a break"

    def test_nothing_is_blocked_during_the_break(self, long_break_app, tmp_path):
        app = long_break_app
        app.navigate_to_tab("Blocked Apps")
        assert app.add_blocked_app(self.TARGET)
        time.sleep(0.6)

        app.navigate_to_tab("Today")
        app.select_shield("Firm")
        app.select_sprint_length(15)
        # No decoy exists yet. Do not let the driver's usual auto-answer hide
        # an unexpected F7 question on this first start (#249).
        app.start_sprint(confirm_open_apps=False)
        assert not app.answer_open_apps_question(), \
            "F7 asked about an open app before the test created its decoy"

        # Five seconds later the sprint finishes and the break is offered.
        assert app.exists("StartBreakButton", timeout=20)
        app.click("StartBreakButton")
        time.sleep(1.0)
        assert app.text_of("BreakPanelTitle") == "On a break"

        # The shield is down: a blocked app may be opened and must survive. The
        # blocker sweeps every two seconds, so twelve is several chances to fail.
        process = self._decoy(tmp_path)
        try:
            deadline = time.time() + 12
            while time.time() < deadline:
                assert process.poll() is None, \
                    "a blocked app was closed during a break; the shield must be down"
                time.sleep(1)

            # And the shield comes straight back up with the next sprint. The
            # decoy is still running, so StartSprint's F7 gate (Blocked Apps
            # already open) fires just like it does from the Start button —
            # answer it the same way start_sprint() does, or the sprint never
            # actually starts and nothing is ever enforced.
            app.click("StartNextSprintButton")
            answered = app.answer_open_apps_question()
            assert answered, "the open-apps question should be answered"
            deadline = time.time() + 10
            warning = ""
            while time.time() < deadline:
                try:
                    warning = app.text_of("ToastText", timeout=0.4)
                except Exception:
                    warning = ""
                if "closing in" in warning.lower():
                    break
                time.sleep(0.2)
            assert "closing in" in warning.lower(), "the shield should warn before closing the app"
        finally:
            if process.poll() is None:
                process.kill()

    def test_a_two_sprint_cycle_runs_itself(self, cycle_app):
        """Five-second sprints and three-second breaks: about fifteen seconds."""
        cycle_app.navigate_to_tab("Today")
        cycle_app.select_sprint_length(15)
        cycle_app.choose("Cycle_2")
        time.sleep(0.4)
        cycle_app.start_sprint()

        assert cycle_app.text_of("CycleProgressText", timeout=5) == "Sprint 1 of 2"

        # Sprint 1 finishes, a three-second break runs itself, and sprint 2
        # starts with no click at all.
        deadline = time.time() + 30
        seen_second = False
        while time.time() < deadline:
            try:
                if cycle_app.text_of("CycleProgressText", timeout=1) == "Sprint 2 of 2":
                    seen_second = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        assert seen_second, "the cycle did not start its second sprint by itself"

        # The cycle stops at two. Nothing is checked in Sessions here on
        # purpose: --short-sprints records nothing at all, which is exactly what
        # stops that flag from buying momentum, a streak day or a goal (tier 5's
        # TestShortSprintsCannotBuyCredit). What a real run proves is that the
        # cycle ends rather than rolling into a third sprint.
        deadline = time.time() + 30
        while time.time() < deadline and cycle_app.exists("StopSprintButton", timeout=1):
            time.sleep(1)

        time.sleep(8)
        assert not cycle_app.exists("StopSprintButton", timeout=2), \
            "the cycle must stop after its last sprint, not roll on"
        # text_of() raises rather than returning a falsy value when the control
        # is gone, so the "label gone" case has to be checked with exists()
        # first rather than relying on `or` to short-circuit past a raise.
        if cycle_app.exists("CycleProgressText", timeout=1):
            assert cycle_app.text_of("CycleProgressText", timeout=1) == "", \
                "the cycle label must go once the cycle is over"

        # And nothing was credited for those five-second sprints.
        settings = verify.read_settings()
        assert settings.get("Sessions", []) == [], \
            "--short-sprints must record nothing"
        assert settings.get("MomentumScore", 0) == 0, \
            "--short-sprints must not move momentum"
        assert settings.get("CurrentStreak", 0) == 0

    def test_a_break_never_moves_momentum_or_the_goal(self, cycle_app):
        cycle_app.navigate_to_tab("Today")
        cycle_app.select_sprint_length(15)
        cycle_app.start_sprint()
        assert cycle_app.exists("StartBreakButton", timeout=20)

        momentum_before = cycle_app.text_of("MomentumValue")
        minutes_before = cycle_app.text_of("FocusMinutesValue")

        cycle_app.click("SkipBreakButton")
        time.sleep(1.0)

        assert cycle_app.text_of("MomentumValue") == momentum_before, \
            "skipping a break must not change momentum"
        assert cycle_app.text_of("FocusMinutesValue") == minutes_before, \
            "a break is not focus time"


# =================================================== the Schedule page (F6)

class TestSchedulePage:
    """F6: templates and schedules, with the sleep window below them, unchanged."""

    def test_the_built_in_templates_are_listed(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        for name in ("Homework evening", "Exam prep", "Light study"):
            assert fresh_app.exists(f"TemplateRow_{name}", timeout=3), name

    def test_the_sleep_window_is_still_on_the_page(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        assert fresh_app.exists("SleepBlockToggle", timeout=3)
        assert fresh_app.exists("SaveSleepWindowButton", timeout=3)

    def test_adding_a_schedule_saves_it(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        assert fresh_app.text_of("ScheduleNextUpText") == "No schedules yet"
        fresh_app.add_schedule("Homework evening", ["Mon", "Tue", "Wed", "Thu"], "17:00")
        schedules = verify.wait_for_settings(lambda st: len(st["Schedules"]) == 1,
                                             what="the new schedule")["Schedules"]
        s = schedules[0]
        assert s["Days"] == [1, 2, 3, 4] and s["StartMinuteOfDay"] == 17 * 60 and s["AskFirst"] is True
        template = next(t for t in verify.read_settings()["Templates"] if t["Id"] == s["TemplateId"])
        assert template["Name"] == "Homework evening"
        assert "Mon–Thu" in fresh_app.text_of(f"ScheduleRow_{s['Id']}")
        next_up = fresh_app.text_of("ScheduleNextUpText")
        assert next_up.startswith("Next: ") and next_up.endswith("17:00 · Homework evening"), next_up

    def test_save_is_refused_without_a_day(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("AddScheduleButton")
        fresh_app.choose("ScheduleTemplate_Light study")
        assert not fresh_app.is_control_enabled("SaveScheduleButton")

    def test_a_new_schedule_starts_from_the_first_template(self, fresh_app):
        """The picker shows which template Save would use; nothing is chosen invisibly."""
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("AddScheduleButton")
        assert fresh_app.is_selected("ScheduleTemplate_Homework evening")
        assert not fresh_app.is_selected("ScheduleTemplate_Exam prep")

    def test_editing_a_schedule_opens_it_as_saved_and_keeps_its_id(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.add_schedule("Exam prep", ["Sat"], "09:00", ask_first=False)
        original = verify.wait_for_settings(lambda st: len(st["Schedules"]) == 1,
                                            what="the new schedule")["Schedules"][0]

        fresh_app.click(f"EditSchedule_{original['Id']}")
        assert fresh_app.is_selected("ScheduleTemplate_Exam prep")
        assert fresh_app.toggle_state("ScheduleDay_Sat") is True
        assert fresh_app.toggle_state("ScheduleDay_Mon") is False
        assert fresh_app.text_of("ScheduleTimeInput") == "09:00"
        assert fresh_app.toggle_state("ScheduleAskFirstToggle") is False

        fresh_app.set_text("ScheduleTimeInput", "10:30")
        fresh_app.click("SaveScheduleButton")
        fresh_app.wait_until_gone("SaveScheduleButton")
        schedules = verify.wait_for_settings(
            lambda st: st["Schedules"] and st["Schedules"][0]["StartMinuteOfDay"] == 10 * 60 + 30,
            what="the edited start time")["Schedules"]
        assert len(schedules) == 1, "editing must not add a second schedule"
        assert schedules[0]["Id"] == original["Id"]

    def test_a_schedule_can_be_switched_off(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.add_schedule("Light study", ["Sun"], "19:00")
        schedule_id = verify.wait_for_settings(lambda st: len(st["Schedules"]) == 1,
                                               what="the new schedule")["Schedules"][0]["Id"]

        assert fresh_app.set_toggle(f"ScheduleEnabled_{schedule_id}", False) is False
        verify.wait_for_settings(lambda st: st["Schedules"][0]["Enabled"] is False,
                                 what="the schedule switched off")
        assert fresh_app.text_of("ScheduleNextUpText") == "All your schedules are off"

    def test_a_sealed_sprint_refuses_a_schedule_change_through_automation(self, fresh_app):
        """
        CLAUDE.md, "Covered controls": prove the lock by what happens, not by
        the grey. The row's switch is driven through UI Automation's Toggle
        pattern and its Delete through Invoke, the way a test or an assistive
        tool would reach them; the file must not change and the switch must
        still read as saved. WPF refuses either pattern on a disabled control
        with an exception, which is one acceptable way to refuse.
        """
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.add_schedule("Light study", ["Sun"], "19:00")
        before = verify.wait_for_settings(lambda st: len(st["Schedules"]) == 1,
                                          what="the new schedule")["Schedules"]
        schedule_id = before[0]["Id"]
        assert before[0]["Enabled"] is True

        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Sealed")
        fresh_app.start_sprint()
        fresh_app.wait_out_grace_period()
        try:
            fresh_app.navigate_to_tab("Schedule")
            refusals = []
            switch = fresh_app.element(f"ScheduleEnabled_{schedule_id}")
            try:
                switch.iface_toggle.Toggle()
            except Exception as exc:                      # noqa: BLE001
                refusals.append(f"toggle: {type(exc).__name__}")
            delete = fresh_app.element(f"DeleteSchedule_{schedule_id}")
            try:
                delete.iface_invoke.Invoke()
            except Exception as exc:                      # noqa: BLE001
                refusals.append(f"delete: {type(exc).__name__}")

            assert fresh_app.toggle_state(f"ScheduleEnabled_{schedule_id}") is True, \
                "the switch must still show the saved state"
            assert fresh_app.exists(f"ScheduleRow_{schedule_id}", timeout=2), \
                "the row must still be there"
            # A refusal has no outcome to wait for; give a wrongly accepted
            # change the same moment the profile-switcher test does.
            time.sleep(0.8)
            assert verify.read_settings()["Schedules"] == before, \
                f"Sealed must keep the schedules exactly as saved (refusals: {refusals})"
            assert "Sealed" in fresh_app.text_of("ScheduleStatusText")
        finally:
            fresh_app.navigate_to_tab("Today")
            fresh_app.stop_sprint()

    def test_deleting_a_template_deletes_its_schedules_after_a_confirmation(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.add_schedule("Exam prep", ["Sat"], "09:00")
        fresh_app.click("DeleteTemplate_Exam prep")
        assert "1 schedule" in (fresh_app.accept_dialog() or ""), \
            "the confirmation names what goes with it"
        settings = verify.wait_for_settings(lambda st: st["Schedules"] == [],
                                            what="the schedule going with its template")
        assert all(t["Name"] != "Exam prep" for t in settings["Templates"])

    def test_restore_brings_back_a_deleted_built_in(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("DeleteTemplate_Light study")
        assert fresh_app.accept_dialog() is not None, "deleting a template asks first"
        assert not fresh_app.exists("TemplateRow_Light study", timeout=1.5)
        fresh_app.click("RestoreTemplatesButton")
        assert fresh_app.exists("TemplateRow_Light study", timeout=3)

    def test_a_new_template_is_saved_with_its_settings(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("NewTemplateButton")
        fresh_app.set_text("TemplateNameInput", "Reading")
        fresh_app.set_text("TemplateMinutesInput", "30")
        fresh_app.choose("TemplateShield_Soft")
        fresh_app.choose("TemplateCycle_2")
        fresh_app.set_text("TemplateBreakInput", "7")
        fresh_app.click("SaveTemplateButton")

        assert fresh_app.exists("TemplateRow_Reading", timeout=3)
        settings = verify.wait_for_settings(lambda st: any(t["Name"] == "Reading" for t in st["Templates"]),
                                            what="the Reading template")
        saved = next(t for t in settings["Templates"] if t["Name"] == "Reading")
        assert (saved["SprintMinutes"], saved["CycleSprints"], saved["BreakMinutes"]) == (30, 2, 7)
        assert saved["Shield"] in (1, "Soft")
        assert saved["ProfileId"] == "", "no profile chosen means whichever is active"
        assert saved["BuiltInKey"] == ""

    def test_a_second_template_with_the_same_name_gets_a_number(self, fresh_app):
        """Rows and their buttons are addressed by name, so two "Reading"s would be one."""
        fresh_app.navigate_to_tab("Schedule")
        for _ in range(2):
            fresh_app.click("NewTemplateButton")
            fresh_app.set_text("TemplateNameInput", "Reading")
            fresh_app.click("SaveTemplateButton")
            fresh_app.wait_until_gone("SaveTemplateButton")

        assert fresh_app.exists("TemplateRow_Reading", timeout=3)
        assert fresh_app.exists("TemplateRow_Reading 2", timeout=3)
        settings = verify.wait_for_settings(
            lambda st: sum(t["Name"].startswith("Reading") for t in st["Templates"]) == 2,
            what="both Reading templates")
        assert [t["Name"] for t in settings["Templates"]][-2:] == ["Reading", "Reading 2"]

    def test_a_template_length_out_of_range_is_refused(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("NewTemplateButton")
        # The labels say the same limits Save checks, built from one set of constants.
        assert fresh_app.text_of("TemplateMinutesLabel") == "Sprint minutes (5–240)"
        assert fresh_app.text_of("TemplateBreakLabel") == "Break minutes (1–60)"
        fresh_app.set_text("TemplateNameInput", "Marathon")
        fresh_app.set_text("TemplateMinutesInput", "300")
        fresh_app.click("SaveTemplateButton")

        status = fresh_app.text_of("TemplateStatusText")
        assert "5" in status and "240" in status, status
        assert all(t["Name"] != "Marathon" for t in verify.read_settings()["Templates"])

    def test_a_template_can_use_a_blocklist_profile(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.new_profile("School")
        settings = verify.wait_for_settings(lambda st: any(p["Name"] == "School" for p in st["Profiles"]),
                                            what="the School profile")
        school = next(p for p in settings["Profiles"] if p["Name"] == "School")

        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("NewTemplateButton")
        assert fresh_app.is_selected("TemplateProfileActive"), \
            "a new template follows whichever profile is active"
        fresh_app.set_text("TemplateNameInput", "Maths")
        fresh_app.choose("TemplateProfile_School")
        fresh_app.click("SaveTemplateButton")

        settings = verify.wait_for_settings(lambda st: any(t["Name"] == "Maths" for t in st["Templates"]),
                                            what="the Maths template")
        saved = next(t for t in settings["Templates"] if t["Name"] == "Maths")
        assert saved["ProfileId"] == school["Id"]

    def test_a_sealed_sprint_makes_the_page_read_only(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Sealed")
        fresh_app.start_sprint()
        fresh_app.wait_out_grace_period()
        try:
            fresh_app.navigate_to_tab("Schedule")
            for auto_id in ("AddScheduleButton", "NewTemplateButton", "RestoreTemplatesButton",
                            "EditTemplate_Exam prep", "DeleteTemplate_Exam prep"):
                # is_control_enabled says False for a control it can't find,
                # so prove it is there first.
                assert fresh_app.exists(auto_id, timeout=3), auto_id
                assert not fresh_app.is_control_enabled(auto_id), \
                    f"{auto_id} must be locked during a Sealed sprint"
            assert "Sealed" in fresh_app.text_of("ScheduleStatusText")
        finally:
            fresh_app.navigate_to_tab("Today")
            fresh_app.stop_sprint()

    def test_the_mouse_wheel_scrolls_the_page_over_the_sleep_window(self, fresh_app):
        """
        The embedded sleep view keeps its own ScrollViewer. Inside this page it
        has nothing to scroll, but WPF still marks every wheel turn over it as
        handled, so the page would stop moving under the pointer.
        """
        import pywinauto.mouse as mouse

        fresh_app.navigate_to_tab("Schedule")
        # To the foot of the page through the Scroll pattern, which doesn't
        # depend on what is under the pointer; the sleep window is last.
        fresh_app.element("SchedulePageScroll").iface_scroll.SetScrollPercent(-1, 100)
        time.sleep(0.6)
        window = fresh_app.window.rectangle()
        before = fresh_app.element("SaveSleepWindowButton").rectangle()
        assert window.top < before.top < window.bottom, "the sleep window's Save is on screen"

        # One turn up with the pointer on the sleep window's own button.
        mouse.scroll(coords=((before.left + before.right) // 2, (before.top + before.bottom) // 2),
                     wheel_dist=1)
        time.sleep(0.6)
        after = fresh_app.element("SaveSleepWindowButton").rectangle()
        assert after.top > before.top, "a wheel turn over the sleep window must scroll the page"


# ============================ scheduled sprints and Today's chips (F6, PR C)

class TestScheduledSprints:
    """F6 done-when: a schedule a minute ahead starts, after a heads-up that can skip it."""

    # Saving a schedule through the editor is several seconds of clicks, so
    # the start has to be further off than that or it passes before Save.
    SETUP_SECONDS = 30

    # --short-schedules: the heads-up lead, the late window and how late a
    # tick may be and still start (SchedulePlanner; pinned in tier 1).
    LEAD_SECONDS = 15
    ON_TIME_SECONDS = 3

    TARGET = "flowshield-test-target"

    def _schedule_in(self, app, seconds: int = 70, template="Light study", ask=True,
                     setup_seconds: int | None = None) -> datetime:
        """
        A schedule for the whole minute `seconds` from now. The editor takes
        HH:MM, so the start rounds down to the minute; one that would land
        inside `setup_seconds` (SETUP_SECONDS by default) moves on a minute.
        Returns the start, which is still more than a lead and a tick away.
        """
        now = datetime.now()
        at = (now + timedelta(seconds=seconds)).replace(second=0, microsecond=0)
        if (at - now).total_seconds() < (setup_seconds or self.SETUP_SECONDS):
            at += timedelta(minutes=1)
        app.navigate_to_tab("Schedule")
        app.add_schedule(template, [at.strftime("%a")], at.strftime("%H:%M"), ask_first=ask)
        verify.wait_for_settings(lambda st: len(st.get("Schedules") or []) == 1, what="the schedule")
        assert datetime.now() < at - timedelta(seconds=self.LEAD_SECONDS + 1), \
            "the editor took so long the heads-up was missed"
        return at

    def _wait_past_the_start(self, at: datetime) -> None:
        """Until the start and its on-time window are behind us, plus a tick or two, so a start would show."""
        while datetime.now() < at + timedelta(seconds=self.ON_TIME_SECONDS + 5):
            time.sleep(0.5)

    def _decoy(self, tmp_path):
        """A blocked app that is open: a renamed ping, as TestPreSprintWarning uses."""
        import shutil
        exe = tmp_path / f"{self.TARGET}.exe"
        shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "PING.EXE", exe)
        return subprocess.Popen(
            [str(exe), "-n", "300", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    @staticmethod
    def _wait_for_sprint(app, timeout: float = 40) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if "Shield" in app.session_state():
                return True
            time.sleep(0.5)
        return False

    START_NOTICES = ("SprintStarted", "ScheduledSprint")

    @staticmethod
    def _log_lines(app) -> list[str]:
        path = app.app_log_path()
        return path.read_text(encoding="utf-8", errors="replace").splitlines() if path else []

    def _start_notices_since(self, app, seen: int, expected: str, timeout: float = 5) -> list[str]:
        """
        The start notifications the app logged ("notification: <kind>") after
        its first `seen` log lines, once `expected` is among them or the
        timeout passes. Call it once the sprint shows as running: a start's
        notices go out in the same dispatcher turn, so all of them are logged.
        """
        deadline = time.time() + timeout
        while True:
            kinds = [line.rsplit("notification: ", 1)[1].strip()
                     for line in self._log_lines(app)[seen:] if "notification: " in line]
            kinds = [kind for kind in kinds if kind in self.START_NOTICES]
            if expected in kinds or time.time() >= deadline:
                return kinds
            time.sleep(0.25)

    def test_heads_up_then_it_starts(self, schedule_app):
        self._schedule_in(schedule_app)
        schedule_app.navigate_to_tab("Today")
        schedule_app.wait_until_control_enabled("HeadsUpStartNowButton", timeout=100)
        # Read straight away: under --short-schedules the card is up for fifteen seconds.
        title = schedule_app.text_of("HeadsUpCard")
        text = schedule_app.text_of("HeadsUpText")
        assert title.startswith("Light study starts at "), title
        assert text == "25 minutes at Soft.", text

        assert self._wait_for_sprint(schedule_app), "the sprint started by itself"
        sprint = verify.read_settings()["ActiveSprint"]
        assert sprint["Shield"] == 1   # Soft, from the template
        assert sprint["TemplateBreakMinutes"] == 5, "the template's own break rides with the sprint"
        assert not schedule_app.exists("HeadsUpStartNowButton", timeout=0.5), "the card has done its job"

    def test_skip_today_stops_it(self, schedule_app):
        at = self._schedule_in(schedule_app)
        schedule_app.navigate_to_tab("Today")
        schedule_app.wait_until_control_enabled("HeadsUpSkipButton", timeout=100)
        schedule_app.click("HeadsUpSkipButton")
        # A click that lands after the start would read as Skip not working.
        assert datetime.now() < at, f"Skip was clicked after the start; too slow for the {self.LEAD_SECONDS}-second lead"
        settings = verify.wait_for_settings(
            lambda st: bool(st["Schedules"][0]["SkippedDatesLocal"]), what="the skip")
        assert settings["Schedules"][0]["SkippedDatesLocal"] == [at.strftime("%Y-%m-%dT00:00:00")], \
            "the start's own date, with no offset"

        # Past the start and its on-time window: nothing started.
        self._wait_past_the_start(at)
        assert verify.read_settings().get("ActiveSprint") is None
        assert "Shield" not in schedule_app.session_state()

    def test_the_heads_up_names_the_app_it_will_close_and_stands_in_for_the_question(
            self, schedule_app, tmp_path):
        process = self._decoy(tmp_path)
        try:
            schedule_app.navigate_to_tab("Blocked Apps")
            assert schedule_app.add_blocked_app(self.TARGET)
            self._schedule_in(schedule_app, template="Homework evening")
            schedule_app.navigate_to_tab("Today")
            schedule_app.wait_until_control_enabled("HeadsUpStartNowButton", timeout=100)
            text = schedule_app.text_of("HeadsUpText")
            assert text.lower().startswith("45 minutes at firm."), text
            assert f"{self.TARGET} will be closed." in text.lower(), text

            assert self._wait_for_sprint(schedule_app), "the heads-up named it, so nothing is asked"
            assert not schedule_app.exists("RunningAppsTitle", timeout=0.5)
            assert verify.read_settings()["ActiveSprint"]["TemplateBreakMinutes"] == 10
        finally:
            if process.poll() is None:
                process.kill()

    def test_without_a_heads_up_an_open_app_is_asked_about_first(self, schedule_app, tmp_path):
        """
        Ask first off: nothing named the app, so the start waits on F7's
        question, as quick start does (#270). Answering it starts the template.
        """
        process = self._decoy(tmp_path)
        try:
            schedule_app.navigate_to_tab("Blocked Apps")
            assert schedule_app.add_blocked_app(self.TARGET)
            self._schedule_in(schedule_app, template="Homework evening", ask=False)
            schedule_app.navigate_to_tab("Schedule")   # away from Today: the question brings it back

            assert schedule_app.exists("RunningAppsTitle", timeout=100), "the question never came"
            assert schedule_app.current_page_title() == "Today"
            assert not schedule_app.exists("StopSprintButton", timeout=1)
            assert process.poll() is None, "nothing may be closed before the answer"
            assert verify.read_settings().get("ActiveSprint") is None

            seen = len(self._log_lines(schedule_app))
            schedule_app.click("StartAnywayButton")
            assert schedule_app.exists("StopSprintButton", timeout=5), "the answer starts the template"
            sprint = verify.wait_for_settings(lambda st: st.get("ActiveSprint") is not None,
                                              what="the sprint")["ActiveSprint"]
            assert sprint["PlannedMinutes"] == 45 and sprint["TemplateBreakMinutes"] == 10
            assert self._start_notices_since(schedule_app, seen, "ScheduledSprint") == ["ScheduledSprint"], \
                "the answered start is still the schedule's, named once"
        finally:
            if process.poll() is None:
                process.kill()

    def test_a_start_without_asking_sends_one_notification(self, schedule_app):
        """
        Review of PR C: "Sprint started" is on by default, so a start with Ask
        first off sent it and "Light study started" back to back. The named
        one (spec 3.3) stands in for it: one start, one notification.
        """
        self._schedule_in(schedule_app, ask=False)
        schedule_app.navigate_to_tab("Today")
        seen = len(self._log_lines(schedule_app))
        assert self._wait_for_sprint(schedule_app, timeout=100), "the sprint started by itself"
        assert self._start_notices_since(schedule_app, seen, "ScheduledSprint") == ["ScheduledSprint"]

    def _wait_for_log_line(self, app, needle: str, since: int, deadline: datetime, what: str) -> None:
        """
        Poll the app log for `needle` after its first `since` lines until
        `deadline`; a miss fails as `what`, not as a timeout. The log is one
        file a day, so an earlier run's line would otherwise match at once.
        """
        while not any(needle in line for line in self._log_lines(app)[since:]):
            assert datetime.now() < deadline, what
            time.sleep(0.2)

    def test_a_start_whose_heads_up_fell_in_a_hand_sprint_is_offered_not_started(self, schedule_app):
        """
        Final review of PR C: Ask first promises a question before a start.
        A sprint running when the heads-up is due swallows it (the scheduler
        refuses while busy, and remembers the heads-up as shown), so at the
        time nobody had been asked. The start is then offered on the card,
        never taken. A 25-minute hand sprint ending between T-15 and T is
        enough; here one is stopped by hand inside that window.
        """
        since = len(self._log_lines(schedule_app))     # this launch's lines only
        # Room for the editor and a hand Start before the heads-up is due.
        at = self._schedule_in(schedule_app, setup_seconds=self.SETUP_SECONDS + self.LEAD_SECONDS)
        schedule_app.navigate_to_tab("Today")
        schedule_app.select_shield("Soft")             # a fresh state starts at Firm, whose Stop asks first
        schedule_app.start_sprint()
        assert datetime.now() < at - timedelta(seconds=self.LEAD_SECONDS + 1), \
            "Start landed too late for the heads-up to fall inside the sprint"

        # The heads-up tick lands while the sprint runs: refused, and remembered
        # as shown. The sprint is then stopped inside the lead: one lookup and
        # an invoke, not click()'s resolve-scroll-settle, so the stop lands
        # seconds before the start instead of racing it (#241). Soft ends on
        # one press, in or out of the grace period.
        stop = schedule_app.element("StopSprintButton")
        self._wait_for_log_line(schedule_app, "schedule HeadsUp for Light study skipped: busy or gated",
                                since=since, deadline=at, what="the heads-up was not swallowed by the sprint")
        try:
            stop.invoke()
        except Exception:                                  # noqa: BLE001
            stop.click_input()
        stopped_at = datetime.now()
        seen = len(self._log_lines(schedule_app))
        assert stopped_at < at, f"the sprint ended after the start; too slow for the {self.LEAD_SECONDS}-second lead"
        ended_by = time.time() + 5
        while "Shield" in schedule_app.session_state():
            assert time.time() < ended_by, "the Stop press did not end the sprint"
            time.sleep(0.2)

        schedule_app.wait_until_control_enabled("HeadsUpStartNowButton", timeout=20)
        assert schedule_app.text_of("HeadsUpCard") == "Light study is due now"
        assert schedule_app.text_of("HeadsUpText") == "25 minutes at Soft."
        assert not any("schedule card shown: HeadsUp for Light study" in line
                       for line in self._log_lines(schedule_app)[since:]), \
            "no heads-up card was ever up: this offer is the first question"

        # Past the start and its on-time window: offered, not started.
        self._wait_past_the_start(at)
        assert verify.read_settings().get("ActiveSprint") is None
        assert "Shield" not in schedule_app.session_state()
        assert schedule_app.exists("HeadsUpStartNowButton", timeout=0.5), "the offer stays up"
        assert self._start_notices_since(schedule_app, seen, "ScheduledSprint") == ["ScheduledSprint"], \
            "the offer is announced once, and no start is"

        # The offer is live: Start now starts the template, with its own break.
        schedule_app.click("HeadsUpStartNowButton")
        assert self._wait_for_sprint(schedule_app, timeout=10), "Start now starts the template"
        sprint = verify.wait_for_settings(lambda st: st.get("ActiveSprint") is not None,
                                          what="the sprint")["ActiveSprint"]
        assert sprint["PlannedMinutes"] == 25 and sprint["TemplateBreakMinutes"] == 5
        assert not schedule_app.exists("HeadsUpStartNowButton", timeout=0.5), "the card has done its job"

    def test_a_template_chip_fills_in_today(self, fresh_app):
        fresh_app.select_shield("Soft")
        fresh_app.click("TemplateChip_Homework evening")
        assert fresh_app.is_selected("Shield_Firm")
        assert fresh_app.is_selected("SprintLength_45")
        assert fresh_app.is_selected("Cycle_3")
        settings = verify.wait_for_settings(lambda st: st["CycleSprints"] == 3, what="the template's cycle")
        assert settings["CycleSprints"] == 3

    def test_the_sprint_options_are_folded_until_change(self, fresh_app):
        """
        #147: idle, Today is the timer, the templates and Start sprint. The
        pickers sit behind one summary line, and a template chip updates the
        line without opening them. Looked up by element() directly, which
        does not go through the driver's unfolding.
        """
        fresh_app.navigate_to_tab("Today")
        toggle = fresh_app.element("SprintOptionsToggle", timeout=3)
        assert toggle.window_text() == "Change sprint options"
        assert self._shown_without_unfolding(fresh_app, "SprintLength_25") is False, \
            "the length picker is folded away by default"

        fresh_app.click("TemplateChip_Homework evening")
        assert fresh_app.text_of("SprintOptionsSummary") == \
            "45 min · Firm shield · 3 sprints with breaks"
        assert self._shown_without_unfolding(fresh_app, "Shield_Firm") is False, \
            "a template fills the choices in without unfolding them"

        fresh_app.click("SprintOptionsToggle")
        assert self._shown_without_unfolding(fresh_app, "Shield_Firm") is True
        assert fresh_app.element("SprintOptionsToggle").window_text() == "Hide sprint options"

        fresh_app.click("SprintOptionsToggle")
        assert self._shown_without_unfolding(fresh_app, "Shield_Firm") is False

    def test_the_sprint_options_hide_while_a_sprint_runs(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.click("SprintOptionsToggle")
        fresh_app.start_sprint()
        fresh_app.wait_until_gone("SprintOptionsToggle")      # the timer is the screen (§1)
        assert self._shown_without_unfolding(fresh_app, "Shield_Firm") is False

    @staticmethod
    def _shown_without_unfolding(app, auto_id: str) -> bool:
        """Whether a picker is in the UIA tree, asked without opening the fold."""
        _, uia = _uia()
        found = app.window.element_info.element.FindFirst(
            uia.TreeScope_Descendants, _automation_id_condition(auto_id))
        return bool(found)

    def test_a_chip_carries_the_templates_break_to_a_hand_start(self, fresh_app):
        """
        PR C polish, item 9: the chip's preset includes the template's break
        length, and a hand change of length afterwards keeps it, so the
        sprint started by Start takes the template's breaks (Light study: 5).
        """
        fresh_app.click("TemplateChip_Light study")
        assert fresh_app.is_selected("SprintLength_25")
        fresh_app.click("SprintLength_15")
        fresh_app.start_sprint()
        sprint = verify.wait_for_settings(lambda st: st.get("ActiveSprint") is not None,
                                          what="the sprint")["ActiveSprint"]
        assert sprint["PlannedMinutes"] == 15, "the hand change of length stands"
        assert sprint["TemplateBreakMinutes"] == 5, "the chip's break rides with the sprint"

    def test_a_template_between_the_preset_lengths_uses_custom(self, fresh_app):
        """Also shows a new template reaching Today's chips (TemplatesChanged)."""
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("NewTemplateButton")
        fresh_app.set_text("TemplateNameInput", "Reading")
        fresh_app.set_text("TemplateMinutesInput", "30")
        fresh_app.click("SaveTemplateButton")
        fresh_app.wait_until_gone("SaveTemplateButton")

        fresh_app.navigate_to_tab("Today")
        fresh_app.click("TemplateChip_Reading")
        assert fresh_app.is_selected("SprintLength_Custom")
        assert fresh_app.text_of("CustomMinutesInput") == "30"
        assert fresh_app.text_of("SprintTimerText") == "30:00"

    def test_the_chips_hide_while_a_sprint_runs(self, fresh_app):
        assert fresh_app.exists("TemplateChip_Light study", timeout=3)
        fresh_app.start_sprint()
        try:
            fresh_app.wait_until_gone("TemplateChip_Light study")
        finally:
            fresh_app.cancel_sprint()
        assert fresh_app.exists("TemplateChip_Light study", timeout=3), "back once the sprint is over"


# ===================================================== the taskbar Jump List (1.0.10)

class TestJumpList:
    """
    Spec 5: right-clicking Basalt on the taskbar offers Start sprint and
    Start <template>, which run FlowShield.exe --start-sprint and
    --start-sprint=<templateId>. An entry does nothing but run its command
    line, so these run the command lines rather than the shell's menu. A cold
    launch handles the argument after startup; a launch while Basalt runs
    hands it over the single-instance pipe.
    """

    MISSING = "That template isn't here any more. Pick one on Today."
    RUNNING = "A sprint is already running."

    @staticmethod
    def _template_id(name: str) -> str:
        return next(t["Id"] for t in verify.read_settings()["Templates"] if t["Name"] == name)

    @staticmethod
    def _running_sprint(app) -> dict:
        # A blocked app already open on this PC is asked about first (F7).
        app.answer_open_apps_question(timeout=5)
        assert app.exists("StopSprintButton", timeout=10), "no sprint started"
        return verify.wait_for_settings(lambda st: st.get("ActiveSprint") is not None,
                                        what="the sprint")["ActiveSprint"]

    @staticmethod
    def _log_lines(app) -> list[str]:
        path = app.app_log_path()
        return path.read_text(encoding="utf-8", errors="replace").splitlines() if path else []

    def _jump_list_lines(self, app, seen: int, timeout: float = 5) -> list[str]:
        """
        What the app logged about the Jump List after its first `seen` log
        lines, once there is anything or the timeout passes. The list is
        built right after the window is shown, in the same startup turn.
        """
        deadline = time.time() + timeout
        while True:
            lines = [line for line in self._log_lines(app)[seen:] if "jump list" in line]
            if lines or time.time() >= deadline:
                return lines
            time.sleep(0.25)

    @staticmethod
    def _toast(app, expected: str, timeout: float = 6) -> str:
        deadline, toast = time.time() + timeout, ""
        while toast != expected and time.time() < deadline:
            toast = app.toast_text(timeout=1)
        return toast

    def test_a_template_starts_from_a_cold_launch_and_a_deleted_one_starts_nothing(self, fresh_app):
        light = self._template_id("Light study")
        entries = len(verify.read_settings()["Templates"]) + 1   # Start sprint, then one per template
        fresh_app.close_app()
        seen = len(self._log_lines(fresh_app))
        fresh_app.launch_app(clean_state=False, extra_args=[f"--start-sprint={light}"])
        fresh_app.connect_window()

        # The list itself: built at startup, and every entry accepted by the
        # shell on this machine. Rebuild swallows a failure into a Warn, so
        # the log is the one place that says the list is really there (review).
        lines = self._jump_list_lines(fresh_app, seen)
        assert any(line.endswith(f"jump list: {entries} entries") for line in lines), lines
        assert not any("could not build the jump list" in line for line in lines), lines

        sprint = self._running_sprint(fresh_app)
        assert sprint["Shield"] == 1, "Soft, from Light study"
        assert sprint["PlannedMinutes"] == 25 and sprint["TemplateBreakMinutes"] == 5

        # A pinned list can outlive a template (review focus 5); the fallback
        # is Today, wherever the window was.
        fresh_app.navigate_to_tab("History")
        launch_again("--start-sprint=missing")
        assert flowshield_pids() == [fresh_app.pid], "the second launch kept running"
        toast = self._toast(fresh_app, self.MISSING)
        assert toast == self.MISSING, toast
        assert fresh_app.current_page_title() == "Today", "a dangling entry falls back to Today"
        assert verify.read_settings()["ActiveSprint"]["StartedUtc"] == sprint["StartedUtc"], \
            "the running sprint was replaced"

        # A template while a sprint runs: said, not silent (review).
        launch_again(f"--start-sprint={light}")
        assert flowshield_pids() == [fresh_app.pid], "the third launch kept running"
        toast = self._toast(fresh_app, self.RUNNING)
        assert toast == self.RUNNING, toast
        assert verify.read_settings()["ActiveSprint"]["StartedUtc"] == sprint["StartedUtc"], \
            "the running sprint was replaced"

    def test_start_sprint_reaches_a_running_copy_as_the_trays_quick_start(self, fresh_app):
        """No template: Today's last settings, exactly as the tray's Start sprint takes them."""
        fresh_app.select_shield("Soft")
        fresh_app.select_sprint_length(15)

        launch_again("--start-sprint")
        assert flowshield_pids() == [fresh_app.pid], "the second launch kept running"
        sprint = self._running_sprint(fresh_app)
        assert sprint["Shield"] == 1 and sprint["PlannedMinutes"] == 15
        assert sprint.get("TemplateBreakMinutes") is None, "no template was involved"


# ============================================ a sleep schedule people trust (3.7)
#
# Written for roadmap 3.7 but NOT run in the session that wrote it: UI tests
# take over the screen. None of them turns Start with Windows on, which would
# write the real Run key; the offer and the warning are checked by what they say.

class TestSleepSchedule:
    NEXT = r"Next: (Tonight|Today|Tomorrow|Next \w+day|\w+day) \d\d:\d\d \u2192 \d\d:\d\d"

    def test_the_times_are_pickers_and_the_nights_are_chips(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        for auto_id in ("SleepStartHour", "SleepStartMinute", "SleepEndHour", "SleepEndMinute"):
            assert fresh_app.exists(auto_id, timeout=3), auto_id
        for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
            assert fresh_app.toggle_state(f"SleepNight_{day}") is True, day

    def test_weeknights_are_saved_and_the_next_night_is_shown(self, fresh_app):
        import re
        fresh_app.navigate_to_tab("Schedule")
        assert fresh_app.set_toggle("SleepBlockToggle", True) is True
        fresh_app.set_sleep_window("23:00", "06:30", nights=["Sun", "Mon", "Tue", "Wed", "Thu"])
        saved = verify.wait_for_settings(lambda st: st.get("SleepBlockDays") == [0, 1, 2, 3, 4],
                                         what="the chosen nights")
        assert saved["SleepBlockStartTime"].startswith("23:00") and saved["SleepBlockEndTime"].startswith("06:30")
        assert re.fullmatch(self.NEXT, fresh_app.sleep_next_text()), fresh_app.sleep_next_text()

    def test_saving_with_no_night_is_refused_and_nothing_changes(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        before = verify.read_settings().get("SleepBlockDays")
        for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
            fresh_app.set_toggle(f"SleepNight_{day}", False)
        fresh_app.click("SaveSleepWindowButton")
        time.sleep(0.6)
        assert "at least one night" in fresh_app.sleep_status().lower()
        assert verify.read_settings().get("SleepBlockDays") == before

    def test_switching_it_on_offers_start_with_windows_and_the_page_keeps_saying_so(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        assert not fresh_app.exists("SleepStartWithWindowsButton", timeout=1)
        assert fresh_app.set_toggle("SleepBlockToggle", True) is True
        assert fresh_app.exists("SleepStartWithWindowsButton", timeout=3)
        assert fresh_app.exists("SleepStartupNotNowButton", timeout=1)
        assert "only works while Basalt is running" in fresh_app.text_of("SleepStartupText")
        fresh_app.click("SleepStartupNotNowButton")
        time.sleep(0.4)
        assert not fresh_app.exists("SleepStartupNotNowButton", timeout=1), "the offer is made once"
        assert fresh_app.exists("SleepStartWithWindowsButton", timeout=1), "the warning stays"
        assert "isn't set to start when you sign in" in fresh_app.text_of("SleepStartupTitle")

    def test_the_pickers_and_nights_are_locked_once_the_trial_has_ended(self, expired_app):
        expired_app.navigate_to_tab("Schedule")
        for auto_id in ("SleepStartHour", "SleepEndMinute", "SleepNight_Mon", "SaveSleepWindowButton"):
            assert expired_app.is_control_enabled(auto_id) is False, auto_id
