#!/usr/bin/env python3
"""BIFURKATION v5 (Referenz: PINKY SMASH) - Math-Hardstyle-Phonk. Diesmal: Hook zuerst, Mathe erzeugt den Hook.

Die logistische Abbildung x -> r*x*(1-x) liefert fuer jedes r einen Orbit (Periode 2, 4, 8, 3 ...).
Dieser Orbit wird ein FESTER Cowbell-Hook, der sich wiederholt; er wechselt nur, wenn die Periode wechselt.
Chaos (r=3.99) zerstoert nicht den Groove, sondern steuert Stutter und Screech-Fills.
Kein Zufallsgenerator: alles Rauschen ist deterministisches Chaos.
"""
import os
import sys

import numpy as np
import scipy.io.wavfile as wf
import scipy.ndimage as nd
import scipy.signal as ss

# ================== phonktion Parameter (env MATHPHONK_PARAMS, JSON) ==================
import json as _json
P = _json.loads(os.environ.get("MATHPHONK_PARAMS", "{}"))
INT = max(1.0, min(10.0, float(P.get("intensity", 6))))  # 1 sanft ... 6 Standard ... 10 brutal
TRANSPOSE = int(P.get("transpose", 0))  # Halbtoene relativ zur Original-Tonart des Templates
SEED = int(P.get("seed", 0))  # Variation der Mathe-Startwerte (0 = Original)
KDRIVE = 0.55 + 0.075 * INT  # Kick-Verzerrung
DUCK = 0.3 + 0.05 * INT  # Sidechain-Tiefe (6 -> 0.6)
LIM = 1.6 - 0.1 * INT  # Limiter-Schwelle relativ (kleiner = platter)
CLIPD = 0.4 + 0.1 * INT  # Endsaettigung relativ
CRUSH_AMT = float(P.get("crush", max(0.0, (INT - 6) / 4)))  # 0..1 Zusatz-Bitcrush auf der Musikspur
NAME = P.get("name")

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
SR = 44100
BPM = float(P.get('bpm', 144))
BEAT = 60 / BPM
BAR = 4 * BEAT
S16 = BEAT / 4
NBARS = 76
TOTAL = NBARS * BAR + 3.5
N = int(TOTAL * SR)
PHI = (1 + 5 ** 0.5) / 2

DR = np.zeros((2, N))
MU = np.zeros((2, N))
SEND = np.zeros((2, N))
KICK_TIMES = []

SCALE = [0, 1, 3, 5, 7, 8, 10]  # D# phrygisch
ROOT = 39  # D#2


def hz(m):
    return 440.0 * 2 ** ((m + TRANSPOSE - 69) / 12)


def deg(i, base=ROOT):
    o, d = divmod(int(i), 7)
    return base + 12 * o + SCALE[d]


def tt(dur):
    return np.arange(int(dur * SR)) / SR


def bar(b):
    return b * BAR


def filt(x, kind, f, order=2):
    return ss.sosfilt(ss.butter(order, f, kind, fs=SR, output="sos"), x)


def lorenz_pan():
    rate, dt = 200, 0.004
    steps = int(TOTAL * rate) + 2
    x, y, z = 1.0, 1.0, 1.0
    out = np.empty(steps)
    for i in range(steps):
        x, y, z = x + 10 * (y - x) * dt, y + (x * (28 - z) - y) * dt, z + (x * y - 8 / 3 * z) * dt
        out[i] = x
    return np.interp(np.arange(N) / SR, np.arange(steps) / rate, np.clip(out / 20, -1, 1))


PAN = lorenz_pan()


def add(sig, t0, bus=MU, pan=0.0, gain=1.0, lorenz=0.0, send=0.0):
    i = int(t0 * SR)
    if i >= N or i < 0:
        return
    s = sig[: N - i] * gain
    a = (np.clip(pan + lorenz * PAN[i : i + len(s)], -1, 1) + 1) * np.pi / 4
    l, r = s * np.cos(a), s * np.sin(a)
    bus[0, i : i + len(s)] += l
    bus[1, i : i + len(s)] += r
    if send:
        SEND[0, i : i + len(s)] += l * send
        SEND[1, i : i + len(s)] += r * send


def logistic_noise(n, r=3.99999, x=0.1234567):
    out = np.empty(n)
    for i in range(n):
        x = r * x * (1 - x)
        if x <= 0 or x >= 1:
            x = 0.3141592
        out[i] = x
    return 2 * out - 1


NOISE = logistic_noise(SR * 3)


def noise(n, k):
    off = int(((k * PHI) % 1) * (len(NOISE) - n))
    return NOISE[off : off + n].copy()


def golden_vel(k):
    return 0.7 + 0.3 * ((k * PHI) % 1)


def euclid(k, n=16, rot=0):
    return np.roll([(i * k) % n < k for i in range(n)], rot)


def collatz(n):
    n = int(n) + 2 * SEED
    s = [n]
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        s.append(n)
    return s


