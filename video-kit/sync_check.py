"""Check that the audio in a finished video lands on the timeline's beat events.

Usage: python3 sync_check.py <video.mp4> <timeline.json>

Decodes the audio from the video itself (so encoder priming or mux offsets are caught),
finds onsets with spectral flux in the band each event lives in (clicks and stabs in
2-9 kHz, impacts in the sub band, 30-200 Hz) and reports how far each event sits from
the nearest onset. A video passes when every event is within 15 ms, about one frame at 60 fps.
"""
import json
import subprocess
import sys

import numpy as np

SR = 44100
HOP = 128
WIN = 1024

video, timeline = sys.argv[1], sys.argv[2]
TL = json.load(open(timeline))
B = 60 / TL["bpm"]

raw = subprocess.run(
    ["ffmpeg", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
    capture_output=True, check=True,
).stdout
x = np.frombuffer(raw, np.float32).astype(np.float64)

frames = np.lib.stride_tricks.sliding_window_view(x, WIN)[::HOP] * np.hanning(WIN)
mag = np.abs(np.fft.rfft(frames, axis=1))
freqs = np.fft.rfftfreq(WIN, 1 / SR)


def onsets_in(lo, hi):
    """Onset times from log spectral flux restricted to lo-hi Hz (local maxima > 2 sigma)."""
    band = mag[:, (freqs > lo) & (freqs < hi)]
    flux = np.maximum(np.diff(np.log1p(band), axis=0), 0).sum(axis=1)
    flux = (flux - np.median(flux)) / (np.std(flux) + 1e-9)
    peaks = [i for i in range(1, len(flux) - 1) if flux[i] > 2.0 and flux[i] >= flux[i - 1] and flux[i] > flux[i + 1]]
    return np.array([(i + 1) * HOP / SR + WIN / 2 / SR for i in peaks])


bands = {"click": onsets_in(2000, 9000), "hook": onsets_in(2000, 9000), "impact": onsets_in(30, 200)}
events = [("click", b) for b in TL.get("clicks", [])] + [("hook", b) for b in TL.get("hookWords", [])] + \
         [("impact", b) for b in TL.get("impacts", [])]
worst = {}
for kind, b in sorted(events, key=lambda e: e[1]):
    t = b * B
    on = bands[kind]
    d = (on[np.argmin(np.abs(on - t))] - t) * 1000
    worst[kind] = max(worst.get(kind, 0), abs(d))
    print(f"{kind:7s} beat {b:5.2f}  t={t:6.3f}s  nearest onset {d:+6.1f} ms")
ok = all(w <= 15 for w in worst.values())
print("\nworst offset per kind: " + ", ".join(f"{k} {w:.1f} ms" for k, w in worst.items()) + f" -> {'PASS' if ok else 'FAIL'}")
