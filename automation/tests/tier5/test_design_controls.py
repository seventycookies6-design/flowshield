# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: design controls."""

from __future__ import annotations
import re
from pathlib import Path
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR

class TestNavigationUsesIconsNotUnicodeGlyphs:
    """
    Design system §5. The navigation used Unicode glyphs (U+25F7, U+2298,
    U+263E, U+2699), which render differently across Windows versions and did
    not match each other. They are now Lucide geometry in Styles/Icons.xaml.

    A font-dependent glyph reintroduced in a view would look fine on the
    machine that added it and wrong on a customer's, so it is caught here
    rather than by eye.
    """

    VIEWS = ("MainWindow.xaml", "Views/BlockedAppsView.xaml",
             "Views/SleepBlockingView.xaml", "Views/TodayView.xaml",
             "Views/SettingsView.xaml", "Views/HistoryView.xaml")
    # The glyphs this replaced, plus the other symbol ranges a future one would
    # most likely come from. U+2192 (a typographic arrow between two fields) is
    # text, not an icon, and is deliberately allowed.
    BANNED = "◷⊘☾⚙↻✓✗⚠⭐★"

    def test_no_glyph_icons_left_in_the_views(self):
        offenders = []
        for name in self.VIEWS:
            path = Path(DESKTOP_DIR) / name
            if not path.exists():
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for ch in self.BANNED:
                    if ch in line:
                        offenders.append(f"{name}:{n} contains U+{ord(ch):04X}")
        assert not offenders, (
            "use a Path with the Icon style and a geometry from Icons.xaml:\n  "
            + "\n  ".join(offenders))


    # The rail's icons, by key. Each is drawn in a 20 x 20 box with
    # Stretch=Uniform, so a geometry whose bounds aren't square is drawn
    # narrower than its neighbours, and one covering less of the grid is
    # drawn heavier.
    NAV_ICONS = ("IconToday", "IconHistory", "IconBlocked", "IconSleep", "IconSettings")

    @staticmethod
    def _bounds(path_data: str) -> tuple[float, float, float, float]:
        """Exact-enough bounds of absolute M/L/A/Z path data: arcs are
        sampled along their real centre, not taken from their end points,
        because a gear's or a circle's extremes sit mid-arc."""
        import math
        tokens = re.findall(r"[MLAZ]|-?[\d.]+", path_data)
        xs, ys = [], []
        x = y = 0.0
        i = 0
        while i < len(tokens):
            cmd = tokens[i]
            i += 1
            if cmd in ("M", "L"):
                x, y = float(tokens[i]), float(tokens[i + 1])
                i += 2
                xs.append(x); ys.append(y)
            elif cmd == "A":
                rx, _ry, _rot, large, sweep, x2, y2 = (float(t) for t in tokens[i:i + 7])
                i += 7
                # SVG endpoint-to-centre conversion, for a circular arc.
                dx, dy = (x - x2) / 2, (y - y2) / 2
                d2 = dx * dx + dy * dy
                rx = max(rx, math.sqrt(d2))
                k = math.sqrt(max(0.0, (rx * rx - d2) / d2)) if d2 else 0.0
                if int(large) == int(sweep):
                    k = -k
                cx, cy = (x + x2) / 2 + k * dy, (y + y2) / 2 - k * dx
                a1 = math.atan2(y - cy, x - cx)
                a2 = math.atan2(y2 - cy, x2 - cx)
                span = a2 - a1
                if sweep and span < 0:
                    span += 2 * math.pi
                elif not sweep and span > 0:
                    span -= 2 * math.pi
                for s in range(65):
                    a = a1 + span * s / 64
                    xs.append(cx + rx * math.cos(a)); ys.append(cy + rx * math.sin(a))
                x, y = x2, y2
        return min(xs), min(ys), max(xs), max(ys)

    def test_nav_icons_are_evenly_proportioned(self):
        """#406: the gear covered 15 x 19 of the grid (its top and bottom
        teeth reached further from the centre than its side ones), so the
        rail drew it tall and narrow beside four round icons."""
        icons = (Path(DESKTOP_DIR) / "Styles" / "Icons.xaml").read_text(encoding="utf-8")
        problems = []
        for key in self.NAV_ICONS:
            data = re.search(rf'x:Key="{key}">([^<]+)<', icons).group(1)
            left, top, right, bottom = self._bounds(data)
            width, height = right - left, bottom - top
            if abs(width - height) > 0.25:
                problems.append(f"{key} covers {width:.2f} x {height:.2f}: not square")
            if not 17.5 <= max(width, height) <= 18.5:
                problems.append(f"{key} covers {max(width, height):.2f} of the grid, not 18")
        assert not problems, "\n  ".join(["nav icons drawn at uneven sizes:"] + problems)

    def test_the_lucide_notice_is_kept(self):
        notice = Path(DESKTOP_DIR) / "Assets" / "Icons" / "LICENSE"
        assert notice.exists(), "Lucide is ISC-licensed; keep its notice with the icons"
        text = notice.read_text(encoding="utf-8")
        assert "ISC License" in text and "Lucide" in text