# ---------- Hook aus dem Orbit ----------
PREF = [0, 4, 1, 5, 7, 2, 8, 3]  # Grundton, Quinte, b2, b6, Oktave, ... (phrygisch-dunkel zuerst)


def orbit_hook(r):
    """Stabiler Orbit der logistischen Abbildung -> Tonfolge. Hoehere x = hoehere Toene."""
    x = 0.5
    for _ in range(4000):
        x = r * x * (1 - x)
    orb = []
    for _ in range(64):
        x = r * x * (1 - x)
        orb.append(round(x, 6))
    p = next(k for k in range(1, 33) if all(abs(orb[i] - orb[i + k]) < 1e-4 for i in range(16)))
    vals = orb[:p]
    degs = sorted(PREF[:p])
    rank = {v: degs[i] for i, v in enumerate(sorted(vals))}
    return [rank[v] for v in vals], p


HOOK_RHYTHM = [0, 3, 6, 9, 12, 14]  # 3-3-3-3-2-2: klassische Phonk-Cowbell


# ---------- Instrumente ----------
def kick(drive=6.0, dur=0.4):
    """Zweistufiger Sweep (Klick -> Punch -> Sub), Punch-Layer bei ~180 Hz, Hard-Clip."""
    t = tt(dur)
    f1 = hz(27)
    f = f1 + (600 - f1) * np.exp(-t / 0.012) + 110 * np.exp(-t / 0.07)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * (0.35 + 0.65 * np.exp(-t / 0.28))
    punch = np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.025)
    x = np.clip((body + 0.5 * punch) * drive * 0.6, -1, 1)
    x = 0.8 * x + 0.2 * np.tanh(drive * body)
    x = filt(x, "lowpass", 6000)
    n = int(0.004 * SR)
    x[:n] += 0.7 * filt(noise(n, 5), "highpass", 3000) * np.linspace(1, 0, n)
    return x * np.minimum(1, (dur - t) / 0.012)


def put_kick(t0, drive=6.0, gain=1.0):
    KICK_TIMES.append(t0)
    add(kick(drive * KDRIVE), t0, DR, gain=gain)


def clap(k):
    t = tt(0.35)
    n = filt(noise(len(t), k), "bandpass", [900, 6000])
    env = sum(np.exp(-np.maximum(t - 0.011 * i, 0) / 0.005) * (t >= 0.011 * i) for i in range(3))
    env += 0.7 * np.exp(-np.maximum(t - 0.033, 0) / 0.11) * (t >= 0.033)
    fb = 200 * (1 + 0.5 * np.exp(-t / 0.01))
    body = np.sin(2 * np.pi * np.cumsum(fb) / SR) * np.exp(-t / 0.04)
    return np.tanh(2.0 * (n * env + 0.5 * body))


def hat(k, open_=False):
    t = tt(0.3 if open_ else 0.05)
    return filt(noise(len(t), k), "highpass", 8000) * np.exp(-t / (0.08 if open_ else 0.014))


def cowbell(f, dur=0.32):
    t = tt(dur)
    x = np.sign(np.sin(2 * np.pi * f * t)) + 0.8 * np.sign(np.sin(2 * np.pi * f * 1.4836 * t))
    x = filt(x, "bandpass", [f * 0.85, min(f * 4.5, 15000)])
    env = np.exp(-t / 0.06) + 0.25 * np.exp(-t / 0.2)
    x = np.tanh(2.2 * x * env)  # Phonk-Cowbell: angezerrt
    return 0.4 * filt(x, "lowpass", 7000)


BEAM = [1.0, 2.756, 5.404, 8.933]  # Euler-Bernoulli-Balken


def beam_bell(f, dur=1.4):
    t = tt(dur)
    x = np.zeros_like(t)
    for i, r in enumerate(BEAM):
        if f * r < SR / 2.2:
            x += np.sin(2 * np.pi * f * r * t) * np.exp(-t * (2.5 + 7 * i)) / (i + 1)
    return x * np.minimum(1, t / 0.002)


def bass808(f, prev, dur, drive=3.0):
    t = tt(dur + 0.04)
    fc = f + (prev - f) * np.exp(-t / 0.05)
    fc = fc * (1 + 0.7 * np.exp(-t / 0.01))
    ph = 2 * np.pi * np.cumsum(fc) / SR
    x = np.sin(ph) + 0.2 * np.sin(2 * ph)
    env = np.clip((dur + 0.04 - t) / 0.03, 0, 1) * (0.55 + 0.45 * np.exp(-t / 0.25))
    return np.tanh(drive * x * env) / np.tanh(drive)


def reverse_bass(f, dur):
    t = tt(dur)
    x = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(4 * np.pi * f * t + 0.3)
    env = (t / dur) ** 1.5 * np.clip((dur - t) / 0.006, 0, 1)
    return filt(np.tanh(6 * x * env), "lowpass", 3000) * env ** 0.3


