# 01 · 逐帧手绘动画 Frame-by-Frame

> 每一帧重画，线条微微颤动，这叫**线条沸腾**（line boil），是手绘动画的指纹。
> 本目录：一颗卡通爆炸的 4 秒无缝循环，程序仿手绘，一拍二。

[▶ 成片 output.mp4](output.mp4) · 脚本 [make_boom.py](make_boom.py)

## 核心知识

### 1. 拍数：一拍一 / 一拍二 / 一拍三

传统手绘不是每秒画 24 张。**一拍二**（on twos）= 每张画停留 2 帧，即 12 张/秒；一拍三 = 8 张/秒。低"绘制帧率"带来的微微顿挫恰恰是手绘味的一部分——本片按 12fps 绘制 48 张原画，编码时每张停 2 帧：

```
ffmpeg -framerate 12 -i frames/f_%03d.png ... -r 24 output.mp4
```

`-framerate 12` 进、`-r 24` 出，ffmpeg 自动逐张复制，这就是一拍二。

### 2. 线条沸腾（line boil）

人手每帧重画同一轮廓，不可能分毫不差，轮廓因此"呼吸"。程序化仿真只需要一件事：**每一帧用独立随机种子抖动所有控制点**。

- 爆炸云 = 14 个圆的并集；星爆 = 多角星形多边形
- 每帧对圆心/半径/顶点加 ±2~4%（轮廓尺寸）的抖动，幅度太小于"死"、太大变"地震"
- 关键细节：**抖动种子 = 帧号**。48 帧循环里第 k 帧永远抖同一个样子，循环点才能无缝
- 经验：**纸纹底必须静态**。纸不该跟着线一起抖，只有"墨"在沸腾

### 3. 描边层 → 填充层：廉价而可靠的粗轮廓画法

PIL 没有矢量描边。画带粗轮廓的形状用两遍法：

1. 先把所有形状**放大 outline 宽度**画一遍深色（描边层）
2. 再按原尺寸画一遍亮色盖上去（填充层）

多圆并集的云朵天然适用；填充层画第二遍并稍微错位，能盖掉并集缝隙漏出的描边。

### 4. 无缝循环的数学

所有运动（脉动、碎片飞散、星光闪烁、速度线闪现）的周期必须是循环时长的**整数分之一**：

```
pulse = sin(2π · 2 · t)        # 每循环 2 次
spark = sin(2π · 3 · t + φ)    # 每循环 3 次
debris 用 frac(t + phase)      # 相位偏移制造错落
```

t 从 0 走到 1 时每个函数都恰好回到起点，循环点零跳变。

### 5. 纸纹底

numpy 一次性生成：细颗粒噪声 + 稀疏深色斑点（纸浆纤维）+ 轻微暗角。生成一次、每帧复用。

## 运行

```bash
python make_boom.py preview 6   # 单帧预览 preview.png
python make_boom.py all         # 渲染 48 帧到 frames/
ffmpeg -y -framerate 12 -i frames/f_%03d.png -c:v libx264 -preset slow -crf 18 \
       -pix_fmt yuv420p -r 24 -movflags +faststart output.mp4
```

值得玩的参数：`boil` 抖动幅度（体验"沸腾强度"）、`NF` 与拍数（改成一拍三试试）、配色常量。

## 延伸

- Richard Williams《The Animator's Survival Kit》：拍数与节奏的圣经
- 关键词：boiling line / shot on twos / rubber hose animation
