"""Give every glowing fixture of the cooked world a light (candles, lamp glass, glow strips), so nothing glows without
lighting its surroundings.
  py glow_lights.py <game_dir> <mapname>
Reads  <game>/maps/<mapname>.tworld           materials (glowing ones: animation type 5), meshes, placements
       export/city/emissive_parts.json         emissive parts of the source (street lamp posts ...), when present
       <game>/maps/<mapname>.tlights          the lights the cook made from the source's light objects; the original is
                                              kept as <mapname>_source.tlights and is the input of every later run
Writes <game>/maps/<mapname>.tlights          the source lights plus one light per glowing fixture that has none:
                                              glowing parts of the nearest detail level, merged within `merge` (64) units,
                                              left out when a source light is within `covered` (80) units; radius from
                                              the fixture's size (candle 120 .. lamp 300 units), colour from the
                                              material's tint at 0.4 of the source lights' typical strength
       <game>/maps/<mapname>_glow_lights.json counts
Run bake_lamp_occlusion.py afterwards (the occlusion maps follow the light list)."""
import sys, os, struct, json, shutil
import numpy as np

game, mapname = sys.argv[1], sys.argv[2]
MERGE = 64.0; COVERED = 80.0; MAXL = 4095; GAIN = 0.4
# decorative bulb strings wound round trees and strung between poles: they glow, but a light at each would light the
# leaves around them and make the trees glow (user, 2026-11-27: "trees should not glow, only the lightbulbs, candles,
# chandelier etc")
NO_LIGHT = ("lightground_03",)
md = os.path.join(game, "maps")
src_p = os.path.join(md, mapname + "_source.tlights"); cur_p = os.path.join(md, mapname + ".tlights")
if not os.path.exists(src_p):
    shutil.copyfile(cur_p, src_p)
d = open(src_p, "rb").read(); n0 = struct.unpack_from("<I", d, 8)[0]
SRC = np.frombuffer(d, dtype="<f4", count=n0 * 8, offset=12).reshape(-1, 8).astype(np.float64)

