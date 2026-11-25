"""Blender (read-only): material records and base textures for materials that are assigned on objects instead of
on their mesh (tools/object_materials.py found them).  blender ... --python export_object_materials.py -- <export_dir>
Uses the same material_info() as export_region.py. Writes <export_dir>/dump/materials_objects.json and copies of
the base images into <export_dir>/dump/textures."""
import bpy, sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
ed = sys.argv[sys.argv.index("--") + 1]
ns = {"bpy": bpy}
_src = open(os.path.join(HERE, "_materials_block.py"), encoding="utf-8").read()
_src = _src[:_src.index(chr(10) + "MAT = {}")]
exec(compile(_src, "_materials_block.py", "exec"), ns)
ov = json.load(open(os.path.join(ed, "object_materials.json")))["overrides"]
names = sorted({a for v in ov.values() for a, b in zip(v["object"], v["data"]) if a and a != b})
out = {}; td = os.path.join(ed, "dump", "textures"); saved = 0
for mn in names:
    m = bpy.data.materials.get(mn)
    if m is None:
        print("OMAT missing", mn); continue
    d = ns["material_info"](m)
    p = next((n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None) if m.node_tree else None
    if p is not None:
        a = p.inputs["Alpha"]
        d["alpha_const"] = None if a.is_linked else float(a.default_value)
    out[mn] = d
    nm = d.get("base_image")
    if nm:
        dst = os.path.join(td, os.path.splitext(nm)[0] + ".png")
        im = bpy.data.images.get(nm)
        if im is not None and not os.path.exists(dst):
            try:
                im.save(filepath=dst); saved += 1
            except Exception as e:
                print("OMAT image failed", nm, e)
json.dump(out, open(os.path.join(ed, "dump", "materials_objects.json"), "w"), indent=1)
print("OMAT materials", len(out), "images saved", saved)
