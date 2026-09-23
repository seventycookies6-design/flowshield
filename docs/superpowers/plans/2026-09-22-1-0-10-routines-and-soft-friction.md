# 1.0.10 routines and Soft friction — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task is test-first (superpowers:test-driven-development): write the failing test, watch it fail, write the code, watch it pass.

**Goal:** Ship 1.0.10's study templates and scheduled sprints (F6), a Soft shield that uses research-backed friction, a recorded "turned back" count, and a taskbar Jump List — without colliding with Miles's 1.0.9 release.

**Architecture:** Pure rules live in `DesktopApp/Models` (no UI, no timers), and a new tier 1 harness (`automation/csharp/ModelProbe`) compiles those files as they are and runs them from pytest, so date and time-zone logic is tested in .NET rather than in a Python copy. View models and services wire the rules in. Work is split into five pull requests: two built now beside 1.0.9 and merged only once `v1.0.9` is published, and three built on top of it.

**Tech Stack:** .NET 8 WPF (MVVM), C# 12, pytest + pywinauto (tiers 1, 3, 5), GitHub CLI.

**Spec:** `docs/superpowers/specs/2026-09-22-1-0-10-routines-and-soft-friction-design.md` — read it before your task. Where this plan and the spec differ, this plan wins; the differences are listed at the end of this plan.

## Global Constraints

- Never close anything on `AppBlockerService.CriticalProcesses`; no admin rights, services, drivers, hosts or DNS edits.
- Nothing new leaves the PC. No accounts, cloud or telemetry. Settings stay in the DPAPI-encrypted file.
- Soft never closes an app on its own. The only close at Soft is the user pressing **Close ‹app›**, which calls `CloseMainWindow` and never `Kill`.
- Never claim a feature the build lacks, on the site, in the app, or in copy.
- Keep every existing `AutomationId`. New ids go on real controls (buttons, text blocks, check boxes), never on `Border`, `Grid` or `StackPanel` (#134).
- Copy follows `DESIGN_SYSTEM.md` §9: no exclamation marks, no emoji, ASCII only in C# string literals, calm, specific.
- Don't edit text files with PowerShell `Get-Content`/`Set-Content`; use file edit tools.
- Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `DesktopApp/Models/*.cs` must compile without WPF view models, services or views (the probe compiles them alone). The only allowed outside reference is `Services.Log`, which the probe stubs.
- **No merge to `main` before the `v1.0.9` GitHub release exists.**
- One UI test run at a time on this PC. Only the controller or one implementer runs `-m ui` tests at once.
- Fast suite before every push: `python -m pytest automation/tests -m "not ui and not stripe" -q`.

## Review Focus

These inputs are implied by the spec but easy to miss; each has a test in the named task.

1. **A settings file from 1.0.9** (no `Templates`, `Schedules` or `TemplatesSeeded`) loads, seeds the three built-ins once, and a user who deletes all templates doesn't get them back on the next launch. → Task 4.
2. **A long gap** (PC asleep six hours, clock changed, timezone changed) produces **at most one** missed-schedule offer, and only for a start 30 minutes ago or less — never a burst of starts. → Task 8.
3. **Two schedules due at the same minute** start one sprint; the second is skipped because a sprint is running. → Task 8.
4. **An app that refuses to close** (its own "save changes?" prompt): **Close** asks once, never kills, the notice goes away, and it counts as turned back. → Task 6.
5. **Dangling references**: a template whose profile was deleted uses the active profile; a schedule or Jump List entry whose template was deleted does nothing harmful (the schedule is removed on load; the Jump List falls back to Today with a toast). → Tasks 4 and 11.

---

## Overnight runbook (for the controller session)

The controller is the owner's Claude Code session. It dispatches implementers and reviewers per task, and does the git and GitHub work between tasks.

### Before the first task

1. `gh release view v1.0.9 --json tagName,publishedAt` — record the result.
2. Start the release watch in the background (a Bash/PowerShell call with `run_in_background: true`) so a notification arrives when 1.0.9 is published:

   ```powershell
   $deadline = (Get-Date).AddHours(9)
   while ((Get-Date) -lt $deadline) {
     gh release view v1.0.9 --json tagName 2>$null | Out-Null
     if ($LASTEXITCODE -eq 0) { "v1.0.9 is published"; exit 0 }
     Start-Sleep -Seconds 600
   }
   "v1.0.9 not published within 9 hours"; exit 1
   ```

3. Open five issues and assign them to `@me`. Label them `enhancement`:
   - A — "F6 part 1: study templates, schedules and the Schedule page (1.0.10)"
   - B — "Soft friction: a growing wait, Close it, intention and try count (1.0.10)"
   - C — "F6 part 2: scheduled sprints start, templates on Today (1.0.10)"
   - D — "Turned back: record it and show it (1.0.10)"
   - E — "Jump List: start a sprint from the taskbar (1.0.10)"

   Each issue body links the spec and names the tasks in this plan.
4. Comment on #38 (Miles's tracker). Copy this text as it stands:

   > Heads-up from Keenan's session for 1.0.10 (spec: `docs/superpowers/specs/2026-09-22-1-0-10-routines-and-soft-friction-design.md`, on branch `docs/1-0-10-spec`). Nothing merges before v1.0.9 is published. Two things touch your side, so say so here if you disagree: (1) the Sleep Blocking tab becomes **Schedule**. Your sleep section moves unchanged to the bottom of that page (the `SleepBlockingView` control is embedded as it is, with all its AutomationIds), so 3.7 can still rework it in place. (2) The Soft notice gains a growing wait before *Allow 5 minutes*, a *Close ‹app›* button (asks the app to close, never kills), and the intention and try count. F7 is yours on the checklist, and I built #224, so I'm taking this one unless you object. The first 1.0.10 PR to merge after your release recreates the changelog's **Unreleased** heading.

5. Push `docs/1-0-10-spec` and open its PR ("Spec and plan: 1.0.10 routines and Soft friction"). It's docs only, so it may merge before 1.0.9 once CI is green; a docs-only merge can't change the 1.0.9 build.

### Order of work

| Phase | PR | Branch / worktree | Tasks | Merge gate |
|---|---|---|---|---|
| Beside 1.0.9 | A | `feat/f6-templates-schedule-page` in `../FlowShield-f6a` | 1–5 | after v1.0.9 |
| Beside 1.0.9 | B | `feat/soft-friction` in `../FlowShield-soft` | 6–7 | after v1.0.9 |
| On 1.0.9 | C | `feat/f6-scheduler` in `../FlowShield-f6b` | 8–9 | after A merges |
| On 1.0.9 | D | `feat/turned-back` in `../FlowShield-turned` | 10 | after B merges |
| On 1.0.9 | E | `feat/jump-list` in `../FlowShield-jump` | 11 | after A merges |

Create each worktree from the latest `origin/main`:

```powershell
git fetch origin
git worktree add ..\FlowShield-f6a -b feat/f6-templates-schedule-page origin/main
```

A and B don't depend on each other; run them one after the other (a single implementer at a time keeps UI test runs serial). Start C, D and E only after 1.0.9 is published **and** their parent PR has merged, each from a fresh `origin/main`. Never stack one PR on another's branch (the stacked-PR gotchas in `CLAUDE.md`).

### Between tasks

- Run `gh release view v1.0.9` at every task boundary as well as the background watch.
- After each task's reviews pass, push the branch. Open the PR when its last task is done, with `Closes #<issue>`, the PR template filled in, the `LEGAL_CHECKLIST.md` items it touches (B touches the legal page's Soft wording), and screenshots of every visible change attached.

### When v1.0.9 is published

1. `git fetch origin`, then in each of A's and B's worktrees `git rebase origin/main`. Resolve conflicts by keeping both intents, then build, run the fast suite and the touched UI tests, and `git push --force-with-lease` (these are our own branches).
2. Check `Website/changelog.html`. If it has no `<h2>Unreleased</h2>` section, the first PR to merge adds one above the newest release, in the same `<div class="release">` shape as the others.
3. Merge A, then B, each with `gh pr merge <n> --squash --delete-branch`, once:
   - CI's `test` check passed (not just "mergeable"),
   - the spec review and the code-quality review for every task passed,
   - the touched UI tests passed on this PC,
   - the diff was read once more after the rebase.
4. Start C, D and E from the new `origin/main`, one at a time, and merge each the same way.

### If v1.0.9 isn't published by 06:00

Merge nothing. Keep A and B green and open. Build C, D and E locally on top of **local merges** of A and B in scratch branches, but don't push or open them. Write the morning report.

### Stop rules

- A task that fails the same review three times: stop that PR, record why, move to the next independent one.
- The fast suite red on `origin/main` (not our change): don't merge anything; record it.
- Anything that would need editing `TodayViewModel.OnTick`, `EndSprint`, `ResumeInterruptedSprint`, `MainWindow.Quit`/`OnClosing` or `App.OnExit` before 1.0.9 is published: stop and defer the task.
- Never cut a release, deploy the licence server, publish the site, touch Miles's branches or merge his PRs.

### Morning report

Write `reports/overnight/2026-09-23-1.0.10.md` (git-ignored), send it with SendUserFile, and post a short version as a comment on #37. It covers:
- what merged (PR links) and what is open and why;
- the results of each test tier, with counts, and any failures quoted;
- the screenshots;
- when 1.0.9 was published, and how any rebase conflicts were resolved;
- anything deferred or stopped under the stop rules;
- the tracker updates made: F6 ticked in `LAUNCH_FEATURE_CHECKLIST.md` by PR C, the #37 list, and the full UI suite run on the final `main`.

After the last merge, run the full suite once on the final `main` (`python -m pytest automation/tests -q`, which takes over the screen) and include the result.

---

## File structure

| File | New? | Responsibility |
|---|---|---|
| `automation/csharp/ModelProbe/ModelProbe.csproj` | new | Compiles `DesktopApp/Models/**/*.cs` into a console app |
| `automation/csharp/ModelProbe/Program.cs` | new | Reads one JSON request on stdin and writes one JSON answer |
| `automation/csharp/ModelProbe/Commands.cs` | new | One method per probe command |
| `automation/csharp/ModelProbe/LogStub.cs` | new | Silent `FlowShield.Services.Log` for the one model that logs |
| `automation/core/model_probe.py` | new | Builds the probe once per session; `probe(request) -> dict` |
| `DesktopApp/Models/StudyTemplate.cs` | new | Template data, the built-ins, `Normalize` |
| `DesktopApp/Models/SprintSchedule.cs` | new | Schedule data, skip dates, `Normalize` |
| `DesktopApp/Models/ScheduleMatcher.cs` | new | Local start → UTC, including DST; starts in a window; next start |
| `DesktopApp/Models/ScheduleText.cs` | new | "Mon–Thu", "17:00", "Next: tonight 17:00 · Homework evening" |
| `DesktopApp/Models/AppSettings.cs` | modify | `Templates`, `Schedules`, `TemplatesSeeded`, template helpers; `FocusSession.TurnedBack` (Task 10); `RunningSprint.TemplateBreakMinutes` (Task 9) |
| `DesktopApp/Services/DataPrivacyService.cs` | modify | Export includes templates and schedules |
| `DesktopApp/ViewModels/ScheduleViewModel.cs` | new | The Schedule page: schedules, templates, editors, next up |
| `DesktopApp/Views/ScheduleView.xaml(.cs)` | new | The Schedule page, which embeds `SleepBlockingView` unchanged |
| `DesktopApp/Styles/Theme.xaml` | modify | `SegmentCheck` style (a `Segment` look for check boxes) |
| `DesktopApp/ViewModels/MainViewModel.cs` | modify | `Schedule` VM, page title and subtitle, `EnsureTemplates`, Soft wiring, scheduler |
| `DesktopApp/MainWindow.xaml(.cs)` | modify | Nav label "Schedule", page host, the Soft **Close** handler |
| `DesktopApp/Models/SoftOverlayPolicy.cs` | modify | Tries, turned back, the growing wait, rotating wording |
| `DesktopApp/Views/SoftOverlayWindow.xaml(.cs)` | modify | Intention, try line, **Close ‹app›**, countdown on **Allow** |
| `DesktopApp/Services/AppBlockerService.cs` | modify | `AskToClose(displayName, settings)` — `CloseMainWindow` only |
| `DesktopApp/Services/ScheduleService.cs` | new | 15-second tick, heads-up, start, missed offer |
| `DesktopApp/ViewModels/TodayViewModel.cs` | modify | Template chips, `StartTemplate`, heads-up card, template break override, `TurnedBack` |
| `DesktopApp/Views/TodayView.xaml` | modify | Chip row, heads-up card, summary "Turned back" line |
| `DesktopApp/Models/HistoryStats.cs`, `ViewModels/HistoryViewModel.cs`, `Views/HistoryView.xaml` | modify | "Turned back" this week |
| `DesktopApp/Services/JumpListService.cs` | new | Builds the taskbar Jump List |
| `DesktopApp/Models/StartSprintArg.cs` | new | Parses `--start-sprint[=id]` |
| `DesktopApp/App.xaml.cs` | modify | Short-timer flags; hands `--start-sprint` to the VM |
| `automation/tests/test_tier1_unit.py` | modify | Probe tests and source pins |
| `automation/tests/test_tier3_e2e.py` | modify | Schedule page, Soft notice, scheduled start, Jump List argument |
| `automation/tests/test_tier5_regressions.py` | modify | Claims, wording, never-kill, ids |
| `automation/desktop/app_controller.py` | modify | `TAB_IDS["schedule"]` and schedule helpers |
| `README.md`, `HANDOFF_PROMPT.md`, `Website/legal.html`, `Website/changelog.html`, `LAUNCH_FEATURE_CHECKLIST.md` | modify | Wording, changelog, ticks |

---

# PR A — templates, schedules and the Schedule page

### Task 1: The model probe harness

**Files:**
- Create: `automation/csharp/ModelProbe/ModelProbe.csproj`
- Create: `automation/csharp/ModelProbe/Program.cs`
- Create: `automation/csharp/ModelProbe/Commands.cs`
- Create: `automation/csharp/ModelProbe/LogStub.cs`
- Create: `automation/core/model_probe.py`
- Test: `automation/tests/test_tier1_unit.py` (new class at the end of the file)

**Interfaces:**
- Produces: `from core.model_probe import probe` — `probe(request: dict) -> dict`, which raises `ProbeError` on a build or run failure. On the C# side, each command is a case in `Commands.Run(JsonObject) -> JsonNode`; later tasks add cases.

- [ ] **Step 1: Write the failing test** — append to `automation/tests/test_tier1_unit.py`:

```python
# ============================ the model probe: real C# from tier 1 (1.0.10)

from core.model_probe import probe


class TestModelProbe:
    """
    Tier 1 mirrors C# rules in Python and pins the C# by source, because there
    is no dotnet test project. That can't prove the C# computes the answer,
    and for time zones .NET decides it, not Python. ModelProbe compiles
    DesktopApp/Models as it is and answers JSON, so these run the real code.
    """

    def test_the_probe_answers(self):
        assert probe({"cmd": "ping"}) == {"ok": True}

    def test_the_probe_runs_the_real_soft_overlay_policy(self):
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0},
            {"op": "show", "app": "Discord", "at": 2},
            {"op": "left"},
            {"op": "show", "app": "Discord", "at": 60},
        ]})
        assert out["results"] == [True, False, True, True]

    def test_an_unknown_command_is_an_error_not_a_silent_pass(self):
        import pytest as _pytest
        from core.model_probe import ProbeError
        with _pytest.raises(ProbeError):
            probe({"cmd": "no-such-command"})
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest automation/tests/test_tier1_unit.py -k ModelProbe -q`
Expected: collection error, `ModuleNotFoundError: No module named 'core.model_probe'`.

- [ ] **Step 3: Write the harness**

`automation/csharp/ModelProbe/ModelProbe.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <!-- Tier 1's window into the real C# rules (1.0.10). Compiles
       DesktopApp/Models as it is, so a rule is tested in .NET rather than
       in a Python copy of it. Models must stay free of views, view models
       and services for this to build; Services.Log is stubbed. -->
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0-windows</TargetFramework>
    <UseWPF>true</UseWPF>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <RootNamespace>FlowShield.ModelProbe</RootNamespace>
    <AssemblyName>ModelProbe</AssemblyName>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="..\..\..\DesktopApp\Models\**\*.cs" LinkBase="Models" />
  </ItemGroup>
</Project>
```

`automation/csharp/ModelProbe/LogStub.cs`:

```csharp
namespace FlowShield.Services;

/// <summary>
/// The probe compiles DesktopApp/Models alone. One model (AppPicker) logs a
/// failure through Services.Log; this silent stand-in lets it build.
/// </summary>
internal static class Log
{
    public static void Info(string message) { }
    public static void Warn(string message) { }
    public static void Error(string message) { }
    public static void Error(string message, Exception ex) { }
}
```

`automation/csharp/ModelProbe/Program.cs`:

```csharp
using System.Text.Json.Nodes;
using FlowShield.ModelProbe;

// One JSON request on stdin, one JSON answer on stdout. Any failure is a
// non-zero exit with the exception on stderr, so a test can never pass on
// an answer that was never computed.
try
{
    var request = JsonNode.Parse(Console.In.ReadToEnd())!.AsObject();
    Console.Out.Write(Commands.Run(request).ToJsonString());
    return 0;
}
catch (Exception ex)
{
    Console.Error.WriteLine(ex.ToString());
    return 1;
}
```

`automation/csharp/ModelProbe/Commands.cs`:

```csharp
using System.Text.Json.Nodes;
using FlowShield.Models;

namespace FlowShield.ModelProbe;

internal static class Commands
{
    /// <summary>Probe times are seconds after this instant, so tests stay readable.</summary>
    private static readonly DateTime Epoch = new(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc);

    public static JsonNode Run(JsonObject request)
    {
        var cmd = (string?)request["cmd"] ?? "";
        return cmd switch
        {
            "ping" => new JsonObject { ["ok"] = true },
            "soft-sequence" => SoftSequence(request),
            _ => throw new ArgumentException($"unknown command '{cmd}'"),
        };
    }

    /// <summary>
    /// Runs SoftOverlayPolicy through a list of steps:
    /// {"op": "show"|"left"|"allow"|"back"|"reset", "app": "Discord", "at": seconds}.
    /// Each step's result is the method's return value, or null for void methods.
    /// </summary>
    private static JsonNode SoftSequence(JsonObject request)
    {
        var policy = new SoftOverlayPolicy();
        var results = new JsonArray();
        foreach (var step in request["steps"]!.AsArray())
        {
            var op = (string)step!["op"]!;
            var app = (string?)step["app"] ?? "";
            var at = Epoch.AddSeconds((double?)step["at"] ?? 0);
            JsonNode? result = op switch
            {
                "show" => (JsonNode)policy.ShouldShow(app, at),
                "left" => (JsonNode)policy.LeftTheForeground(),
                "allow" => Do(() => policy.AllowFiveMinutes(app, at)),
                "back" => Do(() => policy.BackToWork(app, at)),
                "reset" => Do(policy.Reset),
                _ => throw new ArgumentException($"unknown soft op '{op}'"),
            };
            results.Add(result);
        }
        return new JsonObject { ["results"] = results };
    }

    private static JsonNode? Do(Action action)
    {
        action();
        return null;
    }
}
```

`automation/core/model_probe.py`:

```python
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
    result = subprocess.run(
        ["dotnet", "build", str(PROBE_DIR / "ModelProbe.csproj"),
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
```

- [ ] **Step 4: Run it and watch it pass**

Run: `python -m pytest automation/tests/test_tier1_unit.py -k ModelProbe -q`
Expected: `3 passed` (the first run builds the probe, about 10–20 s).

- [ ] **Step 5: Confirm the desktop build ignores the probe, then run the fast suite**

Run: `cd DesktopApp; dotnet build -c Release -nologo` — expect 0 errors (the probe lives outside `DesktopApp/`, so it isn't compiled into the app).
Run: `python -m pytest automation/tests -m "not ui and not stripe" -q` — expect all pass.

- [ ] **Step 6: Commit**

```bash
git add automation/csharp/ModelProbe automation/core/model_probe.py automation/tests/test_tier1_unit.py
git commit -m "Tier 1 runs the real C# model code through a small probe

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `StudyTemplate` and the built-ins

**Files:**
- Create: `DesktopApp/Models/StudyTemplate.cs`
- Modify: `automation/csharp/ModelProbe/Commands.cs` (add two commands)
- Test: `automation/tests/test_tier1_unit.py`

**Interfaces:**
- Consumes: `ShieldLevel` (`AppSettings.cs`: Soft = 1, Firm = 2, Sealed = 3); `CycleState.CycleChoices` = `{0, 2, 3, 4}`, where 0 means one sprint; `CycleState.MinBreakMinutes` = 1 and `MaxBreakMinutes` = 60; `CycleState.DefaultShortBreakMinutes` = 5.
- Produces: `class StudyTemplate { string Id; string Name; int SprintMinutes; ShieldLevel Shield; int CycleSprints; int BreakMinutes; string ProfileId; string BuiltInKey; bool IsBuiltIn [JsonIgnore]; static string NewId(); static IReadOnlyList<StudyTemplate> BuiltIns(); bool Normalize(); const int MaxNameLength = 40, MinSprintMinutes = 5, MaxSprintMinutes = 240; const string UntitledName = "Untitled template"; }`. Built-in keys: `"homework"`, `"exam"`, `"light"`.

- [ ] **Step 1: Write the failing tests** — append to `test_tier1_unit.py`:

```python
class TestStudyTemplates:
    """F6: the three built-ins from the launch checklist, and a template can't hold nonsense."""

    def _builtins(self) -> dict:
        return {t["BuiltInKey"]: t for t in probe({"cmd": "template-builtins"})["templates"]}

    def test_three_built_ins_ship_with_the_checklist_values(self):
        b = self._builtins()
        assert set(b) == {"homework", "exam", "light"}
        hw, ex, li = b["homework"], b["exam"], b["light"]
        assert (hw["Name"], hw["SprintMinutes"], hw["Shield"], hw["CycleSprints"], hw["BreakMinutes"]) \
            == ("Homework evening", 45, 2, 3, 10)
        assert (ex["Name"], ex["SprintMinutes"], ex["Shield"], ex["CycleSprints"]) \
            == ("Exam prep", 90, 3, 0)
        assert (li["Name"], li["SprintMinutes"], li["Shield"], li["CycleSprints"], li["BreakMinutes"]) \
            == ("Light study", 25, 1, 0, 5)

    def test_built_ins_use_whichever_profile_is_active(self):
        assert all(t["ProfileId"] == "" for t in self._builtins().values())

    def test_each_call_hands_out_fresh_ids(self):
        first = {t["Id"] for t in self._builtins().values()}
        second = {t["Id"] for t in self._builtins().values()}
        assert len(first) == 3 and not first & second

    @pytest.mark.parametrize("field,given,expected", [
        ("SprintMinutes", 2, 5),
        ("SprintMinutes", 500, 240),
        ("CycleSprints", 1, 0),
        ("CycleSprints", 7, 0),
        ("CycleSprints", 3, 3),
        ("BreakMinutes", 0, 1),
        ("BreakMinutes", 99, 60),
        ("Shield", 9, 2),
        ("Name", "   ", "Untitled template"),
        ("Name", "x" * 60, "x" * 40),
        ("Name", "  Mock exam  ", "Mock exam"),
    ])
    def test_normalize_clamps_every_field(self, field, given, expected):
        template = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2,
                    "CycleSprints": 0, "BreakMinutes": 5, "ProfileId": "", "BuiltInKey": ""}
        template[field] = given
        out = probe({"cmd": "template-normalize", "template": template})
        assert out["template"][field] == expected
        assert out["changed"] is (given != expected)

    def test_normalize_gives_a_missing_id_a_new_one(self):
        out = probe({"cmd": "template-normalize", "template": {"Id": "", "Name": "A"}})
        assert len(out["template"]["Id"]) == 32 and out["changed"] is True
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest automation/tests/test_tier1_unit.py -k StudyTemplates -q`
Expected: FAIL — `ProbeError ... unknown command 'template-builtins'`.

- [ ] **Step 3: Write `DesktopApp/Models/StudyTemplate.cs`**

```csharp
using System.Text.Json.Serialization;

