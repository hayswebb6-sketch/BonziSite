# -*- mode: python ; coding: utf-8 -*-
import os

spec_dir = os.path.abspath(SPECPATH)

# Blender-rendered motions live in frames/<motion>/frame_NNN.png. Collect them
# by globbing rather than listing 122 paths by hand.
datas = [
    (os.path.join(spec_dir, 'Designer.png'), '.'),
    (os.path.join(spec_dir, 'bonzi.png'), '.'),
    (os.path.join(spec_dir, 'bonzi.ico'), '.'),
    (os.path.join(spec_dir, 'Designer_half.png'), '.'),
    (os.path.join(spec_dir, 'Designer_blink.png'), '.'),
    # change_wallpaper() looks this up with find_asset, so it has to be in the
    # bundle. Without it the build ships with the feature silently inert.
    (os.path.join(spec_dir, 'Bonzi_wallpaper.jpeg'), '.'),
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
    a.binaries,
    a.datas,
    [],
    name='bonzi_buddy_v2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(spec_dir, 'bonzi.ico'),
)
