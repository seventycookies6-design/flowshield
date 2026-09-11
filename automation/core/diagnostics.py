"""Screenshot capture and structured step logging for the FlowShield suite."""

from __future__ import annotations

import ctypes
import json
import time
import traceback
from ctypes import wintypes
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from colorama import Fore, Style, init as colorama_init

from config import LOG_DIR, REPORT_DIR, SCREENSHOT_DIR

colorama_init(autoreset=True)


# ============================================================ screen capture

PW_RENDERFULLCONTENT = 0x00000002


class ScreenCapture:
    """
    Window capture via PrintWindow with PW_RENDERFULLCONTENT.

    PrintWindow asks the window to redraw itself into a bitmap, so it works on
    windows that are occluded or partially off-screen — unlike a desktop-region
    grab. WPF composites through DirectX, which the flag is specifically needed
    for; without it PrintWindow returns a blank surface for WPF windows.
    """

    @staticmethod
    def capture_window(hwnd: int, output_path: str | Path, title: str = "") -> Path | None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from PIL import Image
        except ImportError:
            return None

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        rect = wintypes.RECT()
        if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            return None

        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return None

        hdc_window = user32.GetWindowDC(hwnd)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
        bitmap = gdi32.CreateCompatibleBitmap(hdc_window, width, height)
        gdi32.SelectObject(hdc_mem, bitmap)

        try:
            ok = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
            if not ok:
                # Fall back to a plain blit of whatever is on screen.
                gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_window, 0, 0, 0x00CC0020)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            header = BITMAPINFOHEADER()
            header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            header.biWidth = width
            header.biHeight = -height          # negative => top-down rows
            header.biPlanes = 1
            header.biBitCount = 32
            header.biCompression = 0

            buffer = ctypes.create_string_buffer(width * height * 4)
            gdi32.GetDIBits(hdc_mem, bitmap, 0, height, buffer, ctypes.byref(header), 0)

            image = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1)
            image.convert("RGB").save(output_path)
            return output_path
        except Exception:
            return None
        finally:
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(hwnd, hdc_window)

    @staticmethod
    def capture_screen(output_path: str | Path) -> Path | None:
        """Whole-desktop grab; used when no window handle is available."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import pyautogui
            pyautogui.screenshot().save(output_path)
            return output_path
        except Exception:
            return None


# ============================================================ step recording

@dataclass
class StepRecord:
    index: int
    name: str
    status: str = "running"          # running | passed | failed | skipped
    started: str = ""
    duration_s: float = 0.0
    detail: str = ""
    error: str = ""
    screenshots: list[str] = field(default_factory=list)
    attempts: int = 1


class DiagnosticLogger:
    """Console + file logging with per-step screenshots and a JSON report."""

    def __init__(self, run_name: str = "e2e"):
        self.run_name = run_name
        self.stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = LOG_DIR / f"{run_name}-{self.stamp}.log"
        self.report_path = REPORT_DIR / f"{run_name}-{self.stamp}.json"
        self.shot_dir = SCREENSHOT_DIR / f"{run_name}-{self.stamp}"
        self.shot_dir.mkdir(parents=True, exist_ok=True)

        self.steps: list[StepRecord] = []
        self._current: StepRecord | None = None
        self._t0 = time.time()

        self._write(f"=== FlowShield {run_name} run {self.stamp} ===")

    # ------------------------------------------------------------- plumbing

    def _write(self, line: str) -> None:
        stamped = f"{datetime.now():%H:%M:%S.%f}"[:-3] + f"  {line}"
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(stamped + "\n")

    def info(self, message: str) -> None:
        print(f"    {Style.DIM}{message}{Style.RESET_ALL}")
        self._write(f"     {message}")

    def warn(self, message: str) -> None:
        print(f"    {Fore.YELLOW}! {message}")
        self._write(f"     WARN {message}")

    def error(self, message: str) -> None:
        print(f"    {Fore.RED}✗ {message}")
        self._write(f"     ERROR {message}")

    def note(self, message: str) -> None:
        """A prominent, non-step message (banners, manual instructions)."""
        print(f"{Fore.CYAN}{message}{Style.RESET_ALL}")
        self._write(message)

    # ---------------------------------------------------------------- steps

    def begin(self, name: str) -> StepRecord:
        record = StepRecord(index=len(self.steps) + 1, name=name,
                            started=datetime.now().isoformat(timespec="seconds"))
        self.steps.append(record)
        self._current = record
        record._t0 = time.time()  # type: ignore[attr-defined]

        print(f"\n{Fore.CYAN}▶ STEP {record.index:02d}  {Style.BRIGHT}{name}")
        self._write(f"--- STEP {record.index:02d} {name}")
        return record

    def passed(self, detail: str = "") -> None:
        self._finish("passed", detail)

    def failed(self, error: str, detail: str = "") -> None:
        self._finish("failed", detail, error)

    def skipped(self, reason: str) -> None:
        self._finish("skipped", reason)

    def _finish(self, status: str, detail: str = "", error: str = "") -> None:
        if self._current is None:
            return
        rec = self._current
        rec.status = status
        rec.detail = detail
        rec.error = error
        rec.duration_s = round(time.time() - getattr(rec, "_t0", time.time()), 2)

        glyph = {"passed": (Fore.GREEN, "✓"), "failed": (Fore.RED, "✗"),
                 "skipped": (Fore.YELLOW, "○")}[status]
        colour, mark = glyph
        tail = f" — {detail or error}" if (detail or error) else ""
        print(f"  {colour}{mark} {status.upper()} ({rec.duration_s}s){tail}")
        self._write(f"    {status.upper()} ({rec.duration_s}s) {detail} {error}".rstrip())
        self._current = None

    def exception(self, exc: BaseException) -> None:
        self._write(traceback.format_exc())
        self.failed(f"{type(exc).__name__}: {exc}")

    # ---------------------------------------------------------- screenshots

    def shot(self, label: str, hwnd: int | None = None) -> Path | None:
        """Capture the app window (or the desktop) and attach it to the step."""
        index = len(self.steps)
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)[:60]
        path = self.shot_dir / f"{index:02d}-{safe}.png"

        result = None
        if hwnd:
            result = ScreenCapture.capture_window(hwnd, path, label)
        if result is None:
            result = ScreenCapture.capture_screen(path)

        if result and self._current is not None:
            self._current.screenshots.append(str(result))
        elif result is None:
            self.warn(f"screenshot '{label}' could not be captured")
        return result

    # -------------------------------------------------------------- reports

    @property
    def counts(self) -> dict:
        out = {"passed": 0, "failed": 0, "skipped": 0, "running": 0}
        for step in self.steps:
            out[step.status] = out.get(step.status, 0) + 1
        return out

    def write_report(self, extra: dict | None = None) -> Path:
        payload = {
            "run": self.run_name,
            "timestamp": self.stamp,
            "duration_s": round(time.time() - self._t0, 2),
            "counts": self.counts,
            "log": str(self.log_path),
            "screenshots_dir": str(self.shot_dir),
            "steps": [
                {k: v for k, v in asdict(step).items() if not k.startswith("_")}
                for step in self.steps
            ],
        }
        if extra:
            payload.update(extra)

        self.report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.report_path

    def summary(self) -> bool:
        counts = self.counts
        total = len(self.steps)
        ok = counts["failed"] == 0

        print(f"\n{Style.BRIGHT}{'─' * 64}")
        print(f"{Style.BRIGHT}  {self.run_name.upper()} SUMMARY")
        print(f"{Style.BRIGHT}{'─' * 64}")
        for step in self.steps:
            colour = {"passed": Fore.GREEN, "failed": Fore.RED,
                      "skipped": Fore.YELLOW, "running": Fore.MAGENTA}[step.status]
            mark = {"passed": "✓", "failed": "✗", "skipped": "○", "running": "…"}[step.status]
            print(f"  {colour}{mark}{Style.RESET_ALL} {step.index:02d}. {step.name[:46]:<46}"
                  f" {colour}{step.status:<8}{Style.RESET_ALL} {step.duration_s:>6.2f}s")
            if step.error:
                print(f"        {Fore.RED}{step.error[:100]}")

        print(f"{Style.BRIGHT}{'─' * 64}")
        verdict = f"{Fore.GREEN}PASS" if ok else f"{Fore.RED}FAIL"
        print(f"  {verdict}{Style.RESET_ALL}  "
              f"{counts['passed']}/{total} passed · {counts['failed']} failed · "
              f"{counts['skipped']} skipped")
        print(f"  report: {self.report_path}")
        print(f"  shots:  {self.shot_dir}")
        print(f"{Style.BRIGHT}{'─' * 64}\n")
        return ok


def retry(logger: DiagnosticLogger, attempts: int = 3, delay: float = 1.5):
    """Decorator: retry a flaky UI action, logging each attempt."""
    def wrapper(fn):
        def inner(*args, **kwargs):
            last = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:          # noqa: BLE001 — deliberate catch-all
                    last = exc
                    if attempt < attempts:
                        logger.warn(f"{fn.__name__} attempt {attempt}/{attempts} failed: {exc}")
                        time.sleep(delay)
            raise last  # type: ignore[misc]
        return inner
    return wrapper
