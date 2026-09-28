# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS .app bundle.

The Windows build uses bonzi_buddy_v2.spec; this one exists because a .app is
a directory bundle rather than a single file, and because the two builds do not
bundle the same things. The old macOS build was driven by a long --add-data
command line that left the frames/ folder behind, so macOS users got the
procedural idle animation and none of the wave/dance/spin/globe motions. This
collects the same frame folders the Windows spec does.

Bonzi's version is read out of the entry script at build time so the bundle's
CFBundleShortVersionString can never drift from APP_VERSION.

Run from BonziCode/ :

    python tools/make_icons.py --skip-ico --iconset build/BonziBuddy.iconset
    iconutil -c icns build/BonziBuddy.iconset -o bonzi.icns
    pyinstaller --clean --noconfirm bonzi_buddy_mac.spec
"""
import os
import re

spec_dir = os.path.abspath(SPECPATH)

APP_NAME = "Bonzi Buddy"
BUNDLE_ID = "com.bonzibuddy.app"


def pick_icon():
    """Prefer the .icns CI built with iconutil, fall back to what we have.

    PyInstaller will convert a .png or .ico itself, but it does it by scaling,
    so the retina Dock icon comes out soft. iconutil gets it right, and only
    runs on macOS, which is exactly where this spec runs.
    """
    for name in ("bonzi.icns", "bonzi.ico", "bonzi.png"):
        path = os.path.join(spec_dir, name)
        if os.path.isfile(path):
            return path
    raise SystemExit("no icon found; expected bonzi.icns, bonzi.ico or bonzi.png")


def read_app_version():
    entry = os.path.join(spec_dir, 'bonzi_buddy_v2.py')
    with open(entry, encoding="utf-8") as handle:
        match = re.search(r'^APP_VERSION="([^"]+)"', handle.read(), re.M)
    if not match:
        raise SystemExit("could not read APP_VERSION out of bonzi_buddy_v2.py")
    return match.group(1)


app_version = read_app_version()

# Same payload as the Windows spec: the artwork, plus every rendered frame.
datas = [
    (os.path.join(spec_dir, 'Designer.png'), '.'),
    (os.path.join(spec_dir, 'bonzi.png'), '.'),
    (os.path.join(spec_dir, 'Designer_half.png'), '.'),
    (os.path.join(spec_dir, 'Designer_blink.png'), '.'),
]

frames_root = os.path.join(spec_dir, 'frames')
if os.path.isdir(frames_root):
    for current, _dirs, files in os.walk(frames_root):
        rel = os.path.relpath(current, spec_dir)
        for name in files:
            if name.lower().endswith('.png'):
                datas.append((os.path.join(current, name), rel))
else:
    print('WARNING: no frames/ directory found, the app will fall back to '
          'the procedural idle animation only')

a = Analysis(
    ['bonzi_buddy_v2.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(
    coll,
    name=APP_NAME + '.app',
    icon=pick_icon(),
    bundle_identifier=BUNDLE_ID,
    info_plist={
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleShortVersionString': app_version,
        'CFBundleVersion': app_version,
        # Tk draws in points; without this the window and the animations come
        # out blurry on every Retina display.
        'NSHighResolutionCapable': True,
    },
)
