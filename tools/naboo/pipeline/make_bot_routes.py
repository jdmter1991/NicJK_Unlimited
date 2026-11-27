"""Bot route file (botroutes/<map>.wnt) for Jedi Academy multiplayer bots, generated from the collision.
  py make_bot_routes.py <export_dir> <mapname> <out.wnt> [spacing_units]
The bots walk a chain of waypoints by index (from a point to the next or previous index) and take a neighbour
link when it shortens the way to their goal (ai_main.c: WPTouchRoutine, CheckForShorterRoutes, TotalTrailDistance).
So every consecutive pair in the file must be a link a player can walk, and the neighbour lists hold the other links.
  1. candidate points on a square grid (spacing, default 288 units) on every walkable floor of the collision
     (collision_tris.npy plus the backdrop skirts): upward faces, at least 80 units of headroom, not in or at water
     (water_boxes.npy: a floor less than 8 units over a water surface, or under it, is left out);
  2. links between grid neighbours (8 directions): sampled every 16 units, the floor must continue (steps of at most
     20 units, no gap, never wet), and two body-height segments (30 and 56 units over the floor) must not cross any
     collision triangle, bot wall (monster clip) or closing wall;
  3. connected groups smaller than `min_group` points are dropped (closed rooms, roofs);
  4. the chain: a depth-first walk that prefers the neighbour with the fewest unvisited neighbours (so it runs
     along corridors and rows); where the walk jumps back, the walked path to the next point is repeated, so the
     chain never has a step that is not a link. At most 4096 entries (MAX_WPARRAY_SIZE).
Writes the .wnt and <out>.json (counts)."""
import sys, os, json, time
import numpy as np
from collections import deque

t0 = time.time()
ed, mapname, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
S = float(sys.argv[4]) if len(sys.argv) > 4 else 288.0
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
rc = cfg.get("bot_routes", {})
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
B = cfg["regions"]["city"]["collision_bounds_m"]
blo = (np.array(B[:2]) - ORG[:2]) * UPM; bhi = (np.array(B[2:]) - ORG[:2]) * UPM
MIN_GROUP = int(rc.get("min_group", 12)); HEAD = float(rc.get("headroom", 80.0)); STEP = float(rc.get("max_step", 20.0))
MAXWP = 4096
cdir = os.path.join(ed, "collision")
T = np.load(os.path.join(cdir, "collision_tris.npy")).astype(np.float64).reshape(-1, 3, 3)
if os.path.exists(os.path.join(cdir, "skirts.npy")):
    T = np.concatenate([T, np.load(os.path.join(cdir, "skirts.npy")).astype(np.float64).reshape(-1, 3, 3)])
WB = np.load(os.path.join(cdir, "water_boxes.npy")).astype(np.float64)
BOXES = [np.zeros((0, 2, 3))]
for f in ("bot_walls.npy", "closing_walls.npy"):
    if os.path.exists(os.path.join(cdir, f)):
        BOXES.append(np.load(os.path.join(cdir, f)).astype(np.float64))
BOXES = np.concatenate(BOXES)
n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); ln = np.linalg.norm(n, axis=1)
UP = np.flatnonzero((ln > 1e-6) & (n[:, 2] > 0.7 * ln))
FLAT = np.flatnonzero(np.abs(n[:, 2]) > 1e-6 * np.maximum(ln, 1e-9))      # anything a vertical ray can hit
print("triangles %d, walkable %d  %.0fs" % (len(T), len(UP), time.time() - t0))

CELL = 128.0
def bucket(ids):
    mn = T[ids].min(1); mx = T[ids].max(1)
    gx0 = np.floor(mn[:, 0] / CELL).astype(np.int64); gx1 = np.floor(mx[:, 0] / CELL).astype(np.int64)
    gy0 = np.floor(mn[:, 1] / CELL).astype(np.int64); gy1 = np.floor(mx[:, 1] / CELL).astype(np.int64)
    d = {}
    for k in range(len(ids)):
        for gx in range(gx0[k], gx1[k] + 1):
            for gy in range(gy0[k], gy1[k] + 1):
                d.setdefault((gx, gy), []).append(ids[k])
    return {k: np.array(v, np.int64) for k, v in d.items()}
BU = bucket(UP); BF = bucket(FLAT); BA = bucket(np.arange(len(T)))
print("buckets  %.0fs" % (time.time() - t0))