namespace FlowShield.Models;

/// <summary>
/// A named way to run a sprint (launch checklist F6): its length, shield,
/// cycle, break and blocklist, picked in one click on Today or started by a
/// schedule.
///
/// A preset, not a rule: choosing one fills in Today's controls, and each can
/// still be changed before Start. <see cref="ProfileId"/> empty (or naming a
/// profile that no longer exists) means "whichever profile is active",
/// resolved by <see cref="AppSettings.ProfileFor"/>.
/// </summary>
public class StudyTemplate
{
    public const int MaxNameLength = 40;

    /// <summary>Same bounds as Today's custom sprint length.</summary>
    public const int MinSprintMinutes = 5;
    public const int MaxSprintMinutes = 240;

    public const string UntitledName = "Untitled template";

    public string Id { get; set; } = NewId();
    public string Name { get; set; } = "";
    public int SprintMinutes { get; set; } = 25;
    public ShieldLevel Shield { get; set; } = ShieldLevel.Firm;

    /// <summary>One of <see cref="CycleState.CycleChoices"/>; 0 means a single sprint.</summary>
    public int CycleSprints { get; set; }

    /// <summary>The breaks inside this template's cycle. Hand-started sprints keep the global settings.</summary>
    public int BreakMinutes { get; set; } = CycleState.DefaultShortBreakMinutes;

    public string ProfileId { get; set; } = "";

    /// <summary>"homework", "exam" or "light" for a built-in, so Restore can find what's missing; empty for the user's own.</summary>
    public string BuiltInKey { get; set; } = "";

    [JsonIgnore]
    public bool IsBuiltIn => BuiltInKey.Length > 0;

    public static string NewId() => Guid.NewGuid().ToString("N");

    /// <summary>
    /// The three the checklist ships, as fresh instances with new ids on every
    /// call, so seeding or restoring can never share an object between lists.
    /// </summary>
    public static IReadOnlyList<StudyTemplate> BuiltIns() => new[]
    {
        new StudyTemplate
        {
            Name = "Homework evening", SprintMinutes = 45, Shield = ShieldLevel.Firm,
            CycleSprints = 3, BreakMinutes = 10, BuiltInKey = "homework",
        },
        new StudyTemplate
        {
            Name = "Exam prep", SprintMinutes = 90, Shield = ShieldLevel.Sealed,
            CycleSprints = 0, BreakMinutes = CycleState.DefaultShortBreakMinutes, BuiltInKey = "exam",
        },
        new StudyTemplate
        {
            Name = "Light study", SprintMinutes = 25, Shield = ShieldLevel.Soft,
            CycleSprints = 0, BreakMinutes = 5, BuiltInKey = "light",
        },
    };

    /// <summary>
    /// Brings every field into range: a hand-edited or older settings file can
    /// hold anything. Returns true if anything changed.
    /// </summary>
    public bool Normalize()
    {
        var before = (Id, Name, SprintMinutes, Shield, CycleSprints, BreakMinutes, ProfileId, BuiltInKey);

        if (string.IsNullOrWhiteSpace(Id)) Id = NewId();

        var name = (Name ?? "").Trim();
        if (name.Length == 0) name = UntitledName;
        if (name.Length > MaxNameLength) name = name[..MaxNameLength].TrimEnd();
        Name = name;

        SprintMinutes = Math.Clamp(SprintMinutes, MinSprintMinutes, MaxSprintMinutes);
        if (!Enum.IsDefined(Shield)) Shield = ShieldLevel.Firm;
        if (!CycleState.CycleChoices.Contains(CycleSprints)) CycleSprints = 0;
        BreakMinutes = Math.Clamp(BreakMinutes, CycleState.MinBreakMinutes, CycleState.MaxBreakMinutes);
        ProfileId ??= "";
        BuiltInKey ??= "";

        return before != (Id, Name, SprintMinutes, Shield, CycleSprints, BreakMinutes, ProfileId, BuiltInKey);
    }
}
```

- [ ] **Step 4: Add the probe commands** — in `Commands.cs`, add to the `switch` in `Run`:

```csharp
            "template-builtins" => new JsonObject
            {
                ["templates"] = JsonSerializer.SerializeToNode(StudyTemplate.BuiltIns()),
            },
            "template-normalize" => TemplateNormalize(request),
```

Add `using System.Text.Json;` at the top, and this method:

```csharp
    private static JsonNode TemplateNormalize(JsonObject request)
    {
        var template = request["template"].Deserialize<StudyTemplate>()!;
        var changed = template.Normalize();
        return new JsonObject
        {
            ["template"] = JsonSerializer.SerializeToNode(template),
            ["changed"] = changed,
        };
    }
```

- [ ] **Step 5: Run and watch them pass**

Run: `python -m pytest automation/tests/test_tier1_unit.py -k "StudyTemplates or ModelProbe" -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add DesktopApp/Models/StudyTemplate.cs automation/csharp/ModelProbe/Commands.cs automation/tests/test_tier1_unit.py
git commit -m "F6: study templates and the three built-ins

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `SprintSchedule`, `ScheduleMatcher` and `ScheduleText`

**Files:**
- Create: `DesktopApp/Models/SprintSchedule.cs`, `DesktopApp/Models/ScheduleMatcher.cs`, `DesktopApp/Models/ScheduleText.cs`
- Modify: `automation/csharp/ModelProbe/Commands.cs`
- Test: `automation/tests/test_tier1_unit.py`

**Interfaces:**
- Produces:
  - `class SprintSchedule { string Id; string TemplateId; List<DayOfWeek> Days; int StartMinuteOfDay; bool AskFirst = true; bool Enabled = true; List<DateTime> SkippedDatesLocal; bool IsSkipped(DateTime localDate); void Skip(DateTime localDate); bool Normalize(); const int SkipMemoryDays = 14; }`
  - `static class ScheduleMatcher { DateTime ToUtc(DateTime local, TimeZoneInfo zone); DateTime? StartOnDateUtc(SprintSchedule s, DateTime localDate, TimeZoneInfo zone); IReadOnlyList<DateTime> StartsBetweenUtc(SprintSchedule s, DateTime fromUtcExclusive, DateTime toUtcInclusive, TimeZoneInfo zone); DateTime? NextStartUtc(SprintSchedule s, DateTime afterUtc, TimeZoneInfo zone); }`
  - `static class ScheduleText { string Days(IEnumerable<DayOfWeek> days); string Time(int minuteOfDay); string NextUp(string templateName, DateTime startLocal, DateTime nowLocal); }`
- Every `DateTime` passed in as UTC has `Kind = Utc`. `localDate` is a local calendar date; its time part is ignored.

- [ ] **Step 1: Write the failing tests** — append to `test_tier1_unit.py`. The dates are real: in 2026, US clocks go forward on Sunday 8 March and back on Sunday 1 November; 28 September is a Monday.

```python
EASTERN = "Eastern Standard Time"   # Windows id; UTC-5 in winter, UTC-4 in summer
MON_THU = [1, 2, 3, 4]              # DayOfWeek: Sunday = 0 ... Saturday = 6


def schedule(days=MON_THU, minute=17 * 60, **extra) -> dict:
    return {"Id": "s1", "TemplateId": "t1", "Days": days, "StartMinuteOfDay": minute,
            "AskFirst": True, "Enabled": True, "SkippedDatesLocal": [], **extra}


class TestScheduleMatcher:
    """F6: when a schedule starts, computed by .NET's own time-zone rules."""

    def test_a_weeknight_schedule_starts_at_its_local_time(self):
        out = probe({"cmd": "schedule-start-on", "schedule": schedule(),
                     "date": "2026-09-28", "zone": EASTERN})
        assert out["utc"] == "2026-09-28T21:00:00Z"      # 17:00 EDT

    def test_a_day_that_is_not_chosen_has_no_start(self):
        out = probe({"cmd": "schedule-start-on", "schedule": schedule(),
                     "date": "2026-09-26", "zone": EASTERN})  # Saturday
        assert out["utc"] is None

    def test_spring_forward_starts_at_the_first_minute_that_exists(self):
        s = schedule(days=[0], minute=2 * 60 + 30)       # Sunday 02:30 never happens on 8 March
        out = probe({"cmd": "schedule-start-on", "schedule": s, "date": "2026-03-08", "zone": EASTERN})
        assert out["utc"] == "2026-03-08T07:00:00Z"      # 03:00 EDT

    def test_fall_back_starts_once_at_the_first_of_the_two(self):
        s = schedule(days=[0], minute=60 + 30)           # Sunday 01:30 happens twice on 1 November
        out = probe({"cmd": "schedule-start-on", "schedule": s, "date": "2026-11-01", "zone": EASTERN})
        assert out["utc"] == "2026-11-01T05:30:00Z"      # the EDT 01:30
        between = probe({"cmd": "schedule-between", "schedule": s, "zone": EASTERN,
                         "from": "2026-10-31T12:00:00Z", "to": "2026-11-02T12:00:00Z"})
        assert between["utc"] == ["2026-11-01T05:30:00Z"], "one start, not two"

    def test_next_start_skips_the_weekend(self):
        out = probe({"cmd": "schedule-next", "schedule": schedule(),
                     "after": "2026-09-25T12:00:00Z", "zone": EASTERN})  # Friday
        assert out["utc"] == "2026-09-28T21:00:00Z"

    def test_next_start_is_strictly_after_now(self):
        out = probe({"cmd": "schedule-next", "schedule": schedule(),
                     "after": "2026-09-28T21:00:00Z", "zone": EASTERN})
        assert out["utc"] == "2026-09-29T21:00:00Z"

    def test_starts_in_a_window_cover_every_chosen_day_once(self):
        out = probe({"cmd": "schedule-between", "schedule": schedule(), "zone": EASTERN,
                     "from": "2026-09-27T00:00:00Z", "to": "2026-10-01T00:00:00Z"})
        assert out["utc"] == ["2026-09-28T21:00:00Z", "2026-09-29T21:00:00Z",
                              "2026-09-30T21:00:00Z"]

    def test_no_days_means_never(self):
        out = probe({"cmd": "schedule-next", "schedule": schedule(days=[]),
                     "after": "2026-09-25T12:00:00Z", "zone": EASTERN})
        assert out["utc"] is None


class TestSprintScheduleSkips:
    def test_skip_today_is_remembered_for_that_date_only(self):
        out = probe({"cmd": "schedule-skip", "schedule": schedule(),
                     "skip": ["2026-09-28"], "query": ["2026-09-28", "2026-09-29"]})
        assert out["is_skipped"] == [True, False]

    def test_old_skips_are_pruned_after_fourteen_days(self):
        out = probe({"cmd": "schedule-skip", "schedule": schedule(),
                     "skip": ["2026-09-01", "2026-09-28"], "query": []})
        assert out["skipped"] == ["2026-09-28"]

    @pytest.mark.parametrize("minute,expected", [(-5, 0), (24 * 60, 24 * 60 - 1), (600, 600)])
    def test_normalize_keeps_the_start_inside_the_day(self, minute, expected):
        out = probe({"cmd": "schedule-normalize", "schedule": schedule(minute=minute)})
        assert out["schedule"]["StartMinuteOfDay"] == expected

    def test_normalize_sorts_and_dedupes_days(self):
        out = probe({"cmd": "schedule-normalize", "schedule": schedule(days=[4, 1, 1, 9])})
        assert out["schedule"]["Days"] == [1, 4]


class TestScheduleText:
    @pytest.mark.parametrize("days,expected", [
        ([1, 2, 3, 4, 5], "Weekdays"),
        ([0, 1, 2, 3, 4, 5, 6], "Every day"),
        ([6, 0], "Weekends"),
        ([1, 2, 3, 4], "Mon–Thu"),
        ([1, 3, 5], "Mon, Wed, Fri"),
        ([0], "Sun"),
        ([], "No days"),
    ])
    def test_days(self, days, expected):
        assert probe({"cmd": "text-days", "days": days})["text"] == expected

    @pytest.mark.parametrize("start,now,expected", [
        ("2026-09-28T17:00:00", "2026-09-28T09:00:00", "Next: tonight 17:00 · Homework evening"),
        ("2026-09-28T09:00:00", "2026-09-28T07:00:00", "Next: today 09:00 · Homework evening"),
        ("2026-09-29T17:00:00", "2026-09-28T20:00:00", "Next: tomorrow 17:00 · Homework evening"),
        ("2026-10-01T17:00:00", "2026-09-28T20:00:00", "Next: Thu 17:00 · Homework evening"),
    ])
    def test_next_up(self, start, now, expected):
        out = probe({"cmd": "text-next-up", "name": "Homework evening", "start": start, "now": now})
        assert out["text"] == expected

    def test_the_copy_keeps_to_the_house_voice(self):
        for name in ("ScheduleText.cs", "SprintSchedule.cs", "ScheduleMatcher.cs", "StudyTemplate.cs"):
            source = (Path(SERVER_DIR).parent / "DesktopApp" / "Models" / name).read_text(encoding="utf-8")
            for text in re.findall(r'"([^"]*)"', source):
                assert "!" not in text, f"exclamation mark in {name}: {text!r}"
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest automation/tests/test_tier1_unit.py -k "ScheduleMatcher or SprintScheduleSkips or ScheduleText" -q`
Expected: FAIL — unknown command `schedule-start-on`.

- [ ] **Step 3: Write `DesktopApp/Models/SprintSchedule.cs`**

```csharp
namespace FlowShield.Models;

/// <summary>
/// "Homework evening, Mon-Thu at 17:00" (launch checklist F6).
///
/// A start time only. The template's length decides when the sprint ends,
/// which avoids the midnight-spanning windows other blockers get wrong.
/// </summary>
public class SprintSchedule
{
    /// <summary>How long a "Skip today" is remembered. Older dates can't matter again.</summary>
    public const int SkipMemoryDays = 14;

    public string Id { get; set; } = StudyTemplate.NewId();
    public string TemplateId { get; set; } = "";
    public List<DayOfWeek> Days { get; set; } = new();

    /// <summary>Minutes after local midnight, 0 to 1439.</summary>
    public int StartMinuteOfDay { get; set; } = 17 * 60;

    /// <summary>Heads-up five minutes before, with Start now / Skip today. On by default.</summary>
    public bool AskFirst { get; set; } = true;

    public bool Enabled { get; set; } = true;

    /// <summary>Local dates the user chose Skip today.</summary>
    public List<DateTime> SkippedDatesLocal { get; set; } = new();

    public bool IsSkipped(DateTime localDate) =>
        SkippedDatesLocal.Any(d => d.Date == localDate.Date);

    public void Skip(DateTime localDate)
    {
        var date = localDate.Date;
        if (!IsSkipped(date)) SkippedDatesLocal.Add(date);
        SkippedDatesLocal.RemoveAll(d => d.Date < date.AddDays(-SkipMemoryDays));
        SkippedDatesLocal.Sort();
    }

    /// <summary>Brings a hand-edited or older record into range. True if anything changed.</summary>
    public bool Normalize()
    {
        var changed = false;
        if (string.IsNullOrWhiteSpace(Id)) { Id = StudyTemplate.NewId(); changed = true; }
        TemplateId ??= "";

        var minute = Math.Clamp(StartMinuteOfDay, 0, 24 * 60 - 1);
        if (minute != StartMinuteOfDay) { StartMinuteOfDay = minute; changed = true; }

        var days = (Days ?? new List<DayOfWeek>())
            .Where(d => Enum.IsDefined(d)).Distinct().OrderBy(d => d).ToList();
        if (Days is null || !days.SequenceEqual(Days)) { Days = days; changed = true; }

        SkippedDatesLocal ??= new List<DateTime>();
        return changed;
    }
}
```

- [ ] **Step 4: Write `DesktopApp/Models/ScheduleMatcher.cs`**

```csharp
namespace FlowShield.Models;

/// <summary>
/// When a <see cref="SprintSchedule"/> starts (F6). Pure: no timers, no clock
/// of its own. Every answer is a UTC instant, so a comparison never depends
/// on what the wall clock was doing.
///
/// Daylight saving, written down once:
///   * Spring forward: the start time doesn't exist that day (02:30 on the
///     day clocks jump to 03:00). The sprint starts at the first minute that
///     does exist.
///   * Fall back: the start time happens twice. The sprint starts once, at
///     the first occurrence. Each local date yields one instant, so a second
///     start is impossible.
/// </summary>
public static class ScheduleMatcher
{
    /// <summary>A local wall-clock time in <paramref name="zone"/> as one UTC instant, per the rules above.</summary>
    public static DateTime ToUtc(DateTime local, TimeZoneInfo zone)
    {
        local = DateTime.SpecifyKind(local, DateTimeKind.Unspecified);

        // Spring forward. Bounded, so a malformed zone can't loop forever.
        for (var guard = 0; zone.IsInvalidTime(local) && guard < 24 * 60; guard++)
            local = local.AddMinutes(1);

        if (zone.IsAmbiguousTime(local))
        {
            // Fall back. The earlier instant is the one with the larger offset.
            var offset = zone.GetAmbiguousTimeOffsets(local).Max();
            return DateTime.SpecifyKind(local - offset, DateTimeKind.Utc);
        }

        return TimeZoneInfo.ConvertTimeToUtc(local, zone);
    }

    /// <summary>The start on this local date, or null when the schedule doesn't run that day.</summary>
    public static DateTime? StartOnDateUtc(SprintSchedule schedule, DateTime localDate, TimeZoneInfo zone)
    {
        var date = localDate.Date;
        if (!schedule.Days.Contains(date.DayOfWeek)) return null;
        var minute = Math.Clamp(schedule.StartMinuteOfDay, 0, 24 * 60 - 1);
        return ToUtc(date.AddMinutes(minute), zone);
    }

    /// <summary>Every start after <paramref name="fromUtcExclusive"/> and at or before <paramref name="toUtcInclusive"/>, oldest first.</summary>
    public static IReadOnlyList<DateTime> StartsBetweenUtc(
        SprintSchedule schedule, DateTime fromUtcExclusive, DateTime toUtcInclusive, TimeZoneInfo zone)
    {
        var found = new List<DateTime>();
        if (toUtcInclusive <= fromUtcExclusive || schedule.Days.Count == 0) return found;

        // One day either side: a UTC window can start or end on a different local date.
        var first = TimeZoneInfo.ConvertTimeFromUtc(fromUtcExclusive, zone).Date.AddDays(-1);
        var last = TimeZoneInfo.ConvertTimeFromUtc(toUtcInclusive, zone).Date.AddDays(1);
        for (var day = first; day <= last; day = day.AddDays(1))
        {
            if (StartOnDateUtc(schedule, day, zone) is { } start
                && start > fromUtcExclusive && start <= toUtcInclusive)
            {
                found.Add(start);
            }
        }
        return found;
    }

    /// <summary>The first start strictly after <paramref name="afterUtc"/>, or null when no day is chosen.</summary>
    public static DateTime? NextStartUtc(SprintSchedule schedule, DateTime afterUtc, TimeZoneInfo zone)
    {
        if (schedule.Days.Count == 0) return null;
        var today = TimeZoneInfo.ConvertTimeFromUtc(afterUtc, zone).Date;
        for (var i = 0; i <= 8; i++)
        {
            if (StartOnDateUtc(schedule, today.AddDays(i), zone) is { } start && start > afterUtc)
                return start;
        }
        return null;
    }
}
```

- [ ] **Step 5: Write `DesktopApp/Models/ScheduleText.cs`**