def screech(f, dur, idx_hi=6):
    """FM mit Verhaeltnis phi -> maximal unharmonisch, metallisch."""
    t = tt(dur)
    idx = 2 + idx_hi * (0.5 + 0.5 * np.sin(2 * np.pi * (BPM / 60) * 2 * t))
    x = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * 2 * t))
    x = filt(np.tanh(4 * x), "bandpass", [300, 6500])
    return x * np.minimum(1, t / 0.004) * np.clip((dur - t) / 0.02, 0, 1)


def gwave(f, dur):
    """Die TikTok-Formel als Wavetable."""
    t = tt(dur)
    x = 8 * ((f * t) % 1)
    a = 4 * np.floor(x / 4) + np.mod(x, 2)
    y = filt(np.sin(np.pi * a / 4) * np.cos(np.pi * a / 2), "lowpass", 4000)
    return y * np.minimum(1, t / 0.03) * np.clip((dur - t) / 0.15, 0, 1)


def weierstrass(f, dur, a=0.55, b=3, terms=5):
    t = tt(dur)
    return sum(a ** k * np.cos(b ** k * 2 * np.pi * f * t) for k in range(terms)) / 2


def fourier_riser(f, dur, kmax=63):
    t = tt(dur)
    nt = 1 + (kmax - 1) * (t / dur) ** 2
    y = sum(np.clip((nt - k) / 2, 0, 1) * np.sin(2 * np.pi * k * f * t) / k for k in range(1, kmax + 1, 2))
    rate = 2 + 14 * (t / dur) ** 2
    return y * (0.6 + 0.4 * np.sign(np.sin(2 * np.pi * np.cumsum(rate) / SR))) * (0.3 + 0.7 * t / dur)


def echo(x, d=3 * S16, fb=0.4, taps=5):
    out = np.zeros(len(x) + int(d * SR * taps))
    for k in range(taps + 1):
        i = int(k * d * SR)
        out[i : i + len(x)] += x * fb ** k
    return out



# ================== v3: Bausteine im PINKY-SMASH-Stil ==================
PI = "3141592653589793238462643383279502884197169399375105820974944592"
PI = PI[SEED % 32:] + PI[: SEED % 32]
MUTES = []  # (t0, t1) Stopps auf allen Spuren


def lead(f, dur=S16 * 1.7):
    """Drift-Phonk-Lead: Rechteck + Oktav-Rechteck + Saege, nur harmonische Obertoene, hart angezerrt, dunkel."""
    t = tt(dur)
    x = np.sign(np.sin(2 * np.pi * f * t)) + 0.5 * np.sign(np.sin(2 * np.pi * 2 * f * t)) \
        + 0.5 * ss.sawtooth(2 * np.pi * f * t + 0.5)
    env = np.exp(-t / 0.075) * np.minimum(1, t / 0.001) * np.clip((dur - t) / 0.01, 0, 1)
    x = np.tanh(3.0 * filt(x, "bandpass", [f * 0.7, 7000]) * env)
    return filt(x, "lowpass", 5200) * env ** 0.2


def impact(k):
    t = tt(2.6)
    f = hz(27) + 90 * np.exp(-t / 0.08)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.9)
    n = filt(noise(len(t), k), "lowpass", 3000) * np.exp(-t / 0.35)
    return np.tanh(2.5 * (sub + 0.5 * n))


def sub_bass(b0, nbars, seed):
    """Durchgehender, verzerrter Sub auf dem Grundton. Collatz: ungerader Schritt (3n+1) = Glide hoch."""
    col = collatz(seed)
    jump = [7, 5, 1, 4, 7]
    dur = nbars * BAR
    n = int(dur * SR)
    f = np.full(n, hz(deg(0, ROOT - 12)))
    for b in range(nbars):
        c = col[b % len(col)]
        if c % 2 == 1:  # letzte zwei Achtel des Takts gleiten auf den Sprungton
            i0 = int((b * BAR + 3 * BEAT) * SR)
            i1 = min(int((b + 1) * BAR * SR), n)
            tgt = hz(deg(jump[c % 5], ROOT - 12))
            ramp = np.minimum(1, np.arange(i1 - i0) / (0.06 * SR))
            f[i0:i1] = f[i0] + (tgt - f[i0]) * ramp
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.15 * np.sin(2 * ph)
    x = np.tanh(4.5 * x) / np.tanh(4.5)
    x = filt(x, "lowpass", 900)
    x *= np.minimum(1, np.arange(n) / (0.01 * SR)) * np.clip((n - np.arange(n)) / (0.02 * SR), 0, 1)
    add(x, bar(b0), MU, gain=0.36)


def wall(b0, nbars):
    """Mitten-Wand (330-550 Hz) wie in der Referenz: Saegezahn-Quinte, verzerrt, gesidechaint."""
    dur = nbars * BAR
    t = tt(dur)
    y = np.zeros_like(t)
    for m in (deg(0, ROOT + 24), deg(4, ROOT + 12)):
        for det in (-0.12, 0.12):
            y += ss.sawtooth(2 * np.pi * hz(m + det) * t)
    y = filt(np.tanh(1.5 * y), "bandpass", [250, 1400])
    y *= np.minimum(1, t / 0.02) * np.clip((dur - t) / 0.05, 0, 1)
    add(y, bar(b0), MU, gain=0.07, lorenz=0.25)


