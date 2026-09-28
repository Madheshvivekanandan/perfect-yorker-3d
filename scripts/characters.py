"""Build realistic human characters with MPFB (MakeHuman for Blender, CC0 assets)."""
import bpy
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.objectservice import ObjectService


def make_human(name, skin="young_asian_male", hair="short02", height=0.6, muscle=0.7, weight=0.45,
               race=None, clothes=("male_casualsuit04", "shoes06")):
    info = HumanService._create_default_human_info_dict()
    info["name"] = name
    info["phenotype"].update({"gender": 1.0, "age": 0.45, "muscle": muscle, "weight": weight,
                              "height": height, "proportions": 0.8})
    info["phenotype"]["race"] = race or {"asian": 0.8, "caucasian": 0.1, "african": 0.1}
    info["rig"] = "cmu_mb"
    info["eyes"] = "high-poly/high-poly.mhclo"
    info["eyes_material_type"] = "PROCEDURAL_EYES"
    info["eyebrows"] = "eyebrow001/eyebrow001.mhclo"
    info["eyelashes"] = "eyelashes01/eyelashes01.mhclo"
    info["hair"] = f"{hair}/{hair}.mhclo" if hair else ""
    info["clothes"] = [f"{c}/{c}.mhclo" for c in clothes]
    info["skin_mhmat"] = f"{skin}/{skin}.mhmat"
    info["skin_material_type"] = "ENHANCED_SSS"
    settings = HumanService.get_default_deserialization_settings()
    settings["subdiv_levels"] = 1
    basemesh = HumanService.deserialize_from_dict(info, settings)
    rig = ObjectService.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")
    return rig, basemesh


def children_meshes(rig):
    return [o for o in bpy.data.objects if o.type == 'MESH' and (o.parent == rig or (o.parent and o.parent.parent == rig))]


def kit(rig, cloth_name, shirt_rgb, pants_rgb, waist_z=0.98):
    """Recolour a MakeHuman outfit into a team kit: upper loose parts -> shirt, lower -> trousers."""
    import bmesh, os
    obj = next(o for o in bpy.data.objects if o.parent == rig and o.name.endswith(cloth_name))
    old = obj.active_material
    tex_dir = None
    for n in old.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image and "normal" in n.image.name.lower():
            normal_img = n.image
            break
    else:
        normal_img = None
    mats = []
    for label, rgb, sheen in (("shirt", shirt_rgb, 0.6), ("pants", pants_rgb, 0.4)):
        m = bpy.data.materials.new(f"{rig.name}_{label}")
        m.use_nodes = True
        nt = m.node_tree
        b = nt.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*rgb, 1)
        b.inputs["Roughness"].default_value = 0.75
        b.inputs["Sheen Weight"].default_value = sheen
        b.inputs["Sheen Tint"].default_value = (*rgb, 1)
        # woven fabric micro-bump + original fold normal map
        wave = nt.nodes.new("ShaderNodeTexNoise"); wave.inputs["Scale"].default_value = 900
        bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.12
        nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
        if normal_img:
            ti = nt.nodes.new("ShaderNodeTexImage"); ti.image = normal_img
            ti.image.colorspace_settings.name = "Non-Color"
            nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = 1.0
            nt.links.new(ti.outputs[0], nm.inputs["Color"])
            nt.links.new(nm.outputs[0], bump.inputs["Normal"])
        nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
        mats.append(m)
    obj.data.materials.clear()
    for m in mats:
        obj.data.materials.append(m)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    seen = set()
    for f in bm.faces:
        if f.index in seen:
            continue
        comp, stack = [], [f]
        seen.add(f.index)
        while stack:
            c = stack.pop(); comp.append(c)
            for e in c.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index); stack.append(g)
        zs = [v.co.z for c in comp for v in c.verts]
        idx = 0 if sum(zs) / len(zs) > waist_z else 1
        for c in comp:
            c.material_index = idx
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def remove_part(rig, suffix):
    for o in list(bpy.data.objects):
        if o.parent == rig and o.name.endswith(suffix):
            bpy.data.objects.remove(o)
