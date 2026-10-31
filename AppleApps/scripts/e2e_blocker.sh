#!/usr/bin/env bash
# Run in the logged-in Mac's SSH session after mac_remote.sh build.
# Every launch uses disposable state. The real Application Support folder is untouched.
set -euo pipefail
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="${1:-$(cd "$HERE/../.." && pwd)/DerivedData/Build/Products/Debug/Basalt.app}"
[[ -d "$APP" ]] || { echo "FAIL: app missing: $APP"; exit 1; }
LOCK=/tmp/basalt-blocker-e2e.lock
mkdir "$LOCK" 2>/dev/null || { echo 'FAIL: another blocker e2e run owns the Mac'; exit 1; }
ROOT="$(mktemp -d /tmp/basalt-e2e-XXXXXX)"
stop() { pkill -9 -x Basalt 2>/dev/null || true; pkill -x Calculator 2>/dev/null || true; pkill -9 -x BasaltE2EResist 2>/dev/null || true; }
cleanup() { stop; rmdir "$LOCK"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; find "$ROOT" -name blocker.log -exec tail -15 {} \;; exit 1; }
wait_log() {
  local file="$1" pattern="$2" limit="${3:-12}"
  for ((i=0; i<limit; i++)); do
    if [[ -f "$file" ]] && grep -q "$pattern" "$file"; then return; fi
    sleep 1
  done
  fail "missing log: $pattern"
}
launch() {
  local dir="$1"; shift
  mkdir -p "$dir"
  open -n "$APP" --args --data-dir "$dir" --skip-onboarding --test-timings "$@"
}
wait_gone() {
  for ((j=0; j<10; j++)); do
    if ! pgrep -x Calculator >/dev/null; then return; fi
    sleep 0.2
  done
  fail 'Calculator survived Firm enforcement'
}
stop
echo "Isolated data: $ROOT"

FIRM="$ROOT/firm"
launch "$FIRM" --start-sprint shield=firm minutes=5 block=com.apple.calculator
wait_log "$FIRM/blocker.log" 'sprint started; shield=Firm'
open -b com.apple.calculator
wait_log "$FIRM/blocker.log" 'asked to quit; shield=Firm'
wait_gone
grep 'asked to quit' "$FIRM/blocker.log" | tail -1
echo 'PASS (a) Firm: graceful quit requested, Calculator gone within 2 s of logged request'
stop

SOFT="$ROOT/soft"
launch "$SOFT" --start-sprint shield=soft minutes=5 block=com.apple.calculator
wait_log "$SOFT/blocker.log" 'sprint started; shield=Soft'
open -b com.apple.calculator
wait_log "$SOFT/blocker.log" 'notice shown'
sleep 4
pgrep -x Calculator >/dev/null || fail 'Soft closed Calculator'
if grep -Eq 'asked to quit|forceTerminate' "$SOFT/blocker.log"; then fail 'Soft attempted termination'; fi
grep 'notice shown' "$SOFT/blocker.log" | tail -1
echo 'PASS (b) Soft: notice logged, Calculator remains running, no termination attempted'
stop

SAFE="$ROOT/protected"
finder_before="$(pgrep -x Finder)"
launch "$SAFE" --start-sprint shield=sealed minutes=5 block=com.apple.finder
wait_log "$SAFE/blocker.log" 'protected; never-close'
sleep 3
[[ "$(pgrep -x Finder)" == "$finder_before" ]] || fail 'Finder process changed'
echo 'PASS (c) Never-close: Finder PID unchanged under Sealed with explicit Finder entry'
stop

RECOVER="$ROOT/recovery"
launch "$RECOVER" --start-sprint shield=sealed minutes=5 block=com.apple.calculator
wait_log "$RECOVER/blocker.log" 'sprint started; shield=Sealed'
open -b com.apple.calculator
wait_log "$RECOVER/blocker.log" 'asked to quit; shield=Sealed'
wait_gone
pkill -9 -x Basalt
python3 - "$RECOVER/settings.json" <<'PY'
import json, sys, os, stat
p = sys.argv[1]
s = json.load(open(p))
assert s['activeSprint']['shield'] == 3
assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
print('Persisted active shield=Sealed; settings mode=0600')
PY
launch "$RECOVER"
wait_log "$RECOVER/blocker.log" 'recovery=resume; shield=Sealed'
open -b com.apple.calculator
for ((i=0; i<12; i++)); do
  count="$(grep -c 'asked to quit; shield=Sealed' "$RECOVER/blocker.log")"
  [[ "$count" -ge 2 ]] && break
  sleep 1