class TestInterTypeScale:
    """
    DESIGN_SYSTEM.md §3: Inter, embedded, is the only face the app actually
    renders in (today's fallback chain put it third, behind two Segoe UI
    entries nobody's machine was missing). Embedded as a resource, with its
    OFL licence kept alongside, and its pack URI assembly-qualified so it
    also resolves when the render kit hosts the built DLL rather than
    launching FlowShield.exe.
    """

    FONTS_DIR = Path(DESKTOP_DIR) / "Assets" / "Fonts"
    CSPROJ = Path(DESKTOP_DIR) / "FlowShield.csproj"
    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"
    TODAY_VIEW = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"
    VIEWS = ("MainWindow.xaml", "Views/BlockedAppsView.xaml", "Views/FriendlyErrorDialog.xaml",
             "Views/SleepBlockingView.xaml", "Views/TodayView.xaml", "Views/SettingsView.xaml")

    EMBEDDED_WEIGHTS = ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf")

    # A view is allowed to reference the FontStack resource, or -- for
    # licence keys and anything the user must copy exactly, §3's own
    # exception -- the Cascadia Mono fallback. Nothing else.
    ALLOWED_FONT_FAMILY_VALUES = ("{StaticResource FontStack}", "Cascadia Mono, Consolas, monospace")

    def test_fonts_are_embedded_on_disk_and_in_the_csproj(self):
        csproj = self.CSPROJ.read_text(encoding="utf-8")
        for weight in self.EMBEDDED_WEIGHTS:
            font_path = self.FONTS_DIR / weight
            assert font_path.is_file(), (
                f"{font_path} is missing -- Inter must actually be embedded, not just "
                f"referenced")
            assert f'Assets\\Fonts\\{weight}' in csproj, (
                f"{weight} exists on disk but has no <Resource Include> entry in "
                f"FlowShield.csproj, so it won't ship in the build")

    def test_bold_is_not_embedded_unless_the_scale_uses_it(self):
        """
        §3's scale doesn't use weight 700 anywhere in the app (it's reserved
        for the site hero). UI-SPEC.md §2 is explicit: don't embed Inter-Bold
        unless a real in-app use is found. A stray Bold file would be dead
        weight nobody meant to ship.
        """
        assert not (self.FONTS_DIR / "Inter-Bold.ttf").exists(), (
            "Inter-Bold is embedded but nothing in the §3 app scale uses weight 700 -- "
            "either use it for something real and document why, or drop it")

    def test_the_ofl_licence_is_present(self):
        licence = self.FONTS_DIR / "OFL.txt"
        assert licence.is_file(), "Inter is OFL-licensed; its licence text must ship with it"
        text = licence.read_text(encoding="utf-8")
        assert "SIL Open Font License" in text

    def test_font_stack_is_an_assembly_qualified_pack_uri(self):
        """
        A relative pack URI resolves fine when FlowShield.exe launches itself,
        but silently falls back to a system font when the render kit hosts
        the built DLL directly -- the exact split this test guards against.
        """
        theme = self.THEME.read_text(encoding="utf-8")
        match = re.search(r'<FontFamily x:Key="FontStack">([^<]+)</FontFamily>', theme)
        assert match, "Theme.xaml should define the FontStack FontFamily resource"
        stack = match.group(1)
        assert stack.startswith("pack://application:,,,/FlowShield;component/Assets/Fonts/#Inter"), (
            f"FontStack is {stack!r} -- it must start with the assembly-qualified pack "
            f"URI form, or the render kit's hosted-DLL rendering falls back to Segoe")

    def test_no_view_sets_a_font_family_other_than_the_stack(self):
        offenders = []
        for name in self.VIEWS:
            path = Path(DESKTOP_DIR) / name
            if not path.exists():
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for value in re.findall(r'FontFamily="([^"]+)"', line):
                    if value not in self.ALLOWED_FONT_FAMILY_VALUES:
                        offenders.append(f"{name}:{n} sets FontFamily={value!r}")
        assert not offenders, (
            "a view should reference the FontStack resource (or, for licence keys "
            "only, the Cascadia Mono fallback), not set its own literal FontFamily:\n  "
            + "\n  ".join(offenders))

    def _tag_for(self, xml: str, automation_id: str) -> str:
        """The full opening tag (attributes only) that carries this AutomationId."""
        match = re.search(
            r'<(\w+)\b((?:(?!/?>).)*?AutomationId="' + re.escape(automation_id) + r'"(?:(?!/?>).)*?)/?>',
            xml, re.S)
        assert match, f"no element with AutomationId={automation_id!r} found"
        return match.group(2)

    def test_timer_and_stat_numbers_are_tabular(self):
        """
        §3: the timer, momentum, and every Today stat are tabular so the
        digits don't jiggle as they change. Checked by AutomationId, which
        survives a restyle better than matching on FontSize.
        """
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        tabular_ids = (
            "SprintTimerText", "MomentumValue", "SessionsTodayValue",
            "FocusMinutesValue", "BlocksTodayValue", "DailyGoalProgressText",
        )
        offenders = []
        for automation_id in tabular_ids:
            tag = self._tag_for(xml, automation_id)
            if 'Typography.NumeralAlignment="Tabular"' not in tag:
                offenders.append(automation_id)
        assert not offenders, (
            "these number displays are missing Typography.NumeralAlignment=\"Tabular\": "
            + ", ".join(offenders))

    def test_blocked_app_row_name_and_summary_do_not_wrap(self):
        """
        Regression (PR #171 review): Inter's wider metrics overflowed the
        blocked-app row's fixed-width name column, which fit under Segoe UI
        but, post-swap, wrapped "Minecraft Launcher" to two lines and its
        exe-name line ("minecraftlauncher.exe, Minecraft.Windows.exe") to
        three, with mid-word splits ("minecraftlauncher.ex" / "e"). Both
        TextBlocks must trim to a single line with an ellipsis instead of
        wrapping, so a long app or process name never breaks mid-word again
        regardless of how narrow the row gets.
        """
        view = Path(DESKTOP_DIR) / "Views" / "BlockedAppsView.xaml"
        xml = view.read_text(encoding="utf-8")

        name_match = re.search(
            r'<TextBlock Text="\{Binding DisplayName\}"(?:(?!/?>).)*?/>', xml, re.S)
        assert name_match, "expected the blocked-app row's name TextBlock bound to DisplayName"
        name_tag = name_match.group(0)
        assert 'TextWrapping="NoWrap"' in name_tag, (
            "the blocked-app row's name TextBlock must set TextWrapping=\"NoWrap\" -- "
            "otherwise a long app name wraps across lines under Inter's wider metrics")
        assert 'TextTrimming="CharacterEllipsis"' in name_tag, (
            "the blocked-app row's name TextBlock must set TextTrimming=\"CharacterEllipsis\" "
            "so a long name trims with an ellipsis instead of being clipped bare")

        summary_match = re.search(
            r'<TextBlock Style="\{StaticResource Caption\}"(?:(?!/?>).)*?>'
            r'\s*<Run Text="\{Binding ProcessSummary', xml, re.S)
        assert summary_match, (
            "expected the blocked-app row's process-summary TextBlock bound to "
            "ProcessSummary via a Run")
        summary_tag = summary_match.group(0)
        assert 'TextWrapping="NoWrap"' in summary_tag, (
            "the blocked-app row's process-summary TextBlock must set "
            "TextWrapping=\"NoWrap\" -- otherwise a single long exe name (no spaces) "
            "forces a mid-word break to fit the narrow column")
        assert 'TextTrimming="CharacterEllipsis"' in summary_tag, (
            "the blocked-app row's process-summary TextBlock must set "
            "TextTrimming=\"CharacterEllipsis\" so a long exe name trims with an "
            "ellipsis instead of breaking mid-word")


