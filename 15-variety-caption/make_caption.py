# -*- coding: utf-8 -*-
"""
15 · 综艺花字 Variety Captions — 喵呜日记 EP07
================================================
1080×1920 竖屏。这一版没有 3D、没有着色器，全部技术都压在一件事上：
**一个字怎么叠成一块"综艺花字"**。

同一段文字画五遍，从粗到细、从下到上：
    挤出层 ×2（往下偏移）→ 外描边 → 白描边 → 渐变填充 → 顶部高光
再加上逐字独立相位的弹簧入场、波浪式抖动、呼吸缩放——
情绪就是这么被"放大"的。

    python make_caption.py preview         # 关键帧预览
    python make_caption.py one 1.2 a.png   # 单帧
    python make_caption.py all 4           # 600 帧 → frames/
"""

import os
import sys
import math
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

np.seterr(all="ignore")

# ----------------------------------------------------------------- 规格
W, H = 1080, 1920
FPS = 60
ANIM_FPS = 30
DUR = 10.0
ROOT = os.path.dirname(os.path.abspath(__file__))

F_HZ = "C:/Windows/Fonts/msyhbd.ttc"       # 花字（微软雅黑粗体）
F_SUB = "C:/Windows/Fonts/msyh.ttc"        # 小字

# ----------------------------------------------------------------- 时间轴（120 BPM，一拍 0.5s）
CUES = dict(
    shots=dict(sun=(0.0, 2.5), stare=(2.5, 4.0), fluff=(4.0, 7.5), card=(7.5, 10.0)),
    badge=0.0, title=[0.20, 0.267, 0.333, 0.40, 0.467],
    sparkle=0.80, aside=1.317, scratch=2.5,
    qmarks=[2.567, 2.633, 2.70], punch=3.00,
    quiet=[3.067, 3.133, 3.20, 3.267, 3.333, 3.40],
    sweat=[3.30, 3.50], wipe=4.0, tag=[4.20, 4.267, 4.333, 4.45],
    warn=4.90, warn_beeps=[4.90, 5.10], slide=[5.50, 6.00],
    boom=6.00, shock=[5.933, 6.00, 6.067], subline=6.60,
    freeze=7.50, jue=[8.10, 8.167, 8.233], stamp=8.50, bye=8.90, end=10.0,
)


# ----------------------------------------------------------------- 基础
def sstep(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def clip(x, a=0.0, b=1.0):
    return a if x < a else (b if x > b else x)


def sstep_arr(a, b, x):
    """数组版的 smoothstep（post 里做暗角用）"""
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def bezier(p1x, p1y, p2x, p2y, n=512):
    ts = np.linspace(0.0, 1.0, n)
    omt = 1.0 - ts
    xs = 3 * omt * omt * ts * p1x + 3 * omt * ts * ts * p2x + ts ** 3
    ys = 3 * omt * omt * ts * p1y + 3 * omt * ts * ts * p2y + ts ** 3
    xs = np.maximum.accumulate(xs)
    return lambda x: float(np.interp(clip(x), xs, ys))


eOutQuad = bezier(0.25, 0.46, 0.45, 0.94)
eInCubic = bezier(0.55, 0.055, 0.675, 0.19)
eOutBack = bezier(0.175, 0.885, 0.32, 1.275)


def spring(t, z=0.517, w=22.0):
    """阻尼弹簧 0 → 1（过冲），花字入场的核心"""
    if t <= 0:
        return 0.0
    wd = w * math.sqrt(max(1e-6, 1.0 - z * z))
    return 1.0 - math.exp(-z * w * t) * (math.cos(wd * t) + (z * w / wd) * math.sin(wd * t))


def h1(i):
    x = (int(i) ^ 0x9E3779B9) & 0xFFFFFFFF
    x = (x * 0x85EBCA6B) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 0xC2B2AE35) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296.0


def vn(x, seed):
    i = math.floor(x)
    f = x - i
    u = f * f * (3 - 2 * f)
    return lerp(h1(i * 7919 + seed * 104729), h1((i + 1) * 7919 + seed * 104729), u) * 2 - 1


