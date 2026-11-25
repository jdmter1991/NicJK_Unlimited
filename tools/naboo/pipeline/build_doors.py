"""Opening doors: the palace entrance (two leaves) and the one solid door leaf inside the palace.
  py build_doors.py <export_dir> <game_dir>/taystjk
The static world cannot move anything, so these leaves leave it and come back as game entities:
  * each leaf becomes an MD3 model (models/map_objects/naboo_theed/door_<n>.md3, vertices relative to the leaf's
    centre, the placement's rotation baked in) with a shader that uses the same baked texture as the static world;
  * <export_dir>/doors.json lists, for tools/cook_v1.py, the placements to leave out of the cooked world, and for
    tools/write_collision_bsp.py the world boxes whose static collision is removed, one collision box per leaf
    (in the leaf's own frame) and the func_door entity text.
Doors slide sideways along their own width into the wall (func_door moves in a straight line; the game has no
swinging doors). The two entrance leaves share a team, so they open together.
The entrance object of the source also contains a blasted-open "destroyed" variant of the door (its second
material); it is dropped."""
import sys, os, json, struct, math
import numpy as np

ed, game = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], np.float64)
dump = os.path.join(ed, "dump")
sc = json.load(open(os.path.join(dump, "scene.json")))
BAKED = json.load(open(os.path.join(dump, "baked", "baked.json")))
MATS = json.load(open(os.path.join(dump, "materials.json"))); MATS = MATS.get("materials", MATS)
SPEC = cfg.get("doors", [
    {"mesh": "o_nab_doorpalace_destructible_01_mesh", "slots": [0], "split": True, "speed": 60, "wait": 4},
    {"mesh": "o_nab_buildinglargedoor_door_02_mesh", "slots": None, "split": False, "speed": 80, "wait": 3, "bounds_units": [-2600, 7700, 3300, 13850]},
])
MODEL_DIR = "models/map_objects/naboo_theed"
os.makedirs(os.path.join(game, MODEL_DIR), exist_ok=True)
os.makedirs(os.path.join(game, "shaders"), exist_ok=True)


def san(s):
    return "".join(c if c.isalnum() or c == "_" else "_" for c in s).lower()


def latlong(n):
    """MD3 normal: two bytes, longitude and latitude"""
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    lat = np.arccos(np.clip(n[:, 2], -1, 1)); lng = np.arctan2(n[:, 1], n[:, 0])
    la = np.round(lat * 255.0 / (2 * np.pi)).astype(np.int64) & 255; lo = np.round(lng * 255.0 / (2 * np.pi)).astype(np.int64) & 255
    return (la << 8 | lo).astype("<u2")


def write_md3(path, surfaces):
    """surfaces: list of (shader name, pos (N,3) local units, normals (N,3), st (N,2), tris (T,3)); one frame"""
    blobs = []; allp = np.concatenate([s[1] for s in surfaces])
    for si, (sh, pos, nrm, st, tris) in enumerate(surfaces):
        nv, nt = len(pos), len(tris)
        xyz = np.zeros(nv, dtype=[("p", "<i2", 3), ("n", "<u2")])
        xyz["p"] = np.clip(np.round(pos * 64.0), -32767, 32767).astype("<i2"); xyz["n"] = latlong(nrm)
        shader = struct.pack("<64si", sh.encode("ascii"), 0)
        tri_b = tris.astype("<i4").tobytes(); st_b = st.astype("<f4").tobytes(); xyz_b = xyz.tobytes()
        ofs_tri = 108; ofs_sh = ofs_tri + len(tri_b); ofs_st = ofs_sh + len(shader); ofs_xyz = ofs_st + len(st_b); ofs_end = ofs_xyz + len(xyz_b)
        head = struct.pack("<4s64siiiiiiiiii", b"IDP3", ("leaf%d" % si).encode("ascii"), 0, 1, 1, nv, nt, ofs_tri, ofs_sh, ofs_st, ofs_xyz, ofs_end)
        assert len(head) == 108
        blobs.append(head + tri_b + shader + st_b + xyz_b)
    mn = allp.min(0); mx = allp.max(0)
    frame = struct.pack("<3f3f3ff16s", *mn, *mx, 0.0, 0.0, 0.0, float(np.linalg.norm(np.maximum(np.abs(mn), np.abs(mx)))), b"door")
    ofs_frames = 108; ofs_tags = ofs_frames + len(frame); ofs_surf = ofs_tags; ofs_end = ofs_surf + sum(len(b) for b in blobs)
    head = struct.pack("<4si64siiiiiiiii", b"IDP3", 15, os.path.basename(path).encode("ascii"), 0, 1, 0, len(surfaces), 0, ofs_frames, ofs_tags, ofs_surf, ofs_end)
    assert len(head) == 108
    open(path, "wb").write(head + frame + b"".join(blobs))


