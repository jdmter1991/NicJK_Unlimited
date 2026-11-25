"""Which input collision triangles did not become a brush?  py bsp_dropped_tris.py <map.bsp> <collision_tris.npy> [samples]
A triangle counts as present when some brush's axial bounds contain the triangle's bounds (grown by 2 units)
and are not much larger than it. Prints the dropped share by triangle shape and orientation."""
import sys, struct
import numpy as np

path, tpath = sys.argv[1], sys.argv[2]
NS = int(sys.argv[3]) if len(sys.argv) > 3 else 12000
mm = np.memmap(path, dtype=np.uint8, mode="r")


def lump(i, dt):
    off, ln = struct.unpack_from("<ii", mm, 8 + i * 8)
    return np.frombuffer(mm, dtype=dt, count=ln // np.dtype(dt).itemsize, offset=off)


planes = lump(2, np.dtype([("n", "<f4", 3), ("d", "<f4")]))
sides = lump(9, np.dtype([("plane", "<i4"), ("sh", "<i4"), ("ds", "<i4")]))
brushes = lump(8, np.dtype([("fs", "<i4"), ("ns", "<i4"), ("sh", "<i4")]))
nb = len(brushes)
sb = np.repeat(np.arange(nb), brushes["ns"])
pn = planes["n"][sides["plane"]]; pd = planes["d"][sides["plane"]]
mins = np.full((nb, 3), -np.inf, np.float32); maxs = np.full((nb, 3), np.inf, np.float32)
for ax in range(3):
    pos = pn[:, ax] == 1.0; neg = pn[:, ax] == -1.0
    np.minimum.at(maxs[:, ax], sb[pos], pd[pos]); np.maximum.at(mins[:, ax], sb[neg], -pd[neg])

t = np.load(tpath).astype(np.float64)
rng = np.random.default_rng(7); pick = rng.choice(len(t), size=min(NS, len(t)), replace=False)
tmin = t.min(1); tmax = t.max(1)
e = np.stack([np.linalg.norm(t[:, 1] - t[:, 0], axis=1), np.linalg.norm(t[:, 2] - t[:, 1], axis=1), np.linalg.norm(t[:, 0] - t[:, 2], axis=1)], 1)
n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]); a2 = np.linalg.norm(n, axis=1)
height = a2 / np.maximum(e.max(1), 1e-9)            # smallest altitude
nz = np.abs(n[:, 2]) / np.maximum(a2, 1e-9)
# sort brushes by min x for a quick window
order = np.argsort(mins[:, 0]); smin = mins[order]; smax = maxs[order]
maxw = float(np.percentile(smax[:, 0] - smin[:, 0], 99.9)) + 4
found = np.zeros(len(pick), bool)
for k, i in enumerate(pick):
    lo = np.searchsorted(smin[:, 0], tmin[i, 0] - maxw); hi = np.searchsorted(smin[:, 0], tmin[i, 0] + 2.5, side="right")
    bm = smin[lo:hi]; bx = smax[lo:hi]
    m = (bm <= tmin[i] + 2).all(1) & (bx >= tmax[i] - 2).all(1)
    if m.any():
        ext_t = np.maximum(tmax[i] - tmin[i], 4.0)
        ok = ((bx[m] - bm[m]) <= ext_t * 1.6 + 8).all(1)
        found[k] = ok.any()
h = height[pick]; z = nz[pick]; ar = a2[pick] / 2
print("sampled", len(pick), "present", int(found.sum()), "dropped %.1f %%" % (100 * (~found).mean()))
for lab, lo, hi in (("<0.25", 0, .25), ("0.25-0.5", .25, .5), ("0.5-1", .5, 1), ("1-2", 1, 2), ("2-4", 2, 4), ("4-8", 4, 8), ("8-16", 8, 16), ("16+", 16, 1e9)):
    m = (h >= lo) & (h < hi)
    if m.any():
        print("  min altitude %-8s n=%5d dropped %5.1f %%" % (lab, m.sum(), 100 * (~found[m]).mean()))
for lab, lo, hi in (("vertical |nz|<0.2", 0, .2), ("slanted", .2, .9), ("flat |nz|>0.9", .9, 1.01)):
    m = (z >= lo) & (z < hi)
    print("  %-18s n=%5d dropped %5.1f %%" % (lab, m.sum(), 100 * (~found[m]).mean()))
big = (h >= 8)
print("triangles with min altitude >= 8: dropped %.2f %% (n=%d)" % (100 * (~found[big]).mean(), big.sum()))
d = pick[~found & big][:8]
for i in d:
    print("   example dropped: alt %.1f area %.0f nz %.2f edges %s" % (height[i], a2[i] / 2, nz[i], e[i].round(1)))
