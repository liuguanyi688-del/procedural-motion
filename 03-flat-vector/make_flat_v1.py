# -*- coding: utf-8 -*-
"""扁平矢量 motion demo（popwise 风格）：钴蓝城市 + 珊瑚圆点一镜长成太阳
纯色几何零阴影，全部戏在缓动上。8s 一镜到底，24fps。
用法: python make_flat.py preview | all
"""
import math, random, sys, os
from PIL import Image, ImageDraw

OUT = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(OUT, "frames")

W, H = 1600, 1000
SS = 2
FPS = 24
DUR = 8.0
NF = int(DUR * FPS)

BG       = (30, 48, 226)
BUILD    = (59, 79, 240)
BUILD2   = (48, 67, 232)
WINDOW   = (26, 43, 205)
CORAL    = (249, 86, 77)
CREAM    = (244, 227, 194)
DASH     = (252, 248, 238)
ACCENT   = (86, 106, 246)

ROAD_Y = 820          # 路面顶
ROAD_H = 180

BUILDINGS = [  # (cx, w, h, seed)
    (655, 95, 70, 11), (780, 115, 150, 12), (905, 135, 230, 13),
    (1060, 150, 330, 14), (1220, 165, 430, 15), (1380, 125, 280, 16),
    (1490, 105, 170, 17),
]

def clamp01(x): return max(0.0, min(1.0, x))

def eoc(x):  # easeOutCubic
    x = clamp01(x); return 1 - (1 - x) ** 3

def eob(x, s=1.70158):  # easeOutBack 回弹
    x = clamp01(x); x -= 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2

def cap_line(d, x1, y1, x2, y2, w, fill):
    d.line([x1, y1, x2, y2], fill=fill, width=int(w))
    r = w / 2
    for x, y in ((x1, y1), (x2, y2)):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

def lerp(a, b, p): return a + (b - a) * p

def mixc(c1, c2, p):
    return tuple(int(lerp(a, b, p)) for a, b in zip(c1, c2))

