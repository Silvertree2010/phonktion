import numpy as np, sys
W = H = 1080
n = 512
r = np.arange(n)[:, None]; k = np.arange(n)[None, :]
tri = ((k & ~r) == 0) & (k <= r)  # Lucas: C(r,k) ungerade
img = np.zeros((H, W, 3))
top, size = 90, 760
for y in range(size):
    row = int(y / size * (n - 1))
    xs = np.nonzero(tri[row, : row + 1])[0]
    if len(xs) == 0: continue
    px = (W / 2 + (xs - row / 2) * (size / n) * 1.15).astype(int)
    u = y / size
    for dx in range(2):
        img[top + y, np.clip(px + dx, 0, W - 1)] = [0.25 + 0.75 * u, 0.85 - 0.65 * u, 1.0 - 0.85 * u]
sys.stdout.buffer.write(b"P6 %d %d 255\n" % (W, H) + (np.clip(img, 0, 1) * 255).astype(np.uint8).tobytes())
