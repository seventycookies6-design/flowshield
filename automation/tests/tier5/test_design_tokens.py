# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: design tokens."""

from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR



# ============ app and site colours come from one file (DESIGN_SYSTEM.md §14)

class TestDesignTokensStayInSync:
    """
    Colours were typed twice, in Theme.xaml and styles.css, and drifted. They
    now come from design/tokens.json through tools/build_tokens.py; these tests
    fail when someone edits a generated file by hand or forgets to regenerate.
    """

    ROOT = Path(DESKTOP_DIR).parent

    def test_generated_token_files_are_current(self):
        result = subprocess.run(
            [sys.executable, str(self.ROOT / "tools" / "build_tokens.py"), "--check"],
            cwd=str(self.ROOT), capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_theme_takes_its_palette_from_the_tokens(self):
        """
        F21 moved the Tokens merge out of Theme.xaml and into App.xaml, so the
        dictionary can be swapped at run time; a second merge anywhere else
        would shadow the swapped one. Theme.xaml still must not define a colour
        of its own.
        """
        theme = (Path(DESKTOP_DIR) / "Styles" / "Theme.xaml").read_text(encoding="utf-8")
        app = (Path(DESKTOP_DIR) / "App.xaml").read_text(encoding="utf-8")
        assert '<ResourceDictionary Source="Styles/Tokens.xaml"/>' in app
        assert '<ResourceDictionary Source="Tokens.xaml"/>' not in theme, \
            "Theme.xaml must not merge the tokens itself -- it would shadow the swapped dictionary"
        for key in ("Bg", "Surface", "Ink", "InkFaint", "Primary", "Edge", "Green", "Amber", "Rose"):
            assert f'x:Key="{key}"' not in theme, f"{key} is defined in Theme.xaml instead of the tokens"

    def test_a_token_change_reaches_both_the_app_and_the_site(self, tmp_path):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_tokens", self.ROOT / "tools" / "build_tokens.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)

        data = json.loads((self.ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))
        data["themes"]["dark"]["primary"] = "#123456"
        css = (Path(WEBSITE_DIR) / "styles.css").read_bytes().decode("utf-8").replace("\r\n", "\n")

        assert '<Color x:Key="PrimaryColor">#FF123456</Color>' in build.xaml(data, "dark")
        # A referenced token follows the colour it points at.
        assert '<Color x:Key="PrimarySoftColor">#33123456</Color>' in build.xaml(data, "dark")
        dark_css = build.css(data, css).split('html[data-theme="dark"]')[1]
        assert "--color-primary: #123456;" in dark_css


# ============ the app must fit small screens (roadmap 1.13)

# ===================== every colour is a token, and every token exists (§2)
class TestNoLegacyColourAliases:
    """
    DESIGN_SYSTEM.md §2: the app and the site name colours by token and by
    nothing else. The legacy aliases (Violet, Cyan, Glass*, Accent, WindowBg;
    --violet, --cyan, --grad) all pointed at the right teal, which is why they
    survived so long — the name lied and the pixel didn't.
    """

    XAML_ROOT = Path(DESKTOP_DIR)

    def _xaml_files(self):
        return [
            path for path in self.XAML_ROOT.rglob("*.xaml")
            if "obj" not in path.parts and "bin" not in path.parts
        ]

    def test_the_legacy_names_are_gone_from_the_app(self):
        banned = ("Violet", "VioletBright", "Cyan", "Glass", "GlassStrong",
                  "GlassFill", "WindowBg")
        for path in self._xaml_files():
            source = path.read_text(encoding="utf-8")
            for name in banned:
                assert f'x:Key="{name}"' not in source, f"{path.name} still defines {name}"
                assert f"{{StaticResource {name}}}" not in source, (
                    f"{path.name} still uses {name}"
                )

    def test_the_legacy_names_are_gone_from_the_site(self):
        css = (Path(WEBSITE_DIR) / "styles.css").read_text(encoding="utf-8")
        for name in ("--violet", "--violet-bright", "--cyan", "--grad",
                     "--glass", "--glass-strong"):
            assert f"{name}:" not in css, f"styles.css still defines {name}"
        for page in ("index.html", "legal.html", "success.html", "support.html",
                     "changelog.html", "checkout.js"):
            source = (Path(WEBSITE_DIR) / page).read_text(encoding="utf-8")
            for name in ("--violet", "--cyan", "--grad", "--glass"):
                assert f"var({name})" not in source, f"{page} still uses {name}"

    def test_every_static_resource_key_is_defined(self):
        """
        Deleting an alias that something still referenced would not fail the
        build — an unresolved StaticResource throws when the XAML loads, which
        is to say when the customer opens that screen. Resolve them here
        instead, where it costs a millisecond.
        """
        defined = set()
        for path in self._xaml_files():
            defined |= set(re.findall(r'x:Key="([^"]+)"',
                                      path.read_text(encoding="utf-8")))

        missing = {}
        for path in self._xaml_files():
            used = re.findall(r"\{StaticResource\s+([^}\s]+)\}",
                              path.read_text(encoding="utf-8"))
            for key in used:
                if key not in defined:
                    missing.setdefault(key, set()).add(path.name)

        assert not missing, "XAML references resources nothing defines: " + ", ".join(
            f"{key} (in {', '.join(sorted(files))})" for key, files in sorted(missing.items())
        )


