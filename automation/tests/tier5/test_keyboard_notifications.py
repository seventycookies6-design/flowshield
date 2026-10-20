# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: keyboard notifications."""

from __future__ import annotations
import re
from pathlib import Path
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR



# ============ Basalt never nagged, and never told you anything either (F19, #95)

class TestNotificationsStayQuiet:
    """
    The only notification used to be "still guarding" on minimise. Adding them
    risks the opposite problem, so the quiet rules are pinned here.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_nothing_about_buying_reaches_a_running_sprint(self):
        main = self.read("ViewModels", "MainViewModel.cs")
        notify = main.split("public bool Notify(")[1].split("\n    }")[0]
        # IsFocusInProgress is a running sprint plus the break that follows one
        # (F5); before breaks existed this passed IsSprintRunning.
        assert "NotificationPolicy.ShouldShow(kind, Settings, IsFocusInProgress)" in notify, \
            "every notification must go through the policy, with the sprint state"

    def test_the_trial_notice_happens_once_a_day_at_most(self):
        main = self.read("ViewModels", "MainViewModel.cs")
        trial = main.split("public void MaybeNotifyTrialEnding()")[1].split("\n    }")[0]
        assert "TrialEndingNotifiedLocal?.Date == today" in trial
        assert trial.index("if (!Notify(") < trial.index("TrialEndingNotifiedLocal = today"), \
            "a notice suppressed during a sprint must still be shown afterwards"

    def test_five_minutes_left_fires_once_per_sprint(self):
        today = self.read("ViewModels", "TodayViewModel.cs")
        assert "_endingSoonNotified = false;" in today.split("private void BeginRunning(")[1], \
            "the flag must reset when a sprint starts, or only the first sprint ever notifies"
        tick = today.split("private void OnTick()")[1].split("\n    }")[0]
        assert "!_endingSoonNotified" in tick and "_endingSoonNotified = true;" in tick

    def test_the_countdown_icon_frees_its_handle(self):
        window = self.read("MainWindow.xaml.cs")
        countdown = window.split("private static System.Drawing.Icon? CountdownIcon(")[1].split("\n    }")[0]
        assert "DestroyIcon(handle)" in countdown, \
            "GetHicon leaks a GDI handle every minute of every sprint without this"

    def test_the_tray_icon_and_title_follow_the_countdown(self):
        window = self.read("MainWindow.xaml.cs")
        changed = window.split("private void OnTodayChanged(")[1].split("\n    }")[0]
        assert "nameof(TodayViewModel.Remaining)" in changed
        update = window.split("private void UpdateTrayIcon()")[1].split("\n    }")[0]
        assert "NotificationPolicy.TrayIconText(remaining)" in update
        # F5 put a break ahead of the sprint countdown in the same expression:
        # "Break · 4:59" while one runs, the sprint's time left otherwise.
        assert 'running ? $"Basalt — {Vm?.Today.RemainingText}"' in update
        assert ': "Basalt";' in update
        assert 'onBreak ? $"Basalt — {NotificationPolicy.BreakLabel(remaining)}"' in update

    def test_the_tray_search_only_trusts_explorer(self):
        # A Claude desktop session titled "Basalt …" was double-clicked as
        # if it were the tray icon; any app can show a button with that name.
        controller = (Path(DESKTOP_DIR).parent / "automation" / "desktop" / "app_controller.py").read_text(
            encoding="utf-8")
        find = controller.split("def find_tray_icon(")[1].split("\n    def ")[0]
        assert "element.process_id in explorer" in find

    def test_the_test_driver_matches_the_countdown_title(self):
        controller = (Path(DESKTOP_DIR).parent / "automation" / "desktop" / "app_controller.py").read_text(
            encoding="utf-8")
        assert "WINDOW_TITLE_RE" in controller and "title_re=WINDOW_TITLE_RE" in controller


# ============ a new user's first sprint blocked nothing (F18, #68)

class TestFirstRunNeverNags:
    """
    New installs opened on an empty Today page, so the first sprint blocked
    nothing. The welcome that fixes it must never reach existing users.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_existing_users_are_marked_done_instead_of_shown(self):
        vm = self.read("ViewModels", "FirstRunViewModel.cs")
        show_if_new = vm.split("public void ShowIfNew()")[1].split("\n    }")[0]
        assert show_if_new.index("IsExistingUser(s)") < show_if_new.index("ShouldShow(")
        assert "s.FirstRunCompleted = true;" in show_if_new

    def test_seen_counts_as_done(self):
        show = self.read("ViewModels", "FirstRunViewModel.cs").split("public void Show()")[1].split("IsVisible = true;")[0]
        assert "_main.Settings.FirstRunCompleted = true;" in show and "_main.SaveSettings();" in show

    def test_decided_after_the_trial_flags(self):
        app = self.read("App.xaml.cs")
        assert app.index("--expire-trial") < app.index("ViewModel.FirstRun.ShowIfNew()"), \
            "a trial expired by the flag would get the welcome over its lock screen"

    def test_the_ui_suite_skips_it_unless_asked(self):
        controller = (Path(DESKTOP_DIR).parent / "automation" / "desktop" / "app_controller.py").read_text(encoding="utf-8")
        assert 'args.append("--skip-first-run")' in controller


