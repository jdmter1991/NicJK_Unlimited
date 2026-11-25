# Extras for the cooked world, exported from Blender (read-only on the .blend; nothing is saved back):
#   sky      six cube faces of the scene's sky, rendered with Cycles from an otherwise empty scene
#   terrain  the terrain material's base colour baked to an image and split into 2 x 2 tiles
#   water    the large water meshes that the region export skips for their size
#   blender -b --factory-startup --disable-autoexec <blend> --python export_extras.py -- <config.json> <outdir> [sky] [terrain] [water]
import bpy, sys, json, os, time, traceback
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
cfg = json.load(open(argv[0], encoding="utf-8")); outdir = argv[1]
steps = set(argv[2:]) or {"sky", "terrain", "water"}
xdir = os.path.join(outdir, "dump", "extras"); os.makedirs(xdir, exist_ok=True)
REP = {}
rep_path = os.path.join(outdir, "extras_report.json")


def save_rep():
    json.dump(REP, open(rep_path, "w", encoding="utf-8"), indent=1)


def save_png(name, arr):
    """arr: (h, w, 4) float32, row 0 = bottom (Blender convention)"""
    h, w = arr.shape[:2]
    im = bpy.data.images.new("_out_" + name, w, h, alpha=True)
    im.pixels.foreach_set(arr.astype(np.float32).ravel())
    im.file_format = 'PNG'; im.filepath_raw = os.path.join(xdir, name + ".png"); im.save()
    bpy.data.images.remove(im)


# ---------------------------------------------------------------- water (before anything is hidden)
if "water" in steps:
    t0 = time.time(); items = []
    try:
        for nm in ("Theed_Water", "Naboo_Waterfalls_01"):
            o = bpy.data.objects.get(nm)
            if not o or o.type != 'MESH':
                continue
            me = o.data; me.calc_loop_triangles()
            nv = len(me.vertices); nl = len(me.loops); nt = len(me.loop_triangles)
            pos = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", pos)
            lv = np.empty(nl, np.int32); me.loops.foreach_get("vertex_index", lv)
            ln = np.empty(nl * 3, np.float32); me.corner_normals.foreach_get("vector", ln)
            tl = np.empty(nt * 3, np.int32); me.loop_triangles.foreach_get("loops", tl)
            a = {"pos": pos.reshape(-1, 3), "loop_vert": lv, "loop_normal": ln.reshape(-1, 3), "tri_loops": tl.reshape(-1, 3),
                 "tri_mat": np.zeros(nt, np.int16)}
            if me.uv_layers:
                uv = np.empty(nl * 2, np.float32); me.uv_layers[0].uv.foreach_get("vector", uv); a["uv0"] = uv.reshape(-1, 2)
            fn = nm + ".npz"; np.savez(os.path.join(xdir, fn), **a)
            items.append({"name": nm, "file": fn, "kind": "water", "tris": nt, "matrix": [list(r) for r in o.matrix_world],
                          "materials": [m.name if m else None for m in me.materials]})
        json.dump(items, open(os.path.join(xdir, "extras.json"), "w"), indent=1)
        REP["water"] = {"seconds": round(time.time() - t0, 1), "objects": [(i["name"], i["tris"]) for i in items]}
    except Exception:
        REP["water"] = {"error": traceback.format_exc()[-800:]}
    save_rep(); print("[extras] water", REP["water"], flush=True)

