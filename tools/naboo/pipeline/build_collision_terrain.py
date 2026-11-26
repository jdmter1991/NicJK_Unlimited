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
# the export (export_region.py) writes collision_tris.npy together with collision_stats.json; this step overwrites
# collision_tris.npy with its result. A stats file newer than the kept copy means a new export: take it as the source
_stats = os.path.join(cdir, "collision_stats.json")
if not os.path.exists(src) or (os.path.exists(_stats) and os.path.getmtime(_stats) > os.path.getmtime(src)):
    os.replace(os.path.join(cdir, "collision_tris.npy"), src)
tris = np.load(src)
g0 = np.load(os.path.join(ed, "dump", "meshes", "terrain_grid.npz"))["grid"].astype(np.float64)
g = np.load(os.path.join(ed, "dump", "extras", "terrain_near_carved.npz"))["grid"].astype(np.float64)
xs = g0[0, :, 0]; ys = g0[:, 0, 1]; dx = xs[1] - xs[0]; dy = ys[1] - ys[0]

# ---- a floor under deep water. In places the source terrain lies tens of metres under the water plane (the source
# only ever shows the surface). A player sank through the 12 m water volume there, fell onto ground far below the
# city and came up through walls. The collision bed is therefore never deeper than `max_water_depth_m` below the
# water surface (the drawn terrain is not changed; the water is opaque).
MAXD = float(cc.get("max_water_depth_m", 3.0))
floor_info = {}
_wf0 = os.path.join(ed, "dump", "extras", "water_final.npz")
if os.path.exists(_wf0):
    _w0 = np.load(_wf0); _wr0 = _w0["water"].astype(np.float64); _fx0, _fy0, _fc = float(_w0["x0"]), float(_w0["y0"]), float(_w0["cell"])
    _l0 = np.where(np.isnan(_wr0), -1e9, _wr0); _dl = _l0.copy()
    for _dj in range(-2, 3):
        for _di in range(-2, 3):
            _dl = np.maximum(_dl, np.roll(np.roll(_l0, _dj, 0), _di, 1))
    _gi = np.clip(np.rint((g[:, :, 0] - _fx0) / _fc).astype(np.int64), 0, _wr0.shape[1] - 1); _gj = np.clip(np.rint((g[:, :, 1] - _fy0) / _fc).astype(np.int64), 0, _wr0.shape[0] - 1)
    _wl = _dl[_gj, _gi]
    _raise = (_wl > -1e8) & (g[:, :, 2] < _wl - MAXD)
    floor_info = {"max_water_depth_m": MAXD, "terrain_vertices_raised": int(_raise.sum()), "area_m2": float(_raise.sum() * dx * dy),
                  "deepest_before_m": round(float((_wl - g[:, :, 2])[_raise].max()), 1) if _raise.any() else 0.0}
    g[:, :, 2][_raise] = (_wl - MAXD)[_raise]
    print("floor under deep water:", floor_info)

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
# ---- skirts under walls that stood on terrain which is now carved river bed.
# Carving lowers the ground under visible water by up to a metre; walls, quays and steps whose lowest edge sat on
# the old ground then hang above the new one, and a swimmer passes underneath them (seen in game: a bot came out
# of the water through a canal wall). Every steep object triangle whose two lowest corners were at the old ground
# gets a wall from that edge down to 0.4 m below the carved ground.
def ground(grid, xm, ym):
    fx = np.clip((xm - xs[0]) / dx, 0, len(xs) - 1.001); fy = np.clip((ym - ys[0]) / dy, 0, len(ys) - 1.001)
    i_ = fx.astype(np.int64); j_ = fy.astype(np.int64); u = fx - i_; v = fy - j_
    z = grid[:, :, 2]
    return z[j_, i_] * (1 - u) * (1 - v) + z[j_, i_ + 1] * u * (1 - v) + z[j_ + 1, i_] * (1 - u) * v + z[j_ + 1, i_ + 1] * u * v


