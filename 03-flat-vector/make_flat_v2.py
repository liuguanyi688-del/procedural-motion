# -*- coding: utf-8 -*-
"""扁平矢量 v2（丝滑重制版）：60fps、真抛物线重力、接地锚定压扁、
预备动作、速度方向拉伸、落地粒子、成型冲击环。
8s 一镜到底。用法: python make_flat2.py preview | all
"""
import math, random, sys, os
from PIL import Image, ImageDraw

OUT = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(OUT, "frames2")

W, H = 1600, 1000
SS = 2
FPS = 60
DUR = 8.0
NF = int(DUR * FPS)

BG       = (30, 48, 226)
BG_DEEP  = (26, 42, 218)
BUILD    = (59, 79, 240)
BUILD2   = (48, 67, 232)
WINDOW   = (26, 43, 205)
CORAL    = (249, 86, 77)
CREAM    = (244, 227, 194)
DASH     = (252, 248, 238)
ACCENT   = (86, 106, 246)

ROAD_Y, ROAD_H = 820, 180
SUN = (1200, 228)
SUN_R = 150
DOT_R = 55

BUILDINGS = [(655, 95, 70, 11), (780, 115, 150, 12), (905, 135, 230, 13),
             (1060, 150, 330, 14), (1220, 165, 430, 15), (1380, 125, 280, 16),
             (1490, 105, 170, 17)]

# ---------------- 时间轴（秒） ----------------
T_FALL0, T_FALLD = 2.10, 0.45
IMPS = [(2.55, 2.65, 0.42), (3.20, 3.29, 0.34), (3.71, 3.79, 0.28), (4.09, 4.16, 0.22)]
BOUNCES = [(2.65, 3.20, 300), (3.29, 3.71, 115), (3.79, 4.09, 30)]
T_ROLL0, T_ROLL1 = 4.16, 4.42
T_CR0, T_CR1 = 4.42, 4.62
T_FL0, T_FL1 = 4.62, 5.34
T_BURST = 5.34
T_RAY0 = 5.40
RAY_ORDER = [3, 2, 4, 1, 5, 0, 6]   # 从正下方往两侧依次亮

X0_FALL = 800
X_CHAIN = [X0_FALL, 826, 856, 880]  # 每次落点
X_ROLL_END = 942
P_FLIGHT = ((X_ROLL_END, ROAD_Y - DOT_R), (1150, 300), SUN)

# ---------------- 缓动 ----------------
def clamp01(x): return max(0.0, min(1.0, x))
def eoc(x): x = clamp01(x); return 1 - (1 - x) ** 3
def eio(x):
    x = clamp01(x)
    return 2 * x * x if x < 0.5 else 1 - 2 * (1 - x) ** 2
def eob(x, s=1.70158):
    x = clamp01(x); x -= 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2
def lerp(a, b, p): return a + (b - a) * p
def mixc(c1, c2, p): return tuple(int(lerp(a, b, p)) for a, b in zip(c1, c2))

def cap_line(d, x1, y1, x2, y2, w, fill):
    d.line([x1, y1, x2, y2], fill=fill, width=int(w))
    r = w / 2
    for x, y in ((x1, y1), (x2, y2)):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

def ell_poly(x, y, ra, rb, ang, n=48):
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for i in range(n):
        ph = 2 * math.pi * i / n
        ex, ey = ra * math.cos(ph), rb * math.sin(ph)
        pts.append((x + ex * ca - ey * sa, y + ex * sa + ey * ca))
    return pts

# ---------------- 粒子 ----------------
PARTS = []
def _mk_parts():
    rng = random.Random(99)
    for ti in (2.60, 3.245, 3.75, 4.125):          # 每次砸地溅起小液滴
        x = X_CHAIN[IMPS.index([i for i in IMPS if i[0] == ti][0])] if False else None
    for (t0, t1, amp), xc in zip(IMPS, X_CHAIN):
        for k in range(4):
            PARTS.append((t1, xc, ROAD_Y, rng.uniform(-150, 150),
                          rng.uniform(-300, -170), rng.uniform(7, 13), rng.uniform(0.35, 0.5), 900))
    for k in range(10):                            # 太阳成型爆发
        a = 2 * math.pi * k / 10 + 0.3
        sp = rng.uniform(260, 430)
        PARTS.append((T_BURST, SUN[0], SUN[1], math.cos(a) * sp, math.sin(a) * sp,
                      rng.uniform(9, 16), rng.uniform(0.55, 0.8), 260))
_mk_parts()

def draw_parts(d, t, S):
    for (t0, x, y, vx, vy, size, life, grav) in PARTS:
        p = (t - t0) / life
        if not 0 < p < 1:
            continue
        dt = p * life
        px = (x + vx * dt) * S
        py = (y + vy * dt + 0.5 * grav * dt * dt) * S
        r = size * (1 - p) * S
        d.ellipse([px - r, py - r, px + r, py + r], fill=mixc(CORAL, BG, p))

