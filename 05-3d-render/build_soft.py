# -*- coding: utf-8 -*-
"""05 · 3D 渲染「柔软着陆」：气球字 soft + 铬球句号 + 8733 颗弹珠海的冲击波
Blender 无头 EEVEE。弹珠海 = 几何节点实例化，波 = GN 数学节点按时间计算。
用法: blender -b -P build_soft.py -- [preview|full] [fps]
"""
import bpy, bmesh, math, os, sys
from math import radians
from mathutils import Matrix

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MODE = ARGS[0] if ARGS else "full"
FPS = int(ARGS[1]) if len(ARGS) > 1 else 60
OUT = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(OUT, "frames_%d" % FPS)
os.makedirs(FR, exist_ok=True)

DUR = 8.0
RES_X, RES_Y = 1600, 1000

# 时间轴（秒）
T_TXT0, T_TXT1 = 0.20, 0.75          # 文字下落
T_IMPACT = 2.25                       # 铬球触地 → 冲击波起点
T_CH0 = 1.80                          # 铬球开始下落
REST_TXT = 0.33
REST_CHROME = 0.38
IMPACT = (2.10, 0.20)
TEXT_CENTER = (-0.75, 0.0)

# 弹珠海参数（向参考的 8,700 颗致敬：123×71 = 8733）
BALL_R, SPACING = 0.115, 0.30
GX, GY = 123, 71
FIELD_X, FIELD_Y = GX * SPACING, GY * SPACING

# 波参数：波前速度 = WAVE_SPEED/OMEGA ≈ 2.5 格/秒，门控与其同步
WAVE_A = 0.55
WAVELEN, WAVE_SPEED = 1.3, 12.0
OMEGA = 2 * math.pi / WAVELEN
GATE_PER_UNIT = 0.8 * OMEGA / WAVE_SPEED
DECAY = 0.04
FADE_T = 6.2

# ---------------- 场景 ----------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
try:
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
except Exception:
    scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.fps = FPS
scene.frame_start = 1
scene.frame_end = int(DUR * FPS)
scene.view_settings.view_transform = 'Standard'
ee = scene.eevee
for attr, val in (("taa_render_samples", 32), ("use_raytracing", True)):
    try:
        setattr(ee, attr, val)
    except Exception:
        pass

def F(t):
    return int(round(t * FPS)) + 1

# ---------------- 世界与灯光（粉奶油软光） ----------------
world = bpy.data.worlds.new("W")
scene.world = world
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
bg.inputs[0].default_value = (0.90, 0.68, 0.73, 1.0)
bg.inputs[1].default_value = 0.8

key = bpy.data.lights.new("key", 'AREA')
key.energy = 700
key.size = 9
ko = bpy.data.objects.new("key", key)
ko.location = (-3, -6, 9)
ko.rotation_euler = (radians(32), 0, radians(-18))
scene.collection.objects.link(ko)

fill = bpy.data.lights.new("fill", 'AREA')
fill.energy = 220
fill.size = 16
fo = bpy.data.objects.new("fill", fill)
fo.location = (5, 7, 7)
scene.collection.objects.link(fo)