def render(f):
    t = f / FPS
    S = SS
    img = Image.new("RGB", (W * S, H * S), BG)
    d = ImageDraw.Draw(img)

    # ---------------- 路面（从底部升起） ----------------
    rp = eoc(t / 0.35)
    ry = (H - ROAD_H * rp) * S
    d.rectangle([0, ry, W * S, H * S], fill=CREAM)
    # 白虚线逐个弹出
    k = 0
    for x0 in range(-30, W + 60, 118):
        p = eob((t - (0.30 + k * 0.03)) / 0.4)
        k += 1
        if p <= 0:
            continue
        w = 76 * S * p
        cx = (x0 + 38) * S
        d.rounded_rectangle([cx - w / 2, 905 * S - 8 * S, cx + w / 2, 905 * S + 8 * S],
                            radius=8 * S, fill=DASH)

    # ---------------- 楼群（逐个回弹长高） ----------------
    for i, (cx, bw, bh, seed) in enumerate(BUILDINGS):
        st = 0.15 + i * 0.09
        p = eob((t - st) / 0.55)
        if p <= 0:
            continue
        h = bh * p * S
        col = BUILD if i % 2 == 0 else BUILD2
        x0, x1 = (cx - bw / 2) * S, (cx + bw / 2) * S
        y0 = ROAD_Y * S - h
        d.rectangle([x0, y0, x1, ROAD_Y * S], fill=col)
        # 窗户点点（楼长好后淡入，空闲时轻微闪烁）
        if p > 0.55:
            wa = clamp01((p - 0.55) / 0.45)
            rng = random.Random(seed)
            rows = max(1, int(bh / 90))
            for r_ in range(rows):
                for c_ in range(2):
                    if rng.random() < 0.25:
                        continue
                    wx = x0 + (0.30 + 0.42 * c_) * bw * S
                    wy = y0 + (0.18 + 0.16 * r_) * bh * S
                    tw = 0.55 + 0.45 * math.sin(2 * math.pi * (0.35 * t + rng.random()))
                    d.rounded_rectangle([wx - 7 * S, wy - 10 * S, wx + 7 * S, wy + 10 * S],
                                        radius=4 * S,
                                        fill=mixc(col, WINDOW, wa * (0.5 + 0.5 * tw)))

    # ---------------- 装饰几何 ----------------
    # 胶囊（斜着飘入 + 摇摆）
    pp = eob((t - 0.9) / 0.6)
    if pp > 0:
        ang = -33 + 7 * math.sin(2 * math.pi * 0.45 * t)
        pw, ph = 210 * S * pp, 92 * S * pp
        lay = Image.new("RGBA", (int(pw + 40 * S), int(ph + 40 * S)), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rounded_rectangle([20 * S, 20 * S, 20 * S + pw, 20 * S + ph],
                             radius=ph / 2, fill=ACCENT + (255,))
        lay = lay.rotate(-ang, expand=True, resample=Image.BICUBIC)
        img.paste(lay, (int(600 * S - lay.width / 2), int(590 * S - lay.height / 2)), lay)
    # 扇形（旋入）
    fp = eob((t - 1.1) / 0.6)
    if fp > 0:
        a0 = lerp(-100, -8, fp)
        d.pieslice([1300 * S, 560 * S, 1560 * S, 820 * S],
                   start=a0, end=a0 + 92, fill=ACCENT)
    # 叉（弹出 + 慢转）
    xp = eob((t - 1.25) / 0.45)
    if xp > 0:
        cx, cy, r = 1480 * S, 400 * S, 34 * S * xp
        a = math.radians(42 + 10 * math.sin(2 * math.pi * 0.3 * t + 1))
        for sgn in (1, -1):
            cap_line(d, cx - r * math.cos(a), cy - sgn * r * math.sin(a),
                     cx + r * math.cos(a), cy + sgn * r * math.sin(a), 24 * S, ACCENT)

    # ---------------- 珊瑚圆点 -> 太阳（一镜到底） ----------------
    SUN = (1200, 228)
    ROAD_TOP = ROAD_Y * S
    DOT_R = 55 * S

    def dot_at(x, y, r, sx=1.0, sy=1.0):
        d.ellipse([x - r * sx, y - r * sy, x + r * sx, y + r * sy], fill=CORAL)

    pos, rr, sqx, sqy = None, DOT_R, 1.0, 1.0
    if t < 2.0:
        pos = None
    elif t < 2.5:                                  # 自由落体（带拉伸）
        u = (t - 2.0) / 0.5
        st = 0.28 * math.sin(math.pi * u)
        pos = (800 * S, lerp(-60 * S, ROAD_TOP - DOT_R, u * u))
        sqx, sqy = 1 / (1 + st), 1 + st
    elif t < 3.7:                                  # 两次半回弹
        segs = [(2.5, 3.0, 260), (3.0, 3.38, 95), (3.38, 3.7, 26)]
        drift = [18, 42, 60]
        for (t0, t1, hh), dv in zip(segs, drift):
            if t < t1:
                u = (t - t0) / (t1 - t0)
                x = (800 + dv * u) * S
                y = (ROAD_TOP - DOT_R) - hh * S * math.sin(math.pi * u)
                pos = (x, y)
                break
        for ti in (2.5, 3.0, 3.38, 3.7):           # 触地压扁
            dd = abs(t - ti)
            if dd < 0.09:
                q = 1 - 0.45 * math.sin(math.pi * dd / 0.09)
                sqy, sqx = q, 1 + (1 - q) * 0.85
    elif t < 4.0:                                  # 贴地滚一下
        u = (t - 3.7) / 0.3
        pos = ((860 + 45 * u) * S, ROAD_TOP - DOT_R)
    elif t < 4.85:                                 # 弹射升空长成太阳
        u = (t - 4.0) / 0.85
        p = eob(u)
        x = lerp(905, SUN[0], p) * S
        y = (lerp(ROAD_TOP - DOT_R, SUN[1], p) - 130 * math.sin(math.pi * clamp01(u))) * S
        rr2 = DOT_R + (150 * S - DOT_R) * p
        st = 0.18 * math.sin(math.pi * u)
        pos, rr, sqx, sqy = (x, y), rr2, 1 / (1 + st), 1 + st
    else:                                          # 太阳待机呼吸
        rr = 150 * S * (1 + 0.022 * math.sin(2 * math.pi * 1.1 * (t - 4.85)))
        pos = (SUN[0] * S, SUN[1] * S)

    # 光芒（太阳成形后依次弹出）
    if t > 4.9:
        for j in range(7):
            p = eob((t - (4.95 + j * 0.055)) / 0.4)
            if p <= 0:
                continue
            a = math.radians(24 + j * 22 + 3 * math.sin(2 * math.pi * 0.6 * t + j))
            r1 = rr + 36 * S
            r2 = r1 + 60 * S * (0.9 + 0.1 * math.sin(2 * math.pi * 0.8 * t + j))
            cap_line(d, SUN[0] * S + math.cos(a) * r1, SUN[1] * S + math.sin(a) * r1,
                     SUN[0] * S + math.cos(a) * r2, SUN[1] * S + math.sin(a) * r2,
                     25 * S, CORAL)

    if pos is not None:
        dot_at(pos[0], pos[1], rr, sqx, sqy)

    return img.resize((W, H), Image.LANCZOS)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "preview":
        for fr in (30, 66, 126, 186):
            render(fr).save(os.path.join(OUT, "prev_%03d.png" % fr))
        print("PREVIEW DONE")
    else:
        os.makedirs(FRAMES, exist_ok=True)
        for i in range(NF):
            render(i).save(os.path.join(FRAMES, "f_%04d.png" % i))
            if i % 48 == 0:
                print("frame", i, "/", NF)
        print("done:", NF, "frames")
