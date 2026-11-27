"""Frame time by view: where and in which direction the cooked world is slow to draw.
  py view_sweep.py make <routes.wnt> <out.cfg> [points] [frames_per_view]
      writes a client config that visits `points` (default 40) route points spread over the map (farthest-point
      sampling) and turns to 8 directions at each; after every view it prints "viewpos" so the log can be split
  py view_sweep.py read <qconsole.log> <out_dir>
      pairs every "TWORLD cpu" / "TWORLD view" statistics line (r_tworldStats 1, once per second) with the view printed
      before it; writes views.json and views.md (slowest views first, with the drawn instances, draws and triangles)
Run the config in a local devmap with r_tworldStats 1, logfile 2, uncapped (com_maxfps 0, r_swapInterval 0)."""
import sys, re, json, os
import numpy as np

if sys.argv[1] == "make":
    wnt, out = sys.argv[2], sys.argv[3]
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 40; fr = int(sys.argv[5]) if len(sys.argv) > 5 else 500
    W = np.unique(np.array([[float(v) for v in re.search(r"\(([^)]+)\)", l).group(1).split()] for l in open(wnt)]), axis=0)
    pick = [int(np.argmin(np.linalg.norm(W[:, :2] - np.median(W[:, :2], 0), axis=1)))]
    d = np.linalg.norm(W[:, :2] - W[pick[0], :2], axis=1)
    while len(pick) < min(n, len(W)):
        i = int(np.argmax(d)); pick.append(i); d = np.minimum(d, np.linalg.norm(W[:, :2] - W[i, :2], axis=1))
    lines = []; k = 0
    views = [(W[i], yaw) for i in pick for yaw in range(0, 360, 45)]
    for k, (p, yaw) in enumerate(views):
        nxt = "vstr sw%d" % (k + 1) if k + 1 < len(views) else "echo SWEEP_DONE; wait 200; quit"
        lines.append('set sw%d "setviewpos %d %d %d %d; wait %d; viewpos; wait %d; %s"\n' % (k, p[0], p[1], p[2] + 16, yaw, fr // 3, fr, nxt))
    lines.append('set swgo "wait 2000; cg_draw2D 1; cg_drawFPS 1; r_tworldStats 1; com_maxfps 0; noclip; wait 300; vstr sw0"\nvstr swgo\n')
    open(out, "w").write("".join(lines))
    print("views", len(views), "points", len(pick))
else:
    log, outd = sys.argv[2], sys.argv[3]
    os.makedirs(outd, exist_ok=True)
    cur = None; rows = []; pend = {}
    vp = re.compile(r"\((-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\) : (-?[\d.]+)")
    for line in open(log, errors="replace"):
        m = vp.search(line)
        if m and "TWORLD" not in line:
            cur = tuple(float(v) for v in m.groups()); pend[cur] = []
            continue
        if cur is None:
            continue
        m = re.search(r"TWORLD cpu ms per frame: cull ([\d.]+), uniforms ([\d.]+), fill ([\d.]+), draw ([\d.]+) \(frame ([\d.]+)\)", line)
        if m:
            pend[cur].append({"cull": float(m.group(1)), "uniforms": float(m.group(2)), "fill": float(m.group(3)), "draw": float(m.group(4)), "frame": float(m.group(5))})
            continue
        m = re.search(r"TWORLD view: (\d+) fps, (\d+) of \d+ instances \(lod (\d+)/(\d+)/(\d+), (\d+) too small\), (\d+) draws, (\d+) tris", line)
        if m and pend[cur]:
            pend[cur][-1].update({"fps": int(m.group(1)), "instances": int(m.group(2)), "lod0": int(m.group(3)), "lod1": int(m.group(4)),
                                  "lod2": int(m.group(5)), "draws": int(m.group(7)), "tris": int(m.group(8))})
    for v, st in pend.items():
        st = [s for s in st if "fps" in s]
        if not st:
            continue
        s = st[-1]                 # the last full second at this view (the first can include the move)
        rows.append(dict(s, x=v[0], y=v[1], z=v[2], yaw=v[3]))
    rows.sort(key=lambda r: r["fps"])
    json.dump(rows, open(os.path.join(outd, "views.json"), "w"), indent=1)
    fps = np.array([r["fps"] for r in rows])
    L = ["# View sweep", "", "%d views; fps median %d, 10 %% %d, worst %d" % (len(rows), np.median(fps), np.percentile(fps, 10), fps.min()), "",
         "| fps | cpu frame ms | cull | draw | instances | draws | tris (M) | position, yaw |", "|---|---|---|---|---|---|---|---|"]
    for r in rows[:30]:
        L.append("| %d | %.2f | %.2f | %.2f | %d | %d | %.2f | `setviewpos %d %d %d %d` |" % (r["fps"], r["frame"], r["cull"], r["draw"], r["instances"], r["draws"], r["tris"] / 1e6, r["x"], r["y"], r["z"], r["yaw"]))
    # same place, other directions: how much the direction matters
    by = {}
    for r in rows:
        by.setdefault((round(r["x"]), round(r["y"])), []).append(r)
    spread = sorted(((max(v, key=lambda r: r["fps"])["fps"] / max(1, min(v, key=lambda r: r["fps"])["fps"]), k) for k, v in by.items() if len(v) > 4), reverse=True)
    L += ["", "## Places where the direction matters most (best / worst fps)", ""]
    for ratio, k in spread[:12]:
        v = sorted(by[k], key=lambda r: r["fps"])
        L.append("* %d %d: %d fps at yaw %d (%d instances, %d draws, %.1f M tris) vs %d fps at yaw %d (%d instances, %d draws, %.1f M tris)" % (
            k[0], k[1], v[0]["fps"], v[0]["yaw"], v[0]["instances"], v[0]["draws"], v[0]["tris"] / 1e6, v[-1]["fps"], v[-1]["yaw"], v[-1]["instances"], v[-1]["draws"], v[-1]["tris"] / 1e6))
    open(os.path.join(outd, "views.md"), "w").write("\n".join(L))
    print("\n".join(L[:8]))
