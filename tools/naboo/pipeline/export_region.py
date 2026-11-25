# Export one region of the Naboo scene from Blender (read-only on the .blend; nothing is saved back).
#   blender -b --factory-startup --disable-autoexec <blend> --python export_region.py -- <config.json> <region> <outdir> [dump] [collision] [textures] [gltf] [spawns]
# Outputs in <outdir>:
#   dump/meshes/<n>.npz, dump/scene.json, dump/materials.json      (direct dump, intermediate format candidate i)
#   dump/textures/*.png                                             (base-colour images used in the region)
#   region.glb                                                      (glTF, intermediate format candidate ii)
#   collision/collision_tris.npy, collision/collision_stats.json    (world-space collision triangles, engine units)
#   collision/spawn_candidates.json
#   export_report.json                                              (timings, counts, sizes)
import bpy, sys, json, os, time, re
import numpy as np
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(argv[0], encoding="utf-8"))
region_name, outdir = argv[1], argv[2]
steps = set(argv[3:]) or {"dump", "collision", "textures", "spawns"}
reg = cfg["regions"][region_name]
CX, CY = reg["centre_m"]; H = reg["half_m"]
UPM = cfg["units_per_metre"]; ORG = np.array(cfg["origin_m"], dtype=np.float64)
os.makedirs(outdir, exist_ok=True)
REPORT = {"region": region_name, "centre_m": [CX, CY], "half_m": H, "units_per_metre": UPM, "origin_m": cfg["origin_m"], "steps": sorted(steps)}
report_path = os.path.join(outdir, "export_report.json")
if os.path.exists(report_path):
    try:
        old = json.load(open(report_path, encoding="utf-8")); old.update(REPORT); REPORT = old
    except Exception:
        pass


def save_report():
    json.dump(REPORT, open(report_path, "w", encoding="utf-8"), indent=1)


def dir_size(p):
    t = 0
    for r, _, fs in os.walk(p):
        for f in fs:
            t += os.path.getsize(os.path.join(r, f))
    return t


def to_engine(p):  # (n,3) metres -> engine units
    return ((np.asarray(p, dtype=np.float64) - ORG) * UPM).astype(np.float32)


# ---------------------------------------------------------------- selection
t0 = time.time()
vl_objs = [o for o in bpy.context.view_layer.objects if o.type == 'MESH' and o.data and len(o.data.polygons) > 0 and o.visible_get()]
sel = []; terrain = None
for o in vl_objs:
    bb = np.array([list(o.matrix_world @ Vector(c)) for c in o.bound_box])
    ext = bb.max(0) - bb.min(0); c = (bb.max(0) + bb.min(0)) / 2
    if o.name == "Terrain_Near":
        terrain = o; continue
    if ext.max() >= 200.0:
        continue
    if reg.get("all") or (abs(c[0] - CX) <= H and abs(c[1] - CY) <= H):
        sel.append(o)
meshes = {}
for o in sel:
    meshes.setdefault(o.data.name, o.data)
REPORT["selection"] = {"objects": len(sel), "unique_meshes": len(meshes), "seconds": round(time.time() - t0, 2)}
print("[export] selected %d objects, %d meshes" % (len(sel), len(meshes)), flush=True)


# ---------------------------------------------------------------- materials
def _inputs(n):
    return {i.identifier: i for i in n.inputs}


