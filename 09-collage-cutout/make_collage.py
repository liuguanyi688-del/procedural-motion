# -*- coding: utf-8 -*-
"""09 · 拼贴剪贴（COLLAGE · CUT-OUT）：NOGGIN 脑洞季刊
牛皮纸 + 报纸剪块 + 半调网点绅士肖像；剪开脑袋，星云蹦出来。
12fps 逐格步进（渲染 120 帧唯一画面，容器 60fps 每帧×5）。
用法: python make_collage.py preview | all
"""
import math, random, sys, os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(OUT, "frames")

W, H = 1600, 1000
STEP_FPS = 12
NF = 120                                   # 120 帧唯一画面

KRAFT   = (180, 148, 110)
NEWS_BG = (226, 221, 205)
NEWS_IN = (98, 94, 86)
RED     = (198, 40, 36)
SKIN    = (208, 184, 156)
SKIN_D  = (152, 126, 100)
COAT    = (40, 36, 33)
COLLAR  = (232, 227, 214)
HAIR    = (58, 50, 44)
INK_D   = (52, 48, 44)
PAPER   = (238, 233, 218)

def clamp01(x): return max(0.0, min(1.0, x))
def eio(x):
    x = clamp01(x)
    return 4*x*x*x if x < 0.5 else 1 - (-2*x+2)**3 / 2
def eob(x, s=1.70158):
    x = clamp01(x); x -= 1
    return 1 + (s+1)*x**3 + s*x**2
def lerp(a, b, p): return a + (b-a)*p
def mixc(c1, c2, p): return tuple(int(round(a + (b-a)*p)) for a, b in zip(c1, c2))
def step(t, fps=STEP_FPS): return math.floor(t * fps) / fps
def rng0(k): return random.Random(900 + k).uniform(0, 1)

def cap_line(d, a, b, w, col):
    d.line([a[0], a[1], b[0], b[1]], fill=col, width=int(w))
    r = w / 2
    for x, y in (a, b):
        d.ellipse([x-r, y-r, x+r, y+r], fill=col)

# ---------------- 纹理生成（一次性） ----------------
def make_kraft():
    rng = random.Random(11)
    img = Image.new("RGB", (W, H), KRAFT)
    px = img.load()
    for yy in range(0, H, 2):
        for xx in range(0, W, 2):
            n = rng.randint(-13, 11)
            c = px[xx, yy]
            px[xx, yy] = tuple(max(0, min(255, v + n)) for v in c)
    d = ImageDraw.Draw(img)
    for _ in range(240):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        ln = rng.uniform(14, 44); an = rng.uniform(0, math.pi)
        col = mixc(KRAFT, (226, 204, 174), rng.random() * 0.6)
        d.line([x, y, x + math.cos(an)*ln, y + math.sin(an)*ln], fill=col, width=1)
    return img.filter(ImageFilter.GaussianBlur(0.5))

def make_newsprint(w, h, seed, headline=True):
    rng = random.Random(seed)
    img = Image.new("RGB", (w, h), NEWS_BG)
    d = ImageDraw.Draw(img)
    cols = 7
    cw = (w - 36) / cols
    for c in range(cols):
        x0 = 18 + c * cw
        for y in range(24, h - 24, 5):
            if rng.random() < 0.14:
                continue
            lw = cw * rng.uniform(0.55, 0.95)
            d.rectangle([x0, y, x0 + lw, y + 2], fill=mixc(NEWS_BG, NEWS_IN, rng.uniform(0.55, 0.9)))
    if headline:
        d.rectangle([20, 6, w - 20, 16], fill=NEWS_IN)
    return img

def make_nebula(w, h):
    rng = random.Random(33)
    img = Image.new("RGB", (w, h), (16, 26, 32))
    d = ImageDraw.Draw(img)
    blobs = [(0.30, 0.35, 0.40, (28, 105, 105)), (0.62, 0.28, 0.34, (20, 130, 120)),
             (0.48, 0.62, 0.42, (96, 140, 60)), (0.72, 0.55, 0.28, (205, 120, 40)),
             (0.40, 0.80, 0.32, (30, 90, 100)), (0.85, 0.28, 0.22, (240, 150, 60))]
    for bx, by, br, col in blobs:
        for _ in range(9):
            ox, oy = rng.uniform(-0.10, 0.10), rng.uniform(-0.10, 0.10)
            rr = br * rng.uniform(0.35, 0.7)
            c = mixc(col, (10, 20, 26), rng.uniform(0, 0.45))
            d.ellipse([(bx+ox)*w - rr*w, (by+oy)*h - rr*h,
                       (bx+ox)*w + rr*w, (by+oy)*h + rr*h], fill=c)
    for _ in range(70):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        d.ellipse([x-1, y-1, x+1, y+1], fill=(230, 235, 225))
    return img

