The deployable download is bonzi_buddy_v2.zip in this folder.

Rebuild it from ../BonziCode:
    pyinstaller bonzi_buddy_v2.spec
    Compress-Archive -Path dist\bonzi_buddy_v2.exe -DestinationPath ..\BonziSite\downloads\bonzi_buddy_v2.zip -Force

The zip must contain only the .exe - the PNGs are bundled inside it.
