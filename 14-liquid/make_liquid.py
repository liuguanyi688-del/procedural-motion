# -*- coding: utf-8 -*-
"""
14 · 液态流动 Liquid Motion — drop「万物始于一滴」
=====================================================
一滴水落下、弹跳、融合、跃起、决堤淹没全屏，退去时留下一个液态的字标 drop。

没有 3D 引擎、没有 GLSL。这一版的全部技巧是**把画面当成一个距离场**：
每一个水滴、每一根拉丝、每一个字母，都只是往同一个场里丢一个 SDF，
用 log-sum-exp 做平滑并集——它们就会自己粘在一起、拉出丝、融成一体。
液体的一切"生命感"都来自这一次平滑并集。

    python make_liquid.py preview         # 关键帧预览
    python make_liquid.py one 6.5 a.png   # 单帧
    python make_liquid.py all 3           # 600 帧 → frames/
"""

import os
import sys
import math
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

np.seterr(all="ignore")

# ----------------------------------------------------------------- 规格
W, H = 1920, 1080
FPS = 60
ANIM_FPS = 30                 # 参考是 30fps 动画
DUR = 10.0
FY = 872.0                    # 地板接触线
HOR = 786.0                   # 地平线
G = 5000.0                    # 重力 px/s²
ROOT = os.path.dirname(os.path.abspath(__file__))

F_UI = "C:/Windows/Fonts/Dengb.ttf"        # 中文副标题
F_EN = "C:/Windows/Fonts/Segoeui.ttf"      # 英文副标题
F_HERO = "C:/Windows/Fonts/BOOKOSB.TTF"    # 字标 drop（圆润粗衬线）

# ----------------------------------------------------------------- 时间轴（150 BPM）
BPM = 150
BEAT = 60.0 / BPM             # 0.4 s
CUES = dict(
    pour=0.0, rain=0.4, fuse=2.0, leap=3.2, flood=4.0, immersed=4.42,
    reveal=4.85, gather=5.75, gap=6.2, drop=6.4, glint=7.1, drip=7.6,
    ripple=8.4, end=10.0, pour_snap=0.167,
    merges=[2.0, 2.4, 2.8], apex=3.6,
    flood_in=4.035, flood_full=4.42,
    reveal_start=4.55, reveal_end=5.35,
    logo_snap=6.4, glint_t=7.2, drip_land=8.4, drip_snap=8.567,
    tagline_start=8.42, outro=8.8,
)
# 四滴的落点：时刻 / x / 大小 / 色相
LANDINGS = [(0.40, 640.0, 1.00, 0.05), (0.80, 1250.0, 0.85, 0.62),
            (1.20, 405.0, 0.80, 0.95), (1.60, 960.0, 1.35, 0.36)]
WORD = "drop"
WORD_U = [0.05, 0.30, 0.55, 0.85]          # 四个字母的色相：橘 → 粉 → 粉紫 → 紫

F = lambda t: int(round(t * ANIM_FPS))


# ----------------------------------------------------------------- 基础
def sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def clip(x, a=0.0, b=1.0):
    return np.clip(x, a, b)


def mixc(a, b, x):
    """颜色混合：a/b 是 (3,) 或 (N,3)，x 是标量或可广播数组"""
    return a + (b - a) * x


def bezier(p1x, p1y, p2x, p2y, n=1024):
    """三次贝塞尔缓动，返回查表函数"""
    ts = np.linspace(0.0, 1.0, n, dtype=np.float64)
    omt = 1.0 - ts
    xs = 3 * omt * omt * ts * p1x + 3 * omt * ts * ts * p2x + ts ** 3
    ys = 3 * omt * omt * ts * p1y + 3 * omt * ts * ts * p2y + ts ** 3
    xs = np.maximum.accumulate(xs)

    def f(x):
        xa = np.clip(x, 0.0, 1.0)
        return np.interp(xa, xs, ys)
    return f


eInOut = bezier(0.65, 0.0, 0.35, 1.0)
eIn = bezier(0.5, 0.0, 0.9, 0.4)
eOut = bezier(0.33, 0.9, 0.4, 1.0)
eFront = bezier(0.28, 0.55, 0.42, 1.0)


def spring(t, f=4.0, z=0.3):
    """过冲弹簧（0 → 1，带一点回弹）"""
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    w = 2 * math.pi * f
    d = math.exp(-z * w * t)
    return 1.0 - d * (math.cos(w * math.sqrt(max(0.0, 1 - z * z)) * t) +
                      z / math.sqrt(max(1e-6, 1 - z * z)) * math.sin(w * math.sqrt(max(0.0, 1 - z * z)) * t))


def wob(t, f, decay):
    return 0.0 if t <= 0 else math.exp(-t / decay) * math.sin(2 * math.pi * f * t)


def h21(x, y):
    n = x * 127.1 + y * 311.7
    return np.mod(np.sin(n) * 43758.5453, 1.0)


def grid():
    """全屏像素中心坐标（只读广播视图，不占内存）"""
    px = (np.arange(W, dtype=np.float32)[None, :] + 0.5)
    py = (np.arange(H, dtype=np.float32)[:, None] + 0.5)
    return np.broadcast_to(px, (H, W)), np.broadcast_to(py, (H, W))


_PX = _PY = None


def pxpy():
    global _PX, _PY
    if _PX is None:
        _PX, _PY = grid()
    return _PX, _PY


# ----------------------------------------------------------------- 调色板
# u ∈ [0,1]：橘 → 洋红 → 紫。三段分别是"薄 / 中 / 厚"的液体色。
_PT = (np.array([1.00, 0.74, 0.30], np.float32), np.array([1.00, 0.50, 0.66], np.float32),
       np.array([0.84, 0.52, 1.00], np.float32))
_PM = (np.array([1.00, 0.36, 0.06], np.float32), np.array([1.00, 0.10, 0.44], np.float32),
       np.array([0.56, 0.12, 1.00], np.float32))
_PD = (np.array([0.80, 0.10, 0.04], np.float32), np.array([0.62, 0.02, 0.30], np.float32),
       np.array([0.24, 0.04, 0.60], np.float32))


def _ramp(pal, u):
    """u 可以是标量或任意形状数组；返回 (...,3)"""
    if np.ndim(u) == 0:
        uu = float(clip(np.float32(u)))
        a, b, c = pal
        return (mixc(a, b, uu * 2.0) if uu < 0.5 else mixc(b, c, uu * 2.0 - 1.0))
    uu = clip(u)[..., None]
    a, b, c = pal
    lo = mixc(a, b, uu * 2.0)
    hi = mixc(b, c, uu * 2.0 - 1.0)
    return np.where(uu < 0.5, lo, hi)


def pal_thin(u):
    return _ramp(_PT, u)


def pal_mid(u):
    return _ramp(_PM, u)


def pal_deep(u):
    return _ramp(_PD, u)


# ----------------------------------------------------------------- 影棚环境
KEY = (-0.78, -0.95)          # 主柔光箱在反射方向空间的位置


