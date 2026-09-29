"""Compose the social share card at static/og.png (1200x630).

    python tools/make_og.py

One-off generator, run by hand when the artwork changes; the PNG is committed.
It is not imported by the site and Pillow is not a site dependency.

Fonts come from the system font directory and the layout is tuned for them, so
this is written for the machine the card was designed on. The output is just a
PNG, so anywhere else the geometry may need a nudge - nothing here runs in CI.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1200, 630
FONT_DIR = r"C:\Windows\Fonts"
ROOT = r"C:\Users\Hays\Downloads\Bonzi\BonziSite"

INK_900 = (18, 10, 26)
INK_800 = (28, 16, 41)
INK_600 = (48, 24, 72)
INK_500 = (72, 48, 96)
INK_400 = (96, 72, 144)
INK_300 = (144, 120, 168)
INK_200 = (192, 144, 192)
CHROME_HI = (240, 240, 240)
CHROME_DK = (64, 64, 64)

canvas = Image.new("RGB", (W, H), INK_900)
px = canvas.load()
for y in range(H):
    t = y / (H - 1)
    px_row = tuple(
        round(a + (b - a) * t) for a, b in zip(INK_800, INK_900)
    )
    for x in range(W):
        px[x, y] = px_row

# violet glow behind where the portrait sits
glow = Image.new("L", (W, H), 0)
ImageDraw.Draw(glow).ellipse((620, -140, 1360, 660), fill=150)
glow = glow.filter(ImageFilter.GaussianBlur(120))
canvas.paste(Image.new("RGB", (W, H), INK_300), (0, 0), glow)

# faint scanlines, the same idea as the site background
overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
od = ImageDraw.Draw(overlay)
for y in range(0, H, 3):
    od.line((0, y, W, y), fill=(255, 255, 255, 7))
canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

inset = 22
tb_h = 46
d = ImageDraw.Draw(canvas)
d.rectangle((inset, inset, W - inset, H - inset), outline=CHROME_HI, width=1)
d.rectangle((inset + 1, inset + 1, W - inset - 1, H - inset - 1), outline=INK_600, width=1)

# titlebar gradient, ink-400 -> ink-500 -> ink-600
for x in range(inset + 1, W - inset):
    t = (x - inset) / (W - 2 * inset)
    if t < 0.55:
        k, a, b = t / 0.55, INK_400, INK_500
    else:
        k, a, b = (t - 0.55) / 0.45, INK_500, INK_600
    d.line((x, inset + 1, x, inset + tb_h),
           fill=tuple(round(a[i] + (b[i] - a[i]) * k) for i in range(3)))
d.line((inset, inset + tb_h, W - inset, inset + tb_h), fill=CHROME_DK)

font_title_bar = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 22)
icon = Image.open(f"{ROOT}\\static\\favicon-32.png").convert("RGBA").resize((26, 26))
canvas.paste(icon, (inset + 14, inset + 11), icon)
d.text((inset + 50, inset + 12), "Bonzi Buddy", font=font_title_bar, fill=(255, 255, 255))

bx = W - inset - 14
for _ in range(3):
    bx -= 30
    d.rectangle((bx, inset + 11, bx + 22, inset + 33), fill=(216, 216, 216), outline=CHROME_DK)

# portrait, bottom-right inside the window body
portrait = Image.open(f"{ROOT}\\static\\Designer.png").convert("RGBA")
ph = 520
pw = round(portrait.width * ph / portrait.height)
portrait = portrait.resize((pw, ph), Image.LANCZOS)
canvas.paste(portrait, (W - inset - 40 - pw, H - inset - 12 - ph), portrait)

# text block, vertically centred in the body
font_name = ImageFont.truetype(f"{FONT_DIR}\\segoeuib.ttf", 104)
font_tag = ImageFont.truetype(f"{FONT_DIR}\\segoeui.ttf", 34)
font_foot = ImageFont.truetype(f"{FONT_DIR}\\consola.ttf", 20)

tx = inset + 54
line_h = 44
body_top = inset + tb_h
block_h = 116 + 18 + line_h * 2 + 26 + 24
top = body_top + (H - inset - body_top - block_h) // 2

d.text((tx, top), "Bonzi Buddy", font=font_name, fill=(255, 255, 255))
d.text((tx, top + 122), "The greatest digital friend", font=font_tag, fill=INK_200)
d.text((tx, top + 122 + line_h), "ever created.", font=font_tag, fill=INK_200)
d.text((tx, top + 122 + line_h * 2 + 26),
       "no uninstaller  \u00b7  no terms of service  \u00b7  no explanation",
       font=font_foot, fill=INK_300)

canvas.save(f"{ROOT}\\static\\og.png", optimize=True)
print("wrote static/og.png", canvas.size)
