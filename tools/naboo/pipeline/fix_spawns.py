"""Spawn points: lift the ones that stand under stairs or platforms, and add spawns around the palace forecourt.
  py fix_spawns.py <export_dir> <mapname> [forecourt_count]
The export placed spawns on a grid at terrain level. Where stairs, terraces or plazas were built over the terrain
such a spawn stands underneath them. For every outdoor spawn (not the palace-interior ones) this looks at the
collision triangles (<export_dir>/collision/collision_tris.npy) in the column through it:
  * nothing overhead within 3000 units: left alone;
  * otherwise it moves up to the first walkable surface above it that is open to the sky, flat for 36 units around
    and at most `max_rise` (240 units, 6 m) higher; if there is none (it stands inside a building) it is removed.
Then `forecourt_count` (default 24) new spawns are placed in the palace forecourt and the streets around it
(config "forecourt_box_units"), on open-sky, flat ground within 400 units of terrain height, not in water, spread
as far apart as possible, facing the palace entrance. They carry the key "naboo_forecourt" "1" and are replaced
on every run. Edits naboo/q3base/base/maps/<mapname>.map; run write_collision_bsp.py afterwards."""
import sys, os, json, re
import numpy as np

ed, mapname = sys.argv[1], sys.argv[2]
COUNT = int(sys.argv[3]) if len(sys.argv) > 3 else 24
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
BOX = cfg.get("forecourt_box_units", [-4200.0, 4600.0, 4900.0, 7750.0])
DOOR = np.array(cfg.get("palace_entrance_units", [362.0, 7788.0]))
MAX_RISE = float(cfg.get("spawn_max_rise_units", 240.0))
T = np.load(os.path.join(ed, "collision", "collision_tris.npy")).reshape(-1, 3, 3).astype(np.float64)
A = T[:, 0]; E1 = T[:, 1] - A; E2 = T[:, 2] - A
N = np.cross(E1, E2); l = np.linalg.norm(N, axis=1); ok = l > 1e-6
A = A[ok]; E1 = E1[ok]; E2 = E2[ok]; NZ = (N[ok] / l[ok, None])[:, 2]; T = T[ok]
CELL = 256.0
tmin = T.min(1); tmax = T.max(1)
small = ((tmax[:, 0] - tmin[:, 0]) < 4000) & ((tmax[:, 1] - tmin[:, 1]) < 4000)
buckets = {}
gx0 = np.floor(tmin[:, 0] / CELL).astype(np.int64); gx1 = np.floor(tmax[:, 0] / CELL).astype(np.int64)
gy0 = np.floor(tmin[:, 1] / CELL).astype(np.int64); gy1 = np.floor(tmax[:, 1] / CELL).astype(np.int64)
for i in np.flatnonzero(small):
    for gx in range(gx0[i], gx1[i] + 1):
        for gy in range(gy0[i], gy1[i] + 1):
            buckets.setdefault((gx, gy), []).append(i)
buckets = {k: np.array(v, np.int64) for k, v in buckets.items()}
big = np.flatnonzero(~small)


def hits(x, y):
    ix = buckets.get((int(np.floor(x / CELL)), int(np.floor(y / CELL))))
    ix = big if ix is None else np.concatenate([ix, big])
    a = A[ix]; e1 = E1[ix]; e2 = E2[ix]
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    good = np.abs(det) > 1e-9
    dx = x - a[:, 0]; dy = y - a[:, 1]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = (dx * e2[:, 1] - dy * e2[:, 0]) / det; v = (dy * e1[:, 0] - dx * e1[:, 1]) / det
        z = a[:, 2] + u * e1[:, 2] + v * e2[:, 2]
    inside = good & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
    return z[inside], NZ[ix][inside]


RING = [(0.0, 0.0)] + [(36.0 * np.cos(a_), 36.0 * np.sin(a_)) for a_ in np.arange(8) * np.pi / 4]
WB = np.load(os.path.join(ed, "collision", "water_boxes.npy")) if os.path.exists(os.path.join(ed, "collision", "water_boxes.npy")) else np.zeros((0, 2, 3))


def open_floor(x, y, zf):
    """flat walkable ground at height zf with nothing above it at all"""
    for ox, oy in RING:
        z, nz = hits(x + ox, y + oy)
        if not ((nz > 0.7) & (np.abs(z - zf) <= 8.0)).any() or (z > zf + 8.0).any():
            return False
    p = np.array([x, y, zf + 30.0])
    return not bool(len(WB) and (np.all(WB[:, 0] <= p, 1) & np.all(WB[:, 1] >= p, 1)).any())


mp = os.path.join(HERE, "..", "q3base", "base", "maps", mapname + ".map")
txt = open(mp).read()
txt = re.sub(r'\{\s*\n(?:"[^\n]*\n)*?"naboo_forecourt" "1"\n(?:"[^\n]*\n)*?\}\n', "", txt)
rep = {"outdoor_spawns": 0, "left_alone": 0, "lifted": [], "removed": []}


def fix(m):
    body = m.group(0)
    if '"classname" "info_player_' not in body or '"naboo_palace"' in body:
        return body
    o = re.search(r'"origin" "(-?[\d.]+) (-?[\d.]+) (-?[\d.]+)"', body)
    if not o:
        return body
    x, y, z0 = (float(v) for v in o.groups())
    rep["outdoor_spawns"] += 1
    z, nz = hits(x, y)
    if not (z > z0 + 40.0).any():
        rep["left_alone"] += 1
        return body
    for zf in sorted(z[(nz > 0.7) & (z > z0 + 8.0) & (z < z0 + MAX_RISE)]):
        if open_floor(x, y, zf):
            rep["lifted"].append([int(x), int(y), int(z0), int(zf) + 25])
            return body.replace(o.group(0), '"origin" "%d %d %d"' % (x, y, zf + 25))
    rep["removed"].append([int(x), int(y), int(z0)])
    return ""


