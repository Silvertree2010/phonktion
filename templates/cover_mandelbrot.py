import numpy as np, sys
W = H = 1080
x = np.linspace(-2.25, 0.75, W); y = np.linspace(-1.35, 1.65, H) - 0.15
C = x[None, :] + 1j * y[:, None]
Z = np.zeros_like(C); it = np.zeros(C.shape); alive = np.ones(C.shape, bool)
for i in range(200):
    Z[alive] = Z[alive] ** 2 + C[alive]
    esc = alive & (np.abs(Z) > 4)
    it[esc] = i + 1 - np.log2(np.log2(np.abs(Z[esc])))
    alive &= ~esc
v = np.where(alive, 0, np.sqrt(it / 200))
v = np.clip(v * 1.8, 0, 1)
u = np.linspace(0, 1, W)[None, :]
img = np.stack([v * (0.3 + 0.9 * u), v * (0.9 - 0.6 * u), v * (1 - 0.8 * u)], -1)
edge = alive & ~np.roll(alive, 1, 0) | alive & ~np.roll(alive, 1, 1)
img[edge] = [1, 0.35, 0.25]
img[H - 260:] *= 0.15
sys.stdout.buffer.write(b"P6 %d %d 255\n" % (W, H) + (np.clip(img, 0, 1) * 255).astype(np.uint8).tobytes())
