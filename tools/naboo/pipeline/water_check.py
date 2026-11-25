"""Where is the water mesh hidden by terrain?  py water_check.py <export_dir> [--save]
Rasterises the water meshes (dump/extras/Theed_Water.npz, Naboo_Waterfalls_01.npz) on a 2 m grid, samples the
terrain height under every water sample (near grid where it exists, far grid elsewhere) at full resolution and
at each detail level's spacing, and reports how much water lies under the terrain.
With --save writes dump/extras/water_height.npz (2 m raster of the water surface height, NaN where no water)."""
import sys, os, json
import numpy as np

export_dir = sys.argv[1]
dump = os.path.join(export_dir, "dump")
near = np.load(os.path.join(dump, "meshes", "terrain_grid.npz"))["grid"].astype(np.float64)
far = np.load(os.path.join(dump, "extras", "terrain_far_grid.npz"))["grid"].astype(np.float64)
CELL = 2.0
x0, y0 = far[0, 0, 0], far[0, 0, 1]; x1, y1 = far[-1, -1, 0], far[-1, -1, 1]
W = int((x1 - x0) / CELL) + 1; H = int((y1 - y0) / CELL) + 1
water = np.full((H, W), np.nan, np.float32)


def raster(P, T):
    for a, b, c in P[T]:
        mnx, mxx = min(a[0], b[0], c[0]), max(a[0], b[0], c[0]); mny, mxy = min(a[1], b[1], c[1]), max(a[1], b[1], c[1])
        i0 = max(int(np.ceil((mnx - x0) / CELL)), 0); i1 = min(int((mxx - x0) / CELL), W - 1)
        j0 = max(int(np.ceil((mny - y0) / CELL)), 0); j1 = min(int((mxy - y0) / CELL), H - 1)
        if i1 < i0 or j1 < j0:
            continue
        xs = x0 + np.arange(i0, i1 + 1) * CELL; ys = y0 + np.arange(j0, j1 + 1) * CELL
        X, Y = np.meshgrid(xs, ys)
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-9:
            continue
        w0 = ((b[1] - c[1]) * (X - c[0]) + (c[0] - b[0]) * (Y - c[1])) / d
        w1 = ((c[1] - a[1]) * (X - c[0]) + (a[0] - c[0]) * (Y - c[1])) / d
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any():
            continue
        z = w0 * a[2] + w1 * b[2] + w2 * c[2]
        sub = water[j0:j1 + 1, i0:i1 + 1]
        upd = m & (np.isnan(sub) | (z > sub))
        sub[upd] = z[upd]


items = json.load(open(os.path.join(dump, "extras", "extras.json")))
for it in items:
    a = np.load(os.path.join(dump, "extras", it["file"]))
    M = np.array(it["matrix"]); P = a["pos"].astype(np.float64) @ M[:3, :3].T + M[:3, 3]
    T = a["loop_vert"][a["tri_loops"]]
    raster(P, T)
    print(it["name"], "tris", len(T), "z %.1f..%.1f" % (P[:, 2].min(), P[:, 2].max()))


def bilinear(g, X, Y, stride=1):
    gs = g[::stride, ::stride]
    gx0, gy0 = gs[0, 0, 0], gs[0, 0, 1]; dx = gs[0, 1, 0] - gs[0, 0, 0]; dy = gs[1, 0, 1] - gs[0, 0, 1]
    fx = (X - gx0) / dx; fy = (Y - gy0) / dy
    inside = (fx >= 0) & (fx <= gs.shape[1] - 1) & (fy >= 0) & (fy <= gs.shape[0] - 1)
    ix = np.clip(np.floor(fx).astype(np.int64), 0, gs.shape[1] - 2); iy = np.clip(np.floor(fy).astype(np.int64), 0, gs.shape[0] - 2)
    tx = np.clip(fx - ix, 0, 1); ty = np.clip(fy - iy, 0, 1)
    z = (gs[iy, ix, 2] * (1 - tx) * (1 - ty) + gs[iy, ix + 1, 2] * tx * (1 - ty) + gs[iy + 1, ix, 2] * (1 - tx) * ty + gs[iy + 1, ix + 1, 2] * tx * ty)
    return z, inside


jj, ii = np.nonzero(~np.isnan(water))
X = x0 + ii * CELL; Y = y0 + jj * CELL; wz = water[jj, ii].astype(np.float64)
print("water samples (2 m):", len(wz), "= %.2f km2" % (len(wz) * CELL * CELL / 1e6))
zn, in_near = bilinear(near, X, Y)
zf, _ = bilinear(far, X, Y)
terr = np.where(in_near, zn, zf)
depth = wz - terr
print("in near terrain: %d samples, elsewhere (far terrain): %d" % (in_near.sum(), (~in_near).sum()))
for lab, m in (("near", in_near), ("far", ~in_near)):
    d = depth[m]
    if len(d):
        print("  %-4s full resolution: hidden by terrain %.1f %%, shallower than 0.5 m %.1f %%, median depth %.2f m" % (
            lab, 100 * (d <= 0).mean(), 100 * ((d > 0) & (d < 0.5)).mean(), float(np.median(d))))
for lab, g, m, strides in (("near", near, in_near, (2, 8, 32)), ("far", far, ~in_near, (1, 4, 16))):
    for s in strides:
        z, _ = bilinear(g, X[m], Y[m], s)
        d = wz[m] - z
        print("  %-4s terrain at stride %2d (%3.0f m): hidden %.1f %%" % (lab, s, abs(g[0, s, 0] - g[0, 0, 0]), 100 * (d <= 0).mean()))
if "--save" in sys.argv:
    np.savez_compressed(os.path.join(dump, "extras", "water_height.npz"), water=water, x0=x0, y0=y0, cell=CELL)
    print("saved water_height.npz", water.shape)
