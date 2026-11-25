"""Rebuild the terrain part of the collision triangles from the terrain as it is drawn, and write water volumes.
  py build_collision_terrain.py <export_dir> <region>
Reads  <export_dir>/collision/collision_tris.npy          (engine units; objects + the old 2 m terrain)
       <export_dir>/dump/meshes/terrain_grid.npz          the source terrain grid (1 m), to recognise old terrain triangles
       <export_dir>/dump/extras/terrain_near_carved.npz   the terrain as drawn: carved under visible water (cook_v1.py)
       <export_dir>/dump/extras/water_final.npz           water surface raster, 2 m (cook_v1.py)
Writes <export_dir>/collision/collision_tris.npy          objects + new terrain   (the previous file is kept as *_v1.npy)
       <export_dir>/collision/water_boxes.npy             (n, 2, 3) mins / maxs of water volumes, engine units
       <export_dir>/collision/terrain_rebuild.json

Terrain: 2 m blocks where the 1 m heights lie within `tolerance` of the block's two triangles, 1 m cells elsewhere
(steps, kerbs, river banks). The drawn terrain has 1 m cells everywhere; at 2 m everywhere the collision stuck out
from under fences and walls by up to a metre, at 1 m everywhere it would have four times the triangles.

Water: a volume under every water cell whose surface is above the carved terrain, from `water_depth_m` below the
surface up to the surface, merged along rows.
"""
import sys, os, json, time
import numpy as np

t0 = time.time()
ed, region = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
rc = cfg["regions"][region]
B = rc["collision_bounds_m"]
cc = cfg.get("collision_terrain", {})
TOL = float(cc.get("tolerance_m", 0.05)); WDEPTH = float(cc.get("water_depth_m", 12.0))
cdir = os.path.join(ed, "collision")
src = os.path.join(cdir, "collision_tris_v1.npy")
if not os.path.exists(src):
    os.replace(os.path.join(cdir, "collision_tris.npy"), src)
tris = np.load(src)
g0 = np.load(os.path.join(ed, "dump", "meshes", "terrain_grid.npz"))["grid"].astype(np.float64)
g = np.load(os.path.join(ed, "dump", "extras", "terrain_near_carved.npz"))["grid"].astype(np.float64)
xs = g0[0, :, 0]; ys = g0[:, 0, 1]; dx = xs[1] - xs[0]; dy = ys[1] - ys[0]

# ---- drop the old terrain triangles: all three corners sit on grid points at the grid's height
P = tris.reshape(-1, 3).astype(np.float64) / UPM + ORG
ix = np.rint((P[:, 0] - xs[0]) / dx).astype(np.int64); iy = np.rint((P[:, 1] - ys[0]) / dy).astype(np.int64)
ok = (ix >= 0) & (ix < len(xs)) & (iy >= 0) & (iy < len(ys))
on = np.zeros(len(P), bool)
on[ok] = (np.abs(P[ok, 0] - xs[ix[ok]]) < 0.02) & (np.abs(P[ok, 1] - ys[iy[ok]]) < 0.02) & (np.abs(P[ok, 2] - g0[iy[ok], ix[ok], 2]) < 0.03)
is_terr = on.reshape(-1, 3).all(1)
objects = tris[~is_terr]
print("triangles in %d: old terrain %d, objects %d" % (len(tris), int(is_terr.sum()), len(objects)))

# ---- new terrain inside the collision bounds (+2 m), from the carved grid
i0 = max(int(np.searchsorted(xs, B[0] - 2.0)) // 2 * 2, 0); i1 = min(int(np.searchsorted(xs, B[2] + 2.0)) // 2 * 2 + 2, (len(xs) - 1) // 2 * 2)
j0 = max(int(np.searchsorted(ys, B[1] - 2.0)) // 2 * 2, 0); j1 = min(int(np.searchsorted(ys, B[3] + 2.0)) // 2 * 2 + 2, (len(ys) - 1) // 2 * 2)
Z = g[j0:j1 + 1, i0:i1 + 1, 2]; X = g[j0:j1 + 1, i0:i1 + 1, 0]; Y = g[j0:j1 + 1, i0:i1 + 1, 1]
c00 = Z[0:-2:2, 0:-2:2]; c10 = Z[0:-2:2, 2::2]; c01 = Z[2::2, 0:-2:2]; c11 = Z[2::2, 2::2]
mid_b = Z[0:-2:2, 1:-1:2]; mid_t = Z[2::2, 1:-1:2]; mid_l = Z[1:-1:2, 0:-2:2]; mid_r = Z[1:-1:2, 2::2]; mid_c = Z[1:-1:2, 1:-1:2]
dev = np.maximum.reduce([np.abs(mid_b - (c00 + c10) / 2), np.abs(mid_t - (c01 + c11) / 2), np.abs(mid_l - (c00 + c01) / 2), np.abs(mid_r - (c10 + c11) / 2),
                         np.abs(mid_c - (c00 + c11) / 2)])          # the block's diagonal runs from corner 00 to corner 11
fine = dev > TOL
nby, nbx = fine.shape


def quad_tris(jj, ii, step):
    """two triangles per cell, corners (j, i), (j, i+step), (j+step, i+step), (j+step, i); front faces up"""
    def v(j_, i_):
        return np.stack([X[j_, i_], Y[j_, i_], Z[j_, i_]], -1)
    a = v(jj, ii); b = v(jj, ii + step); c = v(jj + step, ii + step); d = v(jj + step, ii)
    return np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])


