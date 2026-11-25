"""Do the floors that are drawn have collision under them?
  py visual_vs_collision.py <game_dir>/taystjk <mapname> <region> [samples]
Samples points on upward-facing triangles of the cooked world (nearest detail level, opaque materials, placements
of at least `min_radius` units) inside the region's collision bounds, and asks the collision BSP whether there is
solid just beneath each point (4 units below the surface, exact brush test). Also counts points that lie inside a
water volume. A floor without solid is a place where a player would fall through what they see.
Writes <game_dir>/maps/<mapname>_floorcheck.json with the worst clusters (64-unit cells)."""
import sys, os, struct, json, time
import numpy as np

t0 = time.time()
game, mapname, region = sys.argv[1], sys.argv[2], sys.argv[3]
NS = int(sys.argv[4]) if len(sys.argv) > 4 else 60000
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
B = cfg["regions"][region]["collision_bounds_m"]
blo = (np.array([B[0], B[1]]) - ORG[:2]) * UPM; bhi = (np.array([B[2], B[3]]) - ORG[:2]) * UPM

# ---- collision BSP
d = np.memmap(os.path.join(game, "maps", mapname + ".bsp"), dtype=np.uint8, mode="r")


def lump(i, dt):
    off, ln = struct.unpack_from("<ii", d, 8 + i * 8)
    return np.frombuffer(d, dtype=dt, count=ln // np.dtype(dt).itemsize, offset=off)


planes = lump(2, np.dtype([("n", "<f4", 3), ("d", "<f4")])); sides = lump(9, np.dtype([("plane", "<i4"), ("sh", "<i4"), ("ds", "<i4")]))
brushes = lump(8, np.dtype([("fs", "<i4"), ("ns", "<i4"), ("sh", "<i4")]))
shaders = lump(1, np.dtype([("name", "S64"), ("surf", "<i4"), ("cont", "<i4")]))
cont = shaders["cont"][brushes["sh"]]
f = brushes["fs"].astype(np.int64); pd = planes["d"]; pl = lambda k: pd[sides["plane"][f + k]].astype(np.float64)
bmn = np.stack([-pl(0), -pl(2), -pl(4)], 1); bmx = np.stack([pl(1), pl(3), pl(5)], 1)
order = np.argsort(bmn[:, 0]); smn = bmn[order]; smx = bmx[order]
maxw = float((smx[:, 0] - smn[:, 0]).max()) + 1
pn = planes["n"][sides["plane"]].astype(np.float64); pdd = planes["d"][sides["plane"]].astype(np.float64)


def column(p, up=8.0, down=64.0):
    """Vertical line through p against the brushes: returns (gap, in_water). gap = p.z minus the top of the highest
    solid brush whose top lies between p.z - down and p.z + up; None when there is none. The collision is a thin
    shell, so probing single points below a surface would miss it."""
    lo = np.searchsorted(smn[:, 0], p[0] - maxw); hi = np.searchsorted(smn[:, 0], p[0], side="right")
    m = (smn[lo:hi, :2] <= p[:2]).all(1) & (smx[lo:hi, :2] >= p[:2]).all(1) & (smx[lo:hi, 2] >= p[2] - down) & (smn[lo:hi, 2] <= p[2] + up)
    best = None; wet = False
    for b in order[lo:hi][m]:
        s0 = brushes["fs"][b]; k = brushes["ns"][b]
        nn = pn[s0:s0 + k]; dd = pdd[s0:s0 + k] - nn[:, 0] * p[0] - nn[:, 1] * p[1]        # nz * z <= dd
        zlo, zhi = -1e30, 1e30; ok_ = True
        for nz_, d_ in zip(nn[:, 2], dd):
            if nz_ > 1e-9: zhi = min(zhi, d_ / nz_)
            elif nz_ < -1e-9: zlo = max(zlo, d_ / nz_)
            elif d_ < -0.01: ok_ = False; break
        if not ok_ or zhi < zlo:
            continue
        if cont[b] & 4:
            wet = wet or (zlo <= p[2] + 2.0 <= zhi)
        if (cont[b] & 1) and p[2] - down <= zhi <= p[2] + up:
            g_ = p[2] - zhi
            if best is None or g_ < best:
                best = g_
    return best, wet


# ---- cooked world: upward-facing triangles of the nearest detail level
w = np.memmap(os.path.join(game, "maps", mapname + ".tworld"), dtype=np.uint8, mode="r")
magic, ver, nmat, nmesh, nsub, ninst, nvert, nidx = struct.unpack_from("<4sIIIIIII", w, 0); o = 112
mats = np.frombuffer(w, dtype=[("shader", "S64"), ("tint", "<f4", 3), ("flags", "<u4")], count=nmat, offset=o); o += nmat * 80
meshes = np.frombuffer(w, dtype=[("fv", "<u4"), ("nv", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("nl", "<u4"), ("lfs", "<u4", 3), ("lns", "<u4", 3), ("c", "<f4", 3), ("r", "<f4")], count=nmesh, offset=o); o += nmesh * 60
subs = np.frombuffer(w, dtype=[("mat", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("res", "<u4")], count=nsub, offset=o); o += nsub * 16
insts = np.frombuffer(w, dtype=[("mesh", "<u4"), ("m", "<f4", 12), ("c", "<f4", 3), ("r", "<f4")], count=ninst, offset=o); o += ninst * 68
verts = np.frombuffer(w, dtype=[("xyz", "<f4", 3), ("n", "<f4", 3), ("st", "<f4", 2)], count=nvert, offset=o); o += nvert * 32
indexes = np.frombuffer(w, dtype="<u4", count=nidx, offset=o)
MIN_R = 150.0
opaque = np.array([(int(m["flags"]) & 1) == 0 and ((int(m["flags"]) >> 1) & 7) in (0,) for m in mats])
rng = np.random.default_rng(11)
tri_a = []; tri_b = []; tri_c = []; tri_area = []
for inst in insts:
    if inst["r"] < MIN_R or not (blo[0] - inst["r"] < inst["c"][0] < bhi[0] + inst["r"] and blo[1] - inst["r"] < inst["c"][1] < bhi[1] + inst["r"]):
        continue
    me = meshes[inst["mesh"]]; M = inst["m"].reshape(3, 4).astype(np.float64)
    V = verts["xyz"][me["fv"]:me["fv"] + me["nv"]].astype(np.float64) @ M[:, :3].T + M[:, 3]
    for s in range(int(me["lfs"][0]), int(me["lfs"][0]) + int(me["lns"][0])):
        sb = subs[s]
        if not opaque[sb["mat"]] or sb["ni"] == 0:
            continue
        ix = indexes[me["fi"] + sb["fi"]:me["fi"] + sb["fi"] + sb["ni"]].reshape(-1, 3).astype(np.int64)
        a, b, c = V[ix[:, 0]], V[ix[:, 1]], V[ix[:, 2]]
        n = np.cross(b - a, c - a); ar = np.linalg.norm(n, axis=1) * 0.5
        up = (np.abs(n[:, 2]) > 0.95 * 2 * np.maximum(ar, 1e-9)) & (ar > 600.0)      # near-level, at least about 0.4 m2
        if up.any():
            tri_a.append(a[up]); tri_b.append(b[up]); tri_c.append(c[up]); tri_area.append(ar[up])
A = np.concatenate(tri_a); Bv = np.concatenate(tri_b); C = np.concatenate(tri_c); area = np.concatenate(tri_area)
pick = rng.choice(len(A), size=min(NS, len(A)), replace=True, p=area / area.sum())
u = rng.random(len(pick)); v = rng.random(len(pick)); fl = u + v > 1; u[fl] = 1 - u[fl]; v[fl] = 1 - v[fl]
P = A[pick] + (Bv[pick] - A[pick]) * u[:, None] + (C[pick] - A[pick]) * v[:, None]
inb = (P[:, 0] > blo[0]) & (P[:, 0] < bhi[0]) & (P[:, 1] > blo[1]) & (P[:, 1] < bhi[1])
P = P[inb]
print("level triangles %d (%.0f m2), samples inside bounds %d   %.0f s" % (len(A), area.sum() / UPM ** 2, len(P), time.time() - t0), flush=True)
gap = np.full(len(P), np.nan); water = np.zeros(len(P), bool)
for i, p in enumerate(P):
    g_, w_ = column(p)
    water[i] = w_
    if g_ is not None:
        gap[i] = g_
solid = np.abs(gap) <= 4.0            # collision surface within 4 units (10 cm) of the drawn one
above = ~np.isnan(gap)
hole = ~above
cells = {}
for p in P[hole]:
    k = (int(p[0] // 64), int(p[1] // 64), int(p[2] // 64)); cells[k] = cells.get(k, 0) + 1
worst = sorted(cells.items(), key=lambda kv: -kv[1])[:25]
rep = {"seconds": round(time.time() - t0, 1), "samples": int(len(P)), "collision_within_4_units_percent": round(100.0 * float(solid.mean()), 2), "collision_within_16_units_percent": round(100.0 * float((np.abs(gap) <= 16).mean()), 2),
       "collision_within_64_units_below_percent": round(100.0 * float(above.mean()), 2), "no_collision_within_64_units": int(hole.sum()),
       "under_water_surface": int(water.sum()), "hole_cells": len(cells),
       "worst_cells_units": [{"pos": [k[0] * 64 + 32, k[1] * 64 + 32, k[2] * 64 + 32], "samples": n} for k, n in worst]}
json.dump(rep, open(os.path.join(game, "maps", mapname + "_floorcheck.json"), "w"), indent=1)
np.save(os.path.join(game, "maps", mapname + "_floorcheck_holes.npy"), P[hole].astype(np.float32))
print(json.dumps({k: v for k, v in rep.items() if k != "worst_cells_units"}, indent=1)); print(rep["worst_cells_units"][:10])