class TestShieldGlyphsA4:
    """
    DESIGN_SYSTEM.md §6: the three shields are built once, as XAML geometry,
    and reused everywhere a shield glyph appears. UI-SPEC.md A4 wires that
    resource into the Today page's shield chips and the timer ring.
    """

    GLYPHS = Path(DESKTOP_DIR) / "Styles" / "ShieldGlyphs.xaml"
    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"
    TODAY_VIEW = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"

    def _resource_block(self, xml: str, key: str) -> str:
        match = re.search(
            r'<DrawingImage x:Key="' + re.escape(key) + r'">.*?</DrawingImage>', xml, re.S)
        assert match, f"no ShieldGlyph{key.replace('ShieldGlyph', '')} DrawingImage resource found"
        return match.group(0)

    def test_glyph_file_exists_and_takes_its_brushes_from_the_tokens(self):
        """
        F21: the glyphs no longer merge Tokens.xaml themselves -- that copy
        would shadow the dictionary ThemeService swaps, and the glyphs would
        stay dark on a light background. They use DynamicResource instead, and
        App.xaml merges the tokens ahead of them.
        """
        assert self.GLYPHS.is_file(), (
            "DesktopApp/Styles/ShieldGlyphs.xaml is missing -- the shield glyphs must be "
            "built once, in a shared resource dictionary (UI-SPEC.md A4)")
        xml = self.GLYPHS.read_text(encoding="utf-8")
        assert '<ResourceDictionary Source="Tokens.xaml"/>' not in xml, (
            "ShieldGlyphs.xaml must not merge the tokens itself -- that copy shadows "
            "the dictionary F21 swaps at run time")
        assert "{DynamicResource" in xml and "{StaticResource" not in xml, (
            "the glyph brushes must be DynamicResource so a fresh load of this "
            "dictionary picks up the theme in force")

    def test_the_app_merges_the_glyph_dictionary(self):
        app = (Path(DESKTOP_DIR) / "App.xaml").read_text(encoding="utf-8")
        assert '<ResourceDictionary Source="Styles/ShieldGlyphs.xaml"/>' in app, (
            "App.xaml must merge ShieldGlyphs.xaml, after the tokens, or the glyph "
            "resources are never loaded into the app")

    def test_each_shipped_level_has_a_usable_icon(self):
        converter = (Path(DESKTOP_DIR) / "Infrastructure" / "Converters.cs").read_text(
            encoding="utf-8")
        resource_keys = re.findall(
            r'=>\s*"(ShieldGlyph[\w]+)"', converter.split(
                "class ShieldLevelToGlyphConverter", 1)[1].split("class ", 1)[0])
        assert resource_keys, "the shipped shield levels need icon resources"

        xml = self.GLYPHS.read_text(encoding="utf-8")
        resources = dict(re.findall(
            r'<DrawingImage x:Key="(ShieldGlyph[\w]+)">(.*?)</DrawingImage>', xml, re.S))
        for key in resource_keys:
            assert key in resources, f"{key} has no drawable shield icon"
            assert "{DynamicResource" in resources[key], (
                f"{key} must use theme-aware colors for contrast")
            assert re.search(r"<(?:GeometryDrawing|DrawingGroup)\b", resources[key]), (
                f"{key} has no drawable geometry")

    def test_soft_shield_level_is_distinct_and_uses_theme_contrast(self):
        """§6 keeps Soft distinct and readable at the lowest shield level."""
        block = self._resource_block(self.GLYPHS.read_text(encoding="utf-8"), "ShieldGlyphSoft")
        assert "{DynamicResource InkDim}" in block
        assert "{DynamicResource Primary}" not in block, (
            "Soft stays visually distinct and readable at its gentler level")

    def test_firm_shield_level_is_distinct_and_uses_theme_contrast(self):
        """Firm remains visually distinct from Soft while following the active theme."""
        block = self._resource_block(self.GLYPHS.read_text(encoding="utf-8"), "ShieldGlyphFirm")
        assert block.count("{DynamicResource Primary}") >= 1
        assert "{DynamicResource InkDim}" not in block

    def test_sealed_shield_level_is_distinct_and_high_contrast(self):
        block = self._resource_block(self.GLYPHS.read_text(encoding="utf-8"), "ShieldGlyphSealed")
        assert 'Brush="{DynamicResource Primary}"' in block, (
            "Sealed's shield shape must be a solid primary fill, not an outline")
        assert "{DynamicResource PrimaryInk}" in block, (
            "Sealed needs high-contrast details against its filled shield")

    def test_shield_chips_reference_the_shared_glyph_resource(self):
        """
        DynamicResource since F21: ThemeService reloads the glyph dictionary on
        a theme change, and a StaticResource would hold the old instance.
        """
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        for key in ("ShieldGlyphSoft", "ShieldGlyphFirm", "ShieldGlyphSealed"):
            assert f'Source="{{DynamicResource {key}}}"' in xml, (
                f"the {key} chip should render the shared glyph resource, not its own "
                f"re-derived geometry")

    def test_timer_ring_uses_the_glyph_via_a_converter(self):
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        assert 'Converter={StaticResource ShieldGlyph}' in xml, (
            "the timer ring should show the active shield's glyph via a level->glyph "
            "converter (one resource, reused, not a duplicate drawing)")


