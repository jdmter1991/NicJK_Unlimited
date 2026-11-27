"""RBSP (Jedi Academy) lump statistics. Read-only; takes the BSP path as argv[1]."""
import sys, struct, collections
import numpy as np

path = sys.argv[1]
mm = np.memmap(path, dtype=np.uint8, mode="r")
ident = bytes(mm[:4]); version = struct.unpack_from("<i", mm, 4)[0]
print("ident", ident, "version", version, "filesize", mm.size)

NAMES = ["entities", "shaders", "planes", "nodes", "leafs", "leafsurfaces", "leafbrushes",
         "models", "brushes", "brushsides", "drawverts", "drawindexes", "fogs", "surfaces",
         "lightmaps", "lightgrid", "visibility", "lightarray"]
SIZES = {"entities": 1, "shaders": 72, "planes": 16, "nodes": 36, "leafs": 48, "leafsurfaces": 4,
         "leafbrushes": 4, "models": 40, "brushes": 12, "brushsides": 12, "drawverts": 80,
         "drawindexes": 4, "fogs": 72, "surfaces": 148, "lightmaps": 128 * 128 * 3,
         "lightgrid": 30, "visibility": 1, "lightarray": 2}
lumps = {}
print(f"\n{'lump':14} {'offset':>12} {'length':>12} {'elemsize':>8} {'count':>12} rem")
for i, n in enumerate(NAMES):
    off, ln = struct.unpack_from("<ii", mm, 8 + i * 8)
    lumps[n] = (off, ln)
    print(f"{n:14} {off:12,} {ln:12,} {SIZES[n]:8} {ln // SIZES[n]:12,} {ln % SIZES[n]}")
print("sum of lumps", sum(l for _, l in lumps.values()))