def hand(t, seed, a=1.0):
    """手抖：两个八度的值噪声（综艺花字不可能是死板的）"""
    return (a * (7 * vn(t * 0.9, seed) + 2.5 * vn(t * 2.3, seed + 11)),
            a * (6 * vn(t * 0.8, seed + 23) + 2 * vn(t * 2.6, seed + 37)))


# ----------------------------------------------------------------- 花字
class HZ:
    """一套花字样式。核心参数和参考实现一一对应。"""

    def __init__(self, size=150, ext=16, ext_dx=0, ext_color="#0E1440",
                 outer=11, outer_color="#1E2A78", white=6, white_color="#FFFFFF",
                 grad=((0.0, "#FFF7A8"), (0.42, "#FFD23F"), (1.0, "#FF9A1F")),
                 gloss=0.55, font=F_HZ):
        self.size = size
        self.ext = ext
        self.ext_dx = ext_dx
        self.ext_color = ext_color
        self.outer = outer
        self.outer_color = outer_color
        self.white = white
        self.white_color = white_color
        self.grad = grad
        self.gloss = gloss
        self.font = font
        self.W = 2 * (outer + white)        # 基础描边宽（挤出层和外描边共用）

    def key(self):
        return (self.size, self.ext, self.ext_dx, self.ext_color, self.outer, self.outer_color,
                self.white, self.white_color, self.grad, self.gloss, self.font)


def _vgrad(size, stops):
    """竖直渐变（stops 是 [(位置, hex), ...]）"""
    w, h = size
    ys = np.arange(h, dtype=np.float32) / max(1, h - 1)
    cols = np.zeros((h, 3), np.float32)
    pos = [s[0] for s in stops]
    rgb = [np.array([int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)], np.float32)
           for _, hx in stops]
    for i in range(len(stops) - 1):
        m = (ys >= pos[i]) & (ys <= pos[i + 1])
        if not m.any():
            continue
        k = ((ys[m] - pos[i]) / max(1e-6, pos[i + 1] - pos[i]))[:, None]
        cols[m] = rgb[i] * (1 - k) + rgb[i + 1] * k
    cols[ys < pos[0]] = rgb[0]
    cols[ys > pos[-1]] = rgb[-1]
    return Image.fromarray(np.broadcast_to(cols[:, None, :], (h, w, 3)).astype(np.uint8), "RGB")


_GLYPH = {}


def glyph(ch, st):
    """渲染一个字的花字 sprite。**同一段文字叠五层**——这是全部秘密。"""
    k = (ch, st.key())
    if k in _GLYPH:
        return _GLYPH[k]
    fs = st.size
    font = ImageFont.truetype(st.font, fs)
    Ws = st.W
    pad = Ws + st.ext + 30
    tmp = ImageDraw.Draw(Image.new("L", (8, 8)))
    bb = tmp.textbbox((0, 0), ch, font=font, anchor="mm", stroke_width=Ws)
    gw = int(bb[2] - bb[0]) + 2 * pad
    gh = int(bb[3] - bb[1]) + 2 * pad + st.ext
    img = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = gw * 0.5
    cy = pad + (bb[3] - bb[1]) * 0.5
    # 1-2. 挤出：两层，偏移 ext 和 ext*0.5（露出来的部分就是"厚度"）
    for kk in (1.0, 0.5):
        d.text((cx + st.ext_dx * kk, cy + st.ext * kk), ch, font=font, fill=st.ext_color,
               stroke_width=Ws, stroke_fill=st.ext_color, anchor="mm")
    # 3. 外描边
    d.text((cx, cy), ch, font=font, fill=st.outer_color,
           stroke_width=Ws, stroke_fill=st.outer_color, anchor="mm")
    # 4. 白描边
    d.text((cx, cy), ch, font=font, fill=st.white_color,
           stroke_width=2 * st.white, stroke_fill=st.white_color, anchor="mm")
    # 5. 渐变填充
    mask = Image.new("L", (gw, gh), 0)
    ImageDraw.Draw(mask).text((cx, cy), ch, font=font, fill=255, anchor="mm")
    img.paste(_vgrad((gw, gh), st.grad), (0, 0), mask)
    # 6. 顶部高光（从上往下 46% 处衰减到 0）
    if st.gloss > 0:
        a = np.zeros((gh, gw), np.uint8)
        y1 = max(1, int(gh * 0.46))
        a[:y1] = np.linspace(255 * st.gloss, 0, y1)[:, None]
        gl = Image.new("RGBA", (gw, gh), (255, 255, 255, 0))
        gl.putalpha(Image.fromarray(a, "L"))
        img.alpha_composite(Image.composite(gl, Image.new("RGBA", (gw, gh), (0, 0, 0, 0)), mask))
    _GLYPH[k] = (img, (cx, cy))
    return _GLYPH[k]


