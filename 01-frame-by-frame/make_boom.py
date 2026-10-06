# -*- coding: utf-8 -*-
"""逐帧手绘风爆炸循环 demo：程序化"线条沸腾" + 一拍二(12fps 绘制/24fps 编码)"""
import math, random, sys, os
import numpy as np
from PIL import Image, ImageDraw

OUT = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(OUT, "frames")

W, H = 1920, 1080
SS = 2                      # 超采样倍率（抗锯齿）
NF = 48                     # 每循环帧数 = 12fps * 4s

INK    = (48, 41, 35)
PAPER  = (237, 231, 212)
RED    = (205, 56, 34)
RED_D  = (166, 38, 22)
YELLOW = (246, 177, 38)
ORANGE = (238, 126, 26)
CREAM  = (246, 241, 224)

CX, CY = W / 2, H / 2 + 10

# ---------------- 纸纹底（静态，一次生成） ----------------

def make_paper():
    rng = np.random.default_rng(7)
    img = (np.ones((H * SS, W * SS, 3), np.int16)
           * np.array(PAPER, np.int16).reshape(1, 1, 3))
    img += rng.normal(0, 2.6, img.shape).astype(np.int16)          # 细颗粒
    ys = rng.integers(0, H * SS, 2600); xs = rng.integers(0, W * SS, 2600)
    v = rng.integers(14, 42, 2600)
    for y, x, dv in zip(ys, xs, v):                                # 纸浆斑点
        img[y, x] -= dv
        if rng.random() < 0.3 and x + 1 < W * SS:
            img[y, x + 1] -= dv // 2
    yy, xx = np.mgrid[0:H * SS, 0:W * SS].astype(np.float32)
    r2 = ((xx / (W * SS) - 0.5) ** 2 + (yy / (H * SS) - 0.5) ** 2) * 2
    img = (img * (1 - 0.045 * r2)[..., None]).clip(0, 255)         # 暗角
    return Image.fromarray(img.astype(np.uint8))

PAPER_TEX = None  # 惰性生成

# ---------------- 手绘基元 ----------------

def boil(seed):
    return random.Random(seed * 131 + 7)

def draw_blob(d, cx, cy, lobes, scale, sy, f, tag, fill, stroke, sw, boil_amp, sx=1.0):
    """多圆并集的手绘云：先描边层再填充层，逐帧抖动=线条沸腾"""
    pts = []
    for i, (ang, dist, rad) in enumerate(lobes):
        r = boil(f * 17 + i + tag)
        dd = dist * scale + r.uniform(-boil_amp, boil_amp)
        rr = max(8, rad * scale * sy + r.uniform(-boil_amp, boil_amp))
        pts.append((cx + math.cos(ang) * dd * sx + r.uniform(-boil_amp, boil_amp) * .5,
                    cy + math.sin(ang) * dd * sy + r.uniform(-boil_amp, boil_amp) * .5,
                    rr))
    if stroke:
        for x, y, r in pts:
            d.ellipse([x - r - sw, y - r - sw, x + r + sw, y + r + sw], fill=stroke)
    for x, y, r in pts:
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)
    for i, (x, y, r) in enumerate(pts):  # 第二遍错位填充，盖住描边层缝隙
        r2 = boil(f * 91 + i + tag * 7)
        dx = r2.uniform(-boil_amp, boil_amp) * .4
        dy = r2.uniform(-boil_amp, boil_amp) * .4
        d.ellipse([x - r * 1.04 + dx, y - r * 1.04 + dy,
                   x + r * 1.04 + dx, y + r * 1.04 + dy], fill=fill)

def star_poly(cx, cy, n, ro, ri, rot, rng, jit):
    pts = []
    for k in range(n * 2):
        a = rot + k * math.pi / n + rng.uniform(-jit, jit) * 0.4
        r = (ro if k % 2 == 0 else ri) * (1 + rng.uniform(-jit, jit) / max(ro, 1))
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts

