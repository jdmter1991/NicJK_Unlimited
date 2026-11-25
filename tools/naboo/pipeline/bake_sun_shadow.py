"""Bake a static sun shadow map from a cooked world.
  py bake_sun_shadow.py <game_dir>/taystjk <mapname> [--size 8192] [--bounds x0 y0 z0 x1 y1 z1]
Reads  <game>/maps/<mapname>.tworld            meshes (detail level 0), placements, materials, sun direction
       <game>/shaders/*.shader, textures       only to find the alpha channel of cutout (alphaFunc) materials
Writes <game>/maps/<mapname>_shadow.dds        R16_UNORM, depth from the sun (0 = nearest), 65535 = nothing
       <game>/maps/<mapname>.tshadow           header with the world -> texel/depth transform and a reduced
                                               copy of the map for CPU lookups (player lighting)

Method: every casting triangle is sampled on a regular barycentric lattice finer than half a texel and the
samples are splatted into the map keeping the nearest depth; isolated texels that stayed deeper than all eight
neighbours are closed afterwards. Blended materials (water, glass, glow) cast nothing; cutout materials are
tested against their texture's alpha. No Blender involved.
"""
import sys, os, re, struct, time, json, glob
import numpy as np

t0 = time.time()
game, mapname = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8")).get("shadow", {})
SIZE = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else int(cfg.get("size", 8192))
LOW = int(cfg.get("cpu_size", 1024))
STEP = float(cfg.get("sample_step_texels", 0.5))
MIN_R = float(cfg.get("min_caster_radius_units", 0.0))      # smaller placements (ground scatter) cast nothing

