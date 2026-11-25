"""Exact test: is there solid just beneath each sampled input triangle?
  py bsp_solid_under_tris.py <map.bsp> <collision_tris.npy> [samples] [depth]
For a sample of triangles the point (centroid - depth * unit normal) is tested against every brush whose axial
bounds contain it, using all brush planes (inside = on the back of every plane). Reports the share with no solid
by orientation and size. This is the same question the engine's point-contents test answers."""
import sys, struct
import numpy as np

path, tpath = sys.argv[1], sys.argv[2]
NS = int(sys.argv[3]) if len(sys.argv) > 3 else 6000
DEPTH = float(sys.argv[4]) if len(sys.argv) > 4 else 0.75
mm = np.memmap(path, dtype=np.uint8, mode="r")


def lump(i, dt):
    off, ln = struct.unpack_from("<ii", mm, 8 + i * 8)
    return np.frombuffer(mm, dtype=dt, count=ln // np.dtype(dt).itemsize, offset=off)


planes = lump(2, np.dtype([("n", "<f4", 3), ("d", "<f4")]))
sides = lump(9, np.dtype([("plane", "<i4"), ("sh", "<i4"), ("ds", "<i4")]))
brushes = lump(8, np.dtype([("fs", "<i4"), ("ns", "<i4"), ("sh", "<i4")]))
nb = len(brushes)
sb = np.repeat(np.arange(nb), brushes["ns"])
pn = planes["n"][sides["plane"]].astype(np.float64); pd = planes["d"][sides["plane"]].astype(np.float64)
mins = np.full((nb, 3), -np.inf, np.float32); maxs = np.full((nb, 3), np.inf, np.float32)
for ax in range(3):
    pos = pn[:, ax] == 1.0; neg = pn[:, ax] == -1.0
    np.minimum.at(maxs[:, ax], sb[pos], pd[pos]); np.maximum.at(mins[:, ax], sb[neg], -pd[neg])
order = np.argsort(mins[:, 0]); smin = mins[order]; smax = maxs[order]
maxw = float((smax[:, 0] - smin[:, 0]).max()) + 1


def solid(p, eps=0.01):
    lo = np.searchsorted(smin[:, 0], p[0] - maxw); hi = np.searchsorted(smin[:, 0], p[0], side="right")
    m = (smin[lo:hi] <= p).all(1) & (smax[lo:hi] >= p).all(1)
    for b in order[lo:hi][m]:
        f = brushes["fs"][b]; k = brushes["ns"][b]
        if (pn[f:f + k] @ p - pd[f:f + k] <= eps).all():
            return True
    return False


t = np.load(tpath).astype(np.float64)
n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]); a2 = np.linalg.norm(n, axis=1)
nh = n / np.maximum(a2, 1e-9)[:, None]
e = np.stack([np.linalg.norm(t[:, 1] - t[:, 0], axis=1), np.linalg.norm(t[:, 2] - t[:, 1], axis=1), np.linalg.norm(t[:, 0] - t[:, 2], axis=1)], 1)
alt = a2 / np.maximum(e.max(1), 1e-9)
rng = np.random.default_rng(3); pick = rng.choice(len(t), size=min(NS, len(t)), replace=False)
res = np.array([solid(t[i].mean(0) - nh[i] * DEPTH) for i in pick])
res_flip = np.array([solid(t[i].mean(0) + nh[i] * DEPTH) for i in pick])
either = res | res_flip
nz = nh[pick, 2]; al = alt[pick]
print("sampled", len(pick), "depth", DEPTH)
print("solid behind the face: %.1f %%   solid in front instead: %.1f %%   neither side: %.1f %%" % (100 * res.mean(), 100 * (res_flip & ~res).mean(), 100 * (~either).mean()))
for lab, m in (("floor (nz > 0.9)", nz > 0.9), ("ceiling (nz < -0.9)", nz < -0.9), ("wall (|nz| < 0.2)", np.abs(nz) < 0.2), ("slanted", (np.abs(nz) >= 0.2) & (np.abs(nz) <= 0.9))):
    if m.any():
        print("  %-20s n=%5d  no solid on either side %5.1f %%   behind %5.1f %%" % (lab, m.sum(), 100 * (~either[m]).mean(), 100 * res[m].mean()))
for lab, lo, hi in (("alt < 1", 0, 1), ("1-4", 1, 4), ("4-16", 4, 16), ("16+", 16, 1e9)):
    m = (al >= lo) & (al < hi)
    if m.any():
        print("  min altitude %-8s n=%5d  no solid on either side %5.1f %%" % (lab, m.sum(), 100 * (~either[m]).mean()))
fl = (nz > 0.9) & (al >= 16)
print("walkable-size floors (nz > 0.9, altitude >= 16): n=%d, no solid on either side: %d (%.2f %%)" % (fl.sum(), int((~either[fl]).sum()), 100 * (~either[fl]).mean()))
