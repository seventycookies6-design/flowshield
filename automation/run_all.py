"""
Run everything and regenerate FINAL_REPORT.md.

    python automation/run_all.py                 # full suite
    python automation/run_all.py --fast           # skip the slow UI tiers
    python automation/run_all.py --headless       # headless checkout browser

Exit code is non-zero if the E2E run or any test fails.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from colorama import Fore, Style, init as colorama_init

from config import AUTOMATION_DIR, PROJECT_ROOT, REPORT_DIR, stripe_configured, stripe_missing

colorama_init(autoreset=True)


def banner(text: str) -> None:
    print(f"\n{Style.BRIGHT}{'═' * 70}")
    print(f"{Style.BRIGHT}  {text}")
    print(f"{Style.BRIGHT}{'═' * 70}\n")


def run(args: list[str], cwd: Path) -> int:
    print(f"{Style.DIM}$ {' '.join(args)}{Style.RESET_ALL}\n")
    return subprocess.run(args, cwd=str(cwd)).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the whole FlowShield suite")
    parser.add_argument("--fast", action="store_true",
                        help="skip tiers 3 and 4 (the slow UI-driving ones)")
    parser.add_argument("--headless", action="store_true",
                        help="run the Stripe checkout browser headless")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    started = time.time()
    results: dict[str, int] = {}

    if not stripe_configured():
        print(f"{Fore.YELLOW}Stripe is not configured — missing: "
              f"{', '.join(stripe_missing())}")
        print(f"{Fore.YELLOW}Payment steps will be skipped, not failed. "
              f"See STRIPE_SETUP.md.")

    banner("1/3  End-to-end run")
    e2e_args = [sys.executable, "e2e_runner.py"]
    if args.headless:
        e2e_args.append("--headless")
    if args.skip_build:
        e2e_args.append("--skip-build")
    results["e2e"] = run(e2e_args, AUTOMATION_DIR)

    banner("2/3  pytest")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    pytest_args = [
        sys.executable, "-m", "pytest", "tests",
        "-v", "--tb=short",
        "--json-report",
        f"--json-report-file={REPORT_DIR / 'pytest_report.json'}",
    ]
    if args.fast:
        pytest_args += ["-m", "not ui"]
    results["pytest"] = run(pytest_args, AUTOMATION_DIR)

    banner("3/3  Report")
    results["report"] = run([sys.executable, "make_report.py"], AUTOMATION_DIR)

    banner("Summary")
    for name, code in results.items():
        mark = f"{Fore.GREEN}✓ ok" if code == 0 else f"{Fore.RED}✗ exit {code}"
        print(f"  {name:<8} {mark}")

    print(f"\n  elapsed: {time.time() - started:.0f}s")
    print(f"  report:  {PROJECT_ROOT / 'FINAL_REPORT.md'}\n")

    # The report generator's exit code is not a test outcome.
    return 0 if results["e2e"] == 0 and results["pytest"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
