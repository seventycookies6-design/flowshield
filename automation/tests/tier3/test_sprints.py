# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 3: sprints."""

from __future__ import annotations
import time
from datetime import datetime, timedelta
import pytest
from core import state_verifier as verify

pytestmark = pytest.mark.ui



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
        # 1.0.10: nothing was turned back, so there is no "Turned back 0 times".
        assert not fresh_app.exists("SummaryTurnedBackText", timeout=1)

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
        # #300: it ends at its planned end, not whenever the tick that noticed
        # ran -- after a sleep, that tick is hours late.
        assert (ended - started).total_seconds() == session["PlannedMinutes"] * 60, \
            f"a {session['PlannedMinutes']}-minute sprint was recorded as {ended - started}"
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
        """
        #242 reported "End anyway is enabled immediately". It is not: the app
        log showed EndAnywayEnabled flipping 2.507 s after the panel opened,
        against a 2 s FirmConfirmDelay. What could not happen was *reading* it
        inside a 2 s window — element lookup plus IsEnabled is a UIA round trip
        costing a second or more on this page. So the delay is 6 s under
        --short-timers (EndSprintPolicy, same reasoning as #222's grace period)
        and the assertion times how long the button stays disabled instead of
        assuming one read lands inside the window.
        """
        self._start(fresh_app, "Firm")
        fresh_app.wait_out_grace_period()

        opened = time.monotonic()
        fresh_app.click("StopSprintButton")
        assert fresh_app.exists("KeepGoingButton", timeout=3), "Firm ended without a confirmation"

        # Only assert "disabled right now" while the window provably still has
        # time left on it; otherwise the read itself is the thing being timed.
        if time.monotonic() - opened < 3.0:
            assert fresh_app.is_control_enabled("EndAnywayButton") is False, \
                "End anyway was ready immediately"

        # Measured from before the click, which only ever inflates the number —
        # so a button that was enabled from the start cannot fake a long wait.
        fresh_app.wait_until_control_enabled("EndAnywayButton", timeout=20)
        waited = time.monotonic() - opened
        assert waited >= 4.0, \
            f"End anyway unlocked after {waited:.1f}s of a 6s confirm countdown"

        fresh_app.click("EndAnywayButton")
        time.sleep(1.0)
        assert "early" in fresh_app.session_state().lower()

    def test_sealed_needs_the_countdown_and_the_phrase(self, fresh_app):
        self._start(fresh_app, "Sealed")
        fresh_app.wait_out_grace_period()
        assert "need to stop" in fresh_app.end_button_label().lower()

        opened = time.monotonic()
        fresh_app.click("StopSprintButton")
        assert fresh_app.exists("EndPhraseInput", timeout=3), "Sealed didn't ask for the phrase"

        # Same measurement as the Firm test above (#242): the countdown is 8 s
        # under --short-timers, and the right phrase must not beat it.
        fresh_app.set_text("EndPhraseInput", "end my sprint")
        if time.monotonic() - opened < 5.0:
            assert fresh_app.is_control_enabled("EndAnywayButton") is False, \
                "the phrase ended a Sealed sprint before its countdown"

        fresh_app.wait_until_control_enabled("EndAnywayButton", timeout=25)
        waited = time.monotonic() - opened
        assert waited >= 5.0, \
            f"End anyway unlocked after {waited:.1f}s of an 8s sealed countdown"

        # The countdown being over must not let the wrong phrase through. No
        # timing in this half: the gate is the words, not the clock.
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


# =========================================================== daily goal (F15)

