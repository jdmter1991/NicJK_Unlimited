#!/usr/bin/env python3
"""
gla_append.py - build a per-model GLA for NicJK per-model-anims-config.cfg

Appends the animation frames of one or more GLA files to a base GLA
(normally models/players/_humanoid/_humanoid.gla). All files must have the
same skeleton (same bones, same order, same parents); the script refuses
otherwise. The base frames stay at the same frame numbers, so the stock
_humanoid animation.cfg still describes the result and stock clients play the
normal animations on it. The appended frames start at the offsets printed
at the end; give those to "animset" lines in per-model-anims-config.cfg.

Usage:
  python gla_append.py OUT.gla INTERNAL_NAME BASE.gla EXTRA1.gla [EXTRA2.gla ...]

  INTERNAL_NAME is the name stored in the GLA header, normally the path the
  file will have in the game without extension, e.g.
  models/players/_humanoid/_sith  (keep it under models/players/_humanoid/:
  the game only accepts player models whose GLA is in that folder).

A source can be "path/inside.pk3::models/players/x/x.gla" to read it from a
pk3 without extracting it. Nothing is ever written except OUT.gla.

GLA (MDXA version 6) layout: 100-byte header, bone offset table, bones,
frames (numFrames * numBones * 3-byte little-endian indices into the
compressed-bone pool), 4-byte alignment, then the pool (14 bytes per bone).
"""
import struct
import sys
import zipfile

HEADER = 100
COMP = 14


def read_source(spec):
    if "::" in spec:
        pk3, inner = spec.split("::", 1)
        with zipfile.ZipFile(pk3) as z:
            return z.read(inner)
    with open(spec, "rb") as f:
        return f.read()


def parse(data, label):
    ident, ver = struct.unpack_from("<4si", data, 0)
    if ident != b"2LGA" or ver != 6:
        sys.exit(f"{label}: not a version 6 GLA ({ident!r} {ver})")
    _scale, n_frames, ofs_frames, n_bones, ofs_pool, ofs_skel, ofs_end = struct.unpack_from("<f6i", data, 72)
    offsets = struct.unpack_from(f"<{n_bones}i", data, HEADER)
    bones = []
    for o in offsets:
        p = HEADER + o
        name = data[p:p + 64].split(b"\0")[0].decode("latin-1")
        _flags, parent = struct.unpack_from("<Ii", data, p + 64)
        bones.append((name.lower(), parent))
    return {
        "data": data, "frames": n_frames, "ofs_frames": ofs_frames, "bones": n_bones,
        "ofs_pool": ofs_pool, "ofs_skel": ofs_skel, "ofs_end": ofs_end, "skel": bones,
        "pool_count": (ofs_end - ofs_pool) // COMP,
    }


def frame_indices(g):
    """All frame indices as a flat list of ints."""
    raw = g["data"][g["ofs_frames"]:g["ofs_frames"] + g["frames"] * g["bones"] * 3]
    return [raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16) for i in range(0, len(raw), 3)]


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    out_path, internal_name, base_spec, extra_specs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    if len(internal_name) >= 64:
        sys.exit("INTERNAL_NAME must be shorter than 64 characters")

    base = parse(read_source(base_spec), base_spec)
    extras = [(s, parse(read_source(s), s)) for s in extra_specs]
    for spec, g in extras:
        if g["skel"] != base["skel"]:
            sys.exit(f"{spec}: skeleton differs from {base_spec} ({g['bones']} vs {base['bones']} bones); not appending")

    indices = frame_indices(base)
    pools = [base["data"][base["ofs_pool"]:base["ofs_end"]]]
    pool_total = base["pool_count"]
    frame_total = base["frames"]
    report = []
    for spec, g in extras:
        report.append((spec, frame_total, g["frames"]))
        indices.extend(i + pool_total for i in frame_indices(g))
        pools.append(g["data"][g["ofs_pool"]:g["ofs_end"]])
        pool_total += g["pool_count"]
        frame_total += g["frames"]

    if pool_total >= 1 << 24:
        sys.exit("compressed-bone pool too large for 3-byte indices")
    if frame_total > 65535:
        sys.exit(f"{frame_total} frames; the game's animation table holds at most 65535")

    # header + skeleton are copied from the base unchanged (same skeleton)
    head_and_skel = bytearray(base["data"][:base["ofs_frames"]])
    frames_blob = bytearray()
    for i in indices:
        frames_blob += bytes((i & 0xFF, (i >> 8) & 0xFF, (i >> 16) & 0xFF))
    ofs_pool = base["ofs_frames"] + len(frames_blob)
    pad = (-ofs_pool) % 4
    ofs_pool += pad
    pool_blob = b"".join(pools)
    ofs_end = ofs_pool + len(pool_blob)

    name_bytes = internal_name.encode("latin-1")
    head_and_skel[8:72] = name_bytes + b"\0" * (64 - len(name_bytes))
    struct.pack_into("<i", head_and_skel, 76, frame_total)
    struct.pack_into("<i", head_and_skel, 88, ofs_pool)
    struct.pack_into("<i", head_and_skel, 96, ofs_end)

    with open(out_path, "wb") as f:
        f.write(head_and_skel)
        f.write(frames_blob)
        f.write(b"\0" * pad)
        f.write(pool_blob)

    print(f"wrote {out_path}: {frame_total} frames, {base['bones']} bones, {ofs_end} bytes")
    print(f"  base {base_spec}: frames 0..{base['frames'] - 1}")
    for spec, first, count in report:
        print(f"  {spec}: frames {first}..{first + count - 1}  ->  animset offset {first}")


if __name__ == "__main__":
    main()
