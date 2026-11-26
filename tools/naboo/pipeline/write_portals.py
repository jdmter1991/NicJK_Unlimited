"""Write maps/<name>.tportal: the palace interior box and the openings out of it (the entrance door).
  py write_portals.py <export_dir> <game_dir> <mapname>
Inside the box the renderer draws outside placements only when they are seen through an opening. The box starts
just inside the entrance door, so a camera on the steps outside is never "inside". Openings come from the door
leaves of doors.json that lie on the box's boundary (tools/build_doors.py), grown by 24 units.
File: "TPRT", version 1, count, box mins and maxs (6 floats), then per opening 6 floats: plane axis (0 = x,
1 = y), plane position, centre along the other horizontal axis, centre z, half width, half height."""
import sys, os, json, struct
import numpy as np
ed, game, name = sys.argv[1:4]
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
B = cfg.get("palace_interior_box_units", [-2600.0, 7800.0, 250.0, 3300.0, 13850.0, 1400.0])
doors = json.load(open(os.path.join(ed, "doors.json")))["doors"]
ent = [d for d in doors if abs(d["origin"][1] - B[1]) < 60.0]            # leaves in the front wall
out = []
if ent:
    o = np.array([d["origin"] for d in ent]); hx = max(np.array(d["hi"])[1] for d in ent); hz = max(np.array(d["hi"])[2] for d in ent)
    x0 = o[:, 0].min() - hx; x1 = o[:, 0].max() + hx
    out.append((1.0, float(o[:, 1].mean()), float((x0 + x1) / 2), float(o[:, 2].mean()), float((x1 - x0) / 2 + 24.0), float(hz + 24.0)))
# open doorways without a leaf in the outer front wall (door frames of dump/scene.json in front of the box)
sc = json.load(open(os.path.join(ed, "dump", "scene.json")))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
for it in sc["instances"]:
    if it["mesh"] in cfg.get("portal_frame_meshes", ["o_nab_doorpalaceframe_01_mesh"]):
        p = (np.array(it["matrix"])[:3, 3] - ORG) * UPM
        if B[0] < p[0] < B[3] and B[1] - 400.0 < p[1] < B[1] + 100.0:
            out.append((1.0, float(p[1]), float(p[0]), float(p[2] + 114.0), 140.0, 180.0))
# window panes: every placement inside the box with a glass material is an opening of its own size
mats = json.load(open(os.path.join(ed, "dump", "materials.json"), encoding="utf-8")); mats = mats.get("materials", mats)
n_win = 0
for it in (sc["instances"] if cfg.get("window_portals", False) else []):      # off: outward panes are opaque daylight again
    me = sc["meshes"][it["mesh"]]
    slots = [i for i, m in enumerate(me.get("materials") or []) if m and mats.get(m, {}).get("builder") == "glass"]
    if not slots:
        continue
    M = np.array(it["matrix"], np.float64); p = (M[:3, 3] - ORG) * UPM
    if not (B[0] - 100 < p[0] < B[3] + 100 and B[1] - 100 < p[1] < B[4] + 100 and B[2] < p[2] < B[5]):
        continue
    a_ = np.load(os.path.join(ed, "dump", "meshes", me["file"]))
    tl = a_["tri_loops"][np.isin(a_["tri_mat"].astype(np.int64), slots)]
    if len(tl) == 0:
        continue
    P = (a_["pos"][a_["loop_vert"][tl.ravel()]].astype(np.float64) * UPM) @ M[:3, :3].T + p
    lo = P.min(0); hi = P.max(0); ext = hi - lo
    ax = 0 if ext[0] < ext[1] else 1                       # the pane's plane: the thin horizontal axis
    if ext[ax] > 60.0 or ext[2] < 30.0 or len(out) >= 250:
        continue                                           # not a flat upright pane (chandelier glass and the like)
    ox = 1 - ax
    out.append((float(ax), float((lo[ax] + hi[ax]) / 2), float((lo[ox] + hi[ox]) / 2), float((lo[2] + hi[2]) / 2), float(ext[ox] / 2 + 8.0), float(min(ext[2] / 2 + 8.0, 149.0))))
    n_win += 1
print("window openings:", n_win)
open(os.path.join(game, "maps", name + ".tportal"), "wb").write(struct.pack("<4sII6f", b"TPRT", 1, len(out), *B) + b"".join(struct.pack("<6f", *p) for p in out))
print("interior box", B, "openings", len(out))
