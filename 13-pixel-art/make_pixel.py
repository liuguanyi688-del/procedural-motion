# -*- coding: utf-8 -*-
"""
13 · 像素风 Pixel Art  PIXEL QUEST 像素冒险
============================================
320×180 索引色画布 → 语义槽 → 每帧 LUT → 32 色母版调色板 → 整数放大 6 倍 → CRT。

没有 3D、没有着色器。这一版的全部技巧都在"索引"两个字上：
画面里每个像素只存一个**色号**，色号到真实颜色的映射每帧重算一次——
于是"一整天光线的变化"和"水波流动"都不需要重画任何一个像素。

    python make_pixel.py preview        # 关键帧预览
    python make_pixel.py one 6.5 a.png  # 单帧
    python make_pixel.py all 6          # 600 帧 → frames/
"""

import os
import sys
import math
import time

import numpy as np
from PIL import Image, ImageDraw

np.seterr(all="ignore")

# ----------------------------------------------------------------- 规格
IW, IH = 320, 180          # 低分辨率画布
SCALE = 6                  # 6 倍整数放大 → 1920×1080
W, H = IW * SCALE, IH * SCALE
FPS = 60
ANIM_FPS = 30              # 动画以 30fps 步进（像素游戏的节奏）
DUR = 10.0
ROOT = os.path.dirname(os.path.abspath(__file__))

GROUND = 150               # 地面线
BR0, BR1 = 128, 176        # 木桥（同时也是水渠）的世界 x 范围

# ----------------------------------------------------------------- 32 色母版
HEX = ['0d0b1a', '1b1a33', '2a2f5a', '3d4a8a', '4f6fc0', '5b9bea', '8cc8f5', 'c8ecff', 'ffffff',
       '3b1f47', '6b2d5c', 'b0415f', 'e8665a', 'f59a4a', 'ffd166', 'fff3b0',
       '0f2a2a', '1d4a3a', '2e7a45', '4fae4a', '93d65a',
       '2b1a1f', '5a3326', '8a5236', 'c07a45', 'e8b27c',
       '7a1f2e', 'd23c3c', 'ffc9a0',
       '4a5270', '7d88a8', 'b8c2d9']
MP = np.array([[int(h[i:i + 2], 16) for i in (0, 2, 4)] for h in HEX], np.float32)

NSLOT = 128
# 直接色（精灵用）：槽位 64..95 固定映射到母版 0..31
SM = np.zeros((NSLOT, 6), np.int32)
for i in range(32):
    SM[64 + i] = i


def _m(i):
    return 64 + i


E = {}
_n = [1]


def env(name, arr):
    E[name] = _n[0]
    SM[_n[0]] = arr
    _n[0] += 1


#         DAY AFT GOLD SUNS DUSK NIGHT      ← 六个时段，每个语义槽一套色号
env('s0', [4, 4, 3, 3, 2, 1])
env('s1', [5, 5, 4, 10, 3, 2])
env('s2', [6, 6, 25, 11, 10, 3])
env('s3', [7, 15, 14, 12, 11, 9])
env('s4', [7, 14, 13, 13, 12, 10])
env('sun', [15, 15, 15, 14, 13, 13])
env('sunG', [8, 15, 14, 13, 12, 11])
env('clL', [8, 8, 15, 13, 11, 3])
env('clD', [31, 25, 24, 11, 10, 2])
env('mD', [5, 5, 29, 10, 9, 1])
env('mL', [6, 25, 24, 11, 10, 2])
env('mS', [8, 15, 15, 12, 11, 3])
env('mist', [6, 15, 14, 12, 10, 2])
env('rD', [29, 22, 22, 9, 9, 1])
env('rM', [30, 23, 24, 10, 10, 2])
env('rL', [31, 25, 28, 11, 11, 3])
env('fD', [17, 17, 17, 9, 9, 0])
env('fM', [18, 18, 18, 17, 16, 16])
env('fL', [19, 20, 20, 24, 17, 17])
env('hD', [17, 17, 17, 9, 16, 0])
env('hM', [18, 18, 18, 17, 17, 16])
env('hL', [19, 20, 20, 24, 18, 17])
env('gD', [18, 18, 18, 17, 16, 16])
env('gM', [19, 19, 19, 18, 17, 17])
env('gL', [20, 20, 20, 24, 18, 3])
env('dD', [22, 22, 22, 21, 21, 0])
env('dM', [23, 23, 23, 22, 22, 21])
env('dL', [24, 24, 24, 23, 23, 22])
env('flw', [8, 8, 15, 14, 11, 3])
env('rvB', [5, 5, 5, 10, 2, 1])
env('rvD', [4, 4, 4, 9, 1, 0])
env('rvG', [8, 8, 15, 15, 11, 6])
WAT = [[4, 4, 4, 10, 2, 1], [5, 5, 5, 11, 3, 2], [6, 6, 15, 10, 10, 2], [8, 8, 8, 12, 11, 30]]
for _k, _a in enumerate(WAT):
    env('w%d' % _k, _a)
WS = [E['w0'], E['w1'], E['w2'], E['w3']]
for _k in range(4):
    env('st%d' % _k, [8, 8, 8, 8, 8, 8])
STS = [E['st0'], E['st1'], E['st2'], E['st3']]
WFSEQ = [[0, 1, 1, 2, 3, 3, 2, 1], [1, 0, 0, 1, 1, 2, 3, 1]]
WFG = []
for _g, _q in enumerate(WFSEQ):
    row = []
    for _k in range(8):
        env('wf%d_%d' % (_g, _k), [0, 0, 0, 0, 0, 0])
        row.append(_n[0] - 1)
    WFG.append(row)
STAR_SEQ = [8, 31, 29, 31]


def nearest(r, g, b):
    d = 0.3 * (MP[:, 0] - r) ** 2 + 0.59 * (MP[:, 1] - g) ** 2 + 0.11 * (MP[:, 2] - b) ** 2
    return int(np.argmin(d))


def mix_idx(a, b, t):
    A, B = MP[a], MP[b]
    return nearest(A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t, A[2] + (B[2] - A[2]) * t)


