#!/usr/bin/env python3
"""
gla_build.py - combine animations into one humanoid GLA for NicJK

Starts from a GLA (normally the shared models/players/_humanoid/_humanoid.gla)
and appends chosen animations from other GLAs that have the humanoid bones
(any bone order: bones are matched by name, and their parents are checked).
The base frames keep their frame numbers, so the base animation.cfg stays
valid and stock clients keep working. Writes:

  OUT.gla        the combined GLA
  ADDED.cfg      the added animations in animation.cfg format, with their new
                 frame numbers (use it in animremap.cfg:
                 "animset NAME models/players/_humanoid/_humanoid.gla ADDED.cfg 0",
                 then per model "MODEL BOTH_x NAME:ADDED_ANIM")
  FULL.cfg       optional: the base animation.cfg with every added animation
                 whose new name is an animation.cfg name (BOTH_...) replacing
                 that entry - a global change for every model

Build file (one command per line, # or // comments):

  base   GLA [ANIMATION_CFG]            start from this GLA (and its cfg)
  from   GLA [ANIMATION_CFG]            following lines copy from this GLA
  anim   NAME [NEW_NAME]                copy NAME (from the "from" cfg); NEW_NAME
                                        defaults to NAME. Loop and speed come along.
  frames FIRST COUNT NEW_NAME [LOOP [FPS]]
                                        copy a raw frame range of the "from" GLA
  name   INTERNAL_NAME                  name stored in the GLA header (default: base's)
  out    OUT.gla ADDED.cfg [FULL.cfg]

GLA paths can point into a pk3: "C:/path/file.pk3::models/players/x/x.gla".
Relative paths are relative to the build file. Nothing but the out files is
written.

Usage: python gla_build.py BUILDFILE
"""
import os
import struct
import sys
import zipfile

HEADER = 100
COMP = 14
MAX_FRAMES = 65535          # animation tables store frame numbers in 16 bits


def tokens(line):
    """Whitespace-separated tokens; "double quotes" keep spaces; // or # outside quotes starts a comment."""
    out, cur, quoted, i = [], "", False, 0
    while i < len(line):
        c = line[i]
        if c == '"':
            quoted = not quoted
        elif not quoted and (c == "#" or line.startswith("//", i)):
            break
        elif not quoted and c.isspace():
            if cur:
                out.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    if cur:
        out.append(cur)
    return out


def read_source(spec, here):
    if "::" in spec:
        pk3, inner = spec.split("::", 1)
        if not os.path.isabs(pk3):
            pk3 = os.path.join(here, pk3)
        with zipfile.ZipFile(pk3) as z:
            for n in z.namelist():
                if n.lower() == inner.lower():
                    return z.read(n)
        sys.exit("%s: not in %s" % (inner, pk3))
    path = spec if os.path.isabs(spec) else os.path.join(here, spec)
    with open(path, "rb") as f:
        return f.read()


def parse_gla(data, label):
    ident, ver = struct.unpack_from("<4si", data, 0)
    if ident != b"2LGA" or ver != 6:
        sys.exit("%s: not a version 6 GLA" % label)
    _scale, n_frames, ofs_frames, n_bones, ofs_pool, ofs_skel, ofs_end = struct.unpack_from("<f6i", data, 72)
    offsets = struct.unpack_from("<%di" % n_bones, data, HEADER)
    names, parents, base = [], [], []
    for o in offsets:
        p = HEADER + o
        names.append(data[p:p + 64].split(b"\0")[0].decode("latin-1").lower())
        parents.append(struct.unpack_from("<i", data, p + 68)[0])
        base.append(struct.unpack_from("<12f", data, p + 72))
    return dict(data=data, frames=n_frames, ofs_frames=ofs_frames, bones=n_bones, ofs_pool=ofs_pool,
                ofs_end=ofs_end, names=names, parents=parents, base=base, label=label)


def comp_index(g, frame, bone):
    d = g["data"]
    o = g["ofs_frames"] + (frame * g["bones"] + bone) * 3
    return d[o] | (d[o + 1] << 8) | (d[o + 2] << 16)


