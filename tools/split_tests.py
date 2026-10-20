"""Deterministically split the tier 1/3/5 monoliths, then prove collection identity.

Run ``python tools/split_tests.py`` from the split branch. Existing output
packages or the baseline manifest are an error unless --overwrite is supplied.
--check repeats the AST, collection/marker and ordering proof without writing.
No test is executed: every pytest invocation here uses --collect-only.

After the pending test-append PRs merge (on this branch, never main):
  git fetch origin
  git rebase origin/main
  # Resolve modify/delete conflicts by retaining main's latest monoliths.
  git restore --source=origin/main --worktree -- automation/tests/test_tier1_unit.py automation/tests/test_tier3_e2e.py automation/tests/test_tier5_regressions.py
  python tools/split_tests.py --overwrite
  python tools/split_tests.py --check
  $env:FLOWSHIELD_SERVER_PORT='3385'
  $env:FLOWSHIELD_WEBSITE_PORT='5585'
  python -m pytest automation/tests -m "not ui and not stripe" -q -p no:cacheprovider
  python tools/repo_lint/check.py

--overwrite deletes/recreates only the three generated tier packages and their
manifest. It is equivalent to deleting those outputs before running the script.
The committed _split_baseline.json is also runtime data: the root conftest uses
its original collection order to keep UI tests and fixture lifetimes ordered
across area modules. Keep it with the packages; it is not a temporary report.
The input revision defaults to origin/main; --source-ref selects another git
revision. Inputs must match that revision, so --check can independently retrieve
and compare every definition rather than trusting generated AST hashes.

Exact class-name mappings below are deliberately easy to extend. Unseen tests
go to test_misc.py and are printed. Non-test definitions live once in _helpers;
module fixtures live in the tier conftest and retain their original lifetime
through package registration. Interdependent test classes stay together.
Only filesystem-depth and moved-module references are adapted; the
checker compares both original and adapted ASTs and prints each adapted name.
After this migration merges, edit area files directly.
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = {1: "test_tier1_unit.py", 3: "test_tier3_e2e.py", 5: "test_tier5_regressions.py"}
GENERATED = "# Split by tools/split_tests.py; edit this area directly after merge.\n"
MANIFEST = "_split_baseline.json"
SELECTIONS = ("all", "ui", "stripe", "e2e", "touches_user_state", "not ui and not stripe")

# Lists contain test classes only. Helpers/constants are inferred, never copied
# separately into each test module. Ordering is recovered by the collection hook.
GROUPS = {
    1: {
        "licensing": """TestLicenseKeyFormat TestFreeTrial TestTrialEndingNotice
            TestRateLimiter TestActivationLinkParsing TestLicenseWaitCopy TestDeviceToken""",
        "sprints": """TestMomentum TestSprintResume TestASprintIsRecordedAsEndingWhenItDid
            TestEndSprintPolicy TestSprintSummaryCard TestSprintIntention TestCustomSprintLengths
            TestMomentumTrend TestMomentumTrendView TestHistoryStats TestGracefulClose""",
        "blocking": """TestSleepWindow TestTimeParsing TestProcessNameNormalisation
            TestAppSuggestions TestPickerSearch TestPerAppSwitch TestPreSprintRunningApps
            TestSoftOverlayPolicy TestBlocklistProfileRules TestPickerListsOnlyInstalledApps
            TestPickerSkipsThingsThatArentApps TestStoreAppsAreBlockedTimidly""",
        "goals_journal": """TestDailyGoalProgress TestDailyGoalSkips TestDailyGoalStreak
            TestDailyGoalSource TestJournalExportFormulaInjection TestJournalExportCsv
            TestJournalExportMarkdown TestJournalExportFileName TestJournalExportSource""",
        "settings_privacy": """TestNotificationPolicy TestTermsAcceptance TestFirstRunPolicy
            TestSettingsSaveDoesNotRaceItsMutators TestDataPrivacyExport TestYourDataSettingsCard""",
        "breaks": """TestBreakLength TestBreakIsOfferedOnlyForAFinishedSprint TestBreaksChangeNothingElse
            TestCycles TestBreakSurvivesARestart TestBreaksAndCyclesSource TestBreakCopyInTheSleepWindow""",
        "desktop": """TestSpaceShortcutSource TestGlobalHotkeySource TestTrayMenuSource
            TestTokenContrast TestSettingsIsGrouped TestTimerRingDrains TestWindowFitsTheWorkArea""",
        "tooling": "TestDocSteward TestIssueHygieneChecks TestConfiguredPortsReachTheServer TestReportHistory",
    },
    3: {
        "shell": """TestAppShell TestShieldWording TestTermsGate TestNotificationSettings
            TestFirstRun TestOneInstance TestLightTheme TestSettingsRail""",
        "blocking": """TestBlockedApps TestBlocklistProfiles TestPreSprintWarning
            TestFirmWarnsBeforeClosing TestDistractionsAreCountedPerApp TestAppPicker""",
        "soft_shield": "TestSoftShowsTheNotice",
        "sprints": """TestSprints TestSprintIntention TestEndingASprint
            TestMomentumTrendAndExplainer TestSpaceStartsAndEndsASprint""",
        "licensing": """TestTrialUnlocksEverything TestTrialEnded TestTrialExpiringDuringASprint
            TestPurchaseToActivation TestPurchaseUnlocksAnExpiredTrial TestActivationLinks""",
        "goals_data": "TestDailyGoal TestJournalExport TestYourDataCard TestHistoryPage",
        "breaks_schedule": "TestBreaksAndCycles TestSchedulePage TestScheduledSprints TestJumpList",
    },
    5: {
        "claims_privacy": """TestLegalPagesMatchTheProduct TestPrivacyClaimsMatchTheCode
            TestWebsiteClaimsMatchTheApp TestFirmWarnsBeforeItCloses TestSoftShieldWording
            TestShieldWordingIsCanonical TestSuccessPageHonesty TestPurchaseFlowCopy
            TestNoDeveloperTextOnCustomerSurfaces TestHonestLimitsAndPriceComparison
            TestSupportPageDescribesTheShippedApp TestThirdPartyNoticesShip
            TestTheSiteDescribesTheCloseTheAppDoes TestFontAndSiteIconNoticesShip""",
        "licensing": """TestPaymentLinkPurchase TestCheckoutManagedPayments TestLicenseRevocation
            TestHonestWaitingNeverClaimsInvalidKey TestActivateButtonStaysDisabledWhileBusy
            TestEmailIsNotAuthentication TestSurvivesDataLoss TestTrialThenOneTimePurchase
            TestTrialNeverNagsDuringASprint TestDevicesListIsFetchedOnDemandOnly
            TestDeviceReleaseNeedsConfirmation TestDeviceCapShowsTheListInline TestResendCooldown""",
        "settings_safety": """TestSettingsLocation TestSuiteLeavesUserSettingsAlone
            TestSettingsReadRacesTheAtomicWrite TestSettingsSaveRaceRegression
            TestTheSuiteLeavesTheOwnersTrialAlone""",
        "desktop_lifecycle": """TestAutomaticUpdateWiring TestBrandedAppIcon TestReleaseShipsAnArm64Build
            TestStartWithWindowsSource TestStartWithWindowsBehaviour TestPersistenceAcrossRestart
            TestQuitEndsAnyRunningSprint TestActivationLinkWorks TestDeepLinkRegistrationRecovery
            TestUninstallCleansUp TestOneInstanceOnly TestDeleteEverythingRestartRegressions
            TestFriendlyErrorDialog""",
        "blocking": """TestBlocklistThreadSafety TestBlockedAppNotifies TestSleepBlockingEnforces
            TestEveryProcessOfAnAppIsBlocked TestPerAppSwitchGuard
            TestEnforcementBookkeepingIsForgottenWhenTheWindowCloses
            TestEmptyProfileForgetsEnforcementBookkeeping TestTheSleepWindowNeverDropsBelowFirm
            TestBlocklistProfilesKeepTheirPromises TestQuickStartBringsOpenAppQuestionForward
            TestBlockerSweepStopsWhenEnforcementEnds TestSealedToastNamesTheApp
            TestBlockedAppsListKeepsItsViewport""",
        "soft_shield": """TestSoftOverlayNeverCloses TestSoftCloseNeverKills
            TestSoftNoticeFriction TestTurnedBackIsRecordedAndShown""",
        "sprints": """TestTodayCounters TestSprintSurvivesRestart TestNoOneClickEscape
            TestCustomSprintLengthsWired TestCustomSprintLengthBehaviour TestSprintSummaryCard
            TestSummaryCardSeesTheSettledStreak TestSprintIntentionGuard TestDistractionCountIsPerApp
            TestResumingDoesNotCreditTimeFlowShieldWasClosed TestTimeUpAfterSleepUsesWatchedTime
            TestShortSprintsCannotBuyCredit TestACompletedSprintDoesNotCountTheSleep300
            TestLockScreenWaitsForResumedFocus TestMilestoneCardClearsOnTheNextSprint""",
        "goals_history": """TestDailyGoalRegressions TestStreakCountsADayItAlreadySettled
            TestTheGoalSeesTheSprintThatJustFinished TestTheTrendLeavesAnInterruptedSprintAlone TestHistoryPage""",
        "keyboard_notifications": """TestNotificationsStayQuiet TestFirstRunNeverNags
            TestTrayAndKeyboardNeverBypassTheEndFlow TestSpaceRefusedUnderFirstRun
            TestGlobalHotkeyHookIsNeverStacked""",
        "breaks": """TestABreakStandsTheShieldDown TestNothingSellsOrLocksDuringABreak
            TestTheRingSaysWhichClockIsRunning TestTheTrayFollowsTheBreak TestCycleTextFollowsTheSprintLength
            TestBreakCommandsRefreshCanExecute""",
        # These are the two consumers of the offscreen theme/layout probe.
        "theme_probe": "TestBreakCopyTracksScheduledSleepWindow TestTheThemeActuallySwitchesF21",
        # These classes reference each other's bench helpers; keep one globals dict.
        "schedule_lifecycle": """TestSchedulePageKeepsTheSleepWindow TestSchedulePageRefusesInTheViewModel
            TestSchedulePageNamesAndLabels TestScheduledSprintsGoThroughStart
            TestTodayGrewARowAndItsControlsStayReachable TestTheJumpListStartsLikeTheTray
            TestDeleteEverythingClearsTheJumpList TestTheSchedulerTickIsNotStarved316
            TestTheSprintClockIsNotStarved319 TestTheRenameToBasaltKeepsWhatCustomersHave321
            TestDeleteEverythingKeepsTheTrialStart""",
        "design_tokens": """TestDesignTokensStayInSync TestNoLegacyColourAliases
            TestContrastAndTokensA3 TestNoHardcodedColoursA3 TestCornerRadiusNormalisedA2
            TestPillsAreComputed TestLightThemeSwitchF21 TestStoneLook""",
        "window_layout": """TestSmallScreenLayout TestBlockedAppsRowSwitchNotClipped
            TestAppAdaptsToItsWindow TestTheWindowFitsTheWorkArea296 TestTodayDeclutter147
            TestTodayPolishFromThe1011VmRun""",
        "design_controls": """TestNavigationUsesIconsNotUnicodeGlyphs TestInterTypeScale
            TestShieldGlyphsA4 TestTimerRingA4 TestTodayAutomationIdsUnchangedA4 TestMotionA4
            TestKeyboardAndFocusF21 TestAccessibleNamesF21 TestMinorReviewFindings
            TestLastReviewFindings TestCausewayLogoIsTheBrandMark""",
        "website": """TestFooterLinksPointToRealPages TestWebsiteAccessibilityStyles TestSuccessPageKeyRecovery
            TestDownloadGuidePanel TestProductCaptures TestDesignReviewFixesB4 TestLandingPageLengthB5
            TestSiteToneB6 TestPhoneVisitorMarkup TestSiteConversionPass TestTheSiteStaysOfflineForTheBeta
            TestSiteFontsAreSelfHosted TestSiteSystemPassB3 TestSiteServerOverrideIsLocalOnly""",
        "tooling": "TestIssueHygieneStaysAdvisory TestTheUiSuiteCanObserveWhatItAsserts",
    },
}
AREAS = {tier: {name: area for area, text in groups.items() for name in text.split()}
         for tier, groups in GROUPS.items()}


def names(node: ast.AST) -> set[str]:
    """Names loaded anywhere in a definition, including decorators/annotations."""
    return {n.id for n in ast.walk(node)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def bound_names(node: ast.AST) -> set[str]:
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return {node.name}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {alias.asname or alias.name.split(".")[0] for alias in node.names}
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {n.id for target in targets for n in ast.walk(target)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    raise ValueError(f"Unsupported top-level {type(node).__name__} at line {node.lineno}")


# Every allowed AST difference is an exact expression/import replacement here.
# The checker applies this allowlist to the original AST independently of the
# text mover, so an unrelated assertion/body edit cannot pass as a relocation.
EXPRESSION_MOVES = [
    (None, None, "Path(__file__).resolve().parent.parent.parent", "Path(__file__).resolve().parents[3]"),
    (None, None, "Path(__file__).resolve().parent.parent", "Path(__file__).resolve().parents[2]"),
    (3, "current_terms_version", "Path(__file__).resolve().parents[2]", "Path(__file__).resolve().parents[3]"),
    (5, "TestTheUiSuiteCanObserveWhatItAsserts",
     'Path(DESKTOP_DIR).parent / "automation" / "tests" / "test_tier3_e2e.py"',
     'Path(DESKTOP_DIR).parent / "automation" / "tests" / "tier3"'),
    (5, "TestTheUiSuiteCanObserveWhatItAsserts",
     'self.TIER3.read_text(encoding="utf-8")', 'read_test_package(self.TIER3)'),
    (5, "TestTheUiSuiteCanObserveWhatItAsserts",
     '(self.TIER3, self.CONTROLLER)', '(*source_files(self.TIER3), self.CONTROLLER)'),
    (5, "TestSchedulePageNamesAndLabels",
     'sorted((root / "automation" / "tests").glob("test_tier*.py"))',
     'all_test_sources(root / "automation" / "tests")'),
    (5, "TestSchedulePageNamesAndLabels",
     'f\'"{path.name}":\'', 'f\'"{report_key(path)}":\''),
]
IMPORT_MOVES = {
    "test_break_check_rejects_a_question_before_the_decoy_exists": "test_breaks_schedule",
    "test_soft_refocus_handles_foreground_lock_and_always_detaches": "test_soft_shield",
}
SOURCE_HELPERS = {"read_test_package", "source_files", "all_test_sources", "report_key"}


def replacements(tier: int, name: str) -> list[tuple[str, str]]:
    return [(old, new) for selected_tier, selected_name, old, new in EXPRESSION_MOVES
            if selected_tier in (None, tier) and selected_name in (None, name)]


def expression_map(tier: int, name: str) -> dict[str, tuple[str, str]]:
    return {ast.dump(ast.parse(old, mode="eval").body): (old, new)
            for old, new in replacements(tier, name)}


def relocation_edits(text: str, tier: int, name: str) -> list[tuple[ast.AST, str, str, str]]:
    """Locate exact AST expressions; whitespace/Unicode do not affect matching."""
    moves = expression_map(tier, name)
    edits = []

    def visit(node, owner="", method=""):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = f"{owner}.{node.name}" if owner else node.name
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method = node.name
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and not method:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            owner += "." + ",".join(ast.unparse(target) for target in targets)
        replacement = moves.get(ast.dump(node))
        if replacement:
            old, new = replacement
            edits.append((node, old, new, owner))
            return  # Match the whole path, not its nested shorter parent chain.
        if (tier == 5 and name == "TestTheUiSuiteCanObserveWhatItAsserts"
                and method in IMPORT_MOVES and isinstance(node, ast.ImportFrom)
                and ast.dump(node) == ast.dump(ast.parse("from tests import test_tier3_e2e as tier3").body[0])):
            old = "from tests import test_tier3_e2e as tier3"
            new = f"from tests.tier3 import {IMPORT_MOVES[method]} as tier3"
            edits.append((node, old, new, owner))
            return
        for child in ast.iter_child_nodes(node):
            visit(child, owner, method)

    visit(ast.parse(text))
    return edits


def moved_text(text: str, tier: int, node: ast.AST) -> str:
    raw = text.encode("utf-8")
    starts = [0]
    for line in raw.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    edits = []
    for expression, old, new, owner in relocation_edits(text, tier, getattr(node, "name", "")):
        start = starts[expression.lineno - 1] + expression.col_offset
        end = starts[expression.end_lineno - 1] + expression.end_col_offset
        edits.append((start, end, new.encode("utf-8")))
    for start, end, replacement in sorted(edits, reverse=True):
        raw = raw[:start] + replacement + raw[end:]
    return raw.decode("utf-8")


class AllowedMoves(ast.NodeTransformer):
    def __init__(self, tier: int, name: str):
        self.tier = tier
        self.definition = name
        self.method = ""
        self.moves = {ast.dump(ast.parse(old, mode="eval").body): ast.parse(new, mode="eval").body
                      for old, new in replacements(tier, name)}

    def visit(self, node):
        replacement = self.moves.get(ast.dump(node))
        return replacement if replacement is not None else super().visit(node)

    def visit_FunctionDef(self, node):
        previous = self.method
        self.method = node.name
        result = self.generic_visit(node)
        self.method = previous
        return result

    def visit_ImportFrom(self, node):
        if (self.tier == 5 and self.definition == "TestTheUiSuiteCanObserveWhatItAsserts"
                and self.method in IMPORT_MOVES and node.module == "tests"
                and ast.dump(node) == ast.dump(ast.parse("from tests import test_tier3_e2e as tier3").body[0])):
            return ast.parse(f"from tests.tier3 import {IMPORT_MOVES[self.method]} as tier3").body[0]
        return node


def area_map(tree: ast.Module, tier: int) -> dict[str, str]:
    """Infer helpers; co-locate cross-class dependencies and scoped fixtures."""
    owners = {}
    classes = {}
    fixtures = {}
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Expr)):
            continue
        bound = bound_names(node)
        for name in bound - {"pytestmark"}:
            if isinstance(node, ast.ClassDef) and name.startswith("Test") or (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and name.startswith("test_")
            ):
                owners[name] = AREAS[tier].get(name, "misc")
                classes[name] = node
                if name not in AREAS[tier]:
                    print(f"FALLBACK tier{tier}/test_misc.py: {name}")
            else:
                owners[name] = "_helpers"
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            "fixture" in ast.unparse(d) for d in node.decorator_list
        ):
            fixtures[node.name] = node

    def merge(related: set[str], reason: str) -> None:
        if not related:
            return
        areas = {owners[name] for name in related}
        target = sorted(areas - {"misc"})[0] if areas - {"misc"} else "misc"
        if len(areas) > 1:
            print(f"CO-LOCATE tier{tier}: {reason}: {sorted(areas)} -> {target}")
            for name in owners:
                if owners[name] in areas:
                    owners[name] = target

    for name, node in classes.items():
        merge({name} | (names(node) & classes.keys()), f"{name} class dependencies")
    for name in fixtures:
        owners[name] = "_fixtures"
    return owners


def plan_tier(source: str, tier: int) -> dict[str, str]:
    """Build all output in memory, validating dependencies before any writes."""
    tree = ast.parse(source)
    assignments = area_map(tree, tier)
    lines = source.splitlines(keepends=True)
    imports: list[tuple[ast.AST, str]] = []
    definitions: dict[str, tuple[ast.AST, str, set[str]]] = {}
    blocks: dict[str, list[str]] = defaultdict(list)
    required: dict[str, set[str]] = defaultdict(set)
    owners: dict[str, str] = {}
    module_marks: list[str] = []
    previous_end = 0
    for index, node in enumerate(tree.body):
        text = "".join(lines[previous_end:node.end_lineno])
        previous_end = node.end_lineno
        if (index == 0 and isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            continue  # Each area gets its own short module docstring.
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append((node, text.strip()))
            continue
        bound = bound_names(node)
        if bound == {"pytestmark"}:
            module_marks.append(text.strip())
            continue
        missing = bound - assignments.keys()
        if missing:
            raise ValueError(f"Tier {tier}: unmapped definitions: {', '.join(sorted(missing))}")
        areas = {assignments[name] for name in bound}
        if len(areas) != 1:
            raise ValueError(f"Tier {tier}: one assignment spans areas: {bound}")
        area = areas.pop()
        if bound & owners.keys():
            raise ValueError(f"Tier {tier}: duplicate top-level definition: {bound}")
        for name in bound:
            owners[name] = area
            definitions[name] = (node, text, bound)
        blocks[area].append(moved_text(text, tier, node))
        required[area].update(names(node))

    outputs = {"__init__.py": f'"""Tier {tier} tests, grouped by area."""\n'}
    for area in sorted(blocks):
        dependencies: dict[str, list[str]] = defaultdict(list)
        for name in sorted(required[area] & owners.keys()):
            owner = owners[name]
            if owner == area or owner == "_fixtures":
                continue
            if owner != "_helpers":
                raise ValueError(f"Tier {tier}: {area} references {name} in {owner}; "
                                 "co-locate test classes or move shared helpers to _helpers")
            dependencies[owner].append(name)
        used = required[area].copy()
        for mark in module_marks:
            used.update(names(ast.parse(mark)))
        selected_imports = []
        for node, text in imports:
            if (isinstance(node, ast.ImportFrom) and node.module == "__future__"
                    or bound_names(node) & used):
                selected_imports.append(text)
        for owner, imported in sorted(dependencies.items()):
            selected_imports.append(f"from .{owner} import {', '.join(imported)}")
        source_helpers = names(ast.parse("".join(blocks[area]))) & SOURCE_HELPERS
        if source_helpers:
            selected_imports.append("from tests._split_support import " + ", ".join(sorted(source_helpers)))
        # Helpers are not collected test modules, so they do not inherit pytestmark.
        marks = module_marks if area not in ("_helpers", "_fixtures") else []
        header = (GENERATED + f'"""Tier {tier}: {area.replace("_", " ")}."""\n\n'
                  + "\n".join(selected_imports) + "\n\n")
        filename = {"_helpers": "_helpers.py", "_fixtures": "conftest.py"}.get(area, f"test_{area}.py")
        outputs[filename] = header + ("\n\n".join(marks) + "\n\n" if marks else "") + "".join(blocks[area]).rstrip() + "\n"
        if area == "_fixtures":
            # Register module fixtures for the enclosing tier package. The moved
            # function, including its original decorator, stays byte-for-byte.
            # Only registration changes: one original module == one tier package.
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and assignments.get(node.name) == "_fixtures":
                    for decorator in node.decorator_list:
                        if not (isinstance(decorator, ast.Call) and any(
                            kw.arg == "scope" and isinstance(kw.value, ast.Constant) and kw.value.value == "module"
                            for kw in decorator.keywords
                        )):
                            continue
                        registration = copy.deepcopy(decorator)
                        for kw in registration.keywords:
                            if kw.arg == "scope":
                                kw.value = ast.Constant("package")
                        outputs[filename] += (f'\n# Preserve the original tier-module lifetime across area modules.\n'
                                              f'{node.name} = {ast.unparse(registration)}({node.name}.__wrapped__)\n')
        ast.parse(outputs[filename], filename=filename)
    return outputs


def canonical(nodeid: str) -> str:
    """Ignore only the module move; retain class, test and parameter identity."""
    nodeid = nodeid.replace("\\", "/")
    for tier, filename in INPUTS.items():
        nodeid = re.sub(rf"/tier{tier}/test_[^/:]+\.py(?=::)", "/" + filename, nodeid)
    return nodeid


def collect(root: Path, *, originals: bool = False) -> dict[str, list[str]]:
    env = dict(os.environ, FLOWSHIELD_SERVER_PORT="3385", FLOWSHIELD_WEBSITE_PORT="5585",
               PYTHONIOENCODING="utf-8")
    result = {}
    for selection in SELECTIONS:
        command = [sys.executable, "-m", "pytest", "automation/tests", "--collect-only", "-q",
                   "-p", "no:cacheprovider", "-o", "addopts=", "--color=no"]
        if selection != "all":
            command.extend(["-m", selection])
        if originals:
            for tier in INPUTS:
                command.extend(["--ignore", f"automation/tests/tier{tier}"])
        run = subprocess.run(command, cwd=root, env=env, capture_output=True,
                             encoding="utf-8", errors="replace")
        if run.returncode not in (0, 5):
            raise ValueError(f"Collection failed ({selection}):\n{run.stdout}\n{run.stderr}")
        ids = [canonical(line.strip()) for line in run.stdout.splitlines()
               if "::" in line and line.strip().startswith("tests/")]
        if not ids and selection == "all":
            raise ValueError(f"Could not parse collected IDs:\n{run.stdout}")
        result[selection] = ids
        print(f"  {selection}: {len(ids)} collected", flush=True)
    return result


def revision_sources(root: Path, revision: str) -> tuple[str, dict[int, str]]:
    commit = subprocess.check_output(["git", "rev-parse", revision], cwd=root, text=True).strip()
    return commit, {tier: subprocess.check_output(
        ["git", "show", f"{commit}:automation/tests/{filename}"], cwd=root
    ).decode("utf-8") for tier, filename in INPUTS.items()}


def definitions(source: str) -> dict[str, ast.AST]:
    return {n.name: n for n in ast.parse(source).body
            if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}


def dump(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def test_pairs(source: str) -> Counter:
    """Declared (class, test) identities, independently of pytest parameters."""
    pairs = Counter()
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            pairs.update((node.name, method.name) for method in node.body
                         if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                         and method.name.startswith("test_"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            pairs[("", node.name)] += 1
    return pairs


def check(root: Path, baseline: dict) -> None:
    """Independently reconstruct all outputs and compare definition ASTs."""
    _, sources = revision_sources(root, baseline["source_commit"])
    tests = root / "automation" / "tests"
    unchanged = adapted = 0
    for tier, source in sources.items():
        outputs = plan_tier(source, tier)
        actual = {}
        actual_pairs = Counter()
        for path in sorted((tests / f"tier{tier}").glob("*.py")):
            actual_source = path.read_text(encoding="utf-8")
            actual_pairs.update(test_pairs(actual_source))
            for name, node in definitions(actual_source).items():
                if name in actual:
                    raise ValueError(f"Duplicate moved definition: tier{tier}.{name}")
                actual[name] = node
        original_pairs = test_pairs(source)
        if actual_pairs != original_pairs:
            raise ValueError(f"Tier {tier}: declared (class, test) identities changed")
        print(f"tier{tier} declared test pairs: {original_pairs.total()} before / {actual_pairs.total()} after")
        original = definitions(source)
        expected = {name: node for text in outputs.values() for name, node in definitions(text).items()}
        if actual.keys() != original.keys():
            raise ValueError(f"Tier {tier}: moved definition names changed")
        for name, node in original.items():
            allowed = AllowedMoves(tier, name).visit(copy.deepcopy(node))
            if dump(actual[name]) != dump(allowed):
                raise ValueError(f"Tier {tier}: AST difference outside the exact path/import allowlist: {name}")
            if dump(actual[name]) != dump(expected[name]):
                raise ValueError(f"Tier {tier}: unexpected body change: {name}")
            if dump(node) == dump(actual[name]):
                unchanged += 1
            else:
                adapted += 1
                for expression, old, new, owner in relocation_edits(ast.unparse(node), tier, name):
                    print(f"  tier{tier}.{owner}: {old} -> {new}")
        # Compare complete output too: imports, marks, constants and source text.
        for filename, expected_source in outputs.items():
            if (tests / f"tier{tier}" / filename).read_text(encoding="utf-8") != expected_source:
                raise ValueError(f"Tier {tier}: generated source differs: {filename}")
        if {p.name for p in (tests / f"tier{tier}").glob("*.py")} != outputs.keys():
            raise ValueError(f"Tier {tier}: unexpected generated modules")
    print(f"AST identity: {unchanged} unchanged definitions; {adapted} location/import adaptations")
    # Reference updates also touch singleton test files. Verify their complete
    # function/class ASTs, plus every pre-existing root fixture/hook definition.
    paths = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", baseline["source_commit"], "automation/tests"],
        cwd=root, text=True,
    ).splitlines()
    retained = 0
    for filename in paths:
        path = Path(filename)
        if (path.suffix != ".py" or path.name in INPUTS.values()
                or not (path.name.startswith("test_") or filename == "automation/tests/conftest.py")):
            continue
        original = definitions(subprocess.check_output(
            ["git", "show", f'{baseline["source_commit"]}:{filename}'], cwd=root
        ).decode("utf-8"))
        actual = definitions((root / filename).read_text(encoding="utf-8"))
        if path.name != "conftest.py" and original.keys() != actual.keys():
            raise ValueError(f"Unsplit test definitions changed: {filename}")
        for name, node in original.items():
            if name not in actual or dump(node) != dump(actual[name]):
                raise ValueError(f"Unsplit test/fixture body changed: {filename}:{name}")
            retained += 1
    print(f"Unsplit tests/root fixtures: {retained} unchanged definitions")
    print("Before split (recorded from the restored originals):", flush=True)
    for selection, ids in baseline["collection"].items():
        print(f"  {selection}: {len(ids)} collected", flush=True)
    print("After split:", flush=True)
    after = collect(root)
    for selection, before in baseline["collection"].items():
        if Counter(after[selection]) != Counter(before):
            missing = list((Counter(before) - Counter(after[selection])).elements())
            extra = list((Counter(after[selection]) - Counter(before)).elements())
            raise ValueError(f"{selection}: identity changed; missing={missing}, extra={extra}")
        if before != after[selection]:
            mismatch = next((a, b) for a, b in zip(before, after[selection]) if a != b)
            raise ValueError(f"{selection}: collection order changed: {mismatch}")
    print("Identity PASS: same test IDs/pairs, parameters, multiplicities, marker selections and order.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--source-ref", default="origin/main")
    args = parser.parse_args()
    tests = ROOT / "automation" / "tests"
    manifest = tests / MANIFEST
    if args.check:
        check(ROOT, json.loads(manifest.read_text(encoding="utf-8")))
        return
    packages = [tests / f"tier{tier}" for tier in INPUTS]
    if not args.overwrite and any(path.exists() for path in [*packages, manifest]):
        parser.error("Split outputs already exist; delete generated packages/manifest or pass --overwrite")
    commit, sources = revision_sources(ROOT, args.source_ref)
    for tier, source in sources.items():
        if (tests / INPUTS[tier]).read_text(encoding="utf-8") != source:
            parser.error(f"Restore {INPUTS[tier]} from {args.source_ref} before splitting")
    planned = {tier: plan_tier(source, tier) for tier, source in sources.items()}
    # One external test imports this shared fake. Route it to the original while
    # collecting originals, including when generated packages have been deleted.
    consumer = tests / "test_tier5_settings_guard.py"
    consumer_source = consumer.read_text(encoding="utf-8")
    old = "from tests.test_tier5_regressions import _FakeWinreg"
    new = "from tests.tier5._helpers import _FakeWinreg"
    try:
        consumer.write_text(consumer_source.replace(new, old), encoding="utf-8", newline="\n")
        print("Before split:", flush=True)
        baseline = {"source_commit": commit, "collection": collect(ROOT, originals=True)}
    finally:
        consumer.write_text(consumer_source, encoding="utf-8", newline="\n")
    for package in packages:
        if package.exists():
            if package.is_symlink() or package.resolve().parent != tests.resolve():
                raise ValueError(f"Unsafe generated package path: {package}")
            shutil.rmtree(package)
    for tier, outputs in planned.items():
        package = tests / f"tier{tier}"
        package.mkdir()
        for filename, source in outputs.items():
            (package / filename).write_text(source, encoding="utf-8", newline="\n")
            count = sum(isinstance(n, ast.ClassDef) and n.name.startswith("Test")
                        for n in ast.parse(source).body)
            print(f"tier{tier}/{filename}: {count} test classes, {test_pairs(source).total()} test definitions")
    manifest.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8", newline="\n")
    for filename in INPUTS.values():
        (tests / filename).unlink()
    consumer.write_text(consumer_source.replace(old, new), encoding="utf-8", newline="\n")
    check(ROOT, baseline)


if __name__ == "__main__":
    main()

