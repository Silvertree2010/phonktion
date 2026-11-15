#!/usr/bin/env python3
"""TONNETZ - Visuals. Jeder Frame ist eine reine Funktion der Zeit + der exakten Song-Events (events.json).

Der Tonnetz-Torus: Gitter 24 x 9, Tonklasse am Punkt (i, j) = 7i + 4j (mod 12) -> Quinten horizontal, grosse Terzen
schraeg. Jedes Dreieck ist ein Dur- oder Moll-Dreiklang. P, L, R sind Spiegelungen an einer Dreieckskante -
genau so klappen die Dreiecke bei jedem Akkordwechsel um.

Aufruf: visual.py preview t1 t2 ...   |   visual.py render [workers]
"""
import bisect
import json
import math
import os
import subprocess
import sys

import cairo
import cv2
import numpy as np
import scipy.io.wavfile as wf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EV = json.load(open(os.path.join(HERE, "events.json")))
VP = json.loads(os.environ.get("MATHPHONK_PARAMS", "{}"))
TITLE = VP.get("title", "TONNETZ").upper()
WAVNAME = VP.get("name", "tonnetz") + ".wav"
TR = int(EV.get("transpose", 0))
VI = float(EV.get("intensity", 6)) / 6  # Effektstaerke relativ zu Intensitaet 6
W, H, FPS = 1080, 1920, 30
BAR, BPM = EV["bar"], EV["bpm"]
BEAT = BAR / 4
TOTAL = EV["end"] + 1.5
NF = int(TOTAL * FPS)
NAMES = "A Bb B C C# D Eb E F F# G G#".split()
PHI = (1 + 5 ** 0.5) / 2

# ---------------- Events ----------------
KICKS = np.array(EV["kicks"])
CHORDS = EV["chords"]  # (t0, t1, root, q)
CH_T = [c[0] for c in CHORDS]
by = {}
for e in EV["events"]:
    by.setdefault(e[0], []).append(e)
for k in by:
    by[k].sort(key=lambda e: e[1])
ARP = by.get("arp", [])
ARP_T = [e[1] for e in ARP]
TOP = by.get("top", [])
TOP_T = [e[1] for e in TOP]
CLAP_T = sorted(e[1] for e in by.get("clap", []) + by.get("fill", []))
STAB = by.get("stab", [])
IMP_T = sorted(e[1] for e in by.get("impact", []))
GLIDE = by.get("glide", [])
ZENO = by.get("zeno", [])
ZENO_HITS = []
for _, a, b in ZENO:
    span, n = b - a, 0
    while span * 0.9 ** n > 0.004:
        ZENO_HITS.append(b - span * 0.9 ** n)
        n += 1
ZENO_HITS.sort()
POST = EV["post"]
FILTERS = EV["filters"]
MUTES = EV["mutes"]

SECTIONS = [(0, 8, "INTRO"), (8, 40, "DROP I  ·  L R L"), (40, 52, "HEXATONISCHER ZYKLUS"), (52, 56, "DOMINANTE"),
            (56, 72, "DROP II  ·  R L P"), (72, 88, "FINALE"), (88, 100, "OUTRO")]


def recent(times, t, window):
    """Indizes der Events in (t - window, t]."""
    hi = bisect.bisect_right(times, t)
    lo = bisect.bisect_right(times, t - window)
    return range(lo, hi)


def last_before(times, t):
    i = bisect.bisect_right(times, t) - 1
    return i


def chord_at(t):
    i = last_before(CH_T, t)
    if i < 0 or t >= CHORDS[i][1] + 0.05:
        return None, None, i
    return (CHORDS[i][2], CHORDS[i][3]), CHORDS[i][0], i


# ---------------- Neo-Riemann ----------------
def P(c):
    return (c[0], "M" if c[1] == "m" else "m")


def R(c):
    return ((c[0] - 3) % 12, "m") if c[1] == "M" else ((c[0] + 3) % 12, "M")


def L(c):
    return ((c[0] + 4) % 12, "m") if c[1] == "M" else ((c[0] - 4) % 12, "M")


def cname(c):
    return NAMES[(c[0] + TR) % 12] + ("m" if c[1] == "m" else "")


def op_between(a, b):
    for k, f in (("P", P), ("L", L), ("R", R)):
        if f(a) == b:
            return k
    return None