def comp_bytes(g, index):
    p = g["ofs_pool"] + index * COMP
    return g["data"][p:p + COMP]


def read_cfg(spec, here):
    text = read_source(spec, here).decode("latin-1")
    anims = {}
    lines = text.splitlines()
    for line in lines:
        p = line.split()
        if len(p) >= 5 and not p[0].startswith("/"):
            try:
                anims[p[0].upper()] = (int(p[1]), int(p[2]), int(p[3]), p[4])
            except ValueError:
                pass
    return anims, lines


class Builder:
    def __init__(self, base, base_cfg):
        self.base = base
        self.base_cfg = base_cfg
        self.names = base["names"]
        # combined pool: base pool first (unchanged), then new entries
        self.pool = []
        self.pool_index = {}
        for i in range((base["ofs_end"] - base["ofs_pool"]) // COMP):
            b = comp_bytes(base, i)
            self.pool.append(b)
            self.pool_index.setdefault(b, i)
        self.frames_raw = bytearray(base["data"][base["ofs_frames"]:base["ofs_frames"] + base["frames"] * base["bones"] * 3])
        self.n_frames = base["frames"]
        self.added = []            # (name, first, count, loop, fps, source)

    def bone_order(self, src):
        if sorted(src["names"]) != sorted(self.names):
            sys.exit("%s: bones differ from the base (%d vs %d bones, or other names)" % (src["label"], src["bones"], len(self.names)))
        order = [src["names"].index(n) for n in self.names]
        for b, sb in enumerate(order):
            bp = self.base["parents"][b]
            sp = src["parents"][sb]
            if (self.names[bp] if bp >= 0 else None) != (src["names"][sp] if sp >= 0 else None):
                sys.exit("%s: bone %s has another parent than in the base" % (src["label"], self.names[b]))
        worst = max(max(abs(x - y) for x, y in zip(self.base["base"][b], src["base"][order[b]])) for b in range(len(order)))
        return order, worst

    def append(self, src, order, first, count, name, loop, fps):
        if first < 0 or count <= 0 or first + count > src["frames"]:
            sys.exit("%s: frames %d..%d outside the file's %d frames" % (src["label"], first, first + count - 1, src["frames"]))
        if self.n_frames + count > MAX_FRAMES:
            sys.exit("adding %s would make %d frames; the game's animation table holds at most %d" % (name, self.n_frames + count, MAX_FRAMES))
        start = self.n_frames
        for f in range(first, first + count):
            for b in range(len(self.names)):
                cb = comp_bytes(src, comp_index(src, f, order[b]))
                i = self.pool_index.get(cb)
                if i is None:
                    i = len(self.pool)
                    self.pool.append(cb)
                    self.pool_index[cb] = i
                self.frames_raw += bytes((i & 0xFF, (i >> 8) & 0xFF, (i >> 16) & 0xFF))
        self.n_frames += count
        self.added.append((name, start, count, loop, fps, src["label"]))

    def write(self, out_gla, internal_name):
        if len(self.pool) >= 1 << 24:
            sys.exit("compressed-bone pool too large")
        head = bytearray(self.base["data"][:self.base["ofs_frames"]])
        if internal_name:
            nb = internal_name.encode("latin-1")[:63]
            head[8:72] = nb + b"\0" * (64 - len(nb))
        ofs_pool = len(head) + len(self.frames_raw)
        pad = (-ofs_pool) % 4
        ofs_pool += pad
        ofs_end = ofs_pool + len(self.pool) * COMP
        struct.pack_into("<i", head, 76, self.n_frames)
        struct.pack_into("<i", head, 88, ofs_pool)
        struct.pack_into("<i", head, 96, ofs_end)
        with open(out_gla, "wb") as f:
            f.write(head)
            f.write(self.frames_raw)
            f.write(b"\0" * pad)
            for b in self.pool:
                f.write(b)
        return ofs_end


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    build = sys.argv[1]
    here = os.path.dirname(os.path.abspath(build))
    builder = None
    src = src_cfg = None
    order = None
    internal_name = None
    out = None

    for lineno, raw in enumerate(open(build, encoding="latin-1"), 1):
        tok = tokens(raw)
        if not tok:
            continue
        cmd = tok[0].lower()
        where = "%s line %d" % (os.path.basename(build), lineno)
        if cmd == "base":
            base = parse_gla(read_source(tok[1], here), tok[1])
            base_cfg = read_cfg(tok[2], here) if len(tok) > 2 else None
            builder = Builder(base, base_cfg)
            print("base %s: %d frames, %d bones" % (tok[1], base["frames"], base["bones"]))
        elif cmd == "from":
            if not builder:
                sys.exit("%s: 'from' before 'base'" % where)
            src = parse_gla(read_source(tok[1], here), tok[1])
            src_cfg = read_cfg(tok[2], here)[0] if len(tok) > 2 else None
            order, worst = builder.bone_order(src)
            print("from %s: %d frames%s" % (tok[1], src["frames"],
                  "" if worst < 0.01 else ", base pose differs by up to %.2f units (bones matched by name)" % worst))
        elif cmd == "anim":
            if not src_cfg:
                sys.exit("%s: 'anim' needs a 'from' with an animation.cfg" % where)
            name = tok[1].upper()
            if name not in src_cfg:
                sys.exit("%s: %s is not in the source animation.cfg" % (where, name))
            first, count, loop, fps = src_cfg[name]
            builder.append(src, order, first, count, tok[2] if len(tok) > 2 else name, loop, fps)
        elif cmd == "frames":
            if not src:
                sys.exit("%s: 'frames' before 'from'" % where)
            first, count, name = int(tok[1]), int(tok[2]), tok[3]
            loop = int(tok[4]) if len(tok) > 4 else -1
            fps = tok[5] if len(tok) > 5 else "20"
            builder.append(src, order, first, count, name, loop, fps)
        elif cmd == "name":
            internal_name = tok[1]
        elif cmd == "out":
            out = [t if os.path.isabs(t) else os.path.join(here, t) for t in tok[1:]]
        else:
            sys.exit("%s: unknown command %s" % (where, tok[0]))

    if not builder or not out or len(out) < 2:
        sys.exit("need 'base' and 'out OUT.gla ADDED.cfg [FULL.cfg]'")
    size = builder.write(out[0], internal_name)
    with open(out[1], "w", encoding="latin-1", newline="\n") as f:
        f.write("// added by gla_build.py to %s (frames are absolute in that GLA)\n" % os.path.basename(out[0]))
        f.write("// name  first  count  loop  fps    (source)\n")
        for name, first, count, loop, fps, label in builder.added:
            f.write("%-28s %6d %5d %4d %5s    // %s\n" % (name, first, count, loop, fps, label))
    if len(out) > 2:
        if not builder.base_cfg:
            sys.exit("FULL.cfg needs the base animation.cfg on the 'base' line")
        replaced = {n.upper(): (n, a, c, l, fps) for n, a, c, l, fps, _ in builder.added}
        lines_out, done = [], set()
        for line in builder.base_cfg[1]:
            p = line.split()
            key = p[0].upper() if p else ""
            if key in replaced and len(p) >= 5:
                n, a, c, l, fps = replaced[key]
                lines_out.append("%-28s %6d %5d %4d %5s    // gla_build (was: %s)" % (p[0], a, c, l, fps, " ".join(p[1:5])))
                done.add(key)
            else:
                lines_out.append(line)
        extra = [(n, a, c, l, fps) for n, a, c, l, fps, _ in builder.added if n.upper() not in done]
        if extra:
            lines_out.append("")
            lines_out.append("// added by gla_build.py (names the game does not know are ignored by it; use them through animremap animsets)")
            for n, a, c, l, fps in extra:
                lines_out.append("%-28s %6d %5d %4d %5s" % (n, a, c, l, fps))
        with open(out[2], "w", encoding="latin-1", newline="\n") as f:
            f.write("\n".join(lines_out) + "\n")

    print("wrote %s: %d frames (%d added), %d bytes" % (out[0], builder.n_frames, builder.n_frames - builder.base["frames"], size))
    for name, first, count, loop, fps, label in builder.added:
        print("  %-28s frames %d-%d" % (name, first, first + count - 1))


if __name__ == "__main__":
    main()
