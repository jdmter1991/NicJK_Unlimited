# Read-only inspection of a .blend. Run:
#   blender -b --factory-startup --disable-autoexec <file.blend> --python blend_inspect.py -- <out.json>
# Never saves the .blend.
import bpy, sys, json, os, time, re, hashlib, traceback
from collections import Counter, defaultdict
import numpy as np
from mathutils import Vector

t0 = time.time()
out_path = sys.argv[sys.argv.index("--") + 1]
R = {"errors": []}


def section(name):
    def deco(fn):
        try:
            R[name] = fn()
        except Exception:
            R["errors"].append({"section": name, "trace": traceback.format_exc()})
        print("[inspect] %s done at %.1fs" % (name, time.time() - t0), flush=True)
        return fn
    return deco


@section("file")
def _():
    return {
        "blender_running": list(bpy.app.version),
        "file_saved_version": list(bpy.data.version),
        "filepath": bpy.data.filepath,
        "size_bytes": os.path.getsize(bpy.data.filepath),
        "is_dirty": bpy.data.is_dirty,
        "scenes": [s.name for s in bpy.data.scenes],
        "datablock_counts": {k: len(getattr(bpy.data, k)) for k in (
            "objects", "meshes", "materials", "images", "textures", "collections", "lights",
            "cameras", "curves", "armatures", "node_groups", "worlds", "actions", "volumes",
            "pointclouds", "grease_pencils", "lightprobes", "libraries", "texts", "fonts")
            if hasattr(bpy.data, k)},
    }


@section("scene")
def _():
    res = []
    for s in bpy.data.scenes:
        u = s.unit_settings
        res.append({
            "name": s.name, "unit_system": u.system, "scale_length": u.scale_length,
            "length_unit": u.length_unit, "render_engine": s.render.engine,
            "objects": len(s.objects), "view_layers": [v.name for v in s.view_layers],
            "world": s.world.name if s.world else None,
            "frame": [s.frame_start, s.frame_end],
        })
    return res


@section("collections")
def _():
    def walk(c, depth, excl):
        node = {"name": c.name, "depth": depth, "objects": len(c.objects),
                "objects_recursive": len(c.all_objects), "hide_viewport": c.hide_viewport,
                "hide_render": c.hide_render, "excluded": excl.get(c.name, False),
                "children": [walk(ch, depth + 1, excl) for ch in c.children]}
        return node
    res = {}
    for s in bpy.data.scenes:
        excl = {}
        def lc(l):
            excl[l.collection.name] = l.exclude
            for ch in l.children:
                lc(ch)
        for vl in s.view_layers:
            lc(vl.layer_collection)
        res[s.name] = walk(s.collection, 0, excl)
    in_scene = set()
    for s in bpy.data.scenes:
        in_scene.add(s.collection.name)
        for c in s.collection.children_recursive:
            in_scene.add(c.name)
    res["_collections_not_in_any_scene"] = [c.name for c in bpy.data.collections if c.name not in in_scene]
    return res


mesh_stats = {}