buf = np.memmap(os.path.join(game, "maps", mapname + ".tworld"), dtype=np.uint8, mode="r")
magic, ver, nmat, nmesh, nsub, ninst, nvert, nidx = struct.unpack_from("<4sIIIIIII", buf, 0)
assert magic == b"TWLD" and ver == 2
sun = np.array(struct.unpack_from("<3f", buf, 60), np.float64); sun /= np.linalg.norm(sun)
o = 112
mats = np.frombuffer(buf, dtype=[("shader", "S64"), ("tint", "<f4", 3), ("flags", "<u4")], count=nmat, offset=o); o += nmat * 80
meshes = np.frombuffer(buf, dtype=[("fv", "<u4"), ("nv", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("nl", "<u4"), ("lfs", "<u4", 3), ("lns", "<u4", 3),
                                   ("c", "<f4", 3), ("r", "<f4")], count=nmesh, offset=o); o += nmesh * 60
subs = np.frombuffer(buf, dtype=[("mat", "<u4"), ("fi", "<u4"), ("ni", "<u4"), ("res", "<u4")], count=nsub, offset=o); o += nsub * 16
insts = np.frombuffer(buf, dtype=[("mesh", "<u4"), ("m", "<f4", 12), ("c", "<f4", 3), ("r", "<f4")], count=ninst, offset=o); o += ninst * 68
verts = np.frombuffer(buf, dtype=[("xyz", "<f4", 3), ("n", "<f4", 3), ("st", "<f4", 2)], count=nvert, offset=o); o += nvert * 32
indexes = np.frombuffer(buf, dtype="<u4", count=nidx, offset=o)

# ---- bounds of the shadowed region (engine units)
if "--bounds" in sys.argv:
    i = sys.argv.index("--bounds"); bb = np.array([float(x) for x in sys.argv[i + 1:i + 7]]).reshape(2, 3)
elif "bounds_units" in cfg:
    bb = np.array(cfg["bounds_units"], np.float64)
else:
    raise SystemExit("no bounds: pass --bounds or set shadow.bounds_units in naboo_config.json")
corners = np.array([[bb[i][0], bb[j][1], bb[k][2]] for i in (0, 1) for j in (0, 1) for k in (0, 1)])

# ---- sun space: U horizontal, V up the slope, depth grows away from the sun
U = np.cross([0.0, 0.0, 1.0], sun); U /= np.linalg.norm(U)
V = np.cross(sun, U)
cu, cv, cs = corners @ U, corners @ V, corners @ sun
scale = SIZE / max(cu.max() - cu.min(), cv.max() - cv.min())          # texels per unit
W = int(np.ceil((cu.max() - cu.min()) * scale / 4) * 4); H = int(np.ceil((cv.max() - cv.min()) * scale / 4) * 4)
W = min(W, SIZE); H = min(H, SIZE)
u0, v0 = cu.min(), cv.min()
d_near = cs.max() + 64.0; d_range = (cs.max() - cs.min()) + 128.0
rowU = np.array([U[0] * scale, U[1] * scale, U[2] * scale, -u0 * scale])
rowV = np.array([V[0] * scale, V[1] * scale, V[2] * scale, -v0 * scale])
rowD = np.array([-sun[0] / d_range, -sun[1] / d_range, -sun[2] / d_range, d_near / d_range])
print("map %d x %d, %.2f units per texel, depth range %.0f units (%.2f units per step)" % (W, H, 1 / scale, d_range, d_range / 65535))

# ---- materials: who casts, and cutout alpha
script = ""
for f in glob.glob(os.path.join(game, "shaders", "*.shader")):
    script += open(f, encoding="latin1").read() + "\n"
blocks = {}
for m in re.finditer(r"^(\S+)\s*\n\{(.*?)^\}", script, re.S | re.M):
    blocks[m.group(1).lower()] = m.group(2)
alpha_maps = {}


def alpha_of(shader):
    """None for an opaque caster, or (h, w, bool array) for a cutout material."""
    body = blocks.get(shader.lower())
    if body is None or "alphafunc" not in body.lower():
        return None
    mm = re.search(r"^\s*map\s+(\S+)", body, re.M | re.I)
    if not mm:
        return None
    tex = mm.group(1)
    if tex in alpha_maps:
        return alpha_maps[tex]
    res = None
    for ext in (".png", ".tga", ".jpg"):
        p = os.path.join(game, os.path.splitext(tex)[0] + ext)
        if os.path.exists(p):
            from PIL import Image
            im = Image.open(p)
            if im.mode in ("RGBA", "LA"):
                a = im.getchannel("A")
                if max(a.size) > 1024:
                    a = a.resize((max(1, a.size[0] * 1024 // max(a.size)), max(1, a.size[1] * 1024 // max(a.size))), Image.BILINEAR)
                res = np.asarray(a) >= 128
            break
    alpha_maps[tex] = res
    return res


casts = np.zeros(nmat, bool); cut = [None] * nmat
for i in range(nmat):
    fl = int(mats["flags"][i]); name = mats["shader"][i].split(b"\0")[0].decode("latin1")
    if (fl & 1) or ((fl >> 1) & 7) == 1 or ((fl >> 8) & 255):       # blended, water, or partly transparent
        continue
    casts[i] = True; cut[i] = alpha_of(name)
print("materials %d, casting %d, of those cutout with an alpha map %d" % (nmat, casts.sum(), sum(c is not None for c in cut)))

# ---- splat
depth = np.full(H * W, np.float32(2.0))
BUCKETS = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 4096, 8192, 16384]
lattice = {}


def lat(n):
    if n not in lattice:
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
        k = (i + j) <= n
        a_, b_ = i[k] / n, j[k] / n
        if n == 1:                                           # corners and centre
            a_ = np.append(a_, 1 / 3); b_ = np.append(b_, 1 / 3)
        lattice[n] = np.stack([1 - a_ - b_, a_, b_], 1).astype(np.float32)
    return lattice[n]


n_samples = 0; n_tris = 0; n_cut = 0


def splat(P3, UV, amap):
    """P3 (T,3,3) sun-space corners (u texels, v texels, depth 0..1); UV (T,3,2) or None."""
    global n_samples, n_tris, n_cut
    mn = P3[:, :, :2].min(1); mx = P3[:, :, :2].max(1)
    k = (mx[:, 0] >= 0) & (mx[:, 1] >= 0) & (mn[:, 0] < W) & (mn[:, 1] < H)
    if not k.any():
        return
    P3 = P3[k]; UV = UV[k] if UV is not None else None
    e = np.stack([P3[:, 1, :2] - P3[:, 0, :2], P3[:, 2, :2] - P3[:, 1, :2], P3[:, 0, :2] - P3[:, 2, :2]], 1)
    L = np.sqrt((e ** 2).sum(2)).max(1)
    need = np.maximum(np.ceil(L / STEP), 1)
    bi = np.searchsorted(BUCKETS, need)
    n_tris += len(P3)
    for b in np.unique(bi):
        sel = np.flatnonzero(bi == b)
        B = lat(BUCKETS[min(b, len(BUCKETS) - 1)])
        per = max(1, 3000000 // len(B))
        for s0 in range(0, len(sel), per):
            ss = sel[s0:s0 + per]
            S = np.einsum("kc,tcx->tkx", B, P3[ss]).reshape(-1, 3)
            keep = None
            if amap is not None:
                T = np.einsum("kc,tcx->tkx", B, UV[ss]).reshape(-1, 2)
                ah, aw = amap.shape
                tx = np.floor((T[:, 0] % 1.0) * aw).astype(np.int64) % aw; ty = np.floor((T[:, 1] % 1.0) * ah).astype(np.int64) % ah
                keep = amap[ty, tx]
                n_cut += int((~keep).sum())
            x = np.floor(S[:, 0]).astype(np.int64); y = np.floor(S[:, 1]).astype(np.int64)
            ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
            if keep is not None:
                ok &= keep
            idx = y[ok] * W + x[ok]
            np.minimum.at(depth, idx, S[ok, 2])
            n_samples += int(ok.sum())


R4 = np.stack([rowU, rowV, rowD]).astype(np.float64)        # (3,4)
n_small = 0
last = time.time()
for ii in range(ninst):
    inst = insts[ii]; me = meshes[inst["mesh"]]
    M = inst["m"].reshape(3, 4).astype(np.float64)
    # placement sphere against the map rectangle
    c4 = np.append(inst["c"].astype(np.float64), 1.0); cu_, cv_ = R4[0] @ c4, R4[1] @ c4; rr = float(inst["r"]) * scale
    if cu_ + rr < 0 or cv_ + rr < 0 or cu_ - rr > W or cv_ - rr > H:
        continue
    if float(inst["r"]) < MIN_R:
        n_small += 1; continue
    T34 = R4[:, :3] @ M[:, :3]; T4 = R4[:, :3] @ M[:, 3] + R4[:, 3]
    vx = verts["xyz"][me["fv"]:me["fv"] + me["nv"]].astype(np.float64)
    sv = (vx @ T34.T + T4).astype(np.float32)               # all mesh corners in sun space
    for s in range(int(me["lfs"][0]), int(me["lfs"][0]) + int(me["lns"][0])):
        sb = subs[s]
        if not casts[sb["mat"]] or sb["ni"] == 0:
            continue
        ix = indexes[me["fi"] + sb["fi"]:me["fi"] + sb["fi"] + sb["ni"]].reshape(-1, 3).astype(np.int64)
        am = cut[sb["mat"]]
        uv = verts["st"][me["fv"]:me["fv"] + me["nv"]][ix] if am is not None else None
        splat(sv[ix], uv, am)
    if time.time() - last > 30:
        last = time.time(); print("  placement %d of %d, %d M samples, %.0f s" % (ii, ninst, n_samples // 1000000, time.time() - t0), flush=True)
depth = depth.reshape(H, W)
print("triangles %d, samples %d M (cut away by alpha %d M)   %.0f s" % (n_tris, n_samples // 1000000, n_cut // 1000000, time.time() - t0))

# ---- close isolated pinholes: a texel deeper than all eight neighbours takes the deepest neighbour
pad = np.pad(depth, 1, mode="edge")
nb_max = np.full_like(depth, -1.0)
for dy in (0, 1, 2):
    for dx in (0, 1, 2):
        if dy == 1 and dx == 1:
            continue
        np.maximum(nb_max, pad[dy:dy + H, dx:dx + W], out=nb_max)
hole = depth > nb_max + (2.0 / 65535)
depth[hole] = nb_max[hole]
del pad, nb_max
covered = depth <= 1.0
print("texels covered %.1f %%, pinholes closed %d" % (100.0 * covered.mean(), int(hole.sum())))
d16 = np.where(covered, np.clip(np.round(depth * 65535.0), 0, 65534), 65535).astype("<u2")

# ---- write DDS (DX10 header, DXGI_FORMAT_R16_UNORM = 56)
DDSD = 0x1 | 0x2 | 0x4 | 0x1000 | 0x8                        # caps, height, width, pixelformat, pitch
hdr = struct.pack("<4sIIIIIII", b"DDS ", 124, DDSD, H, W, W * 2, 0, 1) + b"\0" * 44
hdr += struct.pack("<II4sIIIII", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)       # pixel format: FOURCC DX10
hdr += struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)                        # caps: texture
hdr += struct.pack("<IIIII", 56, 3, 0, 1, 0)                            # R16_UNORM, 2D, no misc, array 1
assert len(hdr) == 148
out_dds = os.path.join(game, "maps", mapname + "_shadow.dds")
with open(out_dds, "wb") as f:
    f.write(hdr); f.write(d16.tobytes())

# ---- sidecar with the transform and a reduced copy (deepest value of each block: errs towards "lit")
fy = max(1, H // LOW); fx = max(1, W // LOW)
lh, lw = H // fy, W // fx
low = d16[:lh * fy, :lw * fx].reshape(lh, fy, lw, fx).max(axis=(1, 3))
out_side = os.path.join(game, "maps", mapname + ".tshadow")
with open(out_side, "wb") as f:
    f.write(struct.pack("<4sIIIII", b"TSHD", 1, W, H, lw, lh))
    f.write(struct.pack("<12f", *rowU, *rowV, *rowD))
    f.write(struct.pack("<4f", 1.0 / scale, d_range, float(fx), float(fy)))
    f.write(low.astype("<u2").tobytes())
rep = {"seconds": round(time.time() - t0, 1), "width": W, "height": H, "units_per_texel": round(1 / scale, 3), "depth_range_units": round(d_range, 1),
       "triangles": int(n_tris), "samples_millions": n_samples // 1000000, "covered_percent": round(100.0 * float(covered.mean()), 1),
       "pinholes_closed": int(hole.sum()), "small_placements_skipped": int(n_small), "dds_bytes": os.path.getsize(out_dds), "cpu_copy": [int(lw), int(lh)]}
print(json.dumps(rep, indent=1))
