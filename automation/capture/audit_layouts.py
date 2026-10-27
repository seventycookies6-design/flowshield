"""Capture a review sheet of Basalt's main layouts across window sizes."""

from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "automation"))

# Keep screen coordinates physical so work-area bounds, SetWindowPos sizes,
# and GetWindowRect measurements all use the same units.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except (AttributeError, OSError):
    pass

from config import APP_EXE, PROJECT_ROOT, SETTINGS_PATH
from core.settings_guard import preserve_user_settings
from desktop.app_controller import DesktopController


SIZES = {
    "small-laptop-150": (910, 500),
    "laptop-125": (1092, 614),
    "half-1080p": (960, 1040),
    "1080p-125": (1536, 824),
    "1080p": (1920, 1040),
    "1440p-125": (2048, 1112),
    "ultrawide-125": (2752, 1112),
    "4k-150": (2560, 1380),
}

SECTIONS = (
    ("settings-license", "SettingsNav_Licence"),
    ("settings-focus", "SettingsNav_Focus"),
    ("settings-app", "SettingsNav_App"),
    ("settings-notifications", "SettingsNav_Notifications"),
    ("settings-data", "SettingsNav_Data"),
    ("settings-about", "SettingsNav_About"),
)

PAGES = (
    "today-rest", "history", "blocked-apps", "schedule", "sleep-blocking",
    "settings-top", *(page for page, _ in SECTIONS), "today-sprint", "lock-screen",
    "first-run-welcome",
)

TAB_PAGES = {
    "history": "History",
    "blocked-apps": "Blocked Apps",
    "schedule": "Schedule",
    "sleep-blocking": "Schedule",
    "settings-top": "Settings",
}

SPI_GETWORKAREA = 0x0030
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


class RECT(ctypes.Structure):
    _fields_ = [(name, wintypes.LONG) for name in ("left", "top", "right", "bottom")]


class Logger:
    def info(self, message):
        print(message, flush=True)

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", help="comma-separated size labels")
    parser.add_argument("--pages", help="comma-separated page labels")
    parser.add_argument("--theme", choices=("dark", "light", "both"), default="both")
    parser.add_argument("--out", type=Path, help="output directory")
    parser.add_argument("--offscreen", action="store_true",
                        help="render every requested size with the in-process WPF probe")
    return parser.parse_args(argv)


def selected(values, requested, option):
    if not requested:
        return list(values)
    names = [part.strip() for part in requested.split(",") if part.strip()]
    unknown = sorted(set(names) - set(values))
    if unknown:
        raise SystemExit(f"unknown {option}: {', '.join(unknown)}; choose from {', '.join(values)}")
    return names


def app_window_dpi(hwnd):
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
        return dpi if dpi else 96
    except (AttributeError, OSError):
        return 96


def work_area():
    rect = RECT()
    if not ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return rect


def work_area_dips():
    """Return the primary monitor's work area in DIPs for the auto selector."""
    area = work_area()
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        dpi = dpi or 96
    except (AttributeError, OSError):
        dpi = 96
    return ((area.right - area.left) * 96 / dpi,
            (area.bottom - area.top) * 96 / dpi)


def size_window(app, requested_dip):
    """Resize in physical pixels for the window DPI and return its actual size."""
    user32 = ctypes.windll.user32
    hwnd = app.window.handle
    dpi = app_window_dpi(hwnd)
    scale = dpi / 96.0
    area = work_area()
    requested_px = (round(requested_dip[0] * scale), round(requested_dip[1] * scale))
    width_px = min(requested_px[0], area.right - area.left)
    height_px = min(requested_px[1], area.bottom - area.top)
    user32.SetWindowPos.argtypes = (
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    )
    user32.SetWindowPos.restype = wintypes.BOOL
    if not user32.SetWindowPos(
        hwnd, None, area.left, area.top, width_px, height_px,
        SWP_NOZORDER | SWP_NOACTIVATE,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(0.6)
    actual = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(actual)):
        raise ctypes.WinError(ctypes.get_last_error())
    actual_px = (actual.right - actual.left, actual.bottom - actual.top)
    actual_dip = (round(actual_px[0] / scale), round(actual_px[1] / scale))
    return dpi, actual_px, actual_dip


