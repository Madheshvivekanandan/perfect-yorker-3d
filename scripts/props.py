"""Procedurally modelled cricket props and ground (regulation dimensions, metres)."""
import math
import os
import bmesh
import bpy
from mathutils import Matrix, Vector

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

STUMP_H = 0.711
STUMP_R = 0.018
STUMP_X = 0.0953          # outer edges 22.86 cm apart
BOWL_END_Y = 20.12
BALL_R = 0.036


# ------------------------------------------------------------------ helpers
def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def mesh_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def shade_smooth(obj):
    for p in obj.data.polygons:
        p.use_smooth = True


def node_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    return m, nt, nt.nodes["Principled BSDF"]


def tex_image(nt, path, noncolor=False, mapping=None):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path, check_existing=True)
    if noncolor:
        t.image.colorspace_settings.name = "Non-Color"
    if mapping is not None:
        nt.links.new(mapping.outputs[0], t.inputs[0])
    return t


def simple_mat(name, color, rough=0.5, metal=0.0, coat=0.0, emit=None, emit_strength=0.0):
    m, nt, b = node_mat(name)
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = emit_strength
    return m


def noise_bump(nt, bsdf, scale=200.0, strength=0.15, detail=8.0):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return n


# ------------------------------------------------------------------ world + ground
def setup_world(hdri="stadium_01", strength=1.0, rotation_deg=0.0):
    w = bpy.data.worlds.new("Stadium")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(os.path.join(ASSETS, "hdri", hdri + ".exr"))
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value[2] = math.radians(rotation_deg)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Generated"], mp.inputs[0])
    nt.links.new(mp.outputs[0], env.inputs[0])
    nt.links.new(env.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = strength
    return w


def add_sun(energy=4.5, elev=48, azim=-35):
    sun = bpy.data.lights.new("Sun", 'SUN')
    sun.energy = energy
    sun.angle = math.radians(0.8)
    sun.color = (1.0, 0.96, 0.9)
    o = link(bpy.data.objects.new("Sun", sun))
    o.rotation_euler = (math.radians(90 - elev), 0, math.radians(azim))
    return o


def grass_material():
    m, nt, b = node_mat("Outfield")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.35, 0.35, 0.35)       # 1 tile ~ 2.9 m
    nt.links.new(tc.outputs["Object"], mp.inputs[0])
    tdir = os.path.join(ASSETS, "tex")
    col = tex_image(nt, f"{tdir}/grass_ground_Diffuse.jpg", mapping=mp)
    rough = tex_image(nt, f"{tdir}/grass_ground_Rough.jpg", True, mp)
    nor = tex_image(nt, f"{tdir}/grass_ground_nor_gl.jpg", True, mp)
    # mowing stripes (6 m bands across the pitch direction and a second set of diagonal-free bands)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    wave = nt.nodes.new("ShaderNodeMath"); wave.operation = 'MULTIPLY'; wave.inputs[1].default_value = 1 / 6.0
    nt.links.new(sep.outputs["Y"], wave.inputs[0])
    fl = nt.nodes.new("ShaderNodeMath"); fl.operation = 'PINGPONG'; fl.inputs[1].default_value = 1.0
    nt.links.new(wave.outputs[0], fl.inputs[0])
    st = nt.nodes.new("ShaderNodeMath"); st.operation = 'GREATER_THAN'; st.inputs[1].default_value = 0.5
    nt.links.new(fl.outputs[0], st.inputs[0])
    # grass tint: make the Poly Haven grass lusher, then alternate light/dark stripes
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = 0.6
    hsv.inputs["Hue"].default_value = 0.5
    nt.links.new(col.outputs[0], hsv.inputs["Color"])
    mapv = nt.nodes.new("ShaderNodeMapRange")
    mapv.inputs[3].default_value = 0.78
    mapv.inputs[4].default_value = 1.12
    nt.links.new(st.outputs[0], mapv.inputs[0])
    nt.links.new(mapv.outputs[0], hsv.inputs["Value"])
    # large scale variation
    big = nt.nodes.new("ShaderNodeTexNoise"); big.inputs["Scale"].default_value = 0.04
    nt.links.new(tc.outputs["Object"], big.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
    mix.inputs[0].default_value = 0.35
    nt.links.new(hsv.outputs[0], mix.inputs[6])
    nt.links.new(big.outputs["Color"], mix.inputs[7])
    tint = nt.nodes.new("ShaderNodeMix"); tint.data_type = 'RGBA'; tint.blend_type = 'MULTIPLY'
    tint.inputs[0].default_value = 1.0
    tint.inputs[7].default_value = (0.42, 0.95, 0.30, 1)
    nt.links.new(mix.outputs[2], tint.inputs[6])
    nt.links.new(tint.outputs[2], b.inputs["Base Color"])
    nt.links.new(rough.outputs[0], b.inputs["Roughness"])
    nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = 0.8
    nt.links.new(nor.outputs[0], nm.inputs["Color"])
    nt.links.new(nm.outputs[0], b.inputs["Normal"])
    b.inputs["Specular IOR Level"].default_value = 0.35
    return m


def pitch_material():
    m, nt, b = node_mat("Pitch")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.8, 0.8, 0.8)
    nt.links.new(tc.outputs["Object"], mp.inputs[0])
    tdir = os.path.join(ASSETS, "tex")
    dirt = tex_image(nt, f"{tdir}/dry_ground_01_Diffuse.jpg", mapping=mp)
    grass = tex_image(nt, f"{tdir}/sparse_grass_Diffuse.jpg", mapping=mp)
    rough = tex_image(nt, f"{tdir}/dry_ground_01_Rough.jpg", True, mp)
    nor = tex_image(nt, f"{tdir}/dry_ground_01_nor_gl.jpg", True, mp)
    # lighten & desaturate dirt to the typical pale-tan cricket pitch colour
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = 0.3
    hsv.inputs["Value"].default_value = 1.25
    nt.links.new(dirt.outputs[0], hsv.inputs["Color"])
    noise = nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 1.2
    nt.links.new(tc.outputs["Object"], noise.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[1].position = 0.7
    nt.links.new(noise.outputs["Fac"], ramp.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'
    nt.links.new(ramp.outputs[0], mix.inputs[0])
    nt.links.new(hsv.outputs[0], mix.inputs[6])
    gh = nt.nodes.new("ShaderNodeHueSaturation"); gh.inputs["Saturation"].default_value = 0.5; gh.inputs["Value"].default_value = 1.2
    nt.links.new(grass.outputs[0], gh.inputs["Color"])
    nt.links.new(gh.outputs[0], mix.inputs[7])
    tint = nt.nodes.new("ShaderNodeMix"); tint.data_type = 'RGBA'; tint.blend_type = 'MULTIPLY'
    tint.inputs[0].default_value = 1.0
    tint.inputs[7].default_value = (0.86, 0.72, 0.5, 1)
    nt.links.new(mix.outputs[2], tint.inputs[6])
    nt.links.new(tint.outputs[2], b.inputs["Base Color"])
    nt.links.new(rough.outputs[0], b.inputs["Roughness"])
    nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = 0.6
    nt.links.new(nor.outputs[0], nm.inputs["Color"])
    nt.links.new(nm.outputs[0], b.inputs["Normal"])
    return m


def build_ground():
    # outfield: large disc so the HDRI's own ground is fully covered up to the horizon
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=400, segments=128)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    g = mesh_obj("Outfield", bm)
    g.data.materials.append(grass_material())

    # pitch strip (3.05 m x 24 m), subdivided slightly for detail
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=6, y_segments=40, size=0.5)
    bmesh.ops.scale(bm, vec=(3.05, 24.0, 1), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, BOWL_END_Y / 2, 0.003), verts=bm.verts)
    p = mesh_obj("Pitch", bm)
    p.data.materials.append(pitch_material())

    # creases: white paint strips
    paint = simple_mat("CreasePaint", (0.92, 0.92, 0.9), rough=0.8)
    w = 0.05
    def strip(name, x0, x1, y0, y1):
        bm = bmesh.new()
        for v in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            bm.verts.new((v[0], v[1], 0.006))
        bm.faces.new(bm.verts)
        o = mesh_obj(name, bm)
        o.data.materials.append(paint)
    for end, sgn in ((0.0, 1), (BOWL_END_Y, -1)):
        strip("BowlingCrease", -1.32, 1.32, end - w / 2, end + w / 2)
        pc = end + sgn * 1.22
        strip("PoppingCrease", -1.83, 1.83, pc - w / 2, pc + w / 2)
        for xs in (-1.32, 1.32):
            ya, yb = sorted((end - sgn * 1.2, pc))
            strip("ReturnCrease", xs - w / 2, xs + w / 2, ya, yb)
        for xs in (-0.89, 0.89):            # limited-overs wide guidelines
            ya, yb = sorted((pc, pc + sgn * 0.45))
            strip("WideLine", xs - 0.012, xs + 0.012, ya, yb)
    # 30-yard circle: painted white dashes
    for i in range(160):
        a0 = i / 160 * math.tau
        if i % 2:
            continue
        cx, cy = 0, BOWL_END_Y / 2
        pts = []
        for a, r in ((a0, 27.4), (a0 + math.tau / 170, 27.4), (a0 + math.tau / 170, 27.48), (a0, 27.48)):
            pts.append((cx + r * math.cos(a) * 1.0, cy + r * math.sin(a) * 1.25))
        bm = bmesh.new()
        for v in pts:
            bm.verts.new((v[0], v[1], 0.004))
        bm.faces.new(bm.verts)
        o = mesh_obj("Circle30", bm)
        o.data.materials.append(paint)
    build_boundary()
    return g, p


