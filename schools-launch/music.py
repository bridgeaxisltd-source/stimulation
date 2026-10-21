"""Soundtrack for the BridgeAxis OS reel (v2): 128 BPM, D major, D–A–Bm–G.

Usage: python3 music.py <project-dir>   -> <project-dir>/music.wav

Arrangement (beats):
  0–2    hook: a supersaw chord stab on every on-screen word, sub boom on the first
  2–4    snare roll + riser into the brand hit
  4–8    build: filtered four-on-the-floor, the lead hook enters, a half beat of silence before the drop
  8–19.5 drop: punchy kick, claps, house stabs on the offbeats, offbeat bass, lead hook with ping-pong delay
  19.5   one-beat break, back in at 20
  24–27  half-time for the calm rollout section, roll into the CTA at 28
  30.5   final D major stab and tail
UI clicks and ticks come from timeline.json, on the same beat grid as the visuals.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-kit"))
from synthlib import *  # noqa: E402,F403

DIR = Path(sys.argv[1])
TL = json.loads((DIR / "timeline.json").read_text())
B = 60 / TL["bpm"]
N = int(TL["duration"] * SR)
mix = Mix(N)
at = lambda beat: beat * B  # noqa: E731

CHORDS = [(62, 66, 69), (61, 64, 69), (62, 66, 71), (62, 67, 71)]  # D, A, Bm, G
BASS = [38, 45, 47, 43]
chord_at = lambda beat: CHORDS[int(beat // 4) % 4]  # noqa: E731
bass_at = lambda beat: BASS[int(beat // 4) % 4]  # noqa: E731


# ---------------------------------------------------------------- new voices
def kick2():
    n = int(0.36 * SR)
    tt = t_(n)
    f = 50 + 150 * np.exp(-tt / 0.024)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.15)
    click = filt(rng.uniform(-1, 1, n), 1500, 9000) * np.exp(-tt / 0.003)
    return np.tanh((body + 0.5 * click) * 1.8)


def stab(notes, decay=0.14, bright=6500):
    """Short detuned-saw chord, the house 'stab'."""
    n = int(0.6 * SR)
    tt = t_(n)
    out = np.zeros(n)
    for m in notes:
        for det in (-0.12, -0.04, 0.04, 0.12):
            out += saw(mtof(m + det), n, maxf=bright * 1.5)
    env = np.clip(tt / 0.003, 0, 1) * np.exp(-tt / decay)
    return filt(out, 160, bright) * env / (len(notes) * 2)


def lead(m, length):
    """Bright lead: square + saw an octave below, fast attack, gentle decay."""
    n = int((length + 0.3) * SR)
    tt = t_(n)
    v = square(mtof(m), n, 8000) * 0.6 + saw(mtof(m - 12), n, 5000) * 0.4
    env = np.clip(tt / 0.004, 0, 1) * np.exp(-tt / 0.22) * np.clip((length + 0.3 - tt) / 0.05, 0, 1)
    return filt(v, 250, 5200) * env


def rev_cymbal(length):
    """A crash played backwards: swells up and stops dead on the downbeat."""
    c = crash()[: int(length * SR)][::-1]
    return c * np.linspace(0, 1, len(c)) ** 2


# ---------------------------------------------------------------- arrangement helpers
def duck_curve(kick_beats, depth=0.7, release=0.2):
    duck = np.ones(len(mix.L))
    rel = int(release * SR)
    curve = 1 - depth * (1 - np.linspace(0, 1, rel) ** 0.6)
    for b in kick_beats:
        i = int(at(b) * SR)
        seg = duck[i : i + rel]
        duck[i : i + rel] = np.minimum(seg, curve[: len(seg)])
    return duck


full = lambda b: (8 <= b < 19.5) or (20 <= b < 24) or (28 <= b < 30.5)  # noqa: E731
half = lambda b: 24 <= b < 27  # noqa: E731

kicks = [b for b in np.arange(0, 32, 1.0) if (4 <= b < 7.75) or full(b) or (half(b) and b % 2 == 0)]
duck = duck_curve(kicks)

# A ducked bus for the melodic parts, folded into the mix at the end.
busL = np.zeros(len(mix.L))
busR = np.zeros(len(mix.L))


def bus_add(sig, t, gain=1.0, pan=0.0, send=0.0):
    i = int(round(t * SR))
    sig = sig[: len(busL) - i]
    a = (pan + 1) * np.pi / 4
    busL[i : i + len(sig)] += sig * np.cos(a) * gain
    busR[i : i + len(sig)] += sig * np.sin(a) * gain
    if send:
        mix.sendL[i : i + len(sig)] += sig * np.cos(a) * gain * send
        mix.sendR[i : i + len(sig)] += sig * np.sin(a) * gain * send


# ---------------------------------------------------------------- hook (0–4)
for i, b in enumerate(TL["hookWords"]):
    mix.add(stab(chord_at(0) if i < 2 else chord_at(4), decay=0.22), at(b), 0.75, (-0.25, 0.25)[i % 2], send=0.5)
mix.add(boom()[: int(0.7 * SR)] * np.linspace(1, 0, int(0.7 * SR)), at(0), 0.26)
for i, b in enumerate(np.arange(2, 4, 0.125)):
    mix.add(snare(), at(b), 0.08 + 0.022 * i, send=0.2)
mix.add(riser(2 * B), at(2), 0.32, send=0.2)

# soft pad under the hook and build, opening up
for bar, cutoff in [(0, 900), (1, 1800)]:
    # the build pad releases before beat 7.75 so the gap before the drop is truly empty
    l, r = pad_bar(chord_at(bar * 4), 4 * B if bar == 0 else 3.75 * B - 0.35, cutoff)
    i = int(at(bar * 4) * SR)
    busL[i : i + len(l)] += l * 0.09
    busR[i : i + len(r)] += r * 0.09

# ---------------------------------------------------------------- lead hook
MOTIF = [(0, 78, 0.5), (0.5, 81, 1), (1.5, 83, 0.5), (2, 81, 1), (3, 78, 0.5), (3.5, 76, 0.5),
         (4, 74, 0.5), (4.5, 76, 1), (5.5, 78, 0.5), (6, 81, 1), (7, 76, 1)]
for start in [4, 12, 20, 28]:
    for off, note, dur in MOTIF:
        b = start + off
        if (start == 4 and b >= 7.75) or b >= 30.5:  # keep the pre-drop gap and the ending clean
            continue
        g = 0.2 if start == 4 else 0.26
        sig = lead(note, dur * B)
        if start == 4:
            sig = filt(sig, 0, 1400 + 600 * off)  # filtered during the build
        bus_add(sig, at(b), g, 0.0, send=0.35)
        for k, (pan, tap) in enumerate([(-0.6, 0.75), (0.6, 1.5)]):  # ping-pong delay, 3/16 and 3/8
            bus_add(sig, at(b + tap), g * 0.35 / (k + 1), pan, send=0.3)

# ---------------------------------------------------------------- drums and bass
K, C, S, HC, HO, CR, BM = kick2(), clap(), snare(), hat(), hat(True), crash(), boom()
for b in kicks:
    mix.add(K if b >= 8 else filt(K, 0, 900), at(b), 0.5 if b >= 8 else 0.38)
for b in np.arange(8, 30.5, 1.0):
    if full(b) and b % 2 == 1:
        mix.add(C, at(b), 0.7, 0.05, send=0.35)
    if half(b) and b % 4 == 2:
        mix.add(C, at(b), 0.7, 0.05, send=0.45)
for b in np.arange(4, 30.5, 0.25):
    if full(b):
        if b % 1 == 0.5:
            mix.add(HO, at(b), 0.3, 0.3)
        elif b % 0.5:
            mix.add(HC, at(b), 0.11, -0.3)
    elif (4 <= b < 7.75 or half(b)) and b % 1 == 0.5:
        mix.add(HC, at(b), 0.18, 0.3)
for i, b in enumerate(np.arange(7, 7.75, 0.125)):
    mix.add(S, at(b), 0.12 + 0.05 * i, send=0.2)
for i, b in enumerate(np.arange(27, 28, 0.125)):
    mix.add(S, at(b), 0.1 + 0.04 * i, send=0.2)
for b in [19.5, 19.75, 19.875, 23.5, 23.75]:
    mix.add(S, at(b), 0.4, send=0.25)

# house stabs on the offbeats + offbeat bass through the drop
for b in np.arange(8, 30.5, 0.5):
    if not full(b) or b % 1 != 0.5:
        continue
    bus_add(stab(chord_at(b), decay=0.09), at(b), 0.55, (-0.2, 0.2)[int(b) % 2], send=0.25)
    n = int(0.22 * SR)
    tt = t_(n)
    note = mtof(bass_at(b))
    sig = filt(saw(note, n, 2200), 0, 1000) * 0.7 + np.sin(2 * np.pi * note * tt)
    bus_add(np.tanh(sig * 1.6) * np.clip(tt / 0.004, 0, 1) * np.exp(-tt / 0.11), at(b), 0.15)
# half-time section: long pad instead of stabs
l, r = pad_bar(chord_at(24), 3 * B, 3000)
i = int(at(24) * SR)
busL[i : i + len(l)] += l * 0.1
busR[i : i + len(r)] += r * 0.1

# ---------------------------------------------------------------- transitions and hits
for b in TL["impacts"]:
    mix.add(BM, at(b), 0.2)
    if b >= 8:
        mix.add(CR, at(b), 0.28, 0.2, send=0.25)
for b in [8, 20, 28]:  # reverse cymbal into each section
    rc = rev_cymbal(B)
    mix.add(rc, at(b) - len(rc) / SR, 0.22, -0.1, send=0.2)
mix.add(riser(3.75 * B), at(4), 0.3, send=0.2)
mix.add(riser(1.5 * B), at(26.5), 0.28, send=0.2)
for b in TL["whooshes"]:
    mix.add(whoosh(0.5 * B), at(b) - 0.25 * B, 0.36, send=0.3)

# final stab and tail
bus_add(stab((62, 66, 69, 74), decay=0.5, bright=7000), at(30.5), 0.9, send=0.6)
l, r = pad_bar((50, 62, 69), 1.8, 2400)
i = int(at(30.5) * SR)
busL[i : i + len(l)] += l * 0.1
busR[i : i + len(r)] += r * 0.1

# ---------------------------------------------------------------- UI sounds on the grid
CL, TK = ui_click(), ui_tick()
for b in TL["clicks"]:
    mix.add(CL, at(b), 1.0, 0.12, send=0.12)
for i, b in enumerate(TL["ticks"]):
    mix.add(TK, at(b), 0.6, -0.2 if i % 2 else 0.2, send=0.15)

mix.L += busL * duck
mix.R += busR * duck
mix.finish(DIR / "music.wav")