class TestTimerRingA4:
    """UI-SPEC.md A4, §1.7.2 doc amendment: 222px ring, 12px stroke, round cap."""

    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"
    TODAY_VIEW = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"


    def test_progress_dash_radius_matches_the_ring_geometry(self):
        """
        The dash-array converter computes off the stroke's centreline: radius =
        (ellipse diameter - stroke thickness) / 2. A mismatch here would make the
        arc visibly overshoot or undershoot the track it's drawn over.
        """
        theme = self.THEME.read_text(encoding="utf-8")
        match = re.search(
            r'<inf:ProgressToDashConverter x:Key="ProgressDash" Radius="([\d.]+)" '
            r'Thickness="([\d.]+)"/>', theme)
        assert match, "expected the ProgressDash converter resource in Theme.xaml"
        radius, thickness = float(match.group(1)), float(match.group(2))

        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        ellipse_widths = {float(w) for w in re.findall(r'<Ellipse Width="([\d.]+)"', xml)}
        assert len(ellipse_widths) == 1, f"expected one consistent ring diameter, got {ellipse_widths}"
        diameter = next(iter(ellipse_widths))

        assert radius == pytest.approx((diameter - thickness) / 2), (
            f"ProgressDash Radius={radius} doesn't match the ring geometry "
            f"(diameter={diameter}, stroke={thickness} -> expected radius "
            f"{(diameter - thickness) / 2})")

    def test_long_times_shrink_to_fit_inside_the_ring(self):
        """
        At the 64 px timer size "45:00" fits inside the ring, but "1:29:59"
        (a running sprint of an hour or more) and "240:00" (the custom
        maximum, TodayViewModel.CustomMaxMinutes) ran across the 12 px stroke.
        The number sits in a Viewbox that only ever shrinks it, capped inside
        the ring's 198 px inner diameter.
        """
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        fit = re.search(r'<Viewbox x:Name="TimerFit"([^>]*)>(.*?)</Viewbox>', xml, re.S)
        assert fit, "the timer TextBlock must sit inside the TimerFit Viewbox"
        attrs, body = fit.group(1), fit.group(2)
        assert 'StretchDirection="DownOnly"' in attrs, (
            "the Viewbox must only shrink the number; enlarging short times would "
            "change the timer's size as it counts down")
        max_width = re.search(r'MaxWidth="([\d.]+)"', attrs)
        inner = 222 - 2 * 12
        assert max_width and float(max_width.group(1)) < inner, (
            f"the Viewbox needs a MaxWidth inside the ring's {inner} px inner diameter")
        assert 'AutomationProperties.AutomationId="SprintTimerText"' in body, (
            "SprintTimerText stays on the TextBlock itself, inside the Viewbox")


    def test_inter_display_semibold_is_embedded(self):
        font_path = Path(DESKTOP_DIR) / "Assets" / "Fonts" / "InterDisplay-SemiBold.ttf"
        assert font_path.is_file(), "InterDisplay-SemiBold.ttf must be embedded on disk"
        csproj = (Path(DESKTOP_DIR) / "FlowShield.csproj").read_text(encoding="utf-8")
        assert r"Assets\Fonts\InterDisplay-SemiBold.ttf" in csproj, (
            "InterDisplay-SemiBold.ttf exists on disk but has no <Resource Include> "
            "entry in FlowShield.csproj, so it won't ship in the build")


class TestTodayAutomationIdsUnchangedA4:
    """
    Three past incidents put an AutomationId on a layout panel during a
    restyle (#134 and friends) -- UI Automation never surfaces it, so a test
    asking for it would pass whether the control was drawn or not. A4
    rebuilds the ring and the shield chips; every AutomationId that existed
    before must still exist, on a real control, not a Border/Grid/StackPanel/
    Image wrapper.
    """

    TODAY_VIEW = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"

    # The full set of AutomationIds TodayView.xaml carried before A4 touched it
    # (PR #171 / design/a1-inter-app). A4 must not remove or rename any of these.
    EXPECTED_IDS = {
        "SprintTimerText", "SessionStateText", "SprintIntentionText",
        "StartSprintButton", "StopSprintButton",
        "RunningAppsTitle", "RunningAppsExplanation", "RunningAppsList",
        "CloseThemNowButton", "StartAnywayButton",
        "EndSprintPanel", "EndPanelTitle", "EndPanelText", "EndPhraseInput",
        "EndCountdownText", "KeepGoingButton", "EndAnywayButton",
        "SprintLength_15", "SprintLength_25", "SprintLength_45", "SprintLength_60",
        "SprintLength_90", "SprintLength_Custom",
        "CustomMinutesInput", "CustomMinutesError",
        "Shield_Soft", "Shield_Firm", "Shield_Sealed",
        "ShieldDescriptionText", "ShieldBestForText",
        "SealedRestartHint", "SoftHardKillHint",
        "IntentionInput",
        "SummaryTitle", "SummaryMinutesValue", "SummaryDistractionsValue",
        "SummaryMomentumText", "SummaryStreakText", "SummaryIntentionText",
        "JournalPromptTitle", "JournalInput", "SaveJournalButton",
        "MomentumValue", "StreakText", "MomentumTrendRange", "MomentumTrendPeak",
        "MomentumExplainerButton", "MomentumExplainerText",
        "SessionsTodayValue", "FocusMinutesValue", "BlocksTodayValue",
        "DailyGoalProgressText", "DailyGoalBar", "DailyGoalNote",
    }

    # Elements UI Automation never surfaces -- an AutomationId here can never
    # be resolved, so it's not a legitimate handle for anything. Border and
    # ItemsControl are deliberately excluded here: two pre-existing ids
    # (EndSprintPanel, MomentumExplainerText) already sit on those element
    # types from before A4 and are out of this item's scope to relitigate.
    # This list guards the element types A4's own rebuild actually
    # introduces (the ring's Grid, the shield chips' wrapper StackPanel and
    # Image) against the same mistake.
    PANEL_ELEMENTS = ("Grid", "StackPanel", "WrapPanel", "DockPanel", "Image")

    # The Today declutter (#147) moved the momentum explainer to History,
    # ids and all. Moved, not removed: they must be found there instead.
    MOVED_TO_HISTORY = {"MomentumExplainerButton", "MomentumExplainerText"}

    def test_every_expected_automation_id_is_still_present(self):
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        found = set(re.findall(r'AutomationId="([^"]+)"', xml))
        missing = self.EXPECTED_IDS - self.MOVED_TO_HISTORY - found
        assert not missing, f"AutomationIds removed or renamed by A4: {sorted(missing)}"

    def test_the_moved_ids_are_on_history(self):
        history = (Path(DESKTOP_DIR) / "Views" / "HistoryView.xaml").read_text(encoding="utf-8")
        found = set(re.findall(r'AutomationId="([^"]+)"', history))
        assert self.MOVED_TO_HISTORY <= found, sorted(self.MOVED_TO_HISTORY - found)

    def test_no_automation_id_sits_on_a_layout_panel(self):
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        offenders = []
        for tag in re.finditer(r'<(\w+)\b((?:(?!/?>).)*?)/?>', xml, re.S):
            element, attrs = tag.group(1), tag.group(2)
            if element in self.PANEL_ELEMENTS and 'AutomationId="' in attrs:
                offenders.append(f"<{element}> has an AutomationId -- never surfaced to UI Automation")
        assert not offenders, "\n".join(offenders)