# ---------------- 地面衬底 ----------------
gbm = bpy.data.meshes.new("ground")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1, matrix=Matrix.LocRotScale((0, 0, -0.05), None, (60, 40, 0.1)))
bm.to_mesh(gbm)
bm.free()
gm = bpy.data.materials.new("groundmat")
gm.use_nodes = True
gbsdf = next(n for n in gm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
gbsdf.inputs['Base Color'].default_value = (0.92, 0.80, 0.80, 1)
gbsdf.inputs['Roughness'].default_value = 0.6
go = bpy.data.objects.new("ground", gbm)
go.data.materials.append(gm)
scene.collection.objects.link(go)

# ---------------- 相机：低机位 + 浅景深 ----------------
cam = bpy.data.cameras.new("C")
cam.lens = 50
cam.dof.use_dof = True
cam.dof.focus_distance = 7.5
cam.dof.aperture_fstop = 2.2
co = bpy.data.objects.new("C", cam)
co.location = (0, -7.2, 2.4)
scene.collection.objects.link(co)
tgt = bpy.data.objects.new("tgt", None)
tgt.location = (0, 0.8, 0.75)
scene.collection.objects.link(tgt)
con = co.constraints.new('TRACK_TO')
con.target = tgt
con.track_axis = 'TRACK_NEGATIVE_Z'
con.up_axis = 'UP_Y'
scene.camera = co

# ---------------- 几何节点：弹珠海 + 冲击波 ----------------
tree = bpy.data.node_groups.new("WaveField", 'GeometryNodeTree')
tree.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
nt = tree

def N(t, x=0, y=0):
    n = nt.nodes.new(t)
    n.location = (x, y)
    return n

def L(a, ao, b, bi):
    nt.links.new(a.outputs[ao], b.inputs[bi])

def M(op, a=None, b=None, clamp=False, x=0, y=0):
    n = N('ShaderNodeMath', x, y)
    n.operation = op
    n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, tuple):
            nt.links.new(v[0].outputs[v[1]], n.inputs[i])
        else:
            n.inputs[i].default_value = v
    return n

grid = N('GeometryNodeMeshGrid', -1400, 0)
grid.inputs['Size X'].default_value = FIELD_X
grid.inputs['Size Y'].default_value = FIELD_Y
grid.inputs['Vertices X'].default_value = GX
grid.inputs['Vertices Y'].default_value = GY

setpos = N('GeometryNodeSetPosition', -1150, 0)
L(grid, 'Mesh', setpos, 'Geometry')

pos = N('GeometryNodeInputPosition', -1400, -420)

# t - T0
time_n = N('GeometryNodeInputSceneTime', -1400, -820)
dt = M('SUBTRACT', (time_n, 'Seconds'), T_IMPACT, x=-1200, y=-820)

# 冲击距离（网格顶点位置 - 冲击点，取水平长度）
sub_i = N('ShaderNodeVectorMath', -1100, -560)
sub_i.operation = 'SUBTRACT'
sub_i.inputs[1].default_value = (IMPACT[0], IMPACT[1], 0)
nt.links.new(pos.outputs['Position'], sub_i.inputs[0])
len_i = N('ShaderNodeVectorMath', -950, -560)
len_i.operation = 'LENGTH'
L(sub_i, 'Vector', len_i, 0)

# 波前门控：smoothstep(clamp((t-T0-dist*gate)/0.2))，与波峰同速推进
gd = M('MULTIPLY', (len_i, 'Value'), GATE_PER_UNIT, x=-800, y=-640)
g1 = M('SUBTRACT', (dt, 0), (gd, 0), x=-650, y=-680)
g2 = M('DIVIDE', (g1, 0), 0.2, clamp=True, x=-500, y=-680)
gsq = M('MULTIPLY', (g2, 0), (g2, 0), x=-350, y=-680)
g3 = M('MULTIPLY', (g2, 0), 2, x=-350, y=-800)
g4 = M('SUBTRACT', 3, (g3, 0), x=-200, y=-800)
gate = M('MULTIPLY', (gsq, 0), (g4, 0), x=-50, y=-740)

# 相位 sin(dist*ω - (t-T0)*speed)
ph1 = M('MULTIPLY', (len_i, 'Value'), OMEGA, x=-800, y=-980)
ph2 = M('MULTIPLY', (dt, 0), WAVE_SPEED, x=-800, y=-1120)
ph3 = M('SUBTRACT', (ph1, 0), (ph2, 0), x=-600, y=-1040)
sine = M('SINE', (ph3, 0), x=-450, y=-1040)

# 距离衰减 e^(-DECAY*dist)
dmul = M('MULTIPLY', (len_i, 'Value'), -DECAY, x=-950, y=-1260)
decay = M('EXPONENT', (dmul, 0), x=-800, y=-1260)

# 全局时间衰减 fade = clamp(1-(t-T0)/FADE_T)
fdiv = M('DIVIDE', (dt, 0), FADE_T, x=-800, y=-1400)
fade = M('SUBTRACT', 1, (fdiv, 0), clamp=True, x=-650, y=-1400)

