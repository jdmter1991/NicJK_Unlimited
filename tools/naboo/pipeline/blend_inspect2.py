# Second read-only pass: README text, custom props, material dedupe, playable-area bounds,
# per-collection triangles, geometry-nodes instances, packed image sizes, special object lists.
#   blender -b --factory-startup --disable-autoexec <file.blend> --python blend_inspect2.py -- <out.json>
import bpy, sys, json, os, time, re, hashlib, traceback
from collections import Counter, defaultdict
import numpy as np
from mathutils import Vector

t0 = time.time()
out_path = sys.argv[sys.argv.index("--") + 1]
ONLY = set(sys.argv[sys.argv.index("--") + 2:])
R = {"errors": []}


def section(name):
    def deco(fn):
        if ONLY and name not in ONLY:
            return fn
        try:
            R[name] = fn()
        except Exception:
            R["errors"].append({"section": name, "trace": traceback.format_exc()})
        print("[inspect2] %s done at %.1fs" % (name, time.time() - t0), flush=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(R, f, indent=1, default=str)
        return fn
    return deco


def tris_of(m):
    n = len(m.polygons)
    if not n:
        return 0
    lt = np.empty(n, dtype=np.int32); m.polygons.foreach_get("loop_total", lt)
    return int((lt - 2).sum())


TRIS = {m.name: tris_of(m) for m in bpy.data.meshes}
LOOPS = {m.name: len(m.loops) for m in bpy.data.meshes}


@section("readme_text")
def _():
    return {t.name: t.as_string()[:20000] for t in bpy.data.texts}


@section("custom_props")
def _():
    res = {}
    for label, coll in (("objects", bpy.data.objects), ("meshes", bpy.data.meshes), ("materials", bpy.data.materials),
                        ("collections", bpy.data.collections), ("scenes", bpy.data.scenes), ("lights", bpy.data.lights)):
        c = Counter(); ex = {}
        for d in coll:
            for k in d.keys():
                c[k] += 1
                if k not in ex:
                    try:
                        v = d[k]; ex[k] = str(v.to_dict() if hasattr(v, "to_dict") else (list(v) if hasattr(v, "__len__") and not isinstance(v, str) else v))[:200]
                    except Exception:
                        ex[k] = "?"
        res[label] = {"keys": dict(c.most_common(60)), "examples": ex}
    return res


@section("collection_tris")
def _():
    res = {}
    for c in bpy.data.collections:
        mo = [o for o in c.objects if o.type == 'MESH' and o.data]
        if not c.objects:
            continue
        res[c.name] = {"objects": len(c.objects), "mesh_objects": len(mo),
                       "tris": sum(TRIS[o.data.name] for o in mo),
                       "unique_meshes": len(set(o.data.name for o in mo)),
                       "unique_tris": sum(TRIS[n] for n in set(o.data.name for o in mo)),
                       "names_sample": [o.name for o in list(c.objects)[:12]] if len(c.objects) <= 40 else [o.name for o in list(c.objects)[:6]]}
    return res


@section("special_objects")
def _():
    res = {}
    for cn in ("GameModes", "FantasyBattle", "FB_PalaceDestruction", "Terrain", "Water", "TerrainScatter_Sources", "FX_Sources",
               "Sun_Cloudy", "Backdrop_Landingstrip", "FB_Art_Backdrop", "FB_Art_NearBackdrop_01", "Lights_Shared_Lighting"):
        c = bpy.data.collections.get(cn)
        if not c:
            continue
        res[cn] = [{"name": o.name, "type": o.type, "data": o.data.name if o.data else None,
                    "tris": TRIS.get(o.data.name, 0) if o.type == 'MESH' and o.data else 0,
                    "loc": [round(x, 2) for x in o.matrix_world.translation],
                    "dims": [round(x, 2) for x in o.dimensions],
                    "mods": [m.type + ":" + (m.node_group.name if m.type == 'NODES' and m.node_group else "") for m in o.modifiers]}
                   for o in c.objects][:60]
    pat = Counter()
    for o in bpy.data.objects:
        n = o.name.lower()
        for k in ("nocollision", "fxcol", "collision", "_col", "csg", "blocker", "invalidate", "heightfog", "decal", "leak", "volume", "proxy", "occlu", "shadow", "lod", "impostor", "billboard", "backdrop", "sky", "vista"):
            if k in n:
                pat[k] += 1
    res["name_pattern_counts_objects"] = dict(pat)
    zero = [m.name for m in bpy.data.meshes if TRIS[m.name] == 0]
    res["zero_tri_meshes"] = {"count": len(zero), "with_verts": sum(1 for n in zero if len(bpy.data.meshes[n].vertices) > 0),
                              "objects_using": sum(1 for o in bpy.data.objects if o.type == 'MESH' and o.data and TRIS[o.data.name] == 0),
                              "sample": zero[:30]}
    mods = []
    for o in bpy.data.objects:
        for m in o.modifiers:
            mods.append((o.name, m.type, m.node_group.name if m.type == 'NODES' and m.node_group else "", m.show_viewport, m.show_render))
    res["modifier_groups"] = dict(Counter(g for _, _, g, _, _ in mods))
    res["modifier_objects_sample"] = mods[:12]
    return res


@section("playable_area")
def _():
    # distribution of object centres/extents, excluding huge backdrop/sky/terrain objects
    cs = []; ws = []
    for o in bpy.data.objects:
        if o.type != 'MESH' or not o.data or TRIS[o.data.name] == 0:
            continue
        bb = np.array([list(o.matrix_world @ Vector(c)) for c in o.bound_box])
        ext = bb.max(0) - bb.min(0)
        if ext.max() >= 200.0:
            continue
        cs.append(np.concatenate([bb.min(0), bb.max(0)])); ws.append(TRIS[o.data.name])
    cs = np.array(cs); ws = np.array(ws)
    mn = cs[:, :3]; mx = cs[:, 3:]; ctr = (mn + mx) / 2
    pct = lambda a, p: [float(np.percentile(a[:, i], p)) for i in range(3)]
    res = {"objects_lt200m": int(len(cs)), "tris": int(ws.sum()),
           "bbox_min": mn.min(0).tolist(), "bbox_max": mx.max(0).tolist(), "bbox_size": (mx.max(0) - mn.min(0)).tolist(),
           "centre_p0_5": pct(ctr, 0.5), "centre_p1": pct(ctr, 1), "centre_p5": pct(ctr, 5), "centre_p50": pct(ctr, 50),
           "centre_p95": pct(ctr, 95), "centre_p99": pct(ctr, 99), "centre_p99_5": pct(ctr, 99.5)}
    # coarse occupancy 32 m cells: count of cells holding 99% of tris and their bbox
    cell = 32.0
    g = Counter()
    for c, w in zip(ctr, ws):
        g[(int(c[0] // cell), int(c[1] // cell))] += int(w)
    items = sorted(g.items(), key=lambda kv: -kv[1]); tot = sum(v for _, v in items); acc = 0; keep = []
    for k, v in items:
        keep.append(k); acc += v
        if acc >= 0.99 * tot:
            break
    ka = np.array(keep)
    res["cells32m_total"] = len(items); res["cells32m_for_99pct_tris"] = len(keep)
    res["cells99_bbox_m"] = {"min": (ka.min(0) * cell).tolist(), "max": ((ka.max(0) + 1) * cell).tolist()}
    # z distribution (ground level)
    res["z_min_p"] = {str(p): float(np.percentile(mn[:, 2], p)) for p in (0.5, 5, 25, 50, 75, 95, 99.5)}
    # ascii map 64 m cells
    cell = 64.0; g2 = Counter()
    for c, w in zip(ctr, ws):
        g2[(int(c[0] // cell), int(c[1] // cell))] += int(w)
    xs = [k[0] for k in g2]; ys = [k[1] for k in g2]
    rows = []
    for y in range(max(ys), min(ys) - 1, -1):
        row = ""
        for x in range(min(xs), max(xs) + 1):
            v = g2.get((x, y), 0)
            row += " " if v == 0 else ("." if v < 20000 else ("o" if v < 200000 else ("O" if v < 800000 else "#")))
        rows.append(row)
    res["ascii_map_64m"] = {"x0_m": min(xs) * cell, "y_top_m": (max(ys) + 1) * cell, "rows": rows}
    return res


@section("material_dedupe")
def _():
    def val(x):
        if isinstance(x, str):
            return x
        try:
            return tuple(round(float(v), 4) for v in x)
        except (TypeError, ValueError):
            try:
                return round(float(x), 4)
            except Exception:
                return str(x)
    sig_full = Counter(); sig_img = Counter(); sig_base = Counter(); cls = Counter(); cls_tris = Counter()
    mat_cls = {}
    for m in bpy.data.materials:
        nt = m.node_tree
        parts = []; imgs = []; base = None; alpha_linked = False; emis = False; transl = False; transp = False
        if nt:
            for n in nt.nodes:
                p = [n.bl_idname]
                if n.bl_idname == "ShaderNodeTexImage":
                    p.append(n.image.name if n.image else "-"); imgs.append(n.image.name if n.image else "-")
                for i in n.inputs:
                    if not i.is_linked and hasattr(i, "default_value"):
                        p.append(val(i.default_value))
                for o in n.outputs:
                    if n.bl_idname in ("ShaderNodeRGB", "ShaderNodeValue") and hasattr(o, "default_value"):
                        p.append(val(o.default_value))
                for a in ("operation", "blend_type", "data_type", "uv_map", "attribute_name", "mode"):
                    if hasattr(n, a):
                        p.append(str(getattr(n, a)))
                parts.append(tuple(map(str, p)))
                if n.bl_idname == "ShaderNodeBsdfPrincipled":
                    bc = n.inputs.get("Base Color")
                    alpha_linked = n.inputs["Alpha"].is_linked
                    es = n.inputs.get("Emission Strength")
                    if es is not None and (es.is_linked or es.default_value > 0):
                        emis = True
                    # walk back to first image feeding base colour
                    seen = set(); stack = [bc] if bc else []
                    while stack and base is None:
                        s = stack.pop()
                        for l in s.links:
                            fn = l.from_node
                            if fn.name in seen:
                                continue
                            seen.add(fn.name)
                            if fn.bl_idname == "ShaderNodeTexImage" and fn.image:
                                base = fn.image.name; break
                            stack.extend(fn.inputs)
                if n.bl_idname == "ShaderNodeBsdfTranslucent":
                    transl = True
                if n.bl_idname == "ShaderNodeBsdfTransparent":
                    transp = True
                if n.bl_idname == "ShaderNodeEmission":
                    emis = True
        links = sorted((l.from_node.bl_idname, l.from_socket.identifier, l.to_node.bl_idname, l.to_socket.identifier) for l in nt.links) if nt else []
        full = hashlib.md5(repr((sorted(parts), links, m.blend_method)).encode()).hexdigest()
        sig_full[full] += 1
        sig_img[(tuple(sorted(imgs)), m.blend_method)] += 1
        sig_base[base] += 1
        preset = m.name.split("|")[1] if "|" in m.name else "(none)"
        preset = re.sub(r"\.\d{3}$", "", preset)
        if getattr(m, "blend_method", "") == "BLEND":
            c = "blend"
        elif alpha_linked or transp:
            c = "cutout_or_alpha"
        else:
            c = "opaque"
        if transl:
            c += "+translucent"
        if emis:
            c += "+emissive"
        cls[c] += 1; mat_cls[m.name] = (c, preset)
    # triangles per class / preset over instances
    per_mesh = {}
    for me in bpy.data.meshes:
        n = len(me.polygons)
        if not n:
            continue
        mi = np.empty(n, dtype=np.int32); lt = np.empty(n, dtype=np.int32)
        me.polygons.foreach_get("material_index", mi); me.polygons.foreach_get("loop_total", lt)
        names = [mm.name if mm else None for mm in me.materials] or [None]
        acc = Counter()
        for idx in np.unique(mi):
            nm = names[idx] if idx < len(names) else None
            acc[nm] += int((lt[mi == idx] - 2).sum())
        per_mesh[me.name] = acc
    preset_tris = Counter(); preset_n = Counter()
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.data and o.data.name in per_mesh:
            for k, v in per_mesh[o.data.name].items():
                c, p = mat_cls.get(k, ("no_material", "(none)"))
                cls_tris[c] += v; preset_tris[p] += v
    for m in bpy.data.materials:
        preset_n[mat_cls[m.name][1]] += 1
    return {"materials": len(bpy.data.materials), "unique_by_full_node_signature": len(sig_full),
            "unique_by_image_set_and_blend": len(sig_img), "unique_base_colour_images": len(sig_base),
            "materials_without_base_image": sig_base.get(None, 0),
            "class_material_counts": dict(cls), "class_instanced_tris": dict(cls_tris),
            "preset_material_counts": dict(preset_n.most_common(60)), "preset_instanced_tris": dict(preset_tris.most_common(60))}


@section("images2")
def _():
    tot = 0; by_ext = Counter(); big = []; alpha = Counter()
    for im in bpy.data.images:
        sz = 0  # packed_file.size access crashed Blender 5.2 on this file; not read
        tot += sz
        by_ext[os.path.splitext(im.filepath or im.name)[1].lower()] += 1
        big.append((sz, im.name, list(im.size), im.channels, im.depth))
        alpha["ch%d_depth%d" % (im.channels, im.depth)] += 1
    big.sort(reverse=True)
    return {"packed_bytes_total": tot, "by_extension": dict(by_ext), "channels_depth": dict(alpha),
            "largest_packed": [{"bytes": a, "name": b, "size": c, "ch": d, "depth": e} for a, b, c, d, e in big[:25]],
            "non_pow2": [(im.name, list(im.size)) for im in bpy.data.images if any(s & (s - 1) for s in im.size if s)][:30]}


@section("loops_gpu_verts")
def _():
    # GPU vertex estimate = unique (vertex, normal, uv0) corners; sample-free: report loops (upper bound) and verts (lower bound)
    u_loops = sum(LOOPS.values()); inst_loops = 0
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.data:
            inst_loops += LOOPS[o.data.name]
    return {"unique_mesh_loops_upper_bound_gpu_verts": u_loops, "instanced_loops": inst_loops}


@section("sun_world")
def _():
    res = {"suns": []}
    for o in bpy.data.objects:
        if o.type == 'LIGHT' and o.data.type == 'SUN':
            d = o.matrix_world.to_quaternion() @ Vector((0, 0, -1))
            res["suns"].append({"name": o.name, "energy": o.data.energy, "color": list(o.data.color), "direction_light_travels": [round(x, 4) for x in d], "angle": o.data.angle})
    for w in bpy.data.worlds:
        if w.node_tree:
            res[w.name] = [{"node": n.bl_idname, "image": getattr(getattr(n, "image", None), "name", None),
                            "defaults": {i.name: (list(i.default_value) if hasattr(i.default_value, "__len__") else i.default_value)
                                         for i in n.inputs if hasattr(i, "default_value") and not i.is_linked}} for n in w.node_tree.nodes]
    s = bpy.context.scene
    res["view"] = {"view_transform": s.view_settings.view_transform, "look": s.view_settings.look, "exposure": s.view_settings.exposure, "gamma": s.view_settings.gamma}
    return res


@section("geometry_nodes_instances")
def _():
    # evaluate depsgraph and count generated instances (scatter etc.)
    dg = bpy.context.evaluated_depsgraph_get()
    n_real = n_inst = 0; inst_by_parent = Counter(); inst_by_data = Counter(); inst_tris = 0; unknown = 0
    cache = {}
    for oi in dg.object_instances:
        ob = oi.object
        if ob.type != 'MESH':
            continue
        if oi.is_instance:
            n_inst += 1
            parent = oi.parent.original.name if oi.parent else "?"
            inst_by_parent[parent] += 1
            dn = ob.data.name if ob.data else "?"
            if dn not in cache:
                cache[dn] = TRIS.get(dn) if dn in TRIS else (tris_of(ob.data) if ob.data else 0)
            inst_by_data[dn] += 1
            inst_tris += cache[dn] or 0
        else:
            n_real += 1
    # evaluated tri counts of objects with modifiers (realised geometry)
    realised = []
    for o in bpy.data.objects:
        if o.modifiers and o.type == 'MESH':
            eo = o.evaluated_get(dg)
            try:
                me = eo.data
                realised.append((o.name, TRIS.get(o.data.name, 0), tris_of(me), len(me.vertices)))
            except Exception:
                realised.append((o.name, -1, -1, -1))
    realised.sort(key=lambda x: -x[2])
    return {"real_mesh_objects_in_depsgraph": n_real, "generated_instances": n_inst, "generated_instance_tris": inst_tris,
            "instances_by_parent_top": dict(inst_by_parent.most_common(30)), "instances_by_mesh_top": dict(inst_by_data.most_common(40)),
            "objects_with_modifiers_base_vs_evaluated_tris_top": realised[:30],
            "sum_evaluated_tris_objects_with_modifiers": sum(max(r[2], 0) for r in realised),
            "sum_base_tris_objects_with_modifiers": sum(max(r[1], 0) for r in realised)}


R["elapsed_s"] = time.time() - t0
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(R, f, indent=1, default=str)
print("[inspect2] wrote", out_path, "errors:", len(R["errors"]), flush=True)
