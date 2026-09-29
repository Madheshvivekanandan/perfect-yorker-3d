import bpy, json, math
from mathutils import Vector
meta = json.load(open("render/shots.json")); WF, TH = meta["world_fps"], meta["T_HIT"]
rig = bpy.data.objects["Batsman"]; sc = bpy.context.scene
for dt in (-1.0, 0.2, 0.8, 1.5, 2.0, 3.0):
    sc.frame_set(int((TH + dt) * WF))
    out = []
    for b in ("spine01", "neck01", "neck02", "neck03", "head"):
        pb = rig.pose.bones[b]
        m = (rig.matrix_world @ pb.matrix).to_3x3() @ rig.data.bones[b].matrix_local.to_3x3().inverted()
        f = m @ Vector((0, -1, 0))
        out.append(f"{b}:{math.degrees(math.asin(max(-1, min(1, f.z)))):+.0f}")
    print("T+%.1f" % dt, " ".join(out))
print("rest head dir", tuple(round(v, 2) for v in rig.data.bones["head"].matrix_local.to_3x3() @ Vector((0, 1, 0))))
