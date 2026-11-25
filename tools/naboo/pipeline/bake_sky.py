"""Blender (read-only): sky box faces as the source scene shows the sky.
  blender -b --factory-startup --disable-autoexec <file.blend> --python bake_sky.py -- <out_dir> [face px] [x y z in metres]
The earlier bake rendered only the world background. The source's sky is that background seen through the
scene's own sky meshes (cloud layers, fog planes) with the scene's tone mapping (AgX). Here every object is hidden
from rendering except those sky objects, and six 90-degree faces are rendered from above the city with the
scene's own view settings. Nothing is saved to the .blend.
Writes <out_dir>/sky_{rt,lf,bk,ft,up,dn}.png and sky_bake.json (which objects were kept)."""
import bpy, sys, os, re, json, time
from mathutils import Vector, Matrix

args = sys.argv[sys.argv.index("--") + 1:]
out = args[0]; N = int(args[1]) if len(args) > 1 else 1024
pos = [float(v) for v in args[2:5]] if len(args) >= 5 else [700.0, -100.0, 520.0]
t0 = time.time()
sc = bpy.context.scene
PAT = re.compile(r"^(HeightFog|Sky|Cloud)", re.I)       # object names only: the height fog and any sky or cloud object
kept = []
for o in bpy.data.objects:
    if o.type in ("LIGHT", "CAMERA"):
        continue
    if PAT.search(o.name) and o.type in ("MESH", "VOLUME"):
        kept.append({"name": o.name, "type": o.type, "materials": [s.material.name for s in o.material_slots if s.material][:3],
                     "collections": [c.name for c in o.users_collection], "hidden_before": bool(o.hide_render)})
    else:
        o.hide_render = True
sc.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind; prefs.get_devices()
            if any(d.type == kind for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == kind
                sc.cycles.device = "GPU"; break
        except Exception:
            pass
except Exception:
    pass
sc.cycles.samples = 96; sc.cycles.use_denoising = True; sc.cycles.max_bounces = 6
sc.render.resolution_x = N; sc.render.resolution_y = N; sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"; sc.render.film_transparent = False
cam_d = bpy.data.cameras.new("_skycam"); cam_d.type = "PERSP"; cam_d.sensor_fit = "HORIZONTAL"; cam_d.angle = 3.14159265 / 2
cam_d.clip_start = 0.5; cam_d.clip_end = 100000.0
cam = bpy.data.objects.new("_skycam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
# Quake 3 sky box faces: image right = +s, image up = +t (see MakeSkyVec in tr_sky.cpp)
faces = {"rt": ((1, 0, 0), (0, 0, 1)), "lf": ((-1, 0, 0), (0, 0, 1)), "bk": ((0, 1, 0), (0, 0, 1)), "ft": ((0, -1, 0), (0, 0, 1)),
         "up": ((0, 0, 1), (-1, 0, 0)), "dn": ((0, 0, -1), (1, 0, 0))}
for suf, (fwd, up) in faces.items():
    f = Vector(fwd); u = Vector(up); r = f.cross(u)
    cam.matrix_world = Matrix(((r.x, u.x, -f.x, pos[0]), (r.y, u.y, -f.y, pos[1]), (r.z, u.z, -f.z, pos[2]), (0, 0, 0, 1)))
    sc.render.filepath = os.path.join(out, "sky_" + suf + ".png")
    bpy.ops.render.render(write_still=True)
    print("SKY face", suf, "%.0f s" % (time.time() - t0), flush=True)
json.dump({"seconds": round(time.time() - t0, 1), "px": N, "position_m": pos, "view_transform": sc.view_settings.view_transform, "look": sc.view_settings.look,
           "exposure": sc.view_settings.exposure, "kept_objects": kept}, open(os.path.join(out, "sky_bake.json"), "w"), indent=1)
print("SKY done, kept", len(kept), "objects:", [k["name"] for k in kept][:12])
