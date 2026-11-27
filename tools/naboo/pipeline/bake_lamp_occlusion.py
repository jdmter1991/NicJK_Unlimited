"""Bake which way each lamp's light can travel, so every lamp can be drawn at any distance without lighting through walls.
  py bake_lamp_occlusion.py <game_dir> <mapname> <export_dir> [--tile 64] [--near 24]
Reads  <game>/maps/<mapname>.tlights            lamps: position, radius, colour (8 floats each)
       <game>/maps/<mapname>_shadow.dds         the sun shadow map (R16_UNORM); the sun-only original is kept as
                                                <mapname>_shadow_sun.dds and is the input of every later run
       <export>/collision/collision_tris.npy    collision triangles (plus skirts.npy), the occluders
Writes <game>/maps/<mapname>_shadow.dds         the sun map with rows appended below it:
         rows S .. (S = sun map height): lamp parameters, two 2 x 2 blocks per lamp (W / 4 lamps per two rows): x + 32768, y + 32768, z + 32768 (units),
                                     radius (units), r, g, b times 16384, unused
         then: one tile x tile octahedral depth map per lamp, packed left to right, top to bottom:
                                     distance to the first occluder along that direction / radius (65535 = free)
       <game>/maps/<mapname>.tlampocc           "TLOC", version 3, lamps, tile, sun height, parameter row, first tile
                                                row, tiles per row (8 x uint32)
Rays start `near` units from the lamp so its own housing does not block it. The renderer (tr_tworld.cpp) lights every
placement with the lamps whose radius reaches it, tested against these maps; without the file it keeps the four
nearest lamps."""
import sys, os, struct, json, time, shutil
import numpy as np

t0 = time.time()
game, mapname, ed = sys.argv[1], sys.argv[2], sys.argv[3]
TILE = int(sys.argv[sys.argv.index("--tile") + 1]) if "--tile" in sys.argv else 64
NEAR = float(sys.argv[sys.argv.index("--near") + 1]) if "--near" in sys.argv else 24.0
md = os.path.join(game, "maps")
d = open(os.path.join(md, mapname + ".tlights"), "rb").read()
n = struct.unpack_from("<I", d, 8)[0]
LAMPS = np.frombuffer(d, dtype="<f4", count=n * 8, offset=12).reshape(-1, 8).astype(np.float64)
if n > 4095:
    sys.exit("more than 4095 lamps: the placement lists hold indices up to 4095")

# ---- the sun map (pristine copy)
sun_p = os.path.join(md, mapname + "_shadow_sun.dds"); cur_p = os.path.join(md, mapname + "_shadow.dds")
if not os.path.exists(sun_p):
    shutil.copyfile(cur_p, sun_p)
raw = open(sun_p, "rb").read()
H, W = struct.unpack_from("<II", raw, 12)
HDR = 4 + 124 + 20
assert raw[84:88] == b"DX10" and len(raw) == HDR + W * H * 2, "unexpected DDS layout"
sunmap = raw[HDR:]

# ---- occluders
T = np.load(os.path.join(ed, "collision", "collision_tris.npy")).astype(np.float64).reshape(-1, 3, 3)
sk = os.path.join(ed, "collision", "skirts.npy")
if os.path.exists(sk):
    T = np.concatenate([T, np.load(sk).astype(np.float64).reshape(-1, 3, 3)])
tmn = T.min(1); tmx = T.max(1)

# ---- octahedral directions of the tile's texel centres
u = (np.arange(TILE) + 0.5) / TILE * 2.0 - 1.0
UX, UY = np.meshgrid(u, u)                      # row = v (y), column = u (x)
z = 1.0 - np.abs(UX) - np.abs(UY)
x = np.where(z < 0, (1.0 - np.abs(UY)) * np.sign(UX), UX)
y = np.where(z < 0, (1.0 - np.abs(UX)) * np.sign(UY), UY)
DIR = np.stack([x, y, z], -1).reshape(-1, 3)
DIR /= np.linalg.norm(DIR, axis=1, keepdims=True)

