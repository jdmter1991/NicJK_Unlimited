"""Sky occlusion per placement of the cooked world -> maps/<name>.tsky
  py bake_sky_occlusion.py <export_dir> <game_dir>/taystjk <mapname> <region>
The renderer lights everything with one ambient colour. Inside buildings (the palace) and under arcades the source
is far darker, because the sky cannot reach those surfaces. For every placement inside the region's collision
bounds with a radius between `min_radius` and `max_radius` units this casts rays towards the sky from a few of its
vertices (moved 12 units along their normals; only directions on the open side of the surface) against the
collision triangles
(<export_dir>/collision/collision_tris.npy) and stores the share that is blocked: one byte per placement,
0 = open sky, 255 = enclosed. The renderer scales the ambient light by mix(1, r_tworldIndoor, occlusion).
One value per placement: a wall piece that is half inside and half outside gets the average of its vertices.
Larger placements (terrain tiles, building shells, merged scatter chunks) and the small ground scatter stay at 0.
File: "TSKY", version 1, placement count, then the bytes. It must be rebuilt after every cook (placement order)."""
import sys, os, json, struct, time
import numpy as np

t0 = time.time()
ed, game, mapname, region = sys.argv[1:5]
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
sk = cfg.get("sky_occlusion", {})
RMIN = float(sk.get("min_radius", 40.0)); RMAX = float(sk.get("max_radius", 900.0))
NPTS = int(sk.get("points", 5)); TMAX = float(sk.get("ray_length", 3200.0)); CELL = float(sk.get("cell", 160.0))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
B = cfg["regions"][region]["collision_bounds_m"]
blo = (np.array([B[0], B[1]]) - ORG[:2]) * UPM; bhi = (np.array([B[2], B[3]]) - ORG[:2]) * UPM

# ---- sky directions: 8 around at 35 degrees elevation, 4 at 65 degrees, 1 straight up, weighted by sin(elevation)
dirs = []; wts = []
for el, n, off in ((35.0, 8, 0.0), (65.0, 4, 22.5), (90.0, 1, 0.0)):
    for k in range(n):
        az = np.radians(off + 360.0 * k / n); e = np.radians(el)
        dirs.append((np.cos(e) * np.cos(az), np.cos(e) * np.sin(az), np.sin(e))); wts.append(np.sin(e))
D = np.array(dirs); WT = np.array(wts) / np.sum(wts)

# ---- collision triangles in a 2D grid
T = np.load(os.path.join(ed, "collision", "collision_tris.npy")).reshape(-1, 3, 3).astype(np.float64)
A = T[:, 0]; E1 = T[:, 1] - A; E2 = T[:, 2] - A
tmin = T.min(1); tmax = T.max(1)
gx0 = np.floor(tmin[:, 0] / CELL).astype(np.int64); gx1 = np.floor(tmax[:, 0] / CELL).astype(np.int64)
gy0 = np.floor(tmin[:, 1] / CELL).astype(np.int64); gy1 = np.floor(tmax[:, 1] / CELL).astype(np.int64)
big = (gx1 - gx0 + 1) * (gy1 - gy0 + 1) > 400            # a few huge slabs (far terrain): tested against every ray
big_ix = np.flatnonzero(big)
cells = {}
nx = gx1 - gx0 + 1; ny = gy1 - gy0 + 1
for i in np.flatnonzero(~big):
    for gx in range(gx0[i], gx1[i] + 1):
        for gy in range(gy0[i], gy1[i] + 1):
            cells.setdefault((gx, gy), []).append(i)
bucket = {}
for k, v in cells.items():
    ix = np.array(v, np.int64)
    bucket[k] = (A[ix], E1[ix], E2[ix], float(tmax[ix, 2].max()))
del cells
ZTOP = float(tmax[:, 2].max())
print("collision triangles %d, grid cells %d, large triangles %d   %.0f s" % (len(T), len(bucket), len(big_ix), time.time() - t0), flush=True)


def any_hit(a, e1, e2, o, d, tmaxv):
    """does the ray o + t d (0.5 < t < tmaxv) cross one of the triangles? (Moeller-Trumbore, both sides)"""
    p = np.cross(d, e2); det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-9
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = o - a; u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1); v = (q @ d) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    return bool((ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0.5) & (t < tmaxv)).any())


BA, BE1, BE2 = A[big_ix], E1[big_ix], E2[big_ix]


