# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: theme probe."""

from __future__ import annotations
import re
from pathlib import Path
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from ._helpers import THEME_PROBE



class TestBreakCopyTracksScheduledSleepWindow:
    """#272: during an F5 break in scheduled sleep hours, the sprint shield is
    down but the nightly shield still closes blocked apps; Today must say so."""

    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    BREAK_COPY = Path(DESKTOP_DIR) / "Models" / "BreakCopy.cs"

    def vm(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8")

    def copy(self) -> str:
        """Since #301 the break's wording lives in one model, as ShieldCopy's does."""
        assert self.BREAK_COPY.exists(), "#301: the break's wording lives in Models/BreakCopy.cs"
        return self.BREAK_COPY.read_text(encoding="utf-8")

    def panel_text_getter(self) -> str:
        getter = re.search(
            r"public\s+string\s+BreakPanelText\s*=>\s*(.*?);",
            self.vm(),
            re.DOTALL,
        )
        assert getter, "could not find the BreakPanelText getter in TodayViewModel.cs"
        return " ".join(getter.group(1).split())

    def test_break_text_distinguishes_the_nightly_shield_from_an_open_break(self):
        # #301 moved the ternary #272 added into BreakCopy.PanelText; the view
        # model passes it the same sleep-window check.
        expression = self.panel_text_getter()
        assert "BreakCopy.PanelText(AppBlockerService.IsWithinSleepWindow(S)," in expression, (
            "#272: BreakPanelText must check the scheduled sleep window because "
            "blocked apps are still closed during a break then"
        )
        running = " ".join(self.copy().split("if (onBreak)")[1].split(";")[0].split())
        assert re.search(
            r"inSleepWindow\s*\?\s*"
            r"\$?\"[^\"]*sleep[^\"]*\"\s*:\s*"
            r"\"The shield is down\. Blocked apps are allowed until the break ends\.\"",
            running,
            re.IGNORECASE,
        ), (
            "#272: the sleep-window branch must say the nightly shield is still "
            "up and blocked apps will be closed; only its outside branch may say "
            "they are allowed until the break ends"
        )

    def test_each_break_tick_raises_the_sleep_aware_text(self):
        source = self.vm()
        tick = source.split("private void OnBreakTick()")[1].split("\n    }")[0]
        assert "Raise(nameof(BreakPanelText))" in tick, (
            "#272: a break that crosses into scheduled sleep hours must refresh "
            "BreakPanelText on that tick"
        )

    # ------------------------------------------------------------------ #301
    # #272 fixed the running break's line only. Inside the window the offer
    # before a break, the caption under the ring and Settings' description of
    # breaks still promised the shield was down.

    def test_the_offer_says_the_sleep_shield_is_still_up(self):
        """
        Replaces a test that only checked the IsOnBreak setter raised
        BreakPanelText, which it did before #272 too. This one fails whenever
        either offer, short or long, loses its sleep-window line.
        """
        assert "BreakCopy.PanelText(AppBlockerService.IsWithinSleepWindow(S)," in self.panel_text_getter()
        panel = self.copy().split("public static string PanelText(")[1].split("\n    }")[0]
        offer = " ".join(panel.split("if (onBreak)")[1].split(";", 1)[1].split())
        sleep_lines = re.findall(
            r"inSleepWindow\s*\?\s*\$\"[^\"]*nightly sleep shield stays up until "
            r"\{sleepEndsText\}, so blocked apps are still closed\.\"",
            offer,
        )
        assert len(sleep_lines) == 2, (
            "#301: the short and the long break offer must each say the nightly "
            f"sleep shield stays up inside the window; found {len(sleep_lines)}"
        )

    def test_the_ring_caption_follows_the_sleep_window_on_every_break_tick(self):
        tick = self.vm().split("private void OnBreakTick()")[1].split("\n    }")[0]
        assert re.search(
            r"SessionStateText\s*=\s*BreakCopy\.Caption\(\s*"
            r"AppBlockerService\.IsWithinSleepWindow\(S\)\s*,\s*_breakResumed\s*\)",
            tick,
        ), (
            "#301: the caption under the ring must be recomputed on every break "
            "tick, because the window can open or close mid-break"
        )
        caption = self.copy().split("public static string Caption(")[1]
        # #304: the resumed one is parallel again, on two lines.
        for line in ('"Break — sleep shield still up"',
                     '"Break resumed —\\nsleep shield still up"'):
            assert line in caption, f"#301: the caption needs {line} for the sleep window"

    def test_every_ring_caption_fits_inside_the_ring(self, theme_probe):
        """
        #301 and #304. The caption under the ring sat in a horizontal
        StackPanel, which measures it at unlimited width, so it never wrapped.
        A line wider than the ring at that height painted across the stroke,
        and one wider than the whole ring was clipped at both ends: #301's
        first wording showed as "eak resumed — the sleep shield is still u",
        and "Sprint finished while Basalt was closed" (247.6 px) and
        "Break resumed — the shield is down" (206.5 px) still overran the
        ring's ~177 px at the caption line.

        Since #304 the caption wraps, centred, inside a MaxWidth. Whether that
        fits is a question about pixels, so the probe lays out the real
        TodayView with the app's own resources and embedded Inter: every
        caption RingCaption lists, with the shield glyph beside it when a
        sprint runs, and with nothing below it (the caption at its lowest,
        where the ring is narrowest) or with "Sprint 4 of 4" below it. Every
        box it reports must sit inside the ring's inner circle, corners
        included, and no caption may take more than two lines. (The timer's
        own box is not checked: its corners are empty line padding.)
        """
        entries = theme_probe["ringCaptions"]
        assert entries, "the probe measured no ring captions"
        for entry in entries:
            where = f"\"{entry['text']}\" ({entry['below']} below)"
            assert entry["styled"] and entry["fontSize"] == 12, entry
            assert (entry["font"] or "").lower() == "inter-regular.ttf", (
                f"{where} was measured in {entry['font']}, not the embedded Inter")
            # MM:SS in tabular digits is the widest the timer gets without
            # shrinking further, so it is also the tallest: the worst case.
            assert re.fullmatch(r"\d\d:\d\d", entry["timerText"]), entry["timerText"]
            assert entry["timer"][3] > 55, f"{where}: the timer line was not laid out: {entry['timer']}"
            assert entry["lines"] <= 2, f"#304: {where} takes {entry['lines']} lines"

            radius = entry["ringDiameter"] / 2 - entry["ringStroke"]
            centre = entry["ringDiameter"] / 2
            for name in ("caption", "glyph", "cycle"):
                box = entry[name]
                if box is None:
                    continue
                x, y, w, h = box
                for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
                    reach = ((cx - centre) ** 2 + (cy - centre) ** 2) ** 0.5
                    assert reach <= radius, (
                        f"#304: {where}: the {name} box {box} reaches {reach:.1f} px from the "
                        f"centre, past the ring's {radius:.1f} px inner edge")

    def test_the_layout_probe_covers_both_sleep_states_and_the_glyph(self, theme_probe):
        entries = theme_probe["ringCaptions"]
        texts = {" ".join(e["text"].split()) for e in entries}
        for text in ("Break — the shield is down", "Break resumed — the shield is down",
                     "Break — sleep shield still up", "Break resumed — sleep shield still up",
                     "Sprint finished while Basalt was closed", "Sprint resumed — shield III"):
            assert text in texts, f"#304: {text!r} was not laid out"
        assert {e["below"] for e in entries} == {"none", "cycle"}
        assert all((e["glyph"] is not None) == e["running"] for e in entries), (
            "the glyph shows beside a running sprint's caption and nowhere else")

    def test_the_view_model_hard_codes_no_line_about_the_shield_being_down(self):
        """Every break line comes from BreakCopy, which knows about the window."""
        code = re.sub(r"//.*", "", self.vm())
        literals = re.findall(r'"(?:[^"\\\n]|\\.)*"', code)
        claims = [s for s in literals if re.search(r"shield (is|stays|comes) down|shield down", s, re.I)]
        assert not claims, (
            f"#301: {claims} would promise the shield is down inside the sleep "
            "window too; take the line from BreakCopy instead"
        )

    def test_the_offer_is_re_raised_while_it_is_on_screen(self):
        """
        No clock runs while a break is on offer, so the window opening under it
        went unnoticed until the next sprint. The one timer keeps running for
        the offer, raises its text, and stops once nothing is on screen.
        """
        source = self.vm()
        offer = source.split("private void OfferBreakIfEarned(bool completed)")[1].split("\n    }")[0]
        shown = offer.split("BreakOfferVisible = true;")[1].split("BreakOfferVisible = false;")[0]
        # Since #319 every start of the clock goes through StartClock(), which
        # sets when its first tick is due before _tick.Start().
        assert "StartClock();" in shown, (
            "#301: the timer must keep running while a break offer waits on screen"
        )
        tick = source.split("private void OnTick()")[1].split("\n    }")[0]
        assert "if (!IsRunning)" in tick, (
            "#301: OnTick needs a path for when neither a sprint nor a break runs"
        )
        idle = tick.split("if (!IsRunning)")[1].split("var remaining")[0]
        assert re.search(
            r"if\s*\(\s*BreakOfferVisible\s*\)\s*Raise\(nameof\(BreakPanelText\)\);"
            r"\s*else\s+_tick\.Stop\(\);",
            idle,
        ), (
            "#301: while no sprint or break runs, a tick must refresh the offer's "
            "text if the offer is up, and stop the timer if it is not"
        )

    def test_settings_describes_breaks_without_promising_the_shield_is_down(self):
        xaml = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(encoding="utf-8")
        assert "The shield is down while one runs" not in xaml, (
            "#301: a nightly sleep window still closes blocked apps during a break"
        )
        assert ("The sprint's shield is down while one runs (a nightly sleep window "
                "still applies)") in xaml

    # ------------------------------------------------------------------ #304
    # #301's follow-up: the five-minutes-left notification still promised the
    # shield comes down, the ring's older captions overran the ring, and the
    # checklist and the site said the shield is down with no condition.

    RING_CAPTION = Path(DESKTOP_DIR) / "Models" / "RingCaption.cs"

    def code(self) -> str:
        """The view model with comments stripped, so a line left in a comment can't pass."""
        return re.sub(r"//.*", "", self.vm())

    def test_the_five_minutes_left_notification_asks_the_sleep_window(self):
        """
        The notification speaks about the moment the time is up, so the window
        is asked about that moment: a window opening or closing inside the
        last five minutes changes which shield is up then.
        """
        code = self.code()
        call = code.split("NotificationKind.FiveMinutesLeft", 1)[1].split(";", 1)[0]
        call = " ".join(call.split())
        assert re.search(
            r"BreakCopy\.EndingSoon\(\s*AppBlockerService\.IsWithinSleepWindow\(\s*S\s*,\s*"
            r"_endsAtUtc\.ToLocalTime\(\)\s*\)\s*,\s*"
            r"SleepBlockingViewModel\.Format\(\s*S\.SleepBlockEndTime\s*\)\s*\)",
            call,
        ), f"#304: the notification's words must come from BreakCopy.EndingSoon; got {call!r}"
        assert "comes down" not in call, "#304: no hand-typed copy of the line beside it"

    def test_every_ring_caption_comes_from_ring_caption_or_break_copy(self):
        """
        Tier 5's layout probe measures RingCaption's list. A caption typed
        straight into the view model would never be measured.
        """
        code = self.code()
        assignments = re.findall(r"SessionStateText\s*=(?!=)\s*([^;]*);", code)
        assignments += re.findall(r"(?<!void )BeginRunning\(([^;]*)\);", code)
        assignments += re.findall(r"_sessionStateText\s*=\s*([^;]*);", code)
        assert len(assignments) >= 9, assignments
        for rhs in assignments:
            rhs = " ".join(rhs.split())
            if rhs == "stateText":  # BeginRunning's own parameter
                continue
            assert '"' not in rhs, f"#304: {rhs!r} is typed into the view model; add it to RingCaption"
            assert "RingCaption." in rhs or "BreakCopy.Caption(" in rhs, rhs

    def test_ring_caption_lists_every_line_it_defines(self):
        assert self.RING_CAPTION.exists(), "#304: the ring's captions live in Models/RingCaption.cs"
        source = self.RING_CAPTION.read_text(encoding="utf-8")
        every = source.split("public static IReadOnlyList<(string Text, bool Running)> Every()")[1]
        members = re.findall(r"public const string (\w+)", source)
        members += re.findall(r"public static string (\w+)\(ShieldLevel", source)
        assert len(members) >= 9, members
        for member in members:
            assert re.search(rf"\b{member}\b", every), f"#304: RingCaption.Every() leaves out {member}"
        assert "BreakCopy.Caption(" in every, "and the four break captions"

    def test_the_caption_wraps_centred_inside_the_ring(self):
        xaml = (Path(DESKTOP_DIR) / "Views" / "TodayView.xaml").read_text(encoding="utf-8")
        block = xaml.split('AutomationProperties.AutomationId="SessionStateText"')[0]
        block = block[block.rindex("<TextBlock"):]
        assert 'TextWrapping="Wrap"' in block and 'TextAlignment="Center"' in block, block
        assert re.search(r'MaxWidth="\d+"', block), block

    def test_the_checklist_qualifies_the_shield_being_down_during_breaks(self):
        checklist = (Path(DESKTOP_DIR).parent / "LAUNCH_FEATURE_CHECKLIST.md").read_text(encoding="utf-8")
        line = next(l for l in checklist.splitlines() if "During breaks" in l)
        assert "sleep" in line, f"#304: F5 promises the shield is down with no condition: {line}"
        assert "Blocked apps are allowed and" not in line, line

    def test_the_site_never_says_the_shield_is_down_without_the_sleep_window(self):
        for page in sorted((Path(DESKTOP_DIR).parent / "Website").glob("*.html")):
            if page.name == "changelog.html":
                continue  # it describes the fixes to these claims
            for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"shield (is |comes |stays )?down", line, re.I):
                    assert "sleep" in line.lower(), (
                        f"#304: {page.name}:{number} says the shield is down with no word "
                        f"about a sleep window: {line.strip()}")


