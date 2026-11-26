"""Spawn points inside the royal palace.
  py add_palace_spawns.py <export_dir> <mapname> [count]
The spawn grid of the export only looks near terrain level, so the palace interior (several storeys above it) got
none. This finds floor spots from the collision triangles (<export_dir>/collision/collision_tris.npy, engine units)
inside the bounds of the palace-interior meshes of dump/scene.json:
  * a near-level triangle under the spot, and the same floor height (within 6 units) at 8 points 36 units around
    it: flat, solid ground with room for the player box;
  * nothing between 6 and 260 units above the floor at any of the 9 points: room to stand, and not one of the low
    spaces under the flights of the stairs;
  * a ceiling somewhere above (indoors), found with a ray straight up.
From the spots that pass, `count` (default 14) are picked as far apart as possible, per storey in proportion to its
share of the spots. They are appended to naboo/q3base/base/maps/<mapname>.map as info_player_deathmatch entities
with the key "naboo_palace" "1" (earlier ones with that key are replaced), facing the direction in which one can
walk farthest.
Run write_collision_bsp.py afterwards to put them into the BSP."""
import sys, os, json, re, time
import numpy as np

t0 = time.time()
ed, mapname = sys.argv[1], sys.argv[2]
COUNT = int(sys.argv[3]) if len(sys.argv) > 3 else 14
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
sc = json.load(open(os.path.join(ed, "dump", "scene.json")))
pal = {k for k, v in sc["meshes"].items() if any(m and "PalaceInterio" in m for m in (v.get("materials") or []))}
P = np.array([(np.array(it["matrix"])[:3, 3] - ORG) * UPM for it in sc["instances"] if it.get("mesh") in pal])
lo = np.percentile(P, 1, axis=0) - 100.0; hi = np.percentile(P, 99, axis=0) + 100.0
print("palace bounds (units)", lo.round(0), hi.round(0))

T = np.load(os.path.join(ed, "collision", "collision_tris.npy")).reshape(-1, 3, 3).astype(np.float64)
tmin = T.min(1); tmax = T.max(1)
m = (tmax[:, 0] >= lo[0]) & (tmin[:, 0] <= hi[0]) & (tmax[:, 1] >= lo[1]) & (tmin[:, 1] <= hi[1]) & (tmax[:, 2] >= lo[2] - 200) & (tmin[:, 2] <= hi[2] + 3000)
T = T[m]; tmin = tmin[m]; tmax = tmax[m]
A = T[:, 0]; E1 = T[:, 1] - A; E2 = T[:, 2] - A
N = np.cross(E1, E2); area2 = np.linalg.norm(N, axis=1); ok = area2 > 1e-6
T = T[ok]; tmin = tmin[ok]; tmax = tmax[ok]; A = A[ok]; E1 = E1[ok]; E2 = E2[ok]; N = N[ok] / area2[ok, None]
print("collision triangles in the palace volume:", len(T))
# bucket triangles in a 128-unit xy grid
CELL = 128.0
gx0 = np.floor(tmin[:, 0] / CELL).astype(np.int64); gx1 = np.floor(tmax[:, 0] / CELL).astype(np.int64)
gy0 = np.floor(tmin[:, 1] / CELL).astype(np.int64); gy1 = np.floor(tmax[:, 1] / CELL).astype(np.int64)
buckets = {}
for i in range(len(T)):
    for gx in range(gx0[i], gx1[i] + 1):
        for gy in range(gy0[i], gy1[i] + 1):
            buckets.setdefault((gx, gy), []).append(i)
buckets = {k: np.array(v, np.int64) for k, v in buckets.items()}


def hits(x, y):
    """heights where the vertical line through (x, y) crosses a collision triangle, with the triangle's normal z"""
    ix = buckets.get((int(np.floor(x / CELL)), int(np.floor(y / CELL))))
    if ix is None:
        return np.zeros(0), np.zeros(0)
    a = A[ix]; e1 = E1[ix]; e2 = E2[ix]
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    good = np.abs(det) > 1e-9
    dx = x - a[:, 0]; dy = y - a[:, 1]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = (dx * e2[:, 1] - dy * e2[:, 0]) / det; v = (dy * e1[:, 0] - dx * e1[:, 1]) / det
    inside = good & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
    z = a[:, 2] + u * e1[:, 2] + v * e2[:, 2]
    return z[inside], N[ix][inside, 2]


ZMIN = float(cfg.get("palace_spawn_min_z_units", 280.0))      # below this lie the river-side arcades, not the palace floors


def walk_distance(x, y, zf, ang):
    """how far one can walk from the spot in a direction: steps of 32 units with a floor within 40 units of the
    spot's and nothing between 6 and 70 units above it"""
    dx, dy = np.cos(ang), np.sin(ang); zc = zf
    for k in range(1, 40):
        z2, nz2 = hits(x + dx * 32.0 * k, y + dy * 32.0 * k)
        fl = z2[(nz2 > 0.7) & (np.abs(z2 - zc) <= 40.0)]
        if len(fl) == 0:
            return 32.0 * (k - 1)
        zc = float(fl[np.argmin(np.abs(fl - zc))])
        if ((z2 > zc + 6.0) & (z2 < zc + 70.0)).any():
            return 32.0 * (k - 1)
    return 32.0 * 39


