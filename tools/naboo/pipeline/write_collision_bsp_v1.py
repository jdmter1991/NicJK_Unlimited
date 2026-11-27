"""Own collision BSP writer: collision triangles -> RBSP version 1 (Jedi Academy), no map compiler involved.
  py write_collision_bsp.py <export_dir> <mapname> [--out <file.bsp>]
Reads  <export_dir>/collision/collision_tris.npy   world-space triangles in engine units, front faces outward
       naboo/q3base/base/maps/<mapname>.map         only for its point entities (worldspawn keys, spawns)
Writes naboo/q3base/base/maps/<mapname>_own.bsp     (or --out)

What goes into the file
  * one convex brush per triangle: the triangle extruded THICKNESS units behind its plane, clipped to its
    bounding box. Sides are stored with the six axial box planes first, in the order -X +X -Y +Y -Z +Z,
    because the engine derives a brush's bounds from its first six sides (CM_BoundBrush).
  * six slab brushes around everything with the sky shader (the map boundary) and six sky quads on their
    inner faces, so the renderer draws the sky box; every leaf references those six surfaces.
  * a kd-tree over the brush bounds: axial split planes at the median brush centre, a brush is referenced by
    every leaf it overlaps (brushes are never cut). One cluster, one area, no vis data.
  * no lightmaps, light grid or fogs.
Not done here (the map compiler does it): edge bevel planes. Box traces therefore meet sharp convex edges a
little early; point traces are exact.
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
t0 = time.time()

SURF_NODRAW_COL = 0x00200000; CONT_SOLID = 0x00008001      # as written by q3map2 for the same shaders
SURF_SKY = 0x00082000

tris = np.load(os.path.join(export_dir, "collision", "collision_tris.npy")).astype(np.float64)
a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
n = np.cross(b - a, c - a); ln = np.linalg.norm(n, axis=1)
e = np.stack([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)], 1)
ok = (ln / np.maximum(e.max(1), 1e-12)) > MIN_ALT           # drop degenerate slivers
a, b, c, n = a[ok], b[ok], c[ok], (n[ok] / ln[ok, None])
NT = len(a)
print("triangles in %d, used %d (dropped %d thinner than %.2f units)" % (len(tris), NT, len(tris) - NT, MIN_ALT))

# ---- brushes: bounds from the six prism corners
back = np.stack([a - n * THICKNESS, b - n * THICKNESS, c - n * THICKNESS], 1)
pts = np.concatenate([np.stack([a, b, c], 1), back], 1)
bmin = pts.min(1) - 0.125; bmax = pts.max(1) + 0.125

# hull: six slabs around everything
allmin = bmin.min(0); allmax = bmax.max(0)
lo = np.floor((allmin - 64.0) / 64) * 64; hi = np.ceil((allmax + np.array([64.0, 64.0, 2048.0])) / 64) * 64
T = 16.0
hull = [((lo[0] - T, lo[1], lo[2]), (lo[0], hi[1], hi[2])), ((hi[0], lo[1], lo[2]), (hi[0] + T, hi[1], hi[2])),
        ((lo[0], lo[1] - T, lo[2]), (hi[0], lo[1], hi[2])), ((lo[0], hi[1], lo[2]), (hi[0], hi[1] + T, hi[2])),
        ((lo[0], lo[1], lo[2] - T), (hi[0], hi[1], lo[2])), ((lo[0], lo[1], hi[2]), (hi[0], hi[1], hi[2] + T))]
hmin = np.array([h[0] for h in hull]); hmax = np.array([h[1] for h in hull])
NB = NT + 6
BMIN = np.concatenate([bmin, hmin]); BMAX = np.concatenate([bmax, hmax])

# ---- planes. Axial planes are shared (keyed by axis, sign and distance); the others are written as they are.
ax_key = {}; planes = []


def axial(axis, sign, dist):
    k = (axis, sign, round(float(dist) * 8))
    i = ax_key.get(k)
    if i is None:
        nrm = [0.0, 0.0, 0.0]; nrm[axis] = float(sign)
        i = len(planes); planes.append((nrm[0], nrm[1], nrm[2], round(float(dist) * 8) / 8.0)); ax_key[k] = i
    return i


# vectorised axial plane indexes: unique over (axis, sign, quantised dist)
ax_planes = np.empty((NB, 6), np.int64)
keys = []; vals = []
for s in range(6):
    axis = s // 2; sign = -1 if s % 2 == 0 else 1
    d = (-BMIN[:, axis]) if sign < 0 else BMAX[:, axis]
    q = np.round(d * 8).astype(np.int64)
    keys.append(q * 6 + s); vals.append((axis, sign))
allk = np.concatenate(keys)
uq, inv = np.unique(allk, return_inverse=True)
ax_tab = np.zeros((len(uq), 4), np.float32)
s_of = (uq % 6).astype(np.int64); q_of = (uq - s_of) // 6
ax_tab[np.arange(len(uq)), s_of // 2] = np.where(s_of % 2 == 0, -1.0, 1.0)
ax_tab[:, 3] = q_of / 8.0
ax_planes = inv.reshape(6, NB).T                                 # (NB, 6) indexes into ax_tab
n_ax = len(uq)

# non-axial planes of the triangle brushes: top, bottom, three edges (5 per brush)
top = np.concatenate([n, (n * a).sum(1, keepdims=True)], 1)
bot = np.concatenate([-n, -((n * a).sum(1, keepdims=True) - THICKNESS)], 1)
edges = []
for p0, p1 in ((a, b), (b, c), (c, a)):
    en = np.cross(p1 - p0, n); en /= np.maximum(np.linalg.norm(en, axis=1, keepdims=True), 1e-12)
    edges.append(np.concatenate([en, (en * p0).sum(1, keepdims=True)], 1))
tri_planes = np.stack([top, bot] + edges, 1).astype(np.float32)   # (NT, 5, 4)
plane_lump = np.concatenate([ax_tab, tri_planes.reshape(-1, 4)])
NP = len(plane_lump)

# ---- brush sides and brushes
sides_tri = np.empty((NT, 11), np.int32)
sides_tri[:, :6] = ax_planes[:NT]
sides_tri[:, 6:] = n_ax + np.arange(NT * 5, dtype=np.int64).reshape(NT, 5)
SH_COL, SH_SKY = 0, 1
side_lump = np.zeros(NT * 11 + 36, dtype=[("plane", "<i4"), ("shader", "<i4"), ("surf", "<i4")])
side_lump["plane"][:NT * 11] = sides_tri.ravel(); side_lump["shader"][:NT * 11] = SH_COL
side_lump["plane"][NT * 11:] = ax_planes[NT:].ravel(); side_lump["shader"][NT * 11:] = SH_SKY
side_lump["surf"] = -1
brush_lump = np.zeros(NB, dtype=[("first", "<i4"), ("num", "<i4"), ("shader", "<i4")])
brush_lump["first"][:NT] = np.arange(NT) * 11; brush_lump["num"][:NT] = 11; brush_lump["shader"][:NT] = SH_COL
brush_lump["first"][NT:] = NT * 11 + np.arange(6) * 6; brush_lump["num"][NT:] = 6; brush_lump["shader"][NT:] = SH_SKY
print("brushes %d, sides %d, planes %d (%d axial shared)   %.1fs" % (NB, len(side_lump), NP, n_ax, time.time() - t0))

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
shader_lump = np.zeros(2, dtype=[("name", "S64"), ("surf", "<i4"), ("cont", "<i4")])
shader_lump[0] = (b"textures/naboo_sys/col", SURF_NODRAW_COL, CONT_SOLID)
shader_lump[1] = (b"textures/naboo_sys/sky", SURF_SKY, CONT_SOLID)
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
    for kv in ents:
        if any('"classname" "misc_model"' in x for x in kv):
            continue
        ent_text += "{\n" + "\n".join(kv) + "\n}\n"
n_spawn = len(re.findall(r'"classname" "info_player_', ent_text))
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
rep = {"seconds": round(time.time() - t0, 1), "file": out_path, "bytes": os.path.getsize(out_path), "triangles_in": int(len(tris)), "brushes": int(NB),
       "sides": int(len(side_lump)), "planes": int(len(plane_lump)), "nodes": int(NN), "leaves": int(NL), "leaf_brush_refs": int(len(leafbrush_lump)),
       "brushes_per_leaf_median": int(np.median(lb_counts)), "brushes_per_leaf_p99": int(np.percentile(lb_counts, 99)), "brushes_per_leaf_max": int(lb_counts.max()),
       "spawns": n_spawn, "thickness": THICKNESS, "leaf_brushes_target": LEAF_BRUSHES}
json.dump(rep, open(os.path.join(export_dir, "collision", "own_bsp_%s.json" % mapname), "w"), indent=1)
print(json.dumps(rep, indent=1))
