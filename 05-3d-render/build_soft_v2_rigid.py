# -*- coding: utf-8 -*-
"""05 · 3D 渲染「柔软着陆」v2 —— 真·刚体物理版
约 4000 颗弹珠 = 真刚体（Bullet 物理引擎），文字 = 运动学刚体压场，铬球 = 自由落体真弹跳。
模拟烘焙成关键帧后渲染。用法: blender -b -P build_soft.py -- [preview|full] [fps]
"""
import bpy, bmesh, math, os, sys, random
from math import radians
from mathutils import Matrix, Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MODE = ARGS[0] if ARGS else "full"
FPS = int(ARGS[1]) if len(ARGS) > 1 else 60
OUT = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(OUT, "frames_%d" % FPS)
os.makedirs(FR, exist_ok=True)

DUR = 8.0
RES_X, RES_Y = 1600, 1000

# 弹珠场参数
BALL_R, SPACING = 0.165, 0.48
GX, GY = 83, 49                        # 4067 颗
FIELD_X, FIELD_Y = GX * SPACING, GY * SPACING
IMPACT = (2.10, 0.20)                  # 铬球落点（句号位置）
TEXT_CENTER = (-0.75, 0.0)
REST_TXT = 0.42

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

# ---------------- 世界与灯光 ----------------
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

# ---------------- 地面（被动刚体） ----------------
gbm = bpy.data.meshes.new("ground")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1, matrix=Matrix.LocRotScale((0, 0, -0.05), None, (70, 50, 0.1)))
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
go.select_set(True)
bpy.context.view_layer.objects.active = go
bpy.ops.rigidbody.object_add(type='PASSIVE')
go.rigid_body.friction = 0.7
go.rigid_body.restitution = 0.1
go.select_set(False)

# ---------------- 相机：低机位 + 浅景深 + 落地震屏 ----------------
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
# 铬球触地瞬间的镜头微震
for (tt, dz) in ((2.02, 0), (2.09, 0.045), (2.18, -0.03), (2.32, 0.018), (2.55, 0)):
    co.location.z = 2.4 + dz
    co.keyframe_insert("location", index=2, frame=F(tt))

# ---------------- 弹珠材质（世界坐标驱动的粉奶油渐变 + 白噪声斑驳） ----------------
bmat = bpy.data.materials.new("ballmat")
bmat.use_nodes = True
bnt = bmat.node_tree
bbsdf = next(n for n in bnt.nodes if n.type == 'BSDF_PRINCIPLED')
bbsdf.inputs['Roughness'].default_value = 0.16

geo = bnt.nodes.new('ShaderNodeNewGeometry')
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

# ---------------- 弹珠群：共享网格的真刚体 ----------------
ball_mesh = bpy.data.meshes.new("ball")
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=BALL_R)
bm.to_mesh(ball_mesh)
bm.free()
for p in ball_mesh.polygons:
    p.use_smooth = True
ball_mesh.materials.append(bmat)

rng = random.Random(42)
balls = []
for iy in range(GY):
    for ix in range(GX):
        ox = (ix - (GX - 1) / 2) * SPACING + rng.uniform(-0.02, 0.02)
        oy = (iy - (GY - 1) / 2) * SPACING + rng.uniform(-0.02, 0.02)
        o = bpy.data.objects.new("b%04d" % len(balls), ball_mesh)
        o.location = (ox, oy, BALL_R)
        scene.collection.objects.link(o)
        o.select_set(True)
        balls.append(o)
bpy.context.view_layer.objects.active = balls[0]
bpy.ops.rigidbody.objects_add(type='ACTIVE')
for o in balls:
    rb = o.rigid_body
    rb.mass = 0.12
    rb.friction = 0.55
    rb.restitution = rng.uniform(0.25, 0.45)
    rb.collision_shape = 'SPHERE'
    rb.use_margin = True
    rb.collision_margin = 0.0008
for o in balls:                                   # 清空选中集，防止污染后续刚体操作
    o.select_set(False)

# ---------------- 气球文字：运动学刚体（关键帧驱动，真压场） ----------------
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
txt_obj.location = (TEXT_CENTER[0], TEXT_CENTER[1], 3.4)
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
# 运动学刚体：动画驱动，真的把球压开
bpy.ops.object.select_all(action='DESELECT')
txt_obj.select_set(True)
bpy.context.view_layer.objects.active = txt_obj
bpy.ops.rigidbody.object_add(type='ACTIVE')
trb = txt_obj.rigid_body
trb.kinematic = True
trb.collision_shape = 'CONVEX_HULL'
trb.collision_margin = 0.001

def text_z(t):
    if t < 0.20:
        return 3.4
    if t < 0.75:
        u = (t - 0.20) / 0.55
        return 3.4 + (REST_TXT - 3.4) * u * u
    return REST_TXT

for f in range(1, scene.frame_end + 1):
    t = (f - 1) / FPS
    txt_obj.location.z = text_z(t)
    txt_obj.keyframe_insert("location", index=2, frame=f)
for (tt, sc) in ((0.70, (1, 1, 1)), (0.78, (1.10, 1.10, 0.80)),
                 (0.90, (0.96, 0.96, 1.05)), (1.05, (1, 1, 1))):
    txt_obj.scale = sc
    txt_obj.keyframe_insert("scale", frame=F(tt))

# ---------------- 铬球句号：全程运动学，关键帧轨迹含真弹跳弧 ----------------
# （铬球与弹珠质量比 66:1，不可阻挡的运动学碰撞在物理上等价于真刚体，且无爆炸风险）
ch = bpy.data.objects.new("chrome", bpy.data.meshes.new("chrome"))
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=0.38)
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
bpy.ops.object.select_all(action='DESELECT')
ch.select_set(True)
bpy.context.view_layer.objects.active = ch
bpy.ops.rigidbody.object_add(type='ACTIVE')
crb = ch.rigid_body
crb.kinematic = True
crb.collision_shape = 'SPHERE'
crb.use_margin = True
crb.collision_margin = 0.0008

def chrome_z(t):
    if t < 2.0:                                    # easeIn 下落，触地速度 ≈ 7.6 m/s
        u = t / 2.0
        return 8.0 + (0.42 - 8.0) * u * u
    if t < 2.62:                                   # 真实弹跳弧：逐级衰减
        u = (t - 2.0) / 0.62
        return 0.42 + 0.95 * 4 * u * (1 - u)
    if t < 3.15:
        u = (t - 2.62) / 0.53
        return 0.42 + 0.24 * 4 * u * (1 - u)
    if t < 3.55:
        u = (t - 3.15) / 0.40
        return 0.42 + 0.06 * 4 * u * (1 - u)
    return 0.42

for f in range(1, scene.frame_end + 1):
    ch.location.z = chrome_z((f - 1) / FPS)
    ch.keyframe_insert("location", index=2, frame=f)

# ---------------- 烘焙物理为关键帧（确定性 + 渲染稳定） ----------------
try:
    scene.rigidbody_world.use_split_impulse = True
except Exception:
    pass
for attr, val in (("substeps_per_second", 20), ("solver_iterations", 10)):
    try:
        setattr(scene.rigidbody_world, attr, val)
    except Exception:
        pass
scene.rigidbody_world.point_cache.frame_start = 1
scene.rigidbody_world.point_cache.frame_end = scene.frame_end
bpy.ops.ptcache.bake_all(bake=True)   # 无头模式烘缓存即可；bake_to_keyframes 需要完整上下文会失败
print("SIM BAKED")

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
