"""Convert the cooked map's PNG textures to BC7 DDS with full mip chains.
  py convert_textures_dds.py <game_dir> [--all]
Runs texconv (DirectXTex, MIT; naboo/external/texconv/texconv.exe) on <game_dir>/textures/naboo/*.png.
--ignore-srgb is required: the engine works in display space and the PNGs are tagged sRGB, so without it
texconv converts them to linear values for the UNORM target and everything comes out dark.
The PNGs stay in place as a fallback; the renderer prefers a .dds with the same name.
The sky faces in textures/naboo/env are left as PNG.

Only PNGs without an up-to-date .dds are converted unless --all is given.

Cut-out textures (those used by a shader with alphaFunc: leaves, vines, flowers) get two extra steps, because
alpha-tested foliage otherwise thins out: the source renders these materials with stochastic alpha, i.e. with a
coverage equal to the mean alpha, while a 0.5 test on mip-mapped alpha drops most of a thin leaf.
  1. alpha is multiplied by `foliage_alpha_gain` (naboo_config.json, default 1.6) before conversion;
  2. texconv -keepcoverage 0.5 rescales the alpha of every mip so the share of texels passing the 0.5 test
     stays what it is in the top level.
"""
import os, subprocess, sys, time, re, json, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
TEXCONV = os.path.normpath(os.path.join(HERE, "..", "external", "texconv", "texconv.exe"))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
GAIN = float(cfg.get("foliage_alpha_gain", 1.6))
GAIN_OVERRIDE = {k.lower(): float(v) for k, v in cfg.get("foliage_alpha_gain_overrides", {}).items()}     # per texture name
game = sys.argv[1]
d = os.path.join(game, "textures", "naboo")
t0 = time.time()

# textures used by cut-out shaders
script = ""
sd = os.path.join(game, "shaders")
for f in os.listdir(sd):
    if f.lower().endswith(".shader"):
        script += open(os.path.join(sd, f), encoding="latin1").read() + "\n"
cut = set()
for m in re.finditer(r"^(\S+)\s*\n\{(.*?)^\}", script, re.S | re.M):
    body = m.group(2)
    if "alphafunc" in body.lower():
        for mm in re.finditer(r"^\s*map\s+textures/naboo/(\S+)", body, re.M | re.I):
            cut.add(mm.group(1).lower())

stamp = os.path.join(d, "_foliage_gain.txt")
old_gain = open(stamp).read().strip() if os.path.exists(stamp) else ""
redo_cut = old_gain != "%.3f" % GAIN
todo_plain = []; todo_cut = []
for f in sorted(os.listdir(d)):
    if not f.lower().endswith(".png"):
        continue
    stem = f[:-4]; src = os.path.join(d, f); dst = os.path.join(d, stem + ".dds")
    fresh = os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src)
    if stem.lower() in cut:
        if "--all" in sys.argv or redo_cut or not fresh:
            todo_cut.append(f)
    elif "--all" in sys.argv or not fresh:
        todo_plain.append(f)

BASE = [TEXCONV, "-nologo", "-f", "BC7_UNORM", "-m", "0", "-y", "-dx10", "-sepalpha", "--ignore-srgb", "-o", d]
rc = 0


def run(files, extra, folder):
    global rc
    for i in range(0, len(files), 40):
        r = subprocess.run(BASE + extra + [os.path.join(folder, f) for f in files[i:i + 40]], capture_output=True, text=True)
        if r.returncode != 0:
            rc = r.returncode; print(r.stdout[-1500:], r.stderr[-1500:])


if todo_plain:
    run(todo_plain, [], d)
if todo_cut:
    from PIL import Image
    import numpy as np
    tmp = tempfile.mkdtemp(prefix="naboo_cut_")
    try:
        for f in todo_cut:
            im = Image.open(os.path.join(d, f)).convert("RGBA")
            a = np.asarray(im).copy()
            a[:, :, 3] = np.clip(a[:, :, 3].astype(np.float32) * GAIN_OVERRIDE.get(f[:-4].lower(), GAIN), 0, 255).astype(np.uint8)
            Image.fromarray(a).save(os.path.join(tmp, f))
        run(todo_cut, ["-keepcoverage", "0.5"], tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    open(stamp, "w").write("%.3f" % GAIN)
png = [f for f in os.listdir(d) if f.lower().endswith(".png")]
dds = [f for f in os.listdir(d) if f.lower().endswith(".dds")]
print("texconv exit", rc, "seconds %.0f" % (time.time() - t0), "converted plain", len(todo_plain), "cut-out", len(todo_cut), "(gain %.2f, keepcoverage 0.5)" % GAIN,
      "| png", len(png), "dds", len(dds), "dds bytes", sum(os.path.getsize(os.path.join(d, f)) for f in dds))
