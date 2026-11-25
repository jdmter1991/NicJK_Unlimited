"""Bake the near terrain's colour from the source's terrain material, keeping its tiling textures at full resolution.
  py bake_ground.py <export_dir> [--tiles x0 y0 x1 y1] [--merge]
The source terrain (Terrain_Near) is a splat of twelve tiling textures (stone tiles, gravel, concrete, grass ...)
chosen by four mask images, times a colour map. Those textures repeat every 2-8 m at 1-2 mm per texel; no baked
map of a 64 m tile can hold that. So per terrain tile:

  * the dominant tiling layer is found (the layer that contributes most of the tile's colour);
  * the formula is evaluated twice, with that layer's texture black (A: what the other layers contribute) and
    white (A + B), in world space (tools/matexpr.py);
  * the baked map stores, in display space, base = disp(A + B*Tmean) / mix(1, 2*disp(Tmean), w) in RGB and
    w = share of the pixel's light that comes from the dominant layer in alpha (Tmean = the texture's mean colour).

The renderer draws colour = base x mix(1, tile x 2, w) with the tiling texture projected from world position at the
source's scale. Where the dominant layer covers the pixel this is exactly the source's texture times its
modulation; where another layer covers it, the pixel falls back to the baked colour.

Reads  <export_dir>/color_graphs.json (Terrain_Near), dump/meshes/terrain_grid.npz, images from dump/textures_all
Writes <export_dir>/dump/ground/gt_<tx>_<ty>.png and ground.json (tile size, padding, per tile: texture, size,
       tiling layer and its repeats per metre, the layer's share).
Each tile is baked with `pad` texels of surroundings on every side; the cooker maps the tile inside that border.
"""
import sys, os, json, time
import numpy as np
from PIL import Image
from matexpr import Images, Evaluator, linear_to_srgb, intern, images_in

t0 = time.time()
ed = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8")).get("ground_bake", {})
CELLS = int(cfg.get("tile_cells", 64)); SIZE = int(cfg.get("base_size", 512)); PAD = int(cfg.get("pad", 4))
MIN_SHARE = float(cfg.get("min_layer_share", 0.25))
G = json.load(open(os.path.join(ed, "color_graphs.json")))
dump = os.path.join(ed, "dump")
ims = Images([os.path.join(dump, "textures_all"), os.path.join(dump, "textures")], G["images"], max_cache=40)
tab = {}
ce = intern(G["materials"]["Terrain_Near"]["color"], tab)
grid = np.load(os.path.join(dump, "meshes", "terrain_grid.npz"))["grid"]
xs = grid[0, :, 0].astype(np.float64); ys = grid[:, 0, 1].astype(np.float64); side = len(xs)
out_dir = os.path.join(dump, "ground"); os.makedirs(out_dir, exist_ok=True)

# the tiling colour layers of the formula: (image, repeats per metre)
layers = {}
for tn in images_in(ce):
    if tn[2] == "Color" and tn[3][0] == "mapping" and tn[4] == "REPEAT":
        sc = tn[3][1]
        if abs(sc[0]) >= 0.05:
            layers[tn[1]] = float(sc[0])
print("tiling layers:", {k: v for k, v in layers.items()})
LUM = np.array([0.2126, 0.7152, 0.0722], np.float32)


def tile_grid(tx, ty, n):
    x0, x1 = xs[tx], xs[min(tx + CELLS, side - 1)]; y0, y1 = ys[ty], ys[min(ty + CELLS, side - 1)]
    tex_x = (x1 - x0) / (n - 2 * PAD); tex_y = (y1 - y0) / (n - 2 * PAD)
    X = x0 - PAD * tex_x + (np.arange(n) + 0.5) * tex_x
    Y = y1 + PAD * tex_y - (np.arange(n) + 0.5) * tex_y          # row 0 = largest y
    Xg, Yg = np.meshgrid(X.astype(np.float32), Y.astype(np.float32))
    return Xg, Yg


def evaluate(Xg, Yg, override=None):
    ev = Evaluator(ims, Xg, Yg, mode="world", normal=(0.0, 0.0, 1.0), override=override)
    return np.broadcast_to(np.asarray(ev.ev(ce), np.float32), Xg.shape + (3,))


