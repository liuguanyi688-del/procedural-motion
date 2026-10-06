# -*- coding: utf-8 -*-
"""ISOPOLIS 风等轴 2.5D demo：圆角瓷砖马林巴波，正交相机，6s 无缝循环
用法: blender -b -P build_isopolis.py -- [preview|full]
"""
import bpy, bmesh, math, random, sys, os
from math import radians, hypot
from mathutils import Matrix

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MODE = ARGS[0] if ARGS else "full"
FPS = int(ARGS[1]) if len(ARGS) > 1 else 24   # 用法: blender -b -P build_isopolis.py -- full 60
OUT = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(OUT, "frames_%d" % FPS)
os.makedirs(FR, exist_ok=True)

DUR = 6.0
N = 14
GAP_TILE = 0.90

WHITE = (0.880, 0.865, 0.925, 1)   # 象牙白(线性)
NAVY  = (0.030, 0.030, 0.160, 1)   # 深藏蓝(线性)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------------- 渲染设置 ----------------
try:
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
except Exception:
    scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1600
scene.render.resolution_y = 1000
scene.render.fps = FPS
scene.frame_start = 1
scene.frame_end = int(DUR * FPS)
scene.view_settings.view_transform = 'Standard'
ee = scene.eevee
for attr, val in (("taa_render_samples", 32), ("use_gtao", True),
                  ("gtao_distance", 0.5), ("gtao_factor", 0.9)):
    try:
        setattr(ee, attr, val)
    except Exception:
        pass

# ---------------- 世界与灯光 ----------------
world = bpy.data.worlds.new("W")
scene.world = world
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
bg.inputs[0].default_value = (0.735, 0.720, 0.835, 1.0)
bg.inputs[1].default_value = 1.0

key = bpy.data.lights.new("key", 'AREA')
key.energy = 1100
key.size = 4
ko = bpy.data.objects.new("key", key)
ko.location = (-6, -9, 14)
scene.collection.objects.link(ko)

fill = bpy.data.lights.new("fill", 'AREA')
fill.energy = 100
fill.size = 20
fo = bpy.data.objects.new("fill", fill)
fo.location = (9, 10, 12)
scene.collection.objects.link(fo)

# ---------------- 相机：正交等轴 ----------------
cam = bpy.data.cameras.new("C")
cam.type = 'ORTHO'
cam.ortho_scale = 16.9
co = bpy.data.objects.new("C", cam)
co.location = (14.1, -14.1, 14.1)
scene.collection.objects.link(co)
tgt = bpy.data.objects.new("tgt", None)
tgt.location = (0, 0, 0.15)
scene.collection.objects.link(tgt)
con = co.constraints.new('TRACK_TO')
con.target = tgt
con.track_axis = 'TRACK_NEGATIVE_Z'
con.up_axis = 'UP_Y'
scene.camera = co

# ---------------- 地面（砖缝透出的底色） ----------------
gbm = bmesh.new()
bmesh.ops.create_cube(gbm, size=1, matrix=Matrix.LocRotScale((0, 0, -0.01), None, (90, 90, 0.02)))
gmesh = bpy.data.meshes.new("ground")
gbm.to_mesh(gmesh)
gbm.free()
gm = bpy.data.materials.new("groundmat")
gm.use_nodes = True
gbsdf = next(n for n in gm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
gbsdf.inputs['Base Color'].default_value = (0.460, 0.450, 0.585, 1)
gbsdf.inputs['Roughness'].default_value = 0.9
go = bpy.data.objects.new("ground", gmesh)
go.data.materials.append(gm)
scene.collection.objects.link(go)

# ---------------- 圆角瓷砖母本网格 ----------------
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1,
                      matrix=Matrix.LocRotScale((0, 0, 0.15), None, (GAP_TILE, GAP_TILE, 0.30)))
bmesh.ops.bevel(bm, geom=list(bm.verts) + list(bm.edges),
                offset=0.09, segments=5, profile=1.0,
                affect='EDGES', clamp_overlap=True)
template = bpy.data.meshes.new("tile_tpl")
bm.to_mesh(template)
bm.free()
for p in template.polygons:
    p.use_smooth = True

# 母本白材质（命名 BS 方便复制；注意模板网格不挂材质，避免 0 号槽遮蔽）
matw = bpy.data.materials.new("tile_white")
matw.use_nodes = True
bsdf0 = next(n for n in matw.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
bsdf0.name = "BS"
bsdf0.inputs['Base Color'].default_value = WHITE
bsdf0.inputs['Roughness'].default_value = 0.32

# ---------------- 建瓷砖 + 关键帧 ----------------
def F(t):
    return int(round(t * FPS)) + 1

WAVES = [0.10, 2.00, 3.90]
SPEED = 0.15

def kf_color(m, val, fr):
    s = m.node_tree.nodes["BS"].inputs['Base Color']
    s.default_value = val
    s.keyframe_insert('default_value', frame=fr)

tiles = []
for iy in range(N):
    for ix in range(N):
        ox, oy = ix - (N - 1) / 2, iy - (N - 1) / 2
        me = template.copy()
        m = matw.copy()
        me.materials.append(m)
        o = bpy.data.objects.new("t%02d_%02d" % (ix, iy), me)
        o.location = (ox, oy, 0)
        scene.collection.objects.link(o)
        center2 = ix in (6, 7) and iy in (6, 7)
        tiles.append((o, m, hypot(ox, oy), center2, ix * N + iy))
        if center2:                       # 中心 2x2 常驻深蓝
            kf_color(m, NAVY, 1)

for o, m, d, center2, seed in tiles:
    for wi, wt in enumerate(WAVES):
        rng = random.Random(seed * 13 + wi * 101)
        if not center2 and rng.random() < 0.12:
            continue
        pt = wt + d * SPEED + rng.uniform(-0.04, 0.04)
        o.scale = (1, 1, 1)
        o.keyframe_insert("scale", index=2, frame=F(pt))
        o.scale = (1, 1, 3.1)
        o.keyframe_insert("scale", index=2, frame=F(pt + 0.10))
        o.scale = (1, 1, 1)
        o.keyframe_insert("scale", index=2, frame=F(pt + 0.45))
        if not center2:
            kf_color(m, WHITE, F(pt))
            kf_color(m, NAVY, F(pt + 0.07))
            kf_color(m, WHITE, F(pt + 0.40))

# ---------------- 输出 ----------------
scene.render.image_settings.file_format = 'PNG'
if MODE == "preview":
    scene.render.resolution_percentage = 35
    for f in (1, 34, 66):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(OUT, "prev_%03d.png" % f)
        bpy.ops.render.render(write_still=True)
    print("PREVIEW DONE")
else:
    scene.render.filepath = os.path.join(FR, "f_")
    bpy.ops.render.render(animation=True)
    print("FULL RENDER DONE")
