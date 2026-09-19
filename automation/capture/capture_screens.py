import sys, time, subprocess, traceback
sys.path.insert(0, r"C:\FlowShield-Lab\repos\FlowShield\automation")
from pathlib import Path
from desktop.app_controller import DesktopController

OUT = Path(r"C:\FlowShield-Lab\shots")
OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*.png"):
    old.unlink()

class L:
    def log(self, m): print(m, flush=True)
    def __getattr__(self, n): return lambda *a, **k: None

def grab(app, name):
    time.sleep(1.2)
    img = app.window.capture_as_image()
    # Trim the invisible resize border, which otherwise catches a sliver of
    # desktop wallpaper down the sides and along the bottom.
    w, h = img.size
    img.crop((8, 0, w - 8, h - 8)).save(str(OUT / f"{name}.png"))
    print(f"captured {name}", flush=True)

# Fresh sample data: the earlier run left a 45-minute sprint active.
subprocess.run([r"C:\Program Files\Python312\python.exe",
                r"C:\FlowShield-Lab\downloads\seed.py"], check=True)

app = DesktopController(L())
try:
    app.launch_app(clean_state=False, show_first_run=False, dev_fields=False)
    app.connect_window()
    time.sleep(2.5)
    import ctypes
    ctypes.windll.user32.MoveWindow(app.window.handle, 40, 30, 1280, 880, True)
    time.sleep(1.5)
    app.focus(force=True)

    app.navigate_to_tab("Blocked Apps")
    grab(app, "blocked-apps")
    app.navigate_to_tab("Sleep Blocking")
    grab(app, "sleep-blocking")

    app.navigate_to_tab("Today")
    time.sleep(0.8)
    app.set_text("IntentionInput", "Finish the essay conclusion")
    time.sleep(0.4)
    # choose(), not click(): these are RadioButtons, which expose
    # SelectionItem rather than Invoke, and click()'s fallback can miss
    # silently — leaving a 45-minute sprint and a very long wait.
    app.choose("SprintLength_15")
    time.sleep(0.4)
    assert app.is_selected("SprintLength_15"), "the 15-minute length did not take"
    app.start_sprint()
    time.sleep(4)
    grab(app, "sprint-running")

    # A real fifteen-minute sprint, because the summary card only says
    # "Sprint complete" when one actually finished.
    print("waiting out the sprint", flush=True)
    deadline = time.time() + 16.5 * 60
    while time.time() < deadline:
        time.sleep(15)
        if app.exists("SummaryStreakText", timeout=1):
            break
    time.sleep(3)
    grab(app, "sprint-complete")

    try:
        app.set_text("JournalInput", "Conclusion written and trimmed to the word limit.")
        time.sleep(0.5)
        grab(app, "journal-prompt")
        app.click("SaveJournalButton")
        time.sleep(1.5)
    except Exception as exc:
        print(f"journal step: {exc}", flush=True)

    app.navigate_to_tab("Today")
    grab(app, "today")
    print("DONE", flush=True)
except Exception:
    traceback.print_exc()
