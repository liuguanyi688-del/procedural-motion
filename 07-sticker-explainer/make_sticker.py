# -*- coding: utf-8 -*-
"""07 · 贴纸风科普（STICKER EXPLAINER）：超大画布 + 相机运镜
一部手机里藏着多少种元素？标题卡 → 推进屏幕 → 元素贴纸与图表 → 拉远。
60fps。用法: python make_sticker.py preview | all
"""
import math, sys, os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(OUT, "frames")

W, H = 1600, 1000
SS = 2
CW, CH = 3200, 2000                    # 超大画布
FPS = 60
DUR = 10.0

BG      = (230, 230, 233)
DOT     = (212, 212, 219)
INK     = (26, 28, 33)
ORANGE  = (240, 90, 28)
GRAY    = (120, 122, 130)
SHADOW  = (198, 198, 206)
STICKER = (255, 255, 255)
BODY    = (24, 26, 31)
NAVY    = (16, 22, 40)

def clamp01(x): return max(0.0, min(1.0, x))
def eio(x):
    x = clamp01(x)
    return 4*x*x*x if x < 0.5 else 1 - (-2*x+2)**3 / 2
def eob(x, s=1.70158):
    x = clamp01(x); x -= 1
    return 1 + (s+1)*x**3 + s*x**2
def lerp(a, b, p): return a + (b - a) * p
def mixc(c1, c2, p): return tuple(int(round(lerp(a, b, p))) for a, b in zip(c1, c2))

F_TITLE = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 128, index=0)
F_EN    = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 42, index=0)
F_TAG   = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 34, index=0)
F_SMALL = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 32, index=0)
F_SYM   = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 96)
F_SYM2  = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 44)
F_CN    = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 40, index=0)
F_NOTE  = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 28, index=0)
F_HEAD  = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 58, index=0)
F_TAB   = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 30, index=0)

def dashed_rect(d, x0, y0, x1, y1, color, w=3, dash=12, gap=9):
    def dline(a, b):
        length = math.dist(a, b)
        n = int(length // (dash + gap)) + 1
        for k in range(n):
            p0 = k * (dash + gap)
            p1 = min(p0 + dash, length)
            if p0 >= length:
                break
            t0, t1 = p0 / length, p1 / length
            d.line([lerp(a[0], b[0], t0), lerp(a[1], b[1], t0),
                    lerp(a[0], b[0], t1), lerp(a[1], b[1], t1)], fill=color, width=w)
    dline((x0, y0), (x1, y0)); dline((x1, y0), (x1, y1))
    dline((x1, y1), (x0, y1)); dline((x0, y1), (x0, y0))

def sticker_rect(d, x0, y0, x1, y1, r, fill, out_w=0, shadow=True, sh=(26, 30)):
    if shadow:
        d.rounded_rectangle([x0 + sh[0], y0 + sh[1], x1 + sh[0], y1 + sh[1]],
                            radius=r, fill=SHADOW)
    if out_w:
        d.rounded_rectangle([x0 - out_w, y0 - out_w, x1 + out_w, y1 + out_w],
                            radius=r + out_w, fill=STICKER)
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill)

def phone_screen_gradient(d, x0, y0, x1, y1):
    stops = [(20, 34, 78), (36, 92, 180), (238, 130, 40), (216, 60, 30)]
    h = y1 - y0
    for row in range(int(h)):
        p = row / max(1, h - 1)
        seg = min(int(p * (len(stops) - 1)), len(stops) - 2)
        lp = p * (len(stops) - 1) - seg
        col = mixc(stops[seg], stops[seg + 1], lp)
        y = y0 + row
        wave = math.sin(p * 9 + 1.2) * 26
        d.line([x0 - 6 + wave, y, x1 + 6 + wave, y], fill=col)