def draw_char(dst, ch, st, x, y, s=1.0, rot=0.0):
    """把花字 sprite 变换后贴上去（旋转 + 缩放 + 平移）"""
    img, (cx, cy) = glyph(ch, st)
    if s <= 0.01:
        return
    if abs(s - 1.0) > 1e-3 or abs(rot) > 1e-3:
        im = img
        if abs(rot) > 1e-3:
            im = im.rotate(-rot, resample=Image.BICUBIC, center=(cx, cy))
        if abs(s - 1.0) > 1e-3:
            nw, nh = max(1, int(im.width * s)), max(1, int(im.height * s))
            im = im.resize((nw, nh), Image.BILINEAR)
            cx2, cy2 = cx * s, cy * s
        else:
            cx2, cy2 = cx, cy
    else:
        im, cx2, cy2 = img, cx, cy
    dst.alpha_composite(im, (int(x - cx2), int(y - cy2)))


def char_anim(t, t0, ph, drop=0.0, r0=0.0, wig=1.8, bob=3.0, breath=0.012, wf=1.15):
    """逐字动画：弹簧入场 → 下落/旋转 → 保持期的波浪抖动 + 呼吸"""
    u = t - t0
    if u < 0:
        return None
    s = spring(u, 0.517, 22.0)
    y = -drop * (1.0 - spring(u, 0.55, 20.0))
    r = r0 * (1.0 - spring(u, 0.45, 18.0))
    hold = clip((u - 0.22) / 0.35)
    r += hold * wig * math.sin(2 * math.pi * wf * t + ph)
    y += hold * bob * math.sin(2 * math.pi * wf * t + ph + 1.9)
    s *= 1.0 + hold * breath * math.sin(2 * math.pi * wf * 2 * t + ph * 1.7)
    return s, y, r


def draw_line(dst, text, st, cx, cy, t, t0s, sp_x=None, **kw):
    """一行花字，逐字入场。返回最后一个字的结束时刻。"""
    n = len(text)
    sp_x = st.size * 1.16 if sp_x is None else sp_x
    x0 = cx - sp_x * (n - 1) / 2.0
    for i, ch in enumerate(text):
        a = char_anim(t, t0s[i] if isinstance(t0s, (list, tuple)) else t0s + i * 0.045,
                      ph=x0 * 0.013 + i * 0.7, **kw)
        if a is None:
            continue
        s, dy, r = a
        draw_char(dst, ch, st, x0 + i * sp_x, cy + dy, s, r)
    return x0


# ----------------------------------------------------------------- 三只猫（程序生成，零素材）
_CAT = {}

# 三张真实照片，正好对应三种情绪
# (文件, 色调乘子, 裁剪中心 x/y 比例)
ASSETS = {
    "sun":   ("white_dof.jpg", (1.07, 1.00, 0.93), 0.50, 0.52),   # 白猫眯眼晒太阳，暖金石板路
    "stare": ("tux_r1.jpg",    (0.90, 0.97, 1.14), 0.50, 0.46),   # 黑白猫绿眼凝视，蓝涂鸦墙
    "fluff": ("grey_r2.jpg",   (1.15, 0.84, 1.08), 0.55, 0.50),   # 灰猫特写，草地调成粉紫
}
_CW, _CH = int(W * 1.30), int(H * 1.30)      # 比画幅大 30%，给运镜留推拉空间


