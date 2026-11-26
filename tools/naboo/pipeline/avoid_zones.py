"""Areas bots should not use and players should not spawn in (config "avoid_zones"), shared by make_bot_routes.py
and centre_spawns.py. A zone is a box in engine units [x0, y0, x1, y1]; with "lawn_only" only the points in it that
stand on the terrain where the source's terrain material is mostly grass count (the baked ground weight maps,
export/city/dump/ground/gw_*.png, tools/bake_ground_packs.py), so paved streets and buildings in the box stay in use.
  avoided(x, y, z) -> bool array"""
import os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
ZONES = cfg.get("avoid_zones", [])
DUMP = os.path.join(ROOT, "export", "city", "dump")
_g = None; _ground = None; _imgs = {}


def _grid():
    global _g
    if _g is None:
        g = np.load(os.path.join(DUMP, "extras", "terrain_near_carved.npz"))["grid"].astype(np.float64)
        _g = (g[0, :, 0], g[:, 0, 1], g[:, :, 2])
    return _g


def terrain_z(x, y):
    """engine units"""
    gxm, gym, gzm = _grid()
    xm = x / UPM + ORG[0]; ym = y / UPM + ORG[1]
    i = np.clip(np.rint((xm - gxm[0]) / (gxm[1] - gxm[0])).astype(np.int64), 0, len(gxm) - 1)
    j = np.clip(np.rint((ym - gym[0]) / (gym[1] - gym[0])).astype(np.int64), 0, len(gym) - 1)
    return (gzm[j, i] - ORG[2]) * UPM, i, j


def grass_weight(x, y):
    global _ground
    if _ground is None:
        _ground = json.load(open(os.path.join(DUMP, "ground", "ground.json")))
    from PIL import Image
    tc = int(_ground["tile_cells"]); pad = float(_ground["pad"]); side = len(_grid()[0])
    _, i, j = terrain_z(x, y)
    out = np.zeros(len(x))
    for k in range(len(x)):
        tx = (i[k] // tc) * tc; ty = (j[k] // tc) * tc
        t = _ground["tiles"].get("%d,%d" % (tx, ty))
        if not t or "weights" not in t:
            continue
        layers = t.get("layers", [])
        gl = [n for n, l in enumerate(layers) if "grass" in l.lower()]
        if not gl:
            continue
        if t["weights"] not in _imgs:
            _imgs[t["weights"]] = np.asarray(Image.open(os.path.join(DUMP, "ground", t["weights"] + ".png")).convert("RGBA"), np.float64) / 255.0
        im = _imgs[t["weights"]]; n = im.shape[0]
        cx = float(min(tx + tc, side - 1) - tx); cy = float(min(ty + tc, side - 1) - ty)
        fx = (i[k] - tx) / cx; fy = (j[k] - ty) / cy
        px = int(np.clip(pad + fx * (n - 2 * pad), 0, n - 1)); py = int(np.clip(pad + (1.0 - fy) * (n - 2 * pad), 0, n - 1))
        w = im[py, px, :len(layers)]
        s = w.sum()
        out[k] = w[gl].sum() / s if s > 1e-6 else 0.0
    return out


def avoided(x, y, z):
    x = np.atleast_1d(np.asarray(x, np.float64)); y = np.atleast_1d(np.asarray(y, np.float64)); z = np.atleast_1d(np.asarray(z, np.float64))
    r = np.zeros(len(x), bool)
    for zn in ZONES:
        b = zn["box"]
        inb = (x > b[0]) & (x < b[2]) & (y > b[1]) & (y < b[3])
        if not inb.any():
            continue
        if zn.get("lawn_only", False):
            idx = np.flatnonzero(inb)
            tz, _, _ = terrain_z(x[idx], y[idx])
            on = np.abs(z[idx] - tz) < float(zn.get("terrain_tolerance", 40.0))
            gw = np.zeros(len(idx)); gw[on] = grass_weight(x[idx][on], y[idx][on])
            r[idx] |= on & (gw >= float(zn.get("min_grass", 0.5)))
        else:
            r |= inb
    return r
