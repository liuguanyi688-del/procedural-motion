# -*- coding: utf-8 -*-
"""
11 · 几何构成 · 包豪斯  Geometric · Bauhaus — KONSTRUKTION IN 20 SCHLÄGEN
========================================================================
纯 Python + Pillow + numpy 复刻：把「印刷机」搬进代码。

    分色版（黄/红/蓝/黑四张 120px 网格上的墨版）
      → 20 拍装配（120 BPM，一拍 0.5 秒，正好 10 秒）
      → 6–8 秒的「翻版」：瓷砖旋转 → 卡片翻到背面 → 立柱错位 → 卡片转回正面
      → 印刷合成（纸张纹理 / 四色套印 / 套印不准 / 网点粗糙边 / 颗粒）

    python make_bauhaus.py preview        # 关键帧预览 prev_*.png
    python make_bauhaus.py one 6.4 a.png  # 单帧
    python make_bauhaus.py all 3          # 600 帧 → frames/
"""

import os
import sys
import math
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageChops

np.seterr(all="ignore")

# ----------------------------------------------------------------- 版式规格
W, H = 1920, 1080
M = 120                     # 模块
Y0 = 60                     # 网格起点
CX, CY = 960, 540
FPS = 60
DUR = 10.0
BPM = 120
BEAT = 60.0 / BPM           # 0.5 s
TRIM = (120, 60, 1800, 1020)   # 版面裁切框
ROOT = os.path.dirname(os.path.abspath(__file__))

PAPER = np.array([241, 233, 218], np.float32) / 255.0
INKC = {
    "Y": np.array([242, 183, 5], np.float32) / 255.0,
    "R": np.array([224, 60, 49], np.float32) / 255.0,
    "B": np.array([30, 79, 163], np.float32) / 255.0,
    "K": np.array([17, 17, 17], np.float32) / 255.0,
}
DEG = math.pi / 180.0
TAU = math.pi * 2

# ----------------------------------------------------------------- 缓动
def clamp(x, a=0.0, b=1.0):
    return np.clip(x, a, b)


def clampf(x, a=0.0, b=1.0):
    return float(min(b, max(a, x)))


def io2(u):
    u = clamp(u)
    return np.where(u < 0.5, 2 * u * u, 1 - np.power(-2 * u + 2, 2) / 2)


def in2(u):
    u = clamp(u)
    return u * u


def io2f(u):
    u = clampf(u)
    return 2 * u * u if u < 0.5 else 1 - (-2 * u + 2) ** 2 / 2


def in2f(u):
    u = clampf(u)
    return u * u


def prog(t, t0, t1):
    return (t - t0) / (t1 - t0)


def snap(t):
    return round(t * 30) / 30


def lerp(a, b, u):
    return a + (b - a) * u


def f32(x):
    if isinstance(x, np.ndarray):
        return x if x.dtype == np.float32 else x.astype(np.float32)
    return np.float32(x)


def mix(a, b, x):
    a, b, x = f32(a), f32(b), f32(x)
    return a + (b - a) * x


def sstep(a, b, x):
    t = clamp((x - a) / (b - a))
    return t * t * (3.0 - 2.0 * t)


# ----------------------------------------------------------------- 节拍表（来自参考 cues.json）
EV = {
    "marks": dict(t=0.25),
    "circle_land": dict(t=0.5, t0=-0.2),
    "bar_land": dict(t=1.0, t0=0.75),
    "target1": dict(t=1.25, until=1.5, gx=840, gy=1020),
    "tri_in": dict(t=1.5, t0=1.25),
    "target2": dict(t=1.75, until=2.0, gx=840, gy=540),
    "tri_flip": dict(t=2.0, t0=1.75),
    "target3": dict(t=2.25, until=2.5, gx=1080, gy=300),
    "sq_scale": dict(t=2.5, t0=2.25),
    "target4": dict(t=2.75, until=3.0, gx=960, gy=540),
    "circle_slide": dict(t=3.0, t0=2.75),
    "pivot": dict(t=3.0),
    "group_turn": dict(t=4.0, t0=3.25),
    "semi_slide": dict(t=4.5, t0=4.25),
    "qd_sweep": dict(t=5.0, t0=4.75),
    "rule": dict(t=5.25, t0=5.0),
    "ticker_in": dict(t=5.25),
    "red_in": dict(t=5.5),
    "red_split": dict(t=5.75, t0=5.625),
    "drop": dict(t=6.0),
    "reveal": dict(t=7.0, until=7.2),
    "freeze": dict(t=8.0),
    "type_small": dict(t=9.0),
    "lock": dict(t=9.5),
}
RP = {
    "R1": dict(start=6.0, dur=0.25, span=0.25, angle=90.0, origin=(840, 300)),
    "R2": dict(start=6.5, dur=0.20, span=0.30, origin=(120, 60)),
    "R3": dict(start=7.2, dur=0.12, span=0.08, dy=120, origin=(1800, 540)),
    "R4": dict(start=7.5, dur=0.20, span=0.30, origin=(960, 540)),
}
GRID = dict(land0=0.125, step=0.125, draw=0.25, relax=0.2)
DROP, FREEZE = EV["drop"]["t"], EV["freeze"]["t"]
FRONT_RESET = 7.1
LETTERS = dict(t0=8.0, step=0.125, n=7)
TICKER = [8.5, 9.0, 9.5]
TICKER_VO = [9.8833]
LABELS = [7.0, 7.0667, 7.1333]

# 涟漪的波前归一化
R1_SPANK = RP["R1"]["span"] / max(
    math.hypot(x - 840, y - 300)
    for y in range(Y0 + 60, TRIM[3], 120) for x in range(TRIM[0] + 60, TRIM[2], 120))
R2_SPANK = RP["R2"]["span"] / ((TRIM[2] - 120 - TRIM[0]) + (TRIM[3] - 120 - TRIM[1]))
R3_SPANK = RP["R3"]["span"] / (1680 - 240)
_R4R = [math.hypot(x - CX, y - CY)
        for y in range(Y0 + 120, TRIM[3], 240) for x in range(TRIM[0] + 120, TRIM[2], 240)]