def build_boundary():
    """Boundary rope and LED advertising boards (generic, brand-free graphics)."""
    cy = BOWL_END_Y / 2
    cu = bpy.data.curves.new("RopeCurve", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    n = 256
    sp.points.add(n)
    for i in range(n + 1):
        a = i / n * math.tau
        sp.points[i].co = (68 * math.cos(a), cy + 76 * math.sin(a), 0.07, 1)
    cu.bevel_depth = 0.07
    ro = link(bpy.data.objects.new("Rope", cu))
    ro.data.materials.append(simple_mat("RopeMat", (0.85, 0.08, 0.35), rough=0.6))

    # LED boards: animated emissive gradient bands
    m, nt, b = node_mat("LEDBoard")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    grad = nt.nodes.new("ShaderNodeTexWave")
    grad.wave_type = 'BANDS'
    grad.inputs["Scale"].default_value = 0.35
    grad.inputs["Distortion"].default_value = 0.0
    nt.links.new(tc.outputs["UV"], grad.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = 'CONSTANT'
    cr.elements[0].color = (0.02, 0.08, 0.5, 1)
    cr.elements[1].position = 0.5
    cr.elements[1].color = (0.9, 0.35, 0.02, 1)
    e = cr.elements.new(0.75); e.color = (0.95, 0.95, 0.95, 1)
    e = cr.elements.new(0.25); e.color = (0.0, 0.45, 0.2, 1)
    nt.links.new(grad.outputs["Fac"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], b.inputs["Base Color"])
    nt.links.new(ramp.outputs[0], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 1.2
    b.inputs["Roughness"].default_value = 0.3
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new()
    seg = 180
    R = (71, 79)
    for i in range(seg):
        a0, a1 = i / seg * math.tau, (i + 1) / seg * math.tau
        p = [(R[0] * math.cos(a), cy + R[1] * math.sin(a)) for a in (a0, a1)]
        vs = [bm.verts.new((p[0][0], p[0][1], 0)), bm.verts.new((p[1][0], p[1][1], 0)),
              bm.verts.new((p[1][0], p[1][1], 0.9)), bm.verts.new((p[0][0], p[0][1], 0.9))]
        f = bm.faces.new(vs)
        for lp, uv in zip(f.loops, [(i, 0), (i + 1, 0), (i + 1, 1), (i, 1)]):
            lp[uvl].uv = (uv[0] * 2.5, uv[1])
    bo = mesh_obj("LEDBoards", bm)
    bo.data.materials.append(m)


# ------------------------------------------------------------------ stumps / bails / ball
def stump_material():
    m, nt, b = node_mat("StumpPaint")
    b.inputs["Base Color"].default_value = (0.9, 0.9, 0.88, 1)
    b.inputs["Roughness"].default_value = 0.25
    b.inputs["Coat Weight"].default_value = 0.4
    # generic coloured band graphic + ground dirt at the base
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = 'CONSTANT'
    cr.elements[0].position = 0.0; cr.elements[0].color = (0.55, 0.5, 0.42, 1)      # dirty base
    cr.elements[1].position = 0.06; cr.elements[1].color = (0.9, 0.9, 0.88, 1)
    for pos, col in ((0.30, (0.02, 0.1, 0.55, 1)), (0.46, (0.9, 0.9, 0.88, 1)), (0.49, (0.9, 0.3, 0.02, 1)),
                     (0.52, (0.9, 0.9, 0.88, 1))):
        e = cr.elements.new(pos); e.color = col
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs[1].default_value = 0.0
    mr.inputs[2].default_value = STUMP_H
    nt.links.new(sep.outputs["Z"], mr.inputs[0])
    nt.links.new(mr.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], b.inputs["Base Color"])
    return m


def make_stump(name, x, y, mat):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=STUMP_R, radius2=STUMP_R, depth=STUMP_H - 0.012)
    bmesh.ops.translate(bm, vec=(0, 0, (STUMP_H - 0.012) / 2), verts=bm.verts)
    # domed top
    top = bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=8, radius=STUMP_R)
    for v in top["verts"]:
        v.co.z = max(v.co.z, 0) * 0.6 + STUMP_H - 0.012
    o = mesh_obj(name, bm)
    shade_smooth(o)
    o.data.materials.append(mat)
    # object origin at centre of mass for good rigid body behaviour
    o.location = (x, y, 0)
    return o


