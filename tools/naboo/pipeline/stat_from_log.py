"""Real frame rates from the renderer's once-per-second 'TWORLD view' lines between STAT marks.
  py stat_from_log.py <qconsole.log>"""
import sys, re
cur = None; d = {}; last = {}
for l in open(sys.argv[1], errors="replace"):
    m = re.search(r"STAT (\w+)", l)
    if m:
        cur = m.group(1); continue
    m = re.search(r"TWORLD view: (\d+) fps, (\d+) of \d+ instances \(lod (\d+)/(\d+)/(\d+), \d+ too small\), (\d+) draws, (\d+) tris", l)
    if m and cur and cur != "end":
        d.setdefault(cur, []).append(int(m.group(1))); last[cur] = (int(m.group(2)), int(m.group(6)), int(m.group(7)))
for k, v in d.items():
    v = v[1:] if len(v) > 2 else v
    print("%-7s fps min %3d median %3d max %3d | placements %5d draws %5d tris %8d" % (k, min(v), sorted(v)[len(v) // 2], max(v), *last[k]))