# ---------------- Audio-Baender pro Frame ----------------
sr, au = wf.read(os.path.join(ROOT, WAVNAME))
au = au.astype(np.float32).mean(1) / 32768
hop = sr / FPS


def band_env(lo, hi):
    out = np.zeros(NF)
    win = int(hop * 2)
    for f in range(NF):
        a = int(f * hop)
        seg = au[a:a + win]
        if len(seg) < 64:
            continue
        sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        fr = np.fft.rfftfreq(len(seg), 1 / sr)
        out[f] = sp[(fr >= lo) & (fr < hi)].mean()
    return out / (np.percentile(out, 98) + 1e-9)


ENV_CACHE = os.path.join(HERE, ".env_cache_" + WAVNAME + ".npz")
if os.path.exists(ENV_CACHE):
    z = np.load(ENV_CACHE)
    LOW, MID, HIGH = z["low"], z["mid"], z["high"]
else:
    LOW, MID, HIGH = band_env(30, 150), band_env(300, 3000), band_env(4000, 12000)
    np.savez(ENV_CACHE, low=LOW, mid=MID, high=HIGH)

# ---------------- Kamera (integrierte Geschwindigkeit -> deterministisch) ----------------
def section_speed(t):
    b = t / BAR
    if b < 8:
        return 0.10
    if b < 40:
        return 0.28
    if b < 52:
        return 0.06
    if b < 56:
        return 0.45
    if b < 72:
        return 0.34
    if b < 88:
        return 0.42
    return 0.12


ts_ = np.arange(NF + 2) / FPS
YAW = np.cumsum([section_speed(t) for t in ts_]) / FPS
PITCH = 0.95 + 0.25 * np.sin(ts_ * 0.21) + 0.1 * np.sin(ts_ * 0.53)
ROLL = 0.18 * np.sin(ts_ * 0.13)


def dist_at(t):
    b = t / BAR
    d = 3.4
    if 40 <= b < 52:  # Break: Flug in den Torus hinein
        u = (b - 40) / 12
        d = 3.4 - 1.9 * (0.5 - 0.5 * math.cos(math.pi * u))
    elif 52 <= b < 56:
        u = (b - 52) / 4
        d = 1.5 + 1.9 * u ** 2
    elif b >= 88:
        d = 3.4 + 2.5 * ((b - 88) / 12) ** 1.5
    elif b < 8:
        d = 5.5 - 2.1 * (b / 8) ** 0.7
    return d


# ---------------- Torus-Gitter ----------------
I, J = 24, 9
Rr, rr = 1.0, 0.43


def vid(i, j):
    return (i % I) * J + (j % J)


VPC = np.array([(7 * i + 4 * j) % 12 for i in range(I) for j in range(J)])
UV = np.array([(2 * math.pi * i / I, 2 * math.pi * j / J) for i in range(I) for j in range(J)])
TRIS, TRI_CH = [], []
for i in range(I):
    for j in range(J):
        TRIS.append((vid(i, j), vid(i + 1, j), vid(i + 1, j - 1)))
        TRI_CH.append(((7 * i + 4 * j) % 12, "m"))
        TRIS.append((vid(i, j), vid(i + 1, j), vid(i, j + 1)))
        TRI_CH.append(((7 * i + 4 * j) % 12, "M"))
TRIS = np.array(TRIS)
EDGES = {}
for k, (a, b, c) in enumerate(TRIS):
    for e in ((a, b), (b, c), (a, c)):
        EDGES.setdefault(tuple(sorted(e)), []).append(k)
EDGE_LIST = np.array(list(EDGES.keys()))
CH_TRIS = {}
for k, ch in enumerate(TRI_CH):
    CH_TRIS.setdefault(ch, []).append(k)


def torus_xyz(breath=0.0):
    u, v = UV[:, 0], UV[:, 1]
    r = rr * (1 + breath)
    return np.stack([(Rr + r * np.cos(v)) * np.cos(u), (Rr + r * np.cos(v)) * np.sin(u), r * np.sin(v)], 1)


def rot(yaw, pitch, roll):
    cy, sy, cp, sp, cr, sr_ = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch), math.cos(roll), math.sin(roll)
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    Ry = np.array([[cr, 0, sr_], [0, 1, 0], [-sr_, 0, cr]])
    return Ry @ Rx @ Rz


def rotate_about(p, a, b, ang):
    """Punkt p um die Achse a->b drehen (Rodrigues)."""
    k = (b - a) / (np.linalg.norm(b - a) + 1e-9)
    v = p - a
    return a + v * math.cos(ang) + np.cross(k, v) * math.sin(ang) + k * np.dot(k, v) * (1 - math.cos(ang))