def seed_sample_data(theme, *, first_run_completed=True):
    """Reuse the existing capture seeder, then set audit-only trial/theme state."""
    seed_script = PROJECT_ROOT / "automation" / "capture" / "seed_sample_data.py"
    subprocess.run([sys.executable, str(seed_script)], cwd=PROJECT_ROOT, check=True)
    with SETTINGS_PATH.open("r", encoding="utf-8") as stream:
        envelope = json.load(stream)
    settings = json.loads(base64.b64decode(envelope["Data"]).decode("utf-8"))
    settings["Theme"] = {"dark": 1, "light": 2}[theme]
    settings["FirstRunCompleted"] = first_run_completed
    if not first_run_completed:
        # FirstRunPolicy deliberately suppresses the welcome for anyone with
        # existing sessions or a blocklist, so this launch represents a new user.
        settings["BlockedApps"] = []
        settings["Sessions"] = []
        settings["MomentumScore"] = 0
        settings["CurrentStreak"] = 0
    settings["TrialStartedUtc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    envelope["Data"] = base64.b64encode(json.dumps(settings).encode("utf-8")).decode("ascii")
    envelope["WrittenUtc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    with SETTINGS_PATH.open("w", encoding="utf-8") as stream:
        json.dump(envelope, stream, indent=2)

    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Software\FlowShield\Trial") as key:
        winreg.SetValueEx(key, "StartedUtc", 0, winreg.REG_SZ, settings["TrialStartedUtc"])


def capture(app, out_dir, size_label, theme, page, actual_px, actual_dip):
    image = app.window.capture_as_image()
    width, height = image.size
    if width > 16 and height > 8:
        image = image.crop((8, 0, width - 8, height - 8))
    name = f"{size_label}_{actual_dip[0]}x{actual_dip[1]}dip_{theme}_{page}.png"
    image.save(out_dir / name)
    return {
        "file": name,
        "size": size_label,
        "theme": theme,
        "page": page,
        "actual_dip": f"{actual_dip[0]} × {actual_dip[1]} DIP",
        "physical": f"{actual_px[0]} × {actual_px[1]} px",
        "offscreen": False,
    }


def attempt_capture(app, output, size_label, theme, page, metrics, records, skipped, action):
    try:
        action()
        time.sleep(0.65)
        records.append(capture(app, output, size_label, theme, page, *metrics[1:]))
        print(f"captured {size_label} {theme} {page}", flush=True)
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        skipped.append((size_label, theme, page, reason))
        print(f"skipped {size_label} {theme} {page}: {reason}", flush=True)


def new_app(*, first_run=False, expire_trial=False):
    app = DesktopController(Logger())
    extra_args = ["--short-sprints"]
    if first_run:
        # Accept the terms gate while leaving FirstRunPolicy enabled.
        extra_args.append("--accept-terms")
    if expire_trial:
        extra_args.append("--expire-trial")
    app.launch_app(
        clean_state=False,
        extra_args=extra_args,
        show_first_run=first_run,
        dev_fields=False,
    )
    app.connect_window()
    app.focus(force=True)
    return app


def close_app(app):
    if app is not None:
        app.close_app(force=True)


LAYOUT_PROBE_DIR = REPO_ROOT / "automation" / "probe" / "LayoutProbe"
LAYOUT_PROBE_EXE = LAYOUT_PROBE_DIR / "bin" / "Release" / "net8.0-windows" / "LayoutProbe.exe"
OFFSCREEN_ONLY_PAGES = {"lock-screen", "first-run-welcome"}


def ensure_layout_probe():
    """Build the in-process renderer once before offscreen captures in this run."""
    command = ["dotnet", "build", str(LAYOUT_PROBE_DIR / "LayoutProbe.csproj"), "-c", "Release"]
    for attempt in range(2):
        result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True)
        if result.returncode == 0 and LAYOUT_PROBE_EXE.exists():
            print(result.stdout, end="", flush=True)
            return LAYOUT_PROBE_EXE

        diagnostic = (result.stdout or "") + "\n" + (result.stderr or "")
        lowered = diagnostic.lower()
        lock_error = ("being used by another process" in lowered
                      or "file is locked" in lowered
                      or "file-in-use" in lowered
                      or ("obj" in lowered and ("locked" in lowered or "in use" in lowered)))
        if attempt == 0 and lock_error:
            print("LayoutProbe build hit a file lock; retrying in 30 seconds.", flush=True)
            time.sleep(30)
            continue
        raise RuntimeError(f"LayoutProbe build failed:\n{diagnostic[-6000:]}")

    raise RuntimeError("LayoutProbe build did not produce its executable")


def append_probe_records(stdout, size_label, theme, records):
    found = 0
    for line in (stdout or "").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            print(line, flush=True)
            continue
        if not isinstance(item, dict) or "page" not in item or "actual" not in item:
            print(line, flush=True)
            continue

        actual = item["actual"]
        pixels = item.get("pixel_size", {})
        path = Path(item["path"])
        records.append({
            "file": path.name,
            "size": size_label,
            "theme": theme,
            "page": item["page"],
            "requested_dip": (f"{item['requested']['width']:g} × "
                              f"{item['requested']['height']:g} DIP"),
            "actual_dip": f"{actual['width']:g} × {actual['height']:g} DIP",
            "physical": f"{pixels.get('width', 0)} × {pixels.get('height', 0)} px",
            "offscreen": True,
        })
        print(line, flush=True)
        found += 1
    return found


def run_offscreen_probe(exe, output, size_label, theme, pages, *, expire_trial=False,
                        first_run=False):
    if not pages:
        return 0

    width, height = SIZES[size_label]
    command = [
        str(exe), "--size", f"{width}x{height}", "--label", size_label,
        "--theme", theme, "--out", str(output), "--pages", ",".join(pages),
        "--accept-terms",
    ]
    if not first_run:
        command.append("--skip-first-run")
    if expire_trial:
        command.append("--expire-trial")

    # The app's own mutex protects settings and blocker ownership. End a stale
    # dev instance first, as the on-screen controller does before launch.
    DesktopController.kill_stray_instances()
    result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=240)
    if result.returncode != 0:
        diagnostic = (result.stdout or "") + "\n" + (result.stderr or "")
        raise RuntimeError("LayoutProbe failed:\n" + diagnostic[-6000:])
    return result.stdout


