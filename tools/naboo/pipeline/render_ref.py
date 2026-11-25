"""Blender (headless, read-only): reference renders of the source scene from game camera positions.
  blender -b --factory-startup --disable-autoexec <file.blend> --python render_ref.py -- <out_dir> <cams.json>
cams.json: {"units_per_metre": .., "origin_m": [..], "hfov": 96.4, "size": [960, 540], "samples": 48, "frame": 24,
            "cams": [{"name": "..", "pos": [x, y, z], "yaw": deg, "pitch_down": deg}, ...]}   (game units and angles)
The .blend is never saved. Uses Cycles on the GPU when one is available.
"""
import bpy, sys, json, math, time, os

out_dir, spec = sys.argv[sys.argv.index("--") + 1:][:2]
S = json.load(open(spec))
sc = bpy.context.scene
sc.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            devs = [d for d in prefs.devices if d.type == kind]
            if devs:
                for d in prefs.devices:
                    d.use = d.type == kind
                sc.cycles.device = "GPU"
                print("REF device", kind, [d.name for d in devs])
                break
        except Exception as e:
            print("REF device", kind, "unavailable:", e)
except Exception as e:
    print("REF no cycles prefs:", e)
sc.cycles.samples = int(S.get("samples", 48))
sc.cycles.use_denoising = True
sc.cycles.use_adaptive_sampling = True
sc.cycles.max_bounces = 4
sc.render.resolution_x, sc.render.resolution_y = S.get("size", [960, 540]); sc.render.resolution_percentage = 100
sc.render.use_persistent_data = True
sc.render.image_settings.file_format = "PNG"
sc.frame_set(int(S.get("frame", 24)))
cam_data = bpy.data.cameras.new("ref_cam"); cam = bpy.data.objects.new("ref_cam", cam_data); sc.collection.objects.link(cam)
cam_data.sensor_fit = "HORIZONTAL"; cam_data.angle = math.radians(float(S.get("hfov", 96.4)))
cam_data.clip_start = 0.1; cam_data.clip_end = 40000.0
sc.camera = cam
UPM = S["units_per_metre"]; ORG = S["origin_m"]
for c in S["cams"]:
    t0 = time.time()
    cam.location = [c["pos"][i] / UPM + ORG[i] for i in range(3)]
    cam.rotation_euler = (math.radians(90.0 - c.get("pitch_down", 0.0)), 0.0, math.radians(c["yaw"] - 90.0))
    sc.render.filepath = os.path.join(out_dir, "ref_" + c["name"] + ".png")
    bpy.ops.render.render(write_still=True)
    print("REF rendered %s in %.0f s" % (c["name"], time.time() - t0), flush=True)
print("REF done")
