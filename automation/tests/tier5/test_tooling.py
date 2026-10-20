# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: tooling."""

from __future__ import annotations
import re
from pathlib import Path
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from tests._split_support import read_test_package, source_files



# ============================ issue hygiene check (#158)

class TestIssueHygieneStaysAdvisory:
    """
    The check reports; it never edits. A tool that silently relabels or closes
    issues would be trusted for exactly as long as it takes to get one wrong,
    and the thing it is checking is judgement.
    """

    CHECK = Path(__file__).resolve().parents[3] / "tools" / "issue_hygiene" / "check.py"
    WORKFLOW = (Path(__file__).resolve().parents[3] / ".github" /
                "workflows" / "issue-hygiene.yml")

    def test_it_never_edits_an_issue(self):
        source = self.CHECK.read_text(encoding="utf-8")
        calls = re.findall(r'gh\("issue",\s*"(\w+)"', source)
        assert set(calls) <= {"list", "comment"}, (
            f"the check may only read issues and comment; it calls {sorted(set(calls))}"
        )
        for forbidden in ('"edit"', '"close"', '"reopen"', '"delete"'):
            assert f'gh("issue", {forbidden}' not in source

    def test_findings_do_not_fail_the_workflow(self):
        """
        Exit 10 means "found something", and the workflow must not treat it as
        a failure — only exit 2, "could not run", is a real error.
        """
        workflow = self.WORKFLOW.read_text(encoding="utf-8")
        assert 'if [ "$code" = "2" ]' in workflow
        assert "exit 10" not in workflow

    def test_it_runs_weekly_and_on_demand_only(self):
        """Not per merge: issue state drifts over days, not commits, and a
        report on every push is a report nobody reads."""
        workflow = self.WORKFLOW.read_text(encoding="utf-8")
        assert "schedule:" in workflow and "workflow_dispatch:" in workflow
        assert "on:\n  push:" not in workflow

    def test_the_label_set_matches_the_documented_one(self):
        """
        PLANNING.md's table is what people read; KIND_LABELS is what the check
        enforces. They drift apart silently otherwise.
        """
        planning = (Path(__file__).resolve().parents[3] / "PLANNING.md"
                    ).read_text(encoding="utf-8")
        source = self.CHECK.read_text(encoding="utf-8")
        block = source.split("KIND_LABELS = {", 1)[1].split("}", 1)[0]
        for label in re.findall(r'"([a-z-]+)"', block):
            assert f"`{label}`" in planning, (
                f"the check knows the label {label!r}, but PLANNING.md does not list it"
            )


# ================== what the first full UI-suite run taught us (#242-#245)