# ==================================== tray and keyboard reuse the F2 flow (F4)

class TestTrayAndKeyboardNeverBypassTheEndFlow:
    """
    F4 added a second and third way to end a sprint — the tray menu and the
    Space key — on top of the StopSprintButton. All three must resolve to the
    exact same RequestEnd() policy: a shortcut that ended a Firm or Sealed
    sprint immediately would silently undo F2's escape-hatch rules (#47).
    """

    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    MAIN_XAML = Path(DESKTOP_DIR) / "MainWindow.xaml"
    TODAY_XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"

    def test_tray_end_sprint_and_space_drive_the_same_stopcommand_as_the_button(self):
        today_xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        assert 'Command="{Binding StopCommand}"' in today_xaml, \
            "StopSprintButton must still bind StopCommand — this test assumes that binding"

        window = self.WINDOW.read_text(encoding="utf-8")
        assert "vm.Today.StopCommand.Execute(null)" in window, \
            "the tray's End sprint must invoke StopCommand, the same RelayCommand as the button"

        today_vm = self.TODAY_VM.read_text(encoding="utf-8")
        # Space's command wraps TogglePrimary, which itself calls RequestEnd()
        # while running — not a separate, weaker end path.
        assert "ToggleOrEndCommand = new RelayCommand(TogglePrimary" in today_vm
        assert "StopCommand = new RelayCommand(() => RequestEnd()" in today_vm

    def test_no_new_entry_point_calls_endsprint_or_cancelsprint_directly(self):
        """
        RequestEnd() is the only door into EndSprint/CancelSprint — MainWindow
        and the Space/tray wiring must go through it, mirroring the existing
        rule for the old tray Quit and window-close paths (see
        TestNoOneClickEscape.test_tray_quit_and_window_close_use_the_end_flow).
        """
        window = self.WINDOW.read_text(encoding="utf-8")
        for method_name in ("BuildTrayMenu", "EndSprintFromTray", "WndProc"):
            body = window.split(f"private void {method_name}(", 1)
            if len(body) == 1:
                body = window.split(f"private IntPtr {method_name}(", 1)
            block = body[1].split("\n    }")[0]
            assert "EndSprint(" not in block, f"{method_name} must not end a sprint directly"
            assert "CancelSprint(" not in block, f"{method_name} must not cancel a sprint directly"

    def test_the_global_hotkey_only_ever_starts_not_ends(self):
        """The hotkey's one job is F4's 'start the last sprint' — it must never reach End."""
        window = self.WINDOW.read_text(encoding="utf-8")
        wnd_proc = window.split("private IntPtr WndProc(")[1].split("\n    }")[0]
        # Since #270 the hotkey goes through QuickStart(), which only starts.
        quick_start = window.split("private void QuickStart()")[1].split("\n    }")[0]
        assert "QuickStart()" in wnd_proc
        assert "StartCommand.Execute(null)" in quick_start
        for path in (wnd_proc, quick_start):
            assert "StopCommand" not in path
            assert "RequestEnd" not in path

    def test_page_ctrl_shortcuts_and_shield_shift_shortcuts_stay_disjoint(self):
        """
        Issue #37's settlement: Ctrl+1..5 is reserved for pages, Shift+1/2/3
        for shields. Sharing a digit (Ctrl+1 vs Shift+1) is fine — they are
        different combinations — but the same (modifier, key) pair must never
        be bound twice, and nothing may claim Ctrl+1..5 for a shield.
        """
        xaml = self.MAIN_XAML.read_text(encoding="utf-8")
        bindings = re.findall(r'<KeyBinding\s+(?:Modifiers="(\w+)"\s+)?Key="(\w+)"', xaml)
        combos = [(mods or "", key) for mods, key in bindings]
        assert len(combos) == len(set(combos)), f"duplicate KeyBinding combination(s) in {combos}"

        shield_lines = [line for line in xaml.splitlines() if "SelectShield" in line]
        assert shield_lines and all('Modifiers="Shift"' in line for line in shield_lines), \
            "every shield shortcut must use Shift, keeping Ctrl+1..5 free for page navigation"

    def test_ctrl_number_shortcuts_match_the_nav_rails_tab_order(self):
        """
        F16 added History as the rail's second tab (Today, History, Blocked
        Apps, Sleep Blocking, Settings), which used the fifth Ctrl+N slot F4
        left free. Ctrl+N must walk the tabs in the order they are drawn, or
        the shortcut a user memorises from looking at the rail stops matching
        what pressing it actually does.
        """
        xaml = self.MAIN_XAML.read_text(encoding="utf-8")
        tabs = xaml.split('<StackPanel x:Name="NavTabs"', 1)[1].split("<Grid/>", 1)[0]
        rail_order = re.findall(r'CommandParameter="(\w+)"', tabs)
        assert rail_order == ["Today", "History", "BlockedApps", "SleepBlocking", "Settings"], \
            f"the rail's own tab order is {rail_order}; update the expectation or the rail"

        ctrl_bindings = re.findall(
            r'<KeyBinding Modifiers="Ctrl" Key="D(\d)" Command="\{Binding NavigateCommand\}" '
            r'CommandParameter="(\w+)"/>', xaml)
        ctrl_order = [page for _, page in sorted(ctrl_bindings, key=lambda pair: int(pair[0]))]
        assert ctrl_order == rail_order, (
            f"Ctrl+1..{len(ctrl_order)} goes to {ctrl_order}, which does not match the rail's "
            f"own order {rail_order}"
        )


