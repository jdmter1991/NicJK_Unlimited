"""Does the baked far-terrain texture show river where the water mesh is hidden by terrain?
  py river_texture_check.py <export_dir>
Reads dump/extras/terrain_far_bake.png (own PNG decoder: 8-bit RGB/RGBA, non-interlaced), the far terrain grid
and the 2 m water raster. Prints the colour statistics of the texture under visible water, under hidden water
and under dry land, and how much hidden water lies under river-coloured texture."""
import sys, os, zlib, struct
import numpy as np


def read_png(path):
    d = open(path, "rb").read()
    assert d[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8; idat = []; w = h = bd = ct = 0
    while pos < len(d):
        ln, typ = struct.unpack(">I4s", d[pos:pos + 8]); body = d[pos + 8:pos + 8 + ln]; pos += 12 + ln
        if typ == b"IHDR":
            w, h, bd, ct, _, _, il = struct.unpack(">IIBBBBB", body); assert bd == 8 and il == 0 and ct in (2, 6)
        elif typ == b"IDAT":
            idat.append(body)
    ch = 3 if ct == 2 else 4
    raw = np.frombuffer(zlib.decompress(b"".join(idat)), np.uint8).reshape(h, 1 + w * ch)
    out = np.zeros((h, w * ch), np.uint8); prev = np.zeros(w * ch, np.int32)
    for y in range(h):
        f = raw[y, 0]; line = raw[y, 1:].astype(np.int32)
        if f == 0:
            cur = line
        elif f == 2:
            cur = (line + prev) & 255
        elif f == 1:
            cur = line.copy()
            for c in range(ch):
                cur[c::ch] = np.cumsum(line[c::ch]) & 255
        else:
            cur = np.zeros(w * ch, np.int32)
            for i in range(w * ch):
                a = cur[i - ch] if i >= ch else 0; b = prev[i]; c = prev[i - ch] if i >= ch else 0
                if f == 3:
                    cur[i] = (line[i] + ((a + b) >> 1)) & 255
                else:
                    p = a + b - c; pa = abs(p - a); pb = abs(p - b); pc = abs(p - c)
                    pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    cur[i] = (line[i] + pr) & 255
        out[y] = cur; prev = cur
    return out.reshape(h, w, ch)[:, :, :3]


export_dir = sys.argv[1]; dump = os.path.join(export_dir, "dump")
far = np.load(os.path.join(dump, "extras", "terrain_far_grid.npz"))["grid"].astype(np.float64)
w_ = np.load(os.path.join(dump, "extras", "water_height.npz")); wr = w_["water"]; wx0 = float(w_["x0"]); wy0 = float(w_["y0"]); wc = float(w_["cell"])
img = read_png(os.path.join(dump, "extras", "terrain_far_bake.png")).astype(np.float32) / 255.0      # row 0 = top = high y
N = img.shape[0]
x0, y0 = far[0, 0, 0], far[0, 0, 1]; x1, y1 = far[-1, -1, 0], far[-1, -1, 1]


def tex(X, Y):
    u = np.clip(((X - x0) / (x1 - x0) * (N - 1)).round().astype(int), 0, N - 1)
    v = np.clip(((1 - (Y - y0) / (y1 - y0)) * (N - 1)).round().astype(int), 0, N - 1)
    return img[v, u]


def bil(g, X, Y):
    dx = g[0, 1, 0] - g[0, 0, 0]; dy = g[1, 0, 1] - g[0, 0, 1]
    fx = (X - g[0, 0, 0]) / dx; fy = (Y - g[0, 0, 1]) / dy
    ix = np.clip(np.floor(fx).astype(int), 0, g.shape[1] - 2); iy = np.clip(np.floor(fy).astype(int), 0, g.shape[0] - 2)
    tx = np.clip(fx - ix, 0, 1); ty = np.clip(fy - iy, 0, 1)
    return g[iy, ix, 2] * (1 - tx) * (1 - ty) + g[iy, ix + 1, 2] * tx * (1 - ty) + g[iy + 1, ix, 2] * (1 - tx) * ty + g[iy + 1, ix + 1, 2] * tx * ty


jj, ii = np.nonzero(~np.isnan(wr)); X = wx0 + ii * wc; Y = wy0 + jj * wc; wz = wr[jj, ii].astype(np.float64)
dep = wz - bil(far, X, Y)
c = tex(X, Y)
blue = c[:, 2] - c[:, 0]
for lab, m in (("visible water (depth > 0.5 m)", dep > 0.5), ("hidden water, 0..2 m under", (dep <= 0) & (dep > -2)), ("hidden water, 2..10 m under", (dep <= -2) & (dep > -10)), ("hidden water, deeper", dep <= -10)):
    if m.any():
        print("%-30s n=%7d  mean rgb %s  blue-red %.3f  share with blue-red > 0.03: %.1f %%" % (lab, m.sum(), c[m].mean(0).round(3), blue[m].mean(), 100 * (blue[m] > 0.03).mean()))
rng = np.random.default_rng(1); rx = rng.uniform(x0, x1, 200000); ry = rng.uniform(y0, y1, 200000)
ci = tex(rx, ry); kx = np.clip(np.rint((rx - wx0) / wc).astype(int), 0, wr.shape[1] - 1); ky = np.clip(np.rint((ry - wy0) / wc).astype(int), 0, wr.shape[0] - 1)
dry = np.isnan(wr[ky, kx])
print("%-30s n=%7d  mean rgb %s  blue-red %.3f  share with blue-red > 0.03: %.1f %%" % ("land without water mesh", dry.sum(), ci[dry].mean(0).round(3), (ci[dry, 2] - ci[dry, 0]).mean(), 100 * ((ci[dry, 2] - ci[dry, 0]) > 0.03).mean()))
