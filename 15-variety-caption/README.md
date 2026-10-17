# 15 · 综艺花字 Variety Captions — 喵呜日记 EP07

> 多层描边、弹跳、表情贴，专门放大情绪。
> 本目录：**1080×1920 竖屏**（9:16）/ 60fps / 10 秒 / **120 BPM**（一拍 0.5 秒，十六分音符 0.067 秒）。

[▶ 成片 output.mp4](output.mp4) · 脚本 [make_caption.py](make_caption.py)

> 参考坐标：`mg-styles-15` 的 `18-hanazi`（浏览器 SVG + 真实猫咪照片）。
> 这里用**纯 Pillow + numpy** 复刻同一套花字组件——没有 SVG、没有浏览器排版引擎。
> 三张猫咪照片取自参考项目的 `assets/`，仅用于学习复现，版权归原作者。

## 核心知识

### 1. 一个字的五层

这一版的全部技术，都压在"一个字怎么叠成一块综艺花字"上。答案是把**同一段文字画五遍**：

```python
W = 2 * (outer + white)                      # 基础描边宽

# 1-2. 挤出：两层，往下偏移 ext 和 ext*0.5，露出来的部分就是"厚度"
d.text((cx, cy + ext),     ch, fill=ext_color, stroke_width=W, stroke_fill=ext_color)
d.text((cx, cy + ext*0.5), ch, fill=ext_color, stroke_width=W, stroke_fill=ext_color)

# 3. 外描边（同宽，换个颜色）
d.text((cx, cy), ch, fill=outer_color, stroke_width=W, stroke_fill=outer_color)

# 4. 白描边（更细，压在外描边上面）
d.text((cx, cy), ch, fill="#fff", stroke_width=2*white, stroke_fill="#fff")

# 5. 渐变填充（不描边，用遮罩贴上去）
img.paste(vertical_gradient(...), (0, 0), text_mask)

# 6. 顶部高光（从上往下 46% 处衰减到 0）
```

**为什么挤出层和外描边用同样粗的描边**：这样挤出层只会在下方露出一条等宽的"边"，看起来就像字体有厚度。如果挤出层更细，会露出一条缝；更粗，会把外描边顶掉。

**为什么白描边要比外描边细**：它是"高光线"，粗了就变成第二层轮廓，失去锐利感。

**渐变的坐标是整个 sprite 的高度**，不是字形的包围盒——所以同一个 sprite 里，字的上下两端自然吃到渐变的头尾，视觉上"上亮下暗"，这是糖纸感的关键。

### 2. 逐字入场：弹簧，不是缓动

每个字独立入场，用的是**阻尼弹簧**而不是 bezier 缓动：

```python
def spring(t, z=0.517, w=22.0):
    wd = w * sqrt(1 - z*z)
    return 1 - exp(-z*w*t) * (cos(wd*t) + (z*w/wd) * sin(wd*t))
```

- 从 0 弹到 **1.15 左右**再回落（过冲）
- `z = 0.517` 是欠阻尼，所以会"duang"一下
- bezier 缓动做不出这种"砸下去再弹回来"的手感

每个字还带三件事：

```python
y = -drop * (1 - spring(u, 0.55, 20))       # 从上方落下来
r = r0 * (1 - spring(u, 0.45, 18))          # 带着旋转归位
```

### 3. 保持期：波浪式抖动 + 呼吸

字落位之后不能是死的。三个叠加的正弦，**每个字的相位不同**：

```python
ph = x * 0.013 + i * 0.7                    # 相位跟横坐标绑定
r += hold * wig * sin(2π*wf*t + ph)         # 摇摆
y += hold * bob * sin(2π*wf*t + ph + 1.9)   # 上下浮
s *= 1 + hold * breath * sin(2π*wf*2*t + ph*1.7)  # 呼吸缩放
```

`ph = x * 0.013` 是关键：**相位和位置成正比**，所以整行字看起来像一道波浪从左扫到右，而不是所有字一起上下点头。这是综艺花字"活"起来的原因。

### 4. 手抖：两层值噪声

花字整体还有一层"手持摄影"的抖动：

```python
def hand(t, seed, a=1.0):
    return (a * (7*vn(t*0.9, seed) + 2.5*vn(t*2.3, seed+11)),
            a * (6*vn(t*0.8, seed+23) + 2*vn(t*2.6, seed+37)))
```

两个八度的值噪声叠加（低频大幅 + 高频小幅），这是手持感的配方。纯正弦会像"机械摇摆"，纯随机会像"坏掉的信号"。

### 5. 三只猫：真实照片怎么塞进 9:16

素材是三张真实猫咪照片（`assets/`，取自参考项目），比例各不相同（3:4、1:1、3:2），要塞进 1080×1920。三步：

```python
z  = max(CW/w, CH/h)                     # 1. 缩放「填满」，不是 fit
ox = clip(fx*im.width  - CW/2, 0, ...)   # 2. 按指定中心裁剪（每张主体位置不同）
a  = np.asarray(im) * np.array(mul)      # 3. 通道乘子调色
```