h1 = M('MULTIPLY', (sine, 0), WAVE_A, x=-250, y=-1040)
h2 = M('MULTIPLY', (h1, 0), (decay, 0), x=-100, y=-1100)
h3 = M('MULTIPLY', (h2, 0), (gate, 0), x=50, y=-900)
h4 = M('MULTIPLY', (h3, 0), (fade, 0), x=200, y=-900)
zvec = N('ShaderNodeCombineXYZ', 380, -900)
nt.links.new(h4.outputs[0], zvec.inputs['Z'])
nt.links.new(zvec.outputs['Vector'], setpos.inputs['Offset'])

# 颜色：靠近文字偏粉 + 随机斑驳（prox*0.7 + rand*0.3）
sub_t = N('ShaderNodeVectorMath', -1100, -300)
sub_t.operation = 'SUBTRACT'
sub_t.inputs[1].default_value = (TEXT_CENTER[0], TEXT_CENTER[1], 0)
nt.links.new(pos.outputs['Position'], sub_t.inputs[0])
len_t = N('ShaderNodeVectorMath', -950, -300)
len_t.operation = 'LENGTH'
L(sub_t, 'Vector', len_t, 0)
p1 = M('SUBTRACT', 1, (len_t, 'Value'), x=-800, y=-300)
p2 = M('DIVIDE', (p1, 0), 9.5, clamp=True, x=-650, y=-300)
mixp = M('MULTIPLY', (p2, 0), 0.7, x=-480, y=-300)
rand = N('FunctionNodeRandomValue', -800, -160)
rand.data_type = 'FLOAT'
rand.inputs[2].default_value = 0.0
rand.inputs[3].default_value = 1.0
rand.inputs['Seed'].default_value = 7
rmul = M('MULTIPLY', (rand, 1), 0.3, x=-480, y=-160)
tint = M('ADD', (mixp, 0), (rmul, 0), clamp=True, x=-320, y=-260)

# 实例化球体（先实例化，再在 INSTANCE 域存 tint 属性）
sphere = N('GeometryNodeMeshUVSphere', 560, 60)
sphere.inputs['Radius'].default_value = BALL_R
sphere.inputs['Segments'].default_value = 20
sphere.inputs['Rings'].default_value = 12
smooth = N('GeometryNodeSetShadeSmooth', 760, 60)
L(sphere, 'Mesh', smooth, 'Geometry')

# 实例化球体（颜色不走 GN 属性——EEVEE 读不到实例属性，改在材质里按世界坐标算）
inst = N('GeometryNodeInstanceOnPoints', 950, 0)
L(setpos, 'Geometry', inst, 'Points')
L(smooth, 'Geometry', inst, 'Instance')

rscale = N('FunctionNodeRandomValue', 1150, -560)
rscale.data_type = 'FLOAT'
rscale.inputs[2].default_value = 0.9
rscale.inputs[3].default_value = 1.1
rscale.inputs['Seed'].default_value = 3
sci = N('GeometryNodeScaleInstances', 1350, 0)
L(inst, 'Instances', sci, 'Instances')
nt.links.new(rscale.outputs[1], sci.inputs['Scale'])

out = N('NodeGroupOutput', 1750, 0)   # 材质赋值后由 Set Material 接入

field_obj = bpy.data.objects.new("field", bpy.data.meshes.new("field_mesh"))
scene.collection.objects.link(field_obj)
mod = field_obj.modifiers.new("GN", 'NODES')
mod.node_group = tree

# 弹珠材质：按世界坐标算颜色（EEVEE 可靠）——近文字偏粉 + 每球随机斑驳 + 5% 紫
bmat = bpy.data.materials.new("ballmat")
bmat.use_nodes = True
bnt = bmat.node_tree
bbsdf = next(n for n in bnt.nodes if n.type == 'BSDF_PRINCIPLED')
bbsdf.inputs['Roughness'].default_value = 0.16

geo = bnt.nodes.new('ShaderNodeNewGeometry')            # 世界坐标
def vm(op, a, b=None, val=None):
    n = bnt.nodes.new('ShaderNodeVectorMath')
    n.operation = op
    if a is not None:
        bnt.links.new(a, n.inputs[0])
    if b is not None:
        bnt.links.new(b, n.inputs[1])
    if val is not None:
        sock = n.inputs['Scale'] if op == 'SCALE' else n.inputs[1]
        sock.default_value = val
    return n
