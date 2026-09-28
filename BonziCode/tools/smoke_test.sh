#!/bin/bash
# smoke_test.sh: launch the .app that was just built and prove it survives.
#
#   bash tools/smoke_test.sh [seconds]
#
# Every other macOS check in this repo asks whether a file is the right shape.
# That is not the same question as whether the program runs, and the failure it
# misses is the expensive one: a bundle that passes lipo, codesign and the
# Frameworks/frames checks and still dies on first launch, because PyInstaller
# did not bundle something or macOS refused to load it.
#
# It is launched through `open` so it runs as a real GUI app on the runner's
# window server, the same way a user's Launchpad or Finder double-click does.
# The default ten seconds gets past interpreter start, PyInstaller unpacking,
# Tk init, the first canvas frame and the 200ms animation tick.
#
# Note the log is only ever written by log_error(), so a healthy launch leaves
# no log at all. Absence of a log is therefore success, not failure, and the
# assertions here are: the process is still alive, the LaunchAgent plist proves
# module-level code reached main(), and nothing in the log looks like a crash.
# Liveness alone proves nothing - the app refuses to close, and PyInstaller is
# built with disable_windowed_traceback=False, so a crash can raise a traceback
# dialog and sit there looking perfectly healthy.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WAIT="${1:-10}"
# Absolute, because pgrep matches argv[0] and the process is launched with the
# full path, not the relative one used from this directory.
BUNDLE="$(cd dist && pwd)/Bonzi Buddy.app"
BIN="${BUNDLE}/Contents/MacOS/Bonzi Buddy"
LOG_DIR="${HOME}/Library/Logs/BonziBuddy"
LOG="${LOG_DIR}/bonzi.log"
PLIST="${HOME}/Library/LaunchAgents/com.bonzibuddy.app.plist"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
bad()  { printf '\033[31merror: %s\033[0m\n' "$1" >&2; exit 1; }
note() { printf '        %s\n' "$1"; }

[ -d "$BUNDLE" ] || bad "no bundle at ${BUNDLE}"
[ -x "$BIN" ]    || bad "no executable at ${BIN}"

# Cleared first so this run's lines cannot be confused with an earlier one, and
# so a stale log cannot make a broken build look clean. The plist goes too: it
# is rewritten on every start, and a leftover from the packaging step would
# otherwise pass for proof that the app ran.
rm -rf "$LOG_DIR" "$PLIST"

say "launching (waiting ${WAIT}s)"
open "$BUNDLE"
sleep 2

PID=$(pgrep -f "$BIN" | head -1)
[ -n "$PID" ] || bad "the app never started, no process matching ${BIN}"
echo "pid     ${PID}"

sleep "$WAIT"

if ! kill -0 "$PID" 2>/dev/null; then
  bad "the app exited within ${WAIT}s of launching"
fi
echo "alive   after ${WAIT}s"

# add_to_startup() runs at module level just before mainloop(), so the plist
# existing means the frozen app got all the way through its own startup, which
# is a far stronger signal than the process still being around.
say "startup evidence"
if [ -f "$PLIST" ]; then
  echo "ok      LaunchAgent plist written, startup reached main()"
else
  bad "no ${PLIST}, the app did not get as far as add_to_startup()"
fi

if [ -f "$LOG" ]; then
  echo "log     ${LOG}"
  tail -40 "$LOG" | sed 's/^/        /'

  # A crash in a windowed build is logged rather than raised, so a dead app can
  # still leave a full-looking log. These are the messages that mean the bundle
  # is broken rather than merely unbuilt.
  if grep -q 'Traceback (most recent call last)' "$LOG"; then
    bad "the app logged a traceback, it is crashing on launch"
  fi
  if grep -qE 'frame load failed|motion load failed' "$LOG"; then
    bad "the app could not load its frames, the animations are missing"
  fi
  if grep -q 'pyobjc is not installed' "$LOG"; then
    bad "pyobjc did not make it into the bundle, the keylog cannot work"
  fi
  if grep -q 'macos launch agent failed' "$LOG"; then
    bad "the app could not write its LaunchAgent plist"
  fi
  if grep -q 'update check failed' "$LOG"; then
    note "warn: the update check failed. Not fatal, but it means this build"
    note "      could not reach its own manifest, so self-update is blind."
  fi
else
  # log_error writes nothing on a clean run, so this is the expected case.
  echo "ok      no log written, which is what a clean startup looks like"
fi

say "quitting"
# SIGTERM, not a scripted quit, so the shutdown path runs the way a user's Quit
# would. The launch agent is unloaded as well, or it outlives the job and the
# next run inherits an already-registered Bonzi.
kill "$PID" 2>/dev/null
for _ in $(seq 1 10); do
  kill -0 "$PID" 2>/dev/null || break
  sleep 1
done
kill -9 "$PID" 2>/dev/null
pkill -f "$BIN" 2>/dev/null
if [ -f "$PLIST" ]; then
  launchctl unload -w "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
fi
echo "stopped"

printf '\n\033[32msmoke test passed\033[0m\n\n'