def cat_image(mood):
    """真实猫咪照片：缩放填满 → 按指定中心裁剪 → 调色 → 轻微柔化。"""
    if mood in _CAT:
        return _CAT[mood]
    name, mul, fx, fy = ASSETS.get(mood, ASSETS["fluff"])
    p = os.path.join(ROOT, "assets", name)
    src = Image.open(p).convert("RGB")
    z = max(_CW / src.width, _CH / src.height)
    im = src.resize((max(_CW, int(src.width * z + 0.5)), max(_CH, int(src.height * z + 0.5))),
                    Image.LANCZOS)
    ox = int(clip(fx * im.width - _CW / 2, 0, im.width - _CW))
    oy = int(clip(fy * im.height - _CH / 2, 0, im.height - _CH))
    im = im.crop((ox, oy, ox + _CW, oy + _CH))
    a = np.asarray(im, np.float32) * np.array(mul, np.float32)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
    im = im.filter(ImageFilter.GaussianBlur(1.1))
    _CAT[mood] = im
    return im
def shot_of(t):
    if t < 2.5:
        return "sun"
    if t < 4.0:
        return "stare"
    if t < 7.5:
        return "fluff"
    return "card"


def camera(t):
    """每个镜头的运镜：(缩放, 中心 x, 中心 y)。慢推 + 轻微手持。"""
    sh = shot_of(t)
    if sh == "sun":
        k = clip(t / 2.5)
        z = lerp(1.02, 1.12, eOutQuad(k))
        return z, 750 + 8 * math.sin(t * 1.1), 1180 + 6 * math.sin(t * 0.9 + 1)
    if sh == "stare":
        k = clip((t - 2.5) / 1.5)
        z = lerp(1.16, 1.04, eOutQuad(k))
        return z, 745 + 5 * math.sin(t * 1.3), 1150 + 4 * math.sin(t * 1.0)
    if sh == "fluff":
        k = clip((t - 4.0) / 3.5)
        z = lerp(1.05, 1.20, eOutQuad(k))
        return z, 760 + 10 * math.sin(t * 0.8), 1170 + 8 * math.sin(t * 0.7 + 2)
    z = 1.10
    return z, 750, 1150


# ----------------------------------------------------------------- 装饰
def draw_badge(dst, t):
    """左上角节目角标：喵呜日记 EP07"""
    if t < CUES["badge"]:
        return
    k = spring(t - CUES["badge"], 0.45, 16)
    x = lerp(-320, 44, k)
    y = 60
    d = ImageDraw.Draw(dst)
    f = ImageFont.truetype(F_HZ, 40)
    fs = ImageFont.truetype(F_SUB, 24)
    tw = d.textlength("喵呜日记", font=f)
    pw = int(tw + 150)
    d.rounded_rectangle([x, y, x + pw, y + 74], radius=37, fill=(255, 232, 96, 255),
                        outline=(26, 16, 48, 255), width=7)
    d.text((x + 26, y + 15), "喵呜日记", font=f, fill=(26, 16, 48, 255))
    d.rounded_rectangle([x + pw - 108, y + 12, x + pw - 12, y + 62], radius=25,
                        fill=(255, 61, 127, 255), outline=(26, 16, 48, 255), width=5)
    d.text((x + pw - 92, y + 20), "EP07", font=fs, fill=(255, 255, 255, 255))


def draw_sparkle(dst, t, x, y, r, t0, seed=0):
    if t < t0:
        return
    k = clip((t - t0) / 0.42)
    if k >= 1:
        return
    s = math.sin(math.pi * k) ** 0.7
    d = ImageDraw.Draw(dst)
    rr = r * (0.5 + 0.9 * s)
    pts = []
    for i in range(8):
        a = i * math.pi / 4 + k * 1.6
        rad = rr if i % 2 == 0 else rr * 0.30
        pts.append((x + math.cos(a) * rad, y + math.sin(a) * rad))
    d.polygon(pts, fill=(255, 255, 255, int(240 * s)), outline=(255, 210, 63, int(255 * s)), width=4)