def blocked(o, d):
    if len(big_ix) and any_hit(BA, BE1, BE2, o, d, TMAX):
        return True
    # walk the grid cells under the ray
    dx, dy = d[0], d[1]
    gx = int(np.floor(o[0] / CELL)); gy = int(np.floor(o[1] / CELL))
    sx = 1 if dx > 0 else -1; sy = 1 if dy > 0 else -1
    tx = ((gx + (sx > 0)) * CELL - o[0]) / dx if abs(dx) > 1e-12 else 1e30
    ty = ((gy + (sy > 0)) * CELL - o[1]) / dy if abs(dy) > 1e-12 else 1e30
    ddx = CELL / abs(dx) if abs(dx) > 1e-12 else 1e30; ddy = CELL / abs(dy) if abs(dy) > 1e-12 else 1e30
    t = 0.0
    while t < TMAX:
        tn = min(tx, ty, TMAX)
        b = bucket.get((gx, gy))
        if b is not None and o[2] + d[2] * t <= b[3] and any_hit(b[0], b[1], b[2], o, d, tn + 1.0):
            return True
        if o[2] + d[2] * tn > ZTOP:
            return False
        if tx < ty:
            gx += sx; t = tx; tx += ddx
        else:
            gy += sy; t = ty; ty += ddy
    return False


# ---- cooked world
w = np.memmap(os.path.join(game, "maps", mapname + ".tworld"), dtype=np.uint8, mode="r")
magic, ver, nmat, nmesh, nsub, ninst, nvert, nidx = struct.unpack_from("<4sIIIIIII", w, 0); o = 112
o += nmat * 80
meshes = np.frombuffer(w, dtype=[("fv", "<u4"), ("nv", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("nl", "<u4"), ("lfs", "<u4", 3), ("lns", "<u4", 3), ("c", "<f4", 3), ("r", "<f4")], count=nmesh, offset=o); o += nmesh * 60
o += nsub * 16
insts = np.frombuffer(w, dtype=[("mesh", "<u4"), ("m", "<f4", 12), ("c", "<f4", 3), ("r", "<f4")], count=ninst, offset=o); o += ninst * 68
verts = np.frombuffer(w, dtype=[("xyz", "<f4", 3), ("n", "<f4", 3), ("st", "<f4", 2)], count=nvert, offset=o)
occ = np.zeros(ninst, np.uint8)
sel = np.flatnonzero((insts["r"] >= RMIN) & (insts["r"] <= RMAX) & (insts["c"][:, 0] > blo[0]) & (insts["c"][:, 0] < bhi[0]) & (insts["c"][:, 1] > blo[1]) & (insts["c"][:, 1] < bhi[1]))
print("placements %d, in bounds with radius %.0f-%.0f: %d" % (ninst, RMIN, RMAX, len(sel)), flush=True)
rng = np.random.default_rng(7)
pick_cache = {}
for n_done, ii in enumerate(sel):
    inst = insts[ii]; mi = int(inst["mesh"]); me = meshes[mi]
    if mi not in pick_cache:
        nv = int(me["nv"])
        pick_cache[mi] = int(me["fv"]) + rng.choice(nv, size=min(NPTS, nv), replace=False)
    vv = verts[pick_cache[mi]]
    M = inst["m"].reshape(3, 4).astype(np.float64)
    P = vv["xyz"].astype(np.float64) @ M[:, :3].T + M[:, 3]
    Nn = vv["n"].astype(np.float64) @ M[:, :3].T
    Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-9)
    P = P + Nn * 12.0
    tot = 0.0
    for p, nn in zip(P, Nn):
        # only directions on the open side of the surface: a wall can never see the half of the sky behind it,
        # and counting that half as blocked made every street facade look half enclosed
        use = (D @ nn) > 0.1
        if not use.any():
            tot += 1.0                      # faces down: no sky at all
            continue
        ws = WT[use].sum(); blk = 0.0
        for d, wgt in zip(D[use], WT[use]):
            if blocked(p, d):
                blk += wgt
        tot += blk / ws
    occ[ii] = int(round(255.0 * tot / len(P)))
    if n_done % 4000 == 0:
        print("  %d of %d   %.0f s" % (n_done, len(sel), time.time() - t0), flush=True)
with open(os.path.join(game, "maps", mapname + ".tsky"), "wb") as f:
    f.write(struct.pack("<4sII", b"TSKY", 1, ninst)); f.write(occ.tobytes())
h = np.histogram(occ[sel], bins=[0, 26, 77, 128, 179, 230, 256])[0]
rep = {"seconds": round(time.time() - t0, 1), "placements": int(ninst), "baked": int(len(sel)), "rays_per_placement": int(NPTS * len(D)),
       "occlusion_histogram_0_10_30_50_70_90_100_percent": h.tolist(), "mean_occlusion_percent": round(float(occ[sel].mean()) / 2.55, 1)}
json.dump(rep, open(os.path.join(ed, "sky_occlusion.json"), "w"), indent=1)
print(json.dumps(rep, indent=1))
