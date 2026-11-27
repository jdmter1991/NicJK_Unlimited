"""Where players walked through walls: steps between two logged positions (PlayerPos, every 2 s) that were both on the
ground, short (< 400 units) and level (< 40 units up or down), whose straight line at body height (30 and 50 units over
the feet) passes through two or more collision surfaces: in through a wall and out the other side. A straight line can
cut a corner the player walked round, so single surfaces are not counted; spots that repeat across runs are the ones
to check in the game.
  py wall_crossings.py <export_dir> <run_dir> [<run_dir> ...]
Writes <first run_dir>/wall_crossings.json (clusters with a setviewpos line)."""
import sys, os, re, json
import numpy as np

ed, runs = sys.argv[1], sys.argv[2:]
T = np.load(os.path.join(ed, "collision", "collision_tris.npy")).astype(np.float64).reshape(-1, 3, 3)
mn = T.min(1); mx = T.max(1)
CELL = 512.0
bk = {}
gx0 = np.floor(mn[:, 0] / CELL).astype(int); gx1 = np.floor(mx[:, 0] / CELL).astype(int)
gy0 = np.floor(mn[:, 1] / CELL).astype(int); gy1 = np.floor(mx[:, 1] / CELL).astype(int)
for i in np.flatnonzero((gx1 - gx0 + 1) * (gy1 - gy0 + 1) <= 64):
    for a in range(gx0[i], gx1[i] + 1):
        for b in range(gy0[i], gy1[i] + 1):
            bk.setdefault((a, b), []).append(i)
bk = {k: np.array(v) for k, v in bk.items()}


def crossings(a, b):
    keys = {(int(np.floor(p[0] / CELL)), int(np.floor(p[1] / CELL))) for p in (a, b, (a + b) / 2)}
    ids = [bk[k] for k in keys if k in bk]
    if not ids:
        return 0
    sel = np.unique(np.concatenate(ids))
    lo = np.minimum(a, b) - 1; hi = np.maximum(a, b) + 1
    sel = sel[(mx[sel, 0] >= lo[0]) & (mn[sel, 0] <= hi[0]) & (mx[sel, 1] >= lo[1]) & (mn[sel, 1] <= hi[1]) & (mx[sel, 2] >= lo[2]) & (mn[sel, 2] <= hi[2])]
    if not len(sel):
        return 0
    A = T[sel, 0]; e1 = T[sel, 1] - A; e2 = T[sel, 2] - A; d = b - a
    h = np.cross(np.broadcast_to(d, e2.shape), e2); aa = (e1 * h).sum(1); ok = np.abs(aa) > 1e-9
    f = np.where(ok, 1 / np.where(ok, aa, 1), 0); s = a - A
    u = f * (s * h).sum(1); q = np.cross(s, e1); v = f * (q * d).sum(1); t = f * (e2 * q).sum(1)
    hit = ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (t > 0) & (t < 1)
    return int(len(np.unique(np.round(t[hit], 3))))


found = []
for run in runs:
    P = {}
    for line in open(os.path.join(run, "games.log"), errors="replace"):
        m = re.match(r"\s*(\d+):(\d\d) PlayerPos: (\d+) (\S+) (\S+) (\S+) (\d)", line)
        if m:
            P.setdefault(int(m.group(3)), []).append((int(m.group(1)) * 60 + int(m.group(2)), float(m.group(4)), float(m.group(5)), float(m.group(6)), int(m.group(7))))
    names = {}
    for line in open(os.path.join(run, "games.log"), errors="replace"):
        m = re.search(r"ClientConnect: (\d+) \[Bot\] \(BOT\) \"(.*?)\^7\"", line)
        if m:
            names[int(m.group(1))] = m.group(2)
    for c, S in P.items():
        for i in range(1, len(S)):
            t0, x0, y0, z0, g0 = S[i - 1]; t1, x1, y1, z1, g1 = S[i]
            if t1 - t0 > 4 or not (g0 and g1) or abs(z1 - z0) > 40:
                continue
            a = np.array([x0, y0, z0]); b = np.array([x1, y1, z1])
            if np.linalg.norm(b[:2] - a[:2]) > 400 or np.linalg.norm(b[:2] - a[:2]) < 32:
                continue
            n = max(crossings(a + [0, 0, 30], b + [0, 0, 30]), crossings(a + [0, 0, 50], b + [0, 0, 50]))
            if n >= 2:
                found.append({"run": os.path.basename(run.rstrip("/")), "client": c, "name": names.get(c, ""), "t": t1, "from": a.round().tolist(), "to": b.round().tolist(), "surfaces": n})
pts = np.array([(np.array(f["from"]) + np.array(f["to"])) / 2 for f in found]).reshape(-1, 3)
clusters = []
if len(pts):
    k = np.floor(pts[:, :2] / 256).astype(int); u, inv, cnt = np.unique(k, axis=0, return_inverse=True, return_counts=True)
    for i in np.argsort(-cnt)[:25]:
        sel = [found[j] for j in np.flatnonzero(inv.ravel() == i)]
        p = pts[inv.ravel() == i].mean(0)
        clusters.append({"count": int(cnt[i]), "runs": sorted({s["run"] for s in sel}), "x": int(p[0]), "y": int(p[1]), "z": int(p[2]),
                         "setviewpos": "setviewpos %d %d %d 0" % (p[0], p[1], p[2] + 60), "example": sel[0]})
json.dump({"crossings": len(found), "clusters": clusters}, open(os.path.join(runs[0], "wall_crossings.json"), "w"), indent=1)
print("steps through two or more walls:", len(found))
for c in clusters[:15]:
    print(c["count"], c["runs"], c["setviewpos"], c["example"]["name"], c["example"]["from"], "->", c["example"]["to"])
