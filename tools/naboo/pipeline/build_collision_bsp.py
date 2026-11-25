"""Prototype collision BSP: collision triangles -> OBJ chunks + .map -> existing q3map2 -> RBSP.
  py build_collision_bsp.py <export_dir> <mapname> [--no-compile]
Reads  <export_dir>/collision/collision_tris.npy (engine units, world space) and spawn_candidates.json.
Writes naboo/q3base/base/{shaders,models/naboo_col,maps}/...  and runs q3map2 (BSP stage only: no vis, no light).
"""
import sys, os, json, subprocess, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
Q3MAP2 = r"E:\jedi academy modding archive\Netradiant\q3map2.exe"
export_dir, mapname = sys.argv[1], sys.argv[2]
compile_ = "--no-compile" not in sys.argv
BASE = os.path.join(ROOT, "q3base", "base")
for d in ("shaders", "maps", os.path.join("models", "naboo_col")):
    os.makedirs(os.path.join(BASE, d), exist_ok=True)

UPM = cfg["units_per_metre"]; ORG = np.array(cfg["origin_m"])
tris = np.load(os.path.join(export_dir, "collision", "collision_tris.npy")).astype(np.float64)
mn = tris.reshape(-1, 3).min(0); mx = tris.reshape(-1, 3).max(0)
print("collision triangles", len(tris), "bounds", mn.round(1), mx.round(1))

# ---- built-up density: object (non-terrain) collision triangles per 20 m cell
DCELL = 20.0 * UPM
dens = {}
try:
    n_terr = int(json.load(open(os.path.join(export_dir, "collision", "collision_stats.json")))["terrain_tris"])
except Exception:
    n_terr = 0
obj_c = tris[:len(tris) - n_terr].mean(1)
if len(obj_c):
    kx = np.floor(obj_c[:, 0] / DCELL).astype(np.int64); ky = np.floor(obj_c[:, 1] / DCELL).astype(np.int64)
    uq_, cnt_ = np.unique(np.stack([kx, ky], 1), axis=0, return_counts=True)
    dens = {(int(a), int(b)): int(c) for (a, b), c in zip(uq_, cnt_)}


def density(x, y):
    cx, cy = int(np.floor(x / DCELL)), int(np.floor(y / DCELL))
    return sum(dens.get((cx + i, cy + j), 0) for i in (-1, 0, 1) for j in (-1, 0, 1))


# ---- shaders (kept in our own base path so nothing depends on, or touches, the game install)
open(os.path.join(BASE, "shaders", "naboo_sys.shader"), "w").write("""textures/naboo_sys/col
{
	qer_trans 0.4
	surfaceparm nodraw
	surfaceparm nolightmap
}
textures/naboo_sys/hull
{
	qer_trans 0.4
	surfaceparm nodraw
	surfaceparm nolightmap
}
textures/naboo_sys/sky
{
	surfaceparm sky
	surfaceparm noimpact
	surfaceparm nolightmap
	skyParms textures/naboo/env/sky 512 -
}
""")
SKY_HULL = "--nodraw-hull" not in sys.argv
open(os.path.join(BASE, "shaders", "shaderlist.txt"), "w").write("naboo_sys\n")