def soft_rect(qx, qy, hx, hy, soft):
    dx = np.abs(qx) - hx
    dy = np.abs(qy) - hy
    o = np.sqrt(np.maximum(dx, 0.0) ** 2 + np.maximum(dy, 0.0) ** 2) + np.minimum(np.maximum(dx, dy), 0.0)
    return 1.0 - sstep(-soft, soft, o)


def env_map(rx, ry, rz, keyx=None):
    """影棚反射：暗梅子底 + 顶部补光 + 暖地板反弹 + 四盏灯 + 掠射边缘光"""
    kx = KEY[0] if keyx is None else keyx
    c = np.empty(rx.shape + (3,), np.float32)
    c[:] = np.array([0.10, 0.03, 0.12], np.float32) * 0.5
    up = clip(-ry)
    dn = clip(ry)
    c += np.array([0.60, 0.40, 0.75], np.float32) * (0.55 * up * up)[..., None]
    c += np.array([1.0, 0.30, 0.32], np.float32) * (0.32 * sstep(0.2, 0.95, dn))[..., None]
    zf = np.maximum(rz, 0.06)
    qx = rx / zf
    qy = ry / zf
    # 主柔光箱（左上），面板内部还有一道竖直衰减
    kqx = qx - kx
    kqy = qy - KEY[1]
    kb = soft_rect(kqx, kqy, 0.60, 0.36, 0.10)
    c += np.array([1.0, 0.97, 0.93], np.float32) * (30.0 * kb * (0.75 + 0.25 * sstep(0.36, -0.36, kqy)))[..., None]
    # 右上小柔光箱（第二个高光点）
    c += np.array([1.0, 0.90, 0.95], np.float32) * (12.0 * soft_rect(qx - 0.95, qy + 1.25, 0.20, 0.14, 0.07))[..., None]
    # 右侧条光
    c += np.array([1.0, 0.80, 0.92], np.float32) * (14.0 * soft_rect(qx - 1.55, qy + 0.05, 0.07, 1.30, 0.04))[..., None]
    # 左下 kicker
    c += np.array([1.0, 0.80, 0.70], np.float32) * (4.0 * soft_rect(qx + 1.7, qy - 0.7, 0.08, 0.45, 0.08))[..., None]
    # 掠射边缘：吃的是场景的暗色和彩色反弹，不是白
    gr = np.power(1.0 - clip(rz), 4.0)
    nl = np.maximum(np.sqrt(rx * rx + ry * ry), 1e-5)
    rdx = rx / nl
    rdy = ry / nl
    c += gr[..., None] * (np.array([1.0, 0.72, 0.70], np.float32) * (1.1 * sstep(0.2, -0.9, rdx + rdy))[..., None] +
                          np.array([1.0, 0.38, 0.70], np.float32) * (0.9 * sstep(0.5, 1.0, rdx))[..., None])
    return c


# ----------------------------------------------------------------- 字标 SDF
_LET = None


def letters():
    """构建 drop 的 SDF：整词一次栅格化，再按字符切块。

    关键是**整词一次栅格化**：这样基线天然对齐（p 的下伸部不会把 o 顶上去），
    字距就是字体本身的字距，不用自己猜。切块时按字形实际包围盒 + 一点 padding，
    排布也按 ink 宽度而不是图宽——否则每个字母都会带上各自的 padding，
    四个字母会散得像四个独立单词。
    """
    global _LET
    if _LET is not None:
        return _LET
    from scipy.ndimage import distance_transform_edt, gaussian_filter
    font = ImageFont.truetype(F_HERO, 420)
    pad = 120
    tmp = Image.new("L", (8, 8), 0)
    td = ImageDraw.Draw(tmp)
    advs = [td.textlength(ch, font=font) for ch in WORD]
    Wc = int(sum(advs)) + pad * 2
    Hc = 1000
    img = Image.new("L", (Wc, Hc), 0)
    d = ImageDraw.Draw(img)
    x = float(pad)
    for i, ch in enumerate(WORD):
        d.text((x, 260), ch, font=font, fill=255)
        x += advs[i] * 1.03          # 留出间隙；k=0.08 的平滑并集会把 30px 内的形状拉出细颈
    arr = np.asarray(img, np.uint8)
    m_all = arr > 128
    ys_all, xs_all = np.nonzero(m_all)
    y0, y1 = int(ys_all.min()), int(ys_all.max()) + 1
    # 用列投影切出每个字母的墨迹段——比 textbbox 可靠：
    # textbbox 给的是排版边界，窄了就会把字形裁进图里，
    # 采样时 clamp 到边界，负距离会沿着那条边无限延伸，字母直接变成方块。
    colsum = m_all.sum(axis=0)
    segs, in_seg = [], False
    st = 0
    for xx in range(Wc):
        if colsum[xx] > 0 and not in_seg:
            st, in_seg = xx, True
        elif colsum[xx] == 0 and in_seg:
            segs.append((st, xx))
            in_seg = False
    if in_seg:
        segs.append((st, Wc))
    if len(segs) != len(WORD):
        segs = []
        xx = float(pad)
        for i in range(len(WORD)):
            segs.append((int(xx), int(xx + advs[i])))
            xx += advs[i] * 1.03
    outer = distance_transform_edt(~m_all)
    inner = distance_transform_edt(m_all)
    sdf = (outer - inner).astype(np.float32)
    sdf = gaussian_filter(sdf, 9.0).astype(np.float32)
    ppad = 42
    sy0 = max(0, y0 - ppad)
    sy1 = min(Hc, y1 + ppad)
    x_lo = max(0, segs[0][0] - ppad)
    x_hi = min(Wc, segs[-1][1] + ppad)
    off_x = 960.0 - (x_lo + x_hi) / 2.0
    off_y = 470.0 - (sy0 + sy1) / 2.0
    res = []
    for i in range(len(WORD)):
        sx0 = max(0, segs[i][0] - ppad)
        sx1 = min(Wc, segs[i][1] + ppad)
        sub = np.ascontiguousarray(sdf[sy0:sy1, sx0:sx1])
        res.append(dict(sdf=sub, w=sub.shape[1], h=sub.shape[0],
                        ox=sx0 + off_x, oy=sy0 + off_y))
    _LET = res
    return res
def sample_bilinear(img, X, Y):
    """双线性采样（X/Y 是图坐标，自动 clamp）"""
    h, w = img.shape
    X = np.clip(X, 0.0, w - 1.001)
    Y = np.clip(Y, 0.0, h - 1.001)
    x0 = np.floor(X).astype(np.int32)
    y0 = np.floor(Y).astype(np.int32)
    fx = (X - x0).astype(np.float32)
    fy = (Y - y0).astype(np.float32)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    a = img[y0, x0]
    b = img[y0, x1]
    c = img[y1, x0]
    d = img[y1, x1]
    top = a + (b - a) * fx
    bot = c + (d - c) * fx
    return top + (bot - top) * fy