class TestMotionA4:
    """
    DESIGN_SYSTEM.md §8: 120/200/300ms, ease-out entering / ease-in leaving,
    honouring SystemParameters.ClientAreaAnimation everywhere. UI-SPEC.md A4
    asks for one shared duration provider rather than a per-animation check.
    """

    MOTION = Path(DESKTOP_DIR) / "Infrastructure" / "Motion.cs"
    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"

    def test_motion_respects_reduced_motion(self):
        src = self.MOTION.read_text(encoding="utf-8")
        assert "SystemParameters.ClientAreaAnimation" in src, (
            "motion must follow the operating system's reduced-motion setting")
        assert re.search(r"AnimationsEnabled\s*\?.*?:\s*0", src, re.S), (
            "animation duration must collapse to zero when animations are disabled")

    def test_durations_collapse_to_zero_when_animations_are_disabled(self):
        """
        Prove the reduced-motion branch actually exists: every duration must
        be computed as "AnimationsEnabled ? <ms> : 0", not a hardcoded
        millisecond value that ignores the setting.

        Proven to fail first: with the ternary replaced by a bare literal
        (e.g. `private static Duration Of(int ms) =>
        new(TimeSpan.FromMilliseconds(ms));`), this test fails, because the
        conditional this regex looks for is gone.
        """
        src = self.MOTION.read_text(encoding="utf-8")
        match = re.search(
            r'private static Duration Of\(int ms\) =>\s*'
            r'new\(TimeSpan\.FromMilliseconds\(AnimationsEnabled \? ms : 0\)\);', src)
        assert match, (
            "Motion.Of must compute its duration as \"AnimationsEnabled ? ms : 0\" so "
            "every duration in the app is exactly zero when Windows' Animation "
            "effects setting (or the test override) is off")

    def test_motion_has_a_test_seam_for_the_os_setting(self):
        src = self.MOTION.read_text(encoding="utf-8")
        assert "AnimationsEnabledOverride" in src, (
            "Motion needs an injectable override -- SystemParameters.ClientAreaAnimation "
            "reads the live host setting, which a test can't flip")

    def test_segment_and_field_motion_respects_reduced_motion(self):
        """
        The disabled-but-visible chip/field treatment (UI-SPEC.md A4: sprint
        length, shield level and intention all dim to 45% opacity while a
        sprint runs) must animate through Motion.Selection, not a hardcoded
        Storyboard duration that would ignore reduced motion.
        """
        theme = self.THEME.read_text(encoding="utf-8")
        motion = self.MOTION.read_text(encoding="utf-8")
        assert "SystemParameters.ClientAreaAnimation" in motion
        assert re.search(r"AnimationsEnabled\s*\?.*?:\s*0", motion, re.S), (
            "segment and field transitions must stop when reduced motion is enabled")
        assert "Motion." in theme, "theme transitions must use the reduced-motion behavior"


