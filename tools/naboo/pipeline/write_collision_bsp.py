"""Own collision BSP writer: collision triangles -> RBSP version 1 (Jedi Academy), no map compiler involved.
  py write_collision_bsp.py <export_dir> <mapname> [--out <file.bsp>]
Reads  <export_dir>/collision/collision_tris.npy   world-space triangles in engine units, front faces outward
       naboo/q3base/base/maps/<mapname>.map         only for its point entities (worldspawn keys, spawns)
Writes naboo/q3base/base/maps/<mapname>_own.bsp     (or --out)

What goes into the file
  * coplanar neighbouring triangles are merged into convex polygons (at most MERGE_MAX_EXTENT units wide);
    flat ground and walls become a few large slabs instead of many triangles.
  * one convex brush per polygon: the polygon extruded THICKNESS units behind its plane. Sides are stored with
    the six axial box planes first, in the order -X +X -Y +Y -Z +Z, because the engine derives a brush's
    bounds from its first six sides (CM_BoundBrush); then top, bottom and edge planes (axial ones left out,
    the box planes are exact), then edge bevels (edge direction x axis, where the brush lies behind them),
    so box traces do not catch on slanted convex edges.
  * six slab brushes around everything with the sky shader (the map boundary) and six sky quads on their
    inner faces, so the renderer draws the sky box; every leaf references those six surfaces.
  * a kd-tree over the brush bounds: axial split planes at the median brush centre, a brush is referenced by
    every leaf it overlaps (brushes are never cut). One cluster, one area, no vis data.
  * no lightmaps, light grid or fogs.
The previous one-brush-per-triangle version is kept as write_collision_bsp_v1.py.
"""
import sys, os, re, struct, time, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
export_dir, mapname = sys.argv[1], sys.argv[2]
BASE = os.path.join(ROOT, "q3base", "base", "maps")
out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(BASE, mapname + "_own.bsp")
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
THICKNESS = float(cfg.get("bsp_writer", {}).get("thickness", 4.0))
LEAF_BRUSHES = int(cfg.get("bsp_writer", {}).get("leaf_brushes", 96))
MAX_DUP = float(cfg.get("bsp_writer", {}).get("max_duplication", 1.35))
MAX_DEPTH = int(cfg.get("bsp_writer", {}).get("max_depth", 40))
MIN_ALT = float(cfg.get("bsp_writer", {}).get("min_altitude", 0.05))
_w = cfg.get("bsp_writer", {})
MERGE = bool(_w.get("merge", True)); BEVELS = bool(_w.get("bevels", True))
PLANE_TOL = float(_w.get("plane_tolerance", 0.05)); LINE_TOL = float(_w.get("line_tolerance", 0.05))
AXIAL_EXTRUDE = bool(_w.get("axial_extrude", True))
MERGE_MAX_VERTS = int(_w.get("merge_max_corners", 12)); MERGE_MAX_EXTENT = float(_w.get("merge_max_extent", 1024.0))
t0 = time.time()

SURF_NODRAW_COL = 0x00200000; CONT_SOLID = 0x00008001      # as written by q3map2 for the same shaders
SURF_SKY = 0x00082000

tris = np.load(os.path.join(export_dir, "collision", "collision_tris.npy")).astype(np.float64)
N_IN = len(tris)
# opening doors (tools/build_doors.py): their static collision goes, each leaf comes back as a brush model
DOORS = None
_dj = os.path.join(export_dir, "doors.json")
if os.path.exists(_dj):
    DOORS = json.load(open(_dj))
    _t3 = tris.reshape(-1, 3, 3); _gone = np.zeros(len(_t3), bool)
    for _b in DOORS["clear_boxes"]:
        _lo = np.array(_b["mins"]); _hi = np.array(_b["maxs"])
        _gone |= ((_t3 >= _lo) & (_t3 <= _hi)).all((1, 2))
    tris = _t3[~_gone].reshape(tris.shape[0] - int(_gone.sum()), *tris.shape[1:])
    print("doors: %d leaves, %d static collision triangles removed around them" % (len(DOORS["doors"]), int(_gone.sum())))