# ----------------------------------------------------------------- 相机
CAM = [
    (-0.5, 5.4, 640, 382), (0.0, 5.3, 640, 398), (0.167, 4.9, 640, 452), (0.30, 3.8, 642, 690),
    (0.42, 3.3, 648, 800), (0.8, 2.6, 1010, 832), (1.2, 2.15, 745, 812), (1.7, 1.6, 880, 758),
    (2.4, 1.64, 925, 764), (3.05, 1.72, 960, 764), (3.6, 1.46, 960, 590), (4.0, 1.42, 960, 640),
    (4.6, 1.2, 960, 560), (5.0, 1.13, 960, 548), (5.9, 1.0, 960, 540), (8.0, 1.0, 960, 540),
    (10.0, 1.0, 960, 540), (10.5, 1.0, 960, 540),
]


def cam_at(t):
    """非均匀 Catmull-Rom：返回 (zoom, cx, cy)"""
    i = 1
    while i < len(CAM) - 2 and t > CAM[i + 1][0]:
        i += 1
    k0, k1, k2, k3 = CAM[i - 1], CAM[i], CAM[i + 1], CAM[i + 2]
    u = min(1.0, max(0.0, (t - k1[0]) / (k2[0] - k1[0])))
    u2, u3 = u * u, u * u * u
    out = []
    for c in (1, 2, 3):
        m1 = (k2[c] - k0[c]) / (k2[0] - k0[0]) * (k2[0] - k1[0])
        m2 = (k3[c] - k1[c]) / (k3[0] - k1[0]) * (k2[0] - k1[0])
        out.append((2 * u3 - 3 * u2 + 1) * k1[c] + (u3 - 2 * u2 + u) * m1 +
                   (-2 * u3 + 3 * u2) * k2[c] + (u3 - u2) * m2)
    return out[0], out[1], out[2]


# ----------------------------------------------------------------- 叙事
def add_ball(S, x, y, r, u, ax=1.0, ay=1.0, rot=0.0):
    if r > 0.4:
        S["balls"].append((float(x), float(y), float(r), float(u), float(ax), float(ay), float(rot)))


def add_seg(S, ax_, ay_, bx_, by_, ra, rb, u):
    if max(ra, rb) > 0.4:
        S["segs"].append((float(ax_), float(ay_), float(bx_), float(by_), float(ra), float(rb), float(u)))


