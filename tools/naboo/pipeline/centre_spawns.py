"""Move spawn points from the plain outskirts of the map into the detailed city.
  py centre_spawns.py <export_dir> <mapname> <objects.json> <routes.wnt>
objects.json: [name, x, y, z, radius, faces] per mesh object of the source in engine units (Blender listing).
The outskirts of the source are dressed with backdrop pieces (O_NAB_BackdropBuildings, backdrop trees and cliffs)
that are made to be seen from afar. A spawn goes when
  * fewer than `min_detail` (60) detailed objects (not backdrop, terrain, sky, water, lights or effects) stand
    within 1500 units of it, or
  * a backdrop object stands within `min_backdrop` (600) units, or
  * it is more than `max_radius` (13000) units from the centre of the detailed objects, or
  * it is more than `max_route_distance` (300) units from every bot route point (fenced terraces, closed yards).
The same number of spawns is added back on bot route points (walkable, dry, connected; tools/make_bot_routes.py)
with at least `new_min_detail` (200) detailed objects around them, within `new_radius` (9000) units of the centre,
open to the sky, at least 700 units from every spawn, spread as far apart as possible, facing the centre.
New spawns carry "naboo_centre" "1" and are replaced on every run. Edits naboo/q3base/base/maps/<mapname>.map
(previous version kept as <mapname>_before_centre_spawns.map); run write_collision_bsp.py afterwards."""
import sys, os, re, json, shutil
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import avoid_zones

ed, mapname, objs_path, wnt = sys.argv[1:5]
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8")).get("centre_spawns", {})
MIN_DETAIL = cfg.get("min_detail", 60); MIN_BD = cfg.get("min_backdrop", 600.0); MAX_R = cfg.get("max_radius", 13000.0)
NEW_DETAIL = cfg.get("new_min_detail", 200); NEW_R = cfg.get("new_radius", 9000.0); SEP = cfg.get("min_separation", 700.0)
O = json.load(open(objs_path))
bd = np.array([o[1:4] for o in O if re.search("backdrop|terrain_far", o[0].lower()) and "smoke" not in o[0].lower()])
det = np.array([o[1:4] for o in O if not re.search("backdrop|terrain|far|sky|water|invalidate|light|fx_", o[0].lower()) and o[4] < 3000])
CEN = np.median(det[:, :2], 0)


def detail(P):
    return np.array([(np.hypot(det[:, 0] - p[0], det[:, 1] - p[1]) < 1500).sum() for p in P])


def bd_dist(P):
    return np.array([np.hypot(bd[:, 0] - p[0], bd[:, 1] - p[1]).min() for p in P])


# spawns must be within reach of the bot routes: a spawn in a fenced terrace or a closed courtyard traps bots
WALL = np.array([[float(v) for v in re.search(r"\(([^)]+)\)", l).group(1).split()] for l in open(wnt)])
MAX_ROUTE = float(cfg.get("max_route_distance", 300.0))
mp = os.path.join(ROOT, "q3base", "base", "maps", mapname + ".map")
src = open(mp, encoding="utf-8", errors="replace").read()
blocks = list(re.finditer(r"\{[^{}]*\}", src))
keep_txt = []; pos = 0; kept = []; dropped = []
for m in blocks:
    b = m.group(0)
    if "info_player_deathmatch" not in b:
        continue
    o = np.array([float(v) for v in re.search(r'"origin"\s+"([^"]+)"', b).group(1).split()])
    if '"naboo_centre"' in b:
        keep_txt.append(src[pos:m.start()]); pos = m.end(); continue          # replaced below
    d = detail([o])[0]; bdd = bd_dist([o])[0]; r = np.hypot(*(o[:2] - CEN))
    rd = float(np.linalg.norm(WALL[:, :3] - (o + [0, 0, 24]), axis=1).min())      # nearest bot route point
    if d < MIN_DETAIL or bdd < MIN_BD or r > MAX_R or rd > MAX_ROUTE or avoid_zones.avoided([o[0]], [o[1]], [o[2]])[0]:
        keep_txt.append(src[pos:m.start()]); pos = m.end(); dropped.append(o.tolist() + [int(d), round(float(bdd)), round(float(r))])
    else:
        kept.append(o)