# ---------------- 渲染 ----------------
def render(f):
    t = f / FPS
    S = SS
    img = Image.new("RGB", (W * S, H * S), BG)
    d = ImageDraw.Draw(img)

    # 背景深色大圆（若隐若现的层次）
    d.ellipse([-260 * S, 150 * S, 760 * S, 1170 * S], fill=BG_DEEP)

    # 路面
    rp = eoc(t / 0.55)
    ry = (H - ROAD_H * rp) * S
    d.rectangle([0, ry, W * S, H * S], fill=CREAM)
    # 白虚线：弹出后匀速向右输送
    off = max(0.0, t - 1.0) * 36
    k = 0
    for x0 in range(-420, W + 60, 118):
        p = eob((t - (0.30 + k * 0.022)) / 0.35, s=1.9)
        k += 1
        if p <= 0:
            continue
        wdt = 76 * S * p
        cx = (x0 + 38 + off) * S
        d.rounded_rectangle([cx - wdt / 2, 905 * S - 8 * S, cx + wdt / 2, 905 * S + 8 * S],
                            radius=8 * S, fill=DASH)

    # 楼群
    for i, (cx, bw, bh, seed) in enumerate(BUILDINGS):
        rngb = random.Random(seed)
        st = 0.35 + i * 0.10 + rngb.uniform(-0.02, 0.02)
        p = eob((t - st) / 0.6, s=1.9)
        if p <= 0:
            continue
        h = bh * p * S
        col = BUILD if i % 2 == 0 else BUILD2
        x0, x1 = (cx - bw / 2) * S, (cx + bw / 2) * S
        y0 = ROAD_Y * S - h
        d.rectangle([x0, y0, x1, ROAD_Y * S], fill=col)
        if p > 0.6:
            wa = clamp01((p - 0.6) / 0.4)
            rows = max(1, int(bh / 90))
            for r_ in range(rows):
                for c_ in range(2):
                    if rngb.random() < 0.25:
                        continue
                    ph = rngb.random()
                    tw = 0.5 + 0.5 * math.sin(2 * math.pi * (0.22 * t + ph))
                    wx = x0 + (0.30 + 0.42 * c_) * bw * S
                    wy = y0 + (0.18 + 0.16 * r_) * bh * S
                    d.rounded_rectangle([wx - 7 * S, wy - 10 * S, wx + 7 * S, wy + 10 * S],
                                        radius=4 * S,
                                        fill=mixc(col, WINDOW, wa * (0.35 + 0.65 * tw)))

    # 胶囊：滑入 + 漂浮
    pp = eob((t - 0.95) / 0.7, s=1.4)
    if pp > 0:
        px = lerp(-260, 600, pp) * S
        py = (590 + 9 * math.sin(2 * math.pi * 0.4 * t)) * S
        ang = -33 + 8 * math.sin(2 * math.pi * 0.33 * t + 1)
        pw, ph = 210 * S, 92 * S
        lay = Image.new("RGBA", (int(pw + 60 * S), int(ph + 60 * S)), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rounded_rectangle([30 * S, 30 * S, 30 * S + pw, 30 * S + ph],
                             radius=ph / 2, fill=ACCENT + (255,))
        lay = lay.rotate(-ang, expand=True, resample=Image.BICUBIC)
        img.paste(lay, (int(px - lay.width / 2), int(py - lay.height / 2)), lay)
    # 扇形
    fp = eob((t - 1.15) / 0.6, s=1.6)
    if fp > 0:
        a0 = lerp(-100, -8, fp) + 4 * math.sin(2 * math.pi * 0.27 * t)
        d.pieslice([1300 * S, 560 * S, 1560 * S, 820 * S], start=a0, end=a0 + 92, fill=ACCENT)
    # 叉
    xp = eob((t - 1.35) / 0.5, s=2.0)
    if xp > 0:
        cx, cy, r = 1480 * S, 400 * S, 34 * S * xp
        a = math.radians(42 + 12 * math.sin(2 * math.pi * 0.25 * t + 2))
        for sgn in (1, -1):
            cap_line(d, cx - r * math.cos(a), cy - sgn * r * math.sin(a),
                     cx + r * math.cos(a), cy + sgn * r * math.sin(a), 24 * S, ACCENT)

    # 成型冲击环
    if t > T_BURST:
        p = clamp01((t - T_BURST) / 0.7)
        ring_r = (170 + 300 * eoc(p)) * S
        rw = max(2, 16 * (1 - p)) * S
        d.ellipse([SUN[0] * S - ring_r, SUN[1] * S - ring_r,
                   SUN[0] * S + ring_r, SUN[1] * S + ring_r],
                  outline=mixc(CORAL, BG, p), width=int(rw))

    # ---------------- 圆点状态机 ----------------
    r = DOT_R * S
    sqx = sqy = 1.0
    ang = 0.0
    stretch = 0.0
    pos = None

    if t < T_FALL0:
        pos = None
    elif t < T_FALL0 + T_FALLD:                     # 重力下落 + 速度拉伸
        u = (t - T_FALL0) / T_FALLD
        st = 0.30 * math.sin(math.pi * u)
        pos = (X0_FALL * S, lerp(-120 * S, ROAD_Y * S - r, u * u))
        sqx, sqy = 1 / (1 + st * 0.6), 1 + st
    elif t < T_ROLL0:                               # 砸地 / 抛物线回弹
        for (t0, t1, amp) in IMPS:
            if t0 <= t < t1:
                s_ = math.sin(math.pi * (t - t0) / (t1 - t0))
                sqy = 1 - amp * s_
                sqx = 1 + amp * 0.8 * s_
                pos = (0, 0)                        # 占位，x 稍后取
                xi = X_CHAIN[IMPS.index((t0, t1, amp))]
                pos = (xi * S, ROAD_Y * S - r * sqy)  # 底部锚定地面
                break
        if pos is None:
            for bi, (t0, t1, hgt) in enumerate(BOUNCES):
                if t0 <= t < t1:
                    u = (t - t0) / (t1 - t0)
                    x = lerp(X_CHAIN[bi], X_CHAIN[bi + 1], u) * S
                    y = ROAD_Y * S - r - hgt * 4 * u * (1 - u) * S   # 真抛物线
                    pos = (x, y)
                    break
    elif t < T_ROLL1:                               # 减速滚动
        u = (t - T_ROLL0) / (T_ROLL1 - T_ROLL0)
        pos = (lerp(X_CHAIN[3], X_ROLL_END, eoc(u)) * S, ROAD_Y * S - r)
    elif t < T_CR1:                                 # 预备下蹲（蓄力）
        u = eio((t - T_ROLL0) / (T_CR1 - T_ROLL0))
        sqy = 1 - 0.30 * u
        sqx = 1 + 0.24 * u
        pos = (X_ROLL_END * S, ROAD_Y * S - r * sqy)
    elif t < T_FL1:                                 # 弹射：贝塞尔 + 顺速度方向拉伸
        u = (t - T_FL0) / (T_FL1 - T_FL0)
        (x0_, y0_), (x1_, y1_), (x2_, y2_) = P_FLIGHT
        px = (1 - u) ** 2 * x0_ + 2 * u * (1 - u) * x1_ + u ** 2 * x2_
        py = (1 - u) ** 2 * y0_ + 2 * u * (1 - u) * y1_ + u ** 2 * y2_
        e = 0.01
        dxx = (2 * (1 - u) * (x1_ - x0_) + 2 * u * (x2_ - x1_))
        dyy = (2 * (1 - u) * (y1_ - y0_) + 2 * u * (y2_ - y1_))
        ang = math.atan2(dyy, dxx)
        stretch = 0.33 * math.sin(math.pi * u)
        r = DOT_R * S + (SUN_R * S - DOT_R * S) * eoc(u)
        pos = (px * S, py * S)
    else:                                           # 太阳呼吸
        dtb = t - T_BURST
        r = SUN_R * S * (1 + 0.02 * math.sin(2 * math.pi * 0.9 * dtb))
        pos = (SUN[0] * S, (SUN[1] + 4 * math.sin(2 * math.pi * 0.45 * dtb)) * S)

    # 光芒
    if t > T_RAY0:
        rr_base = r if t >= T_FL1 else SUN_R * S
        for j in range(7):
            p = eob((t - (T_RAY0 + RAY_ORDER[j] * 0.055)) / 0.45, s=2.4)
            if p <= 0:
                continue
            a = math.radians(24 + j * 22 + 3 * math.sin(2 * math.pi * 0.5 * t + j))
            L = 60 * S * p * (0.93 + 0.07 * math.sin(2 * math.pi * 0.6 * t + j))
            r1 = rr_base + 24 * S * p
            r2 = r1 + L
            cap_line(d, SUN[0] * S + math.cos(a) * r1, SUN[1] * S + math.sin(a) * r1,
                     SUN[0] * S + math.cos(a) * r2, SUN[1] * S + math.sin(a) * r2,
                     25 * S, CORAL)

    draw_parts(d, t, S)

    if pos is not None:
        if stretch > 0.01:
            a_len = r * (1 + stretch)
            a_perp = r / (1 + stretch * 0.5)
            d.polygon(ell_poly(pos[0], pos[1], a_len, a_perp, ang), fill=CORAL)
        else:
            d.ellipse([pos[0] - r * sqx, pos[1] - r * sqy,
                       pos[0] + r * sqx, pos[1] + r * sqy], fill=CORAL)

    return img.resize((W, H), Image.LANCZOS)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "preview":
        for fr in (141, 156, 273, 299, 327, 450):
            render(fr).save(os.path.join(OUT, "v2_%04d.png" % fr))
        print("PREVIEW DONE")
    else:
        os.makedirs(FRAMES, exist_ok=True)
        for i in range(NF):
            render(i).save(os.path.join(FRAMES, "f_%04d.png" % i))
            if i % 120 == 0:
                print("frame", i, "/", NF)
        print("done:", NF, "frames")
