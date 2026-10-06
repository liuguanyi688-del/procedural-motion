# 05 · 3D 渲染 3D Render

> 三维材质、灯光与物理弹跳，软糯，有分量。八千余颗弹珠铺地，铬球砸成句号。
> 本目录：气球字 soft 柔软着陆 + 铬球成为句号 + 8733 颗弹珠的冲击波，Blender 几何节点 + EEVEE。

[▶ 成片 output.mp4](output.mp4) · 脚本 [build_soft.py](build_soft.py)

## 核心知识

### 1. 几何节点实例化：8733 颗球怎么渲染的

不是建 8733 个对象，而是一棵 GN 树：

```
网格 Grid(123×71) → Set Position(波形偏移) → Instance on Points(UV Sphere) → Scale Instances(±10% 随机) → Set Material
```

8733 颗球共享一个球体网格，显存和渲染开销与一颗球同量级——**实例化的本质是"一份几何，多份变换"**。

### 2. 冲击波 = 一条数学公式，不是模拟

波高是五个因子的乘积，全部用 GN 数学节点搭建：

```
h = A · sin(dist·ω − Δt·speed) · e^(−k·dist) · gate · fade
        └行波相位┘         └距离衰减┘   └波前门控┘ └时间衰减┘
```

- **行波相位** `sin(dist·ω − Δt·speed)`：波峰以 `speed/ω` 的速度向外跑
- **波前门控** `smoothstep(clamp((Δt − dist/gate_speed)/0.2))`：撞击前波不存在，撞击后从落点逐渐"放开"。**门控速度必须与波峰速度一致**（或略慢 20%）——这是本次最隐蔽的坑：门控比波峰慢太多，波永远被压着看不见
- 时间衰减 `1 − Δt/6.2`：波在片尾归于平静，首尾呼应

### 3. 调试方法论：把中间量直接当输出渲染

这次开发波函数时"全链路都对、结果全平"，靠**二分探针**定位：把 `sin`、`×gate`、`×fade` 各级中间结果轮流接到最终输出渲染一帧——三次渲染就把断点锁定。比盯着节点树猜快一个数量级。**每个探针 = 一份只改一行链接的脚本副本**。

### 4. EEVEE 读不到实例属性（重要陷阱）

想给每颗球随机的粉/奶油/紫配色，直觉做法是 GN 里 `Store Named Attribute`（实例域）+ 材质里 `Attribute` 节点读取——**这在 Cycles 有效，在 EEVEE 静默失效**（读到 0）。两个替代方案：

- **方案 A（本目录采用）**：材质里用 `Geometry → Position`（世界坐标）实时计算颜色——近文字距离场 + `White Noise(floor(pos×3))` 做每球恒定的随机斑驳。位置对每颗球天然不同，无需任何属性传递
- 方案 B：GN 里 `Realize Instances` 后存点域属性——但牺牲实例化的全部性能优势

### 5. GN 生成的几何不吃宿主材质槽

材质挂到 GN 对象上、球却渲染成默认灰白——因为**节点树生成的几何需要在树内用 `Set Material` 节点显式赋材质**。这是 GN 渲染流水线最常踩的坑之一。

### 6. 气球文字：字体 × 倒角 × 字腔的三角平衡

Blender 文本对象 `extrude + bevel` 很容易做出气球字，但**倒角半径会同时侵蚀字母内腔（counters）**：Arial Black 这类超黑体字腔极窄，0.05 的倒角就能把 "o" 的孔填死。经验：

- 选字腔宽的字体（Segoe UI Bold > Arial Black）
- 倒角 ≤ 字腔宽度的 1/10，想要圆润就加字号而不是加倒角
- `space_character` 微调字距，防止相邻字母的倒角粘连

### 7. 软着陆：逐帧烘焙的位置动画

文字下落 + 落地压缩 + 被波抖动，位置不是关键帧摆的，是 Python 函数逐帧算出来直接烘焙：

```python
z = REST + 0.05·e^(−1.1·τ)·sin(2π·1.2·τ)    # 冲击波掠过时的抖动，指数衰减
```

确定性 100%，改时间轴零成本。铬球的抛物线弹跳同理（见 03 的"真抛物线"）。

### 8. 浅景深

`camera.dof`：对焦在文字平面，f/2.2——前景与远处的弹珠化成奶油色光斑，"微缩模型"的氛围一半靠它。

## 运行

```bash
blender -b -P build_soft.py -- preview        # 6 帧预览（50% 分辨率）
blender -b -P build_soft.py -- full 60        # 480 帧 @60fps 到 frames_60/
ffmpeg -y -framerate 60 -i frames_60/f_%04d.png -c:v libx264 -preset slow -crf 17 \
       -pix_fmt yuv420p -movflags +faststart output.mp4
```

值得玩的参数：波幅 `WAVE_A`、波速、球数 `GX×GY`、配色三件套、铬球落点 `IMPACT`。

## 延伸

- 关键词：geometry nodes / instance on points / procedural wave / EEVEE Next
- 参考标签是 Blender Cycles——Cycles 下光追反射与实例属性更完整，渲染时间换质量；EEVEE Next 实时管线是本目录的选择（4070 上 480 帧约 10 分钟）
