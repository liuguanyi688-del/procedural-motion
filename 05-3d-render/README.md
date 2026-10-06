# 05 · 3D 渲染 3D Render

> 三维材质、灯光与物理弹跳，软糯，有分量。八千余颗弹珠铺地，铬球砸成句号。
> 本目录：**真·刚体模拟**——4067 颗弹珠各自是 Bullet 物理引擎里的刚体，铬球砸出真弹坑，文字真的从球海犁过去。

[▶ 刚体版 output.mp4](output.mp4) · [▶ v1 运动学波版 output_kinematic_wave.mp4](output_kinematic_wave.mp4) · 脚本 [build_soft.py](build_soft.py) / [build_soft_gn.py](build_soft_gn.py)

## 两个版本，一个知识点

| | v1 运动学波 | v2 刚体模拟 |
|---|---|---|
| 原理 | GN 数学节点给每颗球规定正弦波位移 | 每颗球是 Bullet 引擎里的真刚体，运动是解出来的 |
| 观感 | "整齐的波浪"——所有球同步起伏 | 弹坑、飞溅、翻滚、堆积——每一颗都不同 |
| 本质 | **动效**（规定结果） | **物理**（给定初始条件，结果涌现） |

v1 的波再调参也"不像真的"，因为它的本质是：**所有运动都是作者的規定，没有任何因果关系**。铬球只是悬在球海上方的一块装饰，砸不砸球海都一样。v2 里铬球砸出的坑、球的飞散方向、二级弹跳，全是动量守恒和碰撞求解器的产物——这就是"真实物理引擎"和"物理感动画"的区别。

## 核心知识

### 1. Blender 刚体三板斧：Passive / Active / Kinematic

- **Active（主动）**：参与模拟，受重力与碰撞——4067 颗弹珠全是它
- **Passive（被动）**：不受力、不动，供别人碰撞——地面
- **Kinematic（运动学）**：**完全跟随关键帧动画**，但作为无限质量参与碰撞——文字和铬球用它

关键决策：**铬球全程用运动学，不切动力学**。原因一：质量比 66:1（8kg vs 0.12kg），一个不可阻挡的球犁过泡沫球海，与真刚体的轨迹差异可以忽略，但省掉一切求解器爆炸风险。原因二：切运动学→动力学的瞬间，Blender 从动画曲线推导入射速度，这个推导在高能场景是 NaN 重灾区（本片实际踩过：全场弹珠在撞击后集体消失）。

### 2. 选中集污染：本次最隐蔽的 bug

`bpy.ops.rigidbody.object_add` 作用于**所有选中对象**。给地面加被动刚体后，地面留在选中集里；随后给 4000 颗球执行 `objects_add(type='ACTIVE')`，**地面被一起改成了主动刚体**——它自己也开始自由落体，全场弹珠跟着它以完全相同的加速度坠入虚空，"永远碰不到地面"。诊断方式：读出撞击时刻的求值坐标，发现所有球 z 值完全一致且精确符合自由落体公式——零碰撞。**规矩：每次刚体/转换类 ops 之前，只选中目标对象。**

### 3. 诊断先于修改：读求值坐标，而不是渲染了猜

两版"全场消失"用三个探针定位：烘焙后 `frame_set + depsgraph` 读取弹珠的 `matrix_world`——输出 `ok=204 nan=0 far=0 zmin=zmax=-2.45` 一行就说明：无 NaN、无飞散、**所有球同 z** = 自由落体 = 地面没在碰撞。比渲染十帧瞎猜快十倍。

### 4. 无头渲染的物理烘焙

- `ptcache.bake_all(bake=True)`：把模拟烘进点缓存，渲染时逐帧读缓存——无头模式唯一可靠的路
- `bake_to_keyframes`（把模拟转成关键帧）在后台模式会因上下文缺失报错，别用
- 缓存范围必须显式设 `point_cache.frame_end`，否则默认只模拟 250 帧
- `use_split_impulse = True`：分离冲量，专治高能碰撞时的"爆求解"
- `substeps_per_second` 越高碰撞越细（本片 20 → 内部 1200Hz），代价是烘焙时间线性增长

### 5. 弹珠的颜色：世界坐标方案（EEVEE 陷阱）

给 4067 颗球随机粉/奶油/紫配色，直觉是 GN `Store Named Attribute` + 材质 `Attribute` 节点——**Cycles 有效，EEVEE 静默失效**。替代：材质里用 `Geometry → Position`（世界坐标）实时算——近文字距离场给粉奶油渐变，`White Noise(floor(pos×3))` 给每球恒定的随机斑驳。世界坐标对每颗球天然不同，不依赖任何属性传递。

另一个陷阱：**GN 生成的几何不吃宿主对象的材质槽**——必须在节点树里用 `Set Material` 节点显式赋材质，否则全是默认灰白。（v2 不用 GN 实例化了，弹珠是共享网格的真对象，材质直接生效。）

### 6. 气球文字：字体 × 倒角 × 字腔

超黑体（Arial Black）字腔极窄，0.05 倒角就能把 "o" 的孔填死。选字腔宽的字体（Segoe UI Bold），倒角 ≤ 字腔 1/10，要更圆就加字号。

### 7. 运动学刚体的"软着陆"

文字下落 + 落地压缩 + 抖动，位置逐帧烘焙成关键帧；运动学刚体跟随动画下坠时，**真的把路径上的弹珠犁开**——比任何 fake 的"压坑贴图"都真实。

## 运行

```bash
blender -b -P build_soft.py -- preview        # 烘焙物理 + 6 帧预览
blender -b -P build_soft.py -- full 60        # 烘焙 + 480 帧 @60fps
ffmpeg -y -framerate 60 -i frames_60/f_%04d.png -c:v libx264 -preset slow -crf 17 \
       -pix_fmt yuv420p -movflags +faststart output.mp4
```

值得玩的参数：铬球质量与下落高度（能量）、弹珠 `restitution`（弹性区间）、球数 `GX×GY`、镜头微震。

## 延伸

- 关键词：rigid body simulation / Bullet / kinematic vs dynamic / granular material
- 更进一步的弹珠海：Molecular Nodes / span 类的 GPU 粒子求解器，或 Houdini；Blender 内置 Bullet 在 1 万刚体量级是实用上限