def column_hits(P, bk):
    """for points P (n,2): list of arrays of z where a vertical line hits triangles of the bucket set"""
    out = [np.zeros(0)] * len(P)
    key = np.floor(P / CELL).astype(np.int64)
    order = np.lexsort((key[:, 1], key[:, 0])); ks = key[order]
    st = np.flatnonzero(np.r_[True, (ks[1:] != ks[:-1]).any(1)])
    for a, b in zip(st, np.r_[st[1:], len(ks)]):
        fi = bk.get((int(ks[a, 0]), int(ks[a, 1])))
        if fi is None:
            continue
        A = T[fi, 0]; e1 = T[fi, 1] - A; e2 = T[fi, 2] - A
        det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
        pi = order[a:b]
        for s in range(0, len(pi), 128):
            q = P[pi[s:s + 128]]
            dx = q[:, None, 0] - A[None, :, 0]; dy = q[:, None, 1] - A[None, :, 1]
            with np.errstate(divide="ignore", invalid="ignore"):
                u = (dx * e2[None, :, 1] - dy * e2[None, :, 0]) / det[None, :]; v = (dy * e1[None, :, 0] - dx * e1[None, :, 1]) / det[None, :]
            ins = (np.abs(det)[None, :] > 1e-9) & (u >= -1e-4) & (v >= -1e-4) & (u + v <= 1 + 1e-4)
            z = A[None, :, 2] + u * e1[None, :, 2] + v * e2[None, :, 2]
            for r, p in enumerate(pi[s:s + 128]):
                out[p] = np.sort(z[r][ins[r]])
    return out


# water volumes are rows of raster cells: put them back on that raster (top and bottom per cell)
_cs = float(np.median(WB[:, 1, 1] - WB[:, 0, 1])); _X0 = float(WB[:, 0, 0].min()); _Y0 = float(WB[:, 0, 1].min())
_nx = int(np.ceil((WB[:, 1, 0].max() - _X0) / _cs)) + 2; _ny = int(np.ceil((WB[:, 1, 1].max() - _Y0) / _cs)) + 2
WTOP = np.full((_ny, _nx), -np.inf); WBOT = np.full((_ny, _nx), np.inf)
for b in WB:
    i0 = int(np.floor((b[0, 0] - _X0) / _cs + 1e-6)); i1 = int(np.ceil((b[1, 0] - _X0) / _cs - 1e-6))
    j0 = int(np.floor((b[0, 1] - _Y0) / _cs + 1e-6)); j1 = int(np.ceil((b[1, 1] - _Y0) / _cs - 1e-6))
    WTOP[j0:j1, i0:i1] = np.maximum(WTOP[j0:j1, i0:i1], b[1, 2]); WBOT[j0:j1, i0:i1] = np.minimum(WBOT[j0:j1, i0:i1], b[0, 2])


def wet(x, y, z):
    """feet at (x, y, z) in or at water (also within 12 units of a water cell, so links keep off the edge)"""
    x = np.atleast_1d(np.asarray(x, np.float64)); y = np.atleast_1d(np.asarray(y, np.float64)); z = np.atleast_1d(np.asarray(z, np.float64))
    r = np.zeros(len(x), bool)
    for ox, oy in ((0, 0), (12, 0), (-12, 0), (0, 12), (0, -12)):
        i = np.floor((x + ox - _X0) / _cs).astype(np.int64); j = np.floor((y + oy - _Y0) / _cs).astype(np.int64)
        ok = (i >= 0) & (i < _nx) & (j >= 0) & (j < _ny)
        t = np.full(len(x), -np.inf); bt = np.full(len(x), np.inf)
        t[ok] = WTOP[j[ok], i[ok]]; bt[ok] = WBOT[j[ok], i[ok]]
        r |= (z < t + 8) & (z > bt - 64)
    return r


