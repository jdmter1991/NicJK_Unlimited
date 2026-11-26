"""Blender (read-only): what feeds the Roughness output of the node group behind a material's Principled BSDF.
  blender -b ... --python gloss_group.py -- <out.json> <material> [<material> ...]"""
import bpy, sys, json
args = sys.argv[sys.argv.index("--") + 1:]; out = args[0]


def walk(sock, depth=0, env=None):
    if depth > 14:
        return "..."
    if not sock.is_linked:
        try:
            v = sock.default_value
            return round(float(v), 4) if isinstance(v, (int, float)) else [round(float(x), 4) for x in v]
        except Exception:
            return None
    l = sock.links[0]; n = l.from_node
    if n.bl_idname == "NodeGroupInput":
        return {"group_input": l.from_socket.name, "outer": env.get(l.from_socket.name) if env else None}
    d = {"node": n.bl_idname.replace("ShaderNode", ""), "out": l.from_socket.name}
    if n.bl_idname == "ShaderNodeTexImage":
        d["image"] = n.image.name if n.image else None; return d
    if n.bl_idname == "ShaderNodeMath":
        d["op"] = n.operation; d["clamp"] = n.use_clamp
    if n.bl_idname == "ShaderNodeValToRGB":
        d["ramp"] = [[round(e.position, 3), round(e.color[0], 3)] for e in n.color_ramp.elements]
    if n.bl_idname == "ShaderNodeGroup":
        inner = n.node_tree; go = next((x for x in inner.nodes if x.bl_idname == "NodeGroupOutput" and x.is_active_output), None)
        e2 = {i.name: walk(i, depth + 1, env) for i in n.inputs}
        d["group"] = inner.name; d["inside"] = walk(go.inputs[l.from_socket.name], depth + 1, e2) if go else None
        return d
    d["in"] = [walk(i, depth + 1, env) for i in n.inputs if i.enabled][:4]
    return d


res = {}
for name in args[1:]:
    m = bpy.data.materials.get(name)
    b = next((n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None) if m else None
    if b:
        res[name] = {"Roughness": walk(b.inputs["Roughness"])}
json.dump(res, open(out, "w"), indent=1)
print("gloss_group:", len(res))
