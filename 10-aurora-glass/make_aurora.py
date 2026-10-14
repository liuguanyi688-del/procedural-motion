# -*- coding: utf-8 -*-
"""
10 · 弥散渐变 · 玻璃拟态  Aurora · Glassmorphism
================================================
纯 numpy + Pillow 复刻 —— 没有 AE、没有 Blender、没有着色器编译器，
每一帧都是数学算出来的：

    极光光场 → 透视玻璃卡片（背景模糊 / 边缘折射 / 斜向高光）
             → 液态玻璃透镜（7 采样光谱色散）
             → 玻璃字标（磨砂玻璃字形）
             → 电影后期（bloom / 胶片颗粒 / 暗角 / 抖动）

    python make_aurora.py preview         # 关键帧预览 prev_*.png
    python make_aurora.py one 6.0 a.png   # 单帧
    python make_aurora.py all             # 600 帧 → frames/
"""

import os
import sys
import math
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

np.seterr(all="ignore")

# ----------------------------------------------------------------- 规格
W, H = 1920, 1080          # 设计空间（与参考的 1920×1080 y 向下一致）
FPS = 60
DUR = 10.0
FOCAL = 1600.0             # 焦距
ROOT = os.path.dirname(os.path.abspath(__file__))

# 光场以 1/2 分辨率计算（纯渐变，肉眼无差），玻璃与文字走全分辨率
HALF = 2

LIGHT = np.array([-0.55, -0.83], np.float32)   # 指向主光（左上）的 2D 方向

PAL = {
    "base": "#040312", "violet": "#7050FF", "blue": "#2F46F2", "cyan": "#34CFF0",
    "magenta": "#B653F0", "indigo": "#3320A8", "periwinkle": "#8C8CFF", "deep": "#3036D8",
}


# ----------------------------------------------------------------- 数学
def fract(x):
    return x - np.floor(x)


def sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def f32(x):
    if isinstance(x, np.ndarray):
        return x if x.dtype == np.float32 else x.astype(np.float32)
    return np.float32(x)


def mix(a, b, x):
    return f32(a) + (f32(b) - f32(a)) * f32(x)


def clip(x, a=0.0, b=1.0):
    return np.clip(x, np.float32(a), np.float32(b))


def seg(a, b, x):
    return float(np.clip((x - a) / (b - a), 0.0, 1.0))


def lerp(a, b, x):
    return a + (b - a) * x


def eout_cubic(x):
    x = clip(x)
    return 1.0 - (1.0 - x) ** 3


def ein_out_cubic(x):
    x = clip(x)
    return np.where(x < 0.5, 4 * x ** 3, 1 - (-2 * x + 2) ** 3 / 2)


def eout_back(x, s=1.20):
    x = clip(x)
    c = s + 1.0
    return 1 + c * (x - 1) ** 3 + s * (x - 1) ** 2


def eout_sine(x):
    return np.sin(np.clip(x, 0, 1) * math.pi / 2)


def eout_quint(x):
    x = clip(x)
    return 1 - (1 - x) ** 5


def keysS(kf, fn):
    """一维关键帧插值（t, value）+ 缓动"""
    ts = np.array([k[0] for k in kf], np.float64)
    vs = np.array([k[1] for k in kf], np.float64)

    def f(t):
        t = float(t)
        if t <= ts[0]:
            return float(vs[0])
        if t >= ts[-1]:
            return float(vs[-1])
        i = int(np.searchsorted(ts, t) - 1)
        u = (t - ts[i]) / (ts[i + 1] - ts[i])
        return float(lerp(vs[i], vs[i + 1], float(fn(u))))
    return f


def hexc(h):
    return np.array([int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)], np.float32) / 255.0


def luma(c):
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def sd_round_box(Lx, Ly, hx, hy, r):
    r = min(r, min(hx, hy))
    qx = np.abs(Lx) - hx + r
    qy = np.abs(Ly) - hy + r
    return (np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
            + np.minimum(np.maximum(qx, qy), 0.0) - r)


def hash12(px, py):
    a = fract(px * 0.1031)
    b = fract(py * 0.1031)
    c = fract(px * 0.1031)
    d = a * (b + 33.33) + b * (c + 33.33) + c * (a + 33.33)
    a, b, c = a + d, b + d, c + d
    return fract((a + b) * c)


# ----------------------------------------------------------------- 噪声
NOISE_UNIT = 64.0   # 每噪声单位占多少 tile 像素


def _upsample_grid(g, n):
    """把 m×m 随机格平滑放大到 n×n（周期性，可无缝平铺）"""
    m = g.shape[0]
    x = np.arange(n, dtype=np.float32) * (m / n)
    i0 = np.floor(x).astype(np.int32)
    f = x - i0
    f = f * f * (3.0 - 2.0 * f)
    i1 = (i0 + 1) % m
    i0 = i0 % m
    rows = g[i0] * (1 - f)[:, None] + g[i1] * f[:, None]      # 行方向
    cols = rows[:, i0] * (1 - f)[None, :] + rows[:, i1] * f[None, :]  # 列方向
    return cols.astype(np.float32)


def fbm(n, octaves, seed, base=4):
    rng = np.random.default_rng(seed)
    acc = np.zeros((n, n), np.float32)
    amp, tot, size = 1.0, 0.0, base
    for _ in range(octaves):
        if size > n:
            break
        acc += _upsample_grid(rng.random((size, size), np.float32), n) * amp
        tot += amp
        amp *= 0.5
        size *= 2
    return acc / tot


TILE = 512
_NZ = {}


def noise_tile(key):
    if key not in _NZ:
        if key == "A":
            _NZ[key] = fbm(TILE, 6, 11)
        elif key == "B":
            _NZ[key] = fbm(TILE, 6, 23)
        elif key == "C":
            _NZ[key] = fbm(TILE, 5, 37)
        elif key == "D":
            _NZ[key] = fbm(TILE, 5, 53)
    return _NZ[key]


def sample_tile(t, X, Y):
    n = t.shape[0]
    x = np.mod(X, n)
    y = np.mod(Y, n)
    x0 = np.floor(x)
    y0 = np.floor(y)
    fx = (x - x0).astype(np.float32)
    fy = (y - y0).astype(np.float32)
    x0 = x0.astype(np.int32) % n
    y0 = y0.astype(np.int32) % n
    x1 = (x0 + 1) % n
    y1 = (y0 + 1) % n
    a = t[y0, x0]
    b = t[y0, x1]
    c = t[y1, x0]
    d = t[y1, x1]
    top = a + (b - a) * fx
    bot = c + (d - c) * fx
    return top + (bot - top) * fy


# ----------------------------------------------------------------- 采样 / 模糊 / 缩放
def sample(img, X, Y):
    """双线性采样（X/Y 为目标图像素坐标，越界自动 clamp）

    就地运算版：峰值临时量从 7 个降到 4 个（内存吃紧时很关键）
    """
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


def _box1d(a, r, axis):
    if r < 1:
        return a
    n = a.shape[axis]
    pad = [(r, r) if i == axis else (0, 0) for i in range(a.ndim)]
    p = np.pad(a, pad, mode="edge")
    cs = np.cumsum(p, axis=axis)
    zs = list(cs.shape)
    zs[axis] = 1
    cs = np.concatenate([np.zeros(zs, cs.dtype), cs], axis=axis)
    idx_hi = np.arange(n) + 2 * r + 1
    idx_lo = np.arange(n)
    return (np.take(cs, idx_hi, axis=axis) - np.take(cs, idx_lo, axis=axis)) / (2 * r + 1)


def blur(a, sigma):
    """三次盒式模糊 ≈ 高斯（O(n)，对多通道 float 友好）"""
    if sigma < 0.6:
        return a
    r = max(1, int(round(sigma)))
    for _ in range(3):
        a = _box1d(a, r, 0)
        a = _box1d(a, r, 1)
    return a


def down2(a):
    h, w = a.shape[:2]
    h -= h % 2
    w -= w % 2
    a = a[:h, :w]
    if a.ndim == 3:
        return a.reshape(h // 2, 2, w // 2, 2, a.shape[2]).mean(axis=(1, 3))
    return a.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))


def down4(a):
    b = down2(down2(a))
    return b