def dotize(img, cell, bg):
    w, h = img.size
    sw, sh = max(1, w // cell), max(1, h // cell)
    small = img.convert("RGB").resize((sw, sh), Image.LANCZOS)
    out = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(out)
    r = cell * 0.52
    for yy in range(sh):
        for xx in range(sw):
            c = small.getpixel((xx, yy))
            cx, cy = xx*cell + cell/2, yy*cell + cell/2
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    return out

def torn_masks(w, h, y_cut, seed, amp=13):
    rng = random.Random(seed)
    edge = []
    x = 0.0
    while x <= w:
        edge.append((x, y_cut + rng.uniform(-amp, amp)))
        x += rng.uniform(14, 30)
    edge.append((w, y_cut))
    m_up = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m_up).polygon([(0, 0), (w, 0)] + edge[::-1], fill=255)
    m_lo = Image.new("L", (w, h), 255)
    ImageDraw.Draw(m_lo).polygon([(0, 0)] + edge + [(w, 0)], fill=0)
    return m_up, m_lo, edge

def paper_mask(w, h, seed, amp=9):
    """四边锯齿的纸片蒙版"""
    rng = random.Random(seed)
    pts = []
    x = 0.0
    while x <= w:
        pts.append((x, rng.uniform(0, amp))); x += rng.uniform(12, 26)
    y = 0.0
    while y <= h:
        pts.append((w - rng.uniform(0, amp), y)); y += rng.uniform(12, 26)
    x = float(w)
    while x >= 0:
        pts.append((x, h - rng.uniform(0, amp))); x -= rng.uniform(12, 26)
    y = float(h)
    while y >= 0:
        pts.append((rng.uniform(0, amp), y)); y -= rng.uniform(12, 26)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m

def cap_line(d, a, b, w, col):
    d.line([a[0], a[1], b[0], b[1]], fill=col, width=int(w))
    r = w / 2
    for x, y in (a, b):
        d.ellipse([x-r, y-r, x+r, y+r], fill=col)

# ---------------- 肖像（RGBA 520x680） ----------------
def build_portrait():
    img = Image.new("RGBA", (520, 680), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(130, 680), (185, 470), (395, 470), (455, 680)], fill=COAT)
    d.rectangle([246, 330, 334, 500], fill=SKIN_D)                               # 脖子
    d.polygon([(185, 680), (258, 482), (300, 522), (246, 680)], fill=(30, 27, 25))
    d.polygon([(400, 680), (327, 482), (285, 522), (339, 680)], fill=(30, 27, 25))
    d.polygon([(240, 452), (270, 562), (302, 470)], fill=COLLAR)
    d.polygon([(344, 452), (312, 562), (280, 470)], fill=COLLAR)
    d.ellipse([198, 130, 382, 340], fill=SKIN)
    d.ellipse([258, 130, 392, 332], fill=SKIN_D)
    d.ellipse([196, 96, 384, 208], fill=HAIR)
    d.ellipse([150, 148, 208, 258], fill=HAIR)
    d.ellipse([252, 208, 276, 224], fill=INK_D)
    d.ellipse([316, 208, 340, 224], fill=INK_D)
    d.line([262, 192, 300, 188], fill=INK_D, width=5)
    d.line([318, 188, 356, 192], fill=INK_D, width=5)
    d.line([288, 226, 288, 266], fill=INK_D, width=5)
    d.ellipse([260, 282, 334, 312], fill=(70, 60, 52))
    d.arc([258, 300, 338, 340], 20, 160, fill=(45, 40, 36), width=6)
    rgb = dotize(img.convert("RGB"), 7, KRAFT)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(rgb, (0, 0), img.getchannel("A"))
    out = out.resize((620, 810), Image.LANCZOS)
    return out

# ---------------- 单例素材 ----------------
_K = _NL = _NR = _NEB = _POR = None
_MU = _ML = _EDGE = None
_NEBO = None                                # 星云网点化

def assets():
    global _K, _NL, _NR, _NEB, _POR, _MU, _ML, _EDGE, _NEBO
    if _K is None:
        _K = make_kraft()
        _NL = make_newsprint(340, 620, 5).convert("RGBA")
        _NL.putalpha(paper_mask(340, 620, 5))
        _NR = make_newsprint(460, 640, 9).convert("RGBA")
        _NR.putalpha(paper_mask(460, 640, 9))
        _NEB = make_nebula(620, 620)
        _POR = build_portrait()
        _MU, _ML, _EDGE = torn_masks(620, 810, 226, 77, amp=15)
        _NEBO = dotize(_NEB, 9, (16, 26, 32))
    return _K

