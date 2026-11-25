"""Bake the source's layered materials into textures.
  py bake_materials.py <export_dir> [--only <substring>] [--limit N]
Reads  <export_dir>/color_graphs.json          expressions and image info (tools/color_graphs.py)
       <export_dir>/dump/materials.json, scene.json, pbr_survey.json
       images from dump/textures_all, dump/textures, dump/textures_pbr
Writes <export_dir>/dump/baked/<id>.png        RGB colour (display space), A = smoothness (1 - roughness)
       <export_dir>/dump/baked/baked.json      material -> {tex, tile, tile_scale, approximated, ...}

For every used opaque material whose colour is more than one texture times a constant, the colour and roughness
formulas are evaluated over the material's UV square (tools/matexpr.py).

Tiling layer: when the formula is (close to) a product of one colour texture that repeats several times over the
UV square and everything else, baking it into one map would blur that texture. Then the map stores "everything
else" (halved, the renderer multiplies base x tile x 2) and the tiling texture is kept as a separate layer.
"""
import sys, os, json, hashlib, time
import numpy as np
from PIL import Image
from matexpr import Images, Evaluator, Unsupported, images_in, linear_to_srgb, intern

t0 = time.time()
ed = sys.argv[1]
only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 10 ** 9
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8")).get("material_bake", {})
MAX_RES = int(cfg.get("max_size", 2048)); TILE_RES = int(cfg.get("tile_mode_size", 1024))
G = json.load(open(os.path.join(ed, "color_graphs.json")))
M = json.load(open(os.path.join(ed, "dump", "materials.json"), encoding="utf-8")); M = M["materials"] if "materials" in M else M
M = M if isinstance(M, dict) else {x["name"]: x for x in M}
S = json.load(open(os.path.join(ed, "pbr_survey.json")))
# materials assigned on objects instead of on their mesh (tools/export_object_materials.py, tools/color_graphs.py)
_mo = os.path.join(ed, "dump", "materials_objects.json"); _go = os.path.join(ed, "color_graphs_objects.json")
if os.path.exists(_mo) and os.path.exists(_go):
    M.update(json.load(open(_mo, encoding="utf-8")))
    _g2 = json.load(open(_go)); G["materials"].update(_g2["materials"]); G["images"].update(_g2["images"])
dump = os.path.join(ed, "dump")
ims = Images([os.path.join(dump, "textures_all"), os.path.join(dump, "textures"), os.path.join(dump, "textures_pbr")], G["images"])
out_dir = os.path.join(dump, "baked"); os.makedirs(out_dir, exist_ok=True)


def primary_uv(name):
    b = (S.get(name) or {}).get("Base Color") or {}
    return "UV1" if (b.get("image") and b.get("uv") == "UV1" and M.get(name, {}).get("base_image") == b["image"]) else "UV0"


def simple(e):
    """one texture, optionally times constants: the cooker's texture x tint already covers it"""
    if e[0] == "tex":
        return True
    if e[0] == "mix" and e[1] == "MULTIPLY":
        a, b = e[3], e[4]
        return (a[0] == "tex" and b[0] == "const") or (a[0] == "const" and b[0] == "tex")
    if e[0] == "vmath" and e[1] == "SCALE":
        return simple(e[2])
    return False


def grid(n):
    u = (np.arange(n, dtype=np.float32) + 0.5) / n
    U, Vt = np.meshgrid(u, u)
    return U, 1.0 - Vt                    # row 0 is the top of the image = Blender v near 1


def affine_of(ev, tnode):
    co = ev.coord(tnode[3])
    return co if (co is not None and co[0] == "affine") else None


