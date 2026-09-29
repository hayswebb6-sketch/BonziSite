#!/bin/bash
# selftest_smoke.sh: prove that smoke_test.sh can actually fail.
#
#   bash tools/selftest_smoke.sh
#
# A test that cannot fail is worse than no test, because it looks like cover and
# buys none. Every guard in smoke_test.sh is a message nobody has ever seen
# printed, so this drives the script through each failure it claims to catch and
# asserts the right one fired, then checks it still passes a healthy app.
#
# The whole mac environment is stubbed: open, pgrep and launchctl are shims on
# PATH, the "app" is a shell script, and HOME is a scratch directory. So this
# runs anywhere bash does, including the Linux boxes the publish job uses, and
# never touches the machine it runs on.
#
# The stubs are the reason the assertions have to be written the way they are.
# smoke_test.sh deletes the plist and the log *before* it launches, on purpose,
# so a leftover from an earlier run cannot make a broken build look clean. That
# means a harness which pre-creates those files is testing nothing: they are
# gone before the app is asked for them. So the `open` shim launches the fake
# app, and the fake app writes them, which is what really happens.

set -u

WORK="$(mktemp -d)"
TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUBS="$WORK/stubs"

PASS=0
FAIL=0

cleanup() {
  if [ -s "$WORK/pid" ]; then kill "$(cat "$WORK/pid")" 2>/dev/null || true; fi
  rm -rf "$WORK"
}
trap cleanup EXIT

# sandbox HOME, exported: the fake app runs in a subshell started by the open
# shim and has to find the same HOME the script under test is using.
export HOME="$WORK/home"
mkdir -p "$STUBS" "$WORK/repo/tools" "$HOME"

BUNDLE_DIR="$WORK/repo/dist/Bonzi Buddy.app/Contents/MacOS"
mkdir -p "$BUNDLE_DIR"
printf '#!/bin/sh\nexit 0\n' > "$BUNDLE_DIR/Bonzi Buddy"
chmod +x "$BUNDLE_DIR/Bonzi Buddy"

cp "$TOOLS/smoke_test.sh" "$WORK/repo/tools/"

# open stands in for launching the bundle. It writes the plist and the log the
# way the real app does on its way to main(), records its pid where the pgrep
# shim will look, and returns immediately, exactly as open does.
cat > "$STUBS/open" <<'EOF'
#!/bin/bash
[ -n "${FAKE_NO_START:-}" ] && exit 0
[ -n "${SKIP_PLIST:-}" ] || {
  mkdir -p "$HOME/Library/LaunchAgents"
  printf '<plist/>\n' > "$HOME/Library/LaunchAgents/com.bonzibuddy.app.plist"
}
[ -n "${FAKE_LOG:-}" ] && {
  mkdir -p "$HOME/Library/Logs/BonziBuddy"
  printf '%s\n' "$FAKE_LOG" > "$HOME/Library/Logs/BonziBuddy/bonzi.log"
}
sleep "${FAKE_SLEEP:-300}" >/dev/null 2>&1 &
echo $! > "$FAKE_PID_FILE"
exit 0
EOF

# No pid file means the app never appeared in the process table.
cat > "$STUBS/pgrep" <<'EOF'
#!/bin/bash
[ -s "$FAKE_PID_FILE" ] || exit 1
cat "$FAKE_PID_FILE"
EOF

cat > "$STUBS/launchctl" <<'EOF'
#!/bin/bash
exit 0
EOF
chmod +x "$STUBS"/*

# run <name> <want> <mode> <wait>
#   want: substring the failure message must contain, "" for the pass case
#   mode: pass | fail
run() {
  local name="$1" want="$2" mode="$3" wait="$4" rc
  rm -f "$WORK/pid"
  PATH="$STUBS:$PATH" FAKE_PID_FILE="$WORK/pid" \
    bash "$WORK/repo/tools/smoke_test.sh" "$wait" > "$WORK/out.txt" 2>&1
  rc=$?
  cleanup_pid

  if [ "$mode" = pass ]; then
    if [ $rc -ne 0 ]; then
      printf '  FAIL  %-26s expected pass, rc=%s\n' "$name" "$rc"
      sed 's/^/          /' "$WORK/out.txt"
      FAIL=$((FAIL+1)); return
    fi
    printf '  ok    %-26s passed\n' "$name"
  elif [ $rc -eq 0 ]; then
    printf '  FAIL  %-26s expected FAILURE but it passed\n' "$name"
    FAIL=$((FAIL+1)); return
  elif ! grep -q "$want" "$WORK/out.txt"; then
    printf '  FAIL  %-26s failed for the wrong reason\n' "$name"
    printf '          wanted: %s\n' "$want"
    sed 's/^/          /' "$WORK/out.txt"
    FAIL=$((FAIL+1)); return
  else
    printf '  ok    %-26s rejected: %s\n' "$name" "$want"
  fi
  PASS=$((PASS+1))
}

cleanup_pid() {
  if [ -s "$WORK/pid" ]; then kill "$(cat "$WORK/pid")" 2>/dev/null || true; rm -f "$WORK/pid"; fi
}

printf 'negative tests for smoke_test.sh\n\n'

# an app that never starts at all
FAKE_NO_START=1 run "app never starts" "never appeared" fail 1

# gone before the liveness check, with a wait long enough to be certain
FAKE_SLEEP=1 run "app exits during wait" "exited within" fail 5

# alive, but never reached add_to_startup()
SKIP_PLIST=1 FAKE_SLEEP=300 run "alive, never wrote plist" "add_to_startup" fail 1

# the happy path: alive, plist written, no log
FAKE_SLEEP=300 run "alive + plist, clean" "" pass 1

# every crash signature the log is checked for
for pair in \
  "Traceback (most recent call last):|logged a traceback|traceback in log" \
  "frame load failed for a.png|could not load its frames|frames missing" \
  "pyobjc is not installed, cannot read keys on macOS|keylog cannot work|pyobjc absent" \
  "macos launch agent failed: boom|LaunchAgent plist|launch agent failed"; do
  IFS='|' read -r line want name <<< "$pair"
  FAKE_LOG="$line" FAKE_SLEEP=300 run "$name" "$want" fail 1
done

# a missing bundle is rejected before anything is launched
rm -rf "$WORK/repo/dist"
run "no bundle at all" "no bundle at" fail 1

printf '\n%d ok, %d broken\n\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