```csharp
using System.Globalization;

namespace FlowShield.Models;

/// <summary>How schedules read on screen (F6). Pure, so tier 1 checks the wording.</summary>
public static class ScheduleText
{
    /// <summary>Monday first, the way a school week reads.</summary>
    private static readonly DayOfWeek[] WeekOrder =
    {
        DayOfWeek.Monday, DayOfWeek.Tuesday, DayOfWeek.Wednesday, DayOfWeek.Thursday,
        DayOfWeek.Friday, DayOfWeek.Saturday, DayOfWeek.Sunday,
    };

    private static string Short(DayOfWeek day) =>
        CultureInfo.InvariantCulture.DateTimeFormat.GetAbbreviatedDayName(day);

    /// <summary>"Weekdays", "Every day", "Weekends", "Mon–Thu" or "Mon, Wed, Fri".</summary>
    public static string Days(IEnumerable<DayOfWeek> days)
    {
        var set = days.ToHashSet();
        if (set.Count == 0) return "No days";
        if (set.Count == 7) return "Every day";

        var ordered = WeekOrder.Where(set.Contains).ToList();
        if (ordered.SequenceEqual(WeekOrder.Take(5))) return "Weekdays";
        if (set.SetEquals(new[] { DayOfWeek.Saturday, DayOfWeek.Sunday })) return "Weekends";

        var firstIndex = Array.IndexOf(WeekOrder, ordered[0]);
        var contiguous = ordered.Select((d, i) => Array.IndexOf(WeekOrder, d) == firstIndex + i).All(x => x);
        if (contiguous && ordered.Count >= 3)
            return $"{Short(ordered[0])}–{Short(ordered[^1])}";

        return string.Join(", ", ordered.Select(Short));
    }

    /// <summary>"17:00". 24-hour, like the sleep window.</summary>
    public static string Time(int minuteOfDay)
    {
        var m = Math.Clamp(minuteOfDay, 0, 24 * 60 - 1);
        return $"{m / 60:00}:{m % 60:00}";
    }

    /// <summary>"Next: tonight 17:00 · Homework evening". "Tonight" from 17:00, "today" before.</summary>
    public static string NextUp(string templateName, DateTime startLocal, DateTime nowLocal)
    {
        var time = Time((int)startLocal.TimeOfDay.TotalMinutes);
        var days = (startLocal.Date - nowLocal.Date).Days;
        var when = days switch
        {
            0 => startLocal.Hour >= 17 ? "tonight" : "today",
            1 => "tomorrow",
            _ => Short(startLocal.DayOfWeek),
        };
        return $"Next: {when} {time} · {templateName}";
    }
}
```

- [ ] **Step 6: Add the probe commands** — in `Commands.Run`'s switch:

```csharp
            "schedule-start-on" => ScheduleStartOn(request),
            "schedule-next" => ScheduleNext(request),
            "schedule-between" => ScheduleBetween(request),
            "schedule-skip" => ScheduleSkip(request),
            "schedule-normalize" => ScheduleNormalize(request),
            "text-days" => new JsonObject
            {
                ["text"] = ScheduleText.Days(request["days"]!.AsArray().Select(d => (DayOfWeek)(int)d!)),
            },
            "text-next-up" => new JsonObject
            {
                ["text"] = ScheduleText.NextUp((string)request["name"]!,
                    DateTime.Parse((string)request["start"]!, CultureInfo.InvariantCulture),
                    DateTime.Parse((string)request["now"]!, CultureInfo.InvariantCulture)),
            },
```

Add `using System.Globalization;` and these helpers:

```csharp
    private static SprintSchedule ScheduleOf(JsonObject request) =>
        request["schedule"].Deserialize<SprintSchedule>()!;

    private static TimeZoneInfo ZoneOf(JsonObject request) =>
        TimeZoneInfo.FindSystemTimeZoneById((string)request["zone"]!);

    private static DateTime Utc(string text) =>
        DateTime.Parse(text, CultureInfo.InvariantCulture,
            DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal);

    private static JsonNode? Iso(DateTime? utc) =>
        utc is { } t ? JsonValue.Create(t.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture)) : null;

    private static JsonNode ScheduleStartOn(JsonObject request) => new JsonObject
    {
        ["utc"] = Iso(ScheduleMatcher.StartOnDateUtc(ScheduleOf(request),
            DateTime.Parse((string)request["date"]!, CultureInfo.InvariantCulture), ZoneOf(request))),
    };

    private static JsonNode ScheduleNext(JsonObject request) => new JsonObject
    {
        ["utc"] = Iso(ScheduleMatcher.NextStartUtc(ScheduleOf(request),
            Utc((string)request["after"]!), ZoneOf(request))),
    };

    private static JsonNode ScheduleBetween(JsonObject request)
    {
        var starts = ScheduleMatcher.StartsBetweenUtc(ScheduleOf(request),
            Utc((string)request["from"]!), Utc((string)request["to"]!), ZoneOf(request));
        return new JsonObject { ["utc"] = new JsonArray(starts.Select(s => Iso(s)).ToArray()) };
    }

    private static JsonNode ScheduleSkip(JsonObject request)
    {
        var schedule = ScheduleOf(request);
        foreach (var d in request["skip"]!.AsArray())
            schedule.Skip(DateTime.Parse((string)d!, CultureInfo.InvariantCulture));
        var queries = request["query"]!.AsArray()
            .Select(d => (JsonNode)schedule.IsSkipped(DateTime.Parse((string)d!, CultureInfo.InvariantCulture)))
            .ToArray();
        return new JsonObject
        {
            ["skipped"] = new JsonArray(schedule.SkippedDatesLocal
                .Select(d => (JsonNode)d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)).ToArray()),
            ["is_skipped"] = new JsonArray(queries),
        };
    }

    private static JsonNode ScheduleNormalize(JsonObject request)
    {
        var schedule = ScheduleOf(request);
        var changed = schedule.Normalize();
        return new JsonObject
        {
            ["schedule"] = JsonSerializer.SerializeToNode(schedule),
            ["changed"] = changed,
        };
    }
```

- [ ] **Step 7: Run and watch them pass**

Run: `python -m pytest automation/tests/test_tier1_unit.py -k "ScheduleMatcher or SprintScheduleSkips or ScheduleText or StudyTemplates or ModelProbe" -q`
Expected: all pass. If `Mon–Thu` fails on the dash, check that the source contains the `–` escape rather than a literal character (the house rule is ASCII-only literals).

- [ ] **Step 8: Commit**

```bash
git add DesktopApp/Models/SprintSchedule.cs DesktopApp/Models/ScheduleMatcher.cs DesktopApp/Models/ScheduleText.cs automation/csharp/ModelProbe/Commands.cs automation/tests/test_tier1_unit.py
git commit -m "F6: schedules and when they start, daylight saving included

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Templates and schedules in settings, seeded once

**Files:**
- Modify: `DesktopApp/Models/AppSettings.cs` (add after `EnsureProfiles` and the profile helpers, before the `// ---- sleep` settings block near line 465)
- Modify: `DesktopApp/ViewModels/MainViewModel.cs:29-32` (call `EnsureTemplates`)
- Modify: `DesktopApp/Services/DataPrivacyService.cs:23-56` (export)
- Modify: `automation/csharp/ModelProbe/Commands.cs`
- Test: `automation/tests/test_tier1_unit.py` (new class; and `TestDataPrivacyExport.test_the_export_shape_covers_everything_local` gains two fields)

**Interfaces:**
- Consumes: `StudyTemplate`, `SprintSchedule` (Tasks 2–3); `AppSettings.FindProfile`, `ActiveProfile`.
- Produces on `AppSettings`:
  - `List<StudyTemplate> Templates`, `List<SprintSchedule> Schedules`, `bool TemplatesSeeded`
  - `bool EnsureTemplates()`, `int RestoreBuiltInTemplates()`, `StudyTemplate? FindTemplate(string? id)`, `IReadOnlyList<SprintSchedule> SchedulesUsing(string templateId)`, `int DeleteTemplate(string id)`, `BlocklistProfile ProfileFor(StudyTemplate template)`

- [ ] **Step 1: Write the failing tests**

```python
def settings_json(**fields) -> dict:
    base = {"Profiles": [{"Id": "p1", "Name": "School", "Apps": []},
                         {"Id": "p2", "Name": "Everything", "Apps": []}],
            "ActiveProfileId": "p1"}
    base.update(fields)
    return base


class TestTemplatesInSettings:
    """F6: templates and schedules live in the encrypted settings file."""

    def test_a_1_0_9_settings_file_gets_the_built_ins_once(self):
        out = probe({"cmd": "settings-ensure-templates", "settings": settings_json()})
        assert out["changed_first"] is True and out["changed_second"] is False
        assert out["templates"] == ["Homework evening", "Exam prep", "Light study"]
        assert out["seeded"] is True

    def test_deleting_every_template_does_not_bring_them_back(self):
        out = probe({"cmd": "settings-ensure-templates",
                     "settings": settings_json(Templates=[], TemplatesSeeded=True)})
        assert out["templates"] == [] and out["changed_first"] is False

    def test_a_schedule_whose_template_is_gone_is_removed_on_load(self):
        s = {"Id": "s1", "TemplateId": "missing", "Days": [1], "StartMinuteOfDay": 1020}
        out = probe({"cmd": "settings-ensure-templates",
                     "settings": settings_json(Templates=[], TemplatesSeeded=True, Schedules=[s])})
        assert out["schedules"] == [] and out["changed_first"] is True

    def test_deleting_a_template_deletes_its_schedules(self):
        t = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2}
        keep = {"Id": "s2", "TemplateId": "t2", "Days": [2], "StartMinuteOfDay": 600}
        gone = {"Id": "s1", "TemplateId": "t1", "Days": [1], "StartMinuteOfDay": 1020}
        t2 = {"Id": "t2", "Name": "Other", "SprintMinutes": 30, "Shield": 2}
        out = probe({"cmd": "settings-delete-template", "id": "t1",
                     "settings": settings_json(Templates=[t, t2], TemplatesSeeded=True,
                                               Schedules=[gone, keep])})
        assert out["removed"] == 1
        assert out["templates"] == ["Other"] and out["schedules"] == ["s2"]

    def test_restore_adds_only_the_missing_built_ins(self):
        first = probe({"cmd": "settings-ensure-templates", "settings": settings_json()})
        kept = [t for t in first["raw_templates"] if t["BuiltInKey"] != "exam"]
        out = probe({"cmd": "settings-restore-builtins",
                     "settings": settings_json(Templates=kept, TemplatesSeeded=True)})
        assert out["added"] == 1
        assert sorted(out["templates"]) == ["Exam prep", "Homework evening", "Light study"]

    @pytest.mark.parametrize("profile_id,expected", [("p2", "Everything"), ("", "School"),
                                                     ("deleted", "School")])
    def test_a_template_uses_its_profile_or_the_active_one(self, profile_id, expected):
        t = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2, "ProfileId": profile_id}
        out = probe({"cmd": "settings-profile-for", "template_id": "t1",
                     "settings": settings_json(Templates=[t], TemplatesSeeded=True)})
        assert out["profile"] == expected

    def test_startup_ensures_templates_after_profiles(self):
        source = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "MainViewModel.cs").read_text(encoding="utf-8")
        assert source.index("Settings.EnsureProfiles()") < source.index("Settings.EnsureTemplates()")
```

In `TestDataPrivacyExport.test_the_export_shape_covers_everything_local`, add `"studyTemplates", "sprintSchedules"` to the tuple of fields.

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest automation/tests/test_tier1_unit.py -k "TemplatesInSettings or DataPrivacyExport" -q`
Expected: FAIL (unknown probe command; export fields missing).

- [ ] **Step 3: Add to `AppSettings`** (new region after the profile helpers):

```csharp
    // ---- study templates and schedules (F6) -----------------------------

    /// <summary>Named ways to run a sprint. Seeded with the three built-ins once.</summary>
    public List<StudyTemplate> Templates { get; set; } = new();

    /// <summary>When templates start by themselves.</summary>
    public List<SprintSchedule> Schedules { get; set; } = new();

    /// <summary>
    /// Set once the built-ins have been added, so someone who deletes every
    /// template doesn't find them back on the next launch.
    /// </summary>
    public bool TemplatesSeeded { get; set; }

    public StudyTemplate? FindTemplate(string? id) =>
        string.IsNullOrEmpty(id)
            ? null
            : Templates.FirstOrDefault(t => string.Equals(t.Id, id, StringComparison.Ordinal));

    /// <summary>
    /// Seeds the built-ins on first run, repairs anything out of range, and
    /// drops schedules whose template no longer exists. Run once at startup,
    /// after <see cref="EnsureProfiles"/>. True if anything changed.
    /// </summary>
    public bool EnsureTemplates()
    {
        var changed = false;
        Templates ??= new List<StudyTemplate>();
        Schedules ??= new List<SprintSchedule>();

        if (!TemplatesSeeded)
        {
            Templates.AddRange(StudyTemplate.BuiltIns());
            TemplatesSeeded = true;
            changed = true;
        }

        foreach (var template in Templates) changed |= template.Normalize();
        foreach (var schedule in Schedules) changed |= schedule.Normalize();

        changed |= Schedules.RemoveAll(s => FindTemplate(s.TemplateId) is null) > 0;
        return changed;
    }

    /// <summary>Re-adds any built-in that is missing; never touches the user's own. Returns how many came back.</summary>
    public int RestoreBuiltInTemplates()
    {
        var have = Templates.Select(t => t.BuiltInKey).ToHashSet(StringComparer.Ordinal);
        var missing = StudyTemplate.BuiltIns().Where(b => !have.Contains(b.BuiltInKey)).ToList();
        Templates.AddRange(missing);
        return missing.Count;
    }

    public IReadOnlyList<SprintSchedule> SchedulesUsing(string templateId) =>
        Schedules.Where(s => string.Equals(s.TemplateId, templateId, StringComparison.Ordinal)).ToList();

    /// <summary>Deletes a template and every schedule that starts it. Returns how many schedules went with it.</summary>
    public int DeleteTemplate(string id)
    {
        var template = FindTemplate(id);
        if (template is null) return 0;
        Templates.Remove(template);
        return Schedules.RemoveAll(s => string.Equals(s.TemplateId, id, StringComparison.Ordinal));
    }

    /// <summary>The blocklist a template runs with: its own profile, or the active one if it has none or it was deleted.</summary>
    public BlocklistProfile ProfileFor(StudyTemplate template) =>
        FindProfile(template.ProfileId) ?? ActiveProfile;
```

- [ ] **Step 4: Call it at startup** — in `MainViewModel`'s constructor, directly after the `EnsureProfiles` block (lines 29–32):

```csharp
        // F6: the three built-in templates arrive once, and a schedule whose
        // template is gone is dropped before anything reads it.
        if (Settings.EnsureTemplates())
            Log.Info($"study templates ready: {Settings.Templates.Count}, schedules {Settings.Schedules.Count}");
```

(`App.OnStartup` saves right after construction, as the trial comment above it says, so this persists.)

- [ ] **Step 5: Export them** — in `DataPrivacyService.Export`'s payload, after `activeProfileId = settings.ActiveProfileId,`:

```csharp

            // F6: templates and schedules are stored locally too, so they're
            // part of "everything".
            studyTemplates = settings.Templates,
            sprintSchedules = settings.Schedules,
```

- [ ] **Step 6: Probe commands** — in the `switch`:

```csharp
            "settings-ensure-templates" => SettingsEnsureTemplates(request),
            "settings-delete-template" => SettingsDeleteTemplate(request),
            "settings-restore-builtins" => SettingsRestore(request),
            "settings-profile-for" => SettingsProfileFor(request),
```

```csharp
    private static AppSettings SettingsOf(JsonObject request)
    {
        var settings = request["settings"].Deserialize<AppSettings>() ?? new AppSettings();
        settings.EnsureProfiles();
        return settings;
    }

    private static JsonArray Names(AppSettings s) =>
        new(s.Templates.Select(t => (JsonNode)t.Name).ToArray());

    private static JsonArray ScheduleIds(AppSettings s) =>
        new(s.Schedules.Select(x => (JsonNode)x.Id).ToArray());

    private static JsonNode SettingsEnsureTemplates(JsonObject request)
    {
        var settings = SettingsOf(request);
        var first = settings.EnsureTemplates();
        var second = settings.EnsureTemplates();
        return new JsonObject
        {
            ["changed_first"] = first,
            ["changed_second"] = second,
            ["seeded"] = settings.TemplatesSeeded,
            ["templates"] = Names(settings),
            ["raw_templates"] = JsonSerializer.SerializeToNode(settings.Templates),
            ["schedules"] = ScheduleIds(settings),
        };
    }

    private static JsonNode SettingsDeleteTemplate(JsonObject request)
    {
        var settings = SettingsOf(request);
        var removed = settings.DeleteTemplate((string)request["id"]!);
        return new JsonObject
        {
            ["removed"] = removed, ["templates"] = Names(settings), ["schedules"] = ScheduleIds(settings),
        };
    }

    private static JsonNode SettingsRestore(JsonObject request)
    {
        var settings = SettingsOf(request);
        var added = settings.RestoreBuiltInTemplates();
        return new JsonObject { ["added"] = added, ["templates"] = Names(settings) };
    }

    private static JsonNode SettingsProfileFor(JsonObject request)
    {
        var settings = SettingsOf(request);
        var template = settings.FindTemplate((string)request["template_id"]!)!;
        return new JsonObject { ["profile"] = settings.ProfileFor(template).Name };
    }
```

- [ ] **Step 7: Run and watch them pass, then run the fast suite**

Run: `python -m pytest automation/tests/test_tier1_unit.py -k "TemplatesInSettings or DataPrivacyExport or ScheduleMatcher or StudyTemplates" -q` — pass.
Run: `cd DesktopApp; dotnet build -c Release -nologo` — 0 errors.
Run: `python -m pytest automation/tests -m "not ui and not stripe" -q` — pass. `TestSettingsSaveDoesNotRaceItsMutators` still passes, because `Clone()` round-trips through JSON, which deep-copies the new lists.

- [ ] **Step 8: Commit**

```bash
git add DesktopApp/Models/AppSettings.cs DesktopApp/ViewModels/MainViewModel.cs DesktopApp/Services/DataPrivacyService.cs automation/csharp/ModelProbe/Commands.cs automation/tests/test_tier1_unit.py
git commit -m "F6: templates and schedules are saved, seeded once, and exported

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The Schedule page

**Files:**
- Create: `DesktopApp/ViewModels/ScheduleViewModel.cs`, `DesktopApp/Views/ScheduleView.xaml`, `DesktopApp/Views/ScheduleView.xaml.cs`
- Modify: `DesktopApp/Styles/Theme.xaml` (add `SegmentCheck` after the `Segment` style at line 591)
- Modify: `DesktopApp/ViewModels/MainViewModel.cs` (property, construction, title and subtitle, page refresh, tier change)
- Modify: `DesktopApp/MainWindow.xaml:129-136` (nav label and name), `:185-187` (page host)
- Modify: `automation/desktop/app_controller.py` (`TAB_IDS`, helpers)
- Test: `automation/tests/test_tier3_e2e.py`, `automation/tests/test_tier5_regressions.py`

