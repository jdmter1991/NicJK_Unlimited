"""Blender (headless, read-only): inventory of everything water-like in the scene.
  blender -b --factory-startup --disable-autoexec <file.blend> --python water_inspect.py -- <out.json>
Lists objects whose name or material names look like water (water, river, lake, sea, ocean, pond, fountain,
foam, wave, splash, falls, wet, puddle, canal), with world bounds, triangle counts, visibility, modifiers and
the full node tree of each such material (node types, key inputs, image names, links).
"""
import bpy, sys, json, re
import numpy as np
from mathutils import Vector

out = sys.argv[sys.argv.index("--") + 1]
PAT = re.compile(r"water|river|lake|sea|ocean|pond|fountain|foam|wave|splash|fall|wet|puddle|canal|caustic|ripple|liquid", re.I)


def node_tree(nt, depth=0):
    nodes = []
    for n in nt.nodes:
        d = {"name": n.name, "type": n.bl_idname, "label": n.label}
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            d["image"] = n.image.name; d["size"] = list(n.image.size); d["colorspace"] = n.image.colorspace_settings.name
            d["filepath"] = n.image.filepath
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree and depth < 2:
            d["group"] = n.node_tree.name; d["group_nodes"] = node_tree(n.node_tree, depth + 1)
        ins = {}
        for s in n.inputs:
            if s.is_linked:
                l = s.links[0]; ins[s.name] = "<- %s.%s" % (l.from_node.name, l.from_socket.name)
            elif hasattr(s, "default_value"):
                try:
                    v = s.default_value
                    ins[s.name] = [round(float(x), 4) for x in v] if hasattr(v, "__len__") else round(float(v), 4)
                except Exception:
                    pass
        d["inputs"] = ins
        for attr in ("blend_type", "operation", "data_type", "interpolation", "extension", "projection", "vector_type", "distribution"):
            if hasattr(n, attr):
                d[attr] = str(getattr(n, attr))
        if n.bl_idname == "ShaderNodeMapping":
            pass
        nodes.append(d)
    return nodes


res = {"objects": [], "materials": {}, "scene": {}}
sc = bpy.context.scene
res["scene"] = {"name": sc.name, "engine": sc.render.engine, "frame": sc.frame_current, "frame_range": [sc.frame_start, sc.frame_end],
                "view_transform": sc.view_settings.view_transform, "look": sc.view_settings.look, "exposure": sc.view_settings.exposure,
                "world": sc.world.name if sc.world else None}
mats = set()
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    mnames = [s.material.name for s in o.material_slots if s.material]
    if not (PAT.search(o.name) or PAT.search(o.data.name) or any(PAT.search(m) for m in mnames)):
        continue
    me = o.data
    bb = np.array([o.matrix_world @ Vector(c) for c in o.bound_box])
    res["objects"].append({"name": o.name, "mesh": me.name, "materials": mnames, "polys": len(me.polygons), "verts": len(me.vertices),
                           "min": [round(float(x), 2) for x in bb.min(0)], "max": [round(float(x), 2) for x in bb.max(0)],
                           "hide_render": o.hide_render, "hide_viewport": o.hide_viewport, "in_view_layer": o.name in bpy.context.view_layer.objects,
                           "visible": o.visible_get() if o.name in bpy.context.view_layer.objects else None,
                           "modifiers": [(m.type, m.name) for m in o.modifiers], "animated": bool(o.animation_data),
                           "shape_keys": bool(me.shape_keys), "uv_layers": [u.name for u in me.uv_layers],
                           "color_attrs": [c.name for c in me.color_attributes], "parent": o.parent.name if o.parent else None,
                           "collections": [c.name for c in o.users_collection]})
    mats.update(m for m in mnames if PAT.search(m) or PAT.search(o.name))
for mn in sorted(mats):
    m = bpy.data.materials[mn]
    d = {"blend_method": getattr(m, "blend_method", None), "use_backface_culling": m.use_backface_culling,
         "animated": bool(m.node_tree and m.node_tree.animation_data), "users": m.users}
    if m.node_tree:
        d["nodes"] = node_tree(m.node_tree)
        if m.node_tree.animation_data:
            ad = m.node_tree.animation_data
            d["drivers"] = [(f.data_path, f.driver.expression) for f in ad.drivers]
            if ad.action:
                d["fcurves"] = [(f.data_path, f.array_index, [tuple(round(x, 3) for x in k.co) for k in f.keyframe_points][:6]) for f in ad.action.fcurves] if hasattr(ad.action, "fcurves") else "layered action"
    res["materials"][mn] = d
json.dump(res, open(out, "w"), indent=1)
print("WATER_INSPECT objects %d materials %d" % (len(res["objects"]), len(res["materials"])))
