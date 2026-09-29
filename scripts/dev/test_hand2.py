import bpy, sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from characters import make_human
from mathutils import Vector, Quaternion, Euler
bpy.ops.wm.read_factory_settings(use_empty=True)
rig, body = make_human("bowler", rig="default")
sc = bpy.context.scene
pb = rig.pose.bones
variants = [None, ('X', 50), ('X', -50), ('Z', 50), ('Z', -50)]
for i, v in enumerate(variants):
    for b in pb:
        b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, 0)
    if v:
        for f in range(1, 6):
            for s in (1, 2, 3):
                e = [0, 0, 0]; e['XYZ'.index(v[0])] = math.radians(v[1] * (0.6 if f == 1 else 1))
                pb[f"finger{f}-{s}.R"].rotation_euler = e
    for b in pb:
        b.keyframe_insert("rotation_euler", frame=i + 1)
sc.render.engine='BLENDER_EEVEE'; sc.render.resolution_x=sc.render.resolution_y=400
cam=bpy.data.objects.new("c",bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera=cam; cam.data.lens=85
l=bpy.data.objects.new("s",bpy.data.lights.new("s",'SUN')); sc.collection.objects.link(l); l.rotation_euler=(0.6,0.3,0.4); l.data.energy=4
w=bpy.data.worlds.new("w"); sc.world=w; w.use_nodes=True; w.node_tree.nodes["Background"].inputs[1].default_value=0.8
out=os.path.abspath("render/test/hand"); os.makedirs(out,exist_ok=True)
for i in range(len(variants)):
    sc.frame_set(i+1)
    c = rig.matrix_world @ pb["wrist.R"].tail
    cam.location=c+Vector((-0.45,-0.3,0.05)); d=c-cam.location; cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    sc.render.filepath=f"{out}/d{i}.png"; bpy.ops.render.render(write_still=True)