w = np.memmap(os.path.join(md, mapname + ".tworld"), dtype=np.uint8, mode="r")
magic, ver, nmat, nmesh, nsub, ninst, nvert, nidx = struct.unpack_from("<4sIIIIIII", w, 0); o = 112
mats = np.frombuffer(w, dtype=[("shader", "S64"), ("tint", "<f4", 3), ("flags", "<u4")], count=nmat, offset=o); o += nmat * 80
meshes = np.frombuffer(w, dtype=[("fv", "<u4"), ("nv", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("nl", "<u4"), ("lfs", "<u4", 3), ("lns", "<u4", 3), ("c", "<f4", 3), ("r", "<f4")], count=nmesh, offset=o); o += nmesh * 60
subs = np.frombuffer(w, dtype=[("mat", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("res", "<u4")], count=nsub, offset=o); o += nsub * 16
insts = np.frombuffer(w, dtype=[("mesh", "<u4"), ("m", "<f4", 12), ("c", "<f4", 3), ("r", "<f4")], count=ninst, offset=o); o += ninst * 68
verts = np.frombuffer(w, dtype=[("xyz", "<f4", 3), ("n", "<f4", 3), ("st", "<f4", 2)], count=nvert, offset=o); o += nvert * 32
idx = np.frombuffer(w, dtype="<u4", count=nidx, offset=o)
glow = ((mats["flags"].astype(np.int64) >> 1) & 7) == 5
names = [m.decode(errors="replace") for m in mats["shader"]]
# per mesh: centre and size (mesh space) and colour of its glowing parts at the nearest detail level
mesh_glow = {}
for mi, me in enumerate(meshes):
    pts = []; col = []
    for s in range(int(me["lfs"][0]), int(me["lfs"][0]) + int(me["lns"][0])):
        sb = subs[s]
        if not glow[sb["mat"]] or any(k in names[sb["mat"]] for k in NO_LIGHT):
            continue
        t = idx[me["fi"] + sb["fi"]:me["fi"] + sb["fi"] + sb["ni"]]
        P = verts["xyz"][me["fv"] + np.unique(t)].astype(np.float64)
        pts.append(P); col.append(mats["tint"][sb["mat"]])
    if pts:
        P = np.concatenate(pts)
        mesh_glow[mi] = (P, np.mean(col, 0))
cand = []          # world centre, size, colour
for ii in range(ninst):
    mi = int(insts["mesh"][ii])
    if mi not in mesh_glow:
        continue
    P, c = mesh_glow[mi]
    M = insts["m"][ii].reshape(3, 4).astype(np.float64)
    W = P @ M[:, :3].T + M[:, 3]
    # a fixture with several separate glowing parts (a chandelier) gives one point per part cluster
    k = np.floor(W / MERGE).astype(np.int64)
    _, inv = np.unique(k, axis=0, return_inverse=True)
    for g in range(inv.max() + 1):
        Q = W[inv.ravel() == g]
        cand.append((Q.mean(0), float(np.linalg.norm(Q.max(0) - Q.min(0))), c))
# emissive parts of the source that the cook did not turn into glowing materials (street lamp posts and others):
# export/city/emissive_parts.json from Blender (object, material, x, y, z, size in units, emission colour)
_emi = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "export", "city", "emissive_parts.json")
n_emi = 0
if os.path.exists(_emi):
    for ob_, mt_, x_, y_, z_, sz_, col_ in json.load(open(_emi)):
        c_ = np.asarray(col_, np.float64)
        if c_.max() < 0.05:
            c_ = np.array([1.0, 0.85, 0.6])
        cand.append((np.array([x_, y_, z_]), float(sz_), c_)); n_emi += 1
# merge candidates within MERGE units (greedy), drop those a source light covers
cand.sort(key=lambda x: -x[1])
taken = np.zeros(len(cand), bool); out = []
C = np.array([x[0] for x in cand]).reshape(-1, 3)
for i in range(len(cand)):
    if taken[i]:
        continue
    near = np.flatnonzero(~taken & (np.linalg.norm(C - C[i], axis=1) < MERGE))
    taken[near] = True
    p = C[near].mean(0); size = max(cand[j][1] for j in near); col = np.mean([cand[j][2] for j in near], 0)
    if len(SRC) and np.linalg.norm(SRC[:, :3] - p, axis=1).min() < COVERED:
        continue
    if out and min(np.linalg.norm(q[0] - p) for q in out) < COVERED:
        continue
    out.append((p, size, col, len(near)))
typical = float(np.median(SRC[:, 4:7].max(1))) if len(SRC) else 0.8
new = []
for p, size, col, cnt in out:
    # candle-sized parts (a flame, a bulb) light a small circle, lamp glass and glow strips a wider one; generated lights
    # are dimmer than the source's own lights, which were set by hand for the fixtures they belong to
    r = float(np.clip(120.0 + size * 2.0, 120.0, 300.0))
    c = np.asarray(col, np.float64); c = c / max(c.max(), 1e-6) * typical * GAIN * min(1.6, 0.9 + 0.08 * cnt)
    new.append([p[0], p[1], p[2], r, c[0], c[1], c[2], 0.0])
room = MAXL - n0
dropped = max(0, len(new) - room)
if dropped:
    new.sort(key=lambda L: -L[3]); new = new[:room]
ALL = np.concatenate([SRC, np.array(new, np.float64).reshape(-1, 8)]).astype("<f4")
with open(cur_p, "wb") as f:
    f.write(struct.pack("<4sII", b"TLGT", 1, len(ALL))); f.write(ALL.tobytes())
rep = {"source_lights": int(n0), "emissive_parts_from_source": n_emi, "glowing_meshes": len(mesh_glow), "glowing_parts": len(cand), "fixtures_without_light": len(out),
       "added": len(new), "dropped_over_limit": int(dropped), "total": int(len(ALL))}
json.dump(rep, open(os.path.join(md, mapname + "_glow_lights.json"), "w"), indent=1)
print(json.dumps(rep))