# ----------------------------------------------------------------- 时间轴（150 BPM）
BPM = 150
BEAT = 60.0 / BPM          # 0.4 s
BAR = BEAT * 4             # 1.6 s
CUES = dict(
    jumps=[0.3, 2.0], coins=[0.4, 0.5, 0.6, 3.2, 3.4, 3.6], lands=[0.9, 2.8],
    stomp=2.4, skid=4.0, stop=4.4, alert=4.4, box_open=4.6,
    type=[4.8, 4.9, 5.0, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6], box_close=5.8,
    zoom=[5.9, 6.0, 6.1], zoom_scale=[8, 10, 12], zoom_center=[158, 128],
    chest_shake=[6.0, 6.4], question=6.067, lid_hops=[6.2, 6.3], chest_open=6.4,
    cheer=6.667, item_get=6.8, logo=7.2, shine=7.6,
    subtitle=[8.0, 8.1, 8.2, 8.3], press_start=8.4,
    palette=dict(day=0.0, afternoon=1.6, golden=3.2, sunset=4.4, flash=6.4, dusk=6.47, night=8.0),
    end=10.0, rays_off=7.6, flinch=6.3,
)
F = lambda t: int(round(t * ANIM_FPS))

FLASH = F(CUES["chest_open"])
TRANS = [(F(CUES["palette"]["afternoon"]), 0, 1), (F(CUES["palette"]["golden"]), 1, 2),
         (F(CUES["palette"]["sunset"]), 2, 3)]
FNIGHT = F(CUES["palette"]["night"])


def stage_of(f):
    for T, a, b in TRANS:
        if T <= f < T + 4:
            return (a, b, 1 / 3 if f < T + 2 else 2 / 3)
    # 六个时段：日 / 午后 / 金 / 落日 / 暮 / 夜
    if f < TRANS[0][0]:
        s = 0
    elif f < TRANS[1][0]:
        s = 1
    elif f < TRANS[2][0]:
        s = 2
    elif f < FLASH:
        s = 3
    elif f < FNIGHT:
        s = 4
    else:
        s = 5          # NIGHT 列（原先漏掉，导致 8.0s 后一直停在暮色）
    return (s, s, 0.0)


def make_lut(f):
    a, b, t = stage_of(f)
    lut = np.empty(NSLOT, np.uint8)
    for s in range(NSLOT):
        lut[s] = mix_idx(SM[s][a], SM[s][b], t) if t else SM[s][a]
    # ---- 调色板轮换：水波 10fps、星星 7.5fps，只转色号，不重画像素
    ph = f // 3
    for k in range(4):
        src = WS[(k - ph) & 3]
        lut[WS[k]] = mix_idx(SM[src][a], SM[src][b], t) if t else SM[src][a]
    sp = f // 4
    for k in range(4):
        lut[STS[k]] = STAR_SEQ[(k + sp) & 3]
    for g in range(2):
        for k in range(8):
            w = WAT[WFSEQ[g][(k - f) & 7]]
            lut[WFG[g][k]] = mix_idx(w[a], w[b], t) if t else w[a]
    # ---- 宝箱开启的白闪
    if f == FLASH:
        for s in range(NSLOT):
            lut[s] = 0 if s == _m(0) else 8
    elif f == FLASH + 1:
        for s in range(64):
            lut[s] = 15
    return lut


