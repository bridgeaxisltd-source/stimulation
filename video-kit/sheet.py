"""Contact sheet of frames: python3 sheet.py out.png frame1.png frame2.png ..."""
import sys
from PIL import Image, ImageDraw
out, files = sys.argv[1], sys.argv[2:]
w0, h0 = Image.open(files[0]).size
tw, cols = (640, 3) if w0 >= h0 else (300, 6)
th = round(tw * h0 / w0)
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * tw + (cols + 1) * 8, rows * (th + 30) + 8), (40, 40, 40))
d = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    im = Image.open(f).convert("RGB").resize((tw, th))
    x, y = 8 + (i % cols) * (tw + 8), 8 + (i // cols) * (th + 30)
    sheet.paste(im, (x, y))
    d.text((x + 4, y + th + 6), f.split("/")[-1], fill=(255, 255, 255))
sheet.save(out)