def film(t):
    """给定时刻，返回整个画面的液态状态（纯函数）"""
    S = dict(balls=[], segs=[], letters=[], flood=None,
             rip=dict(x=960.0, y=FY, age=0.0, amp=0.0),
             keyx=KEY[0], bloom=0.55, flash=0.0, caus=0.0, ring=None)

    # ---------- 1. 倒水（0 – 0.9）：上方垂下的细流
    if t < 0.95:
        ps = CUES["pour_snap"]
        if t < ps:
            k = clip(t / ps)
            add_seg(S, 640.0, 150.0, 640.0, FY - 26.0, 5.0 + 9.0 * k, 13.0 + 6.0 * k, 0.05)
            add_ball(S, 640.0, FY - 30.0, 22.0, 0.05, 1.0, 1.05)
        else:
            # 流断开：上半截回抽，下半截落成水珠
            k = clip((t - ps) / 0.30)
            add_seg(S, 640.0, 150.0 - 320.0 * eIn(k), 640.0, FY - 26.0 - 90.0 * eIn(k),
                    13.0 * (1 - k), 12.0 * (1 - k), 0.05)
            if k < 1.0:
                add_ball(S, 640.0, FY - 30.0 - 40.0 * k, 22.0 * (1 - 0.35 * k), 0.05,
                         1.0 + 0.4 * k, 1.0 - 0.3 * k)

    # ---------- 2. 落雨（0.4 – 2.0）：四滴落下、压扁、弹起；融合一开始就交给融合段
    if t < 2.05:
        for (tl, x0, sz, u) in LANDINGS:
            fall = 0.30
            t0 = tl - fall
            if t < t0:
                continue
            r0 = 26.0 * sz
            if t < tl:
                k = clip((t - t0) / fall)
                y = 140.0 + (FY - 34.0 * sz - 140.0) * (k * k)
                add_ball(S, x0, y, r0 * (1.0 - 0.16 * k), u, 1.0 - 0.22 * k, 1.0 + 0.30 * k)
                continue
            dt = t - tl
            # 压扁 → 弹起 → 再落 → 静止
            if dt < 0.115:
                k = dt / 0.115
                sq = math.sin(math.pi * k)
                add_ball(S, x0, FY - r0 * 0.80 + r0 * 0.24 * sq, r0 * (1.0 + 0.42 * sq), u,
                         1.0 + 0.46 * sq, 1.0 - 0.34 * sq)
            elif dt < 0.42:
                k = (dt - 0.115) / 0.305
                hop = 46.0 * sz * math.sin(math.pi * k)
                add_ball(S, x0, FY - r0 * 0.80 - hop, r0 * (1.0 - 0.06 * math.sin(math.pi * k)), u,
                         1.0 + 0.10 * math.cos(math.pi * k), 1.0 + 0.10 * math.sin(math.pi * k))
            else:
                k = clip((dt - 0.42) / 0.35)
                add_ball(S, x0, FY - r0 * 0.78 + 2.0 * wob(dt - 0.42, 3.2, 0.30), r0 * 1.02, u,
                         1.14 - 0.06 * k, 0.90 + 0.06 * k)

    # ---------- 3. 融合（2.0 – 3.2）：四滴向中心聚拢、融成一摊
    if 2.0 <= t < 3.22:
        pts = []
        for i, (tl, x0, sz, u) in enumerate(LANDINGS):
            kk = float(eInOut(clip((t - 2.0 - i * 0.14) / 0.52)))
            if kk <= 0.0:
                continue
            r = 26.0 * sz * (1.0 + 0.55 * kk)
            x = x0 + (960.0 - x0) * kk
            add_ball(S, x, FY - r * 0.76, r, u, 1.16 + 0.14 * kk, 0.88 - 0.10 * kk)
            pts.append((x, r, u))
        # 融合的颈部（拉丝）：只连接靠得够近的相邻两滴。
        # 早先我用一根横跨全屏的长胶囊当"颈"，结果四滴被拉成一根 1400px 的长棒——
        # 液体的脖子是**局部**现象，只能长在快要碰上的两滴之间。
        pts.sort()
        for a in range(len(pts) - 1):
            x1, r1, u1 = pts[a]
            x2, r2, u2 = pts[a + 1]
            gap = (x2 - x1) - r1 - r2
            if gap < 200.0:
                w = float(clip(1.0 - gap / 200.0))
                add_seg(S, x1, FY - r1 * 0.55, x2, FY - r2 * 0.55,
                        r1 * 0.72 * w, r2 * 0.72 * w, (u1 + u2) * 0.5)

    # ---------- 4. 跃起（3.2 – 4.0）：整摊水跳起来
    if 3.2 <= t < 4.02:
        tt = t - 3.2
        mass_r = 150.0
        y0 = FY - mass_r * 0.80
        y = y0 - 1500.0 * tt + 0.5 * 3750.0 * tt * tt
        k = clip(tt / 0.8)
        # 起跳前的下蹲已经由融合段接手；这里是"面团"离地
        if tt < 0.06:
            sq = tt / 0.06
            add_ball(S, 960.0, FY - mass_r * 0.80 + mass_r * 0.30 * sq, mass_r * (1.0 + 0.10 * sq),
                     0.42, 1.10 + 0.16 * sq, 0.92 - 0.14 * sq)
        else:
            add_ball(S, 960.0, max(y, FY - mass_r * 3.4), mass_r * (1.0 + 0.06 * math.sin(tt * 9.0)),
                     0.42, 1.0 - 0.10 * math.sin(tt * 11.0), 1.0 + 0.12 * math.sin(tt * 11.0))

    # ---------- 5. 决堤（4.0 – 4.42）：落回 → 溅起 → 水淹没全屏
    if 4.0 <= t < 4.42:
        tt = t - 4.0
        # 落点溅射
        if tt < 0.22:
            k = tt / 0.22
            add_ball(S, 960.0, FY - 130.0 * (1.0 - k) - 30.0, 150.0 * (1.0 - 0.55 * k), 0.42,
                     1.0 + 0.55 * k, 1.0 - 0.42 * k)
        # 水淹波前
        k = clip((t - CUES["flood_in"]) / (CUES["flood_full"] - CUES["flood_in"]))
        if k > 0.0:
            S["flood"] = dict(front=FY + 70.0 + (3000.0 - FY - 70.0) * float(eFront(k)),
                              back=-500.0 - 2600.0 * float(eFront(k)),
                              phase=1.3 + 2.4 * k, amp=110.0, freq=0.0062, lean=0.12, u=0.90)
            S["caus"] = clip((t - 4.05) / 0.30)
            S["flash"] = 0.9 * math.exp(-((t - 4.05) / 0.055) ** 2)

    # ---------- 6. 浸没 → 揭示（4.42 – 5.9）：水退去，露出字标
    if 4.42 <= t < 5.95:
        k = clip((t - 4.42) / (5.95 - 4.42))
        ke = float(eInOut(k))
        S["flood"] = dict(front=FY + 90.0 - 1900.0 * ke,
                          back=-3100.0,
                          phase=1.3 + 4.0 * k, amp=110.0 * (1.0 - 0.5 * k), freq=0.0062,
                          lean=0.12 * (1.0 - k), u=0.90)
        S["caus"] = max(0.0, 1.0 - 3.0 * k)      # 气泡跟着水走，退水时先消失

    # ---------- 7. 聚拢 / 凝固（4.50 – 6.4）：水一退就开始凝固，否则中间会有一秒空画面
    if t >= 4.50:
        for i, L in enumerate(letters()):
            k = clip((t - 4.50 - i * 0.07) / 1.90)
            if k <= 0.0:
                continue
            # grow 从 -70（一坨互相吞掉的液体）收到 0
            g = -70.0 * (1.0 - float(eOut(k)))
            sc = 1.0 + 0.20 * (1.0 - float(eOut(k)))
            add_letter(S, i, L, g, sc, WORD_U[i % len(WORD_U)])

    # ---------- 8. 光扫（7.1 – 7.5）
    if t >= CUES["glint"]:
        S["glint"] = float(clip((t - CUES["glint"]) / 0.40))

    # ---------- 9. 滴落（7.6 – 8.6）：从 p 的下降部滴下一滴
    if t >= 7.55:
        # p 的落点：字标最右侧字母的下缘
        lx = 1210.0
        if t < CUES["drip_snap"]:
            k = clip((t - 7.55) / (CUES["drip_snap"] - 7.55))
            r = 12.0 + 20.0 * k
            y = 690.0 + 26.0 * k
            add_ball(S, lx, y, r, 0.85, 0.78 - 0.10 * k, 1.26 + 0.16 * k)
            add_seg(S, lx, y, lx, 700.0, r * 0.55, r * 0.92, 0.85)
        else:
            tt = t - CUES["drip_snap"]
            fall = 0.20
            if tt < fall:
                k = tt / fall
                y = 716.0 + (FY - 716.0) * (k * k)
                add_ball(S, lx, y, 32.0 * (1.0 - 0.10 * k), 0.85, 0.82 - 0.10 * k, 1.24 + 0.14 * k)
            else:
                dt = tt - fall
                if dt < 0.10:
                    k = dt / 0.10
                    sq = math.sin(math.pi * k)
                    add_ball(S, lx, FY - 25.0 + 8.0 * sq, 32.0 * (1.0 + 0.35 * sq), 0.85,
                             1.0 + 0.40 * sq, 1.0 - 0.30 * sq)
                elif dt < 0.30:
                    k = (dt - 0.10) / 0.20
                    add_ball(S, lx, FY - 25.0 - 30.0 * math.sin(math.pi * k), 32.0, 0.85,
                             1.05, 0.98)
                else:
                    add_ball(S, lx, FY - 24.0, 33.0, 0.85, 1.12, 0.92)

    # ---------- 10. 涟漪（8.4 – 10）
    if t >= CUES["drip_land"]:
        S["rip"] = dict(x=1210.0, y=FY, age=t - CUES["drip_land"], amp=1.0)
    # 背景光晕环
    if 6.0 <= t < 7.0:
        S["ring"] = dict(x=960.0, y=470.0, r=200.0 + 620.0 * float(eOut(clip((t - 6.0) / 1.0))),
                         w=0.16 * math.sin(math.pi * clip((t - 6.0) / 1.0)))
    if t >= CUES["logo_snap"]:
        S["bloom"] = 0.55 + 0.35 * math.exp(-((t - 6.45) / 0.30) ** 2)

    return S


def add_letter(S, i, L, grow, scale, u):
    S["letters"].append((i, L, grow, scale, u))


