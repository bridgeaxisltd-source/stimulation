"""Cut the promo's assets out of the real ParentConnect product images.

Usage: python3 prep.py <project-dir>
Inputs (copied from bridgeaxis-website/public): parentconnect-attendance-mobile-new.png,
parentconnect-insights-new.png, parentconnect-logo.png.
"""
import sys

import numpy as np
from PIL import Image

A = sys.argv[1] + "/assets"


def key_white(im):
    """Colour-to-alpha against white, then crop to content."""
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    alpha = np.clip((255 - a).max(axis=2) / 255.0 * 1.15, 0, 1)
    alpha[alpha < 0.04] = 0
    rgb = np.clip((a - 255 * (1 - alpha[..., None])) / np.maximum(alpha, 1e-3)[..., None], 0, 255)
    ys, xs = np.where(alpha > 0.1)
    out = np.dstack([rgb, alpha * 255]).astype(np.uint8)
    return Image.fromarray(out[ys.min() - 4 : ys.max() + 4, xs.min() - 4 : xs.max() + 4], "RGBA")


def bbox(im, box, thresh=200):
    """Tight bbox of dark pixels (the device body) inside `box`."""
    sub = np.asarray(im.convert("L").crop(box))
    ys, xs = np.where(sub < thresh)
    return (box[0] + xs.min(), box[1] + ys.min(), box[0] + xs.max() + 1, box[1] + ys.max() + 1)


key_white(Image.open(f"{A}/parentconnect-logo.png")).save(f"{A}/pc-logo-alpha.png")

mob = Image.open(f"{A}/parentconnect-attendance-mobile-new.png").convert("RGB")
w, h = mob.size
left = bbox(mob, (0, 0, w // 2 + 20, h))
right = bbox(mob, (w // 2 + 20, 0, w, h))
mob.crop(left).save(f"{A}/phone-roster.png")
mob.crop(right).save(f"{A}/phone-submitted.png")
print("phone-roster", left, "phone-submitted", right)

ins = Image.open(f"{A}/parentconnect-insights-new.png").convert("RGB")
for i, x0 in enumerate([304, 491, 681, 874]):
    ins.crop((x0, 291, x0 + [176, 177, 180, 188][i], 410)).save(f"{A}/stat{i}.png")
ins.crop((304, 427, 711, 666)).save(f"{A}/chart.png")
ins.crop((1185, 300, 1446, 776)).save(f"{A}/notifs.png")