keep_txt.append(src[pos:]); res = "".join(keep_txt)
kept = np.array(kept)
need = len(dropped) + sum(1 for m in blocks if '"naboo_centre"' in m.group(0))

# candidates: bot route points, open to the sky (no collision over them)
W = np.unique(np.array([[float(v) for v in re.search(r"\(([^)]+)\)", l).group(1).split()] for l in open(wnt)]), axis=0)
W = W[np.hypot(W[:, 0] - CEN[0], W[:, 1] - CEN[1]) < NEW_R]
W = W[detail(W) >= NEW_DETAIL]
W = W[~avoid_zones.avoided(W[:, 0], W[:, 1], W[:, 2] - 24.0)]
# near the ground only: route points on roofs (reached by force jumps) are no place to spawn
_tz, _, _ = avoid_zones.terrain_z(W[:, 0], W[:, 1])
W = W[(W[:, 2] - 24.0 - _tz) < float(cfg.get("max_height_above_ground", 400.0))]
T = np.load(os.path.join(ed, "collision", "collision_tris.npy")).reshape(-1, 3, 3).astype(np.float64)
tmin = T.min(1); tmax = T.max(1)
sel = np.flatnonzero(tmax[:, 2] > W[:, 2].min())
T = T[sel]; tmin = tmin[sel]; tmax = tmax[sel]
open_sky = np.ones(len(W), bool)
for k, (x, y, z) in enumerate(W):
    c = np.flatnonzero((tmin[:, 0] <= x) & (tmax[:, 0] >= x) & (tmin[:, 1] <= y) & (tmax[:, 1] >= y) & (tmax[:, 2] > z + 40))
    for i in c:
        a, b, cc = T[i]; e1 = b - a; e2 = cc - a; det_ = e1[0] * e2[1] - e1[1] * e2[0]
        if abs(det_) < 1e-9:
            continue
        u = ((x - a[0]) * e2[1] - (y - a[1]) * e2[0]) / det_; v = ((y - a[1]) * e1[0] - (x - a[0]) * e1[1]) / det_
        if u >= 0 and v >= 0 and u + v <= 1 and a[2] + u * e1[2] + v * e2[2] > z + 40:
            open_sky[k] = False; break
W = W[open_sky]
added = []
cur = kept[:, :2].copy() if len(kept) else np.zeros((0, 2))
for _ in range(need):
    if not len(W):
        break
    dmin = np.full(len(W), 1e9) if not len(cur) else np.hypot(W[:, None, 0] - cur[None, :, 0], W[:, None, 1] - cur[None, :, 1]).min(1)
    k = int(np.argmax(dmin))
    if dmin[k] < SEP:
        break
    added.append(W[k]); cur = np.vstack([cur, W[k][:2]]); W = np.delete(W, k, 0)
ents = []
for p in added:
    yaw = np.degrees(np.arctan2(CEN[1] - p[1], CEN[0] - p[0]))
    ents.append('{\n"classname" "info_player_deathmatch"\n"origin" "%.0f %.0f %.0f"\n"angle" "%.0f"\n"naboo_centre" "1"\n}\n' % (p[0], p[1], p[2], yaw))
res = res.rstrip("\n") + "\n" + "".join(ents)
shutil.copyfile(mp, os.path.join(os.path.dirname(mp), mapname + "_before_centre_spawns.map"))
open(mp, "w", encoding="utf-8").write(res)
rep = {"centre": CEN.round().tolist(), "dropped": len(dropped), "added": len(added), "kept": len(kept),
       "spawns": len(re.findall(r"info_player_deathmatch", res)), "open_sky_candidates": int(open_sky.sum()), "dropped_positions": dropped}
json.dump(rep, open(os.path.join(ed, "collision", "centre_spawns.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in rep.items() if k != "dropped_positions"}))