def choose_period(ev, ce):
    """the smallest UV span (1, 2, 3, 4, 6 or 8 units) over which the most textures repeat a whole number of times"""
    scales = []
    for tn in images_in(ce):
        co = affine_of(ev, tn)
        if co is not None and abs(co[1]) > 1e-6 and abs(co[3]) > 1e-6:
            scales.append((abs(co[1]), abs(co[3])))
    best = (1, -1)
    for P in (1, 2, 3, 4, 6, 8):
        ok = sum(1 for su, sv in scales if round(su * P) >= 1 and round(sv * P) >= 1 and abs(su * P - round(su * P)) < 0.01 and abs(sv * P - round(sv * P)) < 0.01)
        if ok > best[1]:
            best = (P, ok)
    return best[0]


def scale_of(ev, tnode):
    co = ev.coord(tnode[3])
    if co is None or co[0] != "affine":
        return None
    return (round(co[1], 4), round(co[3], 4))


PART = None
if "--part" in sys.argv:
    PART = tuple(int(x) for x in sys.argv[sys.argv.index("--part") + 1].split("/"))
if "--merge" in sys.argv:
    meta = {}
    for f in sorted(os.listdir(out_dir)):
        if f.startswith("baked_part") and f.endswith(".json"):
            meta.update(json.load(open(os.path.join(out_dir, f))))
    json.dump(meta, open(os.path.join(out_dir, "baked_part%d.json" % PART[0] if PART else "baked.json"), "w"), indent=1)
    print("merged", len(meta), "materials,", len({m["tex"] for m in meta.values()}), "textures, tile mode", len({m["tex"] for m in meta.values() if m["tile"]}))
    sys.exit(0)
OLD = {}
_old = os.path.join(out_dir, "baked.json")
if os.path.exists(_old) and "--changed" in sys.argv:
    OLD = json.load(open(_old))                    # --changed: only materials that gain from a larger UV period are baked again
FORCE = "--force" in sys.argv
meta = {}; done = {}; stats = {"baked": 0, "tile_mode": 0, "reused": 0, "simple": 0, "unsupported": 0, "failed": {}}
names = [n for n in G["materials"] if n in M and M[n].get("cls") == "opaque" and not n.startswith("Terrain_")]
if only:
    names = [n for n in names if only.lower() in n.lower()]