# ---------------------------------------------------------------- sky cube faces
if "sky" in steps:
    t0 = time.time()
    try:
        src = bpy.context.scene
        sc = bpy.data.scenes.new("_sky"); sc.world = src.world
        sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 4
        try:
            sc.cycles.use_denoising = False
        except Exception:
            pass
        N = int(cfg.get("sky_face_px", 1024))
        sc.render.resolution_x = N; sc.render.resolution_y = N; sc.render.resolution_percentage = 100
        sc.render.image_settings.file_format = 'PNG'
        sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'
        sc.view_settings.exposure = float(cfg.get("sky_exposure", 0.0))
        cam_d = bpy.data.cameras.new("_skycam"); cam_d.type = 'PERSP'; cam_d.sensor_fit = 'HORIZONTAL'; cam_d.angle = np.pi / 2
        cam_d.clip_start = 0.1; cam_d.clip_end = 1000.0
        cam = bpy.data.objects.new("_skycam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
        # Quake 3 sky box faces: image right = +s, image up = +t (see MakeSkyVec in tr_sky.cpp)
        faces = {"rt": ((1, 0, 0), (0, 0, 1)), "lf": ((-1, 0, 0), (0, 0, 1)), "bk": ((0, 1, 0), (0, 0, 1)), "ft": ((0, -1, 0), (0, 0, 1)),
                 "up": ((0, 0, 1), (-1, 0, 0)), "dn": ((0, 0, -1), (1, 0, 0))}
        win = bpy.context.window
        for suf, (fwd, up) in faces.items():
            f = Vector(fwd); u = Vector(up); r = f.cross(u)
            m = Matrix(((r.x, u.x, -f.x, 0), (r.y, u.y, -f.y, 0), (r.z, u.z, -f.z, 0), (0, 0, 0, 1)))
            cam.matrix_world = m
            sc.render.filepath = os.path.join(xdir, "sky_" + suf + ".png")
            bpy.ops.render.render(write_still=True, scene=sc.name)
        REP["sky"] = {"seconds": round(time.time() - t0, 1), "px": N, "files": sorted(f for f in os.listdir(xdir) if f.startswith("sky_"))}
    except Exception:
        REP["sky"] = {"error": traceback.format_exc()[-1200:]}
    save_rep(); print("[extras] sky", REP["sky"], flush=True)

# ---------------------------------------------------------------- terrain base-colour bake
if "terrain" in steps:
    t0 = time.time()
    try:
        scene = bpy.context.scene
        terr = bpy.data.objects["Terrain_Near"]; me = terr.data
        for o in bpy.data.objects:                 # only the terrain takes part in the bake (memory)
            if o is not terr:
                o.hide_render = True
        terr.hide_render = False
        terr.modifiers.clear()
        nv = len(me.vertices); nl = len(me.loops)
        pos = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", pos); pos = pos.reshape(-1, 3)
        x0, y0 = pos[:, 0].min(), pos[:, 1].min(); x1, y1 = pos[:, 0].max(), pos[:, 1].max()
        lv = np.empty(nl, np.int32); me.loops.foreach_get("vertex_index", lv)
        uv = np.empty((nl, 2), np.float32)
        uv[:, 0] = (pos[lv, 0] - x0) / (x1 - x0); uv[:, 1] = (pos[lv, 1] - y0) / (y1 - y0)
        layer = me.uv_layers.new(name="_bake"); layer.uv.foreach_set("vector", uv.ravel()); me.uv_layers.active = layer
        try:
            layer.active_render = True
        except Exception:
            pass
        N = int(cfg.get("terrain_bake_px", 4096))
        img = bpy.data.images.new("_terrain_bake", N, N, alpha=False)
        for mat in me.materials:
            if mat and mat.node_tree:
                nd = mat.node_tree.nodes.new("ShaderNodeTexImage"); nd.image = img
                for n in mat.node_tree.nodes:
                    n.select = False
                nd.select = True; mat.node_tree.nodes.active = nd
        scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'; scene.cycles.samples = 1
        b = scene.render.bake
        b.use_pass_direct = False; b.use_pass_indirect = False; b.use_pass_color = True; b.margin = 2
        b.use_selected_to_active = False; b.use_clear = True
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        terr.select_set(True); bpy.context.view_layer.objects.active = terr
        bpy.ops.object.bake(type='DIFFUSE')
        px = np.empty(N * N * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(N, N, 4)
        h = N // 2
        mean = []
        for ty in range(2):                        # row 0 = bottom = low y
            for tx in range(2):
                tile = px[ty * h:(ty + 1) * h, tx * h:(tx + 1) * h]
                save_png("terrain_bake_%d%d" % (tx, ty), tile); mean.append([round(float(v), 3) for v in tile[:, :, :3].mean((0, 1))])
        REP["terrain"] = {"seconds": round(time.time() - t0, 1), "px": N, "bounds_m": [float(x0), float(y0), float(x1), float(y1)],
                          "tile_mean_rgb": mean, "all_black": bool(px[:, :, :3].max() < 0.01)}
        json.dump({"bounds_m": [float(x0), float(y0), float(x1), float(y1)], "tiles": 2}, open(os.path.join(xdir, "terrain_bake.json"), "w"))
    except Exception:
        REP["terrain"] = {"error": traceback.format_exc()[-1500:]}
    save_rep(); print("[extras] terrain", REP["terrain"], flush=True)

print("[extras] done", flush=True)
