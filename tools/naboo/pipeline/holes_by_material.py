"""Which drawn surfaces the floor-check holes lie on.
  py holes_by_material.py <tworld> <holes.npy>
For every hole sample (no collision within 64 units under a drawn upward surface) the placement and material of
the drawn triangle it lies on (nearest detail level), counted by material and by mesh."""
import sys, struct, collections
import numpy as np
w = np.memmap(sys.argv[1], dtype=np.uint8, mode="r"); H = np.load(sys.argv[2]).astype(np.float64)
magic, ver, nmat, nmesh, nsub, ninst, nvert, nidx = struct.unpack_from("<4sIIIIIII", w, 0); o = 112
mats = np.frombuffer(w, dtype=[("shader", "S64"), ("tint", "<f4", 3), ("flags", "<u4")], count=nmat, offset=o); o += nmat * 80
meshes = np.frombuffer(w, dtype=[("fv", "<u4"), ("nv", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("nl", "<u4"), ("lfs", "<u4", 3), ("lns", "<u4", 3), ("c", "<f4", 3), ("r", "<f4")], count=nmesh, offset=o); o += nmesh * 60
subs = np.frombuffer(w, dtype=[("mat", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("res", "<u4")], count=nsub, offset=o); o += nsub * 16
insts = np.frombuffer(w, dtype=[("mesh", "<u4"), ("m", "<f4", 12), ("c", "<f4", 3), ("r", "<f4")], count=ninst, offset=o); o += ninst * 68
verts = np.frombuffer(w, dtype=[("xyz", "<f4", 3), ("n", "<f4", 3), ("st", "<f4", 2)], count=nvert, offset=o); o += nvert * 32
idx = np.frombuffer(w, dtype="<u4", count=nidx, offset=o)
C = insts["c"].astype(np.float64); R = insts["r"].astype(np.float64)
by_mat = collections.Counter(); by_mesh = collections.Counter(); found = 0
cache = {}
for p in H:
    cand = np.flatnonzero((np.abs(C[:, 0] - p[0]) < R) & (np.abs(C[:, 1] - p[1]) < R) & (np.abs(C[:, 2] - p[2]) < R + 32))
    hit = None
    for ii in cand:
        mi = int(insts["mesh"][ii]); me = meshes[mi]; M = insts["m"][ii].reshape(3, 4).astype(np.float64)
        V = verts["xyz"][me["fv"]:me["fv"] + me["nv"]].astype(np.float64) @ M[:, :3].T + M[:, 3]
        for s in range(int(me["lfs"][0]), int(me["lfs"][0]) + int(me["lns"][0])):
            sb = subs[s]; t = idx[me["fi"] + sb["fi"]:me["fi"] + sb["fi"] + sb["ni"]].reshape(-1, 3).astype(np.int64)
            A = V[t[:, 0]]; E1 = V[t[:, 1]] - A; E2 = V[t[:, 2]] - A
            det = E1[:, 0] * E2[:, 1] - E1[:, 1] * E2[:, 0]; ok = np.abs(det) > 1e-6
            dx = p[0] - A[:, 0]; dy = p[1] - A[:, 1]
            with np.errstate(divide="ignore", invalid="ignore"):
                u = (dx * E2[:, 1] - dy * E2[:, 0]) / det; v = (dy * E1[:, 0] - dx * E1[:, 1]) / det
            z = A[:, 2] + u * E1[:, 2] + v * E2[:, 2]
            m_ = ok & (u >= -0.01) & (v >= -0.01) & (u + v <= 1.01) & (np.abs(z - p[2]) < 6)
            if m_.any():
                hit = (mats[sb["mat"]]["shader"].decode(), mi); break
        if hit: break
    if hit:
        found += 1; by_mat[hit[0]] += 1; by_mesh[hit[1]] += 1
print("holes", len(H), "matched to a drawn surface", found)
for k, v in by_mat.most_common(15): print(v, k)
print("meshes:", by_mesh.most_common(10))