# ---------------- Farben ----------------
def hsv(h, s, v):
    h = h % 1.0
    i = int(h * 6)
    f = h * 6 - i
    p, q, t_ = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    return [(v, t_, p), (q, v, p), (p, v, t_), (p, q, v), (t_, p, v), (v, p, q)][i % 6]


def fifths_hue(root):
    """Farbkreis = Quintenzirkel."""
    return ((root * 7) % 12) / 12


PALETTES = {  # (Linien, Akzent, Hintergrund)
    "intro": ((0.3, 0.8, 1.0), (0.7, 0.4, 1.0), (0.02, 0.02, 0.05)),
    "drop1a": ((0.3, 0.85, 1.0), (1.0, 0.3, 0.8), (0.02, 0.01, 0.04)),
    "drop1b": ((0.9, 0.3, 1.0), (0.3, 1.0, 0.9), (0.03, 0.0, 0.04)),
    "break": ((0.35, 0.45, 1.0), (0.75, 0.55, 1.0), (0.0, 0.0, 0.03)),
    "build": ((1.0, 0.85, 0.5), (1.0, 1.0, 1.0), (0.04, 0.03, 0.01)),
    "drop2": ((1.0, 0.35, 0.15), (1.0, 0.8, 0.2), (0.04, 0.0, 0.0)),
    "final": ((1.0, 1.0, 1.0), (1.0, 1.0, 1.0), (0.02, 0.0, 0.03)),
    "outro": ((0.6, 0.6, 0.7), (0.8, 0.8, 0.9), (0.01, 0.01, 0.015)),
}


def palette_name(b):
    if b < 8:
        return "intro"
    if b < 24:
        return "drop1a"
    if b < 40:
        return "drop1b"
    if b < 52:
        return "break"
    if b < 56:
        return "build"
    if b < 72:
        return "drop2"
    if b < 88:
        return "final"
    return "outro"


def palette(t, chord):
    b = t / BAR
    name = palette_name(b)
    line, acc, bg = PALETTES[name]
    if name == "final" and chord:
        h = fifths_hue(chord[0]) + 0.05 * math.sin(t * 2)
        line, acc = hsv(h, 0.75, 1.0), hsv(h + 0.5, 0.6, 1.0)
    # weicher Uebergang an Abschnittsgrenzen (0.5 Takte)
    for edge_b in (8, 24, 40, 52, 56, 72, 88):
        d = (b - edge_b) * BAR
        if 0 <= d < BAR / 2:
            pl, pa, pb = PALETTES[palette_name(edge_b - 0.01)]
            u = d / (BAR / 2)
            mixc = lambda x, y: tuple(x[k] * (1 - u) + y[k] * u for k in range(3))
            line, acc, bg = mixc(pl, line), mixc(pa, acc), mixc(pb, bg)
    return line, acc, bg


# ---------------- Zeit-Remapping fuer Post-FX (Ratchet / Tape-Stop) ----------------
def remap(t):
    squash, dim = 1.0, 1.0
    for kind, t0, d in POST:
        if not (t0 <= t < t0 + d):
            continue
        if kind == "ratchet":
            p = 0.0
            for ln in (d / 2, d / 4, d / 8, d / 16, d / 16):
                if t < t0 + p + ln:
                    return t0 + (t - t0 - p), 1.0, 1.0, True
                p += ln
        if kind == "tapestop":
            tau = d / 3
            x = t - t0
            u = x / d
            return t0 + tau * (1 - math.exp(-x / tau)), 1 - 0.85 * u ** 1.5, 1 - 0.8 * u, False
        if kind == "cantor":
            cell = int((t - t0) / d * 27)
            keep = all(c != "1" for c in np.base_repr(cell, 3).zfill(3))
            dim = 1.0 if keep else 0.08
    for a, b in MUTES:
        if a <= t < b:
            dim = 0.05
    return t, squash, dim, False


def cutoff_at(t):
    for t0, t1, fa, fb in FILTERS:
        if t0 <= t < t1:
            return fa * (fb / fa) ** ((t - t0) / (t1 - t0))
        if fb < fa and t >= t1:
            return fb
    return 20000


