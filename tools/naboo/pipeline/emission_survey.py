"""Blender (read-only): emission of every material (colour, strength, driving image) and light objects.
  blender ... --python emission_survey.py -- <out_dir> ...   writes <out_dir>/../../emission_survey.json"""
import bpy, sys, json, os
out_dir = sys.argv[sys.argv.index("--") + 1]
out = os.path.normpath(os.path.join(out_dir, "..", "..", "emission_survey.json"))
res = {"materials": {}, "lights": []}
def val(s):
    try:
        v = s.default_value
        return [round(float(x), 4) for x in v] if hasattr(v, "__len__") else round(float(v), 4)
    except Exception:
        return None
def first_image(s, d=0):
    if not s.is_linked or d > 10: return None
    n = s.links[0].from_node
    if n.bl_idname == "ShaderNodeTexImage": return [n.image.name if n.image else None, s.links[0].from_socket.name]
    for i in n.inputs:
        r = first_image(i, d + 1)
        if r: return r
    return None
for m in bpy.data.materials:
    if not m.node_tree or m.users == 0: continue
    e = None
    for n in m.node_tree.nodes:
        if n.bl_idname == "ShaderNodeBsdfPrincipled":
            st = n.inputs.get("Emission Strength"); col = n.inputs.get("Emission Color")
            if st is None: continue
            if st.is_linked or (val(st) or 0) > 0:
                e = {"kind": "principled", "strength": val(st), "strength_linked": st.is_linked, "color": val(col), "color_image": first_image(col), "strength_image": first_image(st),
                     "base": val(n.inputs["Base Color"]), "base_image": first_image(n.inputs["Base Color"]), "alpha_image": first_image(n.inputs["Alpha"]), "blend": m.blend_method}
        elif n.bl_idname == "ShaderNodeEmission":
            e = {"kind": "emission", "strength": val(n.inputs["Strength"]), "strength_linked": n.inputs["Strength"].is_linked, "color": val(n.inputs["Color"]),
                 "color_image": first_image(n.inputs["Color"]), "strength_image": first_image(n.inputs["Strength"]), "blend": m.blend_method}
    if e: res["materials"][m.name] = e
for o in bpy.data.objects:
    if o.type == "LIGHT":
        L = o.data
        res["lights"].append({"name": o.name, "type": L.type, "energy": float(L.energy), "color": [round(float(c), 3) for c in L.color], "loc": [round(float(x), 2) for x in o.matrix_world.translation],
                              "radius": float(getattr(L, "shadow_soft_size", 0.0)), "visible": o.visible_get() if o.name in bpy.context.view_layer.objects else None,
                              "collections": [c.name for c in o.users_collection]})
json.dump(res, open(out, "w"), indent=0)
print("EMIS materials", len(res["materials"]), "lights", len(res["lights"]))
