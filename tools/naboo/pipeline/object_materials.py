"""Blender (read-only): objects whose material slots differ from their mesh data's materials (slots linked to the
object), and objects with a custom colour. The export takes materials from the mesh, so those placements would be
drawn with the wrong material.
  blender -b --factory-startup --disable-autoexec <file.blend> --python object_materials.py -- <out.json>"""
import bpy, sys, json
out = sys.argv[sys.argv.index("--") + 1]
res = {"overrides": {}, "object_linked_slots": 0, "objects": 0}
for ob in bpy.data.objects:
    if ob.type != "MESH":
        continue
    res["objects"] += 1
    data_m = [m.name if m else None for m in ob.data.materials]
    slot_m = [s.material.name if s.material else None for s in ob.material_slots]
    if any(s.link == "OBJECT" for s in ob.material_slots):
        res["object_linked_slots"] += 1
    if slot_m != data_m:
        res["overrides"][ob.name] = {"mesh": ob.data.name, "object": slot_m, "data": data_m}
json.dump(res, open(out, "w"), indent=1)
print("object_materials:", res["objects"], "mesh objects,", res["object_linked_slots"], "with object-linked slots,", len(res["overrides"]), "differ from their mesh")