# ---- weld corners to 1/16 unit and drop degenerate triangles
qv = np.round(tris * 16).astype(np.int64) + (1 << 20)
assert qv.min() >= 0 and qv.max() < (1 << 21)
vkey = (qv[:, :, 0] << 42) | (qv[:, :, 1] << 21) | qv[:, :, 2]
uqv, vinv = np.unique(vkey.ravel(), return_inverse=True)
vid = vinv.reshape(-1, 3)
POS = np.stack([(uqv >> 42) & 0x1FFFFF, (uqv >> 21) & 0x1FFFFF, uqv & 0x1FFFFF], 1).astype(np.float64)
POS = (POS - (1 << 20)) / 16.0
NV = len(POS)
a, b, c = POS[vid[:, 0]], POS[vid[:, 1]], POS[vid[:, 2]]
n = np.cross(b - a, c - a); ln = np.linalg.norm(n, axis=1)
e = np.stack([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)], 1)
ok = (ln / np.maximum(e.max(1), 1e-12)) > MIN_ALT           # drop degenerate slivers
vid = vid[ok]; n = n[ok] / ln[ok, None]
a, b, c = POS[vid[:, 0]], POS[vid[:, 1]], POS[vid[:, 2]]        # corners of the triangles that are used
NT = len(vid)
tri_d = (n * POS[vid[:, 0]]).sum(1)
print("triangles in %d, used %d (dropped %d thinner than %.2f units), welded corners %d   %.1fs" % (N_IN, NT, N_IN - NT, MIN_ALT, NV, time.time() - t0))