# ---------------- Zeichnen ----------------
def front_instances(pc, scr, depth, n=2):
    idx = np.nonzero(VPC == pc)[0]
    idx = idx[np.argsort(depth[idx])][:n]
    return idx


def draw_glow_circle(cr, x, y, r, col, a):
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, col[0], col[1], col[2], a)
    g.add_color_stop_rgba(0.35, col[0], col[1], col[2], a * 0.45)
    g.add_color_stop_rgba(1, col[0], col[1], col[2], 0)
    cr.set_source(g)
    cr.arc(x, y, r, 0, 2 * math.pi)
    cr.fill()


def text(cr, s, x, y, size, col, a=1.0, center=True, bold=False):
    cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)
    ext = cr.text_extents(s)
    xx = x - ext.width / 2 - ext.x_bearing if center else x
    cr.set_source_rgba(col[0], col[1], col[2], a)
    cr.move_to(xx, y)
    cr.show_text(s)


def render(t_real, fi):
    t, squash, dim, ratchet = remap(t_real)
    f = min(int(t * FPS), NF - 1)
    b = t / BAR
    chord, ch_t0, ci = chord_at(t)
    line, acc, bg = palette(t, chord)
    low, mid, high = LOW[f], MID[f], HIGH[f]

    # Kick-Huellkurve
    ki = last_before(list(KICKS), t) if False else bisect.bisect_right(KICKS, t) - 1
    k_tau = t - KICKS[ki] if ki >= 0 else 9
    kick = math.exp(-k_tau / 0.09) if k_tau < 1 else 0.0
    clap_i = bisect.bisect_right(CLAP_T, t) - 1
    clap = math.exp(-(t - CLAP_T[clap_i]) / 0.07) if clap_i >= 0 and t - CLAP_T[clap_i] < 0.6 else 0.0
    imp_i = bisect.bisect_right(IMP_T, t) - 1
    imp_tau = t - IMP_T[imp_i] if imp_i >= 0 else 9
    imp = math.exp(-imp_tau / 0.35) if imp_tau < 3 else 0.0

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    # Hintergrund: radialer Verlauf
    g = cairo.RadialGradient(W / 2, H * 0.45, 50, W / 2, H * 0.45, H * 0.8)
    g.add_color_stop_rgb(0, bg[0] * 3 + 0.02 * low, bg[1] * 3, bg[2] * 3 + 0.03 * low)
    g.add_color_stop_rgb(1, bg[0], bg[1], bg[2])
    cr.set_source(g)
    cr.paint()

    # riesiges flaches Tonnetz im Hintergrund (driftet, zeigt denselben Akkord)
    sp_, ang0 = 150.0, 0.12 * math.sin(t * 0.05) + 0.3
    ox, oy = (t * 22) % sp_, (t * 9) % (sp_ * 0.866)
    ca_, sa_ = math.cos(ang0), math.sin(ang0)
    def gp(i, j):
        x0 = (i + 0.5 * j) * sp_ - ox
        y0 = j * sp_ * 0.866 - oy
        return W / 2 + x0 * ca_ - y0 * sa_, H / 2 + x0 * sa_ + y0 * ca_
    cr.set_line_width(1.2)
    for i in range(-9, 10):
        for j in range(-12, 13):
            pc0 = (7 * i + 4 * j) % 12
            a0, b0, c0, d0 = gp(i, j), gp(i + 1, j), gp(i, j + 1), gp(i + 1, j - 1)
            if chord and (pc0, chord[1]) == tuple(chord):
                third = d0 if chord[1] == "m" else c0
                cr.move_to(*a0); cr.line_to(*b0); cr.line_to(*third); cr.close_path()
                cr.set_source_rgba(acc[0], acc[1], acc[2], 0.07 + 0.08 * kick)
                cr.fill()
            cr.set_source_rgba(line[0], line[1], line[2], 0.05 + 0.04 * mid)
            cr.move_to(*a0); cr.line_to(*b0); cr.move_to(*a0); cr.line_to(*c0); cr.move_to(*b0); cr.line_to(*c0)
            cr.stroke()

    # Projektion
    fr = min(f, len(YAW) - 1)
    Rm = rot(YAW[fr] + 0.15 * imp, PITCH[fr], ROLL[fr])
    xyz = torus_xyz(breath=0.12 * low + 0.05 * kick) @ Rm.T
    D = dist_at(t)
    focal = 1180 * (1 + 0.05 * kick + 0.08 * imp)
    cx, cy = W / 2, H * 0.40
    z = xyz[:, 2] + D
    z = np.maximum(z, 0.15)
    scr = np.stack([cx + focal * xyz[:, 0] / z, cy + focal * xyz[:, 1] / z], 1)
    depth = z
    dn = (depth - depth.min()) / (np.ptp(depth) + 1e-9)  # 0 = vorne

    # aktive Akkord-Dreiecke + Klapp-Animation
    active = set(CH_TRIS.get(tuple(chord), [])) if chord else set()
    flip = None
    if chord and ci > 0 and t - ch_t0 < 0.22:
        prev = (CHORDS[ci - 1][2], CHORDS[ci - 1][3])
        op = op_between(prev, tuple(chord))
        if op:
            flip = (prev, (t - ch_t0) / 0.22)

    tri_depth = depth[TRIS].mean(1)
    order = np.argsort(-tri_depth)
    base_alpha = 0.55 + 0.45 * MID[f]
    for k in order:
        if k not in active:
            continue
        a_, b_, c_ = TRIS[k]
        front = 1 - dn[[a_, b_, c_]].mean()
        col = hsv(fifths_hue(chord[0]), 0.65, 1.0) if palette_name(b) == "final" else acc
        pts = scr[[a_, b_, c_]].copy()
        if flip is not None:
            u = flip[1]
            # Nachbar-Dreieck des alten Akkords mit gemeinsamer Kante finden und hinueberklappen
            for e in ((a_, b_, c_), (b_, c_, a_), (a_, c_, b_)):
                key = tuple(sorted(e[:2]))
                for nb in EDGES.get(key, []):
                    if nb != k and TRI_CH[nb] == tuple(flip[0]):
                        old3 = [v for v in TRIS[nb] if v not in e[:2]][0]
                        p3 = rotate_about(xyz[old3], xyz[e[0]], xyz[e[1]], math.pi * min(1, u))
                        zz = max(p3[2] + D, 0.15)
                        sp3 = np.array([cx + focal * p3[0] / zz, cy + focal * p3[1] / zz])
                        new3 = scr[e[2]]
                        w = max(0, (u - 0.7) / 0.3)
                        pts = np.array([scr[e[0]], scr[e[1]], sp3 * (1 - w) + new3 * w])
                        break
                else:
                    continue
                break
        cr.move_to(*pts[0])
        cr.line_to(*pts[1])
        cr.line_to(*pts[2])
        cr.close_path()
        cr.set_source_rgba(col[0], col[1], col[2], (0.12 + 0.6 * front ** 2) * base_alpha * (1 + 0.6 * kick))
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.5 * front)
        cr.set_line_width(1.5 + 2 * front)
        cr.stroke()

    # Gitterkanten
    e_depth = (dn[EDGE_LIST[:, 0]] + dn[EDGE_LIST[:, 1]]) / 2
    flash = 0.35 * clap + 0.5 * imp
    for (a_, b_), ed in zip(EDGE_LIST, e_depth):
        fa = (1 - ed) ** 1.6
        cr.set_source_rgba(min(1, line[0] + flash), min(1, line[1] + flash), min(1, line[2] + flash),
                           0.08 + 0.55 * fa * (0.6 + 0.4 * mid))
        cr.set_line_width(0.6 + 2.2 * fa)
        cr.move_to(*scr[a_])
        cr.line_to(*scr[b_])
        cr.stroke()

    # Punkte: Akkordtoene leuchten
    ctones = set()
    if chord:
        r0 = chord[0]
        ctones = {r0, (r0 + (3 if chord[1] == "m" else 4)) % 12, (r0 + 7) % 12}
    for v in np.argsort(-depth):
        fa = 1 - dn[v]
        rad = 1.5 + 4 * fa
        if VPC[v] in ctones:
            draw_glow_circle(cr, scr[v][0], scr[v][1], rad * 5, acc, 0.35 * fa)
        cr.set_source_rgba(1, 1, 1, 0.25 + 0.7 * fa)
        cr.arc(scr[v][0], scr[v][1], rad, 0, 2 * math.pi)
        cr.fill()

    # Arpeggio-Noten: Blitz + Partikel
    for ei in recent(ARP_T, t, 0.55):
        _, t0, m = ARP[ei]
        tau = t - t0
        pc = (m - 57) % 12
        for v in front_instances(pc, scr, depth, n=2):
            x, y = scr[v]
            if tau < 0.18:
                draw_glow_circle(cr, x, y, 40 + 60 * (1 - tau / 0.18), (1, 1, 1), 0.7 * (1 - tau / 0.18))
            for p in range(9):
                ang = (ei * 2.399963 + p * 2 * math.pi / 9)
                sp = 260 + 220 * ((p * PHI + ei) % 1)
                px = x + math.cos(ang) * sp * tau
                py = y + math.sin(ang) * sp * tau + 380 * tau * tau
                al = max(0, 1 - tau / 0.55)
                cr.set_source_rgba(acc[0], acc[1], acc[2], al * 0.9)
                cr.arc(px, py, 2.2 * (1 + (m - 69) / 24), 0, 2 * math.pi)
                cr.fill()

    # Top-Lead: expandierende Ringe + Melodie-Pfad
    prev_xy = None
    for ei in recent(TOP_T, t, 1.6):
        _, t0, m, dur = TOP[ei]
        tau = t - t0
        pc = (m - 57) % 12
        v = front_instances(pc, scr, depth, n=1)[0]
        x, y = scr[v]
        al = max(0, 1 - tau / 1.6)
        for rr_ in range(3):
            rad = 30 + 420 * (tau / 1.6) ** 0.6 + rr_ * 26
            cr.set_source_rgba(line[0], line[1], line[2], al * (0.8 - 0.25 * rr_))
            cr.set_line_width(4 - rr_)
            cr.arc(x, y, rad, 0, 2 * math.pi)
            cr.stroke()
        if prev_xy is not None:
            cr.set_source_rgba(1, 1, 1, al * 0.6)
            cr.set_line_width(2.5)
            cr.move_to(*prev_xy)
            cr.line_to(x, y)
            cr.stroke()
        prev_xy = (x, y)
        if tau < dur:
            text(cr, NAMES[(pc + TR) % 12], x, y - 60, 46, (1, 1, 1), 0.9 * (1 - tau / dur), bold=True)

    # Glides: Laser, der mit der Tonhoehe ueber den Screen faehrt
    for _, t0, m0, m1, dur in GLIDE:
        if t0 <= t < t0 + dur + 0.3:
            u = min(1, (t - t0) / (dur * 0.85))
            m = m0 + (m1 - m0) * u
            y = H * 0.85 - (m - 60) / 30 * H * 0.7
            al = 1 if t < t0 + dur else 1 - (t - t0 - dur) / 0.3
            for k in range(14):
                yy = y + k * 7 * (1 if m1 > m0 else -1)
                cr.set_source_rgba(acc[0], acc[1], acc[2], al * 0.7 * (1 - k / 14))
                cr.set_line_width(5 - k * 0.3)
                cr.move_to(0, yy)
                cr.line_to(W, yy)
                cr.stroke()

    # Tritonus-Stabs: roter Blitz zwischen Grundton und Tritonus
    stab_amt = 0.0
    for _, t0, m in STAB:
        tau = t - t0
        if 0 <= tau < 0.25:
            stab_amt = max(stab_amt, 1 - tau / 0.25)
            pc = (m - 57) % 12
            va = front_instances(pc, scr, depth, 1)[0]
            vb = front_instances((pc + 6) % 12, scr, depth, 1)[0]
            pa, pb = scr[va], scr[vb]
            for strand in range(3):
                cr.set_source_rgba(1, 0.15 + 0.3 * strand / 3, 0.1, (1 - tau / 0.25) * (1 - strand * 0.25))
                cr.set_line_width(6 - strand * 2)
                cr.move_to(*pa)
                for s in range(1, 12):
                    u = s / 12
                    jx = 40 * math.sin(s * 12.9898 + t0 * 78.233 + strand)
                    jy = 40 * math.sin(s * 4.1414 + t0 * 39.346 + strand * 2)
                    cr.line_to(pa[0] + (pb[0] - pa[0]) * u + jx, pa[1] + (pb[1] - pa[1]) * u + jy)
                cr.line_to(*pb)
                cr.stroke()

    # Kick-Schockwelle
    if k_tau < 0.5:
        cr.set_source_rgba(line[0], line[1], line[2], 0.5 * (1 - k_tau / 0.5))
        cr.set_line_width(3 + 6 * (1 - k_tau / 0.5))
        cr.arc(cx, cy, 120 + 1500 * k_tau, 0, 2 * math.pi)
        cr.stroke()
    if imp_tau < 1.2:
        cr.set_source_rgba(1, 1, 1, 0.8 * (1 - imp_tau / 1.2))
        cr.set_line_width(10 * (1 - imp_tau / 1.2) + 1)
        cr.arc(cx, cy, 60 + 1400 * imp_tau ** 0.7, 0, 2 * math.pi)
        cr.stroke()

    # Zeno-Roll: Streifen pro Schlag, immer dichter
    zi = bisect.bisect_right(ZENO_HITS, t) - 1
    if zi >= 0 and t - ZENO_HITS[zi] < 0.12:
        a = 1 - (t - ZENO_HITS[zi]) / 0.12
        yy = (zi * 997) % H
        cr.set_source_rgba(1, 1, 1, 0.5 * a)
        cr.rectangle(0, yy, W, 6 + 30 * a)
        cr.fill()

    # Live-Wellenform
    a0i = int(t * sr)
    wv = au[a0i:a0i + 2048]
    if len(wv) == 2048:
        xs = np.linspace(60, W - 60, 256)
        ys = H * 0.70 + wv[::8] * 170 * (0.6 + 0.6 * kick)
        cr.set_source_rgba(acc[0], acc[1], acc[2], 0.75)
        cr.set_line_width(2.5)
        cr.move_to(xs[0], ys[0])
        for x_, y_ in zip(xs[1:], ys[1:]):
            cr.line_to(x_, y_)
        cr.stroke()

    # ---------- HUD auf eigener Ebene (bleibt scharf) ----------
    hsurf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    scene_cr, cr = cr, cairo.Context(hsurf)
    hud = (0.85, 0.9, 1.0)
    text(cr, " ".join(TITLE), W / 2, 110, 40, hud, 0.85, bold=True)
    text(cr, "Z12  ·  <P, L, R>  ·  TORUS 24x9", W / 2, 160, 24, hud, 0.45)
    if chord:
        nm = cname(chord)
        pop = 1 + 0.25 * math.exp(-(t - ch_t0) / 0.12)
        text(cr, nm, W / 2, H * 0.80, 190 * pop, (1, 1, 1), 0.95, bold=True)
        if ci > 0:
            prev = (CHORDS[ci - 1][2], CHORDS[ci - 1][3])
            op = op_between(prev, tuple(chord))
            s = f"{op}({cname(prev)}) = {nm}" if op else f"{cname(prev)} -> {nm}"
            text(cr, s, W / 2, H * 0.80 + 80, 44, acc, 0.85)
            if op:
                text(cr, op, W / 2, H * 0.80 - 210, 90, acc, 0.9 * math.exp(-(t - ch_t0) / 0.4), bold=True)
    text(cr, f"BAR {min(100, int(b) + 1):03d}/100   {BPM:g} BPM   {NAMES[TR % 12]}-MOLL", W / 2, H - 90, 26, hud, 0.55)
    # Abschnittstitel
    for b0, b1, title in SECTIONS:
        d = (b - b0) * BAR
        if 0 <= d < 2.2:
            a = min(1, d / 0.15) * min(1, (2.2 - d) / 0.6)
            text(cr, title, W / 2, H * 0.585, 54, (1, 1, 1), a, bold=True)
    # Titel / Abspann
    if t_real < 3.0:
        a = min(1, t_real / 0.4) * min(1, (3.0 - t_real) / 0.8)
        jit = 8 * math.sin(t_real * 90) * (1 - t_real / 3)
        text(cr, TITLE, W / 2 + jit, H * 0.5, 150 if len(TITLE) <= 8 else 1200 / len(TITLE), (1, 1, 1), a, bold=True)
    if t_real > EV["end"] - 4:
        a = min(1, (t_real - EV["end"] + 4) / 1.0)
        text(cr, TITLE, W / 2, H * 0.47, 130 if len(TITLE) <= 8 else 1040 / len(TITLE), (1, 1, 1), a, bold=True)
        text(cr, "  ·  ".join(" ".join(w) for w in EV.get("words", ["LRL", "RLP"])) + "  ·  L P L P L P", W / 2, H * 0.47 + 80, 34, hud, a * 0.8)

    # ---------- Post: Glow, Aberration, Blur (Filter), Grain ----------
    img = np.ndarray((H, W, 4), np.uint8, surf.get_data())[:, :, :3].astype(np.float32) / 255  # BGR
    small = cv2.resize(img, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    glow = cv2.GaussianBlur(small, (0, 0), 6)
    glow = cv2.resize(glow, (W, H), interpolation=cv2.INTER_LINEAR)
    img = img + glow * (0.9 + 0.8 * mid + 0.8 * kick)
    # Kick-Zoom + Shake
    sc = 1 + (0.035 * kick + 0.06 * imp) * VI
    sx = 14 * imp * math.sin(t * 80) + 4 * kick * math.sin(t * 131)
    sy = 14 * imp * math.cos(t * 70) + 4 * kick * math.cos(t * 97)
    M = np.array([[sc, 0, (1 - sc) * W / 2 + sx], [0, sc * squash, (1 - sc * squash) * H / 2 + sy]], np.float32)
    img = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_CONSTANT)
    # chromatische Aberration
    ca = int((3 + 14 * kick + 30 * stab_amt + 20 * imp) * VI)
    img[:, :, 2] = np.roll(img[:, :, 2], ca, axis=1)
    img[:, :, 0] = np.roll(img[:, :, 0], -ca, axis=1)
    if stab_amt > 0:
        img[:, :, 2] += 0.25 * stab_amt
    # Glitch-Streifen bei Clap / Ratchet
    if clap > 0.5 / VI or ratchet:
        rng = np.random.default_rng(fi)
        for _ in range(6 if ratchet else 3):
            y0 = int(rng.integers(0, H - 80))
            hgt = int(rng.integers(8, 70))
            img[y0:y0 + hgt] = np.roll(img[y0:y0 + hgt], int(rng.integers(-90, 90)), axis=1)
    # Filter-Sweep -> Unschaerfe + Abdunkeln
    cut = cutoff_at(t)
    if cut < 12000:
        u = 1 - (math.log(cut) - math.log(180)) / (math.log(12000) - math.log(180))
        sig = 1 + 22 * u ** 1.3
        img = cv2.GaussianBlur(img, (0, 0), sig)
        img *= 1 - 0.65 * u
    # HUD-Ebene (premultiplied BGRA) ueber das Bild legen, mit leichtem Glow
    hb = np.ndarray((H, W, 4), np.uint8, hsurf.get_data()).astype(np.float32) / 255
    halpha = hb[:, :, 3:4]
    hglow = cv2.resize(cv2.GaussianBlur(cv2.resize(hb[:, :, :3], (W // 4, H // 4)), (0, 0), 4), (W, H))
    img = img * (1 - halpha) + hb[:, :, :3] + hglow * 0.6
    # Vignette, Scanlines, Grain
    img *= VIGNETTE
    img *= SCAN
    rng = np.random.default_rng(fi * 7 + 1)
    img += (rng.standard_normal((H // 2, W // 2, 1)).astype(np.float32).repeat(2, 0).repeat(2, 1)) * 0.025
    img *= dim
    if imp_tau < 0.06:
        img = img * 0.4 + 0.6
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


yy, xx = np.mgrid[0:H, 0:W]
VIGNETTE = (1 - 0.55 * (((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.45) / (H * 0.7)) ** 2)).clip(0.2, 1)[..., None].astype(np.float32)
SCAN = (0.94 + 0.06 * (yy % 3 == 0)).astype(np.float32)[..., None]


def render_chunk(args):
    f0, f1, path = args
    p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                          "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        p.stdin.write(render(fi / FPS, fi).tobytes())
    p.stdin.close()
    p.wait()
    return path


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "preview":
        for ts in sys.argv[2:]:
            t = float(ts)
            cv2.imwrite(f"/tmp/tz_{ts}.jpg", render(t, int(t * FPS)), [cv2.IMWRITE_JPEG_QUALITY, 85])
            print("ok", ts)
    else:
        from multiprocessing import Pool
        nw = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        tmp = os.path.join(ROOT, ".vis_tmp")
        os.makedirs(tmp, exist_ok=True)
        step = math.ceil(NF / nw)
        jobs = [(k, min(k + step, NF), os.path.join(tmp, f"seg{k:06d}.mp4")) for k in range(0, NF, step)]
        with Pool(nw) as pool:
            segs = pool.map(render_chunk, jobs)
        lst = os.path.join(tmp, "list.txt")
        open(lst, "w").write("".join(f"file '{s}'\n" for s in segs))
        out = os.path.join(ROOT, VP.get("name", "tonnetz") + "_visuals.mp4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-i", os.path.join(ROOT, WAVNAME), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "320k", "-shortest", out], check=True)
        print("fertig:", out)