# ---- OBJ chunks by 1024-unit XY cell of the triangle centroid, at most 20000 triangles per file
CELL = 1024.0; MAXT = 20000
cen = tris.mean(1)
key = np.floor(cen[:, 0] / CELL).astype(np.int64) * 100003 + np.floor(cen[:, 1] / CELL).astype(np.int64)
order = np.argsort(key, kind="stable"); tris = tris[order]; key = key[order]
bounds = np.flatnonzero(np.diff(key)) + 1
groups = np.split(np.arange(len(tris)), bounds)
models = []
for g in groups:
    for s in range(0, len(g), MAXT):
        sub = tris[g[s:s + MAXT]]
        name = "%s_%03d.obj" % (mapname, len(models))
        P = sub.reshape(-1, 3)
        uq, inv = np.unique(P.round(3), axis=0, return_inverse=True)
        F = inv.reshape(-1, 3) + 1
        F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
        with open(os.path.join(BASE, "models", "naboo_col", name), "w") as f:
            f.write("# naboo collision chunk\nmtllib naboo_col.mtl\no chunk\n")
            # This q3map2 build loads OBJ as Y-up and converts (x, y, z) -> (x, -z, y). Measured on the first compile:
            # brushes came out with y = -z and z = y. Pre-rotate so the result is (x, y, z).
            f.write("".join("v %.3f %.3f %.3f\n" % (v[0], v[2], -v[1]) for v in uq))
            f.write("usemtl textures/naboo_sys/col\n")
            f.write("".join("f %d %d %d\n" % tuple(t) for t in F))
        models.append((name, len(F)))
open(os.path.join(BASE, "models", "naboo_col", "naboo_col.mtl"), "w").write("newmtl textures/naboo_sys/col\nKd 1 1 1\n")
print("wrote", len(models), "OBJ chunks,", sum(n for _, n in models), "triangles")


# ---- .map
def box(mins, maxs, tex):
    x0, y0, z0 = mins; x1, y1, z1 = maxs
    t = " %s 0 0 0 0.5 0.5 0 0 0\n" % tex
    return ("{\n"
            "( %g 0 0 ) ( %g 1 0 ) ( %g 0 1 )" % (x0, x0, x0) + t +
            "( %g 0 0 ) ( %g 0 1 ) ( %g 1 0 )" % (x1, x1, x1) + t +
            "( 0 %g 0 ) ( 0 %g 1 ) ( 1 %g 0 )" % (y0, y0, y0) + t +
            "( 0 %g 0 ) ( 1 %g 0 ) ( 0 %g 1 )" % (y1, y1, y1) + t +
            "( 0 0 %g ) ( 1 0 %g ) ( 0 1 %g )" % (z0, z0, z0) + t +
            "( 0 0 %g ) ( 0 1 %g ) ( 1 0 %g )" % (z1, z1, z1) + t + "}\n")


M = 64.0; T = 16.0
lo = np.floor((mn - M) / 64) * 64; hi = np.ceil((mx + np.array([M, M, 2048.0])) / 64) * 64
H = "naboo_sys/sky" if SKY_HULL else "naboo_sys/hull"   # .map texture names omit the textures/ prefix
hull = [box((lo[0] - T, lo[1], lo[2]), (lo[0], hi[1], hi[2]), H), box((hi[0], lo[1], lo[2]), (hi[0] + T, hi[1], hi[2]), H),
        box((lo[0], lo[1] - T, lo[2]), (hi[0], lo[1], hi[2]), H), box((lo[0], hi[1], lo[2]), (hi[0], hi[1] + T, hi[2]), H),
        box((lo[0], lo[1], lo[2] - T), (hi[0], hi[1], lo[2]), H), box((lo[0], lo[1], hi[2]), (hi[0], hi[1], hi[2] + T), H)]

