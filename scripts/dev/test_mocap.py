import bpy, sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from characters import make_human
from posing import *
bpy.ops.wm.read_factory_settings(use_empty=True)
rig, body = make_human("bowler")
skel = Skeleton(rig)
clip = MocapClip(os.path.abspath("../assets/mocap/16_55.bvh"), "run")
rt = Retargeter(skel, clip)
print("SCALE", rt.scale, "ZOFF", rt.z_offset, "DUR", clip.duration)
for i in range(0, 37):
    t = i/24
    p = rt.pose(t)
    skel.key(p, i+1)
    if i % 6 == 0:
        h, tl = skel.fk(p); print("T", round(t,2), "root", tuple(round(v,2) for v in p["root"]), "Ltoe", round(tl["LeftToeBase"].z,3), "Rtoe", round(tl["RightToeBase"].z,3))
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 640, 360
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
light = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN')); sc.collection.objects.link(light); light.rotation_euler=(0.8,0.2,0.5); light.data.energy=4
bpy.ops.mesh.primitive_plane_add(size=100)
world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes=True; world.node_tree.nodes["Background"].inputs[1].default_value=0.5
out = os.path.abspath("../render/test")
os.makedirs(out, exist_ok=True)
for i in (1, 13, 25, 37):
    sc.frame_set(i)
    hx = rig.pose.bones["Hips"].head
    cam.location = (hx.x - 5, hx.y, 1.2); 
    d = hx - cam.location; cam.rotation_euler = d.to_track_quat('-Z','Y').to_euler()
    sc.render.filepath = f"{out}/mocap_{i:03d}.png"
    bpy.ops.render.render(write_still=True)
