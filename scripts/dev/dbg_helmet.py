import bpy
for o in bpy.data.objects:
    if "helmet" in o.name and "Batsman" in o.name:
        print("H", o.name, o.type, tuple(round(v,3) for v in o.matrix_world.translation), o.parent.name if o.parent else None, o.parent_bone, len(o.data.vertices) if o.type=='MESH' else '', o.hide_render, [m.type for m in o.modifiers] if o.type=='MESH' else '')
rig=bpy.data.objects["Batsman"]
b=rig.data.bones["Head"]; print("HEADBONE", tuple(b.head_local), tuple(b.tail_local), b.length)
