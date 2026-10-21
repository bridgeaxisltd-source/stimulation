"""Synthesizes the 15s soundtrack (120 BPM) with every hit locked to the visual cues in reel.js."""
import math
import sys
import wave

import numpy as np

SR, DUR = 48000, 15.0
N = int(SR * DUR)
dry = np.zeros((2, N))
wet = np.zeros((2, N))   # sent through the reverb
rnd = np.random.default_rng(7)


def env_t(d):
    return np.arange(int(d * SR)) / SR


def add(sig, t0, gain=1.0, pan=0.0, bus=dry):
    i = int(t0 * SR)
    if i >= N or i + len(sig) <= 0:
        return
    if i < 0:
        sig, i = sig[-i:], 0
    n = min(len(sig), N - i)
    a = (pan + 1) * math.pi / 4
    bus[0, i:i + n] += sig[:n] * gain * math.cos(a) * 1.414
    bus[1, i:i + n] += sig[:n] * gain * math.sin(a) * 1.414


def onepole(x, k):
    """Low-pass; k may be a scalar or per-sample array of coefficients (0..1)."""
    y = np.empty_like(x)
    acc = 0.0
    kk = np.broadcast_to(k, x.shape)
    for i in range(len(x)):
        acc += kk[i] * (x[i] - acc)
        y[i] = acc
    return y


def kick():
    t = env_t(0.45)
    f = 45 + 115 * np.exp(-t * 32)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) + rnd.standard_normal(len(t)) * np.exp(-t * 300) * 0.25


def hat(d=0.07):
    t = env_t(d)
    n = rnd.standard_normal(len(t) + 1)
    return np.diff(n) * np.exp(-t * 70) * 0.5


def clap():
    t = env_t(0.3)
    n = rnd.standard_normal(len(t))
    n = n - onepole(n, 0.25)
    e = np.maximum.reduce([np.exp(-np.maximum(t - o, 0) * 90) * (t >= o) for o in (0, 0.012, 0.024)]) + 0.5 * np.exp(-t * 16)
    return n * e * 0.5


def boom(d=1.8, f0=85, f1=38):
    t = env_t(d)
    f = f1 + (f0 - f1) * np.exp(-t * 6)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.4)
    n = onepole(rnd.standard_normal(len(t)), 0.08) * np.exp(-t * 5) * 0.8
    return s + n


def whoosh(d, rising=True):
    t = env_t(d)
    x = t / d
    shape = x ** 2 if rising else (1 - x) ** 1.5 * np.minimum(1, x * 20)
    k = 0.02 + 0.35 * (x if rising else 1 - x)
    return onepole(rnd.standard_normal(len(t)), k) * shape * 1.2


def riser(d):
    t = env_t(d)
    x = t / d
    f = 180 * (7 ** x)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25 + np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR) * 0.12
    noise = onepole(rnd.standard_normal(len(t)), 0.03 + 0.4 * x) * 0.9
    return (tone + noise) * x ** 2.2


def bell(f, d=1.6):
    t = env_t(d)
    s = sum(a * np.sin(2 * np.pi * f * m * t) * np.exp(-t * dec) for m, a, dec in ((1, 1, 3), (2.76, 0.35, 6), (5.4, 0.12, 10)))
    return s * np.minimum(1, t * 400)


def blip(f, d=0.12):
    t = env_t(d)
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 35) * np.minimum(1, t * 800)


def tick():
    t = env_t(0.018)
    n = np.diff(rnd.standard_normal(len(t) + 1))
    return (n * 0.6 + np.sin(2 * np.pi * 2600 * t) * 0.4) * np.exp(-t * 260)


def pad_note(f, d):
    t = env_t(d)
    s = np.zeros(len(t))
    for det in (-0.004, 0, 0.005):
        for k in range(1, 7):
            s += np.sin(2 * np.pi * f * (1 + det) * k * t + k) / k ** 1.4
    a = np.minimum(1, t / 0.5) * np.minimum(1, (d - t) / 0.6)
    return s * a * 0.08


def hz(note):
    names = {'C': -9, 'D': -7, 'E': -5, 'F': -4, 'G': -2, 'A': 0, 'B': 2}
    return 440 * 2 ** ((names[note[0]] + 12 * (int(note[1]) - 4)) / 12)


# --- pad -------------------------------------------------------------------
CHORDS = [(0, 4.2, 'F3 A3 C4 E4'), (4.0, 2.7, 'A2 E3 G3 C4'), (6.5, 2.2, 'F3 A3 C4 E4'), (8.5, 1.7, 'C3 G3 B3 E4'),
          (10.0, 2.7, 'G2 D3 B3 E4'), (12.5, 2.5, 'F2 C3 A3 E4 G4')]
pad = np.zeros((2, N))
for t0, d, notes in CHORDS:
    for j, n in enumerate(notes.split()):
        add(pad_note(hz(n), d), t0, 1.0, (-0.5 + j / max(1, len(notes.split()) - 1)), bus=pad)