def capture_offscreen_size(exe, output, size_label, theme, pages, records, skipped):
    regular_pages = [page for page in pages
                     if page not in OFFSCREEN_ONLY_PAGES and page != "today-sprint"]
    if "today-sprint" in pages:
        skipped.append((size_label, theme, "today-sprint",
                        "offscreen mode omits the interactive sprint-start state"))
        print(f"skipped {size_label} {theme} today-sprint: interactive sprint-start state", flush=True)
    if regular_pages:
        try:
            seed_sample_data(theme)
            stdout = run_offscreen_probe(exe, output, size_label, theme, regular_pages)
            append_probe_records(stdout, size_label, theme, records)
        except Exception as exc:
            skipped.append((size_label, theme, "all-pages", f"offscreen probe failed: {exc}"))
            print(f"skipped {size_label} {theme}: offscreen probe failed: {exc}", flush=True)

    if "lock-screen" in pages:
        try:
            seed_sample_data(theme)
            stdout = run_offscreen_probe(exe, output, size_label, theme, ["lock-screen"],
                                         expire_trial=True)
            append_probe_records(stdout, size_label, theme, records)
        except Exception as exc:
            skipped.append((size_label, theme, "lock-screen", f"offscreen probe failed: {exc}"))
            print(f"skipped {size_label} {theme} lock-screen: {exc}", flush=True)

    if "first-run-welcome" in pages:
        try:
            seed_sample_data(theme, first_run_completed=False)
            stdout = run_offscreen_probe(exe, output, size_label, theme, ["first-run-welcome"],
                                         first_run=True)
            append_probe_records(stdout, size_label, theme, records)
        except Exception as exc:
            skipped.append((size_label, theme, "first-run-welcome", f"offscreen probe failed: {exc}"))
            print(f"skipped {size_label} {theme} first-run-welcome: {exc}", flush=True)


