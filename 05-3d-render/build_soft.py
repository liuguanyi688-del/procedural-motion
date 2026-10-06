# -*- coding: utf-8 -*-
"""05 · 3D 渲染「柔软着陆」v3 —— 软膜果冻版
球海 = 一张软膜：平滑波 + 文字压坑 + 铬球压坑三场叠加；球沿膜法线倾斜、按坡度压扁。
文字/铬球 = 运动学刚体（真压场）。GN 全数学节点，确定性，无模拟爆炸风险。
用法: blender -b -P build_soft.py -- [preview|full] [fps]
"""
import bpy, bmesh, math, os, sys, random
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

BALL_R, SPACING = 0.15, 0.36
GX, GY = 111, 67                        # 7437 颗
FIELD_X, FIELD_Y = GX * SPACING, GY * SPACING
IMPACT = (2.10, 0.20)
TEXT_CENTER = (-0.75, 0.0)
REST_TXT = 0.30

# 波与压坑参数
WAVELEN, WAVE_SPEED = 2.6, 7.0
OMEGA = 2 * math.pi / WAVELEN
WAVE_A_TXT, WAVE_T0_TXT = 0.30, 0.85    # 文字落地波
WAVE_A_CHR, WAVE_T0_CHR = 0.55, 2.10    # 铬球落地震
DECAY = 0.045
CRATER_TXT = (0.26, 2.8, 0.85)          # (深, σ, 起始时刻)
CRATER_CHR = (0.34, 1.7, 2.10)

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

# ---------------- 地面 ----------------
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

# ---------------- 相机 ----------------
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
for (tt, dz) in ((2.02, 0), (2.09, 0.045), (2.18, -0.03), (2.32, 0.018), (2.55, 0)):
    co.location.z = 2.4 + dz
    co.keyframe_insert("location", index=2, frame=F(tt))

# ---------------- 几何节点：软膜球海 ----------------
tree = bpy.data.node_groups.new("SoftMembrane", 'GeometryNodeTree')
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

def VM(op, a=None, ao=0, b=None, bi=None, val=None, x=0, y=0):
    n = N('ShaderNodeVectorMath', x, y)
    n.operation = op
    if a is not None:
        nt.links.new(a.outputs[ao], n.inputs[0])
    if b is not None:
        nt.links.new(b.outputs[bi], n.inputs[1])
    if val is not None:
        sock = n.inputs['Scale'] if op == 'SCALE' else n.inputs[1]
        sock.default_value = val
    return n

grid = N('GeometryNodeMeshGrid', -1700, 0)
grid.inputs['Size X'].default_value = FIELD_X
grid.inputs['Size Y'].default_value = FIELD_Y
grid.inputs['Vertices X'].default_value = GX
grid.inputs['Vertices Y'].default_value = GY

setpos = N('GeometryNodeSetPosition', 900, 0)
L(grid, 'Mesh', setpos, 'Geometry')

pos = N('GeometryNodeInputPosition', -1700, -300)
time_n = N('GeometryNodeInputSceneTime', -1700, -600)
sec = (time_n, 'Seconds')

def dist_from(src):
    sx, sy = src[0], src[1]
    sub = N('ShaderNodeVectorMath', -1500, src[2] if len(src) > 2 else 0)
    sub.operation = 'SUBTRACT'
    sub.inputs[1].default_value = (sx, sy, 0)
    nt.links.new(pos.outputs['Position'], sub.inputs[0])
    ln = N('ShaderNodeVectorMath', -1350, src[2] if len(src) > 2 else 0)
    ln.operation = 'LENGTH'
    L(sub, 'Vector', ln, 0)
    return sub, ln  # (向量差, 距离)

