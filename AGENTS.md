# Bonzi Buddy - working notes

State as of 2026-09-30. Read this first in a new session; it exists because
there is no cross-session memory otherwise.

## What this is

Bonzi Buddy recreation: an animated desktop character in a Tk window, with a
deliberately *visible* keylog and screen-peek window. Visible-by-design is
intentional, not an oversight - see the comment block at
`BonziCode/bonzi_buddy_1.21.py:1899`. Do not "fix" the keylog into a silent
one. Current version is **1.21**.

## Layout

    BonziCode/          the app source, specs, build output
      bonzi_buddy_1.21.py      main source, ~2500 lines
      bonzi_buddy_1.21.spec    Windows onefile .exe
      bonzi_buddy_mac.spec     macOS .app bundle
      requirements.txt         env-markered, same file works on both platforms
      tools/                   build + test helpers
      dist/                    local build output (gitignored)
    app.py              Flask download site
    downloads/          published artifacts, served to users
    templates/ static/  site assets

## Verified working

All three published artifacts are present, stamped, and consistent at 1.21:

| File | Serves | Notes |
|---|---|---|
| `downloads/bonzi_buddy_1.21.zip` | `/download` | contains `bonzi_buddy_1.21.exe` + `version.txt` |
| `downloads/bonzi_buddy_mac_x86_64.zip` | `/download-mac` | Intel, also runs under Rosetta 2 |
| `downloads/bonzi_buddy_mac_arm64.zip` | `/download-mac/arm64` | native Apple Silicon |

`version.txt` lives *inside* each zip, next to the binary it describes, so the
stamp and the binary cannot disagree. `app.py` reads it from there - do not add
a second version file.

`app.py:15-18` hardcodes those three filenames. Renaming a zip silently breaks
the download links. That exact bug happened before, hence the comment.

macOS bundles carry `_CodeSignature/CodeResources` (ad-hoc signed),
`AppKit`/`objc`/`Quartz` frameworks (so the keylog's `NSEvent` import works),
and `Resources/frames/{dance,globe,spin,wave}/`.

## Testing

Two scripts, and the distinction matters:

- `tools/selftest_smoke.sh` - **run this anywhere bash runs**, Windows included.
  Stubs the entire macOS environment (`open`, `pgrep`, `launchctl` shims on
  PATH, fake app is a shell script, scratch `HOME`). Proves the other script can
  actually fail. Last run: **9 ok, 0 broken**.
- `tools/smoke_test.sh` - macOS only. Needs a real `.app`, `launchctl`, and a
  macOS window server. **Cannot run on Windows**, which is the normal dev box.

Only the CI runner can do the real launch check. If asked to verify a macOS
build from Windows, say so rather than implying it was covered.

## Building

Windows:

    cd BonziCode
    pip install -r requirements.txt
    python tools/make_icons.py
    pyinstaller --clean --noconfirm bonzi_buddy_1.21.spec

macOS needs a Mac (`iconutil`, `lipo`, `codesign`, `ditto`). `ditto` rather than
`zip` - the bundle has symlinks and an executable bit that plain zip flattens,
which breaks the signature. `make_icons.py --skip-ico` writes a `.iconset` on
any platform so only `iconutil` is left to CI.

`make_icons.py` matters: the committed icon had only a 256px frame, and Windows
picks the 16px frame for the taskbar, so it was being downscaled into a smear.

The `frames/` directory is globbed by the spec files, not listed path by path.
Missing it degrades to a procedural idle animation rather than failing, so a
build can look fine and have no artwork.

## Open questions

1. **`requests` in `requirements.txt:20` is unused.** The comment says the
   updater is still on stdlib `urllib`. Either wire the updater to `requests` or
   drop it - right now it bloats all three bundles with a library nothing calls.
   Do not guess which; ask.
2. **Which source is authoritative?** `Downloads\` still holds older
   `bonzi_buddy_v2\` copies, `.exe.old` files, and a separate
   `bonzi_buddy_1.21.zip`. Assumed to be abandoned intermediates and a manual
   copy, but unconfirmed - worth checking they are not meant to stay in sync.

## Conventions worth keeping

- Failures are explicit `bad`/`raise` with a message, never bare `-e`. Several
  scripts rely on this.
- A missing artifact is **503, not 404**. The link is fine, the build just has
  not landed yet, and retrying is reasonable.
- Self-update is off by default. Enable via `UPDATE_MANIFEST_URL` in
  `bonzi_buddy_1.21.py`; must be https (the updater rejects plain http) and the
  manifest version must be strictly newer than `APP_VERSION`.
- A push touching only `downloads/` does not trigger a build. Intentional -
  the publish job commits artifacts back to main.

## Unrelated, also in this session

A VirtualBox VM named `Linux` (Ubuntu 26.04 Desktop, `~/VirtualBox VMs/Linux`)
is set up for malware analysis. Isolation applied and **do not undo without
asking**: NIC detached, clipboard disabled, drag-drop disabled, no shared
folders. A 50 GB VDI; reinstalled 2026-09-30. TPM was removed from it - the
host's VirtualBox install has no TPM driver and the VM would not boot
(`DrvTpmEmu#0 ... VERR_NOT_FOUND`).