import bpy, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from characters import make_human
from posing import *
bpy.ops.wm.read_factory_settings(use_empty=True)
rig, body = make_human("bowler")
skel = Skeleton(rig)
clip = MocapClip(os.path.abspath("../assets/mocap/16_55.bvh"), "run")
rt = Retargeter(skel, clip)
p = rt.pose(0)
sc=bpy.context.scene; sc.frame_set(1)
mw=clip.obj.matrix_world
for n in ["LeftShoulder","LeftArm","LeftForeArm","LeftHand","Spine1","LeftUpLeg"]:
    b=clip.obj.data.bones[n]; pb=clip.obj.pose.bones[n]
    sdir=(mw.to_3x3()@(pb.tail-pb.head)).normalized()
    tdir=(p[n]@Vector((0,1,0)))
    print("DIR",n,"src",tuple(round(v,2) for v in sdir),"tgt",tuple(round(v,2) for v in tdir),
          "srcrest",tuple(round(v,2) for v in clip.rest_dir[n]),"tgtrest",tuple(round(v,2) for v in (skel.rest_rot[n]@Vector((0,1,0)))), "parent", b.parent.name if b.parent else None, [c.name for c in b.children])
for f in (1, 60):
    sc.frame_set(f)
    pb=clip.obj.pose.bones["LeftArm"]
    print("CHK", f, tuple(round(v,2) for v in (clip.samples[f]["LeftArm"]@Vector((0,1,0)))), tuple(round(v,2) for v in ((mw@pb.matrix).to_quaternion()@Vector((0,1,0)))), tuple(round(v,2) for v in (mw.to_3x3()@(pb.tail-pb.head)).normalized()))
print("MW", mw)
print("ROT", pb.rotation_mode, clip.act.fcurves[3].data_path if hasattr(clip.act,'fcurves') else None)
