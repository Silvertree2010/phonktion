#!/usr/bin/env python3
"""phonktion: einen Mathe-Phonk-Track (plus Cover, Video, optional Slowed + Visuals) in einem Rutsch bauen.

Beispiel:
  make.py --theme tonnetz --intensity 8 --key F# --bpm 150 --seed 3 --title "Hexagon" --slowed --visuals
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(SKILL, "templates")
TOOLS = os.path.join(SKILL, "tools")
NOTES = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8,
         "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11, "H": 11}
THEMES = {  # Original-Tonart, Original-BPM, Original-wav, Untertitel Cover
    "bifurkation": ("D#", 144, "x → r·x·(1−x)"),
    "sierpinski": ("F#", 144, "C(n,k) mod 2"),
    "mandelbrot": ("G#", 144, "z → z² + c"),
    "tonnetz": ("A", 152, "⟨P, L, R⟩ auf dem Torus"),
}


SUB_HZ = {"bifurkation": 38.89, "sierpinski": 46.25, "mandelbrot": 51.91, "tonnetz": 55.0}  # Sub-Grundton Original


def run(cmd, env=None, cwd=None):
    print("$", " ".join(cmd) if isinstance(cmd, list) else cmd, flush=True)
    r = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    lines = [l for l in out.splitlines() if "Warn" not in l]
    print("\n".join(lines[-25:]))
    if r.returncode:
        sys.exit(f"Fehler in {cmd}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", required=True, choices=THEMES)
    ap.add_argument("--intensity", required=True, type=float, help="1 sanft ... 6 Standard ... 10 brutal")
    ap.add_argument("--key", help="Grundton der Moll-Tonart, z.B. A, F#, Eb (Standard: Original des Themas)")
    ap.add_argument("--bpm", type=float, help="Tempo (Standard: Original des Themas, 125-165 sinnvoll)")
    ap.add_argument("--seed", type=int, default=0, help="Variation der Mathe-Startwerte")
    ap.add_argument("--crush", type=float, help="Zusatz-Bitcrush 0..1 (Standard aus Intensitaet)")
    ap.add_argument("--title", help="Songtitel (Standard: Thema)")
    ap.add_argument("--out", help="Projektordner (Standard ~/Music/<titel>)")
    ap.add_argument("--slowed", action="store_true", help="zusaetzlich Super-Slowed-Version (Faktor 0.797)")
    ap.add_argument("--visuals", action="store_true", help="audio-synchrone Visuals 1080x1920 (nur Thema tonnetz)")
    a = ap.parse_args()

    orig_key, orig_bpm, subtitle = THEMES[a.theme]
    title = a.title or a.theme.upper()
    slug = "".join(c if c.isalnum() else "_" for c in title.lower()).strip("_")
    out = os.path.expanduser(a.out or f"~/Music/{slug}")
    src = os.path.join(out, "src")
    os.makedirs(src, exist_ok=True)
    transpose = 0
    if a.key:
        k = a.key.strip().upper().replace("♯", "#").replace("♭", "B")
        if k not in NOTES:
            sys.exit(f"Unbekannte Tonart {a.key}")
        transpose = (NOTES[k] - NOTES[orig_key]) % 12
        if SUB_HZ[a.theme] * 2 ** (transpose / 12) >= 73.4:  # Sub-Grundton zwischen D1 und D2 halten
            transpose -= 12
    params = {"intensity": a.intensity, "transpose": transpose, "seed": a.seed, "name": slug, "title": title}
    if a.bpm:
        params["bpm"] = a.bpm
    if a.crush is not None:
        params["crush"] = a.crush
    json.dump(params, open(os.path.join(src, "params.json"), "w"), indent=2)

    shutil.copy(os.path.join(T, a.theme + ".py"), os.path.join(src, "makesong.py"))
    shutil.copy(os.path.join(T, f"cover_{a.theme}.py"), os.path.join(src, "cover.py"))
    shutil.copy(os.path.join(TOOLS, "slowed.py"), os.path.join(src, "slowed.py"))
    env = dict(os.environ, MATHPHONK_PARAMS=json.dumps(params))
    if a.theme == "tonnetz":
        shutil.copy(os.path.join(T, "visual_tonnetz.py"), os.path.join(src, "visual.py"))
        env["DUMP_EVENTS"] = os.path.join(src, "events.json")

    wav = os.path.join(out, slug + ".wav")
    run([sys.executable, "-I", os.path.join(src, "makesong.py"), out], env=env)
    print("\n--- Messung ---")
    run([sys.executable, "-I", os.path.join(TOOLS, "full.py"), wav])
    run([sys.executable, "-I", os.path.join(TOOLS, "chroma.py"), wav])

    run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-b:a", "320k", os.path.join(out, slug + ".mp3")])
    # Cover
    ppm = os.path.join(src, ".cover.ppm")
    with open(ppm, "wb") as fh:
        subprocess.run([sys.executable, "-I", os.path.join(src, "cover.py")], stdout=fh, check=True)
    t_esc = title.replace("'", "").replace(":", "")
    s_esc = subtitle.replace("'", "").replace(":", "")
    fs = 110 if len(t_esc) <= 11 else int(1200 / len(t_esc))
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", ppm, "-vf",
         f"drawtext=text='{t_esc}':fontcolor=white:fontsize={fs}:x=(w-tw)/2:y=h-200:font=monospace,"
         f"drawtext=text='{s_esc}':fontcolor=0xbbbbbb:fontsize=44:x=(w-tw)/2:y=h-80:font=monospace",
         os.path.join(out, "cover.png")])
    os.remove(ppm)
    # Cover-Video mit Wellenform
    run(["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", os.path.join(out, "cover.png"), "-i", wav,
         "-filter_complex", "[1:a]showwaves=s=1080x140:mode=cline:colors=0xff5533|0x55ddff,format=rgba,"
         "colorkey=black:0.1[w];[0:v][w]overlay=0:830[v]", "-map", "[v]", "-map", "1:a", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-shortest",
         "-r", "30", os.path.join(out, slug + ".mp4")])
    if a.slowed:
        sw = os.path.join(out, slug + "_super_slowed.wav")
        run([sys.executable, "-I", os.path.join(src, "slowed.py"), wav, sw])
        run(["ffmpeg", "-loglevel", "error", "-y", "-i", sw, "-b:a", "320k", sw[:-4] + ".mp3"])
    if a.visuals:
        if a.theme != "tonnetz":
            print("HINWEIS: --visuals gibt es bisher nur fuer das Thema tonnetz, uebersprungen.")
        else:
            run([sys.executable, "-I", os.path.join(src, "visual.py"), "render", "15"], env=env)
            master = os.path.join(out, slug + "_visuals.mp4")
            run(["ffmpeg", "-loglevel", "error", "-y", "-i", master, "-c:v", "libx264", "-preset", "slow", "-crf", "22",
                 "-maxrate", "14M", "-bufsize", "28M", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
                 os.path.join(out, slug + "_visuals_tiktok.mp4")])
            shutil.rmtree(os.path.join(out, ".vis_tmp"), ignore_errors=True)
    print("\nFERTIG:", out)
    for f in sorted(os.listdir(out)):
        if not f.startswith("."):
            print("  ", f)


if __name__ == "__main__":
    main()