def bm(op, a=None, b=None, val=None, clamp=False):
    n = bnt.nodes.new('ShaderNodeMath')
    n.operation = op
    n.use_clamp = clamp
    if a is not None:
        bnt.links.new(a, n.inputs[0])
    if b is not None:
        bnt.links.new(b, n.inputs[1])
    if val is not None:
        n.inputs[1].default_value = val
    return n

subt = vm('SUBTRACT', geo.outputs['Position'], val=(TEXT_CENTER[0], TEXT_CENTER[1], 0))
lent = vm('LENGTH', subt.outputs['Vector'])
p1 = bm('SUBTRACT', val=1.0)
bnt.links.new(lent.outputs['Value'], p1.inputs[0])
p2 = bm('DIVIDE', p1.outputs[0], val=7.0, clamp=True)
mixp = bm('MULTIPLY', p2.outputs[0], val=0.85)

sc1 = vm('SCALE', geo.outputs['Position'], val=3.0)
fl1 = vm('FLOOR', sc1.outputs['Vector'])
wn1 = bnt.nodes.new('ShaderNodeTexWhiteNoise')
wn1.noise_dimensions = '3D'
bnt.links.new(fl1.outputs['Vector'], wn1.inputs['Vector'])
r1 = bm('MULTIPLY', wn1.outputs['Value'], val=0.15)
tint = bm('ADD', mixp.outputs[0], r1.outputs[0], clamp=True)

mixc = bnt.nodes.new('ShaderNodeMix')
mixc.data_type = 'RGBA'
mixc.inputs[6].default_value = (0.93, 0.83, 0.66, 1)   # 奶油
mixc.inputs[7].default_value = (0.98, 0.42, 0.50, 1)   # 粉
bnt.links.new(tint.outputs[0], mixc.inputs['Factor'])

sc2 = vm('SCALE', geo.outputs['Position'], val=3.0)
ad2 = vm('ADD', sc2.outputs['Vector'], val=(37.7, 11.3, 53.1))
fl2 = vm('FLOOR', ad2.outputs['Vector'])
wn2 = bnt.nodes.new('ShaderNodeTexWhiteNoise')
wn2.noise_dimensions = '3D'
bnt.links.new(fl2.outputs['Vector'], wn2.inputs['Vector'])
gt = bm('GREATER_THAN', wn2.outputs['Value'], val=0.94)
mixv = bnt.nodes.new('ShaderNodeMix')
mixv.data_type = 'RGBA'
mixv.inputs[7].default_value = (0.56, 0.36, 0.92, 1)   # 紫罗兰
bnt.links.new(mixc.outputs[2], mixv.inputs[6])
bnt.links.new(gt.outputs[0], mixv.inputs['Factor'])
bnt.links.new(mixv.outputs[2], bbsdf.inputs['Base Color'])
field_obj.data.materials.append(bmat)

# GN 生成的实例几何不吃宿主材质槽——必须在节点树里显式 Set Material
smat = N('GeometryNodeSetMaterial', 1550, 60)
L(sci, 'Instances', smat, 'Geometry')
smat.inputs['Material'].default_value = bmat
L(smat, 'Geometry', out, 'Geometry')

# ---------------- 气球文字 soft ----------------
fonts = [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\ariblk.ttf",
         r"C:\Windows\Fonts\comicbd.ttf", r"C:\Windows\Fonts\arialbd.ttf"]
font = next((bpy.data.fonts.load(p) for p in fonts if os.path.exists(p)), None)
txt = bpy.data.curves.new("soft", type='FONT')
txt.body = "soft"
if font:
    txt.font = font
txt.size = 2.6
txt.extrude = 0.28
txt.bevel_depth = 0.02
txt.bevel_resolution = 6
txt.resolution_u = 16
txt.space_character = 1.12
txt.align_x = 'CENTER'
txt_obj = bpy.data.objects.new("soft", txt)
txt_obj.location = (TEXT_CENTER[0], TEXT_CENTER[1], REST_TXT)
scene.collection.objects.link(txt_obj)
bpy.context.view_layer.objects.active = txt_obj
txt_obj.select_set(True)
bpy.ops.object.convert(target='MESH')
for p in txt_obj.data.polygons:
    p.use_smooth = True

