# -*- coding: utf-8 -*-
"""09 · 拼贴剪贴 v2 —— 真实素材版
真实维多利亚绅士照(公有领域)洪泛抠图 + 半调网点化;
真实哈勃星云(创生之柱)与 1900 年报纸扫描件;12fps 逐格步进。
用法: python make_collage2.py preview | all
"""
import math, random, sys, os, collections
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from make_collage import (dotize, cap_line, torn_masks, paper_mask, mixc,
                          clamp01, eob, eio, lerp, star, step, rng0,
                          FBANG, FSTICK, FCAP, STEP_FPS)

OUT = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(OUT, "frames2")
A = os.path.join(OUT, "assets")

W, H = 1600, 1000
NF = 120
KRAFT   = (180, 148, 110)
RED     = (198, 40, 36)
PAPER   = (238, 233, 218)
INK     = (52, 48, 44)
T_CUT, T_LIFT, T_HOLE, T_POP, T_BANG, T_NO = 1.6, 2.6, 3.2, 4.0, 5.4, 6.6
PX, PY = 480, 170
CUT_LOCAL = 208
CUT_Y = PY + CUT_LOCAL

FPILL = ImageFont.truetype(r"C:\Windows\Fonts\consolab.ttf", 22)

def en_cn(d, x, y, en, cn, f_en, f_cn, col):
    d.text((x, y), en, font=f_en, fill=col)
    w = d.textlength(en, font=f_en)
    d.text((x + w + 10, y - 2), cn, font=f_cn, fill=col)

