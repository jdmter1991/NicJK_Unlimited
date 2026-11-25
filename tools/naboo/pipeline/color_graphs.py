"""Blender (read-only): Base Color / Roughness / Alpha node graphs of materials as nested expressions, and the
images they use.
  blender -b --factory-startup --disable-autoexec <file.blend> --python color_graphs.py -- <out.json> <names.txt> <image_dir>
names.txt: material names to dump (one per line). Images referenced by those expressions are saved as PNG copies
into image_dir unless a file of that name already exists there. The .blend is never saved.

Scalar / colour expressions:
  ["tex", image, socket, coord]      socket: Color, Alpha, Red, Green, Blue
  ["mix", blend_type, fac, a, b, clamp_result]
  ["math", op, clamp, args...]   ["vmath", op, args...]   ["clamp", x, lo, hi]   ["combine", x, y, z]
  ["sep", channel, x]   ["vcol", layer, socket]   ["geo", output]   ["const", value]   ["other", type]
Coordinates (vector expressions):
  ["uv", name]  ["texcoord", socket]  ["geo", "Position"]  ["mapping", scale, location, rotation, vtype, inner]
  ["combine", x, y, z]  ["vmath", op, args...]  ["default"]
"""
import bpy, sys, json, os

args = sys.argv[sys.argv.index("--") + 1:]
out, names_file, image_dir = args[0], args[1], args[2]
names = [l.rstrip("\n") for l in open(names_file, encoding="utf-8") if l.strip()]
LIMIT = 60
images_used = {}


def cval(s):
    try:
        v = s.default_value
        return [round(float(x), 5) for x in v] if hasattr(v, "__len__") else round(float(v), 5)
    except Exception:
        return None


def vexpr(sock, d=0):
    """vector-valued socket (texture coordinates)"""
    if d > LIMIT:
        return ["deep"]
    if not sock.is_linked:
        return ["const", cval(sock)]
    l = sock.links[0]; n = l.from_node; t = n.bl_idname; fs = l.from_socket.name
    if t == "ShaderNodeMapping":
        return ["mapping", cval(n.inputs["Scale"]), cval(n.inputs["Location"]) if not n.inputs["Location"].is_linked else "linked",
                cval(n.inputs["Rotation"]), n.vector_type, vexpr(n.inputs["Vector"], d + 1) if n.inputs["Vector"].is_linked else ["default"]]
    if t == "ShaderNodeUVMap":
        return ["uv", n.uv_map]
    if t == "ShaderNodeTexCoord":
        return ["texcoord", fs]
    if t == "ShaderNodeNewGeometry":
        return ["geo", fs]
    if t == "ShaderNodeCombineXYZ":
        return ["combine"] + [expr(i, d + 1) for i in list(n.inputs)[:3]]
    if t == "ShaderNodeVectorMath":
        return ["vmath", n.operation] + [vexpr(i, d + 1) if i.type == "VECTOR" else expr(i, d + 1) for i in n.inputs if i.enabled]
    if t == "ShaderNodeSeparateXYZ":
        return ["sep", fs, vexpr(n.inputs[0], d + 1)]
    return ["other", t[10:]]


def expr(sock, d=0):
    if d > LIMIT:
        return ["deep"]
    if sock is None:
        return None
    if not sock.is_linked:
        return ["const", cval(sock)]
    l = sock.links[0]; n = l.from_node; t = n.bl_idname; fs = l.from_socket.name
    if t == "ShaderNodeTexImage":
        if n.image:
            images_used[n.image.name] = n.image
        c = vexpr(n.inputs["Vector"], d + 1) if n.inputs["Vector"].is_linked else ["default"]
        return ["tex", n.image.name if n.image else None, fs, c, n.extension, n.interpolation]
    if t == "ShaderNodeSeparateColor":
        e = expr(n.inputs[0], d + 1)
        if e and e[0] == "tex" and e[2] == "Color":
            return ["tex", e[1], fs, e[3], e[4], e[5]]
        return ["sep", fs, e]
    if t == "ShaderNodeSeparateXYZ":
        return ["sep", fs, vexpr(n.inputs[0], d + 1)]
    if t in ("ShaderNodeMix", "ShaderNodeMixRGB"):
        ins = [i for i in n.inputs if i.enabled]
        fac = next((i for i in ins if i.name in ("Factor", "Fac")), None)
        ab = [i for i in ins if i.name in ("A", "B", "Color1", "Color2")]
        return ["mix", getattr(n, "blend_type", "MIX"), expr(fac, d + 1), expr(ab[0], d + 1) if ab else None, expr(ab[1], d + 1) if len(ab) > 1 else None,
                bool(getattr(n, "clamp_result", False)) or bool(getattr(n, "use_clamp", False)), bool(getattr(n, "clamp_factor", True))]
    if t == "ShaderNodeMath":
        return ["math", n.operation, bool(n.use_clamp)] + [expr(i, d + 1) for i in n.inputs if i.enabled]
    if t == "ShaderNodeVectorMath":
        return ["vmath", n.operation] + [expr(i, d + 1) for i in n.inputs if i.enabled]
    if t == "ShaderNodeVertexColor":
        return ["vcol", n.layer_name, fs]
    if t == "ShaderNodeNewGeometry":
        return ["geo", fs]
    if t in ("ShaderNodeRGB", "ShaderNodeValue"):
        return ["const", cval(n.outputs[0])]
    if t == "ShaderNodeClamp":
        return ["clamp", expr(n.inputs[0], d + 1), expr(n.inputs[1], d + 1), expr(n.inputs[2], d + 1)]
    if t in ("ShaderNodeCombineColor", "ShaderNodeCombineXYZ"):
        return ["combine"] + [expr(i, d + 1) for i in list(n.inputs)[:3]]
    if t == "ShaderNodeMapRange":
        return ["maprange", bool(n.clamp), n.interpolation_type] + [expr(n.inputs[i], d + 1) for i in range(5)]
    if t == "ShaderNodeInvert":
        return ["invert", expr(n.inputs[0], d + 1), expr(n.inputs[1], d + 1)]
    if t == "ShaderNodeGamma":
        return ["gamma", expr(n.inputs[0], d + 1), expr(n.inputs[1], d + 1)]
    return ["other", t[10:]]


res = {"materials": {}, "images": {}}
for nm in names:
    m = bpy.data.materials.get(nm)
    if not m or not m.node_tree:
        continue
    p = next((n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    if p is None:
        continue
    res["materials"][nm] = {"color": expr(p.inputs["Base Color"]), "roughness": expr(p.inputs["Roughness"]), "alpha": expr(p.inputs["Alpha"]),
                            "metallic": expr(p.inputs["Metallic"])}
os.makedirs(image_dir, exist_ok=True)
saved = kept = failed = 0
for nm, im in images_used.items():
    res["images"][nm] = {"colorspace": im.colorspace_settings.name, "size": list(im.size), "channels": im.channels, "alpha_mode": im.alpha_mode}
    dst = os.path.join(image_dir, os.path.splitext(nm)[0] + ".png")
    if os.path.exists(dst):
        kept += 1; continue
    try:
        im.save(filepath=dst); saved += 1
    except Exception as e:
        print("CG image failed", nm, e); failed += 1
json.dump(res, open(out, "w"))
print("CG materials %d images %d (saved %d, already there %d, failed %d)" % (len(res["materials"]), len(images_used), saved, kept, failed))
