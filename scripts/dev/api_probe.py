import bpy
sc=bpy.context.scene
print("ENGINES", [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items])
p=bpy.types.RenderSettings.bl_rna.properties['motion_blur_shutter']; print("SHUTTER", p.hard_min, p.hard_max)
e=sc.eevee; print("EEVEE", [k for k in dir(e) if not k.startswith('_')][:80])
print("CYC", hasattr(sc,'cycles'))
import numpy; print("NUMPY", numpy.__version__)
print("VIEW", [i.identifier for i in bpy.types.ColorManagedViewSettings.bl_rna.properties['look'].enum_items][:20])