class TestKeyboardAndFocusF21:
    """
    DESIGN_SYSTEM.md §13: every interactive element is reachable and usable
    from the keyboard, with a visible 2px focus ring.

    Proven to fail first: before F21 the app set no FocusVisualStyle anywhere,
    so every control fell back to WPF's 1px dotted rectangle -- which on these
    surfaces is next to invisible -- and Escape did nothing on any dialog.
    """

    DESKTOP = Path(DESKTOP_DIR)
    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"

    #: Styles a customer operates, each of which must carry the focus ring.
    FOCUSABLE_STYLES = ("BtnBase", "Field", "Switch", "Segment", "SegmentShield",
                        "PlainItem", "PickerItem", "TimePicker")

    def theme(self) -> str:
        return self.THEME.read_text(encoding="utf-8")

    @staticmethod
    def _style_block(xaml: str, key: str) -> str:
        blocks = [b for b in xaml.split("<Style ")[1:] if f'x:Key="{key}"' in b]
        assert blocks, f"no <Style x:Key=\"{key}\"> in Theme.xaml"
        return blocks[0]

    def test_the_focus_ring_is_two_pixels_of_the_focus_ring_token(self):
        block = self._style_block(self.theme(), "FocusVisual")
        assert 'StrokeThickness="2"' in block, "§13 asks for a 2px ring"
        assert "{DynamicResource FocusRing}" in block, \
            "the ring must use the focus-ring token, and follow the theme"

    @pytest.mark.parametrize("key", FOCUSABLE_STYLES)
    def test_every_operable_style_sets_the_focus_visual(self, key):
        block = self._style_block(self.theme(), key)
        assert '<Setter Property="FocusVisualStyle" Value="{StaticResource FocusVisual}"/>' in block, \
            f"{key} must show the shared 2px focus ring"

    def test_plain_radio_buttons_and_check_boxes_get_it_implicitly(self):
        xaml = self.theme()
        for target in ("RadioButton", "CheckBox"):
            blocks = [b for b in xaml.split("<Style ")[1:]
                      if b.startswith(f'TargetType="{target}">')]
            assert blocks, f"expected an implicit <Style TargetType=\"{target}\">"
            assert "FocusVisualStyle" in blocks[0], \
                f"unstyled {target}s must take the focus ring too"

    def test_the_heatmap_cells_take_focus(self):
        """
        §7: a heatmap must not rely on colour alone, and a cell has to be
        reachable to be read out. HeatCellItem inherits PlainItem's ring.
        """
        block = self._style_block(self.theme(), "HeatCellItem")
        assert 'BasedOn="{StaticResource PlainItem}"' in block
        assert '<Setter Property="Focusable" Value="True"/>' in block

    def test_focusable_false_is_only_on_decoration(self):
        """
        Focusable="False" on something a customer has to operate makes it
        unreachable from the keyboard. Each exception is listed here with its
        reason, so a new one has to be argued for rather than typed.
        """
        allowed_tags = {
            # The scrollbar's paging buttons: the ScrollViewer itself handles
            # Page Up/Down, and these are invisible (Opacity 0).
            "RepeatButton",
            # Inside the time picker's template (3.7): the ToggleButton is the
            # drop-down's hit area and the Popup is its list. The ComboBox
            # itself takes the Tab stop and the focus ring, and the arrow keys
            # and Alt+Down drive the list from there; a second stop on the
            # button would make Tab visit every picker twice.
            "ToggleButton",
            "Popup",
        }
        allowed_styles = {
            # The heatmap legend's five swatches are decoration beside the
            # "Less"/"More" captions, which carry the meaning.
            "HeatLegendItem",
            # The tinted card (#347) is a ContentControl only so it can paint
            # its shadow and its tint on separate layers. It is a container,
            # like a Border; the buttons inside keep their tab stops.
            "CardTinted",
        }
        allowed_ids = {
            # The same legend's own list: not hit-testable either, and every
            # cell it explains is focusable in its place (HeatCellItem).
            "HeatmapLegend",
            # The Schedule page's ScrollViewer: a container. Focusable, it took
            # a Tab stop of its own and drew a dashed rectangle round the whole
            # page. Every control inside keeps its tab stop, and Page Up/Down
            # from any of them still scrolls it.
            "SchedulePageScroll",
            # First-run's shield step scrolls at the smallest window (#406),
            # and is a container for the same reason: the three option cards
            # keep their tab stops, and arrow keys move between them.
            "FirstRunShieldScroll",
        }

        offenders = []
        for path in self.DESKTOP.rglob("*.xaml"):
            if "obj" in path.parts or "bin" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")

            for match in re.finditer(r'<(\w+)((?:[^<>]|\n)*?)Focusable="False"((?:[^<>])*?)>',
                                     text):
                element = match.group(2) + match.group(3)
                automation_id = re.search(r'AutomationProperties.AutomationId="([^"]+)"', element)
                if match.group(1) in allowed_tags:
                    continue
                if automation_id and automation_id.group(1) in allowed_ids:
                    continue
                offenders.append(f"{path.name}: <{match.group(1)}>")

            for match in re.finditer(
                    r'<Setter Property="Focusable" Value="False"\s*/>', text):
                key = re.findall(r'x:Key="([^"]+)"', text[:match.start()])
                if not key or key[-1] not in allowed_styles:
                    offenders.append(f"{path.name}: style {key[-1] if key else '?'}")

        assert not offenders, (
            "these are taken out of the tab order without a reason on record: "
            + ", ".join(sorted(set(offenders))))

    def test_escape_closes_the_dialogs_that_can_be_cancelled(self):
        for name in ("ConfirmDeleteDialog", "FriendlyErrorDialog"):
            xaml = (self.DESKTOP / "Views" / f"{name}.xaml").read_text(encoding="utf-8")
            assert 'IsCancel="True"' in xaml, \
                f"{name} must have a cancel button, so Escape closes it"

    def test_escape_closes_the_panels_that_can_be_cancelled(self):
        window = (self.DESKTOP / "MainWindow.xaml.cs").read_text(encoding="utf-8")
        handler = window.split("protected override void OnPreviewKeyDown(")[1] \
                        .split("\n    /// <summary>")[0]
        assert "Key.Escape" in handler
        assert "DismissActivationCommand" in handler, \
            "Escape must dismiss the activation prompt, which has a Cancel button"
        assert "FirstRun.SkipCommand" in handler, \
            "Escape must skip the welcome, which has a Skip button"

    def test_an_open_panel_keeps_the_keyboard_inside_it(self):
        """
        UI Automation can still reach controls under an overlay (CLAUDE.md,
        "Covered controls"), and so could Tab. Each overlay is a Cycle tab
        scope, and takes focus when it opens.
        """
        xaml = (self.DESKTOP / "MainWindow.xaml").read_text(encoding="utf-8")
        assert xaml.count('KeyboardNavigation.TabNavigation="Cycle"') >= 4, \
            "the lock screen, welcome, activation prompt and terms gate are each a tab scope"
        assert xaml.count('IsVisibleChanged="OnOverlayVisibleChanged"') >= 4


class TestAccessibleNamesF21:
    """
    DESIGN_SYSTEM.md §13: every control has an accessible name. A button whose
    content is a bound string or a TextBlock reads out as nothing useful, and a
    text box has no visible label to borrow from at all.

    Proven to fail first: SettingsView's "Skip today" button and TodayView's
    momentum explainer toggle both had an AutomationId and no name.
    """

    DESKTOP = Path(DESKTOP_DIR)
    TAGS = ("Button", "CheckBox", "RadioButton", "TextBox", "DatePicker",
            "ListBox", "PasswordBox", "ComboBox", "Slider")

    def _views(self):
        return [p for p in self.DESKTOP.rglob("*.xaml")
                if "obj" not in p.parts and "bin" not in p.parts
                and p.parent.name != "Styles"]

    def test_every_control_has_a_name_or_literal_content(self):
        element = re.compile(r"<(" + "|".join(self.TAGS) + r")(?=[\s/>])(.*?)(/>|>)", re.S)
        offenders = []
        for path in self._views():
            text = path.read_text(encoding="utf-8")
            for match in element.finditer(text):
                tag, attributes = match.group(1), match.group(2)
                if "AutomationProperties.Name=" in attributes:
                    continue
                # A literal Content is the control's own visible label, which
                # UI Automation already reads out; a bound one is not.
                if re.search(r'Content="([^"{]+)"', attributes):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.name}:{line} <{tag}>")
        assert not offenders, (
            "controls with no accessible name: " + ", ".join(offenders))

    def test_the_scan_actually_finds_controls(self):
        """A regex that matched nothing would pass for the wrong reason."""
        element = re.compile(r"<(" + "|".join(self.TAGS) + r")(?=[\s/>])", re.S)
        found = sum(len(element.findall(p.read_text(encoding="utf-8"))) for p in self._views())
        assert found > 50, f"expected the app's controls to be scanned, found {found}"

    def test_the_new_appearance_control_did_not_displace_an_existing_id(self):
        """Every AutomationId in the app is still unique to one control."""
        seen = {}
        for path in self._views():
            for automation_id in re.findall(r'AutomationProperties.AutomationId="([^"]+)"',
                                            path.read_text(encoding="utf-8")):
                # A bound id ({Binding AutomationId}) is one per row at run time.
                if automation_id.startswith("{"):
                    continue
                seen.setdefault(automation_id, []).append(path.name)
        duplicates = {k: v for k, v in seen.items() if len(set(v)) > 1}
        # A handful are deliberately shared between a page and the lock screen.
        allowed = {"LicenseKeyInput"}
        assert not (set(duplicates) - allowed), f"duplicate AutomationIds: {duplicates}"


# ================== #290 — minor findings from the 1.0.9 pre-release review

