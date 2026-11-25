"""Which collision triangles have no brush in a q3map2-built BSP, and what do they look like?
  py bsp_match_tris.py <export_dir> <file.bsp>
Matches each triangle to the brush with the nearest bounds (6-D nearest neighbour on mins+maxs).
"""
import sys, os, json, struct
import numpy as np
from scipy.spatial import cKDTree

export_dir, bsp = sys.argv[1], sys.argv[2]
tris = np.load(os.path.join(export_dir, "collision", "collision_tris.npy")).astype(np.float64)
n_terr = int(json.load(open(os.path.join(export_dir, "collision", "collision_stats.json"))).get("terrain_tris", 0))
d = open(bsp, "rb").read()
lumps = [struct.unpack_from("<ii", d, 8 + i * 8) for i in range(18)]
L = lambda i: d[lumps[i][0]:lumps[i][0] + lumps[i][1]]
planes = np.frombuffer(L(2), "<f4").reshape(-1, 4); brushes = np.frombuffer(L(8), "<i4").reshape(-1, 3)
sides = np.frombuffer(L(9), "<i4").reshape(-1, 3)
f = brushes[:, 0].astype(np.int64); pd = planes[:, 3]; pl = lambda k: pd[sides[f + k, 0]].astype(np.float64)
bb = np.stack([-pl(0), -pl(2), -pl(4), pl(1), pl(3), pl(5)], 1)

a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
n = np.cross(b - a, c - a); ln = np.linalg.norm(n, axis=1); nn = n / np.maximum(ln, 1e-12)[:, None]
mn = tris.min(1); mx = tris.max(1)
maj = np.abs(nn).argmax(1); sg = np.sign(nn[np.arange(len(nn)), maj])
r = np.arange(len(tris))
# q3map2 pushes the back points one unit against the dominant axis of the normal
mn2 = mn.copy(); mx2 = mx.copy()
mn2[r, maj] -= (sg > 0) * 1.0; mx2[r, maj] += (sg < 0) * 1.0
tb = np.concatenate([mn2, mx2], 1)
dist, _ = cKDTree(bb).query(tb, k=1, workers=-1)
hit = dist < 2.0
e = np.stack([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)], 1)
alt = ln / np.maximum(e.max(1), 1e-12); area = ln * 0.5
print("triangles %d (terrain first %d), matched %d, unmatched %d" % (len(tris), n_terr, hit.sum(), (~hit).sum()))
is_t = r < n_terr
for name, m in (("terrain", is_t), ("objects", ~is_t)):
    print("  %-8s total %7d  unmatched %7d (%.1f %%)   area unmatched %.1f %%" % (name, m.sum(), (m & ~hit).sum(), 100.0 * (m & ~hit).sum() / max(m.sum(), 1),
                                                                               100.0 * area[m & ~hit].sum() / max(area[m].sum(), 1e-9)))
q = [5, 25, 50, 75, 95]
for name, m in (("matched", hit), ("unmatched", ~hit)):
    print("  %-9s longest edge %s   altitude %s   area %s" % (name, np.round(np.percentile(e.max(1)[m], q), 1), np.round(np.percentile(alt[m], q), 2),
                                                             np.round(np.percentile(area[m], q), 1)))
    print("            |normal z| %s   max |normal component| %s" % (np.round(np.percentile(np.abs(nn[m, 2]), q), 2), np.round(np.percentile(np.abs(nn[m]).max(1), q), 3)))
# duplicates: triangles with identical vertex sets
key = np.sort(np.round(tris, 2).reshape(len(tris), 9).view([("", np.float64)] * 9), axis=1) if False else None
srt = np.sort(np.round(tris, 1), axis=1)
flat = np.ascontiguousarray(np.sort(np.round(tris, 1).reshape(len(tris), 3, 3).view([("x", "f8"), ("y", "f8"), ("z", "f8")]).reshape(len(tris), 3), axis=1)).view("f8").reshape(len(tris), 9)
uq, inv, cnt = np.unique(flat, axis=0, return_inverse=True, return_counts=True)
dup = cnt[inv.ravel()] > 1
print("triangles sharing all three corners with another: %d (unique sets %d); of the unmatched: %d" % (dup.sum(), len(uq), (dup & ~hit).sum()))
np.save(os.path.join(export_dir, "collision", "q3map2_matched.npy"), hit)
