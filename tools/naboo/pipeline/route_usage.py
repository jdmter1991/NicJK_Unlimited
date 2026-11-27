"""How the bots used the route file during a logged run (bot_test_run.sh / steam_session.sh games.log).
  py route_usage.py <run_dir> <routes.wnt>
From the "PlayerPos: client x y z onground" samples (every 2 s):
  * off_route   on-ground samples more than `far` (600) units from every waypoint: where routes are missing, as
                256-unit clusters with a setviewpos line
  * stuck_near  waypoints within 200 units of a stuck spot (a bot within 16 units for 30 s or more): suspect links
  * visits      how many samples fell nearest to each waypoint; waypoints never visited
  * dither      30 s windows of a bot moving back and forth within 250 units with nobody within 400 units
  * links       links (consecutive entries and neighbour lists) whose midpoint no bot came within 96 units of
Writes <run_dir>/route_usage.json and route_usage.md."""
import sys, os, re, json
import numpy as np

run, wnt = sys.argv[1], sys.argv[2]
FAR = 600.0
W = []; NB = []; DN = []
for line in open(wnt):
    m = re.match(r"(\d+) (\d+) \S+ \(([^)]+)\) \{ ([^}]*)\} (\S+)", line)
    if not m:
        continue
    W.append([float(v) for v in m.group(3).split()]); NB.append([int(v.split("-")[0]) for v in m.group(4).split()]); DN.append(float(m.group(5)))
W = np.array(W)
P = []
for line in open(os.path.join(run, "games.log"), errors="replace"):
    m = re.match(r"\s*(\d+):(\d\d) PlayerPos: (\d+) (\S+) (\S+) (\S+) (\d)", line)
    if m:
        P.append((int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)), float(m.group(4)), float(m.group(5)), float(m.group(6)), int(m.group(7))))
P = np.array(P)
Q = P[:, 2:5]
# nearest waypoint per sample (chunked)
near = np.zeros(len(Q), np.int64); dist = np.zeros(len(Q))
for s in range(0, len(Q), 2000):
    d = np.linalg.norm(Q[s:s + 2000, None, :] - W[None, :, :], axis=2)
    near[s:s + 2000] = d.argmin(1); dist[s:s + 2000] = d.min(1)
ground = P[:, 5] == 1


def clusters(pts, cell=256.0, top=20):
    if not len(pts):
        return []
    k = np.floor(pts[:, :2] / cell).astype(np.int64)
    u, inv, cnt = np.unique(k, axis=0, return_inverse=True, return_counts=True)
    out = []
    for i in np.argsort(-cnt)[:top]:
        sel = pts[inv.ravel() == i]
        out.append({"count": int(cnt[i]), "x": int(sel[:, 0].mean()), "y": int(sel[:, 1].mean()), "z": int(np.median(sel[:, 2])),
                    "setviewpos": "setviewpos %d %d %d 0" % (sel[:, 0].mean(), sel[:, 1].mean(), np.median(sel[:, 2]) + 60)})
    return out


off = Q[ground & (dist > FAR)]
# stuck spots
stuck = []
for c in np.unique(P[:, 1]):
    S = P[P[:, 1] == c]; a = 0
    for i in range(1, len(S) + 1):
        if i == len(S) or np.linalg.norm(S[i, 2:5] - S[a, 2:5]) > 16.0 or S[i, 0] - S[i - 1, 0] > 6:
            if i - a >= 15:
                stuck.append(S[a, 2:5])
            a = i
stuck = np.array(stuck).reshape(-1, 3)
# dithering: 30 s windows in which a bot moves more than 1200 units but stays within 250 units of one point while no
# other player is within 400 units (not a fight): a bot going back and forth between route points or trapped
import collections as _co
byt = _co.defaultdict(list)
for r in P:
    byt[int(r[0])].append(r)
dither = []
for c in np.unique(P[:, 1]):
    S = P[P[:, 1] == c]
    for a in range(0, len(S) - 15, 5):
        Wn = S[a:a + 15]
        if Wn[-1, 0] - Wn[0, 0] > 34:
            continue
        path = np.linalg.norm(np.diff(Wn[:, 2:5], axis=0), axis=1).sum(); cen = Wn[:, 2:5].mean(0)
        if path > 1200 and np.linalg.norm(Wn[:, 2:5] - cen, axis=1).max() < 250:
            alone = True
            for r in Wn:
                o = np.array([x for x in byt[int(r[0])] if x[1] != c])
                if len(o) and (np.linalg.norm(o[:, 2:5] - r[2:5], axis=1) < 400).any():
                    alone = False; break
            if alone:
                dither.append(cen)
dither = np.array(dither).reshape(-1, 3)
stuck_wp = sorted({int(j) for p in stuck for j in np.flatnonzero(np.linalg.norm(W - p, axis=1) < 200)})
visits = np.bincount(near, minlength=len(W))
# links walked: a link counts as used when some sample came within 96 units of its midpoint
links = set()
for i, nb in enumerate(NB):
    for j in nb:
        links.add((min(i, j), max(i, j)))
    if DN[i] > 0 and i + 1 < len(W):
        links.add((i, i + 1))
links = sorted(links)
mid = np.array([(W[a] + W[b]) / 2 for a, b in links])
used = np.zeros(len(links), bool)
for s in range(0, len(mid), 500):
    d = np.linalg.norm(mid[s:s + 500, None, :] - Q[None, ::3, :], axis=2).min(1)
    used[s:s + 500] = d < 96
rep = {"run": os.path.basename(run.rstrip("/\\")), "samples": int(len(Q)), "waypoints": int(len(W)),
       "on_ground_samples": int(ground.sum()), "off_route_percent": round(100.0 * float((ground & (dist > FAR)).sum()) / max(1, ground.sum()), 2),
       "median_distance_to_route": round(float(np.median(dist[ground])), 1),
       "waypoints_never_nearest": int((visits == 0).sum()), "links": len(links), "links_unused": int((~used).sum()),
       "stuck_spots": int(len(stuck)), "waypoints_near_stuck": stuck_wp[:200],
       "dither_windows": int(len(dither)), "off_route_spots": clusters(off), "stuck_clusters": clusters(stuck), "dither_spots": clusters(dither)}
json.dump(rep, open(os.path.join(run, "route_usage.json"), "w"), indent=1)
L = ["# Route usage %s" % rep["run"], "", "%d samples, %d waypoints, %d links." % (rep["samples"], rep["waypoints"], rep["links"]), "",
     "* on the ground more than %d units from any waypoint: %.2f %% of on-ground samples" % (FAR, rep["off_route_percent"]),
     "* median distance to the nearest waypoint: %.0f units" % rep["median_distance_to_route"],
     "* waypoints never the nearest one to a bot: %d" % rep["waypoints_never_nearest"],
     "* links no bot came near: %d of %d" % (rep["links_unused"], rep["links"]),
     "* stuck spots: %d (waypoints within 200 units: %d)" % (rep["stuck_spots"], len(stuck_wp)), ""]
for k in ("off_route_spots", "stuck_clusters", "dither_spots"):
    if rep[k]:
        L += ["## %s" % k, "", "| count | position | console |", "|---|---|---|"] + ["| %d | %d %d %d | `%s` |" % (s["count"], s["x"], s["y"], s["z"], s["setviewpos"]) for s in rep[k]] + [""]
open(os.path.join(run, "route_usage.md"), "w").write("\n".join(L))
print(json.dumps({k: v for k, v in rep.items() if k not in ("off_route_spots", "stuck_clusters", "dither_spots", "waypoints_near_stuck")}))
