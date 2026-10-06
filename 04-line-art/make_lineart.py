# -*- coding: utf-8 -*-
"""04 线条动画（LINE ART）：一根金线一笔画——种子、芽叶、天际线、回环、圆日
单条采样路径按进度揭示（SVG 描边动画的 PIL 版），60fps，8s。
用法: python make_lineart.py preview | all
"""
import math, sys, os
from PIL import Image, ImageDraw

OUT = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(OUT, "frames")

W, H = 1600, 1000
SS = 2
FPS = 60
DUR = 8.0
NF = int(DUR * FPS)

T_DRAW = 7.45          # 描线总时长
T_FILL0 = 7.45         # 圆日灌金开始
FILLD = 0.5

BG      = (13, 22, 38)
HALO    = (17, 29, 48)
GOLD    = (219, 178, 106)
GOLD_DIM = (96, 77, 45)
FILL    = (233, 198, 128)
TIP     = (249, 230, 172)

SUN = (760, 205)
SUN_R = 130
GROUND = 780

# ---------------- 路径基元采样（步长≈3px） ----------------
STEP = 3.0

def _line(a, b):
    n = max(2, int(math.dist(a, b) / STEP))
    return [(a[0] + (b[0]-a[0])*i/n, a[1] + (b[1]-a[1])*i/n) for i in range(1, n + 1)]

def _bez(p0, p1, p2, p3):
    # 先粗估长度再按步长采样
    coarse = [((1-u)**3*p0[0] + 3*u*(1-u)**2*p1[0] + 3*u*u*(1-u)*p2[0] + u**3*p3[0],
               (1-u)**3*p0[1] + 3*u*(1-u)**2*p1[1] + 3*u*u*(1-u)*p2[1] + u**3*p3[1])
              for u in [i/12 for i in range(13)]]
    L = sum(math.dist(coarse[i], coarse[i+1]) for i in range(12))
    n = max(4, int(L / STEP))
    return [((1-u)**3*p0[0] + 3*u*(1-u)**2*p1[0] + 3*u*u*(1-u)*p2[0] + u**3*p3[0],
             (1-u)**3*p0[1] + 3*u*(1-u)**2*p1[1] + 3*u*u*(1-u)*p2[1] + u**3*p3[1])
            for i in range(1, n + 1) for u in [i/n]]

