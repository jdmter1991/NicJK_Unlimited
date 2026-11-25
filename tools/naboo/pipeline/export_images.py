"""Blender (read-only): save named images of the .blend as PNG copies.
  blender -b --factory-startup --disable-autoexec <file.blend> --python export_images.py -- <out_dir> <name> [<name> ...]
  (a name may also be @file.txt with one image name per line). Existing files are kept."""
import bpy, sys, os
args = sys.argv[sys.argv.index("--") + 1:]
out = args[0]; names = []
for a in args[1:]:
    names += [l.strip() for l in open(a[1:]) if l.strip()] if a.startswith("@") else [a]
os.makedirs(out, exist_ok=True)
ok = miss = 0
for n in names:
    im = bpy.data.images.get(n)
    dst = os.path.join(out, os.path.splitext(n)[0] + ".png")
    if os.path.exists(dst):
        ok += 1; continue
    if im is None or im.size[0] == 0:
        print("IMG missing", n); miss += 1; continue
    try:
        im.save(filepath=dst)        # writes a copy; the .blend itself is never saved
        ok += 1
    except Exception as e:
        print("IMG failed", n, e); miss += 1
print("IMG done ok %d missing %d" % (ok, miss))