class TestMinorReviewFindings:
    DESKTOP = Path(DESKTOP_DIR)

    def _read(self, *parts) -> str:
        return self.DESKTOP.joinpath(*parts).read_text(encoding="utf-8")

    def test_lost_key_form_rejects_a_malformed_address_before_sending(self):
        js = (Path(WEBSITE_DIR) / "checkout.js").read_text(encoding="utf-8")
        handler = js.split("lost-key-form", 1)[1].split("addEventListener", 1)[1]
        handler = handler.split("\n    var nav")[0]
        check = handler.index("test(email)")
        assert check < handler.index("/resend-license"), "validate before the request"
        assert "Enter a valid email address." in handler[check:handler.index("/resend-license")]
        # the emptiness check stays first, so a blank field keeps its own wording
        assert handler.index("if (!email)") < check

    def test_the_data_export_includes_a_running_sprint(self):
        export = self._read("Services", "DataPrivacyService.cs")
        assert "activeSprint = settings.ActiveSprint" in export

    def test_profile_switching_is_refused_when_the_trial_has_ended(self):
        vm = self._read("ViewModels", "BlockedAppsViewModel.cs")
        select = vm.split("private void SelectProfile(", 1)[1].split("private void NewProfile", 1)[0]
        assert "_main.IsLocked" in select, "refuse in the view model, not only by a disabled chip"
        assert select.index("_main.IsLocked") < select.index("SetActiveProfile")

    def test_running_apps_apply_the_same_not_an_app_filter_as_installed_ones(self):
        catalog = self._read("Services", "AppCatalog.cs")
        running = catalog.split("private static IEnumerable<PickerEntry> Running()", 1)[1] \
            .split("private static IEnumerable<PickerEntry> StartMenu()", 1)[0]
        assert "AppPicker.IsNotAnApp(" in running
# ========== #290 — the last three findings from the 1.0.9 pre-release review

class TestLastReviewFindings:
    DESKTOP = Path(DESKTOP_DIR)

    def _read(self, *parts) -> str:
        return self.DESKTOP.joinpath(*parts).read_text(encoding="utf-8")

    def test_theme_refresh_reaches_template_bindings_like_the_heatmap(self):
        theme = self._read("Services", "ThemeService.cs")
        walk = theme.split("public static void RefreshConverterBindings(", 1)[1] \
            .split("private static readonly DependencyProperty[] ColourProperties", 1)[0]
        # the local-value walk alone misses a binding set by a ControlTemplate
        assert "BindingOperations.GetBindingExpression(root, property)" in walk
        assert "foreach (var property in ColourProperties)" in walk
        props = theme.split("ColourProperties = new[]", 1)[1].split("};", 1)[0]
        # the heatmap cell's Background="{Binding Step, Converter={StaticResource HeatStep}}"
        assert "Border.BackgroundProperty" in props
        xaml = self._read("Styles", "Theme.xaml")
        assert "<Border x:Name=\"Cell\"" in xaml and "Converter={StaticResource HeatStep}" in xaml

    def test_waking_up_copy_is_reported_on_time_not_when_an_attempt_times_out(self):
        service = self._read("Services", "LicenseService.cs")
        validate = service.split("public async Task<LicenseResult> ValidateAsync(", 1)[1] \
            .split("public async Task RefreshAsync(", 1)[0]
        assert "_ = ReportWakingUpLaterAsync(progress, waiting.Token);" in validate
        assert validate.index("ReportWakingUpLaterAsync(progress") < validate.index("for (var attempt = 1")
        assert "waiting.Cancel();" in validate.split("finally", )[-1], "stop the timer once answered"
        timer = validate.split("private static async Task ReportWakingUpLaterAsync(", 1)[1]
        assert "LicenseWaitCopy.WakingUpAfterSeconds" in timer
        assert "progress.Report(LicenseWaitCopy.WakingUpMessage)" in timer
        assert "WakingUpAfterSeconds = 8.0" in self._read("Services", "LicenseWaitCopy.cs")

    def test_a_late_waking_up_report_cannot_overwrite_the_answer(self):
        vm = self._read("ViewModels", "SettingsViewModel.cs")
        activate = vm.split("private async Task ActivateAsync()", 1)[1].split("finally", 1)[0]
        assert "if (!answered) LicenseStatusText = message;" in activate
        assert activate.index("await _license.ValidateAsync(") < activate.index("answered = true;")

    def test_a_stale_devices_response_is_dropped(self):
        vm = self._read("ViewModels", "SettingsViewModel.cs")
        load = vm.split("private async Task LoadDevicesAsync(bool force)", 1)[1] \
            .split("private async Task ReleaseDeviceAsync(", 1)[0]
        assert "var generation = ++_devicesGeneration;" in load
        check = load.index("if (generation != _devicesGeneration) return;")
        assert load.index("await _license.ListDevicesAsync(") < check < load.index("Devices.Clear();")
        release = vm.split("private async Task ReleaseDeviceAsync(", 1)[1].split("// ------", 1)[0]
        # a list asked for before the release may still contain the device
        assert release.index("_devicesGeneration++;") < release.index("await _license.ReleaseDeviceAsync(")
# =========== the Causeway logo replaces the FlowShield shield everywhere (#338)

