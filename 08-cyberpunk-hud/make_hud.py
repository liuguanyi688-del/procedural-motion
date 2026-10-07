# -*- coding: utf-8 -*-
"""08 · 赛博朋克 HUD（FUI）：隼眼-9 目标锁定
开机自检 → 搜索扫描 → 锁定长江口。全部元素确定性绘制；
辉光 = 亮元素双层绘制（底图 + 高斯模糊层）screen 混合。
60fps。用法: python make_hud.py preview | all
"""
import math, sys, os, random
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(OUT, "frames")

W, H = 1600, 1000
FPS = 60
DUR = 10.0
CX, CY, R = 800, 520, 300
T_LOCK = 4.6

BG      = (9, 13, 22)
TEAL    = (62, 230, 216)
TEAL_D  = (26, 92, 92)
ORANGE  = (255, 154, 60)
ORANGE_D= (140, 80, 36)
YELLOW  = (255, 214, 66)
RED     = (255, 84, 68)
GRAYT   = (108, 128, 138)
PANEL   = (14, 20, 30)

FC  = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 22)
FCB = ImageFont.truetype(r"C:\Windows\Fonts\consolab.ttf", 26)
FCB2= ImageFont.truetype(r"C:\Windows\Fonts\consolab.ttf", 54)
FCS = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 18)
FCXS= ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 15)
FCXL= ImageFont.truetype(r"C:\Windows\Fonts\consolab.ttf", 40)
FCN = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 62, index=0)
FCN2= ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 24, index=0)
FCN3= ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 21, index=0)

def en_cn(u, x, y, en, cn, f_en, f_cn, col, gap=8):
    """EN 用等宽字体,CN 用雅黑,顺序拼接"""
    u.text((x, y), en, f_en, col)
    if cn:
        w = u.d.textlength(en, font=f_en)
        u.text((x + w + gap, y - 2), cn, f_cn, col)

def clamp01(x): return max(0.0, min(1.0, x))
def lerp(a, b, p): return a + (b - a) * p
def eio(x):
    x = clamp01(x)
    return 4*x*x*x if x < 0.5 else 1 - (-2*x+2)**3 / 2
def n1(t, a=1.0): return (math.sin(t*3.7*a) + 0.6*math.sin(t*9.1*a+1.3) + 0.3*math.sin(t*21*a+2.1)) / 1.9

class Duo:
    """同时画到底图与辉光层"""
    def __init__(self, d, g):
        self.d, self.g = d, g
    def text(self, pos, s, f, col):
        self.d.text(pos, s, font=f, fill=col)
        self.g.text(pos, s, font=f, fill=col)
    def line(self, a, b=None, w=2, col=None):
        if isinstance(b, (int, float)):          # (x0,y0,x1,y1), width, col
            col = w
            w = b
            x0, y0, x1, y1 = a
        else:                                     # (x0,y0), (x1,y1), width, col
            x0, y0 = a
            x1, y1 = b
        self.d.line([x0, y0, x1, y1], fill=col, width=int(w))
        self.g.line([x0, y0, x1, y1], fill=col, width=int(w))
    def ellipse(self, box, outline, w=2):
        self.d.ellipse(box, outline=outline, width=int(w))
        self.g.ellipse(box, outline=outline, width=int(w))
    def arc(self, box, a0, a1, outline, w=2):
        self.d.arc(box, a0, a1, fill=outline, width=int(w))
        self.g.arc(box, a0, a1, fill=outline, width=int(w))
    def poly(self, pts, outline, w=2):
        self.d.line([c for p in pts for c in p], fill=outline, width=int(w), joint="curve")
        self.g.line([c for p in pts for c in p], fill=outline, width=int(w), joint="curve")
    def rect(self, box, fill):
        self.d.rectangle(box, fill=fill)
    def rrect(self, box, r, fill):
        self.d.rounded_rectangle(box, radius=r, fill=fill)

def mixc(c1, c2, p): return tuple(int(round(a + (b-a)*p)) for a, b in zip(c1, c2))
def dim(col, p): return mixc(BG, col, clamp01(p))

