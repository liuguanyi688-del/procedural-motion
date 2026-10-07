# 08 · 赛博朋克 HUD Cyberpunk FUI

> 电影里的科幻界面：线框、滚动数据、全息地球。瞄准镜开机、搜索、锁定长江口。
> 本目录：隼眼-9 目标光学系统——线框地球 + 长江口海岸线 + 自检清单 + 频谱/遥测/十六进制数据流，60fps。

[▶ 成片 output.mp4](output.mp4) · 脚本 [make_hud.py](make_hud.py)

## 核心知识

### 1. FUI 的三层渲染：底图 + 辉光层 + 扫描线

电影感 HUD 的"发光"不是素材，是**合成**：

```python
base = 深色底图 + 所有 UI 元素(正常亮度)
glow = 纯黑画布 + 只画发光元素(亮色)
out  = ImageChops.screen(base, glow.filter(GaussianBlur(9)))
```

`screen` 混合 `1−(1−a)(1−b)` 保留颜色、只加亮度——每个亮元素自动带一圈同色辉光。最后叠 4px 间距的暗扫描线，CRT 质感完成。封装一个 `Duo` 双画布绘制器，每个元素一次调用同时画到底图和辉光层。

### 2. 线框地球：经纬线的参数化

不需要 3D 引擎，正交投影的线框球就是两族椭圆：

- **纬线**：`y = R·sin(lat)`，椭圆短轴 `R·cos(lat)×0.30`（透视压扁）
- **经线**：随时间旋转的竖椭圆，`rx = |cos(phase)|×R`——动起来就是"转动的全息地球"

长江口海岸线是手工近似的折线（13 个点 + 支流 6 个点），归一化坐标映射进球面——**叙事锚点：锁定的是长江口**。

### 3. 数据全是函数，没有随机数

FUI 的一半生命在"数据在动"：方位角、信号强度、频谱柱高、MATCH 百分比……全部来自**确定性噪声函数**：

```python
def n1(t, a=1.0):
    return (sin(3.7at) + 0.6sin(9.1at+1.3) + 0.3sin(21at+2.1)) / 1.9
```

叠加不同频率的正弦 = 平滑又不可预测的漂移。任意时刻重跑结果完全一致——渲染管线友好，出 bug 也能精确复现。

### 4. 叙事时间轴：开机 → 搜索 → 锁定

10 秒被拆成状态机，每个 UI 部件有自己的出场时刻：

| 时间 | 事件 | 画面反馈 |
|---|---|---|
| 0.3-1.3s | SYS BOOT 自检逐行打出，`[OK]` 依次点亮 | 面板逐块淡入 |
| 1.1-2.6s | 信号图/频谱/遥测上线 | 右栏数据开始滚动 |
| 2.4s+ | CANDIDATES 候选目标扫描，MATCH 从 0% 爬升 | 每帧变化 |
| 4.6s | **TGT-03 LOCKED**：瞄准框从搜索游移吸附到中心 | 括号收拢动画 |
| 4.85s | 警告横幅闪入：目标锁定 TARGET LOCKED | 条纹横幅 + 闪烁 |
| 5-10s | 锁定保持，十六进制数据流、UTC 时钟持续走 | 呼吸感 |

### 5. 中英混排：等宽字体没有中文

Consolas 这类等宽字体没有中文字形，直接画中文就是方块。解法是**双字体拼接**：EN 段用等宽、CN 段用雅黑 Bold，用 `textlength` 量出 EN 宽度后偏移绘制——封装成 `en_cn(u, x, y, en, cn, ...)` 一次调用。

### 6. 排坑

- `ImageDraw.text(xy, text, fill, font)`——**fill 在 font 之前**，font 按位置传会撞进 fill 槽再写 fill= 关键字 → "got multiple values for argument 'fill'"
- `Duo.line` 同时兼容两种调用风格（两点式 / 4 元组式），签名必须 `b=None` 让参数绑定先活下来
- 字符串乘法优先级：`"..." % x * 99.7` 是 `(字符串% x) × 99.7`——格式化完再乘浮点直接 TypeError，该加括号就加括号
- 等宽字体没有中文——所有含中文的行必须走双字体拼接

## 运行

```bash
python make_hud.py preview   # 7 帧预览
python make_hud.py all       # 600 帧（10s × 60fps）到 frames/
ffmpeg -y -framerate 60 -i frames/f_%04d.png -c:v libx264 -preset slow -crf 17 \
       -pix_fmt yuv420p -movflags +faststart output.mp4
```

值得玩的参数：`T_LOCK` 锁定时刻、波幅/频率 `n1` 的系数、海岸线 `COAST` 折线、辉光模糊半径、扫描线间距。

## 延伸

- 参考标签 Three.js 线框——3D 引擎做球体更立体，但 2D 参数化方案零依赖、渲染快 100 倍，FUI 的"平面感"反而更对味
- 关键词：FUI / sci-fi HUD / screen blend / deterministic noise / diegetic interface