def eval_color(sock, depth=0):
    """Follow the colour path feeding a socket. Returns (image name or None, [r, g, b] constant factor).
    Masks and scalar maths are not followed: only colour-carrying inputs. Unknown mix factors count as 0.3."""
    if not sock.is_linked:
        v = sock.default_value
        try:
            return None, [float(v[0]), float(v[1]), float(v[2])]
        except TypeError:
            return None, [float(v)] * 3
    if depth > 40:
        return None, [1.0, 1.0, 1.0]
    l = sock.links[0]; n = l.from_node; t = n.bl_idname
    if t == "ShaderNodeTexImage":
        if l.from_socket.identifier == "Color" and n.image:
            return n.image.name, [1.0, 1.0, 1.0]
        return None, [0.5, 0.5, 0.5]
    if t == "ShaderNodeRGB":
        return None, [float(x) for x in n.outputs[0].default_value[:3]]
    if t == "ShaderNodeMix" and n.data_type == "RGBA":
        ins = _inputs(n)
        A = eval_color(ins["A_Color"], depth + 1); B = eval_color(ins["B_Color"], depth + 1)
        fs = ins["Factor_Float"]; f = None if fs.is_linked else float(fs.default_value)
        if n.blend_type == "MIX":
            if f is not None and f >= 0.99:
                return B
            if f is not None and f <= 0.01:
                return A
            if A[0]:
                return A
            if B[0]:
                return B
            w = 0.3 if f is None else f
            return None, [A[1][i] * (1 - w) + B[1][i] * w for i in range(3)]
        if n.blend_type == "MULTIPLY":
            w = 1.0 if f is None else f
            if A[0] and B[0]:
                return A
            return (A[0] or B[0]), [A[1][i] * (1 - w + w * B[1][i]) for i in range(3)]
        return A if (A[0] or not B[0]) else B
    if t == "ShaderNodeVectorMath":
        ins = list(n.inputs)
        A = eval_color(ins[0], depth + 1)
        if n.operation == "MULTIPLY":
            B = eval_color(ins[1], depth + 1)
            if A[0] and B[0]:
                return A
            return (A[0] or B[0]), [A[1][i] * B[1][i] for i in range(3)]
        if n.operation == "SCALE":
            sc = _inputs(n).get("Scale")
            k = 1.0 if (sc is None or sc.is_linked) else float(sc.default_value)
            return A[0], [x * k for x in A[1]]
        if A[0]:
            return A
        for i in ins[1:]:
            if i.is_linked:
                B = eval_color(i, depth + 1)
                if B[0]:
                    return B
        return A
    if t in ("ShaderNodeMath", "ShaderNodeSeparateColor", "ShaderNodeSeparateXYZ", "ShaderNodeClamp", "ShaderNodeMapRange", "ShaderNodeRGBToBW", "ShaderNodeValue"):
        return None, [1.0, 1.0, 1.0]      # a scalar (mask, AO, ...) multiplied in: unknown, treated as neutral
    if t in ("ShaderNodeCombineColor", "ShaderNodeCombineXYZ"):
        return None, [(float(i.default_value) if not i.is_linked else 0.5) for i in list(n.inputs)[:3]]
    for nm in ("Color", "Image", "Input"):
        i = n.inputs.get(nm)
        if i is not None:
            return eval_color(i, depth + 1)
    for i in n.inputs:
        if i.is_linked:
            return eval_color(i, depth + 1)
    return None, [1.0, 1.0, 1.0]


def first_image_any(sock):
    seen = set(); stack = [sock]
    while stack:
        s = stack.pop()
        for l in s.links:
            fn = l.from_node
            if fn.name in seen:
                continue
            seen.add(fn.name)
            if fn.bl_idname == "ShaderNodeTexImage" and fn.image:
                return [fn.image.name, l.from_socket.identifier]
            stack.extend(fn.inputs)
    return None