# ---------------- 抠图:边界洪泛填充(RGB 色距) ----------------
def cutout(gray, rgb):
    """灰度+RGB → 主体 alpha 蒙版(边界洪泛,色距判定)"""
    small = rgb.resize((160, 170), Image.LANCZOS)
    gsmall = gray.resize((160, 170), Image.LANCZOS)
    w, h = small.size
    px = small.load()
    border = [px[x, 0] for x in range(w)] + [px[x, h-1] for x in range(w)] + \
             [px[0, y] for y in range(h)] + [px[w-1, y] for y in range(h)]
    bgv = sorted(border, key=lambda c: c[0]+c[1]+c[2])[len(border)//2]
    tol2 = 34 * 34
    def close(c):
        return (c[0]-bgv[0])**2 + (c[1]-bgv[1])**2 + (c[2]-bgv[2])**2 <= tol2
    seen = [[False]*h for _ in range(w)]
    dq = collections.deque()
    for x in range(w):
        for y in (0, h-1):
            if close(px[x, y]) and not seen[x][y]:
                seen[x][y] = True; dq.append((x, y))
    for y in range(h):
        for x in (0, w-1):
            if close(px[x, y]) and not seen[x][y]:
                seen[x][y] = True; dq.append((x, y))
    while dq:
        x, y = dq.popleft()
        for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[nx][ny] and close(px[nx, ny]):
                seen[nx][ny] = True; dq.append((nx, ny))
    bgmask = Image.new("L", (w, h), 0)
    bgmask.putdata([255 if seen[x][y] else 0 for y in range(h) for x in range(w)])
    sub = bgmask.point(lambda v: 255 - v)
    # 闭运算填凹湾(发丝高光与背景连通的误抠区),核 41/170 ≈ 1/4 画宽
    sub = sub.filter(ImageFilter.MaxFilter(41)).filter(ImageFilter.MinFilter(41))
    sub = sub.resize((gray.size[0], gray.size[1]), Image.NEAREST)
    sub = sub.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    sub = sub.filter(ImageFilter.GaussianBlur(1.2))
    return sub

# ---------------- 素材准备(一次性) ----------------
_P = _NEB = _NL = _NR = _K = _MU = _ML = _EDGE = _NEBO = None

def assets():
    global _P, _NEB, _NL, _NR, _K, _MU, _ML, _EDGE, _NEBO
    if _P is not None:
        return
    # 绅士:裁切→灰度→对比→抠图→半调网点
    p = Image.open(os.path.join(A, "portrait_1.jpg")).convert("RGB")
    w, h = p.size
    p = p.crop((int(0.10*w), int(0.04*h), int(0.90*w), int(0.58*h)))
    p = p.resize((640, 680), Image.LANCZOS)
    g = ImageOps.autocontrast(p.convert("L"), cutoff=1)
    alpha = cutout(g, p)
    sepia = ImageOps.colorize(g, black=(36, 28, 22), white=(244, 236, 218),
                              mid=(152, 130, 106))
    ht = dotize(sepia, 6, (244, 236, 218))
    ht = ht.convert("RGBA")
    ht.putalpha(alpha)
    _P = ht
    # 星云:创生之柱裁方→半调
    n = Image.open(os.path.join(A, "nebula_0.jpg")).convert("RGB")
    nw, nh = n.size
    n = n.crop((int(0.24*nw), int(0.12*nh), int(0.86*nw), int(0.74*nh)))
    _NEB = dotize(n, 10, (14, 20, 26))
    # 报纸:真实扫描件灰度化
    nw2 = Image.open(os.path.join(A, "news_0.jpg")).convert("L")
    nw2 = ImageOps.autocontrast(nw2, cutoff=1)
    _NL = nw2.resize((360, 660), Image.LANCZOS).convert("RGBA")
    _NL.putalpha(paper_mask(360, 660, 5))
    _NR = nw2.transpose(Image.FLIP_LEFT_RIGHT).resize((440, 610),
            Image.LANCZOS).convert("RGBA")
    _NR.putalpha(paper_mask(440, 610, 9))
    # 牛皮纸:真实纹理平铺 + 细噪声
    k = Image.open(os.path.join(A, "kraft_0.jpg")).convert("RGB").resize((1700, 1060),
            Image.LANCZOS)
    _K = k.crop((50, 30, 50+W, 30+H))
    rng = random.Random(3)
    d = ImageDraw.Draw(_K)
    for _ in range(200):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        ln = rng.uniform(12, 40); an = rng.uniform(0, math.pi)
        d.line([x, y, x + math.cos(an)*ln, y + math.sin(an)*ln],
               fill=mixc(KRAFT, (226, 204, 174), rng.random()*0.5), width=1)
    # 裁切蒙版(肖像局部坐标)
    _MU, _ML, _EDGE = torn_masks(640, 680, CUT_LOCAL, 77, amp=14)
    # 星云网点化副本
    _NEBO = _NEB.filter(ImageFilter.GaussianBlur(0.5))

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

def cap_line(d, a, b, w, col):
    d.line([a[0], a[1], b[0], b[1]], fill=col, width=int(w))
    r = w / 2
    for x, y in (a, b):
        d.ellipse([x-r, y-r, x+r, y+r], fill=col)

# ---------------- 渲染 ----------------
def render(f):
    t12 = f / float(STEP_FPS)
    assets()
    img = _K.copy()
    d = ImageDraw.Draw(img)

    # 报纸剪块(投影 + 旋转)
    for nw, pos, ang in ((_NL, (54, 240), -2.2), (_NR, (1140, 60), 1.6)):
        rot = nw.rotate(ang, expand=True, resample=Image.BICUBIC)
        shd = Image.new("RGBA", rot.size, (0, 0, 0, 0))
        shd.paste((62, 47, 30, 150), (0, 0), rot.getchannel("A"))
        px, py = pos
        img.paste(shd, (px + 10, py + 12), shd)
        img.paste(rot, (px, py), rot)

    # 红色衬圆
    d.ellipse([820-190, 450-190, 820+190, 450+190], fill=RED)

    # 星云洞(裁切线以上,弹跳长大)
    if t12 >= T_HOLE:
        g = eob(clamp01((t12 - T_HOLE) / 0.9))
        nr = 60 + 210 * g
        neb = _NEBO.resize((int(nr*2), int(nr*2)), Image.LANCZOS)
        mask = Image.new("L", neb.size, 0)
        dm = ImageDraw.Draw(mask)
        dm.ellipse([0, 0, neb.size[0]-1, neb.size[1]-1], fill=255)
        dm.rectangle([0, CUT_Y + 6 - (450 - nr), neb.size[0], neb.size[1]], fill=0)
        img.paste(neb, (int(820 - nr), int(450 - nr)), mask)

    # 绅士下半(锯齿上缘)
    lo = Image.new("RGBA", _P.size, (0, 0, 0, 0))
    lo.paste(_P, (0, 0), _ML)
    img.paste(lo, (PX, PY), lo)

    # 头顶片:掀起 + 淡出
    if t12 < T_LIFT:
        up = Image.new("RGBA", _P.size, (0, 0, 0, 0))
        up.paste(_P, (0, 0), _MU)
        img.paste(up, (PX, PY), up)
    elif t12 < T_LIFT + 0.5:
        lift = (t12 - T_LIFT) / 0.5
        up = Image.new("RGBA", _P.size, (0, 0, 0, 0))
        up.paste(_P, (0, 0), _MU)
        up.putalpha(up.getchannel("A").point(lambda v: int(v * (1 - lift*0.8))))
        rot = up.rotate(-9 * lift, expand=True, resample=Image.BICUBIC)
        dx, dy = int(40 * lift), int(-160 * lift)
        img.paste(rot, (PX - (rot.size[0]-640)//2 + dx, PY - (rot.size[1]-680)//2 + dy), rot)

    # 缝线沿锯齿边(只画头部实际范围内)
    if t12 >= T_CUT:
        rng = random.Random(77)
        row = _P.getchannel("A")
        xs = [x for x in range(640) if row.getpixel((x, CUT_LOCAL)) > 100]
        hx0, hx1 = (min(xs) - 8, max(xs) + 8) if xs else (180, 470)
        for k in range(len(_EDGE) - 1):
            (xa, ya), (xb, yb) = _EDGE[k], _EDGE[k+1]
            mx, my = (xa+xb)/2 + PX, (ya+yb)/2 + PY
            if not (hx0 <= mx - PX <= hx1):
                continue
            ang = math.atan2(yb-ya, xb-xa) + math.pi/2
            dl = 9
            cap_line(d, (mx - math.cos(ang)*dl, my - math.sin(ang)*dl),
                     (mx + math.cos(ang)*dl, my + math.sin(ang)*dl), 3, (240, 236, 224))
        if t12 < T_LIFT:
            prog = eio(clamp01((t12 - T_CUT) / (T_LIFT - T_CUT)))
            cap_line(d, (PX + hx0, CUT_Y - PY), (PX + hx0 + (hx1-hx0) * prog, CUT_Y - PY),
                     3, (250, 246, 236))

    # 脑洞蹦出的元素
    elems = []
    for k in range(5):
        elems.append(("star", 690 + rng0(k) * 250, 150 + rng0(k+9) * 140,
                      16 + rng0(k+3) * 10, T_POP + k * 0.12))
    for k in range(4):
        elems.append(("scrap", 640 + rng0(k+21) * 320, 100 + rng0(k+31) * 150,
                      15 + rng0(k+5) * 8, T_POP + 0.7 + k * 0.12))
    for k in range(3):
        elems.append(("neb", 620 + rng0(k+41) * 350, 110 + rng0(k+51) * 150,
                      26 + rng0(k+7) * 14, T_POP + 1.2 + k * 0.14))
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
            crop = _NEBO.crop((int(_NEBO.size[0]*0.3), int(_NEBO.size[1]*0.2),
                               int(_NEBO.size[0]*0.3) + int(sz*2.4),
                               int(_NEBO.size[1]*0.2) + int(sz*2.4)))
            crop = crop.resize((int(sz*2.4), int(sz*2.4)), Image.LANCZOS)
            m = Image.new("L", crop.size, 0)
            ImageDraw.Draw(m).ellipse([4, 4, crop.size[0]-4, crop.size[1]-4], fill=255)
            img.paste(crop, (int(ex - sz*1.2), int(ey + bob - sz*1.2)), m)

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