def _arc(c, r, a0, a1):
    n = max(4, int(abs(a1 - a0) * r / STEP))
    return [(c[0] + r * math.cos(a0 + (a1 - a0) * i / n),
             c[1] + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(1, n + 1)]

def _spiral(c, r0, r1, a0, a1):
    n = max(20, int((r1 - r0 + abs(a1 - a0) * (r0 + r1) / 2) / STEP))
    return [(c[0] + (r0 + (r1 - r0) * i / n) * math.cos(a0 + (a1 - a0) * i / n),
             c[1] + (r0 + (r1 - r0) * i / n) * math.sin(a0 + (a1 - a0) * i / n))
            for i in range(1, n + 1)]

def build_path():
    P = []
    add = P.extend
    # 1. 种子螺旋（2 圈，蓬松一点）
    add(_spiral((140, 720), 4, 26, 0.0, -12.6))
    # 2. 茎：螺旋出口向右上
    add(_bez((166, 719), (180, 700), (190, 676), (196, 652)))
    # 3. 叶1：整圆环叶（右侧）
    add(_arc((212, 652), 16, math.pi, math.pi - 2 * math.pi))
    # 4. 茎继续向上
    add(_bez((196, 652), (194, 640), (192, 632), (190, 624)))
    # 5. 叶2：小环叶
    add(_arc((201, 624), 11, math.pi, math.pi - 2 * math.pi))
    # 6. 长弧降到地面起点（走左侧，避开叶环）
    add(_bez((190, 624), (150, 650), (95, 715), (70, 780)))
    # 7. 地面
    add(_line((70, GROUND), (320, GROUND)))
    # 8. 天际线（共享墙剪影，笔不离纸）
    add(_line((320, GROUND), (320, 590)))            # b1 左墙
    add(_line((320, 590), (470, 590)))               # b1 顶
    add(_line((470, 590), (470, 470)))               # b1右墙 -> b2顶
    add(_line((470, 470), (560, 470)))               # b2 顶
    add(_line((560, 470), (560, 570)))               # -> b3顶
    add(_line((560, 570), (590, 570)))               # b3 阶梯
    add(_line((590, 570), (590, 540)))
    add(_line((590, 540), (620, 540)))
    add(_line((620, 540), (620, 570)))
    add(_line((620, 570), (650, 570)))
    add(_line((650, 570), (650, 380)))               # -> b4顶
    add(_line((650, 380), (695, 380)))               # b4 顶+短天线
    add(_line((695, 380), (715, 352)))
    add(_line((715, 352), (735, 380)))
    add(_line((735, 380), (780, 380)))
    add(_line((780, 380), (780, 470)))               # -> b5拱脚
    add(_arc((830, 470), 50, math.pi, 2 * math.pi))  # b5 拱顶
    add(_line((880, 470), (880, 480)))               # -> b6顶
    add(_line((880, 480), (960, 480)))               # b6 顶
    add(_line((960, 480), (960, 580)))               # -> b7顶
    add(_line((960, 580), (990, 580)))               # b7 尖塔
    add(_line((990, 580), (1012, 475)))
    add(_line((1012, 475), (1034, 580)))
    add(_line((1034, 580), (1060, 580)))
    add(_line((1060, 580), (1060, 620)))             # -> b8顶
    add(_line((1060, 620), (1150, 620)))             # b8 顶
    add(_line((1150, 620), (1150, GROUND)))          # b8 右墙落地
    # 9. 地面右段
    add(_line((1150, GROUND), (1290, GROUND)))
    # 10. 收笔回环（一圈）
    add(_bez((1290, GROUND), (1345, GROUND), (1372, 774), (1395, 773)))
    add(_arc((1395, 715), 58, math.pi/2, math.pi/2 - 2 * math.pi))
    add(_bez((1395, 773), (1450, 772), (1520, 748), (1545, 700)))
    # 11. 甩上高空
    add(_bez((1545, 700), (1608, 596), (1568, 356), (1420, 218)))
    add(_bez((1420, 218), (1300, 96), (1020, 62), (873, 140)))
    # 12. 圆日（从 -30° 视觉逆时针一整圈）
    a0 = -math.pi / 6
    add(_arc(SUN, SUN_R, a0, a0 - 2 * math.pi))
    return P

PTS = build_path()
NPTS = len(PTS)

def clamp01(x): return max(0.0, min(1.0, x))
def eio_sine(x): x = clamp01(x); return -(math.cos(math.pi * x) - 1) / 2
def eob(x, s=1.70158):
    x = clamp01(x); x -= 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2
def lerp(a, b, p): return a + (b - a) * p

def stroke_slice(p):
    """返回进度 p (0..1) 对应的已画点列表（含亚像素笔尖）"""
    idx = p * (NPTS - 1)
    base = int(idx)
    pts = PTS[:base + 1]
    if base + 1 < NPTS:
        fr = idx - base
        a, b = PTS[base], PTS[base + 1]
        pts = pts + [(lerp(a[0], b[0], fr), lerp(a[1], b[1], fr))]
    return pts

def draw_stroke(d, pts, S):
    scaled = [(x * S, y * S) for x, y in pts]
    d.line(scaled, fill=GOLD_DIM, width=int(9 * S), joint="curve")   # 微光
    d.line(scaled, fill=GOLD, width=int(2.6 * S), joint="curve")     # 金线
    r = 1.3 * S
    for x, y in (scaled[0], scaled[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=GOLD)

def render(f):
    t = f / FPS
    S = SS
    img = Image.new("RGB", (W * S, H * S), BG)
    d = ImageDraw.Draw(img)
    # 圆日后的暗晕
    hr = 300 * S
    d.ellipse([SUN[0]*S - hr, SUN[1]*S - hr, SUN[0]*S + hr, SUN[1]*S + hr], fill=HALO)

    p = eio_sine(t / T_DRAW)
    pts = stroke_slice(p)
    draw_stroke(d, pts, S)

    # 笔尖亮点
    if t < T_DRAW:
        tip = pts[-1]
        r = 4.5 * S
        d.ellipse([tip[0]*S - r, tip[1]*S - r, tip[0]*S + r, tip[1]*S + r], fill=TIP)
        r2 = 9 * S
        d.ellipse([tip[0]*S - r2, tip[1]*S - r2, tip[0]*S + r2, tip[1]*S + r2],
                  outline=GOLD_DIM, width=S)

    # 圆日灌金
    if t > T_FILL0:
        fr = SUN_R * eob((t - T_FILL0) / FILLD, s=1.6)
        if fr > 1:
            d.ellipse([SUN[0]*S - fr*S, SUN[1]*S - fr*S,
                       SUN[0]*S + fr*S, SUN[1]*S + fr*S], fill=FILL)

    return img.resize((W, H), Image.LANCZOS)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "preview":
        for fr in (48, 96, 240, 378, 426, 474):
            render(fr).save(os.path.join(OUT, "prev_%03d.png" % fr))
        print("PREVIEW DONE  path points:", NPTS)
    else:
        os.makedirs(FRAMES, exist_ok=True)
        for i in range(NF):
            render(i).save(os.path.join(FRAMES, "f_%04d.png" % i))
            if i % 120 == 0:
                print("frame", i, "/", NF)
        print("done:", NF, "frames")
