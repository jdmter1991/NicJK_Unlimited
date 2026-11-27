"""Water for the source's dry canals: the canal beds that lie below the river's surface and are joined to it get the
river's water, so canals and river read as one flowing body. The terrain is not touched.
  py canal_water.py <export_dir>
Reads  <export>/dump/extras/water_height.npz        the source's water surface raster (2 m), NaN = no water
       <export>/dump/meshes/terrain_grid.npz         the source terrain (1 m grid, exact)
       <export>/collision/collision_tris_prefill.npy collision (to leave out cells under buildings, bridges, walkways)
Writes <export>/dump/extras/canal_water.npz         mask of the added cells and their surface height (same raster)
Flood from every source water cell into its four neighbours while (a) the terrain under the cell centre (lowest of the
four nearest 1 m samples) is at least `min_depth_m` (0.3 m) below the neighbour's surface, (b) nothing in the collision
lies over the cell between the surface and 25 m above it (open to the sky). The surface height is carried along.
Kept: only added stretches that join two or more separate pieces of the source's water (canals), inside the playable
area (regions.city.collision_bounds_m)."""
import sys, os, json
import numpy as np
from collections import deque

ed = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
MIN_DEPTH = float(cfg.get("canal_water_min_depth_m", 0.3))
w = np.load(os.path.join(ed, "dump", "extras", "water_height.npz"))
WR = w["water"].astype(np.float64); x0 = float(w["x0"]); y0 = float(w["y0"]); cs = float(w["cell"])
g = np.load(os.path.join(ed, "dump", "meshes", "terrain_grid.npz"))["grid"].astype(np.float64)
gx = g[0, :, 0]; gy = g[:, 0, 1]; gz = g[:, :, 2]
ny, nx = WR.shape
cxm = x0 + (np.arange(nx) + 0.5) * cs; cym = y0 + (np.arange(ny) + 0.5) * cs
inx = (cxm > gx[0]) & (cxm < gx[-1]); iny = (cym > gy[0]) & (cym < gy[-1])
ix = np.clip(np.searchsorted(gx, cxm) - 1, 0, len(gx) - 2); iy = np.clip(np.searchsorted(gy, cym) - 1, 0, len(gy) - 2)
TZ = np.full(WR.shape, np.inf)
sub = np.minimum(np.minimum(gz[np.ix_(iy, ix)], gz[np.ix_(iy, ix + 1)]), np.minimum(gz[np.ix_(iy + 1, ix)], gz[np.ix_(iy + 1, ix + 1)]))
TZ[np.ix_(iny, inx)] = sub[np.ix_(iny, inx)]

# cells with collision over them (units): any triangle crossing the column between surface level and 25 m above it
T = np.load(os.path.join(ed, "collision", "collision_tris_prefill.npy")).astype(np.float64).reshape(-1, 3, 3)
Tm = (T / UPM) + ORG                                           # metres
level = np.nanmedian(WR)
sel = (Tm[:, :, 2].max(1) > level + 0.3) & (Tm[:, :, 2].min(1) < level + 25.0)
Tm = Tm[sel]
covered = np.zeros(WR.shape, bool)
mn = Tm.min(1); mx = Tm.max(1)
for k in range(len(Tm)):
    i0 = int((mn[k, 0] - x0) / cs); i1 = int((mx[k, 0] - x0) / cs); j0 = int((mn[k, 1] - y0) / cs); j1 = int((mx[k, 1] - y0) / cs)
    if i1 < 0 or j1 < 0 or i0 >= nx or j0 >= ny:
        continue
    i0 = max(i0, 0); j0 = max(j0, 0); i1 = min(i1, nx - 1); j1 = min(j1, ny - 1)
    a, b, c = Tm[k]; e1 = b - a; e2 = c - a; det = e1[0] * e2[1] - e1[1] * e2[0]
    if abs(det) < 1e-9:
        continue
    X, Y = np.meshgrid(cxm[i0:i1 + 1], cym[j0:j1 + 1])
    u = ((X - a[0]) * e2[1] - (Y - a[1]) * e2[0]) / det; v = ((Y - a[1]) * e1[0] - (X - a[0]) * e1[1]) / det
    covered[j0:j1 + 1, i0:i1 + 1] |= (u >= 0) & (v >= 0) & (u + v <= 1)
print("cells covered by collision near water level:", int(covered.sum()))

src = ~np.isnan(WR)
H = np.where(src, WR, np.nan)
add = np.zeros(WR.shape, bool)
dq = deque(zip(*np.nonzero(src)))
while dq:
    j, i = dq.popleft()
    h = H[j, i]
    for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        jj, ii = j + dj, i + di
        if 0 <= jj < ny and 0 <= ii < nx and np.isnan(H[jj, ii]) and not covered[jj, ii] and TZ[jj, ii] < h - MIN_DEPTH:
            H[jj, ii] = h; add[jj, ii] = True; dq.append((jj, ii))


def label(mask):
    """4-connected components: (labels, count)"""
    lab = np.zeros(mask.shape, np.int32); n = 0
    for j0, i0 in zip(*np.nonzero(mask)):
        if lab[j0, i0]:
            continue
        n += 1; lab[j0, i0] = n; q = deque([(j0, i0)])
        while q:
            j, i = q.popleft()
            for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jj, ii = j + dj, i + di
                if 0 <= jj < ny and 0 <= ii < nx and mask[jj, ii] and not lab[jj, ii]:
                    lab[jj, ii] = n; q.append((jj, ii))
    return lab, n


# keep only the added stretches that join two or more separate pieces of the source's water: a canal connects water;
# a low dead end that touches the river on one side only (ground under backdrop towers, a dry basin) stays dry
ls, ns = label(src); la, na = label(add)
kept = np.zeros(na + 1, bool)
touch = [set() for _ in range(na + 1)]
for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
    a_ = np.roll(la, (dj, di), (0, 1)); s_ = ls
    m_ = (a_ > 0) & (s_ > 0)
    for a__, s__ in set(zip(a_[m_].tolist(), s_[m_].tolist())):
        touch[a__].add(s__)
for k in range(1, na + 1):
    kept[k] = len(touch[k]) >= 2
add = kept[la] & add
# only inside the playable area (collision bounds): beyond it the far river's patches lie apart over open country, and
# joining them would flood fields the city looks out on
B = cfg["regions"]["city"]["collision_bounds_m"]
inside = ((cxm > B[0]) & (cxm < B[2]))[None, :] & ((cym > B[1]) & (cym < B[3]))[:, None]
add &= inside
print("added pieces %d, joining two or more source pieces %d" % (na, int(kept.sum())))
np.savez(os.path.join(ed, "dump", "extras", "canal_water.npz"), add=add, height=np.where(add, H, np.nan).astype(np.float32), x0=x0, y0=y0, cell=cs)
rep = {"source_cells": int(src.sum()), "added_cells": int(add.sum()), "added_area_m2": round(float(add.sum() * cs * cs), 1)}
json.dump(rep, open(os.path.join(ed, "dump", "extras", "canal_water.json"), "w"), indent=1)
print(json.dumps(rep))