def world_override(img, value):
    """in world mode the evaluator keys overrides by (image, None)"""
    return {(img, None): value}


sel = None
if "--tiles" in sys.argv:
    i = sys.argv.index("--tiles"); sel = [int(v) for v in sys.argv[i + 1:i + 5]]
tiles = {}; counts = {}
for ty in ([] if "--merge" in sys.argv else range(0, side - 1, CELLS)):
    for tx in range(0, side - 1, CELLS):
        if sel and not (sel[0] <= tx // CELLS <= sel[2] and sel[1] <= ty // CELLS <= sel[3]):
            continue
        # ---- dominant layer, at low resolution
        Xg, Yg = tile_grid(tx, ty, 32)
        full = float((evaluate(Xg, Yg) @ LUM).mean())
        best = None
        for img in layers:
            lo = float((evaluate(Xg, Yg, world_override(img, [0, 0, 0, 1])) @ LUM).mean())
            share = (full - lo) / max(full, 1e-6)
            if best is None or share > best[1]:
                best = (img, share)
        dom = best[0] if best and best[1] >= MIN_SHARE else None
        # ---- base and weight
        Xg, Yg = tile_grid(tx, ty, SIZE)
        if dom:
            A = evaluate(Xg, Yg, world_override(dom, [0, 0, 0, 1]))
            AB = evaluate(Xg, Yg, world_override(dom, [1, 1, 1, 1]))
            Bm = np.maximum(AB - A, 0.0)
            tmean = ims.mean(dom)[:3]
            true_mean = A + Bm * tmean
            w = np.clip((Bm * tmean) @ LUM / np.maximum(true_mean @ LUM, 1e-6), 0.0, 1.0)
            dt = linear_to_srgb(tmean)
            base = linear_to_srgb(true_mean) / (1.0 + (2.0 * dt - 1.0)[None, None, :] * w[..., None])
        else:
            base = linear_to_srgb(evaluate(Xg, Yg)); w = np.zeros(Xg.shape, np.float32)
        rgba = np.concatenate([np.clip(base, 0, 1), w[..., None]], -1)
        name = "gt_%d_%d" % (tx // CELLS, ty // CELLS)
        Image.fromarray((rgba * 255.0 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(out_dir, name + ".png"))
        tiles["%d,%d" % (tx, ty)] = {"tex": name, "size": SIZE, "tile": os.path.splitext(dom)[0] if dom else None, "tile_scale": layers[dom] if dom else None,
                                     "share": round(best[1], 3) if best else 0.0, "clipped": round(float((base > 1.0).mean()), 4)}
        counts[dom] = counts.get(dom, 0) + 1
    print("  row %d of %d, %d tiles, %.0f s" % (ty // CELLS + 1, (side - 1) // CELLS, len(tiles), time.time() - t0), flush=True)
if "--merge" in sys.argv:
    for f_ in sorted(os.listdir(out_dir)):
        if f_.startswith("ground_part") and f_.endswith(".json"):
            tiles.update(json.load(open(os.path.join(out_dir, f_)))["tiles"])
    for v in tiles.values():
        counts[v["tile"]] = counts.get(v["tile"], 0) + 1
    json.dump({"tile_cells": CELLS, "pad": PAD, "tiles": tiles}, open(os.path.join(out_dir, "ground.json"), "w"), indent=0)
elif sel:
    json.dump({"tile_cells": CELLS, "pad": PAD, "tiles": tiles}, open(os.path.join(out_dir, "ground_part_%d_%d.json" % (sel[0], sel[1])), "w"), indent=0)
else:
    json.dump({"tile_cells": CELLS, "pad": PAD, "tiles": tiles}, open(os.path.join(out_dir, "ground.json"), "w"), indent=0)
print(json.dumps({"seconds": round(time.time() - t0, 1), "tiles": len(tiles), "base_size": SIZE, "metres_per_texel_base": round(CELLS / (SIZE - 2 * PAD), 4),
                  "dominant_layers": {str(k): v for k, v in sorted(counts.items(), key=lambda kv: -kv[1])}}, indent=1))
