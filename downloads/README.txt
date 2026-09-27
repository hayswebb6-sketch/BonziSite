How this is built
=================

Normally you do not need to build anything by hand. Pushing to main runs
.github/workflows/build.yml, which builds both platforms and commits the
artifacts into downloads/. The site then serves them:

    downloads/bonzi_buddy_v2.zip    ->  /download
    downloads/bonzi_buddy_mac.zip   ->  /download-mac
    downloads/version.txt           ->  the version in /version.json

Building locally
----------------

From BonziCode/ :

    pip install -r requirements.txt
    pyinstaller --clean --noconfirm bonzi_buddy_v2.spec

That produces dist/bonzi_buddy_v2.exe. requirements.txt uses environment
markers, so pywin32 / winotify / pygetwindow are only installed on Windows and
the same file works on a macOS runner.

On macOS the .spec is not used, because a .app bundle is not a single file.
The workflow builds it directly instead:

    pyinstaller --clean --noconfirm --name "Bonzi Buddy" --windowed \
        --icon bonzi.ico \
        --add-data "Designer.png:." \
        --add-data "Designer_half.png:." \
        --add-data "Designer_blink.png:." \
        --add-data "bonzi.png:." \
        bonzi_buddy_v2.py
    codesign --force --deep --sign - "dist/Bonzi Buddy.app"
    cd dist && zip -qry ../bonzi_buddy_mac.zip "Bonzi Buddy.app"

Turning on self-update
----------------------

In bonzi_buddy_v2.py:

    UPDATE_MANIFEST_URL="https://<your-site-host>/version.json"

Leave it blank to disable self-update. The updater refuses plain http, and
only acts when the manifest version is strictly newer than APP_VERSION, so
bump APP_VERSION together with downloads/version.txt.