def material_info(m):
    d = {"name": m.name, "blend_method": getattr(m, "blend_method", ""), "builder": m.get("builder", ""),
         "shader": m.get("shader", ""), "base_image": None, "tint": [1.0, 1.0, 1.0], "normal_image": None, "alpha_linked": False,
         "alpha_source": None, "transparent_node": False, "translucent_node": False, "images": []}
    nt = m.node_tree
    if not nt:
        d["cls"] = "opaque"; return d
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            d["images"].append(n.image.name)
        elif n.bl_idname == "ShaderNodeBsdfPrincipled":
            img, tint = eval_color(n.inputs["Base Color"])
            tint = [min(max(x, 0.0), 2.0) for x in tint]
            lum = 0.2126 * tint[0] + 0.7152 * tint[1] + 0.0722 * tint[2]
            d["tint_raw"] = [round(x, 4) for x in tint]
            if img and lum < 0.30:
                # products of several unknown-weight tint constants come out far too dark; keep the hue, lift the level
                k = 0.30 / max(lum, 1e-4); tint = [min(x * k, 2.0) for x in tint]
            d["base_image"] = img; d["tint"] = [round(x, 4) for x in tint]
            ni = first_image_any(n.inputs["Normal"]); d["normal_image"] = ni[0] if ni else None
            d["alpha_linked"] = n.inputs["Alpha"].is_linked
            d["alpha_source"] = first_image_any(n.inputs["Alpha"]) if d["alpha_linked"] else None
            d["alpha_default"] = float(n.inputs["Alpha"].default_value)
        elif n.bl_idname == "ShaderNodeBsdfTransparent":
            d["transparent_node"] = True
        elif n.bl_idname == "ShaderNodeBsdfTranslucent":
            d["translucent_node"] = True
        elif n.bl_idname == "ShaderNodeMixShader" and d.get("mix_alpha_source") is None:
            d["mix_alpha_source"] = first_image_any(n.inputs[0])
    if d["alpha_source"] is None and d["transparent_node"]:
        d["alpha_source"] = d.get("mix_alpha_source")
    b = d["builder"]
    invisible = "(invisible)" in b or b in ("fog_card", "placeholder") or b.startswith("fog_billboard")
    d["cls"] = "invisible" if invisible else ("blend" if d["blend_method"] == "BLEND" else ("cutout" if (d["alpha_linked"] or d["transparent_node"]) else "opaque"))
    return d


MAT = {}
for me in meshes.values():
    for m in me.materials:
        if m and m.name not in MAT:
            MAT[m.name] = material_info(m)
if "materials" in steps:
    import collections
    os.makedirs(os.path.join(outdir, "dump"), exist_ok=True)
    json.dump(MAT, open(os.path.join(outdir, "dump", "materials.json"), "w", encoding="utf-8"), indent=1)
    REPORT["materials"] = {"count": len(MAT), "classes": dict(collections.Counter(m["cls"] for m in MAT.values())),
                           "with_base_image": sum(1 for m in MAT.values() if m["base_image"]),
                           "distinct_base_images": len(set(m["base_image"] for m in MAT.values() if m["base_image"])),
                           "tinted": sum(1 for m in MAT.values() if max(abs(x - 1.0) for x in m["tint"]) > 0.02),
                           "cutout_alpha_from_other_image": sum(1 for m in MAT.values() if m["cls"] == "cutout" and m["alpha_source"] and m["alpha_source"][0] != m["base_image"]),
                           "cutout_alpha_from_colour_channel": sum(1 for m in MAT.values() if m["cls"] == "cutout" and m["alpha_source"] and m["alpha_source"][1] != "Alpha"),
                           "cutout_no_alpha_source": sum(1 for m in MAT.values() if m["cls"] == "cutout" and not m["alpha_source"])}
    save_report(); print("[export] materials", REPORT["materials"], flush=True)


