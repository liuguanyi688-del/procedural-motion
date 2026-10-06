# -*- coding: utf-8 -*-
"""06 · 形变动画（SHAPE MORPH）：一滴墨 → 咖啡 → 日落 → 海鸥
SVG 形状插值的代码版：所有形状弧长重采样成相同点数、锚点对齐、逐点缓动插值。
60fps。用法: python make_morph.py preview | all
"""
import math, random, sys, os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(OUT, "frames")

W, H = 1600, 1000
SS = 2
FPS = 60
NP = 120                                    # 每个形状的重采样点数
SC = 2.35                                   # 每场景秒数
MORPH = 1.0                                 # 形变时长

INK_BG   = (21, 21, 28)
INK_FG   = (245, 245, 242)
CF_BG    = (77, 46, 31)
CF_FG    = (238, 225, 205)
CF_COF   = (115, 66, 41)
SUN_TOP  = (235, 87, 26)
SUN_BOT  = (28, 56, 219)
SUN_FG   = (252, 186, 36)
GULL_TOP = (152, 199, 236)
GULL_BOT = (64, 128, 217)
GULL_FG  = (250, 250, 248)

# ---------------- 缓动与几何工具 ----------------
def clamp01(x): return max(0.0, min(1.0, x))
def eio(x):
    x = clamp01(x)
    return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2
def eob(x, s=1.70158):
    x = clamp01(x); x -= 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2
def lerp(a, b, p): return a + (b - a) * p
def mixc(c1, c2, p): return tuple(int(round(lerp(a, b, p))) for a, b in zip(c1, c2))

def bez(p0, p1, p2, p3, n=40):
    return [((1-u)**3*p0[0] + 3*u*(1-u)**2*p1[0] + 3*u*u*(1-u)*p2[0] + u**3*p3[0],
             (1-u)**3*p0[1] + 3*u*(1-u)**2*p1[1] + 3*u*u*(1-u)*p2[1] + u**3*p3[1])
            for u in [i/n for i in range(1, n+1)]]

def arc(c, rx, ry, a0, a1, n=60):
    return [(c[0] + rx*math.cos(a0 + (a1-a0)*i/n), c[1] + ry*math.sin(a0 + (a1-a0)*i/n))
            for i in range(1, n+1)]

def line(a, b, n=24):
    return [(a[0] + (b[0]-a[0])*i/n, a[1] + (b[1]-a[1])*i/n) for i in range(1, n+1)]

def resample(poly, n=NP):
    """闭折线 → 弧长均匀 n 点"""
    pts = poly[:]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    L = [0.0]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i+1) % len(pts)]
        L.append(L[-1] + math.dist(a, b))
    total = L[-1]
    out = []
    j = 0
    for k in range(n):
        target = total * k / n
        while L[j+1] < target:
            j += 1
        seg = L[j+1] - L[j]
        p = (target - L[j]) / seg if seg > 0 else 0
        a, b = pts[j], pts[(j+1) % len(pts)]
        out.append((lerp(a[0], b[0], p), lerp(a[1], b[1], p)))
    return out

def rotate_to_anchor(pts, anchor):
    """旋转点列，使最接近 anchor 的点排到第一位（保证形变不翻卷）"""
    best, bi = 1e18, 0
    for i, p in enumerate(pts):
        d = math.dist(p, anchor)
        if d < best:
            best, bi = d, i
    return pts[bi:] + pts[:bi]

def signed_area(poly):
    s = 0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i+1) % len(poly)]
        s += x1*y2 - x2*y1
    return s / 2

# ---------------- 四个形状（局部坐标，单位化） ----------------
def build_shapes():
    # 墨滴（尾巴朝上）
    d = []
    d += line((0, -1.55), (0, -1.55), 1)
    d += bez((0, -1.55), (0.30, -1.02), (1.05, -0.35), (1.00, 0.28))
    d += arc((0, 0.28), 1.00, 0.80, 0, math.pi)
    d += bez((-1.00, 0.28), (-1.05, -0.35), (-0.30, -1.02), (0, -1.55))
    # 咖啡杯身（梯形圆底）
    c = []
    c += line((-1.02, -0.72), (1.02, -0.72))
    c += bez((1.02, -0.72), (1.02, 0.10), (0.94, 0.38), (0.62, 0.55))
    c += arc((0, 0.55), 0.62, 0.35, 0, math.pi)
    c += bez((-0.62, 0.55), (-0.94, 0.38), (-1.02, 0.10), (-1.02, -0.72))
    # 太阳（半圆穹顶，平底）
    s = []
    s += line((-1.05, 0.18), (-1.05, 0.18), 1)
    s += arc((0, 0.18), 1.05, 1.05, math.pi, 2*math.pi)
    s += line((1.05, 0.18), (-1.05, 0.18), 1)
    # 海鸥（双翼 m 轮廓：两段上凸弧，中央凹口）
    g = []
    g += line((-1.60, -0.15), (-1.60, -0.15), 1)
    g += bez((-1.60, -0.15), (-1.15, -0.40), (-0.45, -0.40), (0, 0.05))
    g += bez((0, 0.05), (0.45, -0.40), (1.15, -0.40), (1.60, -0.15))
    g += bez((1.60, -0.15), (1.05, 0.12), (0.45, 0.26), (0, 0.52))
    g += bez((0, 0.52), (-0.45, 0.26), (-1.05, 0.12), (-1.60, -0.15))
    raw = [d, c, s, g]
    anchors = [(0, -1.55), (0, -0.72), (0, -0.87), (0, 0.05)]
    out = []
    for poly, anc in zip(raw, anchors):
        r = resample(poly, NP)
        r = rotate_to_anchor(r, anc)
        if signed_area(r) < 0:
            r = r[::-1]
        out.append(r)
    return out