done
[[ "$count" -ge 2 ]] || fail 'recovered sprint did not block again'
wait_gone
grep 'recovery=' "$RECOVER/blocker.log" | tail -1
echo 'PASS (d) Crash recovery: kill -9, same Sealed shield resumed, blocking continued'
stop

BREAK="$ROOT/break"
mkdir -p "$BREAK"
python3 - "$SOFT/settings.json" "$BREAK/settings.json" <<'PY'
import json, sys, datetime, os
s = json.load(open(sys.argv[1]))
now = datetime.datetime.now(datetime.timezone.utc)
iso = lambda d: d.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
s['activeSprint'] = None
s['activeBreak'] = dict(startedUtc=iso(now), endsUtc=iso(now + datetime.timedelta(seconds=12)), minutes=1, sprintsPlanned=0, sprintsDone=0)
with open(sys.argv[2], 'w') as f: json.dump(s, f)
os.chmod(sys.argv[2], 0o600)
PY
launch "$BREAK"
wait_log "$BREAK/blocker.log" 'break resumed'
open -b com.apple.calculator
sleep 3
pgrep -x Calculator >/dev/null || fail 'break closed Calculator'
wait_log "$BREAK/blocker.log" 'break ended' 18
pgrep -x Calculator >/dev/null || fail 'idle after break closed Calculator'
if grep -Eq 'asked to quit|forceTerminate|notice shown' "$BREAK/blocker.log"; then fail 'enforced during a break'; fi
echo 'PASS (e) Recovered break: Calculator allowed during break and after expiry, no enforcement'
stop

SCHEDULE="$ROOT/schedule"
mkdir -p "$SCHEDULE"
python3 - "$SOFT/settings.json" "$SCHEDULE/settings.json" <<'PY'
import json, sys, datetime, os
s = json.load(open(sys.argv[1]))
now = datetime.datetime.now().astimezone()
due = now.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
t = s['templates'][0]
t.update(sprintMinutes=5, shield=2, cycleSprints=0, profileId=s['activeProfileId'])
s['activeSprint'] = None
s['activeBreak'] = None
s['scheduleLastCheckUtc'] = now.astimezone(datetime.timezone.utc).isoformat().replace('+00:00','Z')
s['schedules'] = [dict(id='e2e-schedule', templateId=t['id'], days=[(due.weekday()+1)%7], startMinuteOfDay=due.hour*60+due.minute, askFirst=False, enabled=True)]
with open(sys.argv[2], 'w') as f: json.dump(s,f)
os.chmod(sys.argv[2], 0o600)
PY
launch "$SCHEDULE"
wait_log "$SCHEDULE/blocker.log" 'sprint started; shield=Firm' 75
open -b com.apple.calculator
wait_log "$SCHEDULE/blocker.log" 'asked to quit; shield=Firm'
wait_gone
echo 'PASS (f) Schedule: due template started a Firm sprint and blocking worked'
stop

# A disposable AppKit app refuses ordinary quit, so this exercises the real
# deadline/forceTerminate path, which Calculator normally never reaches.
FIXTURE="$ROOT/Resist.app"
mkdir -p "$FIXTURE/Contents/MacOS"
cat > "$ROOT/Resist.swift" <<'SWIFT'
import AppKit
final class Delegate: NSObject, NSApplicationDelegate {
  func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply { .terminateCancel }
}
let app = NSApplication.shared
let delegate = Delegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
SWIFT
cat > "$FIXTURE/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>org.basalt.e2e.resist</string>
<key>CFBundleExecutable</key><string>BasaltE2EResist</string>
<key>CFBundleName</key><string>Quit-resistant test app</string>
<key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
PLIST
swiftc "$ROOT/Resist.swift" -o "$FIXTURE/Contents/MacOS/BasaltE2EResist"
codesign --force --sign - "$FIXTURE" >/dev/null 2>&1
RESIST="$ROOT/resist"
launch "$RESIST" --start-sprint shield=firm minutes=5 block=org.basalt.e2e.resist
wait_log "$RESIST/blocker.log" 'sprint started; shield=Firm'
open -n "$FIXTURE"
wait_log "$RESIST/blocker.log" 'asked to quit; shield=Firm'
pgrep -x BasaltE2EResist >/dev/null || fail 'quit-resistant fixture did not survive ordinary quit'
wait_log "$RESIST/blocker.log" 'forceTerminate; accepted=true'
sleep 1
if pgrep -x BasaltE2EResist >/dev/null; then fail 'forceTerminate left fixture running'; fi
echo 'PASS (g) Firm deadline: quit-resistant AppKit fixture survived graceful request, then was force-terminated'
echo 'ALL SCENARIOS PASS'
echo "Logs retained in $ROOT"
