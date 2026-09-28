How this is built
=================

Normally you do not need to build anything by hand. Pushing to main runs
.github/workflows/build.yml, which builds every platform and commits the
artifacts into downloads/. The site then serves them:

    downloads/bonzi_buddy_v2.zip           ->  /download
    downloads/bonzi_buddy_mac_x86_64.zip   ->  /download-mac
    downloads/bonzi_buddy_mac_arm64.zip    ->  /download-mac/arm64
    downloads/version.txt                  ->  the version in /version.json

The macOS build is published twice, once per CPU architecture. /download-mac
serves the Intel build, which is the right default because Apple Silicon still
runs it under Rosetta 2. /download-mac/arm64 is the native one.

The version manifests exist per platform too, so an installer can find the build
that matches what it is running:

    /version.json           the Windows build
    /version-mac.json       the default macOS build
    /version-mac/arm64.json the native Apple Silicon build

A missing artifact is a 503, not a 404. Nothing is wrong with the link, the
build has just not landed on this branch yet, and it is worth retrying.

Building locally
----------------

From BonziCode/ on Windows:

    pip install -r requirements.txt
    python tools/make_icons.py
    pyinstaller --clean --noconfirm bonzi_buddy_v2.spec

That produces dist/bonzi_buddy_v2.exe. requirements.txt uses environment
markers, so pywin32 / winotify / pygetwindow are only installed on Windows and
the same file works on a macOS runner.

make_icons.py rewrites bonzi.ico with every size the shell actually asks for.
The committed icon only had a 256px frame, and Windows picks the 16px frame for
the taskbar, so it was being downscaled into a smear.

On macOS the .spec has to be the one that produces a bundle, because a .app is a
directory and not a single file:

    pip install -r requirements.txt
    python tools/make_icons.py --skip-ico --iconset build/BonziBuddy.iconset
    iconutil -c icns build/BonziBuddy.iconset -o bonzi.icns
    pyinstaller --clean --noconfirm bonzi_buddy_mac.spec
    codesign --force --deep --sign - "dist/Bonzi Buddy.app"
    ditto -c -k --sequesterRsrc --keepParent \
        "dist/Bonzi Buddy.app" dist/bonzi_buddy_mac_x86_64.zip

iconutil only exists on macOS, which is why make_icons.py writes a .iconset
directory on any platform and leaves the one command that needs a Mac to CI.
Everything else is a plain resize from bonzi.png.

ditto rather than zip: the bundle contains symlinks and an executable bit, and
zip without -y flattens both, which breaks the signature.

For the real thing, run the build on the architecture you are targeting:

    ARCH=x86_64  # or arm64
    pyinstaller --clean --noconfirm bonzi_buddy_mac.spec
    lipo -archs "dist/Bonzi Buddy.app/Contents/MacOS/Bonzi Buddy"

First launch on a Mac
---------------------

The build is ad-hoc signed, not notarised, so Gatekeeper blocks the first
launch. Right-click Bonzi Buddy.app and choose Open. That is a one-time thing
per download. Notarising properly needs a paid Apple Developer ID, which is not
configured for this repository.

Turning on self-update
----------------------

In bonzi_buddy_v2.py:

    UPDATE_MANIFEST_URL="https://<your-site-host>/version.json"

Leave it blank to disable self-update. The updater refuses plain http, and
only acts when the manifest version is strictly newer than APP_VERSION, so
bump APP_VERSION together with downloads/version.txt.

CI greps APP_VERSION out of the file it just compiled, so downloads/version.txt
can never describe a different binary than the one that was published.