tmat = bpy.data.materials.new("balloon")
tmat.use_nodes = True
tbsdf = next(n for n in tmat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
tbsdf.inputs['Base Color'].default_value = (0.93, 0.25, 0.36, 1)
tbsdf.inputs['Roughness'].default_value = 0.09
try:
    tbsdf.inputs['Coat Weight'].default_value = 0.6
except Exception:
    pass
txt_obj.data.materials.append(tmat)

# 文字下落 + 被波抖动（逐帧烘焙 z）
def text_z(t):
    if t < T_TXT0:
        return 3.4
    if t < T_TXT1:
        u = (t - T_TXT0) / (T_TXT1 - T_TXT0)
        return 3.4 + (REST_TXT - 3.4) * u * u
    bob_t = max(0.0, t - 2.45)
    return REST_TXT + 0.05 * math.exp(-1.1 * bob_t) * math.sin(2 * math.pi * 1.2 * bob_t)

for f in range(1, scene.frame_end + 1):
    t = (f - 1) / FPS
    txt_obj.location.z = text_z(t)
    txt_obj.keyframe_insert("location", index=2, frame=f)
# 落地挤压（原点在字腰，微微压进球里=软）
for (tt, sc) in ((0.70, (1, 1, 1)), (0.78, (1.10, 1.10, 0.80)),
                 (0.90, (0.96, 0.96, 1.05)), (1.05, (1, 1, 1)),
                 (2.45, (1, 1, 1)), (2.62, (1.03, 1.03, 0.96)), (2.95, (1, 1, 1))):
    txt_obj.scale = sc
    txt_obj.keyframe_insert("scale", frame=F(tt))

# ---------------- 铬球句号 ----------------
ch = bpy.data.objects.new("chrome", bpy.data.meshes.new("chrome"))
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=REST_CHROME)
bm.to_mesh(ch.data)
bm.free()
for p in ch.data.polygons:
    p.use_smooth = True
cmat = bpy.data.materials.new("chrome")
cmat.use_nodes = True
cbsdf = next(n for n in cmat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
cbsdf.inputs['Base Color'].default_value = (0.92, 0.92, 0.94, 1)
cbsdf.inputs['Metallic'].default_value = 1.0
cbsdf.inputs['Roughness'].default_value = 0.02
ch.data.materials.append(cmat)
ch.location = (IMPACT[0], IMPACT[1], 8.0)
scene.collection.objects.link(ch)

def chrome_z(t):
    if t < T_CH0:
        return 8.0
    if t < T_IMPACT:
        u = (t - T_CH0) / (T_IMPACT - T_CH0)
        return 8.0 + (REST_CHROME - 8.0) * u * u
    if t < 2.80:
        u = (t - T_IMPACT) / 0.55
        return REST_CHROME + 0.55 * 4 * u * (1 - u)
    if t < 3.15:
        u = (t - 2.80) / 0.35
        return REST_CHROME + 0.16 * 4 * u * (1 - u)
    return REST_CHROME

for f in range(1, scene.frame_end + 1):
    t = (f - 1) / FPS
    ch.location.z = chrome_z(t)
    ch.keyframe_insert("location", index=2, frame=f)
    s = 0.001 if t < T_CH0 else 1.0
    ch.scale = (s, s, s)
    ch.keyframe_insert("scale", frame=f)

# ---------------- 输出 ----------------
scene.render.image_settings.file_format = 'PNG'
if MODE == "preview":
    scene.render.resolution_percentage = 50
    for f in (45, 140, 180, 240, 330, 470):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(OUT, "prev_%03d.png" % f)
        bpy.ops.render.render(write_still=True)
    print("PREVIEW DONE")
else:
    scene.render.filepath = os.path.join(FR, "f_")
    bpy.ops.render.render(animation=True)
    print("FULL RENDER DONE")