# ----------------------------------------------------------------- SDF 场
def field_at(S, X, Y, cam, y_off=0, K=0.080, DCLIP=240.0):
    """在世界坐标网格 (X, Y) 上求液体的平滑并集距离场。

    X / Y 是画面某个行区间的世界坐标（子区域时 y_off 给出它在画面中的起始行）。
    返回 (D, Gx, Gy, U)：世界单位的距离、梯度、色相。

    这里最要紧的一点：**场必须在世界坐标里算，不能在像素坐标里算**。
    相机一推近（zoom 从 5.4 拉到 1.0），像素空间的距离就全错了——
    融合半径 k 是世界单位，球与球的粘连程度不能随镜头变化。
    """
    zoom, ccx, ccy = cam
    h, w = X.shape
    acc = np.zeros((h, w), np.float32)
    gx = np.zeros((h, w), np.float32)
    gy = np.zeros((h, w), np.float32)
    uu = np.zeros((h, w), np.float32)

    def bbox(wx, wy, rad_world):
        """世界包围盒 → 像素索引范围（裁剪到子区域）"""
        rad = rad_world * zoom
        px_ = (wx - ccx) * zoom + 959.5
        py_ = (wy - ccy) * zoom + 539.5
        x0 = int(max(0, math.floor(px_ - rad)))
        x1 = int(min(W, math.ceil(px_ + rad) + 1))
        ry0 = int(max(y_off, math.floor(py_ - rad)))
        ry1 = int(min(y_off + h, math.ceil(py_ + rad) + 1))
        return x0, x1, ry0, ry1

    # ---- 球（可椭圆 + 可旋转）
    for (bx, by, r, u, ax_, ay_, rot) in S["balls"]:
        x0, x1, ry0, ry1 = bbox(bx, by, r * max(ax_, ay_) + 150.0)
        if x1 <= x0 or ry1 <= ry0:
            continue
        s0, s1 = ry0 - y_off, ry1 - y_off
        Xs = X[s0:s1, x0:x1] - bx
        Ys = Y[s0:s1, x0:x1] - by
        ca = math.cos(-rot)
        sa = math.sin(-rot)
        qx = ca * Xs + sa * Ys
        qy = -sa * Xs + ca * Ys
        axr = r * ax_
        ayr = r * ay_
        qax = qx / (axr * axr)
        qay = qy / (ayr * ayr)
        d = 0.5 * r * (qx * qax + qy * qay - 1.0)
        gqx = r * qax
        gqy = r * qay
        cb = math.cos(rot)
        sb = math.sin(rot)
        wt = np.exp(-K * np.maximum(d, -DCLIP))
        acc[s0:s1, x0:x1] += wt
        gx[s0:s1, x0:x1] += wt * (cb * gqx - sb * gqy)
        gy[s0:s1, x0:x1] += wt * (sb * gqx + cb * gqy)
        uu[s0:s1, x0:x1] += wt * u

    # ---- 胶囊（变半径，用来做"拉丝"）
    for (sax, say, sbx, sby, ra, rb, u) in S["segs"]:
        mx = (sax + sbx) * 0.5
        my = (say + sby) * 0.5
        half = math.hypot(sbx - sax, sby - say) * 0.5
        x0, x1, ry0, ry1 = bbox(mx, my, max(ra, rb) + half + 150.0)
        if x1 <= x0 or ry1 <= ry0:
            continue
        s0, s1 = ry0 - y_off, ry1 - y_off
        Xs = X[s0:s1, x0:x1] - sax
        Ys = Y[s0:s1, x0:x1] - say
        bax = sbx - sax
        bay = sby - say
        den = max(bax * bax + bay * bay, 1e-4)
        hh = np.clip((Xs * bax + Ys * bay) / den, 0.0, 1.0)
        vx = Xs - bax * hh
        vy = Ys - bay * hh
        rr = np.maximum(ra + (rb - ra) * hh, 0.3)
        d = (vx * vx + vy * vy - rr * rr) / (2.0 * rr)
        wt = np.exp(-K * np.maximum(d, -DCLIP))
        acc[s0:s1, x0:x1] += wt
        gx[s0:s1, x0:x1] += wt * (vx / rr)
        gy[s0:s1, x0:x1] += wt * (vy / rr)
        uu[s0:s1, x0:x1] += wt * u

    # ---- 字标：从字体栅格化出来的 SDF 纹理，按 scale 缩放、grow 膨胀
    for (i, L, grow, scale, u) in S["letters"]:
        sdf = L["sdf"]
        cxl = L["ox"] + L["w"] * 0.5
        cyl = L["oy"] + L["h"] * 0.5
        cw = L["w"] * scale
        chh = L["h"] * scale
        x0, x1, ry0, ry1 = bbox(cxl, cyl, max(cw, chh) * 0.5 + 90.0)
        if x1 <= x0 or ry1 <= ry0:
            continue
        s0, s1 = ry0 - y_off, ry1 - y_off
        Xs = X[s0:s1, x0:x1]
        Ys = Y[s0:s1, x0:x1]
        tx = (Xs - cxl) / scale + L["w"] * 0.5
        ty = (Ys - cyl) / scale + L["h"] * 0.5
        sd = sample_bilinear(sdf, tx, ty)
        dl = sd * scale - grow
        gxp = (sample_bilinear(sdf, tx + 1.0, ty) - sample_bilinear(sdf, tx - 1.0, ty)) * 0.5 * scale
        gyp = (sample_bilinear(sdf, tx, ty + 1.0) - sample_bilinear(sdf, tx, ty - 1.0)) * 0.5 * scale
        wt = np.exp(-K * np.maximum(dl, -DCLIP))
        acc[s0:s1, x0:x1] += wt
        gx[s0:s1, x0:x1] += wt * gxp
        gy[s0:s1, x0:x1] += wt * gyp
        uu[s0:s1, x0:x1] += wt * u

    # ---- 水淹：一条带正弦波前的宽带（两个波前取平滑最大值）
    fl = S["flood"]
    if fl is not None:
        lo_w = min(fl["back"], fl["front"]) - 300.0
        hi_w = max(fl["back"], fl["front"]) + 300.0
        ry0 = int(max(y_off, math.floor((lo_w - ccy) * zoom + 539.5)))
        ry1 = int(min(y_off + h, math.ceil((hi_w - ccy) * zoom + 539.5) + 1))
        if ry1 > ry0:
            s0, s1 = ry0 - y_off, ry1 - y_off
            Xs = X[s0:s1]
            Ys = Y[s0:s1]
            ph = fl["phase"]
            fq = fl["freq"]
            s1_ = np.sin(Xs * fq + ph)
            s2_ = np.sin(Xs * fq * 1.87 + ph * 1.31 + 1.7)
            s3_ = np.sin(Xs * fq * 3.13 - ph * 0.63 + 4.1)
            c1_ = np.cos(Xs * fq + ph)
            c2_ = np.cos(Xs * fq * 1.87 + ph * 1.31 + 1.7)
            c3_ = np.cos(Xs * fq * 3.13 - ph * 0.63 + 4.1)
            A = fl["amp"]
            wave = A * (0.58 * s1_ + 0.30 * s2_ + 0.14 * s3_)
            dwave = A * fq * (0.58 * c1_ + 0.30 * 1.87 * c2_ + 0.14 * 3.13 * c3_)
            nf = np.sqrt(1.0 + dwave * dwave)
            nb = np.sqrt(1.0 + (dwave * 0.85) ** 2)
            dF = (Ys - (fl["front"] + wave)) / nf
            dB = ((fl["back"] + wave * 0.85) - Ys) / nb
            kk = 0.08
            mm = np.maximum(dF, dB)
            eF = np.exp(kk * (dF - mm))
            eB = np.exp(kk * (dB - mm))
            gs = eF + eB
            d = mm + np.log(gs) / kk
            wt = np.exp(-K * np.maximum(d, -DCLIP))
            acc[s0:s1] += wt
            gx[s0:s1] += wt * (eF * (-dwave / nf) / gs)
            gy[s0:s1] += wt * ((eF / nf + eB / nb) / gs)
            uu[s0:s1] += wt * fl["u"]

    accs = np.maximum(acc, 1e-30)
    D = -np.log(accs) / K
    return D, gx / accs, gy / accs, uu / accs