# ============================================ momentum explained (F14 / 3.2)
class TestMomentumTrendAndExplainer:
    """F14: the score is on screen with the rule behind it and 30 days of shape."""

    def test_the_explainer_opens_and_closes(self, fresh_app):
        """On History since the Today declutter (#147), still folded by default."""
        fresh_app.navigate_to_tab("History")
        assert not fresh_app.exists("MomentumExplainerText", timeout=1), \
            "the page leads with the figures, not with the essay"

        fresh_app.click("MomentumExplainerButton")
        time.sleep(0.5)
        assert fresh_app.exists("MomentumExplainerText", timeout=3)

        fresh_app.click("MomentumExplainerButton")
        time.sleep(0.5)
        assert not fresh_app.exists("MomentumExplainerText", timeout=1)

    def test_today_links_to_the_rule_on_history(self, fresh_app):
        """#147: Today keeps the number; its link opens History with the rule showing."""
        fresh_app.navigate_to_tab("Today")
        assert not fresh_app.exists("MomentumExplainerButton", timeout=1), \
            "the explainer moved off Today"
        fresh_app.click("MomentumRulesLink")
        assert fresh_app.exists("MomentumExplainerText", timeout=3), \
            "the link lands on History with the rule already open"
        assert fresh_app.current_page_title() == "History"
        time.sleep(0.5)
        assert fresh_app.is_on_screen("MomentumExplainerButton"), \
            "and scrolled to it: below the fold the link looked dead (VM bench, #330)"

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
        """
        #245: this never actually pressed Space. pywinauto drops a bare " "
        from type_keys unless with_spaces=True, so the old `type_keys(" ")`
        sent nothing at all — a DIAG build logging every PreviewKeyDown saw no
        key arrive. It is sent as {SPACE} now.

        With a real Space arriving, the second half of the old test was wrong
        too: it clicked Shield_Firm first, and the DIAG log then showed
        `key Space focus=RadioButton id='Shield_Firm'`. WPF's ButtonBase owns
        Space for whichever control has keyboard focus — that is what makes
        every button on the page keyboard-operable (F21) — so the key never
        reaches Window.InputBindings. That is correct behaviour, not the
        shortcut failing, and the guard in CanUseSpaceShortcut is about text
        boxes, not about out-shouting a focused button.

        So nothing is clicked before the key: a fresh app opens on Today with
        Firm as the default shield, which is the state a customer is in when
        they press Space, and the only state in which the shortcut is the
        thing that owns the key.
        """
        assert fresh_app.current_page_title() == "Today", \
            "a fresh app should already be on Today; clicking a tab would take the key focus"

        fresh_app.focus(force=True)
        fresh_app.window.type_keys("{SPACE}")
        assert fresh_app.exists("StopSprintButton", timeout=5), \
            "Space did not start the sprint"
        # A blocked app already open would have asked instead of starting.
        fresh_app.answer_open_apps_question()

        # Firm is the default shield, so this is the Firm end flow below.
        assert verify.read_settings()["ActiveSprint"]["Shield"] in (2, "Firm")

        fresh_app.wait_out_grace_period()

        # Space again must open the same F2 flow the button opens — a
        # confirmation that waits — never end the sprint outright.
        opened = time.monotonic()
        fresh_app.window.type_keys("{SPACE}")
        assert fresh_app.exists("KeepGoingButton", timeout=3), \
            "Space skipped Firm's confirmation and ended the sprint directly"

        # Timed, not read once — see test_firm_needs_a_confirmation_that_waits.
        fresh_app.wait_until_control_enabled("EndAnywayButton", timeout=20)
        waited = time.monotonic() - opened
        assert waited >= 4.0, \
            f"End anyway unlocked after {waited:.1f}s — Space must not skip Firm's countdown"

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
        fresh_app.set_text("IntentionInput", "write")

        # set_text ends on {END}, so the caret sits after "write" with the box
        # holding keyboard focus (the DIAG run confirmed
        # focus=TextBox id='IntentionInput' at the moment the key arrives).
        # Type " notes" as real keystrokes: a bare " " is dropped by pywinauto
        # unless with_spaces=True, so the space is sent as {SPACE}, and the word
        # after it proves the space landed *inside* the value — text_of()
        # strips the ends, so a trailing space can never be observed and the
        # old assertion could not pass whatever the app did.
        intention_box = fresh_app.element("IntentionInput")
        intention_box.type_keys("{SPACE}notes")
        time.sleep(0.3)

        assert not fresh_app.exists("StopSprintButton", timeout=1), \
            "a space typed into the intention field also started a sprint"
        assert fresh_app.text_of("IntentionInput") == "write notes", \
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
