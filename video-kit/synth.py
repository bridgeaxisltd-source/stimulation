"""Synthesize a short house track with UI clicks on the beat.

Usage: python3 synth.py <project-dir>   -> <project-dir>/music.wav

Everything is generated from scratch with numpy. Event times (clicks, ticks,
impacts, whooshes) and the arrangement (`music` block: chords, build, drop,
breaks, fills, rolls, risers, final stab) come from the project's
timeline.json, so the audio lines up with the motion on screen.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthlib import *  # noqa: E402,F403

DIR = Path(sys.argv[1])
TL = json.loads((DIR / "timeline.json").read_text())
M = TL["music"]
B = 60 / TL["bpm"]
DUR = TL["duration"]
N = int(DUR * SR)

mix = Mix(N)
L, R, sendL, sendR = mix.L, mix.R, mix.sendL, mix.sendR  # arrangement writes into these in place
add = mix.add


# ---------------------------------------------------------------- harmony
# One chord per bar (MIDI voicings), bass root per bar.
CHORDS = [tuple(c) for c in M["chords"]]
BASS = M["bass"]
BAR = 4 * B
DROP, END = M["drop"], M["end"]
BREAKS = M.get("breaks", [])


def in_break(b):
    return any(lo <= b < hi for lo, hi in BREAKS)



# ---------------------------------------------------------------- arrange
groove = lambda b: DROP <= b < END  # full-beat section

# pad + arp per bar, filter opening up through the intro
padL = np.zeros_like(L)
padR = np.zeros_like(R)
arp = np.zeros_like(L)
arpPan = np.zeros_like(L)
for bar in range(len(CHORDS)):
    start = bar * BAR
    cutoff = M["cutoffs"][bar]
    length = min(BAR, (END - bar * 4) * B)
    if length <= 0:
        break
    l, r = pad_bar(CHORDS[bar], length, cutoff)
    i = int(start * SR)
    padL[i : i + len(l)] += l
    padR[i : i + len(r)] += r
    tones = [CHORDS[bar][0] + 12, CHORDS[bar][1] + 12, CHORDS[bar][2] + 12, CHORDS[bar][0] + 24]
    pattern = [0, 2, 1, 3, 2, 1, 3, 2, 0, 2, 1, 3, 2, 3, 1, 2]
    steps = int(round(length / B * 4))
    for s in range(steps):
        at = start + s * B / 4
        p = pluck(tones[pattern[s]], int(0.25 * SR))
        if bar == 0:
            p = filt(p, 0, 900 + s * 120)
        j = int(at * SR)
        arp[j : j + len(p)] += p * (0.9 if s % 4 == 0 else 0.6)
        arpPan[j : j + len(p)] = -0.45 if s % 2 else 0.45

# final resolving stab
stabL, stabR = pad_bar(M["stab"], 0.25, 6500)
st = int(END * B * SR)
padL[st : st + len(stabL)] += stabL * 1.8
padR[st : st + len(stabR)] += stabR * 1.8
tailL, tailR = pad_bar(M["tail"], 1.6, 2200)
padL[st : st + len(tailL)] += tailL * 0.8
padR[st : st + len(tailR)] += tailR * 0.8

# ping-pong delay on the arp (3/16 note)
d = int(0.75 * B * SR)
arpL = arp * np.cos((arpPan + 1) * np.pi / 4)
arpR = arp * np.sin((arpPan + 1) * np.pi / 4)
for k in range(1, 5):
    g = 0.38 ** k
    src = arp[: len(arp) - d * k] * g
    if k % 2:
        arpL[d * k :] += src
    else:
        arpR[d * k :] += src

# sidechain duck from the kick
duck = np.ones_like(L)
BUILD = M["build"]
kicks = [b for b in np.arange(0, TL["beats"], 1.0) if (BUILD[0] <= b < BUILD[1]) or (groove(b) and not in_break(b))]
rel = int(0.22 * SR)
curve = 1 - 0.72 * (1 - np.linspace(0, 1, rel) ** 0.6)
for b in kicks:
    i = int(b * B * SR)
    duck[i : i + rel] = np.minimum(duck[i : i + rel], curve[: len(duck) - i][:rel])

L += padL * duck * 0.12
R += padR * duck * 0.12
sendL += padL * duck * 0.05
sendR += padR * duck * 0.05
arp_gain = 0.2
L += arpL * duck * arp_gain
R += arpR * duck * arp_gain
sendL += arpL * duck * arp_gain * 0.5
sendR += arpR * duck * arp_gain * 0.5

# drums
K, C, S, HC, HO, CR, BM = kick(), clap(), snare(), hat(), hat(True), crash(), boom()
for b in kicks:
    add(K, b * B, 0.5)
for b in np.arange(DROP, END, 1.0):
    if b % 2 == 1 and not in_break(b):
        add(C, b * B, 0.75, 0.05, send=0.35)
for b in np.arange(BUILD[0], END, 0.5):
    if b % 1 == 0.5:
        add(HO if groove(b) else HC, b * B, 0.32 if groove(b) else 0.2, 0.3)
for b in np.arange(DROP, END, 0.25):
    if b % 0.5:
        add(HC, b * B, 0.12, -0.3)
# snare fills / rolls
for b in M.get("fills", []):
    add(S, b * B, 0.5, send=0.2)
for lo, hi, g0, dg in M.get("rolls", []):
    for i, b in enumerate(np.arange(lo, hi, 0.125)):
        add(S, b * B, g0 + dg * i, send=0.2)

# bass: offbeat house bass + sub under every bar from the drop
for b in np.arange(DROP, END, 0.5):
    if b % 1 == 0.5 and not in_break(b):
        bar = int(b // 4)
        n = int(0.24 * SR)
        tt = t_(n)
        note = mtof(BASS[bar])
        env = np.clip(tt / 0.004, 0, 1) * np.exp(-tt / 0.12)
        sig = filt(saw(note, n, 2500), 0, 900) * 0.8 + np.sin(2 * np.pi * note * tt) * 0.9
        add(np.tanh(sig * 1.5) * env, b * B, 0.17)

# impacts, crashes, risers, whooshes
for b in TL["impacts"]:
    add(BM, b * B, 0.32)
    if b >= DROP:
        add(CR, b * B, 0.3, 0.2, send=0.25)
for at, length, gain in M.get("risers", []):
    add(riser(length * B), at * B, gain, send=0.2)
for b in TL["whooshes"]:
    add(whoosh(0.5 * B), b * B, 0.4, send=0.3)

# UI clicks exactly on the beat grid
CL, TK = ui_click(), ui_tick()
for b in TL["clicks"]:
    add(CL, b * B, 1.0, 0.12, send=0.12)
for i, b in enumerate(TL["ticks"]):
    add(TK, b * B, 0.6, -0.2 if i % 2 else 0.2, send=0.15)

mix.finish(DIR / "music.wav")
