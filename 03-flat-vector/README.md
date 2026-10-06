# 03 · 扁平矢量动画 Flat Vector

> 纯色几何、零阴影，靠回弹和节奏讲故事。一颗珊瑚色圆点，一镜长成太阳。
> 本目录：8 秒一镜到底，**v1（24fps）与 v2（60fps 重制版）双版本**，正好是"帧率与缓动如何决定质感"的对照组。

[▶ v1 · 24fps](output_v1_24fps.mp4) · [▶ v2 · 60fps 重制版](output_v2_60fps.mp4) · 脚本 [make_flat_v1.py](make_flat_v1.py) / [make_flat_v2.py](make_flat_v2.py)

## 核心知识

### 1. 动效的灵魂是时间曲线（easing）

同样两个关键帧，插值方式不同就是两个作品。本片用到的家族（Python 实现都在脚本里）：

```python
def eoc(x):        # easeOutCubic：快出缓停
    return 1 - (1 - x) ** 3

def eob(x, s=1.70158):   # easeOutBack：冲过头再弹回 = "回弹"
    x -= 1
    return 1 + (s + 1) * x**3 + s * x**2

def eio(x):        # easeInOut：两端慢中间快
    return 2*x*x if x < 0.5 else 1 - 2*(1-x)**2
```

楼群出场、虚线弹出、光芒绽放全是 `easeOutBack`；过冲系数 `s` 越大越"Q弹"。行业工具 GSAP 的本质就是这套函数 + 调度器。

### 2. 动画十二法则（精选三条）

迪士尼 1930 年代总结的十二条法则，扁平动效里最常用的是：

- **挤压与拉伸（Squash & Stretch）**：圆点砸地压扁、下落拉长——有形变才有重量
- **预备动作（Anticipation）**：发射前先下蹲 0.2 秒。没有它，动作是"发生"；有了它，动作是"爆发"
- **跟随与交叠（Follow-through）**：太阳成型后光芒才依次弹出，动作不齐发才有生命

### 3. 真抛物线，不是正弦弧

弹跳的高度轨迹用 `4u(1-u)`（抛物线），不能用 `sin(πu)`：正弦弧对称，球上升下降一样快，像飘；抛物线上升减速、下落加速，才符合重力直觉。这是 v1 观感发"假"的原因之一。

### 4. 接地锚定的压扁

压扁时如果球心不动，球会陷进地面。正确做法：**压扁时保持球底贴地**——

```python
center_y = ground - r * squash_y   # 球心 = 地面高 - 压扁后的半径
```

### 5. 帧率：24fps vs 60fps

v1 用 24fps 被"不丝滑"劝退，v2 全部 60fps 重做后过关。结论：**UI/扁平动效 60fps 是底线**（GSAP 在浏览器里就是按屏幕刷新率实时渲染）；对比本目录两个视频一遍就明白。但注意这不是普适真理——01 的手绘风恰恰需要低帧率。

### 6. 速度方向的拉伸

飞行中的球不是圆的，是**沿轨迹切线方向拉长的椭圆**。PIL 没有旋转椭圆，用参数方程生成多边形：

```python
pts = [(x + a·cosφ·cosθ - b·sinφ·sinθ, y + a·cosφ·sinθ + b·sinφ·cosθ) for φ in 48 等分]
```

`θ` 取贝塞尔轨迹的导数方向，拉伸量取速度大小。

### 7. 一镜到底 = 状态机

圆点的 8 秒是一段显式时间轴：`下落 → 砸地×4 → 弹跳×3 → 滚动 → 下蹲蓄力 → 贝塞尔弹射 → 成日呼吸`，每段独立计算位置/缩放/角度，段与段在时间上无缝拼接。叙事感来自分段，丝滑感来自段内缓动。

## 运行

```bash
python make_flat_v2.py preview   # 抽帧预览
python make_flat_v2.py all       # 480 帧（60fps×8s）到 frames2/
ffmpeg -y -framerate 60 -i frames2/f_%04d.png -c:v libx264 -preset slow -crf 17 \
       -pix_fmt yuv420p -movflags +faststart output_v2_60fps.mp4
```

值得玩的参数：时间轴常量 `T_*`、过冲系数 `s`、粒子数量与初速、配色常量。

## 延伸

- GSAP 官方文档 Easing 章节：把本片的缓动函数装进浏览器
- Disney《动画十二法则》（The Illusion of Life）
