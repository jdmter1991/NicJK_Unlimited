"""Normal maps from the height maps that the source feeds through a Bump node.
  py gen_bump_normals.py <export_dir>
pbr_survey.json lists, per material, the image behind the Principled BSDF's Normal input; where the chain contains a
Bump node that image is a height map. The renderer only reads tangent-space normal maps, so each such height map
h is converted: x = -k dh/dx, y = -k dh/dy (image axes, Sobel), z = 1, normalised, stored as RGB = n * 0.5 + 0.5
in dump/textures_pbr/<stem>_bumpn.png. This matches the renderer's tangent frame (T along +U, B along image rows).
k comes from the source (tools/bump_survey.py -> bump_survey.json): strength x distance (metres of height for a
full-range step) x image width / metres of surface per UV unit, i.e. the height difference between neighbouring
texels over their distance on the surface; the median over the materials that use the image, at most
"bump_normal_gain_max" (naboo_config.json, default 40). Without the survey a fixed 3 is used.
Flat images (range under 2 %) are skipped."""
import sys, os, json
import numpy as np
from PIL import Image

ed = sys.argv[1]

HERE = os.path.dirname(os.path.abspath(__file__))
KMAX = float(json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8")).get("bump_normal_gain_max", 40.0))
BS = json.load(open(os.path.join(ed, "bump_survey.json"))) if os.path.exists(os.path.join(sys.argv[1], "bump_survey.json")) else {}
S = json.load(open(os.path.join(ed, "pbr_survey.json")))
dump = os.path.join(ed, "dump"); out = os.path.join(dump, "textures_pbr"); os.makedirs(out, exist_ok=True)
imgs = {}
for k, e in S.items():
    n = e.get("Normal") or {}
    if n.get("image") and "bump" in n.get("ops", []) and n.get("coord") == "uv":
        imgs.setdefault(n["image"], []).append(k)
rep = {}
for img, users in sorted(imgs.items()):
    src = None
    for d_ in ("textures_all", "textures", "textures_pbr"):
        p = os.path.join(dump, d_, os.path.splitext(img)[0] + ".png")
        if os.path.exists(p):
            src = p; break
    if not src:
        rep[img] = {"materials": len(users), "result": "source image not exported"}; continue
    h = np.asarray(Image.open(src).convert("L")).astype(np.float32) / 255.0
    rng = float(h.max() - h.min())
    if rng < 0.02:
        rep[img] = {"materials": len(users), "result": "flat (range %.3f), skipped" % rng}; continue
    ks = []
    for u in users:
        b = (BS.get(u) or {}).get("bump"); mpu = (BS.get(u) or {}).get("metres_per_uv")
        if b and mpu and b.get("strength") is not None and b.get("distance") is not None:
            ks.append((b["strength"] * b["distance"] * h.shape[1] / mpu) * (-1.0 if b.get("invert") else 1.0))
    K = float(np.clip(np.median(ks), -KMAX, KMAX)) if ks else 3.0
    p = np.pad(h, 1, mode="wrap")
    gx = ((p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])) / 8.0
    gy = ((p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])) / 8.0
    n = np.stack([-K * gx, -K * gy, np.ones_like(h)], -1); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    rgba = np.concatenate([n * 0.5 + 0.5, np.ones(h.shape + (1,), np.float32)], -1)
    Image.fromarray((rgba * 255.0 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(out, os.path.splitext(img)[0] + "_bumpn.png"))
    rep[img] = {"materials": len(users), "result": "ok", "size": list(h.shape[::-1]), "height_range": round(rng, 3), "gain": round(K, 2), "gain_from_source": bool(ks), "mean_tilt_deg": round(float(np.degrees(np.arccos(n[..., 2])).mean()), 2)}
json.dump(rep, open(os.path.join(ed, "bump_normals.json"), "w"), indent=1)
for k, v in rep.items():
    print(k, v)
