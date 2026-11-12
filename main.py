#!/usr/bin/env python3
"""coolest-art-01 v2 -- "Bioluminescent abyss"

Deep-sea dark blue-black scene, one large soft bioluminescent organism
(SDF dome body + flowing tapered tentacles). The organism IS the light
source: per-pixel Lambert shading from its core, inverse-square key glow
and cyan rim bounce, plankton points lit by proximity, layered depth
haze blending toward #1B1F3A, final grade + seeded grain.

Python 3 stdlib only. Deterministic (fixed seed). PNG written by hand.
"""
import os
import math
import random
import struct
import time
import zlib

W = H = 1024
SEED = 20261112
OUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "out")

# palette (sRGB 0..1)
KEY = (1.00, 0.4157, 0.1020)      # #FF6A1A
RIM = (0.1647, 0.9020, 1.0000)    # #2AE6FF
SHADOW = (0.0196, 0.0314, 0.0784) # #050814
HAZE = (0.1059, 0.1216, 0.2275)   # #1B1F3A
SEA_TOP = (0.0275, 0.0431, 0.0980)
SEA_BOT = (0.0392, 0.0549, 0.1059)
HI_W = (1.0000, 0.9137, 0.7843)   # #FFE9C8

CORE = (0.62 * W, 0.34 * H)       # light core, off-center
KEY_R = 120.0                     # key glow radius px

t_start = time.time()


# ---------- color space ----------
def s2l(c):
    """sRGB -> linear (per channel, 0..1)."""
    out = []
    for v in c:
        out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return out


def l2s(c):
    out = []
    for v in c:
        v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
        out.append(12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)
    return out


KEY_L = s2l(KEY)
RIM_L = s2l(RIM)
SHADOW_L = s2l(SHADOW)
HAZE_L = s2l(HAZE)
SEA_TOP_L = s2l(SEA_TOP)
SEA_BOT_L = s2l(SEA_BOT)
HI_W_L = s2l(HI_W)


