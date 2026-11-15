#!/usr/bin/env python3
"""TONNETZ - Song 4. Neo-Riemann-Gruppe (P, L, R) auf dem Tonnetz-Torus erzeugt die Akkordfolgen. (Engine aus BIFURKATION v5)

Alt-Doku Engine: BIFURKATION v5 (Referenz: PINKY SMASH) - Math-Hardstyle-Phonk. Diesmal: Hook zuerst, Mathe erzeugt den Hook.

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
BPM = float(P.get('bpm', 152))
BEAT = 60 / BPM
BAR = 4 * BEAT
S16 = BEAT / 4
NBARS = 100
TOTAL = NBARS * BAR + 3.5
N = int(TOTAL * SR)
PHI = (1 + 5 ** 0.5) / 2

DR = np.zeros((2, N))
MU = np.zeros((2, N))
SEND = np.zeros((2, N))
KICK_TIMES = []
EVENTS = []  # fuer Visuals: (typ, zeit, ...)

SCALE = [0, 1, 3, 5, 7, 8, 10]  # A (Moll, Akkorde vom Tonnetz)
ROOT = 45  # A2


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


def rule30(steps, width=1024, take=16):
    """Wolframs Rule 30 als Rauschquelle: neue Zelle = links XOR (mitte OR rechts)."""
    row = np.zeros(width, np.uint8)
    row[width // 2] = 1
    cols = np.linspace(width // 2 - 200, width // 2 + 200, take).astype(int)
    out = np.empty((steps, take), np.uint8)
    for i in range(steps):
        row = np.roll(row, 1) ^ (row | np.roll(row, -1))
        out[i] = row[cols]
    return out.ravel()


R30BITS = rule30(SR * 3 // 16 + 1)
def antenna_noise(n, x=0.1234567):
    """Spitze der Mandelbrot-Antenne: z -> z^2 - 2 auf [-2, 2] ist voll chaotisch."""
    out = np.empty(n)
    for i in range(n):
        x = x * x - 2
        if abs(x) >= 2 or abs(x) < 1e-12:
            x = 0.7071067 + i * 1e-7
        out[i] = x / 2
    return out


NOISE = antenna_noise(SR * 3)


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
def kick(drive=6.0, dur=0.4, f1=None):
    """Zweistufiger Sweep (Klick -> Punch -> Sub), Punch-Layer bei ~180 Hz, Hard-Clip."""
    t = tt(dur)
    f1 = f1 or hz(33)
    f = f1 + (600 - f1) * np.exp(-t / 0.012) + 110 * np.exp(-t / 0.03)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * (0.08 + 0.92 * np.exp(-t / 0.11))  # kurzer Ausklang: Sub traegt die Akkorde
    punch = np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.025)
    x = np.clip((body + 0.5 * punch) * drive * 0.6, -1, 1)
    x = 0.8 * x + 0.2 * np.tanh(drive * body)
    x = filt(x, "lowpass", 6000)
    n = int(0.004 * SR)
    x[:n] += 0.7 * filt(noise(n, 5), "highpass", 3000) * np.linspace(1, 0, n)
    return x * np.minimum(1, (dur - t) / 0.012)


def put_kick(t0, drive=6.0, gain=1.0):
    """Kick-Ausklang auf den Grundton des aktuellen Akkords gestimmt (wie getunte Hardstyle-Kicks)."""
    KICK_TIMES.append(t0)
    ch = next((c for a, b, c in TIMELINE if a <= t0 < b), None)
    f1 = hz(midi_of(ch[0], 28 - TRANSPOSE)) if ch else None
    add(kick(drive * KDRIVE, f1=f1), t0, DR, gain=gain)


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
            EVENTS.append(("clap", bar(b) + j * BEAT))
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
    EVENTS.append(("zeno", t_end - span, t_end))
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
    EVENTS.append(("fill", bar(b) + 3 * BEAT))
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
    x = filt(noise(n // 2 + 1, k).repeat(2)[:n], "bandpass", [600, 9000]) * np.exp((t - dur) / (dur / 5))
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



# ================== SIERPINSKI: Mathe-Bausteine ==================
from math import comb


def pascal_row(n, m=7):
    return [comb(n, k) % m for k in range(n + 1)]


def thue_morse(n):
    return bin(n).count("1") % 2


def lucas_odd(r, k):
    """Satz von Lucas: C(r,k) ist ungerade genau dann, wenn k & ~r == 0 (Sierpinski-Dreieck)."""
    return (k & ~r) == 0


def hook_lead(f, prev, dur):
    t = tt(dur + 0.08)
    fc = f + (prev - f) * np.exp(-t / 0.035)
    y = sum(ss.sawtooth(2 * np.pi * np.cumsum(fc * 2 ** (dt / 1200)) / SR) for dt in (-14, -5, 5, 14)) / 4
    y += 0.5 * np.sign(np.sin(2 * np.pi * np.cumsum(fc / 2) / SR))
    e = np.exp(-t / 0.12)
    out = filt(y, "lowpass", 900) * (1 - e) + filt(y, "lowpass", 5400) * e
    env = np.minimum(1, t / 0.005) * np.clip((dur + 0.08 - t) / 0.08, 0, 1)
    return np.tanh(2.2 * out * env)


FIBWORD = "abaababaabaab"
HOOK_LEN = [3 if c == "a" else 2 for c in FIBWORD[:6]]  # 3-2-3-3-2-3
CALL = [(v - 1) % 7 for v in pascal_row(5)]  # 1 5 10 10 5 1 mod 7 -> 0 4 2 2 4 0
ANSWER = [(v - 1) % 7 for v in pascal_row(6)][:6]  # 1 6 15 20 15 6 mod 7 -> 0 5 0 5 0 5
CALL[0] = 7  # Auftakt eine Oktave hoeher


def play_hook_lead(b0, nbars, gain=0.42, octave=ROOT + 36):
    prev = hz(deg(CALL[0], octave))
    for b in range(b0, b0 + nbars):
        notes = CALL if (b - b0) % 2 == 0 else ANSWER
        pos = 0
        for d, ln in zip(notes, HOOK_LEN):
            f = hz(deg(d, octave))
            add(hook_lead(f, prev, ln * S16 * 0.95), bar(b) + pos * S16, MU, gain=gain, lorenz=0.15, send=0.35)
            prev = f
            pos += ln


ROW_CYCLE = [3, 4, 5, 6, 3, 4, 5, 7]  # Takt 8 = Zeile 7 = fast nur Nullen (Lucas) -> Pause


def run_pascal(b0, nbars, gain=0.62, cutoff=None, octave=False, glitch=False, rows=ROW_CYCLE):
    """16tel-Linie: gerade 16tel = naechster Eintrag der Pascal-Zeile (mod 7) als Skalenstufe (0 = Pause),
    ungerade 16tel = Grundton-Anker."""
    g = 0
    for b in range(b0, b0 + nbars):
        row = pascal_row(rows[(b - b0) % len(rows)])
        lucas_bar = all(v == 0 for v in row[1:-1])
        for s in range(16):
            if s % 2 == 0:
                v = row[(s // 2) % len(row)]
                if v == 0:
                    continue
                d = v - 1 + 7
            else:
                if lucas_bar:
                    continue
                d = 0
            if glitch:
                g += 1
                if R30BITS[g % len(R30BITS)] and R30BITS[(g * 7) % len(R30BITS)] and R30BITS[(g * 13) % len(R30BITS)]:
                    d += 7  # Rule-30 entscheidet ueber Oktavspruenge
            sig = lead(hz(deg(d, ROOT + 24)))
            if cutoff is not None:
                u = (b - b0 + s / 16) / nbars
                sig = filt(sig, "lowpass", cutoff[0] * (cutoff[1] / cutoff[0]) ** u)
            vel = (1.0 if s % 4 == 0 else 0.8) * golden_vel(b * 16 + s)
            t0 = bar(b) + s * S16
            add(sig, t0, MU, gain=gain * vel, lorenz=0.25, send=0.25)
            if octave and s % 2 == 0:
                add(lead(hz(deg(d + 7, ROOT + 24))), t0, MU, gain=gain * 0.35 * vel, lorenz=-0.6, send=0.2)
        if lucas_bar:
            fill(b, k0=b * 11)


def bell(f, dur=1.6):
    t = tt(dur)
    x = sum(np.sin(2 * np.pi * f * h * t) * np.exp(-t * (1.5 + 2.5 * h)) / h for h in (1, 2, 3, 4, 6))
    return np.tanh(1.5 * x) * np.minimum(1, t / 0.003)


def pascal_bells(b, n, gain=0.22, base=ROOT + 36, off=0, span=16):
    """Zeile n des Dreiecks als Arpeggio: Eintrag k -> Stufe (C(n,k) mod 7)."""
    row = pascal_row(n)
    step = span / max(len(row), 1)
    for k, v in enumerate(row):
        if v:
            add(bell(hz(deg(v - 1, base)), 1.4), bar(b) + (off + k * step) * S16, MU, gain=gain, lorenz=0.9, send=0.5)


def sub_tm(b0, nbars):
    """Durchgehender Sub; Thue-Morse(Takt)=1 -> letzter Beat gleitet auf die Quinte, sonst Grundton."""
    dur = nbars * BAR
    n = int(dur * SR)
    f = np.full(n, hz(deg(0, ROOT - 12)))
    for b in range(nbars):
        if thue_morse(b0 + b):
            i0 = int((b * BAR + 3 * BEAT) * SR)
            i1 = min(int((b + 1) * BAR * SR), n)
            tgt = hz(deg(4 if thue_morse(b0 + b + 1) else 5, ROOT - 12))
            f[i0:i1] = f[i0] + (tgt - f[i0]) * np.minimum(1, np.arange(i1 - i0) / (0.06 * SR))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = filt(np.tanh(4.5 * (np.sin(ph) + 0.15 * np.sin(2 * ph))) / np.tanh(4.5), "lowpass", 900)
    x *= np.minimum(1, np.arange(n) / (0.01 * SR)) * np.clip((n - np.arange(n)) / (0.02 * SR), 0, 1)
    add(x, bar(b0), MU, gain=0.36)


def binary_roll(t_end, beats=8, k0=0):
    """Schlaege pro Beat verdoppeln sich: 1,1,2,2,4,4,8,16 (Zweierpotenzen)."""
    per = [1, 1, 2, 2, 4, 4, 8, 16][-beats:]
    t0 = t_end - beats * BEAT
    c = 0
    for j, p in enumerate(per):
        for i in range(p):
            add(clap(k0 + c), t0 + j * BEAT + i * BEAT / p, DR, gain=0.25 + 0.4 * j / beats, send=0.15)
            c += 1


def fill(b, k0=0):
    for i in range(4):
        add(clap(k0 + i), bar(b) + 3 * BEAT + i * S16, DR, gain=0.35 + 0.08 * i)
    for i in range(4):
        add(snare_hi(k0 + 10 + i, 1 + 0.15 * i), bar(b) + 3 * BEAT + 2 * S16 + i * S16 / 2, DR, gain=0.4)


def snare_hi(k, pitch):
    t = tt(0.12)
    n = filt(noise(len(t), k), "bandpass", [1500, 7000]) * np.exp(-t / 0.04)
    return np.tanh(2 * (n + 0.6 * np.sin(2 * np.pi * 240 * pitch * t) * np.exp(-t / 0.03)))


def swell(t_end, dur=BAR, k=0, gain=0.22):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = filt(noise(n // 2 + 1, k).repeat(2)[:n], "bandpass", [600, 9000]) * np.exp((t - dur) / (dur / 5))
    add(x, t_end - dur, DR, gain=gain, lorenz=0.5)


def downlift(t0, dur=2 * BEAT, k=0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 2500 * np.exp(-t / (dur / 3)) + 80
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (dur / 2)) * 0.5
    x += filt(noise(n, k), "highpass", 3000) * np.exp(-t / (dur / 3)) * 0.4
    add(x, t0, MU, gain=0.25, send=0.4)


def halftime(b0, nbars):
    for b in range(b0, b0 + nbars):
        put_kick(bar(b), drive=11)
        put_kick(bar(b) + 1.5 * BEAT, drive=11, gain=0.8)
        if thue_morse(b):
            put_kick(bar(b) + 3.5 * BEAT, drive=11, gain=0.7)
        add(clap(b * 7), bar(b) + 2 * BEAT, DR, gain=0.7, send=0.2)
        for i in range(12):
            add(hat(b * 12 + i), bar(b) + i * BEAT / 3, DR, gain=0.12 * golden_vel(i), lorenz=0.6)


def drums_r30(b0, nbars, drive=11.0, stutter=False):
    drums(b0, nbars, drive=drive)
    if not stutter:
        return
    g = 0
    for b in range(b0, b0 + nbars):
        for s in range(16):
            g += 1
            if s % 4 and all(R30BITS[(g * m) % len(R30BITS)] for m in (3, 5, 11, 17)):
                for z in range(3):
                    put_kick(bar(b) + s * S16 + z * S16 / 3, drive=drive, gain=0.5)


POST = []


# ================== MANDELBROT: Mathe-Bausteine ==================
import cmath


def cardioid_point(p, q):
    th = 2 * np.pi * p / q
    return cmath.exp(1j * th) / 2 - cmath.exp(2j * th) / 4


def bulb_center(p, q):
    """Newton auf P(c) = f_c^q(0) = 0, Start knapp ausserhalb des Kardioid-Randpunkts beim Winkel p/q."""
    cb = cardioid_point(p, q)
    c = cb + 0.3 / q ** 2 * (cb - 0.25) / abs(cb - 0.25)
    for _ in range(60):
        z, dz = 0j, 0j
        for _ in range(q):
            dz = 2 * z * dz + 1
            z = z * z + c
        c -= z / dz
    return c


def cycle(c, q):
    z, out = 0j, []
    for _ in range(q):
        out.append(z)
        z = z * z + c
    return out


PREF = [0, 4, 1, 5, 7, 2, 8, 3]


def bulb_notes(p, q):
    """Zyklus-Punkte nach Winkel um den Fixpunkt alpha ranken -> Skalenstufen. Er rotiert um p/q."""
    c = bulb_center(p, q)
    alpha = (1 - cmath.sqrt(1 - 4 * c)) / 2
    angs = [cmath.phase(z - alpha) for z in cycle(c, q)]
    degs = sorted(PREF[:q])
    order = sorted(range(q), key=lambda k: angs[k])
    rank = {k: degs[i] for i, k in enumerate(order)}
    return [rank[k] for k in range(q)], c


def golden_notes(n, span=8):
    """Siegel-Scheibe am goldenen Winkel: Dynamik konjugiert zur Rotation um 1/phi -> nie periodisch."""
    return [int(((k / PHI) % 1) * span) for k in range(n)]


def escape(c, maxit=20000):
    z = 0j
    for i in range(maxit):
        z = z * z + c
        if abs(z) > 2:
            return i
    return maxit


def julia_mask(c, cells=32, ang=0.0):
    """32 Punkte auf einer Geraden durch 0: Punkt gehoert zur gefuellten Julia-Menge -> Gate offen."""
    out = []
    for k in range(cells):
        z = (-1.6 + 3.2 * (k + 0.5) / cells) * cmath.exp(1j * ang)
        for _ in range(80):
            z = z * z + c
            if abs(z) > 2:
                break
        out.append(1.0 if abs(z) <= 2 else 0.0)
    return out


def shepard(dur, rate=1.0, f0=27.5, octs=8, down=False):
    """Shepard-Risset-Glissando: Oktavkomponenten steigen endlos (unendlicher Zoom)."""
    t = tt(dur)
    y = np.zeros_like(t)
    for k in range(octs):
        lf = (k + (-1 if down else 1) * rate * t) % octs
        f = f0 * 2 ** lf
        amp = np.exp(-((lf - octs / 2) ** 2) / 2.5)
        y += amp * np.sin(2 * np.pi * np.cumsum(f) / SR)
    return y / 3 * np.minimum(1, t / 0.5) * np.clip((dur - t) / 0.3, 0, 1)


def boll_roll(t_end, beats=8, k0=0):
    """Fluchtzeit N(1/4+eps) ~ pi/sqrt(eps): Schlaege pro Beat = Fluchtzeit bei immer kleinerem eps."""
    eps = [2.0 ** (-j * 1.15) for j in range(beats)]
    counts = [min(escape(0.25 + e), 24) for e in eps]
    t0 = t_end - beats * BEAT
    c = 0
    for j, p in enumerate(counts):
        for i in range(p):
            add(clap(k0 + c), t0 + j * BEAT + i * BEAT / p, DR, gain=0.2 + 0.45 * j / beats, send=0.15)
            c += 1
    return counts, [round(escape(0.25 + e) * e ** 0.5, 3) for e in (1e-2, 1e-4, 1e-6)]


def run_cycle(b0, nbars, notes, gain=0.62, cutoff=None, octave=False, chaos=False, mirror=True):
    """16tel-Linie: gerade 16tel = Zyklus-Ton oben, ungerade = Grundton-Anker; Takt 4 gespiegelt."""
    p = len(notes)
    hi, lo = max(notes), min(notes)
    k = 0
    ci = 0
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
                ci += 1
                if NOISE[(ci * 997) % len(NOISE)] > 0.93:
                    d = int((NOISE[(ci * 31) % len(NOISE)] + 1) * 6) % 12
            sig = lead(hz(deg(d, ROOT + 24)))
            if cutoff is not None:
                u = (b - b0 + s / 16) / nbars
                sig = filt(sig, "lowpass", cutoff[0] * (cutoff[1] / cutoff[0]) ** u)
            vel = (1.0 if s % 4 == 0 else 0.8) * golden_vel(b * 16 + s)
            t0 = bar(b) + s * S16
            add(sig, t0, MU, gain=gain * vel, lorenz=0.25, send=0.25)
            if octave and s % 2 == 0:
                add(lead(hz(deg(d + 7, ROOT + 24))), t0, MU, gain=gain * 0.35 * vel, lorenz=-0.6, send=0.2)


HOOK_POS = [i for i, v in enumerate(euclid(5, 16)) if v]  # 5 aus 16, maximal gleichmaessig = Rotation 5/16


def play_hook5(b0, nbars, notes, gain=0.42, octave=ROOT + 36):
    hi, lo = max(notes), min(notes)
    call = list(notes)
    answer = [hi + lo - n for n in notes]
    answer[-1] = 0
    lens = [HOOK_POS[i + 1] - HOOK_POS[i] if i + 1 < 5 else 16 - HOOK_POS[i] + HOOK_POS[0] for i in range(5)]
    prev = hz(deg(call[0], octave))
    for b in range(b0, b0 + nbars):
        ns = call if (b - b0) % 2 == 0 else answer
        for d, pos, ln in zip(ns, HOOK_POS, lens):
            f = hz(deg(d, octave))
            add(hook_lead(f, prev, ln * S16 * 0.95), bar(b) + pos * S16, MU, gain=gain, lorenz=0.15, send=0.35)
            prev = f


def sub_orbit(b0, nbars, notes):
    """Sub auf dem Grundton; Zyklus-Ton > Mitte -> letzter Beat gleitet (Quinte/Oktave/b2)."""
    dur = nbars * BAR
    n = int(dur * SR)
    f = np.full(n, hz(deg(0, ROOT - 12)))
    mid = (max(notes) + min(notes)) / 2
    for b in range(nbars):
        v = notes[(b0 + b) % len(notes)]
        if v > mid:
            i0 = int((b * BAR + 3 * BEAT) * SR)
            i1 = min(int((b + 1) * BAR * SR), n)
            tgt = hz(deg([4, 7, 1][b % 3], ROOT - 12))
            f[i0:i1] = f[i0] + (tgt - f[i0]) * np.minimum(1, np.arange(i1 - i0) / (0.06 * SR))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = filt(np.tanh(4.5 * (np.sin(ph) + 0.15 * np.sin(2 * ph))) / np.tanh(4.5), "lowpass", 900)
    x *= np.minimum(1, np.arange(n) / (0.01 * SR)) * np.clip((n - np.arange(n)) / (0.02 * SR), 0, 1)
    add(x, bar(b0), MU, gain=0.36)


def bells_seq(b0, notes, step_beats=2, gain=0.18, base=ROOT + 36, count=16):
    for i in range(count):
        add(bell(hz(deg(notes[i % len(notes)] + 7, base)), step_beats * BEAT + 0.6), bar(b0) + i * step_beats * BEAT,
            MU, gain=gain, lorenz=0.9, send=0.5)


N3, C3 = bulb_notes(1, 3)
N5, C5 = bulb_notes(2, 5)
N8, C8 = bulb_notes(3, 8)
GOLD = golden_notes(64)
POST = []


# ================== TONNETZ: Neo-Riemann-Gruppe auf dem Torus ==================
from collections import deque

NAMES = "A A# B C C# D D# E F F# G G#".split()  # Tonklassen relativ zu A


def P(ch):
    r, q = ch
    return (r, "M" if q == "m" else "m")


def R(ch):
    r, q = ch
    return ((r - 3) % 12, "m") if q == "M" else ((r + 3) % 12, "M")


def L(ch):
    r, q = ch
    return ((r + 4) % 12, "m") if q == "M" else ((r - 4) % 12, "M")


OPS = {"P": P, "L": L, "R": R}


def walk(start, word):
    out = [start]
    for w in word:
        out.append(OPS[w](out[-1]))
    return out


def tonnetz_path(a, b):
    """Kuerzester Weg auf dem Tonnetz (BFS ueber P, L, R)."""
    q, seen = deque([(a, "")]), {a}
    while q:
        ch, w = q.popleft()
        if ch == b:
            return w
        for k, f in OPS.items():
            n = f(ch)
            if n not in seen:
                seen.add(n)
                q.append((n, w + k))


def name(ch):
    return NAMES[ch[0]] + ("m" if ch[1] == "m" else "")


def tones(ch):
    r, q = ch
    return [r, (r + (3 if q == "m" else 4)) % 12, (r + 7) % 12]


def midi_of(pc, lo):
    """Kleinste MIDI-Note >= lo mit Tonklasse pc (A = 0 -> MIDI 57 = A3)."""
    m = lo + ((pc - (lo - 57)) % 12)
    return m


def chord_range(ch, lo, hi):
    ts = tones(ch)
    return [m for m in range(lo, hi + 1) if (m - 57) % 12 in ts]


AM = (0, "m")
# Seed waehlt die Neo-Riemann-Woerter (alle getestet: enden auf Moll-Tonika-Umfeld, Final kadenziert ueber E-Dur)
WORDS1 = ["LRL", "RLR", "LPL", "LRP"]  # Am F Dm Bb | Am C Em G | Am F Fm Db | Am F Dm D
WORDS2 = ["RLP", "LRL", "RLR", "PLR"]
W1, W2 = WORDS1[SEED % 4], WORDS2[(SEED // 4) % 4]
PROG1 = walk(AM, W1)[:4]
PROG2 = walk(AM, W2)[:4]
HEXA = walk(AM, "LPLPLP")[:6]  # Am F Fm Db C#m A
FINAL = [AM, PROG1[1], PROG1[2], (7, "M")]  # ... -> E-Dur (V) -> Am
GRAY = [i ^ (i >> 1) for i in range(16)]  # 0 1 3 2 6 7 5 4 12 13 15 14 10 11 9 8

TIMELINE = []  # (t0, t1, chord) fuer Pad/Sub


def prog_at(b0, nbars, prog, per=1.0):
    """Akkord-Zeitachse: jeder Akkord 'per' Takte."""
    out = []
    t, i = 0.0, 0
    while t < nbars - 1e-9:
        d = min(per, nbars - t)
        out.append((bar(b0) + t * BAR, bar(b0) + (t + d) * BAR, prog[i % len(prog)]))
        t += d
        i += 1
    TIMELINE.extend(out)
    return out


def sub_prog(segs, dive_every=4, gain=0.5):
    """Sub folgt den Akkord-Grundtoenen (60 ms Glide); am Ende jeder Phrase ein Oktav-Dive (grosser Slide)."""
    t0, t1 = segs[0][0], segs[-1][1]
    n = int((t1 - t0) * SR)
    f = np.zeros(n)
    prev = None
    for k, (a, b, ch) in enumerate(segs):
        i0, i1 = int((a - t0) * SR), int((b - t0) * SR)
        tgt = hz(midi_of(ch[0], 28 - TRANSPOSE))
        if prev is None:
            prev = tgt
        ramp = np.minimum(1, np.arange(i1 - i0) / (0.06 * SR))
        f[i0:i1] = prev + (tgt - prev) * ramp
        prev = tgt
    # Oktav-Dives: letzte halbe Beat jeder Phrase (alle dive_every Takte) faellt der Sub eine Oktave
    tt_ = np.arange(n) / SR
    phrase = dive_every * BAR
    pos = (tt_ % phrase) / phrase
    dive_start = 1 - (BEAT / 2) / phrase
    m = pos > dive_start
    f[m] *= 2 ** (-((pos[m] - dive_start) / (1 - dive_start)) * 1.0)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = filt(np.tanh(4.5 * (np.sin(ph) + 0.15 * np.sin(2 * ph))) / np.tanh(4.5), "lowpass", 900)
    x *= np.minimum(1, tt_ / 0.01) * np.clip((n / SR - tt_) / 0.03, 0, 1)
    add(x, t0, MU, gain=gain)


def pad_prog(segs, gain=0.07):
    """Mitten-Wand folgt den Akkorden (verstimmte Saegen auf den Akkordtoenen um A3)."""
    for a, b, ch in segs:
        d = b - a
        t = tt(d)
        y = np.zeros_like(t)
        for m in chord_range(ch, 52, 64):
            for det in (-0.1, 0.1):
                y += ss.sawtooth(2 * np.pi * hz(m + det) * t)
        y = filt(np.tanh(1.2 * y), "bandpass", [220, 1600])
        y *= np.minimum(1, t / 0.01) * np.clip((d - t) / 0.01, 0, 1)
        add(y, a, MU, gain=gain, lorenz=0.25)


def arp_gray(segs, gain=0.55, cutoff=None, octave=False):
    """16tel-Arpeggio: Akkordtoene (A4..A6) in Gray-Code-Reihenfolge; ungerade 16tel = Grundton-Anker."""
    for a, b, ch in segs:
        pool = chord_range(ch, 69, 93)
        anchor = midi_of(ch[0], 57)
        n16 = int(round((b - a) / S16))
        for s in range(n16):
            g = GRAY[s % 16]
            m = pool[g % len(pool)] if s % 2 == 0 else anchor + 12
            t0 = a + s * S16
            EVENTS.append(("arp", t0, m))
            sig = lead(hz(m))
            if cutoff is not None:
                u = (t0 - cutoff[2]) / (cutoff[3] - cutoff[2])
                sig = filt(sig, "lowpass", cutoff[0] * (cutoff[1] / cutoff[0]) ** np.clip(u, 0, 1))
            vel = (1.0 if s % 4 == 0 else 0.8) * golden_vel(int(t0 * 97))
            add(sig, t0, MU, gain=gain * vel, lorenz=0.25, send=0.25)
            if octave and s % 2 == 0:
                add(lead(hz(m + 12)), t0, MU, gain=gain * 0.3 * vel, lorenz=-0.6, send=0.2)


def top_line(segs, gain=0.36, start=81, glide_in=False):
    """Gehaltener Lead (Vaspertine-Stil): pro Akkord 6-4-6 Sechzehntel, Stimmfuehrung = naechster Akkordton
    zum Vorton (minimale Bewegung auf dem Tonnetz), rhythmische Luecken zwischen den Toenen."""
    prev_m = start
    prev_f = hz(start - 12) if glide_in else hz(start)
    for a, b, ch in segs:
        pool = chord_range(ch, 74, 91)
        m1 = min(pool, key=lambda m: abs(m - prev_m))
        up = [m for m in pool if m > m1]
        m2 = up[0] if up else m1 - 12
        for pos, ln, m in ((0, 6, m1), (6, 4, m2), (10, 6, m1)):
            t0 = a + pos * S16
            if t0 >= b - 1e-6:
                break
            f = hz(m)
            EVENTS.append(("top", t0, m, ln * S16 * 0.8))
            add(hook_lead(f, prev_f, ln * S16 * 0.8), t0, MU, gain=gain, lorenz=0.15, send=0.35)
            prev_f = f
        prev_m = m1


def glide_lead(t0, m_from, m_to, dur, gain=0.35):
    """Grosser Pitch-Slide ueber mehrere Toene (linear in Halbtoenen)."""
    EVENTS.append(("glide", t0, m_from, m_to, dur))
    t = tt(dur)
    mm = m_from + (m_to - m_from) * np.minimum(1, t / (dur * 0.85))
    f = 440 * 2 ** ((mm - 69) / 12)
    y = sum(ss.sawtooth(2 * np.pi * np.cumsum(f * 2 ** (d / 1200)) / SR) for d in (-12, 0, 12)) / 3
    y = filt(np.tanh(2 * y), "lowpass", 4500) * np.minimum(1, t / 0.01) * np.clip((dur - t) / 0.05, 0, 1)
    add(y, t0, MU, gain=gain, send=0.3)


def tritone_stab(t0, ch, gain=0.35):
    """Tritonus-Stab (Whip-Stil): Grundton + verminderte Quinte, kurz und dreckig."""
    EVENTS.append(("stab", t0, midi_of(ch[0], 57)))
    r = midi_of(ch[0], 57)
    t = tt(0.22)
    y = sum(np.sign(np.sin(2 * np.pi * hz(m) * t)) for m in (r, r + 6, r + 12))
    y = filt(np.tanh(2.5 * y), "bandpass", [200, 5000]) * np.exp(-t / 0.07)
    add(y, t0, MU, gain=gain, send=0.3, lorenz=0.4)


def stabs(segs, every=4):
    for k, (a, b, ch) in enumerate(segs):
        if k % every == every - 1:
            tritone_stab(b - BEAT / 2, ch)


FILTERS = []  # (t0, t1, f_start, f_end) Tiefpass auf dem ganzen Mix
DUCK_SEC = []  # (t0, t1, Tiefe)
POST = []
CRUSH = []

def add_imp(sig, t0, *a, **k):
    EVENTS.append(("impact", t0))
    add(sig, t0, *a, **k)


# ================== ARRANGEMENT (100 Takte @152) ==================
# Intro 0-8: Beat + Arp sofort da, aber hinter einem Tiefpass, der sich oeffnet (Filter-Sweep auf dem Mix)
seg = prog_at(0, 8, PROG1)
drums(0, 8, drive=10)
sub_prog(seg)
pad_prog(seg)
arp_gray(seg, gain=0.5)
FILTERS.append((0, bar(8) - BEAT, 250, 16000))
glide_lead(bar(7), 69, 81, BAR, gain=0.3)
swell(bar(8), 2 * BAR, k=1)

# Drop 1 8-40: 32 Takte am Stueck. Variation alle 8 Takte statt Unterbrechung
add_imp(impact(1), bar(8), MU, gain=0.55, send=0.5)
seg = prog_at(8, 32, PROG1)
drums(8, 32, drive=11)
sub_prog(seg)
pad_prog(seg)
arp_gray(seg[:8])
arp_gray(seg[8:16], octave=True)
top_line(seg[16:], glide_in=True)
arp_gray(seg[16:24], gain=0.42)
arp_gray(seg[24:], gain=0.42, octave=True)
stabs(seg)
for b in (15, 23, 31, 39):
    fill(b, k0=b * 7)
for b in (16, 24, 32):
    add_imp(impact(b), bar(b), MU, gain=0.35, send=0.4)
POST.append(("ratchet", bar(31) + 3 * BEAT, BEAT, 0))
POST.append(("tapestop", bar(39) + 2 * BEAT, 2 * BEAT, 0))
DUCK_SEC.append((bar(8), bar(40), 0.6))

# Langer Break 40-52: hexatonischer Zyklus (je 2 Takte), sehr leise, Filter zu -> auf, gehaltener Lead mit Slides
seg = prog_at(40, 12, HEXA, per=2.0)
pad_prog(seg, gain=0.06)
for a, b, ch in seg:
    for m in chord_range(ch, 64, 76):
        add(bell(hz(m), 2 * BAR * 0.9), a + (m % 3) * S16, MU, gain=0.06, lorenz=0.9, send=0.6)
    add(filt(weierstrass(hz(midi_of(ch[0], 33)), b - a), "lowpass", 600), a, MU, gain=0.08)
top_line(seg, gain=0.22)
glide_lead(bar(47), 76, 64, BAR, gain=0.18)  # Pitch-Dive
FILTERS.append((bar(40), bar(44), 900, 3000))
FILTERS.append((bar(44), bar(52), 3000, 16000))

# Build 52-56: Dominante E-Dur, Arp gefiltert, Riser, Slide eine Oktave hoch in den Drop
seg = prog_at(52, 4, [(7, "M")])
pad_prog(seg)
arp_gray(seg, gain=0.45, cutoff=(400, 8000, bar(52), bar(56)))
sub_prog(seg, dive_every=99)
zeno(bar(56), 3 * BAR, k0=700)
swell(bar(56), 2 * BAR, k=3)
add(shepard(4 * BAR, rate=0.6), bar(52), MU, gain=0.14)
glide_lead(bar(55), 64, 88, BAR, gain=0.3)
stop(55, 0.5)

# Drop 2 56-88: Progression R L P (Am C Em E), tieferes Pumpen; letzte 16 Takte FINAL (Am F Dm E) + alles
add_imp(impact(5), bar(56), MU, gain=0.6, send=0.5)
seg = prog_at(56, 16, PROG2)
drums(56, 16, drive=12)
sub_prog(seg)
pad_prog(seg)
arp_gray(seg[:8])
arp_gray(seg[8:], octave=True)
top_line(seg[8:], gain=0.32)
stabs(seg)
fill(63, 300)
fill(71, 310)
DUCK_SEC.append((bar(56), bar(88), 0.85))
POST.append(("ratchet", bar(71) + 3 * BEAT, BEAT, 0))
seg = prog_at(72, 16, FINAL)
add_imp(impact(6), bar(72), MU, gain=0.5, send=0.4)
drums(72, 8, drive=12)
drums_r30(80, 8, drive=12, stutter=True)
sub_prog(seg)
pad_prog(seg, gain=0.08)
arp_gray(seg, gain=0.5, octave=True)
top_line(seg, gain=0.38, glide_in=True)
stabs(seg, every=2)
for b in (79, 83):
    fill(b, k0=b * 5)
POST.append(("cantor", bar(83), BAR, 0))
POST.append(("ratchet", bar(87) + 3 * BEAT, BEAT, 0))

# Outro 88-100: langes Ausfaden, Tiefpass schliesst sich, Beat duennt aus
seg = prog_at(88, 12, PROG1)
drums(88, 8, drive=9)
sub_prog(seg)
pad_prog(seg, gain=0.06)
arp_gray(seg[:8], gain=0.4)
top_line(seg[4:], gain=0.25)
FILTERS.append((bar(88), bar(100), 16000, 180))
END = bar(100)
add(echo(bell(hz(69), 3.0), fb=0.5, taps=6), END - BAR, MU, gain=0.25, send=0.7)

print("Drop 1:", [name(c) for c in PROG1], f"(Wort {W1})")
print("Drop 2:", [name(c) for c in PROG2], f"(Wort {W2})")
print("Break:", [name(c) for c in HEXA], "(Wort LPLPLP, hexatonischer Zyklus)")
print("Final:", [name(c) for c in FINAL], " Dm->E auf dem Tonnetz:", tonnetz_path(PROG1[2], (7, "M")))
pcs = set()
for _, _, ch in TIMELINE:
    pcs |= set(tones(ch))
print("Tonklassen im Song:", len(pcs), sorted(NAMES[p] for p in pcs))

# ================== MIXDOWN ==================




duck = np.ones(N)
dts = np.arange(int(0.3 * SR)) / SR
for kt in KICK_TIMES:
    depth = min(0.95, next((d for a, b, d in DUCK_SEC if a <= kt < b), 0.6) * DUCK / 0.6)
    shape = 1 - depth * np.exp(-dts / (0.06 + 0.05 * (depth > 0.7)))
    i = int(kt * SR)
    seg = duck[i : i + len(shape)]
    np.minimum(seg, shape[: len(seg)], out=seg)
MU *= duck

ir_t = tt(2.0)
ir = np.stack([noise(len(ir_t), 11), noise(len(ir_t), 12)]) * np.exp(-ir_t / 0.55)
ir[:, : int(0.02 * SR)] = 0
for c in range(2):
    MU[c] += 0.045 * ss.fftconvolve(filt(SEND[c], "bandpass", [250, 6000]), ir[c])[:N]

mu_hi = np.stack([filt(c, "highpass", 150, 4) for c in MU])
mu_lo = MU - mu_hi
pk = np.abs(mu_hi).max() + 1e-9
for b0, b1, bs, be, hold, wet in CRUSH:
    i0, i1 = int(bar(b0) * SR), int(bar(b1) * SR)
    seg = mu_hi[:, i0:i1]
    n = seg.shape[1]
    idx = (np.arange(n) // hold) * hold  # Sample-and-Hold = Samplerate / hold
    held = seg[:, idx]
    lv = 2 ** np.linspace(bs, be, n)  # Bit-Tiefe -> Stufen
    crushed = np.round(held / pk * lv) / lv * pk
    w = np.minimum(1, np.minimum(np.arange(n), n - np.arange(n)) / (0.004 * SR)) * wet
    mu_hi[:, i0:i1] = seg * (1 - w) + crushed * w
MU = mu_lo + mu_hi
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
mix = np.stack([c - 0.15 * zf(c, "lowpass", 70) + 0.45 * zf(c, "bandpass", [500, 2500]) + 0.35 * zf(c, "bandpass", [2500, 6000]) for c in mix])


# --- Filter-Sweeps auf dem ganzen Mix: Ueberblendung nullphasiger Tiefpaesse (phasengleich) ---
CUTS = [150, 230, 350, 540, 830, 1270, 1950, 3000, 4600, 7000, 11000, 16000]
for t0, t1, fa, fb in FILTERS:
    i0, i1 = int(t0 * SR), min(int(t1 * SR), N)
    pad = int(0.2 * SR)
    j0, j1 = max(0, i0 - pad), min(N, i1 + pad)
    region = mix[:, j0:j1]
    vers = [np.stack([ss.sosfiltfilt(ss.butter(2, c, "lowpass", fs=SR, output="sos"), ch) for ch in region]) for c in CUTS]
    n = i1 - i0
    cut = fa * (fb / fa) ** np.linspace(0, 1, n)
    pos = np.interp(np.log(cut), np.log(CUTS), np.arange(len(CUTS)))
    lo = np.clip(np.floor(pos).astype(int), 0, len(CUTS) - 2)
    w = pos - lo
    out = np.zeros((2, n))
    for k in range(len(CUTS) - 1):
        m = lo == k
        if m.any():
            out[:, m] = vers[k][:, i0 - j0 : i1 - j0][:, m] * (1 - w[m]) + vers[k + 1][:, i0 - j0 : i1 - j0][:, m] * w[m]
    mix[:, i0:i1] = out
    if fb < fa:  # schliessender Filter bleibt danach zu
        mix[:, i1:] = np.stack([ss.sosfiltfilt(ss.butter(2, fb, "lowpass", fs=SR, output="sos"), ch) for ch in mix[:, i1:]]) if i1 < N else mix[:, i1:]

# --- Post-FX auf dem Mix ---
def cantor_mask(n, level=3):
    """Cantor-Menge: Zellen behalten, deren Basis-3-Darstellung keine 1 enthaelt."""
    cells = 3 ** level
    keep = np.array([all(int(dg) != 1 for dg in np.base_repr(c, 3).zfill(level)) for c in range(cells)], float)
    g = np.repeat(keep, int(np.ceil(n / cells)))[:n]
    return nd.uniform_filter1d(g, int(0.003 * SR))  # weiche Kanten gegen Klicks


for kind, t0, d, arg in POST:
    i0, n = int(t0 * SR), int(d * SR)
    if kind == "mask":  # Julia-Gate: 32tel offen, wenn der Punkt zur gefuellten Julia-Menge gehoert
        gm = nd.uniform_filter1d(np.repeat(np.array(arg, float), int(np.ceil(n / 32)))[:n], int(0.003 * SR))
        mix[:, i0 : i0 + n] *= gm
    elif kind == "lucas":  # Sierpinski-Gate: 32tel k klingt, wenn C(arg,k) ungerade
        keep = np.array([float((k & ~arg) == 0) for k in range(32)])
        gm = nd.uniform_filter1d(np.repeat(keep, int(np.ceil(n / 32)))[:n], int(0.003 * SR))
        mix[:, i0 : i0 + n] *= gm
    elif kind == "cantor":
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

# Master: Saettigung -> Limiter -> Clipper (Brickwall wie die Referenz)
mix /= np.abs(mix).max()
mix = np.tanh(2.0 * mix) / np.tanh(2.0)
THR = 0.4 * LIM
pk = nd.maximum_filter1d(np.abs(mix).max(0), int(0.004 * SR))
g = np.minimum(1, THR / (pk + 1e-9))
g = nd.minimum_filter1d(g, int(0.004 * SR))
a = np.exp(-1 / (0.06 * SR))
gs = ss.lfilter([1 - a], [1, -a], g, zi=[g[0] * a])[0]
mix = mix * np.minimum(g, gs) / THR
mix = np.clip(np.tanh(1.0 * CLIPD * mix) / np.tanh(1.0 * CLIPD), -1, 1) * 0.97
# Dynamik nach dem Limiter: Break und Intro leiser, damit die Drops knallen
auto_db = np.zeros(N)
for a_, b_, g0, g1 in ((0, 8, -12, -2), (40, 52, -4, -4), (52, 56, -3, 0), (88, 100, 0, -24)):
    i0, i1 = int(bar(a_) * SR), min(int(bar(b_) * SR), N)
    auto_db[i0:i1] = np.linspace(g0, g1, i1 - i0)
auto_db[int(bar(100) * SR):] = -40
auto = nd.uniform_filter1d(10 ** (auto_db / 20), int(0.03 * SR))
mix *= auto
mix *= np.clip((N / SR - np.arange(N) / SR) / 1.0, 0, 1)

os.makedirs(OUT, exist_ok=True)
wf.write(os.path.join(OUT, (NAME or "tonnetz") + ".wav"), SR, (mix.T * 32767).astype(np.int16))
for name_, a_, b_ in [("intro", 0, 8), ("drop1", 8, 40), ("break", 40, 52), ("build", 52, 56), ("drop2", 56, 72), ("final", 72, 88), ("outro", 88, 100)]:
    seg = mix[:, int(bar(a_) * SR) : int(bar(b_) * SR)]
    print(f"{name_:6s} rms={20*np.log10(np.sqrt((seg**2).mean())+1e-9):6.1f} dBFS")
print("Dauer:", round(N / SR, 1), "s")

if os.environ.get("DUMP_EVENTS"):
    import json
    ch_ev = [(a, b, c[0], c[1]) for a, b, c in sorted(TIMELINE)]
    json.dump({"transpose": TRANSPOSE, "intensity": INT, "words": [W1, W2], "bpm": BPM, "bar": BAR, "end": END, "total": N / SR, "chords": ch_ev, "kicks": sorted(KICK_TIMES),
               "events": EVENTS, "post": [(k, t, d) for k, t, d, _ in POST], "filters": FILTERS, "mutes": MUTES},
              open(os.environ["DUMP_EVENTS"], "w"))
    print("Events:", len(EVENTS), "Kicks:", len(KICK_TIMES))