```python
ASSETS = {
    "sun":   ("white_dof.jpg", (1.07, 1.00, 0.93), 0.50, 0.52),  # 白猫眯眼晒太阳
    "stare": ("tux_r1.jpg",    (0.90, 0.97, 1.14), 0.50, 0.46),  # 黑白猫绿眼凝视
    "fluff": ("grey_r2.jpg",   (1.15, 0.84, 1.08), 0.55, 0.50),  # 灰猫，草地压成粉紫
}
```

**为什么不用 fit + 模糊背景填充**：竖屏 9:16 比所有素材都窄，`fit` 之后上下留大片空白，再糊一层背景就成了"横屏转竖屏"的廉价感。直接裁掉左右反而更像特写。

**源图要比画幅大 30%**（`_CW = W*1.30`）——运镜会推近到 1.2 倍，图不够大就糊了。

调色的作用不只是"统一色调"：灰猫那张原本是绿色草地，`(1.15, 0.84, 1.08)` 把绿压下去、红蓝提上来，整张就变成了粉紫调，和"炸毛"的情绪对上了。**一个 3 元素的乘法就完成了情绪换色**，比重新找素材快得多。

### 6. 竖屏构图

1080×1920 和 1920×1080 的构图逻辑完全不同：

| | 横屏 | 竖屏 |
|---|---|---|
| 花字位置 | 底部字幕区 | **画面中上部**（视线高度） |
| 单行字数 | 可以长 | **不超过 5-6 字**，多了就换行 |
| 字号 | 相对小 | **大**（170px 起），要占屏宽的 70% |
| 安全区 | 上下留边 | **顶部 120px / 底部 300px**（避开角标和平台 UI） |

## 叙事时间轴（120 BPM / 10 秒）

| 时间 | 事件 |
|---|---|
| 0.0s | 角标「喵呜日记 EP07」从左上弹入 |
| 0.20–0.467s | **「前方高能」**五个字逐个弹入（暖金渐变 + 深蓝外描边 + 挤出） |
| 0.80s | 星星爆点 ×4 |
| 1.32s | 旁白小字「这只猫有点东西」 |
| **2.5s** | 抓痕转场（三道白爪印划过）+ 切到镜头二 |
| 2.567–2.70s | 三个「?」弹入 |
| 3.067–3.40s | 六个「静」字逐个冒出 |
| 3.30/3.50s | 两滴汗落下 |
| **4.0s** | 横向擦除转场 + 切到镜头三（炸毛） |
| 4.20–4.45s | 标签「炸毛了」弹入 |
| **4.90s** | **黄黑斜纹警告条「⚠ 前方高能 ⚠」**（伴随两次蜂鸣抖动） |
| **6.0s** | 「砰！」从 3 倍缩放砸下 + 震屏 |
| 6.60s | 副标题「这不是猫是情绪」 |
| **7.5s** | 定格（压暗 + 上下黑边收拢） |
| 8.10–8.23s | 「绝了」三个字 |
| 8.50s | 印章「喵呜日记」盖下（旋转 9°） |
| 8.90s | 「下期见」 |
| 10.0s | 结束 |

## 运行

```bash
# 关键帧预览
python make_caption.py preview

# 单帧
python make_caption.py one 1.4 frame.png

# 全部 600 帧（约 3.3 秒/帧，4 并发约 8 分钟）
python make_caption.py all 4

# 只渲某一段
python make_caption.py range 0 150 4

# 编码
ffmpeg -y -framerate 60 -i frames/f_%04d.png -c:v libx264 -preset slower -crf 18 \
       -pix_fmt yuv420p -movflags +faststart output.mp4
```

值得玩的参数：

- `HZ(...)` 的 `ext / outer / white` —— 三个描边层的粗细配比，改一下就是另一套风格
- `grad` —— 渐变的三段色标（暖金 / 冰蓝 / 品红是三套现成的）
- `char_anim` 的 `wig / bob / breath / wf` —— 抖动幅度和频率
- `spring(t, z, w)` 的 `z` —— 阻尼比。调到 0.9 就变成"稳重"的入场，0.3 会晃到失控

## 工程注记

**性能**：3.3 秒/帧。瓶颈不在花字（sprite 有缓存，每帧只做变换），而在：
- 剪影的 `MinFilter(31)` 腐蚀（大核形态学，很慢，但每张图只算一次）
- `post` 的全屏 numpy 运算（暗角 + 颗粒）
- 每帧 20 个字的 rotate + resize（BICUBIC）

**三个坑**：

- **`PIL.textbbox` 的 `anchor="mm"` 要配合 `stroke_width` 一起量**，否则描边会被裁掉。
- **`sstep` 写成标量版（`min/max`）就不能传数组**。`post` 里做暗角时踩了这个，报
  "truth value of an array is ambiguous"。数组要用 `np.clip` 的版本。
- **`_vgrad` 的 stops 是 `[(位置, hex), ...]`**，取颜色要 `for _, hx in stops`，
  直接 `for c in stops` 会拿到 tuple 然后 `int(c[1:3], 16)` 报错。

## 延伸

- 关键词：variety caption / multi-layer stroke / extruded type / spring easing /
  per-glyph phase / value noise / rim light / bokeh / vertical composition
- 同源手法：日式综艺（《月曜から夜ふかし》）的字幕包装、After Effects 的
  "多层描边"表达式、剪映/CapCut 的花字模板、Bilibili 封面的立体字
