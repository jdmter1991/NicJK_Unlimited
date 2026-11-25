"""Blender (read-only): what is in the separate palace-interior .blend: scenes, render settings, world, lights,
cameras, object bounds, and the world positions of mesh objects by name (to line the file up with the main scene).
  blender -b --factory-startup --disable-autoexec <file.blend> --python palace_inspect.py -- <out.json>"""
import bpy, sys, json
from mathutils import Vector
out = sys.argv[sys.argv.index("--") + 1]
res = {"scenes": [], "lights": [], "cameras": [], "objects": {}, "collections": [c.name for c in bpy.data.collections][:80]}
for s in bpy.data.scenes:
    w = s.world
    res["scenes"].append({"name": s.name, "engine": s.render.engine, "frame": s.frame_current, "view_transform": s.view_settings.view_transform, "look": s.view_settings.look,
                          "exposure": s.view_settings.exposure, "world": w.name if w else None, "camera": s.camera.name if s.camera else None,
                          "objects": len(s.objects), "resolution": [s.render.resolution_x, s.render.resolution_y]})
lo = Vector((1e18,) * 3); hi = Vector((-1e18,) * 3)
for ob in bpy.data.objects:
    if ob.type == "LIGHT":
        d = ob.data
        res["lights"].append({"name": ob.name, "type": d.type, "energy": d.energy, "color": list(d.color), "pos": list(ob.matrix_world.translation), "hide_render": ob.hide_render,
                              "size": getattr(d, "shadow_soft_size", None), "spot": getattr(d, "spot_size", None)})
    elif ob.type == "CAMERA":
        res["cameras"].append({"name": ob.name, "pos": list(ob.matrix_world.translation), "rot": list(ob.matrix_world.to_euler()), "lens": ob.data.lens, "sensor": ob.data.sensor_width})
    elif ob.type == "MESH":
        p = ob.matrix_world.translation
        res["objects"][ob.name] = {"mesh": ob.data.name, "pos": [round(v, 4) for v in p], "mats": [s.material.name if s.material else None for s in ob.material_slots][:6], "polys": len(ob.data.polygons), "hide_render": ob.hide_render}
        for c in ob.bound_box:
            v = ob.matrix_world @ Vector(c)
            lo = Vector((min(lo[i], v[i]) for i in range(3))); hi = Vector((max(hi[i], v[i]) for i in range(3)))
res["bounds"] = [list(lo), list(hi)]
res["counts"] = {"meshes": len(res["objects"]), "lights": len(res["lights"]), "materials": len(bpy.data.materials), "images": len(bpy.data.images)}
for w in bpy.data.worlds:
    res.setdefault("worlds", {})[w.name] = [n.bl_idname for n in w.node_tree.nodes] if w.use_nodes and w.node_tree else []
json.dump(res, open(out, "w"), indent=1)
print("palace_inspect:", res["counts"], res["scenes"])
