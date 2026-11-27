"""Walls one collision has and another lacks: a check after changing the collision reduction.
  py wall_holes.py <reference_tris.npy> <new_tris.npy> <out.json> [spacing]
Horizontal rays on a grid over the city (every `spacing` units, default 256; along +x, -x, +y, -y) at 40, 100 and 160
units over the drawn terrain; a ray counts as a hole when the reference collision has a surface within 400 units and the
new one has none within that distance + 64. Clusters (256-unit cells) with a setviewpos line."""
import sys, os, json
import numpy as np

ref_p, new_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
SP = float(sys.argv[4]) if len(sys.argv) > 4 else 256.0
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
B = cfg["regions"]["city"]["collision_bounds_m"]
g = np.load(os.path.join(os.path.dirname(HERE), "export", "city", "dump", "extras", "terrain_near_carved.npz"))["grid"].astype(np.float64)
gx = (g[0, :, 0] - ORG[0]) * UPM; gy = (g[:, 0, 1] - ORG[1]) * UPM; gz = (g[:, :, 2] - ORG[2]) * UPM
R = 400.0; CELL = 512.0


def load(p):
    T = np.load(p).astype(np.float64).reshape(-1, 3, 3)
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); ln = np.linalg.norm(n, axis=1)
    T = T[(ln > 1e-6) & (np.abs(n[:, 2]) < 0.7 * ln)]          # walls and slopes only
    mn = T.min(1); mx = T.max(1); bk = {}
    x0 = np.floor(mn[:, 0] / CELL).astype(int); x1 = np.floor(mx[:, 0] / CELL).astype(int)
    y0 = np.floor(mn[:, 1] / CELL).astype(int); y1 = np.floor(mx[:, 1] / CELL).astype(int)
    for i in np.flatnonzero((x1 - x0 + 1) * (y1 - y0 + 1) <= 64):
        for a in range(x0[i], x1[i] + 1):
            for b in range(y0[i], y1[i] + 1):
                bk.setdefault((a, b), []).append(i)
    return T, {k: np.array(v) for k, v in bk.items()}


def first_hit(TB, o, d):
    T, bk = TB
    e = o + d * R
    keys = {(int(np.floor(p[0] / CELL)), int(np.floor(p[1] / CELL))) for p in (o, e, (o + e) / 2)}
    ids = [bk[k] for k in keys if k in bk]
    if not ids:
        return np.inf
    sel = np.unique(np.concatenate(ids))
    A = T[sel, 0]; e1 = T[sel, 1] - A; e2 = T[sel, 2] - A; dd = d * (R + 64)
    h = np.cross(np.broadcast_to(dd, e2.shape), e2); a = (e1 * h).sum(1); ok = np.abs(a) > 1e-9
    f = np.where(ok, 1 / np.where(ok, a, 1), 0); s = o - A
    u = f * (s * h).sum(1); q = np.cross(s, e1); v = f * (q * dd).sum(1); t = f * (e2 * q).sum(1)
    hit = ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (t > 0) & (t < 1)
    return float(t[hit].min() * (R + 64)) if hit.any() else np.inf


REF = load(ref_p); NEW = load(new_p)
xs = np.arange((B[0] - ORG[0]) * UPM, (B[2] - ORG[0]) * UPM, SP); ys = np.arange((B[1] - ORG[1]) * UPM, (B[3] - ORG[1]) * UPM, SP)
holes = []; rays = 0
for x in xs:
    i = np.clip(np.searchsorted(gx, x), 1, len(gx) - 1)
    for y in ys:
        j = np.clip(np.searchsorted(gy, y), 1, len(gy) - 1)
        tz = gz[j, i]
        for hz in (40.0, 100.0, 160.0):
            o = np.array([x, y, tz + hz])
            for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
                d = np.array(d, float); rays += 1
                r = first_hit(REF, o, d)
                if r < R and first_hit(NEW, o, d) > r + 64:
                    holes.append((o + d * r).tolist())
H = np.array(holes).reshape(-1, 3)
cl = []
if len(H):
    k = np.floor(H[:, :2] / 256).astype(int); u, inv, cnt = np.unique(k, axis=0, return_inverse=True, return_counts=True)
    for q in np.argsort(-cnt)[:40]:
        p = H[inv.ravel() == q].mean(0)
        cl.append({"count": int(cnt[q]), "x": int(p[0]), "y": int(p[1]), "z": int(p[2]), "setviewpos": "setviewpos %d %d %d 0" % (p[0], p[1], p[2] + 20)})
json.dump({"rays": rays, "holes": len(holes), "clusters": cl}, open(out_p, "w"), indent=1)
print("rays %d, wall holes %d" % (rays, len(holes)))
for c in cl[:12]:
    print(c["count"], c["setviewpos"])