R4_MXR, R4_MNR = max(_R4R), min(_R4R)
R4_SPANK = RP["R4"]["span"] / (R4_MXR - R4_MNR)


def casc_on(t):
    q = snap(t)
    return DROP <= q < FREEZE


def group_angle(t):
    """12 齿擒纵：缓动进度量化成 7.5° 一齿，齿内在后 65% 走完再停住"""
    p = io2f(prog(t, EV["group_turn"]["t0"], EV["group_turn"]["t"]))
    x = p * 12
    k = min(12, math.floor(x + 1e-9))
    f = x - k
    return (-90 + 7.5 * (k + io2f(clampf((f - 0.35) / 0.65)))) * DEG


# ----------------------------------------------------------------- 字体
FONTS = {}
FDIR = "C:/Windows/Fonts/"
F_EN = "segoeuib.ttf"
F_EN_R = "segoeui.ttf"
F_CN = "msyhbd.ttc"


def F(name, size):
    key = (name, int(size))
    if key not in FONTS:
        FONTS[key] = ImageFont.truetype(FDIR + name, max(1, int(size)))
    return FONTS[key]


def tlen(d, s, f, track=0.0):
    if not s:
        return 0.0
    return sum(d.textlength(c, font=f) for c in s) + track * (len(s) - 1)


def tdraw(d, x, y, s, f, fill, track=0.0, align="left", base="la"):
    if align == "right":
        x -= tlen(d, s, f, track)
    elif align == "center":
        x -= tlen(d, s, f, track) / 2.0
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill, anchor=base)
        x += d.textlength(ch, font=f) + track
    return x


# ----------------------------------------------------------------- 纸纹与颗粒
_PAPER = None
_GRAIN = None


def _fbm(n, octaves, seed, base=4):
    rng = np.random.default_rng(seed)
    acc = np.zeros((n, n), np.float32)
    amp, tot, size = 1.0, 0.0, base
    for _ in range(octaves):
        if size > n:
            break
        m = size
        x = np.arange(n, dtype=np.float32) * (m / n)
        i0 = np.floor(x).astype(np.int32)
        fr = x - i0
        fr = fr * fr * (3 - 2 * fr)
        i1 = (i0 + 1) % m
        i0 = i0 % m
        g = rng.random((m, m), np.float32)
        rows = g[i0] * (1 - fr)[:, None] + g[i1] * fr[:, None]
        acc += (rows[:, i0] * (1 - fr)[None, :] + rows[:, i1] * fr[None, :]) * amp
        tot += amp
        amp *= 0.5
        size *= 2
    return acc / tot


def paper_tile():
    global _PAPER
    if _PAPER is None:
        p = _fbm(1024, 7, 5)
        _PAPER = np.clip((p - 0.5) * 0.22 + 0.82, 0.0, 1.0).astype(np.float32)
    return _PAPER


def grain_tile():
    global _GRAIN
    if _GRAIN is None:
        rng = np.random.default_rng(11)
        _GRAIN = rng.random((2048, 2048), np.float32)
    return _GRAIN


def sample(img, X, Y):
    """双线性采样（越界 clamp），就地运算版"""
    h, w = img.shape[:2]
    X = np.clip(X, 0.0, w - 1.001)
    Y = np.clip(Y, 0.0, h - 1.001)
    x0 = np.floor(X).astype(np.int32)
    y0 = np.floor(Y).astype(np.int32)
    two_d = img.ndim == 2
    fx = (X - x0).astype(np.float32)
    fy = (Y - y0).astype(np.float32)
    if not two_d:
        fx = fx[..., None]
        fy = fy[..., None]
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    a = img[y0, x0]
    b = img[y0, x1]
    b -= a
    b *= fx
    b += a
    c = img[y1, x0]
    d = img[y1, x1]
    d -= c
    d *= fx
    d += c
    d -= b
    d *= fy
    d += b
    return d


def h21(ix, iy):
    """整数格点哈希（与参考的 h21 同构）"""
    x = np.mod(ix * 123.34 + iy * 456.21, 1.0)
    x = x + np.mod(ix * 45.32 + iy * 45.32 + x * (x + 45.32), 1.0) * 0.0
    return np.mod(x, 1.0)


def vnoise(px, py, cell):
    """值噪声：格边长为 cell 设计像素，平滑插值，无重复周期"""
    x = px / cell
    y = py / cell
    i0 = np.floor(x)
    j0 = np.floor(y)
    fx = x - i0
    fy = y - j0
    fx = fx * fx * (3.0 - 2.0 * fx)
    fy = fy * fy * (3.0 - 2.0 * fy)
    a = h21(i0, j0)
    b = h21(i0 + 1.0, j0)
    c = h21(i0, j0 + 1.0)
    d = h21(i0 + 1.0, j0 + 1.0)
    top = a + (b - a) * fx
    bot = c + (d - c) * fx
    return top + (bot - top) * fy


# ----------------------------------------------------------------- 形状
def p_circle(cx, cy, r):
    return lambda d: d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)


def p_ring(cx, cy, r0, r1):
    def f(d):
        d.ellipse([cx - r1, cy - r1, cx + r1, cy + r1], fill=255)
        d.ellipse([cx - r0, cy - r0, cx + r0, cy + r0], fill=0)
    return f


def p_rect(x, y, w, h):
    return lambda d: d.rectangle([x, y, x + w, y + h], fill=255)


def p_poly(pts):
    return lambda d: d.polygon([tuple(p) for p in pts], fill=255)


def p_sector(px, py, r, a0):
    return lambda d: d.pieslice([px - r, py - r, px + r, py + r],
                                start=a0 / DEG, end=(a0 + math.pi / 2) / DEG, fill=255)


def p_semi(cx, cy, r, a0):
    return lambda d: d.pieslice([cx - r, cy - r, cx + r, cy + r],
                                start=a0 / DEG, end=(a0 + math.pi) / DEG, fill=255)


