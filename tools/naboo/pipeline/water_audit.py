"""Water audit: every water object of the source against the cooked world.
  py water_audit.py <export_dir> <game_dir>/taystjk|nicjk <mapname>
Source side: <export_dir>/water_inspect.json (tools/water_inspect.py): objects with a water, fountain or waterfall
material, their bounds and whether they are visible in the source.
Port side: placements of the cooked world whose mesh has a submesh with an animated water (type 1) or foam
(type 4) material, and the final water grid of the cook (dump/extras/water_final.npz).
For each source object: is there a water / foam placement inside its bounds (grown by 40 units)? For the river
object: how much of its surface that lies above the source terrain is in the port's water grid.
Writes <export_dir>/water_audit.json and prints one line per object."""
import sys, os, json, struct
import numpy as np

ed, game, mapname = sys.argv[1:4]
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
W = ("Theed_Water", "blinn3|SS_FountainTheed_Wat", "lambert8|SS_FountainTheed_Wat", "lambert9|SS_FountainTheed_Wat", "lambert2|SS_MeshP_Water_Thres",
     "waterfall|SS_Naboo_Waterfalls_", "lambert4|SS_FountainTheed_Fal")
src = json.load(open(os.path.join(ed, "water_inspect.json")))["objects"]

w = np.memmap(os.path.join(game, "maps", mapname + ".tworld"), dtype=np.uint8, mode="r")
magic, ver, nmat, nmesh, nsub, ninst, nvert, nidx = struct.unpack_from("<4sIIIIIII", w, 0); o = 112
mats = np.frombuffer(w, dtype=[("shader", "S64"), ("tint", "<f4", 3), ("flags", "<u4")], count=nmat, offset=o); o += nmat * 80
meshes = np.frombuffer(w, dtype=[("fv", "<u4"), ("nv", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("nl", "<u4"), ("lfs", "<u4", 3), ("lns", "<u4", 3), ("c", "<f4", 3), ("r", "<f4")], count=nmesh, offset=o); o += nmesh * 60
subs = np.frombuffer(w, dtype=[("mat", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("res", "<u4")], count=nsub, offset=o); o += nsub * 16
insts = np.frombuffer(w, dtype=[("mesh", "<u4"), ("m", "<f4", 12), ("c", "<f4", 3), ("r", "<f4")], count=ninst, offset=o)
anim = (mats["flags"] >> 1) & 7
kind = np.zeros(nmesh, np.int64)                 # bit 0: water, bit 1: foam
tris = np.zeros((nmesh, 2), np.int64)
for mi, me in enumerate(meshes):
    for s in range(int(me["lfs"][0]), int(me["lfs"][0]) + int(me["lns"][0])):
        a = int(anim[subs[s]["mat"]])
        if a == 1:
            kind[mi] |= 1; tris[mi, 0] += int(subs[s]["ni"]) // 3
        elif a == 4:
            kind[mi] |= 2; tris[mi, 1] += int(subs[s]["ni"]) // 3
wi = np.flatnonzero(kind[insts["mesh"]] != 0)
wc = insts["c"][wi].astype(np.float64); wk = kind[insts["mesh"][wi]]; wt = tris[insts["mesh"][wi]]
print("port: %d placements with a water or foam material (%d water, %d foam)" % (len(wi), int((wk & 1 > 0).sum()), int((wk & 2 > 0).sum())))

rows = []
for ob in src:
    wm = [m for m in ob["materials"] if m and m.startswith(W)]
    if not wm:
        continue
    lo = (np.array(ob["min"]) - ORG) * UPM - 40.0; hi = (np.array(ob["max"]) - ORG) * UPM + 40.0
    inside = ((wc >= lo) & (wc <= hi)).all(1)
    want_w = any(not m.startswith(("lambert4", "waterfall")) for m in wm); want_f = any(m.startswith(("lambert4", "waterfall")) for m in wm)
    got_w = bool((inside & (wk & 1 > 0)).any()); got_f = bool((inside & (wk & 2 > 0)).any())
    big = float(np.max(hi - lo)) > 20000
    status = "not visible in the source" if not ob["visible"] else ("river object, see grid" if big else ("ok" if (got_w or not want_w) and (got_f or not want_f) else "MISSING " + " ".join(x for x, g_, wn in (("water", got_w, want_w), ("foam", got_f, want_f)) if wn and not g_)))
    rows.append({"object": ob["name"], "visible": ob["visible"], "centre_units": [int(v) for v in ((lo + hi) / 2)], "wants": [k for k, v in (("water", want_w), ("foam", want_f)) if v],
                 "placements_inside": int(inside.sum()), "water_tris": int(wt[inside, 0].sum()), "foam_tris": int(wt[inside, 1].sum()), "status": status})
for r in rows:
    print("%-36s %-28s placements %d water tris %d foam tris %d  at %s" % (r["object"][:36], r["status"], r["placements_inside"], r["water_tris"], r["foam_tris"], r["centre_units"]))

# river: the port's water grid against the source's terrain
rep = {"objects": rows, "missing": [r["object"] for r in rows if r["status"].startswith("MISSING")]}
wf = os.path.join(ed, "dump", "extras", "water_final.npz"); tg = os.path.join(ed, "dump", "meshes", "terrain_grid.npz")
if os.path.exists(wf) and os.path.exists(tg):
    g = np.load(wf); Wg = g["water"]; x0 = float(g["x0"]); y0 = float(g["y0"]); c = float(g["cell"]); fill = g["fill"]
    T = np.load(tg)["grid"]; xs = T[0, :, 0]; ys = T[:, 0, 1]
    jj, ii = np.nonzero(~np.isnan(Wg)); X = x0 + ii * c; Y = y0 + jj * c
    inb = (X > xs[0]) & (X < xs[-1]) & (Y > ys[0]) & (Y < ys[-1])
    ix = np.clip(np.searchsorted(xs, X[inb]), 0, len(xs) - 1); iy = np.clip(np.searchsorted(ys, Y[inb]), 0, len(ys) - 1)
    tz = T[iy, ix, 2]; wz = Wg[jj[inb], ii[inb]]; fl = fill[jj[inb], ii[inb]]
    above = wz - tz > -0.3
    rep["river_grid_inside_near_terrain"] = {"cells_2m": int(inb.sum()), "source_water_at_or_above_source_terrain": int((above & ~fl).sum()), "source_water_under_source_terrain_hidden_in_both": int((~above & ~fl).sum()),
                                             "cells_added_by_the_port_to_close_gaps": int(fl.sum()), "area_visible_m2": float((above | fl).sum() * c * c)}
    print("river grid inside the near terrain:", rep["river_grid_inside_near_terrain"])
json.dump(rep, open(os.path.join(ed, "water_audit.json"), "w"), indent=1)
print("missing:", rep["missing"])