HEADROOM = float(cfg.get("palace_spawn_headroom_units", 260.0))      # 6.6 m: not in the low spaces under stair flights
RING = [(0.0, 0.0)] + [(36.0 * np.cos(a_), 36.0 * np.sin(a_)) for a_ in np.arange(8) * np.pi / 4]
WIDE = RING + [(120.0 * np.cos(a_), 120.0 * np.sin(a_)) for a_ in np.arange(8) * np.pi / 4]
cands = []
STEP = float(cfg.get("palace_spawn_step_units", 96.0))
for x in np.arange(lo[0], hi[0], STEP):
    for y in np.arange(lo[1], hi[1], STEP):
        z, nz = hits(x, y)
        if len(z) == 0:
            continue
        for zf in np.unique(np.round(z[(nz > 0.95) & (z >= ZMIN) & (z <= hi[2])], 0)):
            good = True; first_above = []
            for ox, oy in WIDE:
                z2, nz2 = hits(x + ox, y + oy)
                up = z2[z2 > zf + 6.0]
                first_above.append(float(up.min()) if len(up) else 1e9)
                if (ox, oy) in RING and (not ((nz2 > 0.95) & (np.abs(z2 - zf) <= 6.0)).any() or ((z2 > zf + 6.0) & (z2 < zf + HEADROOM)).any()):
                    good = False; break
            # a flight of stairs overhead shows as a ceiling whose height changes from point to point (the steps are
            # level pieces, so slope alone does not give it away): the nearest ceiling must be level within 20 units
            # over a circle of 120 units, unless it is more than 900 units up
            if good:
                fa = np.array(first_above)
                if fa.min() < zf + 900.0 and fa.max() - fa.min() > 20.0:
                    good = False
            if good and (z > zf + 80.0).any():                 # a ceiling above: indoors
                cands.append((x, y, zf))
C = np.array(cands)
print("floor spots that pass:", len(C), "  %.0f s" % (time.time() - t0))
if len(C) == 0:
    sys.exit("no spawn spots found")
# storeys: cluster floor heights in 60-unit bins
lev = np.round(C[:, 2] / 60.0).astype(np.int64)
levels, cnt = np.unique(lev, return_counts=True)
print("storeys (height, spots):", [(int(l * 60), int(c)) for l, c in zip(levels, cnt)])
centre = np.array([np.median(P[:, 0]), np.median(P[:, 1])])
chosen = []
share = np.maximum(1, np.round(COUNT * cnt / cnt.sum())).astype(int)
for l, k in zip(levels, share):
    S = C[lev == l]
    # farthest-point sampling, starting from the spot nearest the storey's centroid
    sel = [int(np.argmin(np.linalg.norm(S[:, :2] - S[:, :2].mean(0), axis=1)))]
    d = np.linalg.norm(S[:, :2] - S[sel[0], :2], axis=1)
    while len(sel) < min(k, len(S)):
        j = int(np.argmax(d))
        if d[j] < 200.0:
            break
        sel.append(j); d = np.minimum(d, np.linalg.norm(S[:, :2] - S[j, :2], axis=1))
    chosen += [S[j] for j in sel]
chosen = np.array(chosen)[:max(COUNT, 1) + 4]
mp = os.path.join(HERE, "..", "q3base", "base", "maps", mapname + ".map")
txt = open(mp).read()
txt = re.sub(r'\{\s*\n(?:"[^\n]*\n)*?"naboo_palace" "1"\n(?:"[^\n]*\n)*?\}\n', "", txt)
add = ""
for x, y, z in chosen:
    # face the direction with the longest walkable stretch (16 directions)
    best_ = max(((walk_distance(x, y, z, a_), -abs(np.arctan2(np.sin(a_ - np.arctan2(centre[1] - y, centre[0] - x)), np.cos(a_ - np.arctan2(centre[1] - y, centre[0] - x)))), a_) for a_ in np.arange(16) * np.pi / 8))
    ang = int(round(np.degrees(best_[2])))
    add += '{\n"classname" "info_player_deathmatch"\n"origin" "%d %d %d"\n"angle" "%d"\n"naboo_palace" "1"\n}\n' % (round(x), round(y), round(z) + 25, ang)
open(mp, "w").write(txt.rstrip("\n") + "\n" + add)
json.dump({"spots": len(C), "storeys": [(int(l * 60), int(c)) for l, c in zip(levels, cnt)], "spawns": [[int(round(v)) for v in c_] for c_ in chosen.tolist()]},
          open(os.path.join(ed, "palace_spawns.json"), "w"), indent=1)
print("added", len(chosen), "palace spawns:", [[int(round(v)) for v in c_] for c_ in chosen.tolist()])
