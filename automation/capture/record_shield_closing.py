"""
Record the shield closing a real blocked app (F27).

Frames are grabbed in this one process at ~10 fps and encoded on the host:
the bench's screenshot verb is a scheduled-task round trip each time, which
is nowhere near fast enough for video.
"""
import sys, time, subprocess, ctypes, ctypes.wintypes as w, traceback
sys.path.insert(0, r"C:\FlowShield-Lab\repos\FlowShield\automation")
from pathlib import Path
from PIL import ImageGrab
from core.settings_guard import preserve_user_settings
from desktop.app_controller import DesktopController

FRAMES = Path(r"C:\FlowShield-Lab\frames")
if FRAMES.exists():
    for f in FRAMES.glob("*.jpg"):
        f.unlink()
FRAMES.mkdir(parents=True, exist_ok=True)

STEAM = r"C:\Program Files (x86)\Steam\steam.exe"
FPS, SECONDS = 10, 12
# 16:9 inside the 1920x1080 desktop, wide enough for both windows side by side.
REGION = (0, 0, 1920, 1080)
SCALE = (1280, 720)

class L:
    def log(self, m): print(m, flush=True)
    def __getattr__(self, n): return lambda *a, **k: None

u = ctypes.windll.user32

def steam_windows():
    found = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
    def cb(hwnd, _):
        if not u.IsWindowVisible(hwnd):
            return True
        n = u.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        r = w.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
        if "steam" in buf.value.lower() and (r.right - r.left) > 400:
            found.append((hwnd, buf.value, (r.left, r.top, r.right, r.bottom)))
        return True
    u.EnumWindows(CB(cb), 0)
    return found

# The owner's real settings are backed up and restored around everything
# below: seeding writes invented sample data straight into settings.json,
# and this script is in the repo for anyone to rerun (CLAUDE.md).
with preserve_user_settings():
    # Fresh sample data every time: a previous recording leaves its sprint saved
    # as active, and a resumed sprint disables the length and shield pickers.
    subprocess.run([r"C:\Program Files\Python312\python.exe",
                    r"C:\FlowShield-Lab\downloads\seed.py"], check=True)

    app = DesktopController(L())
    try:
        app.launch_app(clean_state=False, show_first_run=False, dev_fields=False)
        app.connect_window()
        time.sleep(2.5)
        u.MoveWindow(app.window.handle, 40, 60, 1040, 900, True)
        app.navigate_to_tab("Today")
        app.choose("SprintLength_45")
        time.sleep(0.5)

        subprocess.Popen([STEAM])
        for _ in range(40):
            time.sleep(3)
            if steam_windows():
                break
        wins = steam_windows()
        print("steam windows:", [(x[1], x[2]) for x in wins], flush=True)
        if wins:
            # Move it without resizing: Steam's sign-in window is fixed-size, and
            # forcing dimensions on it just distorts the layout.
            SWP_NOSIZE, SWP_NOZORDER = 0x0001, 0x0004
            u.SetWindowPos(wins[0][0], 0, 1130, 240, 0, 0, SWP_NOSIZE | SWP_NOZORDER)
        time.sleep(2)

        app.focus(force=True)
        time.sleep(1)

        started = False
        total = FPS * SECONDS
        t0 = time.time()
        for i in range(total):
            target = t0 + i / FPS
            delay = target - time.time()
            if delay > 0:
                time.sleep(delay)
            frame = ImageGrab.grab(bbox=REGION).resize(SCALE)
            frame.save(str(FRAMES / f"f{i:04d}.jpg"), quality=82)
            # Two seconds in, start the sprint; the blocker polls every 2 s, so the
            # close lands a few frames later and the whole thing fits the clip.
            if not started and i == FPS * 2:
                app.click("StartSprintButton")
                started = True
                print("sprint started", flush=True)
        print(f"captured {total} frames in {time.time() - t0:.1f}s", flush=True)
    except Exception:
        traceback.print_exc()
