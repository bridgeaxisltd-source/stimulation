"""Synthesize a short house track with UI clicks on the beat.

Usage: python3 synth.py <project-dir>   -> <project-dir>/music.wav

Everything is generated from scratch with numpy. Event times (clicks, ticks,
impacts, whooshes) and the arrangement (`music` block: chords, build, drop,
breaks, fills, rolls, risers, final stab) come from the project's
timeline.json, so the audio lines up with the motion on screen.
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np

DIR = Path(sys.argv[1])
TL = json.loads((DIR / "timeline.json").read_text())
M = TL["music"]
SR = 44100
B = 60 / TL["bpm"]
DUR = TL["duration"]
N = int(DUR * SR)
rng = np.random.default_rng(7)

L = np.zeros(N + SR * 3)
R = np.zeros(N + SR * 3)
sendL = np.zeros_like(L)
sendR = np.zeros_like(R)


def t_(n):
    return np.arange(n) / SR


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def filt(x, lo=0.0, hi=None):
    """Brick-ish FFT band filter with short cosine skirts."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.ones_like(f)
    if lo > 0:
        g *= np.clip((f - lo * 0.7) / (lo * 0.3), 0, 1)
    if hi:
        g *= np.clip((hi * 1.3 - f) / (hi * 0.3), 0, 1)
    return np.fft.irfft(X * g, len(x))


def add(sig, at, gain=1.0, pan=0.0, send=0.0):
    """Mix a mono signal in at time `at` (seconds), equal-power pan."""
    i = int(round(at * SR))
    if i >= len(L):
        return
    sig = sig[: len(L) - i]
    a = (pan + 1) * np.pi / 4
    gl, gr = np.cos(a) * gain, np.sin(a) * gain
    L[i : i + len(sig)] += sig * gl
    R[i : i + len(sig)] += sig * gr
    if send:
        sendL[i : i + len(sig)] += sig * gl * send
        sendR[i : i + len(sig)] += sig * gr * send


def saw(freq, n, maxf=7000):
    tt = t_(n)
    out = np.zeros(n)
    for k in range(1, int(maxf / freq) + 1):
        out += np.sin(2 * np.pi * freq * k * tt + k * 0.7) / k
    return out * 0.6


def square(freq, n, maxf=9000):
    tt = t_(n)
    out = np.zeros(n)
    for k in range(1, int(maxf / freq) + 1, 2):
        out += np.sin(2 * np.pi * freq * k * tt) / k
    return out * 0.8


# ---------------------------------------------------------------- drums
def kick():
    n = int(0.45 * SR)
    tt = t_(n)
    f = 46 + 120 * np.exp(-tt / 0.032)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-tt / 0.13)
    s[:120] += rng.uniform(-1, 1, 120) * np.linspace(0.6, 0, 120)
    return np.tanh(s * 1.6)


def clap():
    n = int(0.35 * SR)
    tt = t_(n)
    env = np.zeros(n)
    for o in (0, 0.011, 0.022):
        i = int(o * SR)
        env[i:] += np.exp(-(tt[: n - i]) / 0.007)
    env += 0.5 * np.exp(-np.maximum(tt - 0.022, 0) / 0.1) * (tt > 0.022)
    return filt(rng.uniform(-1, 1, n), 900, 6000) * env


def snare():
    n = int(0.25 * SR)
    tt = t_(n)
    body = np.sin(2 * np.pi * 190 * tt) * np.exp(-tt / 0.04)
    return filt(rng.uniform(-1, 1, n), 1200, 9000) * np.exp(-tt / 0.07) + 0.6 * body


def hat(open_=False):
    n = int((0.3 if open_ else 0.08) * SR)
    tt = t_(n)
    return filt(rng.uniform(-1, 1, n), 7500, 16000) * np.exp(-tt / (0.09 if open_ else 0.017))


def crash():
    n = int(1.8 * SR)
    tt = t_(n)
    return filt(rng.uniform(-1, 1, n), 3500, 15000) * np.exp(-tt / 0.55)


def boom():
    n = int(1.4 * SR)
    tt = t_(n)
    f = 30 + 60 * np.exp(-tt / 0.18)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.28)
    s += filt(rng.uniform(-1, 1, n), 0, 260) * np.exp(-tt / 0.12) * 1.5
    return np.tanh(s * 1.4)