def resize_f(a, size):
    """可分离双线性缩放（纯 numpy，确定性；不用 PIL —— 它在 F 模式上有内存风险）"""
    Wt, Ht = int(size[0]), int(size[1])
    h, w = a.shape[:2]
    if h == Ht and w == Wt:
        return a.copy()
    xs = (np.arange(Wt, dtype=np.float32) + 0.5) * (w / Wt) - 0.5
    x0 = np.floor(xs).astype(np.int32)
    fx = (xs - x0).astype(np.float32)
    x0c = np.clip(x0, 0, w - 1)
    x1c = np.clip(x0 + 1, 0, w - 1)
    if a.ndim == 2:
        tmp = a[:, x0c] * (1.0 - fx) + a[:, x1c] * fx
    else:
        tmp = a[:, x0c] * (1.0 - fx)[None, :, None] + a[:, x1c] * fx[None, :, None]
    ys = (np.arange(Ht, dtype=np.float32) + 0.5) * (h / Ht) - 0.5
    y0 = np.floor(ys).astype(np.int32)
    fy = (ys - y0).astype(np.float32)
    y0c = np.clip(y0, 0, h - 1)
    y1c = np.clip(y0 + 1, 0, h - 1)
    if a.ndim == 2:
        return tmp[y0c] * (1.0 - fy)[:, None] + tmp[y1c] * fy[:, None]
    return tmp[y0c] * (1.0 - fy)[:, None, None] + tmp[y1c] * fy[:, None, None]


# ----------------------------------------------------------------- 字体
FONTS = {}
FDIR = "C:/Windows/Fonts/"


def F(name, size):
    key = (name, size)
    if key not in FONTS:
        FONTS[key] = ImageFont.truetype(FDIR + name, size)
    return FONTS[key]


F_UI = "msyh.ttc"          # 微软雅黑
F_UI_B = "msyhbd.ttc"
F_EN = "segoeui.ttf"
F_EN_B = "segoeuib.ttf"
F_EN_L = "segoeuil.ttf"


def tlen(d, s, f, track=0.0):
    if not s:
        return 0.0
    return sum(d.textlength(c, font=f) for c in s) + track * (len(s) - 1)


def tdraw(d, x, y, s, f, fill, track=0.0):
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + track
    return x - track


def tdraw_c(d, cx, y, s, f, fill, track=0.0):
    """以 cx 居中绘制"""
    tdraw(d, cx - tlen(d, s, f, track) / 2.0, y, s, f, fill, track)


# ----------------------------------------------------------------- 光斑路径（闭合 Catmull-Rom 环）
def loop_bezier(pts, period, phase):
    n = len(pts)

    def f(t):
        u = ((t / period + phase) % 1.0) * n
        i = int(math.floor(u))
        s = u - i
        p0 = pts[(i - 1) % n]
        p1 = pts[i % n]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        a = 1 - s
        return [a * a * a * p1[k] + 3 * a * a * s * c1[k] + 3 * a * s * s * c2[k] + s * s * s * p2[k]
                for k in (0, 1)]
    return f


BLOBS = [
    dict(col="violet", rx=470, ry=300, ang=18, i=1.15,
         path=loop_bezier([[600, 300], [780, 240], [840, 420], [560, 460]], 30, 0.05)),
    dict(col="magenta", rx=400, ry=230, ang=-28, i=0.90,
         path=loop_bezier([[1560, 170], [1720, 330], [1380, 360], [1300, 130]], 34, 0.6)),
    dict(col="cyan", rx=360, ry=260, ang=32, i=1.00,
         path=loop_bezier([[1500, 860], [1320, 700], [1160, 660], [1420, 980]], 26, 0.12)),
    dict(col="blue", rx=500, ry=250, ang=-8, i=0.95,
         path=loop_bezier([[820, 880], [560, 800], [700, 980], [1060, 920]], 36, 0.5)),
    dict(col="indigo", rx=560, ry=380, ang=0, i=0.32,
         path=loop_bezier([[1020, 540], [1160, 470], [1080, 640], [880, 600]], 40, 0.3)),
    dict(col="periwinkle", rx=240, ry=170, ang=10, i=0.45,
         path=loop_bezier([[1180, 420], [1060, 520], [900, 560], [1120, 360]], 24, 0.1)),
    dict(col="deep", rx=460, ry=210, ang=-6, i=0.55,
         path=loop_bezier([[1180, 1090], [1320, 1040], [1060, 1010], [980, 1080]], 32, 0.2)),
]


# ----------------------------------------------------------------- 时间轴（10s @ 60fps）
CUES = dict(
    cardA_in=-0.90, cardB_in=-0.35, cardC_in=0.05,
    pdur=1.55, land=1.5,
    typing=0.70, reply=[1.50, 1.875, 2.25, 2.625], chips=3.00,
    toggle_on=3.75, slider=[3.95, 4.85], knob_glass=4.62, snap=5.45,
    drop=6.00, partA=8.12, partB=6.72, partC=6.95,
    lens_born=4.62, lens_glide=[5.95, 6.90],
    word=6.90, word_end=8.30, sweep=[7.15, 8.05],
    ring_open=[7.35, 8.10], wave=9.00, ring_glint=[9.10, 9.60], end=DUR,
)

GAIN0 = keysS([[0, 0.78], [1.3, 1.0], [5.8, 1.0], [5.985, 1.0], [6.055, 1.085],
               [6.3, 1.17], [7.4, 1.0], [8.3, 1.04], [8.95, 1.03], [9.3, 1.08], [10, 1.06]],
              lambda u: math.sin(u * math.pi / 2))


def gain(t):
    return GAIN0(t) + 0.08 * float(ein_out_cubic(seg(CUES["slider"][0], CUES["slider"][1], t)))


def camera(t):
    return (34.0 * math.sin(0.13 * t + 0.4),
            -20.0 * math.sin(0.19 * t + 1.1),
            70.0 * math.cos(0.09 * t) - 35.0)


# ----------------------------------------------------------------- 卡片定义
class Card:
    def __init__(self, cid, w, h, r, base, rot, tin, pdur, part=None, drift=(0, 0, 0),
                 draw=None, part_keep=0.0):
        self.id = cid
        self.w, self.h, self.r = w, h, r
        self.base = np.array(base, np.float32)
        self.rot = rot
        self.tin, self.pdur = tin, pdur
        self.part = part
        self.part_keep = part_keep
        self.drift = np.array(drift, np.float32)
        self.draw = draw
        self.tex = None
        self.tex_t = None


def rot_matrix(rx, ry, rz):
    rx, ry, rz = math.radians(rx), math.radians(ry), math.radians(rz)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], np.float32)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], np.float32)
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], np.float32)
    return Rz @ Ry @ Rx


def card_state(c, t, lens_c):
    """入场 / 漂移 / 让位 —— 返回中心、基向量、不透明度、雾化、内容透明度"""
    e = eout_back(seg(c.tin, c.tin + c.pdur, t))
    op = sstep(0.0, 0.30, seg(c.tin, c.tin + c.pdur, t))
    defocus = 1.0 + 26.0 * (1.0 - e)
    content_a = sstep(0.30, 0.85, seg(c.tin, c.tin + c.pdur, t))

    # 让位（parting）：飞走 + 淡出 + 失焦
    part = 0.0
    if c.part is not None:
        part = eout_cubic(seg(c.part, c.part + 0.75, t))
        op *= 1.0 - part * (1.0 - c.part_keep)
        defocus += 22.0 * part

    # 呼吸：卡片被光推动一点点
    bre = 0.6 * math.sin(0.7 * t + hash(c.id) % 7)

    p = c.base.copy()
    p[1] += 70.0 * (1.0 - e) + bre
    p[2] += 560.0 * (1.0 - e)
    p += c.drift * part

    # 入场时角度收拢
    k = 1.0 - e
    rot = (c.rot[0] * (1 - 0.55 * k), c.rot[1] * (1 - 0.55 * k), c.rot[2])
    R = rot_matrix(*rot)
    U = R[:, 0].astype(np.float32)
    V = R[:, 1].astype(np.float32)
    N = R[:, 2].astype(np.float32)
    return p.astype(np.float32), U, V, N, float(op), float(defocus), float(content_a), float(part)


