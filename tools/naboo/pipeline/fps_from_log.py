"""Frame rates from FPS_BEGIN / FPS_STOP console marks (3000 frames between each pair; the log has 1 s timestamps).
  py fps_from_log.py <qconsole.log> [frames]"""
import sys, re, datetime
n = float(sys.argv[2]) if len(sys.argv) > 2 else 3000.0
beg = {}; out = []
for l in open(sys.argv[1], errors="replace"):
    m = re.search(r"FPS_(BEGIN|STOP) (\w+)", l)
    if not m:
        continue
    t = datetime.datetime.strptime(l[:19], "%Y-%m-%d %H:%M:%S")
    if m.group(1) == "BEGIN":
        beg[m.group(2)] = t
    elif m.group(2) in beg:
        s = (t - beg[m.group(2)]).total_seconds()
        out.append("%s %d-%d" % (m.group(2), n / (s + 1), n / max(s - 1, 0.5)) if s > 1 else "%s >%d" % (m.group(2), n))
print("  ".join(out))
