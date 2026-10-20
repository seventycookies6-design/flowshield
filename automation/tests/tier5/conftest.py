# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5:  fixtures."""

from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from ._helpers import THEME_PROBE



@pytest.fixture(scope="module")
def theme_probe():
    """
    Runs `automation/probe/ThemeProbe` once and hands back its report.

    Module-scoped: it builds and runs the real app's resources, which costs a
    few seconds, and every assertion below reads the same three snapshots.
    """
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        pytest.skip("no .NET SDK on this machine")

    result = subprocess.run(
        [dotnet, "run", "--project", str(THEME_PROBE), "-c", "Release", "-v", "q", "--nologo"],
        cwd=str(Path(DESKTOP_DIR).parent), capture_output=True, text=True, timeout=600)

    assert result.returncode == 0, (
        "the theme probe did not run:\n" + result.stdout[-2000:] + result.stderr[-2000:])

    # The build writes to stdout too; the report is the last JSON line.
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    assert lines, "the probe printed no report:\n" + result.stdout[-2000:]
    return json.loads(lines[-1])

# Preserve the original tier-module lifetime across area modules.
theme_probe = pytest.fixture(scope='package')(theme_probe.__wrapped__)
