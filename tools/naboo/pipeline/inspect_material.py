"""Print the node tree of materials whose name contains a given text (and of objects using them).
  blender -b --factory-startup --disable-autoexec file.blend --python inspect_material.py -- <text> <out.json>"""
import bpy, sys, json
a = sys.argv[sys.argv.index("--") + 1:]; out = {}
for m in bpy.data.materials:
    if a[0] in m.name and m.node_tree:
        d = {"blend": getattr(m, "blend_method", None), "nodes": [], "links": []}
        for n in m.node_tree.nodes:
            ins = {}
            for s in n.inputs:
                try:
                    v = s.default_value; v = list(v) if hasattr(v, "__len__") else v
                except Exception:
                    v = None
                ins[s.name] = {"v": v, "linked": s.is_linked}
            d["nodes"].append({"name": n.name, "type": n.bl_idname, "in": ins, "blend_type": getattr(n, "blend_type", None), "op": getattr(n, "operation", None),
                               "image": getattr(getattr(n, "image", None), "name", None), "attr": getattr(n, "attribute_name", None), "layer": getattr(n, "layer_name", None)})
        for l in m.node_tree.links:
            d["links"].append([l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name])
        out[m.name] = d
json.dump(out, open(a[1], "w"), indent=1)