# ---------- SDF: organism ----------
def sd_segment(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    L2 = vx * vx + vy * vy
    if L2 <= 1e-9:
        return math.hypot(wx, wy)
    t = (wx * vx + wy * vy) / L2
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    dx = wx - t * vx
    dy = wy - t * vy
    return math.hypot(dx, dy)


def dome_sdf(x, y):
    """Rounded superellipse dome; center above CORE, extends past top edge."""
    cx, cy = CORE[0], CORE[1] - 150.0
    a, b = 230.0, 290.0
    n = 2.6
    # superellipse: ((|dx|/a)^n + (dy/b)^n)^(1/n) - 1, with soft top
    dx = abs(x - cx) / a
    dy = (y - cy) / b
    if dy < 0.0:
        dy = -dy * 0.55  # flatter top (cut by frame anyway)
    d = (dx ** n + dy ** n) ** (1.0 / n) - 1.0
    return d * min(a, b)


def tentacles():
    """Build tentacle polylines: (points, base_width, tip_width)."""
    rng = random.Random(SEED + 7)
    tents = []
    specs = [
        (-0.30, 0.55, 26, 4),
        (-0.12, 0.72, 22, 3),
        (0.04, 0.88, 30, 5),
        (0.18, 0.62, 24, 4),
        (0.32, 0.78, 20, 3),
        (0.44, 0.50, 18, 3),
        (0.55, 0.66, 26, 4),
    ]
    for frac_x, length, width, amp in specs:
        x0 = CORE[0] + frac_x * 230.0
        y0 = CORE[1] + 95.0
        n = 22
        pts = []
        phase = rng.uniform(0, math.tau)
        sway = rng.uniform(0.7, 1.3)
        for i in range(n + 1):
            t = i / n
            x = x0 + math.sin(t * 2.4 * sway + phase) * amp * 14.0 * t + t * t * 30.0 * frac_x
            y = y0 + length * H * t
            pts.append((x, y))
        w0 = width * 0.85
        w1 = width * 0.12
        tents.append((pts, w0, w1))
    return tents


TENTS = tentacles()


def tent_sdf(x, y):
    d = 1e9
    for pts, w0, w1 in TENTS:
        n = len(pts)
        for i in range(n - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            t = (i + 0.5) / (n - 1)
            w = w0 + (w1 - w0) * t
            dd = sd_segment(x, y, ax, ay, bx, by) - w
            if dd < d:
                d = dd
    return d


# ---------- coarse distance field ----------
GN = 257  # grid resolution (GN x GN), bilinear upscaled
GRID = [[1e9] * GN for _ in range(GN)]
gx0, gy0 = -80.0, -80.0
gscale = (W + 160.0) / (GN - 1)

for j in range(GN):
    y = gy0 + j * gscale
    for i in range(GN):
        x = gx0 + i * gscale
        d = dome_sdf(x, y)
        dt = tent_sdf(x, y)
        GRID[j][i] = d if d < dt else dt

# gradient step for normal estimation
GSTEP = gscale


def sample_field(x, y):
    fx = (x - gx0) / gscale
    fy = (y - gy0) / gscale
    i = int(fx)
    j = int(fy)
    if i < 0:
        i = 0
    elif i > GN - 2:
        i = GN - 2
    if j < 0:
        j = 0
    elif j > GN - 2:
        j = GN - 2
    tx = fx - i
    ty = fy - j
    a = GRID[j][i] * (1 - tx) + GRID[j][i + 1] * tx
    b = GRID[j + 1][i] * (1 - tx) + GRID[j + 1][i + 1] * tx
    return a * (1 - ty) + b * ty


# ---------- plankton ----------
def build_plankton():
    rng = random.Random(SEED + 31)
    pts = []
    tries = 0
    while len(pts) < 420 and tries < 20000:
        tries += 1
        x = rng.uniform(0, W)
        y = rng.uniform(0, H)
        if sample_field(x, y) < 6.0:
            continue  # not inside the organism
        # bias density toward the light
        dl = math.hypot(x - CORE[0], y - CORE[1])
        keep = 1.0 / (1.0 + (dl / 520.0) ** 2) + 0.12
        if rng.random() < keep:
            r = rng.uniform(1.0, 2.6)
            glow_r = r * rng.uniform(5.0, 9.0)
            tint = rng.random()  # 0 = warm-lit, 1 = cyan
            pts.append((x, y, r, glow_r, tint))
    return pts


PLANKTON = build_plankton()


def smoothstep(a, b, x):
    t = (x - a) / (b - a)
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return t * t * (3 - 2 * t)


# ---------- render ----------
buf = [[0.0, 0.0, 0.0] for _ in range(W * H)]

for py in range(H):
    y = py + 0.5
    for px in range(W):
        x = px + 0.5
        # base sea: vertical gradient
        tvert = y / H
        r = SEA_TOP_L[0] + (SEA_BOT_L[0] - SEA_TOP_L[0]) * tvert
        g = SEA_TOP_L[1] + (SEA_BOT_L[1] - SEA_TOP_L[1]) * tvert
        b = SEA_TOP_L[2] + (SEA_BOT_L[2] - SEA_TOP_L[2]) * tvert

        d = sample_field(x, y)
        dl = math.hypot(x - CORE[0], y - CORE[1])

        # organism surface shading (Lambert from core, cyan rim at grazing)
        if d < 2.0:
            e = GSTEP
            nx = sample_field(x + e, y) - sample_field(x - e, y)
            ny = sample_field(x, y + e) - sample_field(x, y - e)
            nl = math.hypot(nx, ny)
            if nl > 1e-6:
                nx /= nl
                ny /= nl
            lx = CORE[0] - x
            ly = CORE[1] - y
            ll = math.hypot(lx, ly)
            if ll > 1e-6:
                lx /= ll
                ly /= ll
            diff = nx * lx + ny * ly
            diff = diff if diff > 0.0 else 0.0
            att = 1.0 / (1.0 + (dl / (KEY_R * 2.2)) ** 2)
            kd = 0.12 + 0.55 * diff * att
            r += KEY_L[0] * kd * 1.25
            g += KEY_L[1] * kd * 1.05
            b += KEY_L[2] * kd * 0.85
            rim_band = math.exp(-(d / 4.0) ** 2) * (1.0 - diff * 0.6)
            rim_band = rim_band if rim_band > 0.0 else 0.0
            r += RIM_L[0] * rim_band * 0.70
            g += RIM_L[1] * rim_band * 1.10
            b += RIM_L[2] * rim_band * 1.20

        # key glow (inverse-square-ish), additive in linear
        gk = 1.0 / (1.0 + (dl / KEY_R) ** 2)
        gk *= gk * 0.75 + gk * 0.25
        r += KEY_L[0] * gk * 1.15
        g += KEY_L[1] * gk * 0.72
        b += KEY_L[2] * gk * 0.32

        # wide cyan bounce halo + far warm wash (glow menembus fog)
        gb = 1.0 / (1.0 + (dl / (KEY_R * 2.8)) ** 2)
        gb *= gb
        r += RIM_L[0] * gb * 0.030
        g += RIM_L[1] * gb * 0.100
        b += RIM_L[2] * gb * 0.150
        gw = 1.0 / (1.0 + (dl / 620.0) ** 2)
        r += KEY_L[0] * gw * 0.010
        g += KEY_L[1] * gw * 0.014
        b += KEY_L[2] * gw * 0.020

        idx = py * W + px
        buf[idx][0] = r
        buf[idx][1] = g
        buf[idx][2] = b

# plankton sprites: small local glows, lit by the organism light
for (x, y, r0, gr, tint) in PLANKTON:
    cx = int(x)
    cy = int(y)
    rad = int(gr) + 2
    dl0 = math.hypot(x - CORE[0], y - CORE[1])
    lit = 0.35 + 0.65 / (1.0 + (dl0 / 460.0) ** 2)
    near_tent = 1.0 if sample_field(x, y) < 60.0 else 0.0
    selfglow = 0.35 * near_tent
    wr = (KEY_L[0] * (1 - tint) * 0.9 + RIM_L[0] * (tint + selfglow) * 0.55) * lit
    wg = (KEY_L[1] * (1 - tint) * 0.9 + RIM_L[1] * (tint + selfglow) * 0.55) * lit
    wb = (KEY_L[2] * (1 - tint) * 0.9 + RIM_L[2] * (tint + selfglow) * 0.55) * lit
    amp = 0.22 + 0.20 * (r0 / 2.6)
    # plankton jauh dari cahaya harus redup (menyala karena disinari)
    amp *= 0.35 + 0.65 / (1.0 + (dl0 / 700.0) ** 2)
    y0 = cy - rad
    if y0 < 0:
        y0 = 0
    y1 = cy + rad + 1
    if y1 > H:
        y1 = H
    x0 = cx - rad
    if x0 < 0:
        x0 = 0
    x1 = cx + rad + 1
    if x1 > W:
        x1 = W
    for py in range(y0, y1):
        dy = py + 0.5 - y
        row = py * W
        for px in range(x0, x1):
            dx = px + 0.5 - x
            d2 = (dx * dx + dy * dy) / (gr * gr)
            if d2 > 4.0:
                continue
            f = 1.0 / (1.0 + d2)
            f *= f
            idx = row + px
            buf[idx][0] += wr * amp * f
            buf[idx][1] += wg * amp * f
            buf[idx][2] += wb * amp * f

# ---------- depth haze: 5 layers, factor rises with depth ----------
haze_layers = []
rng_h = random.Random(SEED + 55)
for k in range(5):
    depth_at = 0.14 + k * 0.175          # 0.14 .. 0.84
    wgt = 1.0 / (1.0 + k * 0.18)
    off = rng_h.uniform(-0.04, 0.04)
    haze_layers.append((depth_at, wgt, off))

# precompute haze factor on a coarse grid, bilinear-upsampled
HN = 129
HGRID = [[0.0] * HN for _ in range(HN)]
hscale = (W - 1) / (HN - 1)
for j in range(HN):
    y = j * hscale + 0.5
    for i in range(HN):
        x = i * hscale + 0.5
        dl = math.hypot(x - CORE[0], y - CORE[1])
        dt = 1.0 / (1.0 + (dl / 560.0) ** 2)          # 1 near light, 0 far
        tv = y / H
        tt = tv
        tt = 0.0 if tt < 0.0 else (1.0 if tt > 1.0 else tt)
        dv = 1.0 - (tt * tt * (3 - 2 * tt) if tv > 0.55 else 0.0) * 0.25
        depth = (1.0 - dt) * dv
        f = 0.0
        wsum = 0.0
        for (dat, wgt, off) in haze_layers:
            w = wgt * math.exp(-((depth - (dat + off)) / 0.16) ** 2)
            f += w * dat
            wsum += w
        if wsum > 1e-6:
            f /= wsum
        f = 0.15 + (f - 0.15) * 0.9 if f > 0.15 else 0.15
        if f > 0.85:
            f = 0.85
        HGRID[j][i] = f


def sample_haze(x, y):
    fx = x / hscale
    fy = y / hscale
    i = int(fx)
    j = int(fy)
    if i > HN - 2:
        i = HN - 2
    if j > HN - 2:
        j = HN - 2
    tx = fx - i
    ty = fy - j
    a = HGRID[j][i] * (1 - tx) + HGRID[j][i + 1] * tx
    b = HGRID[j + 1][i] * (1 - tx) + HGRID[j + 1][i + 1] * tx
    return a * (1 - ty) + b * ty


for py in range(H):
    y = py + 0.5
    row = py * W
    for px in range(W):
        x = px + 0.5
        idx = row + px
        f = sample_haze(x, y)
        c0 = buf[idx]
        c0[0] = c0[0] + (HAZE_L[0] - c0[0]) * f
        c0[1] = c0[1] + (HAZE_L[1] - c0[1]) * f
        c0[2] = c0[2] + (HAZE_L[2] - c0[2]) * f

# ---------- grade + tone curve ----------
for idx in range(W * H):
    c = buf[idx]
    # soft tone curve (filmic-ish), applied in linear
    for i in range(3):
        v = c[i]
        v = 0.0 if v < 0.0 else v
        c[i] = v / (1.0 + 0.28 * v)
    # shadow floor -> #050814, highlight roll -> #FFE9C8
    # threshold in LINEAR luminance is small; protect the haze-lit bg from
    # being crushed back to black (keep fog visible)
    lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    s = smoothstep(0.006, 0.055, lum)
    for i in range(3):
        c[i] = SHADOW_L[i] + (c[i] - SHADOW_L[i]) * s
    h = smoothstep(0.75, 1.30, lum)
    for i in range(3):
        c[i] = c[i] + (HI_W_L[i] - c[i]) * h * 0.45

# ---------- grain: seeded smooth value noise, +-2 levels ----------
# bilinear-interpolated value noise (6px cells): deterministic, correlated
# between neighbours so the PNG still compresses, range stays within +-2
GT = 74  # value-noise lattice cells across the frame (14px spacing)
rng_g = random.Random(SEED + 99)
VLAT = [[rng_g.uniform(-2.0, 2.0) for _ in range(GT + 1)] for _ in range(GT + 1)]
GCELL = 14.0


def grain_at(x, y):
    fx = x / GCELL
    fy = y / GCELL
    i = int(fx)
    j = int(fy)
    if i > GT - 1:
        i = GT - 1
    if j > GT - 1:
        j = GT - 1
    tx = fx - i
    ty = fy - j
    sx = tx * tx * (3 - 2 * tx)
    sy = ty * ty * (3 - 2 * ty)
    a = VLAT[j][i] * (1 - sx) + VLAT[j][i + 1] * sx
    b = VLAT[j + 1][i] * (1 - sx) + VLAT[j + 1][i + 1] * sx
    v = a * (1 - sy) + b * sy
    n = int(v + 0.5) if v >= 0 else -int(-v + 0.5)
    if n > 2:
        n = 2
    elif n < -2:
        n = -2
    return n


# ---------- PNG writer ----------
def write_png(path):
    raw = bytearray()
    for py in range(H):
        raw.append(0)  # filter 0
        row = py * W
        for px in range(W):
            c = buf[row + px]
            s = l2s(c)
            n = grain_at(px, py)
            for v in s:
                # coarse quantize (multiple of 4) + grain +-2: the grain
                # dithers away the banding while keeping runs compressible
                b = (int(v * 255.0 / 4.0 + 0.5) * 4) + n
                if b < 0:
                    b = 0
                elif b > 255:
                    b = 255
                raw.append(b)
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        c += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return c

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


os.makedirs(OUT_DIR, exist_ok=True)
out_path = os.path.join(OUT_DIR, "coolest-art-01.png")
write_png(out_path)

elapsed = time.time() - t_start
print("wrote %s (%d bytes) in %.1fs" % (out_path, os.path.getsize(out_path), elapsed))
