"""Close-up inspection renders at given world times (for checking hands/heads)."""
import bpy, json, os, sys
from mathutils import Vector
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
meta = json.load(open(os.path.join(ROOT, "render", "shots.json")))
WF, TR, TH = meta["world_fps"], meta["T_REL"], meta["T_HIT"]
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 800, 600
sc.eevee.taa_render_samples = 24
sc.render.use_motion_blur = False
cam = bpy.data.objects.new("inspect", bpy.data.cameras.new("inspect")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.dof.use_dof = False
def bone_pos(obj, bone, tail=False):
    pb = bpy.data.objects[obj].pose.bones[bone]
    return bpy.data.objects[obj].matrix_world @ (pb.tail if tail else pb.head)
checks = [
    ("grip_polish", 5.3, "Bowler", "wrist.R", Vector((-0.35, -0.35, 0.1)), 50),
    ("grip_polish_side", 5.3, "Bowler", "wrist.R", Vector((-0.5, 0.2, 0.05)), 50),
    ("gather", TR - 0.18, "Bowler", "spine01", Vector((3.0, 0.0, 0.3)), 50),
    ("release", TR, "Bowler", "spine01", Vector((3.0, -0.5, 0.3)), 50),
    ("follow", TR + 0.15, "Bowler", "spine01", Vector((3.0, -1.0, 0.3)), 50),
    ("celebrate", TR + 2.8, "Bowler", "spine01", None, 50),
    ("bat_stance", 8.0, "Batsman", "spine01", Vector((2.4, 0.3, 0.2)), 45),
    ("bat_hit+0.8", TH + 0.8, "Batsman", "head", Vector((1.8, 1.4, 0.0)), 45),
    ("bat_hit+2", TH + 2.0, "Batsman", "head", Vector((1.8, 1.4, 0.0)), 45),
    ("bat_hit+3", TH + 3.0, "Batsman", "head", Vector((1.8, 1.4, 0.0)), 45),
    ("nonstriker", 9.0, "NonStriker", "spine01", Vector((0.8, -2.5, 0.2)), 45),
    ("umpire", 9.0, "Umpire", "spine01", Vector((0.6, -2.5, 0.2)), 45),
]
out = os.path.join(ROOT, "render", "closeups"); os.makedirs(out, exist_ok=True)
for name, t, obj, bone, off, lens in checks:
    f = t * WF; sc.frame_set(int(f), subframe=f - int(f))
    tgt = bone_pos(obj, bone)
    if off is None:     # in front of the bowler, whatever way he faces
        rig = bpy.data.objects[obj]
        fwd = (rig.matrix_world.to_3x3() @ (rig.pose.bones["spine01"].matrix.to_3x3() @ Vector((0, 0, -1)))).normalized()
        fwd.z = 0; fwd.normalize()
        off = -fwd * 3.0 + Vector((0, 0, 0.2))
    cam.location = tgt + off
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    sc.render.filepath = os.path.join(out, name + ".png")
    bpy.ops.render.render(write_still=True)