# ---------------------------------------------------------------- mesh extraction
def mesh_arrays(me, full=True):
    me.calc_loop_triangles()
    nv = len(me.vertices); nl = len(me.loops); nt = len(me.loop_triangles)
    pos = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", pos); pos = pos.reshape(-1, 3)
    tri_loops = np.empty(nt * 3, np.int32); me.loop_triangles.foreach_get("loops", tri_loops); tri_loops = tri_loops.reshape(-1, 3)
    tri_verts = np.empty(nt * 3, np.int32); me.loop_triangles.foreach_get("vertices", tri_verts); tri_verts = tri_verts.reshape(-1, 3)
    tri_mat = np.empty(nt, np.int32); me.loop_triangles.foreach_get("material_index", tri_mat)
    out = {"pos": pos, "tri_loops": tri_loops, "tri_verts": tri_verts, "tri_mat": tri_mat.astype(np.int16)}
    if not full:
        return out
    loop_vert = np.empty(nl, np.int32); me.loops.foreach_get("vertex_index", loop_vert); out["loop_vert"] = loop_vert
    nrm = np.empty(nl * 3, np.float32); me.corner_normals.foreach_get("vector", nrm); out["loop_normal"] = nrm.reshape(-1, 3)
    for i, uvl in enumerate(me.uv_layers[:2]):
        uv = np.empty(nl * 2, np.float32); uvl.uv.foreach_get("vector", uv); out["uv%d" % i] = uv.reshape(-1, 2)
    ca = me.color_attributes.get("Color0")
    if ca is not None:
        n = nv if ca.domain == 'POINT' else nl
        col = np.empty(n * 4, np.float32); ca.data.foreach_get("color", col)
        out["color"] = (col.reshape(-1, 4).clip(0, 1) * 255 + 0.5).astype(np.uint8); out["color_domain"] = np.array([0 if ca.domain == 'POINT' else 1], np.int8)
    return out


def terrain_crop(o, stride=1, margin=0.0, bounds=None):
    me = o.data; nv = len(me.vertices)
    pos = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", pos); pos = pos.reshape(-1, 3)
    side = int(round(nv ** 0.5)); assert side * side == nv, "terrain is not a square grid"
    g = pos.reshape(side, side, 3)
    # find which axis order the grid uses
    xs_along_j = abs(g[0, -1, 0] - g[0, 0, 0]) > abs(g[-1, 0, 0] - g[0, 0, 0])
    if not xs_along_j:
        g = g.transpose(1, 0, 2)
    xs = g[0, :, 0]; ys = g[:, 0, 1]
    wm = np.array(o.matrix_world)
    assert np.allclose(wm, np.eye(4), atol=1e-6), "terrain has a transform"
    bx0, by0, bx1, by1 = bounds if bounds else (CX - H, CY - H, CX + H, CY + H)
    jx = np.where((xs >= bx0 - margin) & (xs <= bx1 + margin))[0]; iy = np.where((ys >= by0 - margin) & (ys <= by1 + margin))[0]
    sub = g[iy.min():iy.max() + 1:stride, jx.min():jx.max() + 1:stride]
    h, w = sub.shape[:2]
    idx = np.arange(h * w).reshape(h, w)
    a = idx[:-1, :-1].ravel(); b = idx[:-1, 1:].ravel(); c = idx[1:, :-1].ravel(); d = idx[1:, 1:].ravel()
    tris = np.concatenate([np.stack([a, b, d], 1), np.stack([a, d, c], 1)])
    P = sub.reshape(-1, 3)
    # make triangles face up
    n = np.cross(P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]])
    flip = n[:, 2] < 0
    tris[flip] = tris[flip][:, ::-1]
    return P.copy(), tris.astype(np.int32)


def terrain_grid(o):
    """whole height grid as (side, side, 3) metres indexed [y][x]"""
    me = o.data; nv = len(me.vertices)
    pos = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", pos); pos = pos.reshape(-1, 3)
    side = int(round(nv ** 0.5)); assert side * side == nv, "terrain is not a square grid"
    g = pos.reshape(side, side, 3)
    if not (abs(g[0, -1, 0] - g[0, 0, 0]) > abs(g[-1, 0, 0] - g[0, 0, 0])):
        g = g.transpose(1, 0, 2)
    assert np.allclose(np.array(o.matrix_world), np.eye(4), atol=1e-6), "terrain has a transform"
    if g[0, -1, 0] < g[0, 0, 0]:
        g = g[:, ::-1]
    if g[-1, 0, 1] < g[0, 0, 1]:
        g = g[::-1]
    return np.ascontiguousarray(g)


