"""Tier 5: user-visible promises from the #406 layout update."""

from __future__ import annotations

import re
from pathlib import Path
from config import DESKTOP_DIR


ROOT = Path(DESKTOP_DIR)


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8").replace("\ufeff", "")


class TestCappedPagesAndWheelRouting:
    def test_title_and_page_host_share_the_page_width_cap(self):
        xaml = read("MainWindow.xaml")
        assert re.search(r'<StackPanel\b(?=[^>]*Grid.Row="0")(?=[^>]*MaxWidth="{StaticResource PageMaxWidth}")[^>]*>', xaml)
        assert re.search(r'<Grid\b(?=[^>]*x:Name="PageHost")(?=[^>]*MaxWidth="{StaticResource PageMaxWidth}")[^>]*>', xaml)
        theme = read("Styles", "Theme.xaml")
        match = re.search(r'<sys:Double x:Key="PageMaxWidth">([0-9.]+)</sys:Double>', theme)
        assert match and 1100 <= float(match.group(1)) <= 1600

    def test_wheel_over_an_overlay_does_not_scroll_the_page_under_it(self):
        code = read("MainWindow.xaml.cs")
        handler = code.split("private void OnContentWheel", 1)[1].split("private static ScrollViewer? FirstScrollable", 1)[0]
        assert "ReferenceEquals(e.OriginalSource, ContentArea)" in handler


class TestRadioButtonStyles:
    def test_every_radio_button_has_an_explicit_non_stock_style(self):
        files = [ROOT / "MainWindow.xaml", *sorted((ROOT / "Views").glob("*.xaml"))]
        offenders = []
        for path in files:
            text = path.read_text(encoding="utf-8").replace("\ufeff", "")
            for match in re.finditer(r'<RadioButton\b([^>]*)>', text):
                if not re.search(r'\bStyle="{StaticResource [^}]+}"', match.group(1)):
                    offenders.append(f"{path.name}: {match.group(0)}")
        assert not offenders, "radio buttons falling back to the stock template:\n" + "\n".join(offenders)


class TestSettingsCardsStayStacked:
    def test_every_adaptive_settings_group_is_a_single_column(self):
        xaml = read("Views", "SettingsView.xaml")
        panels = re.findall(r'<inf:AdaptiveColumns\b([^>]*)>', xaml)
        assert panels
        assert all(re.search(r'\bMaxColumns="1"', attrs) for attrs in panels)


class TestEmptyFieldHints:
    def test_empty_field_template_uses_helptext_and_shows_it_when_empty(self):
        theme = read("Styles", "Theme.xaml")
        field = theme.split('<Style x:Key="Field"', 1)[1].split('</Style>', 1)[0]
        assert "AutomationProperties.HelpText" in field
        assert 'Visibility="Collapsed"' in field
        assert re.search(r'<Trigger Property="Text" Value="">.*?Visibility" Value="Visible"', field, re.S)
        for control_id in ("IntentionInput", "JournalInput", "LicenseEmailInput", "FirstRunSearchInput", "LicenseKeyInput"):
            xaml = "\n".join(path.read_text(encoding="utf-8") for path in [ROOT / "MainWindow.xaml", *ROOT.joinpath("Views").glob("*.xaml")])
            element = re.search(r'<TextBox\b(?=[^>]*AutomationProperties.AutomationId="' + control_id + r'")[^>]*>', xaml)
            assert element and re.search(r'AutomationProperties.HelpText="[^"]+"', element.group(0)), control_id


class TestSelectedSettingsRail:
    def test_selected_section_gets_surface_and_primary_indicator_like_main_rail(self):
        theme = read("Styles", "Theme.xaml")
        settings = theme.split('<Style x:Key="SettingsNavLink"', 1)[1].split('</Style>', 1)[0]
        nav = theme.split('<Style x:Key="NavButton"', 1)[1].split('</Style>', 1)[0]
        checked = settings.split('<Trigger Property="IsChecked" Value="True">', 1)[1].split('</Trigger>', 1)[0]
        assert 'TargetName="bd" Property="Background" Value="{DynamicResource Surface2}"' in checked
        assert 'TargetName="bar" Property="Opacity" Value="1"' in checked
        assert '{DynamicResource Primary}' in settings and '{DynamicResource Primary}' in nav