# ---------------- 内容元素（画布坐标） ----------------
def draw_title_card(d, t):
    p = lambda t0, dur=0.5: eob((t - t0) / dur, s=1.8)
    fade = lambda t0, dur=0.5: eio((t - t0) / dur)

    # 橙色小方块 + 栏目标签
    a = p(0.20)
    if a > 0.01:
        d.rectangle([160, 320 + 30 * (1 - a), 208, 368 + 30 * (1 - a)], fill=ORANGE)
        d.text((238, 322 + 30 * (1 - a)), "硬核拆解  EXPLAINER · NO.001", font=F_TAG,
               fill=GRAY if a > 0.9 else mixc(BG, GRAY, a))
    # 主标题两行（上滑入场）
    a = p(0.35)
    if a > 0.01:
        dy = 60 * (1 - a)
        d.text((152, 500 + dy), "一部手机里，", font=F_TITLE, fill=INK)
    a = p(0.50)
    if a > 0.01:
        dy = 60 * (1 - a)
        d.text((152, 700 + dy), "藏着多少种元素？", font=F_TITLE, fill=INK)
    # 橙色高亮条
    a = p(0.72, 0.45)
    if a > 0.01:
        w = 1450 * a
        d.rounded_rectangle([152, 940, 152 + w, 1010], radius=14, fill=ORANGE)
    a = fade(0.85)
    if a > 0.01:
        d.text((152, 1064), "HOW MANY ELEMENTS HIDE INSIDE ONE PHONE?",
               font=F_EN, fill=mixc(BG, GRAY, a))
    a = fade(1.00)
    if a > 0.01:
        d.text((152, 1180), "拆开一部智能手机，逐一对照元素周期表",
               font=F_SMALL, fill=mixc(BG, GRAY, a))
    # 虚线占位框
    a = p(1.15, 0.5)
    if a > 0.01:
        col = mixc(BG, (188, 188, 196), a)
        for k in range(10):
            x0 = 152 + k * 150
            dashed_rect(d, x0, 1330, x0 + 118, 1424, col, w=4)
    # 底部实验室标
    a = fade(1.35)
    if a > 0.01:
        d.rectangle([152, 1768, 186, 1802], fill=ORANGE)
        d.text((206, 1762), "格物  GEWU LAB", font=F_TAG, fill=mixc(BG, INK, a))
    # 右下角 tab 栏
    a = fade(1.5)
    if a > 0.01:
        tabs = [("01 拆解", True), ("02 周期表", False), ("03 分类", False), ("04 产地", False)]
        for k, (txt, act) in enumerate(tabs):
            x = 2170 + k * 250
            col = ORANGE if act else mixc(BG, GRAY, a)
            d.text((x, 1806), txt, font=F_TAB, fill=col)
            if act:
                d.rounded_rectangle([x, 1860, x + 130, 1870], radius=5, fill=ORANGE)

def draw_phone(d, t):
    p = eob((t - 0.45) / 0.6, s=1.6)
    if p <= 0.01:
        return
    cx, cy = 2600, 1000
    bw, bh = 780, 940
    sc = p
    x0, y0 = cx - bw / 2 * sc, cy - bh / 2 * sc
    x1, y1 = cx + bw / 2 * sc, cy + bh / 2 * sc
    r = 90 * sc
    # 贴纸白描边 + 投影
    d.rounded_rectangle([x0 - 18 + 30, y0 - 18 + 34, x1 + 18 + 30, y1 + 18 + 34],
                        radius=r + 18, fill=SHADOW)
    d.rounded_rectangle([x0 - 18, y0 - 18, x1 + 18, y1 + 18], radius=r + 18, fill=STICKER)
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=BODY)
    sx0, sy0, sx1, sy1 = x0 + 46, y0 + 52, x1 - 46, y1 - 52
    phone_screen_gradient(d, sx0, sy0, sx1, sy1)
    # 屏幕高光
    d.rounded_rectangle([sx0, sy0, sx1, sy0 + 60], radius=30, fill=(255, 255, 255, 30))

