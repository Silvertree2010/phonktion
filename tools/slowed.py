"""Super-Slowed-Version: Tape-Style (Tempo und Tonhoehe zusammen, Faktor 0.797 wie bei ECLIPSER) + Chaos-Hall."""
import sys
import numpy as np, scipy.io.wavfile as wf, scipy.signal as ss
src, dst = sys.argv[1], sys.argv[2]
sr, x = wf.read(src); x = x.astype(float) / 32768
F = 0.797
x = ss.resample_poly(x, 1000, int(1000 * F), axis=0)  # mehr Samples bei gleicher SR = langsamer + tiefer
r = 3.99999; v = 0.271828; n = int(3.2 * sr); ir = np.empty((n, 2))
for c in range(2):
    for i in range(n):
        v = r * v * (1 - v); ir[i, c] = 2 * v - 1
t = np.arange(n) / sr
ir *= np.exp(-t / 0.9)[:, None]; ir[: int(0.03 * sr)] = 0
sos = ss.butter(2, [200, 5000], "bandpass", fs=sr, output="sos")
wet = np.stack([ss.fftconvolve(ss.sosfilt(sos, x[:, c]), ir[:, c])[: len(x)] for c in range(2)], 1)
y = x + 0.008 * wet
y /= np.abs(y).max()
y = np.tanh(1.5 * y) / np.tanh(1.5) * 0.97
wf.write(dst, sr, (y * 32767).astype(np.int16))
print("Dauer", round(len(y) / sr, 1), "s")
