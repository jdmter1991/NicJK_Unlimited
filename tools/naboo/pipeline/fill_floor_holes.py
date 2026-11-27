"""Close floor holes in the collision with the drawn floor itself.
  py fill_floor_holes.py <export_dir> <tworld>
For every upward-facing triangle the cooked world draws at its nearest detail level (opaque materials, placements
inside the collision bounds, terrain tiles left out: terrain under building floors has no collision on purpose),
the collision triangles (<export_dir>/collision/collision_tris.npy) are asked whether there is collision within 16
units under the triangle's centre, its corners pulled 20 % towards the centre and, for triangles over 2 m2, a lattice
of about one point per square metre. Where there is none, the drawn
triangle is added to the collision as it is. The reduced collision of a large mesh (quay paving, palace floors) can
sag below or miss parts of the drawn floor; this puts the drawn floor back exactly there.
Writes collision_tris.npy (the input is kept as collision_tris_prefill.npy) and collision/floor_fill.json."""
import sys, os, json, time, struct
import numpy as np

t0 = time.time()
ed, tw_path = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
B = cfg["regions"]["city"]["collision_bounds_m"]
blo = (np.array(B[:2]) - ORG[:2]) * UPM; bhi = (np.array(B[2:]) - ORG[:2]) * UPM
cdir = os.path.join(ed, "collision")
src = os.path.join(cdir, "collision_tris.npy")
keep = os.path.join(cdir, "collision_tris_prefill.npy")
# the terrain step writes collision_tris.npy fresh each run; keep its output as this step's input
_rep = os.path.join(cdir, "floor_fill.json")
# collision_tris.npy is this step's input only when it is newer than this step's last run (the terrain step wrote it)
if os.path.exists(src) and (not os.path.exists(keep) or not os.path.exists(_rep) or os.path.getmtime(src) > os.path.getmtime(_rep)):
    os.replace(src, keep)
CT = np.load(keep).astype(np.float64).reshape(-1, 3, 3)