@section("meshes")
def _():
    tot_v = tot_t = tot_p = 0
    uvc = Counter(); attr_c = Counter(); custom_n = 0; nomat = 0; zero_user = 0
    dup = defaultdict(list)
    for m in bpy.data.meshes:
        nv = len(m.vertices); npoly = len(m.polygons)
        lt = np.empty(npoly, dtype=np.int32)
        if npoly:
            m.polygons.foreach_get("loop_total", lt)
        ntri = int((lt - 2).clip(min=0).sum()) if npoly else 0
        ngon = int((lt > 4).sum()) if npoly else 0
        quad = int((lt == 4).sum()) if npoly else 0
        co = np.empty(nv * 3, dtype=np.float32)
        if nv:
            m.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            mn = co.min(0); mx = co.max(0)
            h = hashlib.md5(co.tobytes()).hexdigest()[:16]
        else:
            mn = mx = np.zeros(3); h = "empty"
        area = 0.0
        if npoly:
            a = np.empty(npoly, dtype=np.float32); m.polygons.foreach_get("area", a); area = float(a.sum())
        st = {"verts": nv, "polys": npoly, "tris": ntri, "quads": quad, "ngons": ngon, "loops": len(m.loops),
              "users": m.users, "uv_layers": [u.name for u in m.uv_layers],
              "color_attrs": [a.name for a in m.color_attributes],
              "materials": [mm.name if mm else None for mm in m.materials],
              "custom_normals": bool(getattr(m, "has_custom_normals", False)),
              "bbox_min": [float(x) for x in mn], "bbox_max": [float(x) for x in mx],
              "area": area, "hash": h, "shape_keys": bool(m.shape_keys)}
        mesh_stats[m.name] = st
        tot_v += nv; tot_t += ntri; tot_p += npoly
        uvc[len(m.uv_layers)] += 1
        for a in m.attributes:
            attr_c["%s:%s:%s" % (a.name, a.domain, a.data_type)] += 1
        custom_n += st["custom_normals"]
        nomat += (len([x for x in m.materials if x]) == 0)
        zero_user += (m.users == 0)
        dup[(nv, npoly, h)].append(m.name)
    dups = [v for v in dup.values() if len(v) > 1 and v and mesh_stats[v[0]]["verts"] > 0]
    dup_extra_tris = sum(mesh_stats[v[0]]["tris"] * (len(v) - 1) for v in dups)
    top = sorted(mesh_stats.items(), key=lambda kv: -kv[1]["tris"])[:60]
    return {"count": len(bpy.data.meshes), "unique_verts": tot_v, "unique_tris": tot_t, "unique_polys": tot_p,
            "uv_layer_count_hist": dict(uvc), "attribute_hist": dict(attr_c.most_common(60)),
            "with_custom_normals": custom_n, "without_material": nomat, "zero_users": zero_user,
            "identical_geometry_groups": len(dups),
            "identical_geometry_meshes": sum(len(v) for v in dups),
            "identical_geometry_redundant_tris": dup_extra_tris,
            "identical_geometry_examples": sorted(dups, key=lambda v: -len(v))[:25],
            "tri_count_hist": {lab: sum(1 for s in mesh_stats.values() if lo <= s["tris"] < hi) for lab, lo, hi in (
                ("0", 0, 1), ("1-99", 1, 100), ("100-999", 100, 1000), ("1k-9k", 1000, 10000),
                ("10k-99k", 10000, 100000), ("100k-999k", 100000, 1000000), ("1M+", 1000000, 10**12))},
            "top_by_tris": [{"name": k, "tris": v["tris"], "verts": v["verts"], "users": v["users"],
                             "mats": v["materials"][:6], "size": [round(v["bbox_max"][i] - v["bbox_min"][i], 2) for i in range(3)]}
                            for k, v in top]}


