import bpy, sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from characters import make_human
from posing import *
from mathutils import Vector, Quaternion
bpy.ops.wm.read_factory_settings(use_empty=True)
rig, body = make_human("bowler")
skel = Skeleton(rig)
sc = bpy.context.scene
def local_curl(p, bone, axis, deg):
    q = p[bone] @ Quaternion(Vector(axis), math.radians(deg)) @ p[bone].inverted()
    rotate_subtree(skel, p, bone, q)
variants = [None, ((1,0,0),60), ((1,0,0),-60), ((0,0,1),60), ((0,0,1),-60)]
for i, v in enumerate(variants):
    p = skel.rest_pose()
    point_bone(skel, p, "RightArm", (0,-0.3,-0.95)); point_bone(skel, p, "RightForeArm", (0,-0.9,-0.2)); point_bone(skel, p, "RightHand", (0,-1,0))
    if v:
        local_curl(p, "RightFingerBase", v[0], v[1]); local_curl(p, "RightHandFinger1", v[0], v[1])
    skel.key(p, i+1)
sc.render.engine='BLENDER_EEVEE'; sc.render.resolution_x=sc.render.resolution_y=400
cam=bpy.data.objects.new("c",bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera=cam; cam.data.lens=85
l=bpy.data.objects.new("s",bpy.data.lights.new("s",'SUN')); sc.collection.objects.link(l); l.rotation_euler=(0.6,0.3,0.4); l.data.energy=4
w=bpy.data.worlds.new("w"); sc.world=w; w.use_nodes=True; w.node_tree.nodes["Background"].inputs[1].default_value=0.8
out=os.path.abspath("render/test/hand"); os.makedirs(out,exist_ok=True)
for i in range(len(variants)):
    sc.frame_set(i+1)
    h=skel.fk({k:v for k,v in [(n, None) for n in []]}) if False else None
    hb=rig.pose.bones["RightHand"]; c=rig.matrix_world@hb.tail
    cam.location=c+Vector((-0.35,-0.25,0.15)); d=c-cam.location; cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    sc.render.filepath=f"{out}/h{i}.png"; bpy.ops.render.render(write_still=True)
