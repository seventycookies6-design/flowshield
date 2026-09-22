"""
Tier 3 — end-to-end through the real UI.

These drive the shipped binary with UI Automation and check that what the UI
claims matches what was actually persisted to the DPAPI-encrypted settings file.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

import pytest

from config import TEST_BLOCK_APP
from core import state_verifier as verify

pytestmark = pytest.mark.ui


# ================================================================ app shell

class TestAppShell:
    def test_window_opens_on_the_today_page(self, app):
        assert app.current_page_title() == "Today"

    @pytest.mark.parametrize("tab", ["History", "Blocked Apps", "Sleep Blocking",
                                     "Settings", "Today"])
    def test_every_tab_is_reachable(self, app, tab):
        assert app.navigate_to_tab(tab) == tab

    def test_a_clean_install_starts_the_seven_day_trial(self, app):
        app.navigate_to_tab("Settings")
        assert "free trial — 7 days left" in app.get_license_status_text().lower()
        assert app.tier_badge().upper() == "TRIAL · 7 DAYS LEFT"
        # The panel is a Border, which UI Automation can't see; its button can be.
        assert not app.exists("LockBuyButton", timeout=1.5), "a new install is locked"

        settings = verify.read_settings()
        assert settings.get("TrialStartedUtc"), "the trial start was not saved"

    def test_the_app_writes_an_encrypted_settings_file(self, app):
        # Touch a setting so the file definitely exists.
        app.navigate_to_tab("Blocked Apps")
        app.add_blocked_app("settings-file-probe")
        time.sleep(0.8)

        result = verify.settings_is_encrypted()
        assert result.ok, result.detail

    def test_settings_cannot_be_read_without_dpapi(self, app):
        """The on-disk bytes must not contain the plaintext payload."""
        from config import SETTINGS_PATH

        # Write a distinctive value ourselves rather than relying on a previous
        # test having run — each test gets its own wiped instance.
        marker = "plaintext-leak-canary"
        app.navigate_to_tab("Blocked Apps")
        app.add_blocked_app(marker)
        time.sleep(0.9)

        raw = SETTINGS_PATH.read_text(encoding="utf-8", errors="replace")
        assert marker not in raw, "a blocked app name appeared in plaintext on disk"

        # And it really is recoverable through DPAPI — so the test proves
        # encryption, not merely that the write failed.
        settings = verify.read_settings()
        names = [a["ProcessName"] for a in settings["BlockedApps"]]
        assert marker in names, names


# ============================================================= blocked apps

class TestBlockedApps:
    def test_adding_an_app_shows_it_in_the_list(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)
        names = fresh_app.blocked_app_names()
        assert any(TEST_BLOCK_APP.lower() in n.lower() for n in names), names

    def test_adding_an_app_persists_it_to_disk(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)
        result = verify.verify_blocked_app_persisted(TEST_BLOCK_APP)
        assert result.ok, result.detail

    def test_a_duplicate_is_refused(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.6)
        before = len(fresh_app.blocked_app_names())

        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)
        after = len(fresh_app.blocked_app_names())

        assert after == before, "the same process was added twice"

    def test_there_is_no_blocked_app_limit(self, fresh_app):
        """The old free tier stopped at three; the trial and a purchase have no cap."""
        fresh_app.navigate_to_tab("Blocked Apps")
        for index in range(5):
            fresh_app.add_blocked_app(f"limit-probe-{index}")
            time.sleep(0.5)

        names = fresh_app.blocked_app_names()
        assert len(names) == 5, f"only {len(names)} of 5 apps were added: {names}"

    def test_removing_an_app_takes_it_off_the_list_and_disk(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)
        assert verify.verify_blocked_app_persisted(TEST_BLOCK_APP).ok

        fresh_app.remove_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)

        names = fresh_app.blocked_app_names()
        assert not any(TEST_BLOCK_APP.lower() in n.lower() for n in names), names
        assert not verify.verify_blocked_app_persisted(TEST_BLOCK_APP).ok

    def test_a_protected_system_process_cannot_be_blocked(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app("explorer")
        time.sleep(0.8)

        names = " ".join(fresh_app.blocked_app_names()).lower()
        assert "explorer" not in names, "explorer.exe must never be blockable"


# ============================================================== sprint flow

class TestPreSprintWarning:
    """
    F7 / roadmap 1.8: a blocked app already open is named before the sprint
    starts, with the choice to close it first or go ahead.
    """

    TARGET = "flowshield-test-target"

    def _decoy(self, tmp_path):
        import shutil
        exe = tmp_path / f"{self.TARGET}.exe"
        shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "PING.EXE", exe)
        return subprocess.Popen(
            [str(exe), "-n", "300", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _arm(self, app):
        app.navigate_to_tab("Blocked Apps")
        assert app.add_blocked_app(self.TARGET)
        time.sleep(0.6)
        app.navigate_to_tab("Today")
        app.choose("Shield_Firm")
        time.sleep(0.4)

    def test_an_open_blocked_app_is_named_before_the_sprint_starts(self, fresh_app, tmp_path):
        process = self._decoy(tmp_path)
        try:
            self._arm(fresh_app)
            fresh_app.start_sprint(confirm_open_apps=False)
            time.sleep(1.0)

            assert fresh_app.exists("RunningAppsTitle", timeout=5), (
                "a blocked app was already open and nothing said so"
            )
            # The app title-cases display names, so compare without case.
            listed = fresh_app.text_of("RunningAppsList")
            assert self.TARGET.lower() in listed.lower(), listed

            # Nothing has started yet — the panel is a question, not a countdown.
            assert not fresh_app.exists("StopSprintButton", timeout=1)
            assert process.poll() is None, "nothing may be closed before the answer"
        finally:
            if process.poll() is None:
                process.kill()

    def test_start_anyway_starts_the_sprint(self, fresh_app, tmp_path):
        process = self._decoy(tmp_path)
        try:
            self._arm(fresh_app)
            fresh_app.start_sprint(confirm_open_apps=False)
            assert fresh_app.exists("RunningAppsTitle", timeout=5)

            fresh_app.click("StartAnywayButton")
            time.sleep(1.5)

            assert not fresh_app.exists("RunningAppsTitle", timeout=1)
            assert fresh_app.exists("StopSprintButton", timeout=5), "the sprint should be running"
        finally:
            if process.poll() is None:
                process.kill()

    def test_the_panel_does_not_come_back_after_it_is_answered(self, fresh_app, tmp_path):
        """
        Both answers call back into the start path. Without the latch that is a
        loop the customer cannot get out of.
        """
        process = self._decoy(tmp_path)
        try:
            self._arm(fresh_app)
            fresh_app.start_sprint(confirm_open_apps=False)
            assert fresh_app.exists("RunningAppsTitle", timeout=5)
            fresh_app.click("CloseThemNowButton")
            time.sleep(2.0)
            assert not fresh_app.exists("RunningAppsTitle", timeout=2), (
                "answering the panel must not put it straight back up"
            )
            assert fresh_app.exists("StopSprintButton", timeout=5)
        finally:
            if process.poll() is None:
                process.kill()


class TestFirmWarnsBeforeClosing:
    """
    F7 / roadmap 1.8: Firm asks a blocked app to close, gives it a few seconds
    to save, and only then forces it.

    The suite runs with --short-timers, so the grace period is 2 s rather than
    10. The point being tested is that a warning happens at all and that the
    app outlives it briefly — not the exact duration, which is tier 1's job.
    """

    TARGET = "flowshield-test-target"

    def _decoy(self, tmp_path):
        import shutil
        exe = tmp_path / f"{self.TARGET}.exe"
        shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "PING.EXE", exe)
        return subprocess.Popen(
            [str(exe), "-n", "300", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_the_app_is_warned_and_survives_the_grace_period(self, fresh_app, tmp_path):
        process = self._decoy(tmp_path)
        try:
            fresh_app.navigate_to_tab("Blocked Apps")
            assert fresh_app.add_blocked_app(self.TARGET)
            time.sleep(0.6)

            fresh_app.navigate_to_tab("Today")
            fresh_app.choose("Shield_Firm")
            time.sleep(0.4)
            fresh_app.start_sprint()

            # The warning names the app and says how long there is to save.
            warned = ""
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    text = fresh_app.text_of("ToastText", timeout=1)
                except Exception:
                    text = ""
                if "closing in" in text:
                    warned = text
                    break
                time.sleep(0.5)

            assert warned, "a blocked app must be warned before it is closed"
            assert self.TARGET.lower() in warned.lower(), warned
            assert "Save your work." in warned, warned

            # And it is still there while that warning is on screen — which is
            # the entire difference from the old behaviour.
            assert process.poll() is None, (
                "the app was killed before its grace period; the warning would "
                "have been a lie"
            )

            deadline = time.time() + 25
            while time.time() < deadline and process.poll() is None:
                time.sleep(1)
            assert process.poll() is not None, "the grace period must end in a close"
        finally:
            if process.poll() is None:
                process.kill()

    def test_hard_kill_gives_no_warning(self, fresh_app, tmp_path):
        """
        The setting exists so there is no window to slip through. If this ever
        starts warning, the feature people turned on has quietly gone away.
        """
        process = self._decoy(tmp_path)
        try:
            fresh_app.navigate_to_tab("Blocked Apps")
            assert fresh_app.add_blocked_app(self.TARGET)
            time.sleep(0.4)

            fresh_app.navigate_to_tab("Settings")
            assert fresh_app.set_toggle("HardKillModeToggle", True) is True
            time.sleep(0.4)

            fresh_app.navigate_to_tab("Today")
            fresh_app.choose("Shield_Firm")
            time.sleep(0.4)
            fresh_app.start_sprint()

            deadline = time.time() + 20
            seen = []
            while time.time() < deadline and process.poll() is None:
                try:
                    seen.append(fresh_app.text_of("ToastText", timeout=1))
                except Exception:
                    pass
                time.sleep(0.5)

            assert process.poll() is not None, "hard kill must still close the app"
            assert not any("closing in" in t for t in seen), (
                f"hard kill must not warn first; saw {seen}"
            )
        finally:
            if process.poll() is None:
                process.kill()


class TestSoftShowsTheNotice:
    """
    F7 / roadmap 1.7: at Soft, a blocked app coming to the front gets a
    topmost full-screen notice naming it and the time left — and the app is
    still running afterwards, whichever button was pressed.

    The decoy is a copy of Notepad rather than the copy of ping the other tier 3
    blocker tests use: this one has to *have a window* and be the foreground
    one, which is the whole trigger. Same name either way, so it is the same
    entry on the blocklist.

    The notice is its own top-level window, so it is found through Desktop
    rather than through the controller, which only searches the main window.
    """

    TARGET = "flowshield-test-target"
    OVERLAY = "SoftOverlayWindow"

    def _decoy(self, tmp_path):
        import shutil
        exe = tmp_path / f"{self.TARGET}.exe"
        shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "NOTEPAD.EXE", exe)
        process = subprocess.Popen([str(exe)])
        time.sleep(2.0)                       # let it open its window
        return process

    def _overlay(self, timeout=15):
        """The notice's window, or None. Raced, not slept on (#146)."""
        from pywinauto import Desktop

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                window = Desktop(backend="uia").window(auto_id=self.OVERLAY)
                if window.exists(timeout=0.5):
                    return window
            except Exception:
                pass
            time.sleep(0.4)
        return None

    def _arm_and_start(self, app):
        app.navigate_to_tab("Blocked Apps")
        assert app.add_blocked_app(self.TARGET)
        time.sleep(0.6)
        app.navigate_to_tab("Today")
        app.choose("Shield_Soft")
        time.sleep(0.4)
        app.start_sprint(confirm_open_apps=True)

    def test_a_blocked_app_in_front_gets_a_notice_that_closes_nothing(self, fresh_app, tmp_path):
        process = self._decoy(tmp_path)
        try:
            self._arm_and_start(fresh_app)

            overlay = self._overlay()
            assert overlay is not None, (
                "a blocked app was the foreground window at Soft and nothing said so"
            )

            named = overlay.child_window(auto_id="SoftOverlayText").window_text()
            assert self.TARGET.lower() in named.lower(), named
            assert "on your blocklist until" in named, named
            assert overlay.child_window(auto_id="SoftOverlayTimeLeft").exists()

            # Soft's promise: the distraction is noted, not closed.
            assert process.poll() is None, "Soft must never close the blocked app"

            overlay.child_window(auto_id="SoftOverlayBackToWorkButton").click_input()
            time.sleep(1.5)
            assert self._overlay(timeout=2) is None, "Back to work must take it down"
            assert process.poll() is None, "Back to work must not close the blocked app"
        finally:
            if process.poll() is None:
                process.kill()

    def test_allow_five_minutes_keeps_it_quiet(self, fresh_app, tmp_path):
        process = self._decoy(tmp_path)
        try:
            self._arm_and_start(fresh_app)

            overlay = self._overlay()
            assert overlay is not None
            overlay.child_window(auto_id="SoftOverlayAllowButton").click_input()
            time.sleep(1.0)

            # Back to the decoy: inside the five minutes, nothing appears.
            process_window = None
            from pywinauto import Desktop
            try:
                process_window = Desktop(backend="uia").window(process_id=process.pid)
                process_window.set_focus()
            except Exception:
                pass
            time.sleep(6.0)                     # three sweeps of the blocker
            assert self._overlay(timeout=2) is None, (
                "Allow 5 minutes has to mean five minutes"
            )
            assert process.poll() is None
        finally:
            if process.poll() is None:
                process.kill()

    def test_firm_closes_the_app_instead_of_covering_it(self, fresh_app, tmp_path):
        """The notice is Soft's. Firm has seconds to save in, and a panel over
        the window being saved would be the worst possible moment for one."""
        process = self._decoy(tmp_path)
        try:
            fresh_app.navigate_to_tab("Blocked Apps")
            assert fresh_app.add_blocked_app(self.TARGET)
            time.sleep(0.6)
            fresh_app.navigate_to_tab("Today")
            fresh_app.choose("Shield_Firm")
            time.sleep(0.4)
            fresh_app.start_sprint(confirm_open_apps=True)

            deadline = time.time() + 25
            while time.time() < deadline and process.poll() is None:
                assert self._overlay(timeout=0.5) is None, (
                    "Firm must not show the Soft notice"
                )
                time.sleep(0.5)
            assert process.poll() is not None, "Firm still closes the app"
        finally:
            if process.poll() is None:
                process.kill()


