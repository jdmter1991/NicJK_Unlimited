"""Numpy evaluator for the material expressions written by color_graphs.py.

A material's colour in the source is a formula over several images, constants and masks. This module evaluates such
a formula over a grid of texture coordinates (mesh UV space for objects, world XY for the terrain), in linear
light as Blender does, so the result can be stored as one texture.

Coordinates in UV space are kept as an affine map (u' = a*u + b, v' = c*v + d). A texture whose scale is not a
whole number is not periodic over the unit square and cannot be baked into it; so are textures projected from
world position or mapped with another UV set. Those contribute their mean value (reported per bake).
"""
import os, json
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


class Unsupported(Exception):
    pass


def srgb_to_linear(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, np.float32), 0.0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055).astype(np.float32)


class Images:
    """Lazy image store: RGBA float32, colour channels linearised when the source image is sRGB."""

    def __init__(self, dirs, info, max_cache=24):
        self.dirs = dirs; self.info = info; self.cache = {}; self.order = []; self.max_cache = max_cache; self.means = {}

    def path(self, name):
        stem = os.path.splitext(name)[0]
        for d in self.dirs:
            p = os.path.join(d, stem + ".png")
            if os.path.exists(p):
                return p
        return None

    def get(self, name):
        if name in self.cache:
            return self.cache[name]
        p = self.path(name)
        if p is None:
            raise Unsupported("image not exported: %s" % name)
        im = Image.open(p)
        if im.mode in ("I;16", "I", "F"):
            a = np.asarray(im, np.float32) / 65535.0
            a = np.stack([a, a, a, np.ones_like(a)], -1)
        else:
            a = np.asarray(im.convert("RGBA"), np.float32) / 255.0
        cs = (self.info.get(name) or {}).get("colorspace", "sRGB")
        if cs == "sRGB":
            a = a.copy(); a[:, :, :3] = srgb_to_linear(a[:, :, :3])
        self.cache[name] = a; self.order.append(name)
        while len(self.order) > self.max_cache:
            self.cache.pop(self.order.pop(0), None)
        return a

    def mean(self, name):
        if name not in self.means:
            a = self.get(name)
            self.means[name] = a.reshape(-1, 4).mean(0)
        return self.means[name]


CH = {"Red": 0, "Green": 1, "Blue": 2, "Alpha": 3, "R": 0, "G": 1, "B": 2, "X": 0, "Y": 1, "Z": 2}


