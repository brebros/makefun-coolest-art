#!/usr/bin/env python3
"""Synthwave sunset — procedural 1024x1024 PNG, pure stdlib.

Coolest-art-01 entry. Deterministic output (fixed seed).
"""
import zlib
import struct
import os
import random
import time

W = H = 1024
HORIZON = 620  # y of horizon line

# ---- helpers -----------------------------------------------------------

def lerp(a, b, t):
    return a + (b - a) * t

def lerp3(c1, c2, t):
    return (
        lerp(c1[0], c2[0], t),
        lerp(c1[1], c2[1], t),
        lerp(c1[2], c2[2], t),
    )

def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))

def px(buf, x, y, c):
    """Blend-add a color into the float buffer at x,y (c in 0..255 floats)."""
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        for k in range(3):
            buf[i + k] = clamp(buf[i + k] + c[k], 0, 255)

def setpx(buf, x, y, c):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        buf[i] = c[0]; buf[i + 1] = c[1]; buf[i + 2] = c[2]

# ---- sky gradient (dark purple -> magenta -> orange at horizon) --------

def sky_color(y):
    t = y / HORIZON
    if t < 0.45:
        return lerp3((16, 8, 44), (96, 28, 108), t / 0.45)
    if t < 0.78:
        return lerp3((96, 28, 108), (210, 74, 90), (t - 0.45) / 0.33)
    return lerp3((210, 74, 90), (255, 150, 60), (t - 0.78) / 0.22)

# ---- sun with horizontal gaps ------------------------------------------

def sun_factor(x, y):
    """Return (core, gap_darken) for sun disk."""
    cx, cy = W / 2, 400
    r = 210
    dx = x - cx
    dy = y - cy
    d = (dx * dx + dy * dy) ** 0.5
    if d > r + 60:
        return 0.0, 0.0
    core = clamp((r + 26 - d) / 26.0)  # soft edge
    gap = 0.0
    if d < r:
        # bands: wider gaps toward the bottom of the disk
        rel = (y - (cy - r)) / (2 * r)  # 0 top .. 1 bottom
        band = 7.0
        frac = rel * band
        ph = frac - int(frac)
        thr = rel * 0.75  # gaps grow toward bottom
        if ph > 1.0 - thr * 0.9:
            gap = (ph - (1.0 - thr * 0.9)) / max(thr * 0.9, 1e-6)
    return core, gap

def sun_color():
    return (255, 210, 120)

# ---- mountains: layered ridges via midpoint displacement ----------------

def ridge(seed, base_y, amp, roughness):
    rnd = random.Random(seed)
    n = 257
    pts = [0.0] * n
    pts[0] = rnd.uniform(-amp, amp)
    pts[n - 1] = rnd.uniform(-amp, amp)
    step = n - 1
    scale = 1.0
    while step > 1:
        half = step // 2
        for i in range(half, n - 1, step):
            mid = (pts[i - half] + pts[i + half]) / 2 + rnd.uniform(-amp, amp) * scale
            pts[i] = mid
        step = half
        scale *= roughness
    return [base_y + v for v in pts]

def mountain_heights(x, pts):
    idx = x * (len(pts) - 1) / (W - 1)
    i0 = int(idx)
    frac = idx - i0
    return lerp(pts[i0], pts[min(i0 + 1, len(pts) - 1)], frac)

# ---- render --------------------------------------------------------------