def draw_warn_bar(dst, t):
    """黄黑斜纹警告条：⚠ 前方高能 ⚠（截图里最抢眼的那块）"""
    t0 = CUES["warn"]
    if t < t0:
        return
    k = spring(t - t0, 0.42, 15)
    shake = 0.0
    for b in CUES["warn_beeps"]:
        if 0 <= t - b < 0.12:
            shake = 14 * math.sin((t - b) / 0.12 * math.pi * 3) * (1 - (t - b) / 0.12)
    cw, chh = 1010, 300
    cx, cy = W * 0.5 + shake, H - 300
    s = k
    d = ImageDraw.Draw(dst)
    # 斜纹底
    bar = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar)
    bd.rectangle([0, 0, cw, chh], fill=(255, 214, 40, 245))
    for i in range(-2, int(cw / 40) + 3):
        x0 = i * 40
        bd.polygon([(x0, 0), (x0 + 20, 0), (x0 + 20 - chh * 0.5, chh), (x0 - chh * 0.5, chh)],
                   fill=(28, 20, 22, 205))
    # 圆角遮罩
    m = Image.new("L", (cw, chh), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, cw - 1, chh - 1], radius=26, fill=255)
    bar.putalpha(m)
    if abs(s - 1.0) > 1e-3:
        bar = bar.resize((max(1, int(cw * s)), max(1, int(chh * s))), Image.BILINEAR)
    dst.alpha_composite(bar, (int(cx - bar.width / 2), int(cy - bar.height / 2)))
    # 文字（用花字）
    # 文字用纯白 + 粗黑描边：黄黑斜纹本身已经很花，字再用黄渐变就糊成一片
    # 渐变必须有明暗层次。写成 #FFFFFF -> #FFFFFF 的话，五层叠完就是一坨白板，
    # 描边再细也救不回来——眼睛认字靠的是笔画之间的明暗差，不是轮廓。
    st = HZ(size=124, ext=12, ext_color="#000000", outer=8, outer_color="#0A060C",
            white=4, white_color="#FFFFFF",
            grad=((0.0, "#FFFFFF"), (0.42, "#FFF2F7"), (1.0, "#FFC2DC")), gloss=0.60)
    txt = "前方高能"
    sp = st.size * 1.18
    n = len(txt)
    x0 = cx - sp * (n - 1) / 2
    for i, ch in enumerate(txt):
        a = char_anim(t, t0 + 0.06 + i * 0.045, ph=i * 0.9, wig=1.4, bob=2.2)
        if a is None:
            continue
        ss, dy, r = a
        draw_char(dst, ch, st, x0 + i * sp, cy + dy, ss, r)
    # 三角警告符号
    for sgn in (-1, 1):
        ax = cx + sgn * (sp * n / 2 + 34)
        tri = [(ax, cy - 40), (ax + 44, cy + 34), (ax - 44, cy + 34)]
        d.polygon(tri, fill=(255, 60, 40, 255), outline=(26, 16, 48, 255), width=6)
        d.text((ax - 11, cy - 22), "!", font=ImageFont.truetype(F_HZ, 52), fill=(255, 255, 255, 255))


def draw_stamp(dst, t):
    """印章：绝赞 / 喵呜日记"""
    t0 = CUES["stamp"]
    if t < t0:
        return
    k = clip((t - t0) / 0.16)
    if k <= 0:
        return
    s = lerp(2.4, 1.0, eInCubic(k)) if k < 0.6 else 1.0
    a = int(255 * min(1.0, k * 3))
    cx, cy = W * 0.5 + 210, H - 620
    d = ImageDraw.Draw(dst)
    f = ImageFont.truetype(F_HZ, 54)
    tw = d.textlength("喵呜日记", font=f)
    bw, bh = int(tw + 56), 96
    im = Image.new("RGBA", (int(bw * s), int(bh * s)), (0, 0, 0, 0))
    dd = ImageDraw.Draw(im)
    dd.rounded_rectangle([3, 3, im.width - 4, im.height - 4], radius=int(14 * s),
                         outline=(228, 48, 62, a), width=max(3, int(7 * s)))
    dd.text((im.width / 2, im.height / 2), "喵呜日记", font=ImageFont.truetype(F_HZ, int(54 * s)),
            fill=(228, 48, 62, a), anchor="mm")
    rot = im.rotate(9, resample=Image.BICUBIC, expand=True)
    dst.alpha_composite(rot, (int(cx - rot.width / 2), int(cy - rot.height / 2)))


def draw_sweat(dst, t, x, y, t0, s=1.0):
    if t < t0:
        return
    k = clip((t - t0) / 0.5)
    if k >= 1:
        return
    yy = y + 90 * eInCubic(k)
    a = int(255 * (1 - k))
    d = ImageDraw.Draw(dst)
    r = 26 * s
    d.ellipse([x - r, yy - r * 1.25, x + r, yy + r * 1.25], fill=(150, 232, 255, a),
              outline=(30, 42, 120, a), width=5)
    d.ellipse([x - r * 0.42, yy - r * 0.55, x - r * 0.05, yy + r * 0.1], fill=(255, 255, 255, a))


