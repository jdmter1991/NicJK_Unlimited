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
# fixtures inside the palace: the source's daylight scene has no lights there, the better-lit palace file shows
# them on. One light per ceiling fixture and wall fixture (dump/scene.json), warm, 6 m and 3.5 m.
n_src = len(out)
FIX = cfg.get("palace_fixture_lights", {"lightceiling_01_a_mesh": [6.0, 1.3], "lightwall_06_a_mesh": [3.5, 0.8], "lightwall_01_a_mesh": [3.5, 0.8], "o_nab_palace_chandelier_01_mesh": [8.0, 1.6]})
PB = cfg.get("palace_bounds_units", [-2600, 7700, 250, 3300, 13850, 1400])
if FIX:
    sc = json.load(open(os.path.join(ed, "dump", "scene.json")))
    for it in sc["instances"]:
        f_ = FIX.get(it["mesh"])
        if not f_:
            continue
        p = (np.array(it["matrix"])[:3, 3] - ORG) * UPM
        if not (PB[0] < p[0] < PB[3] and PB[1] < p[1] < PB[4] and PB[2] < p[2] < PB[5]):
            continue
        c = np.array([1.0, 0.74, 0.46]) * f_[1]
        out.append(struct.pack("<8f", p[0], p[1], p[2], f_[0] * UPM, c[0], c[1], c[2], 0.0))
print(len(out) - n_src, "palace fixture lights added")
open(os.path.join(game, "maps", name + ".tlights"), "wb").write(struct.pack("<4sII", b"TLGT", 1, len(out)) + b"".join(out))
print(len(out), "lights written")