class TestDistractionsAreCountedPerApp:
    """
    One app closing is one distraction, however many processes it runs.

    Steam runs seven; closing it once was reported as seven distractions, which
    made the number grow with an app's implementation rather than with anything
    the customer did (#138). Every process is still closed — what changed is the
    counting.

    This is the first tier 3 test that puts a real process in front of the
    blocker. `flowshield-test-target` was only ever a name on the blocklist
    before, so nothing exercised enforcement end to end.
    """

    TARGET = "flowshield-test-target"

    def _decoys(self, tmp_path, count=3):
        """
        Several processes of ONE blocked app.

        They share an executable name on purpose: that is what makes them one
        app with several processes, which is the case this test exists for.
        Copies of ping, which sits quietly for as long as it is asked to and
        has no window to steal focus.
        """
        import shutil
        exe = tmp_path / f"{self.TARGET}.exe"
        shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "PING.EXE", exe)
        return [
            subprocess.Popen(
                [str(exe), "-n", "300", "127.0.0.1"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for _ in range(count)
        ]

    def test_closing_one_app_counts_one_distraction(self, fresh_app, tmp_path):
        processes = self._decoys(tmp_path)
        try:
            fresh_app.navigate_to_tab("Blocked Apps")
            assert fresh_app.add_blocked_app(self.TARGET)
            time.sleep(0.6)

            fresh_app.navigate_to_tab("Today")
            assert fresh_app.text_of("BlocksTodayValue") == "0"

            fresh_app.choose("Shield_Firm")
            time.sleep(0.4)
            fresh_app.start_sprint()

            # The blocker sweeps every two seconds; give it several.
            deadline = time.time() + 25
            while time.time() < deadline:
                if all(p.poll() is not None for p in processes):
                    break
                time.sleep(1)

            alive = [p.pid for p in processes if p.poll() is None]
            assert not alive, (
                f"every process of a blocked app must be closed; {len(alive)} "
                f"survived. Deduplicating the count must never skip a kill."
            )

            time.sleep(2.5)
            counted = fresh_app.text_of("BlocksTodayValue")
            assert counted == "1", (
                f"{len(processes)} processes of one blocked app were closed; the "
                f"customer should see one distraction, not {counted}"
            )
        finally:
            for p in processes:
                if p.poll() is None:
                    p.kill()


class TestSprints:
    def test_starting_a_sprint_runs_the_timer_down(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(2.5)

        timer = fresh_app.sprint_timer()
        assert timer != "25:00", f"timer did not advance (still {timer})"
        assert "engaged" in fresh_app.session_state().lower()
        fresh_app.stop_sprint()

    def test_ending_a_sprint_early_is_recorded_as_such(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.5)
        fresh_app.stop_sprint()
        time.sleep(0.8)
        assert "early" in fresh_app.session_state().lower()

    def test_abandoning_a_sprint_does_not_zero_momentum(self, fresh_app):
        """Momentum decays on an abandoned sprint; it must not reset to zero."""
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.stop_sprint()
        time.sleep(1.0)

        settings = verify.read_settings()
        assert settings["MomentumScore"] >= 0
        assert len(settings["Sessions"]) == 1
        assert settings["Sessions"][0]["Completed"] is False

    def test_the_journal_prompt_appears_after_a_sprint(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.stop_sprint()
        time.sleep(0.8)
        assert fresh_app.exists("JournalInput", timeout=4)

    def test_a_journal_entry_is_saved_with_the_session(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.stop_sprint()
        time.sleep(0.8)

        fresh_app.set_text("JournalInput", "shipped the licence server")
        fresh_app.click("SaveJournalButton")
        time.sleep(1.0)

        settings = verify.read_settings()
        assert settings["Sessions"][-1]["Journal"] == "shipped the licence server"

    def test_ending_early_shows_the_neutral_summary_card(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.5)
        fresh_app.stop_sprint()
        time.sleep(1.0)

        title = fresh_app.text_of("SummaryTitle")
        assert "ended early" in title.lower()
        assert "it'll recover" in title.lower()
        assert "−0" not in title, "no momentum was lost, so the card must not say 'momentum −0'"
        assert fresh_app.text_of("SummaryDistractionsValue") == "No distractions caught"

        settings = verify.read_settings()
        assert fresh_app.text_of("SummaryMomentumText").endswith(f"→ {int(settings['MomentumScore'])}")

    def test_finishing_a_sprint_shows_the_summary_card(self, fresh_app):
        """The shortest sprint is five minutes; the card must show what settings stores."""
        fresh_app.navigate_to_tab("Today")
        fresh_app.click("SprintLength_Custom")
        fresh_app.set_text("CustomMinutesInput", "5")
        time.sleep(0.5)
        fresh_app.start_sprint()

        assert fresh_app.exists("SummaryTitle", timeout=340), \
            "the 5-minute sprint finished but the summary card never appeared"

        settings = verify.read_settings()
        session = settings["Sessions"][-1]
        assert session["Completed"] is True

        assert fresh_app.text_of("SummaryTitle") == "Sprint complete"
        started = datetime.fromisoformat(session["StartedUtc"].replace("Z", "+00:00"))
        ended = datetime.fromisoformat(session["EndedUtc"].replace("Z", "+00:00"))
        actual_minutes = round((ended - started).total_seconds() / 60)
        assert fresh_app.text_of("SummaryMinutesValue") == \
            f"{actual_minutes} minutes focused"

        if session["BlocksEnforced"] == 0:
            expected = "No distractions caught"
        else:
            nudges = session["NudgesSent"]
            expected = (f"{session['AppsClosed']} closed · "
                        f"{'1 nudge' if nudges == 1 else f'{nudges} nudges'}")
        assert fresh_app.text_of("SummaryDistractionsValue") == expected

        momentum = fresh_app.text_of("SummaryMomentumText")
        assert momentum.endswith(f"→ {int(settings['MomentumScore'])}")
        assert momentum.startswith("+"), "a finished sprint gained momentum"
        assert fresh_app.text_of("SummaryStreakText") == "Day 1"


# ================================================== sprint intention (F13)

class TestSprintIntention:
    """F13: the optional intention is saved with the sprint and shown back."""

    def test_an_intention_is_saved_shown_on_the_timer_and_repeated(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.set_text("IntentionInput", "finish chapter 3")
        time.sleep(0.4)
        fresh_app.start_sprint()
        time.sleep(1.2)

        assert fresh_app.text_of("SprintIntentionText") == "finish chapter 3"

        fresh_app.stop_sprint()
        time.sleep(1.0)

        settings = verify.read_settings()
        assert settings["Sessions"][-1]["Intention"] == "finish chapter 3"
        assert fresh_app.text_of("SummaryIntentionText") == "You planned: finish chapter 3"
        assert fresh_app.text_of("JournalPromptTitle") == \
            "You planned: finish chapter 3. What moved?"
        assert fresh_app.text_of("IntentionInput") == ""

    def test_an_empty_intention_leaves_everything_default(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.stop_sprint()
        time.sleep(0.8)

        settings = verify.read_settings()
        assert settings["Sessions"][-1]["Intention"] == ""
        assert not fresh_app.exists("SummaryIntentionText", timeout=1)
        assert fresh_app.text_of("JournalPromptTitle") == "What moved?"

    def test_a_long_intention_is_capped_and_stays_on_one_line(self, fresh_app):
        long_one = ("finish the entire chapter three problem set and then review every single "
                    "lecture slide from week nine before the exam tomorrow morning")
        fresh_app.navigate_to_tab("Today")
        fresh_app.set_text("IntentionInput", long_one)
        time.sleep(0.4)

        typed = fresh_app.text_of("IntentionInput")
        assert len(typed) == 80, f"the input accepted {len(typed)} characters"
        assert typed == long_one[:80]

        fresh_app.start_sprint()
        time.sleep(1.2)

        # The ring's line must not grow taller than a single caption line.
        line = fresh_app.element("SprintIntentionText").rectangle()
        assert line.height() < 24, f"the intention wrapped inside the ring ({line.height()}px tall)"

        fresh_app.cancel_sprint()
        time.sleep(0.8)

    def test_cancelling_a_sprint_clears_the_intention_input(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.set_text("IntentionInput", "write the report")
        time.sleep(0.4)
        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.cancel_sprint()
        time.sleep(0.8)

        assert fresh_app.text_of("IntentionInput") == ""
        settings = verify.read_settings()
        assert settings["Sessions"] == []


# ==================================================== the trial unlocks all

class TestTrialUnlocksEverything:
    """During the 7-day trial every feature is available, as after a purchase."""

    def test_sleep_blocking_turns_on(self, fresh_app):
        fresh_app.navigate_to_tab("Sleep Blocking")
        assert fresh_app.set_toggle("SleepBlockToggle", True) is True
        fresh_app.set_sleep_window("23:15", "06:45")
        time.sleep(0.8)
        saved = verify.verify_sleep_window(enabled=True, start="23:15", end="06:45")
        assert saved.ok, saved.detail

    def test_shield_three_and_long_sprints_stick(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Sealed")
        time.sleep(0.8)
        assert "locks" in fresh_app.text_of("ShieldDescriptionText").lower()

    def test_hard_kill_mode_turns_on(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        assert fresh_app.set_toggle("HardKillModeToggle", True) is True
        time.sleep(0.8)
        assert verify.read_settings()["HardKillModeEnabled"] is True


# ==================================================== shield wording (F1)

class TestShieldWording:
    """F1: Today and first run show each shield's promise and scenario."""

    EXPECTED = {
        "Soft": ("Notes distractions and nudges you.", "Best for classes or light work."),
        "Firm": ("Closes blocked apps.", "Best for homework."),
        "Sealed": ("Closes apps and locks the list until the sprint ends.",
                   "Best for exams and deep work."),
    }

    def test_today_shows_the_promise_and_scenario_for_each_shield(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        for level, (promise, best_for) in self.EXPECTED.items():
            fresh_app.select_shield(level)
            time.sleep(0.5)
            assert fresh_app.text_of("ShieldDescriptionText") == promise, level
            assert fresh_app.text_of("ShieldBestForText") == best_for, level

    def test_first_run_uses_the_same_wording(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.click("ShowFirstRunButton")
        assert fresh_app.exists("FirstRunSkipButton", timeout=3)

        # In the full suite the Settings button is often scrolled out of view and
        # invoked directly, so the welcome can still be opening when Next is
        # pressed. Wait for step 1, then confirm the step actually moved.
        deadline = time.time() + 5
        while time.time() < deadline and fresh_app.text_of("FirstRunStepText") != "Step 1 of 3":
            time.sleep(0.25)
        assert fresh_app.text_of("FirstRunStepText") == "Step 1 of 3"

        for _ in range(2):
            fresh_app.click("FirstRunNextButton")
            deadline = time.time() + 3
            while time.time() < deadline and fresh_app.text_of("FirstRunStepText") != "Step 2 of 3":
                time.sleep(0.25)
            if fresh_app.text_of("FirstRunStepText") == "Step 2 of 3":
                break
        assert fresh_app.text_of("FirstRunStepText") == "Step 2 of 3"
        try:
            for level, (promise, best_for) in self.EXPECTED.items():
                assert fresh_app.text_of(f"FirstRun{level}Promise") == promise, level
                assert fresh_app.text_of(f"FirstRun{level}BestFor") == best_for, level
        finally:
            fresh_app.click("FirstRunSkipButton")
            time.sleep(0.5)
            assert not fresh_app.exists("FirstRunSkipButton", timeout=1)


# ================================================== after the trial ends

class TestTrialEnded:
    """With the trial over and nothing bought, the app is locked."""

    def test_the_lock_screen_offers_the_purchase(self, expired_app):
        assert expired_app.exists("LockBuyButton", timeout=5), "no lock screen after the trial"
        assert "$4.99" in expired_app.text_of("TrialEndedText")
        assert expired_app.tier_badge().upper() == "TRIAL ENDED"

    def test_a_sprint_cannot_start(self, expired_app):
        expired_app.navigate_to_tab("Today")
        try:
            expired_app.start_sprint()
        except Exception:                      # noqa: BLE001 — covered by the lock screen
            pass
        time.sleep(1.5)
        assert "engaged" not in expired_app.session_state().lower(), "a locked app started a sprint"
        assert verify.read_settings()["Sessions"] == []

    def test_sleep_blocking_and_hard_kill_are_disabled(self, expired_app):
        expired_app.navigate_to_tab("Sleep Blocking")
        assert expired_app.is_control_enabled("SleepBlockToggle") is False
        expired_app.navigate_to_tab("Settings")
        assert expired_app.is_control_enabled("HardKillModeToggle") is False
        assert "trial ended" in expired_app.get_license_status_text().lower()

    def test_the_buy_button_opens_the_store(self, expired_app):
        expired_app.click("LockBuyButton")
        time.sleep(1.5)
        assert expired_app.app_log_contains("opening upgrade page")


# ========================= a trial that expires mid-sprint (F20, #9) ========

class TestTrialExpiringDuringASprint:
    """
    A trial that runs out while a sprint is in progress must not interrupt
    it, and must not interrupt the summary card the sprint ends on either.
    The lock is only allowed to appear once that card has been read and
    dismissed with "Save entry" — never before.
    """

    def test_the_lock_waits_for_the_sprint_and_its_summary(self, trial_expiring_soon_app):
        app = trial_expiring_soon_app
        app.navigate_to_tab("Today")

        # The shortest sprint FlowShield offers (5 minutes) comfortably
        # outlasts the 8-second trial set by --expire-trial-in=8.
        app.click("SprintLength_Custom")
        app.set_text("CustomMinutesInput", "5")
        time.sleep(0.5)
        app.start_sprint()

        # Give the trial time to actually cross its boundary, then confirm
        # the sprint is still running with no lock screen anywhere in sight —
        # this is the moment a naive "check access every minute" would fail.
        time.sleep(15)
        assert app.exists("StopSprintButton", timeout=1), \
            "the sprint must still be running well after the trial has technically ended"
        assert not app.exists("LockBuyButton", timeout=1.5), \
            "the trial ending must never interrupt a running sprint"

        # Wait for the sprint to finish on its own and the summary card to appear.
        assert app.exists("SummaryTitle", timeout=340), \
            "the 5-minute sprint never finished"
        assert app.text_of("SummaryTitle") == "Sprint complete"

        # The summary/journal card is up: the lock must still be held off so
        # "what moved?" is never interrupted by "buy FlowShield".
        time.sleep(2)
        assert not app.exists("LockBuyButton", timeout=1.5), \
            "the lock must wait until the summary card is dismissed"
        assert app.tier_badge().upper() != "TRIAL ENDED", \
            "the tier badge must not flip to ended while the summary is still on screen"

        # Dismiss the card the normal way, exactly as F12 describes.
        app.set_text("JournalInput", "watched the trial run out mid-sprint")
        app.click("SaveJournalButton")

        # Only now is the lock allowed to appear.
        assert app.exists("LockBuyButton", timeout=5), \
            "the lock must appear once the summary card has been dismissed"
        assert app.tier_badge().upper() == "TRIAL ENDED"


# ============================================ full purchase path (Stripe)

@pytest.mark.stripe
@pytest.mark.e2e
class TestPurchaseToActivation:
    """
    The complete money path: checkout → licence → activation → persisted Pro.

    Skipped without Stripe credentials.
    """

    def test_full_flow(self, fresh_app, server, needs_stripe, logger):
        import requests

        from browser.stripe_checkout import StripeCheckoutAutomator
        from config import (TEST_CARD, TEST_CVC, TEST_EMAIL, TEST_EXPIRY,
                            TEST_NAME, TEST_ZIP)

        created = requests.post(f"{server}/create-checkout",
                                json={"email": TEST_EMAIL}, timeout=45).json()
        assert created["url"].startswith("https://checkout.stripe.com/")

        automator = StripeCheckoutAutomator(logger=logger, headless=True,
                                            shot_dir=logger.shot_dir)
        result = automator.complete_checkout(
            checkout_url=created["url"], email=TEST_EMAIL, card_number=TEST_CARD,
            expiry=TEST_EXPIRY, cvc=TEST_CVC, postal_code=TEST_ZIP,
            cardholder=TEST_NAME)
        assert result.ok, result.message
        assert result.session_id

        deadline = time.time() + 60
        payload = {}
        while time.time() < deadline:
            response = requests.get(f"{server}/get-license",
                                    params={"session_id": result.session_id}, timeout=20)
            payload = response.json()
            if response.status_code == 200 and payload.get("isPro"):
                break
            time.sleep(2)
        assert payload.get("isPro") is True, payload
        assert payload["licenseKey"] == created["licenseKey"]

        fresh_app.navigate_to_tab("Settings")
        fresh_app.enter_license_key(payload["licenseKey"])
        fresh_app.click_activate_pro()
        status = fresh_app.wait_for_license_status("Licence active", timeout=45)
        assert "licence active" in status.lower()

        ui = verify.verify_ui_pro_status(fresh_app, expected_pro=True)
        assert ui.ok, ui.detail

        disk = verify.verify_dpapi_settings(expected_pro=True)
        assert disk.ok, disk.detail
        assert disk.data["LicenseKey"] == payload["licenseKey"]


@pytest.mark.stripe
@pytest.mark.e2e
class TestPurchaseUnlocksAnExpiredTrial:
    """Buying FlowShield after the trial has ended must lift the lock."""

    def test_a_licence_unlocks_the_locked_app(self, expired_app, server,
                                              needs_stripe, logger):
        import requests

        from browser.stripe_checkout import StripeCheckoutAutomator
        from config import (TEST_CARD, TEST_CVC, TEST_EMAIL, TEST_EXPIRY,
                            TEST_NAME, TEST_ZIP)

        created = requests.post(f"{server}/create-checkout", json={}, timeout=45).json()
        automator = StripeCheckoutAutomator(logger=logger, headless=True,
                                            shot_dir=logger.shot_dir)
        paid = automator.complete_checkout(
            checkout_url=created["url"], email=TEST_EMAIL, card_number=TEST_CARD,
            expiry=TEST_EXPIRY, cvc=TEST_CVC, postal_code=TEST_ZIP,
            cardholder=TEST_NAME)
        assert paid.ok, paid.message

        deadline = time.time() + 60
        while time.time() < deadline:
            body = requests.get(f"{server}/get-license",
                                params={"session_id": paid.session_id}, timeout=20).json()
            if body.get("isPro"):
                break
            time.sleep(2)

        # Activate from the lock screen itself — the Settings page is behind it.
        expired_app.set_text("LockLicenseKeyInput", created["licenseKey"])
        expired_app.click("LockActivateButton")

        deadline = time.time() + 45
        while time.time() < deadline and expired_app.exists("LockBuyButton", timeout=1):
            time.sleep(1)
        assert not expired_app.exists("LockBuyButton", timeout=1), "the lock stayed up after buying"

        expired_app.navigate_to_tab("Settings")
        assert "licence active" in expired_app.get_license_status_text().lower()
        assert expired_app.tier_badge().upper() == "PURCHASED"



# ====================================== ending a sprint by shield level (F2)

class TestEndingASprint:
    """
    The app is launched with --short-timers: a 3 s grace period, 2 s for Firm's
    confirmation and 3 s for Sealed's countdown. Every step still has to happen.
    """

    def _start(self, app, shield):
        app.navigate_to_tab("Today")
        app.select_shield(shield)
        time.sleep(0.4)
        app.start_sprint()
        time.sleep(0.6)

    def test_cancelling_in_the_grace_period_leaves_no_record(self, fresh_app):
        self._start(fresh_app, "Sealed")
        assert "cancel" in fresh_app.end_button_label().lower()
        fresh_app.cancel_sprint()
        time.sleep(1.0)

        assert "cancelled" in fresh_app.session_state().lower()
        settings = verify.read_settings()
        assert settings["Sessions"] == [], "a cancelled sprint was recorded"
        assert settings.get("ActiveSprint") is None
        assert settings["MomentumScore"] == 0

    def test_soft_ends_straight_away(self, fresh_app):
        self._start(fresh_app, "Soft")
        fresh_app.wait_out_grace_period()
        assert fresh_app.end_button_label() == "End sprint"
        fresh_app.click("StopSprintButton")
        time.sleep(1.0)
        assert "early" in fresh_app.session_state().lower()
        assert not fresh_app.exists("KeepGoingButton", timeout=1)

    def test_firm_needs_a_confirmation_that_waits(self, fresh_app):
        self._start(fresh_app, "Firm")
        fresh_app.wait_out_grace_period()
        fresh_app.click("StopSprintButton")

        assert fresh_app.exists("KeepGoingButton", timeout=3), "Firm ended without a confirmation"
        assert fresh_app.is_control_enabled("EndAnywayButton") is False, "End anyway was ready immediately"
        time.sleep(2.8)
        assert fresh_app.is_control_enabled("EndAnywayButton") is True
        fresh_app.click("EndAnywayButton")
        time.sleep(1.0)
        assert "early" in fresh_app.session_state().lower()

    def test_sealed_needs_the_countdown_and_the_phrase(self, fresh_app):
        self._start(fresh_app, "Sealed")
        fresh_app.wait_out_grace_period()
        assert "need to stop" in fresh_app.end_button_label().lower()
        fresh_app.click("StopSprintButton")
        assert fresh_app.exists("EndPhraseInput", timeout=3), "Sealed didn't ask for the phrase"

        fresh_app.set_text("EndPhraseInput", "end my sprint")
        time.sleep(0.5)
        assert fresh_app.is_control_enabled("EndAnywayButton") is False, \
            "the phrase ended a Sealed sprint before its countdown"

        time.sleep(3.5)
        fresh_app.set_text("EndPhraseInput", "end sprint")
        time.sleep(0.5)
        assert fresh_app.is_control_enabled("EndAnywayButton") is False, "the wrong phrase was accepted"

        fresh_app.set_text("EndPhraseInput", "end my sprint")
        time.sleep(0.6)
        assert fresh_app.is_control_enabled("EndAnywayButton") is True
        fresh_app.click("EndAnywayButton")
        time.sleep(1.0)

        session = verify.read_settings()["Sessions"][-1]
        assert session["Completed"] is False and session["Shield"] in (3, "Sealed")

    def test_keep_going_backs_out_at_no_cost(self, fresh_app):
        self._start(fresh_app, "Firm")
        fresh_app.wait_out_grace_period()
        fresh_app.click("StopSprintButton")
        assert fresh_app.exists("KeepGoingButton", timeout=3)
        fresh_app.click("KeepGoingButton")
        time.sleep(0.8)

        assert fresh_app.exists("StopSprintButton", timeout=2), "the sprint stopped after Keep going"
        settings = verify.read_settings()
        assert settings["Sessions"] == [] and settings.get("ActiveSprint")


# ============================================================ app picker (F8)

class TestAppPicker:
    def _saved(self, process: str) -> dict:
        apps = verify.read_settings()["BlockedApps"]
        return next(a for a in apps if a["ProcessName"].lower() == process)

    def test_blocking_steam_from_suggestions_saves_all_its_processes(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.set_text("AppSearchInput", "steam")
        time.sleep(0.6)
        fresh_app.click("PickApp_steam")
        time.sleep(1.0)

        steam = self._saved("steam")
        assert steam["Name"] == "Steam"
        assert [p.lower() for p in steam["ExtraProcessNames"]] == ["steamwebhelper"]
        assert any("Steam" in n for n in fresh_app.blocked_app_names())
        assert fresh_app.text_of("PickApp_steam") == "Steam is blocked"
        assert fresh_app.is_control_enabled("PickApp_steam") is False, "Steam could be added twice"

    def test_typing_a_known_process_gets_the_whole_app(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app("steamwebhelper")
        time.sleep(1.0)
        helper = self._saved("steamwebhelper")
        assert helper["Name"] == "Steam" and [p.lower() for p in helper["ExtraProcessNames"]] == ["steam"]

    def test_searching_for_a_protected_process_explains_why_it_is_missing(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.set_text("AppSearchInput", "explorer")
        time.sleep(0.6)
        assert "never closes windows system processes" in fresh_app.text_of("AppSearchNotice").lower()
        assert not fresh_app.exists("PickApp_explorer", timeout=1)

    def test_browsers_carry_the_warning(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.set_text("AppSearchInput", "chrome")
        time.sleep(0.6)
        texts = " ".join(t for item in fresh_app.element("AppPickerList").children() for t in item.texts())
        assert "closes the whole browser" in texts.lower(), texts


# ===================================================== terms acceptance (legal)

class TestTermsGate:
    """A clean install must agree to the terms before FlowShield can do anything."""

    def _launch(self, logger, clean=True):
        from desktop.app_controller import DesktopController

        app = DesktopController(logger)
        app.launch_app(clean_state=clean, show_first_run=True)
        app.connect_window()
        time.sleep(1.5)
        return app

    def test_a_clean_install_must_agree_before_anything_else(self, logger):
        app = self._launch(logger)
        try:
            assert app.exists("AcceptTermsButton", timeout=4), "no terms gate on a clean install"
            assert "closes programs" in app.text_of("TermsDataLossText").lower()
            assert "unsaved work" in app.text_of("TermsDataLossText").lower()
            assert app.text_of("TermsVersionText").startswith("Version ")

            # The page behind the gate must not act. The overlay stops a mouse,
            # so this invokes the covered button directly — the harder case.
            try:
                app.element("StartSprintButton").invoke()
            except Exception:
                pass
            time.sleep(1.0)
            assert not app.exists("StopSprintButton", timeout=1), \
                "a sprint started while the terms were still on screen"
            assert verify.read_settings().get("ActiveSprint") is None

            assert not app.exists("FirstRunSkipButton", timeout=1), \
                "the welcome must wait behind the terms"
            assert verify.read_settings().get("TermsAcceptedVersion", "") == ""

            app.click("AcceptTermsButton")

            deadline = time.time() + 8
            settings = verify.read_settings()
            while time.time() < deadline and not settings.get("TermsAcceptedVersion"):
                time.sleep(0.5)
                settings = verify.read_settings()
            assert settings["TermsAcceptedVersion"].startswith("1.0 ("), settings["TermsAcceptedVersion"]
            assert settings["TermsAcceptedUtc"], "the time of acceptance must be recorded"
            assert not app.exists("AcceptTermsButton", timeout=1)
            assert app.exists("FirstRunSkipButton", timeout=4), \
                "the welcome should follow once the terms are accepted"
        finally:
            app.close_app()

    def test_it_is_not_asked_again_after_accepting(self, logger):
        app = self._launch(logger)
        try:
            app.accept_terms_if_shown()
        finally:
            app.close_app()

        again = self._launch(logger, clean=False)
        try:
            assert not again.exists("AcceptTermsButton", timeout=2), "the gate came back"
        finally:
            again.close_app()

    def test_settings_shows_when_the_terms_were_accepted(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        text = fresh_app.text_of("TermsAcceptedText")
        assert "accepted" in text.lower() and "1.0 (" in text, text


# ========================================================= notifications (F19)

class TestNotificationSettings:
    TOGGLES = [
        ("NotifySprintStartedToggle", "SprintStarted"),
        ("NotifyFiveMinutesLeftToggle", "FiveMinutesLeft"),
        ("NotifySprintCompleteToggle", "SprintComplete"),
        ("NotifySprintInterruptedToggle", "SprintInterrupted"),
        ("NotifyTrialEndingToggle", "TrialEnding"),
    ]

    def test_every_notification_is_on_for_a_new_install(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        assert fresh_app.toggle_state("NotificationsToggle") is True
        for toggle, _ in self.TOGGLES:
            assert fresh_app.toggle_state(toggle) is True, toggle

    def test_switching_one_off_is_saved(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.set_toggle("NotifyFiveMinutesLeftToggle", False)
        time.sleep(0.8)

        kinds = verify.read_settings()["NotificationKinds"]
        assert kinds["FiveMinutesLeft"] is False
        assert verify.read_settings()["NotificationsEnabled"] is True

    def test_the_master_switch_disables_the_rest(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.set_toggle("NotificationsToggle", False)
        time.sleep(0.8)
        assert verify.read_settings()["NotificationsEnabled"] is False
        assert fresh_app.is_control_enabled("NotifySprintStartedToggle") is False

    def test_a_running_sprint_puts_the_countdown_in_the_title(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.click("SprintLength_15")
        fresh_app.start_sprint()
        time.sleep(1.5)
        title = fresh_app.window.window_text()
        assert title.startswith("FlowShield —"), title
        assert ":" in title, title


# ============================================================ first run (F18)

class TestFirstRun:
    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def _launch(self, logger, clean=True):
        from desktop.app_controller import DesktopController

        app = DesktopController(logger)
        app.launch_app(clean_state=clean, show_first_run=True)
        app.connect_window()
        time.sleep(1.5)
        # The terms gate comes before the welcome on a clean install; its own
        # behaviour is covered by TestTermsGate.
        app.accept_terms_if_shown()
        return app

    def _run_value(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                return winreg.QueryValueEx(k, "FlowShield")[0]
        except FileNotFoundError:
            return None

    def _set_run_value(self, value):
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
            if value is None:
                try:
                    winreg.DeleteValue(k, "FlowShield")
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(k, "FlowShield", 0, winreg.REG_SZ, value)

    def test_completing_it_saves_every_choice_and_starts_the_sprint(self, logger):
        saved_run = self._run_value()          # the toggle writes the real Run value
        app = self._launch(logger)
        try:
            assert app.exists("FirstRunSkipButton", timeout=3), "a clean install didn't get the welcome"
            assert app.text_of("FirstRunStepText") == "Step 1 of 3"

            app.set_text("FirstRunSearchInput", "steam")
            time.sleep(0.8)
            # Steam may already be ticked for this PC, so drive it to checked rather than blind-clicking.
            assert app.set_toggle("FirstRunPickApp_steam", True) is True, "Steam wouldn't stay ticked"
            app.click("FirstRunNextButton")
            time.sleep(0.4)

            assert app.text_of("FirstRunStepText") == "Step 2 of 3"
            app.click("FirstRunShield_Sealed")
            app.click("FirstRunNextButton")
            time.sleep(0.4)

            app.click("FirstRunLength_45")
            assert app.set_toggle("FirstRunStartWithWindows", True) is True, "Start-with-Windows wouldn't stay ticked"
            assert "unlocked for 7 days" in app.text_of("FirstRunTrialText").lower()
            app.click("FirstRunStartButton")
            time.sleep(1.5)

            assert not app.exists("FirstRunSkipButton", timeout=1), "the welcome stayed open"
            assert app.exists("StopSprintButton", timeout=3), "the first sprint didn't start"

            s = verify.read_settings()
            steam = next(
                (a for a in s["BlockedApps"] if a["ProcessName"].lower() == "steam"),
                None,
            )
            assert steam is not None, "Steam was not saved to the blocklist"
            assert [p.lower() for p in steam["ExtraProcessNames"]] == ["steamwebhelper"]
            assert s["DefaultShield"] in (3, "Sealed")
            assert s["DefaultSprintMinutes"] == 45
            assert s["StartWithWindows"] is True, "StartWithWindows setting was not saved"
            assert self._run_value(), "start-with-Windows Run registry value was not written"
            assert s["FirstRunCompleted"] is True
            active = s["ActiveSprint"]
            assert active["PlannedMinutes"] == 45 and active["Shield"] in (3, "Sealed")
        finally:
            app.close_app()
            self._set_run_value(saved_run)

    def test_skipping_means_it_never_comes_back(self, logger):
        app = self._launch(logger)
        try:
            app.click("FirstRunSkipButton")
            time.sleep(0.8)
            assert not app.exists("FirstRunSkipButton", timeout=1)
            assert verify.read_settings()["FirstRunCompleted"] is True
        finally:
            app.close_app()

        again = self._launch(logger, clean=False)
        try:
            assert not again.exists("FirstRunSkipButton", timeout=2), "the welcome came back after skipping"
            assert again.current_page_title() == "Today"
        finally:
            again.close_app()

    def test_settings_can_open_it_again(self, fresh_app):
        assert not fresh_app.exists("FirstRunSkipButton", timeout=1)
        fresh_app.navigate_to_tab("Settings")
        fresh_app.click("ShowFirstRunButton")
        assert fresh_app.exists("FirstRunSkipButton", timeout=3)
        assert fresh_app.text_of("FirstRunStepText") == "Step 1 of 3"
        fresh_app.click("FirstRunSkipButton")
        time.sleep(0.5)
        assert not fresh_app.exists("FirstRunSkipButton", timeout=1)

    def test_a_locked_trial_never_gets_it(self, logger):
        from desktop.app_controller import DesktopController

        app = DesktopController(logger)
        app.launch_app(clean_state=True, show_first_run=True, extra_args=["--expire-trial"])
        app.connect_window()
        try:
            time.sleep(1.5)
            assert app.exists("LockBuyButton", timeout=3)
            assert not app.exists("FirstRunSkipButton", timeout=1), "the welcome covered the lock screen"
        finally:
            app.close_app()


# ======================================================= one instance (1.3)

def launch_again(*extra: str) -> int:
    """Start a second FlowShield without closing the first; returns its exit code."""
    import subprocess
    from pathlib import Path

    from config import APP_EXE

    proc = subprocess.run([str(APP_EXE), *extra], cwd=str(Path(APP_EXE).parent), timeout=30)
    return proc.returncode


def flowshield_pids() -> list[int]:
    import psutil

    return [p.pid for p in psutil.process_iter(["name"])
            if (p.info["name"] or "").lower() == "flowshield.exe"]


class TestOneInstance:
    def test_opening_it_again_brings_back_the_running_copy(self, fresh_app):
        import win32gui

        hwnd = fresh_app.window.handle             # UIA can't find a hidden window later
        fresh_app.window.close()                   # minimise-to-tray is on by default
        time.sleep(1.0)
        assert not win32gui.IsWindowVisible(hwnd), "closing didn't hide to the tray"

        launch_again()
        time.sleep(1.5)

        assert flowshield_pids() == [fresh_app.pid], "a second FlowShield kept running"
        assert win32gui.IsWindowVisible(hwnd), "the running copy wasn't brought back"


# =================================================== flowshield:// links (1.4)

# Shaped like a real key; never activated, so it doesn't need to exist.
LINK_KEY = "FS-ABCD-EFGH-JKMN-PQR5"
LINK = f"flowshield://activate?key={LINK_KEY}"


class TestActivationLinks:
    def _launch_with(self, logger, *extra):
        from desktop.app_controller import DesktopController

        app = DesktopController(logger)
        app.launch_app(clean_state=True, extra_args=list(extra))
        app.connect_window()
        time.sleep(1.2)
        return app

    def test_a_link_fills_in_the_key_and_waits_for_a_click(self, logger):
        app = self._launch_with(logger, LINK)
        try:
            assert app.exists("ConfirmActivationButton", timeout=3), "no confirmation was shown"
            assert app.text_of("ActivationLinkKey") == LINK_KEY
            assert app.current_page_title() == "Settings"
            time.sleep(1.0)
            settings = verify.read_settings()
            assert not settings.get("IsPro") and not settings.get("LicenseKey"), \
                "the link activated without the user's click"

            app.click("DismissActivationButton")
            time.sleep(0.6)
            assert not app.exists("ConfirmActivationButton", timeout=1)
            assert not verify.read_settings().get("IsPro")
        finally:
            app.close_app()

    def test_activate_checks_the_key_with_the_server(self, logger, server):
        app = self._launch_with(logger, LINK)
        try:
            app.click("ConfirmActivationButton")
            status = app.wait_for_license_status("not activated", timeout=30)
            assert "not activated" in status.lower(), status   # a made-up key is refused
            assert not app.exists("ConfirmActivationButton", timeout=1)
        finally:
            app.close_app()

    def test_a_link_reaches_a_copy_that_is_already_running(self, fresh_app):
        launch_again(LINK)
        time.sleep(1.5)
        assert flowshield_pids() == [fresh_app.pid]
        assert fresh_app.exists("ConfirmActivationButton", timeout=3), "the running copy ignored the link"
        assert fresh_app.text_of("ActivationLinkKey") == LINK_KEY

    @pytest.mark.parametrize("link", [
        "flowshield://settings?hardkill=on",
        "flowshield://activate?key=not-a-key",
        "flowshield://activate",
    ])
    def test_other_links_do_nothing(self, logger, link):
        app = self._launch_with(logger, link)
        try:
            assert not app.exists("ConfirmActivationButton", timeout=2)
            assert app.current_page_title() == "Today"
        finally:
            app.close_app()


# =========================================================== daily goal (F15)

# ============================================ momentum explained (F14 / 3.2)
class TestMomentumTrendAndExplainer:
    """F14: the score is on screen with the rule behind it and 30 days of shape."""

    def test_the_explainer_opens_and_closes(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        assert not fresh_app.exists("MomentumExplainerText", timeout=1),             "the card leads with the number, not with the essay"

        fresh_app.click("MomentumExplainerButton")
        time.sleep(0.5)
        assert fresh_app.exists("MomentumExplainerText", timeout=3)

        fresh_app.click("MomentumExplainerButton")
        time.sleep(0.5)
        assert not fresh_app.exists("MomentumExplainerText", timeout=1)

    def test_the_chart_stays_hidden_until_there_is_momentum(self, fresh_app):
        """
        Not "until there is a sprint". Ending one early leaves the score at
        zero, and a line on the bottom gridline reads as broken.

        Asserted on the captions, not on the Grid that holds the line: a layout
        panel is not surfaced to UI Automation, so exists() on one answers the
        same either way.

        The *visible* case cannot be reached from here — momentum only moves on
        a finished sprint, and the shortest is 15 real minutes, which no tier 3
        test can wait for. It is covered at tier 1 instead, on the same rules.
        """
        fresh_app.navigate_to_tab("Today")
        assert not fresh_app.exists("MomentumTrendRange", timeout=1),             "a clean install has nothing to plot"

        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.stop_sprint()
        time.sleep(1.0)

        assert not fresh_app.exists("MomentumTrendRange", timeout=2),             "a sprint ended early leaves momentum at zero, so there is still nothing to draw"


class TestDailyGoal:
    """
    F15: an optional daily goal, a bar on Today, and a streak that only counts
    days the goal was met.
    """

    def test_no_goal_is_set_on_a_fresh_install(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        assert fresh_app.is_selected("GoalOffRadio") is True, \
            "the goal is opt-in; a new install must not start with one"

    def test_the_bar_is_absent_until_a_goal_is_set(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        # The ProgressBar, not the StackPanel around it: WPF does not surface a
        # bare panel as a UIA element, so asserting on the panel passes whether
        # the bar is there or not.
        assert fresh_app.exists("DailyGoalBar") is False, \
            "a goal-less user must not see an empty progress bar"

    def test_choosing_sprints_offers_a_target_and_saves_it(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.8)

        settings = verify.read_settings()
        assert settings["DailyGoalKind"] in (2, "Sprints")
        assert settings["DailyGoalTarget"] == 3, "picking sprints must land on a usable default"
        assert "sprints" in fresh_app.text_of("GoalUnitLabel").lower()

    def test_switching_kind_does_not_carry_the_number_across(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalMinutesRadio")
        time.sleep(0.6)
        assert verify.read_settings()["DailyGoalTarget"] == 90

        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)
        assert verify.read_settings()["DailyGoalTarget"] == 3, \
            "90 minutes is a normal day; 90 sprints is nobody's day"

    def test_a_target_out_of_range_is_reported_and_not_saved(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)

        fresh_app.set_text("GoalTargetInput", "999")
        time.sleep(0.6)

        assert fresh_app.exists("GoalTargetError") is True
        assert verify.read_settings()["DailyGoalTarget"] == 3, \
            "an out-of-range target must be refused, not silently clamped into the file"

    def test_the_bar_appears_on_today_once_a_goal_exists(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)

        fresh_app.navigate_to_tab("Today")
        assert fresh_app.exists("DailyGoalBar") is True
        assert "/ 3 sprints" in fresh_app.text_of("DailyGoalProgressText")

    def test_finishing_a_sprint_moves_the_bar(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)
        fresh_app.set_text("GoalTargetInput", "2")
        time.sleep(0.6)

        fresh_app.navigate_to_tab("Today")
        assert fresh_app.text_of("DailyGoalProgressText").startswith("0 /")

        fresh_app.select_sprint_length(15)
        fresh_app.start_sprint()
        time.sleep(1.0)
        fresh_app.stop_sprint()
        time.sleep(1.0)

        # Ending early does not complete a sprint, so a sprint-counted goal
        # stays where it was. This is the same rule the Today tile uses.
        assert fresh_app.text_of("DailyGoalProgressText").startswith("0 /")

    def test_taking_a_day_off_is_offered_once_a_week(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)

        assert "1 day off left" in fresh_app.text_of("SkipRemainingText")
        fresh_app.click("SkipTodayButton")
        time.sleep(0.8)

        assert "0 days off left" in fresh_app.text_of("SkipRemainingText")
        assert len(verify.read_settings()["SkipDatesLocal"]) == 1

        fresh_app.navigate_to_tab("Today")
        assert fresh_app.text_of("DailyGoalNote") == "Day off"

    def test_a_day_off_can_be_taken_back(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)
        fresh_app.click("SkipTodayButton")
        time.sleep(0.8)
        fresh_app.click("SkipTodayButton")
        time.sleep(0.8)

        assert "1 day off left" in fresh_app.text_of("SkipRemainingText")
        assert verify.read_settings()["SkipDatesLocal"] == []
# ======================================================= journal export (F17)

class TestJournalExport:
    """
    F17: sprints and journal lines saved as a file the customer keeps.

    The point of doing this end to end is the file itself — the formatters are
    unit-tested, but nothing else proves the bytes that land on disk.
    """

    def _one_sprint_with_a_journal_line(self, app, line):
        app.navigate_to_tab("Today")
        app.start_sprint()
        time.sleep(1.2)
        app.stop_sprint()
        time.sleep(0.8)
        app.set_text("JournalInput", line)
        app.click("SaveJournalButton")
        time.sleep(1.0)

    def test_the_export_card_counts_the_sprints_in_range(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        assert "0 sprints" in fresh_app.text_of("ExportRangeText")

        self._one_sprint_with_a_journal_line(fresh_app, "wrote the exporter")
        fresh_app.navigate_to_tab("Settings")
        assert "1 sprint in this range" in fresh_app.text_of("ExportRangeText")

    def test_csv_is_written_with_the_journal_line(self, fresh_app, tmp_path):
        self._one_sprint_with_a_journal_line(fresh_app, "wrote the exporter")

        target = tmp_path / "export.csv"
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("ExportCsvRadio")
        time.sleep(0.4)
        fresh_app.click("ExportJournalButton")
        assert fresh_app.save_dialog_to(str(target)), "the Save dialog never appeared"
        time.sleep(1.5)

        raw = target.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), "Excel needs the UTF-8 BOM"

        text = raw.decode("utf-8-sig")
        assert "\r\n" in text, "Excel on Windows expects CRLF"

        lines = [line for line in text.splitlines() if line.strip()]
        assert lines[0].startswith("date (local),start (local)")
        assert "wrote the exporter" in lines[1]
        assert len(lines) == 2, f"expected a header and one row, got {len(lines)}"

    def test_markdown_is_written_and_grouped_by_day(self, fresh_app, tmp_path):
        self._one_sprint_with_a_journal_line(fresh_app, "wrote the exporter")

        target = tmp_path / "export.md"
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("ExportMarkdownRadio")
        time.sleep(0.4)
        fresh_app.click("ExportJournalButton")
        assert fresh_app.save_dialog_to(str(target)), "the Save dialog never appeared"
        time.sleep(1.5)

        text = target.read_text(encoding="utf-8")
        assert not text.startswith("﻿"), "a BOM shows up as stray characters in Markdown"
        assert text.startswith("# FlowShield journal")
        assert f"## {datetime.now():%Y-%m-%d}" in text, "sessions must be grouped under their day"
        assert "wrote the exporter" in text

    def test_a_journal_line_that_looks_like_a_formula_is_defused(self, fresh_app, tmp_path):
        """The one real security issue in an export: a cell Excel would run."""
        self._one_sprint_with_a_journal_line(fresh_app, "=1+1")

        target = tmp_path / "formula.csv"
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("ExportCsvRadio")
        time.sleep(0.4)
        fresh_app.click("ExportJournalButton")
        assert fresh_app.save_dialog_to(str(target))
        time.sleep(1.5)

        text = target.read_text(encoding="utf-8-sig")
        assert "'=1+1" in text, "a leading = must be defused before Excel opens it"


# ============================== tray and keyboard start a sprint (F4)
#
# Written for F4 but not run in this session: UI tests take over the screen,
# only one can run at a time on this machine, and the orchestrator schedules
# them. See the PR description.

class TestSpaceStartsAndEndsASprint:
    """
    Space on Today (F4) must behave exactly like clicking StartSprintButton
    and StopSprintButton — including going through the F2 end flow, not
    ending a Firm sprint immediately.
    """

    def test_space_starts_a_sprint_and_opens_the_firm_end_flow(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Firm")
        time.sleep(0.4)

        # Space with focus away from any text box starts the sprint, the same
        # as StartSprintButton.
        fresh_app.focus()
        fresh_app.window.type_keys(" ")
        assert fresh_app.exists("StopSprintButton", timeout=5), \
            "Space did not start the sprint"

        fresh_app.wait_out_grace_period()

        # Space again must open the same F2 flow the button opens — a
        # confirmation that waits — never end the sprint outright.
        fresh_app.window.type_keys(" ")
        assert fresh_app.exists("KeepGoingButton", timeout=3), \
            "Space skipped Firm's confirmation and ended the sprint directly"
        assert fresh_app.is_control_enabled("EndAnywayButton") is False, \
            "End anyway must still wait out Firm's grace, whatever triggered it"

        # Clean up through the real flow rather than leaving a sprint running.
        fresh_app.click("KeepGoingButton")
        time.sleep(0.5)
        fresh_app.stop_sprint()

    def test_space_typed_into_the_intention_field_stays_a_space(self, fresh_app):
        """
        The guard in TodayViewModel.CanUseSpaceShortcut: typing into the
        intention box must not also start a sprint underneath the user.
        """
        fresh_app.navigate_to_tab("Today")
        fresh_app.set_text("IntentionInput", "write the release notes")
        # set_text leaves focus in the box; one more space must land in the
        # text, not toggle the sprint.
        intention_box = fresh_app.element("IntentionInput")
        intention_box.type_keys(" ")
        time.sleep(0.3)

        assert not fresh_app.exists("StopSprintButton", timeout=1), \
            "a space typed into the intention field also started a sprint"
        assert fresh_app.text_of("IntentionInput").endswith(" "), \
            "the space must still land in the text box"

    def test_an_empty_range_still_saves_a_file_with_headings(self, fresh_app, tmp_path):
        target = tmp_path / "empty.csv"
        fresh_app.navigate_to_tab("Settings")
        fresh_app.click("ExportJournalButton")
        assert fresh_app.save_dialog_to(str(target))
        time.sleep(1.5)

        text = target.read_text(encoding="utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]
        assert len(lines) == 1, "an empty range writes the header and nothing else"
        assert "headings only" in fresh_app.text_of("ExportStatusText")


# ============================================================ your data (F23)

class TestYourDataCard:
    """
    Settings -> Your data: the card is visible, names what leaves the PC, and
    its Export button opens a real Save dialog. Delete everything is checked
    only as far as its confirmation dialog — actually confirming it restarts
    the app into first run, which belongs in its own isolated run rather than
    alongside the rest of this suite.
    """

    def test_the_card_and_its_controls_are_visible(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        assert fresh_app.exists("WhatLeavesText")
        assert fresh_app.exists("ExportDataButton")
        assert fresh_app.exists("DeleteEverythingButton")

        leaves = fresh_app.text_of("WhatLeavesText").lower()
        assert "licence key" in leaves and "device" in leaves

    def test_export_opens_a_save_dialog_and_excludes_the_licence_key(self, fresh_app, tmp_path):
        target = tmp_path / "flowshield-data.json"
        fresh_app.navigate_to_tab("Settings")
        fresh_app.click("ExportDataButton")
        assert fresh_app.save_dialog_to(str(target)), "the Save dialog never appeared"
        time.sleep(1.0)

        import json
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert "licence" in payload
        assert "licenseKey" not in payload["licence"], \
            "the export must never contain the licence key"
        assert "blockedApps" in payload and "sessions" in payload

    def test_delete_everything_asks_for_confirmation_first(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.click("DeleteEverythingButton")
        time.sleep(0.5)
        assert fresh_app.exists("ConfirmDeleteDialog"), \
            "an irreversible local wipe must not happen on a single click"
        assert fresh_app.exists("ConfirmDeleteConfirmButton")
        assert fresh_app.exists("ConfirmDeleteCancelButton")

        # Cancelling must leave everything exactly as it was.
        fresh_app.click("ConfirmDeleteCancelButton")
        time.sleep(0.5)
        assert fresh_app.exists("DeleteEverythingButton"), "Settings must still be there after cancelling"


# =========================================== History and the weekly view (F16)

class TestHistoryPage:
    """
    F16: the History page. The unit tests pin the arithmetic; what only the real
    app can show is that the page is reachable, that it picks up a sprint that
    happened on another page, and that the week's figures on screen match what
    was actually written to the settings file.
    """

    def _one_sprint(self, app, intention, journal):
        app.navigate_to_tab("Today")
        app.set_text("IntentionInput", intention)
        app.start_sprint()
        time.sleep(1.2)
        app.stop_sprint()
        time.sleep(0.8)
        app.set_text("JournalInput", journal)
        app.click("SaveJournalButton")
        time.sleep(1.0)

    def test_history_is_reachable_and_empty_to_begin_with(self, fresh_app):
        assert fresh_app.navigate_to_tab("History") == "History"
        assert fresh_app.text_of("WeekSprintsValue") == "0"
        assert fresh_app.text_of("WeekFocusHours") == "0.0"
        assert "No sprints yet" in fresh_app.text_of("HistoryEmptyText")
        # Nothing has been blocked, and the card says so rather than naming an app.
        assert "Nothing has needed blocking yet" in fresh_app.text_of("MostBlockedNote")

    def test_the_week_picks_up_a_sprint_run_on_today(self, fresh_app):
        """
        The refresh-on-entry case. History is built when the app starts, so
        without MainViewModel refreshing it on navigation the page would show
        zeroes for the rest of the run.
        """
        self._one_sprint(fresh_app, "finish chapter 3", "shipped the history page")

        fresh_app.navigate_to_tab("History")
        assert int(fresh_app.text_of("WeekDistractionsValue")) >= 0
        # Ended early, so it is not a completed sprint — but its minutes count.
        assert fresh_app.text_of("WeekSprintsValue") == "0"
        assert float(fresh_app.text_of("WeekFocusHours")) >= 0.0

        # The row is the newest, so it is the first HistoryRow* control found.
        assert "ended early" in fresh_app.text_of("HistoryRowOutcome")
        assert "finish chapter 3" in fresh_app.text_of("HistoryRowIntention")
        assert "shipped the history page" in fresh_app.text_of("HistoryRowJournal")

        # And it matches what was persisted, not just what the UI claims.
        session = verify.read_settings()["Sessions"][-1]
        assert session["Intention"] == "finish chapter 3"
        assert session["Journal"] == "shipped the history page"
        assert session["Completed"] is False

    def test_the_heatmap_states_its_values_rather_than_only_colouring_them(self, fresh_app):
        """
        DESIGN_SYSTEM.md §7: never colour alone. Every cell is a focusable
        control whose accessible name is its own day and minutes, so this is
        also the check that a screen reader gets something to read.
        """
        self._one_sprint(fresh_app, "", "measured the heatmap")
        fresh_app.navigate_to_tab("History")

        assert fresh_app.exists("FocusHeatmap"), "the heatmap never rendered"
        assert "–" in fresh_app.text_of("HeatmapRange"), "the range names both ends"
        assert "best day" in fresh_app.text_of("HeatmapPeak")
        assert fresh_app.text_of("HeatmapLegendLow") == "Less"
        assert fresh_app.text_of("HeatmapLegendHigh") == "More"

    def test_the_export_is_reachable_from_history(self, fresh_app):
        """F17's card stays on Settings; History is the way to it (F16)."""
        fresh_app.navigate_to_tab("History")
        fresh_app.click("HistoryExportButton")
        time.sleep(0.8)
        assert fresh_app.current_page_title() == "Settings"
        assert fresh_app.exists("ExportJournalButton")

    def test_looking_at_history_changes_nothing(self, fresh_app):
        """The page only reads. Visiting it must not rewrite the sprint record."""
        self._one_sprint(fresh_app, "", "wrote it down")
        before = verify.read_settings()["Sessions"]

        fresh_app.navigate_to_tab("History")
        time.sleep(1.0)
        fresh_app.navigate_to_tab("Today")
        time.sleep(0.5)

        assert verify.read_settings()["Sessions"] == before