# ----------------------------------------------------------------- 着色
def shade(D, Gx, Gy, U, X, Y, t, glint=0.0, deep=1.0, sheet=False):
    """液态着色：厚度定色，SDF 转球冠高度场求法线，再上影棚反射。

    **按行分条带处理**。水淹那几秒整个画面都是液体，若一次性把 207 万像素
    全丢进布尔索引，峰值内存会顶到 300MB+，三进程直接 OOM
    （本机可用内存常年只有 1.3–1.8GB）。分成 216 行的条带后峰值降到 1/5。
    """
    gl = np.maximum(np.sqrt(Gx * Gx + Gy * Gy), 0.20)
    cov = np.clip(0.5 - D / gl, 0.0, 1.0)
    rgb = np.zeros(D.shape + (3,), np.float32)
    rows = np.nonzero(cov.max(axis=1) > 0.0025)[0]
    if rows.size == 0:
        return rgb, cov
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    BAND = 216

    for ys in range(y0, y1, BAND):
        ye = min(y1, ys + BAND)
        m = cov[ys:ye] > 0.0025
        if not m.any():
            continue
        Dm = D[ys:ye][m]
        Gxm = Gx[ys:ye][m]
        Gym = Gy[ys:ye][m]
        Um = U[ys:ye][m]
        Xm = X[ys:ye][m]
        Ym = Y[ys:ye][m]

        x = np.maximum(-Dm, 0.0)                       # 到表面的深度 = 液层厚度
        R, Hc = 95.0, 210.0
        h0 = np.sqrt(2.0 * R * x + 2.0 * R * 0.6)
        th = np.tanh(h0 / Hc)
        dhdx = (1.0 - th * th) * R / np.maximum(h0, 1e-6)
        ghx = -dhdx * Gxm
        ghy = -dhdx * Gym

        # 深部的大理石纹：域扭曲的色带，每条带边是一道软脊
        # 频率必须压得很低——正弦的梯度是"振幅×频率"，比真噪声陡得多，
        # 照搬参考里的系数会得到一堆 10px 宽的细纹，像指纹而不像大理石。
        du = np.zeros_like(x)
        if deep > 0.0:
            dp = sstep(90.0, 320.0, x) * deep
            qx = Xm * 0.00118
            qy = Ym * 0.00118
            w1 = np.sin(qx * 3.1 + qy * 2.0 + t * 0.50)
            w2 = np.sin((qx + 0.80 * w1) * 3.4 - qy * 2.6 + t * 0.35)
            ph = 1.5 * w2 + 0.7 * w1
            band = np.sin(ph)
            A = 26.0 * dp
            ghx += A * 0.5 * np.cos(ph) * (0.00118 * 3.4 * 1.5)
            ghy += A * 0.5 * np.cos(ph) * (0.00118 * 2.6 * 1.5)
            vein = sstep(0.35, 0.8, band) - sstep(-0.35, -0.8, band)
            du = dp * (0.40 * vein + 0.10 * w2)

        nl = np.sqrt(ghx * ghx + ghy * ghy + 1.0)
        nx = -ghx / nl
        ny = -ghy / nl
        nz = 1.0 / nl

        uu = Um + du
        body = mixc(pal_thin(uu), pal_mid(uu), sstep(0.0, 5.0, x)[..., None])
        body = mixc(body, pal_deep(uu),
                    (sstep(40.0, 260.0, x) * (0.55 + (0.22 - 0.55) * sstep(200.0, 400.0, x)))[..., None])

        Lx, Ly, Lz = -0.55, -0.70, 0.62
        ndl = nx * Lx + ny * Ly + nz * Lz
        side = 1.0 - nz
        col = body * ((0.26 + 0.50 * (0.5 + 0.5 * ndl)) * (0.50 + 0.50 * nz))[..., None]

        # 透射：背光在边缘内侧压出一道饱和的月牙
        l2n = math.hypot(Lx, Ly)
        nl2 = np.maximum(np.sqrt(nx * nx + ny * ny), 1e-6)
        away = (nx / nl2) * (-Lx / l2n) + (ny / nl2) * (-Ly / l2n)
        trans = np.power(np.maximum(away, 0.0), 1.2) * sstep(0.10, 0.50, side) * \
            (1.0 - 0.85 * sstep(0.70, 1.0, side))
        col += (pal_mid(uu) * 1.4 + pal_thin(uu) * 0.3) * trans[..., None]
        col += pal_mid(uu) * (np.exp(-x / 3.0) * 0.22)[..., None]

        # 菲涅尔 + 影棚反射
        rx = 2.0 * nz * nx
        ry = 2.0 * nz * ny
        rz = 2.0 * nz * nz - 1.0
        fr = 0.04 + 0.96 * np.power(1.0 - np.clip(nz, 0.0, 1.0), 5.0)
        if sheet:
            fr = fr * (1.0 - sstep(30.0, 48.0, x) * 0.75)
        col = col * (1.0 - fr)[..., None] + env_map(rx, ry, rz) * fr[..., None]

        # 大平液面（水淹）的宽镜面光带
        if sheet:
            deepm = sstep(90.0, 320.0, x) * deep
            if deepm.any():
                nlb = math.sqrt(0.16 ** 2 + 0.22 ** 2 + 1.0)
                sb = np.power(np.maximum((rx * -0.16 + ry * -0.22 + rz * 1.0) / nlb, 0.0), 380.0)
                col += np.array([1.0, 0.90, 0.95], np.float32) * (sb * deepm * 1.6)[..., None]

        # 光扫：一道斜向的窄带扫过液体
        if glint > 0.0:
            bandg = np.exp(-((Xm * 0.86 + Ym * 0.51 - (700.0 + 1500.0 * glint)) / 150.0) ** 2)
            col += np.array([1.0, 0.96, 0.99], np.float32) * (bandg * 0.55 * math.sin(math.pi * glint))[..., None]

        rgb[ys:ye][m] = col

    return rgb, cov
