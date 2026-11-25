"""Blender (read-only): material records and base textures for the terrain scatter meshes that the region export
never saw.  blender ... --python export_scatter_materials.py -- <export_dir>
Uses the same material_info() as export_region.py (tools/_materials_block.py).
Writes <export_dir>/dump/materials_scatter.json and copies of the base images into <export_dir>/dump/textures."""
import bpy, sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
ed = sys.argv[sys.argv.index("--") + 1]
ns = {"bpy": bpy}
_src = open(os.path.join(HERE, "_materials_block.py"), encoding="utf-8").read()
_src = _src[:_src.index(chr(10) + "MAT = {}")]           # the functions only, not the region export's own loop
exec(compile(_src, "_materials_block.py", "exec"), ns)
sc = json.load(open(os.path.join(ed, "dump", "scatter", "scatter.json")))
have = json.load(open(os.path.join(ed, "dump", "materials.json"), encoding="utf-8"))
have = have["materials"] if "materials" in have else have
have = set(have if isinstance(have, dict) else [x["name"] for x in have])
out = {}; td = os.path.join(ed, "dump", "textures"); saved = 0
for it in sc["items"]:
    for mn in it["materials"]:
        if not mn or mn in have or mn in out:
            continue
        m = bpy.data.materials.get(mn)
        if m is None:
            print("SMAT missing", mn); continue
        d = ns["material_info"](m)
        p = next((n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None) if m.node_tree else None
        if p is not None:
            a = p.inputs["Alpha"]
            d["alpha_const"] = None if a.is_linked else float(a.default_value)
        out[mn] = d
        for key in ("base_image",):
            nm = d.get(key)
            if nm:
                dst = os.path.join(td, os.path.splitext(nm)[0] + ".png")
                im = bpy.data.images.get(nm)
                if im is not None and not os.path.exists(dst):
                    try:
                        im.save(filepath=dst); saved += 1
                    except Exception as e:
                        print("SMAT image failed", nm, e)
        print("SMAT", mn[:44], "| builder", d.get("builder"), "| cls", d.get("cls"), "| base", d.get("base_image"), "| tint", d.get("tint"), "| alpha", d.get("alpha_source"), d.get("alpha_const"), flush=True)
json.dump(out, open(os.path.join(ed, "dump", "materials_scatter.json"), "w", encoding="utf-8"), indent=1)
print("SMAT done", len(out), "materials,", saved, "images saved")