class TestCausewayLogoIsTheBrandMark:
    """
    After the rename to Basalt the app icon, the tray, the installer, the app's
    navigation and the site's favicon and header still drew the FlowShield
    shield in the old colours. They now use the approved Causeway mark, copied
    from `design/brand/` rather than redrawn.
    """

    BRAND = Path(DESKTOP_DIR).parent / "design" / "brand"
    PAGES = ("index.html", "legal.html", "support.html", "success.html", "changelog.html")

    @classmethod
    def polygons(cls, name: str) -> list[str]:
        svg = (cls.BRAND / name).read_text(encoding="utf-8")
        return re.findall(r'<polygon points="([^"]+)"', svg)

    @staticmethod
    def frame(path: Path, size: int):
        from PIL import Image

        icon = Image.open(path)
        icon.size = (size, size)
        icon.load()
        return icon.convert("RGBA")

    def test_icon_files_are_the_causeway_tiles(self):
        assets = Path(DESKTOP_DIR) / "Assets"
        assert (assets / "FlowShield.svg").read_text(encoding="utf-8") == \
            (self.BRAND / "basalt-icon.svg").read_text(encoding="utf-8")
        assert (assets / "FlowShield.Running.svg").read_text(encoding="utf-8") == \
            (self.BRAND / "basalt-icon-firm.svg").read_text(encoding="utf-8"), \
            "the running icon is the Firm tile"

        idle = self.frame(assets / "FlowShield.ico", 256)
        running = self.frame(assets / "FlowShield.Running.ico", 256)
        ground = (0x17, 0x18, 0x1B, 255)
        # Tile coordinates are 0-100; the frame is 256 px.
        at = lambda image, x, y: image.getpixel((round(x * 2.56), round(y * 2.56)))
        assert at(idle, 1, 1)[3] == 0, "the tile's rounded corner is transparent"
        assert at(idle, 50, 8) == ground and at(running, 50, 8) == ground
        # Centre of the front column's top face: grey when idle, teal mid-sprint.
        assert at(idle, 61.25, 56.5) == (0xE6, 0xE6, 0xE3, 255)
        assert at(running, 61.25, 56.5) == (0x3A, 0xA8, 0x92, 255)
        # The back column's top stays grey on Firm.
        assert at(running, 61.25, 25.5) == (0xE6, 0xE6, 0xE3, 255)

    def test_icon_script_reads_the_brand_svgs(self):
        script = (Path(DESKTOP_DIR).parent / "tools" / "build_icons.py").read_text(encoding="utf-8")
        assert '"basalt-icon.svg"' in script and '"basalt-icon-firm.svg"' in script
        assert '"FlowShield"' in script and '"FlowShield.Running"' in script, \
            "installs, the .csproj and LoadIcon depend on the old file names"

    def test_app_navigation_uses_the_shared_brand_asset(self):
        xaml = (Path(DESKTOP_DIR) / "MainWindow.xaml").read_text(encoding="utf-8-sig")
        nav = xaml[xaml.index('x:Name="NavBrand"'):xaml.index('x:Name="NavBrandText"')]
        assert "{StaticResource BrandMarkTile}" in nav
        mark = (Path(DESKTOP_DIR) / "Styles" / "BrandMark.xaml").read_text(encoding="utf-8")
        assert 'x:Key="BrandMarkTile"' in mark
        app = (Path(DESKTOP_DIR) / "App.xaml").read_text(encoding="utf-8")
        assert '<ResourceDictionary Source="Styles/BrandMark.xaml"/>' in app

    def test_site_favicon_and_header_use_the_shared_mark(self):
        asset = (self.BRAND / "basalt-icon.svg").read_text(encoding="utf-8")
        view_box = re.search(r'viewBox="([^"]+)"', asset)
        colors = set(re.findall(r'fill="(#[0-9A-Fa-f]{6})"', asset))
        assert view_box and colors, "the shared brand asset needs its dimensions and palette"
        for page in self.PAGES:
            html = (Path(WEBSITE_DIR) / page).read_text(encoding="utf-8")
            favicon = re.search(r'<link rel="icon" href="([^"]+)"', html).group(1)
            assert "data:image/svg+xml" in favicon and view_box.group(1) in favicon, (
                f"{page} favicon must use the shared Causeway mark proportions")
            assert "<polygon" in favicon, f"{page} favicon must render the shared tile mark"
            assert any("%23" + color[1:] in favicon for color in colors), (
                f"{page} favicon must use the shared mark palette")

        index = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        brand = index[index.index('<a class="brand"'):index.index("</a>", index.index('<a class="brand"'))]
        assert 'class="brand-mark' in brand, "the header must render the Causeway mark"
        assert any(f'fill="{color}"' in brand for color in colors), (
            "the header must use colors from the shared Causeway asset")


class TestDatePickersFollowTheActiveTheme:
    """Export date inputs and their calendar must not fall back to stock white UI."""

    @staticmethod
    def picker_styles():
        import xml.etree.ElementTree as ET

        path = Path(DESKTOP_DIR) / "Styles" / "Pickers.xaml"
        assert path.is_file(), "DatePicker needs the app's themed templates"
        source = path.read_text(encoding="utf-8-sig")
        return source, ET.fromstring(source)

    def test_picker_dictionary_is_merged_after_theme(self):
        import xml.etree.ElementTree as ET

        app = ET.parse(Path(DESKTOP_DIR) / "App.xaml")
        sources = [element.attrib["Source"] for element in app.iter()
                   if "Source" in element.attrib]
        assert "Styles/Pickers.xaml" in sources
        assert sources.index("Styles/Pickers.xaml") > sources.index("Styles/Theme.xaml")

    def test_datepicker_and_calendar_have_templates_and_focus_visuals(self):
        _, root = self.picker_styles()
        ns = "{http://schemas.microsoft.com/winfx/2006/xaml/presentation}"
        key = "{http://schemas.microsoft.com/winfx/2006/xaml}Key"
        styles = root.findall(ns + "Style")
        picker = next((s for s in styles if s.get("TargetType") in
                       ("DatePicker", "{x:Type DatePicker}") and key not in s.attrib), None)
        calendar = next((s for s in styles if s.get("TargetType") in
                         ("Calendar", "{x:Type Calendar}")), None)
        assert picker is not None, "Settings must pick up an implicit DatePicker style"
        assert calendar is not None, "The popup Calendar needs a matching style"
        for style in (picker, calendar):
            setters = {s.get("Property"): s for s in style.findall(ns + "Setter")}
            assert "Template" in setters
            assert "FocusVisualStyle" in setters

    def test_picker_colours_are_dynamic_token_resources(self):
        import xml.etree.ElementTree as ET

        source, _ = self.picker_styles()
        assert "#" not in source, "Picker colours must come from theme tokens"
        nskey = "{http://schemas.microsoft.com/winfx/2006/xaml}Key"
        tokens = set()
        for name in ("Tokens.xaml", "Tokens.Light.xaml"):
            root = ET.parse(Path(DESKTOP_DIR) / "Styles" / name).getroot()
            tokens.update(e.get(nskey) for e in root if e.tag.rsplit("}", 1)[-1]
                          in ("Color", "SolidColorBrush"))
        references = re.findall(r"\{(StaticResource|DynamicResource)\s+([^{}]+)\}", source)
        colours = [(kind, key) for kind, key in references if key in tokens]
        assert colours, "Picker templates must use the shared colour tokens"
        assert all(kind == "DynamicResource" for kind, _ in colours), colours
