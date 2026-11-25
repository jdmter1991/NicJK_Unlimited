"""Check that solid brushes exist under spawn points and under a grid of terrain sample points.
  py bsp_ground_check.py <map.bsp> [collision_tris.npy]
Brush bounds are taken from each brush's axial planes (q3map2 adds axial bevels to every brush).
For each info_player_* origin: distance from the origin down to the highest brush top below it (inside the
brush's XY bounds). With collision_tris.npy: the same test for a sample of upward-facing input triangles, to
find input ground that did not become a brush.
"""
import sys, struct, re
import numpy as np

path = sys.argv[1]
mm = np.memmap(path, dtype=np.uint8, mode="r")


def lump(i, dt):
    off, ln = struct.unpack_from("<ii", mm, 8 + i * 8)
    return np.frombuffer(mm, dtype=dt, count=ln // np.dtype(dt).itemsize, offset=off)


planes = lump(2, np.dtype([("n", "<f4", 3), ("d", "<f4")]))
sides = lump(9, np.dtype([("plane", "<i4"), ("sh", "<i4"), ("ds", "<i4")]))
brushes = lump(8, np.dtype([("fs", "<i4"), ("ns", "<i4"), ("sh", "<i4")]))
off, ln = struct.unpack_from("<ii", mm, 8)
ents = bytes(mm[off:off + ln]).decode("latin-1")

nb = len(brushes)
side_brush = np.repeat(np.arange(nb), brushes["ns"])
assert len(side_brush) == len(sides), "brush sides are not contiguous per brush"
pn = planes["n"][sides["plane"]]; pd = planes["d"][sides["plane"]]
mins = np.full((nb, 3), -np.inf, np.float32); maxs = np.full((nb, 3), np.inf, np.float32)
for ax in range(3):
    pos = pn[:, ax] == 1.0; neg = pn[:, ax] == -1.0
    np.minimum.at(maxs[:, ax], side_brush[pos], pd[pos])
    np.maximum.at(mins[:, ax], side_brush[neg], -pd[neg])
bounded = np.isfinite(mins).all(1) & np.isfinite(maxs).all(1)
print("brushes", nb, "with full axial bounds", int(bounded.sum()))
size = (maxs - mins)[bounded]
print("brush size median", np.median(size, axis=0).round(1), "p99", np.percentile(size, 99, axis=0).round(1))


def ground_below(p, reach=96.0):
    m = bounded & (mins[:, 0] <= p[0]) & (maxs[:, 0] >= p[0]) & (mins[:, 1] <= p[1]) & (maxs[:, 1] >= p[1]) & (maxs[:, 2] <= p[2] + 1) & (maxs[:, 2] >= p[2] - reach)
    if not m.any():
        return None
    return float(p[2] - maxs[m, 2].max())


sp = [np.array(list(map(float, m.group(1).split()))) for m in re.finditer(r'"classname" "info_player_\w+"\s*"origin" "([^"]+)"', ents)]
gaps = [ground_below(p) for p in sp]
none = sum(1 for g in gaps if g is None)
ok = [g for g in gaps if g is not None]
print("spawns", len(sp), "with a brush within 96 units below:", len(ok), "without:", none)
if ok:
    print("  gap origin->brush top: min %.1f median %.1f max %.1f" % (min(ok), float(np.median(ok)), max(ok)))
for p, g in zip(sp, gaps):
    if g is None:
        print("  NO GROUND under spawn", p.round(0))

if len(sys.argv) > 2:
    t = np.load(sys.argv[2]).astype(np.float64)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]); a = np.linalg.norm(n, axis=1)
    up = (n[:, 2] / np.maximum(a, 1e-9) > 0.9) & (a > 400)
    idx = np.flatnonzero(up)
    rng = np.random.default_rng(1); pick = rng.choice(idx, size=min(1500, len(idx)), replace=False)
    miss = 0
    for i in pick:
        c = t[i].mean(0) + np.array([0, 0, 8.0])
        if ground_below(c, reach=24.0) is None:
            miss += 1
    print("upward-facing input triangles sampled", len(pick), "of", len(idx), "- no brush within 24 units below the centre:", miss,
          "(%.1f %%)" % (100.0 * miss / max(len(pick), 1)))