txt = re.sub(r'\{\s*\n(?:"[^\n]*\n)+?\}\n', fix, txt)

# ---- forecourt spawns
g = np.load(os.path.join(ed, "dump", "extras", "terrain_near_carved.npz"))["grid"].astype(np.float64)
xs = g[0, :, 0]; ys = g[:, 0, 1]
cands = []
for x in np.arange(BOX[0], BOX[2], 150.0):
    for y in np.arange(BOX[1], BOX[3], 150.0):
        z, nz = hits(x, y)
        if len(z) == 0:
            continue
        zf = float(z.max())
        if not (nz[np.argmax(z)] > 0.7):
            continue
        tz = (g[np.clip(np.searchsorted(ys, y / UPM + ORG[1]), 0, len(ys) - 1), np.clip(np.searchsorted(xs, x / UPM + ORG[0]), 0, len(xs) - 1), 2] - ORG[2]) * UPM
        if abs(zf - tz) < 400.0 and open_floor(x, y, zf):
            cands.append((x, y, zf))
C = np.array(cands)
chosen = []
if len(C):
    sel = [int(np.argmin(np.linalg.norm(C[:, :2] - (DOOR + np.array([0.0, -900.0])), axis=1)))]
    d = np.linalg.norm(C[:, :2] - C[sel[0], :2], axis=1)
    while len(sel) < min(COUNT, len(C)):
        j = int(np.argmax(d))
        if d[j] < 250.0:
            break
        sel.append(j); d = np.minimum(d, np.linalg.norm(C[:, :2] - C[j, :2], axis=1))
    chosen = [C[j] for j in sel]
add = ""
for x, y, z in chosen:
    ang = int(round(np.degrees(np.arctan2(DOOR[1] - y, DOOR[0] - x))))
    add += '{\n"classname" "info_player_deathmatch"\n"origin" "%d %d %d"\n"angle" "%d"\n"naboo_forecourt" "1"\n}\n' % (round(x), round(y), round(z) + 25, ang if ang != 0 else 360)
# ---- spawns at the cafes: next to every group of outdoor chairs and tables (the user liked spawning there)
txt = re.sub(r'\{\s*\n(?:"[^\n]*\n)*?"naboo_cafe" "1"\n(?:"[^\n]*\n)*?\}\n', "", txt)
sc = json.load(open(os.path.join(ed, "dump", "scene.json")))
chairs = np.array([(np.array(it["matrix"])[:3, 3] - ORG) * UPM for it in sc["instances"] if it["mesh"].startswith(("chairoutdoor", "tableoutdoor"))])
cafes = []
if len(chairs):
    keys = {}
    for p in chairs:
        keys.setdefault((int(p[0] // 500), int(p[1] // 500), int(p[2] // 200)), []).append(p)
    for k, pts in sorted(keys.items(), key=lambda kv: -len(kv[1])):
        if len(pts) < 3 or len(cafes) >= int(cfg.get("cafe_spawns", 10)):
            continue
        cen = np.mean(pts, 0); best = None
        for ox in np.arange(-300.0, 301.0, 60.0):
            for oy in np.arange(-300.0, 301.0, 60.0):
                x, y = cen[0] + ox, cen[1] + oy
                if np.min(np.linalg.norm(chairs[:, :2] - (x, y), axis=1)) < 50.0:
                    continue                                       # not on top of the furniture
                z, nz = hits(x, y)
                for zf in z[(nz > 0.7) & (np.abs(z - cen[2]) < 60.0)]:
                    good = True
                    for rx, ry in RING:
                        z2, nz2 = hits(x + rx, y + ry)
                        if not ((nz2 > 0.7) & (np.abs(z2 - zf) <= 8.0)).any() or ((z2 > zf + 8.0) & (z2 < zf + 90.0)).any():
                            good = False; break
                    if good and (best is None or ox * ox + oy * oy < best[0]):
                        best = (ox * ox + oy * oy, x, y, float(zf))
        if best and all(np.hypot(best[1] - c_[0], best[2] - c_[1]) > 300.0 for c_ in cafes):
            cafes.append((best[1], best[2], best[3], cen))
for x, y, z, cen in cafes:
    ang = int(round(np.degrees(np.arctan2(cen[1] - y, cen[0] - x))))
    add += '{\n"classname" "info_player_deathmatch"\n"origin" "%d %d %d"\n"angle" "%d"\n"naboo_cafe" "1"\n}\n' % (round(x), round(y), round(z) + 25, ang if ang != 0 else 360)
rep["cafe_spawns"] = [[int(c_[0]), int(c_[1]), int(c_[2])] for c_ in cafes]; rep["chairs_and_tables"] = int(len(chairs))
open(mp, "w").write(txt.rstrip("\n") + "\n" + add)
rep["forecourt_candidates"] = len(C); rep["forecourt_added"] = [[int(v) for v in c_] for c_ in chosen]
rep["spawns_total"] = len(re.findall(r'"classname" "info_player_', txt + add))
json.dump(rep, open(os.path.join(ed, "spawn_fix.json"), "w"), indent=1)
print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in rep.items()}), "\nlifted:", rep["lifted"], "\nremoved:", rep["removed"])