SHAPES = build_shapes()

# ---------------- 场景表 ----------------
SCENES = [
    dict(num="01", name="墨滴", en="INK", top=INK_BG, bot=INK_BG, ysplit=2000,
         fg=INK_FG, center=(800, 470), scale=175),
    dict(num="02", name="咖啡", en="COFFEE", top=CF_BG, bot=CF_BG, ysplit=2000,
         fg=CF_FG, center=(800, 480), scale=150),
    dict(num="03", name="日落", en="SUNSET", top=SUN_TOP, bot=SUN_BOT, ysplit=560,
         fg=SUN_FG, center=(760, 545), scale=150, sea=True),
    dict(num="04", name="海鸥", en="SEAGULL", top=GULL_TOP, bot=GULL_BOT, ysplit=760,
         fg=GULL_FG, center=(800, 400), scale=195),
]

def cap_line(d, x1, y1, x2, y2, w, fill):
    d.line([x1, y1, x2, y2], fill=fill, width=int(w))
    r = w / 2
    for x, y in ((x1, y1), (x2, y2)):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

# ---------------- 场景专属小件 ----------------
def accents(d, idx, tl, S, mix_bg):
    """tl = 场景内时间(秒)；小件在形变完成后弹入"""
    s = SS
    pop = lambda t0: eob((tl - t0) / 0.45, s=1.9)
    fadeout = 1.0 - clamp01((tl - (SC - 0.45)) / 0.45)   # 形变开始前退场
    if idx == 1:                                          # 咖啡：把手/蒸汽/碟
        p = pop(1.10) * fadeout
        if p > 0.01:
            hx, hy, hr = (800 + 148) * s, 452 * s, 52 * s
            d.arc([hx - hr, hy - hr, hx + hr, hy + hr], start=-70, end=70,
                  fill=mixc(mix_bg, CF_FG, p), width=int(24 * s * p))
        p = pop(1.25) * fadeout
        if p > 0.01:
            for sx in (762, 838):
                for k in range(3):
                    yy = (318 - k * 44) * s
                    sway = math.sin(tl * 2.4 + k * 1.7 + sx) * 7
                    xa, xb = sx * s + sway * s, (sx + 26) * s + sway * s
                    w = (20 - k * 4) * s
                    col = mixc(mix_bg, (248, 246, 240), p * (1 - k * 0.22))
                    d.rounded_rectangle([min(xa, xb), yy - 9 * s, max(xa, xb), yy + 9 * s],
                                        radius=9 * s, fill=col)
        p = pop(1.40) * fadeout
        if p > 0.01:
            cap_line(d, 660 * s, 622 * s, 940 * s, 622 * s, 18 * s * p,
                     mixc(mix_bg, CF_FG, p))
    elif idx == 2:                                        # 日落：光芒/海平线
        for k in range(7):
            p = pop(1.10 + k * 0.05) * fadeout
            if p <= 0.01:
                continue
            a = math.radians(197 + k * 27.5)
            cx, cy = 760 * s, 545 * s
            r1, r2 = 190 * s, (252 + 6 * math.sin(tl * 2 + k)) * s
            cap_line(d, cx + math.cos(a) * r1, cy + math.sin(a) * r1,
                     cx + math.cos(a) * r2, cy + math.sin(a) * r2,
                     24 * s, mixc(mix_bg, SUN_FG, p))
        for k, (wy, wl) in enumerate(((645, 440), (706, 340), (762, 250), (812, 168))):
            p = pop(1.25 + k * 0.07) * fadeout
            if p <= 0.01:
                continue
            cap_line(d, (760 - wl / 2) * s, wy * s, (760 + wl / 2) * s, wy * s,
                     20 * s, mixc(mix_bg, SUN_FG, p))
    elif idx == 3:                                        # 海鸥：两朵云线
        for k, (cx0, cy0, w0) in enumerate(((430, 300, 150), (1180, 250, 190))):
            p = pop(1.20 + k * 0.1) * fadeout
            if p <= 0.01:
                continue
            col = mixc(mix_bg, (255, 255, 255), p * 0.75)
            cap_line(d, (cx0 - w0 / 2) * s, cy0 * s, (cx0 + w0 / 2) * s, cy0 * s,
                     16 * s, col)

