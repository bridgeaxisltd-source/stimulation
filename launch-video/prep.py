import sys
import numpy as np
from PIL import Image

A = sys.argv[1] + "/assets"

# Real logo -> tight crop with white keyed to alpha (colour-to-alpha against white).
im = np.asarray(Image.open(f"{A}/bridgeaxis-logo.png").convert("RGB")).astype(np.float32)
alpha = np.clip((255 - im).max(axis=2) / 255.0 * 1.15, 0, 1)
alpha[alpha < 0.04] = 0
safe = np.maximum(alpha, 1e-3)[..., None]
rgb = np.clip((im - 255 * (1 - alpha[..., None])) / safe, 0, 255)
ys, xs = np.where(alpha > 0.1)
y0, y1, x0, x1 = ys.min() - 6, ys.max() + 6, xs.min() - 6, xs.max() + 6
out = np.dstack([rgb, alpha * 255]).astype(np.uint8)[y0:y1, x0:x1]
Image.fromarray(out, "RGBA").save(f"{A}/logo-alpha.png")
# Mark only (the "A" bridge symbol is left of the wordmark)
mark_w = int((500 - x0) * 1.0)
Image.fromarray(out[:, :mark_w], "RGBA").save(f"{A}/logo-mark.png")
Image.fromarray(out[:, mark_w:], "RGBA").save(f"{A}/logo-word.png")

# Real buttons cropped from the live-site screenshots (1920x1080, dpr 1).
hero = Image.open(f"{A}/hero.png")
hero.crop((172, 800, 354, 848)).save(f"{A}/btn-start.png")
hero.crop((366, 800, 572, 848)).save(f"{A}/btn-explore.png")
hero.crop((1701, 21, 1878, 63)).save(f"{A}/btn-consult.png")
prod = Image.open(f"{A}/sec-product.png")
prod.crop((172, 702, 388, 750)).save(f"{A}/btn-pc.png")
print("logo crop", out.shape, "mark_w", mark_w)