# ---------------- 长江口海岸线（手工近似） ----------------
COAST = [(0.66,0.02),(0.62,0.10),(0.67,0.16),(0.60,0.24),(0.66,0.31),(0.57,0.40),
         (0.63,0.48),(0.54,0.57),(0.60,0.65),(0.52,0.74),(0.58,0.82),(0.50,0.92),(0.55,1.00)]
RIVER = [(0.63,0.48),(0.72,0.42),(0.78,0.46),(0.74,0.56),(0.80,0.62),(0.76,0.72)]

# ---------------- 各部件 ----------------
def globe(u, t, locked):
    fade = clamp01(t / 1.2)
    # 内盘
    u.d.ellipse([CX-R, CY-R, CX+R, CY+R], fill=(13, 21, 33))
    # 经线（旋转）
    for i in range(6):
        ph = t * 0.25 + i * math.pi / 6
        rx = abs(math.cos(ph)) * R
        if rx > 6:
            u.ellipse([CX-rx, CY-R, CX+rx, CY+R], dim(TEAL_D, fade * (0.5 + 0.5*abs(math.cos(ph)))), 2)
    # 纬线
    for lat in (-60, -30, 0, 30, 60):
        la = math.radians(lat)
        ry = R * math.cos(la) * 0.30
        yy = CY + R * math.sin(la)
        u.ellipse([CX - R*math.cos(la), yy - ry, CX + R*math.cos(la), yy + ry],
                  dim(TEAL_D, fade * 0.9), 2)
    # 海岸线（亮橙）
    cp = [(CX + (p[0]-0.5)*2*R*0.86, CY + (p[1]-0.5)*2*R*0.92) for p in COAST]
    u.poly(cp, ORANGE, 4)
    rp = [(CX + (p[0]-0.5)*2*R*0.86, CY + (p[1]-0.5)*2*R*0.92) for p in RIVER]
    u.poly(rp, ORANGE, 3)
    u.text((CX + 96, CY - 66), "", FCXS, dim(ORANGE, fade))
    en_cn(u, CX + 96, CY - 66, "EST.", "长江口", FCXS, FCN3, dim(ORANGE, fade))

def rings_ticks(u, t, locked):
    fade = clamp01(t / 1.2)
    for k, rr in enumerate((R+42, R+92, R+142)):
        u.ellipse([CX-rr, CY-rr, CX+rr, CY+rr], dim(ORANGE_D, fade * (0.9 - k*0.22)), 2)
    # 刻度
    for deg in range(0, 360, 5):
        a = math.radians(deg - 90)
        r0, r1 = R + 8, R + (26 if deg % 30 == 0 else 14)
        u.line((CX + math.cos(a)*r0, CY + math.sin(a)*r0),
               (CX + math.cos(a)*r1, CY + math.sin(a)*r1),
               2, dim(ORANGE, fade * (0.9 if deg % 30 == 0 else 0.45)))
        if deg % 30 == 0:
            u.text((CX + math.cos(a)*(R+52) - 18, CY + math.sin(a)*(R+52) - 10),
                   "%03d" % deg, FCXS, dim(ORANGE, fade * 0.8))
    # 扫描余晖
    sw = (t * 55) % 360
    for k in range(14):
        a1 = sw - k * 3.2
        u.arc([CX-R-30, CY-R-30, CX+R+30, CY+R+30], a1 - 3.4, a1,
              dim(TEAL, fade * 0.5 * (1 - k/14)), 3)

def reticle(u, t, locked):
    if t < 3.4:
        return
    hunt = math.sin(t * 5.2) * 26 if not locked else 0
    gap = lerp(150 + hunt, 92, eio(clamp01((t - T_LOCK) / 0.3)))
    w = 4 if locked else 2
    col = ORANGE if locked else TEAL
    a = clamp01((t - 3.4) / 0.4)
    col = dim(col, a)
    for sx, sy in ((-1,-1),(1,-1),(-1,1),(1,1)):
        x, y = CX + sx*gap, CY + sy*gap
        u.line((x, y, x - sx*34, y), w, col)
        u.line((x, y, x, y - sy*34), w, col)
    if locked:
        u.ellipse([CX-7, CY-7, CX+7, CY+7], ORANGE, 3)
        u.line((CX-16, CY, CX+16, CY), 2, dim(ORANGE, 0.8))
        u.line((CX, CY-16, CX, CY+16), 2, dim(ORANGE, 0.8))