**Interfaces:**
- Consumes: Task 4's `AppSettings` members; `ScheduleText`; `ScheduleMatcher.NextStartUtc`; `MainViewModel.Settings`, `SaveSettings()`, `Toast(string)`, `IsLocked`, `IsSprintRunning`, `Blocker.ActiveShield`; `SleepBlockingViewModel` (unchanged).
- Produces:
  - `MainViewModel.Schedule` (`ScheduleViewModel`) with a `Sleep` property that returns `MainViewModel.SleepBlocking`.
  - `ScheduleViewModel.Refresh()` and `ScheduleViewModel.TemplatesChanged` (an `event EventHandler`, used by Task 9's chips and Task 11's Jump List).
  - AutomationIds: `ScheduleNextUpText`, `AddScheduleButton`, `ScheduleTemplate_{Name}` (the editor's template choices), `ScheduleDay_Mon` … `ScheduleDay_Sun`, `ScheduleTimeInput`, `ScheduleAskFirstToggle`, `SaveScheduleButton`, `CancelScheduleButton`, `ScheduleRow_{Id}` (row text), `ScheduleEnabled_{Id}`, `EditSchedule_{Id}`, `DeleteSchedule_{Id}`, `NewTemplateButton`, `RestoreTemplatesButton`, `TemplateRow_{Name}`, `EditTemplate_{Name}`, `DeleteTemplate_{Name}`, `TemplateNameInput`, `TemplateMinutesInput`, `TemplateShield_Soft|Firm|Sealed`, `TemplateCycle_0|2|3|4`, `TemplateBreakInput`, `TemplateProfile_{Name}`, `SaveTemplateButton`, `CancelTemplateButton`, `ScheduleStatusText`.
  - The page title "Schedule". The `AppPage.SleepBlocking` enum value and `Tab_SleepBlocking` stay; `Ctrl+4` is unchanged.

- [ ] **Step 1: Write the failing UI tests** — in `test_tier3_e2e.py`, change the `TestAppShell` parametrize list's `"Sleep Blocking"` to `"Schedule"`, replace every other `navigate_to_tab("Sleep Blocking")` in the file with `navigate_to_tab("Schedule")` (grep for them), and append:

```python
# =================================================== the Schedule page (F6)

class TestSchedulePage:
    """F6: templates and schedules, with the sleep window below them, unchanged."""

    def test_the_built_in_templates_are_listed(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        for name in ("Homework evening", "Exam prep", "Light study"):
            assert fresh_app.exists(f"TemplateRow_{name}", timeout=3), name

    def test_the_sleep_window_is_still_on_the_page(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        assert fresh_app.exists("SleepBlockToggle", timeout=3)
        assert fresh_app.exists("SaveSleepWindowButton", timeout=3)

    def test_adding_a_schedule_saves_it(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.add_schedule("Homework evening", ["Mon", "Tue", "Wed", "Thu"], "17:00")
        schedules = verify.read_settings()["Schedules"]
        assert len(schedules) == 1
        s = schedules[0]
        assert s["Days"] == [1, 2, 3, 4] and s["StartMinuteOfDay"] == 17 * 60 and s["AskFirst"] is True
        template = next(t for t in verify.read_settings()["Templates"] if t["Id"] == s["TemplateId"])
        assert template["Name"] == "Homework evening"
        assert "Mon–Thu" in fresh_app.text_of(f"ScheduleRow_{s['Id']}")

    def test_save_is_refused_without_a_day(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("AddScheduleButton")
        fresh_app.choose("ScheduleTemplate_Light study")
        assert not fresh_app.is_control_enabled("SaveScheduleButton")

    def test_deleting_a_template_deletes_its_schedules_after_a_confirmation(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.add_schedule("Exam prep", ["Sat"], "09:00")
        fresh_app.click("DeleteTemplate_Exam prep")
        assert "1 schedule" in fresh_app.dismiss_dialog(), "the confirmation names what goes with it"
        settings = verify.read_settings()
        assert all(t["Name"] != "Exam prep" for t in settings["Templates"])
        assert settings["Schedules"] == []

    def test_restore_brings_back_a_deleted_built_in(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("DeleteTemplate_Light study")
        fresh_app.dismiss_dialog()
        fresh_app.click("RestoreTemplatesButton")
        assert fresh_app.exists("TemplateRow_Light study", timeout=3)
```

`dismiss_dialog()` in `app_controller.py` presses the default button and returns the dialog's text. Read it (line ~1205) to confirm it accepts; if it cancels instead, add an `accept_dialog()` helper beside it that clicks the dialog's `Yes`/`OK`/`Delete` button and returns the text.

In `app_controller.py`, add `"schedule": "Tab_SleepBlocking"` to `TAB_IDS`, and this helper next to `set_sleep_window`:

```python
    def add_schedule(self, template: str, days: list[str], time_text: str,
                     ask_first: bool = True) -> None:
        """Schedule page: Add schedule, pick a template, days and time, then Save."""
        self.click("AddScheduleButton")
        self.choose(f"ScheduleTemplate_{template}")
        for day in days:
            self.set_toggle(f"ScheduleDay_{day}", True)
        self.set_text("ScheduleTimeInput", time_text)
        self.set_toggle("ScheduleAskFirstToggle", ask_first)
        self.click("SaveScheduleButton")
        time.sleep(0.8)
```

In `test_tier5_regressions.py`, append:

```python
class TestSchedulePageKeepsTheSleepWindow:
    """F6 moves Sleep Blocking inside Schedule; nothing of the sleep window may be lost."""

    def test_the_sleep_view_is_embedded_not_rewritten(self):
        page = (Path(DESKTOP_DIR) / "Views" / "ScheduleView.xaml").read_text(encoding="utf-8")
        assert "<views:SleepBlockingView" in page and 'DataContext="{Binding Sleep}"' in page
        sleep = (Path(DESKTOP_DIR) / "Views" / "SleepBlockingView.xaml").read_text(encoding="utf-8")
        for automation_id in ("SleepBlockToggle", "SleepStartInput", "SleepEndInput",
                              "SaveSleepWindowButton", "SleepStatusText", "SleepWindowText"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in sleep

    def test_the_tab_keeps_its_id_and_shortcut(self):
        xaml = (Path(DESKTOP_DIR) / "MainWindow.xaml").read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="Tab_SleepBlocking"' in xaml
        assert 'Key="D4" Command="{Binding NavigateCommand}" CommandParameter="SleepBlocking"' in xaml
        assert 'Text="Schedule"' in xaml

    def test_every_new_id_is_on_a_real_control(self):
        xaml = (Path(DESKTOP_DIR) / "Views" / "ScheduleView.xaml").read_text(encoding="utf-8")
        for match in re.finditer(r"<(\w+)[^>]*AutomationProperties\.AutomationId=", xaml):
            assert match.group(1) not in ("Border", "Grid", "StackPanel", "WrapPanel"), (
                f"an AutomationId on a {match.group(1)} is never surfaced (#134)")
```

- [ ] **Step 2: Build, then run and watch them fail**

Run: `python -m pytest automation/tests/test_tier5_regressions.py -k SchedulePageKeeps -q` — FAIL (no `ScheduleView.xaml`).
Run the UI tests (UI-test lock: nobody else running them): `python -m pytest automation/tests/test_tier3_e2e.py -k "SchedulePage or TestAppShell" -q` — FAIL (no "Schedule" title).

- [ ] **Step 3: Add `SegmentCheck` to `Theme.xaml`** — copy the whole `<Style x:Key="Segment" TargetType="RadioButton">` block (line 591 to its closing `</Style>`) directly below it. In the copy, change `x:Key="Segment"` to `x:Key="SegmentCheck"`, and change every `TargetType="RadioButton"` inside it (the style's and its `ControlTemplate`'s) to `TargetType="CheckBox"`. Nothing else changes. Day chips then look exactly like shield and cycle chips.

- [ ] **Step 4: Write `DesktopApp/ViewModels/ScheduleViewModel.cs`**

```csharp
using System.Collections.ObjectModel;
using FlowShield.Infrastructure;
using FlowShield.Models;
using FlowShield.Services;

namespace FlowShield.ViewModels;

/// <summary>
/// The Schedule page (F6): schedules on top, templates below, and the sleep
/// window at the bottom, unchanged, through <see cref="Sleep"/>.
/// Read-only during a Sealed sprint, like the blocklist.
/// </summary>
public class ScheduleViewModel : ViewModelBase
{
    private readonly MainViewModel _main;
    private AppSettings S => _main.Settings;

    public ScheduleViewModel(MainViewModel main)
    {
        _main = main;
        AddScheduleCommand = new RelayCommand(() => OpenScheduleEditor(null), () => CanEdit);
        EditScheduleCommand = new RelayCommand(p => OpenScheduleEditor(p as ScheduleRow), _ => CanEdit);
        DeleteScheduleCommand = new RelayCommand(p => DeleteSchedule(p as ScheduleRow), _ => CanEdit);
        SaveScheduleCommand = new RelayCommand(SaveSchedule, () => CanSaveSchedule);
        CancelScheduleCommand = new RelayCommand(() => ScheduleEditorVisible = false);

        NewTemplateCommand = new RelayCommand(() => OpenTemplateEditor(null), () => CanEdit);
        EditTemplateCommand = new RelayCommand(p => OpenTemplateEditor(p as StudyTemplate), _ => CanEdit);
        DeleteTemplateCommand = new RelayCommand(p => DeleteTemplate(p as StudyTemplate), _ => CanEdit);
        RestoreTemplatesCommand = new RelayCommand(RestoreTemplates, () => CanEdit);
        SaveTemplateCommand = new RelayCommand(SaveTemplate, () => CanEdit);
        CancelTemplateCommand = new RelayCommand(() => TemplateEditorVisible = false);

        Refresh();
    }

    /// <summary>The sleep window, exactly as before (Miles's Roadmap 3.7 reworks it in place).</summary>
    public SleepBlockingViewModel Sleep => _main.SleepBlocking;

    /// <summary>Raised when templates are added, renamed or removed, so Today's chips and the Jump List follow.</summary>
    public event EventHandler? TemplatesChanged;

    /// <summary>Sealed locks the blocklist for the sprint; schedules and templates follow the same rule.</summary>
    public bool CanEdit => !(_main.IsSprintRunning && _main.Blocker.ActiveShield == ShieldLevel.Sealed) && !_main.IsLocked;

    public ObservableCollection<ScheduleRow> Schedules { get; } = new();
    public ObservableCollection<StudyTemplate> Templates { get; } = new();

    private string _nextUpText = "";
    public string NextUpText { get => _nextUpText; private set => Set(ref _nextUpText, value); }

    private string _statusText = "";
    public string StatusText { get => _statusText; private set => Set(ref _statusText, value); }

    public void Refresh()
    {
        Templates.Clear();
        foreach (var t in S.Templates) Templates.Add(t);

        Schedules.Clear();
        foreach (var s in S.Schedules)
            Schedules.Add(new ScheduleRow(s, S.FindTemplate(s.TemplateId)?.Name ?? ""));

        NextUpText = BuildNextUp(DateTime.UtcNow, TimeZoneInfo.Local);
        Raise(nameof(CanEdit));
        Raise(nameof(HasSchedules));
    }

    public bool HasSchedules => Schedules.Count > 0;

    private string BuildNextUp(DateTime nowUtc, TimeZoneInfo zone)
    {
        var next = S.Schedules
            .Where(s => s.Enabled)
            .Select(s => (Schedule: s, At: ScheduleMatcher.NextStartUtc(s, nowUtc, zone)))
            .Where(x => x.At is not null)
            .OrderBy(x => x.At)
            .FirstOrDefault();
        if (next.Schedule is null) return "No schedules yet";
        var name = S.FindTemplate(next.Schedule.TemplateId)?.Name ?? "";
        return ScheduleText.NextUp(name,
            TimeZoneInfo.ConvertTimeFromUtc(next.At!.Value, zone),
            TimeZoneInfo.ConvertTimeFromUtc(nowUtc, zone));
    }

    // ------------------------------------------------------ schedule editor

    private SprintSchedule? _editingSchedule;

    private bool _scheduleEditorVisible;
    public bool ScheduleEditorVisible
    {
        get => _scheduleEditorVisible;
        private set { if (Set(ref _scheduleEditorVisible, value)) Raise(nameof(CanSaveSchedule)); }
    }

    private StudyTemplate? _editorTemplate;
    public StudyTemplate? EditorTemplate
    {
        get => _editorTemplate;
        set { if (Set(ref _editorTemplate, value)) Raise(nameof(CanSaveSchedule)); }
    }

    /// <summary>Mon..Sun chips, Monday first.</summary>
    public ObservableCollection<DayChoice> EditorDays { get; } = new();

    private string _editorTime = "17:00";
    public string EditorTime { get => _editorTime; set => Set(ref _editorTime, value); }

    private bool _editorAskFirst = true;
    public bool EditorAskFirst { get => _editorAskFirst; set => Set(ref _editorAskFirst, value); }

    public bool CanSaveSchedule =>
        CanEdit && ScheduleEditorVisible && EditorTemplate is not null && EditorDays.Any(d => d.IsChosen);

    private void OpenScheduleEditor(ScheduleRow? row)
    {
        _editingSchedule = row?.Schedule;
        EditorTemplate = row is null ? S.Templates.FirstOrDefault() : S.FindTemplate(row.Schedule.TemplateId);
        EditorTime = ScheduleText.Time(row?.Schedule.StartMinuteOfDay ?? 17 * 60);
        EditorAskFirst = row?.Schedule.AskFirst ?? true;

        EditorDays.Clear();
        foreach (var day in DayChoice.WeekOrder)
        {
            var choice = new DayChoice(day, row?.Schedule.Days.Contains(day) ?? false);
            choice.Changed += (_, _) => Raise(nameof(CanSaveSchedule));
            EditorDays.Add(choice);
        }
        StatusText = "";
        ScheduleEditorVisible = true;
    }

    private void SaveSchedule()
    {
        if (!CanSaveSchedule || EditorTemplate is null) return;
        if (!SleepBlockingViewModel.TryParse(EditorTime, out var time))
        {
            StatusText = $"\"{EditorTime}\" isn't a valid time. Use HH:mm, e.g. 17:00.";
            return;
        }

        var schedule = _editingSchedule ?? new SprintSchedule();
        schedule.TemplateId = EditorTemplate.Id;
        schedule.Days = EditorDays.Where(d => d.IsChosen).Select(d => d.Day).ToList();
        schedule.StartMinuteOfDay = (int)time.TotalMinutes;
        schedule.AskFirst = EditorAskFirst;
        schedule.Normalize();
        if (_editingSchedule is null) S.Schedules.Add(schedule);

        _main.SaveSettings();
        ScheduleEditorVisible = false;
        Refresh();
        _main.Toast("Schedule saved.");
        Log.Info($"schedule saved: {EditorTemplate.Name} {ScheduleText.Days(schedule.Days)} {ScheduleText.Time(schedule.StartMinuteOfDay)}");
    }

    private void DeleteSchedule(ScheduleRow? row)
    {
        if (row is null || !CanEdit) return;
        S.Schedules.Remove(row.Schedule);
        _main.SaveSettings();
        Refresh();
        Log.Info("schedule deleted");
    }

    /// <summary>The row's on/off switch.</summary>
    public void SetScheduleEnabled(ScheduleRow row, bool enabled)
    {
        if (!CanEdit) { row.RaiseEnabled(); return; }
        row.Schedule.Enabled = enabled;
        _main.SaveSettings();
        NextUpText = BuildNextUp(DateTime.UtcNow, TimeZoneInfo.Local);
    }

    // ------------------------------------------------------ template editor

    private StudyTemplate? _editingTemplate;

    private bool _templateEditorVisible;
    public bool TemplateEditorVisible { get => _templateEditorVisible; private set => Set(ref _templateEditorVisible, value); }

    private string _templateName = "";
    public string TemplateName { get => _templateName; set => Set(ref _templateName, value); }

    private string _templateMinutes = "25";
    public string TemplateMinutes { get => _templateMinutes; set => Set(ref _templateMinutes, value); }

    private ShieldLevel _templateShield = ShieldLevel.Firm;
    public ShieldLevel TemplateShield { get => _templateShield; set => Set(ref _templateShield, value); }

    private int _templateCycle;
    public int TemplateCycle { get => _templateCycle; set => Set(ref _templateCycle, value); }

    private string _templateBreak = "5";
    public string TemplateBreak { get => _templateBreak; set => Set(ref _templateBreak, value); }

    private BlocklistProfile? _templateProfile;
    /// <summary>Null means "whichever profile is active".</summary>
    public BlocklistProfile? TemplateProfile { get => _templateProfile; set => Set(ref _templateProfile, value); }

    public IReadOnlyList<BlocklistProfile> Profiles => S.Profiles;
    public int[] CycleChoices { get; } = CycleState.CycleChoices;

    private void OpenTemplateEditor(StudyTemplate? template)
    {
        _editingTemplate = template;
        TemplateName = template?.Name ?? "";
        TemplateMinutes = (template?.SprintMinutes ?? 25).ToString();
        TemplateShield = template?.Shield ?? ShieldLevel.Firm;
        TemplateCycle = template?.CycleSprints ?? 0;
        TemplateBreak = (template?.BreakMinutes ?? CycleState.DefaultShortBreakMinutes).ToString();
        TemplateProfile = template is null ? null : S.FindProfile(template.ProfileId);
        Raise(nameof(Profiles));
        StatusText = "";
        TemplateEditorVisible = true;
    }

    private void SaveTemplate()
    {
        if (!int.TryParse(TemplateMinutes, out var minutes)
            || minutes < StudyTemplate.MinSprintMinutes || minutes > StudyTemplate.MaxSprintMinutes)
        {
            StatusText = $"Sprint length must be {StudyTemplate.MinSprintMinutes}–{StudyTemplate.MaxSprintMinutes} minutes.";
            return;
        }
        if (!int.TryParse(TemplateBreak, out var breakMinutes)
            || breakMinutes < CycleState.MinBreakMinutes || breakMinutes > CycleState.MaxBreakMinutes)
        {
            StatusText = $"Breaks must be {CycleState.MinBreakMinutes}–{CycleState.MaxBreakMinutes} minutes.";
            return;
        }

        var template = _editingTemplate ?? new StudyTemplate();
        template.Name = TemplateName;
        template.SprintMinutes = minutes;
        template.Shield = TemplateShield;
        template.CycleSprints = TemplateCycle;
        template.BreakMinutes = breakMinutes;
        template.ProfileId = TemplateProfile?.Id ?? "";
        template.Normalize();
        if (_editingTemplate is null) S.Templates.Add(template);

        _main.SaveSettings();
        TemplateEditorVisible = false;
        Refresh();
        TemplatesChanged?.Invoke(this, EventArgs.Empty);
        _main.Toast($"{template.Name} saved.");
    }

    private void DeleteTemplate(StudyTemplate? template)
    {
        if (template is null || !CanEdit) return;
        var using_ = S.SchedulesUsing(template.Id).Count;
        var question = using_ == 0
            ? $"Delete {template.Name}?"
            : $"Delete {template.Name} and {(using_ == 1 ? "1 schedule" : $"{using_} schedules")} that start it?";
        if (!_main.Confirm(question, "Delete")) return;

        S.DeleteTemplate(template.Id);
        _main.SaveSettings();
        Refresh();
        TemplatesChanged?.Invoke(this, EventArgs.Empty);
        Log.Info($"template deleted: {template.Name}, with {using_} schedule(s)");
    }

    private void RestoreTemplates()
    {
        var added = S.RestoreBuiltInTemplates();
        if (added > 0) _main.SaveSettings();
        Refresh();
        TemplatesChanged?.Invoke(this, EventArgs.Empty);
        _main.Toast(added == 0 ? "All three built-in templates are already here."
                               : $"Restored {(added == 1 ? "1 template" : $"{added} templates")}.");
    }
}

/// <summary>One row on the Schedule page.</summary>
public class ScheduleRow : ViewModelBase
{
    public ScheduleRow(SprintSchedule schedule, string templateName)
    {
        Schedule = schedule;
        TemplateName = templateName;
    }

    public SprintSchedule Schedule { get; }
    public string Id => Schedule.Id;
    public string TemplateName { get; }

    /// <summary>"Homework evening · Mon–Thu · 17:00 · asks first".</summary>
    public string Summary =>
        $"{TemplateName} · {ScheduleText.Days(Schedule.Days)} · {ScheduleText.Time(Schedule.StartMinuteOfDay)}"
        + (Schedule.AskFirst ? " · asks first" : "");

    public bool Enabled => Schedule.Enabled;
    public void RaiseEnabled() => Raise(nameof(Enabled));
}

/// <summary>One day chip in the schedule editor.</summary>
public class DayChoice : ViewModelBase
{
    public static readonly DayOfWeek[] WeekOrder =
    {
        DayOfWeek.Monday, DayOfWeek.Tuesday, DayOfWeek.Wednesday, DayOfWeek.Thursday,
        DayOfWeek.Friday, DayOfWeek.Saturday, DayOfWeek.Sunday,
    };

    public DayChoice(DayOfWeek day, bool chosen)
    {
        Day = day;
        _isChosen = chosen;
    }

    public DayOfWeek Day { get; }
    public string Label => System.Globalization.CultureInfo.InvariantCulture.DateTimeFormat.GetAbbreviatedDayName(Day);

    public event EventHandler? Changed;

    private bool _isChosen;
    public bool IsChosen
    {
        get => _isChosen;
        set { if (Set(ref _isChosen, value)) Changed?.Invoke(this, EventArgs.Empty); }
    }
}
```

Before writing, confirm three things in the code: that `ViewModelBase` has `Set(ref field, value)` returning bool and `Raise(string?)` (read `Infrastructure/ViewModelBase.cs`); that `RelayCommand` has both `(Action, Func<bool>?)` and `(Action<object?>, Func<object?, bool>?)` constructors (read `Infrastructure/RelayCommand.cs`); and whether `MainViewModel` already has a yes/no confirmation helper. **If `Confirm` doesn't exist**, add it to `MainViewModel`, mirroring how `BlockedAppsViewModel` confirms profile deletion (search it for `ConfirmDeleteDialog` or `MessageBox`) and reusing that same dialog:

```csharp
    /// <summary>A yes/no question with a named destructive button. Used by pages that delete things.</summary>
    public bool Confirm(string question, string confirmLabel) =>
        Views.ConfirmDeleteDialog.Ask(App.Current.MainWindow, question, confirmLabel);
```

If `ConfirmDeleteDialog` has no static `Ask`, call it the way its existing caller does.

- [ ] **Step 5: Write `DesktopApp/Views/ScheduleView.xaml`** and its code-behind. The code-behind is `public partial class ScheduleView : UserControl { public ScheduleView() => InitializeComponent(); }` plus one handler for the row switch:

```csharp
    private void OnScheduleEnabledClick(object sender, RoutedEventArgs e)
    {
        if (sender is CheckBox { DataContext: ScheduleRow row } box && DataContext is ScheduleViewModel vm)
            vm.SetScheduleEnabled(row, box.IsChecked == true);
    }
```

The XAML (it follows `SleepBlockingView.xaml`'s structure; use the same `xmlns`, plus `xmlns:views="clr-namespace:FlowShield.Views"` and `xmlns:models="clr-namespace:FlowShield.Models"`):

```xml
<UserControl x:Class="FlowShield.Views.ScheduleView"
             xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
             xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
             xmlns:inf="clr-namespace:FlowShield.Infrastructure"
             xmlns:views="clr-namespace:FlowShield.Views"
             xmlns:models="clr-namespace:FlowShield.Models">
    <!-- The Schedule page (F6). Schedules first, then templates, then the
         sleep window embedded unchanged: SleepBlockingView keeps every one
         of its AutomationIds, and Roadmap 3.7 reworks it in place. -->
    <ScrollViewer VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Disabled">
        <StackPanel Margin="0,0,8,0">

            <TextBlock Text="{Binding NextUpText}" Style="{StaticResource H2}" Margin="0,0,0,16"
                       AutomationProperties.AutomationId="ScheduleNextUpText"/>

            <inf:AdaptiveColumns MinColumnWidth="400" MaxColumns="2" Spacing="16">

                <!-- your schedules -->
                <Border Style="{StaticResource Card}" Padding="24">
                    <StackPanel>
                        <TextBlock Text="YOUR SCHEDULES" Style="{StaticResource Eyebrow}" Margin="0,0,0,12"/>
                        <TextBlock Text="A template starts by itself at the time you pick. By default FlowShield asks five minutes before."
                                   Style="{StaticResource Caption}" TextWrapping="Wrap" Margin="0,0,0,12"/>

                        <ItemsControl ItemsSource="{Binding Schedules}">
                            <ItemsControl.ItemTemplate>
                                <DataTemplate>
                                    <Grid Margin="0,0,0,8">
                                        <Grid.ColumnDefinitions>
                                            <ColumnDefinition Width="Auto"/>
                                            <ColumnDefinition Width="*"/>
                                            <ColumnDefinition Width="Auto"/>
                                            <ColumnDefinition Width="Auto"/>
                                        </Grid.ColumnDefinitions>
                                        <CheckBox Grid.Column="0" Style="{StaticResource Switch}" VerticalAlignment="Center"
                                                  IsChecked="{Binding Enabled, Mode=OneWay}" Click="OnScheduleEnabledClick"
                                                  IsEnabled="{Binding DataContext.CanEdit, RelativeSource={RelativeSource AncestorType=ItemsControl}}"
                                                  AutomationProperties.AutomationId="{Binding Id, StringFormat=ScheduleEnabled_{0}}"
                                                  AutomationProperties.Name="{Binding TemplateName, StringFormat=Turn the {0} schedule on or off}"/>
                                        <TextBlock Grid.Column="1" Text="{Binding Summary}" Style="{StaticResource Body}"
                                                   TextWrapping="Wrap" VerticalAlignment="Center" Margin="12,0,12,0"
                                                   AutomationProperties.AutomationId="{Binding Id, StringFormat=ScheduleRow_{0}}"/>
                                        <Button Grid.Column="2" Style="{StaticResource BtnQuiet}" Content="Edit"
                                                Command="{Binding DataContext.EditScheduleCommand, RelativeSource={RelativeSource AncestorType=ItemsControl}}"
                                                CommandParameter="{Binding}"
                                                AutomationProperties.AutomationId="{Binding Id, StringFormat=EditSchedule_{0}}"
                                                AutomationProperties.Name="{Binding TemplateName, StringFormat=Edit the {0} schedule}"/>
                                        <Button Grid.Column="3" Style="{StaticResource BtnQuiet}" Content="Delete" Margin="8,0,0,0"
                                                Command="{Binding DataContext.DeleteScheduleCommand, RelativeSource={RelativeSource AncestorType=ItemsControl}}"
                                                CommandParameter="{Binding}"
                                                AutomationProperties.AutomationId="{Binding Id, StringFormat=DeleteSchedule_{0}}"
                                                AutomationProperties.Name="{Binding TemplateName, StringFormat=Delete the {0} schedule}"/>
                                    </Grid>
                                </DataTemplate>
                            </ItemsControl.ItemTemplate>
                        </ItemsControl>

                        <Button Style="{StaticResource BtnGhost}" Content="Add schedule" HorizontalAlignment="Left"
                                Margin="0,8,0,0" Command="{Binding AddScheduleCommand}"
                                AutomationProperties.AutomationId="AddScheduleButton"/>

                        <!-- editor -->
                        <StackPanel Margin="0,16,0,0"
                                    Visibility="{Binding ScheduleEditorVisible, Converter={StaticResource BoolVis}}">
                            <TextBlock Text="TEMPLATE" Style="{StaticResource Eyebrow}" Margin="0,0,0,8"/>
                            <ItemsControl ItemsSource="{Binding Templates}">
                                <ItemsControl.ItemsPanel><ItemsPanelTemplate><WrapPanel/></ItemsPanelTemplate></ItemsControl.ItemsPanel>
                                <ItemsControl.ItemTemplate>
                                    <DataTemplate>
                                        <RadioButton Style="{StaticResource Segment}" GroupName="ScheduleTemplate" Margin="0,0,8,8"
                                                     Content="{Binding Name}"
                                                     Checked="OnEditorTemplateChecked"
                                                     AutomationProperties.AutomationId="{Binding Name, StringFormat=ScheduleTemplate_{0}}"/>
                                    </DataTemplate>
                                </ItemsControl.ItemTemplate>
                            </ItemsControl>

                            <TextBlock Text="DAYS" Style="{StaticResource Eyebrow}" Margin="0,8,0,8"/>
                            <ItemsControl ItemsSource="{Binding EditorDays}">
                                <ItemsControl.ItemsPanel><ItemsPanelTemplate><WrapPanel/></ItemsPanelTemplate></ItemsControl.ItemsPanel>
                                <ItemsControl.ItemTemplate>
                                    <DataTemplate>
                                        <CheckBox Style="{StaticResource SegmentCheck}" Margin="0,0,8,8"
                                                  Content="{Binding Label}" IsChecked="{Binding IsChosen}"
                                                  AutomationProperties.AutomationId="{Binding Label, StringFormat=ScheduleDay_{0}}"/>
                                    </DataTemplate>
                                </ItemsControl.ItemTemplate>
                            </ItemsControl>

                            <TextBlock Text="Starts" Style="{StaticResource Caption}" Margin="4,8,0,8"/>
                            <TextBox Style="{StaticResource Field}" Width="112" HorizontalAlignment="Left"
                                     Text="{Binding EditorTime, UpdateSourceTrigger=PropertyChanged}"
                                     AutomationProperties.AutomationId="ScheduleTimeInput"
                                     AutomationProperties.Name="Schedule start time"/>

                            <CheckBox Style="{StaticResource Switch}" Margin="0,16,0,0" IsChecked="{Binding EditorAskFirst}"
                                      AutomationProperties.AutomationId="ScheduleAskFirstToggle"
                                      AutomationProperties.Name="Ask five minutes before">
                                <TextBlock Text="Ask five minutes before" Style="{StaticResource Body}"/>
                            </CheckBox>

                            <StackPanel Orientation="Horizontal" Margin="0,16,0,0">
                                <Button Style="{StaticResource BtnPrimary}" Content="Save schedule"
                                        Command="{Binding SaveScheduleCommand}"
                                        AutomationProperties.AutomationId="SaveScheduleButton"/>
                                <Button Style="{StaticResource BtnQuiet}" Content="Cancel" Margin="12,0,0,0"
                                        Command="{Binding CancelScheduleCommand}"
                                        AutomationProperties.AutomationId="CancelScheduleButton"/>
                            </StackPanel>
                        </StackPanel>

                        <TextBlock Text="{Binding StatusText}" Style="{StaticResource Caption}" TextWrapping="Wrap"
                                   Margin="0,12,0,0" AutomationProperties.AutomationId="ScheduleStatusText"/>
                    </StackPanel>
                </Border>

                <!-- templates -->
                <Border Style="{StaticResource Card}" Padding="24">
                    <StackPanel>
                        <TextBlock Text="TEMPLATES" Style="{StaticResource Eyebrow}" Margin="0,0,0,12"/>
                        <ItemsControl ItemsSource="{Binding Templates}">
                            <ItemsControl.ItemTemplate>
                                <DataTemplate>
                                    <Grid Margin="0,0,0,8">
                                        <Grid.ColumnDefinitions>
                                            <ColumnDefinition Width="*"/>
                                            <ColumnDefinition Width="Auto"/>
                                            <ColumnDefinition Width="Auto"/>
                                        </Grid.ColumnDefinitions>
                                        <TextBlock Grid.Column="0" Text="{Binding Name}" Style="{StaticResource Body}"
                                                   VerticalAlignment="Center"
                                                   AutomationProperties.AutomationId="{Binding Name, StringFormat=TemplateRow_{0}}"/>
                                        <Button Grid.Column="1" Style="{StaticResource BtnQuiet}" Content="Edit"
                                                Command="{Binding DataContext.EditTemplateCommand, RelativeSource={RelativeSource AncestorType=ItemsControl}}"
                                                CommandParameter="{Binding}"
                                                AutomationProperties.AutomationId="{Binding Name, StringFormat=EditTemplate_{0}}"/>
                                        <Button Grid.Column="2" Style="{StaticResource BtnQuiet}" Content="Delete" Margin="8,0,0,0"
                                                Command="{Binding DataContext.DeleteTemplateCommand, RelativeSource={RelativeSource AncestorType=ItemsControl}}"
                                                CommandParameter="{Binding}"
                                                AutomationProperties.AutomationId="{Binding Name, StringFormat=DeleteTemplate_{0}}"/>
                                    </Grid>
                                </DataTemplate>
                            </ItemsControl.ItemTemplate>
                        </ItemsControl>

                        <StackPanel Orientation="Horizontal" Margin="0,8,0,0">
                            <Button Style="{StaticResource BtnGhost}" Content="New template"
                                    Command="{Binding NewTemplateCommand}"
                                    AutomationProperties.AutomationId="NewTemplateButton"/>
                            <Button Style="{StaticResource BtnQuiet}" Content="Restore built-ins" Margin="12,0,0,0"
                                    Command="{Binding RestoreTemplatesCommand}"
                                    AutomationProperties.AutomationId="RestoreTemplatesButton"/>
                        </StackPanel>

                        <!-- template editor -->
                        <StackPanel Margin="0,16,0,0"
                                    Visibility="{Binding TemplateEditorVisible, Converter={StaticResource BoolVis}}">
                            <TextBlock Text="Name" Style="{StaticResource Caption}" Margin="4,0,0,8"/>
                            <TextBox Style="{StaticResource Field}" Text="{Binding TemplateName, UpdateSourceTrigger=PropertyChanged}"
                                     MaxLength="40" AutomationProperties.AutomationId="TemplateNameInput"
                                     AutomationProperties.Name="Template name"/>
                            <TextBlock Text="Sprint minutes" Style="{StaticResource Caption}" Margin="4,12,0,8"/>
                            <TextBox Style="{StaticResource Field}" Width="112" HorizontalAlignment="Left"
                                     Text="{Binding TemplateMinutes, UpdateSourceTrigger=PropertyChanged}"
                                     AutomationProperties.AutomationId="TemplateMinutesInput"
                                     AutomationProperties.Name="Sprint minutes"/>
                            <TextBlock Text="SHIELD" Style="{StaticResource Eyebrow}" Margin="0,12,0,8"/>
                            <WrapPanel>
                                <RadioButton Style="{StaticResource Segment}" GroupName="TemplateShield" Content="Soft" Margin="0,0,8,8"
                                             IsChecked="{Binding TemplateShield, Converter={StaticResource EnumEquals}, ConverterParameter={x:Static models:ShieldLevel.Soft}}"
                                             AutomationProperties.AutomationId="TemplateShield_Soft"/>
                                <RadioButton Style="{StaticResource Segment}" GroupName="TemplateShield" Content="Firm" Margin="0,0,8,8"
                                             IsChecked="{Binding TemplateShield, Converter={StaticResource EnumEquals}, ConverterParameter={x:Static models:ShieldLevel.Firm}}"
                                             AutomationProperties.AutomationId="TemplateShield_Firm"/>
                                <RadioButton Style="{StaticResource Segment}" GroupName="TemplateShield" Content="Sealed" Margin="0,0,8,8"
                                             IsChecked="{Binding TemplateShield, Converter={StaticResource EnumEquals}, ConverterParameter={x:Static models:ShieldLevel.Sealed}}"
                                             AutomationProperties.AutomationId="TemplateShield_Sealed"/>
                            </WrapPanel>
                            <TextBlock Text="SPRINTS IN A ROW" Style="{StaticResource Eyebrow}" Margin="0,8,0,8"/>
                            <ItemsControl ItemsSource="{Binding CycleChoices}">
                                <ItemsControl.ItemsPanel><ItemsPanelTemplate><WrapPanel/></ItemsPanelTemplate></ItemsControl.ItemsPanel>
                                <ItemsControl.ItemTemplate>
                                    <DataTemplate>
                                        <RadioButton Style="{StaticResource Segment}" GroupName="TemplateCycle" Margin="0,0,8,8"
                                                     Content="{Binding Converter={StaticResource CycleLabel}}"
                                                     Checked="OnTemplateCycleChecked"
                                                     AutomationProperties.AutomationId="{Binding StringFormat=TemplateCycle_{0}}"/>
                                    </DataTemplate>
                                </ItemsControl.ItemTemplate>
                            </ItemsControl>
                            <TextBlock Text="Break minutes" Style="{StaticResource Caption}" Margin="4,8,0,8"/>
                            <TextBox Style="{StaticResource Field}" Width="112" HorizontalAlignment="Left"
                                     Text="{Binding TemplateBreak, UpdateSourceTrigger=PropertyChanged}"
                                     AutomationProperties.AutomationId="TemplateBreakInput"
                                     AutomationProperties.Name="Break minutes"/>
                            <StackPanel Orientation="Horizontal" Margin="0,16,0,0">
                                <Button Style="{StaticResource BtnPrimary}" Content="Save template"
                                        Command="{Binding SaveTemplateCommand}"
                                        AutomationProperties.AutomationId="SaveTemplateButton"/>
                                <Button Style="{StaticResource BtnQuiet}" Content="Cancel" Margin="12,0,0,0"
                                        Command="{Binding CancelTemplateCommand}"
                                        AutomationProperties.AutomationId="CancelTemplateButton"/>
                            </StackPanel>
                        </StackPanel>
                    </StackPanel>
                </Border>
            </inf:AdaptiveColumns>

            <TextBlock Text="SLEEP WINDOW" Style="{StaticResource Eyebrow}" Margin="0,24,0,12"/>
            <views:SleepBlockingView DataContext="{Binding Sleep}"/>
        </StackPanel>
    </ScrollViewer>
</UserControl>
```

Converters: find out how `TodayView.xaml` binds its shield `SegmentShield` radio buttons and its cycle chooser (`CycleChoices`) to the view model (grep `SelectedShield` and `CycleChoices` in `TodayView.xaml`), and **use exactly the same binding pattern** in place of the `EnumEquals` and `CycleLabel` converters written above, which may not exist. If Today uses commands, add matching commands (`SelectTemplateShieldCommand`, `SelectTemplateCycleCommand`) to `ScheduleViewModel`. The template-profile chips use the same pattern as Today's `TodayProfile_{Name}` radio buttons, with the id `TemplateProfile_{Name}` plus one "Active profile" choice (`TemplateProfile_Active`) that sets `TemplateProfile = null`. The code-behind `Checked` handlers set `vm.EditorTemplate` and `vm.TemplateCycle` from the sender's `DataContext`, the same way `OnScheduleEnabledClick` works.

- [ ] **Step 6: Wire it into the shell**
  - `MainViewModel`: add `public ScheduleViewModel Schedule { get; }` and construct it right after `SleepBlocking = new SleepBlockingViewModel(this);` with `Schedule = new ScheduleViewModel(this);`. In `CurrentPageTitle`, change `AppPage.SleepBlocking => "Sleep Blocking"` to `"Schedule"`. Its subtitle becomes `"Templates that start by themselves, and your nightly window."`. In the `CurrentPage` setter's switch, the `AppPage.SleepBlocking` case calls `SleepBlocking.RefreshStatus(); Schedule.Refresh();`. In `OnTierChanged` (line ~409), add `Schedule.Refresh();` after `SleepBlocking.OnTierChanged();`. In `OnSprintStateChanged`, add `Schedule?.Refresh();` so `CanEdit` follows a Sealed sprint. The `?.` matters: `OnSprintStateChanged` can run while the constructor is still building the page view models.
  - `MainWindow.xaml:133` `AutomationProperties.Name="Schedule"`; `:136` `Text="Schedule"` (keep `x:Name="NavSleepBlockingLabel"`); the icon stays `IconSleep`.
  - `MainWindow.xaml:185` replaces `<views:SleepBlockingView DataContext="{Binding SleepBlocking}" .../>` with `<views:ScheduleView DataContext="{Binding Schedule}" .../>`, keeping the same `Visibility` binding.
  - Update the comment at `MainWindow.xaml:23-25` to read "Schedule" where it lists "Sleep Blocking".
  - Grep `automation/` for other `"Sleep Blocking"` title expectations (`grep -rn "Sleep Blocking" automation`) and change the ones that compare the **page title** to `"Schedule"`. Leave comments and the `SleepBlockingView` references alone.

- [ ] **Step 7: Build, run and watch them pass**

Run: `cd DesktopApp; dotnet build -c Release -nologo` — 0 errors, 0 new warnings.
Run: `python -m pytest automation/tests/test_tier5_regressions.py -k "SchedulePageKeeps" -q` — pass.
Run (UI lock): `python -m pytest automation/tests/test_tier3_e2e.py -k "SchedulePage or TestAppShell or Sleep" -q` — pass.
Run: `python -m pytest automation/tests -m "not ui and not stripe" -q` — pass.

- [ ] **Step 8: Screenshots** — launch with `python -m automation.smoke_ui` or the capture kit, or start the app by hand and take a screenshot of the Schedule page in dark and light themes, with the schedule editor open and with one saved schedule. Save them under `screenshots/1.0.10/` (git-ignored) for the PR.

- [ ] **Step 9: Commit and open PR A**

```bash
git add DesktopApp automation
git commit -m "F6: the Schedule page, with the sleep window kept as it was

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -u origin feat/f6-templates-schedule-page
```

Open the PR with `Closes #<A>`, the template filled in, screenshots, and a line saying it must not merge before v1.0.9. No changelog line yet: nothing starts by itself until PR C, and a line now would claim a feature 1.0.10 might not ship.

---

# PR B — Soft friction

### Task 6: The Soft rules — tries, the growing wait, turned back, wording

**Files:**
- Modify: `DesktopApp/Models/SoftOverlayPolicy.cs`
- Modify: `DesktopApp/App.xaml.cs:36-42` (short timers)
- Modify: `DesktopApp/Services/AppBlockerService.cs` (add `AskToClose`)
- Modify: `automation/csharp/ModelProbe/Commands.cs`
- Test: `automation/tests/test_tier1_unit.py` (extend the Python mirror class and `TestSoftOverlayPolicy`), `automation/tests/test_tier5_regressions.py`

**Interfaces:**
- Produces on `SoftOverlayPolicy`:
  - `int Tries { get; }` — notices shown this sprint, across all apps
  - `int TurnedBack { get; }`
  - `void CloseIt(string displayName, DateTime nowUtc)` — counts as turned back and goes quiet like Back to work
  - `BackToWork` now also counts as turned back
  - `static TimeSpan AllowWait(int tryNumber)` — 5/10/20/30 s, or 1 s under `UseShortTimers`
  - `static bool UseShortTimers { get; set; }`
  - `Reset()` also zeroes `Tries` and `TurnedBack`
- Produces on `SoftOverlayCopy`:
  - `static string Sentence(string displayName, DateTime endsAtLocal, int tryNumber)` — four wordings; try 1 is the existing sentence
  - `static string TryLine(int tryNumber)` — "1st try this sprint", "2nd try this sprint", …
  - `static string Intention(string intention)` — "You planned: {intention}" or ""
  - `static string AllowLabel(TimeSpan left)` — "Allow 5 minutes · 0:08", or "Allow 5 minutes" at zero
  - `const string CloseNote = "Nothing is closed unless you choose to."`
- Produces on `AppBlockerService`: `int AskToClose(string displayName, AppSettings settings)` — calls `CloseMainWindow` on every running process of that enabled app in the active profile, skipping critical processes; never kills; returns how many were asked.

- [ ] **Step 1: Write the failing tests** — add probe tests in `test_tier1_unit.py` after `TestSoftOverlayPolicy`:

```python
class TestSoftFriction:
    """
    1.0.10: the one sec study (PNAS 2023) found the 'don't open it' choice did
    the most and a wait helped; fixed friction fades within weeks. So: Close
    first, a wait before Allow that grows with each try, varied wording.
    """

    def test_tries_count_every_notice_this_sprint_across_apps(self):
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0}, {"op": "left"},
            {"op": "show", "app": "Steam", "at": 10}, {"op": "left"},
            {"op": "show", "app": "Discord", "at": 20},
            {"op": "tries"},
        ]})
        assert out["results"][-1] == 3

    @pytest.mark.parametrize("try_number,seconds", [(1, 5), (2, 10), (3, 20), (4, 30), (9, 30)])
    def test_the_wait_before_allow_grows(self, try_number, seconds):
        assert probe({"cmd": "soft-wait", "try": try_number})["seconds"] == seconds

    def test_short_timers_make_every_wait_one_second(self):
        assert probe({"cmd": "soft-wait", "try": 4, "short": True})["seconds"] == 1

    def test_close_and_back_to_work_count_as_turned_back_and_allow_does_not(self):
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0}, {"op": "close", "app": "Discord", "at": 1},
            {"op": "left"},
            {"op": "show", "app": "Steam", "at": 30}, {"op": "back", "app": "Steam", "at": 31},
            {"op": "left"},
            {"op": "show", "app": "Discord", "at": 60}, {"op": "allow", "app": "Discord", "at": 61},
            {"op": "turned"},
        ]})
        assert out["results"][-1] == 2

    def test_close_goes_quiet_like_back_to_work(self):
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0}, {"op": "close", "app": "Discord", "at": 0},
            {"op": "show", "app": "Discord", "at": 1}, {"op": "left"},
            {"op": "show", "app": "Discord", "at": 30},
        ]})
        assert out["results"][2] is False and out["results"][4] is True

    def test_a_new_sprint_starts_counting_again(self):
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0}, {"op": "back", "app": "Discord", "at": 0},
            {"op": "reset"}, {"op": "tries"}, {"op": "turned"},
        ]})
        assert out["results"][-2:] == [0, 0]

    @pytest.mark.parametrize("n,line", [(1, "1st try this sprint"), (2, "2nd try this sprint"),
                                        (3, "3rd try this sprint"), (4, "4th try this sprint"),
                                        (11, "11th try this sprint"), (12, "12th try this sprint"),
                                        (13, "13th try this sprint"), (21, "21st try this sprint"),
                                        (22, "22nd try this sprint")])
    def test_the_try_line(self, n, line):
        assert probe({"cmd": "soft-copy", "try": n})["try_line"] == line

    def test_the_first_sentence_is_the_design_systems_own_example(self):
        out = probe({"cmd": "soft-copy", "try": 1, "app": "Discord", "ends": "2026-09-28T17:45:00"})
        assert out["sentence"].startswith("Discord is on your blocklist until")

    def test_the_wording_varies_across_four_tries_and_then_repeats(self):
        sentences = [probe({"cmd": "soft-copy", "try": n, "app": "Discord",
                            "ends": "2026-09-28T17:45:00"})["sentence"] for n in range(1, 6)]
        assert len(set(sentences[:4])) == 4 and sentences[4] == sentences[0]
        assert all("Discord" in s or "this time" in s for s in sentences)

    @pytest.mark.parametrize("seconds,label", [(8, "Allow 5 minutes · 0:08"),
                                               (30, "Allow 5 minutes · 0:30"),
                                               (0, "Allow 5 minutes")])
    def test_the_allow_button_counts_down_in_text(self, seconds, label):
        assert probe({"cmd": "soft-copy", "try": 1, "allow_left": seconds})["allow_label"] == label

    def test_an_empty_intention_shows_nothing(self):
        assert probe({"cmd": "soft-copy", "try": 1, "intention": "  "})["intention"] == ""
        assert probe({"cmd": "soft-copy", "try": 1, "intention": "finish chapter 3"})["intention"] \
            == "You planned: finish chapter 3"
```

Change the existing tier 1 source pin `test_the_policy_decides_nothing_about_closing_anything`: it stays as it is. The **policy** still mentions no `Process`, `Kill(` or `CloseMainWindow(`, because closing lives in `AppBlockerService.AskToClose`.

Update the Python mirror class `SoftOverlayPolicy` in tier 1 (it's used by the older tests): add `tries` and `turned_back` counters, increment `tries` when `should_show` returns True, increment `turned_back` in `back_to_work` and a new `close_it`, and zero both in `reset`, so the mirror keeps matching the C#.

In `test_tier5_regressions.py`, append:

```python
class TestSoftCloseNeverKills:
    """
    1.0.10 gives Soft a Close button. Soft still never closes anything on its
    own, and a user-chosen close asks politely (CloseMainWindow) and never kills,
    so the app's own "save changes?" prompt still appears.
    """

    BLOCKER = Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs"

    def _ask_to_close(self) -> str:
        source = self.BLOCKER.read_text(encoding="utf-8")
        assert "public int AskToClose(string displayName, AppSettings settings)" in source
        return source.split("public int AskToClose(", 1)[1].split("\n    }", 1)[0]

    def test_it_only_asks(self):
        body = self._ask_to_close()
        assert "CloseMainWindow()" in body
        for forbidden in ("Kill(", "KillAll(", "_closingAt["):
            assert forbidden not in body, f"AskToClose must never {forbidden}"

    def test_it_never_touches_a_critical_process(self):
        assert "CriticalProcesses.Contains(" in self._ask_to_close()

    def test_it_is_only_reached_from_the_close_button(self):
        callers = [p for p in Path(DESKTOP_DIR).rglob("*.cs")
                   if "AskToClose(" in p.read_text(encoding="utf-8")]
        names = sorted(p.name for p in callers)
        assert names == ["AppBlockerService.cs", "MainViewModel.cs"], names

    def test_the_sweep_still_closes_nothing_at_soft(self):
        source = self.BLOCKER.read_text(encoding="utf-8")
        soft = source.split("if (!terminate)", 1)[1].split("continue;", 1)[0]
        assert "AskToClose" not in soft
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest automation/tests/test_tier1_unit.py -k "SoftFriction or SoftOverlayPolicy" automation/tests/test_tier5_regressions.py -k SoftCloseNeverKills -q`
Expected: FAIL (unknown ops and commands; `AskToClose` missing).

- [ ] **Step 3: Extend `SoftOverlayPolicy`.** Add these members to the class:

```csharp
    /// <summary>Set by --short-timers so the UI suite isn't waiting thirty seconds.</summary>
    public static bool UseShortTimers { get; set; }

    /// <summary>
    /// The wait before "Allow 5 minutes" can be pressed: 5, 10, 20, then 30
    /// seconds for every later try this sprint. A wait helped in the one sec
    /// study; one that grows keeps it from going stale.
    /// </summary>
    public static TimeSpan AllowWait(int tryNumber)
    {
        if (UseShortTimers) return TimeSpan.FromSeconds(1);
        return TimeSpan.FromSeconds(tryNumber switch
        {
            <= 1 => 5,
            2 => 10,
            3 => 20,
            _ => 30,
        });
    }

    /// <summary>Notices shown this sprint, across every app. The try number of the one on screen.</summary>
    public int Tries { get; private set; }

    /// <summary>Close or Back to work, this sprint. Allow doesn't count.</summary>
    public int TurnedBack { get; private set; }

    /// <summary>"Close ‹app›": the user chose to close it. Counts as turned back and goes quiet like Back to work.</summary>
    public void CloseIt(string displayName, DateTime nowUtc)
    {
        TurnedBack++;
        Quieten(displayName, nowUtc, BackToWorkQuiet);
    }
```

In `ShouldShow`, replace `_showing = true; return true;` with:

```csharp
        _showing = true;
        Tries++;
        return true;
```

`BackToWork` becomes a block body:

```csharp
    public void BackToWork(string displayName, DateTime nowUtc)
    {
        TurnedBack++;
        Quieten(displayName, nowUtc, BackToWorkQuiet);
    }
```

In `Reset()`, add `Tries = 0;` and `TurnedBack = 0;`. Update the class summary: "Soft closes nothing on its own; the Close button is the user's choice, carried out by `AppBlockerService.AskToClose`." The tier 1 source pin `test_each_answer_maps_to_its_own_window` asserts the expression-bodied `BackToWork`; change that assertion to check `TurnedBack++;` and `Quieten(displayName, nowUtc, BackToWorkQuiet);` inside the `BackToWork` body.

Extend `SoftOverlayCopy`:

```csharp
    /// <summary>
    /// Four calm ways to say the same thing, chosen by the try number so the
    /// notice doesn't go stale (habituation fades fixed friction). Try 1 is
    /// DESIGN_SYSTEM.md section 7's own example.
    /// </summary>
    public static string Sentence(string displayName, DateTime endsAtLocal, int tryNumber)
    {
        var until = Until(endsAtLocal);
        return ((Math.Max(tryNumber, 1) - 1) % 4) switch
        {
            0 => $"{displayName} is on your blocklist until {until}",
            1 => $"You set this time aside until {until}",
            2 => $"{displayName} can wait until {until}",
            _ => $"This sprint runs until {until}. {displayName} will still be there",
        };
    }

    /// <summary>"3rd try this sprint".</summary>
    public static string TryLine(int tryNumber)
    {
        var n = Math.Max(tryNumber, 1);
        var suffix = (n % 100) is 11 or 12 or 13 ? "th" : (n % 10) switch
        {
            1 => "st",
            2 => "nd",
            3 => "rd",
            _ => "th",
        };
        return $"{n}{suffix} try this sprint";
    }

    /// <summary>"You planned: finish chapter 3", or nothing when no intention was set.</summary>
    public static string Intention(string? intention)
    {
        var text = (intention ?? "").Trim();
        return text.Length == 0 ? "" : $"You planned: {text}";
    }

    /// <summary>"Allow 5 minutes · 0:08" while waiting; the plain label once it can be pressed. Text, so reduced motion changes nothing.</summary>
    public static string AllowLabel(TimeSpan left)
    {
        if (left <= TimeSpan.Zero) return "Allow 5 minutes";
        var seconds = (int)Math.Ceiling(left.TotalSeconds);
        return $"Allow 5 minutes · {seconds / 60}:{seconds % 60:00}";
    }

    /// <summary>The note under the buttons: Soft's promise, in words.</summary>
    public const string CloseNote = "Nothing is closed unless you choose to.";
```

Keep the old two-argument `Sentence(displayName, endsAtLocal)`, but have it call `Sentence(displayName, endsAtLocal, 1)`, so the existing tier 1 pin `test_the_sentence_names_the_app_and_when_the_blocklist_holds_until` still finds `{displayName} is on your blocklist until`.

- [ ] **Step 4: `AppBlockerService.AskToClose`** — add after `RunningBlockedApps`:

```csharp
    /// <summary>
    /// The Soft notice's "Close ‹app›" (1.0.10). The user chose it; Soft itself
    /// still closes nothing. Asks every running process of that app to close,
    /// the way its own close button would, so unsaved work gets its "save
    /// changes?" prompt. Never kills, and never touches a critical process.
    /// Returns how many processes were asked.
    /// </summary>
    public int AskToClose(string displayName, AppSettings settings)
    {
        var app = settings.ActiveProfile.Apps.FirstOrDefault(a =>
            a.IsEnabled && string.Equals(a.DisplayName, displayName, StringComparison.OrdinalIgnoreCase));
        if (app is null) return 0;

        var names = new HashSet<string>(app.AllProcessNames, StringComparer.OrdinalIgnoreCase);
        var asked = 0;
        foreach (var process in SafeGetProcesses())
        {
            try
            {
                var name = process.ProcessName;
                if (CriticalProcesses.Contains(name) || !names.Contains(name)) continue;
                if (process.CloseMainWindow())
                {
                    asked++;
                    Log.Info($"soft: asked {name} (pid {process.Id}) to close, as the user chose");
                }
            }
            catch (Exception ex)
            {
                Log.Warn($"soft: could not ask a process to close: {ex.Message}");
            }
            finally
            {
                process.Dispose();
            }
        }
        return asked;
    }
```

- [ ] **Step 5: Short timers** — in `App.xaml.cs`'s `--short-timers` block (line 36 onward), add `Models.SoftOverlayPolicy.UseShortTimers = true;` beside the other three.

- [ ] **Step 6: Probe support** — in `SoftSequence`'s `op` switch, add:

```csharp
                "close" => Do(() => policy.CloseIt(app, at)),
                "tries" => (JsonNode)policy.Tries,
                "turned" => (JsonNode)policy.TurnedBack,
```

and add commands to `Run`:

```csharp
            "soft-wait" => SoftWait(request),
            "soft-copy" => SoftCopy(request),
```

```csharp
    private static JsonNode SoftWait(JsonObject request)
    {
        SoftOverlayPolicy.UseShortTimers = (bool?)request["short"] ?? false;
        var seconds = SoftOverlayPolicy.AllowWait((int)request["try"]!).TotalSeconds;
        SoftOverlayPolicy.UseShortTimers = false;
        return new JsonObject { ["seconds"] = seconds };
    }

    private static JsonNode SoftCopy(JsonObject request)
    {
        var n = (int)request["try"]!;
        var app = (string?)request["app"] ?? "Discord";
        var ends = DateTime.Parse((string?)request["ends"] ?? "2026-09-28T17:45:00", CultureInfo.InvariantCulture);
        return new JsonObject
        {
            ["sentence"] = SoftOverlayCopy.Sentence(app, ends, n),
            ["try_line"] = SoftOverlayCopy.TryLine(n),
            ["intention"] = SoftOverlayCopy.Intention((string?)request["intention"]),
            ["allow_label"] = SoftOverlayCopy.AllowLabel(TimeSpan.FromSeconds((double?)request["allow_left"] ?? 0)),
        };
    }
```

- [ ] **Step 7: Run and watch them pass**

Run: `python -m pytest automation/tests/test_tier1_unit.py -k "SoftFriction or SoftOverlayPolicy or ModelProbe" automation/tests/test_tier5_regressions.py -k "SoftCloseNeverKills or SoftOverlayNeverCloses" -q`
Expected: pass, except `test_it_is_only_reached_from_the_close_button`, which passes after Task 7 wires `MainViewModel`. Mark it `@pytest.mark.xfail(strict=True, reason="wired in Task 7")` now and remove the mark in Task 7.

- [ ] **Step 8: Commit**

```bash
git add DesktopApp/Models/SoftOverlayPolicy.cs DesktopApp/Services/AppBlockerService.cs DesktopApp/App.xaml.cs automation
git commit -m "Soft friction rules: tries, a growing wait, turned back, varied wording

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The Soft notice on screen, and Soft's promise in words

**Files:**
- Modify: `DesktopApp/Views/SoftOverlayWindow.xaml`, `DesktopApp/Views/SoftOverlayWindow.xaml.cs`
- Modify: `DesktopApp/ViewModels/MainViewModel.cs:462-546` (request record, `OnSoftForeground`, a new `SoftOverlayCloseIt`)
- Modify: `DesktopApp/MainWindow.xaml.cs:393-426` (wire **Close**)
- Modify: `README.md:16`, `DesktopApp/Models/AppSettings.cs:10`, `HANDOFF_PROMPT.md:28`, `Website/legal.html:77` (region), `Website/index.html` (the Soft description in the shields section, if it says the app "keeps running")
- Test: `automation/tests/test_tier5_regressions.py`, `automation/tests/test_tier3_e2e.py`

**Interfaces:**
- Consumes: Task 6.
- Produces:
  - `MainViewModel.SoftOverlayRequest(string DisplayName, string Sentence, string TimeLeft, IntPtr Window, string Intention, string TryLine, TimeSpan AllowWait)`
  - `MainViewModel.SoftOverlayCloseIt(string displayName)`
  - `MainViewModel.SoftTurnedBackThisSprint` (int; read by Task 10)
  - `SoftOverlayWindow` events `BackToWork`, `AllowFiveMinutes` and `CloseIt`
  - New AutomationIds: `SoftOverlayCloseButton`, `SoftOverlayIntention`, `SoftOverlayTryLine`

- [ ] **Step 1: Write the failing tests** — in `test_tier5_regressions.py`:
  - In `TestSoftShieldWording.test_old_overlay_wording_is_gone`, keep the `"blocked app keeps running"` assertions (the new wording keeps that phrase) and add `assert "unless you choose to close it" in readme` and `... in model`.
  - In `test_legal_page_distinguishes_soft_from_closing_modes`, keep the existing assertions and add `assert "unless you choose Close on its notice" in legal`.
  - In `TestSoftOverlayNeverCloses.test_its_controls_carry_automation_ids_on_real_controls`, add `"SoftOverlayCloseButton"`, `"SoftOverlayIntention"` and `"SoftOverlayTryLine"` to the tuple.
  - Append:

```python
class TestSoftNoticeFriction:
    MAIN_VM = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    MAIN_WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    OVERLAY_XAML = Path(DESKTOP_DIR) / "Views" / "SoftOverlayWindow.xaml"
    OVERLAY_CS = Path(DESKTOP_DIR) / "Views" / "SoftOverlayWindow.xaml.cs"

    def test_close_is_the_primary_focused_button(self):
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        close = xaml.split('AutomationProperties.AutomationId="SoftOverlayCloseButton"')[0].rsplit("<Button", 1)[1]
        assert "BtnPrimary" in close and 'IsDefault="True"' in close
        back = xaml.split('AutomationProperties.AutomationId="SoftOverlayBackToWorkButton"')[0].rsplit("<Button", 1)[1]
        assert "BtnPrimary" not in back and 'IsCancel="True"' in back, "Escape is still Back to work"

    def test_allow_waits_before_it_can_be_pressed(self):
        code = self.OVERLAY_CS.read_text(encoding="utf-8")
        assert "AllowButton.IsEnabled = false" in code
        assert "SoftOverlayCopy.AllowLabel(" in code
        assert "DispatcherTimer" in code

    def test_the_close_handler_asks_through_the_view_model_only(self):
        block = self.MAIN_WINDOW.read_text(encoding="utf-8").split("overlay.CloseIt +=", 1)[1].split("};", 1)[0]
        assert "SoftOverlayCloseIt" in block
        for forbidden in ("Kill", "CloseMainWindow", "Process"):
            assert forbidden not in block

    def test_the_view_model_counts_it_and_asks_the_blocker(self):
        source = self.MAIN_VM.read_text(encoding="utf-8")
        body = source.split("public void SoftOverlayCloseIt(string displayName)", 1)[1].split("\n    }", 1)[0]
        assert "_softOverlay.CloseIt(displayName, DateTime.UtcNow);" in body
        assert "Blocker.AskToClose(displayName, Settings)" in body

    def test_the_request_carries_intention_try_and_wait(self):
        handler = self.MAIN_VM.read_text(encoding="utf-8").split("private void OnSoftForeground", 1)[1].split("\n    }", 1)[0]
        for piece in ("SoftOverlayCopy.Intention(", "SoftOverlayCopy.TryLine(_softOverlay.Tries)",
                      "SoftOverlayPolicy.AllowWait(_softOverlay.Tries)",
                      "SoftOverlayCopy.Sentence(e.DisplayName, Today.EndsAtUtc.ToLocalTime(), _softOverlay.Tries)"):
            assert piece in handler, piece
```

  - In `test_tier3_e2e.py`, find the existing Soft notice test class (grep `SoftOverlayBackToWorkButton`) and add, in the same style:

```python
    def test_allow_is_disabled_until_the_wait_runs_out(self, soft_notice):
        """--short-timers makes the wait one second."""
        app = soft_notice
        assert not app.is_control_enabled("SoftOverlayAllowButton")
        app.wait_until_control_enabled("SoftOverlayAllowButton", timeout=5)
        assert "1st try this sprint" in app.text_of("SoftOverlayTryLine")

    def test_close_asks_the_app_to_close_and_counts_nothing_as_a_kill(self, soft_notice):
        app = soft_notice
        app.click("SoftOverlayCloseButton")
        assert app.app_log_contains("asked") and app.app_log_contains("as the user chose")
```

  Adapt the fixture name to whatever the existing Soft notice tests use. If those tests are skipped or failing because of #250 (the decoy loses the OS foreground), keep the new tests beside them with the same mark and note it in the PR. Tier 1 and tier 5 carry the proof.

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest automation/tests/test_tier5_regressions.py -k "SoftNoticeFriction or SoftShieldWording or SoftOverlayNeverCloses" -q` — FAIL.

- [ ] **Step 3: The window.** In `SoftOverlayWindow.xaml`, replace the `SoftOverlayNote` text and the button row (lines 65–81) with:

```xml
                <TextBlock x:Name="IntentionText" Style="{StaticResource Body}" TextWrapping="Wrap"
                           Margin="0,12,0,0" Visibility="Collapsed"
                           AutomationProperties.AutomationId="SoftOverlayIntention"/>

                <TextBlock x:Name="TryLineText" Style="{StaticResource Caption}" Margin="0,12,0,0"
                           AutomationProperties.AutomationId="SoftOverlayTryLine"/>

                <TextBlock Text="Nothing is closed unless you choose to."
                           Style="{StaticResource Caption}" TextWrapping="Wrap" Margin="0,4,0,0"
                           AutomationProperties.AutomationId="SoftOverlayNote"/>

                <WrapPanel Orientation="Horizontal" Margin="0,24,0,0">
                    <Button x:Name="CloseButton" Style="{StaticResource BtnPrimary}"
                            Padding="24,12" IsDefault="True" Margin="0,0,12,8"
                            Click="OnCloseIt"
                            AutomationProperties.AutomationId="SoftOverlayCloseButton"/>
                    <!-- IsCancel so Escape is the same as Back to work. -->
                    <Button x:Name="BackToWorkButton" Style="{StaticResource BtnGhost}"
                            Content="Back to work" Padding="24,12" IsCancel="True" Margin="0,0,12,8"
                            Click="OnBackToWork"
                            AutomationProperties.AutomationId="SoftOverlayBackToWorkButton"
                            AutomationProperties.Name="Back to work"/>
                    <Button x:Name="AllowButton" Style="{StaticResource BtnQuiet}" Content="Allow 5 minutes"
                            Padding="24,12" Margin="0,0,0,8"
                            Click="OnAllowFiveMinutes"
                            AutomationProperties.AutomationId="SoftOverlayAllowButton"
                            AutomationProperties.Name="Allow 5 minutes"/>
                </WrapPanel>
```

In `SoftOverlayWindow.xaml.cs`:

```csharp
    /// <summary>Close ‹app›: the user's choice. MainWindow passes it to the view model, which asks the blocker.</summary>
    public event EventHandler? CloseIt;

    private DispatcherTimer? _allowTimer;
    private DateTime _allowAtUtc;

    /// <summary>Fills in the notice. Called before Show.</summary>
    public void Configure(string displayName, string sentence, string timeLeft, IntPtr anchor,
                          string intention, string tryLine, TimeSpan allowWait)
    {
        SentenceText.Text = sentence;
        TimeLeftText.Text = timeLeft;
        IntentionText.Text = intention;
        IntentionText.Visibility = intention.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
        TryLineText.Text = tryLine;
        CloseButton.Content = $"Close {displayName}";
        AutomationProperties.SetName(CloseButton, $"Close {displayName}");
        _anchor = anchor;

        // The wait before Allow (1.0.10). Text only, so reduced motion changes nothing.
        _allowAtUtc = DateTime.UtcNow + allowWait;
        AllowButton.IsEnabled = false;
        AllowButton.Content = SoftOverlayCopy.AllowLabel(allowWait);
        _allowTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(250) };
        _allowTimer.Tick += (_, _) => UpdateAllow();
        _allowTimer.Start();
    }

    private void UpdateAllow()
    {
        var left = _allowAtUtc - DateTime.UtcNow;
        AllowButton.Content = SoftOverlayCopy.AllowLabel(left);
        if (left > TimeSpan.Zero) return;
        AllowButton.IsEnabled = true;
        _allowTimer?.Stop();
    }

    protected override void OnClosed(EventArgs e)
    {
        _allowTimer?.Stop();
        base.OnClosed(e);
    }

    private void OnCloseIt(object sender, RoutedEventArgs e) => Answer(CloseIt);
```

Remove the old `Configure(string, string, IntPtr)`. In `OnSourceInitialized`, focus `CloseButton` instead of `BackToWorkButton`, and update the comment: "The primary action has focus, so Enter is Close; Escape is Back to work." Add `using System.Windows.Automation;`, `using System.Windows.Threading;` and `using FlowShield.Models;`. `OnAllowFiveMinutes` must refuse while disabled: start it with `if (!AllowButton.IsEnabled) return;` (UI Automation can invoke a disabled-looking control through a covering surface, #134).

- [ ] **Step 4: The view model and MainWindow.**
  - `MainViewModel.SoftOverlayRequest` gains `string Intention, string TryLine, TimeSpan AllowWait`.
  - In `OnSoftForeground`, the request becomes:

```csharp
            SoftOverlayRequested?.Invoke(this, new SoftOverlayRequest(
                e.DisplayName,
                SoftOverlayCopy.Sentence(e.DisplayName, Today.EndsAtUtc.ToLocalTime(), _softOverlay.Tries),
                SoftOverlayCopy.TimeLeft(Today.Remaining),
                e.Window,
                SoftOverlayCopy.Intention(Today.IntentionDisplayText),
                SoftOverlayCopy.TryLine(_softOverlay.Tries),
                SoftOverlayPolicy.AllowWait(_softOverlay.Tries)));
```

  (`ShouldShow` has already incremented `Tries`, so the count includes this notice. Confirm that `Today.IntentionDisplayText` is the running sprint's intention; it's set in `BeginRunning`.)
  - Add:

```csharp
    /// <summary>Turned back this sprint (Close or Back to work). Read when the sprint is recorded.</summary>
    public int SoftTurnedBackThisSprint => _softOverlay.TurnedBack;

    /// <summary>
    /// "Close ‹app›" on the Soft notice (1.0.10). The user chose it: the blocker
    /// asks the app to close and never kills it, so its own save prompt appears.
    /// </summary>
    public void SoftOverlayCloseIt(string displayName)
    {
        _softOverlay.CloseIt(displayName, DateTime.UtcNow);
        var asked = Blocker.AskToClose(displayName, Settings);
        Log.Info($"soft notice: close {displayName} chosen; asked {asked} process(es)");
    }
```

  - `MainWindow.OnSoftOverlayRequested`: call `overlay.Configure(request.DisplayName, request.Sentence, request.TimeLeft, request.Window, request.Intention, request.TryLine, request.AllowWait);` and add:

```csharp
            overlay.CloseIt += (_, _) =>
            {
                CloseSoftOverlay();
                Vm?.SoftOverlayCloseIt(request.DisplayName);
            };
```

  Update that method's summary: "Close asks the blocked app to close (the user's choice, never a kill); Back to work brings FlowShield forward; Allow goes quiet after its wait."
  - Remove the `xfail` mark from Task 6's `test_it_is_only_reached_from_the_close_button`.

- [ ] **Step 5: Soft's promise in words.** Every place below keeps its existing phrase and gains the qualifier:
  - `README.md:16` → `Shield I  · Soft    a full-screen notice on its own screen; the blocked app keeps running unless you choose to close it`
  - `DesktopApp/Models/AppSettings.cs:10` → `/// <summary>Full-screen notice on its own screen; the blocked app keeps running unless you choose to close it.</summary>`
  - `HANDOFF_PROMPT.md:28` → add "Close ‹app›" to the list of buttons and ", unless you choose Close" after "the app keeps running".
  - `Website/legal.html` near line 77 → after "Soft records the distraction and leaves the application running", insert " unless you choose Close on its notice". Keep the sentence otherwise as it is.
  - `Website/index.html`: grep the shields section for Soft's description. If it says the app keeps running or that Soft never closes, add the same qualifier. If it only says "Notes distractions and nudges you." (`ShieldCopy`), leave it; that's still true.
  - Changelog: nothing yet (Task 10 adds the 1.0.10 lines once A and B are merged after 1.0.9).

- [ ] **Step 6: Build and run everything this touches**

Run: `cd DesktopApp; dotnet build -c Release -nologo` — 0 errors.
Run: `python -m pytest automation/tests -m "not ui and not stripe" -q` — pass.
Run (UI lock): `python -m pytest automation/tests/test_tier3_e2e.py -k "Soft" -q` — pass, or the #250 marks as already on `main`.

- [ ] **Step 7: Screenshot** of the notice at try 1 (Allow counting down) and try 3 (a different sentence and "3rd try this sprint"), in dark and light. If #250 stops tier 3 from raising it, raise it by hand: add Notepad to the blocklist, start a Soft sprint, click Notepad.

- [ ] **Step 8: Commit and open PR B**

```bash
git add DesktopApp README.md HANDOFF_PROMPT.md Website automation
git commit -m "Soft notice: Close first, a wait before Allow, intention and try count

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -u origin feat/soft-friction
```

The PR body names `LEGAL_CHECKLIST.md`'s item on the legal page describing what FlowShield closes, and notes that this PR must not merge before v1.0.9.

---

# PR C — scheduled sprints start, and templates on Today (after 1.0.9)

> **Before starting:** 1.0.9 must be published and PRs A and B merged. Work from a fresh `origin/main`. **Re-read** `TodayViewModel.StartSprint`, `BeginRunning`, `EndSprint`, `OfferBreakIfEarned`, `ResumeInterruptedSprint` and `RunningSprint` on that `main`: Miles's #203/#204 fixes may have changed them. The code below is anchored to method names, not line numbers. Where it conflicts with his changes, keep his behaviour and fit this code around it.

### Task 8: `ScheduleService` — heads-up, start, missed offer

**Files:**
- Create: `DesktopApp/Models/SchedulePlanner.cs` (pure decisions)
- Create: `DesktopApp/Services/ScheduleService.cs` (the timer)
- Modify: `automation/csharp/ModelProbe/Commands.cs`
- Test: `automation/tests/test_tier1_unit.py`

**Interfaces:**
- Produces:
  - `enum ScheduleActionKind { HeadsUp, Start, OfferMissed }`
  - `record ScheduleAction(ScheduleActionKind Kind, SprintSchedule Schedule, DateTime StartUtc)`
  - `static class SchedulePlanner { static TimeSpan HeadsUpLead; static TimeSpan LateWindow; static bool UseShortSchedules; static IReadOnlyList<ScheduleAction> Decide(IEnumerable<SprintSchedule> schedules, DateTime lastTickUtc, DateTime nowUtc, TimeZoneInfo zone, ISet<string> headsUpShown); }`
  - `ScheduleService(Func<IReadOnlyList<SprintSchedule>> schedules)` with `Start()`, `Stop()`, `Tick(DateTime nowUtc)` and `event EventHandler<ScheduleAction>? Action`
- Rules, which the tests pin:
  - **HeadsUp** fires once per (schedule, start) when now enters `[start − lead, start)` and the schedule has `AskFirst`.
  - **Start** fires when a start falls in `(lastTick, now]` and now − start ≤ 1 minute.
  - A start that falls in the interval but more than 1 minute before now (a gap: sleep, app closed or a clock jump) becomes **OfferMissed** if now − start ≤ `LateWindow`. Otherwise nothing happens.
  - At most **one** OfferMissed per tick: the most recent start.
  - Disabled schedules and skipped dates produce nothing.
  - Actions come out oldest first. The caller starts at most one sprint per tick; later Starts in the same tick are logged and skipped.
  - `HeadsUpLead` is 5 min and `LateWindow` is 30 min, or 5 s and 10 s under `UseShortSchedules`.

- [ ] **Step 1: Write the failing tests**

```python
class TestSchedulePlanner:
    """F6: what the scheduler does on each tick. Pure, so the gaps can be tested."""

    Z = EASTERN

    def decide(self, schedules, last, now, shown=()):
        return probe({"cmd": "schedule-decide", "schedules": schedules, "zone": self.Z,
                      "last": last, "now": now, "shown": list(shown)})

    def test_heads_up_five_minutes_before(self):
        out = self.decide([schedule()], "2026-09-28T20:54:50Z", "2026-09-28T20:55:05Z")
        assert out["actions"] == [{"kind": "HeadsUp", "id": "s1", "start": "2026-09-28T21:00:00Z"}]

    def test_heads_up_only_once(self):
        out = self.decide([schedule()], "2026-09-28T20:55:05Z", "2026-09-28T20:55:20Z",
                          shown=["s1@2026-09-28T21:00:00Z"])
        assert out["actions"] == []

    def test_no_heads_up_when_ask_first_is_off(self):
        out = self.decide([schedule(AskFirst=False)], "2026-09-28T20:54:50Z", "2026-09-28T20:55:05Z")
        assert out["actions"] == []

    def test_start_at_the_time(self):
        out = self.decide([schedule()], "2026-09-28T20:59:50Z", "2026-09-28T21:00:05Z")
        assert [a["kind"] for a in out["actions"]] == ["Start"]

    def test_a_skipped_day_does_nothing(self):
        s = schedule(SkippedDatesLocal=["2026-09-28T00:00:00"])
        out = self.decide([s], "2026-09-28T20:54:50Z", "2026-09-28T21:00:05Z")
        assert out["actions"] == []

    def test_a_disabled_schedule_does_nothing(self):
        out = self.decide([schedule(Enabled=False)], "2026-09-28T20:59:50Z", "2026-09-28T21:00:05Z")
        assert out["actions"] == []

    def test_waking_twenty_minutes_late_offers_never_starts(self):
        out = self.decide([schedule()], "2026-09-28T20:30:00Z", "2026-09-28T21:20:00Z")
        assert [a["kind"] for a in out["actions"]] == ["OfferMissed"]

    def test_waking_an_hour_late_does_nothing(self):
        out = self.decide([schedule()], "2026-09-28T20:30:00Z", "2026-09-28T22:00:00Z")
        assert out["actions"] == []

    def test_a_long_gap_offers_at_most_one_start(self):
        """Review focus 2: asleep over several scheduled starts is one offer, not a burst."""
        daily = schedule(days=[0, 1, 2, 3, 4, 5, 6], minute=21 * 60)  # 21:00 every day
        out = self.decide([daily], "2026-09-25T12:00:00Z", "2026-09-29T01:10:00Z")  # 21:10 EDT on the 28th
        assert [a["kind"] for a in out["actions"]] == ["OfferMissed"]
        assert out["actions"][0]["start"] == "2026-09-29T01:00:00Z"

    def test_two_schedules_at_the_same_minute_come_out_in_a_stable_order(self):
        """Review focus 3: the service starts the first and skips the second."""
        a = schedule(Id="a", TemplateId="t1")
        b = schedule(Id="b", TemplateId="t2")
        out = self.decide([b, a], "2026-09-28T20:59:50Z", "2026-09-28T21:00:05Z")
        assert [x["id"] for x in out["actions"]] == ["a", "b"]

    def test_short_schedules_shrink_the_lead_and_late_window(self):
        out = probe({"cmd": "schedule-windows", "short": True})
        assert out == {"lead": 5, "late": 10}
        assert probe({"cmd": "schedule-windows", "short": False}) == {"lead": 300, "late": 1800}
```

- [ ] **Step 2: Run and watch them fail** — `-k SchedulePlanner`, unknown command.

- [ ] **Step 3: `DesktopApp/Models/SchedulePlanner.cs`**

```csharp
namespace FlowShield.Models;

public enum ScheduleActionKind { HeadsUp, Start, OfferMissed }

public sealed record ScheduleAction(ScheduleActionKind Kind, SprintSchedule Schedule, DateTime StartUtc);

/// <summary>
/// What the scheduler does on one tick (F6). Pure: given the last tick and
/// now, it says which heads-ups, starts and missed offers are due. The service
/// only carries them out.
///
/// A start more than a minute old when first seen was missed (the PC slept,
/// FlowShield was closed, the clock jumped). Missed starts are offered, never
/// started, and only the latest one inside the late window, so a long gap is
/// one question rather than a burst of sprints.
/// </summary>
public static class SchedulePlanner
{
    public static bool UseShortSchedules { get; set; }

    public static TimeSpan HeadsUpLead => UseShortSchedules ? TimeSpan.FromSeconds(5) : TimeSpan.FromMinutes(5);
    public static TimeSpan LateWindow => UseShortSchedules ? TimeSpan.FromSeconds(10) : TimeSpan.FromMinutes(30);

    /// <summary>How late a start may be seen and still count as on time: one tick and a bit.</summary>
    public static readonly TimeSpan OnTime = TimeSpan.FromMinutes(1);

    public static string HeadsUpKey(SprintSchedule s, DateTime startUtc) =>
        $"{s.Id}@{startUtc:yyyy-MM-ddTHH:mm:ssZ}";

    public static IReadOnlyList<ScheduleAction> Decide(
        IEnumerable<SprintSchedule> schedules, DateTime lastTickUtc, DateTime nowUtc,
        TimeZoneInfo zone, ISet<string> headsUpShown)
    {
        var actions = new List<ScheduleAction>();
        ScheduleAction? latestMissed = null;

        foreach (var s in schedules.Where(x => x.Enabled).OrderBy(x => x.Id, StringComparer.Ordinal))
        {
            // Heads-up: a start within the lead, not yet announced.
            if (s.AskFirst && ScheduleMatcher.NextStartUtc(s, nowUtc - TimeSpan.FromTicks(1), zone) is { } next
                && next > nowUtc && next - nowUtc <= HeadsUpLead
                && !IsSkipped(s, next, zone)
                && !headsUpShown.Contains(HeadsUpKey(s, next)))
            {
                actions.Add(new ScheduleAction(ScheduleActionKind.HeadsUp, s, next));
            }

            foreach (var start in ScheduleMatcher.StartsBetweenUtc(s, lastTickUtc, nowUtc, zone))
            {
                if (IsSkipped(s, start, zone)) continue;
                var late = nowUtc - start;
                if (late <= OnTime)
                    actions.Add(new ScheduleAction(ScheduleActionKind.Start, s, start));
                else if (late <= LateWindow && (latestMissed is null || start > latestMissed.StartUtc))
                    latestMissed = new ScheduleAction(ScheduleActionKind.OfferMissed, s, start);
            }
        }

        if (latestMissed is not null) actions.Add(latestMissed);
        return actions.OrderBy(a => a.StartUtc).ThenBy(a => a.Schedule.Id, StringComparer.Ordinal).ToList();
    }

    private static bool IsSkipped(SprintSchedule s, DateTime startUtc, TimeZoneInfo zone) =>
        s.IsSkipped(TimeZoneInfo.ConvertTimeFromUtc(startUtc, zone).Date);
}
```

Probe commands:

```csharp
            "schedule-decide" => ScheduleDecide(request),
            "schedule-windows" => ScheduleWindows(request),
```

```csharp
    private static JsonNode ScheduleDecide(JsonObject request)
    {
        var schedules = request["schedules"].Deserialize<List<SprintSchedule>>()!;
        var shown = request["shown"]!.AsArray().Select(x => (string)x!).ToHashSet();
        var actions = SchedulePlanner.Decide(schedules, Utc((string)request["last"]!),
            Utc((string)request["now"]!), ZoneOf(request), shown);
        return new JsonObject
        {
            ["actions"] = new JsonArray(actions.Select(a => (JsonNode)new JsonObject
            {
                ["kind"] = a.Kind.ToString(), ["id"] = a.Schedule.Id, ["start"] = Iso(a.StartUtc),
            }).ToArray()),
        };
    }

    private static JsonNode ScheduleWindows(JsonObject request)
    {
        SchedulePlanner.UseShortSchedules = (bool)request["short"]!;
        var answer = new JsonObject
        {
            ["lead"] = (int)SchedulePlanner.HeadsUpLead.TotalSeconds,
            ["late"] = (int)SchedulePlanner.LateWindow.TotalSeconds,
        };
        SchedulePlanner.UseShortSchedules = false;
        return answer;
    }
```

The `SkippedDatesLocal` in the tests is `"2026-09-28T00:00:00"`, which System.Text.Json reads as a `DateTime` with `Kind = Unspecified`. `IsSkipped` compares `.Date`, so the kind doesn't matter.

- [ ] **Step 4: `DesktopApp/Services/ScheduleService.cs`**

```csharp
using System.Windows.Threading;
using FlowShield.Models;

namespace FlowShield.Services;

/// <summary>
/// Runs the schedules (F6): a 15-second tick that asks <see cref="SchedulePlanner"/>
/// what is due and raises it. Deciding whether a start is allowed (terms,
/// first run, trial, a sprint already running) is the caller's job, through
/// the same gates as the Start button.
/// </summary>
public sealed class ScheduleService
{
    public static readonly TimeSpan Interval = TimeSpan.FromSeconds(15);

    private readonly Func<IReadOnlyList<SprintSchedule>> _schedules;
    private readonly DispatcherTimer _timer = new() { Interval = Interval };
    private readonly HashSet<string> _headsUpShown = new(StringComparer.Ordinal);
    private DateTime _lastTickUtc;

    public ScheduleService(Func<IReadOnlyList<SprintSchedule>> schedules)
    {
        _schedules = schedules;
        _timer.Tick += (_, _) => Tick(DateTime.UtcNow);
    }

    public event EventHandler<ScheduleAction>? Action;

    public void Start()
    {
        _lastTickUtc = DateTime.UtcNow;
        _timer.Start();
    }

    public void Stop() => _timer.Stop();

    public void Tick(DateTime nowUtc)
    {
        // A clock set backwards must not replay starts that already passed.
        if (nowUtc < _lastTickUtc) _lastTickUtc = nowUtc;

        var actions = SchedulePlanner.Decide(_schedules(), _lastTickUtc, nowUtc, TimeZoneInfo.Local, _headsUpShown);
        _lastTickUtc = nowUtc;

        foreach (var action in actions)
        {
            if (action.Kind == ScheduleActionKind.HeadsUp)
                _headsUpShown.Add(SchedulePlanner.HeadsUpKey(action.Schedule, action.StartUtc));
            Action?.Invoke(this, action);
        }
    }
}
```

- [ ] **Step 5: Run and watch them pass; commit**

```bash
git add DesktopApp/Models/SchedulePlanner.cs DesktopApp/Services/ScheduleService.cs automation
git commit -m "F6: the scheduler decides heads-ups, starts and missed offers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Templates on Today, the heads-up card, and starting from a schedule

**Files:**
- Modify: `DesktopApp/ViewModels/TodayViewModel.cs` (new region "templates and schedules (F6)"; `StartSprint` gains an overload; the break length honours the template)
- Modify: `DesktopApp/Models/AppSettings.cs` (`RunningSprint.TemplateBreakMinutes`)
- Modify: `DesktopApp/Views/TodayView.xaml` (chip row above Start; heads-up card)
- Modify: `DesktopApp/ViewModels/MainViewModel.cs` (create and start `ScheduleService`, route actions, refresh chips on `Schedule.TemplatesChanged`)
- Modify: `DesktopApp/App.xaml.cs` (`--short-schedules`)
- Modify: `DesktopApp/ViewModels/SettingsViewModel.cs`, `DesktopApp/Views/SettingsView.xaml` (a switch for the `ScheduledSprint` notification, in the same group and pattern as the other notification switches)
- Modify: `Website/changelog.html` (Unreleased lines), `LAUNCH_FEATURE_CHECKLIST.md` (tick F6), `automation/desktop/app_controller.py` (the flag is added per test, not by default)
- Test: tier 1, tier 3 and tier 5

**Interfaces:**
- Consumes: Tasks 4, 5 and 8; `NotificationKind.ScheduledSprint`; `_main.Notify(kind, title, body)`; `CycleState.BreakMinutes(...)`.
- Produces:
  - `TodayViewModel.Templates` (an `ObservableCollection<StudyTemplate>`), `ApplyTemplateCommand`, `void ApplyTemplate(StudyTemplate t)`, `bool StartTemplate(StudyTemplate t, bool skipOpenAppsPanel)`
  - The heads-up card: `HeadsUpVisible`, `HeadsUpTitle`, `HeadsUpText`, `StartNowCommand`, `SkipTodayCommand`
  - AutomationIds `TemplateChip_{Name}`, `HeadsUpCard` (on the title `TextBlock`), `HeadsUpText`, `HeadsUpStartNowButton`, `HeadsUpSkipButton`
  - `RunningSprint.TemplateBreakMinutes` (`int?`, null means the global break settings)

- [ ] **Step 1: Write the failing tests**
  - Tier 5 source pins: `StartTemplate` calls the same gates as `StartSprint` (it must go through `StartSprint`, not copy it); the scheduled start passes `skipOpenAppsPanel: true`; `OnScheduleAction` refuses when `IsSprintRunning || Today.IsOnBreak || IsLocked || TermsGateVisible || FirstRun.IsVisible`; an `OfferMissed` never calls `StartTemplate` directly (it only shows the card); `--short-schedules` sets `SchedulePlanner.UseShortSchedules`; `RunningSprint.TemplateBreakMinutes` is written in `StartSprint` and read wherever the offered break length is computed.
  - Tier 3: change the file's import to `from datetime import datetime, timedelta`. Add a `schedule_app` fixture beside `fresh_app` (in `automation/tests/conftest.py`, wherever `fresh_app` is defined) that launches exactly like `fresh_app` plus the `--short-schedules` flag. Read `launch_app` in `app_controller.py:134` for how extra arguments are passed, and copy `fresh_app`'s teardown. Then:

```python
class TestScheduledSprints:
    """F6 done-when: a schedule a minute ahead starts, after a heads-up that can skip it."""

    def _schedule_in(self, app, seconds: int, template="Light study", ask=True):
        at = datetime.now() + timedelta(seconds=seconds)
        app.navigate_to_tab("Schedule")
        day = at.strftime("%a")
        app.add_schedule(template, [day], at.strftime("%H:%M"), ask_first=ask)
        return at

    def test_heads_up_then_it_starts(self, schedule_app):
        self._schedule_in(schedule_app, 70)
        schedule_app.navigate_to_tab("Today")
        schedule_app.wait_until_control_enabled("HeadsUpStartNowButton", timeout=90)
        assert "Light study" in schedule_app.text_of("HeadsUpText")
        deadline = time.time() + 40
        while time.time() < deadline and "Shield" not in schedule_app.session_state():
            time.sleep(1)
        assert "Shield" in schedule_app.session_state(), "the sprint started by itself"
        assert verify.read_settings()["ActiveSprint"]["Shield"] == 1   # Soft, from the template

    def test_skip_today_stops_it(self, schedule_app):
        self._schedule_in(schedule_app, 70)
        schedule_app.navigate_to_tab("Today")
        schedule_app.wait_until_control_enabled("HeadsUpSkipButton", timeout=90)
        schedule_app.click("HeadsUpSkipButton")
        time.sleep(20)
        assert verify.read_settings().get("ActiveSprint") is None
        assert verify.read_settings()["Schedules"][0]["SkippedDatesLocal"], "the skip was saved"

    def test_a_template_chip_fills_in_today(self, fresh_app):
        fresh_app.click("TemplateChip_Homework evening")
        assert fresh_app.is_selected("Shield_Firm")
        settings = verify.read_settings()
        assert settings["CycleSprints"] == 3
```

  Take the minute alignment into account: `_schedule_in` rounds to the minute through `%H:%M`, so pick `seconds` to land 60–120 s ahead. If the rounded time falls under 5 s ahead, add 60 s.

- [ ] **Step 2: Run and watch them fail.**

- [ ] **Step 3: `RunningSprint.TemplateBreakMinutes`** — add to `RunningSprint`:

```csharp
    /// <summary>
    /// The break length of the template this cycle was started from (F6), or
    /// null for a hand-started sprint, which uses the global break settings.
    /// Saved with the sprint so a restart mid-cycle keeps the template's breaks.
    /// </summary>
    public int? TemplateBreakMinutes { get; set; }
```

In `TodayViewModel`, add `private int? _templateBreakMinutes;`. Set it in `StartTemplate`. Write it into `S.ActiveSprint` in `StartSprint` (`TemplateBreakMinutes = _templateBreakMinutes,`). Restore it in `ResumeInterruptedSprint` (`_templateBreakMinutes = saved.TemplateBreakMinutes;`). Clear it when the cycle finishes (in `OfferBreakIfEarned`'s `CycleFinished` branch) and in the manual `StartSprint` path (the plain Start button sets `_templateBreakMinutes = null` before calling the shared start). `OfferedBreakMinutes` becomes:

```csharp
    private int OfferedBreakMinutes =>
        _templateBreakMinutes
        ?? CycleState.BreakMinutes(S.CompletedSprintsInARow, S.ShortBreakMinutes, S.LongBreakMinutes);
```

Check what `StartBreak` uses for the length; if it reads `OfferedBreakMinutes`, that one change covers it. If it computes the length separately, route it through `OfferedBreakMinutes`.

- [ ] **Step 4: Apply and start a template** — in `TodayViewModel`:

```csharp
    // ------------------------------------------------ templates and schedules (F6)

    public ObservableCollection<StudyTemplate> Templates { get; } = new();

    public RelayCommand ApplyTemplateCommand { get; private set; } = null!;

    public void RefreshTemplates()
    {
        Templates.Clear();
        foreach (var t in S.Templates) Templates.Add(t);
    }

    /// <summary>A chip on Today: fills in length, shield, cycle and profile. Each can still be changed.</summary>
    public void ApplyTemplate(StudyTemplate template)
    {
        if (IsRunning || IsOnBreak) return;
        SelectedMinutes = template.SprintMinutes;
        SelectedShield = template.Shield;
        CycleSprints = template.CycleSprints;
        var profile = S.ProfileFor(template);
        if (!ReferenceEquals(profile, S.ActiveProfile)) SelectProfileCommand.Execute(profile);
        _templateBreakMinutes = template.BreakMinutes;
        Log.Info($"template applied: {template.Name}");
    }

    /// <summary>
    /// Starts a template, from a schedule or the heads-up card. The same gates
    /// as Start (terms, first run, trial, can-start) apply, because it goes
    /// through <see cref="StartSprint"/>. From a schedule the pre-sprint
    /// open-apps panel is skipped: the heads-up already named them.
    /// </summary>
    public bool StartTemplate(StudyTemplate template, bool skipOpenAppsPanel)
    {
        if (IsRunning || IsOnBreak) return false;
        ApplyTemplate(template);
        if (skipOpenAppsPanel) _runningAppsAnswered = true;
        StartSprint();
        return IsRunning;
    }
```

`SelectedMinutes`'s setter only accepts `SprintLengths` (15, 25, 45, 60, 90). Read how a custom length is set (`CustomMinMinutes`/`CustomMaxMinutes` and the property around line 347) and set a non-preset template length through that same path, so a 30-minute template works. Confirm `SelectProfileCommand` exists on `TodayViewModel` (the Today profile chips bind to it) and that it accepts a `BlocklistProfile`.

Construct `ApplyTemplateCommand = new RelayCommand(p => { if (p is StudyTemplate t) ApplyTemplate(t); }, _ => !IsRunning && !IsOnBreak);` in the constructor, and call `RefreshTemplates()` there too.

- [ ] **Step 5: The heads-up card**

```csharp
    private ScheduleAction? _headsUp;

    private bool _headsUpVisible;
    public bool HeadsUpVisible { get => _headsUpVisible; private set => Set(ref _headsUpVisible, value); }

    private string _headsUpTitle = "";
    public string HeadsUpTitle { get => _headsUpTitle; private set => Set(ref _headsUpTitle, value); }

    private string _headsUpText = "";
    public string HeadsUpText { get => _headsUpText; private set => Set(ref _headsUpText, value); }

    public RelayCommand StartNowCommand { get; private set; } = null!;
    public RelayCommand SkipTodayCommand { get; private set; } = null!;

    /// <summary>"Homework evening starts at 17:00", or "You missed Homework evening".</summary>
    public void ShowHeadsUp(ScheduleAction action, StudyTemplate template)
    {
        _headsUp = action;
        var at = ScheduleText.Time((int)TimeZoneInfo.ConvertTimeFromUtc(action.StartUtc, TimeZoneInfo.Local).TimeOfDay.TotalMinutes);
        var open = _main.Blocker.RunningBlockedApps(S);
        var closing = template.Shield >= ShieldLevel.Firm && open.Count > 0
            ? $" {string.Join(", ", open)} will be closed."
            : "";
        var locks = template.Shield == ShieldLevel.Sealed ? " The list locks until it ends." : "";

        HeadsUpTitle = action.Kind == ScheduleActionKind.OfferMissed
            ? $"You missed {template.Name}"
            : $"{template.Name} starts at {at}";
        HeadsUpText = action.Kind == ScheduleActionKind.OfferMissed
            ? $"It was due at {at}. Start it now, or leave it for today."
            : $"{template.SprintMinutes} minutes at {template.Shield}.{closing}{locks}";
        HeadsUpVisible = true;
    }

    public void HideHeadsUp()
    {
        _headsUp = null;
        HeadsUpVisible = false;
    }

    /// <summary>The start time arrived while the card is up: the card has done its job.</summary>
    public bool HeadsUpIsFor(SprintSchedule schedule) => _headsUp?.Schedule.Id == schedule.Id;

    private void StartNow()
    {
        if (_headsUp is null) return;
        var template = S.FindTemplate(_headsUp.Schedule.TemplateId);
        HideHeadsUp();
        if (template is not null) StartTemplate(template, skipOpenAppsPanel: true);
    }

    private void SkipToday()
    {
        if (_headsUp is null) return;
        var schedule = _headsUp.Schedule;
        schedule.Skip(TimeZoneInfo.ConvertTimeFromUtc(_headsUp.StartUtc, TimeZoneInfo.Local).Date);
        _main.SaveSettings();
        HideHeadsUp();
        _main.Toast("Skipped for today. Your momentum is unchanged.");
        Log.Info($"schedule skipped for today: {schedule.Id}");
    }
```

Construct both commands in the constructor. Add `using FlowShield.Models;` if it's missing.

- [ ] **Step 6: Route the actions in `MainViewModel`**

```csharp
    public ScheduleService Scheduler { get; private set; } = null!;

    // in the constructor, after Today.ResumeInterruptedSprint():
        Scheduler = new ScheduleService(() => Settings.Schedules);
        Scheduler.Action += (_, a) => OnScheduleAction(a);
        Scheduler.Start();
        Schedule.TemplatesChanged += (_, _) => Today.RefreshTemplates();

    /// <summary>
    /// A schedule's moment (F6). Refused, quietly and with a log line, when a
    /// sprint or break is running, the trial has ended, or a gate is up. A
    /// missed start is only ever offered.
    /// </summary>
    private void OnScheduleAction(ScheduleAction action)
    {
        var template = Settings.FindTemplate(action.Schedule.TemplateId);
        if (template is null) return;

        if (IsSprintRunning || Today.IsOnBreak || IsLocked || TermsGateVisible || FirstRun.IsVisible)
        {
            Log.Info($"schedule {action.Kind} for {template.Name} skipped: busy or gated");
            return;
        }

        switch (action.Kind)
        {
            case ScheduleActionKind.HeadsUp:
                Today.ShowHeadsUp(action, template);
                Notify(NotificationKind.ScheduledSprint, $"{template.Name} in 5 minutes",
                    "Start now or skip it on Today.");
                break;

            case ScheduleActionKind.OfferMissed:
                Today.ShowHeadsUp(action, template);
                break;

            case ScheduleActionKind.Start:
                Today.HideHeadsUp();
                if (Today.StartTemplate(template, skipOpenAppsPanel: true) && !action.Schedule.AskFirst)
                    Notify(NotificationKind.ScheduledSprint, $"{template.Name} started",
                        $"{template.SprintMinutes} minutes at {template.Shield}.");
                break;
        }
    }
```

Check `Notify`'s real signature (grep `public void Notify(`) and match it. Check the name of the break-running property on `TodayViewModel` (`IsOnBreak`).

- [ ] **Step 7: The flag** — in `App.xaml.cs`, beside `--short-sprints`:

```csharp
        if (args.Any(a => a.Equals("--short-schedules", StringComparison.OrdinalIgnoreCase)))
        {
            Models.SchedulePlanner.UseShortSchedules = true;
            Log.Info("short schedule windows enabled by --short-schedules flag");
        }
```

- [ ] **Step 8: Today's XAML** — above the Start button's row, following the profile chip pattern in `TodayView.xaml` (lines 297–321):

```xml
                    <!-- templates (F6): a preset, not a lock -->
                    <ItemsControl ItemsSource="{Binding Templates}" Margin="0,16,0,0"
                                  Visibility="{Binding IsIdle, Converter={StaticResource BoolVis}}">
                        <ItemsControl.ItemsPanel><ItemsPanelTemplate><WrapPanel/></ItemsPanelTemplate></ItemsControl.ItemsPanel>
                        <ItemsControl.ItemTemplate>
                            <DataTemplate>
                                <Button Style="{StaticResource BtnQuiet}" Margin="0,0,8,8" Content="{Binding Name}"
                                        Command="{Binding DataContext.ApplyTemplateCommand, RelativeSource={RelativeSource AncestorType=ItemsControl}}"
                                        CommandParameter="{Binding}"
                                        AutomationProperties.AutomationId="{Binding Name, StringFormat=TemplateChip_{0}}"
                                        AutomationProperties.Name="{Binding Name, StringFormat=Use the {0} template}"/>
                            </DataTemplate>
                        </ItemsControl.ItemTemplate>
                    </ItemsControl>
```

Use whatever property Today already binds to hide idle-only controls during a sprint. If there's no `IsIdle`, bind `IsRunning` through the inverse converter Today already uses.

The heads-up card goes at the top of Today's main column, styled like the break panel card (a `Card` border with `PrimarySoft` background):

```xml
                <Border Style="{StaticResource Card}" Padding="20" Margin="0,0,0,16"
                        Background="{DynamicResource PrimarySoft}" BorderBrush="{DynamicResource Primary}"
                        Visibility="{Binding HeadsUpVisible, Converter={StaticResource BoolVis}}">
                    <StackPanel>
                        <TextBlock Text="{Binding HeadsUpTitle}" Style="{StaticResource H2}"
                                   AutomationProperties.AutomationId="HeadsUpCard"/>
                        <TextBlock Text="{Binding HeadsUpText}" Style="{StaticResource Body}" TextWrapping="Wrap"
                                   Margin="0,4,0,0" AutomationProperties.AutomationId="HeadsUpText"/>
                        <StackPanel Orientation="Horizontal" Margin="0,12,0,0">
                            <Button Style="{StaticResource BtnPrimary}" Content="Start now"
                                    Command="{Binding StartNowCommand}"
                                    AutomationProperties.AutomationId="HeadsUpStartNowButton"/>
                            <Button Style="{StaticResource BtnGhost}" Content="Skip today" Margin="12,0,0,0"
                                    Command="{Binding SkipTodayCommand}"
                                    AutomationProperties.AutomationId="HeadsUpSkipButton"/>
                        </StackPanel>
                    </StackPanel>
                </Border>
```

- [ ] **Step 9: Settings switch** for the scheduled-sprint notification: copy the pattern of the nearest existing per-kind switch (grep `NotificationKind.BreakOver` in `SettingsViewModel.cs` and its XAML). AutomationId `NotifyScheduledSprintToggle`.

- [ ] **Step 10: Docs.** In `Website/changelog.html`, under `<h2>Unreleased</h2>` (create it, per the runbook, if it's missing), add:

```html
      <li>Study templates: Homework evening, Exam prep and Light study, one click on Today, and your own.</li>
      <li>Schedules: a template can start by itself on the days and time you pick, with a heads-up five minutes before and Skip today.</li>
      <li>Sleep Blocking is now the Schedule page; the nightly window is unchanged, at the bottom.</li>
      <li>The Soft notice has a Close button, waits a few seconds before Allow 5 minutes, and shows what you planned.</li>
```

Tick F6 in `LAUNCH_FEATURE_CHECKLIST.md` with a one-paragraph "Done" note in the style of F5's, and the PR number.

- [ ] **Step 11: Build, run tiers 1 and 5, the new and touched tier 3 tests (UI lock), take screenshots of the chips and the heads-up card, commit, open PR C.**

```bash
git commit -m "F6: schedules start, with a heads-up; templates on Today

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

# PR D — turned back, recorded and shown (after 1.0.9 and PR B)

### Task 10: `FocusSession.TurnedBack`, the summary card and History

**Files:**
- Modify: `DesktopApp/Models/AppSettings.cs` (`FocusSession.TurnedBack`)
- Modify: `DesktopApp/ViewModels/TodayViewModel.cs` (`EndSprint` records it; `UpdateSummaryCard` shows it)
- Modify: `DesktopApp/Views/TodayView.xaml` (a summary line)
- Modify: `DesktopApp/Models/HistoryStats.cs` (`Week.TurnedBack`), `DesktopApp/ViewModels/HistoryViewModel.cs`, `DesktopApp/Views/HistoryView.xaml`
- Modify: `automation/csharp/ModelProbe/Commands.cs`; `Website/changelog.html` (one line)
- Test: tiers 1, 3 and 5

**Interfaces:**
- Consumes: `MainViewModel.SoftTurnedBackThisSprint` (Task 7).
- Produces: `FocusSession.TurnedBack` (int, default 0); `HistoryStats.Week.TurnedBack` (int); `TodayViewModel.SummaryTurnedBackText` and `SummaryTurnedBackVisible`; `HistoryViewModel.WeekTurnedBackText`; AutomationIds `SummaryTurnedBackText` and `HistoryTurnedBackText`.

- [ ] **Step 1: Failing tests**
  - Probe command `history-week` {sessions, now} → the `Week` as JSON. Tier 1: a week with sessions of `TurnedBack` 2 and 3 reports `TurnedBack == 5`, and a session outside the week isn't counted.
  - Probe command `turned-back-text` {n} → `"Turned back 1 time"`, `"Turned back 4 times"`, `""` for 0.
  - Tier 5 pins:
    - `EndSprint` sets `_current.TurnedBack = _main.SoftTurnedBackThisSprint;` **before** `_main.Blocker.StopEnforcing();` and before `_main.OnSprintStateChanged()` (which resets the policy).
    - `UpdateSummaryCard` sets `SummaryTurnedBackVisible = session.TurnedBack > 0`.
    - Nothing stores which app was turned back from: `TurnedBack` is an `int`, and `FocusSession` has no new string or list field.
  - Tier 3: a short Soft sprint (with `--short-sprints`) where the notice is answered with Back to work shows "Turned back 1 time" on the summary card, and the saved session has `TurnedBack == 1`. If #250 blocks raising the notice in tier 3, mark this test like the existing Soft tests and rely on tier 1 and tier 5.

- [ ] **Step 2: Watch them fail.**

- [ ] **Step 3: Implement.**
  - `FocusSession`:

```csharp
    /// <summary>
    /// Times the Soft notice was answered with Close or Back to work (1.0.10).
    /// A count only: which app is never recorded.
    /// </summary>
    public int TurnedBack { get; set; }
```

  - `EndSprint`, right after `_current.NudgesSent = _nudgesThisSprint;`: `_current.TurnedBack = _main.SoftTurnedBackThisSprint;`
  - Add a pure helper to `HistoryStats`, `public static string TurnedBackText(int n) => n <= 0 ? "" : n == 1 ? "Turned back 1 time" : $"Turned back {n} times";`, and use it in both places.
  - `Week` gains `int TurnedBack` as its last positional field, and `ForWeek` passes `inWeek.Sum(s => s.TurnedBack)`. Fix every `new Week(` caller (grep).
  - `UpdateSummaryCard`: `SummaryTurnedBackText = HistoryStats.TurnedBackText(session.TurnedBack); SummaryTurnedBackVisible = session.TurnedBack > 0;`
  - The summary card XAML gets a `Caption` line under the distractions line, bound with `BoolVis`. History's week card gets a line beside distractions caught ("Turned back 11 times"), hidden at zero.
  - Changelog `Unreleased`: `<li>The summary card and History show how many times you turned back from a blocked app.</li>`

- [ ] **Step 4: Run tiers 1 and 5, the touched tier 3 tests, and screenshots; commit; open PR D.**

```bash
git commit -m "Turned back: counted per sprint, shown on the card and in History

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

# PR E — the Jump List (after 1.0.9 and PR A)

### Task 11: Start a sprint from the taskbar

**Files:**
- Create: `DesktopApp/Models/StartSprintArg.cs` (pure parsing), `DesktopApp/Services/JumpListService.cs`
- Modify: `DesktopApp/App.xaml.cs:179-191` (hand the argument over at startup and from a second launch)
- Modify: `DesktopApp/ViewModels/MainViewModel.cs` (`HandleStartSprintArg`; rebuild the Jump List on `Schedule.TemplatesChanged`)
- Modify: `automation/csharp/ModelProbe/Commands.cs`; `Website/changelog.html`
- Test: tiers 1, 5 and 3

**Interfaces:**
- Produces:
  - `static class StartSprintArg { const string Flag = "--start-sprint"; static bool TryFind(IEnumerable<string> args, out string? templateId); }` — `--start-sprint` → true with a null id; `--start-sprint=abc` → true with `"abc"`; case-insensitive; otherwise false.
  - `static class JumpListService { static void Rebuild(IReadOnlyList<StudyTemplate> templates, string exePath); }`
  - `MainViewModel.HandleStartSprintArg(IEnumerable<string> args)`

- [ ] **Step 1: Failing tests**
  - Probe `start-arg` {args} → {found, id}. Cases: `["--tray"]` → false; `["--start-sprint"]` → true, null; `["--START-SPRINT=abc"]` → true, "abc"; `["--start-sprint="]` → true, null.
  - Tier 5 pins:
    - `HandleStartSprintArg` starts only through `Today.StartTemplate(` or the same method the tray's "Start sprint (last settings)" uses (grep `BuildTrayMenu` in `MainWindow.xaml.cs` for its call), so the F2 and trial gates apply.
    - `JumpListService` uses `System.Windows.Shell.JumpList` and `JumpTask`, and never writes the registry.
    - `App.xaml.cs` calls `HandleStartSprintArg` both at startup and inside `Instance?.Listen(`.
    - A missing template id leads to `Toast(` and no start (review focus 5).
  - Tier 3: launch the app with `--start-sprint=<the Light study id>` (read the id from the settings after a first launch; the fixture relaunches), and confirm a Soft sprint is running. Then launch a second process with `--start-sprint=missing`, and confirm no second sprint and the toast "That template isn't here any more".

- [ ] **Step 2: Watch them fail.**

- [ ] **Step 3: Implement**

```csharp
namespace FlowShield.Models;

/// <summary>The Jump List's argument: --start-sprint, or --start-sprint=&lt;templateId&gt;.</summary>
public static class StartSprintArg
{
    public const string Flag = "--start-sprint";

    public static bool TryFind(IEnumerable<string> args, out string? templateId)
    {
        templateId = null;
        foreach (var arg in args)
        {
            if (arg.Equals(Flag, StringComparison.OrdinalIgnoreCase)) return true;
            if (arg.StartsWith(Flag + "=", StringComparison.OrdinalIgnoreCase))
            {
                var id = arg[(Flag.Length + 1)..].Trim();
                templateId = id.Length == 0 ? null : id;
                return true;
            }
        }
        return false;
    }
}
```

```csharp
using System.Windows;
using System.Windows.Shell;
using FlowShield.Models;

namespace FlowShield.Services;

/// <summary>
/// The taskbar Jump List (1.0.10): "Start sprint" and one "Start ‹template›"
/// per template. Each relaunches FlowShield with --start-sprint, which the
/// single-instance pipe hands to the running copy. A per-user shell feature:
/// no registry, no admin.
/// </summary>
public static class JumpListService
{
    public static void Rebuild(IReadOnlyList<StudyTemplate> templates, string exePath)
    {
        try
        {
            var list = new JumpList { ShowRecentCategory = false, ShowFrequentCategory = false };
            list.JumpItems.Add(new JumpTask
            {
                Title = "Start sprint",
                Description = "Start a sprint with your last settings",
                ApplicationPath = exePath,
                Arguments = StartSprintArg.Flag,
                IconResourcePath = exePath,
            });
            foreach (var t in templates)
            {
                list.JumpItems.Add(new JumpTask
                {
                    Title = $"Start {t.Name}",
                    Description = $"{t.SprintMinutes} minutes at {t.Shield}",
                    ApplicationPath = exePath,
                    Arguments = $"{StartSprintArg.Flag}={t.Id}",
                    IconResourcePath = exePath,
                });
            }
            JumpList.SetJumpList(Application.Current, list);
            list.Apply();
        }
        catch (Exception ex)
        {
            // A missing Jump List costs a shortcut, never the app.
            Log.Warn($"could not build the jump list: {ex.Message}");
        }
    }
}
```

`MainViewModel`:

```csharp
    /// <summary>A --start-sprint launch (the Jump List). Same gates as the tray start.</summary>
    public void HandleStartSprintArg(IEnumerable<string> args)
    {
        if (!StartSprintArg.TryFind(args, out var templateId)) return;
        if (templateId is null)
        {
            // Match exactly what the tray's "Start sprint (last settings)" calls.
            Today.StartSprintFromTray();
            return;
        }
        var template = Settings.FindTemplate(templateId);
        if (template is null)
        {
            CurrentPage = AppPage.Today;
            Toast("That template isn't here any more. Pick one on Today.");
            return;
        }
        Today.StartTemplate(template, skipOpenAppsPanel: false);
    }
```

Replace `Today.StartSprintFromTray()` with the real method the tray menu calls (grep `BuildTrayMenu`). In `App.xaml.cs`: after `ViewModel.HandleLink(DeepLink.FindLink(args));`, add `ViewModel.HandleStartSprintArg(args);`. Inside the `Listen` callback, after `ViewModel.HandleLink(...)`, add `ViewModel.HandleStartSprintArg(launchArgs);`. After the window is shown, add `if (Environment.ProcessPath is { } exe) Services.JumpListService.Rebuild(ViewModel.Settings.Templates, exe);`, and subscribe `Schedule.TemplatesChanged` to rebuild it too. Make sure `Program.cs` passes `--start-sprint` arguments through `SingleInstance.SendToRunningInstance(args)` unchanged; it forwards all of them.

Changelog `Unreleased`: `<li>Right-click FlowShield on the taskbar to start a sprint or any template.</li>`

- [ ] **Step 4: Run the tests, build, take a screenshot of the taskbar Jump List (right-click the pinned or running icon), commit, open PR E.**

```bash
git commit -m "Jump List: start a sprint or a template from the taskbar

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Where this plan refines the spec

These are decided here, and the spec is updated to match in the same docs PR:

1. `StudyTemplate.CycleSprints` uses the existing `CycleState.CycleChoices` values `{0, 2, 3, 4}` (0 = one sprint), not 1–4.
2. Built-ins carry a `BuiltInKey` ("homework", "exam", "light") instead of a `BuiltIn` bool, so **Restore built-ins** can tell which one is missing.
3. A template with no profile, or one whose profile was deleted, uses the **active** profile, not the "default" one; after F9, "default" only means the first profile.
4. Delivery is five PRs, not six. The models and the Schedule page are one PR (A), because a page PR stacked on an unmerged models PR is the stacked-PR problem in `CLAUDE.md`.
5. `TemplatesSeeded` records that the built-ins were added, so deleting every template is respected.
6. Tier 1 gains `ModelProbe`, which runs the real C# for the date, time-zone and Soft rules.