def capture_regular_pages(app, size_label, theme, pages, metrics, output, records, skipped):
    if "today-rest" in pages:
        attempt_capture(app, output, size_label, theme, "today-rest", metrics, records, skipped,
                        lambda: app.navigate_to_tab("Today"))
    for page, tab in TAB_PAGES.items():
        if page not in pages:
            continue

        def navigate(tab=tab, page=page):
            title = app.navigate_to_tab(tab)
            if page == "settings-top" and title.lower() != "settings":
                raise RuntimeError(f"expected Settings, got {title}")
            if page == "sleep-blocking":
                control = app.element("SleepBlockToggle", timeout=8)
                app._scroll_into_view(control, "SleepBlockToggle")

        attempt_capture(app, output, size_label, theme, page, metrics, records, skipped, navigate)
    for page, rail_id in SECTIONS:
        if page not in pages:
            continue

        def select_section(rail_id=rail_id):
            app.navigate_to_tab("Settings")
            app.click(rail_id, control_type="RadioButton")
            if not app.is_on_screen("SettingsGroup_" + {
                "SettingsNav_Licence": "Licence", "SettingsNav_Focus": "Focus",
                "SettingsNav_App": "App", "SettingsNav_Notifications": "Notifications",
                "SettingsNav_Data": "Data", "SettingsNav_About": "About",
            }[rail_id]):
                raise RuntimeError(f"section {rail_id} did not scroll into view")

        attempt_capture(app, output, size_label, theme, page, metrics, records, skipped, select_section)

    if "today-sprint" in pages:
        def running_sprint():
            app.navigate_to_tab("Today")
            app.set_text("IntentionInput", "Finish the essay conclusion")
            app.choose("SprintLength_15")
            # Soft only notes and nudges: this runs on a real desktop, and the
            # sample blocklist names apps (Steam, Discord) that may be open on
            # it. Firm would close them (#406's first audit run nearly did).
            app.choose("Shield_Soft")
            if not app.is_selected("Shield_Soft"):
                raise RuntimeError("the Soft shield did not take; not starting a sprint")
            app.start_sprint()
            app.element("StopSprintButton", timeout=8)

        attempt_capture(app, output, size_label, theme, "today-sprint", metrics, records, skipped,
                        running_sprint)
        try:
            if app.exists("StopSprintButton", timeout=0.5):
                app.cancel_sprint()
        except Exception as exc:
            print(f"could not cancel preview sprint: {exc}", flush=True)


def capture_special(app, page, size_label, theme, metrics, output, records, skipped):
    expected = {"lock-screen": "TrialEndedText", "first-run-welcome": "FirstRunStepText"}[page]

    def visible_state():
        app.element(expected, timeout=12)

    attempt_capture(app, output, size_label, theme, page, metrics, records, skipped, visible_state)


