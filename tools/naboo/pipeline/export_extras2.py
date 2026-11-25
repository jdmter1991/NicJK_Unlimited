# More extras for the cooked world (read-only on the .blend; nothing is saved back):
#   detail  a neutral, tiling grain texture for the ground (mean 0.5, used as a x2 multiply)
#   far     the far terrain (height grid + base-colour bake) and the large backdrop meshes the region export skips
#   blender -b --factory-startup --disable-autoexec <blend> --python export_extras2.py -- <config.json> <outdir> [detail] [far]
import bpy, sys, json, os, time, traceback
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(argv[0], encoding="utf-8")); outdir = argv[1]
steps = set(argv[2:]) or {"detail", "far"}
xdir = os.path.join(outdir, "dump", "extras"); os.makedirs(xdir, exist_ok=True)
rep_path = os.path.join(outdir, "extras2_report.json")
REP = {}
HERE = os.path.dirname(os.path.abspath(__file__))


def save_rep():
    json.dump(REP, open(rep_path, "w", encoding="utf-8"), indent=1)


def save_png(name, arr):
    h, w = arr.shape[:2]
    im = bpy.data.images.new("_out_" + name, w, h, alpha=True)
    im.pixels.foreach_set(arr.astype(np.float32).ravel())
    im.file_format = 'PNG'; im.filepath_raw = os.path.join(xdir, name + ".png"); im.save()
    bpy.data.images.remove(im)


