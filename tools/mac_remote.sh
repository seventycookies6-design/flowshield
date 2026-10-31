#!/usr/bin/env bash
# Build and test AppleApps/ on a Mac over SSH from any checkout (Windows Git Bash,
# Linux or another Mac). The Mac needs Xcode, XcodeGen (brew install xcodegen) and
# an SSH host entry; see AppleApps/CLAUDE.md.
#
#   tools/mac_remote.sh sync            copy AppleApps/ to the Mac
#   tools/mac_remote.sh test            sync, then run the BasaltCore tests
#   tools/mac_remote.sh build           sync, generate the project and build the app
#   tools/mac_remote.sh run [args...]   build, then open the app in the Mac's GUI session
#   tools/mac_remote.sh ssh <command>   run a command in the synced folder
#
# BASALT_MAC_HOST picks the SSH host (default: devmac). BASALT_MAC_DIR picks the
# folder on the Mac (default: ~/basalt-remote/<branch>), so two branches or two
# worktrees never build over each other.
set -euo pipefail

HOST="${BASALT_MAC_HOST:-devmac}"
ROOT="$(git rev-parse --show-toplevel)"
BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD | tr '/' '-')"
DIR="${BASALT_MAC_DIR:-basalt-remote/$BRANCH}"
REMOTE_ENV='set -o pipefail; export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH";'

# DIR is interpolated into a remote shell command. Keep it relative to HOME and
# refuse traversal before any removal or sync.
if [[ ! "$DIR" =~ ^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$ ]]; then
  echo "BASALT_MAC_DIR must be a relative path with simple directory names" >&2
  exit 2
fi

remote() {
  ssh -o BatchMode=yes "$HOST" "$REMOTE_ENV cd \"\$HOME/$DIR/AppleApps\" && $*"
}

sync() {
  # tar over ssh rather than rsync: Git Bash on Windows has no rsync. Build output
  # stays on the Mac because it lives outside AppleApps/ (see derived data below).
  ssh -o BatchMode=yes "$HOST" "test ! -L \"\$HOME/$DIR/AppleApps\" && rm -rf \"\$HOME/$DIR/AppleApps\" && mkdir -p \"\$HOME/$DIR\""
  tar -C "$ROOT" --exclude='AppleApps/**/.build' --exclude='AppleApps/**/*.xcodeproj' \
    -czf - AppleApps | ssh -o BatchMode=yes "$HOST" "tar -xzf - -C \"\$HOME/$DIR\""
}

build() {
  sync
  remote "xcodegen generate --quiet && xcodebuild -project Basalt.xcodeproj -scheme Basalt \
    -configuration Debug -derivedDataPath \"\$HOME/$DIR/DerivedData\" build CODE_SIGNING_ALLOWED=NO"
}

case "${1:-}" in
  sync) sync ;;
  test) sync; remote "swift test --package-path BasaltCore" ;;
  build) build ;;
  run)
    shift
    build
    remote "pkill -x Basalt || true; open -n \"\$HOME/$DIR/DerivedData/Build/Products/Debug/Basalt.app\" --args $*"
    ;;
  ssh) shift; remote "$*" ;;
  *) sed -n '2,14p' "$0"; exit 2 ;;
esac