def render():
    rnd = random.Random(1337)
    buf = [0.0] * (W * H * 3)

    # precompute mountains (3 layers, back to front)
    layers = [
        (ridge(11, HORIZON - 150, 60, 0.55), (86, 30, 110)),
        (ridge(22, HORIZON - 90, 80, 0.55), (58, 18, 86)),
        (ridge(33, HORIZON - 35, 100, 0.55), (34, 10, 60)),
    ]

    # stars (upper 55% of sky)
    stars = []
    for _ in range(340):
        sx = rnd.randrange(W)
        sy = int(rnd.randrange(int(HORIZON * 0.72)) * (1 - 0.5 * rnd.random()))
        bright = rnd.uniform(0.35, 1.0)
        stars.append((sx, sy, bright))

    sun = sun_color()
    horizon_glow = (255, 120, 60)

    for y in range(H):
        if y < HORIZON:
            sky = sky_color(y)
            row = y * W
            for x in range(W):
                c = sky
                # faint sun glow spill
                core, gap = sun_factor(x, y)
                if core > 0:
                    d = ((x - W / 2) ** 2 + (y - 400) ** 2) ** 0.5
                    if d < 420:
                        spill = clamp((420 - d) / 420) * 0.35
                        c = lerp3(c, horizon_glow, spill)
                setpx(buf, x, y, c)
                if core > 0:
                    sc = lerp3(c, sun, core)
                    if gap > 0:
                        sc = lerp3(sc, (110, 40, 90), gap * 0.85)
                    setpx(buf, x, y, sc)
            # stars on top of sky (skip near sun)
            for sx, sy, bright in stars:
                if sy == y:
                    dx = sx - W / 2
                    dy = sy - 400
                    if dx * dx + dy * dy > 480 ** 2:
                        v = 255 * bright
                        setpx(buf, sx, sy, (v, v, min(255, v + 20)))
        elif y == HORIZON:
            for x in range(W):
                setpx(buf, x, y, (255, 140, 70))
        else:
            # floor: dark gradient with cyan perspective grid
            depth = (y - HORIZON) / (H - HORIZON)
            base = lerp3((40, 12, 60), (8, 4, 24), depth * 0.9)
            row = y * W
            for x in range(W):
                setpx(buf, x, y, base)
            # horizontal grid lines: perspective spacing, thicker when closer
            t = depth
            period = max(3, int(6 + 40 * t))
            thick = 1 if t < 0.15 else (2 if t < 0.45 else 3)
            if (y - HORIZON) % period < thick:
                bright = (1.0 - t) * (1.0 - t)
                for x in range(W):
                    setpx(buf, x, y, (int(0 + 90 * bright), int(230 - 40 * t), int(235 - 30 * t)))
            # vertical grid lines converging to vanishing point
            vpx = W / 2
            for k in range(-14, 15):
                xg = vpx + k * (1 + t * t * 60)
                xi = int(xg)
                if abs(xg - xi) < 0.5 + t * 2 and 0 <= xi < W:
                    setpx(buf, xi, y, (0, 210, 220))
                    if xi + 1 < W:
                        setpx(buf, xi + 1, y, (0, 160, 170))
            # sun reflection column on grid
            for x in range(int(W / 2) - 40, int(W / 2) + 41):
                refl = clamp((1.0 - abs(x - W / 2) / 40.0)) * clamp(1.0 - depth) * 0.25
                if rnd.random() < 0.8:
                    i = (y * W + x) * 3
                    buf[i] = clamp(buf[i] + 200 * refl, 0, 255)
                    buf[i + 1] = clamp(buf[i + 1] + 90 * refl, 0, 255)
                    buf[i + 2] = clamp(buf[i + 2] + 40 * refl, 0, 255)

    # mountains drawn last over sky (and slightly over horizon)
    for pts, col in layers:
        for x in range(W):
            hy = mountain_heights(x, pts)
            for y in range(max(0, int(hy)), min(H, HORIZON + 30)):
                shade = 1.0
                # subtle top rim light
                if y < hy + 3:
                    shade = 1.35
                setpx(buf, x, y, (col[0] * shade, col[1] * shade, col[2] * shade))

    # nebula wisps in upper sky (soft radial blobs, deterministic)
    nebulas = []
    for _ in range(6):
        nx = rnd.randrange(100, W - 100)
        ny = rnd.randrange(40, 300)
        nr = rnd.uniform(80, 190)
        nc = rnd.choice([(150, 40, 160), (40, 130, 170), (120, 30, 120)])
        nebulas.append((nx, ny, nr, nc))

    # vignette
    for y in range(H):
        dy = (y - H / 2) / (H / 2)
        for x in range(W):
            dx = (x - W / 2) / (W / 2)
            v = 1.0 - 0.28 * (dx * dx + dy * dy)
            i = (y * W + x) * 3
            # nebula contribution (sky only, upper third)
            if y < HORIZON * 0.45:
                for nx, ny, nr, nc in nebulas:
                    dd = ((x - nx) ** 2 + (y - ny) ** 2) ** 0.5
                    if dd < nr:
                        s = (1.0 - dd / nr) ** 2 * 0.30
                        buf[i] = clamp(buf[i] * (1 - s) + nc[0] * s, 0, 255)
                        buf[i + 1] = clamp(buf[i + 1] * (1 - s) + nc[1] * s, 0, 255)
                        buf[i + 2] = clamp(buf[i + 2] * (1 - s) + nc[2] * s, 0, 255)
            # film grain: tiny deterministic hash noise, per 16px block
            g = ((x >> 4) * 73856093 ^ (y * 19349663)) & 0x0F
            grain = (g / 15.0 - 0.5) * 5.0
            buf[i] = clamp(buf[i] * v + grain, 0, 255)
            buf[i + 1] = clamp(buf[i + 1] * v + grain, 0, 255)
            buf[i + 2] = clamp(buf[i + 2] * v + grain, 0, 255)

    return buf

# ---- PNG writer ----------------------------------------------------------

def chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

def write_png(path, buf):
    raw = bytearray()
    for y in range(H):
        raw.append(0)  # filter type 0
        row = y * W * 3
        for v in buf[row:row + W * 3]:
            raw.append(int(v))
    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
           chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)

if __name__ == "__main__":
    t0 = time.time()
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    buf = render()
    size = write_png(os.path.join(outdir, "entry.png"), buf)
    print("wrote entry.png bytes=%d elapsed=%.2fs" % (size, time.time() - t0))
