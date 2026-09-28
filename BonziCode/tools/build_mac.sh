#!/bin/bash
# build_mac.sh: produce a signed, stamped .app on this Mac, same as CI does.
#
#   bash tools/build_mac.sh              # native architecture
#   bash tools/build_mac.sh x86_64       # the Intel build, for Rosetta users
#
# Every step mirrors .github/workflows/build.yml on purpose. A build made here
# and one made by CI should be the same shape, so a difference between them is
# a real bug rather than a difference in procedure.

set -euo pipefail

TARGET="${1:-$(uname -m)}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

case "$TARGET" in
  arm64|x86_64) ;;
  *) echo "usage: $0 [arm64|x86_64], got '${TARGET}'" >&2; exit 2 ;;
esac

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
die() { printf '\033[31merror: %s\033[0m\n' "$1" >&2; exit 1; }

# PYTHON is resolved before anything else, because requirements.txt is
# installed with it and a wrong interpreter wastes the whole run.
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
[ -n "$PY" ] || die "no Python 3.10+ on PATH, install it first"

say "environment"
echo "python   $("$PY" --version 2>&1) ($(command -v "$PY"))"
echo "host     $(uname -m)"
echo "target   ${TARGET}"
if [ "$(uname -m)" != "$TARGET" ]; then
  echo "note     cross-building; the resulting bundle will only be usable"
  echo "         under Rosetta 2 on Apple Silicon, or on Intel"
fi

say "installing dependencies"
# This is where pyobjc-framework-Cocoa comes from. Without it the keylog
# imports AppKit against a package that is not there and fails silently.
"$PY" -m pip install --upgrade pip >/dev/null
"$PY" -m pip install -r requirements.txt

"$PY" -c 'import AppKit' 2>/dev/null ||
  die "AppKit will not import after install, the keylog would be dead"

say "reading APP_VERSION"
VERSION=$(grep -oE 'APP_VERSION="[^"]+"' bonzi_buddy_v2.py | head -1 | cut -d'"' -f2)
[ -n "$VERSION" ] || die "could not read APP_VERSION from bonzi_buddy_v2.py"
echo "version  ${VERSION}"

say "dock icon"
# iconutil only exists on macOS, which is why make_icons.py writes an .iconset
# here and leaves this one command to a real machine.
"$PY" tools/make_icons.py --skip-ico --iconset build/BonziBuddy.iconset
command -v iconutil >/dev/null 2>&1 || die "iconutil missing, cannot make an icns"
iconutil -c icns build/BonziBuddy.iconset -o bonzi.icns
[ -s bonzi.icns ] || die "iconutil produced an empty icns"
echo "wrote    bonzi.icns"

say "building the bundle"
rm -rf "dist/Bonzi Buddy.app"
"$PY" -m PyInstaller --clean --noconfirm bonzi_buddy_mac.spec

BIN="dist/Bonzi Buddy.app/Contents/MacOS/Bonzi Buddy"
[ -x "$BIN" ] || die "no executable at ${BIN}"
[ -d "dist/Bonzi Buddy.app/Contents/Frameworks" ] || die "no Frameworks, the bundle is incomplete"
[ -d "dist/Bonzi Buddy.app/Contents/Resources/frames" ] || die "no frames, the animations are missing"

# A wrong-arch bundle is the one macOS failure that looks fine here and breaks
# on someone else's machine, so the slice is checked rather than assumed.
say "verifying the slice"
SLICE=$(lipo -archs "$BIN")
echo "slice    ${SLICE}"
case "$TARGET" in
  arm64) echo "$SLICE" | grep -q arm64 || die "asked for arm64, got ${SLICE}" ;;
  x86_64) echo "$SLICE" | grep -q x86_64 || die "asked for x86_64, got ${SLICE}" ;;
esac

say "signing"
# An unsigned .app is quarantined on first launch. This is ad-hoc, not a
# Developer ID, so Gatekeeper still asks once, which is why the site tells
# people to right-click and choose Open.
codesign --force --deep --sign - "dist/Bonzi Buddy.app"
codesign --verify --deep --strict "dist/Bonzi Buddy.app"
echo "verified"

say "packaging"
# ditto rather than zip: the bundle has symlinks and an executable bit, and
# zip without -y flattens both, which breaks the signature.
ZIP="dist/bonzi_buddy_mac_${TARGET}.zip"
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "dist/Bonzi Buddy.app" "$ZIP"

# The version goes inside the zip, next to the binary it describes, so the
# site's manifest can never advertise a number that is not this build.
mkdir -p build
printf '%s\n' "$VERSION" > build/version.txt
zip -j -q "$ZIP" build/version.txt
rm -f build/version.txt

say "checking what was produced"
[ -s "$ZIP" ] || die "zip is empty"
unzip -l "$ZIP" | grep -q 'version.txt' ||
  die "version.txt is not in the zip, the site would refuse to advertise it"
ls -lh "$ZIP"
shasum -a 256 "$ZIP"

cat <<EOF

built ${VERSION} for ${TARGET}

  ${ZIP}

To try it:
  open "${ZIP%.*}"          # or unzip, then right-click the .app and Open

To run the doctor and see which permissions are still missing:
  bash tools/mac_doctor.sh

To publish it, copy the zip into downloads/ at the repo root and commit:
  bonzi_buddy_mac_${TARGET}.zip
The site will then serve it at /download-mac${TARGET:+/${TARGET}} and the
updater will find it at /version-mac${TARGET:+/${TARGET}}.json
EOF
