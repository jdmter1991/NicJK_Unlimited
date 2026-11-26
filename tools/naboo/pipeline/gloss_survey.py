"""Blender (read-only): how glossy each material is: the Principled BSDF's Roughness, Metallic, specular and coat
inputs (value, or the chain of nodes and images feeding them).
  blender -b --factory-startup --disable-autoexec <file.blend> --python gloss_survey.py -- <out.json>"""
import bpy, sys, json
out = sys.argv[sys.argv.index("--") + 1]


def chain(sock, depth=0):
    if not sock.is_linked or depth > 8:
        try:
            v = sock.default_value
            return round(float(v), 4) if isinstance(v, (int, float)) else [round(float(x), 4) for x in v]
        except Exception:
            return None
    n = sock.links[0].from_node; d = {"node": n.bl_idname.replace("ShaderNode", ""), "out": sock.links[0].from_socket.name}
    if n.bl_idname == "ShaderNodeTexImage":
        d["image"] = n.image.name if n.image else None; return d
    if n.bl_idname == "ShaderNodeMath":
        d["op"] = n.operation
    if n.bl_idname in ("ShaderNodeMapRange", "ShaderNodeValToRGB", "ShaderNodeInvert", "ShaderNodeMath", "ShaderNodeMix", "ShaderNodeMixRGB", "ShaderNodeSeparateColor", "ShaderNodeSeparateRGB", "ShaderNodeClamp", "ShaderNodeGamma", "ShaderNodeBrightContrast"):
        d["in"] = [chain(i, depth + 1) for i in n.inputs if i.enabled][:4]
    if n.bl_idname == "ShaderNodeValToRGB":
        d["ramp"] = [[round(e.position, 3), round(e.color[0], 3)] for e in n.color_ramp.elements]
    return d


res = {}
for m in bpy.data.materials:
    if not m.use_nodes or not m.node_tree or m.users == 0:
        continue
    b = next((n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    if not b:
        continue
    e = {}
    for name in ("Roughness", "Metallic", "Specular IOR Level", "Specular", "Coat Weight", "Coat Roughness", "IOR"):
        s = b.inputs.get(name)
        if s is not None:
            e[name] = chain(s)
    res[m.name] = e
json.dump(res, open(out, "w"), indent=1)
print("gloss_survey:", len(res), "materials")
