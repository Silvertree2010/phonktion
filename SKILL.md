---
name: phonktion
description: Baut einen Mathe-Hardstyle/Drift-Phonk-Track (Stil-Referenz PINKY SMASH) komplett aus Formeln - Chaos/Bifurkation, Pascal/Sierpinski, Mandelbrot oder Tonnetz (Neo-Riemann-Akkorde) - mit einstellbarer Intensitaet, Tonart, Tempo, Variation; dazu Cover, Video, optional Super-Slowed und audio-synchrone Visuals. Nutzen bei "mach einen math phonk song", "noch einen song in die richtung", "/phonktion", Song mit Intensitaet X.
---

# phonktion

Ein Befehl erzeugt einen fertigen Track mit Projektordner. Die Engine stammt aus den Songs BIFURKATION, SIERPINSKI,
MANDELBROT und TONNETZ. Intensität 6 mit Original-Tonart/Tempo/Seed 0 reproduziert den jeweiligen Original-Song bitgenau.

## 1. Parameter klären

**Pflicht:** `intensity` (1–10) und `theme`. Fehlt eins davon, frage **einmal** mit AskUserQuestion und bündle dabei
alle offenen Punkte (Intensität, Thema, optional Tonart/Tempo/Visuals) in einer Fragerunde. Alles andere bekommt
Standardwerte, frag nicht weiter.

| Parameter | Werte | Standard |
|---|---|---|
| `--theme` | `bifurkation`, `sierpinski`, `mandelbrot`, `tonnetz` | – (Pflicht) |
| `--intensity` | 1 sanft … 6 Standard … 10 brutal | – (Pflicht) |
| `--key` | Moll-Grundton: A, F#, Eb, C … | Original des Themas |
| `--bpm` | 125–165 sinnvoll | Original (144, TONNETZ 152) |
| `--seed` | 0, 1, 2 … Variation der Mathe-Startwerte | 0 |
| `--crush` | 0..1 Zusatz-Bitcrush | aus Intensität |
| `--title` | Songtitel | Themenname |
| `--slowed` | Super-Slowed-Version (Faktor 0.797, wie PINKY SMASH) | aus |
| `--visuals` | 1080×1920-Visuals synchron zu jeder Note, **nur `tonnetz`**, ca. 6 min Render | aus |

**Was Intensität macht** (6 = genau die Original-Songs):

| | 1 | 6 | 10 |
|---|---|---|---|
| Kick-Verzerrung | ×0,6 | ×1,0 | ×1,3 |
| Limiter | weich, mehr Dynamik | wie Original | plattgedrückt |
| Sidechain | flach | 0,6 | 0,8 tief |
| Bitcrush Musikspur (>150 Hz) | aus | aus | 5 Bit + Sample-Hold ×4 |
| Visuals (Aberration, Glitch, Zoom) | ruhig | Original | chaotisch |

**Themen:**
- `bifurkation`: D# phrygisch. Melodie = Orbits der logistischen Abbildung (Periode 4→8→3→Chaos), Collatz-Bass, Zeno-Roll, Fibonacci-Hook, Cantor-Gate. Seed: π-Ziffern-Versatz und Collatz-Start.
- `sierpinski`: F# phrygisch. Pascal-Zeilen mod 7 als Melodie, Lucas-Pause, Thue-Morse-Bass, Rule-30-Rauschen, Lucas-Gate, Binär-Roll. Seed: Hook-Zeilen und Zeilen-Rotation.
- `mandelbrot`: G# phrygisch. Kardioid-Knospen 1/3→2/5→3/8, goldener Winkel, Boll-π-Roll, Shepard-Zoom, Julia-Gate, fraktal gesteuerter Bitcrush. Seed: goldene Folge und Crush-Muster.
- `tonnetz`: A-Moll, 152 BPM, **Akkordfolgen** aus Neo-Riemann-Wörtern (P/L/R), hexatonischer Break, Gray-Code-Arp, gehaltener Lead, Filter-Sweeps, Tritonus-Stabs, auf den Akkord gestimmte Kick. Seed wählt die Wörter: Drop 1 aus `LRL, RLR, LPL, LRP` (seed % 4), Drop 2 aus `RLP, LRL, RLR, PLR` (seed // 4 % 4). Das Thema ist am nächsten an PINKY SMASH, empfohlen als Standard.

## 2. Bauen

```bash
python -I ~/.claude/skills/phonktion/tools/make.py --theme tonnetz --intensity 8 --key F# --seed 1 --title "Hexagon" --slowed
```

Projektordner ist `~/Music/<titel>/` (oder `--out`). Darin liegen `<titel>.wav/.mp3/.mp4`, `cover.png`, optional
`_super_slowed.mp3` und `_visuals_tiktok.mp4`, außerdem `src/` mit dem Generator (`makesong.py` liest `src/params.json`
über die Umgebungsvariable `MATHPHONK_PARAMS`). Audio-Render ca. 10–25 s, mit Visuals ca. 6 min, dafür
`run_in_background` nutzen.

## 3. Prüfen, bevor du "fertig" sagst

Du kannst den Track nicht hören. Lies stattdessen die Messung, die `make.py` ausgibt:
- **Key/Chroma:** Die stärkste Tonklasse sollte der Grundton sein. Bei `tonnetz` mit anderen Seeds können Akkordtöne
  vorne liegen (z.B. G# bei F#m–A–C#m–E), das ist Harmonie, kein Fehler. Prüf es mit
  `tools/bass.py <bpm> <wav>`: Die Bassfolge muss der gedruckten Akkordfolge entsprechen.
- **Struktur-Balken:** Drops █, Break deutlich leiser (░/▒).
- **Crest-Faktor:** etwa 3,5–7 dB. **Sub-Peak:** 37–75 Hz. Weniger als 36 Hz hört man auf dem Handy nicht.
- Sag dem User ehrlich, dass du nur gemessen und nicht gehört hast.

## 4. Gelernte Regeln (nicht wieder brechen)

- **Nur harmonische Obertöne** in tonalen Leads. Unharmonische Verhältnisse (808-Cowbell 1.4836, φ-FM) machen Tonart-Matsch.
  Genau daran sind die ersten Versionen gescheitert (4/10).
- **Hook statt Zufall:** Mathe erzeugt einen festen, wiederholten Hook. Chaos nur als Effekt (Fills, Stutter).
- **Alle paar Takte ein Ereignis** (Gate, Ratchet, Tape-Stop, Beat-Switch, Fill, Swell), sonst wirkt der Track "langweilig".
- **Kick-Ausklang auf den Akkord-Grundton stimmen**, sonst überdeckt die Kick die Bassprogression.
- **Array-Längen:** Rauschpuffer mit `(n + 1) // 2` statt `n // 2` anlegen, sonst stürzt der Render bei krummen BPM ab.
- **Neue Stil-Referenz?** Tracks mit `yt-dlp` in ein eigenes Temp-Verzeichnis laden, mit `tools/full.py` und `tools/bass.py`
  vermessen (BPM, Tonart, Bandbalance, Crest, Pump, Bassfolge, Struktur), mit dem eigenen Track vergleichen und die
  Downloads danach löschen.

## 5. Hinweise

- Abspielen z.B. mit `mpv <datei>`. Keine Player oder Apps ungefragt starten.
- Gibt es ein persönliches Memory-System, den neuen Song dort mit Parametern vermerken.