bj, bi = np.nonzero(~fine)
coarse = quad_tris(bj * 2, bi * 2, 2)
fj, fi = np.nonzero(fine)
parts = [coarse]
for oj in (0, 1):
    for oi in (0, 1):
        parts.append(quad_tris(fj * 2 + oj, fi * 2 + oi, 1))
terr_m = np.concatenate(parts)
n = np.cross(terr_m[:, 1] - terr_m[:, 0], terr_m[:, 2] - terr_m[:, 0])
if (n[:, 2] < 0).mean() > 0.5:
    terr_m = terr_m[:, ::-1]
terr = ((terr_m - ORG) * UPM).astype(np.float32)
out = np.concatenate([objects.astype(np.float32), terr])
np.save(os.path.join(cdir, "collision_tris.npy"), out)

# ---- water volumes
boxes = []
wf = os.path.join(ed, "dump", "extras", "water_final.npz")
n_cells = 0
if os.path.exists(wf):
    w = np.load(wf); wr = w["water"].astype(np.float64); wx0, wy0, wc = float(w["x0"]), float(w["y0"]), float(w["cell"])
    H, W = wr.shape
    cx = wx0 + np.arange(W) * wc; cy = wy0 + np.arange(H) * wc
    inb = ((cy >= B[1]) & (cy <= B[3]))[:, None] & ((cx >= B[0]) & (cx <= B[2]))[None, :]
    # carved terrain height at the cell centres (nearest grid point)
    gi = np.clip(np.rint((cx - xs[0]) / dx).astype(np.int64), 0, len(xs) - 1); gj = np.clip(np.rint((cy - ys[0]) / dy).astype(np.int64), 0, len(ys) - 1)
    tz = g[np.ix_(gj, gi)][:, :, 2]
    wet = inb & ~np.isnan(wr) & (np.nan_to_num(wr, nan=-1e9) - tz > 0.05)
    n_cells = int(wet.sum())
    zq = np.round(np.nan_to_num(wr, nan=0.0) * 50.0)           # runs must share the surface height to 2 cm
    for j in np.flatnonzero(wet.any(1)):
        row = wet[j]; ii = np.flatnonzero(row)
        cuts = np.flatnonzero((np.diff(ii) > 1) | (np.diff(zq[j, ii]) != 0)) + 1
        for run in np.split(ii, cuts):
            a, b = int(run[0]), int(run[-1]); zw = float(wr[j, a])
            mn = np.array([cx[a] - wc / 2, cy[j] - wc / 2, zw - WDEPTH]); mx = np.array([cx[b] + wc / 2, cy[j] + wc / 2, zw])
            boxes.append([(mn - ORG) * UPM, (mx - ORG) * UPM])
boxes = np.array(boxes, np.float32).reshape(-1, 2, 3)
np.save(os.path.join(cdir, "water_boxes.npy"), boxes)
rep = {"seconds": round(time.time() - t0, 1), "old_terrain_tris": int(is_terr.sum()), "object_tris": int(len(objects)), "blocks_2m": int((~fine).sum()),
       "blocks_1m": int(fine.sum()), "new_terrain_tris": int(len(terr)), "total_tris": int(len(out)), "tolerance_m": TOL,
       "carved_below_source_vertices": int((g[j0:j1 + 1, i0:i1 + 1, 2] < g0[j0:j1 + 1, i0:i1 + 1, 2] - 0.01).sum()),
       "water_cells": n_cells, "water_boxes": int(len(boxes)), "water_depth_m": WDEPTH}
json.dump(rep, open(os.path.join(cdir, "terrain_rebuild.json"), "w"), indent=1)
print(json.dumps(rep, indent=1))
