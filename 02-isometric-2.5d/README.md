# 02 · 等轴 2.5D Isometric

> 没有透视的俯视，像摆在桌上的微缩模型。瓷砖一格一格长出来，踩着马林巴的节拍。
> 本目录：14×14 圆角瓷砖的三波"马林巴"动画，Blender 真 3D 渲染，24fps 与 60fps 双版本。

[▶ 24fps 版 output_24fps.mp4](output_24fps.mp4) · [▶ 60fps 版 output_60fps.mp4](output_60fps.mp4) · 脚本 [build_isopolis.py](build_isopolis.py)

## 核心知识

### 1. 正交相机：等轴感的来源

透视相机近大远小；**正交相机（orthographic）没有透视收缩**，平行线永远平行——这就是"摆在桌上"的错觉来源。Three.js 里对应 `OrthographicCamera`，Blender 里把相机 `type` 设为 `ORTHO` 并用 `ortho_scale` 控制取景宽度。

### 2. 等轴角度的数学

经典"真等轴"（true isometric）：

- 俯仰角 **35.264°** = arctan(1/√2)，三个坐标轴在画面上的投影两两夹角 120°
- 偏航角 45°，让网格对角线对齐屏幕水平方向

一个实用技巧：**别手算欧拉角**。把相机放在等轴方向上（位置 ≈ `(d, -d, d)`，三轴等距），再加一个 Track To 约束瞄准场景中心——角度自动正确，改距离也不破坏等轴。

### 3. 为什么用真 3D，而不是 2D 画菱形

等轴瓷砖可以用 2D 代码画平行四边形，但真 3D 让渲染器**免费**给你：圆角倒角的高光、环境光遮蔽（缝隙自然变暗）、大面积光源的软阴影。这些恰是"微缩模型感"的全部来源，2D 仿一套成本极高。

### 4. 无头渲染管线

```
blender -b -P build_isopolis.py -- full 60
```

`-b` 后台模式不打开界面，`-P` 执行脚本，`--` 后传自定义参数（本脚本支持输出模式与帧率）。EEVEE 是实时光栅渲染器，196 块瓷砖 + 软光照在笔记本 GPU 上约 2 秒/帧（1600×1000）。

脚本内三个工程要点（都是踩过坑的）：

- **bmesh 批量建模**：所有瓷砖共享一个带倒角的网格数据块，196 个对象秒建
- **材质按对象独立**：每块瓷砖一份材质副本，直接对 Base Color 打关键帧（注意 Blender 4.5 只支持 socket 级 `keyframe_insert`，材质路径级会报错）
- **动画只有两个通道**：`scale_z`（从地面长起来）+ `Base Color`（白↔深蓝），其余全是调度

### 5. 波前调度：马林巴节拍的算法

瓷砖被"敲响"的时刻不是逐帧安排的，是一个公式：

```
press_time(瓷砖) = 波次起点 + 距中心的欧氏距离 × 波速(0.15s/格) + 随机抖动(±0.04s)
```

三道波（0.1s / 2.0s / 3.9s 各发一次）+ 每波 12% 随机休眠 → 从中心荡向四周、且每波图案不同的节奏。首尾帧状态相同（平铺白砖 + 中心 2×2 深蓝），循环无缝。

### 6. 帧率：24 vs 60

本目录两个成片唯一的差别是渲染帧率。瓷砖弹起 0.45 秒的动作，24fps 只有 11 帧，60fps 有 27 帧——回弹的过冲和落点明显更顺。**数字动效类 60fps 起步**，对比着看一遍就懂。

## 运行

```bash
blender -b -P build_isopolis.py -- full 60      # 渲 360 帧到 frames_60/
ffmpeg -y -framerate 60 -i frames_60/f_%04d.png -c:v libx264 -preset slow -crf 17 \
       -pix_fmt yuv420p -movflags +faststart output_60fps.mp4
```

值得玩的参数：波速 `SPEED`、弹起倍数 3.1、波次数与间隔、瓷砖颜色。

## 延伸

- Three.js `OrthographicCamera`：网页里做同款的技术栈
- 关键词：isometric projection / orthographic camera / 2.5D game art
