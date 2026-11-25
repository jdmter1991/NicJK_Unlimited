"""Second pass over the ground bake: terrain tiles where the source blends several tiling textures.
  py bake_ground_packs.py <export_dir> [--tiles x0 y0 x1 y1]
bake_ground.py keeps ONE tiling layer per terrain tile at full resolution. In the city the source's terrain
material blends two or three (e.g. 71 % stone tiles and 26 % concrete in the streets, three around the pond), so
most of the detail stayed in the blurred baked map. For every tile whose second layer contributes at least
`pack_min_second_share` of the light this pass writes instead:

  gt_<x>_<y>.png  base colour: the formula with every tiling texture replaced by its mean colour (display space)
  gw_<x>_<y>.png  weights: RGB = share of each pixel's light that comes from layers 1-4 (RGBA)
  gp_<...>.png    one "pack" per combination of layers (shared between tiles): R, G, B, A = each layer's brightness
                  relative to its mean, times 0.5, tiled over the common period of the layers

The renderer draws colour = base x (1 + sum_i w_i x (2 x pack_i - 1)), the pack projected from world position.
Only the layers' brightness pattern is kept, their hue comes from the base map: within these textures the
colour varies by about 0.01 around brightness x mean colour, the brightness by 0.03 - 0.18.
Tiles with a single layer keep the colour path of bake_ground.py. Updates dump/ground/ground.json.
"""
import sys, os, json, time, math
import numpy as np
from PIL import Image
from matexpr import Images, Evaluator, linear_to_srgb, intern, images_in

Image.MAX_IMAGE_PIXELS = None
t0 = time.time()
ed = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8")).get("ground_bake", {})
MIN2 = float(cfg.get("pack_min_second_share", 0.04)); MINL = float(cfg.get("pack_min_layer_share", 0.03))
G = json.load(open(os.path.join(ed, "color_graphs.json")))
dump = os.path.join(ed, "dump"); out_dir = os.path.join(dump, "ground")
GJ = json.load(open(os.path.join(out_dir, "ground.json")))
CELLS = int(GJ["tile_cells"]); PAD = int(GJ["pad"])
tex_dirs = [os.path.join(dump, "textures_all"), os.path.join(dump, "textures")]
ims = Images(tex_dirs, G["images"], max_cache=40)
ce = intern(G["materials"]["Terrain_Near"]["color"], {})
grid = np.load(os.path.join(dump, "meshes", "terrain_grid.npz"))["grid"]
xs = grid[0, :, 0].astype(np.float64); ys = grid[:, 0, 1].astype(np.float64); side = len(xs)
layers = {}
for tn in images_in(ce):
    if tn[2] == "Color" and tn[3][0] == "mapping" and tn[4] == "REPEAT" and abs(tn[3][1][0]) >= 0.05:
        layers[tn[1]] = float(tn[3][1][0])
LUM = np.array([0.2126, 0.7152, 0.0722], np.float32)
MEAN = {(n, None): [float(v) for v in ims.mean(n)[:3]] + [1.0] for n in layers}


def tile_grid(tx, ty, n):
    x0, x1 = xs[tx], xs[min(tx + CELLS, side - 1)]; y0, y1 = ys[ty], ys[min(ty + CELLS, side - 1)]
    tex_x = (x1 - x0) / (n - 2 * PAD); tex_y = (y1 - y0) / (n - 2 * PAD)
    X = x0 - PAD * tex_x + (np.arange(n) + 0.5) * tex_x
    Y = y1 + PAD * tex_y - (np.arange(n) + 0.5) * tex_y
    return np.meshgrid(X.astype(np.float32), Y.astype(np.float32))


def evaluate(Xg, Yg, black=None):
    ov = dict(MEAN)
    if black:
        ov[(black, None)] = [0.0, 0.0, 0.0, 1.0]
    ev = Evaluator(ims, Xg, Yg, mode="world", normal=(0.0, 0.0, 1.0), override=ov)
    return np.broadcast_to(np.asarray(ev.ev(ce), np.float32), Xg.shape + (3,))


def source_image(name):
    for d_ in tex_dirs:
        p = os.path.join(d_, name)
        if os.path.exists(p):
            return Image.open(p).convert("RGBA")
    raise FileNotFoundError(name)


PACKS = {}
CONTRAST = {}


def contrast(n):
    """standard deviation of the layer's brightness relative to its mean: how much detail is lost without it"""
    if n not in CONTRAST:
        a = np.asarray(source_image(n).resize((512, 512), Image.BILINEAR)).astype(np.float32) / 255.0
        Y = a[..., :3] @ LUM; CONTRAST[n] = float((Y / max(float(Y.mean()), 1e-6)).std())
    return CONTRAST[n]