PX, PY = 510, 245
CUT_Y = PY + 226
T_CUT, T_LIFT, T_HOLE, T_POP, T_BANG, T_NO = 1.6, 2.6, 3.2, 4.0, 5.4, 6.6

FBANG = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 56)
FSTICK = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 44, index=0)
FCAP = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 20)

def star(d, cx, cy, r, col, p):
    pts = []
    for k in range(10):
        a = -math.pi/2 + k * math.pi / 5
        rr = r * (1 if k % 2 == 0 else 0.42) * max(p, 0.05)
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    d.polygon(pts, fill=col)

def draw_scrap(d, cx, cy, sz, p, ang):
    pts = [(cx - sz, cy - sz*0.6), (cx + sz, cy - sz*0.5),
           (cx + sz*0.9, cy + sz*0.7), (cx - sz*0.85, cy + sz*0.6)]
    d.polygon(pts, fill=PAPER)

def draw_half(d, cx, cy, r, p):
    rr = r * p
    n = 5
    for yy in range(-n, n+1):
        for xx in range(-n, n+1):
            if xx*xx + yy*yy > n*n:
                continue
            d.ellipse([cx + xx*r*0.42 - rr*0.3, cy + yy*r*0.42 - rr*0.3,
                       cx + xx*r*0.42 + rr*0.3, cy + yy*r*0.42 + rr*0.3],
                      fill=(120, 118, 112))

