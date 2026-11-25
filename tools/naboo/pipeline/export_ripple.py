# Water ripple texture for the animated water: greyscale, mean 0.5, made from the game's water normal map.
#   blender -b --factory-startup --disable-autoexec <blend> --python export_ripple.py -- <outdir>
import bpy, sys, os
import numpy as np
outdir = sys.argv[sys.argv.index("--") + 1]
xdir = os.path.join(outdir, "dump", "extras"); os.makedirs(xdir, exist_ok=True)
src = None
for nm in ("T_WaterPlane_01_N.png", "T_DistortionNoise_01_N.png"):
    if bpy.data.images.get(nm):
        src = bpy.data.images[nm]; break
w, h = src.size
px = np.empty(w * h * 4, np.float32); src.pixels.foreach_get(px); px = px.reshape(h, w, 4)
k = max(1, w // 512)
nx = px[::k, ::k, 0] - 0.5; ny = px[::k, ::k, 1] - 0.5
r = nx * 0.8 + ny * 0.6                      # slope along a fixed light direction: reads as ripples
r = 0.5 + r / (np.abs(r).max() + 1e-6) * 0.5
r = np.clip(0.5 + (r - r.mean()) * 1.6, 0.0, 1.0)
out = np.ones(r.shape + (4,), np.float32); out[:, :, 0] = out[:, :, 1] = out[:, :, 2] = r
im = bpy.data.images.new("_ripple", r.shape[1], r.shape[0], alpha=True)
im.pixels.foreach_set(out.ravel()); im.file_format = 'PNG'; im.filepath_raw = os.path.join(xdir, "water_ripple.png"); im.save()
print("[ripple] source", src.name, "size", r.shape, "mean %.3f std %.3f" % (r.mean(), r.std()), flush=True)
