"""Pack the cooked map into pk3 files for a release.
  py build_pk3.py <mod_dir> <mapname> <out_dir> [tag]
Takes from <mod_dir>: maps/<mapname>.{bsp,tworld,tpbr,tuv2,tao,tsky,tlights,tportal,tshadow}, maps/<mapname>_shadow.dds,
the map's shader files, door models, music, arena script, level shot, the sky box, and every texture
(textures/naboo/*.dds) named in the shader files, the PBR side file or the door models. PNG sources are left out.
The engine's zip reader has no zip64, so each pk3 stays under 1.9 GB: one for the map files, the textures split
over as many as needed. Files are deflated at level 1 (the engine reads stored and deflated entries)."""
import sys, os, re, zipfile, json, time
mod, mapname, out = sys.argv[1], sys.argv[2], sys.argv[3]
tag = sys.argv[4] if len(sys.argv) > 4 else "beta1"
os.makedirs(out, exist_ok=True)
LIMIT = 1900 * 1024 * 1024
t0 = time.time()
maps = [f for f in ("%s.bsp %s.tworld %s.tpbr %s.tuv2 %s.tao %s.tsky %s.tlights %s.tportal %s.tshadow %s_shadow.dds" % ((mapname,) * 10)).split()
        if os.path.exists(os.path.join(mod, "maps", f))]
shaders = ["naboo_%s.shader" % mapname, "naboo_sys.shader", "naboo_doors.shader"]
small = [("maps/" + f) for f in maps] + [("shaders/" + f) for f in shaders if os.path.exists(os.path.join(mod, "shaders", f))]
for d in ("models/map_objects/" + mapname, "music/" + mapname, "textures/naboo/env"):
    for f in sorted(os.listdir(os.path.join(mod, d))) if os.path.isdir(os.path.join(mod, d)) else []:
        small.append(d + "/" + f)
for f in ("%s_readme.txt" % mapname, "scripts/%s.arena" % mapname, "botroutes/%s.wnt" % mapname, "levelshots/%s.jpg" % mapname, "levelshots_16_9/%s.jpg" % mapname):
    if os.path.exists(os.path.join(mod, f)):
        small.append(f)
# texture names: every "textures/naboo/<name>" in the shader files, the PBR side file and the door models
words = set()
for f in small:
    if f.endswith((".shader", ".tpbr", ".md3")):
        data = open(os.path.join(mod, f), "rb").read()
        for m in re.finditer(rb"textures/naboo/([A-Za-z0-9_#.\-]+)", data):
            w = m.group(1).decode("ascii").lower(); words.add(w); words.add(os.path.splitext(w)[0])
tdir = os.path.join(mod, "textures", "naboo")
alltex = sorted(f for f in os.listdir(tdir) if f.lower().endswith(".dds"))
used = [f for f in alltex if os.path.splitext(f)[0].lower() in words]
print("textures: %d of %d referenced" % (len(used), len(alltex)))


def write(name, files):
    p = os.path.join(out, name)
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=False) as z:
        for f in files:
            z.write(os.path.join(mod, f), f)
    print(name, len(files), "files", round(os.path.getsize(p) / 1048576.0, 1), "MB"); return p


made = [write("zz_%s_%s_1_map.pk3" % (mapname, tag), small)]
part, cur, size = 2, [], 0
for f in used:
    s = os.path.getsize(os.path.join(tdir, f))
    if size + s > LIMIT and cur:
        made.append(write("zz_%s_%s_%d_textures.pk3" % (mapname, tag, part), cur)); part += 1; cur, size = [], 0
    cur.append("textures/naboo/" + f); size += s
if cur:
    made.append(write("zz_%s_%s_%d_textures.pk3" % (mapname, tag, part), cur))
json.dump({"files": [os.path.basename(p) for p in made], "bytes": [os.path.getsize(p) for p in made], "textures_used": len(used), "textures_on_disk": len(alltex),
           "unreferenced": [f for f in alltex if f not in set(used)][:400], "seconds": round(time.time() - t0, 1)}, open(os.path.join(out, "pk3_report.json"), "w"), indent=1)