def draw_scratch(dst, t):
    """抓痕转场：三道白爪印划过"""
    t0 = CUES["scratch"]
    k = clip((t - t0) / 0.30)
    if k <= 0 or k >= 1:
        return
    d = ImageDraw.Draw(dst)
    a = int(255 * math.sin(math.pi * k))
    for i, off in enumerate((-120, 0, 120)):
        x0 = -200 + (W + 400) * eOutQuad(k)
        d.line([(x0 + off, 0), (x0 + off + 260, H)], fill=(255, 255, 255, a), width=16)
        d.line([(x0 + off + 6, 0), (x0 + off + 266, H)], fill=(26, 16, 48, int(a * 0.35)), width=5)


def wipe_mask(t, t0, dur=0.22, vertical=False):
    """擦除转场遮罩：返回 0..1 的进度（1 = 完全盖住）"""
    k = (t - t0) / dur
    if k <= 0:
        return 0.0
    if k >= 1:
        return 0.0
    return math.sin(math.pi * k) ** 0.6


# ----------------------------------------------------------------- 渲染
def base_image(t):
    """猫 + 运镜"""
    sh = shot_of(t)
    cat = cat_image(sh)
    z, cx, cy = camera(t)
    cw, chh = int(W / z), int(H / z)
    x0 = int(clip(cx - cw / 2, 0, cat.width - cw))
    y0 = int(clip(cy - chh / 2, 0, cat.height - chh))
    crop = cat.crop((x0, y0, x0 + cw, y0 + chh)).resize((W, H), Image.BILINEAR)
    return crop.convert("RGBA")


