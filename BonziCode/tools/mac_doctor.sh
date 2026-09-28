#!/bin/bash
# mac_doctor.sh: work out which parts of Bonzi actually work on this Mac.
#
# Six things he does are gated behind macOS privacy permissions, and a refused
# permission looks exactly like a broken feature. This checks each one and says
# which, so a bug report is a line of output instead of a guess.
#
#   bash tools/mac_doctor.sh
#
# Nothing here is modified. It only reads permissions and runs commands that
# would run anyway.

PASS=0
FAIL=0
SKIP=0

ok()   { printf '  \033[32mok\033[0m    %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }
warn() { printf '  \033[33mwarn\033[0m  %s\n' "$1"; SKIP=$((SKIP+1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }
note() { printf '        %s\n' "$1"; }

printf '\033[1mBonzi macOS doctor\033[0m\n'

# ---------------------------------------------------------------- machine ---
head_ "Machine"
SW_VERS=$(sw_vers -productVersion 2>/dev/null)
ARCH=$(uname -m)
ok "macOS ${SW_VERS} on ${ARCH}"
if [ "$ARCH" = "x86_64" ]; then
  if sysctl -n sysctl.proc_translated 2>/dev/null | grep -q 1; then
    note "this is Apple Silicon running the Intel build under Rosetta 2"
    note "that is the expected default, not a problem"
  fi
fi
# A .app built for the wrong slice launches and then dies on a missing library.
if [ -d "/Applications/Bonzi Buddy.app" ]; then
  BIN="/Applications/Bonzi Buddy.app/Contents/MacOS/Bonzi Buddy"
  if [ -x "$BIN" ]; then
    ok "installed bundle found"
    note "slice: $(lipo -archs "$BIN" 2>/dev/null || echo unknown)"
  else
    warn "bundle present but the executable is missing"
  fi
else
  warn "no /Applications/Bonzi Buddy.app yet"
fi

# ----------------------------------------------------------------- python ---
head_ "Python"
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
      PY="$candidate"
      break
    fi
  fi
done
if [ -n "$PY" ]; then
  ok "$($PY --version 2>&1) at $(command -v "$PY")"
else
  bad "no Python 3.10+ found, needed to build"
  note "install it, or just download a build instead of building one"
  PY=python3
fi

# ------------------------------------------------------------ requirements ---
head_ "Dependencies"
if [ -n "$PY" ]; then
  if "$PY" -c 'import PyInstaller, PIL' >/dev/null 2>&1; then
    ok "PyInstaller and Pillow importable"
  else
    warn "PyInstaller/Pillow missing, pip install -r requirements.txt"
  fi
  if "$PY" -c 'import AppKit' >/dev/null 2>&1; then
    ok "AppKit imports, the keylog has what it needs"
  else
    bad "AppKit will not import, so the keylog cannot work"
    note "pyobjc-framework-Cocoa is in requirements.txt but not installed"
    note "fix: pip3 install -r requirements.txt"
  fi
fi

# ------------------------------------------------- Accessibility / keylog ---
head_ "Accessibility (visible keylog)"
if [ -n "$PY" ] && "$PY" -c 'import AppKit' >/dev/null 2>&1; then
  OUT=$("$PY" - <<'PYEOF' 2>&1
import AppKit
monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
    AppKit.NSEventMaskFlagKeyDown, lambda e: None)
print("granted" if monitor is not None else "denied")
PYEOF
)
  if [ "$OUT" = "granted" ]; then
    ok "global key monitor accepted"
  else
    bad "global key monitor refused (denied)"
    note "System Settings > Privacy & Security > Accessibility"
    note "add Bonzi Buddy with the + button, then relaunch him"
    note "an ad-hoc build is replaced by every rebuild, re-add after updates"
  fi
else
  warn "skipped, AppKit unavailable"
fi

# ------------------------------------------------------ Screen Recording ---
head_ "Screen Recording (seeing what you are working in)"
TMPPNG=$(mktemp -t bonzi_screen).png
if screencapture -x "$TMPPNG" >/dev/null 2>&1 && [ -s "$TMPPNG" ]; then
  ok "screen capture works, foreground detection should work"
else
  bad "screen capture produced nothing"
  note "System Settings > Privacy & Security > Screen Recording"
  note "add Bonzi Buddy, then relaunch him, macOS needs a restart to apply"
fi
rm -f "$TMPPNG"

# ------------------------------------------------------------- Automation ---
head_ "Automation (frontmost app and clipboard)"
FRONT=$(osascript -e 'tell application "System Events" to name of first application process whose frontmost is true' 2>&1)
if [ -n "$FRONT" ] && ! echo "$FRONT" | grep -qiE 'error|not allowed|denied|1743'; then
  ok "can read the frontmost app (${FRONT})"
else
  bad "cannot read the frontmost app: ${FRONT}"
  note "System Settings > Privacy & Security > Automation"
  note "this is what the AppleScript behind the clipboard needs too"
fi

CLIP=$(osascript -e 'set the clipboard to "bonzi"' 2>&1 && osascript -e 'the clipboard' 2>&1)
if [ "$CLIP" = "bonzi" ]; then
  ok "can set and read the clipboard"
else
  bad "clipboard round trip failed: ${CLIP}"
fi

# --------------------------------------------------------------- commands ---
head_ "Commands he shells out to"
for cmd in osascript pmset launchctl /usr/bin/open; do
  if command -v "$cmd" >/dev/null 2>&1; then
    ok "${cmd}"
  else
    bad "${cmd} missing"
  fi
done

BATT=$(pmset -g batt 2>/dev/null)
if [ -n "$BATT" ]; then
  ok "pmset reports a power source"
else
  warn "pmset said nothing, probably a desktop with no battery"
fi

# ------------------------------------------------------------------ build ---
head_ "Build tools (only needed to build, not to run)"
for tool in iconutil codesign lipo ditto zip; do
  if command -v "$tool" >/dev/null 2>&1; then
    ok "${tool}"
  else
    warn "${tool} missing, needed to produce a build"
  fi
done

# ------------------------------------------------------------ log summary ---
head_ "His own log"
LOG="$HOME/Library/Logs/BonziBuddy/bonzi.log"
if [ -f "$LOG" ]; then
  ok "log at ${LOG}"
  printf '        last 5 lines:\n'
  tail -5 "$LOG" | sed 's/^/        /'
  if grep -q 'update check failed' "$LOG" 2>/dev/null; then
    note "update check failures above are the reason he never updated"
  fi
else
  warn "no log yet at ${LOG}, he has probably not run"
fi

printf '\n\033[1m%d ok, %d failed, %d warnings\033[0m\n' "$PASS" "$FAIL" "$SKIP"
if [ "$FAIL" -gt 0 ]; then
  printf 'Anything marked FAIL is a fixable permission or install problem above.\n'
fi
printf '\n'