def make_bail(name, loc, mat):
    bm = bmesh.new()
    L = 0.1095
    profile = [(-L / 2, 0.004), (-L / 2 + 0.013, 0.004), (-L / 2 + 0.016, 0.0075), (-0.012, 0.0075),
               (-0.008, 0.0095), (0.008, 0.0095), (0.012, 0.0075), (L / 2 - 0.016, 0.0075),
               (L / 2 - 0.013, 0.004), (L / 2, 0.004)]
    rings = []
    seg = 16
    for x, r in profile:
        ring = [bm.verts.new((x, r * math.cos(a), r * math.sin(a))) for a in [i / seg * math.tau for i in range(seg)]]
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(seg):
            bm.faces.new((r0[i], r0[(i + 1) % seg], r1[(i + 1) % seg], r1[i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    o = mesh_obj(name, bm)
    shade_smooth(o)
    o.data.materials.append(mat)
    o.location = loc
    return o


def bail_material():
    """LED bails: white plastic, emission animated (flash red when dislodged)."""
    m, nt, b = node_mat("LEDBail")
    b.inputs["Base Color"].default_value = (0.95, 0.95, 0.95, 1)
    b.inputs["Roughness"].default_value = 0.2
    b.inputs["Transmission Weight"].default_value = 0.3
    b.inputs["Emission Color"].default_value = (1.0, 0.05, 0.02, 1)
    b.inputs["Emission Strength"].default_value = 0.0
    return m


def build_wicket(y, prefix):
    mat = bpy.data.materials.get("StumpPaint") or stump_material()
    bmat = bpy.data.materials.get("LEDBail") or bail_material()
    stumps = [make_stump(f"{prefix}_stump_{n}", x, y, mat)
              for n, x in (("off", STUMP_X - STUMP_R), ("mid", 0.0), ("leg", -(STUMP_X - STUMP_R)))]
    zb = STUMP_H + 0.0085
    bails = [make_bail(f"{prefix}_bail_{i}", (sx * (STUMP_X - STUMP_R) / 2, y, zb), bmat) for i, sx in ((0, 1), (1, -1))]
    return stumps, bails


def ball_material():
    m, nt, b = node_mat("BallLeather")
    b.inputs["Base Color"].default_value = (0.88, 0.87, 0.82, 1)     # white limited-overs ball
    b.inputs["Roughness"].default_value = 0.32
    b.inputs["Coat Weight"].default_value = 0.6
    b.inputs["Coat Roughness"].default_value = 0.15
    n = noise_bump(nt, b, scale=900, strength=0.08)
    # scuff marks
    sc = nt.nodes.new("ShaderNodeTexNoise"); sc.inputs["Scale"].default_value = 60
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.62; ramp.color_ramp.elements[0].color = (0.88, 0.87, 0.82, 1)
    ramp.color_ramp.elements[1].position = 0.75; ramp.color_ramp.elements[1].color = (0.62, 0.58, 0.5, 1)
    nt.links.new(sc.outputs["Fac"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], b.inputs["Base Color"])
    return m


def build_ball():
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=BALL_R)
    ball = mesh_obj("Ball", bm)
    shade_smooth(ball)
    ball.data.materials.append(ball_material())
    # seam: two rows of stitching around the equator (in the ball's XZ plane -> seam upright when flying along Y)
    seam = simple_mat("Seam", (0.1, 0.35, 0.15), rough=0.6)
    for k, off in enumerate((-0.0028, 0.0028)):
        cu = bpy.data.curves.new(f"SeamC{k}", 'CURVE')
        cu.dimensions = '3D'
        sp = cu.splines.new('POLY'); sp.points.add(95); sp.use_cyclic_u = True
        r = math.sqrt(BALL_R ** 2 - off ** 2) + 0.0004
        for i in range(96):
            a = i / 96 * math.tau
            sp.points[i].co = (r * math.cos(a), off, r * math.sin(a), 1)
        cu.bevel_depth = 0.0009
        so = link(bpy.data.objects.new(f"BallSeam{k}", cu))
        so.data.materials.append(seam)
        so.parent = ball
    return ball


# ------------------------------------------------------------------ bat
def bat_materials():
    wood, nt, b = node_mat("Willow")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.bands_direction = 'X'
    wave.inputs["Scale"].default_value = 30
    wave.inputs["Distortion"].default_value = 4
    wave.inputs["Detail"].default_value = 3
    nt.links.new(tc.outputs["Object"], wave.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.78, 0.62, 0.40, 1)
    ramp.color_ramp.elements[1].color = (0.9, 0.78, 0.58, 1)
    nt.links.new(wave.outputs["Fac"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.45
    b.inputs["Coat Weight"].default_value = 0.2
    grip = simple_mat("Grip", (0.02, 0.02, 0.025), rough=0.8)
    gn = grip.node_tree
    noise_bump(gn, gn.nodes["Principled BSDF"], scale=400, strength=0.4)
    decal = simple_mat("BatDecal", (0.05, 0.12, 0.6), rough=0.35)
    decal2 = simple_mat("BatDecal2", (0.95, 0.4, 0.02), rough=0.35)
    return wood, grip, decal, decal2


def build_bat(name="Bat"):
    """Bat with origin at the top of the handle, blade along -Z, face toward -Y."""
    wood, grip, decal, decal2 = (bpy.data.materials.get("Willow"), bpy.data.materials.get("Grip"),
                                 bpy.data.materials.get("BatDecal"), bpy.data.materials.get("BatDecal2"))
    if wood is None:
        wood, grip, decal, decal2 = bat_materials()
    bm = bmesh.new()
    W = 0.106
    blade_len = 0.61
    rings = []
    seg_u = 14
    nz = 30
    for j in range(nz + 1):
        z = -j / nz * blade_len
        t = j / nz
        # thickness profile: thin at shoulder, thick spine near the bottom third, taper at toe
        thick = 0.022 + 0.04 * math.sin(min(t / 0.82, 1) * math.pi * 0.5) ** 1.6 - (0.012 if t > 0.94 else 0)
        width = W * (0.86 + 0.14 * min(t * 5, 1))
        ring = []
        for i in range(seg_u):
            s = i / (seg_u - 1)
            x = (s - 0.5) * width
            # flat face at y = -0.0; curved back bulging toward +y
            ring.append((x, 0.0, z))
        for i in range(seg_u - 1, -1, -1):
            s = i / (seg_u - 1)
            x = (s - 0.5) * width
            bulge = thick * (1 - (2 * s - 1) ** 2) ** 0.5 + 0.012
            ring.append((x, bulge, z))
        rings.append([bm.verts.new(v) for v in ring])
    n = len(rings[0])
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(n):
            bm.faces.new((r0[i], r0[(i + 1) % n], r1[(i + 1) % n], r1[i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.translate(bm, vec=(0, -0.02, -0.33), verts=bm.verts)
    blade = mesh_obj(name, bm)
    blade.data.materials.append(wood)
    blade.modifiers.new("bevel", 'BEVEL').width = 0.004
    for p in blade.data.polygons:
        p.use_smooth = True
    # handle
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.0165, radius2=0.0175, depth=0.34)
    bmesh.ops.translate(bm, vec=(0, 0.0, -0.17), verts=bm.verts)
    h = mesh_obj(name + "_handle", bm)
    shade_smooth(h)
    h.data.materials.append(grip)
    h.parent = blade
    # face decals (generic stripes)
    for k, (z0, mat) in enumerate(((-0.40, decal), (-0.46, decal2))):
        bm = bmesh.new()
        vs = [bm.verts.new(v) for v in ((-0.045, -0.0205, z0), (0.045, -0.0205, z0), (0.045, -0.0205, z0 - 0.045), (-0.045, -0.0205, z0 - 0.045))]
        bm.faces.new(vs)
        d = mesh_obj(f"{name}_decal{k}", bm)
        d.data.materials.append(mat)
        d.parent = blade
    return blade


# ------------------------------------------------------------------ protective gear (attached to bones)
def attach_to_bone(obj, rig, bone):
    """Parent obj to a bone while keeping its current world transform (rig must be in rest pose)."""
    bpy.context.view_layer.update()
    mw = obj.matrix_world.copy()
    obj.parent = rig
    obj.parent_type = 'BONE'
    obj.parent_bone = bone
    bpy.context.view_layer.update()
    obj.matrix_world = mw


def build_pad(name, rig, side, mat):
    """Batting pad: curved shell with vertical bolsters in front of the shin + knee roll."""
    s = ".L" if side == "Left" else ".R"
    knee = rig.data.bones[f"lowerleg01{s}"].head_local.copy()
    ankle = rig.data.bones[f"lowerleg02{s}"].tail_local.copy()
    bm = bmesh.new()
    rows, cols = 18, 22
    height = (knee - ankle).length + 0.2
    grid = []
    for j in range(rows + 1):
        t = j / rows
        z = -0.05 + t * height                           # from just above the ankle up past the knee
        rad = 0.085 + 0.02 * math.exp(-((t - 0.78) / 0.07) ** 2)   # knee roll bulge
        row = []
        for i in range(cols + 1):
            a = math.radians(-100 + 200 * i / cols)
            bolster = 0.006 * abs(math.cos(i / cols * math.pi * 3.5))
            r = rad + bolster
            row.append(bm.verts.new((r * math.sin(a), -r * math.cos(a), z)))
        grid.append(row)
    for j in range(rows):
        for i in range(cols):
            bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
    o = mesh_obj(name, bm)
    o.modifiers.new("solid", 'SOLIDIFY').thickness = 0.02
    o.modifiers.new("sub", 'SUBSURF').levels = 1
    shade_smooth(o)
    o.data.materials.append(mat)
    # orient along the shin, shell facing the front of the leg (-Y)
    shin = (knee - ankle).normalized()
    rot = Vector((0, 0, 1)).rotation_difference(shin).to_matrix().to_4x4()
    o.matrix_world = Matrix.Translation(ankle + Vector((0, 0.035, 0))) @ rot
    attach_to_bone(o, rig, f"lowerleg01{s}")
    return o


def build_glove(name, rig, side, mat):
    s = ".L" if side == "Left" else ".R"
    b = rig.data.bones[f"wrist{s}"]
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.scale(bm, vec=(0.095, 0.14, 0.085), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0.06, 0), verts=bm.verts)
    o = mesh_obj(name, bm)
    o.modifiers.new("sub", 'SUBSURF').levels = 2
    shade_smooth(o)
    o.data.materials.append(mat)
    o.matrix_world = b.matrix_local.copy()
    attach_to_bone(o, rig, f"wrist{s}")
    return o


def build_helmet(name, rig, shell_mat, grille_mat):
    hb = rig.data.bones["head"]
    c = hb.head_local + (hb.tail_local - hb.head_local) * 0.55 + Vector((0, 0.01, 0))
    R = 0.132
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=R)
    # cut the face opening and the lower half
    kill = [v for v in bm.verts if v.co.z < -0.035 or (v.co.y < -0.04 and v.co.z < 0.03)]
    bmesh.ops.delete(bm, geom=kill, context='VERTS')
    for v in bm.verts:
        v.co.y *= 1.12
    o = mesh_obj(name, bm)
    o.modifiers.new("solid", 'SOLIDIFY').thickness = 0.012
    o.modifiers.new("sub", 'SUBSURF').levels = 1
    shade_smooth(o)
    o.data.materials.append(shell_mat)
    o.location = c
    # peak
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.scale(bm, vec=(0.2, 0.07, 0.008), verts=bm.verts)
    pk = mesh_obj(name + "_peak", bm)
    pk.modifiers.new("sub", 'SUBSURF').levels = 2
    pk.data.materials.append(shell_mat)
    pk.location = c + Vector((0, -R * 1.08, 0.03))
    pk.rotation_euler = (math.radians(-12), 0, 0)
    # grille bars
    bars = []
    for k, (dz, rr) in enumerate(((-0.02, R * 1.2), (-0.065, R * 1.15), (-0.105, R * 1.0))):
        cu = bpy.data.curves.new(f"{name}_bar{k}", 'CURVE')
        cu.dimensions = '3D'
        sp = cu.splines.new('POLY'); sp.points.add(20)
        for i in range(21):
            a = math.radians(-70 + 140 * i / 20)
            sp.points[i].co = (rr * math.sin(a) * 0.95, -rr * math.cos(a), dz, 1)
        cu.bevel_depth = 0.0035
        bo = link(bpy.data.objects.new(f"{name}_bar{k}", cu))
        bo.data.materials.append(grille_mat)
        bo.location = c
        bars.append(bo)
    cu = bpy.data.curves.new(f"{name}_vbar", 'CURVE'); cu.dimensions = '3D'
    sp = cu.splines.new('POLY'); sp.points.add(1)
    sp.points[0].co = (0, -R * 1.2, -0.02, 1); sp.points[1].co = (0, -R * 1.0, -0.105, 1)
    cu.bevel_depth = 0.0035
    vb = link(bpy.data.objects.new(f"{name}_vbar", cu)); vb.location = c
    vb.data.materials.append(grille_mat)
    for part in [o, pk, vb] + bars:
        attach_to_bone(part, rig, "head")
    return o