class TestTheThemeActuallySwitchesF21:
    """
    The one F21 test that is not source text.

    Every other test in this file reads the XAML and the C# and checks that the
    right words are in the right places. All of them passed against a
    ThemeService that did nothing at all: it looked for the merged dictionary
    with

        merged.FirstOrDefault(d => d.Source == DarkTokens)

    where DarkTokens is an absolute pack URI, while App.xaml merges the
    dictionary with a *relative* Source ("Styles/Tokens.xaml").
    ResourceDictionary.Source hands back exactly the Uri that was set on it, so
    the two never compared equal, the lookup found nothing, the swap logged
    "theme not switched" and returned, and Settings -> Appearance moved a radio
    button and changed no pixels. Source tests cannot see that, and neither can
    a probe that merges the dictionaries itself with pack URIs -- it builds the
    equality the app does not have.

    So this runs the real App.xaml. `automation/probe/ThemeProbe` creates the
    app's own Application subclass, calls InitializeComponent() to merge exactly
    what App.xaml merges in exactly the way it spells it, asks ThemeService to
    switch, and prints what each resource resolves to. No window is created and
    nothing is shown, so it is safe to run beside a UI suite.

    Proven to fail first: restoring the Uri-equality line above makes
    test_switching_to_light_changes_every_colour fail with Bg still #FF141517.
    """

    PROBE = THEME_PROBE

    #: A few tokens whose two themes are far apart, with their values from
    #: design/tokens.json. If these are right, the dictionary really was swapped.
    EXPECTED_DARK = {"Bg": "#FF141517", "Ink": "#FFEDEDEB", "Primary": "#FF3AA892"}
    EXPECTED_LIGHT = {"Bg": "#FFECEBE7", "Ink": "#FF1C1D1F", "Primary": "#FF0C6B5C"}

    @pytest.fixture()
    def probe(self, theme_probe):
        return theme_probe

    def test_the_app_starts_dark(self, probe):
        assert probe["start"]["isLight"] is False
        for key, value in self.EXPECTED_DARK.items():
            assert probe["start"][key] == value, f"{key} is wrong before any switch"

    def test_switching_to_light_changes_every_colour(self, probe):
        """The check the whole feature rests on: the resources really change."""
        assert probe["light"]["isLight"] is True, \
            "ThemeService reported no switch -- it did not find the dictionary to replace"
        for key, value in self.EXPECTED_LIGHT.items():
            assert probe["light"][key] == value, (
                f"{key} is still {probe['light'][key]} after Apply(Light) -- the merged "
                f"Tokens dictionary was not swapped")

        changed = sum(1 for key, value in probe["start"].items()
                      if key != "isLight" and probe["light"][key] != value)
        assert changed >= 14, (
            f"only {changed} resources changed; the light theme redefines all of them")

    def test_switching_back_to_dark_restores_every_colour(self, probe):
        for key, value in probe["start"].items():
            assert probe["dark"][key] == value, \
                f"{key} did not come back to its dark value"

    def test_the_shield_glyphs_are_recoloured_too(self, probe):
        """
        The case a DynamicResource cannot serve: these brushes are inside
        DrawingImages, which are Freezables, so the dictionary is reloaded. If
        the reload is skipped the glyphs keep the dark theme's colours -- and a
        text-muted glyph on a light surface is close to invisible.
        """
        assert probe["start"]["glyphSoft"] == "#FFAEB0B3"
        assert probe["light"]["glyphSoft"] == "#FF54565A", \
            "the Soft glyph kept its dark colour; ShieldGlyphs.xaml was not reloaded"
        assert probe["light"]["glyphFirm"] == "#FF0C6B5C"
        assert probe["dark"]["glyphSoft"] == "#FFAEB0B3"

    def test_the_heatmap_ramp_follows_the_theme(self, probe):
        """Mixed in code from surface-2 and primary, so it has to re-read them."""
        assert probe["start"]["heatTop"] == "#FF3AA892"
        assert probe["light"]["heatTop"] == "#FF0C6B5C", \
            "the heatmap's top step is still the dark theme's primary"

    def test_the_probe_shows_no_window(self):
        """
        It must stay safe to run while a UI suite owns the screen, so it may
        never create or show a window.
        """
        source = (self.PROBE / "Program.cs").read_text(encoding="utf-8")
        for forbidden in ("new Window", ".Show()", ".ShowDialog()", "app.Run("):
            assert forbidden not in source, \
                f"the theme probe must not {forbidden} -- it runs beside the UI suite"