tiles_per_row = W // TILE
tile_rows = (n + tiles_per_row - 1) // tiles_per_row
LPR = W // 4                                   # lamps per pair of parameter rows (4 texels wide, 2 high each)
param_rows = 2 * ((n + LPR - 1) // LPR)
extra = param_rows + tile_rows * TILE
img = np.full((extra, W), 65535, np.uint16)
blocked_share = []
for li in range(n):
    p = LAMPS[li, :3]; r = LAMPS[li, 3]
    # two 2 x 2 blocks per lamp, so the shader reads each with one gather: [x y / z radius] and [r g / b 0]
    pr, pc = 2 * (li // LPR), 4 * (li % LPR)
    blk = [(0, 0, p[0] + 32768), (0, 1, p[1] + 32768), (1, 0, p[2] + 32768), (1, 1, r),
           (0, 2, LAMPS[li, 4] * 16384), (0, 3, LAMPS[li, 5] * 16384), (1, 2, LAMPS[li, 6] * 16384), (1, 3, 0)]
    for dr_, dc_, v_ in blk:
        img[pr + dr_, pc + dc_] = int(np.clip(round(v_), 0, 65535))
    sel = np.flatnonzero((tmx[:, 0] >= p[0] - r) & (tmn[:, 0] <= p[0] + r) & (tmx[:, 1] >= p[1] - r) & (tmn[:, 1] <= p[1] + r)
                        & (tmx[:, 2] >= p[2] - r) & (tmn[:, 2] <= p[2] + r))
    best = np.full(len(DIR), r)
    for s in range(0, len(sel), 1500):
        A = T[sel[s:s + 1500], 0]; e1 = T[sel[s:s + 1500], 1] - A; e2 = T[sel[s:s + 1500], 2] - A
        h = np.cross(DIR[:, None, :], e2[None, :, :]); a = (e1[None, :, :] * h).sum(2)
        ok = np.abs(a) > 1e-9
        f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0)
        sv = p[None, None, :] - A[None, :, :]
        uu = f * (sv * h).sum(2)
        q = np.cross(sv, e1[None, :, :]); vv = f * (DIR[:, None, :] * q).sum(2); tt = f * (e2[None, :, :] * q).sum(2)
        hit = ok & (uu >= 0) & (uu <= 1) & (vv >= 0) & (uu + vv <= 1) & (tt > NEAR) & (tt < r)
        tt = np.where(hit, tt, np.inf)
        best = np.minimum(best, tt.min(1))
    dep = np.clip(best / r, 0.0, 1.0)
    blocked_share.append(float((dep < 0.999).mean()))
    tr, tc = divmod(li, tiles_per_row)
    img[param_rows + tr * TILE:param_rows + (tr + 1) * TILE, tc * TILE:(tc + 1) * TILE] = np.round(dep.reshape(TILE, TILE) * 65535).astype(np.uint16)
    if li % 50 == 0:
        print("lamp %d/%d, %d occluder triangles  %.0fs" % (li, n, len(sel), time.time() - t0))

H2 = H + extra
DDSD = 0x1 | 0x2 | 0x4 | 0x1000 | 0x8
hdr = struct.pack("<4sIIIIIII", b"DDS ", 124, DDSD, H2, W, W * 2, 0, 1) + b"\0" * 44
hdr += struct.pack("<II4sIIIII", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)
hdr += struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
hdr += struct.pack("<IIIII", 56, 3, 0, 1, 0)
with open(cur_p, "wb") as f:
    f.write(hdr); f.write(sunmap); f.write(img.astype("<u2").tobytes())
with open(os.path.join(md, mapname + ".tlampocc"), "wb") as f:
    f.write(struct.pack("<4s7I", b"TLOC", 3, n, TILE, H, H, H + param_rows, tiles_per_row))
rep = {"lamps": n, "tile": TILE, "sun_height": H, "width": W, "rows_added": extra, "mean_blocked_share": round(float(np.mean(blocked_share)), 3),
       "seconds": round(time.time() - t0, 1)}
json.dump(rep, open(os.path.join(md, mapname + "_lampocc.json"), "w"), indent=1)
print(json.dumps(rep))