def wave_block(tag, src, t0, A, x0, y0):
    """返回 (h_socket, gvec_socket)：行波高度与解析梯度向量"""
    dvec, dist = dist_from(src)
    dt = M('SUBTRACT', sec, t0, x=x0, y=y0 - 200)
    gd = M('MULTIPLY', (dist, 'Value'), 0.8 * OMEGA / WAVE_SPEED, x=x0 + 150, y=y0 + 150)
    g1 = M('SUBTRACT', (dt, 0), (gd, 0), x=x0 + 300, y=y0 + 120)
    g2 = M('DIVIDE', (g1, 0), 0.25, clamp=True, x=x0 + 450, y=y0 + 120)
    gsq = M('MULTIPLY', (g2, 0), (g2, 0), x=x0 + 600, y=y0 + 120)
    g3 = M('MULTIPLY', (g2, 0), 2, x=x0 + 600, y=y0)
    g4 = M('SUBTRACT', 3, (g3, 0), x=x0 + 750, y=y0)
    gate = M('MULTIPLY', (gsq, 0), (g4, 0), x=x0 + 900, y=y0 + 60)
    ph1 = M('MULTIPLY', (dist, 'Value'), OMEGA, x=x0 + 150, y=y0 - 150)
    ph2 = M('MULTIPLY', (dt, 0), WAVE_SPEED, x=x0 + 150, y=y0 - 300)
    ph3 = M('SUBTRACT', (ph1, 0), (ph2, 0), x=x0 + 300, y=y0 - 220)
    sn = M('SINE', (ph3, 0), x=x0 + 450, y=y0 - 220)
    cs = M('COSINE', (ph3, 0), x=x0 + 450, y=y0 - 360)
    dk = M('MULTIPLY', (dist, 'Value'), -DECAY, x=x0 + 150, y=y0 - 450)
    dc = M('EXPONENT', (dk, 0), x=x0 + 300, y=y0 - 450)
    fdiv = M('DIVIDE', (dt, 0), 6.5, clamp=False, x=x0 + 300, y=y0 - 600)
    fde = M('SUBTRACT', 1, (fdiv, 0), clamp=True, x=x0 + 450, y=y0 - 600)
    h1 = M('MULTIPLY', (sn, 0), A, x=x0 + 1050, y=y0 - 200)
    h2 = M('MULTIPLY', (h1, 0), (dc, 0), x=x0 + 1200, y=y0 - 240)
    h3 = M('MULTIPLY', (h2, 0), (gate, 0), x=x0 + 1350, y=y0 - 240)
    h4 = M('MULTIPLY', (h3, 0), (fde, 0), x=x0 + 1500, y=y0 - 240)
    g1n = M('MULTIPLY', (cs, 0), A * OMEGA, x=x0 + 1050, y=y0 - 420)
    g2n = M('MULTIPLY', (g1n, 0), (dc, 0), x=x0 + 1200, y=y0 - 460)
    g3n = M('MULTIPLY', (g2n, 0), (gate, 0), x=x0 + 1350, y=y0 - 460)
    g4n = M('MULTIPLY', (g3n, 0), (fde, 0), x=x0 + 1500, y=y0 - 460)
    unit = VM('DIVIDE', dvec, 'Vector', dist, 'Value', x=x0 + 1050, y=y0 - 640)
    gvec = VM('SCALE', unit, 'Vector', x=x0 + 1650, y=y0 - 560)
    nt.links.new(g4n.outputs[0], gvec.inputs['Scale'])
    return (h4, 0), (gvec, 'Vector')

def crater_block(tag, src, depth, sigma, t_start, x0, y0):
    """返回 (h_socket, e_socket, gvec_socket)：压坑高度、高斯值、梯度向量"""
    dvec, dist = dist_from(src)
    q = M('DIVIDE', (dist, 'Value'), sigma, x=x0, y=y0 - 100)
    qs = M('MULTIPLY', (q, 0), (q, 0), x=x0 + 150, y=y0 - 100)
    en = M('EXPONENT', (qs, 0), x=x0 + 300, y=y0 - 100)
    dk = M('MULTIPLY', (qs, 0), -1, x=x0 + 300, y=y0 - 240)
    nt.links.new(dk.outputs[0], en.inputs[0])          # exp(-(q^2))
    ssub = M('SUBTRACT', (time_n, 'Seconds'), t_start, x=x0, y=y0 - 400)
    s = M('DIVIDE', (ssub, 0), 0.5, clamp=True, x=x0 + 150, y=y0 - 400)
    h1 = M('MULTIPLY', (en, 0), -depth, x=x0 + 450, y=y0 - 160)
    h = M('MULTIPLY', (h1, 0), (s, 0), x=x0 + 600, y=y0 - 160)
    gm = M('MULTIPLY', (en, 0), depth * 2.0 / (sigma * sigma), x=x0 + 450, y=y0 - 560)
    gm2 = M('MULTIPLY', (gm, 0), (dist, 'Value'), x=x0 + 600, y=y0 - 560)
    gm3 = M('MULTIPLY', (gm2, 0), (s, 0), x=x0 + 750, y=y0 - 560)
    unit = VM('DIVIDE', dvec, 'Vector', dist, 'Value', x=x0 + 450, y=y0 - 720)
    gvec = VM('SCALE', unit, 'Vector', x=x0 + 900, y=y0 - 660)
    nt.links.new(gm3.outputs[0], gvec.inputs['Scale'])
    return (h, 0), (en, 0), (gvec, 'Vector')