class TestSleepWindowPickersDrawRoadmap37:
    """
    Roadmap 3.7: the sleep window's times are picked, not typed. The probe
    builds the real SleepBlockingView offscreen with the app's own resources,
    so a XAML error, a missing style or a picker that draws at 0 x 0 fails
    here instead of on a customer's Schedule page. (Which value each picker
    holds is the view model's, and is covered from the source in tier 1.)
    """

    PICKERS = {"SleepStartHour": (24, "00", "23"), "SleepEndHour": (24, "00", "23"),
               "SleepStartMinute": (60, "00", "59"), "SleepEndMinute": (60, "00", "59")}

    def test_every_picker_lists_every_valid_value(self, theme_probe):
        pickers = theme_probe["sleepPage"]["pickers"]
        assert set(pickers) == set(self.PICKERS)
        for auto_id, (count, first, last) in self.PICKERS.items():
            entry = pickers[auto_id]
            assert (entry["items"], entry["first"], entry["last"]) == (count, first, last), auto_id

    def test_every_picker_is_themed_named_reachable_and_drawn(self, theme_probe):
        for auto_id, entry in theme_probe["sleepPage"]["pickers"].items():
            assert entry["styled"] and entry["templated"], f"{auto_id} is not using the picker style"
            assert entry["focusable"], f"{auto_id} cannot take the keyboard"
            assert entry["name"].startswith("Sleep block"), f"{auto_id} has no accessible name"
            assert entry["width"] >= 60 and entry["height"] >= 28, f"{auto_id} drew at {entry['width']} x {entry['height']}"

    def test_a_picked_value_shows_its_label_in_the_closed_box(self, theme_probe):
        # The probe picks 22 in each hour box and 30 in each minute box.
        for auto_id, entry in theme_probe["sleepPage"]["pickers"].items():
            expected = "22" if auto_id.endswith("Hour") else "30"
            assert entry["shown"] == expected, f"{auto_id} draws {entry['shown']!r}, not {expected!r}"

    def test_the_page_still_has_its_save_button(self, theme_probe):
        assert theme_probe["sleepPage"]["saveButton"] is True