def lump(n, dtype):
    off, ln = lumps[n]
    return np.frombuffer(mm, dtype=dtype, count=ln // np.dtype(dtype).itemsize, offset=off)

# ---- shaders
sh = lump("shaders", np.dtype([("name", "S64"), ("surf", "<i4"), ("cont", "<i4")]))
print("\nshaders", len(sh))

# ---- planes
pl = lump("planes", np.dtype([("n", "<f4", 3), ("d", "<f4")]))
print("planes", len(pl))
axial = (np.abs(pl["n"]) == 1.0).any(axis=1)
print("  axial planes", int(axial.sum()))

# ---- nodes / leafs
nodes = lump("nodes", np.dtype([("plane", "<i4"), ("ch", "<i4", 2), ("mins", "<i4", 3), ("maxs", "<i4", 3)]))
leafs = lump("leafs", np.dtype([("cluster", "<i4"), ("area", "<i4"), ("mins", "<i4", 3), ("maxs", "<i4", 3),
                                ("fls", "<i4"), ("nls", "<i4"), ("flb", "<i4"), ("nlb", "<i4")]))
print("nodes", len(nodes), "leafs", len(leafs))
if len(nodes):
    print("  world bounds", nodes[0]["mins"], nodes[0]["maxs"], "size", nodes[0]["maxs"] - nodes[0]["mins"])
print("  clusters used: max", int(leafs["cluster"].max()), "leafs with cluster>=0", int((leafs["cluster"] >= 0).sum()),
      "areas max", int(leafs["area"].max()))
nlb = leafs["nlb"].astype(np.int64); nls = leafs["nls"].astype(np.int64)
def dist(name, a):
    a = np.asarray(a)
    if a.size == 0:
        print(f"  {name}: empty"); return
    q = np.percentile(a, [50, 90, 99, 99.9])
    print(f"  {name}: sum {int(a.sum()):,} mean {a.mean():.1f} p50 {q[0]:.0f} p90 {q[1]:.0f} p99 {q[2]:.0f} p99.9 {q[3]:.0f} max {int(a.max()):,}")
dist("leafbrushes per leaf", nlb)
dist("leafbrushes per leaf (cluster>=0)", nlb[leafs["cluster"] >= 0])
dist("leafsurfaces per leaf", nls)
ext = (leafs["maxs"] - leafs["mins"]).astype(np.int64)
dist("leaf max extent (units)", ext.max(axis=1))

# tree depth
ch = nodes["ch"]
depth_hist = collections.Counter()
stack = [(0, 0)]
while stack:
    n, d = stack.pop()
    if n < 0:
        depth_hist[d] += 1
    else:
        stack.append((int(ch[n][0]), d + 1)); stack.append((int(ch[n][1]), d + 1))
ds = sorted(depth_hist)
print("  leaf depth min", ds[0], "max", ds[-1], "avg", sum(k * v for k, v in depth_hist.items()) / sum(depth_hist.values()))

# ---- models
models = lump("models", np.dtype([("mins", "<f4", 3), ("maxs", "<f4", 3), ("fs", "<i4"), ("ns", "<i4"), ("fb", "<i4"), ("nb", "<i4")]))
print("models", len(models))
print("  model0: surfaces", int(models[0]["ns"]), "brushes", int(models[0]["nb"]), "mins", models[0]["mins"], "maxs", models[0]["maxs"])
if len(models) > 1:
    dist("submodel brushes", models[1:]["nb"]); dist("submodel surfaces", models[1:]["ns"])

# ---- brushes
br = lump("brushes", np.dtype([("fs", "<i4"), ("ns", "<i4"), ("shader", "<i4")]))
bs = lump("brushsides", np.dtype([("plane", "<i4"), ("shader", "<i4"), ("draw", "<i4")]))
print("brushes", len(br), "brushsides", len(bs))
dist("sides per brush", br["ns"])
hist = np.bincount(np.clip(br["ns"], 0, 64))
print("  sides histogram (n:count):", {i: int(c) for i, c in enumerate(hist) if c})
bc = np.bincount(br["shader"], minlength=len(sh))
print("  top brush shaders:")
for i in np.argsort(-bc)[:15]:
    if bc[i]:
        print(f"    {int(bc[i]):10,} {sh[i]['name'].decode(errors='replace'):60} surf 0x{int(sh[i]['surf']) & 0xffffffff:08x} cont 0x{int(sh[i]['cont']) & 0xffffffff:08x}")
cont = sh["cont"][br["shader"]]
CONTENTS = {0x1: "SOLID", 0x2: "LAVA", 0x4: "WATER", 0x8: "FOG", 0x10: "PLAYERCLIP", 0x20: "MONSTERCLIP",
            0x40: "BOTCLIP", 0x80: "SHOTCLIP", 0x100: "BODY", 0x200: "CORPSE", 0x400: "TRIGGER", 0x800: "NODROP",
            0x1000: "TERRAIN", 0x2000: "LADDER", 0x4000: "ABSEIL", 0x8000: "OPAQUE", 0x10000: "OUTSIDE",
            0x10000000: "DETAIL", 0x20000000: "INSIDE", 0x80000000: "TRANSLUCENT"}
print("  brush contents combos:")
for v, c in sorted(collections.Counter(cont.astype(np.uint32).tolist()).items(), key=lambda kv: -kv[1])[:12]:
    print(f"    {c:10,} 0x{v:08x} " + "|".join(n for b, n in CONTENTS.items() if v & b))
print("  unique planes referenced by brushsides", len(np.unique(bs["plane"])), "max plane idx", int(bs["plane"].max()))
print("  world brushes", int(models[0]["nb"]), "submodel brushes", int(models[1:]["nb"].sum()) if len(models) > 1 else 0)

# leafbrush references
lb = lump("leafbrushes", "<i4")
print("leafbrushes", len(lb), "unique brushes referenced", len(np.unique(lb)))
refs = np.bincount(lb, minlength=len(br))
dist("leaves referencing each brush", refs)
# sides that a full leaf test touches
sides_per_brush = br["ns"].astype(np.int64)
cs = np.concatenate([[0], np.cumsum(sides_per_brush[lb])])
flb = leafs["flb"].astype(np.int64)
leaf_sides = cs[np.clip(flb + nlb, 0, len(lb))] - cs[np.clip(flb, 0, len(lb))]
dist("brushsides reachable per leaf", leaf_sides)

# ---- surfaces
sf = lump("surfaces", np.dtype([("shader", "<i4"), ("fog", "<i4"), ("type", "<i4"), ("fv", "<i4"), ("nv", "<i4"),
                                ("fi", "<i4"), ("ni", "<i4"), ("rest", "V120")]))
print("surfaces", len(sf))
TYPES = {0: "BAD", 1: "PLANAR", 2: "PATCH", 3: "TRISOUP", 4: "FLARE"}
for t, c in sorted(collections.Counter(sf["type"].tolist()).items()):
    m = sf["type"] == t
    print(f"  type {TYPES.get(t, t)}: {c:,} surfaces, verts {int(sf['nv'][m].sum()):,}, indexes {int(sf['ni'][m].sum()):,} (tris {int(sf['ni'][m].sum()) // 3:,})")
dist("verts per surface", sf["nv"]); dist("indexes per surface", sf["ni"])
print("  world surfaces", int(models[0]["ns"]))
print("drawverts", lumps["drawverts"][1] // 80, "drawindexes", lumps["drawindexes"][1] // 4, "tris", lumps["drawindexes"][1] // 12)
print("fogs", lumps["fogs"][1] // 72, "lightmaps", lumps["lightmaps"][1] // (128 * 128 * 3))

# ---- lightgrid
print("lightgrid points (30b)", lumps["lightgrid"][1] // 30, "lightarray entries", lumps["lightarray"][1] // 2)

# ---- vis
off, ln = lumps["visibility"]
if ln >= 8:
    nc, cb = struct.unpack_from("<ii", mm, off)
    print("vis clusters", nc, "clusterBytes", cb, "data", ln - 8)
    vis = np.frombuffer(mm, dtype=np.uint8, count=nc * cb, offset=off + 8).reshape(nc, cb)
    bits = np.unpackbits(vis, axis=1, bitorder="little")[:, :nc]
    vc = bits.sum(axis=1)
    dist("clusters visible from a cluster", vc)
    print("  mean visible fraction", float(vc.mean()) / nc)
else:
    print("no vis data")

# ---- entities
off, ln = lumps["entities"]
print("entity text bytes", ln)
