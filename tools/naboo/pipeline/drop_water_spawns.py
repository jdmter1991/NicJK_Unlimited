"""Remove spawn points that stand over open water.
  py drop_water_spawns.py <export_dir> <mapname>
The export placed spawns on a grid at terrain level; with the source's exact terrain (no lowering under water) some
of them stand a little above a river or canal surface and players spawn straight into the water. A spawn goes when
its column is inside a water volume's footprint, it is less than `spawn_water_clearance_units` (200) above the
water surface, and there is no collision floor between the water surface and the spawn.
Edits naboo/q3base/base/maps/<mapname>.map (the previous file is kept as <mapname>_before_water_spawns.map);
run write_collision_bsp.py afterwards."""
import sys, os, re, json, shutil
import numpy as np

ed, mapname = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
CLEAR = float(cfg.get("spawn_water_clearance_units", 200.0))
mp = os.path.join(ROOT, "q3base", "base", "maps", mapname + ".map")
WB = np.load(os.path.join(ed, "collision", "water_boxes.npy")).astype(np.float64)
T = np.load(os.path.join(ed, "collision", "collision_tris.npy")).reshape(-1, 3, 3).astype(np.float64)
tmin = T.min(1); tmax = T.max(1)


def floor_between(x, y, z0, z1):
    sel = np.flatnonzero((tmin[:, 0] <= x) & (tmax[:, 0] >= x) & (tmin[:, 1] <= y) & (tmax[:, 1] >= y) & (tmax[:, 2] >= z0) & (tmin[:, 2] <= z1))
    for i in sel:
        a, b, c = T[i]; e1 = b - a; e2 = c - a
        det = e1[0] * e2[1] - e1[1] * e2[0]
        if abs(det) < 1e-9:
            continue
        u = ((x - a[0]) * e2[1] - (y - a[1]) * e2[0]) / det; v = ((y - a[1]) * e1[0] - (x - a[0]) * e1[1]) / det
        if u >= 0 and v >= 0 and u + v <= 1:
            z = a[2] + u * e1[2] + v * e2[2]
            if z0 < z < z1:
                return True
    return False


src = open(mp, encoding="utf-8", errors="replace").read()
out = []; pos = 0; dropped = []
for m in re.finditer(r"\{[^{}]*\}", src):
    body = m.group(0)
    if "info_player_deathmatch" in body or "info_player_start" in body:
        o = re.search(r'"origin"\s+"([^"]+)"', body)
        x, y, z = (float(v) for v in o.group(1).split())
        k = np.flatnonzero((WB[:, 0, 0] <= x) & (WB[:, 1, 0] >= x) & (WB[:, 0, 1] <= y) & (WB[:, 1, 1] >= y))
        if len(k):
            top = float(WB[k, 1, 2].max())
            if z - top < CLEAR and not floor_between(x, y, top - 8, z):
                out.append(src[pos:m.start()]); pos = m.end(); dropped.append([x, y, z, top])
                continue
out.append(src[pos:]); res = "".join(out)
if dropped:
    shutil.copyfile(mp, os.path.join(os.path.dirname(mp), mapname + "_before_water_spawns.map"))
    open(mp, "w", encoding="utf-8").write(res)
left = len(re.findall(r"info_player_(?:deathmatch|start)", res))
rep = {"dropped": len(dropped), "spawns_left": left, "positions": dropped}
json.dump(rep, open(os.path.join(ed, "collision", "water_spawns.json"), "w"), indent=1)
print(json.dumps({"dropped": len(dropped), "spawns_left": left}))