wT_h, wT_g = wave_block("txt", TEXT_CENTER, WAVE_T0_TXT, WAVE_A_TXT, -1200, -900)
wC_h, wC_g = wave_block("chr", IMPACT, WAVE_T0_CHR, WAVE_A_CHR, -1200, -1900)
cT_h, cT_e, cT_g = crater_block("txt", TEXT_CENTER, *CRATER_TXT, 600, -1200)
cC_h, cC_e, cC_g = crater_block("chr", IMPACT, *CRATER_CHR, 600, -2400)

H1 = M('ADD', wT_h, wC_h, x=1200, y=-1200)
H2 = M('ADD', (H1, 0), cT_h, x=1350, y=-1200)
H = M('ADD', (H2, 0), cC_h, x=1500, y=-1200)
Hr = M('ADD', (H, 0), BALL_R, x=1650, y=-1150)   # 球心抬到膜面之上一个半径，别半埋
zvec = N('ShaderNodeCombineXYZ', 1800, -1200)
nt.links.new(Hr.outputs[0], zvec.inputs['Z'])
nt.links.new(zvec.outputs['Vector'], setpos.inputs['Offset'])

G1 = N('ShaderNodeVectorMath', 1200, -2100)
G1.operation = 'ADD'
L(wT_g[0], wT_g[1], G1, 0)
L(wC_g[0], wC_g[1], G1, 1)
G2 = N('ShaderNodeVectorMath', 1350, -2100)
G2.operation = 'ADD'
L(G1, 'Vector', G2, 0)
L(cT_g[0], cT_g[1], G2, 1)
G3 = N('ShaderNodeVectorMath', 1500, -2100)
G3.operation = 'ADD'
L(G2, 'Vector', G3, 0)
L(cC_g[0], cC_g[1], G3, 1)
neg = N('ShaderNodeVectorMath', 1650, -2100)
neg.operation = 'SCALE'
L(G3, 'Vector', neg, 0)
neg.inputs['Scale'].default_value = -1.0
nrm = N('ShaderNodeVectorMath', 1800, -2100)
nrm.operation = 'NORMALIZE'
nt.links.new(neg.outputs['Vector'], nrm.inputs[0])
nz = N('ShaderNodeCombineXYZ', 1800, -2250)
nt.links.new(nrm.outputs['Vector'], nz.inputs['Z'])
aln = N('FunctionNodeAlignEulerToVector', 1950, -2100)
aln.axis = 'Z'
nt.links.new(nrm.outputs['Vector'], aln.inputs['Vector'])

# 坡度压扁 + 压坑果冻压扁
gl = N('ShaderNodeVectorMath', 1950, -2350)
gl.operation = 'LENGTH'
L(G3, 'Vector', gl, 0)
glh = M('MULTIPLY', (gl, 'Value'), 0.5, x=2100, y=-2350)   # 坡度减半，煎饼变果冻
gq = M('MULTIPLY', (glh, 0), (glh, 0), x=2250, y=-2350)
g1p = M('ADD', (gq, 0), 1, x=2400, y=-2350)
gsq = M('SQRT', (g1p, 0), x=2550, y=-2350)
sz1 = M('DIVIDE', 1, (gsq, 0), x=2700, y=-2350)
szm = M('MULTIPLY', (sz1, 0), 0.25, x=2850, y=-2350)
szf = M('ADD', (szm, 0), 0.75, x=3000, y=-2350)            # 压扁下限 0.75
pr1 = M('MULTIPLY', cT_e, -0.30, x=2100, y=-2550)
pr2 = M('MULTIPLY', cC_e, -0.35, x=2100, y=-2700)
press = M('ADD', (szf, 0), (pr1, 0), clamp=True, x=3150, y=-2450)
press2 = M('ADD', (press, 0), (pr2, 0), clamp=True, x=3300, y=-2500)
svec = N('ShaderNodeCombineXYZ', 3000, -2450)
svec.inputs['X'].default_value = 1.0
svec.inputs['Y'].default_value = 1.0
nt.links.new(press2.outputs[0], svec.inputs['Z'])

sphere = N('GeometryNodeMeshUVSphere', 3000, 60)
sphere.inputs['Radius'].default_value = BALL_R
sphere.inputs['Segments'].default_value = 20
sphere.inputs['Rings'].default_value = 12
smooth = N('GeometryNodeSetShadeSmooth', 3180, 60)
L(sphere, 'Mesh', smooth, 'Geometry')

inst = N('GeometryNodeInstanceOnPoints', 3350, 0)
L(setpos, 'Geometry', inst, 'Points')
L(smooth, 'Geometry', inst, 'Instance')
nt.links.new(aln.outputs['Rotation'], inst.inputs['Rotation'])

