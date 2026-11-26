"""Where bots run into map problems, from a bot test run's server log (bot_test_run.sh).
  py bot_test_analyze.py <run_dir> [<run_dir> ...]
Reads <run_dir>/games.log: "PlayerPos: <client> <x> <y> <z> <onground>" every 2 s for every live player and
"DeathPos: <mod> <client> <x> <y> <z> <name>" at every death (g_logPlayerPos / g_logDeathPos), and compares them
with the map: the drawn terrain (export/city/dump/extras/terrain_near_carved.npz, 1 m grid) and the water volumes
(export/city/collision/water_boxes.npy).
Categories, each clustered into 256-unit cells (the spots to fix):
  fell_out      died in the kill volume over the hull floor (fell out of the world); the spot is where the
                player was last seen before that, i.e. near the gap
  below_ground  standing more than 96 units under the drawn terrain at that place
  drowned       died by water
  falling       died by falling damage
  in_water      inside a water volume (bots should rarely be there)
  stuck         alive and within 16 units of the same place for 30 s or more
Writes <run_dir>/analysis.json and analysis.md (and, for several runs, the summary of all of them in the first)."""
import sys, os, re, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
ED = os.path.join(ROOT, "export", "city")
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
MOD_WATER, MOD_FALLING, MOD_SUICIDE, MOD_TRIGGER_HURT = 33, 38, 39, 41
g = np.load(os.path.join(ED, "dump", "extras", "terrain_near_carved.npz"))["grid"].astype(np.float64)
gx = (g[0, :, 0] - ORG[0]) * UPM; gy = (g[:, 0, 1] - ORG[1]) * UPM; gz = (g[:, :, 2] - ORG[2]) * UPM
WB = np.load(os.path.join(ED, "collision", "water_boxes.npy")).astype(np.float64)


def terrain_z(x, y):
    i = np.clip(np.searchsorted(gx, x), 1, len(gx) - 1); j = np.clip(np.searchsorted(gy, y), 1, len(gy) - 1)
    inside = (x > gx[0]) & (x < gx[-1]) & (y > gy[0]) & (y < gy[-1])
    return np.where(inside, gz[j, i], np.nan)


def in_water(p):
    if not len(WB):
        return np.zeros(len(p), bool)
    out = np.zeros(len(p), bool)
    for s in range(0, len(p), 4000):
        q = p[s:s + 4000]
        out[s:s + 4000] = ((q[:, None, :] >= WB[None, :, 0] - 1) & (q[:, None, :] <= WB[None, :, 1] + 1)).all(2).any(1)
    return out


def parse(run):
    pos = []; deaths = []
    t_re = re.compile(r"^\s*(\d+):(\d\d) (.*)$")
    for line in open(os.path.join(run, "games.log"), errors="replace"):
        m = t_re.match(line)
        if not m:
            continue
        t = int(m.group(1)) * 60 + int(m.group(2)); rest = m.group(3)
        if rest.startswith("PlayerPos:"):
            f = rest.split()
            pos.append((t, int(f[1]), float(f[2]), float(f[3]), float(f[4]), int(f[5])))
        elif rest.startswith("DeathPos:"):
            f = rest.split(None, 6)
            deaths.append((t, int(f[1]), int(f[2]), float(f[3]), float(f[4]), float(f[5]), f[6].strip() if len(f) > 6 else ""))
    return pos, deaths


def cluster(points, cell=256.0, top=15):
    if not len(points):
        return []
    P = np.array(points, np.float64)
    k = np.floor(P[:, :2] / cell).astype(np.int64)
    u, inv, cnt = np.unique(k, axis=0, return_inverse=True, return_counts=True)
    out = []
    for i in np.argsort(-cnt)[:top]:
        sel = P[inv.ravel() == i]
        out.append({"count": int(cnt[i]), "x": int(sel[:, 0].mean()), "y": int(sel[:, 1].mean()), "z": int(np.median(sel[:, 2])),
                    "setviewpos": "setviewpos %d %d %d 0" % (sel[:, 0].mean(), sel[:, 1].mean(), np.median(sel[:, 2]) + 60)})
    return out