def draw_star(d, cx, cy, n, ro, ri, rot, f, tag, fill, sw=0):
    rng = boil(f * 23 + tag)
    pts = star_poly(cx, cy, n, ro, ri, rot, rng, 0.05)
    if sw:
        d.line(pts + [pts[0]], fill=INK, width=sw, joint="curve")
    d.polygon(pts, fill=fill)

def sparkle(d, cx, cy, r, color, rot, squish=0.32):
    pts = []
    for k in range(8):
        a = rot + k * math.pi / 4
        rr = r if k % 2 == 0 else r * squish
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    d.polygon(pts, fill=color)

# ---------------- 场景元素定义 ----------------

LOBES = []
for i in range(14):
    ang = i / 14 * 2 * math.pi + 0.12
    dist = 405 + 80 * math.sin(i * 2.1 + 0.8) + 40 * math.sin(i * 4.3)
    rad = 196 + 50 * math.sin(i * 1.7 + 2.0) + 26 * math.sin(i * 3.7 + 1.0)
    LOBES.append((ang, dist, max(150, rad)))

CLOUDS = [  # (cx, cy, 尺寸, 瓣数, seed)
    (140, 120, 1.9, 5, 11), (1790, 140, 2.0, 6, 22),
    (1930, 760, 1.35, 4, 33), (200, 1030, 1.6, 5, 44),
    (1500, 1070, 1.0, 4, 55), (1760, 430, 0.65, 3, 66),
]

def cloud_lobes(n, base, seed):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        a = i / n * 2 * math.pi + rng.uniform(-0.2, 0.2)
        out.append((a, rng.uniform(0.45, 0.75) * base,
                    rng.uniform(0.42, 0.6) * base))
    return out

SWIRLS = [(0.9, 0.90), (2.1, 0.98), (3.2, 0.86), (4.2, 0.96), (5.4, 0.88)]  # (角,距比)

DEBRIS = [(random.Random(500 + i).uniform(0, 2 * math.pi),
           random.Random(700 + i).uniform(0, 1),
           random.Random(800 + i).uniform(7, 14),
           YELLOW if i % 2 else ORANGE) for i in range(11)]

SPARKS = [(330, 180, 30, 0.0), (1590, 150, 34, 0.33), (1750, 900, 28, 0.66),
          (150, 620, 24, 0.5), (620, 90, 22, 0.2), (1300, 60, 20, 0.8),
          (1800, 520, 18, 0.15), (90, 330, 18, 0.9)]

SQUIGS = [(1270, 190, 62, 0.8), (700, 845, 56, 2.4), (1345, 795, 46, 4.2)]  # 墨色小卷

# ---------------- 每帧渲染 ----------------