T = objects.reshape(-1, 3, 3).astype(np.float64) / UPM + ORG               # metres
nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); nl = np.linalg.norm(nrm, axis=1)
steep = (nl > 1e-9) & (np.abs(nrm[:, 2]) < 0.5 * np.maximum(nl, 1e-12))
inb = (T[:, :, 0].min(1) > xs[1]) & (T[:, :, 0].max(1) < xs[-2]) & (T[:, :, 1].min(1) > ys[1]) & (T[:, :, 1].max(1) < ys[-2])
cand = np.flatnonzero(steep & inb)
order = np.argsort(T[cand, :, 2], axis=1)
lowA = T[cand, order[:, 0]]; lowB = T[cand, order[:, 1]]                   # the two lowest corners
gA0 = ground(g0, lowA[:, 0], lowA[:, 1]); gB0 = ground(g0, lowB[:, 0], lowB[:, 1])
gA = ground(g, lowA[:, 0], lowA[:, 1]); gB = ground(g, lowB[:, 0], lowB[:, 1])
SK_ABOVE = float(cc.get("skirt_edge_above_old_ground_m", 0.6)); SK_MIN = float(cc.get("skirt_min_gap_m", 0.15)); SK_BELOW = float(cc.get("skirt_below_m", 0.4))
at_ground = (lowA[:, 2] < gA0 + SK_ABOVE) & (lowB[:, 2] < gB0 + SK_ABOVE) & (lowA[:, 2] > gA0 - 1.0) & (lowB[:, 2] > gB0 - 1.0)
gap = np.maximum(lowA[:, 2] - gA, lowB[:, 2] - gB)
carved_here = ((gA0 - gA) > 0.05) | ((gB0 - gB) > 0.05)
edge_len = np.linalg.norm((lowA - lowB)[:, :2], axis=1)
# ... and walls that end above the bed of a river that was deep already in the source (their lowest edge lies under
# the water surface but above the ground): the same skirt, wherever water is within 4 m of the edge.
_wf = os.path.join(ed, "dump", "extras", "water_final.npz")
under_water = np.zeros(len(cand), bool)
if os.path.exists(_wf):
    _w = np.load(_wf); _wr = _w["water"].astype(np.float64); _x0, _y0, _c = float(_w["x0"]), float(_w["y0"]), float(_w["cell"])
    _lvl = np.where(np.isnan(_wr), -1e9, _wr)
    _d = _lvl.copy()                                   # water level of the nearest water cell within two cells
    for _dj in range(-2, 3):
        for _di in range(-2, 3):
            _d = np.maximum(_d, np.roll(np.roll(_lvl, _dj, 0), _di, 1))
    def wlevel(xm, ym):
        i_ = np.clip(np.rint((xm - _x0) / _c).astype(np.int64), 0, _wr.shape[1] - 1); j_ = np.clip(np.rint((ym - _y0) / _c).astype(np.int64), 0, _wr.shape[0] - 1)
        return _d[j_, i_]
    wA = wlevel(lowA[:, 0], lowA[:, 1]); wB = wlevel(lowB[:, 0], lowB[:, 1])
    under_water = (lowA[:, 2] < wA + 0.3) & (lowB[:, 2] < wB + 0.3) & (lowA[:, 2] > gA - 0.2) & (lowB[:, 2] > gB - 0.2)
n_first = int((at_ground & carved_here & (gap > SK_MIN) & (edge_len > 0.05)).sum())
sk = ((at_ground & carved_here) | under_water) & (gap > SK_MIN) & (edge_len > 0.05)
a_ = lowA[sk]; b_ = lowB[sk]
a2 = a_.copy(); b2 = b_.copy(); a2[:, 2] = np.maximum(gA[sk] - SK_BELOW, a_[:, 2] - WDEPTH); b2[:, 2] = np.maximum(gB[sk] - SK_BELOW, b_[:, 2] - WDEPTH)      # never deeper than the water volumes
q1 = np.stack([a_, b_, b2], 1); q2 = np.stack([a_, b2, a2], 1)
qn = np.cross(q1[:, 1] - q1[:, 0], q1[:, 2] - q1[:, 0]); flip = (qn * nrm[cand][sk]).sum(1) < 0
q1[flip] = q1[flip][:, ::-1]; q2[flip] = q2[flip][:, ::-1]
skirts = ((np.concatenate([q1, q2]) - ORG) * UPM).astype(np.float32)
skirt_info = {"wall_edges": int(sk.sum()), "of_which_over_carved_ground": n_first, "gaps_over_1m": int((gap[sk] > 1.0).sum()), "gaps_over_1_6m_player_height": int((gap[sk] > 1.6).sum()), "triangles": int(len(skirts)), "edge_length_m": round(float(edge_len[sk].sum()), 1), "mean_gap_m": round(float(gap[sk].mean()), 2) if sk.any() else 0.0,
              "max_gap_m": round(float(gap[sk].max()), 2) if sk.any() else 0.0}