# ---- merge coplanar neighbours into convex polygons (what the map compiler does too)
loops = None
if MERGE:
    eu = vid; ev = vid[:, [1, 2, 0]]
    ek = (eu.astype(np.int64) * NV + ev).ravel(); ok_ = (ev.astype(np.int64) * NV + eu).ravel()
    order = np.argsort(ek, kind="stable"); sk = ek[order]
    p = np.searchsorted(sk, ok_); p[p >= len(sk)] = 0
    has = sk[p] == ok_
    nb_edge = order[p]                                        # flat index (tri*3+slot) of the opposite directed edge
    ti = np.repeat(np.arange(NT), 3); tj = nb_edge // 3; sj = nb_edge % 3
    opp = POS[vid[tj, (sj + 2) % 3]]
    cop = has & (ti != tj) & ((n[ti] * n[tj]).sum(1) > 0.99995) & (np.abs((n[ti] * opp).sum(1) - tri_d[ti]) < PLANE_TOL)
    active = np.zeros(NT, bool); active[ti[cop]] = True; active[tj[cop]] = True
    act = np.flatnonzero(active)
    print("coplanar neighbour pairs %d, triangles with one %d   %.1fs" % (cop.sum() // 2, len(act), time.time() - t0))
    P = [tuple(x) for x in POS.tolist()]
    NRM = n.tolist(); DD = tri_d.tolist()
    loops = {int(i): [int(x) for x in vid[i]] for i in act}
    owner = {}
    for i, lp in loops.items():
        k = len(lp)
        for t in range(k):
            owner[lp[t] * NV + lp[(t + 1) % k]] = i
    n_merge = 0

    def try_merge(pi, qi, u, v):
        lp = loops[pi]; lq = loops[qi]
        nx, ny, nz = NRM[pi]; d0 = DD[pi]
        qn = NRM[qi]
        if nx * qn[0] + ny * qn[1] + nz * qn[2] < 0.9999:
            return None
        for w in lq:
            pw = P[w]
            if abs(nx * pw[0] + ny * pw[1] + nz * pw[2] - d0) > PLANE_TOL:
                return None
        i = lp.index(u)
        if lp[(i + 1) % len(lp)] != v:
            return None
        j = lq.index(v)
        if lq[(j + 1) % len(lq)] != u:
            return None
        m = lp[i + 1:] + lp[:i + 1] + (lq[j + 1:] + lq[:j + 1])[1:-1]
        # the two loops may share more than one edge: remove the back-and-forth spikes that leaves
        changed = True
        while changed and len(m) >= 3:
            changed = False
            k = len(m)
            for t in range(k):
                if m[t - 1] == m[(t + 1) % k]:
                    drop = {t, (t + 1) % k}
                    m = [m[x] for x in range(k) if x not in drop]
                    changed = True
                    break
        k = len(m)
        if k < 3 or len(set(m)) != k:
            return None
        out = []
        for t in range(k):
            p0 = P[m[t - 1]]; p1 = P[m[t]]; p2 = P[m[(t + 1) % k]]
            ax, ay, az = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            bx, by, bz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
            cr = (ay * bz - az * by) * nx + (az * bx - ax * bz) * ny + (ax * by - ay * bx) * nz
            base = ((p2[0] - p0[0]) ** 2 + (p2[1] - p0[1]) ** 2 + (p2[2] - p0[2]) ** 2) ** 0.5
            if base < 1e-6:
                return None
            dev = cr / base                       # distance of the corner from the line through its neighbours
            if dev < -LINE_TOL:
                return None                       # reflex corner: not convex
            if dev <= LINE_TOL:
                if ax * bx + ay * by + az * bz <= 0:
                    return None
                continue                          # corner on a straight edge: drop it
            out.append(m[t])
        if len(out) < 3 or len(out) > MERGE_MAX_VERTS:
            return None
        xs = [P[w] for w in out]
        for axn in range(3):
            vals = [q_[axn] for q_ in xs]
            if max(vals) - min(vals) > MERGE_MAX_EXTENT:
                return None
        return out

    queue = list(loops.keys())
    while queue:
        pi = queue.pop()
        lp = loops.get(pi)
        if lp is None:
            continue
        again = True
        while again:
            again = False
            lp = loops[pi]; k = len(lp)
            for t in range(k):
                u = lp[t]; v = lp[(t + 1) % k]
                qi = owner.get(v * NV + u)
                if qi is None or qi == pi or qi not in loops:
                    continue
                m = try_merge(pi, qi, u, v)
                if m is None:
                    continue
                for old_i in (pi, qi):
                    ol = loops[old_i]; ko = len(ol)
                    for s in range(ko):
                        kk = ol[s] * NV + ol[(s + 1) % ko]
                        if owner.get(kk) == old_i:
                            del owner[kk]
                del loops[qi]
                loops[pi] = m
                for s in range(len(m)):
                    owner[m[s] * NV + m[(s + 1) % len(m)]] = pi
                n_merge += 1
                again = True
                break
    print("merges %d: %d triangles became %d polygons   %.1fs" % (n_merge, len(act), len(loops), time.time() - t0))

# ---- polygon groups by corner count
groups = {}                                                   # k -> (corner ids (M,k), normals (M,3))
if loops is None:
    groups[3] = (vid, n)
else:
    keep = ~active
    groups[3] = ([vid[keep]], [n[keep]])
    byk = {}
    for i, lp in loops.items():
        byk.setdefault(len(lp), ([], []))
        byk[len(lp)][0].append(lp); byk[len(lp)][1].append(i)
    for k, (ls, ids) in byk.items():
        arr = np.array(ls, np.int64); nn_ = n[np.array(ids)]
        if k == 3:
            groups[3][0].append(arr); groups[3][1].append(nn_)
        else:
            groups[k] = ([arr], [nn_])
    groups = {k: (np.concatenate(v[0]), np.concatenate(v[1])) for k, v in groups.items()}

AX3 = np.eye(3)


def build_group(ids, nrm):
    """Brushes for M convex k-gons: bounds and the non-axial planes (M,S,4) with a validity mask (M,S)."""
    M, k = ids.shape
    V = POS[ids]                                              # (M,k,3)
    d = (V * nrm[:, None, :]).sum(2).mean(1)
    # extrude against the dominant axis of the normal (as the map compiler does): the side faces then contain
    # an axis direction, which keeps the number of bevel planes low
    if AXIAL_EXTRUDE:
        mj = np.abs(nrm).argmax(1); r_ = np.arange(M)
        xd = np.zeros((M, 3)); xd[r_, mj] = np.sign(nrm[r_, mj])
    else:
        xd = nrm
    depth = THICKNESS * (xd * nrm).sum(1)
    Bk = V - xd[:, None, :] * THICKNESS
    A = np.concatenate([V, Bk], 1)                            # (M,2k,3)
    mn = A.min(1); mx = A.max(1)
    top = np.concatenate([nrm, d[:, None]], 1); bot = np.concatenate([-nrm, -(d[:, None] - depth[:, None])], 1)
    Vn = np.roll(V, -1, axis=1); ed = Vn - V                   # edge j runs from corner j to corner j+1
    en = np.cross(ed, xd[:, None, :]); en /= np.maximum(np.linalg.norm(en, axis=2, keepdims=True), 1e-12)
    epl = np.concatenate([en, (en * V).sum(2, keepdims=True)], 2)          # (M,k,4)
    fixed = np.concatenate([top[:, None], bot[:, None], epl], 1)           # (M,2+k,4)
    fvalid = np.abs(fixed[:, :, :3]).max(2) < 0.9999999        # axial ones are already among the six box planes
    if not BEVELS:
        return mn, mx, fixed, fvalid
    # edge bevels: for every edge direction (k polygon edges, plus the extrusion direction) and every axis,
    # the plane through that edge with normal edge x axis, where the whole brush lies behind it
    D = np.concatenate([ed / np.maximum(np.linalg.norm(ed, axis=2, keepdims=True), 1e-12), xd[:, None, :]], 1)   # (M,k+1,3)
    cn = np.cross(D[:, :, None, :], AX3[None, None, :, :])    # (M,k+1,3,3)
    cl = np.linalg.norm(cn, axis=3, keepdims=True)
    good = (cl[..., 0] > 0.01)
    cn = cn / np.maximum(cl, 1e-12)
    cn = np.stack([cn, -cn], 3)                               # (M,k+1,3,2,3)
    good = np.repeat(good[..., None], 2, axis=3).reshape(M, -1)
    C = cn.reshape(M, -1, 3)                                  # (M,(k+1)*6,3)
    dots = np.einsum("mcx,mvx->mcv", C, A)                    # (M,C,2k)
    dist = dots.max(2)
    at = dots >= dist[:, :, None] - 0.02                      # corners on the plane
    nC = C.shape[1]
    on_edge = np.zeros((M, nC), bool)
    for j in range(k + 1):
        sl = slice(j * 6, j * 6 + 6)
        if j < k:                                             # top edge j or bottom edge j lies in the plane
            jn = (j + 1) % k
            on_edge[:, sl] = (at[:, sl, j] & at[:, sl, jn]) | (at[:, sl, k + j] & at[:, sl, k + jn])
        else:                                                 # a side edge (top corner i to bottom corner i)
            on_edge[:, sl] = (at[:, sl, :k] & at[:, sl, k:]).any(2)
    bvalid = good & on_edge & (np.abs(C).max(2) < 0.9999)
    # drop bevels equal to a plane already present (fixed sides, earlier bevels)
    allN = np.concatenate([fixed[:, :, :3], C], 1)            # (M,2+k+nC,3)
    allV = np.concatenate([np.ones((M, 2 + k), bool), bvalid], 1)
    dd = np.einsum("mcx,mpx->mcp", C, allN) > 0.9999          # (M,nC,S)
    S = allN.shape[1]
    earlier = (np.arange(S)[None, :] < (2 + k + np.arange(nC))[:, None])   # (nC,S)
    dup = (dd & earlier[None] & allV[:, None, :]).any(2)
    bvalid &= ~dup
    bpl = np.concatenate([C, dist[:, :, None]], 2)
    return mn, mx, np.concatenate([fixed, bpl], 1), np.concatenate([fvalid, bvalid], 1)


g_min = []; g_max = []; g_planes = []; g_counts = []; n_bevel = 0; poly_hist = {}
for k in sorted(groups):
    ids, nrm = groups[k]
    poly_hist[k] = len(ids)
    for s0 in range(0, len(ids), 20000):
        mn_, mx_, pl_, va_ = build_group(ids[s0:s0 + 20000], nrm[s0:s0 + 20000])
        g_min.append(mn_); g_max.append(mx_); g_planes.append(pl_[va_].astype(np.float32)); g_counts.append(va_.sum(1))
        n_bevel += int(va_[:, 2 + k:].sum())
bmin = np.concatenate(g_min); bmax = np.concatenate(g_max)
nonax = np.concatenate(g_planes); nonax_count = np.concatenate(g_counts).astype(np.int64)
# water volumes (tools/build_collision_terrain.py): axis-aligned boxes with water contents, after the solid brushes
NWATER = 0
WB = np.zeros((0, 2, 3))
_wb = os.path.join(export_dir, "collision", "water_boxes.npy")
if os.path.exists(_wb) and bool(_w.get("water", True)):
    WB = np.load(_wb).astype(np.float64)
    if len(WB):
        NWATER = len(WB)
        bmin = np.concatenate([bmin, WB[:, 0]]); bmax = np.concatenate([bmax, WB[:, 1]])
        nonax_count = np.concatenate([nonax_count, np.zeros(NWATER, np.int64)])
NPOLY = len(bmin)
print("polygons by corner count %s; bevel planes %d (%.2f per brush)   %.1fs" % (poly_hist, n_bevel, n_bevel / NPOLY, time.time() - t0))

# hull: six slabs around everything
allmin = bmin.min(0); allmax = bmax.max(0)
lo = np.floor((allmin - 64.0) / 64) * 64; hi = np.ceil((allmax + np.array([64.0, 64.0, 2048.0])) / 64) * 64
T = 16.0
hull = [((lo[0] - T, lo[1], lo[2]), (lo[0], hi[1], hi[2])), ((hi[0], lo[1], lo[2]), (hi[0] + T, hi[1], hi[2])),
        ((lo[0], lo[1] - T, lo[2]), (hi[0], lo[1], hi[2])), ((lo[0], hi[1], lo[2]), (hi[0], hi[1] + T, hi[2])),
        ((lo[0], lo[1], lo[2] - T), (hi[0], hi[1], lo[2])), ((lo[0], lo[1], hi[2]), (hi[0], hi[1], hi[2] + T))]
hmin = np.array([h[0] for h in hull]); hmax = np.array([h[1] for h in hull])
NB = NPOLY + 6
BMIN = np.concatenate([bmin, hmin]).astype(np.float32).astype(np.float64); BMAX = np.concatenate([bmax, hmax]).astype(np.float32).astype(np.float64)

# ---- axial box planes, shared by exact value: the first six sides of every brush, order -X +X -Y +Y -Z +Z
keys = []
for s in range(6):
    axis = s // 2
    dv_ = (-BMIN[:, axis]) if s % 2 == 0 else BMAX[:, axis]
    keys.append((np.int64(s) << 32) | dv_.astype(np.float32).view(np.uint32).astype(np.int64))
uq, inv = np.unique(np.concatenate(keys), return_inverse=True)
n_ax = len(uq)
ax_tab = np.zeros((n_ax, 4), np.float32)
s_of = (uq >> 32).astype(np.int64)
ax_tab[np.arange(n_ax), s_of // 2] = np.where(s_of % 2 == 0, -1.0, 1.0)
ax_tab[:, 3] = (uq & 0xFFFFFFFF).astype(np.uint32).view(np.float32)
ax_planes = inv.reshape(6, NB).T                                  # (NB,6) indexes into ax_tab
plane_lump = np.concatenate([ax_tab, nonax])
NP = len(plane_lump)

# ---- brush sides and brushes
SH_COL, SH_SKY, SH_WATER = 0, 1, 2
CONT_WATER = 0x00000004
cnt = np.concatenate([6 + nonax_count, np.full(6, 6, np.int64)])
first = np.concatenate([[0], np.cumsum(cnt)[:-1]])
side_lump = np.zeros(int(cnt.sum()), dtype=[("plane", "<i4"), ("shader", "<i4"), ("surf", "<i4")])
side_lump["plane"][(first[:, None] + np.arange(6)[None, :]).ravel()] = ax_planes.ravel()
tot_na = int(nonax_count.sum())
na_before = np.concatenate([[0], np.cumsum(nonax_count)[:-1]])
pos_na = np.repeat(first[:NPOLY] + 6, nonax_count) + (np.arange(tot_na) - np.repeat(na_before, nonax_count))
side_lump["plane"][pos_na] = n_ax + np.arange(tot_na)
side_lump["shader"] = SH_COL; side_lump["shader"][first[NPOLY]:] = SH_SKY
if NWATER:
    side_lump["shader"][first[NPOLY - NWATER]:first[NPOLY]] = SH_WATER
side_lump["surf"] = -1
brush_lump = np.zeros(NB, dtype=[("first", "<i4"), ("num", "<i4"), ("shader", "<i4")])
brush_lump["first"] = first; brush_lump["num"] = cnt; brush_lump["shader"] = SH_COL; brush_lump["shader"][NPOLY:] = SH_SKY
if NWATER:
    brush_lump["shader"][NPOLY - NWATER:NPOLY] = SH_WATER
print("brushes %d, sides %d (%.2f per brush), planes %d (%d axial shared)   %.1fs" % (NB, len(side_lump), len(side_lump) / NB, NP, n_ax, time.time() - t0))

# ---- kd-tree over brush bounds
node_plane = []; node_child = []; node_box = []
leaf_box = []; leaf_first = []; leaf_num = []; leaf_brushes = []
split_tab = {}; extra_planes = []


def split_plane(axis, dist):
    k = (axis, dist)
    i = split_tab.get(k)
    if i is None:
        nrm = [0.0, 0.0, 0.0]; nrm[axis] = 1.0
        i = NP + len(extra_planes); extra_planes.append((nrm[0], nrm[1], nrm[2], float(dist))); split_tab[k] = i
    return i


def make_leaf(idx, mn, mx):
    leaf_box.append((mn, mx)); leaf_first.append(sum(len(x) for x in leaf_brushes) if False else None)
    leaf_brushes.append(idx); leaf_num.append(len(idx))
    return -(len(leaf_box) - 1) - 1


CEN = (BMIN + BMAX) * 0.5
root_mn = (lo - T).astype(np.float64); root_mx = (hi + T).astype(np.float64)
# iterative build: stack of (brush index array, mins, maxs, depth, parent node, child slot)
stack = [(np.arange(NB), root_mn, root_mx, 0, -1, 0)]
root_ref = None
while stack:
    idx, mn, mx, depth, parent, slot = stack.pop()
    ref = None
    if len(idx) > LEAF_BRUSHES and depth < MAX_DEPTH:
        done = False
        for axis in np.argsort(-(mx - mn)):
            axis = int(axis)
            d = float(np.round(np.median(CEN[idx, axis])))
            if d <= mn[axis] + 1 or d >= mx[axis] - 1:
                continue
            front = idx[BMAX[idx, axis] > d - 0.5]; backi = idx[BMIN[idx, axis] < d + 0.5]
            if len(front) + len(backi) > len(idx) * MAX_DUP:
                continue                         # too many brushes straddle this plane: try another axis
            ni = len(node_plane)
            node_plane.append(split_plane(axis, d)); node_child.append([0, 0]); node_box.append((mn, mx))
            fmn = mn.copy(); fmn[axis] = d; bmx = mx.copy(); bmx[axis] = d
            stack.append((front, fmn, mx, depth + 1, ni, 0)); stack.append((backi, mn, bmx, depth + 1, ni, 1))
            ref = ni; done = True
            break
        if not done:
            ref = make_leaf(idx, mn, mx)
    else:
        ref = make_leaf(idx, mn, mx)
    if parent < 0:
        root_ref = ref
    else:
        node_child[parent][slot] = ref
assert root_ref == 0, "the root must be node 0"
NL = len(leaf_box); NN = len(node_plane)
lb_counts = np.array(leaf_num, np.int64)
lb_first = np.concatenate([[0], np.cumsum(lb_counts)[:-1]])
leafbrush_lump = np.concatenate(leaf_brushes).astype("<i4")
print("tree: %d nodes, %d leaves, %d leaf-brush refs (%.2f per brush); brushes per leaf median %d p99 %d max %d   %.1fs" % (
    NN, NL, len(leafbrush_lump), len(leafbrush_lump) / NB, int(np.median(lb_counts)), int(np.percentile(lb_counts, 99)), int(lb_counts.max()), time.time() - t0))

plane_lump = np.concatenate([plane_lump, np.array(extra_planes, np.float32).reshape(-1, 4)])
node_lump = np.zeros(NN, dtype=[("plane", "<i4"), ("children", "<i4", 2), ("mins", "<i4", 3), ("maxs", "<i4", 3)])
node_lump["plane"] = node_plane; node_lump["children"] = np.array(node_child, np.int32)
node_lump["mins"] = np.floor(np.array([b_[0] for b_ in node_box])); node_lump["maxs"] = np.ceil(np.array([b_[1] for b_ in node_box]))
NSKY = 6
leaf_lump = np.zeros(NL, dtype=[("cluster", "<i4"), ("area", "<i4"), ("mins", "<i4", 3), ("maxs", "<i4", 3),
                                ("firstSurf", "<i4"), ("numSurf", "<i4"), ("firstBrush", "<i4"), ("numBrush", "<i4")])
leaf_lump["mins"] = np.floor(np.array([b_[0] for b_ in leaf_box])); leaf_lump["maxs"] = np.ceil(np.array([b_[1] for b_ in leaf_box]))
leaf_lump["firstSurf"] = 0; leaf_lump["numSurf"] = NSKY            # every leaf shares the same six sky references
leaf_lump["firstBrush"] = lb_first; leaf_lump["numBrush"] = lb_counts
leafsurf_lump = np.arange(NSKY, dtype="<i4")

# ---- sky quads on the inner faces of the hull
dv = np.zeros(24, dtype=[("xyz", "<f4", 3), ("st", "<f4", 2), ("lm", "<f4", (4, 2)), ("normal", "<f4", 3), ("color", "u1", (4, 4))])
surf = np.zeros(6, dtype=[("shader", "<i4"), ("fog", "<i4"), ("type", "<i4"), ("firstVert", "<i4"), ("numVerts", "<i4"), ("firstIndex", "<i4"),
                          ("numIndexes", "<i4"), ("lmStyles", "u1", 4), ("vStyles", "u1", 4), ("lmNum", "<i4", 4), ("lmX", "<i4", 4), ("lmY", "<i4", 4),
                          ("lmW", "<i4"), ("lmH", "<i4"), ("lmOrigin", "<f4", 3), ("lmVecs", "<f4", (3, 3)), ("pw", "<i4"), ("ph", "<i4")])
assert surf.dtype.itemsize == 148 and dv.dtype.itemsize == 80
faces = [(0, lo[0], 1.0), (0, hi[0], -1.0), (1, lo[1], 1.0), (1, hi[1], -1.0), (2, lo[2], 1.0), (2, hi[2], -1.0)]
for i, (axis, d, sgn) in enumerate(faces):
    u, v = [x for x in range(3) if x != axis]
    q = []
    for cu, cv in ((lo[u], lo[v]), (hi[u], lo[v]), (hi[u], hi[v]), (lo[u], hi[v])):
        p = [0.0, 0.0, 0.0]; p[axis] = d; p[u] = cu; p[v] = cv; q.append(p)
    dv["xyz"][i * 4:i * 4 + 4] = q
    nrm = [0.0, 0.0, 0.0]; nrm[axis] = sgn; dv["normal"][i * 4:i * 4 + 4] = nrm
    dv["color"][i * 4:i * 4 + 4] = 255
    surf["shader"][i] = SH_SKY; surf["fog"][i] = -1; surf["type"][i] = 1        # MST_PLANAR
    surf["firstVert"][i] = i * 4; surf["numVerts"][i] = 4; surf["firstIndex"][i] = i * 6; surf["numIndexes"][i] = 6
    surf["lmStyles"][i] = 255; surf["vStyles"][i] = (0, 255, 255, 255); surf["lmNum"][i] = -1
    surf["lmVecs"][i][2] = nrm
dv["lm"] = 0
index_lump = np.tile(np.array([0, 1, 2, 0, 2, 3], "<i4"), 6)

# ---- shaders, model, entities
shader_lump = np.zeros(3, dtype=[("name", "S64"), ("surf", "<i4"), ("cont", "<i4")])
shader_lump[0] = (b"textures/naboo_sys/col", SURF_NODRAW_COL, CONT_SOLID)
shader_lump[1] = (b"textures/naboo_sys/sky", SURF_SKY, CONT_SOLID)
shader_lump[2] = (b"textures/naboo_sys/water", 0, CONT_WATER)
model_lump = np.zeros(1, dtype=[("mins", "<f4", 3), ("maxs", "<f4", 3), ("firstSurf", "<i4"), ("numSurf", "<i4"), ("firstBrush", "<i4"), ("numBrush", "<i4")])
model_lump["mins"][0] = lo - T; model_lump["maxs"][0] = hi + T; model_lump["numSurf"][0] = NSKY; model_lump["numBrush"][0] = NB

ent_text = ""
mp = os.path.join(BASE, mapname + ".map")
if os.path.exists(mp):
    txt = open(mp).read()
    # point entities and worldspawn keys only: drop brush blocks and the misc_model entities the compiler used
    depth = 0; cur = []; ents = []
    for line in txt.splitlines():
        s_ = line.strip()
        if s_ == "{":
            depth += 1
            if depth == 1:
                cur = []
            continue
        if s_ == "}":
            if depth == 1:
                ents.append(cur)
            depth -= 1
            continue
        if depth == 1 and s_.startswith('"'):
            cur.append(s_)
    n_wet_spawn = 0
    for kv in ents:
        if any('"classname" "misc_model"' in x for x in kv):
            continue
        if any('"classname" "info_player_' in x for x in kv):
            # a spawn point under water or without ground stood on terrain that is now river bed
            org_ = next((x for x in kv if x.startswith('"origin"')), None)
            if org_:
                o_ = np.array([float(v) for v in org_.split('"')[3].split()])
                in_water = bool((np.all(WB[:, 0] <= o_, 1) & np.all(WB[:, 1] >= o_, 1)).any())
                # ground: an upward-facing collision triangle under the origin, at most 96 units below it
                m_ = (n[:, 2] > 0.7) & (np.minimum(np.minimum(a[:, 0], b[:, 0]), c[:, 0]) <= o_[0]) & (np.maximum(np.maximum(a[:, 0], b[:, 0]), c[:, 0]) >= o_[0])                      & (np.minimum(np.minimum(a[:, 1], b[:, 1]), c[:, 1]) <= o_[1]) & (np.maximum(np.maximum(a[:, 1], b[:, 1]), c[:, 1]) >= o_[1])
                zs_ = a[m_, 2] - (n[m_, 0] * (o_[0] - a[m_, 0]) + n[m_, 1] * (o_[1] - a[m_, 1])) / n[m_, 2]
                grounded = bool(((zs_ <= o_[2] + 8.0) & (zs_ >= o_[2] - 96.0)).any())
                if in_water or not grounded:
                    n_wet_spawn += 1; continue
        ent_text += "{\n" + "\n".join(kv) + "\n}\n"
n_spawn = len(re.findall(r'"classname" "info_player_', ent_text))
n_doors = 0
if DOORS:
    # one brush per leaf, in the leaf's own coordinates (the entity's origin places it): the six axial bounding
    # planes first, as the engine expects, then the planes of the leaf's oriented box that are not axial
    pl_new = []; sd_new = []; br_new = []; md_new = []
    for dr in DOORS["doors"]:
        ax_ = np.array(dr["axes"], np.float64); lo_ = np.array(dr["lo"]); hi_ = np.array(dr["hi"])
        corners = np.array([[x_, y_, z_] for x_ in (lo_[0], hi_[0]) for y_ in (lo_[1], hi_[1]) for z_ in (lo_[2], hi_[2])]) @ ax_
        mn_ = corners.min(0); mx_ = corners.max(0)
        planes_ = [((-1, 0, 0), -mn_[0]), ((1, 0, 0), mx_[0]), ((0, -1, 0), -mn_[1]), ((0, 1, 0), mx_[1]), ((0, 0, -1), -mn_[2]), ((0, 0, 1), mx_[2])]
        for k_ in range(3):
            if np.abs(ax_[k_]).max() < 0.9999:
                planes_.append((tuple(ax_[k_]), hi_[k_])); planes_.append((tuple(-ax_[k_]), -lo_[k_]))
        f_ = len(side_lump) + len(sd_new)
        for nn_, dd_ in planes_:
            sd_new.append((len(plane_lump) + len(pl_new), SH_COL, -1)); pl_new.append((nn_[0], nn_[1], nn_[2], dd_))
        md_new.append((mn_, mx_, len(brush_lump) + len(br_new))); br_new.append((f_, len(planes_), SH_COL))
        ent_text += "{\n" + "\n".join(dr["entity"] + ['"model" "*%d"' % (1 + n_doors)]) + "\n}\n"
        n_doors += 1
    plane_lump = np.concatenate([plane_lump, np.array(pl_new, np.float32)])
    side_lump = np.concatenate([side_lump, np.array(sd_new, dtype=side_lump.dtype)])
    brush_lump = np.concatenate([brush_lump, np.array(br_new, dtype=brush_lump.dtype)])
    md2 = np.zeros(len(md_new), dtype=model_lump.dtype)
    for k_, (mn_, mx_, fb_) in enumerate(md_new):
        md2["mins"][k_] = mn_; md2["maxs"][k_] = mx_; md2["firstBrush"][k_] = fb_; md2["numBrush"][k_] = 1
    model_lump = np.concatenate([model_lump, md2])
if not ent_text:
    ent_text = '{\n"classname" "worldspawn"\n}\n'
ent_lump = ent_text.encode("ascii") + b"\0"

# ---- write
lumps = [ent_lump, shader_lump.tobytes(), plane_lump.astype("<f4").tobytes(), node_lump.tobytes(), leaf_lump.tobytes(), leafsurf_lump.tobytes(),
         leafbrush_lump.tobytes(), model_lump.tobytes(), brush_lump.tobytes(), side_lump.tobytes(), dv.tobytes(), index_lump.tobytes(),
         b"", surf.tobytes(), b"", b"", b"", b""]
ofs = 8 + 18 * 8
dirent = b""
for L in lumps:
    dirent += struct.pack("<ii", ofs, len(L)); ofs += (len(L) + 3) & ~3
with open(out_path, "wb") as f:
    f.write(b"RBSP" + struct.pack("<i", 1) + dirent)
    for L in lumps:
        f.write(L); f.write(b"\0" * (((len(L) + 3) & ~3) - len(L)))
rep = {"seconds": round(time.time() - t0, 1), "file": out_path, "bytes": os.path.getsize(out_path), "triangles_in": int(N_IN), "triangles_used": int(NT), "water_brushes": int(NWATER), "spawns_dropped_in_water_or_without_ground": int(n_wet_spawn) if "n_wet_spawn" in globals() else 0, "brushes": int(NB), "merge": MERGE, "bevels": BEVELS, "bevel_planes": int(n_bevel), "polygons_by_corners": {str(k): int(v) for k, v in poly_hist.items()},
       "sides": int(len(side_lump)), "planes": int(len(plane_lump)), "nodes": int(NN), "leaves": int(NL), "leaf_brush_refs": int(len(leafbrush_lump)),
       "brushes_per_leaf_median": int(np.median(lb_counts)), "brushes_per_leaf_p99": int(np.percentile(lb_counts, 99)), "brushes_per_leaf_max": int(lb_counts.max()),
       "spawns": n_spawn, "thickness": THICKNESS, "leaf_brushes_target": LEAF_BRUSHES}
json.dump(rep, open(os.path.join(export_dir, "collision", "own_bsp_%s.json" % mapname), "w"), indent=1)
print(json.dumps(rep, indent=1))