# ============================ Space cannot reach through the first-run wizard

class TestSpaceRefusedUnderFirstRun:
    """
    PR #214 review: the first-run wizard (F18) covers Today the same way the
    terms gate does, but nothing stopped Space — or a StartSprint() call from
    the tray or automation — from starting a sprint underneath it. The gate
    belongs in the view model, not only in the wizard's covering panel
    (CLAUDE.md's "a gate must refuse in the view model, not only by covering
    the screen").
    """

    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"

    def source(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8")

    def test_the_space_shortcut_checks_first_run_is_not_showing(self):
        source = self.source()
        guard = source.split("private bool CanUseSpaceShortcut()")[1].split("\n\n")[0]
        assert "_main.FirstRun.IsVisible" in guard, \
            "Space must refuse while the first-run wizard is up, the same as the terms gate"

    def test_shift_shield_shortcuts_check_first_run_is_not_showing(self):
        source = self.source()
        guard = source.split("private bool CanChangeShield()")[1].split("\n\n")[0]
        assert "_main.FirstRun.IsVisible" in guard

    def test_startsprint_itself_refuses_under_the_wizard(self):
        """
        The view-model gate, not only the guard on the keyboard command:
        StartSprint() is also what the tray's "Start sprint (last settings)"
        and the global hotkey call directly, and neither goes through
        CanUseSpaceShortcut.
        """
        source = self.source()
        start = source.split("private void StartSprint()")[1].split("\n    private ")[0]
        assert "_main.FirstRun.IsVisible" in start, \
            "StartSprint must refuse while the first-run wizard hasn't finished, like the terms gate above it"
        # Must be checked, not just referenced in a comment.
        gate = re.search(r'if\s*\(\s*_main\.FirstRun\.IsVisible\s*\)', start)
        assert gate, "expected an explicit `if (_main.FirstRun.IsVisible)` guard in StartSprint"


# ==================================== the global hotkey hook never stacks up

class TestGlobalHotkeyHookIsNeverStacked:
    """
    PR #214 review: SetUpGlobalHotkey() re-runs every time the Settings toggle
    changes, and used to call HwndSource.AddHook without ever removing the
    previous one — so toggling the setting off and on stacked a WndProc hook
    per toggle, each one calling StartCommand again on the same key press.
    """

    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"

    def source(self) -> str:
        return self.WINDOW.read_text(encoding="utf-8")

    def test_a_single_hook_field_is_tracked(self):
        source = self.source()
        assert re.search(r'private\s+HwndSource\?\s+_hotkeySource;', source), \
            "expected a tracked HwndSource field so the hook can be removed later"

    def test_setup_removes_the_previous_hook_before_adding_a_new_one(self):
        source = self.source()
        setup = source.split("private void SetUpGlobalHotkey()")[1].split("\n    private ")[0]
        remove_index = setup.find("_hotkeySource.RemoveHook(WndProc)")
        add_index = setup.find(".AddHook(WndProc)")
        assert remove_index != -1, "SetUpGlobalHotkey must remove any hook it previously added"
        assert add_index != -1, "SetUpGlobalHotkey must (re)add the hook when the hotkey is enabled"
        assert remove_index < add_index, \
            "the old hook must be removed before a new one is added, or hooks stack on every toggle"
        # And the removal must not be conditional on _hotkeyRegistered alone —
        # it needs its own null check so a re-run after a failed RegisterHotKey
        # still tears down a hook left over from a previous success.
        assert "if (_hotkeySource is not null)" in setup

    def test_closing_removes_the_hook_alongside_unregistering(self):
        source = self.source()
        closing = source.split("protected override void OnClosing")[1]
        unregister_index = closing.find("UnregisterHotKey(")
        remove_hook_index = closing.find("_hotkeySource.RemoveHook(WndProc)")
        assert unregister_index != -1
        assert remove_hook_index != -1, "OnClosing must remove the WndProc hook, not just unregister the hotkey"
