"""Tonnetz-Gitter: Tonklassen auf Dreiecksgitter (Quinten horizontal, grosse Terzen schraeg), Pfad Am-F-Dm-Bb hervorgehoben."""
import numpy as np, sys
W = H = 1080
img = np.zeros((H, W, 3))
s = 92.0
def pos(i, j): return np.array([W / 2 + (i + 0.5 * j) * s, 470 - j * s * 0.866])
def line(p, q, col, w=2):
    n = int(np.linalg.norm(q - p)) + 1
    for t in np.linspace(0, 1, n):
        x, y = (p + (q - p) * t).astype(int)
        img[max(0, y - w):y + w, max(0, x - w):x + w] = col
def tri(a, b, c, col):
    xs = np.arange(W)[None, :]; ys = np.arange(H)[:, None]
    def side(p, q): return (xs - q[0]) * (p[1] - q[1]) - (p[0] - q[0]) * (ys - q[1])
    d1, d2, d3 = side(a, b), side(b, c), side(c, a)
    m = ~(((d1 < 0) | (d2 < 0) | (d3 < 0)) & ((d1 > 0) | (d2 > 0) | (d3 > 0)))
    img[m] = img[m] * 0.3 + np.array(col) * 0.7
# Tonklasse am Gitterpunkt (i, j) = 7i + 4j (mod 12), A = 0
# Akkord-Dreiecke: Moll = (i,j),(i+1,j),(i+1,j-1)? -> wir faerben die Dreiecke des Pfads
def pc(i, j): return (7 * i + 4 * j) % 12
def find_tri(root, q):
    for i in range(-6, 7):
        for j in range(-5, 6):
            if q == "m":  # Moll: r, r+7, r+3  -> (i,j),(i+1,j),(i+1,j-1)
                if pc(i, j) == root: return pos(i, j), pos(i + 1, j), pos(i + 1, j - 1)
            else:  # Dur: r, r+7, r+4 -> (i,j),(i+1,j),(i,j+1)
                if pc(i, j) == root and abs(i) < 3 and abs(j) < 3: return pos(i, j), pos(i + 1, j), pos(i, j + 1)
# Pfad auf dem Gitter: benachbarte Dreiecke teilen eine Kante (L, R, L)
TRIS = [((0, 0), (1, 0), (1, -1)),     # Am  = A E C
        ((0, -1), (0, 0), (1, -1)),    # F   = F A C   (L: teilt A-C)
        ((-1, 0), (0, 0), (0, -1)),    # Dm  = D A F   (R: teilt A-F)
        ((-1, -1), (-1, 0), (0, -1))]  # Bb  = Bb D F  (L: teilt D-F)
cols = [(0.35, 0.85, 1.0), (0.6, 0.6, 0.9), (0.85, 0.45, 0.6), (1.0, 0.33, 0.25)]
for t, c in zip(TRIS, cols):
    tri(*[pos(*v) for v in t], c)
for i in range(-7, 8):
    for j in range(-5, 6):
        p = pos(i, j)
        if not (0 < p[0] < W and 40 < p[1] < 820): continue
        u = p[0] / W
        col = (0.3 + 0.6 * u, 0.7 - 0.4 * u, 0.9 - 0.7 * u)
        for q in (pos(i + 1, j), pos(i, j + 1), pos(i + 1, j - 1)):
            if 0 < q[0] < W and 40 < q[1] < 820: line(p, q, np.array(col) * 0.55, 1)
        y, x = p.astype(int)[::-1]
        img[y - 6:y + 6, x - 6:x + 6] = col
sys.stdout.buffer.write(b"P6 %d %d 255\n" % (W, H) + (np.clip(img, 0, 1) * 255).astype(np.uint8).tobytes())
