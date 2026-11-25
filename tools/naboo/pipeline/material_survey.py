# Read-only survey of every material: game texture slots (custom property), image nodes and what feeds
# Base Color / Alpha / Normal, plus constant tints on the way.
#   blender -b --factory-startup --disable-autoexec <blend> --python material_survey.py -- <out.json>
import bpy, sys, json
out_path = sys.argv[sys.argv.index("--") + 1]


def upstream(sock, depth=0, seen=None, path=""):
    """Walk back from a socket; return list of (image name, path description, depth)."""
    seen = seen if seen is not None else set()
    res = []
    for l in sock.links:
        n = l.from_node
        key = (n.name, l.from_socket.identifier)
        if key in seen or depth > 40:
            continue
        seen.add(key)
        tag = n.bl_idname.replace("ShaderNode", "")
        extra = ""
        if n.bl_idname == "ShaderNodeMix":
            extra = ":" + n.blend_type + ":" + n.data_type
        elif n.bl_idname == "ShaderNodeMath":
            extra = ":" + n.operation
        elif n.bl_idname == "ShaderNodeSeparateColor":
            extra = ":" + l.from_socket.identifier
        p = path + ">" + tag + extra
        if n.bl_idname == "ShaderNodeTexImage":
            res.append({"image": n.image.name if n.image else None, "out": l.from_socket.identifier, "path": p, "depth": depth})
            continue
        for i in n.inputs:
            if i.is_linked:
                res.extend(upstream(i, depth + 1, seen, p + "[" + i.identifier + "]"))
    return res


def consts(sock, depth=0, seen=None):
    """Unlinked colour inputs of Mix nodes and RGB nodes upstream (possible tints)."""
    seen = seen if seen is not None else set()
    res = []
    for l in sock.links:
        n = l.from_node
        if n.name in seen or depth > 40:
            continue
        seen.add(n.name)
        if n.bl_idname == "ShaderNodeRGB":
            res.append({"rgb": [round(x, 4) for x in n.outputs[0].default_value], "label": n.label or n.name, "depth": depth})
        for i in n.inputs:
            if i.is_linked:
                res.extend(consts(i, depth + 1, seen))
            elif n.bl_idname == "ShaderNodeMix" and i.type == 'RGBA':
                res.append({"mix_const": [round(x, 4) for x in i.default_value], "input": i.identifier, "blend": n.blend_type, "depth": depth})
    return res


R = {}
for m in bpy.data.materials:
    d = {"builder": m.get("builder", ""), "shader": m.get("shader", ""), "blend": m.blend_method,
         "textures": m.get("textures", ""), "values": m.get("values", ""), "users": m.users}
    nt = m.node_tree
    if nt:
        d["image_nodes"] = [{"image": n.image.name if n.image else None, "label": n.label, "name": n.name} for n in nt.nodes if n.bl_idname == "ShaderNodeTexImage"]
        for n in nt.nodes:
            if n.bl_idname == "ShaderNodeBsdfPrincipled":
                d["base"] = upstream(n.inputs["Base Color"])
                d["base_consts"] = consts(n.inputs["Base Color"])[:12]
                d["base_default"] = [round(x, 4) for x in n.inputs["Base Color"].default_value]
                d["alpha"] = upstream(n.inputs["Alpha"])
                d["alpha_default"] = n.inputs["Alpha"].default_value
                d["normal"] = [x["image"] for x in upstream(n.inputs["Normal"])][:4]
                break
        d["has_transparent"] = any(n.bl_idname == "ShaderNodeBsdfTransparent" for n in nt.nodes)
        d["mixshader_fac"] = [upstream(n.inputs[0]) for n in nt.nodes if n.bl_idname == "ShaderNodeMixShader"][:2]
    R[m.name] = d
json.dump(R, open(out_path, "w", encoding="utf-8"))
print("[survey] wrote", len(R))
