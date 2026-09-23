"""
Runs FlowShield's real C# model code from Python (1.0.10).

Tier 1 has always mirrored C# rules in Python and pinned the C# by reading its
source, because there is no dotnet test project (CLAUDE.md). That proves the
rule is right and that the code mentions it; it can't prove the C# computes
it. For rules where .NET itself decides the answer -- time zones and daylight
saving above all -- ModelProbe compiles DesktopApp/Models as it is and answers
one JSON request per run.
"""
from __future__ import annotations

import functools
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = ROOT / "automation" / "csharp" / "ModelProbe"
PROBE_EXE = PROBE_DIR / "bin" / "Release" / "net8.0-windows" / "ModelProbe.exe"


class ProbeError(RuntimeError):
    """The probe didn't build, or a command failed inside it."""


@functools.lru_cache(maxsize=1)
def build() -> Path:
    """Builds the probe once per test session."""
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise ProbeError("ModelProbe needs the .NET 8 SDK, and dotnet is not on PATH")
    result = subprocess.run(
        [dotnet, "build", str(PROBE_DIR / "ModelProbe.csproj"),
         "-c", "Release", "-nologo", "-v", "q"],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise ProbeError(
            "ModelProbe did not build. DesktopApp/Models must compile without "
            "views, view models or services:\n"
            + result.stdout[-4000:] + result.stderr[-2000:]
        )
    return PROBE_EXE


def probe(request: dict) -> dict:
    """Sends one request to the real C# and returns its JSON answer."""
    exe = build()
    result = subprocess.run(
        [str(exe)], input=json.dumps(request),
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise ProbeError(f"ModelProbe failed on {request.get('cmd')!r}:\n{result.stderr[-3000:]}")
    return json.loads(result.stdout)
