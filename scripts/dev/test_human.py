import bpy, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from characters import make_human
bpy.ops.wm.read_factory_settings(use_empty=True)
rig, body = make_human("bowler")
print("RIG", rig, "BODY", body)
for o in bpy.data.objects: print("OBJ", o.name, o.type, o.parent.name if o.parent else None, [m.type for m in o.modifiers])
for o in bpy.data.objects:
    if o.type=='MESH':
        for s in o.material_slots: print("MAT", o.name, s.material.name if s.material else None)
print("BONES", [ (b.name, tuple(round(x,3) for x in b.head_local)) for b in rig.data.bones][:8])
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath("render/test_human.blend"))