# ---- 1. candidate points
xs = np.arange(blo[0] + S / 2, bhi[0], S); ys = np.arange(blo[1] + S / 2, bhi[1], S)
GX, GY = np.meshgrid(xs, ys); G = np.stack([GX.ravel(), GY.ravel()], 1)
fl = column_hits(G, BU); ce = column_hits(G, BF)
nodes = []          # (gi, gj, x, y, z_floor)
for k in range(len(G)):
    for z in fl[k]:
        above = ce[k][(ce[k] > z + 4)]
        if len(above) and above[0] < z + HEAD:
            continue
        if z < -3000:
            continue
        if wet(G[k, 0], G[k, 1], z)[0]:
            continue
        nodes.append((k % len(xs), k // len(xs), G[k, 0], G[k, 1], z))
nodes = np.array(nodes, np.float64)
sys.path.insert(0, HERE)
import avoid_zones
_av = avoid_zones.avoided(nodes[:, 2], nodes[:, 3], nodes[:, 4])
nodes = nodes[~_av]
print("candidate points %d (%d in avoided zones left out)  %.0fs" % (len(nodes), int(_av.sum()), time.time() - t0))

# ---- 2. links
SAMP = 16.0
def seg_hits_tris(p0, p1):
    lo = np.minimum(p0, p1); hi = np.maximum(p0, p1)
    keys = [(gx, gy) for gx in range(int(np.floor(lo[0] / CELL)), int(np.floor(hi[0] / CELL)) + 1)
            for gy in range(int(np.floor(lo[1] / CELL)), int(np.floor(hi[1] / CELL)) + 1)]
    ids = [BA[k] for k in keys if k in BA]
    if not ids:
        return False
    fi = np.unique(np.concatenate(ids))
    A = T[fi, 0]; e1 = T[fi, 1] - A; e2 = T[fi, 2] - A
    d = p1 - p0
    h = np.cross(np.broadcast_to(d, e2.shape), e2); a = (e1 * h).sum(1)
    ok = np.abs(a) > 1e-9
    f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0)
    s = p0 - A; u = f * (s * h).sum(1)
    q = np.cross(s, e1); v = f * (q * d).sum(1); t = f * (e2 * q).sum(1)
    return bool((ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (t >= 0) & (t <= 1)).any())


def seg_hits_boxes(p0, p1):
    if not len(BOXES):
        return False
    d = p1 - p0
    with np.errstate(divide="ignore", invalid="ignore"):
        t1 = (BOXES[:, 0] - p0) / d; t2 = (BOXES[:, 1] - p0) / d
    tmin = np.where(d == 0, np.where((p0 >= BOXES[:, 0]) & (p0 <= BOXES[:, 1]), -np.inf, np.inf), np.minimum(t1, t2))
    tmax = np.where(d == 0, np.where((p0 >= BOXES[:, 0]) & (p0 <= BOXES[:, 1]), np.inf, -np.inf), np.maximum(t1, t2))
    lo = tmin.max(1); hi = tmax.min(1)
    return bool(((lo <= hi) & (hi >= 0) & (lo <= 1)).any())


idx_of = {}
for i, (gi, gj, x, y, z) in enumerate(nodes):
    idx_of.setdefault((int(gi), int(gj)), []).append(i)
pairs = []
for i, (gi, gj, x, y, z) in enumerate(nodes):
    for dgi, dgj in ((1, 0), (0, 1), (1, 1), (1, -1)):
        for j in idx_of.get((int(gi) + dgi, int(gj) + dgj), []):
            if abs(nodes[j, 4] - z) < S * 0.7:
                pairs.append((i, j))
print("candidate links %d  %.0fs" % (len(pairs), time.time() - t0))
# floors along all candidate links at once
segs = []
for i, j in pairs:
    a = nodes[i, 2:5]; b = nodes[j, 2:5]; L = np.hypot(*(b[:2] - a[:2])); m = max(2, int(np.ceil(L / SAMP)) + 1)
    segs.append(m)
tot = int(sum(segs)); SP = np.zeros((tot, 2)); EZ = np.zeros(tot); off = 0; starts = []
for (i, j), m in zip(pairs, segs):
    t = np.linspace(0, 1, m); a = nodes[i, 2:5]; b = nodes[j, 2:5]
    SP[off:off + m] = a[:2] + (b[:2] - a[:2]) * t[:, None]; EZ[off:off + m] = a[2] + (b[2] - a[2]) * t
    starts.append(off); off += m
SF = column_hits(SP, BU)
print("floors along links  %.0fs" % (time.time() - t0))
edges = []
for e, ((i, j), m, o) in enumerate(zip(pairs, segs, starts)):
    prev = nodes[i, 4]; ok = True; zs = []
    for k in range(m):
        f = SF[o + k]
        if not len(f):
            ok = False; break
        c = f[np.argmin(np.abs(f - prev))]
        if abs(c - prev) > STEP or abs(c - EZ[o + k]) > 64:
            ok = False; break
        prev = c; zs.append(c)
    if not ok or abs(prev - nodes[j, 4]) > 1.0 or wet(SP[o:o + m, 0], SP[o:o + m, 1], np.array(zs)).any():
        continue
    a = nodes[i, 2:5].copy(); b = nodes[j, 2:5].copy()
    blocked = False
    for hgt in (30.0, 56.0):
        if seg_hits_tris(a + [0, 0, hgt], b + [0, 0, hgt]) or seg_hits_boxes(a + [0, 0, hgt], b + [0, 0, hgt]):
            blocked = True; break
    if not blocked:
        edges.append((i, j))
print("walkable links %d of %d  %.0fs" % (len(edges), len(pairs), time.time() - t0))

# ---- 3. groups
adj = [[] for _ in range(len(nodes))]
for i, j in edges:
    adj[i].append(j); adj[j].append(i)
comp = -np.ones(len(nodes), np.int64); nc = 0
for s in range(len(nodes)):
    if comp[s] >= 0:
        continue
    dq = deque([s]); comp[s] = nc
    while dq:
        u = dq.popleft()
        for w in adj[u]:
            if comp[w] < 0:
                comp[w] = nc; dq.append(w)
    nc += 1
sizes = np.bincount(comp, minlength=nc)
keep = sizes[comp] >= MIN_GROUP
# groups that lie entirely at canal-bed level (dry canals bots cannot walk out of) are left out
_zmed = np.array([np.median(nodes[comp == c_, 4]) for c_ in range(nc)])
keep &= _zmed[comp] > float(rc.get("bed_level", -120.0))
# groups high above the ground (roofs reached only by force jumps) are left out
_tzn, _, _ = avoid_zones.terrain_z(nodes[:, 2], nodes[:, 3])
_hmed = np.array([np.median(nodes[comp == c_, 4] - _tzn[comp == c_]) for c_ in range(nc)])
keep &= _hmed[comp] < float(rc.get("max_group_height", 1200.0))
print("groups %d, kept %d with %d points" % (nc, int((sizes >= MIN_GROUP).sum()), int(keep.sum())))

# ---- 4. chain
visited = np.zeros(len(nodes), bool); chain = []
def path_between(a, b):
    """shortest walked path a -> b over links (BFS), without a"""
    prev = {a: -1}; dq = deque([a])
    while dq:
        u = dq.popleft()
        if u == b:
            break
        for w in adj[u]:
            if w not in prev:
                prev[w] = u; dq.append(w)
    p = []; u = b
    while u != a:
        p.append(u); u = prev[u]
    return p[::-1]
order = np.argsort(-sizes[comp] * 1e6 + np.arange(len(nodes)))       # biggest group first
groups_done = 0
for s in order:
    if not keep[s] or visited[s]:
        continue
    stack = [s]; last = None
    while stack:
        u = stack.pop()
        if visited[u]:
            continue
        if last is not None and u not in adj[last]:
            chain.extend(path_between(last, u))
        else:
            chain.append(u)
        visited[u] = True; last = u
        nb = [w for w in adj[u] if not visited[w] and keep[w]]
        nb.sort(key=lambda w: -sum(1 for x in adj[w] if not visited[x]))      # fewest unvisited last = taken first
        stack.extend(nb)
    groups_done += 1
    chain.append(-1)                          # group boundary
print("chain entries %d (points %d)  %.0fs" % (sum(1 for c in chain if c >= 0), int(visited.sum()), time.time() - t0))

# entries; a group boundary is a break: the bots' trail sum would join two groups, so the first point of the next
# group gets no "next" distance from the previous one (disttonext 0 on the last point of a group)
ent = []; brk = set()
for c in chain:
    if c < 0:
        if ent:
            brk.add(len(ent) - 1)
        continue
    ent.append(c)
if len(ent) > MAXWP:
    print("TOO MANY ENTRIES: %d > %d, use a larger spacing" % (len(ent), MAXWP)); sys.exit(2)
first_idx = {}
for k, c in enumerate(ent):
    first_idx.setdefault(c, k)
lines = []
for k, c in enumerate(ent):
    x, y, z = nodes[c, 2], nodes[c, 3], nodes[c, 4] + 24.0
    nb = sorted({first_idx[w] for w in adj[c] if w in first_idx and first_idx[w] != k})[:32]
    if k + 1 < len(ent) and k not in brk:
        dn = float(np.linalg.norm(nodes[ent[k + 1], 2:5] - nodes[c, 2:5]))
    else:
        dn = 0.0
    lines.append("%d 0 0.000000 (%.1f %.1f %.1f) { %s} %.1f\n" % (k, x, y, z, "".join("%d " % w for w in nb), dn))
data = "".join(lines).encode("ascii")
if len(data) >= 524288:
    print("FILE TOO LARGE %d" % len(data)); sys.exit(3)
os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
open(out_path, "wb").write(data)
rep = {"spacing": S, "candidate_points": len(nodes), "links": len(edges), "points_kept": int(keep.sum()), "entries": len(ent),
       "groups": groups_done, "bytes": len(data), "seconds": round(time.time() - t0, 1)}
json.dump(rep, open(out_path + ".json", "w"), indent=1)
print(json.dumps(rep))