# spawn points: farthest-point sampling over the candidates
spawns = []
sp = os.path.join(export_dir, "collision", "spawn_candidates.json")
if os.path.exists(sp):
    c = np.array([x["pos_m"] for x in json.load(open(sp))["candidates"]], dtype=np.float64)
    if len(c):
        cu = (c - ORG) * UPM
        zmed = np.median(cu[:, 2])
        cu = cu[np.abs(cu[:, 2] - zmed) < 60 * UPM]      # sanity band only; the exporter already keeps ground-level points
        n_all = len(cu)
        # 1. inside the built-up area: at least the median object density among candidates
        d = np.array([density(p[0], p[1]) for p in cu])
        thr = float(np.percentile(d, float(cfg.get("spawn_density_percentile", 50))))
        cu = cu[d >= max(thr, 1)]
        n_dense = len(cu)
        # 2. mutually reachable (proxy): largest group linked by neighbouring grid points with a small height step
        step_u = 1.6 * float(cfg["regions"].get(os.path.basename(os.path.normpath(export_dir)), {}).get("spawn_grid_m", 6.0)) * UPM
        lab = -np.ones(len(cu), np.int64); cur = 0
        for i0 in range(len(cu)):
            if lab[i0] >= 0:
                continue
            stack = [i0]; lab[i0] = cur
            while stack:
                i = stack.pop()
                near = np.flatnonzero((lab < 0) & (np.abs(cu[:, 0] - cu[i, 0]) <= step_u) & (np.abs(cu[:, 1] - cu[i, 1]) <= step_u) & (np.abs(cu[:, 2] - cu[i, 2]) <= 3.0 * UPM))
                lab[near] = cur; stack.extend(near.tolist())
            cur += 1
        big = np.bincount(lab).argmax(); cu = cu[lab == big]
        print("spawn candidates: %d total, %d in built-up cells, %d in the largest connected group (of %d groups)" % (n_all, n_dense, len(cu), cur))
        pick = [int(np.argmin(np.linalg.norm(cu[:, :2] - cu[:, :2].mean(0), axis=1)))]
        d = np.linalg.norm(cu - cu[pick[0]], axis=1)
        while len(pick) < min(int(cfg.get("spawn_count", 64)), len(cu)):
            i = int(np.argmax(d)); pick.append(i); d = np.minimum(d, np.linalg.norm(cu - cu[i], axis=1))
        centre = cu[:, :2].mean(0)
        for i in pick:
            p = cu[i]; yaw = np.degrees(np.arctan2(centre[1] - p[1], centre[0] - p[0]))
            spawns.append((p[0], p[1], p[2] + 40.0, yaw))
print("spawn points", len(spawns))

mp = os.path.join(BASE, "maps", mapname + ".map")
with open(mp, "w") as f:
    f.write('{\n"classname" "worldspawn"\n"message" "Naboo Theed collision prototype"\n"_blocksize" "1024 1024 0"\n"distanceCull" "60000"\n')
    f.write("".join(hull)); f.write("}\n")
    for name, _ in models:
        f.write('{\n"classname" "misc_model"\n"origin" "0 0 0"\n"model" "models/naboo_col/%s"\n"spawnflags" "2"\n}\n' % name)
    for i, (x, y, z, yaw) in enumerate(spawns):
        cls = "info_player_start" if i == 0 else "info_player_deathmatch"
        f.write('{\n"classname" "%s"\n"origin" "%.0f %.0f %.0f"\n"angle" "%.0f"\n}\n' % (cls, x, y, z, yaw))
print("wrote", mp)

if compile_:
    t0 = time.time()
    cmd = [Q3MAP2, "-game", "ja", "-fs_basepath", os.path.dirname(BASE), "-meta", mp]
    log = os.path.join(export_dir, "collision", "q3map2_%s.log" % mapname)
    with open(log, "w") as lf:
        rc = subprocess.call(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=os.path.dirname(Q3MAP2))
    dt = time.time() - t0
    bsp = os.path.join(BASE, "maps", mapname + ".bsp")
    print("q3map2 exit", rc, "seconds %.1f" % dt, "bsp bytes", os.path.getsize(bsp) if os.path.exists(bsp) else None, "log", log)
    json.dump({"q3map2_exit": rc, "seconds": round(dt, 1), "input_tris": int(sum(n for _, n in models)), "obj_chunks": len(models),
               "spawns": len(spawns), "bsp_bytes": os.path.getsize(bsp) if os.path.exists(bsp) else None,
               "hull_units": [lo.tolist(), hi.tolist()]}, open(os.path.join(export_dir, "collision", "bsp_build_%s.json" % mapname), "w"), indent=1)