class TestContrastAndTokensA3:
    """
    UI-SPEC.md A3 (#147, DESIGN_SYSTEM.md §2): text-faint and the light-theme
    ok/warn/danger values were measured below WCAG 2.1's 4.5:1 normal-text
    threshold. This computes the ratios straight from design/tokens.json --
    the single source of truth -- for every pair in DESIGN_SYSTEM.md's
    "Contrast" table, in both themes.

    Proven to fail first: run against the pre-fix values (text-faint dark
    #7E7B73 / light #8A867E; ok light #2F7D4A; warn light #9A6B1F; danger
    light #B33A4A) and text-faint on surface measures 4.07:1 (dark) / 3.27:1
    (light) -- both below 4.5, matching the doc's own "current" column -- and
    the light ok/warn pairs also fail. Restoring the pre-fix hex values below
    and rerunning reproduces that failure; the fixed values in tokens.json
    pass every pair.
    """

    ROOT = Path(DESKTOP_DIR).parent
    TOKENS = ROOT / "design" / "tokens.json"

    PRE_FIX_TEXT_FAINT = {"dark": "#7E7B73", "light": "#8A867E"}
    PRE_FIX_STATUS_LIGHT = {"ok": "#2F7D4A", "warn": "#9A6B1F", "danger": "#B33A4A"}

    # Every pair DESIGN_SYSTEM.md §2's "Contrast" table measures.
    PAIRS = [
        ("text", "bg"),
        ("text-muted", "bg"),
        ("text-faint", "surface"),
        ("primary", "bg"),
        ("primary-ink", "primary"),
        ("warn", "bg"),
        ("ok", "bg"),
        ("danger", "bg"),
    ]

    THRESHOLD = 4.5

    @staticmethod
    def _hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

    @classmethod
    def _resolve(cls, theme: dict, name: str, seen: tuple = ()) -> tuple[int, int, int, float]:
        """A token as (r, g, b, alpha), following {"ref", "alpha"} references --
        the same resolution rule tools/build_tokens.py uses."""
        assert name not in seen, f"circular token reference: {seen + (name,)}"
        value = theme[name]
        if isinstance(value, str):
            r, g, b = cls._hex_to_rgb(value)
            return r, g, b, 1.0
        r, g, b, _ = cls._resolve(theme, value["ref"], seen + (name,))
        return r, g, b, float(value["alpha"])

    @staticmethod
    def _composite(fg: tuple[int, int, int, float], bg: tuple[int, int, int, float]) -> tuple[int, int, int]:
        """Alpha-composite fg over bg (both already resolved), for tokens defined as a ref+alpha."""
        fr, fg_, fb, fa = fg
        br, bgc, bb, _ba = bg
        return (
            round(fr * fa + br * (1 - fa)),
            round(fg_ * fa + bgc * (1 - fa)),
            round(fb * fa + bb * (1 - fa)),
        )

    @staticmethod
    def _luminance(rgb: tuple[int, int, int]) -> float:
        def lin(c: int) -> float:
            c = c / 255
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = rgb
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

    @classmethod
    def _contrast(cls, rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
        l1, l2 = cls._luminance(rgb1), cls._luminance(rgb2)
        lighter, darker = max(l1, l2), min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    def _ratio(self, theme: dict, fg_name: str, bg_name: str) -> float:
        fg = self._resolve(theme, fg_name)
        bg = self._resolve(theme, bg_name)
        fg_rgb = self._composite(fg, bg) if fg[3] < 1.0 else fg[:3]
        bg_rgb = bg[:3]
        return self._contrast(fg_rgb, bg_rgb)

    def _themes(self) -> dict:
        return json.loads(self.TOKENS.read_text(encoding="utf-8"))["themes"]

    @pytest.mark.parametrize("theme_name", ["dark", "light"])
    def test_every_section_2_pair_meets_wcag_normal_text(self, theme_name):
        themes = self._themes()
        theme = themes[theme_name]
        failures = []
        for fg_name, bg_name in self.PAIRS:
            ratio = self._ratio(theme, fg_name, bg_name)
            if ratio < self.THRESHOLD:
                failures.append(f"{fg_name} on {bg_name} ({theme_name}): {ratio:.2f}:1")
        assert not failures, (
            "tokens.json pairs fail WCAG 2.1's 4.5:1 normal-text threshold: "
            + "; ".join(failures)
        )

    @pytest.mark.parametrize("theme_name", ["dark", "light"])
    def test_pre_fix_values_would_have_failed(self, theme_name):
        """Confirms this test is actually load-bearing: swap in the exact
        pre-fix hex values DESIGN_SYSTEM.md's "current" column measured, and
        the same computation must fail below 4.5:1."""
        themes = self._themes()
        theme = dict(themes[theme_name])
        theme["text-faint"] = self.PRE_FIX_TEXT_FAINT[theme_name]
        if theme_name == "light":
            theme.update(self.PRE_FIX_STATUS_LIGHT)

        ratio = self._ratio(theme, "text-faint", "surface")
        assert ratio < self.THRESHOLD, (
            f"expected the pre-fix text-faint/surface ratio to fail below 4.5:1, got {ratio:.2f}:1 "
            f"-- this test would no longer prove the fix does anything")

        if theme_name == "light":
            for status in ("ok", "warn"):
                ratio = self._ratio(theme, status, "bg")
                assert ratio < self.THRESHOLD, (
                    f"expected the pre-fix light {status}/bg ratio to fail below 4.5:1, got {ratio:.2f}:1")


class TestNoHardcodedColoursA3:
    """
    UI-SPEC.md A3 (#147, DESIGN_SYSTEM.md §2 "No hard-coded colours in
    views"): every colour in the restyled files must come from a
    design/tokens.json-generated resource, referenced by name -- never a
    literal #RRGGBB/#AARRGGBB in the markup itself.

    Proven to fail first: this test fails against the pre-A3 Theme.xaml
    (Card's DropShadowEffect Color="#FF000000", BtnDanger's
    Background="#22FF6B8B"/BorderBrush="#55FF6B8B", the scrollbar thumb's
    Background="#30FFFFFF") and the pre-A3 MainWindow.xaml (four scrim
    Background="#F2121110"/"#B3121110"/"#F7121110" occurrences).
    """

    ROOT = Path(DESKTOP_DIR).parent
    HEX = re.compile(r'#[0-9A-Fa-f]{6,8}\b')

    FILES = (
        [Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"]
        + sorted((Path(DESKTOP_DIR) / "Views").glob("*.xaml"))
        + [Path(DESKTOP_DIR) / "MainWindow.xaml"]
    )

    def test_no_hex_colour_literal_remains(self):
        offenders = []
        for path in self.FILES:
            text = path.read_text(encoding="utf-8")
            for match in self.HEX.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(self.ROOT)}:{line_no}: {match.group(0)}")
        assert not offenders, (
            "hard-coded hex colour literal(s) found -- reference a Tokens.xaml-generated "
            "brush resource instead:\n" + "\n".join(offenders)
        )

    def test_the_files_list_actually_covers_something(self):
        """A regex that silently matched zero files would pass for the wrong
        reason -- confirm the scan really walks a non-trivial set of XAML."""
        assert len(self.FILES) >= 5, "expected Theme.xaml, MainWindow.xaml and several Views/*.xaml"

    # ------------------------------------------------------------------ C#
    #
    # F21 (#236): the markup was the only thing checked, so a colour could
    # still be built in code and escape the tokens entirely -- and two were.
    # The tray's countdown icon was drawn in a literal teal and near-black
    # (Color.FromArgb(0xFF, 0x3A, 0xA8, 0x92) / (0xFF, 0x0E, 0x14, 0x12)) and
    # the heatmap ramp fell back to Color.FromRgb(0x18, 0x20, 0x1E) /
    # (0x3A, 0xA8, 0x92). All four are the dark theme's colours frozen into
    # code: in the light theme the tray icon stayed dark-theme teal on a
    # near-black disc. This test fails against each of them.

    CSHARP_FILES = tuple(
        path for path in Path(DESKTOP_DIR).rglob("*.cs")
        if "obj" not in path.parts and "bin" not in path.parts
    )

    #: A colour built from literals, rather than read from a token.
    LITERAL_COLOUR = re.compile(
        r"From(?:A?)[Rr]gb\(\s*(?:0[xX][0-9A-Fa-f]+|\d+)\s*(?:,\s*(?:0[xX][0-9A-Fa-f]+|\d+)\s*)+\)"
    )
    #: A colour taken from the framework's palette instead of the tokens.
    NAMED_COLOUR = re.compile(r"\bBrushes\.\w+|new SolidColorBrush\(Colors\.\w+")
    #: A hex literal in a string, e.g. ColorConverter.ConvertFromString("#3AA892").
    HEX_IN_CODE = re.compile(r'"#[0-9A-Fa-f]{6,8}"')

    def test_no_colour_is_built_from_literals_in_code(self):
        offenders = []
        for path in self.CSHARP_FILES:
            text = path.read_text(encoding="utf-8")
            for pattern in (self.LITERAL_COLOUR, self.NAMED_COLOUR, self.HEX_IN_CODE):
                for match in pattern.finditer(text):
                    line_no = text.count("\n", 0, match.start()) + 1
                    offenders.append(
                        f"{path.relative_to(self.ROOT)}:{line_no}: {match.group(0)}")
        assert not offenders, (
            "colours built in C# do not follow the theme -- read the token with "
            "ThemeService.TryColour instead:\n" + "\n".join(offenders))

    def test_the_csharp_scan_covers_the_app(self):
        assert len(self.CSHARP_FILES) >= 20, \
            f"expected the whole app to be scanned, got {len(self.CSHARP_FILES)} files"

    def test_the_patterns_catch_the_colours_that_were_there(self):
        """The four literals F21 removed, verbatim -- the regexes must match them."""
        assert self.LITERAL_COLOUR.search(
            "new System.Drawing.SolidBrush(System.Drawing.Color.FromArgb(0xFF, 0x3A, 0xA8, 0x92))")
        assert self.LITERAL_COLOUR.search("MediaColor.FromRgb(0x18, 0x20, 0x1E)")
        assert self.NAMED_COLOUR.search("new SolidColorBrush(Colors.HotPink)")
        assert self.HEX_IN_CODE.search('ColorConverter.ConvertFromString("#3AA892")')
        # And must not flag the ramp's computed mix, which is the correct shape.
        assert not self.LITERAL_COLOUR.search(
            "MediaColor.FromRgb((byte)Math.Round(from.R + (to.R - from.R) * mix), g, b)")


class TestCornerRadiusNormalisedA2:
    """
    UI-SPEC.md A2 (#147, DESIGN_SYSTEM.md §4): every CornerRadius in the app
    must be one of the four legal values -- 6 (small chips/tags), 10
    (buttons/inputs/toggles/interactive rows), 14 (cards/dialogs/surfaces),
    or "fully round" -- and every one of them must be a StaticResource
    reference to Theme.xaml's four named resources (RadiusChip/RadiusControl/
    RadiusCard), not a bare number repeated at each call site. Fully round
    elements use inf:Pill.IsRound instead of a radius (TestPillsAreComputed).

    Proven to fail first: the FIXTURE strings below are lifted verbatim from
    the pre-A2 XAML (CornerRadius="11" on NavButton, CornerRadius="7" on the
    FirstRun app-icon badge, <Setter Property="CornerRadius" Value="12"/> on
    RowCard) -- none of them are legal literals and none reference a
    resource, so test_fixture_of_known_pre_fix_values_is_rejected below
    fails against them, and passes only once every real call site is
    converted (test_every_cornerradius_is_a_named_resource).
    """

    ROOT = Path(DESKTOP_DIR).parent
    FILES = (
        [Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"]
        + sorted((Path(DESKTOP_DIR) / "Views").glob("*.xaml"))
        + [Path(DESKTOP_DIR) / "MainWindow.xaml"]
    )

    LEGAL_RESOURCE_KEYS = {"RadiusChip", "RadiusControl", "RadiusCard"}

    # Matches both CornerRadius="X" (inline) and
    # <Setter Property="CornerRadius" Value="X"/> (style setters).
    INLINE = re.compile(r'CornerRadius="([^"]*)"')
    SETTER = re.compile(r'Property="CornerRadius"\s+Value="([^"]*)"')
    RESOURCE_REF = re.compile(r'^\{StaticResource (\w+)\}$')

    # Verbatim pre-A2 fragments (Theme.xaml/MainWindow.xaml as they existed
    # before this change): a bare literal on a Border, and a bare literal on
    # a style Setter. Neither is a StaticResource reference.
    PRE_FIX_FIXTURE = '\n'.join([
        '<Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="11"',
        '<Border CornerRadius="7" Background="{StaticResource PrimarySoft}"',
        '<Setter Property="CornerRadius" Value="12"/>',
    ])

    def _offenders(self, text: str) -> list[str]:
        bad = []
        for m in self.INLINE.finditer(text):
            bad.append(m.group(1))
        for m in self.SETTER.finditer(text):
            bad.append(m.group(1))
        offenders = []
        for val in bad:
            rm = self.RESOURCE_REF.match(val)
            if not rm or rm.group(1) not in self.LEGAL_RESOURCE_KEYS:
                offenders.append(val)
        return offenders

    def test_fixture_of_known_pre_fix_values_is_rejected(self):
        """This test's own checker must actually catch the bug: run it
        against verbatim pre-A2 fragments and confirm every one is flagged."""
        offenders = self._offenders(self.PRE_FIX_FIXTURE)
        assert len(offenders) == 3, (
            f"expected the checker to flag all 3 pre-fix fragments, flagged {len(offenders)}: {offenders}"
        )



    def test_the_files_list_actually_covers_something(self):
        assert len(self.FILES) >= 5, "expected Theme.xaml, MainWindow.xaml and several Views/*.xaml"


class TestPillsAreComputed:
    """
    A2 first expressed "fully round" as CornerRadius="9999", on the belief
    that WPF clips corner geometry to half the smaller side. It doesn't: CSS
    clamps an oversized border-radius, but WPF scales the curves, so the
    renders showed the tier badge as an ellipse and the 5 px scrollbar thumb
    as a spike. Pills now set inf:Pill.IsRound, which keeps the radius at half
    the element's smaller side as it resizes (Infrastructure/Pill.cs).
    """

    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"
    PILL = Path(DESKTOP_DIR) / "Infrastructure" / "Pill.cs"
    FILES = (
        [Path(DESKTOP_DIR) / "Styles" / "Theme.xaml", Path(DESKTOP_DIR) / "MainWindow.xaml"]
        + sorted((Path(DESKTOP_DIR) / "Views").glob("*.xaml"))
    )
    # Anything at or beyond this is "make it round" by brute force, which WPF
    # renders as an ellipse on any element that isn't square.
    BRUTE_FORCE = 100

    def test_no_corner_radius_is_large_enough_to_draw_an_ellipse(self):
        offenders = []
        for path in self.FILES:
            text = path.read_text(encoding="utf-8")
            values = re.findall(r'CornerRadius="([\d.,\s]+)"', text)
            values += re.findall(r'<CornerRadius x:Key="\w+">([\d.,\s]+)</CornerRadius>', text)
            values += re.findall(r'Property="CornerRadius"\s+Value="([\d.,\s]+)"', text)
            for v in values:
                if any(float(part) >= self.BRUTE_FORCE for part in v.split(",") if part.strip()):
                    offenders.append(f"{path.name}: {v}")
        assert not offenders, (
            "a huge CornerRadius draws an ellipse in WPF, not a pill; use "
            "inf:Pill.IsRound=\"True\":\n  " + "\n  ".join(offenders))

    def test_the_round_elements_use_the_pill_behaviour(self):
        theme = self.THEME.read_text(encoding="utf-8")
        chip = re.search(r'<Style x:Key="Chip" TargetType="Border">.*?</Style>', theme, re.S)
        assert chip and 'Property="inf:Pill.IsRound" Value="True"' in chip.group(0), (
            "the Chip style (the tier badge) must be fully round via inf:Pill.IsRound")
        # The nav bar, toggle track, scrollbar thumb, and both progress bar
        # borders, plus the Chip setter above.
        assert theme.count('inf:Pill.IsRound="True"') >= 5, (
            "expected the nav bar, toggle track, scrollbar thumb and progress "
            "bar borders to set inf:Pill.IsRound")

    def test_the_radius_is_half_the_smaller_side(self):
        source = self.PILL.read_text(encoding="utf-8")
        assert "Math.Min(width, height)" in source and "smaller / 2" in source, (
            "Pill.RadiusFor must use half the SMALLER side; half the larger side "
            "is exactly the ellipse this replaced")
        assert "SizeChanged" in source, "the radius must follow the element as it resizes"


# ================================= the light theme and the keyboard (F21, #236)

class TestLightThemeSwitchF21:
    """
    F21 / DESIGN_SYSTEM.md §12 "Theme": the app draws in dark, light, or
    whatever Windows is set to, and switches while it runs.

    Proven to fail first: before F21, App.xaml merged only Theme.xaml,
    Theme.xaml and ShieldGlyphs.xaml each merged Tokens.xaml themselves, every
    colour reference in every view was a StaticResource, and there was no
    ThemeService at all -- each assertion below fails against that tree.

    The arrangement is load-bearing and not obvious, which is why it is pinned
    here: WPF resolves a merged dictionary's keys nearest-last, so a *second*
    Tokens merge anywhere would shadow the one ThemeService swaps, and the app
    would silently stay dark for ever.
    """

    DESKTOP = Path(DESKTOP_DIR)
    SERVICE = Path(DESKTOP_DIR) / "Services" / "ThemeService.cs"

    def read(self, *parts) -> str:
        return self.DESKTOP.joinpath(*parts).read_text(encoding="utf-8")

    def _xaml_files(self):
        return [p for p in self.DESKTOP.rglob("*.xaml")
                if "obj" not in p.parts and "bin" not in p.parts]

    def test_app_merges_the_tokens_first_and_on_their_own(self):
        app = self.read("App.xaml")
        order = [app.find('Source="Styles/Tokens.xaml"'),
                 app.find('Source="Styles/ShieldGlyphs.xaml"'),
                 app.find('Source="Styles/Theme.xaml"')]
        assert all(position > 0 for position in order), \
            "App.xaml must merge Tokens.xaml, ShieldGlyphs.xaml and Theme.xaml itself"
        assert order == sorted(order), \
            "the tokens must be merged before the glyphs and the styles that reference them"

    def test_nothing_else_merges_a_tokens_dictionary(self):
        offenders = []
        for path in self._xaml_files():
            if path.name == "App.xaml":
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r'<ResourceDictionary Source="[^"]*Tokens(\.Light)?\.xaml"', text):
                offenders.append(path.name)
        assert not offenders, (
            "a second Tokens merge shadows the dictionary ThemeService swaps, pinning "
            "the app to one theme: " + ", ".join(offenders))

    def test_every_colour_reference_is_dynamic(self):
        """
        A StaticResource brush is resolved once, when the XAML loads. Swapping
        the dictionary under it changes nothing, so every colour token is
        referenced dynamically -- with one documented exception.
        """
        names = json.loads((Path(DESKTOP_DIR).parent / "design" / "tokens.json")
                           .read_text(encoding="utf-8"))["app_names"]
        keys = set(names.values()) | {value + "Color" for value in names.values()}

        # The Card style's drop shadow is a Freezable inside a sealed Style
        # setter, which cannot carry a DynamicResource. It is black in both
        # themes (design/tokens.json "shadow"), so it never needs to change.
        allowed = {("Theme.xaml", "ShadowColor")}

        offenders = []
        for path in self._xaml_files():
            if path.name.startswith("Tokens"):
                continue
            text = path.read_text(encoding="utf-8")
            for key in re.findall(r"\{StaticResource\s+([^}\s]+)\}", text):
                if key in keys and (path.name, key) not in allowed:
                    offenders.append(f"{path.name}: {key}")
        assert not offenders, (
            "colour tokens referenced with StaticResource will not follow a theme "
            "change: " + ", ".join(sorted(set(offenders))))

    def test_the_shield_glyphs_are_referenced_dynamically_too(self):
        """
        A DynamicResource inside a Freezable resolves once and never again, so
        ThemeService reloads the glyph dictionary instead. Anything holding the
        old DrawingImage by StaticResource would keep the old colours.
        """
        for path in self._xaml_files():
            text = path.read_text(encoding="utf-8")
            for key in ("ShieldGlyphSoft", "ShieldGlyphFirm", "ShieldGlyphSealed"):
                assert f"{{StaticResource {key}}}" not in text, \
                    f"{path.name} holds {key} statically; it will not be recoloured"

    def test_the_service_swaps_the_dictionary_and_follows_windows(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        assert "Tokens.Light.xaml" in source and "Tokens.xaml" in source, \
            "ThemeService must swap between the two generated token dictionaries"
        assert "MergedDictionaries" in source, "the swap happens in App.Resources"
        assert "AppsUseLightTheme" in source, \
            "System must follow Windows' own app theme"
        assert "SystemEvents.UserPreferenceChanged" in source, \
            "a Windows theme change must be picked up without a restart"
        assert "Registry.CurrentUser.OpenSubKey" in source, "HKCU, read-only"
        for write in ("SetValue", "CreateSubKey", "DeleteValue", "LocalMachine"):
            assert write not in source, \
                f"the Windows theme is read-only; ThemeService must not call {write}"

    def test_the_glyphs_are_reloaded_when_the_theme_changes(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        swap = source.split("private static void Swap(")[1].split("\n    private ")[0]
        assert "ShieldGlyphs" in swap, \
            "the swap must reload ShieldGlyphs.xaml -- its brushes are inside Freezables"
        assert "RefreshConverterBindings" in swap, \
            "converters that look colours up themselves must be re-run after the swap"

    def test_the_converters_that_read_colours_reread_them(self):
        converters = self.read("Infrastructure", "Converters.cs")
        for converter in ("HeatStepToBrushConverter", "ResourceKeyToBrushConverter",
                          "ShieldLevelToGlyphConverter"):
            assert converter in converters
        assert "TryFindResource" in converters or "TryColour" in converters, \
            "these converters must look the resource up each time, not cache it"

    def test_the_setting_defaults_to_following_windows_and_persists(self):
        settings = self.read("Models", "AppSettings.cs")
        assert "public AppTheme Theme { get; set; } = AppTheme.System;" in settings, \
            "the stored default must be System, so an upgrade keeps following Windows"
        theme = self.read("Models", "AppTheme.cs")
        assert "System = 0" in theme, \
            "System must serialise as 0 or every settings file written before F21 reads as Dark"

        view_model = self.read("ViewModels", "SettingsViewModel.cs")
        appearance = view_model.split("public AppTheme Theme")[1].split("\n    /// <summary>")[0]
        assert "ThemeService.Apply(value)" in appearance, "the choice applies immediately"
        assert "_main.SaveSettings()" in appearance, "and is saved"

    def test_settings_offers_the_three_choices_with_ids(self):
        xaml = self.read("Views", "SettingsView.xaml")
        assert "APPEARANCE" in xaml
        for automation_id, name in (("ThemeSystemRadio", "System theme"),
                                    ("ThemeDarkRadio", "Dark theme"),
                                    ("ThemeLightRadio", "Light theme")):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml
            assert f'AutomationProperties.Name="{name}"' in xaml

    def test_the_title_bar_and_the_tray_icon_follow_the_theme(self):
        window = self.read("MainWindow.xaml.cs")
        assert "ThemeService.IsLight ? 0 : 1" in window, \
            "DWM's dark title bar must be off in the light theme"
        assert "ThemeService.Changed += OnThemeChanged" in window, \
            "the window must redraw what it painted in code when the theme changes"
        countdown = window.split("private static System.Drawing.Icon? CountdownIcon(")[1]
        assert "ThemeService.TryColour(\"PrimaryColor\"" in countdown, \
            "the tray countdown icon must be drawn in the current theme's primary"

# ============================== the Basalt stone look (light marble, dark basalt)

class TestStoneLook:
    """
    DESIGN_SYSTEM.md §2 and §4 "Stone": the neutrals read as cool marble in
    light and basalt charcoal in dark, the page ground carries a fine grain,
    and one row of basalt columns stands on the hero's bottom edge. The old
    neutrals were warm beige and brown-black, which read as paper, not rock.
    """

    ROOT = Path(DESKTOP_DIR).parent
    CSS = Path(WEBSITE_DIR) / "styles.css"

    def _css(self) -> str:
        return self.CSS.read_text(encoding="utf-8")

    def _rule(self, selector: str) -> str:
        css = self._css()
        match = re.search(r"^" + re.escape(selector) + r" \{", css, re.M)
        assert match, f"no top-level rule for {selector}"
        return css[match.start():css.index("}", match.start())]

    @pytest.mark.parametrize("theme_name", ("light", "dark"))
    def test_the_neutrals_are_cool_stone_not_warm_sand(self, theme_name):
        """
        Marble is near-neutral white and basalt a blue-grey black; the old
        beige (#E6E4DF, red 7 above blue) and brown-black (#121110) lean red.
        Light may keep a trace of warmth (veined marble); dark grounds may not.
        Text is left out: it is ink on the stone, not the stone.
        """
        theme = json.loads((self.ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))["themes"][theme_name]
        for token in ("bg", "bg-soft", "surface", "surface-2"):
            value = theme[token].lstrip("#")
            red, blue = int(value[0:2], 16), int(value[4:6], 16)
            limit = 6 if theme_name == "light" else 0
            assert red - blue <= limit, f"{theme_name} {token} #{value} leans warm, not stone"


    def test_the_grain_is_on_the_page_ground_only(self):
        """Text sits on solid surfaces above the grain, so contrast is unchanged."""
        assert "var(--texture-grain)" in self._rule("body")
        css = self._css()
        for block in css.split("}"):
            if "var(--texture-grain)" in block:
                assert "--color-surface" not in block, (
                    "the grain belongs on the page ground, never on a card or text box")

    def test_basalt_columns_stand_inside_the_hero_padding(self):
        hero = self._rule(".hero")
        assert "position: relative" in hero
        assert "var(--space-12)" in hero, "the columns rely on the hero's 48px bottom padding"
        columns = self._rule(".hero::after")
        assert "height: 40px" in columns, "taller than the 48px padding, they would reach the text"
        assert "bottom: 0" in columns
        assert "pointer-events: none" in columns
        assert "background-color: var(--color-text)" in columns, "the motif follows the theme"
        assert "mask:" in columns and "-webkit-mask:" in columns