def build_index(output, records, skipped):
    groups = {}
    for record in records:
        groups.setdefault(record["page"], []).append(record)
    chunks = ["""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Basalt layout audit</title>
<style>body{font:16px system-ui,sans-serif;margin:24px;background:#f3f4f6;color:#17202a}h1{margin-bottom:8px}h2{margin-top:36px;border-bottom:1px solid #aab2bd;padding-bottom:6px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:18px}figure{margin:0;padding:12px;background:white;border:1px solid #d5d8dc;border-radius:8px}img{display:block;width:100%;max-width:100%;height:auto}figcaption{font-size:14px;line-height:1.5;margin-top:8px;overflow-wrap:anywhere}</style></head><body>
<h1>Basalt layout audit</h1><p>Captured pages are grouped below. Labels include actual window DIP and physical pixel dimensions.</p>"""]
    for page, items in groups.items():
        chunks.append(f"<section><h2>{page}</h2><div class=\"grid\">")
        for item in items:
            chunks.append(
                f'<figure><img loading="lazy" src="{item["file"]}" alt="{page} at {item["size"]}">'
                f'<figcaption><strong>{item["size"]}</strong> · {item["theme"]}<br>'
                f'{item.get("requested_dip", item["actual_dip"])} requested · '
                f'{item["actual_dip"]} actual · {item["physical"]}'
                f'{" · offscreen" if item.get("offscreen") else ""}</figcaption></figure>'
            )
        chunks.append("</div></section>")
    if skipped:
        chunks.append("<section><h2>Skipped</h2><ul>")
        for size_label, theme, page, reason in skipped:
            chunks.append(f"<li>{size_label} · {theme} · {page}: {reason}</li>")
        chunks.append("</ul></section>")
    chunks.append("</body></html>")
    (output / "index.html").write_text("\n".join(chunks), encoding="utf-8")


def run(args):
    sizes = selected(SIZES, args.sizes, "size labels")
    pages = selected(PAGES, args.pages, "page labels")
    themes = ("dark", "light") if args.theme == "both" else (args.theme,)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.out or PROJECT_ROOT / "reports" / "ui-audit" / stamp
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    records, skipped, launch_failed, successful_launches = [], [], False, 0

    if args.offscreen:
        offscreen_sizes = set(sizes)
    else:
        area_width, area_height = work_area_dips()
        offscreen_sizes = {
            size_label for size_label in sizes
            if (SIZES[size_label][0] > area_width or SIZES[size_label][1] > area_height)
        }
    probe_exe = ensure_layout_probe() if offscreen_sizes else None

    # All app launches and seeded writes stay inside the shared user-state guard.
    with preserve_user_settings():
        for theme in themes:
            for size_label in sizes:
                if size_label in offscreen_sizes:
                    before = len(records)
                    capture_offscreen_size(probe_exe, output, size_label, theme, pages, records, skipped)
                    successful_launches += len(records) - before
                    continue

                metrics = None
                app = None
                try:
                    seed_sample_data(theme)
                    app = new_app()
                    successful_launches += 1
                    metrics = size_window(app, SIZES[size_label])
                    print(f"{size_label}: {metrics[2][0]} × {metrics[2][1]} DIP; "
                          f"{metrics[1][0]} × {metrics[1][1]} px at {metrics[0]} DPI", flush=True)
                except Exception as exc:
                    close_app(app)
                    if not APP_EXE.exists():
                        raise RuntimeError(f"app could not launch: {exc}") from exc
                    skipped.append((size_label, theme, "all-pages", f"launch or connect failed: {exc}"))
                    print(f"skipped {size_label} {theme}: launch or connect failed: {exc}", flush=True)
                    launch_failed = True
                    continue

                try:
                    capture_regular_pages(app, size_label, theme, pages, metrics, output,
                                          records, skipped)
                finally:
                    close_app(app)

                for special in ("lock-screen", "first-run-welcome"):
                    if special not in pages:
                        continue
                    special_app = None
                    try:
                        seed_sample_data(theme, first_run_completed=(special != "first-run-welcome"))
                        special_app = new_app(
                            first_run=(special == "first-run-welcome"),
                            expire_trial=(special == "lock-screen"),
                        )
                        successful_launches += 1
                        metrics = size_window(special_app, SIZES[size_label])
                        capture_special(special_app, special, size_label, theme, metrics,
                                        output, records, skipped)
                    except Exception as exc:
                        skipped.append((size_label, theme, special, f"could not launch state: {exc}"))
                        print(f"skipped {size_label} {theme} {special}: {exc}", flush=True)
                    finally:
                        close_app(special_app)

    build_index(output, records, skipped)
    print(f"Output: {output}", flush=True)
    print(f"Captured {len(records)} images; skipped {len(skipped)} states.", flush=True)
    return 1 if launch_failed and successful_launches == 0 else 0


def main(argv=None):
    args = parse_args(argv)
    try:
        return run(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
