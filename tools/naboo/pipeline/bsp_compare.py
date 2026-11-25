"""Compare collision BSPs by what a trace has to look at.
  py bsp_compare.py <a.bsp> [<b.bsp> ...]
For each file: brush count, sides per brush, brush size distribution, and for player-sized boxes at the spawn
points (plus offsets around them) the number of distinct brushes whose bounds overlap the box, i.e. the
candidates the engine must test side by side after its tree and leaf lookups.
"""
import sys, struct, re
import numpy as np


def load(path):
    d = open(path, "rb").read()
    assert d[:4] == b"RBSP"
    lumps = [struct.unpack_from("<ii", d, 8 + i * 8) for i in range(18)]
    L = lambda i: d[lumps[i][0]:lumps[i][0] + lumps[i][1]]
    planes = np.frombuffer(L(2), "<f4").reshape(-1, 4)
    brushes = np.frombuffer(L(8), "<i4").reshape(-1, 3)
    sides = np.frombuffer(L(9), "<i4").reshape(-1, 3)
    leafs = np.frombuffer(L(4), "<i4").reshape(-1, 12)
    ents = L(0).decode("latin1")
    return planes, brushes, sides, leafs, ents


def report(path):
    planes, brushes, sides, leafs, ents = load(path)
    first, num = brushes[:, 0].astype(np.int64), brushes[:, 1]
    ok = num >= 6
    f = first[ok]
    pd = planes[:, 3]
    pl = lambda k: pd[sides[f + k, 0]]
    mn = np.stack([-pl(0), -pl(2), -pl(4)], 1).astype(np.float64)
    mx = np.stack([pl(1), pl(3), pl(5)], 1).astype(np.float64)
    ext = mx - mn
    big = ext.max(1)
    print("== %s" % path)
    print("brushes %d (with >=6 sides %d), sides/brush mean %.2f  min %d  max %d" % (len(brushes), ok.sum(), num.mean(), num.min(), num.max()))
    q = [5, 25, 50, 75, 95, 99]
    print("largest extent percentiles %s: %s" % (q, np.round(np.percentile(big, q), 1)))
    print("smallest extent percentiles %s: %s" % (q, np.round(np.percentile(ext.min(1), q), 1)))
    print("brushes with largest extent < 8: %d   < 16: %d   < 32: %d" % ((big < 8).sum(), (big < 16).sum(), (big < 32).sum()))
    nb = leafs[:, 11]
    print("leaves %d, with brushes %d; brushes per leaf mean %.0f median %d p99 %d max %d" % (
        len(leafs), (nb > 0).sum(), nb[nb > 0].mean(), np.median(nb[nb > 0]), np.percentile(nb[nb > 0], 99), nb.max()))
    sp = np.array([[float(x) for x in m.split()] for m in re.findall(r'"origin" "([^"]+)"', ents)])
    if len(sp) == 0:
        return
    rng = np.random.default_rng(1)
    pts = (sp[:, None, :] + np.concatenate([np.zeros((1, 3)), rng.uniform(-400, 400, (15, 3)) * [1, 1, 0.1]])[None]).reshape(-1, 3)
    # drop the huge hull slabs from the candidate counts
    keep = big < 20000
    mn2, mx2 = mn[keep], mx[keep]
    for name, lo, hi in (("standing box", (-15, -15, -24), (15, 15, 40)), ("box swept 64 units", (-47, -47, -40), (47, 47, 56)),
                         ("box swept 256 units", (-143, -143, -88), (143, 143, 104))):
        cnt = np.empty(len(pts), np.int64)
        for i, p in enumerate(pts):
            cnt[i] = np.count_nonzero(np.all(mx2 >= p + lo, 1) & np.all(mn2 <= p + hi, 1))
        print("  %-20s candidates: mean %.1f  median %d  p90 %d  max %d" % (name, cnt.mean(), np.median(cnt), np.percentile(cnt, 90), cnt.max()))


for p in sys.argv[1:]:
    report(p)