class Plates:
    """四张墨版（Y / R / B / K），255 = 满版

    关键：**挖空（knockout）**。真实分色印刷里，印某一色时会把该位置的其他色版挖掉，
    否则黑色底子会把彩色的三原色图直接乘黑。后画的形状会挖掉先画的——这决定了绘制的先后顺序。
    """

    def __init__(self):
        self.img = {k: Image.new("L", (W, H), 0) for k in "YRBK"}
        self.d = {k: ImageDraw.Draw(self.img[k]) for k in "YRBK"}

    def paint(self, ink, fn):
        S = Image.new("L", (W, H), 0)
        fn(ImageDraw.Draw(S))
        self.paint_mask(ink, S)

    def paint_mask(self, ink, S):
        if S.getbbox() is None:
            return
        inv = ImageChops.invert(S)
        for k in "YRBK":
            if k == ink:
                self.img[k] = ImageChops.lighter(self.img[k], S)
            else:
                self.img[k] = ImageChops.multiply(self.img[k], inv)
        self.d = {k: ImageDraw.Draw(self.img[k]) for k in "YRBK"}

    def erase(self, ink, fn):
        """在某一色版上直接挖掉（不做挖空），用于「露出纸张」的文字"""
        fn(self.d[ink])

    def arr(self):
        """归一化到 0..1 的四色墨量"""
        return {k: np.asarray(self.img[k], np.float32) * (1.0 / 255.0) for k in "YRBK"}


# ----------------------------------------------------------------- 版面元素
def target(p, x, y):
    p.paint("K", p_ring(x, y, 21, 25))
    p.paint("K", p_rect(x - 44, y - 2, 32, 4))
    p.paint("K", p_rect(x + 12, y - 2, 32, 4))
    p.paint("K", p_rect(x - 2, y - 44, 4, 32))
    p.paint("K", p_rect(x - 2, y + 12, 4, 32))
    p.paint("K", p_circle(x, y, 4))


def draw_group(p, t, keep_dot=True, no_rule=False):
    """中央 8×8 模块内的全部元素（按最终坐标绘制，整体做 12 齿擒纵旋转）"""
    ang = group_angle(t)
    q = Plates()
    for i in range(1, 5):
        e = EV["target%d" % i]
        if snap(t) >= e["t"] and snap(t) < e["until"]:
            target(q, e["gx"], e["gy"])

    e1 = EV["circle_land"]
    if t >= e1["t0"]:
        u = in2f(prog(t, e1["t0"], e1["t"]))
        dx = (1 - u) * 6 * M
        sl = io2f(prog(t, EV["circle_slide"]["t0"], EV["circle_slide"]["t"]))
        q.paint("R", p_circle(840 + dx, 300 - M * (1 - sl), 240))

    e4 = EV["sq_scale"]
    if t >= e4["t0"]:
        s = io2f(prog(t, e4["t0"], e4["t"]))
        if s > 0.001:
            q.paint("B", p_rect(1080, 300 - 240 * s, 240 * s + 4 * s, 240 * s))

    e3, e3f = EV["tri_in"], EV["tri_flip"]
    if t >= e3["t0"]:
        sy = -io2f(prog(t, e3["t0"], e3["t"])) if t < e3["t"] else lerp(-1, 1, io2f(prog(t, e3f["t0"], e3f["t"])))
        apex = 1020 - 480 * sy
        if abs(sy) > 0.002:
            q.paint("Y", p_poly([[600, 1020], [1080, 1020], [840, apex]]))

    e2 = EV["bar_land"]
    if t >= e2["t0"]:
        u = in2f(prog(t, e2["t0"], e2["t"]))
        q.paint("K", p_rect(1320, 60, 120, 960 * u))

    if snap(t) >= EV["pivot"]["t"] and not no_rule and not casc_on(t):
        if keep_dot:
            q.paint("K", p_circle(CX, CY, 20))
        rr = io2f(prog(t, EV["pivot"]["t"], EV["group_turn"]["t0"]))
        if t < EV["group_turn"]["t"] + 0.25 and rr > 0.001:
            a0 = -math.pi / 2

            def arc(d, a0=a0, rr=rr):
                d.pieslice([CX - 60, CY - 60, CX + 60, CY + 60],
                           start=a0 / DEG, end=(a0 + math.pi * 2 * rr) / DEG, fill=255)
                d.ellipse([CX - 56, CY - 56, CX + 56, CY + 56], fill=0)
            q.paint("K", arc)

    if abs(ang) > 1e-6:
        for k in "YRBK":
            p.img[k].paste(q.img[k].rotate(-ang / DEG, center=(CX, CY), resample=Image.BICUBIC), (0, 0))
    else:
        for k in "YRBK":
            p.img[k].paste(q.img[k], (0, 0))
    p.d = {k: ImageDraw.Draw(p.img[k]) for k in "YRBK"}


def draw_outer(p, t, no_rule=False):
    e5 = EV["semi_slide"]
    if t >= e5["t0"]:
        u = io2f(prog(t, e5["t0"], e5["t"]))
        p.paint("B", p_semi(1436 - 240 * (1 - u), 780, 244, -90 * DEG))

    e6 = EV["qd_sweep"]
    if t >= e6["t0"]:
        u = io2f(prog(t, e6["t0"], e6["t"]))
        p.paint("K", p_sector(600, 1020, 240, (90 + 90 * u) * DEG))

    er = EV["rule"]
    if t >= er["t0"] and not no_rule and not casc_on(t):
        u = io2f(prog(t, er["t0"], er["t"]))
        p.paint("K", p_rect(360, 537, (1800 - 360) * u, 6))

    e7, e7s = EV["red_in"], EV["red_split"]
    if snap(t) >= e7["t"]:
        r = 240 * io2f(prog(t, e7s["t0"], e7s["t"]))

        def redq(d, r=r):
            # 5.50 红色 2×2 方块切进来；5.75 外角被圆规扫成以 (1440,540) 为心的四分之一圆
            if r < 0.5:
                d.polygon([(1436, 540), (1436, 300), (1680, 300), (1680, 540)], fill=255)
            else:
                d.polygon([(1436, 540), (1436, 300), (1680 - r, 300),
                           (1680, 300 + r), (1680, 540)], fill=255)
                d.pieslice([1680 - 2 * r, 300, 1680, 300 + 2 * r], start=-90, end=0, fill=255)
        p.paint("R", redq)

    if t >= EV["group_turn"]["t"]:
        p.paint("K", p_rect(1320, 60, 120, 960))

    if snap(t) >= EV["ticker_in"]["t"]:
        qq = 0.0
        for tt in TICKER + TICKER_VO:
            qq += io2f(prog(t, tt - 0.25, tt))
        p.paint("K", p_sector(480, 180, 120, (180 + 90 * qq) * DEG))


