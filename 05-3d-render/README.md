# 05 · 3D 渲染 3D Render

> 三维材质、灯光与物理弹跳，软糯，有分量。八千余颗弹珠铺地，铬球砸成句号。
> 本目录经历三版迭代（都保留可对比）：运动学波 → 刚体模拟 → **软膜果冻**，正好是一部"什么样的物理才是对的物理"的教材。

[▶ 最终版·软膜果冻 output.mp4](output.mp4) · [▶ v2 刚体颗粒 output_rigid_granular.mp4](output_rigid_granular.mp4) · [▶ v1 运动学波 output_kinematic_wave.mp4](output_kinematic_wave.mp4)

脚本：[build_soft.py](build_soft.py)（最终版）· build_soft_gn.py（v1，git 历史中）

## 三版演进：什么才是"对的物理"

| | v1 运动学波 | v2 刚体模拟 | v3 软膜果冻（最终） |
|---|---|---|---|
| 模型 | GN 数学节点给每颗球规定正弦波 | 4067 颗球各自是 Bullet 刚体 | 球海 = 一张软膜的高度场，球骑在膜上 |
| 观感 | 整齐的波浪，同步起伏 | 弹坑、飞溅、颗粒乱滚 | 平滑的涟漪、球被压扁、文字陷进去 |
| 错在哪 | 一切运动都是规定，铬球与球海毫无因果 | 物理是真的，但**情绪错了**：颗粒混沌 ≠ 软糯 | — |

v2 的教训最有价值：真实（rigid body simulation 100% 正确）不等于正确（reference 要的是软膜果冻，不是砂砾爆炸）。**"软"的正确物理模型是把球海看成一整张弹性膜上的一颗颗果冻，而不是一堆互不相关的刚体。**

## 最终版核心知识

### 1. 软膜高度场的构成

球的上下运动由三个高度场叠加，全是解析公式（GN 数学节点）：

```
H = 波纹(text) + 波纹(chrome) + 压坑(text) + 压坑(chrome)

波纹    = A·sin(dist·ω − Δt·speed) · e^(−k·dist) · gate · fade
压坑    = −depth · e^(−(dist/σ)²) · settle(t)     ← 文字/铬球的"体重"
```

两道波（文字落地、铬球触地各一发）+ 两个静态压坑，让画面因果清晰：每个起伏都有来源。

### 2. 果冻感三要素

1. **沿法线倾斜**：解析求高度场梯度（波用 cos、高斯坑用解析导数），实例 `Align Euler to Vector` 把每颗球的 Z 对齐膜面法线——球"躺"在坡上
2. **按坡度压扁**：`scale_z = 0.75 + 0.25/sqrt(1+(0.5·|∇H|)²)`——坡上果冻被压扁，0.75 下限防止煎饼
3. **压坑果冻压扁**：文字/铬球压坑内 `scale_z ×(1−0.3·e^(−(d/σ)²))`——被体重压住的球瘪下去

材质再补一刀：Principled 开 Subsurface（次表面散射）+ Coat，奶油果冻的"透光感"。

### 3. 排障实录：四个 bug 四种类型（每个都是通用教训）

| 症状 | 根因 | 教训 |
|---|---|---|
| 全场球消失 | `CombineXYZ` 只接了 Z，X/Y 默认 **0** → 实例被缩成零宽度 | 组合向量节点逐通道检查默认值 |
| 全场球被改类型 | `bpy.ops.rigidbody.*` 作用于**全部选中对象**，地面残留在选中集里被改成主动刚体，跟着一起自由落体 | 刚体/转换类 ops 前只选中目标 |
| 撞击后全场消失 | 60kg 铬球从 21m 落下，12kJ 动能把 0.12kg 的球崩出画面 | 真物理=真参数：能量必须匹配叙事 |
| 节点树搭到一半类型报错 | 标量 Math / 矢量 VectorMath 助手混用、`(节点,口)` 元组重复包裹 | 封装构建函数时统一签名，先写类型约定 |

### 4. 无头渲染与调试

- 物理部分（v2）无头模式只能 `ptcache.bake_all`，`bake_to_keyframes` 需要完整 GUI 上下文会报错
- GN 树在无头模式用"探针法"调试：把中间量（梯度、高度）直接接到最终输出渲一帧，三个探针锁定断点
- `Scene Time` 节点提供秒数；所有时间常数（`WAVE_T0` 等）都是脚本顶部常量

## 运行

```bash
blender -b -P build_soft.py -- preview        # 6 帧预览（50% 分辨率）
blender -b -P build_soft.py -- full 60        # 480 帧 @60fps 到 frames_60/
ffmpeg -y -framerate 60 -i frames_60/f_%04d.png -c:v libx264 -preset slow -crf 17 \
       -pix_fmt yuv420p -movflags +faststart output.mp4
```

值得玩的参数：两道波的 `A / WAVELEN / SPEED`、压坑 `depth / σ`、果冻压扁的 0.75 下限、球数 `GX×GY`。

## 延伸

- 关键词：height field / membrane / jelly squash / align euler to vector / subsurface
- 参考用 Cycles 渲染（光追更润），本目录 EEVEE Next 在 4070 上 480 帧约 12 分钟
