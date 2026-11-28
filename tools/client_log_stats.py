"""Summarize a client qconsole.log produced by run_client_bench.ps1 (com_speeds 1 + BENCH markers)."""
import sys, re, collections

rx = re.compile(r"frame:\s*(\d+)\s+all:\s*(-?\d+)\s+sv:\s*(-?\d+)\s+ev:\s*(-?\d+)\s+cl:\s*(-?\d+)\s+gm:\s*(-?\d+)\s+rf:\s*(-?\d+)\s+bk:\s*(-?\d+)")
segs = collections.OrderedDict()
cur = None
for line in open(sys.argv[1], encoding="latin-1", errors="replace"):
    if "BENCH_BEGIN" in line:
        m = re.search(r"BENCH_BEGIN cycle (\d+) (\w+)", line)
        cur = (int(m.group(1)), m.group(2)) if m else None
        if cur:
            segs[cur] = []
        continue
    if "BENCH_STOP" in line or "BENCH_END" in line:
        cur = None
        continue
    if cur:
        m = rx.search(line)
        if m:
            segs[cur].append(tuple(int(x) for x in m.groups()[1:]))

if not segs:
    print("no BENCH segments found")
    sys.exit(0)
print(f"{'cycle':5} {'pos':4} {'frames':>6} {'fps':>7} {'ms avg':>7} {'p99 ms':>6} {'max ms':>6} {'cgame':>6} {'front':>6} {'back':>6}")
tot = collections.defaultdict(lambda: [0, 0])
for (cyc, pos), fr in segs.items():
    if not fr:
        print(f"{cyc:5} {pos:4} no frames"); continue
    alls = sorted(f[0] for f in fr)
    n = len(fr); s = sum(alls)
    fps = 1000.0 * n / s if s > 0 else float('inf')
    avg = lambda i: sum(f[i] for f in fr) / n
    print(f"{cyc:5} {pos:4} {n:6} {fps:7.1f} {s / n:7.2f} {alls[int(n * 0.99) - 1]:6} {alls[-1]:6} {avg(4):6.2f} {avg(5):6.2f} {avg(6):6.2f}")
    if cyc > 1:
        tot[pos][0] += n; tot[pos][1] += s
print("\nper position, cycles after the first:")
for pos, (n, s) in tot.items():
    print(f"  {pos}: {1000.0 * n / s if s else 0:7.1f} fps over {n} frames")