@section("objects")
def _():
    types = Counter(); hidden = Counter(); mods = Counter(); parents = 0; depth_h = Counter()
    inst_tris = inst_verts = 0; vis_tris = 0
    scale_h = Counter(); nonuni = 0; neg = 0; rotated = 0
    mesh_use = Counter(); inst_coll = Counter(); empties_inst = 0
    wmin = np.array([1e30] * 3); wmax = np.array([-1e30] * 3)
    vmin = np.array([1e30] * 3); vmax = np.array([-1e30] * 3)
    lod_names = []; prefix = Counter(); per_obj = []
    scene = bpy.context.scene
    vl_objs = set(o.name for o in bpy.context.view_layer.objects)
    in_any_scene = set()
    for s in bpy.data.scenes:
        in_any_scene.update(o.name for o in s.objects)
    not_in_scene = 0
    for o in bpy.data.objects:
        types[o.type] += 1
        if o.name not in in_any_scene:
            not_in_scene += 1
        hv = o.hide_viewport; hr = o.hide_render
        try:
            hg = o.hide_get() if o.name in vl_objs else None
        except Exception:
            hg = None
        vis = (o.name in vl_objs) and not hv and not hr and not hg and o.visible_get()
        hidden["hide_viewport"] += hv; hidden["hide_render"] += hr; hidden["hide_eye"] += bool(hg)
        hidden["not_in_view_layer"] += (o.name not in vl_objs); hidden["visible_get_false"] += (not vis)
        if o.parent:
            parents += 1
        d = 0; p = o.parent
        while p:
            d += 1; p = p.parent
        depth_h[d] += 1
        for md in o.modifiers:
            mods[md.type] += 1
        if o.instance_type != 'NONE':
            empties_inst += 1
            if o.instance_collection:
                inst_coll[o.instance_collection.name] += 1
        if re.search(r'lod', o.name, re.I):
            lod_names.append(o.name)
        prefix[re.split(r'[._\-\d ]', o.name)[0][:24].lower()] += 1
        sc = o.matrix_world.to_scale()
        s3 = [round(abs(x), 3) for x in sc]
        key = "%g" % round(sum(s3) / 3, 2)
        scale_h[key] += 1
        if max(s3) - min(s3) > 0.01 * max(max(s3), 1e-9):
            nonuni += 1
        if o.matrix_world.determinant() < 0:
            neg += 1
        if o.type == 'MESH' and o.data:
            st = mesh_stats.get(o.data.name)
            if st:
                inst_tris += st["tris"]; inst_verts += st["verts"]
                if vis:
                    vis_tris += st["tris"]
                mesh_use[o.data.name] += 1
                bb = np.array([list(o.matrix_world @ Vector(c)) for c in o.bound_box])
                wmin = np.minimum(wmin, bb.min(0)); wmax = np.maximum(wmax, bb.max(0))
                if vis:
                    vmin = np.minimum(vmin, bb.min(0)); vmax = np.maximum(vmax, bb.max(0))
                per_obj.append((o.name, o.data.name, st["tris"], [round(float(x), 2) for x in (bb.max(0) - bb.min(0))],
                                [round(float(x), 2) for x in (bb.max(0) + bb.min(0)) / 2], vis,
                                [round(x, 4) for x in sc]))
    shared = {k: v for k, v in mesh_use.items() if v > 1}
    shared_saved = sum(mesh_stats[k]["tris"] * (v - 1) for k, v in shared.items())
    top_shared = sorted(shared.items(), key=lambda kv: -kv[1])[:40]
    per_obj.sort(key=lambda x: -x[2])
    biggest_extent = sorted(per_obj, key=lambda x: -max(x[3]))[:25]
    return {"count": len(bpy.data.objects), "types": dict(types), "hidden": dict(hidden),
            "not_in_any_scene": not_in_scene, "parented": parents, "parent_depth_hist": dict(depth_h),
            "modifiers": dict(mods), "instancer_objects": empties_inst, "instanced_collections": dict(inst_coll.most_common(40)),
            "instanced_tris_all_mesh_objects": inst_tris, "instanced_verts_all_mesh_objects": inst_verts,
            "instanced_tris_visible": vis_tris,
            "mesh_data_shared_by_gt1_objects": len(shared),
            "objects_using_shared_mesh": sum(shared.values()),
            "tris_saved_if_instanced": shared_saved,
            "top_shared_meshes": [{"mesh": k, "instances": v, "tris": mesh_stats[k]["tris"]} for k, v in top_shared],
            "top_shared_by_tris_saved": [{"mesh": k, "instances": v, "tris": mesh_stats[k]["tris"]} for k, v in
                                         sorted(shared.items(), key=lambda kv: -mesh_stats[kv[0]]["tris"] * (kv[1] - 1))[:40]],
            "world_scale_hist": dict(scale_h.most_common(30)), "non_uniform_scale": nonuni, "negative_scale": neg,
            "world_bbox_all_mesh": {"min": wmin.tolist(), "max": wmax.tolist(), "size": (wmax - wmin).tolist()},
            "world_bbox_visible_mesh": {"min": vmin.tolist(), "max": vmax.tolist(), "size": (vmax - vmin).tolist()},
            "lod_named_objects": len(lod_names), "lod_named_examples": lod_names[:40],
            "name_prefix_hist": dict(prefix.most_common(80)),
            "top_objects_by_tris": [{"obj": a, "mesh": b, "tris": c, "size": d, "center": e, "visible": f, "scale": g} for a, b, c, d, e, f, g in per_obj[:40]],
            "largest_extent_objects": [{"obj": a, "mesh": b, "tris": c, "size": d, "center": e, "visible": f} for a, b, c, d, e, f, g in biggest_extent],
            "object_size_hist_max_extent_m": {lab: sum(1 for x in per_obj if lo <= max(x[3]) < hi) for lab, lo, hi in (
                ("<0.5", 0, .5), ("0.5-2", .5, 2), ("2-10", 2, 10), ("10-50", 10, 50), ("50-200", 50, 200), ("200-1000", 200, 1000), ("1000+", 1000, 1e12))}}