_scratch = None
LOD_RATIOS = cfg.get("lod", {}).get("ratios", [0.3, 0.08])
LOD_MIN_TRIS = cfg.get("lod", {}).get("min_tris", [200, 1200])


def make_lods(me, i, ntris, md):
    """decimated copies of a mesh (Blender's Decimate modifier on a temporary object; the .blend is never saved)"""
    global _scratch
    if _scratch is None:
        _scratch = bpy.data.collections.new("_naboo_lod_scratch"); bpy.context.scene.collection.children.link(_scratch)
    out = []; prev = ntris
    for li, ratio in enumerate(LOD_RATIOS):
        if ntris < LOD_MIN_TRIS[li]:
            break
        to = bpy.data.objects.new("_lod", me); _scratch.objects.link(to)
        mod = to.modifiers.new("d", 'DECIMATE'); mod.ratio = ratio
        dg = bpy.context.evaluated_depsgraph_get(); ev = to.evaluated_get(dg); em = ev.to_mesh()
        try:
            a = mesh_arrays(em)
        except Exception:
            a = None
        ev.to_mesh_clear(); bpy.data.objects.remove(to)
        if a is None:
            break
        n = len(a["tri_verts"])
        if n == 0 or n > prev * 0.8:
            break
        fn = "%04d_lod%d.npz" % (i, li + 1)
        np.savez(os.path.join(md, fn), **a); out.append(fn); prev = n
    return out


# ---------------------------------------------------------------- step: dump
if "dump" in steps:
    t0 = time.time()
    md = os.path.join(outdir, "dump", "meshes"); os.makedirs(md, exist_ok=True)
    index = {}; tot_t = tot_v = tot_l = 0; n_lod_files = 0
    for i, (name, me) in enumerate(sorted(meshes.items())):
        a = mesh_arrays(me)
        fn = "%04d.npz" % i
        np.savez(os.path.join(md, fn), **a)
        index[name] = {"file": fn, "verts": int(len(a["pos"])), "tris": int(len(a["tri_verts"])), "loops": int(len(a["loop_vert"])),
                       "materials": [m.name if m else None for m in me.materials], "uv_layers": len(me.uv_layers),
                       "has_color": "color" in a, "frostbite_mesh": me.get("frostbite_mesh", "")}
        tot_t += len(a["tri_verts"]); tot_v += len(a["pos"]); tot_l += len(a["loop_vert"])
        if "lods" in steps:
            index[name]["lods"] = make_lods(me, i, len(a["tri_verts"]), md)
            n_lod_files += len(index[name]["lods"])
    extra = {}
    if terrain and reg.get("terrain_grid"):
        g = terrain_grid(terrain)
        np.savez(os.path.join(md, "terrain_grid.npz"), grid=g)
        extra["terrain_grid"] = {"file": "terrain_grid.npz", "side": int(g.shape[0]), "tile_cells": 128, "strides": [2, 8, 32]}
        tp = np.zeros((0, 3), np.float32); tt = np.zeros((0, 3), np.int32)
    else:
        tp, tt = terrain_crop(terrain) if terrain else (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32))
    np.savez(os.path.join(md, "terrain_crop.npz"), pos=tp, tri_verts=tt)
    inst = []; inst_tris = 0
    for o in sel:
        inst.append({"name": o.name, "mesh": o.data.name, "matrix": [list(r) for r in o.matrix_world],
                     "collection": o.users_collection[0].name if o.users_collection else "", "blueprint": o.get("blueprint", "")})
        inst_tris += index[o.data.name]["tris"]
    json.dump({"units": "metres", "meshes": index, "instances": inst,
               "terrain_crop": {"file": "terrain_crop.npz", "verts": int(len(tp)), "tris": int(len(tt))}, **extra},
              open(os.path.join(outdir, "dump", "scene.json"), "w", encoding="utf-8"))
    json.dump(MAT, open(os.path.join(outdir, "dump", "materials.json"), "w", encoding="utf-8"), indent=1)
    REPORT["dump"] = {"seconds": round(time.time() - t0, 2), "unique_tris": tot_t, "unique_verts": tot_v, "unique_loops": tot_l,
                      "instanced_tris": inst_tris, "terrain_tris": int(len(tt)), "materials": len(MAT), "lod_files": n_lod_files,
                      "material_classes": {k: sum(1 for m in MAT.values() if m["cls"] == k) for k in ("opaque", "cutout", "blend", "invisible")},
                      "materials_with_base_image": sum(1 for m in MAT.values() if m["base_image"]),
                      "distinct_base_images": len(set(m["base_image"] for m in MAT.values() if m["base_image"])),
                      "distinct_images_all": len(set(i for m in MAT.values() for i in m["images"])),
                      "bytes": dir_size(os.path.join(outdir, "dump", "meshes"))}
    save_report(); print("[export] dump", REPORT["dump"], flush=True)

