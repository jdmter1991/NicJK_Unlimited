"""Write maps/<name>.tlights from the source's light objects (tools/emission_survey.py).
  py write_lights.py <export_dir> <game_dir> <mapname>
Sun and the glows that belong to fire effects (collections with VFX in the name) are left out. Spot and area
lights are treated as point lights. Radius = 2.5 m * sqrt(watts / 10), between 2 and 9 m; colour times 0.9."""
import json, sys, os, struct
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ed, game, name = sys.argv[1:4]
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8")); UPM = cfg["units_per_metre"]; ORG = np.array(cfg["origin_m"])
E = json.load(open(os.path.join(ed, "emission_survey.json")))
out = []
for l in E["lights"]:
    col = l["collections"][0] if l["collections"] else ""
    if l["type"] == "SUN" or "VFX" in col:
        continue
    r_m = min(max(2.5 * (l["energy"] / 10.0) ** 0.5, 2.0), 9.0)
    p = (np.array(l["loc"]) - ORG) * UPM; c = np.array(l["color"]) * 0.9
    out.append(struct.pack("<8f", p[0], p[1], p[2], r_m * UPM, c[0], c[1], c[2], 0.0))
open(os.path.join(game, "maps", name + ".tlights"), "wb").write(struct.pack("<4sII", b"TLGT", 1, len(out)) + b"".join(out))
print(len(out), "lights written")