doors = []; skip = []; clear = []; shader_text = {}; n_model = 0
for spec in SPEC:
    me = sc["meshes"][spec["mesh"]]
    a = np.load(os.path.join(dump, "meshes", me["file"]))
    lv = a["loop_vert"].astype(np.int64); tl = a["tri_loops"].astype(np.int64); tm = a["tri_mat"].astype(np.int64)
    names = me.get("materials") or [None]
    for it in sc["instances"]:
        if it["mesh"] != spec["mesh"]:
            continue
        M = np.array(it["matrix"], np.float64); R = M[:3, :3]; t = (M[:3, 3] - ORG) * UPM
        b_ = spec.get("bounds_units")
        if b_ and not (b_[0] <= t[0] <= b_[2] and b_[1] <= t[1] <= b_[3]):
            continue                                           # the same door mesh in the city stays static
        skip.append(it["name"])
        Pw_all = (a["pos"].astype(np.float64) * UPM) @ R.T + t
        clear.append({"mins": (Pw_all.min(0) - 2.0).tolist(), "maxs": (Pw_all.max(0) + 2.0).tolist()})
        use = np.isin(tm, spec["slots"]) if spec["slots"] is not None else np.ones(len(tm), bool)
        ext_l = a["pos"].max(0) - a["pos"].min(0)
        thin = int(np.argmin(ext_l)); wide = [i for i in (0, 1) if i != thin][0] if thin != 2 else 0
        cen_w = (a["pos"][lv[tl]].mean(1))[:, wide]
        mid = float((a["pos"][lv[tl[use]]].reshape(-1, 3)[:, wide].min() + a["pos"][lv[tl[use]]].reshape(-1, 3)[:, wide].max()) / 2)
        parts = [(use & (cen_w < mid), -1.0), (use & (cen_w >= mid), 1.0)] if spec["split"] else [(use, 1.0)]
        team = "naboo_door_%d" % len(doors) if spec["split"] else None
        for sel, sign in parts:
            loops = tl[sel]                                    # (T,3) loop indices
            # one vertex per loop, welded on position / normal / uv
            surfaces = []; Pl_all = []
            for slot in np.unique(tm[sel]):
                lp = tl[sel & (tm == slot)]
                mname = names[slot] if slot < len(names) else None
                bk = BAKED.get(mname) if mname else None
                uvn = "uv1" if (bk and bk.get("uv") == "UV1" and "uv1" in a.files) else "uv0"
                tex = bk["tex"] if bk else san(os.path.splitext((MATS.get(mname, {}).get("base_image") or "white"))[0])[:44]
                fl = lp.ravel()
                pos_l = a["pos"][lv[fl]].astype(np.float64) * UPM; nrm_l = a["loop_normal"][fl].astype(np.float64); uv = a[uvn][fl].astype(np.float64)
                key = np.concatenate([np.round(pos_l * 16), np.round(nrm_l * 64), np.round(uv * 4096)], 1)
                uq, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
                pw = pos_l[first] @ R.T + t; nw = nrm_l[first] @ np.linalg.inv(R)
                st = uv[first].copy(); st[:, 1] = 1.0 - st[:, 1]
                tri = inv.reshape(-1, 3)[:, ::-1]              # the game's models wind the other way round
                sname = "models/map_objects/naboo_theed/" + tex
                shader_text[sname] = "%s\n{\n\tcull none\n\t{\n\t\tmap textures/naboo/%s\n\t\trgbGen const ( 0.5 0.47 0.44 )\n\t}\n}\n" % (sname, tex)
                # split into chunks of at most 900 vertices (the engine's limit per model surface)
                tri_left = tri
                while len(tri_left):
                    used = []; seen = set(); k = 0
                    while k < len(tri_left) and len(seen | set(tri_left[k].tolist())) <= 900:
                        seen |= set(tri_left[k].tolist()); k += 1
                    chunk = tri_left[:k]; tri_left = tri_left[k:]
                    ids = np.array(sorted(seen), np.int64); remap = np.full(len(pw), -1, np.int64); remap[ids] = np.arange(len(ids))
                    surfaces.append([sname, pw[ids], nw[ids], st[ids], remap[chunk]]); Pl_all.append(pw[ids])
            allw = np.concatenate(Pl_all)
            origin = np.round((allw.min(0) + allw.max(0)) / 2.0)
            for s_ in surfaces:
                s_[1] = s_[1] - origin
            path = "%s/door_%d.md3" % (MODEL_DIR, n_model); n_model += 1
            write_md3(os.path.join(game, path), [tuple(s_) for s_ in surfaces])
            # collision box in the leaf's own frame: the placement's axes (unit length), half extents along them
            axes = R / np.linalg.norm(R, axis=0, keepdims=True)                # columns = local x, y, z in world
            loc = (allw - origin) @ axes
            lo_, hi_ = loc.min(0), loc.max(0)
            lo_[thin] = min(lo_[thin], -3.0); hi_[thin] = max(hi_[thin], 3.0)  # at least 6 units thick
            move = axes[:, wide] * sign
            yaw = math.degrees(math.atan2(move[1], move[0]))
            width = float(hi_[wide] - lo_[wide])
            ent = ['"classname" "func_door"', '"origin" "%d %d %d"' % tuple(int(v) for v in origin), '"angle" "%d"' % int(round(yaw)) if abs(round(yaw)) > 0 else '"angle" "360"',
                   '"speed" "%d"' % spec["speed"], '"wait" "%d"' % spec["wait"], '"lip" "6"', '"model2" "%s"' % path, '"naboo_door" "1"']
            if team:
                ent.append('"team" "%s"' % team)
            doors.append({"origin": origin.tolist(), "axes": axes.T.tolist(), "lo": lo_.tolist(), "hi": hi_.tolist(), "entity": ent, "model": path,
                          "verts": int(sum(len(s_[1]) for s_ in surfaces)), "tris": int(sum(len(s_[4]) for s_ in surfaces)), "surfaces": len(surfaces),
                          "move_dir": move.tolist(), "travel_units": round(width - 6.0, 1), "mesh": spec["mesh"]})
open(os.path.join(game, "shaders", "naboo_doors.shader"), "w").write("// generated by tools/build_doors.py\n" + "\n".join(shader_text.values()))
json.dump({"skip_instances": skip, "clear_boxes": clear, "doors": doors}, open(os.path.join(ed, "doors.json"), "w"), indent=1)
for d in doors:
    print("door %-24s origin %s travel %.0f units, %d verts %d tris in %d surfaces, box %s .. %s" % (d["model"].split("/")[-1], [int(v) for v in d["origin"]], d["travel_units"], d["verts"], d["tris"], d["surfaces"],
                                                                                                  np.round(d["lo"]).astype(int).tolist(), np.round(d["hi"]).astype(int).tolist()))
print("left out of the static world:", skip)