# ---------------- 字幕与进度点 ----------------
def load_fonts():
    f1 = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 46, index=0)
    f2 = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 38, index=0)
    f3 = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 24, index=0)
    return f1, f2, f3
F1, F2, F3 = load_fonts()

def caption(d, idx, tl, mix_bg):
    s = SS
    fade = 1.0 - clamp01((tl - (SC - 0.4)) / 0.4)
    if fade <= 0.01:
        return
    S = SCENES[idx]
    col = mixc(mix_bg, (255, 255, 255), 0.92 * fade)
    x, y = 96 * s, 872 * s
    d.text((x, y), S["num"], font=F1, fill=col)
    xn = x + 108 * s
    d.text((xn, y + 6 * s), S["name"], font=F2, fill=col)
    d.text((xn + 132 * s, y + 14 * s), S["en"], font=F3, fill=mixc(mix_bg, (255, 255, 255), 0.55 * fade))
    # 进度点
    for k in range(7):
        dx = (1450 + k * 34) * s
        dy = 896 * s
        if k == idx:
            d.rounded_rectangle([dx - 20 * s, dy - 7 * s, dx + 20 * s, dy + 7 * s],
                                radius=7 * s, fill=col)
        else:
            r = 6 * s
            d.ellipse([dx - r, dy - r, dx + r, dy + r],
                      fill=mixc(mix_bg, (255, 255, 255), 0.35 * fade))

# ---------------- 形变插值 ----------------
def morph_shape(i0, i1, p):
    a, b = SHAPES[i0], SHAPES[i1]
    return [(lerp(pa[0], pb[0], p), lerp(pa[1], pb[1], p)) for pa, pb in zip(a, b)]

# ---------------- 渲染 ----------------
def render(f):
    t = f / FPS
    s = SS
    img = Image.new("RGB", (W * s, H * s), SCENES[0]["top"])
    d = ImageDraw.Draw(img)

    total_scenes = len(SCENES)
    seg_i = min(int(t / SC), total_scenes - 1)
    t_in = t - seg_i * SC
    # 形变进度：场景开始后 MORPH 秒内从上一形状变到当前
    p = eio(clamp01(t_in / MORPH)) if seg_i > 0 else 1.0
    prev_i = max(0, seg_i - 1)

    S0, S1 = SCENES[prev_i], SCENES[seg_i]
    # 背景：双色分割 + 分割线位置 + 颜色随形变过渡
    ysplit = lerp(S0["ysplit"], S1["ysplit"], p) * s
    top = mixc(S0["top"], S1["top"], p)
    bot = mixc(S0["bot"], S1["bot"], p)
    d.rectangle([0, 0, W * s, min(ysplit, H * s)], fill=top)
    if ysplit < H * s:
        d.rectangle([0, ysplit, W * s, H * s], fill=bot)

    # 主形状
    cx = lerp(S0["center"][0], S1["center"][0], p) * s
    cy = lerp(S0["center"][1], S1["center"][1], p) * s
    sc = lerp(S0["scale"], S1["scale"], p) * s
    fg = mixc(S0["fg"], S1["fg"], p)
    mix_bg = mixc(S0["top"], S1["top"], p)
    poly = morph_shape(prev_i, seg_i, p)
    d.polygon([((cx + px * sc), (cy + py * sc)) for px, py in poly], fill=fg)

    # 日落场景：海面矩形盖住形状下缘（形变途中颜色同步过渡）
    if ysplit < H * s:
        d.rectangle([0, ysplit, W * s, H * s], fill=bot)

    # 场景小件
    accents(d, seg_i, t_in, S1, mix_bg)

    # 字幕
    caption(d, seg_i, t_in, mix_bg)

    return img.resize((W, H), Image.LANCZOS)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    DUR = len(SCENES) * SC
    NF = int(DUR * FPS)
    if mode == "preview":
        for fr in (30, 100, 170, 250, 330, 410, 500, 550):
            render(fr).save(os.path.join(OUT, "prev_%03d.png" % fr))
        print("PREVIEW DONE  total %.1fs %d frames" % (DUR, NF))
    else:
        os.makedirs(FRAMES, exist_ok=True)
        for i in range(NF):
            render(i).save(os.path.join(FRAMES, "f_%04d.png" % i))
            if i % 120 == 0:
                print("frame", i, "/", NF)
        print("done:", NF, "frames")