print("skirts under walls over carved ground:", skirt_info)
# ---- no terrain collision under the city's floors (see the module notes)
under_info = {"terrain_tris_in": int(len(terr))}
if cc.get("drop_terrain_under_floors", True) and len(terr):
    GAP = float(cc.get("floor_above_terrain_units", 64.0)); REACH = float(cc.get("floor_search_units", 6000.0))
    O_ = objects.reshape(-1, 3, 3).astype(np.float64)
    nz_ = np.cross(O_[:, 1] - O_[:, 0], O_[:, 2] - O_[:, 0]); ln_ = np.linalg.norm(nz_, axis=1)
    up_ = (ln_ > 1e-6) & (nz_[:, 2] > 0.5 * np.maximum(ln_, 1e-9))
    F = O_[up_]
    CELL_ = 128.0
    fmin = F.min(1); fmax = F.max(1)
    gx0 = np.floor(fmin[:, 0] / CELL_).astype(np.int64); gx1 = np.floor(fmax[:, 0] / CELL_).astype(np.int64)
    gy0 = np.floor(fmin[:, 1] / CELL_).astype(np.int64); gy1 = np.floor(fmax[:, 1] / CELL_).astype(np.int64)
    TT = terr.reshape(-1, 3, 3).astype(np.float64); C_ = TT.mean(1)
    cx_ = np.floor(C_[:, 0] / CELL_).astype(np.int64); cy_ = np.floor(C_[:, 1] / CELL_).astype(np.int64)
    key_t = cx_ * 1000003 + cy_
    order = np.argsort(key_t); key_s = key_t[order]
    starts = np.flatnonzero(np.r_[True, key_s[1:] != key_s[:-1]])
    want = {int(key_s[a]): order[a:b] for a, b in zip(starts, np.r_[starts[1:], len(key_s)])}
    bucket = {}
    for i in range(len(F)):
        if (gx1[i] - gx0[i] + 1) * (gy1[i] - gy0[i] + 1) > 4096:
            continue                                     # huge slabs: they are the terrain-level ground itself
        for gx in range(gx0[i], gx1[i] + 1):
            for gy in range(gy0[i], gy1[i] + 1):
                k = gx * 1000003 + gy
                if k in want:
                    bucket.setdefault(k, []).append(i)
    drop = np.zeros(len(TT), bool)
    for k, ti in want.items():
        fi = bucket.get(k)
        if not fi:
            continue
        fi = np.array(fi); a = F[fi, 0]; e1 = F[fi, 1] - a; e2 = F[fi, 2] - a
        det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]; ok_ = np.abs(det) > 1e-9
        P_ = C_[ti]
        dxp = P_[:, None, 0] - a[None, :, 0]; dyp = P_[:, None, 1] - a[None, :, 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = (dxp * e2[None, :, 1] - dyp * e2[None, :, 0]) / det[None, :]; v = (dyp * e1[None, :, 0] - dxp * e1[None, :, 1]) / det[None, :]
        inside = ok_[None, :] & (u >= 0) & (v >= 0) & (u + v <= 1)
        z = a[None, :, 2] + u * e1[None, :, 2] + v * e2[None, :, 2]
        hz = (z - P_[:, None, 2])
        drop[ti] = (inside & (hz > GAP) & (hz < REACH)).any(1)
    terr = terr.reshape(-1, 3, 3)[~drop].reshape(-1, *terr.shape[1:]) if terr.ndim == 3 else terr[~drop]
    under_info.update({"terrain_tris_dropped_under_floors": int(drop.sum()), "terrain_tris_kept": int(len(terr))})
print("terrain under floors:", under_info)
out = np.concatenate([objects.astype(np.float32), terr, skirts.reshape(-1, *objects.shape[1:])])
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
       "water_cells": n_cells, "water_boxes": int(len(boxes)), "water_depth_m": WDEPTH, "skirts": skirt_info, "deep_water_floor": floor_info, "terrain_under_floors": under_info}
json.dump(rep, open(os.path.join(cdir, "terrain_rebuild.json"), "w"), indent=1)
print(json.dumps(rep, indent=1))