def render(t):
    img = base_image(t)
    d = ImageDraw.Draw(img)

    # ---- 镜头 1：sun（0 – 2.5）
    if t < 2.55:
        # 主标题「前方高能」五个字逐个弹入
        st_main = HZ(size=170, ext=20, ext_dx=-2, ext_color="#7A1B00",
                     outer=13, outer_color="#1A0B33", white=7, white_color="#FFFFFF",
                     grad=((0.0, "#FFF9C4"), (0.38, "#FFD23F"), (1.0, "#FF7A18")), gloss=0.58)
        draw_line(img, "前方高能", st_main, W * 0.5, 560, t, CUES["title"],
                  drop=70, r0=-9, wig=1.6, bob=4.0)
        # 旁白小字
        if t >= CUES["aside"]:
            k = spring(t - CUES["aside"], 0.5, 18)
            st_sub = HZ(size=62, ext=8, ext_color="#12203F", outer=7, outer_color="#0E1630",
                        white=4, white_color="#FFFFFF",
                        grad=((0.0, "#FFFFFF"), (1.0, "#BFD8FF")), gloss=0.45)
            draw_line(img, "这只猫有点东西", st_sub, W * 0.5, 920, t,
                      [CUES["aside"] + i * 0.04 for i in range(7)], wig=1.2, bob=2.4)
        for (sx, sy, sr, s0) in [(160, 470, 34, 0.80), (930, 520, 26, 0.867),
                                 (880, 900, 40, 0.933), (200, 1010, 24, 1.0)]:
            draw_sparkle(img, t, sx, sy, sr, s0)

    # ---- 镜头 2：stare（2.5 – 4.0）
    if 2.45 <= t < 4.05:
        st_q = HZ(size=150, ext=14, ext_color="#0B1E4A", outer=12, outer_color="#101A3A",
                  white=6, white_color="#FFFFFF",
                  grad=((0.0, "#FFFFFF"), (0.5, "#DCEBFF"), (1.0, "#8FB6FF")), gloss=0.5)
        for i, t0 in enumerate(CUES["qmarks"]):
            a = char_anim(t, t0, ph=i * 1.4, drop=40, r0=(i - 1) * 12, wig=2.4, bob=5.0)
            if a is None:
                continue
            s, dy, r = a
            draw_char(img, "?", st_q, W * 0.30 + i * 150, 620 + dy + (i - 1) * 26, s * 0.9, r)
        # 六个「静」字
        st_q2 = HZ(size=76, ext=8, ext_color="#101A3A", outer=7, outer_color="#2A3E7A",
                   white=4, white_color="#FFFFFF",
                   grad=((0.0, "#EAF4FF"), (1.0, "#7FA8E8")), gloss=0.4)
        for i, t0 in enumerate(CUES["quiet"]):
            a = char_anim(t, t0, ph=i * 0.8, wig=1.0, bob=2.0)
            if a is None:
                continue
            s, dy, r = a
            draw_char(img, "静", st_q2, W * 0.5 + (i - 2.5) * 92, 1650 + dy, s * 0.95, r)
        for i, t0 in enumerate(CUES["sweat"]):
            draw_sweat(img, t, 880 + i * 70, 760 + i * 130, t0, 1.15 - i * 0.2)

    # ---- 镜头 3：fluff（4.0 – 7.5）
    if 3.95 <= t < 7.55:
        # 标签
        if t >= CUES["tag"][0]:
            st_tag = HZ(size=104, ext=12, ext_color="#4A0A2A", outer=9, outer_color="#1A0B33",
                        white=5, white_color="#FFFFFF",
                        grad=((0.0, "#FFE6F2"), (1.0, "#FF3D7F")), gloss=0.5)
            draw_line(img, "炸毛了", st_tag, W * 0.5, 470, t, CUES["tag"], drop=50, r0=8,
                      wig=2.0, bob=4.5)
        # 副标题
        if t >= CUES["subline"]:
            st_s = HZ(size=70, ext=8, ext_color="#2A0E3A", outer=7, outer_color="#180A26",
                      white=4, white_color="#FFFFFF",
                      grad=((0.0, "#FFFFFF"), (1.0, "#FFC9E4")), gloss=0.45)
            draw_line(img, "这不是猫是情绪", st_s, W * 0.5, 900, t,
                      [CUES["subline"] + i * 0.035 for i in range(7)], wig=1.3, bob=2.6)
        # 「砰！」
        if t >= CUES["boom"] - 0.02:
            k = clip((t - CUES["boom"]) / 0.34)
            if k < 1:
                # 起始缩放别给到 3 倍：136px 的字乘 3 已经超出 1080 画宽，会被裁掉
                s = lerp(2.0, 1.0, eInCubic(min(1.0, k * 2.0)))
                a = 1.0 if k < 0.75 else (1.0 - (k - 0.75) / 0.25)
                st_b = HZ(size=112, ext=14, ext_color="#5A0A0A", outer=10, outer_color="#20050A",
                          white=6, white_color="#FFFFFF",
                          grad=((0.0, "#FFF3B0"), (0.4, "#FF6A2A"), (1.0, "#D81E1E")), gloss=0.55)
                if a > 0.02:
                    draw_char(img, "砰", st_b, W * 0.5 - 68, 720, s, -8)
                    draw_char(img, "!", st_b, W * 0.5 + 96, 720, s * 1.05, 6)
        # 警告条
        draw_warn_bar(img, t)
        draw_scratch(img, t)

    # ---- 结尾卡片（7.5 – 10）
    if t >= 7.45:
        k = clip((t - CUES["freeze"]) / 0.3)
        if k > 0:
            ov = Image.new("RGBA", (W, H), (8, 6, 14, int(118 * k)))
            img.alpha_composite(ov)
        st_e = HZ(size=150, ext=18, ext_color="#5A1030", outer=12, outer_color="#2A0A1E",
                  white=7, white_color="#FFFFFF",
                  grad=((0.0, "#FFFFFF"), (0.45, "#FFD8EC"), (1.0, "#FF74BE")), gloss=0.55)
        draw_line(img, "绝了", st_e, W * 0.5, 720, t, CUES["jue"], drop=60, r0=-10,
                  wig=2.2, bob=5.0)
        if t >= CUES["bye"]:
            st_bye = HZ(size=64, ext=7, ext_color="#2A2A44", outer=6, outer_color="#1A1A30",
                        white=4, white_color="#FFFFFF",
                        grad=((0.0, "#FFFFFF"), (1.0, "#B8C8E8")), gloss=0.4)
            draw_line(img, "下期见", st_bye, W * 0.5, 1000, t,
                      [CUES["bye"] + i * 0.05 for i in range(3)], wig=1.4, bob=3.0)
        draw_stamp(img, t)

    # ---- 转场
    for (t0, vert) in ((CUES["wipe"], False), (7.5, True)):
        a = wipe_mask(t, t0, 0.24, vert)
        if a > 0.01:
            if vert:
                hh = int(H * a)
                d.rectangle([0, 0, W, hh], fill=(10, 8, 16, 255))
                d.rectangle([0, H - hh, W, H], fill=(10, 8, 16, 255))
            else:
                ww = int(W * a)
                d.rectangle([0, 0, ww, H], fill=(10, 8, 16, 255))
                d.rectangle([W - ww, 0, W, H], fill=(10, 8, 16, 255))

    # ---- 角标
    draw_badge(img, t)

    # ---- 后期：震屏 + 暗角 + 颗粒
    img = post(img, t)
    return img