# ----------------------------------------------------------------- 卡片内容（PIL 绘制，2 倍超采样）
S = 2


def _radial(img, cx, cy, r, stops):
    """在 RGBA 图上叠一个径向渐变圆（stops: [(pos, (r,g,b,a)), ...]）"""
    x0, y0 = int(cx - r) - 1, int(cy - r) - 1
    x1, y1 = int(cx + r) + 2, int(cy + r) + 2
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img.width, x1), min(img.height, y1)
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    d = np.hypot(xx - cx, yy - cy) / max(r, 1e-3)
    a = np.zeros_like(d)
    rgb = np.zeros(d.shape + (3,), np.float32)
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        m = (d >= p0) & (d < p1)
        u = np.clip((d - p0) / max(p1 - p0, 1e-6), 0, 1)[m]
        for k in range(3):
            rgb[..., k][m] = lerp(c0[k], c1[k], u)
        a[m] = lerp(c0[3], c1[3], u)
    a[d >= stops[-1][0]] = 0.0
    a *= np.clip(1.0 - d, 0, 1) ** 0.15
    sub = np.asarray(img.crop((x0, y0, x1, y1)), np.float32)
    sa = sub[..., 3:4] / 255.0
    srgb = sub[..., :3] / 255.0
    na = a[..., None]
    out_a = na + sa * (1 - na)
    out_rgb = (rgb * na + srgb * sa * (1 - na)) / np.maximum(out_a, 1e-5)
    sub[..., :3] = out_rgb * 255.0
    sub[..., 3:4] = out_a * 255.0
    img.paste(Image.fromarray(np.clip(sub, 0, 255).astype(np.uint8), "RGBA"), (x0, y0))


def _sun(d, cx, cy, r, a=230):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, a), width=int(max(1, r * 0.30)))
    for i in range(8):
        ang = i * math.pi / 4
        x0 = cx + math.cos(ang) * r * 1.55
        y0 = cy + math.sin(ang) * r * 1.55
        x1 = cx + math.cos(ang) * r * 2.30
        y1 = cy + math.sin(ang) * r * 2.30
        d.line([x0, y0, x1, y1], fill=(255, 255, 255, a), width=int(max(1, r * 0.30)))


def _moon(img, cx, cy, r, a=235):
    m = Image.new("L", (int(r * 4), int(r * 4)), 0)
    dm = ImageDraw.Draw(m)
    c = r * 2
    dm.ellipse([c - r, c - r, c + r, c + r], fill=255)
    dm.ellipse([c - r * 0.42, c - r * 1.20, c + r * 1.55, c + r * 0.78], fill=0)
    lay = Image.new("RGBA", m.size, (255, 255, 255, 0))
    lay.putalpha(m.point(lambda v: int(v * a / 255)))
    img.alpha_composite(lay, (int(cx - c), int(cy - c)))


def content_chat(c, t):
    w, h = c.w, c.h
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    P0 = 34
    # 头像光球
    _radial(img, (P0 + 13) * S, (P0 + 14) * S, 12.5 * S,
            [(0.0, (0.91, 0.89, 1.0, 1)), (0.35, (0.60, 0.49, 1.0, 1)),
             (0.75, (0.25, 0.33, 0.94, 1)), (1.0, (0.21, 0.78, 0.93, 0))])
    d.text(((P0 + 44) * S, (P0 + 3) * S), "极光", font=F(F_UI_B, 20 * S), fill=(255, 255, 255, 244))
    d.text(((w - P0) * S, (P0 + 6) * S), "刚刚", font=F(F_UI, 16 * S), fill=(255, 255, 255, 130),
           anchor="ra")

    # 用户气泡
    txt = "帮我安排一个慢悠悠的周日。"
    fq = F(F_UI, 21 * S)
    tw = tlen(d, txt, fq)
    bx1 = w - P0
    bx0 = bx1 - (tw / S + 40)
    by0, by1 = 84, 132
    d.rounded_rectangle([bx0 * S, by0 * S, bx1 * S, by1 * S], radius=24 * S,
                        fill=(255, 255, 255, 26), outline=(255, 255, 255, 34), width=1 * S)
    k = int(round(len(txt) * seg(CUES["typing"], CUES["typing"] + 1.05, t)))
    if k > 0:
        tdraw(d, (bx0 + 20) * S, ((by0 + by1) / 2) * S, txt[:k], fq, (255, 255, 255, 240), 0)
        # 用 anchor 手动居中：上面按左对齐，这里改回右对齐更自然
    img2 = img

    # 回复三行
    lines = ["睡到自然醒。", "四点去江边散步，", "等灯亮起来。"]
    fr = F(F_UI, 23 * S)
    for i, ln in enumerate(lines):
        a0 = CUES["reply"][i]
        k = float(ein_out_cubic(seg(a0, a0 + 0.42, t)))
        if k <= 0:
            continue
        y = (176 + i * 37) * S + (1 - k) * 10 * S
        alpha = [250, 205, 165][i] * k
        tdraw(d, P0 * S, y, ln, fr, (255, 255, 255, int(alpha)), 0)

    # chips
    chips = ["加入日历", "3:30 提醒我"]
    fc = F(F_UI, 17 * S)
    ck = float(eout_back(seg(CUES["chips"], CUES["chips"] + 0.5, t)))
    x = P0
    for i, s in enumerate(chips):
        cw = tlen(d, s, fc) / S + 40
        if ck > 0:
            y0c, y1c = h - 70, h - 30
            d.rounded_rectangle([x * S, y0c * S, (x + cw) * S, y1c * S], radius=20 * S,
                                fill=(255, 255, 255, int(30 * ck)),
                                outline=(255, 255, 255, int(56 * ck)), width=1 * S)
            tdraw(d, (x + 20) * S, ((y0c + y1c) / 2 - 10) * S, s, fc,
                  (255, 255, 255, int(232 * ck)), 0)
        x += cw + 14
    return img2


