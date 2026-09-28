"""Build the Bonzi icons from bonzi.png.

Run from BonziCode/ :

    python tools/make_icons.py                 # rewrite bonzi.ico
    python tools/make_icons.py --iconset build/BonziBuddy.iconset

Why this exists: the .exe icon resource and the macOS Dock icon are the same
picture, and both are picky about size. Windows picks whichever of the sizes
inside the .ico best matches the taskbar (16px in a taskbar, 32px on Alt-Tab),
so a single 256px frame turns into a blurry smear at 16px. The macOS Dock wants
an .icns, which has to be built by iconutil from a .iconset directory of ten
sized PNGs - iconutil only exists on macOS, so we emit the .iconset here and let
CI run the one command that needs a Mac.

Everything is resized from bonzi.png, the dedicated square crop of Bonzi's
face. Designer.png is the full 1024x1536 body with most of the canvas empty, so
resizing that would shrink him into the middle of the icon.
"""

import argparse
import os

from PIL import Image

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE=os.path.join(ROOT, "bonzi.png")
ICO=os.path.join(ROOT, "bonzi.ico")

# Windows reads the frame that matches the surface it is drawing on. 16 is the
# taskbar, 32 is Alt-Tab and the window title, 256 is the Explorer thumbnail.
ICO_SIZES=[16, 20, 24, 32, 40, 48, 64, 96, 128, 256]

# (filename, pixel size) pairs for the .iconset that iconutil turns into an
# .icns. The @2x entries are the retina frames.
ICONSET_SIZES=[
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

def resized(source, size):
    # LANCZOS keeps the eyes and the glasses legible when we blow the 512px
    # source up to the 1024px frame the retina Dock actually asks for.
    return source.resize((size, size), Image.LANCZOS)

def write_ico(source, path):
    source.save(path, format="ICO", sizes=[(n, n) for n in ICO_SIZES])
    written=Image.open(path)
    print(f"{path}: {written.size[0]}px source, frames {ICO_SIZES}")

def write_iconset(source, directory):
    os.makedirs(directory, exist_ok=True)
    for name, size in ICONSET_SIZES:
        resized(source, size).save(os.path.join(directory, name), format="PNG")
    print(f"{directory}: {len(ICONSET_SIZES)} frames")
    print("now run: iconutil -c icns <dir> -o bonzi.icns")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=SOURCE, help="the square Bonzi crop")
    parser.add_argument("--ico", default=ICO, help="where to write the .ico")
    parser.add_argument("--iconset", default=None,
                        help="also write a macOS .iconset here")
    parser.add_argument("--skip-ico", action="store_true",
                        help="macOS runs only need the .iconset")
    args=parser.parse_args()

    with Image.open(args.source) as opened:
        source=opened.convert("RGBA")

    if source.width!=source.height:
        raise SystemExit(
            f"{args.source} is {source.width}x{source.height}; icons are square"
        )

    if not args.skip_ico:
        write_ico(source, args.ico)

    if args.iconset:
        write_iconset(source, args.iconset)

if __name__=="__main__":
    main()