def screen_app(d, t):
    """推进到屏幕后，屏幕内部显示元素贴纸与图表（画布坐标）"""
    pop = lambda t0, dur=0.45: eob((t - t0) / dur, s=1.9)
    if t < 4.45:
        return
    sx0, sy0, sx1, sy1 = 2260, 580, 2940, 1420
    d.rounded_rectangle([sx0, sy0, sx1, sy1], radius=8, fill=NAVY)
    a = pop(4.55)
    if a > 0.01:
        d.text((sx0 + 36, sy0 + 34), "手机里的元素", font=F_HEAD,
               fill=mixc(NAVY, (255, 255, 255), a))
        d.text((sx0 + 36, sy0 + 108), "ELEMENTS IN A PHONE", font=F_NOTE,
               fill=mixc(NAVY, (150, 160, 200), a))
    tiles = [
        ("Fe", "铁", "外壳骨架"), ("Cu", "铜", "电路导线"),
        ("Li", "锂", "电池心脏"), ("Co", "钴", "电池正极"),
    ]
    cols = [(96, 170, 250), (250, 150, 70), (120, 220, 170), (230, 120, 190)]
    for k, (sym, cn, note) in enumerate(tiles):
        a = pop(4.75 + k * 0.14)
        if a <= 0.01:
            continue
        col = cols[k]
        tx = sx0 + 36 + (k % 2) * 330
        ty = sy0 + 180 + (k // 2) * 190
        sc = 0.8 + 0.2 * a
        w, h = 296 * sc, 158 * sc
        x0, y0 = tx + (296 - w) / 2, ty + (158 - h) / 2
        x1, y1 = x0 + w, y0 + h
        d.rounded_rectangle([x0 - 10, y0 - 10, x1 + 10, y1 + 10], radius=18, fill=STICKER)
        d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=mixc(NAVY, col, 0.16))
        d.text((x0 + 20, y0 + 10), sym, font=F_SYM2, fill=col)
        d.text((x0 + 20 + 118 * sc, y0 + 18), cn, font=F_CN,
               fill=mixc(NAVY, (255, 255, 255), a))
        d.text((x0 + 20, y0 + 112), note, font=F_NOTE,
               fill=mixc(NAVY, (170, 178, 205), a))
    # 质量占比条形图贴纸
    a = pop(5.75, 0.55)
    if a > 0.01:
        gx0, gy0, gx1, gy1 = sx0 + 36, sy0 + 640, sx1 - 36, sy1 - 40
        d.rounded_rectangle([gx0 - 10, gy0 - 10, gx1 + 10, gy1 + 10], radius=18, fill=STICKER)
        d.rounded_rectangle([gx0, gy0, gx1, gy1], radius=12, fill=mixc(NAVY, (255, 255, 255), 0.06))
        d.text((gx0 + 22, gy0 + 14), "机身质量占比", font=F_NOTE,
               fill=mixc(NAVY, (255, 255, 255), a))
        bars = [("铁", 0.92, (96, 170, 250)), ("铝", 0.55, (150, 140, 245)),
                ("铜", 0.38, (250, 150, 70)), ("其他", 0.22, (120, 220, 170))]
        bw_total = gx1 - gx0 - 150
        for k, (nm, v, col) in enumerate(bars):
            by = gy0 + 56 + k * 26
            d.text((gx0 + 24, by - 5), nm, font=F_NOTE,
                   fill=mixc(NAVY, (255, 255, 255), a))
            d.rounded_rectangle([gx0 + 92, by, gx0 + 92 + bw_total * v * a, by + 18],
                                radius=9, fill=col)

def draw_dots(d):
    step = 62
    for yy in range(40, CH, step):
        for xx in range(40, CW, step):
            d.ellipse([xx - 4, yy - 4, xx + 4, yy + 4], fill=DOT)

# ---------------- 相机 ----------------
def camera(t):
    """返回 (x0, y0, x1, y1) 画布裁剪窗口（宽高比 1.6）"""
    full = (0, 0, CW, CH)
    # 推进目标：屏幕中心
    def rect_c(cx, cy, w):
        h = w / 1.6
        return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    target = rect_c(2600, 1000, 1500)
    if t < 3.0:
        drift = eio(t / 3.0) * 24
        return (full[0] + drift, full[1], full[2] + drift, full[3])
    if t < 4.6:
        p = eio((t - 3.0) / 1.6)
        return tuple(lerp(full[i], target[i], p) for i in range(4))
    if t < 7.4:
        p = eio((t - 4.6) / 2.8) * 120
        return (target[0] - p * 0.5, target[1] - p * 0.31,
                target[2] + p * 0.5, target[3] + p * 0.31)
    if t < 9.0:
        p = eio((t - 7.4) / 1.6)
        return tuple(lerp(target[i], full[i], p) for i in range(4))
    return full

# ---------------- 渲染 ----------------
def render(f):
    t = f / FPS
    canvas = Image.new("RGB", (CW, CH), BG)
    d = ImageDraw.Draw(canvas)
    draw_dots(d)
    draw_title_card(d, t)
    draw_phone(d, t)
    screen_app(d, t)

    x0, y0, x1, y1 = camera(t)
    x0 = max(0, min(CW - 10, x0)); x1 = max(x0 + 10, min(CW, x1))
    y0 = max(0, min(CH - 10, y0)); y1 = max(y0 + 10, min(CH, y1))
    view = canvas.crop((int(x0), int(y0), int(x1), int(y1))).resize((W, H), Image.LANCZOS)
    return view

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    NF = int(DUR * FPS)
    if mode == "preview":
        for fr in (60, 210, 285, 340, 420, 510, 580):
            render(fr).save(os.path.join(OUT, "prev_%03d.png" % fr))
        print("PREVIEW DONE  %d frames total" % NF)
    else:
        os.makedirs(FRAMES, exist_ok=True)
        for i in range(NF):
            render(i).save(os.path.join(FRAMES, "f_%04d.png" % i))
            if i % 120 == 0:
                print("frame", i, "/", NF)
        print("done:", NF, "frames")
