"""Blender (read-only): scroll vectors and texture channel wiring of the animated water materials."""
import bpy, sys, json
out = sys.argv[sys.argv.index("--") + 1]
res = {}
for mn in ("Theed_Water", "waterfall|SS_Naboo_Waterfalls_", "lambert4|SS_FountainTheed_Fal", "blinn3|SS_FountainTheed_Wat"):
    m = bpy.data.materials.get(mn)
    if not m: continue
    d = {"nodes": {}, "links": []}
    for n in m.node_tree.nodes:
        e = {"type": n.bl_idname}
        if n.bl_idname in ("ShaderNodeVectorMath", "ShaderNodeMath", "ShaderNodeMapping", "ShaderNodeBump", "ShaderNodeNormalMap"):
            e["op"] = getattr(n, "operation", None)
            e["in"] = []
            for s in n.inputs:
                try:
                    v = s.default_value; v = [round(float(x), 5) for x in v] if hasattr(v, "__len__") else round(float(v), 5)
                except Exception:
                    v = None
                e["in"].append([s.name, v, s.is_linked])
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            e["image"] = n.image.name; e["size"] = list(n.image.size); e["path"] = n.image.filepath
        if n.bl_idname == "ShaderNodeVertexColor":
            e["layer"] = n.layer_name
        d["nodes"][n.name] = e
    for l in m.node_tree.links:
        d["links"].append([l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name, l.to_socket.identifier])
    res[mn] = d
ob = bpy.data.objects.get("Theed_Water")
res["Theed_Water_object"] = {"matrix": [list(r) for r in ob.matrix_world], "scale": list(ob.scale)}
json.dump(res, open(out, "w"), indent=1)
print("WI2 done")
