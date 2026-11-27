"""Estimate collision workload of typical bot traces on an RBSP.

Emulates CM_TraceThroughTree leaf selection for point (ray) traces started at the
map's spawn points and counts, per trace: leaves touched, leafbrush entries walked,
and how many of those brushes overlap the trace's AABB (i.e. survive a bounds reject).
argv[1]=bsp
"""
import sys, struct, re, math
import numpy as np

path = sys.argv[1]
mm = np.memmap(path, dtype=np.uint8, mode="r")
L = [struct.unpack_from("<ii", mm, 8 + i * 8) for i in range(18)]
def lump(i, dt):
    off, ln = L[i]
    return np.frombuffer(mm, dtype=dt, count=ln // np.dtype(dt).itemsize, offset=off)

planes = lump(2, np.dtype([("n", "<f4", 3), ("d", "<f4")]))
nodes = lump(3, np.dtype([("plane", "<i4"), ("ch", "<i4", 2), ("mins", "<i4", 3), ("maxs", "<i4", 3)]))
leafs = lump(4, np.dtype([("cluster", "<i4"), ("area", "<i4"), ("mins", "<i4", 3), ("maxs", "<i4", 3),
                          ("fls", "<i4"), ("nls", "<i4"), ("flb", "<i4"), ("nlb", "<i4")]))
lb = lump(6, "<i4")
br = lump(8, np.dtype([("fs", "<i4"), ("ns", "<i4"), ("shader", "<i4")]))
bs = lump(9, np.dtype([("plane", "<i4"), ("shader", "<i4"), ("draw", "<i4")]))

# brush bounds the way CM_BoundBrush does it: first six sides are the axial planes
fs = br["fs"].astype(np.int64)
pd = planes["d"]
bmins = np.stack([-pd[bs["plane"][fs + 0]], -pd[bs["plane"][fs + 2]], -pd[bs["plane"][fs + 4]]], axis=1)
bmaxs = np.stack([pd[bs["plane"][fs + 1]], pd[bs["plane"][fs + 3]], pd[bs["plane"][fs + 5]]], axis=1)
ext = bmaxs - bmins
print("brush bounds sanity: negative-extent brushes", int((ext < 0).any(axis=1).sum()),
      "median extent", np.median(ext, axis=0), "p99 extent", np.percentile(ext, 99, axis=0))

pn = planes["n"]; nplane = nodes["plane"]; nch = nodes["ch"]
SURF_EPS = 0.125

def leaves_for_segment(p1, p2):
    out = []
    stack = [(0, p1, p2)]
    while stack:
        num, a, b = stack.pop()
        if num < 0:
            out.append(-1 - num); continue
        pi = nplane[num]; n = pn[pi]; d = pd[pi]
        t1 = float(n @ a) - d; t2 = float(n @ b) - d
        if t1 >= SURF_EPS and t2 >= SURF_EPS:
            stack.append((int(nch[num][0]), a, b)); continue
        if t1 < -SURF_EPS and t2 < -SURF_EPS:
            stack.append((int(nch[num][1]), a, b)); continue
        if t1 == t2:
            stack.append((int(nch[num][0]), a, b)); stack.append((int(nch[num][1]), a, b)); continue
        f = min(1.0, max(0.0, t1 / (t1 - t2)))
        mid = a + (b - a) * f
        side = 1 if t1 < t2 else 0
        stack.append((int(nch[num][side]), a, mid)); stack.append((int(nch[num][side ^ 1]), mid, b))
    return out

def point_leaf(p):
    num = 0
    while num >= 0:
        pi = nplane[num]
        num = int(nch[num][0]) if float(pn[pi] @ p) - pd[pi] >= 0 else int(nch[num][1])
    return -1 - num

def measure(p1, p2, pad):
    ls = set(leaves_for_segment(p1, p2))
    walked = 0; ids = []
    for l in ls:
        f, n = int(leafs["flb"][l]), int(leafs["nlb"][l])
        walked += n; ids.append(lb[f:f + n])
    if not ids:
        return len(ls), 0, 0, 0
    u = np.unique(np.concatenate(ids))
    lo = np.minimum(p1, p2) - pad; hi = np.maximum(p1, p2) + pad
    ov = ((bmins[u] <= hi) & (bmaxs[u] >= lo)).all(axis=1)
    sides = int(br["ns"][u][ov].sum())
    return len(ls), walked, int(ov.sum()), sides

# spawn points from entity lump
off, ln = L[0]
text = bytes(mm[off:off + ln]).decode("latin-1")
spawns = []
for block in re.findall(r"\{([^{}]*)\}", text):
    e = dict(re.findall(r'"([^"]*)"\s+"([^"]*)"', block))
    if e.get("classname", "").startswith("info_player"):
        spawns.append(np.array([float(x) for x in e["origin"].split()], dtype=np.float32))
print("spawn points", len(spawns))

print("\nper spawn: leaf, brushes in leaf, leaf extent")
sl = []
for s in spawns:
    l = point_leaf(s + np.array([0, 0, 24], dtype=np.float32))
    sl.append(int(leafs["nlb"][l]))
sl = np.array(sl)
print("  brushes in spawn leaf: min", sl.min(), "median", np.median(sl), "mean", sl.mean(), "max", sl.max())

def run(name, length, pad, vertical=False):
    res = []
    for s in spawns:
        eye = s + np.array([0, 0, 36], dtype=np.float32)
        if vertical:
            dirs = [np.array([0, 0, -1], dtype=np.float32)]
        else:
            dirs = [np.array([math.cos(a), math.sin(a), 0], dtype=np.float32) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)]
        for d in dirs:
            res.append(measure(eye, eye + d * length, pad))
    r = np.array(res, dtype=np.float64)
    def row(i, label):
        c = r[:, i]
        print(f"    {label:34} mean {c.mean():10.1f}  p50 {np.percentile(c, 50):9.0f}  p90 {np.percentile(c, 90):9.0f}  max {c.max():9.0f}")
    print(f"\n{name}: {len(res)} traces, length {length}, box half-extent {pad}")
    row(0, "leaves touched")
    row(1, "leafbrush entries walked")
    row(2, "brushes overlapping trace AABB")
    row(3, "brushsides in overlapping brushes")

run("ground check (down 64, point)", 64, 0, vertical=True)
run("short move/obstacle probe (48, player box)", 48, 15)
run("local visibility ray (512)", 512, 0)
run("mid visibility ray (2048)", 2048, 0)
run("long visibility ray (8192)", 8192, 0)