@section("spatial_grid")
def _():
    # triangle density on a 64 m XY grid from object bbox centers (coarse)
    cell = 64.0; g = Counter(); go = Counter()
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.data and o.data.name in mesh_stats:
            c = o.matrix_world @ (sum((Vector(b) for b in o.bound_box), Vector()) / 8)
            k = (int(c.x // cell), int(c.y // cell))
            g[k] += mesh_stats[o.data.name]["tris"]; go[k] += 1
    cells = sorted(g.items(), key=lambda kv: -kv[1])
    return {"cell_m": cell, "occupied_cells": len(g),
            "top_cells": [{"cell": list(k), "tris": v, "objects": go[k]} for k, v in cells[:30]],
            "tris_in_top10pct_cells": sum(v for _, v in cells[:max(1, len(cells) // 10)])}


@section("materials")
def _():
    node_h = Counter(); blend = Counter(); render_m = Counter(); bf = Counter(); nodeless = 0
    princ_link = Counter(); img_per_mat = Counter(); out = []; zero = 0; grp = Counter()
    kw = Counter()
    for m in bpy.data.materials:
        zero += (m.users == 0)
        blend[getattr(m, "blend_method", "?")] += 1
        render_m[getattr(m, "surface_render_method", "?")] += 1
        bf[bool(m.use_backface_culling)] += 1
        for k in ("water", "glass", "leaf", "leaves", "foliage", "grass", "tree", "plant", "alpha", "decal", "emis", "light", "sky", "terrain", "ground", "fx", "flag", "cloth", "window", "ivy", "flower", "bush", "hedge"):
            if k in m.name.lower():
                kw[k] += 1
        d = {"name": m.name, "users": m.users, "blend": getattr(m, "blend_method", None), "nodes": [], "images": [], "linked": []}
        nt = m.node_tree if m.use_nodes else None
        if not nt:
            nodeless += 1
        else:
            def walk(tree, seen):
                for n in tree.nodes:
                    node_h[n.bl_idname] += 1
                    d["nodes"].append(n.bl_idname)
                    if n.bl_idname == "ShaderNodeTexImage":
                        d["images"].append(n.image.name if n.image else None)
                    if n.bl_idname == "ShaderNodeGroup" and n.node_tree:
                        grp[n.node_tree.name] += 1
                        if n.node_tree.name not in seen:
                            seen.add(n.node_tree.name); walk(n.node_tree, seen)
                    if n.bl_idname == "ShaderNodeBsdfPrincipled":
                        for i in n.inputs:
                            if i.is_linked:
                                princ_link[i.name] += 1; d["linked"].append(i.name)
            walk(nt, set())
        img_per_mat[len(d["images"])] += 1
        d["node_count"] = len(d["nodes"]); d["nodes"] = dict(Counter(d["nodes"]))
        out.append(d)
    out.sort(key=lambda x: -x["users"])
    return {"count": len(bpy.data.materials), "zero_users": zero, "without_nodes": nodeless,
            "blend_method": dict(blend), "surface_render_method": dict(render_m),
            "backface_culling": {str(k): v for k, v in bf.items()},
            "node_type_hist": dict(node_h.most_common(60)), "node_groups_used": dict(grp.most_common(40)),
            "principled_linked_inputs": dict(princ_link.most_common(40)),
            "image_nodes_per_material_hist": dict(img_per_mat), "name_keyword_hist": dict(kw),
            "node_count_hist": {lab: sum(1 for x in out if lo <= x["node_count"] < hi) for lab, lo, hi in (
                ("0", 0, 1), ("1-5", 1, 6), ("6-15", 6, 16), ("16-40", 16, 41), ("41+", 41, 10**9))},
            "samples_most_used": out[:25],
            "samples_most_complex": sorted(out, key=lambda x: -x["node_count"])[:10],
            "all_names": [m.name for m in bpy.data.materials]}


@section("material_usage")
def _():
    # triangles per material slot over all mesh object instances
    tri_by_mat = Counter()
    per_mesh = {}
    for m in bpy.data.meshes:
        n = len(m.polygons)
        if not n:
            continue
        mi = np.empty(n, dtype=np.int32); lt = np.empty(n, dtype=np.int32)
        m.polygons.foreach_get("material_index", mi); m.polygons.foreach_get("loop_total", lt)
        names = [mm.name if mm else "<none>" for mm in m.materials] or ["<none>"]
        acc = Counter()
        for idx in np.unique(mi):
            nm = names[idx] if idx < len(names) else "<none>"
            acc[nm] += int((lt[mi == idx] - 2).sum())
        per_mesh[m.name] = acc
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.data and o.data.name in per_mesh:
            for k, v in per_mesh[o.data.name].items():
                tri_by_mat[k] += v
    slots = Counter(len(v) for v in per_mesh.values())
    return {"materials_with_tris": len(tri_by_mat), "top_materials_by_instanced_tris": tri_by_mat.most_common(50),
            "material_slots_used_per_mesh_hist": dict(slots)}


@section("images")
def _():
    res = []; packed = ext_ok = ext_missing = gen = 0; px = 0; cs = Counter(); fmt = Counter(); sizes = Counter(); packed_bytes = 0
    base = os.path.dirname(bpy.data.filepath)
    for im in bpy.data.images:
        w, h = im.size[0], im.size[1]
        is_packed = im.packed_file is not None or len(getattr(im, "packed_files", [])) > 0
        ap = bpy.path.abspath(im.filepath, start=base) if im.filepath else ""
        exists = bool(ap) and os.path.exists(ap)
        if im.source == 'GENERATED' or im.type in ('RENDER_RESULT', 'COMPOSITING'):
            gen += 1; status = "generated"
        elif is_packed:
            packed += 1; status = "packed"
            try:
                packed_bytes += sum(p.size for p in im.packed_files)
            except Exception:
                pass
        elif exists:
            ext_ok += 1; status = "external_ok"
        else:
            ext_missing += 1; status = "external_missing"
        px += w * h
        cs[im.colorspace_settings.name] += 1; fmt[im.file_format] += 1; sizes["%dx%d" % (w, h)] += 1
        res.append({"name": im.name, "size": [w, h], "status": status, "path": im.filepath, "users": im.users,
                    "fmt": im.file_format, "cs": im.colorspace_settings.name, "channels": im.channels, "depth": im.depth,
                    "alpha_mode": im.alpha_mode})
    suffix = Counter()
    for r in res:
        b = os.path.splitext(r["name"])[0].lower()
        mm = re.search(r'_([a-z]{1,8})$', b)
        suffix[mm.group(1) if mm else "?"] += 1
    return {"count": len(res), "packed": packed, "external_ok": ext_ok, "external_missing": ext_missing, "generated": gen,
            "packed_bytes": packed_bytes, "total_pixels": px, "rgba8_uncompressed_bytes_no_mips": px * 4,
            "colorspace": dict(cs), "file_format": dict(fmt), "size_hist": dict(sizes.most_common(30)),
            "zero_users": sum(1 for r in res if r["users"] == 0), "name_suffix_hist": dict(suffix.most_common(40)),
            "missing_examples": [r for r in res if r["status"] == "external_missing"][:40],
            "all": res}


@section("lights_world")
def _():
    lt = Counter(); ls = []
    for o in bpy.data.objects:
        if o.type == 'LIGHT' and o.data:
            l = o.data; lt[l.type] += 1
            ls.append({"obj": o.name, "type": l.type, "energy": l.energy, "color": list(l.color),
                       "loc": [round(x, 2) for x in o.matrix_world.translation],
                       "shadow": getattr(l, "use_shadow", None), "spot_size": getattr(l, "spot_size", None)})
    worlds = []
    for w in bpy.data.worlds:
        nodes = [n.bl_idname for n in w.node_tree.nodes] if w.use_nodes and w.node_tree else []
        imgs = [n.image.name for n in w.node_tree.nodes if n.bl_idname in ("ShaderNodeTexEnvironment", "ShaderNodeTexImage") and n.image] if nodes else []
        worlds.append({"name": w.name, "nodes": nodes, "images": imgs, "color": list(w.color)})
    cams = [{"obj": o.name, "loc": [round(x, 2) for x in o.matrix_world.translation]} for o in bpy.data.objects if o.type == 'CAMERA']
    others = [{"obj": o.name, "type": o.type, "empty_type": getattr(o, "empty_display_type", None)} for o in bpy.data.objects if o.type not in ('MESH', 'LIGHT', 'CAMERA')][:80]
    return {"light_types": dict(lt), "lights": ls[:200], "worlds": worlds, "cameras": cams, "non_mesh_objects_sample": others}


@section("orphans_misc")
def _():
    return {"orphan_meshes": sum(1 for m in bpy.data.meshes if m.users == 0),
            "orphan_materials": sum(1 for m in bpy.data.materials if m.users == 0),
            "orphan_images": sum(1 for m in bpy.data.images if m.users == 0),
            "fake_user_meshes": sum(1 for m in bpy.data.meshes if m.use_fake_user),
            "libraries": [l.filepath for l in bpy.data.libraries],
            "texts": [t.name for t in bpy.data.texts],
            "node_groups": [(g.name, g.bl_idname, len(g.nodes)) for g in bpy.data.node_groups][:80],
            "dup_suffix_objects": sum(1 for o in bpy.data.objects if re.search(r'\.\d{3}$', o.name)),
            "dup_suffix_materials": sum(1 for o in bpy.data.materials if re.search(r'\.\d{3}$', o.name)),
            "dup_suffix_images": sum(1 for o in bpy.data.images if re.search(r'\.\d{3}$', o.name)),
            "dup_suffix_meshes": sum(1 for o in bpy.data.meshes if re.search(r'\.\d{3}$', o.name))}


R["elapsed_s"] = time.time() - t0
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(R, f, indent=1, default=str)
# full per-mesh table separately (large)
with open(os.path.splitext(out_path)[0] + "_meshes.json", "w", encoding="utf-8") as f:
    json.dump(mesh_stats, f, default=str)
print("[inspect] wrote", out_path, "errors:", len(R["errors"]), flush=True)