# ---------------------------------------------------------------- 正面「填充场」
SH = [
    ("R", "qd", 840, 300, 1.6, lambda x, y: max(0.0, math.hypot(x - 840, y - 300) - 240)),
    ("R", "qd", 1440, 540, 1.0, lambda x, y: sd_box(x, y, 1440, 300, 1680, 540)),
    ("B", "sq", 1200, 180, 1.0, lambda x, y: sd_box(x, y, 1080, 60, 1320, 300)),
    ("B", "semi", 1440, 780, 1.0,
     lambda x, y: sd_box(x, y, 1440, 540, 1440, 1020) if x < 1440 else max(0.0, math.hypot(x - 1440, y - 780) - 240)),
    ("Y", "hst", 840, 860, 1.0, lambda x, y: min(sd_seg(x, y, 600, 1020, 840, 540),
                                                 sd_seg(x, y, 1080, 1020, 840, 540),
                                                 sd_seg(x, y, 600, 1020, 1080, 1020))),
    ("K", "bar", 1380, 540, 1.0, lambda x, y: sd_box(x, y, 1320, 60, 1440, 1020)),
    ("K", "qd", 600, 1020, 1.0, lambda x, y: sd_box(x, y, 360, 780, 600, 1020)),
]


def sd_box(x, y, x0, y0, x1, y1):
    dx = max(x0 - x, 0.0, x - x1)
    dy = max(y0 - y, 0.0, y - y1)
    return math.hypot(dx, dy)


def sd_seg(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    h = clampf(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy))
    return math.hypot(px - ax - vx * h, py - ay - vy * h)