class TestTheUiSuiteCanObserveWhatItAsserts:
    """
    Four of the first full UI run's failures were the suite measuring itself
    rather than the product (#242, #243, #245). None of them could fail loudly:
    each looked exactly like a product bug. These are the source-level traps,
    so the same classes of mistake cannot come back quietly.
    """

    POLICY = Path(DESKTOP_DIR) / "Models" / "EndSprintPolicy.cs"
    CONTROLLER = Path(DESKTOP_DIR).parent / "automation" / "desktop" / "app_controller.py"
    TIER3 = Path(DESKTOP_DIR).parent / "automation" / "tests" / "tier3"

    def _short_seconds(self, name: str) -> float:
        source = self.POLICY.read_text(encoding="utf-8")
        match = re.search(
            name + r"\s*=>\s*UseShortTimers\s*\?\s*TimeSpan\.FromSeconds\((\d+(?:\.\d+)?)\)"
            r"\s*:\s*TimeSpan\.From(\w+)\((\d+(?:\.\d+)?)\)",
            source,
        )
        assert match, f"{name}'s short/real pair was not found; update this test"
        return float(match.group(1))

    def _real(self, name: str) -> tuple[str, float]:
        source = self.POLICY.read_text(encoding="utf-8")
        match = re.search(
            name + r"\s*=>\s*UseShortTimers\s*\?\s*TimeSpan\.FromSeconds\(\d+(?:\.\d+)?\)"
            r"\s*:\s*TimeSpan\.From(\w+)\((\d+(?:\.\d+)?)\)",
            source,
        )
        assert match, f"{name}'s short/real pair was not found; update this test"
        return match.group(1), float(match.group(2))

    # A UIA element lookup plus an IsEnabled read costs a second or more on
    # Today. #242's log showed End anyway unlocking 2.507 s after the panel
    # opened -- correct against a 2 s delay, and unobservable by the test that
    # was meant to catch it. Anything under this is a window the suite cannot
    # see into, so a test asserting on it is really asserting on its own speed.
    OBSERVABLE_SECONDS = 5.0

    @pytest.mark.parametrize("phantom_question", [False, True])
    def test_break_check_rejects_a_question_before_the_decoy_exists(
        self, monkeypatch, tmp_path, phantom_question,
    ):
        """#249: exercise the real UI test against a five-second sprint bench.

        A ten-second close grace cannot finish inside that sprint. The test
        must observe enforcement's warning, and must not silently answer an
        unexpected question on the first start. Only the UI/OS boundary is fake.
        """
        from types import SimpleNamespace
        from tests.tier3 import test_breaks_schedule as tier3

        clock = [0.0]
        monkeypatch.setattr(tier3, "time", SimpleNamespace(
            time=lambda: clock[0],
            sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
        ))
        state = {"next_started": None, "warned": False, "dead": False,
                 "question": phantom_question}
        decoy = SimpleNamespace(
            poll=lambda: 0 if state["dead"] else None,
            kill=lambda: state.update(dead=True),
        )

        def click(auto_id):
            if auto_id == "StartNextSprintButton":
                state["next_started"] = clock[0]
                state["question"] = True

        def answer_open_apps_question():
            asked = state["question"]
            state["question"] = False
            return asked

        def start_sprint(confirm_open_apps=True):
            if confirm_open_apps:
                answer_open_apps_question()

        def text_of(auto_id, **kwargs):
            if auto_id == "BreakPanelTitle":
                return "On a break"
            if auto_id == "ToastText" and clock[0] - state["next_started"] < 5:
                state["warned"] = True
                return "Blocked at shield Firm; closing in 10 s"
            return ""

        app = SimpleNamespace(
            navigate_to_tab=lambda tab: None,
            add_blocked_app=lambda name: True,
            select_shield=lambda shield: None,
            select_sprint_length=lambda minutes: None,
            start_sprint=start_sprint,
            exists=lambda auto_id, **kwargs: auto_id == "StartBreakButton",
            click=click,
            text_of=text_of,
            answer_open_apps_question=answer_open_apps_question,
        )
        test = tier3.TestBreaksAndCycles()
        monkeypatch.setattr(test, "_decoy", lambda path: decoy)
        if phantom_question:
            with pytest.raises(AssertionError, match="before.*decoy"):
                test.test_nothing_is_blocked_during_the_break(app, tmp_path)
        else:
            test.test_nothing_is_blocked_during_the_break(app, tmp_path)
            assert state["warned"], "check enforcement before the short sprint ends"

    @pytest.mark.parametrize("focus_result", ["accepted", "refused", "error", "attach_error"])
    def test_soft_refocus_handles_foreground_lock_and_always_detaches(
        self, monkeypatch, focus_result,
    ):
        """#250: a successful API call is not proof of OS foreground ownership.

        Model Windows refusing an unattached background caller, then exercise
        the actual Soft-test helper. No real input queues or windows are used.
        """
        from types import SimpleNamespace
        import pywintypes
        import win32api
        import win32gui
        import win32process
        from tests.tier3 import test_soft_shield as tier3

        clock = [0.0]
        monkeypatch.setattr(tier3, "time", SimpleNamespace(
            time=lambda: clock[0], monotonic=lambda: clock[0],
            sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
        ))
        foreground = [100]
        attached = set()
        thread_for = {100: 11, 200: 22}
        monkeypatch.setattr(win32api, "GetCurrentThreadId", lambda: 33)
        monkeypatch.setattr(win32gui, "PeekMessage", lambda *args: None)
        monkeypatch.setattr(win32gui, "GetForegroundWindow", lambda: foreground[0])
        monkeypatch.setattr(win32gui, "IsIconic", lambda hwnd: False)
        monkeypatch.setattr(win32process, "GetWindowThreadProcessId",
                            lambda hwnd: (thread_for[hwnd], hwnd))

        def attach(caller, other, enabled):
            if enabled:
                if focus_result == "attach_error" and other == 22:
                    raise pywintypes.error(5, "AttachThreadInput", "refused by bench")
                attached.add((caller, other))
            else:
                attached.remove((caller, other))

        def request_focus(hwnd):
            if focus_result == "error":
                raise pywintypes.error(5, "SetForegroundWindow", "refused by bench")
            if focus_result == "accepted" and attached == {(33, 11), (33, 22)}:
                foreground[0] = hwnd

        monkeypatch.setattr(win32process, "AttachThreadInput", attach)
        monkeypatch.setattr(win32gui, "SetForegroundWindow", request_focus)
        test = tier3.TestSoftShowsTheNotice()
        monkeypatch.setattr(test, "_foreground_pid", lambda: foreground[0])
        monkeypatch.setattr(test, "_decoy_windows", lambda process: [SimpleNamespace(
            handle=200, set_focus=lambda: request_focus(200),
        )])
        if focus_result == "accepted":
            test._bring_forward(SimpleNamespace(pid=200))
            assert foreground[0] == 200
        else:
            with pytest.raises(pytest.fail.Exception, match="foreground"):
                test._bring_forward(SimpleNamespace(pid=200))
            assert foreground[0] == 100
        assert not attached, "input queues must be detached on success and failure"

    def test_every_shortened_wait_is_long_enough_to_observe(self):
        for name in ("GracePeriod", "FirmConfirmDelay", "SealedCountdown"):
            seconds = self._short_seconds(name)
            assert seconds >= self.OBSERVABLE_SECONDS, (
                f"{name} is {seconds}s under --short-timers, shorter than a UIA "
                f"round trip; a test asserting the gate would fail on the app's "
                f"correct behaviour, as #242 did"
            )

    def test_shortening_never_touches_what_a_customer_gets(self):
        assert self._real("GracePeriod") == ("Minutes", 2.0)
        assert self._real("FirmConfirmDelay") == ("Seconds", 5.0)
        assert self._real("SealedCountdown") == ("Seconds", 30.0)

    def test_the_soft_allow_wait_is_observed_with_real_timers(self):
        """
        The Soft notice's Allow wait is three seconds under --short-timers
        (SoftOverlayPolicy.AllowWait; the 1.0.10 spec fixes it there), which
        is under OBSERVABLE_SECONDS: a tier 3 test asserting "Allow is still
        disabled" against it would be asserting on its own speed, #242's trap
        again. So the tier 3 test that observes the wait launches the app
        without --short-timers and watches the real five-second first try.
        """
        policy = (Path(DESKTOP_DIR) / "Models" / "SoftOverlayPolicy.cs").read_text(encoding="utf-8")
        match = re.search(r"if \(UseShortTimers\) return TimeSpan\.FromSeconds\((\d+(?:\.\d+)?)\);", policy)
        assert match, "SoftOverlayPolicy.AllowWait's --short-timers value was not found"
        shortened = float(match.group(1))

        tier3 = read_test_package(self.TIER3)
        head = re.search(r"def test_allow_is_disabled_until_the_wait_runs_out\(self, (\w+)\)", tier3)
        assert head, "the tier 3 test that observes Allow's wait was not found"
        if shortened < self.OBSERVABLE_SECONDS:
            assert head.group(1) == "real_wait_app", (
                f"Allow's wait is {shortened:g}s under --short-timers, shorter than a UIA "
                f"round trip; the test must run on the real_wait_app fixture"
            )
        fixture = tier3.split("def real_wait_app(", 1)
        assert len(fixture) == 2, "the real_wait_app fixture was not found in tier 3"
        assert "short_timers=False" in fixture[1].split("yield", 1)[0], (
            "real_wait_app must launch without --short-timers"
        )

    def test_the_driver_agrees_with_the_shortened_grace_period(self):
        """
        #222 widened the grace period and left SHORT_GRACE_SECONDS at the old
        value with a comment naming timers that no longer existed. A stale
        mirror of a constant is worse than no mirror.
        """
        source = self.CONTROLLER.read_text(encoding="utf-8")
        match = re.search(r"SHORT_GRACE_SECONDS\s*=\s*(\d+(?:\.\d+)?)", source)
        assert match, "SHORT_GRACE_SECONDS was not found in the controller"
        assert float(match.group(1)) == self._short_seconds("GracePeriod"), (
            "the driver's idea of the shortened grace period must match "
            "EndSprintPolicy.cs"
        )

    def test_waiting_out_the_grace_period_outlasts_it(self):
        """
        wait_out_grace_period polls for the button to stop offering a free
        cancel, and 24 call sites trust it. Its own deadline therefore has to
        outlast the thing it is waiting for: at 15 s it was exactly the grace
        period, so a call made near the start of a sprint could time out before
        the flip and return as if the grace were over -- silently, because
        returning on the deadline is legitimate for callers that only want to
        be past it.
        """
        from desktop.app_controller import DesktopController

        grace = self._short_seconds("GracePeriod")
        assert DesktopController.SHORT_GRACE_SECONDS == grace
        assert DesktopController.GRACE_WAIT_TIMEOUT > grace, (
            f"wait_out_grace_period's default ({DesktopController.GRACE_WAIT_TIMEOUT}s) "
            f"must outlast the {grace}s grace period it waits for"
        )
        assert DesktopController.GRACE_WAIT_MARGIN_SECONDS >= 5.0, (
            "the margin must cover a label read landing just before the "
            "boundary plus the poll interval"
        )

        # And the default must stay derived, not written out beside the grace:
        # two literals is how they came to be equal in the first place.
        source = self.CONTROLLER.read_text(encoding="utf-8")
        assert "GRACE_WAIT_TIMEOUT = SHORT_GRACE_SECONDS + GRACE_WAIT_MARGIN_SECONDS" in source, (
            "derive the timeout from SHORT_GRACE_SECONDS rather than repeating a number"
        )
        assert not re.search(r"def wait_out_grace_period\(self, timeout: float = \d", source), (
            "a literal default here cannot follow the grace period when it changes"
        )

    def test_no_ui_test_sends_a_bare_space_to_type_keys(self):
        """
        pywinauto drops " " from type_keys unless with_spaces=True, so
        `type_keys(" ")` sends nothing at all -- which is why F4's Space
        shortcut tests failed against a shortcut that works (#245). {SPACE}
        is unambiguous and needs no flag.
        """
        # A real call, so the sentence above describing the trap is not itself
        # an offender.
        pattern = re.compile(r"\.type_keys\(\s*(['\"])( +)\1\s*\)")
        for path in (*source_files(self.TIER3), self.CONTROLLER):
            text = path.read_text(encoding="utf-8")
            assert not pattern.search(text), (
                f"{path.name}: type_keys with a bare space sends no key; use "
                '"{SPACE}" or pass with_spaces=True'
            )

    def test_no_test_asserts_on_whitespace_text_of_strips(self):
        """
        text_of() strips both ends, so an assertion about a leading or trailing
        space can never pass however the app behaves -- #245's second test
        asserted exactly that and read as a product bug for a night.
        """
        text = read_test_package(self.TIER3)
        offenders = re.findall(
            r"text_of\([^)]*\)\.(?:startswith|endswith)\(\s*(['\"]) +\1", text)
        assert not offenders, (
            "text_of() strips whitespace; assert on an interior space instead"
        )

    def test_the_trial_that_expires_mid_sprint_gets_a_usable_runway(self):
        """
        #243: --expire-trial-in=8 ran out before the driver had finished
        connecting, so the app correctly refused the Pro-gated custom sprint
        length and F20's scenario never started a sprint at all.
        """
        conftest = (Path(DESKTOP_DIR).parent / "automation" / "tests" / "conftest.py").read_text(
            encoding="utf-8")
        block = conftest.split("def trial_expiring_soon_app(", 1)
        assert len(block) == 2, "the trial_expiring_soon_app fixture was not found"
        match = re.search(r"runway\s*=\s*(\d+)", block[1])
        assert match, "the fixture should name its runway in one place"
        assert int(match.group(1)) >= 60, (
            "a trial shorter than the driver's own setup expires before the test "
            "can pick a Pro-gated sprint length"
        )
        assert "trial_ends_at" in block[1], (
            "the fixture must publish when the trial ends so the test can wait "
            "for the real boundary rather than sleeping a guess"
        )
