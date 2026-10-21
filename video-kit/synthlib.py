"""Instruments, effects and mixer for the video-kit soundtracks (numpy only).

Import from a track script:

    from synthlib import *
    mix = Mix(n_samples)
    mix.add(kick(), at_seconds, gain=0.5)
    mix.finish(path_to_wav)

All noise comes from one seeded generator, so a track renders identically every time
as long as it calls the instruments in the same order.
"""
import wave

import numpy as np

SR = 44100
rng = np.random.default_rng(7)


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


class Mix:
    """Stereo bus with a reverb send, glue limiter and fade-out."""

    def __init__(self, n):
        self.n = n
        self.L = np.zeros(n + SR * 3)
        self.R = np.zeros(n + SR * 3)
        self.sendL = np.zeros_like(self.L)
        self.sendR = np.zeros_like(self.R)

    def add(self, sig, at, gain=1.0, pan=0.0, send=0.0):
        """Mix a mono signal in at time `at` (seconds), equal-power pan."""
        L, R = self.L, self.R
        i = int(round(at * SR))
        if i >= len(L):
            return
        sig = sig[: len(L) - i]
        a = (pan + 1) * np.pi / 4
        gl, gr = np.cos(a) * gain, np.sin(a) * gain
        L[i : i + len(sig)] += sig * gl
        R[i : i + len(sig)] += sig * gr
        if send:
            self.sendL[i : i + len(sig)] += sig * gl * send
            self.sendR[i : i + len(sig)] += sig * gr * send

    def finish(self, path):
        L, R, sendL, sendR, N = self.L, self.R, self.sendL, self.sendR, self.n
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
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        print("wrote", path, f"{N / SR:.2f}s")
