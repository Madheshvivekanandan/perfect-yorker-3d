import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
for f in ["09_01","09_02","16_35","16_55","16_45"]:
    bpy.ops.import_anim.bvh(filepath=f"assets/mocap/{f}.bvh", global_scale=1.0, frame_start=1, use_fps_scale=False, rotate_mode='NATIVE', axis_forward='-Z', axis_up='Y')
    a = bpy.context.object
    fr = a.animation_data.action.frame_range
    sc = bpy.context.scene
    hs=[]
    for t in range(int(fr[0]), int(fr[1])+1, 12):
        sc.frame_set(t); h=a.matrix_world @ a.pose.bones["Hips"].head; hs.append(tuple(round(v,2) for v in h))
    print("BVH", f, fr[:], "hips", hs)
    print("REST", [(b.name, tuple(round(v,2) for v in b.head_local)) for b in a.data.bones if b.name in ("Hips","LeftFoot","Head","LeftHand","LeftArm")])