def post(img, t):
    # 震屏（砰的那一下）
    shake = 0.0
    for b in (CUES["boom"],):
        if 0 <= t - b < 0.22:
            k = (t - b) / 0.22
            shake = 26 * (1 - k) ** 2 * math.sin(k * math.pi * 9)
    if abs(shake) > 0.5:
        img = Image.fromarray(np.roll(np.asarray(img), int(shake), axis=0), "RGBA")
    a = np.asarray(img, np.float32) / 255.0
    # 暗角
    yy = (np.arange(H, dtype=np.float32)[:, None] + 0.5) / H - 0.5
    xx = ((np.arange(W, dtype=np.float32)[None, :] + 0.5) / W - 0.5) * (W / H)
    r2 = xx * xx + yy * yy
    a[..., :3] *= (1.0 - 0.34 * sstep_arr(0.10, 0.62, np.sqrt(r2)))[..., None]
    # 颗粒
    fr = t * FPS
    g = (np.mod(np.sin((xx * 1920 + fr * 37.1) * 12.9898 + (yy * 1080 + fr * 91.7) * 78.233) * 43758.5453, 1.0) - 0.5)
    a[..., :3] += (g * 0.030)[..., None]
    return Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


# ----------------------------------------------------------------- CLI
def save(img, path):
    img.convert("RGB").save(path, quality=95)


def cmd_one(t, out):
    t0 = time.time()
    img = render(t)
    save(img, out)
    print("%s  t=%.2fs  %.1fs" % (out, t, time.time() - t0), flush=True)


def _worker(i):
    img = render(i / float(FPS))
    save(img, os.path.join(ROOT, "frames", "f_%04d.png" % i))
    return i


def cmd_all(workers=4, lo=0, hi=None):
    os.makedirs(os.path.join(ROOT, "frames"), exist_ok=True)
    n = int(round(DUR * FPS))
    hi = n if hi is None else min(hi, n)
    lo = max(0, lo)
    tot = hi - lo
    t0 = time.time()
    import multiprocessing as mp
    done = 0
    with mp.Pool(workers, maxtasksperchild=30) as pool:
        for _ in pool.imap_unordered(_worker, range(lo, hi), chunksize=1):
            done += 1
            if done % 20 == 0 or done == tot:
                el = time.time() - t0
                print("  %3d/%d  %.2f 帧/秒  ETA %.1f 分钟" %
                      (done, tot, done / max(el, 1e-3),
                       (tot - done) / max(done / max(el, 1e-3), 1e-3) / 60.0), flush=True)
    print("完成 %d 帧，用时 %.1f 分钟" % (tot, (time.time() - t0) / 60.0))


def cmd_preview():
    for t in (0.10, 0.55, 1.40, 2.80, 3.20, 4.30, 5.20, 6.05, 6.90, 8.20, 9.40):
        img = render(t)
        save(img, os.path.join(ROOT, "prev_%.2f.png" % t))
        print("prev_%.2f.png" % t, flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if cmd == "one":
        cmd_one(float(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "out.png")
    elif cmd == "all":
        cmd_all(int(sys.argv[2]) if len(sys.argv) > 2 else 4)
    elif cmd == "range":
        # argv = [script, 'range', lo, hi, workers] —— workers 在 [4]，不是 [5]
        cmd_all(int(sys.argv[4]) if len(sys.argv) > 4 else 2, int(sys.argv[2]), int(sys.argv[3]))
    else:
        cmd_preview()