def analyse(run):
    pos, deaths = parse(run)
    rep = {"run": os.path.basename(run.rstrip("/\\")), "position_samples": len(pos), "deaths": len(deaths)}
    if not pos:
        return rep, {}
    A = np.array([p[:5] for p in pos], np.float64)          # t, client, x, y, z
    tz = terrain_z(A[:, 2], A[:, 3])
    below = (~np.isnan(tz)) & (A[:, 4] < tz - 96.0)
    wet = in_water(A[:, 2:5])
    cats = {"below_ground": A[below][:, 2:5].tolist(), "in_water": A[wet][:, 2:5].tolist()}
    # stuck: same client within 16 units over >= 15 consecutive samples (30 s)
    stuck = []
    for c in np.unique(A[:, 1]):
        S = A[A[:, 1] == c]
        run_start = 0
        for i in range(1, len(S) + 1):
            if i == len(S) or np.linalg.norm(S[i, 2:5] - S[run_start, 2:5]) > 16.0 or S[i, 0] - S[i - 1, 0] > 6:
                if i - run_start >= 15:
                    stuck.append(S[run_start, 2:5].tolist())
                run_start = i
    cats["stuck"] = stuck
    last_seen = {}
    fell, drowned, falling = [], [], []
    di = 0; D = sorted(deaths)
    by_client = {}
    for p in pos:
        by_client.setdefault(p[1], []).append(p)
    for t, mod, cl, x, y, z, name in D:
        if mod == MOD_TRIGGER_HURT:
            prev = [p for p in by_client.get(cl, []) if p[0] <= t and p[5] == 1 and p[4] > z + 200]       # last time on solid ground
            fell.append(list(prev[-1][2:5]) if prev else [x, y, z])
        elif mod == MOD_WATER:
            drowned.append([x, y, z])
        elif mod == MOD_FALLING:
            falling.append([x, y, z])
    cats.update({"fell_out": fell, "drowned": drowned, "falling": falling})
    rep["counts"] = {k: len(v) for k, v in cats.items()}
    rep["samples_below_ground_percent"] = round(100.0 * below.mean(), 3)
    rep["samples_in_water_percent"] = round(100.0 * wet.mean(), 3)
    rep["deaths_by_cause"] = {str(k): int(v) for k, v in zip(*np.unique([d[1] for d in deaths], return_counts=True))} if deaths else {}
    rep["spots"] = {k: cluster(v) for k, v in cats.items()}
    return rep, cats


def write(run, rep):
    json.dump(rep, open(os.path.join(run, "analysis.json"), "w"), indent=1)
    L = ["# Bot test %s" % rep["run"], "", "%d position samples, %d deaths." % (rep["position_samples"], rep["deaths"]), ""]
    if "counts" in rep:
        L += ["| problem | count |", "|---|---|"] + ["| %s | %d |" % (k, v) for k, v in rep["counts"].items()] + [""]
        L += ["Below ground: %.3f %% of samples; in water: %.3f %%." % (rep["samples_below_ground_percent"], rep["samples_in_water_percent"]), ""]
        for k, sp in rep["spots"].items():
            if sp:
                L += ["## %s" % k, "", "| count | position (x y z) | console |", "|---|---|---|"] + ["| %d | %d %d %d | `%s` |" % (s["count"], s["x"], s["y"], s["z"], s["setviewpos"]) for s in sp] + [""]
    open(os.path.join(run, "analysis.md"), "w").write("\n".join(L))


allc = {}
for run in sys.argv[1:]:
    rep, cats = analyse(run)
    write(run, rep)
    print(json.dumps({k: rep[k] for k in rep if k != "spots"}))
    for k, v in cats.items():
        allc.setdefault(k, []).extend(v)
if len(sys.argv) > 2:
    summ = {"runs": [os.path.basename(r.rstrip("/\\")) for r in sys.argv[1:]], "counts": {k: len(v) for k, v in allc.items()}, "spots": {k: cluster(v) for k, v in allc.items()}}
    json.dump(summ, open(os.path.join(sys.argv[1], "analysis_all_runs.json"), "w"), indent=1)
    print(json.dumps(summ["counts"]))