for name in names[:limit]:
    g = G["materials"][name]
    ce, re_ = g["color"], g["roughness"]
    if ce is None or simple(ce):
        stats["simple"] += 1; continue
    puv = primary_uv(name)
    key = hashlib.sha1(json.dumps([ce, re_, puv]).encode()).hexdigest()[:16]
    _tab = {}; ce = intern(ce, _tab); re_ = intern(re_, _tab) if re_ is not None else None
    if key in done:
        meta[name] = done[key]; stats["reused"] += 1; continue
    if PART and int(key[:8], 16) % PART[1] != PART[0]:
        continue
    try:
        # ---- is there a tiling colour layer the formula is (nearly) proportional to?
        U, V = grid(64)
        probe = Evaluator(ims, U, V, primary_uv=puv)
        PER = choose_period(probe, ce)
        if name in OLD and int(OLD[name].get("uv_period", 1)) == PER and not FORCE:
            meta[name] = OLD[name]; done[key] = OLD[name]; stats["kept"] = stats.get("kept", 0) + 1; continue
        U, V = U * PER, V * PER

        def EV(n_=None, **kw):
            e_ = Evaluator(ims, U if n_ is None else n_[0], V if n_ is None else n_[1], primary_uv=puv, **kw); e_.period = float(PER)
            return e_
        cands = {}; phase = {}
        for tn in images_in(ce):
            if tn[2] != "Color":
                continue
            sc = scale_of(probe, tn); co_ = affine_of(probe, tn)
            if sc and sc[0] > 0 and sc[1] > 0 and sc[0] * PER >= 2 and sc[1] * PER >= 2 and abs(sc[0] * PER - round(sc[0] * PER)) < 0.01 and abs(sc[1] * PER - round(sc[1] * PER)) < 0.01:
                cands[(tn[1], sc)] = True; phase[(tn[1], sc)] = (co_[2], co_[4])
        tile = None
        for (img, sc) in sorted(cands, key=lambda k: -k[1][0]):
            e0 = EV(override={(img, sc): [0, 0, 0, 1]}).ev(ce)
            e1 = EV(override={(img, sc): [1, 1, 1, 1]}).ev(ce)
            A = float(np.mean(np.abs(e0))); Bm = float(np.mean(np.abs(np.asarray(e1) - np.asarray(e0))))
            if Bm > 1e-4 and A < 0.12 * Bm * float(ims.mean(img)[:3].mean()):
                tile = (img, sc); break
        res = TILE_RES if tile else MAX_RES
        if not tile:
            sizes = [G["images"].get(tn[1], {}).get("size", [1024])[0] for tn in images_in(ce) if tn[2] == "Color"]
            res = int(min(MAX_RES, max([256] + sizes)))
        U, V = grid(res)
        # the renderer samples the tiling layer at (scaled UV) x repeats, without the mapping's offset: shift the
        # baked map's origin so that the layer's phase is zero there (the cooker shifts the mesh UVs the same way)
        OFF = (0.0, 0.0)
        if tile and PER > 1:
            OFF = ((-phase[tile][0] / tile[1][0]) % (1.0 / tile[1][0]), (-phase[tile][1] / tile[1][1]) % (1.0 / tile[1][1]))
        U, V = U * PER + OFF[0], V * PER + OFF[1]
        ev = EV((U, V), override={tile: [1, 1, 1, 1]} if tile else None)
        col = np.broadcast_to(np.asarray(ev.ev(ce), np.float32), (res, res, 3))
        disp = linear_to_srgb(col)
        clipped = 0.0
        if tile:
            clipped = float((disp > 2.0).mean()); disp = disp * 0.5
        try:
            evr = EV((U, V))
            rough = np.broadcast_to(np.asarray(evr.ev(re_), np.float32), (res, res)) if re_ is not None else np.full((res, res), 0.7, np.float32)
            rough_ok = True
        except Unsupported:
            rough = np.full((res, res), 0.7, np.float32); rough_ok = False
        rgba = np.concatenate([np.clip(disp, 0, 1), (1.0 - np.clip(rough, 0, 1))[..., None]], -1)
        fn = "bk_%s.png" % key
        Image.fromarray((rgba * 255.0 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(out_dir, fn))
        m = {"tex": fn[:-4], "size": res, "uv": puv, "tile": os.path.splitext(tile[0])[0] if tile else None, "tile_scale": list(tile[1]) if tile else None,
             "approximated": sorted(ev.approx)[:8], "uv_period": int(PER), "uv_offset": [round(OFF[0], 6), round(OFF[1], 6)], "stretched": sorted(ev.snapped)[:8], "roughness_baked": rough_ok, "mean_srgb": [round(float(x), 3) for x in rgba[..., :3].mean((0, 1))],
             "clipped_share": round(clipped, 4)}
        done[key] = m; meta[name] = m
        stats["baked"] += 1; stats["tile_mode"] += 1 if tile else 0
    except Unsupported as ex:
        stats["unsupported"] += 1; stats["failed"][str(ex)] = stats["failed"].get(str(ex), 0) + 1
    if stats["baked"] % 25 == 0 and stats["baked"]:
        print("  baked %d (tile mode %d), reused %d, %.0f s" % (stats["baked"], stats["tile_mode"], stats["reused"], time.time() - t0), flush=True)
json.dump(meta, open(os.path.join(out_dir, "baked_part%d.json" % PART[0] if PART else "baked.json"), "w"), indent=1)
stats["materials_with_bake"] = len(meta); stats["seconds"] = round(time.time() - t0, 1)
stats["tile_images"] = sorted({m["tile"] for m in meta.values() if m["tile"]})
print(json.dumps(stats, indent=1))
