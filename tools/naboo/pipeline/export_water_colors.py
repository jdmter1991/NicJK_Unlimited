"""Blender (read-only): per-vertex red of the Color0 attribute for the foam meshes (fountain falls, waterfalls).
  blender -b --factory-startup --disable-autoexec <file.blend> --python export_water_colors.py -- <dump>/extras
Writes <dump>/extras/vcol_<mesh data name, lower case>.npz with pos (mesh space, metres) and r (0..1)."""
import bpy, sys, os, re
import numpy as np
out = sys.argv[sys.argv.index("--") + 1]
done = set()
for o in bpy.data.objects:
    if o.type != "MESH" or not re.match(r"MeshP_Fountain_Theed|Naboo_Waterfalls", o.name):
        continue
    me = o.data
    if me.name in done:
        continue
    done.add(me.name)
    ca = me.color_attributes.get("Color0")
    if ca is None:
        print("VCOL none on", me.name); continue
    n = len(ca.data); col = np.empty(n * 4, np.float32); ca.data.foreach_get("color", col); col = col.reshape(-1, 4)
    nv = len(me.vertices); pos = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", pos); pos = pos.reshape(-1, 3)
    if ca.domain == "CORNER":
        lv = np.empty(len(me.loops), np.int64); me.loops.foreach_get("vertex_index", lv)
        s = np.zeros(nv); c = np.zeros(nv); np.add.at(s, lv, col[:, 0]); np.add.at(c, lv, 1.0); r = s / np.maximum(c, 1)
    else:
        r = col[:, 0].astype(np.float64)
    fn = "vcol_" + re.sub(r"[^a-z0-9_]+", "_", me.name.lower()) + ".npz"
    np.savez(os.path.join(out, fn), pos=pos, r=r.astype(np.float32))
    print("VCOL", o.name, me.name, ca.domain, ca.data_type, nv, "r min/mean/max %.3f %.3f %.3f" % (r.min(), r.mean(), r.max()), fn)
print("VCOL done")
