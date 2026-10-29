# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5:  helpers."""

from __future__ import annotations
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR


NODE = r"C:\Program Files\nodejs\node.exe"
NODE_EXE = NODE if Path(NODE).exists() else "node"


def customer_copy_surface_paths():
    """Files that can carry visible seat-limit copy for customers."""
    website = Path(WEBSITE_DIR)
    desktop = Path(DESKTOP_DIR)
    server = Path(SERVER_DIR)
    candidates = [
        *website.rglob("*.html"), *desktop.rglob("*.xaml"), *desktop.rglob("*.cs"),
        *server.rglob("*.js"), *server.rglob("*.html"),
    ]
    return sorted(
        (path for path in candidates if "node_modules" not in path.parts),
        key=lambda path: str(path).lower(),
    )


# ====================== the site only sells implemented features

class _PricingFeatureParser(HTMLParser):
    """Collect checked features from every plan in the pricing section."""

    def __init__(self):
        super().__init__()
        self.in_pricing = False
        self.plan_stack = []
        self.checked_features = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "section" and attributes.get("id") == "pricing":
            self.in_pricing = True
        elif tag == "ul" and self.in_pricing:
            self.plan_stack.append(attributes.get("data-plan", "unnamed pricing list"))
        elif tag == "li" and self.plan_stack:
            classes = set(attributes.get("class", "").split())
            if "on" in classes:
                self.checked_features.append(
                    (self.plan_stack[-1], attributes.get("data-feature")))

    def handle_endtag(self, tag):
        if tag == "ul" and self.plan_stack:
            self.plan_stack.pop()
        elif tag == "section" and self.in_pricing:
            self.in_pricing = False


# ============ a lost database must not revoke anyone's subscription

def _db_admin(*args) -> str:
    result = subprocess.run(
        [NODE_EXE, str(Path(SERVER_DIR).parent / "tools" / "db_admin.js"), *args],
        cwd=str(Path(SERVER_DIR).parent), capture_output=True, text=True, timeout=60,
    )
    return (result.stdout or "").strip().splitlines()[-1] if result.stdout.strip() else ""


# ============ footer links point at pages that exist (roadmap 6.6)

class _FooterLinkParser(HTMLParser):
    """Collect href values from every <a> inside <footer>."""

    def __init__(self):
        super().__init__()
        self.in_footer = False
        self.footer_links = []

    def handle_starttag(self, tag, attrs):
        if tag == "footer":
            self.in_footer = True
        elif tag == "a" and self.in_footer:
            href = dict(attrs).get("href")
            if href:
                self.footer_links.append(href)

    def handle_endtag(self, tag):
        if tag == "footer":
            self.in_footer = False


# ===================================== bug hunt, 22 September 2026 (#194-#199)

DESKTOP = Path(DESKTOP_DIR)


#: Where the offscreen theme probe lives, and where it is run from.
THEME_PROBE = Path(DESKTOP_DIR).parent / "automation" / "probe" / "ThemeProbe"


class _FakeWinreg:
    """Just enough of winreg for the guard: one dict of (subkey, name) -> (value, type)."""

    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1
    KEY_SET_VALUE = 2

    def __init__(self):
        self.values = {}

    class _Key:
        def __init__(self, subkey):
            self.subkey = subkey

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def OpenKey(self, root, subkey, *args):
        if not any(k == subkey for k, _ in self.values):
            raise FileNotFoundError(subkey)
        return self._Key(subkey)

    def CreateKeyEx(self, root, subkey, *args, **kwargs):
        return self._Key(subkey)

    def QueryValueEx(self, key, name):
        if (key.subkey, name) not in self.values:
            raise FileNotFoundError(name)
        return self.values[(key.subkey, name)]

    def SetValueEx(self, key, name, reserved, value_type, value):
        self.values[(key.subkey, name)] = (value, value_type)

    def DeleteValue(self, key, name):
        if self.values.pop((key.subkey, name), None) is None:
            raise FileNotFoundError(name)