# ---------------------------------------------------------------- step: textures (base colour only)
if "textures" in steps:
    t0 = time.time()
    td = os.path.join(outdir, "dump", "textures"); os.makedirs(td, exist_ok=True)
    names = sorted(set(m["base_image"] for m in MAT.values() if m["base_image"]))
    if reg.get("terrain_grid") and bpy.data.images.get("near_colour.png"):
        names.append("near_colour.png")
    ok = 0; fail = []; px = 0
    for n in names:
        im = bpy.data.images.get(n)
        try:
            dst = os.path.join(td, os.path.splitext(n)[0] + ".png")
            im.save(filepath=dst)   # writes a copy; the .blend itself is never saved
            ok += 1; px += im.size[0] * im.size[1]
        except Exception as e:
            fail.append([n, str(e)[:120]])
    REPORT["textures"] = {"seconds": round(time.time() - t0, 2), "requested": len(names), "written": ok, "failed": fail,
                          "pixels": px, "bytes": dir_size(td)}
    save_report(); print("[export] textures", REPORT["textures"], flush=True)

# ---------------------------------------------------------------- step: collision
if "collision" in steps:
    t0 = time.time()
    cc = dict(cfg["collision"]); cc.update(reg.get("collision", {}))
    CB = reg.get("collision_bounds_m")          # [x0, y0, x1, y1] in metres, or None
    cd = os.path.join(outdir, "collision"); os.makedirs(cd, exist_ok=True)
    excl = [s.lower() for s in cc["exclude_name_substrings"]]
    stats = {"objects_in": len(sel), "skipped_outside": 0, "skipped_name": 0, "skipped_small": 0, "skipped_no_solid_tris": 0, "boxed": 0, "decimated": 0, "kept_full": 0,
             "source_tris_instanced": 0, "solid_source_tris_instanced": 0}
    cache = {}
    scratch = bpy.data.collections.new("_naboo_scratch"); bpy.context.scene.collection.children.link(scratch)

    def solid_local(me):
        """collision triangles of one mesh in local space: (positions, tris, kind)"""
        if me.name in cache:
            return cache[me.name]
        a = mesh_arrays(me, full=False)
        names = [m.name if m else None for m in me.materials] or [None]
        solid_slot = np.array([(MAT.get(n, {}).get("cls", "opaque") == "opaque") for n in names] + [True] * 64)
        keep = solid_slot[a["tri_mat"].clip(0, len(solid_slot) - 1)]
        tv = a["tri_verts"][keep]
        if len(tv) == 0:
            cache[me.name] = (None, None, "none", len(a["tri_verts"]), 0); return cache[me.name]
        used = np.unique(tv); remap = np.full(len(a["pos"]), -1, np.int64); remap[used] = np.arange(len(used))
        P = a["pos"][used]; T = remap[tv].astype(np.int32)
        ext = P.max(0) - P.min(0)
        n_solid = len(T)
        if ext.max() < cc["box_below_extent_m"]:
            mn, mx = P.min(0), P.max(0)
            c = np.array([[mn[0], mn[1], mn[2]], [mx[0], mn[1], mn[2]], [mx[0], mx[1], mn[2]], [mn[0], mx[1], mn[2]],
                          [mn[0], mn[1], mx[2]], [mx[0], mn[1], mx[2]], [mx[0], mx[1], mx[2]], [mn[0], mx[1], mx[2]]], np.float32)
            f = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]], np.int32)
            cache[me.name] = (c, f, "box", len(a["tri_verts"]), n_solid); return cache[me.name]
        target = min(max(n_solid * cc["decimate_fraction"], cc["decimate_min_tris"]), cc["decimate_max_tris"])
        if n_solid <= target:
            cache[me.name] = (P, T, "full", len(a["tri_verts"]), n_solid); return cache[me.name]
        tm = bpy.data.meshes.new("_tmp"); tm.from_pydata(P.tolist(), [], T.tolist()); tm.update()
        to = bpy.data.objects.new("_tmp", tm); scratch.objects.link(to)
        mod = to.modifiers.new("d", 'DECIMATE'); mod.ratio = float(target) / n_solid
        dg = bpy.context.evaluated_depsgraph_get(); ev = to.evaluated_get(dg); em = ev.to_mesh()
        b = mesh_arrays(em, full=False); P2 = b["pos"].copy(); T2 = b["tri_verts"].copy()
        ev.to_mesh_clear(); bpy.data.objects.remove(to); bpy.data.meshes.remove(tm)
        cache[me.name] = (P2, T2, "decimated", len(a["tri_verts"]), n_solid); return cache[me.name]

    chunks = []; per_kind_tris = {"box": 0, "decimated": 0, "full": 0}
    for o in sel:
        nm = o.name.lower(); mn_ = o.data.name.lower()
        if any(s in nm or s in mn_ for s in excl):
            stats["skipped_name"] += 1; continue
        bb = np.array([list(o.matrix_world @ Vector(c)) for c in o.bound_box]); ext = (bb.max(0) - bb.min(0)).max()
        if CB:
            cxy = (bb.max(0) + bb.min(0)) / 2
            if not (CB[0] <= cxy[0] <= CB[2] and CB[1] <= cxy[1] <= CB[3]):
                stats["skipped_outside"] += 1; continue
        if ext < cc["skip_below_extent_m"]:
            stats["skipped_small"] += 1; continue
        P, T, kind, n_src, n_solid = solid_local(o.data)
        stats["source_tris_instanced"] += n_src; stats["solid_source_tris_instanced"] += n_solid
        if P is None:
            stats["skipped_no_solid_tris"] += 1; continue
        M = np.array(o.matrix_world, dtype=np.float64)
        W = P.astype(np.float64) @ M[:3, :3].T + M[:3, 3]
        tri = W[T]
        if np.linalg.det(M[:3, :3]) < 0:
            tri = tri[:, ::-1]
        chunks.append(tri)
        stats[{"box": "boxed", "decimated": "decimated", "full": "kept_full"}[kind]] += 1
        per_kind_tris[kind] += len(T)
    n_obj_tris = sum(len(c) for c in chunks)
    if terrain:
        tp, tt = terrain_crop(terrain, stride=cc["terrain_stride"], margin=2.0, bounds=CB)
        chunks.append(tp.astype(np.float64)[tt]); stats["terrain_tris"] = int(len(tt))
    allt = np.concatenate(chunks) if chunks else np.zeros((0, 3, 3))
    # drop degenerate triangles
    n = np.cross(allt[:, 1] - allt[:, 0], allt[:, 2] - allt[:, 0]); area = np.linalg.norm(n, axis=1) * 0.5
    good = area > 1e-6
    stats["degenerate_dropped"] = int((~good).sum())
    allt = allt[good]
    eng = to_engine(allt.reshape(-1, 3)).reshape(-1, 3, 3)
    np.save(os.path.join(cd, "collision_tris.npy"), eng)
    stats.update({"object_tris": n_obj_tris, "tris_by_kind": per_kind_tris, "total_tris": int(len(eng)), "unique_meshes_processed": len(cache),
                  "bounds_units": [eng.reshape(-1, 3).min(0).tolist(), eng.reshape(-1, 3).max(0).tolist()], "seconds": round(time.time() - t0, 2)})
    json.dump(stats, open(os.path.join(cd, "collision_stats.json"), "w"), indent=1)
    REPORT["collision"] = stats; save_report(); print("[export] collision", stats, flush=True)