def build_field():
    """在 drop 前一瞬把版面画出来，逐格判断空位，按最近形状决定填充形制"""
    p = Plates()
    draw_group(p, DROP - 0.001, keep_dot=True, no_rule=True)
    draw_outer(p, DROP - 0.001, no_rule=True)
    ink = np.maximum(np.maximum(p.arr()["Y"], p.arr()["R"]),
                     np.maximum(p.arr()["B"], p.arr()["K"]))
    tx0, ty0, tx1, ty1 = TRIM
    cells = []
    for r in range(8):
        for c in range(tx0 // M, tx1 // M):
            y0 = Y0 + r * M
            sub = ink[y0 + 3:y0 + M - 2:M // 24, c * M + 3:(c + 1) * M - 2:M // 24]
            if sub.size and sub.max() > 8.0 / 255.0:
                continue
            x0 = c * M
            mx, my = x0 + M / 2, y0 + M / 2
            best, bd = None, 1e18
            for s in SH:
                d = s[5](mx, my) / s[4]
                if d < bd - 1e-6:
                    bd, best = d, s
            kx = x0 if best[2] < mx else x0 + M
            ky = y0 if best[3] < my else y0 + M
            form = best[1]
            if best[0] == "K" and form == "qd" and (r + c) % 2 == 1:
                form = "bar"
            cells.append(dict(x0=x0, y0=y0, kx=kx, ky=ky, mx=mx, my=my,
                              ink=best[0], form=form, sx=best[2], sy=best[3]))
    return cells


def draw_field(p, cells):
    for f in cells:
        x0, y0, kx, ky, mx, my = f["x0"], f["y0"], f["kx"], f["ky"], f["mx"], f["my"]
        form = f["form"]
        if form == "qd":
            if kx == x0:
                a0 = 0 if ky == y0 else 270
            else:
                a0 = 90 if ky == y0 else 180
            p.paint(f["ink"], p_sector(kx, ky, M, a0 * DEG))
        elif form == "hst":
            p.paint(f["ink"], p_poly([[kx, ky], [x0 + M if kx == x0 else x0, ky],
                                      [kx, y0 + M if ky == y0 else y0]]))
        elif form == "sq":
            p.paint(f["ink"], p_rect(x0 if kx == x0 else x0 + M / 2,
                                     y0 if ky == y0 else y0 + M / 2, M / 2, M / 2))
        elif form == "semi":
            hz = abs(f["sx"] - mx) >= abs(f["sy"] - my)
            if hz:
                p.paint(f["ink"], p_semi(kx, my, M / 2, (-90 if kx == x0 else 90) * DEG))
            else:
                p.paint(f["ink"], p_semi(mx, ky, M / 2, (0 if ky == y0 else 180) * DEG))
        elif form == "bar":
            p.paint(f["ink"], p_rect(x0 if kx == x0 else x0 + M / 2, y0, M / 2, M))


# ---------------------------------------------------------------- 背面：康定斯基三原色
def draw_back(t):
    p = Plates()
    p.paint("K", p_rect(TRIM[0], TRIM[1], TRIM[2] - TRIM[0], TRIM[3] - TRIM[1]))
    p.paint("Y", p_poly([[120, 780], [600, 780], [360, 300]]))
    p.paint("R", p_rect(720, 300, 480, 480))
    p.paint("B", p_circle(1560, 540, 240))
    # 色版描边（trap）：让颜色越过被挖空的黑色边界 2.5px，套印不准时不会露白缝
    p.erase("Y", lambda d: d.line([(120, 780), (600, 780), (360, 300), (120, 780)], fill=255, width=5))
    p.erase("R", lambda d: d.rectangle([720, 300, 1200, 780], outline=255, width=5))
    p.erase("B", lambda d: d.ellipse([1320, 300, 1800, 780], outline=255, width=5))
    n = sum(1 for tt in LABELS if snap(t) >= tt)
    for de, zh, x in [("GELB", "黄", 360), ("ROT", "红", 960), ("BLAU", "蓝", 1560)][:n]:
        # 挖掉黑版 → 露出纸张本色
        p.erase("K", lambda d, x=x, de=de: d.text((x - 8, 900), de, font=F(F_EN, 24), fill=0, anchor="ra"))
        p.erase("K", lambda d, x=x, zh=zh: d.text((x + 16, 901), zh, font=F(F_CN, 26), fill=0, anchor="la"))
    return p


# ---------------------------------------------------------------- 字标
TB = dict(x0=360, y0=780, x1=1800, y1=1020, em=180,
          cells=[("几", 420), ("何", 600), ("构", 780), ("成", 960), ("包", 1200), ("豪", 1380), ("斯", 1560)])


def title_on(t):
    return snap(t) >= FRONT_RESET


def draw_title(p, t):
    if not title_on(t):
        return
    p.paint("K", p_rect(TB["x0"], TB["y0"], TB["x1"] - TB["x0"], TB["y1"] - TB["y0"]))
    f = F(F_CN, TB["em"])
    for i, (g, x) in enumerate(TB["cells"]):
        cx = x + TB["em"] / 2
        if i < 4:      # 「几何构成」挖空到纸
            p.erase("K", lambda d, cx=cx, g=g: d.text((cx, 900), g, font=f, fill=0, anchor="mm"))
        else:          # 「包豪斯」印黄，并挖掉黑
            p.paint("Y", lambda d, cx=cx, g=g: d.text((cx, 900), g, font=f, fill=255, anchor="mm"))


def measure_type():
    f = F(F_EN, 100)
    img = Image.new("L", (300, 300), 0)
    d = ImageDraw.Draw(img)
    bb = d.textbbox((0, 0), "H", font=f)
    caph = (bb[3] - bb[1]) / 100.0
    size = M / caph
    ff = F(F_EN, size)
    word = list("BAUHAUS")
    adv = [d.textlength(c, font=ff) for c in word]
    bb0 = d.textbbox((0, 0), word[0], font=ff)
    bbn = d.textbbox((0, 0), word[-1], font=ff)
    bbL0 = bb0[0]
    bbRn = bbn[2]
    sumadv = sum(adv[:-1])
    length = 8 * M
    track = (length - (bbL0 + sumadv + bbRn)) / (len(word) - 1)
    xs = []
    x = bbL0
    for i in range(len(word)):
        xs.append(x)
        x += adv[i] + track
    # 德语说明词的中点（供中文成对对齐）
    f24 = F(F_EN, 24)
    o = 0.0
    mids = []
    for w in ["FORM", " · ", "FARBE", " · ", "FUNKTION"]:
        wd = tlen(d, w, f24, 7.2)
        if len(w.strip()) > 1:
            mids.append(o + (wd - 7.2) / 2.0)
        o += wd
    return dict(size=size, word=word, xs=xs, track=track, ff=ff, mids=mids)


def paste_local(p, ink, S, base_x, base_y):
    """把一张局部坐标的墨版贴进版面：局部 (x 右, y 下) → 世界 (base_x + y, base_y - x)
    即整体逆时针转 90°（文字自下而上读）。"""
    SH, SW = S.shape
    XW = base_x + np.arange(SH, dtype=np.int32)
    YW = base_y - np.arange(SW, dtype=np.int32)
    ox = (XW >= 0) & (XW < W)
    oy = (YW >= 0) & (YW < H)
    if not ox.any() or not oy.any():
        return
    full = np.zeros((H, W), np.float32)
    full[np.ix_(YW[oy], XW[ox])] = S.T[np.ix_(oy, ox)]
    p.paint_mask(ink, Image.fromarray(np.clip(full, 0, 255).astype(np.uint8), "L"))


def draw_type(p, t, TY):
    tg = snap(t)
    n = min(LETTERS["n"], int(math.floor((tg - LETTERS["t0"]) / LETTERS["step"] + 1e-6)) + 1)
    if tg >= LETTERS["t0"] and n > 0:
        AS, DS = 150, 46
        S = Image.new("L", (1020, AS + DS), 0)
        d = ImageDraw.Draw(S)
        for i in range(n):
            d.text((TY["xs"][i], AS), TY["word"][i], font=TY["ff"], fill=255, anchor="ls")
        paste_local(p, "K", np.asarray(S, np.float32), 240 - AS, 1020)

    if tg >= EV["type_small"]["t"]:
        AS2 = 34
        S = Image.new("L", (1020, AS2 + 24), 0)
        d = ImageDraw.Draw(S)
        tdraw(d, 0, AS2, "FORM · FARBE · FUNKTION", F(F_EN, 24), 255, 7.2, "left", "ls")
        paste_local(p, "K", np.asarray(S, np.float32), 291 - AS2, 1020)
        zh = [("形", "式"), ("色", "彩"), ("功", "能")]
        mids = TY["mids"]
        for i, pr in enumerate(zh):
            yc = 1020 - mids[i]
            p.paint("K", lambda d, a=pr[0], y=yc - 3: d.text((324, y), a, font=F(F_CN, 26), fill=255, anchor="ma"))
            p.paint("K", lambda d, a=pr[1], y=yc + 27: d.text((324, y), a, font=F(F_CN, 26), fill=255, anchor="ma"))
        p.paint("Y", p_poly([[264, 108], [288, 108], [276, 84]]))
        p.paint("R", p_rect(264, 120, 24, 24))
        p.paint("B", p_circle(276, 168, 12))


def draw_marks(p, t):
    for y in (30, 1050):
        p.paint("K", p_ring(CX, y, 10, 11.5))
        p.paint("K", p_rect(CX - 18, y - 0.75, 36, 1.5))
        p.paint("K", p_rect(CX - 0.75, y - 18, 1.5, 36))
    if snap(t) >= EV["marks"]["t"]:
        for x, y, sx in [(120, 60, -1), (1800, 60, 1), (120, 1020, -1), (1800, 1020, 1)]:
            sy = -1 if y < 540 else 1
            p.paint("K", p_rect(x - 40 if sx < 0 else x + 12, y - 0.75, 28, 1.5))
            p.paint("K", p_rect(x - 0.75, y - 40 if sy < 0 else y + 12, 1.5, 28))
    firsts = [("Y", EV["tri_in"]["t"]), ("R", EV["circle_land"]["t0"] + 0.05),
              ("B", EV["sq_scale"]["t0"] + 0.05), ("K", EV["bar_land"]["t0"] + 0.05)]
    for i, (ink, tt) in enumerate(firsts):
        if snap(t) >= tt:
            p.paint(ink, p_rect(1500 + i * 30, 1043, 24, 14))
    f = F(F_EN, 13)

    def label(d, s, x, y, align):
        tdraw(d, x, y, s, f, 255, 2.6, align)
    p.paint("K", lambda d: label(d, "BOGEN 11 — KONSTRUKTION IN 20 SCHLÄGEN · 120 BPM · M = 120 PX", 152, 1050, "left"))
    p.paint("K", lambda d: label(d, "KINETISCHES PLAKAT · Nº 11 · WEIMAR 1919", 1768, 30, "right"))
    n = int(clampf(math.floor(snap(t) / BEAT + 1e-6) + 1, 1, 20))
    p.paint("K", lambda d, s="SCHLAG %02d / 20" % n: label(d, s, 152, 30, "left"))


def render_front(t):
    p = Plates()
    draw_group(p, t)
    draw_outer(p, t)
    if casc_on(t):
        draw_field(p, FIELD)
    draw_title(p, t)
    draw_type(p, t, TY)
    draw_marks(p, t)
    return p


# ---------------------------------------------------------------- 网格进度
def grid_prog(t):
    gv = np.zeros(15, np.float32)
    wv = np.zeros(15, np.float32)
    gh = np.zeros(9, np.float32)
    wh = np.zeros(9, np.float32)

    def line(d, arr, warr, i):
        L = GRID["land0"] + d * GRID["step"]
        arr[i] = io2f(prog(t, L - GRID["draw"], L))
        pk = 2.0 if d <= 1 else 1.0
        rl = 8.0 / 30.0 if d <= 1 else GRID["relax"]
        warr[i] = pk if t < L else pk * (1 - io2f(prog(t, L, L + rl)))

    for i in range(15):
        line(abs(i - 7), gv, wv, i)
    for j in range(9):
        line(abs(j - 4), gh, wh, j)
    return gv, gh, wv, wh


# ---------------------------------------------------------------- 套印状态
def registration(t):
    q = snap(t)
    f = int(round(t * 30))
    rv, lock = EV["reveal"]["t"], EV["lock"]["t"]
    reg, dens, spread = 1.0, 0.955, 0.0
    if q >= RP["R2"]["start"] and q < rv:
        reg = 1 + 1.3 * in2f(prog(q, RP["R2"]["start"], rv - 1 / 30.0))
    elif q >= rv and q < FREEZE:
        reg = 0.15 + 0.85 * io2f(prog(q, RP["R4"]["start"], FREEZE))
    elif q >= FREEZE and q < lock:
        u = io2f(prog(q, FREEZE + 0.5, lock - 1 / 30.0))
        reg = 1 + 0.4 * u
        spread = 4.5 * u
    if q >= lock:
        reg, dens = 0.12, 0.985
    fr = f - int(round(rv * 30))
    fl = f - int(round(lock * 30))
    if fr == 0:
        dens += 0.12
    elif fr == 1:
        dens += 0.05
    if fl == 0:
        dens += 0.10
    elif fl == 1:
        dens += 0.04
    return reg, dens, spread


def camera(t):
    f = int(round(t * 30))
    fr = f - int(round(EV["reveal"]["t"] * 30))
    fl = f - int(round(EV["lock"]["t"] * 30))
    z = 1.03 if fr == 0 else (1.012 if fr == 1 else 1.0)
    dy = 2.0 if fl == 0 else (1.0 if fl == 1 else 0.0)
    return 0.0, dy, z


# ---------------------------------------------------------------- 级联（翻版）
def rot_tile(q0x, q0y, qx, qy, t):
    """R1：正面 120px 瓷砖各自绕中心旋转，波前从红圆心放射"""
    if t >= FRONT_RESET or t < RP["R1"]["start"]:
        return qx, qy, np.ones_like(qx)
    inb = (q0x >= 120) & (q0x < 1800) & (q0y >= 60) & (q0y < 1020)
    cx = (np.floor((q0x - 0.0) / 120.0) + 0.5) * 120.0
    cy = 60.0 + (np.floor((q0y - 60.0) / 120.0) + 0.5) * 120.0
    u = clamp((t - RP["R1"]["start"] - np.hypot(cx - 840.0, cy - 300.0) * R1_SPANK) / RP["R1"]["dur"])
    u = np.where(inb, u, 0.0)
    th = RP["R1"]["angle"] * DEG * io2(u)
    cs, sn = np.cos(th), np.sin(th)
    s = 1.0 / (np.abs(cs) + np.abs(sn))
    l0x, l0y = q0x - cx, q0y - cy
    lx, ly = qx - cx, qy - cy
    r0x = (cs * l0x + sn * l0y) / s
    r0y = (-sn * l0x + cs * l0y) / s
    rx = (cs * lx + sn * ly) / s
    ry = (-sn * lx + cs * ly) / s
    gap = sstep(0.0, 0.035, np.abs(np.sin(2 * th)))
    cov = clamp((60.0 - np.maximum(np.abs(r0x), np.abs(r0y))) * s + 0.5 + (1.0 - gap))
    turned = np.minimum(1.0, np.abs(sn) * 20.0)
    lim = 60.0 - 0.75 * turned + 4.0 * (1.0 - turned)
    rx = cx + np.clip(rx, -lim, lim)
    ry = cy + np.clip(ry, -lim, lim)
    cov = np.where(inb, cov, 1.0)
    return rx, ry, cov


def slide_col(q0x, q0y, qx, qy, t):
    """R3：背面 240px 立柱成对错位一格，波前自右向左；标签带静止"""
    if t < RP["R3"]["start"]:
        return qx, qy
    inb = (q0x >= 120) & (q0x < 1800) & (q0y >= 60) & (q0y < 1020)
    band = (q0y >= 840) & (q0y < 960)
    act = inb & (~band)
    col = np.floor((q0x - 120.0) / 240.0)
    cx = 240.0 + col * 240.0
    u = clamp((t - RP["R3"]["start"] - (1680.0 - cx) * R3_SPANK) / RP["R3"]["dur"])
    u = np.where(act, u, 0.0)
    direction = np.where(np.mod(col, 2.0) < 0.5, -1.0, 1.0)
    nx = np.clip(qx, cx - 119.25, cx + 119.25)
    ny = np.clip(qy - direction * RP["R3"]["dy"] * io2(u), 61.0, 1019.0)
    ny = np.where((q0y < 840.0) & (ny >= 840.0), 839.0, ny)
    ny = np.where((q0y >= 960.0) & (ny < 960.0), 960.0, ny)
    return nx, ny


def cascade_geom(p0x, p0y, qx, qy, t):
    """返回 (是否在级联中, 是否背面, 采样坐标, 覆盖度, 阴影)"""
    inb = (p0x >= 120) & (p0x < 1800) & (p0y >= 60) & (p0y < 1020)
    cx = 120.0 + (np.floor((p0x - 120.0) / 240.0) + 0.5) * 240.0
    cy = 60.0 + (np.floor((p0y - 60.0) / 240.0) + 0.5) * 240.0
    if t < RP["R4"]["start"]:
        u = clamp((t - RP["R2"]["start"] - ((cx - 120.0) + (cy - 60.0)) * R2_SPANK) / RP["R2"]["dur"])
        sc = np.cos(math.pi * io2(u))
        ax = False
    else:
        u = clamp((t - RP["R4"]["start"] - (R4_MXR - np.hypot(cx - CX, cy - CY)) * R4_SPANK) / RP["R4"]["dur"])
        sc = -np.cos(math.pi * io2(u))
        ax = True
    aa = np.abs(sc)
    sn = np.sqrt(np.maximum(0.0, 1.0 - sc * sc))
    back = sc < 0.0
    l0a = (p0x - cx) if not ax else (p0y - cy)
    l0b = (p0y - cy) if not ax else (p0x - cx)
    la = (qx - cx) if not ax else (qy - cy)
    lb = (qy - cy) if not ax else (qx - cx)
    fs = np.where(back, -1.0, 1.0) if not ax else np.where(back, -1.0, 1.0)
    xs = 1.0 - 0.22 * sn * (0.5 + 0.5 * fs * np.clip(l0a / 120.0, -1.0, 1.0))
    cov = clamp(120.0 * aa - np.abs(l0a) + 0.5) * clamp(120.0 * xs - np.abs(l0b) + 0.5)
    ca = np.clip(la / np.maximum(aa, 1e-4), -119.6, 119.6)
    cb = np.clip(lb / np.maximum(xs, 1e-4), -119.6, 119.6)
    if not ax:
        sxp = cx + cb
        syp = cy + ca
    else:
        sxp = cx + ca
        syp = cy + cb
    return inb, back, aa, sn, cov, sxp, syp


# ---------------------------------------------------------------- 印刷合成
def press(front, back, t):
    reg, dens, spread = registration(t)
    camx, camy, camz = camera(t)
    gv, gh, wv, wh = grid_prog(t)
    casc = casc_on(t)
    out = np.empty((H, W, 3), np.float32)
    pt = paper_tile()
    gt = grain_tile()
    fr = front.arr()
    bk = back.arr()
    frame = int(round(t * FPS))

    ys = np.arange(0, H, 240, dtype=np.int32)
    for y0 in ys:
        y1 = min(H, y0 + 240)
        px = (np.arange(W, dtype=np.float32)[None, :] + 0.5)
        py = (np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5)
        PX = np.broadcast_to(px, (y1 - y0, W))
        PY = np.broadcast_to(py, (y1 - y0, W))
        # 相机
        p = np.empty((y1 - y0, W, 2), np.float32)
        p[..., 0] = 960.0 + (PX - 960.0) / camz + camx
        p[..., 1] = 540.0 + (PY - 540.0) / camz + camy
        px_ = p[..., 0]
        py_ = p[..., 1]

        # 纸
        pl = sample(pt, np.mod(px_ / 2600.0 * 1024.0, 1024.0), np.mod(py_ / 2600.0 * 1024.0, 1024.0))
        tooth = pl - 0.82
        big = sample(pt, np.mod(px_ / 340.0 * 1024.0, 1024.0), np.mod(py_ / 340.0 * 1024.0, 1024.0)) - 0.5
        col = PAPER[None, None, :] * (1.0 + tooth * 0.30 + big * 0.018)[..., None]
        vcx = px_ / W - 0.5
        vcy = py_ / H - 0.5
        col = col * (1.0 - (vcx * vcx + vcy * vcy) * 0.10)[..., None]

        # 网格
        g = np.zeros_like(px_)
        for i in range(15):
            x = float(i + 1) * 120.0
            on = (np.abs(py_ - 540.0) <= gv[i] * 480.0).astype(np.float32)
            wdt = np.clip(mix(1.1, 3.2, np.minimum(wv[i], 1.0)) + 2.8 * max(wv[i] - 1.0, 0.0), 0.0, None)
            g = np.maximum(g, np.clip(wdt * 0.5 + 0.5 - np.abs(px_ - x), 0.0, 1.0) * on *
                           mix(0.28 if i == 7 else 0.17, 0.92, min(wv[i], 1.0)))
        for j in range(9):
            y = 60.0 + float(j) * 120.0
            on = (np.abs(px_ - 960.0) <= gh[j] * 960.0).astype(np.float32)
            wdt = np.clip(mix(1.1, 3.2, np.minimum(wh[j], 1.0)) + 2.8 * max(wh[j] - 1.0, 0.0), 0.0, None)
            g = np.maximum(g, np.clip(wdt * 0.5 + 0.5 - np.abs(py_ - y), 0.0, 1.0) * on *
                           mix(0.28 if j == 4 else 0.17, 0.92, min(wh[j], 1.0)))

        # 粗糙边（分色版共用的手绘抖动）
        rough_x = (vnoise(px_, py_, 5.0) - 0.5) * 1.3 + (vnoise(px_ + 3.1, py_ + 8.7, 1.6) - 0.5) * 0.35
        rough_y = (vnoise(px_ + 17.3, py_ + 17.3, 5.0) - 0.5) * 1.3 + \
            (vnoise(px_ + 3.1, py_ + 8.7, 1.6) - 0.5) * 0.35
        rough_x = rough_x * 1.3
        rough_y = rough_y * 1.3

        offs = {
            "Y": (rough_x + spread, rough_y),
            "R": (rough_x + 1.3 * reg, rough_y - 0.9 * reg),
            "B": (rough_x - 1.0 * reg, rough_y + 1.2 * reg),
            "K": (rough_x + 0.5 * reg, rough_y + 0.4 * reg),
        }

        m = {}
        shade = np.zeros_like(px_)
        for ink in "YRBK":
            ox, oy = offs[ink]
            qx, qy = px_ + ox, py_ + oy
            if casc:
                inb, back, aa, sn, cov, sxp, syp = cascade_geom(px_, py_, qx, qy, t)
                # 背面采样坐标（R3 错位）
                bx, by = slide_col(px_, py_, qx, qy, t)
                # 正面采样坐标（R1 瓷砖旋转）
                fx_, fy_, fcov = rot_tile(px_, py_, qx, qy, t)
                fF_flat = sample(fr[ink], fx_, fy_) * fcov
                fB_flat = sample(bk[ink], bx, by)
                backv = np.where(back, fB_flat, fF_flat)
                board = mix(1.0 if ink == "K" else 0.0, backv, sstep(0.72, 0.96, aa))
                fv = np.where(back, sample(bk[ink], *slide_col(px_, py_, sxp, syp, t)),
                              sample(fr[ink], *rot_tile(px_, py_, sxp, syp, t)[:2]))
                val = np.where(aa > 0.9995, backv, np.where(aa < 0.002, board,
                                                            mix(board, fv, cov)))
                val = np.where(inb, val, fF_flat)
                shade = np.where(inb, np.where(aa > 0.9995, 0.0, np.where(aa < 0.002, 0.0, cov * sn)), 0.0)
            else:
                fx_, fy_, fcov = rot_tile(px_, py_, qx, qy, t)
                val = sample(fr[ink], fx_, fy_) * fcov
            m[ink] = val

        mottle = vnoise(px_, py_, 9.0) * 0.5 + vnoise(px_, py_, 37.0) * 0.5
        dd = np.clip(dens + 0.06 * (mottle - 0.5) + tooth * 0.35, 0.0, 1.1 if dens > 1.0 else 1.0)
        inkmax = np.maximum(np.maximum(m["Y"], m["R"]), np.maximum(m["B"], m["K"]))
        col = col * (1.0 - g * (1.0 - np.clip(inkmax * 1.2, 0.0, 1.0)))[..., None]
        for ink in "YRBK":
            k = np.minimum(1.0, dd + (0.03 if ink == "K" else 0.0))
            col = col * mix(1.0, (INKC[ink] / PAPER)[None, None, :], (m[ink] * k)[..., None])
        col = col * (1.0 - 0.2 * shade)[..., None]
        col = np.maximum(col, 0.0)

        # 颗粒 + 抖动
        gx = np.mod(px + hash1(frame, 1.7) * 2048.0, 2048.0)
        gy = np.mod(py + hash1(frame, 9.1) * 2048.0, 2048.0)
        gr = sample(gt, gx, gy) - 0.5
        col = col + gr[..., None] * 0.045
        col = col + ((hash2(px, py, frame) - 0.5) / 255.0)[..., None]
        out[y0:y1] = col

    return np.clip(out, 0.0, 1.0)


def hash1(a, b):
    x = (a * 123.34 + b * 456.21)
    x = x - np.floor(x)
    return float(x)


def hash2(px, py, frame):
    x = np.mod(px * 0.1031 + frame * 0.31, 1.0)
    y = np.mod(py * 0.1031 + frame * 0.17, 1.0)
    z = np.mod((px + py) * 0.0707 + frame * 0.11, 1.0)
    return np.mod((x + y) * z, 1.0)


# ---------------------------------------------------------------- 单帧
FIELD = None
TY = None


def init_once():
    global FIELD, TY
    if FIELD is None:
        FIELD = build_field()
    if TY is None:
        TY = measure_type()


def render_frame(t):
    init_once()
    front = render_front(t)
    back = draw_back(t)
    return press(front, back, t)


# ---------------------------------------------------------------- CLI
def save(img, path):
    a = np.clip(img * 255.0 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(a, "RGB").save(path, quality=95)


def cmd_one(t, out):
    t0 = time.time()
    save(render_frame(t), out)
    print("%s  t=%.2fs  %.1fs" % (out, t, time.time() - t0))


def _worker(args):
    i, = args
    save(render_frame(i / FPS), os.path.join(ROOT, "frames", "f_%04d.png" % i))
    return i


def cmd_all(workers=3, lo=0, hi=None):
    os.makedirs(os.path.join(ROOT, "frames"), exist_ok=True)
    n = int(round(DUR * FPS))
    if hi is None:
        hi = n
    idx = list(range(lo, min(hi, n)))
    t0 = time.time()
    import multiprocessing as mp
    with mp.Pool(workers) as pool:
        done = 0
        for _ in pool.imap_unordered(_worker, [(i,) for i in idx], chunksize=2):
            done += 1
            if done % 20 == 0 or done == len(idx):
                el = time.time() - t0
                r = done / max(el, 1e-3)
                print("  %3d/%d  %.2f 帧/秒  ETA %.1f 分钟" % (
                    done, len(idx), r, (len(idx) - done) / max(r, 1e-3) / 60.0), flush=True)
    print("完成 %d 帧，用时 %.1f 分钟" % (len(idx), (time.time() - t0) / 60.0))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if cmd == "one":
        cmd_one(float(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "prev_one.png")
    elif cmd == "all":
        cmd_all(int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    elif cmd == "range":
        cmd_all(int(sys.argv[4]) if len(sys.argv) > 4 else 3, int(sys.argv[2]), int(sys.argv[3]))
    else:
        for t in [0.6, 1.6, 2.6, 3.6, 4.6, 5.6, 6.15, 6.7, 7.3, 7.8, 8.6, 9.6]:
            cmd_one(t, os.path.join(ROOT, "prev_%.2f.png" % t))
