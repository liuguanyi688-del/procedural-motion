# -*- coding: utf-8 -*-
"""
12 · 复古 Synthwave  Neon Drive — 80s SYNTHWAVE · VHS
=====================================================
纯 numpy 光线投射 3D 渲染器 + VHS 磁带后期。没有 THREE.js、没有着色器编译器。

    相机沿速度曲线推进 → 每像素投射光线
      → 天空（渐变 + 星场 + 地平线热光）
      → 条纹落日（带子向下滚动，被山挡住）
      → 山脊剪影（脊状噪声 + 霓虹网格）
      → 无限霓虹网格地面（透视 + 脉冲波 + 车的倒影）
      → 3D 物体（棕榈剪影 / 反光柱 / 车）
      → VHS 后期（YIQ 色度延迟 / 行抖动 / 磁带撕裂 / RGB 分离 / 扫描线 / CRT 关机）

    python make_synth.py preview        # 关键帧预览
    python make_synth.py one 6.0 a.png  # 单帧
    python make_synth.py all 3          # 600 帧 → frames/
"""

import os
import sys
import math
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

np.seterr(all="ignore")

W, H = 1920, 1080
FPS = 60
DUR = 10.0
ROOT = os.path.dirname(os.path.abspath(__file__))

FOV = 50.0
FPX = (H / 2) / math.tan(FOV / 2 * math.pi / 180)   # 1158.0
SHIFT = 75.0
HORIZON = H / 2 + SHIFT
HAZE = np.array([1.0, 0.24, 0.55], np.float32)
SUN_D = 1150.0
SUN_RPX = 250.0
SUN_R = SUN_RPX / FPX * SUN_D
MT_D = 830.0          # 山脊距相机的距离
POST_X = 6.25         # 反光柱横向位置
POST_SP = 8.0         # 反光柱间距（米）
PALM_H = 13.5

CUES = dict(
    bpm=100, build=1.8, lane_change=[1.8, 2.25], drop=4.2, outro=9.0,
    osd_play=0.10, track_lock=1.0, mask_open=[1.0, 1.5],
    sun_rise=[1.1, 3.9], tilt_up=[1.0, 2.6], build_ramp=[2.6, 3.85],
    palm_pass=[1.62, 2.22, 2.82, 3.42, 5.1, 6.3, 7.5, 8.7],
    palm_side=[-1, 1, -1, 1, 1, -1, 1, -1],
    tape_rewind=[3.867, 3.933], tape_hold=[3.933, 4.2], slam=4.2,
    car_launch=4.2, car_vanish=4.875,
    glint=[4.95, 5.55], glint_star=5.4, neon_trace=[5.8, 6.6], ignite=6.6,
    tagline=[7.2, 8.1], glint2_star=8.4, glint_end=[9.0, 9.6], end_dolly=[7.2, 9.6],
    glitches=[0.37, 0.63, 1.53, 2.47, 3.23, 6.07, 7.77, 9.37], vslip=3.23,
    stop=9.667, crt_off=[9.833, 9.967], oncoming=dict(pass_t=2.25, x=1.35, v=30, y=0.66, half=0.72),
)


# ----------------------------------------------------------------- 缓动
def clamp(x, a=0.0, b=1.0):
    return np.clip(x, a, b)


def clampf(x, a=0.0, b=1.0):
    return float(min(b, max(a, x)))


def smooth(k):
    k = clamp(k)
    return k * k * (3 - 2 * k)


def smoothf(k):
    k = clampf(k)
    return k * k * (3 - 2 * k)


def eInOutSine(k):
    return -(math.cos(math.pi * clampf(k)) - 1) / 2


def eOutExpo(k):
    k = clampf(k)
    return 1.0 if k >= 1 else 1 - 2 ** (-10 * k)


def eOutCubic(k):
    return 1 - (1 - clampf(k)) ** 3


def eInCubic(k):
    return clampf(k) ** 3


def eInQuart(k):
    return clampf(k) ** 4


def lerp(a, b, k):
    return a + (b - a) * k


def f32(x):
    if isinstance(x, np.ndarray):
        return x if x.dtype == np.float32 else x.astype(np.float32)
    return np.float32(x)


def mix(a, b, x):
    a, b, x = f32(a), f32(b), f32(x)
    return a + (b - a) * x


def sstep(a, b, x):
    t = clamp((x - a) / (b - a))
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------- 相机
def speed(t):
    if t < 1.0:
        return 18 + 4 * t
    if t < 2.0:
        return 22 + 26 * smoothf(t - 1)
    if t < 2.6:
        return 48
    if t < 3.8:
        return 48 + 13 * smoothf((t - 2.6) / 1.2)
    if t < CUES["slam"]:
        return 61 - 35 * smoothf((t - 3.8) / 0.4)
    return 34 + 30 * math.exp(-(t - CUES["slam"]) * 2.4)


_DT = 1.0 / 2400
_ZT = [0.0]
_z = 0.0
for _i in range(int(10.6 / _DT) + 1):
    _t = _i * _DT
    _z -= 0.5 * (speed(_t) + speed(_t + _DT)) * _DT
    _ZT.append(_z)
ZT = np.array(_ZT, np.float32)


def camZ(t):
    f = clampf(t, 0, 10.5) / _DT
    i = int(f)
    k = f - i
    return float(lerp(ZT[i], ZT[i + 1], k))