def banner(u, t, locked):
    if not locked:
        return
    a = clamp01((t - T_LOCK - 0.25) / 0.25)
    if a <= 0.01:
        return
    y = 470
    u.rect((CX-470, y-52, CX+470, y+52), (26, 16, 8))
    for k in range(9):
        u.rect((CX-470 + k*110, y-52, CX-470 + k*110 + 62, y+52), (54, 30, 12))
    u.line((CX-470, y-52, CX+470, y-52), 3, ORANGE)
    u.line((CX-470, y+52, CX+470, y+52), 3, ORANGE)
    fl = 0.75 + 0.25 * math.sin(t * 9)
    u.text((CX-392, y-36), "■", FCS, dim(YELLOW, a))
    en_cn(u, CX-376, y-38, "ALERT 03", "警告", FCS, FCN3, dim(YELLOW, a))
    u.text((CX-300, y-40), "目标锁定", FCN, dim(YELLOW, a * fl))
    u.text((CX+60, y-30), "TARGET", FCB2, dim(YELLOW, a * fl))
    u.text((CX+60, y+28), "LOCKED", FCB2, dim(YELLOW, a * fl))
    # 顶部小横幅
    if t > T_LOCK + 0.6:
        en_cn(u, CX-160, 40, "TARGET LOCKED", "目标锁定", FCB, FCN2,
              dim(ORANGE, 0.85 + 0.15*math.sin(t*7)))

def panel_frame(u, x0, y0, x1, y1, title_cn, title_en, fade):
    u.rect((x0, y0, x1, y1), dim(PANEL, fade * 0.85))
    u.line((x0, y0, x0, y1), 2, dim(TEAL_D, fade))
    u.line((x0, y0, x0 + 26, y0), 2, dim(TEAL, fade))
    u.line((x1, y0, x1, y1), 2, dim(TEAL_D, fade))
    u.line((x1 - 26, y0, x1, y0), 2, dim(TEAL, fade))
    u.text((x0 + 14, y0 + 10), "▍", FCXS, dim(TEAL, fade))
    en_cn(u, x0 + 26, y0 + 10, title_en, title_cn, FCXS, FCN3, dim(TEAL, fade))