def make_pack(names):
    """names: up to four layer images in a fixed order. Returns (pack name, repeats per metre, mean of each channel)."""
    key = tuple(names)
    if key in PACKS:
        return PACKS[key]
    periods = [int(round(12.0 / layers[n])) for n in names]            # in twelfths of a metre... periods of 2, 3, 4, 8 m
    P12 = 1
    for p in periods:
        P12 = P12 * p // math.gcd(P12, p)
    P = P12 / 12.0                                                     # common period in metres
    size = 2048 if P <= 8.0 else 4096
    short = lambda n: n.replace("T_Naboo_", "").replace("T_NAT_TAK_", "").replace("_CS.png", "").replace("_", "").lower()
    pname = "gp_%02d" % len(PACKS)                                  # short: material names are limited to 64 characters
    out = np.full((size, size, 4), 128, np.uint8); means = []
    for c, n in enumerate(names):
        rep = int(round(P * layers[n])); im = source_image(n)
        per = size / rep
        im = im.resize((max(int(round(per)), 4),) * 2, Image.LANCZOS)
        a = np.asarray(im).astype(np.float32) / 255.0
        Y = a[..., :3] @ LUM
        D = np.clip(0.5 * Y / max(float(Y.mean()), 1e-6), 0.0, 1.0)
        # tile `rep` times over the pack; exact copies when the size divides evenly, nearest texel otherwise
        idx = np.floor((np.arange(size) + 0.5) / size * rep * D.shape[0]).astype(np.int64) % D.shape[0]
        out[..., c] = (D[np.ix_(idx, idx)] * 255.0 + 0.5).astype(np.uint8)
        means.append(float(out[..., c].mean()) / 255.0)
    Image.fromarray(out, "RGBA").save(os.path.join(out_dir, pname + ".png"))
    PACKS[key] = (pname, 1.0 / P, means + [0.5] * (4 - len(means)), size)
    print("  pack %s: period %.0f m, %d px, layers %s" % (pname, P, size, list(names)), flush=True)
    return PACKS[key]


sel = None
if "--tiles" in sys.argv:
    i = sys.argv.index("--tiles"); sel = [int(v) for v in sys.argv[i + 1:i + 5]]
n_pack = 0; n_single = 0; combos = {}
for key in sorted(GJ["tiles"], key=lambda k: tuple(int(v) for v in k.split(","))):
    tx, ty = (int(v) for v in key.split(","))
    if sel and not (sel[0] <= tx // CELLS <= sel[2] and sel[1] <= ty // CELLS <= sel[3]):
        continue
    t = GJ["tiles"][key]
    Xg, Yg = tile_grid(tx, ty, 32)
    fullmap = np.maximum(evaluate(Xg, Yg) @ LUM, 1e-6); full = float(fullmap.mean())
    sh = []; score = {}
    for n in layers:
        dmap = np.maximum(fullmap - evaluate(Xg, Yg, n) @ LUM, 0.0)
        s_ = float(dmap.mean()) / full
        # share of the light inside each 8 m block (4 x 4 samples): a layer that fills a small patch still counts
        peak = float((dmap.reshape(8, 4, 8, 4).mean((1, 3)) / fullmap.reshape(8, 4, 8, 4).mean((1, 3))).max())
        sh.append((s_, n)); score[n] = contrast(n) * (0.5 * s_ + 0.5 * peak) if s_ >= 0.003 else 0.0
    sh.sort(reverse=True)
    t["shares"] = {n: round(s, 3) for s, n in sh if s >= 0.005}
    for k_ in ("pack", "pack_scale", "weights", "layers", "covered"):
        t.pop(k_, None)
    if sh[1][0] < MIN2 and max(score[n] for s, n in sh[1:]) < 0.01:
        n_single += 1
        continue
    names = sorted(sorted((n for n in layers if score[n] > 0.0), key=lambda n: -score[n])[:4])
    pname, pscale, pmeans, psize = make_pack(names)
    Xg, Yg = tile_grid(tx, ty, int(t["size"]))
    M = evaluate(Xg, Yg); Ml = np.maximum(M @ LUM, 1e-6)
    W = np.zeros(Xg.shape + (4,), np.float32)
    for c, n in enumerate(names):
        W[..., c] = np.clip(np.maximum(M - evaluate(Xg, Yg, n), 0.0) @ LUM / Ml, 0.0, 1.0)
    corr = 1.0 + (W * (2.0 * np.array(pmeans, np.float32) - 1.0)).sum(-1)
    base = np.clip(linear_to_srgb(M) / corr[..., None], 0.0, 1.0)
    rgba = np.concatenate([base, np.ones(Xg.shape + (1,), np.float32)], -1)
    if len(names) < 4:
        W[..., 3] = 0.0
    Image.fromarray((rgba * 255.0 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(out_dir, t["tex"] + ".png"))
    wname = t["tex"].replace("gt_", "gw_")
    Image.fromarray((W * 255.0 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(out_dir, wname + ".png"))
    t.update({"pack": pname, "pack_scale": pscale, "weights": wname, "layers": names, "covered": round(float(W.sum(-1).mean()), 3)})
    n_pack += 1; combos[pname] = combos.get(pname, 0) + 1
    if n_pack % 10 == 0:
        print("  %d pack tiles, %d single, %.0f s" % (n_pack, n_single, time.time() - t0), flush=True)
json.dump(GJ, open(os.path.join(out_dir, "ground.json"), "w"), indent=0)
print(json.dumps({"seconds": round(time.time() - t0, 1), "tiles_with_blended_layers": n_pack, "single_layer_tiles": n_single, "packs": combos,
                  "pack_sizes": {v[0]: v[3] for v in PACKS.values()}}, indent=1))