def run16(b0, nbars, r, gain=0.62, cutoff=None, chaos=False):
    """16tel-Linie: gerade 16tel = Orbit-Ton (oben), ungerade = Grundton-Anker (unten).
    Letztes Viertel jedes 2. Takts: Lauf durch den Orbit ohne Anker."""
    notes, p = orbit_hook(r)
    k = 0
    xc = 0.37
    for b in range(b0, b0 + nbars):
        for s in range(16):
            run = (b - b0) % 2 == 1 and s >= 12
            if s % 2 == 0 or run:
                d = notes[k % p] + 7
                k += 1
            else:
                d = 0
            if chaos:
                xc = 3.99 * xc * (1 - xc)
                if xc > 0.93:
                    d = int(xc * 70) % 12  # chaotischer Ausreisser
            sig = lead(hz(deg(d, ROOT + 24)))
            if cutoff is not None:
                u = (b - b0 + s / 16) / nbars
                sig = filt(sig, "lowpass", cutoff[0] * (cutoff[1] / cutoff[0]) ** u)
            vel = 1.0 if s % 4 == 0 else 0.8
            add(sig, bar(b) + s * S16, MU, gain=gain * vel * golden_vel(b * 16 + s), lorenz=0.25, send=0.25)


def drums(b0, nbars, drive=8.0, hats_on=True, stutter=False):
    x = 0.61
    for b in range(b0, b0 + nbars):
        for j in range(4):
            put_kick(bar(b) + j * BEAT, drive=drive)
        for j in (1, 3):
            add(clap(b * 4 + j), bar(b) + j * BEAT, DR, gain=0.55, send=0.1)
        if hats_on:
            for s in (2, 6, 10, 14):
                add(hat(b * 16 + s, True), bar(b) + s * S16, DR, gain=0.12)
        if stutter:
            for s in range(16):
                x = 3.99 * x * (1 - x)
                if x > 0.975 and s % 4 != 0:
                    for z in range(3):
                        put_kick(bar(b) + s * S16 + z * S16 / 3, drive=drive, gain=0.5)


def stop(b, beats=1):
    """Ein Beat Stille vor dem naechsten Abschnitt."""
    MUTES.append((bar(b + 1) - beats * BEAT, bar(b + 1)))


def zeno(t_end, span, k0=500, gain=0.55):
    q, n = 0.9, 0
    while span * q ** n > 0.004:
        add(clap(k0 + n), t_end - span * q ** n, DR, gain=gain * (0.3 + 0.7 * min(n, 50) / 50), send=0.15)
        n += 1
    return n



# ================== v4: gegen Langeweile ==================
POST = []  # Effekte auf dem fertigen Mix: ("cantor"|"ratchet"|"tapestop", t0, dauer)


def run16(b0, nbars, r, gain=0.62, cutoff=None, chaos=False, octave=False, mirror=True):
    """16tel-Linie. Phrasen à 4 Takte: Takt 4 spielt die GESPIEGELTE Kontur
    (logistische Abbildung ist symmetrisch: f(x) = f(1-x) -> x und 1-x sind Zwillinge)."""
    notes, p = orbit_hook(r)
    hi, lo = max(notes), min(notes)
    k = 0
    xc = 0.37
    for b in range(b0, b0 + nbars):
        resp = mirror and (b - b0) % 4 == 3
        for s in range(16):
            run = (b - b0) % 2 == 1 and s >= 12
            if s % 2 == 0 or run:
                n = notes[k % p]
                d = (hi + lo - n if resp else n) + 7
                k += 1
            else:
                d = 0
            if chaos:
                xc = 3.99 * xc * (1 - xc)
                if xc > 0.93:
                    d = int(xc * 70) % 12
            sig = lead(hz(deg(d, ROOT + 24)))
            if cutoff is not None:
                u = (b - b0 + s / 16) / nbars
                sig = filt(sig, "lowpass", cutoff[0] * (cutoff[1] / cutoff[0]) ** u)
            vel = (1.0 if s % 4 == 0 else 0.8) * golden_vel(b * 16 + s)
            t0 = bar(b) + s * S16
            add(sig, t0, MU, gain=gain * vel, lorenz=0.25, send=0.25)
            if octave and s % 2 == 0:
                add(lead(hz(deg(d + 7, ROOT + 24))), t0, MU, gain=gain * 0.35 * vel, pan=0.0, lorenz=-0.6, send=0.2)


def bell(f, dur=1.6):
    """Harmonische Glocke (nur ganzzahlige Obertoene -> bleibt in der Tonart)."""
    t = tt(dur)
    x = sum(np.sin(2 * np.pi * f * h * t) * np.exp(-t * (1.5 + 2.5 * h)) / h for h in (1, 2, 3, 4, 6))
    return np.tanh(1.5 * x) * np.minimum(1, t / 0.003)