def left_panel(u, t):
    x0, x1 = 58, 372
    fade = clamp01(t / 0.8)
    panel_frame(u, x0, 108, x1, 940, "隼眼-9 · 目标光学系统", "KESTREL-9", fade)
    # SYS BOOT
    lines = [("OPTIC CORE v4.2.1", 0.30), ("GYRO FPS 499.7°", 0.45), ("GYRO ALIGN 0.0001°", 0.60),
             ("ORBIT LED 512 NM", 0.75), ("UPLINK QOS 9.66", 0.90), ("SIG DBL 20 PROOF", 1.05),
             ("SEARCH MODE ENGAGED", 1.25), ("TGT-03 LOCKED", T_LOCK + 0.3)]
    en_cn(u, x0+14, 158, "SYS BOOT", "系统自检", FCXS, FCN3, dim(TEAL, fade))
    for k, (s, t0) in enumerate(lines):
        if t < t0:
            break
        yy = 190 + k * 30
        col = ORANGE if "ENGAGED" in s or "LOCKED" in s else TEAL
        u.text((x0+14, yy), "· " + s, FCS, dim(col, fade))
        if t > t0 + 0.22:
            u.text((x1-56, yy), "[OK]", FCS, dim(TEAL, fade))
        elif "ENGAGED" in s:
            if int(t * 3) % 2 == 0:
                u.text((x1-56, yy), "[..]", FCS, dim(YELLOW, fade))
    # EFF RNG 大数字
    if t > 1.6:
        en_cn(u, x0+14, 470, "EFF RNG", "等效距离", FCXS, FCN3, dim(TEAL, fade))
        v = 102.5 + n1(t) * 0.8
        u.text((x0+14, 500), "%08.1f" % (v * 10), FCB2, dim(TEAL, fade))
        u.text((x0+300, 528), "KM", FCXS, dim(TEAL, fade))
        u.rect((x0+14, 596, x0+14 + 280, 606), dim(TEAL_D, fade))
        u.rect((x0+14, 596, x0+14 + 280 * clamp01((t-1.6)/2.2), 606), dim(TEAL, fade))
    # NAV TELEMETRY
    if t > 2.3:
        en_cn(u, x0+14, 654, "NAV TELEMETRY", "导航遥测", FCXS, FCN3, dim(TEAL, fade))
        rows = [("AZM", 121.48 + n1(t)*0.06, "°"), ("ELEV", 31.23 + n1(t*1.3)*0.04, "°"),
                ("DIS", 512.09 + n1(t*0.7)*0.4, "KM"), ("VEL", 7.613 + n1(t*1.9)*0.05, "M/S"),
                ("BRT", 41.2 + n1(t*2.3)*0.3, "%")]
        for k, (nm, v, un) in enumerate(rows):
            yy = 690 + k * 40
            u.text((x0+14, yy), nm, FC, dim(GRAYT, fade))
            u.text((x0+84, yy-4), "%09.3f %s" % (v, un), FCB, dim(ORANGE, fade))
            u.rect((x0+292, yy+2, x0+292 + 42, yy+14), dim(TEAL_D, fade))
            u.rect((x0+292, yy+2, x0+292 + 42 * (0.4 + 0.3*math.sin(t*2+k)), yy+14),
                   dim(TEAL, fade))
    # MINIMAP
    if t > 3.1:
        en_cn(u, x0+14, 894, "SOM MINIMAP", "态势", FCXS, FCN3, dim(TEAL, fade))

def right_panel(u, t):
    x0, x1 = 1228, 1542
    fade = clamp01(t / 1.0)
    panel_frame(u, x0, 108, x1, 940, "信号分析", "SIGNAL ANALYSIS", fade)    # 折线图 ×2
    def graph(y0, label, unit, seed, col):
        u.text((x0+14, y0), label + "  " + unit, FCXS, dim(TEAL, fade))
        pts = []
        for i in range(48):
            xx = x0 + 14 + i * 6
            v = n1((i + t * 30) * 0.11 + seed, 1.3)
            pts.append((xx, y0 + 52 + v * 26))
        u.poly(pts, col, 2)
        cur = pts[-1]
        u.ellipse([cur[0]-4, cur[1]-4, cur[0]+4, cur[1]+4], col, 2)
        val = -62.1 + n1(t, 1.7) * 1.2 if seed < 1 else 78.2 + n1(t, 1.1) * 1.5
        u.text((x1-116, y0 + 22), "%+.1f" % val if seed < 1 else "%.1f %%" % val,
               FCB, dim(col, fade))
    if t > 1.1:
        graph(150, "SIG PWR", "-dBm", 0.3, ORANGE)
        graph(262, "COHERENCE", "%", 1.7, ORANGE)
    # CANDIDATES
    if t > 2.1:
        en_cn(u, x0+14, 372, "CANDIDATES", "候选目标", FCXS, FCN3, dim(TEAL, fade))
        cnd = [("CND-01", "0BX", "NO MATCH"), ("CND-02", "UNC", "NO MATCH"),
               ("CND-03", "SHA", "MATCH %.1f%%" % min(99.7, (t-2.4)*55))]
        for k, (cid, cd, st) in enumerate(cnd):
            yy = 404 + k * 34
            u.text((x0+14, yy), cid + "  " + cd, FC, dim(TEAL, fade))
            m = st.startswith("MATCH")
            ok = m and t > T_LOCK
            u.text((x1-160, yy), st if not m else ("MATCH 99.7%%" if ok else
                   "MATCH %.1f%%" % (clamp01((t-2.4)*55) * 99.7)), FC,
                   dim(YELLOW if ok else GRAYT, fade))
    # SPECTRUM
    if t > 2.6:
        en_cn(u, x0+14, 528, "SPECTRUM", "频谱", FCXS, FCN3, dim(TEAL, fade))
        u.text((x0+150, 528), "▲ 8.412 GHz", FCXS, dim(ORANGE, fade))
        for i in range(36):
            bx = x0 + 16 + i * 8.4
            v = 0.12 + 0.5 * math.exp(-((i - 19) ** 2) / 34) * (0.7 + 0.3 * math.sin(t * 6 + i))
            v *= 0.75 + 0.25 * math.sin(t * 11 + i * 2.1)
            bh = 88 * clamp01(v)
            col = ORANGE if 16 <= i <= 22 else TEAL
            u.rect((bx, 560 + 96 - bh, bx + 5, 560 + 96), dim(col, fade))
        u.line((x0+14, 560+96, x1-14, 560+96), 2, dim(TEAL_D, fade))
    # DATA LINK hex
    if t > 3.2:
        en_cn(u, x0+14, 700, "DATA LINK  0X07", "数据链路", FCXS, FCN3, dim(TEAL, fade))
        u.text((x1-108, 700), "UDP 9.6.0", FCXS, dim(ORANGE, fade))
        rng = random.Random(int(t * 1.5))
        for r_ in range(4):
            row = " ".join("%02X" % rng.randint(0, 255) for _ in range(8))
            u.text((x0+14, 732 + r_ * 26), "%04X  %s" % (0x403E + r_ * 8, row),
                   FCS, dim(TEAL, fade * (1 - r_ * 0.18)))
        u.text((x1-118, 732), "UDP 0.9.6", FCS, dim(ORANGE, fade))