# ---------------------------------------------------------------- detail texture
if "detail" in steps:
    t0 = time.time()
    try:
        src = None
        for nm in cfg.get("detail_sources", ["T_Naboo_GravelFine_01_CS.png", "T_Naboo_Concrete_02_CS.png", "T_Naboo_Concrete_01_CS.png"]):
            if bpy.data.images.get(nm):
                src = bpy.data.images[nm]; break
        w, h = src.size
        px = np.empty(w * h * 4, np.float32); src.pixels.foreach_get(px); px = px.reshape(h, w, 4)
        k = max(1, w // 512)
        lum = (px[::k, ::k, 0] * 0.3 + px[::k, ::k, 1] * 0.59 + px[::k, ::k, 2] * 0.11)
        lum = 0.5 + (lum - lum.mean()) * float(cfg.get("detail_contrast", 0.9))
        lum = np.clip(lum, 0.15, 0.85)
        out = np.ones(lum.shape + (4,), np.float32); out[:, :, 0] = out[:, :, 1] = out[:, :, 2] = lum
        save_png("ground_detail", out)
        REP["detail"] = {"seconds": round(time.time() - t0, 1), "source": src.name, "size": list(lum.shape), "mean": round(float(lum.mean()), 3),
                         "std": round(float(lum.std()), 3)}
    except Exception:
        REP["detail"] = {"error": traceback.format_exc()[-800:]}
    save_rep(); print("[extras2] detail", REP["detail"], flush=True)

# ---------------------------------------------------------------- far scenery
if "far" in steps:
    t0 = time.time()
    try:
        # material functions shared with the region exporter (definitions only)
        blk = open(os.path.join(HERE, "_materials_block.py"), encoding="utf-8").read()
        exec(blk[:blk.index("MAT = {}")], globals())

        skip = ("terrain_", "theed_water", "naboo_waterfalls", "heightfog", "invalidatelightplane", "meshp_sky", "fx", "grenadeblocker")
        items = []; mats = {}; images = set()
        for o in bpy.context.view_layer.objects:
            if o.type != 'MESH' or not o.data or len(o.data.polygons) == 0 or not o.visible_get():
                continue
            nm = o.name.lower()
            if any(nm.startswith(s) for s in skip):
                continue
            bb = np.array([list(o.matrix_world @ Vector(c)) for c in o.bound_box])
            if (bb.max(0) - bb.min(0)).max() < 200.0:
                continue
            me = o.data; me.calc_loop_triangles()
            nv = len(me.vertices); nl = len(me.loops); nt = len(me.loop_triangles)
            pos = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", pos)
            lv = np.empty(nl, np.int32); me.loops.foreach_get("vertex_index", lv)
            ln = np.empty(nl * 3, np.float32); me.corner_normals.foreach_get("vector", ln)
            tl = np.empty(nt * 3, np.int32); me.loop_triangles.foreach_get("loops", tl)
            tm = np.empty(nt, np.int32); me.loop_triangles.foreach_get("material_index", tm)
            a = {"pos": pos.reshape(-1, 3), "loop_vert": lv, "loop_normal": ln.reshape(-1, 3), "tri_loops": tl.reshape(-1, 3), "tri_mat": tm.astype(np.int16)}
            if me.uv_layers:
                uv = np.empty(nl * 2, np.float32); me.uv_layers[0].uv.foreach_get("vector", uv); a["uv0"] = uv.reshape(-1, 2)
            fn = "far_%03d.npz" % len(items); np.savez(os.path.join(xdir, fn), **a)
            mnames = [m.name if m else None for m in me.materials]
            for m in me.materials:
                if m and m.name not in mats:
                    mats[m.name] = material_info(m)
                    if mats[m.name]["base_image"]:
                        images.add(mats[m.name]["base_image"])
            items.append({"name": o.name, "file": fn, "kind": "far", "tris": nt, "matrix": [list(r) for r in o.matrix_world], "materials": mnames})
        tex_ok = 0
        for n in sorted(images):
            try:
                bpy.data.images[n].save(filepath=os.path.join(xdir, os.path.splitext(n)[0] + ".png")); tex_ok += 1
            except Exception:
                pass
        json.dump({"objects": items, "materials": mats}, open(os.path.join(xdir, "far.json"), "w"), indent=1)

        # far terrain: height grid + base-colour bake
        terr = bpy.data.objects["Terrain_Far"]; me = terr.data
        nv = len(me.vertices); nl = len(me.loops)
        pos = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", pos); pos = pos.reshape(-1, 3)
        side = int(round(nv ** 0.5)); assert side * side == nv
        g = pos.reshape(side, side, 3)
        if not (abs(g[0, -1, 0] - g[0, 0, 0]) > abs(g[-1, 0, 0] - g[0, 0, 0])):
            g = g.transpose(1, 0, 2)
        if g[0, -1, 0] < g[0, 0, 0]:
            g = g[:, ::-1]
        if g[-1, 0, 1] < g[0, 0, 1]:
            g = g[::-1]
        np.savez(os.path.join(xdir, "terrain_far_grid.npz"), grid=np.ascontiguousarray(g))
        for o in bpy.data.objects:
            if o is not terr:
                o.hide_render = True
        terr.hide_render = False; terr.modifiers.clear()
        x0, y0 = pos[:, 0].min(), pos[:, 1].min(); x1, y1 = pos[:, 0].max(), pos[:, 1].max()
        lv = np.empty(nl, np.int32); me.loops.foreach_get("vertex_index", lv)
        uv = np.empty((nl, 2), np.float32); uv[:, 0] = (pos[lv, 0] - x0) / (x1 - x0); uv[:, 1] = (pos[lv, 1] - y0) / (y1 - y0)
        layer = me.uv_layers.new(name="_bake"); layer.uv.foreach_set("vector", uv.ravel()); me.uv_layers.active = layer
        N = 2048
        img = bpy.data.images.new("_far_bake", N, N, alpha=False)
        for mat in me.materials:
            if mat and mat.node_tree:
                nd = mat.node_tree.nodes.new("ShaderNodeTexImage"); nd.image = img
                for n in mat.node_tree.nodes:
                    n.select = False
                nd.select = True; mat.node_tree.nodes.active = nd
        scene = bpy.context.scene
        scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'; scene.cycles.samples = 1
        b = scene.render.bake
        b.use_pass_direct = False; b.use_pass_indirect = False; b.use_pass_color = True; b.margin = 2; b.use_selected_to_active = False
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        terr.select_set(True); bpy.context.view_layer.objects.active = terr
        bpy.ops.object.bake(type='DIFFUSE')
        px = np.empty(N * N * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(N, N, 4)
        save_png("terrain_far_bake", px)
        json.dump({"bounds_m": [float(x0), float(y0), float(x1), float(y1)], "side": side}, open(os.path.join(xdir, "terrain_far.json"), "w"))
        REP["far"] = {"seconds": round(time.time() - t0, 1), "objects": [(i["name"], i["tris"]) for i in items], "materials": len(mats),
                      "textures_written": tex_ok, "far_grid_side": side, "far_bake_mean_rgb": [round(float(v), 3) for v in px[:, :, :3].mean((0, 1))]}
    except Exception:
        REP["far"] = {"error": traceback.format_exc()[-1500:]}
    save_rep(); print("[extras2] far", REP["far"], flush=True)
print("[extras2] done", flush=True)