def render(f):
    global PAPER_TEX
    if PAPER_TEX is None:
        PAPER_TEX = make_paper()
    t = f / NF
    s = SS
    img = PAPER_TEX.copy()
    d = ImageDraw.Draw(img)
    cx, cy = CX * s, CY * s

    pulse = 1 + 0.055 * math.sin(2 * math.pi * 2 * t) + 0.035 * math.sin(2 * math.pi * 3 * t + 1.3)
    sy = 1 + 0.028 * math.sin(2 * math.pi * 2 * t + 0.8)

    # 角落云朵
    for cxx, cyy, size, n, seed in CLOUDS:
        draw_blob(d, cxx * s, cyy * s, cloud_lobes(n, 130 * size, seed),
                  1.0, 1.0, f, seed, CREAM, INK, 10 * s, 9 * s)

    # 速度线（闪烁）
    r = boil(f * 31)
    for gx, gy, ang in [(390, 465, 0.12), (1385, 235, -0.1), (1355, 655, 0.08)]:
        for k in range(3):
            if (f + k * 2) % 6 >= 4:
                continue
            x0 = (gx + k * 44) * s; y0 = (gy + k * 38) * s
            L = (95 + r.uniform(-8, 8)) * s
            a = ang + r.uniform(-0.03, 0.03)
            d.line([x0, y0, x0 + math.cos(a) * L, y0 + math.sin(a) * L],
                   fill=INK, width=6 * s)

    # 红色爆炸云
    draw_blob(d, cx, cy, LOBES, pulse, sy, f, 99, RED, INK, 15 * s, 15 * s, sx=1.08)

    # 内部黄色小卷球
    for ang, dist_r in SWIRLS:
        rr = boil(f * 41 + int(ang * 10))
        dd = 450 * pulse * dist_r
        bx = cx + math.cos(ang) * dd * 1.08 + rr.uniform(-6, 6) * s
        by = cy + math.sin(ang) * dd * sy + rr.uniform(-6, 6) * s
        rb = 34 * s
        d.ellipse([bx - rb, by - rb, bx + rb, by + rb], fill=YELLOW)
        ox = rb * 0.42 * math.cos(ang * 2.3)
        oy = rb * 0.42 * math.sin(ang * 2.3)
        d.ellipse([bx + ox - rb * .5, by + oy - rb * .5,
                   bx + ox + rb * .5, by + oy + rb * .5], fill=RED_D)
        d.ellipse([bx + ox * 1.6 - rb * .2, by + oy * 1.6 - rb * .2,
                   bx + ox * 1.6 + rb * .2, by + oy * 1.6 + rb * .2], fill=YELLOW)

    # 黄色星爆 + 白色内核
    rot = -0.18 + 0.06 * math.sin(2 * math.pi * 2 * t + 0.5)
    draw_star(d, cx, cy, 11, 310 * pulse, 148 * pulse, rot, f, 7, YELLOW, 14 * s)
    draw_star(d, cx, cy - 6 * s, 7, 118 * pulse, 58 * pulse,
              0.4 - 0.05 * math.sin(2 * math.pi * 3 * t), f, 8, (253, 250, 240))

    # 墨色小卷（烟）
    for qx, qy, qr, ph in SQUIGS:
        if (f + int(ph * 3)) % 8 < 6:
            rr = boil(f * 53 + int(ph))
            bx = qx * s + rr.uniform(-7, 7) * s
            by = qy * s + rr.uniform(-7, 7) * s
            rb = (qr + rr.uniform(-6, 6)) * s
            d.arc([bx - rb, by - rb, bx + rb, by + rb],
                  rr.randint(0, 180), rr.randint(200, 320), fill=INK, width=5 * s)

    # 飞散碎屑
    for ang, ph, size, col in DEBRIS:
        frac = (t + ph) % 1.0
        rr = 470 + 155 * frac
        bx = cx + math.cos(ang) * rr
        by = cy + math.sin(ang) * rr * sy
        rb = size * s * (1 - 0.4 * frac)
        d.ellipse([bx - rb, by - rb, bx + rb, by + rb], fill=col)

    # 闪烁星星
    for sx_, sy_, sr, ph in SPARKS:
        sc = 0.5 + 0.5 * math.sin(2 * math.pi * 3 * t + ph * 2 * math.pi)
        if sc < 0.18:
            continue
        rr = boil(f * 61 + int(ph * 40))
        sparkle(d, sx_ * s + rr.uniform(-4, 4) * s, sy_ * s + rr.uniform(-4, 4) * s,
                sr * sc * s, YELLOW if ph < 0.5 else ORANGE,
                rr.uniform(0, 3.14))

    return img.resize((W, H), Image.LANCZOS)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "preview":
        fr = int(sys.argv[2]) if len(sys.argv) > 2 else 6
        render(fr).save(os.path.join(OUT, "preview.png"))
        print("preview frame", fr, "->", os.path.join(OUT, "preview.png"))
    else:
        os.makedirs(FRAMES, exist_ok=True)
        for i in range(NF):
            render(i).save(os.path.join(FRAMES, "f_%03d.png" % i))
            if i % 12 == 0:
                print("frame", i, "/", NF)
        print("done:", NF, "frames in", FRAMES)