def counter(b0, nbars, r=3.55, gain=0.3):
    """Hohe Gegenmelodie: ganze Orbit-Periode in halben Noten, eine Oktave ueber dem Lead."""
    notes, p = orbit_hook(r)
    for i in range(nbars * 2):
        add(bell(hz(deg(sorted(notes)[::-1][i % p] + 7, ROOT + 36)), 2 * BEAT + 0.6), bar(b0) + i * 2 * BEAT,
            MU, gain=gain, lorenz=0.9, send=0.5)


def fill(b, k0=0):
    """Snare-Fill im letzten Beat: 16tel -> 32tel, Tonhoehe steigt."""
    for i in range(4):
        add(clap(k0 + i), bar(b) + 3 * BEAT + i * S16, DR, gain=0.35 + 0.08 * i)
    for i in range(4):
        add(snare_hi(k0 + 10 + i, 1 + 0.15 * i), bar(b) + 3 * BEAT + 2 * S16 + i * S16 / 2, DR, gain=0.4)


def snare_hi(k, pitch):
    t = tt(0.12)
    n = filt(noise(len(t), k), "bandpass", [1500, 7000]) * np.exp(-t / 0.04)
    body = np.sin(2 * np.pi * 240 * pitch * t) * np.exp(-t / 0.03)
    return np.tanh(2 * (n + 0.6 * body))


