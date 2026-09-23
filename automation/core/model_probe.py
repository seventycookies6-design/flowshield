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

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = ROOT / "automation" / "csharp" / "ModelProbe"
PROBE_EXE = PROBE_DIR / "bin" / "Release" / "net8.0-windows" / "ModelProbe.exe"

BUILD_TIMEOUT = 300
RUN_TIMEOUT = 60


class ProbeError(RuntimeError):
    """The probe didn't build, or a command failed inside it."""


# The build's outcome, kept for the session: the exe, or the ProbeError the
# build raised. functools.lru_cache would remember only a success, so a Models
# folder that doesn't compile would be rebuilt (up to BUILD_TIMEOUT each time)
# by every test that probes.
_build_outcome: Path | ProbeError | None = None


def _tail(text: str | bytes | None, limit: int) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return text[-limit:]


def _run(command: list[str], what: str, *, timeout: int,
         stdin: str | None = None) -> subprocess.CompletedProcess:
    """subprocess.run, with a hang reported as a ProbeError that says what hung."""
    try:
        return subprocess.run(command, input=stdin, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(
            f"{what} did not finish within {timeout}s:\n"
            + _tail(exc.stdout, 4000) + _tail(exc.stderr, 2000)
        ) from exc


def _build() -> Path:
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise ProbeError("ModelProbe needs the .NET 8 SDK, and dotnet is not on PATH")
    result = _run(
        [dotnet, "build", str(PROBE_DIR / "ModelProbe.csproj"), "-c", "Release", "-nologo", "-v", "q"],
        "dotnet build of ModelProbe", timeout=BUILD_TIMEOUT,
    )
    if result.returncode != 0:
        raise ProbeError(
            "ModelProbe did not build. DesktopApp/Models must compile without "
            "views, view models or services:\n"
            + result.stdout[-4000:] + result.stderr[-2000:]
        )
    return PROBE_EXE


def build() -> Path:
    """Builds the probe once per test session, and remembers a failure too."""
    global _build_outcome
    if _build_outcome is None:
        try:
            _build_outcome = _build()
        except ProbeError as exc:
            _build_outcome = exc
    if isinstance(_build_outcome, ProbeError):
        raise _build_outcome
    return _build_outcome


def probe(request: dict) -> dict:
    """Sends one request to the real C# and returns its JSON answer."""
    exe = build()
    what = f"ModelProbe {request.get('cmd')!r}"
    result = _run([str(exe)], what, timeout=RUN_TIMEOUT, stdin=json.dumps(request))
    if result.returncode != 0:
        raise ProbeError(f"{what} failed:\n{result.stderr[-3000:]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(
            f"{what} answered something that isn't JSON (a stray Console.WriteLine in Models?):\n"
            + result.stdout[-3000:]
        ) from exc
