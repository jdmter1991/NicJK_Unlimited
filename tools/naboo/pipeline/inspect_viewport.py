"""Write the saved 3D viewport views (and the scene camera) of a .blend to JSON.
  blender -b --factory-startup --disable-autoexec file.blend --python inspect_viewport.py -- <out.json>"""
import bpy, sys, json
out = {"views": [], "camera": None}
for scr in bpy.data.screens:
    for ar in scr.areas:
        if ar.type == "VIEW_3D":
            sp = ar.spaces[0]; r = sp.region_3d
            if r is None:
                continue
            inv = r.view_matrix.inverted()
            out["views"].append({"screen": scr.name, "size": [ar.width, ar.height], "perspective": r.view_perspective, "lens": sp.lens,
                                 "eye": list(inv.translation), "forward": list(-inv.col[2].xyz), "up": list(inv.col[1].xyz),
                                 "distance": r.view_distance, "shading": sp.shading.type})
c = bpy.context.scene.camera
if c:
    m = c.matrix_world
    out["camera"] = {"name": c.name, "eye": list(m.translation), "forward": list(-m.col[2].xyz), "lens": c.data.lens, "sensor": c.data.sensor_width}
json.dump(out, open(sys.argv[sys.argv.index("--") + 1], "w"), indent=1)