sci = N('GeometryNodeScaleInstances', 3550, 0)
L(inst, 'Instances', sci, 'Instances')
nt.links.new(svec.outputs['Vector'], sci.inputs['Scale'])

smat = N('GeometryNodeSetMaterial', 3750, 0)
L(sci, 'Instances', smat, 'Geometry')

out = N('NodeGroupOutput', 3950, 0)
L(smat, 'Geometry', out, 'Geometry')

field_obj = bpy.data.objects.new("field", bpy.data.meshes.new("field_mesh"))
scene.collection.objects.link(field_obj)
mod = field_obj.modifiers.new("GN", 'NODES')
mod.node_group = tree

# ---------------- 弹珠材质（果冻：世界坐标渐变 + 次表面） ----------------
bmat = bpy.data.materials.new("ballmat")
bmat.use_nodes = True
bnt = bmat.node_tree
bbsdf = next(n for n in bnt.nodes if n.type == 'BSDF_PRINCIPLED')
bbsdf.inputs['Roughness'].default_value = 0.13
try:
    bbsdf.inputs['Coat Weight'].default_value = 0.5
    bbsdf.inputs['Subsurface Weight'].default_value = 0.18
    bbsdf.inputs['Subsurface Radius'].default_value = (0.06, 0.02, 0.02)
except Exception:
    pass

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
mixc.inputs[6].default_value = (0.93, 0.83, 0.66, 1)
mixc.inputs[7].default_value = (0.98, 0.42, 0.50, 1)
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
mixv.inputs[7].default_value = (0.56, 0.36, 0.92, 1)
bnt.links.new(mixc.outputs[2], mixv.inputs[6])
bnt.links.new(gt.outputs[0], mixv.inputs['Factor'])
bnt.links.new(mixv.outputs[2], bbsdf.inputs['Base Color'])
field_obj.data.materials.append(bmat)
smat.inputs['Material'].default_value = bmat

# ---------------- 气球文字：运动学刚体，压得更狠 ----------------
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
bpy.ops.object.select_all(action='DESELECT')
txt_obj.select_set(True)
bpy.context.view_layer.objects.active = txt_obj
bpy.ops.object.convert(target='MESH')
for p in txt_obj.data.polygons:
    p.use_smooth = True
tmat = bpy.data.materials.new("balloon")
tmat.use_nodes = True
tbsdf = next(n for n in tmat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
tbsdf.inputs['Base Color'].default_value = (0.93, 0.25, 0.36, 1)
tbsdf.inputs['Roughness'].default_value = 0.08
try:
    tbsdf.inputs['Coat Weight'].default_value = 0.65
    tbsdf.inputs['Subsurface Weight'].default_value = 0.22
    tbsdf.inputs['Subsurface Radius'].default_value = (0.08, 0.02, 0.02)
except Exception:
    pass
txt_obj.data.materials.append(tmat)
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
    wob = max(0.0, t - 1.0)
    return REST_TXT + 0.04 * math.exp(-1.3 * wob) * math.sin(2 * math.pi * 1.3 * wob)

for f in range(1, scene.frame_end + 1):
    t = (f - 1) / FPS
    txt_obj.location.z = text_z(t)
    txt_obj.keyframe_insert("location", index=2, frame=f)
    lean = 0.06 * math.exp(-1.1 * max(0.0, t - 0.78)) * math.sin(2 * math.pi * 1.1 * max(0.0, t - 0.78))
    txt_obj.rotation_euler.y = lean
    txt_obj.keyframe_insert("rotation_euler", index=1, frame=f)
for (tt, sc) in ((0.70, (1, 1, 1)), (0.78, (1.16, 1.16, 0.70)),
                 (0.92, (0.94, 0.94, 1.08)), (1.10, (1, 1, 1))):
    txt_obj.scale = sc
    txt_obj.keyframe_insert("scale", frame=F(tt))

# ---------------- 铬球句号：全程运动学，关键帧弹跳弧 ----------------
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
    if t < 2.0:
        u = t / 2.0
        return 8.0 + (0.42 - 8.0) * u * u
    if t < 2.62:
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

# ---------------- 输出 ----------------
scene.render.image_settings.file_format = 'PNG'
if MODE == "preview":
    scene.render.resolution_percentage = 50
    for f in (45, 100, 140, 180, 240, 470):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(OUT, "prev_%03d.png" % f)
        bpy.ops.render.render(write_still=True)
    print("PREVIEW DONE")
else:
    scene.render.filepath = os.path.join(FR, "f_")
    bpy.ops.render.render(animation=True)
    print("FULL RENDER DONE")