class Evaluator:
    """mode 'uv': grid over the unit square of the material's own UV set (`primary_uv`);
    mode 'world': grid over world X, Y in metres (terrain), normal straight up."""

    def __init__(self, images, U, V, mode="uv", primary_uv="UV0", override=None, normal=(0.7071, 0.7071, 0.0)):
        self.im = images; self.U = U; self.V = V; self.mode = mode; self.primary_uv = primary_uv
        self.override = override or {}          # (image, scale tuple) -> RGBA constant
        self.normal = normal; self.memo = {}; self.approx = set(); self.samples = {}; self.snapped = set(); self.period = 1.0

    # ---- coordinates
    def coord(self, c):
        """returns ('affine', a, b, c, d) in uv mode, ('grid', X, Y) in world mode, or None"""
        k = c[0]
        if k == "default":
            return self._base()
        if k == "uv":
            name = c[1] or "UV0"
            if self.mode == "uv" and name == self.primary_uv:
                return self._base()
            return None
        if k == "texcoord":
            if c[1] == "UV":
                return self._base() if self.mode == "uv" and self.primary_uv == "UV0" else None
            if c[1] in ("Object", "Generated") and self.mode == "world":
                return self._base()
            return None
        if k == "geo":
            if c[1] == "Position" and self.mode == "world":
                return self._base()
            return None
        if k == "mapping":
            scale, loc, rot, vtype, inner = c[1], c[2], c[3], c[4], c[5]
            b = self.coord(inner)
            if b is None:
                return None
            if rot and any(abs(r) > 1e-5 for r in rot):
                return None
            lx, ly = (0.0, 0.0) if loc == "linked" or loc is None else (loc[0], loc[1])
            if vtype == "TEXTURE":
                return self._affine(b, 1.0 / scale[0], -lx / scale[0], 1.0 / scale[1], -ly / scale[1])
            return self._affine(b, scale[0], lx, scale[1], ly)
        if k == "combine":
            # coordinates computed per pixel (an atlas column chosen by a mask, for instance): sampled as a grid
            try:
                x = self.ev(c[1]); y = self.ev(c[2])
            except Unsupported:
                return None                 # cannot be computed here (world position in a UV bake): the caller uses the image's mean
            return ("grid", np.broadcast_to(x, self.U.shape), np.broadcast_to(y, self.U.shape))
        if k == "vmath":
            op = c[1]
            b = self.coord(c[2])
            if b is None:
                return None
            if op in ("SCALE",):
                s = float(np.mean(self.ev(c[-1])))
                return self._affine(b, s, 0.0, s, 0.0)
            if op in ("MULTIPLY", "ADD", "SUBTRACT") and c[3][0] == "const" and c[3][1] is not None:
                v = c[3][1]
                if op == "MULTIPLY":
                    return self._affine(b, v[0], 0.0, v[1], 0.0)
                sgn = 1.0 if op == "ADD" else -1.0
                return self._affine(b, 1.0, sgn * v[0], 1.0, sgn * v[1])
            return None
        return None

    def _base(self):
        return ("affine", 1.0, 0.0, 1.0, 0.0)          # of the grid: mesh UV in uv mode, world x, y in world mode

    @staticmethod
    def _affine(b, sx, ox, sy, oy):
        if b[0] == "affine":
            return ("affine", b[1] * sx, b[2] * sx + ox, b[3] * sy, b[4] * sy + oy)
        return ("grid", b[1] * sx + ox, b[2] * sy + oy)

    # ---- textures
    def tex(self, e):
        name, sock, c = e[1], e[2], e[3]
        if name is None:
            raise Unsupported("texture node without image")
        co = self.coord(c)
        scale_key = None
        if self.mode == "world" and (name, None) in self.override:
            return self._pick(np.asarray(self.override[(name, None)], np.float32), sock)
        if co is not None and co[0] == "affine" and self.mode == "uv":
            scale_key = (round(co[1], 4), round(co[3], 4))
            if (name, scale_key) in self.override:
                return self._pick(np.asarray(self.override[(name, scale_key)], np.float32), sock)
            # the grid covers `period` UV units: a texture fits when it repeats a whole number of times over that
            # span. One that misses a whole number by less than 4 % (a large-scale dirt map at 1.095) is stretched
            # to the nearest whole number; anything else cannot tile in the baked map and is replaced by its mean.
            P_ = float(getattr(self, "period", 1.0))
            su, sv = co[1] * P_, co[3] * P_
            if round(su) == 0 or round(sv) == 0:
                co = None
            elif abs(su - round(su)) > 0.01 or abs(sv - round(sv)) > 0.01:
                if abs(su - round(su)) < 0.04 * abs(su) and abs(sv - round(sv)) < 0.04 * abs(sv):
                    co = ("affine", round(su) / P_, co[2], round(sv) / P_, co[4]); self.snapped.add(name)
                else:
                    co = None
        if co is None:
            self.approx.add(name)
            return self._pick(self.im.mean(name), sock)
        if co[0] == "affine":
            ck = (name, co)
            if ck not in self.samples:             # one bilinear lookup per image and mapping, shared by all channels
                self.samples[ck] = self._sample(self.im.get(name), self.U * co[1] + co[2], self.V * co[3] + co[4])
            return self._pick(self.samples[ck], sock)
        return self._pick(self._sample(self.im.get(name), co[1], co[2]), sock)

    @staticmethod
    def _pick(a, sock):
        if sock == "Color":
            return a[..., :3]
        return a[..., CH[sock]]

    @staticmethod
    def _sample(img, u, v):
        h, w = img.shape[:2]
        x = (u % 1.0) * w - 0.5; y = (1.0 - (v % 1.0)) * h - 0.5          # Blender V runs bottom-up
        x0 = np.floor(x).astype(np.int64); y0 = np.floor(y).astype(np.int64)
        fx = (x - x0).astype(np.float32)[..., None]; fy = (y - y0).astype(np.float32)[..., None]
        x1 = (x0 + 1) % w; y1 = (y0 + 1) % h; x0 %= w; y0 %= h
        return (img[y0, x0] * (1 - fx) + img[y0, x1] * fx) * (1 - fy) + (img[y1, x0] * (1 - fx) + img[y1, x1] * fx) * fy

    # ---- expressions
    def ev(self, e):
        if e is None:
            raise Unsupported("missing input")
        key = id(e)
        if key in self.memo:
            return self.memo[key]
        r = self._ev(e)
        self.memo[key] = r
        return r

    @staticmethod
    def _c3(x):
        x = np.asarray(x, np.float32)
        return x if (x.ndim >= 1 and x.shape[-1] == 3) else x[..., None]

    def _ev(self, e):
        k = e[0]
        if k == "const":
            v = e[1]
            if v is None:
                raise Unsupported("constant without value")
            v = np.asarray(v, np.float32)
            return v[:3] if v.ndim == 1 and v.shape[0] >= 3 else (v[0] if v.ndim == 1 else v)
        if k == "tex":
            return self.tex(e)
        if k == "mix":
            bt, fac, a, b, clamp_res = e[1], e[2], e[3], e[4], e[5]
            f = np.clip(np.asarray(self.ev(fac), np.float32), 0.0, 1.0)
            A = self._c3(self.ev(a)); B = self._c3(self.ev(b))
            if f.ndim and f.shape[-1] != 3:
                f = f[..., None]
            if bt == "MIX":
                r = A + (B - A) * f
            elif bt == "MULTIPLY":
                r = A * (1 - f) + A * B * f
            elif bt == "ADD":
                r = A + B * f
            elif bt == "SUBTRACT":
                r = A - B * f
            elif bt == "SCREEN":
                r = 1 - (1 - f + f * (1 - B)) * (1 - A)
            elif bt == "OVERLAY":
                r = np.where(A < 0.5, A * (1 - f + 2 * f * B), 1 - (1 - f + 2 * f * (1 - B)) * (1 - A))
            elif bt == "DARKEN":
                r = A * (1 - f) + np.minimum(A, B) * f
            elif bt == "LIGHTEN":
                r = A * (1 - f) + np.maximum(A, B) * f
            elif bt == "DIVIDE":
                r = A * (1 - f) + f * A / np.maximum(B, 1e-6)
            else:
                raise Unsupported("mix type " + bt)
            if clamp_res:
                r = np.clip(r, 0, 1)
            return r if r.shape[-1] == 3 else r[..., 0]
        if k == "math":
            op, cl = e[1], e[2]
            a = [np.asarray(self.ev(x), np.float32) for x in e[3:]]
            if op == "ADD": r = a[0] + a[1]
            elif op == "SUBTRACT": r = a[0] - a[1]
            elif op == "MULTIPLY": r = a[0] * a[1]
            elif op == "DIVIDE": r = a[0] / np.where(np.abs(a[1]) < 1e-9, 1e-9, a[1])
            elif op == "MULTIPLY_ADD": r = a[0] * a[1] + a[2]
            elif op == "POWER": r = np.power(np.maximum(a[0], 0), a[1])
            elif op == "ROUND": r = np.floor(a[0] + 0.5)
            elif op == "MINIMUM": r = np.minimum(a[0], a[1])
            elif op == "MAXIMUM": r = np.maximum(a[0], a[1])
            elif op == "ABSOLUTE": r = np.abs(a[0])
            elif op == "SQRT": r = np.sqrt(np.maximum(a[0], 0))
            elif op == "LESS_THAN": r = (a[0] < a[1]).astype(np.float32)
            elif op == "GREATER_THAN": r = (a[0] > a[1]).astype(np.float32)
            elif op == "FLOOR": r = np.floor(a[0])
            elif op == "FRACT": r = a[0] - np.floor(a[0])
            elif op == "SMOOTH_MIN": r = np.minimum(a[0], a[1])
            elif op == "SMOOTH_MAX": r = np.maximum(a[0], a[1])
            else:
                raise Unsupported("math " + op)
            return np.clip(r, 0, 1) if cl else r
        if k == "vmath":
            op = e[1]
            a = [np.asarray(self.ev(x), np.float32) for x in e[2:]]
            if op == "SCALE": return self._c3(a[0]) * (a[-1][..., None] if a[-1].ndim else a[-1])
            if op == "ADD": return self._c3(a[0]) + self._c3(a[1])
            if op == "SUBTRACT": return self._c3(a[0]) - self._c3(a[1])
            if op == "MULTIPLY": return self._c3(a[0]) * self._c3(a[1])
            if op == "MULTIPLY_ADD": return self._c3(a[0]) * self._c3(a[1]) + self._c3(a[2])
            if op == "NORMALIZE":
                v = self._c3(a[0]); return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)
            raise Unsupported("vector math " + op)
        if k == "clamp":
            return np.clip(self.ev(e[1]), self.ev(e[2]), self.ev(e[3]))
        if k == "combine":
            p = [np.asarray(self.ev(x), np.float32) for x in e[1:4]]
            shp = np.broadcast_shapes(*[x.shape for x in p])
            return np.stack([np.broadcast_to(x, shp) for x in p], -1)
        if k == "sep":
            ch, inner = e[1], e[2]
            if inner[0] == "geo":
                if inner[1] == "Normal":
                    return np.float32(self.normal[CH[ch]])
                if inner[1] == "Position" and self.mode == "world":
                    return (self.U, self.V, np.float32(0.0))[CH[ch]]
                raise Unsupported("geometry " + inner[1])
            if inner[0] in ("mapping", "uv", "texcoord", "default"):
                # a component of a texture coordinate used as a number
                co = self.coord(inner)
                if co is None:
                    raise Unsupported("coordinate as value")
                if co[0] == "affine":
                    return (self.U * co[1] + co[2], self.V * co[3] + co[4], np.float32(0.0))[CH[ch]]
                return (co[1], co[2], np.float32(0.0))[CH[ch]]
            v = np.asarray(self.ev(inner), np.float32)
            return v[..., CH[ch]] if (v.ndim and v.shape[-1] == 3) else v
        if k == "geo":
            if e[1] == "Backfacing":
                return np.float32(0.0)
            if e[1] == "Normal":
                return np.asarray(self.normal, np.float32)
            raise Unsupported("geometry " + e[1])
        if k == "vcol":
            self.approx.add("vertex colour " + str(e[1]))
            return np.float32(1.0) if e[2] != "Color" else np.ones(3, np.float32)
        if k == "maprange":
            cl = e[1]; x, a, b, c, d = [np.asarray(self.ev(v), np.float32) for v in e[3:8]]
            t = (x - a) / np.where(np.abs(b - a) < 1e-9, 1e-9, b - a)
            if cl:
                t = np.clip(t, 0, 1)
            return c + (d - c) * t
        if k == "invert":
            f = np.asarray(self.ev(e[1]), np.float32); c = self._c3(self.ev(e[2]))
            return c + ((1 - c) - c) * (f[..., None] if f.ndim else f)
        if k == "gamma":
            return np.power(np.maximum(self._c3(self.ev(e[1])), 0), np.asarray(self.ev(e[2]), np.float32))
        raise Unsupported(str(k) + (":" + str(e[1]) if len(e) > 1 and isinstance(e[1], str) else ""))


def images_in(e, out=None, coords=False):
    """all ('tex', image, socket, coord) nodes of an expression"""
    out = [] if out is None else out
    if isinstance(e, (list, tuple)):
        if e and e[0] == "tex":
            out.append(e)
        for x in e:
            if isinstance(x, (list, tuple)):
                images_in(x, out)
    return out


def intern(e, table=None):
    """Turn a JSON expression into nested tuples in which equal subtrees are one object, so that the evaluator's
    memo (keyed by object identity) computes every distinct sub-expression once."""
    table = {} if table is None else table
    if isinstance(e, list):
        t = tuple(intern(x, table) for x in e)
        return table.setdefault(t, t)
    return e