# ---------------------------------------------------------------- step: spawn candidates (ray casts against the visual scene)
if "spawns" in steps:
    t0 = time.time()
    dg = bpy.context.evaluated_depsgraph_get(); sc = bpy.context.scene
    cands = []; step = float(reg.get("spawn_grid_m", 6.0))
    SB = reg.get("collision_bounds_m") or [CX - H, CY - H, CX + H, CY + H]
    xs = np.arange(SB[0] + 8, SB[2] - 8 + 0.1, step); ys = np.arange(SB[1] + 8, SB[3] - 8 + 0.1, step)
    tg = terrain_grid(terrain) if terrain else None
    max_above = float(reg.get("spawn_max_above_terrain_m", 1e9))
    for x in xs:
        for y in ys:
            hit, loc, nrm, _, ob, _ = sc.ray_cast(dg, Vector((x, y, 700.0)), Vector((0, 0, -1)), distance=400.0)
            if not hit or nrm.z < 0.94:
                continue
            if tg is not None:
                ix = int(round((x - tg[0, 0, 0]) / (tg[0, 1, 0] - tg[0, 0, 0]))); iy = int(round((y - tg[0, 0, 1]) / (tg[1, 0, 1] - tg[0, 0, 1])))
                if 0 <= ix < tg.shape[1] and 0 <= iy < tg.shape[0] and loc.z - float(tg[iy, ix, 2]) > max_above:
                    continue
            base = loc + Vector((0, 0, 0.15))
            up, uloc, *_ = sc.ray_cast(dg, base, Vector((0, 0, 1)), distance=3.0)
            if up:
                continue
            clear = True
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)):
                for hgt in (0.4, 1.0, 1.7):
                    h2, *_ = sc.ray_cast(dg, loc + Vector((0, 0, hgt)), Vector((dx, dy, 0)).normalized(), distance=1.5)
                    if h2:
                        clear = False; break
                if not clear:
                    break
            if clear:
                cands.append({"pos_m": [x, y, loc.z], "object": ob.name if ob else ""})
    json.dump({"candidates": cands, "grid_step_m": step}, open(os.path.join(outdir, "collision", "spawn_candidates.json"), "w"), indent=1) if os.path.isdir(os.path.join(outdir, "collision")) else None
    REPORT["spawns"] = {"seconds": round(time.time() - t0, 2), "grid_points": int(len(xs) * len(ys)), "candidates": len(cands),
                        "z_range_m": [min(c["pos_m"][2] for c in cands), max(c["pos_m"][2] for c in cands)] if cands else None}
    save_report(); print("[export] spawns", REPORT["spawns"], flush=True)

# ---------------------------------------------------------------- step: glTF
if "gltf" in steps:
    t0 = time.time()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in sel:
        o.select_set(True)
    glb = os.path.join(outdir, "region.glb")
    try:
        bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True, export_apply=False,
                                  export_yup=True, export_tangents=False, export_animations=False)
        REPORT["gltf"] = {"seconds": round(time.time() - t0, 2), "bytes": os.path.getsize(glb)}
    except Exception as e:
        REPORT["gltf"] = {"seconds": round(time.time() - t0, 2), "error": str(e)[:500]}
    save_report(); print("[export] gltf", REPORT["gltf"], flush=True)

save_report()
print("[export] done", flush=True)