# ----------------------------------------------------------------- 背景
def backdrop(X, Y, S):
    y = Y / H
    c = mixc(np.array([0.045, 0.012, 0.058], np.float32),
             np.array([0.150, 0.042, 0.175], np.float32), sstep(0.0, HOR / H, y)[..., None])
    dx = (X - 960.0) / 1050.0
    dy = (Y - 500.0) / 620.0
    c += np.array([0.34, 0.10, 0.35], np.float32) * (0.17 * np.exp(-(dx * dx + dy * dy) * 1.6))[..., None]
    dhx = (X - 960.0) / 620.0
    dhy = (Y - 470.0) / 300.0
    c += np.array([0.62, 0.16, 0.42], np.float32) * (0.13 * np.exp(-(dhx * dhx + dhy * dhy) * 2.2))[..., None]
    if S.get("ring") is not None:
        R0 = S["ring"]
        rl = np.sqrt((X - R0["x"]) ** 2 + ((Y - R0["y"]) * 1.18) ** 2)
        e = (rl - R0["r"]) / 120.0
        c += np.array([1.0, 0.58, 0.66], np.float32) * \
            (R0["w"] * (1.1 * np.exp(-e * e) + 0.045 * sstep(R0["r"] + 60.0, 0.0, rl)))[..., None]
    return c


def floor_col(X, Y):
    dy = Y - HOR
    c = mixc(np.array([0.050, 0.013, 0.065], np.float32),
             np.array([0.105, 0.028, 0.125], np.float32), sstep(0.0, 260.0, dy)[..., None])
    # 地板上的柔光池
    dx = (X - 960.0) / 900.0
    c += np.array([0.22, 0.06, 0.24], np.float32) * (0.28 * np.exp(-(dx * dx) * 1.4) * np.exp(-dy / 300.0))[..., None]
    return c


def rip_rings(X, Y, rip):
    if rip["amp"] <= 0.001:
        return None
    rd = np.sqrt((X - rip["x"]) ** 2 + ((Y - rip["y"]) * 0.55) ** 2)
    rings = np.zeros_like(rd)
    for i in range(3):
        rr = rip["age"] * 470.0 - i * 90.0
        if rr <= 0:
            continue
        rings += np.exp(-((rd - rr) / 46.0) ** 2)
    return rings * np.exp(-rip["age"] * 2.0) * rip["amp"]


# ----------------------------------------------------------------- 渲染
def render_frame(t):
    S = film(t)
    cam = cam_at(t)
    zoom, ccx, ccy = cam
    PX, PY = pxpy()
    # 世界坐标
    Xw = (PX - 960.0) / zoom + ccx
    Yw = (PY - 540.0) / zoom + ccy

    # ---- 背景 + 地板（地平线是弯的：影棚背景墙）
    hzc = HOR - 42.0 * np.power((Xw - 960.0) / 980.0, 2.0)
    hb = sstep(-85.0, 65.0, Yw - hzc)
    col = backdrop(Xw, Yw, S) * (1.0 - hb[..., None]) + floor_col(Xw, Yw) * hb[..., None]

    # ---- 主场（世界坐标）
    D, Gx, Gy, U = field_at(S, Xw, Yw, cam)

    # ---- 阴影 + 彩色焦散
    # field(p - so) 的一阶泰勒展开：Ds ≈ D - (Gx·24 + Gy·32)
    # 省掉一次全屏 SDF。符号别搞反——光在左上，影子就该落在右下。
    Ds = D - Gx * 24.0 - Gy * 32.0
    sh = sstep(26.0, -34.0, Ds)
    col *= (1.0 - 0.50 * sh)[..., None]
    ca = sstep(-8.0, -60.0, Ds)
    col += pal_mid(U) * (0.075 * ca)[..., None]
    col += pal_thin(U) * (0.05 * sstep(-30.0, -110.0, Ds))[..., None]

    # ---- 地板反射：把接触线下方 190 px 内的像素，按镜面坐标再采样一次场
    ys = int(max(0, math.floor((FY - ccy) * zoom + 540.0)))
    ye = int(min(H, math.ceil((FY + 190.0 - ccy) * zoom + 540.0)))
    if ye > ys:
        Xm = Xw[ys:ye]
        Ym = 2.0 * FY - Yw[ys:ye]
        Dm, Gxm, Gym, Um = field_at(S, Xm, Ym, cam, y_off=ys)
        rgbm, covm = shade(Dm, Gxm, Gym, Um, Xm, Ym, t, deep=1.0)
        dy = Yw[ys:ye] - FY
        fade = np.exp(-dy / 80.0) * 0.50 * sstep(170.0, 90.0, dy)
        a = (covm * fade)[..., None]
        col[ys:ye] = col[ys:ye] * (1.0 - a) + rgbm * 0.75 * a

    # ---- 接触暗化：液体与地板相接处压一道暗边
    cont = sstep(4.0, -10.0, D + Gy * (FY - 3.0 - Yw)) * np.exp(-np.abs(Yw - FY) / 7.0)
    col *= (1.0 - 0.65 * cont)[..., None]

    # ---- 地平线：一道淡淡的抛光边
    hl = np.exp(-np.abs(Yw - hzc) / 34.0) * sstep(0.0, 800.0, 980.0 - np.abs(Xw - 960.0))
    col += np.array([0.60, 0.30, 0.62], np.float32) * (hl * 0.035)[..., None]

    # ---- 涟漪环
    rg = rip_rings(Xw, Yw, S["rip"])
    if rg is not None:
        col += np.array([1.0, 0.66, 0.82], np.float32) * (rg * 0.55)[..., None]

    # ---- 液体
    sheet = S["flood"] is not None
    rgb, cov = shade(D, Gx, Gy, U, Xw, Yw, t, glint=S.get("glint", 0.0), deep=1.0, sheet=sheet)
    col = col * (1.0 - cov)[..., None] + rgb * cov[..., None]

    # ---- 碳酸气泡（水淹期间水体内部的小气泡）
    if S["caus"] > 0.01:
        bl = 0
        for i in range(26):
            bx = 300.0 + h21(i * 1.7, 3.1) * 1320.0
            by = 620.0 + h21(i * 2.3, 7.7) * 380.0
            rr = 2.0 + h21(i * 3.1, 1.3) * 3.2
            if h21(i * 5.3, 9.1) > 0.65:
                continue
            dd = np.sqrt((Xw - bx) ** 2 + (Yw - by) ** 2)
            bl += np.exp(-((dd - rr) / 1.4) ** 2)
        col += np.array([1.0, 0.86, 0.94], np.float32) * (np.minimum(bl, 2.0) * 0.30 * S["caus"])[..., None]

    # ---- 后期
    return post(col, t, S)


# ----------------------------------------------------------------- 后期
_BLOOM_DN = {}