def scene_time(t):
    """磁带时间重映射：追踪期的 15fps、倒带 2 帧、STOP 后走带减速"""
    fr = int(round(t * FPS))
    if fr < 30:
        return (fr // 2) * 2 / FPS
    r0 = int(round(CUES["tape_rewind"][0] * FPS))
    r1 = int(round(CUES["tape_rewind"][1] * FPS))
    s0 = int(round(CUES["slam"] * FPS))
    if r0 <= fr < r1:
        return (r0 - 1 - (fr - r0)) / FPS
    if r1 <= fr < s0:
        return (fr // 2) * 2 / FPS
    st = int(round(CUES["stop"] * FPS))
    if fr >= st:
        return CUES["stop"] + ((fr // 2) * 2 - st) / FPS * 0.5
    return max(t, CUES["slam"]) if fr >= s0 else t


def camera(t):
    ts = scene_time(t)
    fr = int(round(t * FPS))
    tilt = smoothf((ts - CUES["tilt_up"][0]) / (CUES["tilt_up"][1] - CUES["tilt_up"][0]))
    build = smoothf((ts - CUES["build_ramp"][0]) / (CUES["build_ramp"][1] - CUES["build_ramp"][0]))
    camY = lerp(lerp(2.4, 1.45, tilt), 1.10, build)
    LANE = CUES["lane_change"]
    lkc = clampf((ts - LANE[0] - 0.2) / (LANE[1] - LANE[0] + 0.05))
    ed = CUES["end_dolly"]
    endD = eInOutSine((ts - ed[0]) / (ed[1] - ed[0]))
    rx = -0.30 * (1 - tilt)
    ry = 0.012 * math.sin(ts * 0.4) + 0.011 * endD
    roll = 0.0
    cx = 0.9 * math.sin(ts * 0.55) - 2.5 * eInOutSine(lkc) + 1.0 * endD
    cy = camY + 0.05 * math.sin(ts * 2.1)
    cz = camZ(ts)
    rise = smoothf((ts - CUES["sun_rise"][0]) / (CUES["sun_rise"][1] - CUES["sun_rise"][0]))
    sunPx = lerp(-150, 110, rise) + 16 * eInOutSine((ts - 7.2) / 2.8)
    return dict(ts=ts, fr=fr, cam=(cx, cy, cz), rx=rx, ry=ry, roll=roll,
                tilt=tilt, build=build, rise=rise, sunPx=sunPx, endD=endD)


def car_gap(ts):
    if ts < CUES["slam"]:
        return lerp(15, 9.5, eInOutSine(ts / 2.6)) if ts < 2.6 else lerp(9.5, 7.0, smoothf((ts - 2.6) / 1.2))
    u = ts - CUES["slam"]
    return 7.0 + 8 * u + 260 * u * u


def car_x(ts):
    LANE = CUES["lane_change"]
    lkc = eInOutSine((ts - LANE[0]) / (LANE[1] - LANE[0]))
    s = min(ts, CUES["slam"])
    return 0.35 * math.sin(s * 0.8 + 1.2) - 2.5 * lkc


# ----------------------------------------------------------------- 噪声
def h21(ix, iy):
    x = np.mod(ix * 123.34 + iy * 456.21, 1.0)
    return np.mod(x, 1.0)


def h11(p):
    p = np.mod(p * 0.1031, 1.0)
    p = p * (p + 33.33)
    p = p * (p + p)
    return np.mod(p, 1.0)


def vnoise(px, py, cell):
    x = px / cell
    y = py / cell
    i0 = np.floor(x)
    j0 = np.floor(y)
    fx = x - i0
    fy = y - j0
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = h21(i0, j0)
    b = h21(i0 + 1.0, j0)
    c = h21(i0, j0 + 1.0)
    d = h21(i0 + 1.0, j0 + 1.0)
    top = a + (b - a) * fx
    bot = c + (d - c) * fx
    return top + (bot - top) * fy


def ridged(x, z):
    """脊状噪声：5 个八度的 1-|noise| 叠加"""
    s = np.zeros_like(x)
    a, f = 0.55, 1.0
    for _ in range(5):
        n = vnoise(x * f * 1.0 + 137.0, z * f * 1.0 + 61.0, 1.0) * 2 - 1
        s = s + a * (1 - np.abs(n))
        a *= 0.5
        f *= 2.03
    return s


# ----------------------------------------------------------------- 采样
def sample(img, X, Y):
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


# ----------------------------------------------------------------- 光线场
class Rays:
    """相机只有平移与微小俯仰/偏航，光线场逐帧重建（1920×1080 的 3 个分量）"""

    def __init__(self):
        self.px = (np.arange(W, dtype=np.float32)[None, :] + 0.5)
        self.py = (np.arange(H, dtype=np.float32)[:, None] + 0.5)
        self.u = self.px - 960.0
        self.v = HORIZON - self.py

    def build(self, rx, ry):
        u = np.broadcast_to(self.u, (H, W)).astype(np.float32)
        v = np.broadcast_to(self.v, (H, W)).astype(np.float32)
        z = np.full((H, W), -FPX, np.float32)
        L = np.sqrt(u * u + v * v + FPX * FPX)
        u, v, z = u / L, v / L, z / L
        if abs(rx) > 1e-6:
            cr, sr = math.cos(rx), math.sin(rx)
            v2 = v * cr - z * sr
            z2 = v * sr + z * cr
            v, z = v2, z2
        if abs(ry) > 1e-6:
            cy_, sy_ = math.cos(ry), math.sin(ry)
            u2 = u * cy_ + z * sy_
            z2 = -u * sy_ + z * cy_
            u, z = u2, z2
        self.dx, self.dy, self.dz = u, v, z
        self.fwy = np.abs(np.diff(self.dy, axis=0, prepend=self.dy[:1])) + 1e-6


RAYS = Rays()


# ----------------------------------------------------------------- 天空
def sky_pass(cam, fr):
    d = RAYS
    e = d.dy
    pxa = e / np.maximum(d.fwy, 1e-6)
    c = np.empty((H, W, 3), np.float32)
    c[..., 0] = 0.46
    c[..., 1] = 0.07
    c[..., 2] = 0.40
    c = mix(c, np.array([0.30, 0.05, 0.40], np.float32), sstep(0.015, 0.13, e)[..., None])
    c = mix(c, np.array([0.10, 0.025, 0.24], np.float32), sstep(0.10, 0.28, e)[..., None])
    c = mix(c, np.array([0.022, 0.006, 0.07], np.float32), sstep(0.24, 0.50, e)[..., None])
    upx = np.maximum(pxa, 0.0)
    c = c + HAZE * ((np.exp(-upx / 12.0) * 0.50 + np.exp(-upx / 55.0) * 0.30))[..., None]
    below = (pxa < 0.0)[..., None]
    c = np.where(below, HAZE * 0.45, c)
    c = c + (np.exp(-pxa * pxa / 2.2) * 1.25)[..., None] * np.array([1.0, 0.82, 0.96], np.float32)

    # 星场
    spx = np.arctan2(d.dx, -d.dz) * 70.0
    spy = np.arcsin(np.clip(e, -1, 1)) * 70.0
    i0 = np.floor(spx)
    j0 = np.floor(spy)
    fx = spx - i0 - 0.5
    fy = spy - j0 - 0.5
    h = h21(i0, j0)
    jx = h21(i0 + 7.1, j0) - 0.5
    jy = h21(i0, j0 + 3.7) - 0.5
    fwsx = np.abs(np.diff(spx, axis=1, prepend=spx[:, :1])) + 1e-4
    r = np.hypot(fx - jx * 0.7, fy - jy * 0.7) / fwsx
    tw = 0.65 + 0.35 * np.sin(fr * 0.37 * (1 + h * 3) + h * 40)
    big = (h > 0.994).astype(np.float32)
    star = (h > 0.88) * np.exp(-r * r / np.where(big > 0, np.float32(1.9), np.float32(0.7))) * \
        (0.35 + 0.65 * np.mod(h * 91, 1)) * tw
    frx = np.abs((fx - jx * 0.7) / fwsx)
    fry = np.abs((fy - jy * 0.7) / fwsx)
    star = star + big * (np.exp(-frx * 0.9) * np.exp(-fry * fry * 0.9) +
                         np.exp(-fry * 0.9) * np.exp(-frx * frx * 0.9)) * 0.35 * tw
    star = star * sstep(0.04, 0.16, e)
    c = c + (star * 1.7)[..., None] * np.array([0.95, 0.9, 1.0], np.float32)

    # 流星
    if 7.55 < cam["ts"] < 8.1:
        qx = np.arctan2(d.dx, -d.dz)
        qy = np.arcsin(np.clip(e, -0.999, 0.999))
        sh = (cam["ts"] - 7.55) / 0.55
        A = np.array([-0.62, 0.40], np.float32)
        B = np.array([-0.30, 0.30], np.float32)
        hd = A + (B - A) * sh
        dr = (B - A) / np.linalg.norm(B - A)
        tl = hd - dr * 0.10 * math.sin(math.pi * sh)
        pa = np.stack([qx - tl[0], qy - tl[1]], -1)
        ba = hd - tl
        hh = np.clip((pa[..., 0] * ba[0] + pa[..., 1] * ba[1]) / (ba @ ba), 0, 1)
        dd = np.hypot(pa[..., 0] - ba[0] * hh, pa[..., 1] - ba[1] * hh)
        dd = dd / 1e-4
        along = np.clip((pa[..., 0] * dr[0] + pa[..., 1] * dr[1]) / 0.10, 0, 1)
        c = c + (np.exp(-dd * dd * 0.35) * along * math.sin(math.pi * sh) * 1.2)[..., None] * \
            np.array([0.8, 0.95, 1.0], np.float32)
    return c


# ----------------------------------------------------------------- 落日
def sun_pass(c, cam):
    ts = cam["ts"]
    cx, cy, cz = cam["cam"]
    sunY = cy + cam["sunPx"] / FPX * SUN_D
    sunX = cx * 0.96
    sunZ = cz - SUN_D
    d = RAYS
    with np.errstate(divide="ignore", invalid="ignore"):
        tt = (sunZ - cz) / d.dz
    valid = (tt > 1.0) & (d.dz < -1e-6)
    px = cx + d.dx * tt
    py = cy + d.dy * tt
    vx = (px - sunX) / SUN_R
    vy = (py - sunY) / SUN_R
    r = np.hypot(vx, vy)
    aa = 1.0 / SUN_R * 6.0
    disc = 1.0 - sstep(1.0 - aa, 1.0 + aa, r)
    col = np.empty((H, W, 3), np.float32)
    col[..., 0] = 1.0
    col[..., 1] = 0.24
    col[..., 2] = 0.56
    col = mix(col, np.array([1.0, 0.40, 0.28], np.float32), sstep(-1.0, -0.25, vy)[..., None])
    col = mix(col, np.array([1.0, 0.62, 0.22], np.float32), sstep(-0.3, 0.25, vy)[..., None])
    col = mix(col, np.array([1.0, 0.86, 0.36], np.float32), sstep(0.15, 0.65, vy)[..., None])
    col = mix(col, np.array([1.0, 0.96, 0.62], np.float32), sstep(0.6, 1.0, vy)[..., None])
    w = 0.38 - vy
    ph = w * 8.5 - ts * 0.55
    gapF = np.clip(w * 0.42, 0, 0.62) * (w >= 0)
    fp = np.mod(ph, 1.0)
    afw = 1e-3 * 1.2
    gap = sstep(gapF + afw, gapF - afw, fp) * (gapF > 0.001)
    a = disc * (1.0 - gap)
    halo = np.array([1.0, 0.28, 0.52], np.float32) * \
        (np.exp(-np.maximum(r - 1.0, 0) * 3.2) * 0.30 + np.exp(-np.maximum(r - 1.0, 0) * 0.9) * 0.10)[..., None] * \
        (1.0 - disc * (1.0 - gap))[..., None]
    m = valid & (a > 0.001)
    src = col * a[..., None] + halo
    c = np.where(m[..., None], c * (1.0 - a[..., None]) + src, c)
    return c


# ----------------------------------------------------------------- 山脊
_MT_X = np.linspace(-950, 950, 480, dtype=np.float32)
_MT_Z = np.linspace(-190, 190, 40, dtype=np.float32)


def mountain_profile(cam):
    """在世界坐标上采样山脊高度场"""
    cx, cy, cz = cam["cam"]
    mx = cx * 0.9 + _MT_X[None, :]
    mz = cz - MT_D + _MT_Z[:, None]
    ax = np.abs(_MT_X)[None, :]
    env = smooth((ax - 150) / 380.0) * (0.45 + 0.55 * smooth((-_MT_Z[:, None] + 190) / 380.0))
    h = env * (18 + 150 * np.power(np.maximum(ridged(mx * 0.0042 + 3.1, mz * 0.006), 0), 1.6) * 0.75)
    return np.maximum(0, h)


def mountain_pass(c, cam):
    """把山脊投影到屏幕：逐列求剪影顶（按 sy 排序取每列首个），再填剪影 + 霓虹网格"""
    cx, cy, cz = cam["cam"]
    h = mountain_profile(cam)                        # (nz, nx)
    Xw = cx * 0.9 + _MT_X[None, :]
    Zw = cz - MT_D + _MT_Z[:, None]
    dz = np.maximum(cz - Zw, 1.0)
    sx = 960.0 + FPX * (Xw - cx) / dz
    sy = HORIZON - FPX * (h - cy) / dz
    u = np.broadcast_to((_MT_X[None, :] / 1900.0 + 0.5), h.shape)
    v = np.broadcast_to((_MT_Z[:, None] / 380.0 + 0.5), h.shape)
    cols = np.round(sx).astype(np.int32)
    valid = (cols >= 0) & (cols < W) & (h > 0.5)
    fc = cols[valid]
    fs = sy[valid]
    fu = u[valid]
    fv = v[valid]
    order = np.argsort(fs)                           # 由高到低（sy 小 = 高）
    uc, first = np.unique(fc[order], return_index=True)
    sel = order[first]
    top = np.full(W, H + 10, np.float32)
    topu = np.zeros(W, np.float32)
    topv = np.zeros(W, np.float32)
    top[uc] = fs[sel]
    topu[uc] = fu[sel]
    topv[uc] = fv[sel]

    yy = np.arange(H, dtype=np.float32)[:, None]
    inside = (yy >= top[None, :]) & (yy < HORIZON)
    # 网格：竖线用真实 u，横线用"远平面"近似把屏幕 y 映到 v
    gx = np.broadcast_to(topu[None, :] * 48.0, (H, W))
    vy = 0.5 + np.maximum(HORIZON - yy, 0.0) / FPX * (MT_D / 380.0)
    gy = np.broadcast_to(vy * 12.0, (H, W))
    fwx = 2.4
    fwy = 1.8
    dx = np.abs(np.mod(gx - 0.5, 1.0) - 0.5) / fwx
    dy = np.abs(np.mod(gy - 0.5, 1.0) - 0.5) / fwy
    gd = gx + gy
    dd = np.abs(np.mod(gd - 0.5, 1.0) - 0.5) / (fwx + fwy)
    m = np.minimum(np.minimum(dx, dy), dd)
    core = 1.0 - sstep(0.25, 1.1, m)
    glow = np.exp(-m / 2.2)
    hh = np.clip((HORIZON - yy) / 190.0, 0.0, 1.0)[..., None]
    fill = mix(np.array([0.05, 0.0, 0.12], np.float32), np.array([0.10, 0.02, 0.20], np.float32), hh)
    wire = mix(np.array([1.0, 0.18, 0.80], np.float32), np.array([0.22, 0.88, 1.0], np.float32),
               sstep(0.12, 0.7, hh))
    mcol = fill + wire * (core * 0.85 + glow * 0.22)[..., None]
    hgt = np.maximum(HORIZON - yy, 0.0)
    mcol = mix(mcol, HAZE * 0.55, (np.exp(-hgt / 9.0) * 0.62)[..., None])
    mcol = mcol + (np.exp(-hgt * hgt / 2.2) * 1.25)[..., None] * np.array([1.0, 0.82, 0.96], np.float32)
    c = np.where(inside[..., None], mcol, c)
    return c


# ----------------------------------------------------------------- 地面网格
def floor_pass(c, cam):
    cx, cy, cz = cam["cam"]
    d = RAYS
    y0 = max(0, int(HORIZON) - 2)
    sl = slice(y0, H)

    def hit(dx, dy, dz):
        with np.errstate(divide="ignore", invalid="ignore"):
            t = -cy / dy
        ok = dy < -1e-6
        t = np.where(ok, t, 1e6)
        return cx + dx * t, cz + dz * t

    dx = d.dx[sl]
    dy = d.dy[sl]
    dz = d.dz[sl]
    X, Z = hit(dx, dy, dz)
    p = np.stack([X / 2.5 + 0.5, Z / 5.0], -1)
    # 数值求导：取 px+1 / py+1 的光线
    dxp = np.concatenate([d.dx[sl][:, 1:], d.dx[sl][:, -1:]], axis=1)
    dyp = np.concatenate([d.dy[sl][:, 1:], d.dy[sl][:, -1:]], axis=1)
    dzp = np.concatenate([d.dz[sl][:, 1:], d.dz[sl][:, -1:]], axis=1)
    X2, Z2 = hit(dxp, dyp, dzp)
    p2 = np.stack([X2 / 2.5 + 0.5, Z2 / 5.0], -1)
    dxq = np.concatenate([d.dx[sl][1:, :], d.dx[sl][-1:, :]], axis=0)
    dyq = np.concatenate([d.dy[sl][1:, :], d.dy[sl][-1:, :]], axis=0)
    dzq = np.concatenate([d.dz[sl][1:, :], d.dz[sl][-1:, :]], axis=0)
    X3, Z3 = hit(dxq, dyq, dzq)
    p3 = np.stack([X3 / 2.5 + 0.5, Z3 / 5.0], -1)

    fw = np.maximum(np.maximum(np.abs(p2 - p), np.abs(p3 - p)), 1e-5)
    dd = np.abs(np.mod(p - 0.5, 1.0) - 0.5) / fw
    fade = 1.0 - sstep(0.10, 0.42, fw)
    core = (1.0 - sstep(0.3, 1.35, dd)) * fade
    glow = (np.exp(-dd / 3.4) + np.exp(-dd / 15.0) * 0.16) * fade
    line = np.maximum(core[..., 0], core[..., 1])
    gl = np.maximum(glow[..., 0], glow[..., 1])
    dist = np.hypot(X - cx, Z - cz)
    lc = np.array([1.0, 0.16, 0.82], np.float32)
    base = mix(np.array([0.018, 0.0, 0.05], np.float32), np.array([0.09, 0.01, 0.15], np.float32),
               sstep(30.0, 700.0, dist)[..., None])
    col = base + lc * (gl * 0.50)[..., None] + \
        mix(lc, np.array([1.0, 0.85, 0.97], np.float32), 0.5) * line[..., None]
    far = (1.0 - fade) * np.minimum(1.0, fw * 3.2)
    col = col + lc * np.minimum((far[..., 0] * 0.5 + far[..., 1]) * 0.30, 0.22)[..., None]
    fog = sstep(150.0, 950.0, dist)
    col = mix(col, HAZE * 0.55, (fog * 0.70)[..., None])
    pxb = np.maximum((np.arange(y0, H, dtype=np.float32)[:, None] + 0.5) - HORIZON, 0.0)
    col = mix(col, np.array([0.102, 0.024, 0.188], np.float32),
              ((sstep(3.0, 8.0, pxb) - sstep(18.0, 30.0, pxb)) * 0.85)[..., None])
    az = np.arctan2(dx, -dz)
    rip = 0.55 + 0.45 * sstep(-0.3, 0.7, np.sin(pxb * 0.42 - cam["ts"] * 7.0))
    refl = np.exp(-az * az / 0.006) * np.exp(-pxb / 150.0) * rip
    col = col + (refl * 0.62)[..., None] * np.array([1.0, 0.42, 0.35], np.float32)
    col = col + (np.exp(-pxb * pxb / 2.2) * 1.25)[..., None] * np.array([1.0, 0.82, 0.96], np.float32)
    col = col + HAZE * (np.exp(-pxb / 3.2) * 0.40 + np.exp(-pxb / 60.0) * 0.05)[..., None]
    c[sl] = col
    return c


# ----------------------------------------------------------------- 3D 物体光栅化
def project(pts, cam):
    cx, cy, cz = cam["cam"]
    rx, ry = cam["rx"], cam["ry"]
    X = pts[:, 0] - cx
    Y = pts[:, 1] - cy
    Z = pts[:, 2] - cz
    if abs(rx) > 1e-6:
        cr, sr = math.cos(rx), math.sin(rx)
        Y, Z = Y * cr - Z * sr, Y * sr + Z * cr
    if abs(ry) > 1e-6:
        cyy, syy = math.cos(ry), math.sin(ry)
        X, Z = X * cyy + Z * syy, -X * syy + Z * cyy
    dz = np.maximum(-Z, 0.05)
    sx = 960.0 + FPX * X / dz
    sy = HORIZON - FPX * Y / dz
    return sx, sy, dz


class Zbuf:
    def __init__(self):
        self.z = np.full((H, W), np.inf, np.float32)

    def quad(self, img, pts, col, emissive=0.0, alpha=1.0, additive=False):
        sx, sy, dz = project(np.asarray(pts, np.float32), CURCAM)
        if np.any(dz <= 0.05):
            return
        x0 = int(max(0, np.floor(sx.min())))
        x1 = int(min(W, np.ceil(sx.max()) + 1))
        y0 = int(max(0, np.floor(sy.min())))
        y1 = int(min(H, np.ceil(sy.max()) + 1))
        if x1 <= x0 or y1 <= y0:
            return
        xs = np.arange(x0, x1, dtype=np.float32)[None, :]
        ys = np.arange(y0, y1, dtype=np.float32)[:, None]
        XS = np.broadcast_to(xs, (y1 - y0, x1 - x0))
        YS = np.broadcast_to(ys, (y1 - y0, x1 - x0))
        inside = np.zeros((y1 - y0, x1 - x0), bool)
        dep = np.full((y1 - y0, x1 - x0), np.inf, np.float32)
        for tri in ((0, 1, 2), (0, 2, 3)):
            ax, ay = sx[tri[0]], sy[tri[0]]
            bx, by = sx[tri[1]], sy[tri[1]]
            cx_, cy_ = sx[tri[2]], sy[tri[2]]
            den = (by - cy_) * (ax - cx_) + (cx_ - bx) * (ay - cy_)
            if abs(den) < 1e-9:
                continue
            l1 = ((by - cy_) * (XS - cx_) + (cx_ - bx) * (YS - cy_)) / den
            l2 = ((cy_ - ay) * (XS - cx_) + (ax - cx_) * (YS - cy_)) / den
            l3 = 1 - l1 - l2
            m = (l1 >= -0.002) & (l2 >= -0.002) & (l3 >= -0.002)
            d = l1 * dz[tri[0]] + l2 * dz[tri[1]] + l3 * dz[tri[2]]
            inside |= m
            dep = np.where(m & (d < dep), d, dep)
        sub_z = self.z[y0:y1, x0:x1]
        take = inside & (dep < sub_z)
        if not take.any():
            return
        sub = img[y0:y1, x0:x1]
        colr = np.asarray(col, np.float32)
        src = colr[None, None, :] if emissive <= 0 else (colr * emissive)[None, None, :]
        if additive:
            blended = sub + src * alpha
        else:
            blended = sub * (1 - alpha) + src * alpha
        img[y0:y1, x0:x1] = np.where(take[..., None], blended, sub)
        sub_z[take] = dep[take]


# ----------------------------------------------------------------- 棕榈 / 反光柱 / 车
_PALM = {}


def palm_sprite(seed, rim_dir):
    """程序生成棕榈剪影：品红描边 + 近黑叶体"""
    key = (seed, rim_dir)
    if key in _PALM:
        return _PALM[key]
    PW, PH = 300, 620
    img = Image.new("RGBA", (PW, PH), (0, 0, 0, 0))
    rng = np.random.default_rng(seed)

    def trunk_x(u):
        return 140 + 30 * math.sin(u * 0.95)

    for dx, fill in ((rim_dir * 4.0, (255, 60, 185, 255)), (0.0, (10, 1, 24, 255))):
        d = ImageDraw.Draw(img)
        # 树干：底部粗、顶部细的多边形
        left, right = [], []
        for i in range(14):
            u = i / 13.0
            x = trunk_x(u)
            y = PH * (1.0 - u * 0.92)
            w = 20 - 11 * u
            left.append((x - w / 2 + dx, y))
            right.append((x + w / 2 + dx, y))
        d.polygon(left + right[::-1], fill=fill)
        # 叶冠：9 片下垂的叶
        cx0 = trunk_x(1.0) + dx
        cy0 = PH * 0.08
        for k in range(9):
            th = math.radians(172 - 164 * k / 8.0)
            L = PW * (0.46 + 0.16 * float(rng.random()))
            seg = []
            for i in range(12):
                u = i / 11.0
                seg.append((cx0 + math.cos(th) * L * u,
                            cy0 - math.sin(th) * L * u + (u * u) * L * 0.62))
            d.line(seg, fill=fill, width=9, joint="curve")
        # 椰果
        for k in range(3):
            a = -0.6 + k * 0.6
            d.ellipse([cx0 + math.cos(a) * 16 - 6, cy0 + math.sin(a) * 16 - 6,
                       cx0 + math.cos(a) * 16 + 6, cy0 + math.sin(a) * 16 + 6], fill=fill)
    _PALM[key] = img
    return img


def paste_billboard(img, zbuf, cam, tex, wx, wy, wz, hworld):
    """把一张带 alpha 的贴图当广告牌贴到世界坐标 (wx,wy,wz)"""
    cx, cy, cz = cam["cam"]
    rx, ry = cam["rx"], cam["ry"]
    hw = hworld * tex.width / tex.height
    P = np.array([[wx - hw / 2, wy, wz], [wx + hw / 2, wy, wz],
                  [wx + hw / 2, wy + hworld, wz], [wx - hw / 2, wy + hworld, wz]], np.float32)
    sx, sy, dz = project(P, cam)
    if np.any(dz <= 0.5) or sy.max() < 0 or sy.min() > H or sx.max() < 0 or sx.min() > W:
        return
    x0 = int(max(0, np.floor(sx.min())))
    x1 = int(min(W, np.ceil(sx.max()) + 1))
    y0 = int(max(0, np.floor(sy.min())))
    y1 = int(min(H, np.ceil(sy.max()) + 1))
    if x1 <= x0 or y1 <= y0:
        return
    # 用四角做双线性映射（广告牌正对相机，投影是仿射的）
    xs = np.arange(x0, x1, dtype=np.float32)[None, :]
    ys = np.arange(y0, y1, dtype=np.float32)[:, None]
    XS = np.broadcast_to(xs, (y1 - y0, x1 - x0))
    YS = np.broadcast_to(ys, (y1 - y0, x1 - x0))
    xmin, xmax = sx.min(), sx.max()
    ymin, ymax = sy.min(), sy.max()
    u = (XS - xmin) / max(xmax - xmin, 1e-3) * (tex.width - 1)
    v = (YS - ymin) / max(ymax - ymin, 1e-3) * (tex.height - 1)
    t = np.asarray(tex, np.float32) / 255.0
    rgba = sample(t, u, v)
    a = rgba[..., 3]
    if a.max() <= 0.01:
        return
    sub_z = zbuf.z[y0:y1, x0:x1]
    sub = img[y0:y1, x0:x1]
    src = rgba[..., :3]
    blended = sub * (1 - a[..., None]) + src * a[..., None]
    m = a > 0.004
    img[y0:y1, x0:x1] = np.where(m[..., None], blended, sub)
    sub_z[m] = dz.mean()


def draw_posts(img, zbuf, cam):
    """路侧反光柱：柱子 + 发光帽"""
    cx, cy, cz = cam["cam"]
    z0 = cz - 3.0
    n = int((1150.0) / POST_SP)
    for k in range(n):
        z = z0 - k * POST_SP
        if z > cz or cz - z > 900:
            continue
        for sd in (-1, 1):
            x = sd * POST_X
            # 柱身
            zbuf.quad(img, [[x - 0.045, 0.0, z - 0.045], [x + 0.045, 0.0, z - 0.045],
                            [x + 0.045, 0.86, z - 0.045], [x - 0.045, 0.86, z - 0.045]],
                      np.array([0.03, 0.0, 0.06], np.float32))
            # 发光帽
            e = max(0.15, 1.0 - (cz - z) / 700.0)
            zbuf.quad(img, [[x - 0.07, 0.86, z - 0.07], [x + 0.07, 0.86, z - 0.07],
                            [x + 0.07, 1.06, z - 0.07], [x - 0.07, 1.06, z - 0.07]],
                      np.array([1.0, 0.55, 0.20], np.float32), emissive=e * 2.4)


def draw_car(img, zbuf, cam):
    """80 年代跑车：低多边形楔形 + 尾灯 + 路面红色倒影"""
    ts = cam["ts"]
    if ts >= CUES["car_vanish"]:
        return
    cx, cy, cz = cam["cam"]
    g = car_gap(ts)
    if g > 300:
        return
    cxx = car_x(ts)
    czz = cz - g
    i = clampf((ts - CUES["car_vanish"] + 0.40) / 0.40)
    fade = 1.0 - i
    body = np.array([0.075, 0.028, 0.125], np.float32)
    dark = np.array([0.022, 0.009, 0.04], np.float32)
    glass = np.array([0.030, 0.014, 0.062], np.float32)
    hw = 0.92
    zr, zf = czz + 2.10, czz - 2.30        # 尾 / 头
    y0, y1 = 0.26, 0.80
    # 车尾面
    zbuf.quad(img, [[cxx - hw, y0, zr], [cxx + hw, y0, zr], [cxx + hw, y1, zr], [cxx - hw, y1, zr]], body)
    # 车顶
    zbuf.quad(img, [[cxx - hw, y1, zf], [cxx + hw, y1, zf], [cxx + hw, y1, zr], [cxx - hw, y1, zr]], body)
    # 两侧
    zbuf.quad(img, [[cxx - hw, y0, zf], [cxx - hw, y0, zr], [cxx - hw, y1, zr], [cxx - hw, y1, zf]], dark)
    zbuf.quad(img, [[cxx + hw, y0, zf], [cxx + hw, y0, zr], [cxx + hw, y1, zr], [cxx + hw, y1, zf]], dark)
    # 座舱（后窗 + 顶）
    zbuf.quad(img, [[cxx - hw * 0.80, y1, czz + 0.35], [cxx + hw * 0.80, y1, czz + 0.35],
                    [cxx + hw * 0.74, y1 + 0.30, czz - 0.45], [cxx - hw * 0.74, y1 + 0.30, czz - 0.45]], glass)
    zbuf.quad(img, [[cxx - hw * 0.74, y1 + 0.30, czz - 0.45], [cxx + hw * 0.74, y1 + 0.30, czz - 0.45],
                    [cxx + hw * 0.76, y1 + 0.26, czz - 1.25], [cxx - hw * 0.76, y1 + 0.26, czz - 1.25]], body)
    # 尾灯：两条宽横条
    for sd in (-1, 1):
        x0 = cxx + sd * 0.44 - 0.34
        zbuf.quad(img, [[x0, 0.55, zr + 0.012], [x0 + 0.68, 0.55, zr + 0.012],
                        [x0 + 0.68, 0.70, zr + 0.012], [x0, 0.70, zr + 0.012]],
                  np.array([1.0, 0.10, 0.16], np.float32), emissive=2.8)
    # 保险杠
    zbuf.quad(img, [[cxx - hw, 0.30, zr + 0.006], [cxx + hw, 0.30, zr + 0.006],
                    [cxx + hw, 0.44, zr + 0.006], [cxx - hw, 0.44, zr + 0.006]], dark)
    # 车轮
    for sd in (-1, 1):
        zbuf.quad(img, [[cxx + sd * hw - 0.06, 0.0, czz - 1.35], [cxx + sd * hw + 0.06, 0.0, czz - 1.35],
                        [cxx + sd * hw + 0.06, 0.30, czz - 1.35], [cxx + sd * hw - 0.06, 0.30, czz - 1.35]], dark)
        zbuf.quad(img, [[cxx + sd * hw - 0.06, 0.0, czz + 1.35], [cxx + sd * hw + 0.06, 0.0, czz + 1.35],
                        [cxx + sd * hw + 0.06, 0.30, czz + 1.35], [cxx + sd * hw - 0.06, 0.30, czz + 1.35]], dark)
    # 路面上被尾灯照出的红色倒影（加性）
    gl = max(0.0, 1.0 - g / 140.0) * fade
    if gl > 0.01:
        zbuf.quad(img, [[cxx - 1.5, 0.02, czz + 2.2], [cxx + 1.5, 0.02, czz + 2.2],
                        [cxx + 1.5, 0.02, czz + 11.0], [cxx - 1.5, 0.02, czz + 11.0]],
                  np.array([0.55, 0.045, 0.10], np.float32), alpha=0.55 * gl, additive=True)
    return gl


# ----------------------------------------------------------------- VHS 后期
# CRT 关机逐帧表（照参考的 30fps 表映射到 60fps）：[uCrtX, uCrtY, 热线强度, 蓝白辉光]
CRT_TABLE = {
    590: (1.0, 0.30, 0.25, 0.0), 591: (1.0, 0.30, 0.25, 0.0),
    592: (1.0, 0.0019, 1.0, 0.030), 593: (1.0, 0.0019, 1.0, 0.030),
    594: (0.26, 0.0019, 1.1, 0.022), 595: (0.26, 0.0019, 1.1, 0.022),
    596: (0.0073, 0.013, 1.3, 0.036), 597: (0.0073, 0.013, 1.3, 0.036),
    598: (0.0055, 0.010, 0.35, 0.012), 599: (0.0055, 0.010, 0.35, 0.012),
}


def to_yiq(c):
    y = c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114
    i = c[..., 0] * 0.596 - c[..., 1] * 0.274 - c[..., 2] * 0.322
    q = c[..., 0] * 0.211 - c[..., 1] * 0.523 + c[..., 2] * 0.312
    return y, i, q


def to_rgb(y, i, q):
    r = y + 0.956 * i + 0.621 * q
    g = y - 0.272 * i - 0.647 * q
    b = y - 1.106 * i + 1.703 * q
    return np.stack([r, g, b], -1)


def vhs_pass(img, t, fr, cam):
    ts = cam["ts"]
    PX = (np.arange(W, dtype=np.float32)[None, :] + 0.5)
    PY = (np.arange(H, dtype=np.float32)[:, None] + 0.5)
    PXb = np.broadcast_to(PX, (H, W))
    PYb = np.broadcast_to(PY, (H, W))
    # ---- 各通道状态
    uTrack = (0.75 + 0.25 * math.sin(t * 9)) if t < 1 else (
        (0.3 + 0.5 * smoothf((t - CUES["stop"]) / 0.17)) if fr >= int(round(CUES["stop"] * FPS)) else 0.0)
    uStatic = (clampf(0.42 - 0.30 * t + 0.12 * (h11(np.float32(fr + 500)) - 0.5))
               if t < 1 else (0.06 if fr >= int(round(CUES["stop"] * FPS)) + 2 else 0.0))
    glv, gseed = 0.0, 0.0
    for gt in CUES["glitches"]:
        g0 = int(round(gt * FPS))
        if g0 <= fr < g0 + 2:
            glv = 1.0
            gseed = gt * 13.7 + fr
    uSplit = 1.0 if t < 1.2 else (1 - smoothf((t - 1.2) / 0.3) if t < 1.5 else
                                  (1.0 if fr >= int(round(CUES["stop"] * FPS)) else 0.0))
    uVSlip = 12.0 if fr == int(round(CUES["vslip"] * FPS)) else (
        -12.0 if fr == int(round(CUES["stop"] * FPS)) else 0.0)
    uDim = lerp(1.0, 0.5, smoothf((t - 3.9) / 0.2)) if (
        int(round(CUES["tape_rewind"][0] * FPS)) + 1 <= fr < int(round(CUES["slam"] * FPS))) else 1.0
    uShakeY = 0.0
    if fr >= int(round(CUES["slam"] * FPS)):
        uS = fr - int(round(CUES["slam"] * FPS))
        uShakeY = 26 * math.exp(-uS * 5)
    # ---- CRT 关机（照参考的逐帧表：光栅先压成横线，再收成点）
    uCrtX, uCrtY, uCrtG, uCrtA = CRT_TABLE.get(fr, (1.0, 1.0, 0.0, 0.0))
    uCrtX = max(uCrtX, 0.0005)
    uCrtY = max(uCrtY, 0.0006)

    ccx, ccy = 960.0, 540.0
    px = (PXb - ccx) / uCrtX + ccx
    py = (PYb - ccy) / uCrtY + ccy
    inside = ((1 - sstep(-1, 1, np.abs(PYb - ccy) - 540.0 * uCrtY - 1)) *
              (1 - sstep(-1, 1, np.abs(PXb - ccx) - 960.0 * uCrtX - 1)))
    px = px
    py = py + uVSlip
    vuvx = px / W
    vuvy = py / H
    yTop = H - py
    ln = np.floor(yTop)
    wob = (vnoise(yTop * 0.03 + fr * 0.9, 0.0, 1.0) - 0.5) * (1.1 + 12.0 * uTrack)
    wob = wob + (vnoise(yTop * 0.45 + fr * 7.3, 0.0, 1.0) - 0.5) * (0.35 + 2.5 * uTrack)
    bandC = 1.0 - (np.mod(fr * 0.023 + 0.18, 1.0))
    band = sstep(0.075, 0.0, np.abs(vuvy - bandC)) * uTrack
    wob = wob + band * (h21(ln * 0.5, np.float32(fr)) - 0.5) * 70.0
    gh = 6.0 + 14.0 * float(h11(np.float32(gseed * 1.7 + 0.3)))
    gRow = np.floor((yTop + float(h11(np.float32(gseed))) * 80.0) / gh)
    gOn = glv * (h21(gRow, np.float32(gseed)) > 0.82)
    sgn = np.where(h21(gRow, np.float32(gseed + 5)) < 0.5, np.float32(-1.0), np.float32(1.0))
    wob = wob + gOn * sgn * (8.0 + 32.0 * h21(gRow, np.float32(gseed + 3)))
    hs = 1.0 - sstep(5.0, 17.0, py)
    wob = wob + hs * (16.0 + 24.0 * h21(ln, np.float32(fr)))
    uvx = vuvx + (wob) / W
    uvy = vuvy + uShakeY / H

    c0 = sample(img, uvx * W - 0.5, uvy * H - 0.5)
    Y = to_yiq(c0)[0] * 0.6 + 0.2 * (to_yiq(sample(img, uvx * W - 0.5 + 1, uvy * H - 0.5))[0] +
                                     to_yiq(sample(img, uvx * W - 0.5 - 1, uvy * H - 0.5))[0])
    lag = 1.0 + gOn * 3.0
    iq = np.zeros((H, W, 2), np.float32)
    ws = 0.0
    for i in range(5):
        w = math.exp(-i * 0.55)
        s = sample(img, uvx * W - 0.5 - (i * 2.6 + lag), uvy * H - 0.5)
        yq = to_yiq(s)
        iq = iq + np.stack([yq[1], yq[2]], -1) * w
        ws += w
    iq = iq / ws
    col = to_rgb(Y, iq[..., 0] * 1.1, iq[..., 1] * 1.1)
    spx = mix(1.2, 2.2, np.maximum(uSplit, gOn))
    rr = sample(img, uvx * W - 0.5 + spx, uvy * H - 0.5)[..., 0]
    bb = sample(img, uvx * W - 0.5 - spx, uvy * H - 0.5)[..., 2]
    col[..., 0] = mix(col[..., 0], rr, 0.6)
    col[..., 2] = mix(col[..., 2], bb, 0.6)
    rs = np.zeros((H, W), np.float32)
    rw = 0.0
    for i in range(1, 5):
        w = math.exp(-i * 0.55)
        rs = rs + sample(img, uvx * W - 0.5 - (i * 1.6 + spx), uvy * H - 0.5)[..., 0] * w
        rw += w
    col[..., 0] = np.maximum(col[..., 0], rs / rw * 0.82)
    sn = h21(np.floor(px * 0.5) + fr * 37.0, ln * 1.3 + fr * 17.0)
    col = col * (1.0 - uStatic) + (sn * 0.9)[..., None] * uStatic
    col = col + (band * sn * sn * 0.55)[..., None]
    sline = (h21(ln, np.float32(fr * 3.1)) > (0.992 - band * 0.25 - uTrack * 0.02)).astype(np.float32)
    col = col + (sline * sstep(0.55, 0.95, vnoise(px / 70.0 + ln * 1.7 + fr * 3.0, 0.0, 1.0)) *
                 (0.12 + 0.55 * uTrack))[..., None] * np.array([0.9, 0.95, 1.0], np.float32)
    col = col * (1.0 - (hs * 0.55)[..., None]) + (h21(px + fr, ln) * 0.55)[..., None] * (hs * 0.55)[..., None]
    col = col * uDim
    col = col * np.where(np.mod(yTop, 3.0) < 1.0, np.float32(0.88), np.float32(1.0))[..., None]
    col = col + ((h21(px * 1.37 + fr * 13.1, py * 0.91 + fr * 7.7) - 0.5) * 0.05)[..., None]
    qx = vuvx - 0.5
    qy = vuvy - 0.5
    col = col * (1.0 - (qx * qx * 0.95 + qy * qy * 1.15) * 0.62)[..., None]
    # CRT 关机：压扁 + 热线 + 蓝白辉光
    col = col * (inside * (1.0 + (1.0 - uCrtY) * 1.4) * (1.0 if uCrtX > 0.02 else 0.0))[..., None]
    lx = np.maximum(np.abs(PXb - 960.0) - 960.0 * uCrtX, 0.0)
    ly = np.maximum(np.abs(PYb - 540.0) - 540.0 * uCrtY, 0.0)
    col = col + (uCrtG * np.exp(-ly * ly / 1.1) * np.exp(-lx * lx / 5.0))[..., None] * \
        np.array([1.0, 0.92, 0.98], np.float32)
    col = col + (uCrtA * 10.0 * np.exp(-np.hypot(lx, ly * 1.6) / 60.0))[..., None] * \
        np.array([0.72, 0.84, 1.0], np.float32)
    return np.clip(col, 0.0, 1.0)


# ----------------------------------------------------------------- 叠加层
def draw_osd(img, t, cam):
    """VHS 播放指示：SP ▶ 0:00:03"""
    if t < CUES["osd_play"]:
        return img
    fr = cam["fr"]
    out = Image.fromarray(np.clip(img * 255, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(out)
    f = F("consola.ttf", 26)
    f2 = F("consolab.ttf", 26)
    sec = min(9.999, max(0.0, t - 0.0))
    d.text((1330, 972), "SP", font=f2, fill=(228, 232, 236))
    d.polygon([(1396, 972), (1396, 994), (1416, 983)], fill=(228, 232, 236))
    d.text((1430, 972), "0:00:%02d" % int(sec), font=f2, fill=(228, 232, 236))
    if t < 2.6:
        d.text((1330, 1006), "TRACKING", font=f, fill=(190, 196, 200))
    return np.asarray(out, np.float32) / 255.0


FONTS = {}


def F(name, size):
    key = (name, size)
    if key not in FONTS:
        FONTS[key] = ImageFont.truetype("C:/Windows/Fonts/" + name, size)
    return FONTS[key]


# ----------------------------------------------------------------- 单帧
CURCAM = None


def render_frame(t):
    global CURCAM
    cam = camera(t)
    CURCAM = cam
    RAYS.build(cam["rx"], cam["ry"])
    c = sky_pass(cam, cam["fr"])
    c = sun_pass(c, cam)
    c = mountain_pass(c, cam)
    c = floor_pass(c, cam)

    # 3D 物体：由远及近
    zbuf = Zbuf()
    ts = cam["ts"]
    cx, cy, cz = cam["cam"]
    objs = []
    for i, (tp, sd) in enumerate(zip(CUES["palm_pass"], CUES["palm_side"])):
        late = tp > 4.5
        hx = float(h11(np.float32(i + 3)))
        px_ = sd * ((22 + 3 * hx) if late else (8.2 + 1.6 * hx))
        pz = camZ(tp + 0.22)
        if cz - pz > 1500 or cz - pz < -50:
            continue
        objs.append((abs(pz - cz), px_, pz, sd))
    objs.sort(key=lambda o: -o[0])
    for dist, px_, pz, sd in objs:
        tex = palm_sprite(11 if sd >= 0 else 23, 1)
        paste_billboard(c, zbuf, cam, tex, px_, 0.0, pz, PALM_H)
    draw_posts(c, zbuf, cam)
    draw_car(c, zbuf, cam)

    c = vhs_pass(c, t, cam["fr"], cam)
    c = draw_osd(c, t, cam)
    return c


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
        for t in [0.4, 1.4, 2.4, 3.4, 4.25, 5.0, 6.0, 6.8, 7.6, 8.6, 9.3, 9.9]:
            cmd_one(t, os.path.join(ROOT, "prev_%.2f.png" % t))