# --- drums -----------------------------------------------------------------
duck = np.ones(N)
kicks = [2.0 + 0.5 * i for i in range(21) if not (4.0 < 2.0 + 0.5 * i < 6.0 and (i % 2))]
for k in kicks:
    add(kick(), k, 0.9)
    i = int(k * SR)
    seg = np.arange(N - i) / SR
    duck[i:] = np.minimum(duck[i:], 1 - 0.6 * np.exp(-seg * 7))
for b in np.arange(4.25, 12.3, 0.5):
    add(hat(), b, 0.35, 0.3)
for b in np.arange(6.5, 12.3, 0.25):
    add(hat(0.03), b, 0.15, -0.3)
for b in np.arange(7.0, 12.1, 1.0):
    add(clap(), b, 0.5)
    add(clap(), b, 0.25, bus=wet)
for k in [6.5 + 0.5 * i for i in range(12)]:   # bass plucks on the off-beats of the build
    t = env_t(0.22)
    root = {6.5: 'F2', 8.5: 'C2', 10.0: 'G2'}
    r = hz(root[max(x for x in root if x <= k)]) / 2
    add((np.sin(2 * np.pi * r * t) + 0.3 * np.sin(4 * np.pi * r * t)) * np.exp(-t * 12), k + 0.25, 0.55)

# --- cue design ------------------------------------------------------------
add(riser(2.0), 0.0, 0.55)
for t0, g in ((2.0, 1.0), (6.0, 0.55), (12.55, 1.1)):
    add(boom(), t0, g)
    add(boom(), t0, g * 0.4, bus=wet)
add(boom(1.2, 70, 45), 13.27, 0.6)
for t0, d, up, g in ((3.6, 0.45, True, 0.6), (6.0, 0.55, True, 0.4), (7.0, 1.0, False, 0.5), (9.2, 0.8, True, 0.45), (12.05, 0.5, True, 0.7), (12.45, 0.7, False, 0.35)):
    add(whoosh(d, up), t0, g, -0.2 if up else 0.2)
PENTA = [hz(n) for n in 'C6 D6 E6 G6 A6 C7 D7 E7 G7'.split()]
for i, f in enumerate(PENTA):        # one chime per wordmark letter
    add(bell(f, 1.2), 2.05 + i * 0.045, 0.06, -0.6 + i * 0.15, bus=wet)
for f in (hz('F5'), hz('A5'), hz('C6'), hz('E6')):
    add(bell(f, 2.5), 2.0, 0.08, bus=wet)
PROMPT = 'Pricing page for a Mars travel startup'
for i in range(len(PROMPT)):        # same schedule as charTime() in reel.js
    add(tick(), 4.45 + 1.3 * (i + 0.3 * math.sin(i * 2.7)) / len(PROMPT), 0.22 + 0.08 * rnd.random(), 0.2 * rnd.standard_normal())
add(blip(1800, 0.06), 5.95, 0.4)
for j, off in enumerate((0.05, 0.1, 0.15, 0.25, 0.38, 0.5, 0.66, 0.82)):
    add(blip(PENTA[j], 0.15), 6.55 + off, 0.12, -0.3 + 0.08 * j, bus=wet)
for t0, p in ((7.3, -0.7), (7.48, 0.7)):
    add(bell(hz('G5'), 1.0), t0, 0.08, p, bus=wet)
add(bell(hz('C6'), 1.0), 8.62, 0.1, bus=wet)
add(blip(2400, 0.05), 9.12, 0.45)
add(blip(1200, 0.08), 9.14, 0.25)
for k in np.arange(10.65, 12.0, 0.045):
    add(tick(), k, 0.12, 0.4)
add(bell(hz('E6'), 1.2), 12.0, 0.1, 0.4, bus=wet)
add(bell(hz('B6'), 1.2), 12.07, 0.07, 0.4, bus=wet)
for f in (hz('F5'), hz('C6'), hz('E6'), hz('G6'), hz('A6')):   # logo lockup chord
    add(bell(f, 3.0), 13.27, 0.09, bus=wet)
for i, f in enumerate((hz('C6'), hz('E6'), hz('G6'))):
    add(bell(f, 1.0), 14.0 + i * 0.11, 0.05, -0.4 + 0.4 * i, bus=wet)
add(whoosh(0.7, True)[::-1] * 0.5, 14.2, 0.3)

# --- mix -------------------------------------------------------------------
pad *= duck
wet += pad * 0.6
ir_t = env_t(1.8)
mix = dry + pad
for ch in range(2):
    ir = rnd.standard_normal(len(ir_t)) * np.exp(-ir_t * 3.2)
    ir[: int(0.015 * SR)] = 0
    size = 1 << int(np.ceil(np.log2(N + len(ir))))
    rev = np.fft.irfft(np.fft.rfft(wet[ch], size) * np.fft.rfft(ir, size), size)[:N]
    mix[ch] += wet[ch] + rev / np.max(np.abs(rev) + 1e-9) * np.max(np.abs(wet[ch])) * 0.9
mix = np.tanh(mix * 1.3)
mix *= 0.89 / np.max(np.abs(mix))
fade = int(0.4 * SR)
mix[:, -fade:] *= np.linspace(1, 0, fade)

out = sys.argv[1] if len(sys.argv) > 1 else 'out/reel_audio.wav'
with wave.open(out, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix.T * 32767).astype(np.int16).tobytes())
print('wrote', out)
