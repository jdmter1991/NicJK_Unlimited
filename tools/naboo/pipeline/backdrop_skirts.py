"""Blender (headless, read-only): invisible collision skirts under the walkway tops of the backdrop canals.
  blender -b --factory-startup --disable-autoexec Naboo_Theed.blend --python backdrop_skirts.py -- <export_dir>
The source's backdrop canal pieces (NabooBackdropCanal_*) are shells: a flat walkway top, a quay wall and a fence.
Under the top lies an older, hidden copy of the river (water plane and rough terrain) that the source only closes to
the eye, so players and bots slip under the walkway and walk on that leftover ground. For every outer edge of the
upward faces of those objects this writes a vertical wall from the edge down to <depth> units under it, both faces
(so it blocks from either side). Nothing visible changes: the walls only go into the collision.
Writes <export_dir>/collision/skirts.npy (triangles, engine units) and skirts.json; write_collision_bsp.py adds them."""
import bpy, bmesh, sys, os, json
import numpy as np
from mathutils import Vector

ed = sys.argv[sys.argv.index("--") + 1]
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = Vector(cfg["origin_m"])
sk = cfg.get("backdrop_skirts", {})
pats = [p.lower() for p in sk.get("objects", ["naboobackdropcanal"])]
depth = float(sk.get("depth_units", 1600.0))
dg = bpy.context.evaluated_depsgraph_get()
tris = []; stats = {}
for ob in bpy.data.objects:
    if ob.type != "MESH" or not any(p in ob.name.lower() for p in pats):
        continue
    me = ob.evaluated_get(dg).to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); bm.transform(ob.matrix_world)
    bm.normal_update()
    up = {f for f in bm.faces if f.normal.z > 0.9}
    n = 0
    for e in bm.edges:
        lf = [f for f in e.link_faces if f in up]
        if len(lf) != 1:
            continue
        a = (e.verts[0].co - ORG) * UPM; b = (e.verts[1].co - ORG) * UPM
        if (a - b).length < 1.0:
            continue
        a2 = Vector((a.x, a.y, a.z - depth)); b2 = Vector((b.x, b.y, b.z - depth))
        for t in ((a, b, b2), (a, b2, a2), (b, a, a2), (b, a2, b2)):      # both faces
            tris.append([list(v) for v in t])
        n += 1
    stats[ob.name] = {"up_faces": len(up), "skirt_edges": n}
    bm.free(); ob.evaluated_get(dg).to_mesh_clear()
os.makedirs(os.path.join(ed, "collision"), exist_ok=True)
np.save(os.path.join(ed, "collision", "skirts.npy"), np.array(tris, np.float32).reshape(-1, 3, 3))
json.dump({"depth_units": depth, "objects": stats, "triangles": len(tris)}, open(os.path.join(ed, "collision", "skirts.json"), "w"), indent=1)
print("SKIRTS", json.dumps(stats), len(tris))
