# 06 · 形变动画 Shape Morph

> 一个形状连续变成下一个，形状本身就是叙事。一滴墨变成咖啡、太阳和海鸥。
> 本目录：4 幕形变（墨滴 → 咖啡 → 日落 → 海鸥），背景/配色/字幕随场景同步过渡，60fps。

[▶ 成片 output.mp4](output.mp4) · 脚本 [make_morph.py](make_morph.py)

## 核心知识：形状插值的全部秘密就三句话

### 1. 同点数：所有形状重采样成 N 个点

两个任意多边形之间没法直接插值——顶点数不同。解法是把每个形状**按弧长均匀重采样**成相同的 N 个点：

```python
def resample(poly, n):
    # 沿闭合折线累计弧长，然后在等弧长位置取 n 个点
    target = total * k / n  →  线性插值出该位置的点
```

这一步等价于 SVG path morph 库（flubber、GSAP MorphPlugin）内部做的"点数归一化"。

### 2. 对齐：锚点决定形变"不翻卷"

光有点数还不够——点列从哪个点开始数，决定了哪个顶点对应哪个顶点。错位的对应会让形状在插值中途"拧麻花"。解法：给每个形状指定一个**语义锚点**（墨滴的尾巴尖、杯口的中心、太阳的顶、海鸥的中央凹口），把点列旋转到锚点开头：

```python
rotate_to_anchor(pts, anchor)   # 找最接近 anchor 的点，旋转到队首
```

另外用**有向面积**统一绕向（全部顺时针），防止一正一反的两个形状插值时塌成线。

### 3. 缓动插值：`p = easeInOutCubic(t)`，逐点 lerp

```python
poly = [(lerp(a[0], b[0], p), lerp(a[1], b[1], p)) for a, b in zip(A, B)]
```

没有别的了。形变动画的"高级感"全部来自：对应关系正确（不翻卷）+ 缓动正确（easeInOut）+ 中间不停顿。

### 4. 场景系统：形状只是主角，配角要有退场戏

每个场景 = 主形状 + 背景双色分割 + 小件（蒸汽/光芒/海平线/云）+ 字幕 + 进度点。规则：

- **形变期**（1.0s）：主形状逐点插值，背景双色与分割线位置同步 lerp，上一幕小件退场
- **停留期**（1.35s）：本幕小件依次弹入（easeOutBack 错峰），字幕淡入
- 日落场景的海面矩形画在主形状**之后**，才能盖住太阳的下缘——画家算法的层次即叙事

### 5. 背景也是"形状"

分割线位置 `ysplit` 本身就是可插值的量：墨滴/咖啡场景分割线在画面外（单色），日落时滑到 560 露出蓝海，海鸥时停在 760。**把一切状态都变成可插值的数字，是所有形变动画的通用心法。**

## 运行

```bash
python make_morph.py preview   # 8 帧预览
python make_morph.py all       # 564 帧（9.4s × 60fps）到 frames/
ffmpeg -y -framerate 60 -i frames/f_%04d.png -c:v libx264 -preset slow -crf 17 \
       -pix_fmt yuv420p -movflags +faststart output.mp4
```

值得玩的参数：`NP`（点数，影响细节保持）、各场景 `scale / center`、小件弹入时刻、配色表。

## 延伸

- flubber：JS 里最著名的任意形状插值库，思想与本目录一致（重采样 + 对应 + 插值）
- GSAP MorphPlugin / SVG `<animate>` 的 path 插值：要求路径指令结构一致，本质相同
- 关键词：shape morphing / vertex interpolation / arc-length parameterization