# ---- drawn upward triangles of the cooked world (nearest detail level)
w = np.memmap(tw_path, dtype=np.uint8, mode="r")
magic, ver, nmat, nmesh, nsub, ninst, nvert, nidx = struct.unpack_from("<4sIIIIIII", w, 0); o = 112
mats = np.frombuffer(w, dtype=[("shader", "S64"), ("tint", "<f4", 3), ("flags", "<u4")], count=nmat, offset=o); o += nmat * 80
meshes = np.frombuffer(w, dtype=[("fv", "<u4"), ("nv", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("nl", "<u4"), ("lfs", "<u4", 3), ("lns", "<u4", 3), ("c", "<f4", 3), ("r", "<f4")], count=nmesh, offset=o); o += nmesh * 60
subs = np.frombuffer(w, dtype=[("mat", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("res", "<u4")], count=nsub, offset=o); o += nsub * 16
insts = np.frombuffer(w, dtype=[("mesh", "<u4"), ("m", "<f4", 12), ("c", "<f4", 3), ("r", "<f4")], count=ninst, offset=o); o += ninst * 68
verts = np.frombuffer(w, dtype=[("xyz", "<f4", 3), ("n", "<f4", 3), ("st", "<f4", 2)], count=nvert, offset=o); o += nvert * 32
idx = np.frombuffer(w, dtype="<u4", count=nidx, offset=o)
names = [m.decode(errors="replace") for m in mats["shader"]]
def solid_shader(n):
    # the cook names shaders <texture>_<class>: o opaque (od<n> with a detail layer), c cut-out, b blend, a add, w water, g glass
    suf = n.rsplit("_", 1)[-1]
    return suf.startswith("o") and not (n.startswith("textures/naboo/gt_") or "terrain" in n or "roof" in n or n.startswith("textures/naboo/dd_"))
ok_mat = np.array([(f & 1) == 0 and solid_shader(n) for n, f in zip(names, mats["flags"].astype(np.int64))])
MIN_AREA = float(cfg.get("floor_fill_min_area_m2", 0.2)) * UPM * UPM
C = insts["c"].astype(np.float64)
inb = (C[:, 0] > blo[0]) & (C[:, 0] < bhi[0]) & (C[:, 1] > blo[1]) & (C[:, 1] < bhi[1])
D = []
for ii in np.flatnonzero(inb):
    me = meshes[insts["mesh"][ii]]; M = insts["m"][ii].reshape(3, 4).astype(np.float64)
    V = None
    for s in range(int(me["lfs"][0]), int(me["lfs"][0]) + int(me["lns"][0])):
        sb = subs[s]
        if not ok_mat[sb["mat"]]:
            continue
        if V is None:
            V = verts["xyz"][me["fv"]:me["fv"] + me["nv"]].astype(np.float64) @ M[:, :3].T + M[:, 3]
        t = idx[me["fi"] + sb["fi"]:me["fi"] + sb["fi"] + sb["ni"]].reshape(-1, 3).astype(np.int64)
        T = V[t]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); ln = np.linalg.norm(n, axis=1)
        up = (ln * 0.5 > MIN_AREA) & (n[:, 2] > 0.7 * np.maximum(ln, 1e-9))   # walkable slope, large enough to stand on
        if up.any():
            D.append(T[up])
D = np.concatenate(D) if D else np.zeros((0, 3, 3))
print("drawn walkable triangles:", len(D), " %.0fs" % (time.time() - t0))

# ---- collision under each drawn triangle: test points (centre and corners pulled in)
cen = D.mean(1)
pts = np.concatenate([cen[:, None, :], D * 0.8 + cen[:, None, :] * 0.2], 1)      # (n,4,3)
P_list = [pts.reshape(-1, 3)]; owner = [np.repeat(np.arange(len(D)), 4)]
# large triangles: a lattice of about one point per square metre (at most 64) as well, so a hole in the middle of a
# wide floor is found even when the corners have collision under them (a 35 m2 quay stone triangle had)
area_m2 = np.linalg.norm(np.cross(D[:, 1] - D[:, 0], D[:, 2] - D[:, 0]), axis=1) * 0.5 / (UPM * UPM)
for ti in np.flatnonzero(area_m2 > 2.0):
    k = int(min(10, np.ceil(np.sqrt(2.0 * area_m2[ti]))))
    uu, vv = np.meshgrid(np.arange(k) + 0.5, np.arange(k) + 0.5)
    uu = uu.ravel() / k; vv = vv.ravel() / k; sel = uu + vv < 1.0
    uu = uu[sel]; vv = vv[sel]
    Q = D[ti, 0] + uu[:, None] * (D[ti, 1] - D[ti, 0]) + vv[:, None] * (D[ti, 2] - D[ti, 0])
    P_list.append(Q); owner.append(np.full(len(Q), ti))
P_all = np.concatenate(P_list); owner = np.concatenate(owner)
CELL = 128.0
cmin = CT.min(1); cmax = CT.max(1)
cn = np.cross(CT[:, 1] - CT[:, 0], CT[:, 2] - CT[:, 0])
cup = np.abs(cn[:, 2]) > 1e-6
gx0 = np.floor(cmin[:, 0] / CELL).astype(np.int64); gx1 = np.floor(cmax[:, 0] / CELL).astype(np.int64)
gy0 = np.floor(cmin[:, 1] / CELL).astype(np.int64); gy1 = np.floor(cmax[:, 1] / CELL).astype(np.int64)
P = P_all
pk = np.floor(P[:, 0] / CELL).astype(np.int64) * 1000003 + np.floor(P[:, 1] / CELL).astype(np.int64)
want = set(pk.tolist())
bucket = {}
for i in np.flatnonzero(cup):
    if (gx1[i] - gx0[i] + 1) * (gy1[i] - gy0[i] + 1) > 1024:
        continue
    for gx in range(gx0[i], gx1[i] + 1):
        for gy in range(gy0[i], gy1[i] + 1):
            k = gx * 1000003 + gy
            if k in want:
                bucket.setdefault(k, []).append(i)
big = np.flatnonzero(cup & ((gx1 - gx0 + 1) * (gy1 - gy0 + 1) > 1024))
print("collision buckets built  %.0fs" % (time.time() - t0))
has = np.zeros(len(P), bool)
order = np.argsort(pk); ks = pk[order]
starts = np.flatnonzero(np.r_[True, ks[1:] != ks[:-1]])
for a, b in zip(starts, np.r_[starts[1:], len(ks)]):
    pi = order[a:b]; fi = bucket.get(int(ks[a]), [])
    fi = np.concatenate([np.array(fi, np.int64), big]) if len(big) else np.array(fi, np.int64)
    if not len(fi):
        continue
    A = CT[fi, 0]; e1 = CT[fi, 1] - A; e2 = CT[fi, 2] - A
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    for s in range(0, len(pi), 256):
        q = P[pi[s:s + 256]]
        dx = q[:, None, 0] - A[None, :, 0]; dy = q[:, None, 1] - A[None, :, 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = (dx * e2[None, :, 1] - dy * e2[None, :, 0]) / det[None, :]; v = (dy * e1[None, :, 0] - dx * e1[None, :, 1]) / det[None, :]
        ins = (np.abs(det)[None, :] > 1e-9) & (u >= -1e-4) & (v >= -1e-4) & (u + v <= 1 + 1e-4)
        z = A[None, :, 2] + u * e1[None, :, 2] + v * e2[None, :, 2]
        dz = q[:, None, 2] - z
        has[pi[s:s + 256]] = (ins & (dz > -24) & (dz < 16)).any(1)
missing = np.zeros(len(D), bool); np.logical_or.at(missing, owner, ~has)
add = D[missing]
# winding: collision triangles face outward (up for floors), as drawn
out = np.concatenate([CT, add]).astype(np.float32)
np.save(src, out)
area = float((np.linalg.norm(np.cross(add[:, 1] - add[:, 0], add[:, 2] - add[:, 0]), axis=1) * 0.5).sum() / UPM / UPM) if len(add) else 0.0
rep = {"seconds": round(time.time() - t0, 1), "drawn_walkable_triangles": int(len(D)), "added_triangles": int(len(add)), "added_area_m2": round(area, 1),
       "collision_triangles_before": int(len(CT)), "after": int(len(out))}
json.dump(rep, open(os.path.join(cdir, "floor_fill.json"), "w"), indent=1)
print(json.dumps(rep))