# ----------------------------------------------------------------- 画布
class Buf:
    def __init__(self):
        self.d = np.zeros(IH * IW, np.uint8)

    def px(self, x, y, c):
        if 0 <= x < IW and 0 <= y < IH:
            self.d[y * IW + x] = c

    def rect(self, x, y, w, h, c):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(IW, x + w), min(IH, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        self.d.reshape(IH, IW)[y0:y1, x0:x1] = c

    def blit(self, spr, x, y, flip=False):
        h, w, d = spr['h'], spr['w'], spr['d']
        for j in range(h):
            yy = y + j
            if yy < 0 or yy >= IH:
                continue
            for i in range(w):
                xx = x + (w - 1 - i if flip else i)
                if xx < 0 or xx >= IW:
                    continue
                c = d[j * w + i]
                if c:
                    self.d[yy * IW + xx] = c

    def line(self, x0, y0, x1, y1, fn):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        e = dx + dy
        while True:
            fn(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * e
            if e2 >= dy:
                e += dy
                x0 += sx
            if e2 <= dx:
                e += dx
                y0 += sy


def hsh(x, y):
    h = (int(x) * 374761393 + int(y) * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFFFF) / 4294967296.0


def rng(seed):
    a = [seed & 0xFFFFFFFF]

    def f():
        a[0] = (a[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = a[0]
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = (t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return f


BAY = np.array([0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5], np.float32) / 16.0


def bay(x, y):
    return float(BAY[(int(y) & 3) * 4 + (int(x) & 3)])


# ----------------------------------------------------------------- 精灵
LEG = dict(k=_m(0), w=_m(8), r=_m(27), R=_m(26), o=_m(12), s=_m(28), S=_m(25), b=_m(4), B=_m(3),
           y=_m(14), Y=_m(13), g=_m(19), G=_m(20), d=_m(23), D=_m(21), n=_m(2), t=_m(24), h=_m(22),
           l=_m(30), L=_m(31), c=_m(6), e=_m(11), z=_m(7), v=_m(5), C=_m(3), u=_m(15), p=_m(17),
           P=_m(18), i=_m(1), I=_m(2), kk=_m(0))


def spr(rows, leg=LEG):
    h = len(rows)
    w = max(len(r) for r in rows)
    d = np.zeros(w * h, np.uint8)
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != '.' and ch in leg:
                d[j * w + i] = leg[ch]
    return dict(w=w, h=h, d=d)


def outline(s, col=None):
    col = _m(0) if col is None else col
    w, h, d = s['w'], s['h'], s['d']
    o = np.zeros((h + 2) * (w + 2), np.uint8)
    src = d.reshape(h, w)
    for j in range(h):
        for i in range(w):
            if src[j, i]:
                o[(j + 1) * (w + 2) + (i + 1)] = src[j, i]
    res = o.reshape(h + 2, w + 2).copy()
    for j in range(h + 2):
        for i in range(w + 2):
            if res[j, i]:
                continue
            near = False
            for dj, di in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                jj, ii = j + dj, i + di
                if 0 <= jj < h + 2 and 0 <= ii < w + 2 and res[jj, ii]:
                    near = True
                    break
            if near:
                o[j * (w + 2) + i] = col
    return dict(w=w + 2, h=h + 2, d=o)


O = lambda rows: outline(spr(rows))

# 主角：12×16（红帽 + 蓝衣），另加 1px 描边
HERO = O([
    '....rrrr....',
    '...rrrrrr...',
    '..rrRRRRrr..',
    '..oooooooo..',
    '..okkoooko..',
    '..oooooooo..',
    '...oooooo...',
    '..bbbbbbbb..',
    '.bbbbbbbbbb.',
    '.bbyyyyyybb.',
    '.bbbbbbbbbb.',
    '..bbbbbbbb..',
    '..bb....bb..',
    '..bb....bb..',
    '..kk....kk..',
    '..kk....kk..',
])
HERO_JUMP = O([
    '....rrrr....',
    '...rrrrrr...',
    '..rrRRRRrr..',
    '..oooooooo..',
    '..okkoooko..',
    '..oooooooo..',
    '...oooooo...',
    '.bbbbbbbbbb.',
    'bbbbbbbbbbbb',
    'bbyyyyyyyybb',
    '.bbbbbbbbbb.',
    '..bbbbbbbb..',
    '..bb..bb....',
    '.kk....kk...',
    '.kk.....kk..',
    'kk.......kk.',
])
COIN = [O(['..yyyy..', '.yYYYYy.', 'yYYwwYYy', 'yYwyywYy', 'yYwyywYy', 'yYYwwYYy', '.yYYYYy.', '..yyyy..']),
        O(['..yyyy..', '.yYYYYy.', '.yYwwYy.', '..yYYy..', '..yYYy..', '.yYwwYy.', '.yYYYYy.', '..yyyy..']),
        O(['...yy...', '..yYYy..', '..ywwy..', '..ywwy..', '..ywwy..', '..ywwy..', '..yYYy..', '...yy...']),
        O(['...yy...', '...yy...', '...yy...', '...yy...', '...yy...', '...yy...', '...yy...', '...yy...'])]
SLIME_A = O(['..eeeeeeee..', '.ekkeeeekke.', 'eSSSSSSSSSSe', 'eSwwSSSSwwSe', 'eSSSSSSSSSSe', '.eeeeeeeeee.', '..eeeeeeee..', '...eeeeee...', '..e.ee.ee.e.'])
SLIME_B = O(['...eeeeee...', '..ekkeeekke.', '.eSSSSSSSSe.', 'eSwwSSSSwwSe', 'eSSSSSSSSSSe', '.eeeeeeeeee.', '..eeeeeeee..', '...eeeeee...', '..e.ee.ee.e.'])
CHEST = O([
    '.hIuuttttttttttIh.',
    'ihuttttttttttttlhi',
    'iItttttttttttllLIi',
    'iILlllllllllllLLIi',
    'iiiiiiiuyyYiiiiiii',
    'iItttttyykYtttttIi',
    'ihlllllYYkYlllllhi',
    'iIllllllllllllllIi',
    'iILLLLLLLLLLLLLLIi',
    'iItlllllllllllllIi',
    'iILLLLLLLLLLLLLLIi',
    'iiiiiiiiiiiiiiiiii',
])
CHEST_OPEN = O([
    '..iILLLLLLLLIi....',
    '.iIeLLLLLLLLeIi...',
    '.ihLLLLLLLLLLhi...',
    '.iIeeeeeeeeeeeeIi.',
    '.iLLeeeeeeeeeeLLi.',
    'iiiiiiiuyyYiiiiiii',
    'iItttttyykYtttttIi',
    'ihlllllYYkYlllllhi',
    'iIllllllllllllllIi',
    'iILLLLLLLLLLLLLLIi',
    'iItlllllllllllllIi',
    'iiiiiiiiiiiiiiiiii',
])
GEM = O(['...w...', '..zwv..', '.zzvvc.', 'zzzvvcC', '.zvvcC.', '..vcC..', '...C...'])
BUBBLE = O(['..wwwww..', '.wwBBBww.', 'wwBwwwBww', 'wwwwwwBww', 'wwwwBBwww', 'wwwwBwwww', 'wwwwwwwww', '.wwwBwww.', '..wwww...', '..ww.....', '..w......'])
SPARK = [spr(['.ww.', 'wwww', 'wwww', '.ww.']), spr(['..ww..', '.wwwww', 'ww..ww', '.wwww.']),
         spr(['.w..w.', 'w....w', '.w..w.'])]
PUFF = [spr(['.ww.', 'wwww', 'wwww', '.ww.']), spr(['..ww..', '.wwwww', 'ww..ww', '.wwww.']),
        spr(['.w..w.', 'w....w', '.w..w.'])]

# ----------------------------------------------------------------- 5×7 位图字体
FONT = {
    'A': ['01110', '10001', '10001', '11111', '10001', '10001', '10001'],
    'B': ['11110', '10001', '11110', '10001', '10001', '10001', '11110'],
    'C': ['01111', '10000', '10000', '10000', '10000', '10000', '01111'],
    'D': ['11110', '10001', '10001', '10001', '10001', '10001', '11110'],
    'E': ['11111', '10000', '11110', '10000', '10000', '10000', '11111'],
    'G': ['01111', '10000', '10000', '10111', '10001', '10001', '01111'],
    'I': ['11111', '00100', '00100', '00100', '00100', '00100', '11111'],
    'K': ['10001', '10010', '10100', '11000', '10100', '10010', '10001'],
    'L': ['10000', '10000', '10000', '10000', '10000', '10000', '11111'],
    'M': ['10001', '11011', '10101', '10101', '10001', '10001', '10001'],
    'N': ['10001', '11001', '10101', '10011', '10001', '10001', '10001'],
    'O': ['01110', '10001', '10001', '10001', '10001', '10001', '01110'],
    'P': ['11110', '10001', '10001', '11110', '10000', '10000', '10000'],
    'Q': ['01110', '10001', '10001', '10001', '10101', '10010', '01101'],
    'R': ['11110', '10001', '10001', '11110', '10100', '10010', '10001'],
    'S': ['01111', '10000', '10000', '01110', '00001', '00001', '11110'],
    'T': ['11111', '00100', '00100', '00100', '00100', '00100', '00100'],
    'U': ['10001', '10001', '10001', '10001', '10001', '10001', '01110'],
    'V': ['10001', '10001', '10001', '10001', '10001', '01010', '00100'],
    'X': ['10001', '10001', '01010', '00100', '01010', '10001', '10001'],
    'Y': ['10001', '10001', '01010', '00100', '00100', '00100', '00100'],
    '0': ['01110', '10001', '10011', '10101', '11001', '10001', '01110'],
    '1': ['00100', '01100', '00100', '00100', '00100', '00100', '01110'],
    '2': ['01110', '10001', '00001', '00110', '01000', '10000', '11111'],
    '3': ['11111', '00010', '00100', '00010', '00001', '10001', '01110'],
    '4': ['00010', '00110', '01010', '10010', '11111', '00010', '00010'],
    '5': ['11111', '10000', '11110', '00001', '00001', '10001', '01110'],
    '6': ['00110', '01000', '10000', '11110', '10001', '10001', '01110'],
    '7': ['11111', '00001', '00010', '00100', '01000', '01000', '01000'],
    '8': ['01110', '10001', '10001', '01110', '10001', '10001', '01110'],
    '9': ['01110', '10001', '10001', '01111', '00001', '00010', '01100'],
    'X2': ['00000', '10001', '01010', '00100', '01010', '10001', '00000'],
    '/': ['00001', '00010', '00010', '00100', '01000', '01000', '10000'],
    '-': ['00000', '00000', '00000', '11111', '00000', '00000', '00000'],
    '!': ['00100', '00100', '00100', '00100', '00100', '00000', '00100'],
    ' ': ['00000'] * 7,
}


def text(b, s, x, y, col, sh=None, sp=1):
    cx = x
    for ch in s.upper():
        g = FONT.get(ch)
        if g is None:
            cx += 4
            continue
        for j in range(7):
            for i in range(5):
                if g[j][i] == '1':
                    if sh:
                        b.px(cx + i + 1, y + j + 1, sh)
                    b.px(cx + i, y + j, col)
        cx += 6 + sp
    return cx


def text_w(s, sp=1):
    return sum(6 + sp for _ in s)


def wrap_words(s, maxw, sp=1):
    """按词折行（像素字体字宽固定，直接按字符数算）"""
    rows, cur = [], ''
    for w in s.split(' '):
        t = (cur + ' ' + w) if cur else w
        if cur and len(t) * (6 + sp) > maxw:
            rows.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        rows.append(cur)
    return rows


# ----------------------------------------------------------------- 背景层（预计算一次）
def build_mountains():
    w = 420
    R = rng(7)
    pts, peaks = [], []
    x, hi = -10, True
    while x < w + 40:
        y = 62 + R() * 18 if hi else 92 + R() * 10
        pts.append((x, y))
        if hi:
            peaks.append((x, y))
        x += 16 + R() * 22
        hi = not hi
    top = np.full(w, 120.0, np.float32)
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        for xx in range(int(math.ceil(ax)), int(bx)):
            if 0 <= xx < w:
                top[xx] = round(ay + (by - ay) * (xx - ax) / (bx - ax) + (1 if hsh(xx, 3) < 0.25 else 0))
    d = np.zeros(w * IH, np.uint8)
    for xx in range(w):
        t = top[xx]
        pk = min(peaks, key=lambda p: abs(p[0] - xx))
        for yy in range(int(t), IH):
            if yy < t:
                continue
            edge = pk[0] - (yy - pk[1]) * 0.35
            lit = xx + (bay(xx, yy) * 3.0 - 1.5) >= edge
            if yy > 112 and (yy - 112) / 14 > bay(xx, yy):
                c = E['mist']
            elif pk[1] < 76 and yy < pk[1] + 6 - abs(xx - pk[0]) * 0.3 + (1 if hsh(xx, 9) < 0.3 else 0):
                c = E['mS']
            else:
                c = E['mL'] if lit else E['mD']
            d[yy * w + xx] = c
    return dict(w=w, d=d)


def build_mid():
    """中景：松林冠层 + 岩壁瀑布"""
    w = 440
    R = rng(11)
    ridge = lambda x: round(111 + 4 * math.sin(x * 0.043) + 3 * math.sin(x * 0.11 + 1.3))
    CL0, CL1, CLT = 118, 166, 96
    canopy = np.zeros(w, np.int16)
    tipc = np.zeros(w, np.int16)
    x = 0
    while x < w:
        tw = 4 + int(R() * 4)
        th = 3 + int(R() * 5)
        for i in range(min(tw, w - x)):
            u = abs(i - (tw - 1) / 2) / ((tw + 1) / 2)
            canopy[x + i] = round(th * (1 - u))
            tipc[x + i] = x + (tw >> 1)
        x += tw
    bush = np.full(w, 999, np.int16)
    bushC = np.zeros(w, np.int16)
    R2 = rng(12)
    bx, k = -3, 0
    while bx < w + 6:
        r = 3 + int(R2() * 3)
        cy = 127 + (3 if (k & 1) else 0) + int(R2() * 2)
        for i in range(-r, r + 1):
            xx = bx + i
            if xx < 0 or xx >= w:
                continue
            t = round(cy - math.sqrt(max(0.0, (r + 0.4) ** 2 - i * i)) * 0.85)
            if t < bush[xx]:
                bush[xx] = t
                bushC[xx] = bx
        bx += r + 1 + int(R2() * 3)
        k += 1
    WF_X, WF_W = 137, 9
    d = np.zeros(w * IH, np.uint8)
    for xx in range(w):
        for yy in range(IH):
            s = 0
            if CL0 <= xx < CL1:
                t = CLT + (CL0 + 4 - xx if xx < CL0 + 4 else 0) + (xx - (CL1 - 5) if xx >= CL1 - 5 else 0)
                if yy >= t:
                    FY = 124
                    if FY <= yy < FY + 3 and WF_X - 2 <= xx < WF_X + WF_W + 2:
                        kk = yy - FY
                        s = E['w3'] if (kk == 0 or (kk == 1 and ((xx + yy) & 1)) or (kk == 2 and bay(xx, yy) < 0.25)) else WS[(xx + yy) & 3]
                    elif FY + 3 <= yy < FY + 6 and WF_X - 3 <= xx < WF_X + WF_W + 3:
                        s = E['w0'] if yy == FY + 5 else WS[(math.floor((xx + (yy & 1) * 2) / 3)) & 3]
                    elif WF_X <= xx < WF_X + WF_W and CLT + 1 <= yy < FY:
                        if yy < CLT + 3:
                            s = E['w3']
                        else:
                            g = 1 if (xx == WF_X or xx == WF_X + WF_W - 1) else (0 if hsh(xx, 41) < 0.5 else 1)
                            s = WFG[g][(yy + int(hsh(xx, 43) * 8)) & 7]
                    elif yy < t + 2:
                        s = E['fL'] if yy == t else E['fM']
                    elif xx >= CL1 - 7 or (WF_X + WF_W < xx < WF_X + WF_W + 2):
                        s = E['rL']
                    elif xx < CL0 + 6 or (WF_X - 2 <= xx < WF_X):
                        s = E['rD']
                    elif (yy - t) % 6 == 3 and hsh(xx >> 2, yy) < 0.65:
                        s = E['rD']
                    elif yy > 126 and (yy - 126) / 18 > bay(xx, yy):
                        s = E['rD']
                    else:
                        s = E['rL'] if hsh(xx, yy) < 0.07 else E['rM']
                    d[yy * w + xx] = s
                    continue
            top = ridge(xx) - canopy[xx]
            if yy < top:
                continue
            lit = xx > tipc[xx] and yy < ridge(xx) + 2
            if yy < ridge(xx) + 1:
                s = E['fL'] if lit else (E['fD'] if xx < tipc[xx] else E['fM'])
            elif yy >= bush[xx]:
                lit2 = xx > bushC[xx]
                if yy == bush[xx]:
                    s = E['fL'] if (lit2 and hsh(xx, 51) < 0.7) else E['fM']
                elif yy == bush[xx] + 1 and lit2 and hsh(xx, 52) < 0.35:
                    s = E['fL']
                else:
                    s = E['fD'] if (yy - bush[xx] - 4) / 6 > bay(xx, yy) else E['fM']
            elif yy > 120 and (yy - 120) / 12 > bay(xx, yy):
                s = E['fD']
            else:
                cg = (xx + 60) // 6
                dy = yy - ridge(xx) - 1 + int(hsh(cg, 31) * 5)
                row, r, q = dy // 5, dy % 5, (xx + 60) % 6
                if r == 0 and q == 3 and hsh(cg, row) < 0.7:
                    s = E['fL']
                elif r == 1 and (q == 2 or q == 4):
                    s = E['fM']
                elif r == 4 and q != 3:
                    s = E['fD']
                else:
                    s = E['fM']
            if s:
                d[yy * w + xx] = s
    # 岩壁与林线上更高的孤松
    x = 6
    while x < w:
        if not (WF_X - 4 < x < WF_X + WF_W + 3):
            on_cliff = CL0 + 4 <= x < CL1 - 5
            base = CLT + 1 if on_cliff else ridge(x) - 1
            h = (12 if on_cliff else 9) + int(R() * 10)
            tier = max(1, math.ceil(h / 3))
            for r in range(h):
                k2 = r // tier
                within = r % tier
                half = int((within + 1) * (0.7 + k2 * 0.35))
                yy = base - h + r
                for dx in range(-half, half + 1):
                    xx2 = x + dx
                    if 0 <= xx2 < w and 0 <= yy < IH:
                        d[yy * w + xx2] = E['fL'] if (dx == half and dx > 0) else (E['fM'] if dx >= 0 else E['fD'])
        x += 12 + int(R() * 22)
    return dict(w=w, d=d)


def build_hills():
    w = 500
    R = rng(23)
    bumps = []
    x = -10
    while x < w + 20:
        bumps.append((x, 12 + R() * 11))
        x += 20 + R() * 20
    d = np.zeros(w * IH, np.uint8)
    for xx in range(w):
        for yy in range(IH):
            best = None
            for cx, r in bumps:
                cy = GROUND + r * 0.3
                dd = math.hypot(xx - cx, (yy - cy) * 1.15)
                if dd <= r and (best is None or dd - r < best[4]):
                    best = (cx, cy, r, dd, dd - r)
            if best is None:
                continue
            rim = best[2] - best[3]
            if rim < 1.5 and xx > best[0] - best[2] * 0.3:
                s = E['hL']
            elif rim < 2.5 and (xx + yy) % 3 == 0 and xx > best[0]:
                s = E['hL']
            elif yy > 138 and (yy - 138) / 14 > bay(xx, yy):
                s = E['hD']
            elif hsh(xx >> 1, yy >> 1) < 0.08:
                s = E['hL']
            else:
                s = E['hM']
            d[yy * w + xx] = s
    return dict(w=w, d=d)


MT = build_mountains()
MID = build_mid()
HILLS = build_hills()

CLOUDS = []
_R = rng(31)
for _i in range(9):
    _bumps = []
    _w = 18 + int(_R() * 22)
    _h = 8 + int(_R() * 6)
    for _b in range(3 + int(_R() * 3)):
        _bumps.append((4 + _R() * (_w - 8), 2 + _R() * (_h - 3)))
    CLOUDS.append(dict(x=_i * 47 + int(_R() * 20), y=8 + int(_R() * 34), w=_w, h=_h, bumps=_bumps))


def blit_layer(b, L, off, y0=0, y1=IH):
    w = L['w']
    d = L['d'].reshape(IH, w)
    for y in range(y0, y1):
        for x in range(IW):
            r = off + x
            if 0 <= r < w:
                s = d[y, r]
                if s:
                    b.d[y * IW + x] = s


# ----------------------------------------------------------------- 世界状态（闭式）
SKID = [0, 2, 3, 4, 5, 6, 7, 7, 8, 8, 8, 8, 8]
X0 = 150
CAM_END = 260
fStop, fSkid = F(CUES['stop']), F(CUES['skid'])
J1, J2, STOMP, L2 = F(CUES['jumps'][0]), F(CUES['jumps'][1]), F(CUES['stomp']), F(CUES['lands'][1])
FGET, FCHEER, FLINCH = F(CUES['item_get']), F(CUES['cheer']), F(CUES['flinch'])
CHEST_X = 424
BR0W, BR1W = 300, 352


def hx(f):
    if f <= fSkid:
        return X0 + 2 * f
    return X0 + 2 * fSkid + SKID[min(f - fSkid, 12)]


def cam_x(f):
    r = hx(f) - 96
    if r < CAM_END - 6:
        return int(r)
    return int(min(CAM_END, CAM_END - 6 + max(0.0, f - (CAM_END - 6 - (hx(0) - 96)) / 2.0)))


def hero_h(f):
    if J1 <= f < J1 + 18:
        s = (f - J1) / 18.0
        return round(112 * s * (1 - s))
    if J2 <= f <= STOMP:
        s = (f - J2) / 13.21
        return round(96 * s * (1 - s))
    if STOMP < f < L2:
        u = (f - STOMP) / float(L2 - STOMP)
        return round(8 * (1 - u) + 72 * u * (1 - u))
    return 0


def bridge_sag(wx):
    return round(2 * math.sin(math.pi * (wx - BR0W) / (BR1W - BR0W))) if BR0W <= wx < BR1W else 0


COINS = [(F(t), hx(F(t)) + 8, GROUND - hero_h(F(t)) - 10) for t in CUES['coins']]
SLIME_X = hx(STOMP) + 8


def score_at(f):
    s, c = 0, 0
    for cf, _, _ in COINS:
        if f >= cf:
            s += 100
            c += 1
    if f >= STOMP:
        s += 500
    return s, c


# ----------------------------------------------------------------- 绘制
def draw_sky(b, f, cx):
    a, bb, t = stage_of(f)
    # 天空渐变：用 5 条语义槽
    band = [E['s0'], E['s1'], E['s2'], E['s3'], E['s4']]
    edges = [0, 34, 62, 86, 106, 150]
    for i in range(5):
        b.rect(0, edges[i], IW, edges[i + 1] - edges[i], band[i])
    # 条带边界用 4×4 有序抖动过渡（像素画里最经典的渐变手法）
    for i in range(4):
        yb = edges[i + 1]
        for y in range(max(0, yb - 3), min(IH, yb + 3)):
            hi = y >= yb
            for x in range(IW):
                if (bay(x, y) < 0.5) != hi:
                    b.px(x, y, band[i + 1] if hi else band[i])
    # 星星（夜里出现）
    if f >= FNIGHT - 6:
        k = min(1.0, (f - (FNIGHT - 6)) / 6.0)
        if k > 0.2:
            for i in range(70):
                sx = int(hsh(i, 1) * IW)
                sy = int(hsh(i, 2) * 70)
                if hsh(i, 3) < k:
                    b.px(sx, sy, STS[i & 3])
    # 太阳 / 月亮
    sa, sb, st = stage_of(f)
    prog = f / float(F(CUES['end']))
    sunx = 232 - int(150 * prog)
    suny = 74 - int(46 * math.sin(min(1.0, prog * 1.35) * math.pi * 0.85))
    if f < FNIGHT + 4:
        r = 13
        for j in range(-r, r + 1):
            for i in range(-r, r + 1):
                d = math.hypot(i, j)
                if d <= r:
                    c = E['sun'] if d < r * 0.62 else E['sunG']
                    b.px(sunx + i, suny + j, c)
    else:
        r = 9
        for j in range(-r, r + 1):
            for i in range(-r, r + 1):
                d = math.hypot(i, j)
                if d <= r and not (i > 2 and j < -2 and d > 5):
                    b.px(sunx + i, suny + j, E['clL'] if d < r * 0.6 else E['clD'])
    # 云
    off = int(cx * 0.12)
    for c in CLOUDS:
        x0 = ((c['x'] - off) % 420 + 420) % 420 - 50
        by = c['h'] - 1
        for j in range(c['h']):
            for i in range(c['w']):
                inn = False
                rim = 0.0
                for bx2, r2 in c['bumps']:
                    dd = math.hypot(i - bx2, (j - by) * 1.25)
                    if dd <= r2:
                        inn = True
                        rim = max(rim, r2 - dd)
                if not inn:
                    continue
                shade = j >= by - 1 or (j >= by - 3 and bay(x0 + i, j) < 0.5)
                b.px(x0 + i, c['y'] + j, E['clD'] if shade else E['clL'])


def draw_ground(b, f, cx):
    for y in range(138, IH):
        for x in range(IW):
            wx = x + cx
            s = 0
            if BR0W <= wx < BR1W:
                sag = bridge_sag(wx)
                py = y - sag
                if 150 <= py <= 153:
                    s = E['dD'] if (wx - BR0W) % 4 == 3 else (E['dL'] if py == 150 else (E['dD'] if py == 153 else E['dM']))
                elif y >= 154 + sag:
                    deep = y - 156
                    dash = ((y * 7 + (wx >> 2)) & 3) == 0
                    if dash and hsh(wx >> 2, y) < 0.17 and ((wx // 3 + (f >> 2)) & 3) == 0:
                        s = E['rvG']
                    elif dash or (y == 154 + sag and (wx & 3) < 2):
                        s = WS[(math.floor((wx + (y & 1) * 2) / 3)) & 3]
                    else:
                        s = E['rvD'] if deep > 10 else E['rvB']
                rope = 143 + round(4 * math.sin(math.pi * (wx - BR0W) / (BR1W - BR0W)))
                if y == rope:
                    s = E['dD']
                if (wx - BR0W) % 8 == 4 and y > rope and py < 150:
                    s = E['dD']
                if (wx - BR0W < 2 or BR1W - wx <= 2) and 141 <= y < 154:
                    s = E['dL'] if (wx - BR0W == 0 or BR1W - wx == 1) else E['dD']
            elif y < 150:
                if y == 149 and hsh(wx, 1) < 0.35:
                    s = E['gM']
                elif y == 148 and hsh(wx, 1) < 0.1:
                    s = E['gL']
                if hsh(wx, 77) < 0.035:
                    s = E['flw'] if y == 147 else (E['gD'] if y >= 148 else s)
            else:
                bank = wx == BR0W - 1 or wx == BR1W
                if y == 150:
                    s = E['gM'] if hsh(wx, 2) < 0.15 else E['gL']
                elif y <= 152:
                    s = E['gL'] if hsh(wx, y) < 0.08 else E['gM']
                elif y == 153:
                    s = E['gD']
                else:
                    drip = int(hsh(wx >> 1, 5) * 3)
                    if y < 154 + drip and y <= 155:
                        s = E['gD']
                    else:
                        ty = y - 156
                        row = ty // 12
                        tx = (wx + (row & 1) * 8) & 15
                        if tx == 0 or ty % 12 == 11 or ty < 0:
                            s = E['dD']
                        elif tx == 1 or ty % 12 == 0:
                            s = E['dL']
                        else:
                            s = E['dL'] if hsh(wx, y) < 0.05 else (E['dD'] if hsh(wx + 1, y - 1) < 0.05 else E['dM'])
                if bank and y > 150:
                    s = E['dD']
            if s:
                b.d[y * IW + x] = s


def draw_rays(b, f):
    tau = f - FLASH
    if tau < 0:
        return
    step = -1 if f < F(CUES['rays_off']) else (f - F(CUES['rays_off'])) // 3
    if step >= 2:
        return
    cx = CHEST_X - CAM_END + 10
    cy = GROUND - 11
    # 半径必须留在画布内：开箱的星芒是局部光效，不是全屏扫射
    # （原先最大 190px，在 320x180 画布上会把主角和 logo 一起吞掉）
    if step == 0:
        R = 26
    elif step == 1:
        R = 14
    elif tau < 6:
        R = 30 + tau * 8                                   # 爆发 30 → 78
    else:
        R = max(24, 78 - (tau - 6) * 4) + (2 if (f // 6) & 1 else 0)
    core = 8 if step == 0 else (0 if step == 1 else 12)
    rot = (f // 3) * 0.035
    for y in range(max(0, cy - R), GROUND):
        for x in range(max(0, cx - R), min(IW, cx + R)):
            dx, dy = x - cx, y - cy
            d = math.hypot(dx, dy)
            if d > R:
                continue
            a = math.atan2(dy, dx) + rot
            band = int((a / (2 * math.pi) + 1) * 18) & 1
            fall = 1 - d / R
            if d < core:
                continue
            if band and fall * 1.3 > bay(x, y):
                b.px(x, y, _m(15) if d < R * 0.4 else _m(14))


def draw_hero(b, f, cx):
    h = hero_h(f)
    x = hx(f) - cx
    sag = bridge_sag(hx(f) + 8)
    if f >= FGET or f >= FCHEER or f >= FLASH:
        s = HERO_JUMP if (f >= FLASH) else HERO
    else:
        s = HERO_JUMP if h > 0 else HERO
    b.blit(s, x - 6, GROUND - 20 - h + sag + 1)


def draw_entities(b, f, cx):
    for cf, cxp, cyp in COINS:
        sx = cxp - cx - 4
        if f < cf:
            b.blit(COIN[(f // 3 + cxp) & 3], sx, cyp - 5)
        elif f < cf + 9:
            a = f - cf
            s = SPARK[1 if a < 3 else (2 if a < 6 else 0)]
            b.blit(s, cxp - cx - (s['w'] >> 1), cyp - (s['h'] >> 1))
    sx = SLIME_X - cx
    if f < STOMP:
        A = (f // 5) & 1 == 0
        s = SLIME_A if A else SLIME_B
        b.blit(s, sx - 7, GROUND - (9 if A else 7))
    elif f < STOMP + 7:
        b.blit(SLIME_B, sx - 7, GROUND - 3)
    elif f < STOMP + 16:
        a = f - STOMP - 7
        s = PUFF[min(2, a // 3)]
        b.blit(s, sx - (s['w'] >> 1), GROUND - 6 - a // 3)
    # 宝箱
    chx = CHEST_X - cx
    if chx > -30 and chx < IW + 30:
        shake = 0
        if F(CUES['chest_shake'][0]) <= f < FLASH:
            shake = 1 if (f & 1) else -1
        if f < FLASH:
            b.blit(CHEST, chx - 9 + shake, GROUND - 12)
        else:
            b.blit(CHEST_OPEN, chx - 9, GROUND - 12)
            b.blit(GEM, chx - 3, GROUND - 12 - min(22, (f - FLASH) * 2))


def draw_hud(b, f):
    score, cnt = score_at(f)
    text(b, 'SCORE', 8, 6, _m(8), _m(0))
    text(b, '%06d' % score, 8, 16, _m(15), _m(0))
    text(b, 'X%02d' % cnt, IW - 52, 6, _m(8), _m(0))


def draw_box(b, f):
    fO, fC = F(CUES['box_open']), F(CUES['box_close'])
    if not (fO <= f < fC):
        return
    x, y, w, h = 92, 96, 150, 44
    b.rect(x, y, w, h, _m(8))
    b.rect(x + 2, y + 2, w - 4, h - 4, _m(0))
    b.rect(x + 3, y + 3, w - 6, h - 6, _m(31))
    rows = wrap_words('A MYSTERIOUS CHEST! PRESS X TO OPEN. WHAT IS INSIDE...', 126)
    n = 0
    for tt in CUES['type']:
        if f >= F(tt):
            n += 1
    k = max(0, n * 2)                      # 打字机：已显示字符数
    for i, r in enumerate(rows[:3]):
        if k <= 0:
            break
        text(b, r[:k], x + 8, y + 9 + i * 11, _m(0))
        k -= len(r) + 1


def draw_logo(b, f, cx):
    if f < F(CUES['logo']):
        return
    # 「像素风」用 5×7 字体放大 3 倍 + 英文副标
    k = min(1, (f - F(CUES['logo'])) / 4)
    y = 30 + int((1 - k) * 20)
    text(b, 'PIXEL QUEST', 118, y, _m(15), _m(0), sp=2)
    text(b, 'PIXEL ART', 148, y + 14, _m(8), _m(0), sp=2)
    if f >= F(CUES['press_start']) and ((f // 15) & 1) == 0:
        text(b, 'PRESS START', 128, 148, _m(8), _m(0), sp=1)


# ----------------------------------------------------------------- CRT 合成
def crt_pass(idx_rgb, t, f):
    """整数放大 6 倍 + 扫描线 + 荫罩 + 桶形畸变 + 暗角"""
    img = Image.fromarray(idx_rgb, "RGB").resize((W, H), Image.NEAREST)
    a = np.asarray(img, np.float32) / 255.0

    xs = (np.arange(W, dtype=np.float32)[None, :] + 0.5)
    ys = (np.arange(H, dtype=np.float32)[:, None] + 0.5)
    nx = (xs / W - 0.5) * 2.0
    ny = (ys / H - 0.5) * 2.0
    r2 = nx * nx + ny * ny
    # 桶形畸变
    k = 1.0 + 0.032 * r2 + 0.012 * r2 * r2
    sx = (nx * k * 0.5 + 0.5) * W - 0.5
    sy = (ny * k * 0.5 + 0.5) * H - 0.5
    SX = np.broadcast_to(sx, (H, W))
    SY = np.broadcast_to(sy, (H, W))
    x0 = np.clip(np.floor(SX).astype(np.int32), 0, W - 1)
    y0 = np.clip(np.floor(SY).astype(np.int32), 0, H - 1)
    fx = np.clip(SX - x0, 0, 1)[..., None]
    fy = np.clip(SY - y0, 0, 1)[..., None]
    x1 = np.minimum(x0 + 1, W - 1)
    y1 = np.minimum(y0 + 1, H - 1)
    c00 = a[y0, x0]
    c10 = a[y0, x1]
    c01 = a[y1, x0]
    c11 = a[y1, x1]
    top = c00 + (c10 - c00) * fx
    bot = c01 + (c11 - c01) * fx
    c = top + (bot - top) * fy
    # 出屏即黑
    outside = ((sx < -0.5) | (sx > W - 0.5) | (sy < -0.5) | (sy > H - 0.5))
    c = np.where(np.broadcast_to(outside, (H, W))[..., None], 0.0, c)

    # 扫描线（每 6 个输出行一组，与 1 个源行对齐）
    row = (np.arange(H, dtype=np.float32)[:, None] % SCALE)
    scan = 1.0 - 0.30 * np.exp(-((row - SCALE * 0.5) ** 2) / 1.1)
    c = c * np.broadcast_to(scan, (H, W))[..., None]
    # 荫罩：每 3 个输出列循环 R/G/B
    col = (np.arange(W, dtype=np.int32)[None, :] % 3)
    mask = np.ones((H, W, 3), np.float32)
    for ch in range(3):
        mask[..., ch] = np.where(np.broadcast_to(col == ch, (H, W)), 1.22, 0.62)
    c = c * mask
    # 暗角 + 轻微辉光
    vig = 1.0 - 0.42 * np.clip(r2 * 0.62, 0, 1) ** 1.3
    c = c * vig[..., None]
    # 开机/关机
    crt_on = min(1.0, t / 0.35)
    if t < 0.35:
        c = c * crt_on
        line = np.exp(-((ys - H * 0.5) ** 2) / 60.0)
        c = c + line[..., None] * np.array([0.6, 0.7, 1.0], np.float32) * (1 - crt_on)
    return np.clip(c, 0, 1)


# ----------------------------------------------------------------- 单帧
LAYERS = None


def render_frame(t):
    f = int(round(t * ANIM_FPS))
    lut = make_lut(f)
    b = Buf()
    cx = cam_x(f)
    draw_sky(b, f, cx)
    blit_layer(b, MT, int(cx * 0.125), 40, IH)
    blit_layer(b, MID, int(cx * 0.30), 60, IH)
    blit_layer(b, HILLS, int(cx * 0.55), 118, IH)
    draw_ground(b, f, cx)
    draw_rays(b, f)
    draw_entities(b, f, cx)
    draw_hero(b, f, cx)
    draw_box(b, f)
    draw_hud(b, f)
    draw_logo(b, f, cx)
    rgb = MP[lut[b.d]].astype(np.uint8).reshape(IH, IW, 3)
    return crt_pass(rgb, t, f)


# ----------------------------------------------------------------- CLI
def save(img, path):
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(path, quality=95)


def cmd_one(t, out):
    t0 = time.time()
    save(render_frame(t), out)
    print("%s  t=%.2fs  %.1fs" % (out, t, time.time() - t0))


def _worker(args):
    i, = args
    save(render_frame(i / FPS), os.path.join(ROOT, "frames", "f_%04d.png" % i))
    return i


def cmd_all(workers=6, lo=0, hi=None):
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
            if done % 40 == 0 or done == len(idx):
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
        cmd_all(int(sys.argv[2]) if len(sys.argv) > 2 else 6)
    elif cmd == "range":
        cmd_all(int(sys.argv[4]) if len(sys.argv) > 4 else 6, int(sys.argv[2]), int(sys.argv[3]))
    else:
        for t in [0.3, 1.0, 2.0, 2.5, 3.4, 4.5, 5.2, 6.0, 6.5, 7.3, 8.2, 9.0]:
            cmd_one(t, os.path.join(ROOT, "prev_%.2f.png" % t))