# ---------------- 渲染 ----------------
def render(f):
    t12 = f / float(STEP_FPS)                 # f 即 12fps 帧号
    img = assets().copy()
    d = ImageDraw.Draw(img)

    # 报纸剪块（投影 + 旋转）
    for nw, pos, ang in ((_NL, (56, 250), -2.2), (_NR, (1120, 26), 1.8), (_NR, (1060, 540), -1.2)):
        rot = nw.rotate(ang, expand=True, resample=Image.BICUBIC)
        shd = Image.new("RGBA", rot.size, (0, 0, 0, 0))
        shd.paste((62, 47, 30, 160), (0, 0), rot.getchannel("A"))
        px, py = pos
        img.paste(shd, (px + 10, py + 12), shd)
        img.paste(rot, (px, py), rot)

    # 红色衬圆
    d.ellipse([820-190, 460-190, 820+190, 460+190], fill=RED)

    # 星云洞（裁切线以上，弹跳长大）
    if t12 >= T_HOLE:
        g = eob(clamp01((t12 - T_HOLE) / 0.9))
        nr = 60 + 200 * g
        neb = _NEBO.resize((int(nr*2), int(nr*2)), Image.LANCZOS)
        mask = Image.new("L", neb.size, 0)
        dm = ImageDraw.Draw(mask)
        dm.ellipse([0, 0, neb.size[0]-1, neb.size[1]-1], fill=255)
        dm.rectangle([0, CUT_Y - (430 - nr) + 8, neb.size[0], neb.size[1]], fill=0)
        img.paste(neb, (int(820 - nr), int(430 - nr)), mask)

    # 肖像下半（锯齿上缘）
    lo = Image.new("RGBA", _POR.size, (0, 0, 0, 0))
    lo.paste(_POR, (0, 0), _ML)
    img.paste(lo, (PX, PY), lo)

    # 头顶片：剪开后掀起+淡出
    if t12 < T_LIFT:
        up = Image.new("RGBA", _POR.size, (0, 0, 0, 0))
        up.paste(_POR, (0, 0), _MU)
        img.paste(up, (PX, PY), up)
    elif t12 < T_LIFT + 0.5:
        lift = (t12 - T_LIFT) / 0.5
        up = Image.new("RGBA", _POR.size, (0, 0, 0, 0))
        up.paste(_POR, (0, 0), _MU)
        up.putalpha(up.getchannel("A").point(lambda v: int(v * (1 - lift * 0.8))))
        rot = up.rotate(-10 * lift, expand=True, resample=Image.BICUBIC)
        dx, dy = int(36 * lift), int(-150 * lift)
        img.paste(rot, (PX - (rot.size[0]-520)//2 + dx, PY - (rot.size[1]-680)//2 + dy), rot)

    # 缝线沿锯齿边
    if t12 >= T_CUT:
        rng = random.Random(77)
        for k in range(0, len(_EDGE) - 1):
            (xa, ya), (xb, yb) = _EDGE[k], _EDGE[k+1]
            mx, my = (xa+xb)/2 + PX, (ya+yb)/2 + PY
            ang = math.atan2(yb-ya, xb-xa) + math.pi/2
            dl = 9
            cap_line(d, (mx - math.cos(ang)*dl, my - math.sin(ang)*dl),
                     (mx + math.cos(ang)*dl, my + math.sin(ang)*dl), 3, (240, 236, 224))
        if t12 < T_LIFT:                     # 裁切进行时的动态虚线
            prog = eio(clamp01((t12 - T_CUT) / (T_LIFT - T_CUT)))
            cap_line(d, (PX + 10, CUT_Y - PY), (PX + 10 + 500 * prog, CUT_Y - PY),
                     3, (250, 246, 236))

    # 脑洞蹦出的元素
    elems = []
    for k in range(5):
        elems.append(("star", 690 + rng0(k) * 250, 170 + rng0(k+9) * 130,
                      16 + rng0(k+3) * 10, T_POP + k * 0.12))
    for k in range(4):
        elems.append(("scrap", 650 + rng0(k+21) * 310, 120 + rng0(k+31) * 150,
                      15 + rng0(k+5) * 8, T_POP + 0.7 + k * 0.12))
    for k in range(3):
        elems.append(("half", 630 + rng0(k+41) * 340, 140 + rng0(k+51) * 140,
                      26 + rng0(k+7) * 12, T_POP + 1.2 + k * 0.14))
    for kind, ex, ey, sz, t0 in elems:
        p = eob(clamp01((t12 - t0) / 0.3))
        if p <= 0.01:
            continue
        bob = math.sin((t12 - t0) * 2.2) * 5
        if kind == "star":
            star(d, ex, ey + bob, sz, RED if int(ex) % 2 else PAPER, p)
        elif kind == "scrap":
            draw_scrap(d, ex, ey + bob, sz, p, 0)
        else:
            draw_half(d, ex, ey + bob, sz, p)

    # BANG!
    letters = "BANG!"
    bgc = [(30, 28, 28), RED, (30, 28, 28), (30, 28, 28), RED]
    fgc = [PAPER, (250, 244, 232), PAPER, PAPER, (250, 244, 232)]
    angs = (-8, 6, -5, 7, -6)
    for k, ch in enumerate(letters):
        p = eob(clamp01((t12 - (T_BANG + k * 0.14)) / 0.3))
        if p <= 0.01:
            continue
        bx, by = 1252 + k * 54, 130 + (3 if k % 2 else 0)
        tile = Image.new("RGBA", (92, 104), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        td.rectangle([0, 6, 88, 100], fill=bgc[k] + (255,))
        td.text((44, 53), ch, font=FBANG, fill=fgc[k] + (255,), anchor="mm")
        rot = tile.rotate(angs[k], expand=True, resample=Image.BICUBIC)
        sc = 0.6 + 0.4 * p
        rot = rot.resize((max(1, int(rot.size[0]*sc)), max(1, int(rot.size[1]*sc))), Image.LANCZOS)
        img.paste(rot, (int(bx - rot.size[0]/2), int(by - rot.size[1]/2)), rot)

    # №06 贴纸
    p = eob(clamp01((t12 - T_NO) / 0.4))
    if p > 0.01:
        tile = Image.new("RGBA", (220, 130), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        td.rectangle([0, 10, 216, 126], fill=RED + (255,))
        td.text((108, 66), "№06", font=FSTICK, fill=(250, 244, 230, 255), anchor="mm")
        rot = tile.rotate(-4, expand=True, resample=Image.BICUBIC)
        sc = 0.7 + 0.3 * p
        rot = rot.resize((int(rot.size[0]*sc), int(rot.size[1]*sc)), Image.LANCZOS)
        img.paste(rot, (int(1390 - rot.size[0]/2), int(648 - rot.size[1]/2)), rot)

    d.text((1042, 932), "V1  ·  CUT & PASTE ON KRAFT, 1868", font=FCAP,
           fill=mixc(KRAFT, (70, 56, 42), 0.9))
    return img

FPS_CONT = 60

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "preview":
        for fr in (30, 100, 115, 125, 140, 160, 200, 230, 260, 330, 420, 560):
            render(fr).save(os.path.join(OUT, "prev_%03d.png" % fr))
        print("PREVIEW DONE")
    else:
        os.makedirs(FRAMES, exist_ok=True)
        for i in range(NF):
            render(i).save(os.path.join(FRAMES, "f_%04d.png" % i))
            if i % 30 == 0:
                print("frame", i, "/", NF)
        print("done:", NF, "frames")
