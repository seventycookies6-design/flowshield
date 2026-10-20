# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 3:  helpers."""

from __future__ import annotations
from pathlib import Path
import pytest



# ===================================================== terms acceptance (legal)

def current_terms_version() -> str:
    """LegalTerms.Version as the app has it, so a terms bump needs no test edit."""
    source = (Path(__file__).resolve().parents[3] / "DesktopApp" / "Models" / "LegalTerms.cs")
    return source.read_text(encoding="utf-8").split('public const string Version = "')[1].split('"')[0]


# ======================================================= one instance (1.3)

def launch_again(*extra: str) -> int:
    """Start a second Basalt without closing the first; returns its exit code."""
    from pathlib import Path

    from config import APP_EXE
    from core.settings_guard import run_app_process

    proc = run_app_process([str(APP_EXE), *extra], cwd=str(Path(APP_EXE).parent), timeout=30)
    return proc.returncode


def flowshield_pids() -> list[int]:
    import psutil

    return [p.pid for p in psutil.process_iter(["name"])
            if (p.info["name"] or "").lower() == "flowshield.exe"]


# =================================================== flowshield:// links (1.4)

# Shaped like a real key; never activated, so it doesn't need to exist.
LINK_KEY = "FS-ABCD-EFGH-JKMN-PQR5"
LINK = f"flowshield://activate?key={LINK_KEY}"
