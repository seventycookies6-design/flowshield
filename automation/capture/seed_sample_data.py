"""
Seed the lab VM with sample data for the F27 captures.

Everything here is invented for the screenshots: three well-known apps on the
blocklist, a fortnight of sprints, and journal lines a student might write.
It is never anyone's real blocklist, and no licence is involved — the app is
in its free trial.

Written through the settings file's documented unprotected envelope
(Protected=false), which SettingsService.Load already handles, so nothing is
faked in the UI: the app loads this and renders it with the shipped code.
The momentum and streak below are computed with the app's own rules rather
than typed in, so the numbers on screen agree with each other.
"""
import base64, json, os
from datetime import datetime, timedelta, timezone

MINUTES_WEIGHT = lambda m: min(max(m / 25.0, 0.5), 3.0)

def after(score, completed, minutes, shield):
    if completed:
        return round(score + 10 * MINUTES_WEIGHT(minutes), 1)
    return round(max(0.0, score * 0.7 - 5) if shield == 3 else max(0.0, score * 0.85 - 2), 1)

# (days ago, start hour, minutes, shield, completed, journal)
PLAN = [
    (13, 17, 25, 2, True,  "Read two chapters of the biology unit."),
    (12, 18, 45, 2, True,  "Finished the essay outline."),
    (11, 17, 25, 1, True,  "Cleared the maths problem set."),
    (10, 19, 45, 2, True,  "Wrote the introduction properly this time."),
    ( 9, 16, 25, 2, False, "Gave up on the reading, came back later."),
    ( 8, 18, 45, 3, True,  "Whole lab report done in one sitting."),
    ( 7, 17, 25, 2, True,  "Vocabulary revision."),
    ( 6, 20, 60, 3, True,  "Past paper under timed conditions."),
    ( 5, 17, 45, 2, True,  "Rewrote the conclusion."),
    ( 4, 18, 25, 2, True,  "Chemistry equations drilled."),
    ( 3, 19, 45, 2, True,  "Finished the history notes."),
    ( 2, 17, 60, 3, True,  "Full mock exam, no phone."),
    ( 1, 18, 45, 2, True,  "Edited the essay down to the word limit."),
]

now = datetime.now()
sessions, score = [], 0.0
for days_ago, hour, minutes, shield, completed, journal in PLAN:
    start_local = (now - timedelta(days=days_ago)).replace(
        hour=hour, minute=5, second=0, microsecond=0)
    start = start_local.astimezone(timezone.utc)
    actual = minutes if completed else max(6, minutes // 3)
    sessions.append({
        "StartedUtc": start.strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
        "EndedUtc": (start + timedelta(minutes=actual)).strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
        "PlannedMinutes": minutes,
        "Shield": shield,
        "Completed": completed,
        "BlocksEnforced": 2 if completed else 1,
        "AppsClosed": 2 if (completed and shield >= 2) else 0,
        "NudgesSent": 0 if shield >= 2 else 2,
        "MomentumAtStart": score,
        "Intention": "",
        "Journal": journal,
        "Interrupted": False,
    })
    score = after(score, completed, minutes, shield)

# Streak: consecutive days ending yesterday that had a completed sprint.
days_with_sprint = {13 - p[0] for p in PLAN if p[4]}
streak, d = 0, 1
while (13 - d) in {13 - p[0] for p in PLAN if p[4]}:
    streak += 1; d += 1

settings = {
    "BlockedApps": [
        {"Name": "Steam", "ProcessName": "steam",
         "ExtraProcessNames": ["steamwebhelper"], "IconPath": None},
        {"Name": "Discord", "ProcessName": "discord",
         "ExtraProcessNames": ["discordptb"], "IconPath": None},
        {"Name": "Minecraft Launcher", "ProcessName": "minecraftlauncher",
         "ExtraProcessNames": [], "IconPath": None},
    ],
    "IsSleepBlockEnabled": True,
    "SleepBlockStartTime": "22:30:00",
    "SleepBlockEndTime": "06:30:00",
    "HardKillModeEnabled": False,
    "NotificationsEnabled": True,
    "FirstRunCompleted": True,
    "TermsAcceptedVersion": "1.1 (23 September 2026)",
    "TermsAcceptedUtc": (now - timedelta(days=14)).astimezone(timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
    "TrialStartedUtc": (now - timedelta(days=2)).astimezone(timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
    "DefaultSprintMinutes": 45,
    "DefaultShield": 2,
    "MomentumScore": score,
    "CurrentStreak": streak,
    "StreakSettledDayLocal": (now - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00"),
    "Sessions": sessions,
    "ActiveSprint": None,
}

path = os.path.join(os.environ["APPDATA"], "FlowShield", "settings.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
envelope = {
    "Version": 1,
    "Protected": False,
    "Entropy": "FlowShield.Settings.v1",
    "WrittenUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
    "Data": base64.b64encode(json.dumps(settings).encode("utf-8")).decode("ascii"),
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(envelope, f, indent=2)
print(f"seeded {len(sessions)} sessions, momentum {score}, streak {streak}", flush=True)
print(f"-> {path}", flush=True)