def header(u, t):
    fade = clamp01(t / 0.6)
    en_cn(u, 84, 52, "◈ KESTREL-9", "隼眼-9 · 目标光学系统", FCB, FCN2, dim(TEAL, fade))
    if t > T_LOCK + 0.5:
        u.rrect((CX-150, 44, CX+150, 76), 8, dim((60, 34, 14), 1))
        u.text((CX-124, 48), "TARGET LOCKED  目标锁定", FCS, dim(ORANGE, 1))
    tt = 3 * 3600 + 14 * 60 + 57 + t
    u.text((1382, 52), "● REC", FCS, dim(RED, fade))
    u.text((1436, 50), "UTC %02d:%02d:%04.1f" % (tt/3600, (tt/60) % 60, tt % 60),
           FCB, dim(RED, fade))

# ---------------- 渲染 ----------------
def render(f):
    t = f / FPS
    locked = t >= T_LOCK
    base = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(base)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    u = Duo(d, g)

    # 角框
    for sx, sy in ((-1,-1),(1,-1),(-1,1),(1,1)):
        x = 34 + (sx > 0) * (W - 68)
        y = 26 + (sy > 0) * (H - 52)
        u.line((x, y, x + sx*46, y), 3, dim(TEAL, 0.8))
        u.line((x, y, x, y + sy*38), 3, dim(TEAL, 0.8))

    globe(u, t, locked)
    rings_ticks(u, t, locked)
    reticle(u, t, locked)
    banner(u, t, locked)
    left_panel(u, t)
    right_panel(u, t)
    header(u, t)

    out = ImageChops.screen(base, glow.filter(ImageFilter.GaussianBlur(9)))
    # 扫描线
    dd = ImageDraw.Draw(out)
    for yy in range(0, H, 4):
        dd.line([0, yy, W, yy], fill=(6, 8, 12))
    dd.text((30, 962), "KASTREL-9 · TARGET OPTICS · EST. 041°",
            font=ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 16), fill=(70, 88, 96))
    return out

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    NF = int(DUR * FPS)
    if mode == "preview":
        for fr in (40, 130, 220, 290, 320, 420, 560):
            render(fr).save(os.path.join(OUT, "prev_%03d.png" % fr))
        print("PREVIEW DONE  %d frames" % NF)
    else:
        os.makedirs(FRAMES, exist_ok=True)
        for i in range(NF):
            render(i).save(os.path.join(FRAMES, "f_%04d.png" % i))
            if i % 100 == 0:
                print("frame", i, "/", NF)
        print("done:", NF, "frames")
