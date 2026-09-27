# -*- mode: python ; coding: utf-8 -*-
import os

spec_dir = os.path.abspath(SPECPATH)


a = Analysis(
    ['bonzi_buddy_v2.py'],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(spec_dir, 'Designer.png'), '.'),
        (os.path.join(spec_dir, 'bonzi.png'), '.'),
        (os.path.join(spec_dir, 'bonzi.ico'), '.'),
        (os.path.join(spec_dir, 'Designer_half.png'), '.'),
        (os.path.join(spec_dir, 'Designer_blink.png'), '.'),
    ],
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