def riser(length, lo=900, hi=12000):
    n = int(length * SR)
    tt = t_(n)
    ramp = (tt / length) ** 2.5
    noise = filt(rng.uniform(-1, 1, n), lo, hi) * ramp
    f = 180 * (8 ** (tt / length))
    sweep = np.sin(2 * np.pi * np.cumsum(f) / SR) * ramp * 0.25
    return noise + sweep


def whoosh(length):
    n = int(length * SR)
    tt = t_(n)
    shape = np.sin(np.pi * np.clip(tt / length, 0, 1)) ** 2 * (tt / length)
    return filt(rng.uniform(-1, 1, n), 600, 7000) * shape


# ---------------------------------------------------------------- UI sounds
def ui_click():
    n = int(0.06 * SR)
    tt = t_(n)
    burst = filt(rng.uniform(-1, 1, n), 2500, 11000) * np.exp(-tt / 0.0015)
    blip = np.sin(2 * np.pi * 1750 * tt) * np.exp(-tt / 0.011)
    body = np.sin(2 * np.pi * 380 * tt) * np.exp(-tt / 0.018)
    return burst * 1.0 + blip * 0.55 + body * 0.45


def ui_tick():
    n = int(0.03 * SR)
    tt = t_(n)
    return (np.sin(2 * np.pi * 3300 * tt) * np.exp(-tt / 0.005)
            + filt(rng.uniform(-1, 1, n), 4000, 14000) * np.exp(-tt / 0.001))


# ---------------------------------------------------------------- harmony
# One chord per bar (MIDI voicings), bass root per bar.
CHORDS = [tuple(c) for c in M["chords"]]
BASS = M["bass"]
BAR = 4 * B
DROP, END = M["drop"], M["end"]
BREAKS = M.get("breaks", [])


def in_break(b):
    return any(lo <= b < hi for lo, hi in BREAKS)


def pad_bar(notes, length, cutoff, bright=1.0):
    n = int((length + 0.35) * SR)
    tt = t_(n)
    env = np.clip(tt / 0.06, 0, 1) * np.clip((length + 0.35 - tt) / 0.35, 0, 1)
    l = np.zeros(n)
    r = np.zeros(n)
    for m in notes:
        for det, side in ((-0.09, 0), (0.0, 1), (0.09, 2)):
            v = saw(mtof(m + det), n, maxf=min(7000, cutoff * 2.5))
            if side == 0:
                l += v
            elif side == 2:
                r += v
            else:
                l += v * 0.7
                r += v * 0.7
    l, r = filt(l, 120, cutoff), filt(r, 120, cutoff)
    return l * env * bright, r * env * bright


def pluck(m, n):
    tt = t_(n)
    return square(mtof(m), n) * np.exp(-tt / 0.065)


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

# reverb: decorrelated exponential-noise impulse response, FFT convolution
irn = int(1.7 * SR)
irt = t_(irn)
irs = []
for _ in range(2):
    ir = filt(rng.uniform(-1, 1, irn), 200, 7000) * np.exp(-irt / 0.42)
    ir[: int(0.012 * SR)] = 0
    irs.append(ir / np.sqrt(np.sum(ir ** 2)))
size = len(L) + irn
nfft = 1 << (size - 1).bit_length()
wetL = np.fft.irfft(np.fft.rfft(sendL, nfft) * np.fft.rfft(irs[0], nfft), nfft)[: len(L)]
wetR = np.fft.irfft(np.fft.rfft(sendR, nfft) * np.fft.rfft(irs[1], nfft), nfft)[: len(L)]
L += wetL * 0.9
R += wetR * 0.9

# master: trim, high-pass rumble, glue, limit, fade
mix = np.stack([L[:N], R[:N]])
mix = np.stack([filt(ch, 28, None) for ch in mix])
mix /= np.max(np.abs(mix)) + 1e-9
mix = np.tanh(mix * 1.6) / np.tanh(1.6)
mix *= 0.93 / np.max(np.abs(mix))
fade = np.ones(N)
fade[: int(0.01 * SR)] = np.linspace(0, 1, int(0.01 * SR))
fade[-int(0.35 * SR):] = np.linspace(1, 0, int(0.35 * SR)) ** 2
mix *= fade

pcm = (mix.T * 32767).astype(np.int16)
with wave.open(str(DIR / "music.wav"), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("wrote", DIR / "music.wav", f"{N / SR:.2f}s")