def swell(t_end, dur=BAR, k=0, gain=0.22):
    """Reverse-Swell: Chaos-Rauschen, exponentiell anschwellend, endet genau auf dem Abschnittsanfang."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = filt(noise((n + 1) // 2, k).repeat(2)[:n], "bandpass", [600, 9000]) * np.exp((t - dur) / (dur / 5))
    add(x, t_end - dur, DR, gain=gain, lorenz=0.5)


def downlift(t0, dur=2 * BEAT, k=0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 2500 * np.exp(-t / (dur / 3)) + 80
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (dur / 2)) * 0.5
    x += filt(noise(n, k), "highpass", 3000) * np.exp(-t / (dur / 3)) * 0.4
    add(x, t0, MU, gain=0.25, send=0.4)


def halftime(b0, nbars):
    """Trap-Phonk-Halftime: Kick 1 + 'und von 2', Clap auf 3, Hat-Triolen."""
    for b in range(b0, b0 + nbars):
        put_kick(bar(b), drive=11)
        put_kick(bar(b) + 1.5 * BEAT, drive=11, gain=0.8)
        if b % 2:
            put_kick(bar(b) + 3.5 * BEAT, drive=11, gain=0.7)
        add(clap(b * 7), bar(b) + 2 * BEAT, DR, gain=0.7, send=0.2)
        for i in range(12):
            add(hat(b * 12 + i), bar(b) + i * BEAT / 3, DR, gain=0.12 * golden_vel(i), lorenz=0.6)


def sub_bounce(b0, nbars, seed):
    col = collatz(seed)
    ci = 0
    for b in range(b0, b0 + nbars):
        for j in range(4):
            n = col[ci % len(col)]
            ci += 1
            d = 0 if n % 2 == 0 else [7, 4, 1, 5][n % 4]
            add(reverse_bass(hz(deg(d, ROOT - 12)), BEAT / 2), bar(b) + j * BEAT + BEAT / 2, MU, gain=0.5)


# ================== ARRANGEMENT (62 Takte @144) ==================
# Intro 0-8: Einschlaege, Lead gefiltert, Zeno-Roll
for i, b in enumerate((0, 2, 4)):
    add(impact(i), bar(b), MU, gain=0.75, send=0.6)
    put_kick(bar(b), drive=12, gain=0.9)
    add(echo(bell(hz(deg(int(PI[i * 2]) % 7 + 7, ROOT + 24)), 2.0), d=3 * S16, fb=0.45, taps=6),
        bar(b) + BEAT, MU, gain=0.22, lorenz=0.8, send=0.6)
run16(4, 4, 3.5, gain=0.25, cutoff=(350, 3500), mirror=False)
add(filt(weierstrass(hz(27), 8 * BAR), "lowpass", 500) * np.linspace(0, 1, int(8 * BAR * SR)), 0, MU, gain=0.18)
ZENO = zeno(bar(8), 2 * BAR)
swell(bar(8), 2 * BAR, k=1)
stop(7, 0.5)

# Drop 1 8-24: Phrasen A A A A', Fills, Oktav-Layer ab Takt 16, Cantor-Gate, Ratchet, Tape-Stop
drums(8, 16)
sub_bass(8, 16, 27)
wall(8, 16)
run16(8, 8, 3.5)
run16(16, 8, 3.55, octave=True)
for b in (11, 15, 19):
    fill(b, k0=b * 10)
swell(bar(16), BAR, k=2)
add(impact(3), bar(16), MU, gain=0.4, send=0.4)
POST.append(("cantor", bar(19), BAR))
POST.append(("ratchet", bar(22) + 3 * BEAT, BEAT))
POST.append(("tapestop", bar(23) + 2 * BEAT, 2 * BEAT))

# Break 24-28: TikTok-Formel als Lead + Gegenmelodie-Vorschau
fib = [0, 1]
while len(fib) < 8:
    fib.append((fib[-1] + fib[-2]) % 7)
for i, d in enumerate(fib):
    add(echo(gwave(hz(deg(d, ROOT + 24)), 2 * BEAT), fb=0.35, taps=4), bar(24) + i * 2 * BEAT, MU,
        gain=0.18, lorenz=0.3, send=0.5)
counter(24, 4, gain=0.12)
add(filt(weierstrass(hz(27), 4 * BAR), "lowpass", 700) * np.minimum(1, tt(4 * BAR) / 1.0), bar(24), MU, gain=0.12)

# Build 28-30: r gleitet in Periode 3, Zeno-Roll, Swell
nr = int(2 * BAR * SR)
x = 0.5
for b in (28, 29):
    for s in range(16):
        r = 3.57 + 0.26 * ((b - 28) * 16 + s) / 32
        for _ in range(3):
            x = r * x * (1 - x)
        add(lead(hz(deg(int(x * 8) + 7 if s % 2 == 0 else 0, ROOT + 24))), bar(b) + s * S16, MU, gain=0.45, send=0.3)
zeno(bar(30), 2 * BAR, k0=700)
swell(bar(30), 2 * BAR, k=3)
add(filt(noise((nr + 2) // 3, 4).repeat(3)[:nr], "highpass", 2000) * np.linspace(0, 1, nr) ** 2, bar(28), DR, gain=0.12)
stop(29, 0.5)

# Drop 2a 30-34: BEAT-SWITCH Halftime, Reverse-Bass, Periode 3 + Screech
halftime(30, 4)
sub_bounce(30, 4, 97)
wall(30, 4)
run16(30, 4, 3.83, mirror=False)
notes3, p3 = orbit_hook(3.83)
for i in range(4 * 8):
    add(screech(hz(deg(notes3[i % p3], ROOT + 12)), BEAT / 2 * 0.9), bar(30) + i * BEAT / 2, MU, gain=0.13, send=0.1)
POST.append(("ratchet", bar(33) + 3 * BEAT, BEAT))
swell(bar(34), BAR, k=4)

# Drop 2b 34-50: 4/4 Hardstyle, Periode 3 mit Spiegel-Antworten, Gegenmelodie ab 42
add(impact(5), bar(34), MU, gain=0.5, send=0.4)
drums(34, 16, drive=11)
sub_bass(34, 16, 871)
wall(34, 16)
run16(34, 8, 3.83)
run16(42, 8, 3.55, octave=True)
counter(42, 8, gain=0.22)
for b in (37, 45, 49):
    fill(b, k0=b * 13)
POST.append(("cantor", bar(41), BAR))
swell(bar(42), BAR, k=5)
add(impact(6), bar(42), MU, gain=0.4, send=0.4)

# ---------- v5: Hook im Fibonacci-Rhythmus ----------
FIBWORD = "abaababaabaab"  # Fibonacci-Wort: a->ab, b->a
HOOK_LEN = [3 if c == "a" else 2 for c in FIBWORD[:6]]  # 3-2-3-3-2-3 = 16 Sechzehntel


def hook_lead(f, prev, dur):
    """Langer Lead: 4 verstimmte Saegezaehne, Glide vom Vorton, Filter-Envelope, angezerrt."""
    t = tt(dur + 0.08)
    fc = f + (prev - f) * np.exp(-t / 0.035)
    y = sum(ss.sawtooth(2 * np.pi * np.cumsum(fc * 2 ** (dt / 1200)) / SR) for dt in (-14, -5, 5, 14)) / 4
    y += 0.5 * np.sign(np.sin(2 * np.pi * np.cumsum(fc / 2) / SR))
    e = np.exp(-t / 0.12)  # Filter-Envelope als Ueberblendung hell -> dunkel
    out = filt(y, "lowpass", 900) * (1 - e) + filt(y, "lowpass", 5400) * e
    env = np.minimum(1, t / 0.005) * np.clip((dur + 0.08 - t) / 0.08, 0, 1)
    return np.tanh(2.2 * out * env)


def play_hook_lead(b0, nbars, gain=0.42, octave=ROOT + 36):
    seq, p = orbit_hook(3.5)  # [5, 0, 4, 1]
    hi, lo = max(seq), min(seq)
    call = [seq[0], seq[2], seq[0], seq[3], seq[2], seq[1]]
    answer = [hi + lo - n for n in call]  # Spiegelung f(x) = f(1-x)
    answer[-1] = 0  # Antwort landet auf dem Grundton
    prev = hz(deg(call[0], octave))
    for b in range(b0, b0 + nbars):
        notes = call if (b - b0) % 2 == 0 else answer
        pos = 0
        for d, ln in zip(notes, HOOK_LEN):
            f = hz(deg(d, octave))
            add(hook_lead(f, prev, ln * S16 * 0.95), bar(b) + pos * S16, MU, gain=gain, lorenz=0.15, send=0.35)
            prev = f
            pos += ln


# Break 2 50-54: der Hook allein, mit Hall + Weierstrass-Drone
add(filt(weierstrass(hz(27), 4 * BAR), "lowpass", 900) * np.minimum(1, tt(4 * BAR) / 0.5), bar(50), MU, gain=0.12)
play_hook_lead(50, 4, gain=0.35)
for b in (50, 52):
    add(impact(20 + b), bar(b), MU, gain=0.35, send=0.5)
POST.append(("tapestop", bar(49) + 2 * BEAT, 2 * BEAT))

# Build 54-56: Hook laeuft weiter, Zeno-Roll, Swell
play_hook_lead(54, 2, gain=0.4)
run16(54, 2, 3.5, gain=0.35, cutoff=(400, 4000), mirror=False)
zeno(bar(56), 2 * BAR, k0=900)
swell(bar(56), 2 * BAR, k=8)
stop(55, 0.5)

# Drop 3 56-72: FINALE. Hook oben + 16tel-Linie + alles; ab 64 Chaos, Stutter, Oktaven
add(impact(30), bar(56), MU, gain=0.55, send=0.5)
drums(56, 8, drive=12)
drums(64, 8, drive=12, stutter=True)
sub_bass(56, 16, 27)
wall(56, 16)
play_hook_lead(56, 16, gain=0.4)
run16(56, 8, 3.5, gain=0.5)
run16(64, 8, 3.55, gain=0.5, chaos=True, octave=True)
counter(64, 8, r=3.5, gain=0.16)
x = 0.31
for b in range(64, 72):
    for s in range(16):
        x = 3.99 * x * (1 - x)
        if x > 0.92 and s % 2 == 1:
            add(screech(hz(deg(int(x * 30) % 10, ROOT + 12)), S16 * 1.9, idx_hi=8), bar(b) + s * S16, MU, gain=0.13, lorenz=0.7)
for b in (59, 63, 67):
    fill(b, k0=b * 17)
swell(bar(64), BAR, k=9)
add(impact(31), bar(64), MU, gain=0.45, send=0.4)
POST.append(("cantor", bar(61), BAR))
POST.append(("ratchet", bar(69) + 3 * BEAT, BEAT))
POST.append(("tapestop", bar(71), BAR))

# Outro 72-76: rueckwaerts durch die Bifurkation zum Fixpunkt
x = 0.4
for b in range(72, 76):
    for s in range(16):
        r = 3.99 - 1.09 * ((b - 72) * 16 + s) / 64
        for _ in range(2):
            x = r * x * (1 - x)
        add(lead(hz(deg(int(x * 8) + 7 if s % 2 == 0 else 0, ROOT + 24))), bar(b) + s * S16, MU,
            gain=0.4 * (1 - 0.15 * (b - 72)), send=0.35)
downlift(bar(72), BAR)
END = bar(76)
put_kick(END, drive=12)
add(impact(9), END, MU, gain=0.6, send=0.6)

# ================== MIXDOWN ==================

duck = np.ones(N)
shape = 1 - DUCK * np.exp(-np.arange(int(0.25 * SR)) / SR / 0.06)
for kt in KICK_TIMES:
    i = int(kt * SR)
    seg = duck[i : i + len(shape)]
    np.minimum(seg, shape[: len(seg)], out=seg)
MU *= duck

ir_t = tt(2.0)
ir = np.stack([noise(len(ir_t), 11), noise(len(ir_t), 12)]) * np.exp(-ir_t / 0.55)
ir[:, : int(0.02 * SR)] = 0
for c in range(2):
    MU[c] += 0.045 * ss.fftconvolve(filt(SEND[c], "bandpass", [250, 6000]), ir[c])[:N]

# --- phonktion: Intensitaets-Bitcrush auf der Musikspur > 150 Hz (Kick/Sub bleiben sauber) ---
if CRUSH_AMT > 0:
    _hi = np.stack([filt(c, "highpass", 150, 4) for c in MU])
    _lo = MU - _hi
    _bits = 12 - 7 * CRUSH_AMT  # min. 5 Bit: dreckig, aber tonal
    _hold = 1 + int(round(3 * CRUSH_AMT))
    _pk = np.abs(_hi).max() + 1e-9
    _idx = (np.arange(N) // _hold) * _hold
    _cr = np.round(_hi[:, _idx] / _pk * 2 ** _bits) / 2 ** _bits * _pk
    MU = _lo + _hi * (1 - 0.75 * CRUSH_AMT) + _cr * 0.75 * CRUSH_AMT
mix = DR + MU
low = filt(mix.mean(0), "lowpass", 120, 4)
mix = np.stack([filt(c, "highpass", 120, 4) for c in mix]) + low
mix = np.stack([filt(filt(c, "highpass", 25), "lowpass", 14000) for c in mix])  # dunkel wie die Referenz

# Master-EQ Richtung Referenz: Sub -3 dB, Mitten 500-2500 Hz +3 dB
zf = lambda c, k, f: ss.sosfiltfilt(ss.butter(2, f, k, fs=SR, output="sos"), c)  # nullphasig
mix = np.stack([c - 0.35 * zf(c, "lowpass", 70) + 0.45 * zf(c, "bandpass", [500, 2500]) + 0.35 * zf(c, "bandpass", [2500, 6000]) for c in mix])


# --- Post-FX auf dem Mix ---
def cantor_mask(n, level=3):
    """Cantor-Menge: Zellen behalten, deren Basis-3-Darstellung keine 1 enthaelt."""
    cells = 3 ** level
    keep = np.array([all(int(dg) != 1 for dg in np.base_repr(c, 3).zfill(level)) for c in range(cells)], float)
    g = np.repeat(keep, int(np.ceil(n / cells)))[:n]
    return nd.uniform_filter1d(g, int(0.003 * SR))  # weiche Kanten gegen Klicks


for kind, t0, d in POST:
    i0, n = int(t0 * SR), int(d * SR)
    if kind == "cantor":
        mix[:, i0 : i0 + n] *= cantor_mask(n)
    elif kind == "ratchet":  # geometrische Wiederholungen: 1/2, 1/4, 1/8, 1/16, 1/16
        src = mix[:, i0 : i0 + n].copy()
        p, ln = 0, n // 2
        for ln in (n // 2, n // 4, n // 8, n // 16, n // 16):
            w = np.minimum(1, np.minimum(np.arange(ln), ln - np.arange(ln)) / (0.002 * SR))
            mix[:, i0 + p : i0 + p + ln] = src[:, :ln] * w
            p += ln
    elif kind == "tapestop":  # Abspielrate faellt exponentiell: pos(t) = tau*(1-exp(-t/tau))
        tau = d / 3
        t = np.arange(n) / SR
        pos = i0 + tau * (1 - np.exp(-t / tau)) * SR
        for c in range(2):
            mix[c, i0 : i0 + n] = np.interp(pos, np.arange(len(mix[c])), mix[c]) * np.clip((d - t) / 0.05, 0, 1)

for a_, b_ in MUTES:
    i0, i1 = int(a_ * SR), int(b_ * SR)
    w = int(0.004 * SR)
    mix[:, i0 - w : i0] *= np.linspace(1, 0, w)
    mix[:, i0:i1] = 0
    mix[:, i1 : i1 + w] *= np.linspace(0, 1, w)

i0, i1 = int(bar(72) * SR), int((bar(76) - BEAT) * SR)
m = np.abs(mix).max()
lv = 2 ** np.linspace(10, 3, i1 - i0)
mix[:, i0:i1] = np.round(mix[:, i0:i1] / m * lv) / lv * m

# Master: Saettigung -> Limiter -> Clipper (Brickwall wie die Referenz)
mix /= np.abs(mix).max()
mix = np.tanh(2.0 * mix) / np.tanh(2.0)
THR = 0.25 * LIM
pk = nd.maximum_filter1d(np.abs(mix).max(0), int(0.004 * SR))
g = np.minimum(1, THR / (pk + 1e-9))
g = nd.minimum_filter1d(g, int(0.004 * SR))
a = np.exp(-1 / (0.06 * SR))
gs = ss.lfilter([1 - a], [1, -a], g, zi=[g[0] * a])[0]
mix = mix * np.minimum(g, gs) / THR
mix = np.clip(np.tanh(2.0 * CLIPD * mix) / np.tanh(2.0 * CLIPD), -1, 1) * 0.97
# Dynamik nach dem Limiter: Break und Intro leiser, damit die Drops knallen
auto = np.ones(N)
for a_, b_, gdb in ((0, 8, -3), (24, 28, -5), (28, 30, -2), (50, 54, -5), (54, 56, -2)):
    auto[int(bar(a_) * SR) : int(bar(b_) * SR)] = 10 ** (gdb / 20)
auto = nd.uniform_filter1d(auto, int(0.03 * SR))
mix *= auto
mix *= np.clip((N / SR - np.arange(N) / SR) / 1.0, 0, 1)

os.makedirs(OUT, exist_ok=True)
wf.write(os.path.join(OUT, (NAME or "bifurkation_v5") + ".wav"), SR, (mix.T * 32767).astype(np.int16))
for r in (3.5, 3.55, 3.83):
    print(f"r={r}: hook {orbit_hook(r)}")
for name, a_, b_ in [("intro", 0, 8), ("drop1", 8, 24), ("break", 24, 28), ("build", 28, 30),
                     ("half", 30, 34), ("drop2", 34, 50), ("break2", 50, 54), ("build2", 54, 56), ("drop3", 56, 72), ("outro", 72, 76)]:
    seg = mix[:, int(bar(a_) * SR) : int(bar(b_) * SR)]
    print(f"{name:6s} rms={20*np.log10(np.sqrt((seg**2).mean())+1e-9):6.1f} dBFS")
print("Zeno:", ZENO, "Dauer:", round(N / SR, 1), "s")