def content_voice(c, t):
    w, h = c.w, c.h
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    P0 = 30
    d.text((P0 * S, P0 * S), "聆听中", font=F(F_UI_B, 19 * S), fill=(255, 255, 255, 244))
    lw = tlen(d, "聆听中", F(F_UI_B, 19 * S)) / S
    sec = int(t)
    d.text(((P0 + lw + 12) * S, (P0 + 3) * S), "%d:%02d" % (sec // 60, sec % 60),
           font=F(F_EN, 16 * S), fill=(255, 255, 255, 128))

    # 波形：一圈一圈往外推的能量
    cy = 116
    x = P0 + 30
    n = 0
    on = sstep(0.25, 0.75, t)
    while x < w - P0 - 4:
        ph = n * 0.62 - t * 7.4
        env = math.exp(-((x - (P0 + 40)) / (w * 0.52)) ** 2) if x > P0 + 30 else 1.0
        amp = (0.22 + 0.78 * abs(math.sin(ph) * math.sin(ph * 0.37 + 1.1))) * env
        bh = (3.0 + 46.0 * amp) * on
        a = int(255 * (0.30 + 0.62 * env) * on)
        d.rounded_rectangle([x * S, (cy - bh / 2) * S, (x + 3) * S, (cy + bh / 2) * S],
                            radius=1.6 * S, fill=(255, 255, 255, a))
        x += 7
        n += 1
    # 声源光球
    _radial(img, (P0 + 13) * S, cy * S, 15 * S,
            [(0.0, (1.0, 1.0, 1.0, 1)), (0.35, (0.75, 0.96, 1.0, 0.95)),
             (0.72, (0.26, 0.83, 0.95, 0.55)), (1.0, (0.26, 0.83, 0.95, 0))])
    return img


def content_modes(c, t):
    w, h = c.w, c.h
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    P0 = 30
    on = float(ein_out_cubic(seg(CUES["toggle_on"], CUES["toggle_on"] + 0.45, t)))

    # ---- 行 1：专注
    y1 = 76
    _moon(img, (P0 + 15) * S, y1 * S, 12 * S)
    d.text(((P0 + 42) * S, (y1 - 20) * S), "专注", font=F(F_UI_B, 21 * S), fill=(255, 255, 255, 246))
    d.text(((P0 + 42) * S, (y1 + 6) * S), "只有家人能联系到你", font=F(F_UI, 15 * S),
           fill=(255, 255, 255, 128))
    tw_, th_ = 48, 28
    tx1 = w - P0
    tx0 = tx1 - tw_
    ty0 = y1 - th_ / 2
    if on > 0.01:
        _radial(img, ((tx0 + tw_ / 2) * S), (y1 * S), (th_ / 2) * S * 1.15,
                [(0.0, (0.36, 0.49, 1.0, on)), (0.75, (0.27, 0.72, 1.0, on)), (1.0, (0.26, 0.83, 0.95, 0))])
    d.rounded_rectangle([tx0 * S, ty0 * S, tx1 * S, (ty0 + th_) * S], radius=(th_ / 2) * S,
                        fill=(255, 255, 255, int(lerp(38, 96, on))),
                        outline=(255, 255, 255, int(lerp(48, 90, on))), width=1 * S)
    # 旋钮：4.62s 起被液态玻璃珠「接管」——珠子长大，白旋钮淡出
    gk = float(ein_out_cubic(seg(CUES["knob_glass"], CUES["knob_glass"] + 0.55, t)))
    lg = float(ein_out_cubic(seg(CUES["lens_born"], 5.95, t)))
    kfade = 1.0 - lg
    kr = lerp(11.0, 12.6, gk)
    kx = lerp(tx0 + th_ / 2, tx1 - th_ / 2, on)
    if gk > 0.02 and kfade > 0.02:
        _radial(img, kx * S, y1 * S, kr * S * 1.25,
                [(0.0, (1.0, 1.0, 1.0, 0.98 * kfade)), (0.55, (0.86, 0.92, 1.0, 0.85 * kfade)),
                 (0.85, (0.62, 0.72, 1.0, 0.55 * kfade)), (1.0, (0.55, 0.65, 1.0, 0.0))])
    if kfade > 0.02:
        d.ellipse([(kx - kr) * S, (y1 - kr) * S, (kx + kr) * S, (y1 + kr) * S],
                  fill=(255, 255, 255, int(lerp(255, 232, gk) * kfade)))

    # ---- 行 2：光晕滑杆
    y2 = 176
    _sun(d, (P0 + 15) * S, y2 * S, 9 * S, 225)
    d.text(((P0 + 42) * S, (y2 - 15) * S), "光晕", font=F(F_UI_B, 21 * S), fill=(255, 255, 255, 246))
    v = float(lerp(0.30, 0.74, ein_out_cubic(seg(CUES["slider"][0], CUES["slider"][1], t))))
    sx0 = P0 + 96
    sx1 = w - P0 - 52
    d.rounded_rectangle([sx0 * S, (y2 - 2) * S, sx1 * S, (y2 + 2) * S], radius=2 * S,
                        fill=(255, 255, 255, 46))
    kx2 = sx0 + (sx1 - sx0) * v
    _radial(img, ((sx0 + kx2) / 2) * S, y2 * S, ((kx2 - sx0) / 2) * S * 1.02,
            [(0.0, (0.44, 0.36, 1.0, 0.0)), (0.5, (0.48, 0.40, 1.0, 0.42)),
             (0.86, (0.30, 0.62, 1.0, 0.30)), (1.0, (0.26, 0.83, 0.95, 0.0))])
    d.rounded_rectangle([sx0 * S, (y2 - 2) * S, kx2 * S, (y2 + 2) * S], radius=2 * S,
                        fill=(255, 255, 255, 235))
    d.ellipse([(kx2 - 8) * S, (y2 - 8) * S, (kx2 + 8) * S, (y2 + 8) * S], fill=(255, 255, 255, 250))
    d.text((sx1 * S, (y2 - 30) * S), "%d%%" % round(v * 100), font=F(F_EN, 15 * S),
           fill=(255, 255, 255, 150), anchor="ra")
    return img


# ----------------------------------------------------------------- 极光光场
def aurora(px, py, t, cam, g, ripple_p):
    qx = px / 1080.0
    qy = py / 1080.0
    U = NOISE_UNIT
    # 两层 fbm 扭曲
    wx = sample_tile(noise_tile("A"), qx * 0.9 * U + t * 2.6, qy * 0.9 * U + t * 1.7)
    wy = sample_tile(noise_tile("B"), qx * 0.9 * U + t * 2.2 + 41.0, qy * 0.9 * U + t * 1.3 + 17.0)
    w2x = sample_tile(noise_tile("C"), qx * 2.1 * U + t * 4.1 + 9.0, qy * 2.1 * U + t * 3.2 + 3.0)
    w2y = sample_tile(noise_tile("D"), qx * 2.1 * U + t * 3.6 + 71.0, qy * 2.1 * U + t * 4.4 + 29.0)
    wx = (wx - 0.5) * 2.0
    wy = (wy - 0.5) * 2.0
    w2x = (w2x - 0.5) * 2.0
    w2y = (w2y - 0.5) * 2.0
    WARP = 150.0
    pw_x = px + wx * WARP + w2x * WARP * 0.3
    pw_y = py + wy * WARP + w2y * WARP * 0.3

    # 缓慢的光涟漪（drop）
    rc_x, rc_y, rc_r, rc_a = ripple_p
    rdx = pw_x - rc_x
    rdy = pw_y - rc_y
    rl = np.hypot(rdx, rdy)
    ring = np.exp(-((rl - rc_r) / 170.0) ** 2) * rc_a
    sc = ring * 46.0 / np.maximum(rl, 1.0)
    pw_x = pw_x + rdx * sc
    pw_y = pw_y + rdy * sc

    acc = np.zeros(pw_x.shape + (3,), np.float32)
    ws = np.zeros(pw_x.shape, np.float32)
    for i, b in enumerate(BLOBS):
        bx, by = b["path"](t)
        bx -= cam[0] * 0.35
        by -= cam[1] * 0.35
        a = math.radians(b["ang"]) + 0.08 * math.sin(t * 0.3 + i)
        ca, sa = math.cos(a), math.sin(a)
        dx = pw_x - bx
        dy = pw_y - by
        rx = (ca * dx + sa * dy) / b["rx"]
        ry = (-sa * dx + ca * dy) / b["ry"]
        gg = np.exp(-(rx * rx + ry * ry)) * b["i"]
        acc += hexc(PAL[b["col"]]) * gg[..., None]
        ws += gg

    mixc = acc / np.maximum(ws, 1e-4)[..., None]
    cov = np.power(np.maximum(1.0 - np.exp(-ws * 1.5), 0.0), 1.3)
    col = mix(hexc(PAL["base"]), mixc, cov[..., None]) + acc * 0.07
    core = sstep(0.75, 2.1, ws)
    col = mix(col, col * 1.22 + np.array([0.035, 0.03, 0.07], np.float32), (core * 0.55)[..., None])
    col *= (g * (1.0 + ring * 0.2))[..., None]
    col += np.array([0.50, 0.36, 1.0], np.float32) * (ring * 0.045 * cov)[..., None]

    silk = sample_tile(noise_tile("A"), px / 260.0 * U + wx * 0.8 * U * 0.4 + 3.0, py / 1400.0 * U + 7.0)
    col *= (1.0 + (silk - 0.5) * 2.0 * 0.05 * cov)[..., None]
    return col, cov, ring


def motes(px, py, t):
    m = np.zeros(px.shape + (3,), np.float32)
    lockK = sstep(7.0, 7.6, t)
    for i in range(10):
        fi = float(i)
        h1 = hash12(np.float32(fi * 1.37 + 0.2), np.float32(fi * 7.11 + 0.7))
        h2 = hash12(np.float32(fi * 7.11 + 0.7), np.float32(fi * 1.37 + 0.2))
        v1 = hash12(np.float32(fi), np.float32(3.1))
        v2 = hash12(np.float32(3.1), np.float32(fi))
        velx = (v1 - 0.5) * 10.0 + 2.0
        vely = (v2 - 0.5) * 6.0 - 3.0
        posx = h1 * 1880.0 + 20.0 + velx * t
        posy = h2 * 1040.0 + 20.0 + vely * t
        sig = lerp(3.0, 5.0, hash12(np.float32(fi), np.float32(4.4)))
        amp = lerp(0.12, 0.25, hash12(np.float32(fi), np.float32(5.5)))
        tw = 0.8 + 0.2 * math.sin(t * (0.5 + hash12(np.float32(fi), np.float32(2.2))) + fi * 2.1)
        bdx = abs(posx - 960.0) - 380.0
        bdy = abs(posy - 600.0) - 150.0
        keep = lerp(1.0, float(sstep(0.0, 70.0, max(bdx, bdy))), lockK)
        dd = np.hypot(px - posx, py - posy)
        m += (np.exp(-dd * dd / (2.0 * sig * sig)) * amp * tw * keep)[..., None] * np.array(
            [0.86, 0.9, 1.0], np.float32)
    return m


# ----------------------------------------------------------------- 玻璃卡片
def plane_local(px, py, C, U, V, N, O):
    dx = px - 960.0
    dy = py - 540.0
    L = np.sqrt(dx * dx + dy * dy + FOCAL * FOCAL)
    dx, dy, dz = dx / L, dy / L, FOCAL / L
    den = dx * N[0] + dy * N[1] + dz * N[2]
    k = (C[0] - O[0]) * N[0] + (C[1] - O[1]) * N[1] + (C[2] - O[2]) * N[2]
    tt = k / den
    rx = (O[0] + dx * tt) - C[0]
    ry = (O[1] + dy * tt) - C[1]
    rz = (O[2] + dz * tt) - C[2]
    return rx * U[0] + ry * U[1] + rz * U[2], rx * V[0] + ry * V[1] + rz * V[2]


def card_bbox(c, st, cam):
    C, U, V, N, op, dfc, ca, part = st
    O = np.array([960.0 + cam[0], 540.0 + cam[1], -FOCAL + cam[2]], np.float32)
    hw, hh = c.w / 2.0, c.h / 2.0
    xs, ys = [], []
    for sx in (-1, 1):
        for sy in (-1, 1):
            P = C + U * (hw * sx) + V * (hh * sy)
            dz = P[2] - O[2]
            if dz <= 1.0:
                continue
            xs.append(960.0 + FOCAL * (P[0] - O[0]) / dz)
            ys.append(540.0 + FOCAL * (P[1] - O[1]) / dz)
    if not xs:
        return None
    m = 130.0 + dfc * 3.0
    x0 = int(max(0, min(xs) - m))
    x1 = int(min(W, max(xs) + m))
    y0 = int(max(0, min(ys) - m))
    y1 = int(min(H, max(ys) + m))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, x1, y0, y1


def draw_card(scene, quarter, c, st, cam, t):
    bb = card_bbox(c, st, cam)
    if bb is None:
        return
    C, U, V, N, op, defocus, content_a, part = st
    if op <= 0.002:
        return
    x0, x1, y0, y1 = bb
    O = np.array([960.0 + cam[0], 540.0 + cam[1], -FOCAL + cam[2]], np.float32)
    hw, hh = c.w / 2.0, c.h / 2.0
    px = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
    py = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5

    Lx, Ly = plane_local(px, py, C, U, V, N, O)
    Lx1, _ = plane_local(px + 1.0, py, C, U, V, N, O)
    _, Ly1 = plane_local(px, py + 1.0, C, U, V, N, O)
    pxw = np.maximum(np.hypot(Lx1 - Lx, Ly1 - Ly), 1e-4)

    sd = sd_round_box(Lx, Ly, hw, hh, c.r)
    sdS = sd / pxw
    dw = max(defocus, 0.5)
    cov = clip(0.5 - sdS / (2.0 * dw), 0.0, 1.0)
    if cov.max() <= 0.0:
        return

    # 外法线
    r = min(c.r, min(hw, hh))
    qx = np.abs(Lx) - hw + r
    qy = np.abs(Ly) - hh + r
    both = (qx > 0) & (qy > 0)
    nrm = np.hypot(np.maximum(qx, 1e-6), np.maximum(qy, 1e-6))
    gx = np.where(both, qx / nrm, np.where(qx > qy, 1.0, 0.0))
    gy = np.where(both, qy / nrm, np.where(qx > qy, 0.0, 1.0))
    gx = gx * np.sign(Lx + 1e-6)
    gy = gy * np.sign(Ly + 1e-6)

    inside = -sdS
    rim = 1.0 - sstep(0.0, 13.0, inside)
    offs = -np.power(np.maximum(rim, 0.0), 1.3) * 24.0
    bb_col = sample(quarter, (px + gx * offs) / 4.0, (py + gy * offs) / 4.0)

    # 磨砂配方：模糊 + 提饱和 + 7% 白
    l = luma(bb_col)[..., None]
    frost = 1.0
    bb_col = np.maximum(l + (bb_col - l) * (1.0 + 0.46 * frost), 0.0)
    col = bb_col * 1.02 + 0.056 * frost + np.array([0.012, 0.012, 0.03], np.float32)

    # 边缘内辉光
    facing = clip(gx * LIGHT[0] + gy * LIGHT[1], -1.0, 1.0) * 0.5 + 0.5
    col = col + (1.0 - sstep(0.0, 26.0, inside))[..., None] * (0.018 + 0.05 * facing ** 2)[..., None]

    # 斜向柔光带
    ux = Lx / hw
    uy = Ly / hh
    band = (ux * 0.8 + uy * 0.6) / math.hypot(0.8, 0.6)
    sheen = 0.55 * math.sin(0.5 * t + 1.0)
    col = col + np.exp(-((band - sheen) / 0.45) ** 2)[..., None] * 0.045

    # 划过的高光
    gk = seg(2.2, 3.4, t) * (1.0 - seg(2.9, 3.8, t)) + seg(5.0, 6.2, t) * (1.0 - seg(5.7, 6.6, t))
    gpos = lerp(-1.3, 1.3, float(ein_out_cubic(seg(2.2, 3.8, t))))
    glint = gk * 0.16
    col = col + np.exp(-((band - gpos) / 0.16) ** 2)[..., None] * glint * \
        (0.6 + 0.4 * sstep(0.0, 30.0, inside))[..., None] * np.array([0.93, 0.95, 1.0], np.float32)
    col = col + (1.0 - clip((uy + ux * 0.4 + 1.0) * 0.5, 0.0, 1.0))[..., None] * 0.035

    # 卡面 UI（预乘）
    if content_a > 0.002:
        tex = c.tex
        cuvx = (Lx + hw) / (2 * hw) * tex.shape[1]
        cuvy = (Ly + hh) / (2 * hh) * tex.shape[0]
        cimg = sample(tex, cuvx, cuvy)
        ca = cimg[..., 3:4] * content_a
        col = col * (1.0 - ca) + cimg[..., :3] * ca

    # 1px 内描边（受光侧更亮）
    sw = 0.9 + (dw - 0.5) * 1.5
    stroke = clip(1.0 - np.abs(inside - sw) / sw, 0.0, 1.0) * (0.9 / sw)
    sa = np.minimum(mix(0.14, 0.70, np.power(facing, 1.6)) * 1.0, 0.95)
    col = mix(col, np.ones_like(col), (stroke * sa)[..., None])

    a = (cov * op)[..., None]
    sub = scene[y0:y1, x0:x1]
    out = sub * (1.0 - a) + col * a
    scene[y0:y1, x0:x1] = np.where(a > 0.0, out, sub)


# ----------------------------------------------------------------- 液态玻璃透镜
def lens_state(t):
    """珠子（4.62）→ 长大成透镜（5.95）→ 滑到中心（6.90）→ 收成句号环（8.30）"""
    grow = float(ein_out_cubic(seg(CUES["lens_born"], 5.95, t)))
    glide = float(ein_out_cubic(seg(CUES["lens_glide"][0], CUES["lens_glide"][1], t)))
    ringk = float(ein_out_cubic(seg(CUES["ring_open"][0], CUES["ring_open"][1], t)))
    # 起点：专注开关的旋钮（投影到屏幕空间）
    cx = lerp(776.0, 960.0, glide)
    cy = lerp(786.0, 600.0, glide)
    hx = lerp(14.0, 132.0, grow)
    hy = lerp(14.0, 86.0, grow)
    rr = lerp(11.0, 46.0, grow)
    # 收成字标右边的句号环
    cx = lerp(cx, 1408.0, ringk)
    cy = lerp(cy, 640.0, ringk)
    hx = lerp(hx, 46.0, ringk)
    hy = lerp(hy, 46.0, ringk)
    rr = lerp(rr, 46.0, ringk)
    return dict(on=grow, c=(cx, cy), hx=hx, hy=hy, r=rr,
                ring_w=15.0 * ringk, glide=glide, grow=grow)


def draw_lens(scene, quarter, t, cam):
    L = lens_state(t)
    if L["on"] <= 0.004:
        return
    O = np.array([960.0 + cam[0], 540.0 + cam[1], -FOCAL + cam[2]], np.float32)
    cx, cy = L["c"]
    hx, hy = L["hx"], L["hy"]
    rr = L["r"]
    m = 90 + max(hx, hy) * 0.9
    x0 = int(max(0, cx - hx - m))
    x1 = int(min(W, cx + hx + m))
    y0 = int(max(0, cy - hy - m))
    y1 = int(min(H, cy + hy + m))
    if x1 <= x0 or y1 <= y0:
        return
    px = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
    py = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
    PX = np.broadcast_to(px, (y1 - y0, x1 - x0))
    PY = np.broadcast_to(py, (y1 - y0, x1 - x0))

    def sdf(ax, ay):
        d = sd_round_box(ax - cx, ay - cy, hx, hy, rr)
        if L["ring_w"] > 0.5:
            d = np.maximum(d, -d - L["ring_w"])
        return d

    sd = sdf(PX, PY)
    on = L["on"]

    # 场景（含阴影 + 玻璃聚光）
    sc = sample(scene, PX, PY)
    s_sh = sdf(PX, PY - 20.0)
    sh = (1.0 - sstep(-20.0, 60.0, s_sh)) * 0.26 * on
    sc = sc * (1.0 - sh)[..., None]

    if on <= 0.02:
        return

    # 厚度场（凸方圆形）
    bezel = 26.0
    d_in = -sdf(PX, PY)
    xh = clip(d_in / bezel, 0.0, 1.0)
    hC = np.power(1.0 - np.power(1.0 - xh, 2.2), 1.0 / 2.2)

    e = 0.75
    hx1 = np.power(1.0 - np.power(1.0 - clip(-sdf(PX + e, PY) / bezel, 0, 1), 2.2), 1 / 2.2)
    hx0 = np.power(1.0 - np.power(1.0 - clip(-sdf(PX - e, PY) / bezel, 0, 1), 2.2), 1 / 2.2)
    hy1 = np.power(1.0 - np.power(1.0 - clip(-sdf(PX, PY + e) / bezel, 0, 1), 2.2), 1 / 2.2)
    hy0 = np.power(1.0 - np.power(1.0 - clip(-sdf(PX, PY - e) / bezel, 0, 1), 2.2), 1 / 2.2)
    DEPTH = 26.0
    nx = -(hx1 - hx0) / (2 * e) * DEPTH
    ny = -(hy1 - hy0) / (2 * e) * DEPTH
    nl = np.sqrt(nx * nx + ny * ny + 1.0)
    nx, ny, nz = nx / nl, ny / nl, 1.0 / nl
    gl_ = np.hypot(nx, ny)
    gxn = np.where(gl_ > 1e-4, nx / np.maximum(gl_, 1e-6), 0.0)
    gyn = np.where(gl_ > 1e-4, ny / np.maximum(gl_, 1e-6), 0.0)
    edgeX = clip(-sd / bezel, 0.0, 1.0)

    # 7 采样光谱色散 —— 斯涅尔折射 R = ηI + (η·cosθi − √k)·N，入射光 I = (0,0,−1)
    IOR, DISP, MAG, MAXD = 1.42, 0.055, 1.06, 22.0
    SW = np.array([[0.00, 0.00, 0.30], [0.00, 0.10, 0.40], [0.00, 0.25, 0.25], [0.05, 0.35, 0.05],
                   [0.25, 0.25, 0.00], [0.40, 0.05, 0.00], [0.30, 0.00, 0.00]], np.float32)
    acc = np.zeros(PX.shape + (3,), np.float32)
    for i in range(7):
        kk = (3.0 - i) / 3.0                       # +1 紫 → −1 红
        eta = 1.0 / (IOR + DISP * kk)              # 折射率随波长变化 = 色散
        cosi = nz
        k_ = np.maximum(1.0 - eta * eta * (1.0 - cosi * cosi), 0.0)
        f_ = eta * cosi - np.sqrt(k_)
        rx = f_ * nx
        ry = f_ * ny
        rz = -eta + f_ * nz
        disp_x = rx / np.maximum(-rz, 0.25) * DEPTH
        disp_y = ry / np.maximum(-rz, 0.25) * DEPTH
        dl = np.maximum(np.hypot(disp_x, disp_y), 1e-3)
        sc_ = np.minimum(1.0, MAXD * (1.0 + 0.9 * kk) / dl)
        disp_x *= sc_
        disp_y *= sc_
        mag = MAG * (1.0 - 0.02 * kk)
        sxp = cx + (PX - cx) / mag + disp_x
        syp = cy + (PY - cy) / mag + disp_y
        acc += sample(sc, sxp, syp) * SW[i]

    col = acc
    # 磨砂只留在最外缘
    bl = sample(quarter, PX - gxn * 24.0, PY - gyn * 24.0)
    col = mix(col, bl * 1.1 + 0.03, (0.35 * np.power(1.0 - edgeX, 3.0))[..., None])
    col = mix(luma(col)[..., None].repeat(3, 2), col, 1.08) * 1.035 + 0.01

    # 菲涅尔反射
    F_ = np.power(1.0 - nz, 1.6)
    refl = sample(quarter, PX + gxn * 120.0, PY + gyn * 120.0) * 1.35 + 0.1
    col = mix(col, refl, clip(F_ * 0.85, 0.0, 0.5)[..., None])

    # 高光：主光（左上）+ 环境反弹（右下）
    Lk = np.array([-0.55, -0.83, 0.9], np.float32)
    Lk = Lk / np.linalg.norm(Lk)
    Lb = np.array([0.55, 0.83, 0.9], np.float32)
    Lb = Lb / np.linalg.norm(Lb)
    Vv = np.array([0.0, 0.0, 1.0], np.float32)
    rk = 2.0 * (nx * Lk[0] + ny * Lk[1] + nz * Lk[2]) * nz - Lk[2]
    rb = 2.0 * (nx * Lb[0] + ny * Lb[1] + nz * Lb[2]) * nz - Lb[2]
    col = col + np.maximum(rk, 0.0)[..., None] ** 18 * 0.75
    col = col + (np.maximum(rb, 0.0) ** 26 * 0.28)[..., None] * np.array([0.85, 0.92, 1.0], np.float32)

    # 环上滑过的镜面反光
    rg = seg(CUES["ring_glint"][0], CUES["ring_glint"][1], t)
    if rg > 0:
        ang = np.arctan2(PY - cy, PX - cx)
        ga = rg * 6.0 - 3.0
        da = np.mod(ang - ga + math.pi, 2 * math.pi) - math.pi
        wg = 0.35 + 0.65 * hC if L["ring_w"] > 0.5 else 0.1 + 0.9 * np.power(1.0 - edgeX, 2.0)
        col = col + np.exp(-da * da / 0.09)[..., None] * (0.9 * math.sin(math.pi * min(rg, 1.0)) * wg)[..., None]

    # 边缘亮线 + 内辉光
    facing = gxn * LIGHT[0] + gyn * LIGHT[1]
    lit = np.maximum(facing, 0.0) ** 2 + 0.55 * np.maximum(-facing, 0.0) ** 2
    line = clip(1.0 - np.abs(-sd - 0.8) / 1.0, 0.0, 1.0)
    col = mix(col, np.ones_like(col), (line * (0.28 + 0.62 * lit))[..., None])
    col = col + (np.exp(-(-sd) / 5.0) * (0.05 + 0.14 * lit))[..., None]
    col = col * (1.0 - (0.08 * (1.0 - edgeX) * np.maximum(-facing, 0.0) * (1.0 - lit))[..., None])

    # 台面上滑行的掠光
    lpx = (PX - cx) / max(hx, 1.0)
    lpy = (PY - cy) / max(hy, 1.0)
    gph = (L["glide"] * 2.0 - 1.0) if L["glide"] < 1 else (seg(7.0, 8.6, t) * 2.0 - 1.0)
    diag = (lpx * 1.0 + lpy * -0.4) / math.hypot(1.0, 0.4)
    col = col + np.exp(-((diag - gph) / 0.1) ** 2)[..., None] * (edgeX * 0.05)[..., None]

    a = (clip(0.5 - sd, 0.0, 1.0) * on)[..., None]
    sub = scene[y0:y1, x0:x1]
    out = sub * (1.0 - a) + col * a
    scene[y0:y1, x0:x1] = np.where(a > 0.0, out, sub)


# ----------------------------------------------------------------- 玻璃字标
def word_mask(t):
    """返回全分辨率的字标遮罩（0..1）与字号缩放"""
    ws = float(eout_cubic(seg(CUES["word"] - 0.35, CUES["word"] + 1.25, t)))
    if ws <= 0.01:
        return None, 0.0
    grow = lerp(0.30, 1.0, ws)
    img = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(img)
    size = int(216 * grow)
    if size < 6:
        return None, 0.0
    ft = F(F_UI_B, size)
    fsub = F(F_UI_B, max(8, int(54 * grow)))
    fen = F(F_EN_B, max(6, int(29 * grow)))
    a = float(sstep(0.0, 0.35, ws))
    # 从透镜处向外展开，最后略左移，把右边的位置让给句号环
    cx = lerp(985.0, 902.0, ws)
    cy = lerp(548.0, 520.0, ws)
    items = [("玻璃拟态", ft, 255, 10 * grow),
             ("弥散渐变", fsub, int(255 * a), 8 * grow),
             ("AURORA · GLASS", fen, int(232 * a), 7 * grow)]
    hs = []
    for s_, f_, al, tr in items:
        bb = d.textbbox((0, 0), s_, font=f_)
        hs.append(bb[3] - bb[1])
    gap1, gap2 = 36 * grow, 16 * grow
    total = hs[0] + gap1 + hs[1] + gap2 + hs[2]
    y = cy - total / 2.0
    for i, (s_, f_, al, tr) in enumerate(items):
        bb = d.textbbox((0, 0), s_, font=f_)
        tdraw_c(d, cx, y - bb[1], s_, f_, al, tr)
        y += hs[i] + (gap1 if i == 0 else gap2)
    return np.asarray(img, np.float32) / 255.0, grow


def draw_glyphs(scene, quarter, t):
    m, grow = word_mask(t)
    if m is None or m.max() <= 0.01:
        return
    ys, xs = np.nonzero(m > 0.004)
    if len(ys) == 0:
        return
    MG = 150
    x0 = max(0, int(xs.min()) - MG)
    y0 = max(0, int(ys.min()) - MG)
    x1 = min(W, int(xs.max()) + MG)
    y1 = min(H, int(ys.max()) + MG)
    x1 = x0 + ((x1 - x0) // 4) * 4          # 对齐到 4 的倍数，保证 down4 / resize 严格可逆
    y1 = y0 + ((y1 - y0) // 4) * 4
    m = m[y0:y1, x0:x1]
    hh, ww = m.shape

    mn = blur(m, 5.0)                        # 窄模糊 = 倒角高度
    mw = resize_f(blur(down4(m), 6.0), (ww, hh))   # 宽模糊 = 圆顶 / 投影

    px = (np.arange(ww, dtype=np.float32) + 0.5 + x0)[None, :]
    py = (np.arange(hh, dtype=np.float32) + 0.5 + y0)[:, None]
    PX = np.broadcast_to(px, (hh, ww))
    PY = np.broadcast_to(py, (hh, ww))

    # 深靛蓝池 + 暗晕：让亮玻璃在缩略图尺寸也读得出来
    pool = np.exp(-(((PX - 960.0) / 640.0) ** 2 + ((PY - 528.0) / 265.0) ** 2)) * 1.0 * grow
    sub = scene[y0:y1, x0:x1]
    bg = sub * mix(np.ones(3, np.float32), np.array([0.42, 0.39, 0.64], np.float32), pool[..., None])
    bg = bg + (pool * 0.010)[..., None]
    bg = bg * (1.0 - (0.42 * pool * clip(mw * 2.2) * (1.0 - m))[..., None])

    # 投影（光从左上 → 影子落右下）
    sh = sample(mw, PX - 5.0, PY - 11.0)
    shN = sample(mn, PX - 2.2, PY - 5.0)
    bg = bg * (1.0 - (0.34 * clip(sh * 0.75 + shN * 0.45) * (1.0 - m))[..., None])

    # 高度场与坡度
    e, ew = 1.25, 4.0
    gNx = (sample(mn, PX + e, PY) - sample(mn, PX - e, PY)) / (2 * e)
    gNy = (sample(mn, PX, PY + e) - sample(mn, PX, PY - e)) / (2 * e)
    gWx = (sample(mw, PX + ew, PY) - sample(mw, PX - ew, PY)) / (2 * ew)
    gWy = (sample(mw, PX, PY + ew) - sample(mw, PX, PY - ew)) / (2 * ew)
    slx = -(gNx * 7.5 + gWx * 5.0)
    sly = -(gNy * 7.5 + gWy * 5.0)
    nl = np.sqrt(slx * slx + sly * sly + 1.0)
    nx, ny, nz = slx / nl, sly / nl, 1.0 / nl
    gl_ = np.hypot(gNx, gNy)
    ndx = np.where(gl_ > 1e-4, -gNx / np.maximum(gl_, 1e-6), 0.0)
    ndy = np.where(gl_ > 1e-4, -gNy / np.maximum(gl_, 1e-6), 0.0)
    hN = sample(mn, PX, PY)
    bev = 1.0 - sstep(0.42, 0.97, hN)
    facing = ndx * LIGHT[0] + ndy * LIGHT[1]

    # 玻璃体：磨砂极光被折射（R/G/B 各偏一点 → 边缘色散）
    REFR = 30.0
    ox = -nx * REFR
    oy = -ny * REFR
    fr_r = sample(quarter, (PX + ox * 1.08) / 4.0, (PY + oy * 1.08) / 4.0)[..., 0]
    fr_g = sample(quarter, (PX + ox) / 4.0, (PY + oy) / 4.0)[..., 1]
    fr_b = sample(quarter, (PX + ox * 0.92) / 4.0, (PY + oy * 0.92) / 4.0)[..., 2]
    fr = np.stack([fr_r, fr_g, fr_b], -1)
    l = luma(fr)[..., None]
    fr = np.maximum(l + (fr - l) * 1.42, 0.0)
    col = fr * 1.08 + 0.062 + np.array([0.01, 0.012, 0.035], np.float32)
    col = col + (0.07 * clip(-ny * 3.0, -1.0, 1.0))[..., None]
    col = col * (1.0 - (0.50 * np.power(bev, 0.8) * np.power(np.maximum(-facing, 0.0), 1.1))[..., None])
    col = col + (bev * (0.06 + 0.72 * np.power(np.maximum(facing, 0.0), 1.7)))[..., None]
    band_e = sstep(0.34, 0.50, hN) * (1.0 - sstep(0.50, 0.72, hN))
    col = col + (band_e * np.power(np.maximum(-facing, 0.0), 2.0) * 0.42)[..., None] * np.array(
        [1.0, 0.93, 0.86], np.float32)
    col = mix(col, np.ones_like(col),
              (band_e * (0.22 + 0.70 * np.power(np.maximum(facing, 0.0), 1.4)))[..., None])

    # 圆顶上的主光镜面
    Lk = np.array([LIGHT[0], LIGHT[1], 0.9], np.float32)
    Lk = Lk / np.linalg.norm(Lk)
    sp = np.maximum(2.0 * (nx * Lk[0] + ny * Lk[1] + nz * Lk[2]) * nz - Lk[2], 0.0) ** 24
    col = col + (sp * 0.55)[..., None]

    # 掠过的高光扫光
    ks = seg(CUES["sweep"][0], CUES["sweep"][1], t)
    if 0 < ks < 1:
        dd = ((PX - 960.0) * 0.864 + (PY - 540.0) * 0.503) - lerp(-620.0, 620.0, float(ein_out_cubic(ks)))
        col = col + (np.exp(-dd * dd / (70.0 ** 2)) * (0.42 * math.sin(math.pi * ks))
                     * (0.35 + 0.65 * bev))[..., None] * np.array([1.0, 0.98, 0.95], np.float32)

    # 9.0s 的一圈光波
    wv = seg(CUES["wave"], CUES["wave"] + 1.1, t)
    if wv > 0:
        rl = np.hypot(PX - 960.0, PY - 548.0)
        rad = lerp(80.0, 1600.0, float(eout_sine(wv)))
        wave = 1.35 * (1.0 - wv) ** 1.5 * np.exp(-((rl - rad) / 15.0) ** 2)
        col = col + wave[..., None] * np.array([1.0, 0.96, 0.93], np.float32)

    out = bg * (1.0 - m[..., None]) + col * m[..., None]
    sub[:] = np.where((m > 0.002)[..., None], out, sub)
# ----------------------------------------------------------------- 后期
def post(scene, t, frame_idx, grain_tile):
    # ---- bloom：1/4 分辨率，阈值 + 大模糊
    q = down4(scene)
    l = luma(q)
    q = q * sstep(0.58, 0.95, l)[..., None]
    q = blur(q, 9.0)
    bloom = resize_f(q, (W, H))
    bamt = 0.26 + 0.38 * math.exp(-((t - 6.30) / 0.34) ** 2) + 0.08 * seg(8.9, 9.3, t) * (1 - seg(9.3, 9.9, t))
    c = scene + bloom * bamt

    # ---- 高光肩部（防止死白）
    hi = np.maximum(c - 0.82, 0.0)
    c = c - hi + hi / (1.0 + hi * 2.2)

    # ---- 暗角
    px = np.arange(W, dtype=np.float32)[None, :] + 0.5
    py = np.arange(H, dtype=np.float32)[:, None] + 0.5
    vx = (px - 960.0) / 1250.0
    vy = (py - 560.0) / 900.0
    vv = vx * vx + vy * vy
    c = c * (1.0 - (0.34 * np.power(clip(vv, 0.0, 1.6), 1.25))[..., None])

    # ---- 胶片颗粒（逐帧种子）
    go = np.array([hash12(np.float32(frame_idx * 0.618), np.float32(frame_idx * 1.303)),
                   hash12(np.float32(frame_idx * 1.303), np.float32(frame_idx * 0.618))], np.float32) * 2048.0
    gy = np.mod(py + go[1], 2048.0)
    gx = np.mod(px + go[0], 2048.0)
    g = sample(grain_tile, gx, gy) - 0.5
    g = np.broadcast_to(g, (H, W))
    l = luma(c)
    c = c + (g * 0.055 * (0.55 + 0.9 * l * (1.4 - l)))[..., None]

    # ---- 三角抖动（对抗色带）
    dth = hash12(px + frame_idx * 17.31, py + frame_idx * 17.31) + \
        hash12(px * 1.37 + frame_idx * 3.1, py * 1.37 + frame_idx * 3.1) - 1.0
    c = c + (dth / 255.0)[..., None]

    # ---- 首尾淡入淡出
    fade = sstep(0.0, 1.10, t) * (1.0 - sstep(DUR - 0.55, DUR, t))
    c = c * fade
    return clip(c, 0.0, 1.0)


# ----------------------------------------------------------------- 单帧渲染
_GRAIN = None


def grain_tile():
    global _GRAIN
    if _GRAIN is None:
        rng = np.random.default_rng(7)
        g = rng.random((2048, 2048), np.float32)
        g = blur(g, 0.9)
        _GRAIN = g
    return _GRAIN


CARDS = [
    Card("A", 660, 470, 42, [1090, 500, 0], (2, 6.5, 0), CUES["cardA_in"], CUES["pdur"], 6.92,
         drift=(880, -30, -560), draw=content_chat, part_keep=0.42),
    Card("B", 400, 200, 38, [752, 292, 230], (4, -10, 0), CUES["cardB_in"], 1.65, CUES["partB"],
         drift=(-640, -400, -520), draw=content_voice),
    Card("C", 440, 250, 40, [652, 800, -120], (-4, -9, 0), CUES["cardC_in"], 1.65, CUES["partC"],
         drift=(-440, 330, -460), draw=content_modes),
]


def render_frame(t):
    cam = camera(t)
    g = gain(t)

    # ---- 极光场（1/2 分辨率）
    hw2, hh2 = W // HALF, H // HALF
    px = (np.arange(hw2, dtype=np.float32)[None, :] + 0.5) * HALF
    py = (np.arange(hh2, dtype=np.float32)[:, None] + 0.5) * HALF
    PX = np.broadcast_to(px, (hh2, hw2))
    PY = np.broadcast_to(py, (hh2, hw2))

    rc_x, rc_y = lens_state(t)["c"]
    k = seg(CUES["drop"] - 0.05, CUES["drop"] + 1.9, t)
    rip = (rc_x, rc_y, 60.0 + 1500.0 * float(eout_sine(k)),
           1.6 * (1.0 - k) ** 1.5 * seg(0.0, 0.035, k))

    col, cov, ring = aurora(PX, PY, t, cam, g, rip)
    col = col + motes(PX, PY, t) * (0.55 + 0.45 * cov[..., None]) * (1.0 - 0.0)
    col = col + np.array([0.50, 0.36, 1.0], np.float32) * (ring * 0.045 * cov)[..., None]

    # ---- 卡片投影（画在光场上）
    O = np.array([960.0 + cam[0], 540.0 + cam[1], -FOCAL + cam[2]], np.float32)
    for c in CARDS:
        st = card_state(c, t, rc_x)
        if st[4] <= 0.01:
            continue
        C, U, V, N = st[0], st[1], st[2], st[3]
        Lx, Ly = plane_local(PX, PY - 34.0, C, U, V, N, O)
        sd = sd_round_box(Lx, Ly, c.w / 2.0, c.h / 2.0, c.r)
        shd = 1.0 - sstep(-46.0, 84.0, sd)
        col = col * (1.0 - (shd * 0.34 * st[4] * (1.0 - st[7]))[..., None])

    scene = resize_f(col, (W, H))

    # ---- 玻璃字标：它活在玻璃「后面」，所以让位的卡片会先磨砂它
    quarter = blur(down4(scene), 8.0)
    draw_glyphs(scene, quarter, t)

    # ---- 玻璃卡片（由远及近，逐张磨砂它背后的东西）
    states = [(c, card_state(c, t, rc_x)) for c in CARDS]
    states.sort(key=lambda s: -s[1][0][2])
    for c, st in states:
        if st[4] <= 0.002:
            continue
        if c.draw is not None:
            if c.tex is None or c.tex_t != t:
                c.tex = np.asarray(c.draw(c, t), np.float32) / 255.0
                c.tex[..., :3] *= c.tex[..., 3:4]
                c.tex_t = t
        quarter = blur(down4(scene), 7.0)
        draw_card(scene, quarter, c, st, cam, t)

    # ---- 液态玻璃透镜
    quarter = blur(down4(scene), 6.0)
    draw_lens(scene, quarter, t, cam)

    return post(scene, t, int(round(t * FPS)), grain_tile())


# ----------------------------------------------------------------- CLI
def save(img, path):
    a = np.clip(img * 255.0 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(a, "RGB").save(path, quality=95)


def cmd_one(t, out):
    t0 = time.time()
    save(render_frame(t), out)
    print("%s  t=%.2fs  %.1fs" % (out, t, time.time() - t0))


def _worker(args):
    i, = args
    t = i / FPS
    save(render_frame(t), os.path.join(ROOT, "frames", "f_%04d.png" % i))
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


def cmd_preview():
    for t in [0.6, 1.9, 3.2, 4.4, 5.2, 6.15, 6.7, 7.6, 8.4, 9.3]:
        cmd_one(t, os.path.join(ROOT, "prev_%.2f.png" % t))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if cmd == "one":
        cmd_one(float(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "prev_one.png")
    elif cmd == "all":
        cmd_all(int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    elif cmd == "range":
        cmd_all(int(sys.argv[4]) if len(sys.argv) > 4 else 3, int(sys.argv[2]), int(sys.argv[3]))
    else:
        cmd_preview()