def _down(a, f):
    h, w = a.shape[:2]
    h2, w2 = max(1, h // f), max(1, w // f)
    if a.ndim == 3:
        return a[:h2 * f, :w2 * f].reshape(h2, f, w2, f, 3).mean(axis=(1, 3))
    return a[:h2 * f, :w2 * f].reshape(h2, f, w2, f).mean(axis=(1, 3))


def _up(a, w, h):
    """双线性上采样到 (h, w)"""
    sh, sw = a.shape[:2]
    xs = (np.arange(w, dtype=np.float32) + 0.5) * (sw / w) - 0.5
    ys = (np.arange(h, dtype=np.float32) + 0.5) * (sh / h) - 0.5
    x0 = np.clip(np.floor(xs).astype(np.int32), 0, sw - 1)
    y0 = np.clip(np.floor(ys).astype(np.int32), 0, sh - 1)
    x1 = np.minimum(x0 + 1, sw - 1)
    y1 = np.minimum(y0 + 1, sh - 1)
    fx = np.clip(xs - x0, 0, 1)[None, :]
    fy = np.clip(ys - y0, 0, 1)[:, None]
    if a.ndim == 3:
        fx = fx[..., None]
        fy = fy[..., None]
    top = a[y0][:, x0] + (a[y0][:, x1] - a[y0][:, x0]) * fx
    bot = a[y1][:, x0] + (a[y1][:, x1] - a[y1][:, x0]) * fx
    return top + (bot - top) * fy


def bloom(col, amount):
    """在 1/4 分辨率上做多级 bloom，最后一次性上采样。

    全屏做 6 级上采样是这台机器上最贵的一步（实测 1.65s/帧，占整帧 1/3）。
    但 bloom 本来就是模糊的，1/4 分辨率完全够用——参考实现走的也是 mip 链。
    """
    q = _down(col, 4)
    hq, wq = q.shape[:2]
    acc = np.zeros_like(q)
    wsum = 0.0
    for l in range(1, 6):
        small = _down(q, 2 ** l)
        bright = np.maximum(small - 0.62, 0.0)
        up = _up(bright, wq, hq)
        w = 1.0 / (1.0 + l * 0.6)
        acc += up * w
        wsum += w
    return _up(acc / wsum, W, H) * amount


def tonemap(x):
    m = np.maximum(np.maximum(x[..., 0], x[..., 1]), x[..., 2])
    k = 0.72
    mt = np.where(m < k, m, k + (1.0 - k) * (1.0 - np.exp(-(m - k) / (1.0 - k))))
    c = x * (mt / np.maximum(m, 1e-5))[..., None]
    wh = sstep(1.0, 6.0, m)
    return c * (1.0 - wh * 0.85)[..., None] + (mt * wh * 0.85)[..., None]


def post(col, t, S):
    hdr = col + bloom(col, S["bloom"])
    hdr = hdr * (2.0 ** S["flash"])
    c = tonemap(hdr)
    # 暗角
    PX, PY = pxpy()
    qx = (PX / W - 0.5) * (W / H)
    qy = PY / H - 0.5
    c *= (1.0 - 0.40 * sstep(0.30, 1.02, np.sqrt(qx * qx + qy * qy)))[..., None]
    s = np.power(np.maximum(c, 0.0), 1.0 / 2.2)
    # 颗粒 + 抖动（一次哈希，比两次 sin 省一半）
    fr = t * FPS
    g = h21(PX + fr * 37.1, PY + fr * 91.7) - 0.5
    lum = s[..., 0] * 0.299 + s[..., 1] * 0.587 + s[..., 2] * 0.114
    s += (g * (0.034 * (1.0 - lum) * sstep(0.0, 0.25, lum) + 0.014))[..., None]
    # 片头片尾的整体淡入
    return np.clip(s, 0.0, 1.0)


def draw_type(img, t):
    """前景文字层：右对齐在字标的右侧"""
    if t < CUES["tagline_start"]:
        return img
    age = t - CUES["tagline_start"]
    im = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(im, "RGBA")
    lines = [("万物始于一滴", F_UI, 46, 986, (255, 232, 240), 0.96, 16),
             ("LIQUID MOTION", F_EN, 26, 1040, (255, 200, 224), 0.72, 9)]
    for (txt, fp, sz, y, cl, al, tr) in lines:
        try:
            f = ImageFont.truetype(fp, sz)
        except Exception:
            continue
        ws = [d.textlength(c, font=f) for c in txt]
        total = sum(ws) + tr * (len(ws) - 1)
        x = 1420.0 - total
        for i, c in enumerate(txt):
            cx = x + sum(ws[:i]) + tr * i
            k = clip((age - 0.02 - abs(cx - 1210.0) / 2000.0) / 0.30)
            a = float(eOut(k)) if k > 0 else 0.0
            if a <= 0.004:
                continue
            dy = 8.0 * (1.0 - float(eOut(k)))
            d.text((cx, y + dy), c, font=f, fill=(cl[0], cl[1], cl[2], int(255 * a * al)))
    return np.asarray(im, np.float32) / 255.0


# ----------------------------------------------------------------- CLI
def save(img, path):
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(path, quality=95)


def render(t):
    col = render_frame(t)
    col = draw_type(col, t)
    return col


def cmd_one(t, out):
    t0 = time.time()
    img = render(t)
    save(img, out)
    print("%s  t=%.2fs  %.1fs" % (out, t, time.time() - t0), flush=True)


def _worker(i):
    t = i / float(FPS)
    path = os.path.join(ROOT, "frames", "f_%04d.png" % i)
    last = None
    for attempt in range(4):
        try:
            img = render(t)
            save(img, path)
            return i
        except MemoryError as e:      # 全屏 SDF 的峰值内存很凶，本机可用常年 1.3-1.8GB
            last = e
            import gc
            gc.collect()
            time.sleep(1.5 + attempt * 1.5)
    raise last


def cmd_all(workers=3, lo=0, hi=None):
    os.makedirs(os.path.join(ROOT, "frames"), exist_ok=True)
    n = int(round(DUR * FPS))
    hi = n if hi is None else min(hi, n)
    lo = max(0, lo)
    t0 = time.time()
    tot = hi - lo
    import multiprocessing as mp
    done = 0
    # maxtasksperchild：每渲 6 帧就换一个干净进程。
    # 全屏 SDF 每帧的峰值分配很凶，进程跑久了内存碎片会累积到分配不出 8MB。
    with mp.Pool(workers, maxtasksperchild=6) as pool:
        for _ in pool.imap_unordered(_worker, range(lo, hi), chunksize=1):
            done += 1
            if done % 10 == 0 or done == tot:
                el = time.time() - t0
                print("  %3d/%d  %.2f 帧/秒  ETA %.1f 分钟" %
                      (done, tot, done / max(el, 1e-3), (tot - done) / max(done / max(el, 1e-3), 1e-3) / 60.0),
                      flush=True)
    print("完成 %d 帧，用时 %.1f 分钟" % (tot, (time.time() - t0) / 60.0))


def cmd_preview():
    for t in (0.30, 0.55, 1.30, 2.60, 3.60, 4.30, 5.20, 6.45, 7.30, 8.60, 9.50):
        img = render(t)
        save(img, os.path.join(ROOT, "prev_%.2f.png" % t))
        print("prev_%.2f.png" % t, flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if cmd == "one":
        cmd_one(float(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "out.png")
    elif cmd == "all":
        cmd_all(int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    elif cmd == "range":
        cmd_all(int(sys.argv[5]) if len(sys.argv) > 5 else 3, int(sys.argv[2]), int(sys.argv[3]))
    else:
        cmd_preview()
