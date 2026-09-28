import bpy, sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from characters import make_human
from posing import *
from anim import *
bpy.ops.wm.read_factory_settings(use_empty=True)
rig, body = make_human("bowler")
skel = Skeleton(rig)
A = MocapClip(os.path.abspath("../assets/mocap/16_55.bvh"), "A")
B = MocapClip(os.path.abspath("../assets/mocap/%s.bvh" % sys.argv[-1]), "B")
T0 = 1.0
tr_guess = T0 + 4.0
track = BowlerTrack(skel, A, B, t_run_start=T0, run_rate=1.15)
track.build(T0 + 7.0, rate_fn=lambda t: 1.15, heading_fn=lambda t: 0.0, stop_fn=lambda t: 0.0)
lc = track.foot_contacts("Left", T0 + 3.0, T0 + 5.5)
rc = track.foot_contacts("Right", T0 + 3.0, T0 + 5.5)
print("LEFT", [(round(t,3), round(p.y,2)) for t,p in lc]); print("RIGHT", [(round(t,3), round(p.y,2)) for t,p in rc])
tr = lc[1][0]
print("TR", tr)
# speed
i0, i1 = track.index(T0+2.5), track.index(T0+3.5)
print("SPEED", (track.raw[i1]["root"]-track.raw[i0]["root"]).length)
sc = bpy.context.scene
sc.render.fps = WORLD_FPS
for i in range(track.index(tr-1.0), track.index(tr+1.0), 4):
    t = track.times[i]
    p = bowling_overrides(skel, track.raw[i], t, tr, T0, T0)
    skel.key(p, i)
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 480, 360
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
light = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN')); sc.collection.objects.link(light); light.rotation_euler=(0.8,0.2,0.5); light.data.energy=4
bpy.ops.mesh.primitive_plane_add(size=200)
world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes=True; world.node_tree.nodes["Background"].inputs[1].default_value=0.6
out = os.path.abspath("../render/test/bowl"); os.makedirs(out, exist_ok=True)
hr = track.raw[track.index(tr)]["root"]
cam.location = (hr.x - 6, hr.y, 1.3); cam.rotation_euler = (math.radians(88), 0, math.radians(-90))
cam.data.lens = 30
k = 0
for dt in [-0.6,-0.45,-0.35,-0.25,-0.15,-0.08,0,0.06,0.12,0.2,0.3,0.45]:
    i = track.index(tr+dt); i -= i % 4
    sc.frame_set(i)
    sc.render.filepath = f"{out}/b_{k:02d}.png"; k+=1
    bpy.ops.render.render(write_still=True)
