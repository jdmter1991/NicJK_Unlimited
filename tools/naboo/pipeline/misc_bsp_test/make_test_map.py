"""Test map for misc_bsp: a stock map with one more entity that loads a second BSP as a part.
  py make_test_map.py <game base dir> <out maps dir> [--fog]
Writes <out>/misc_test.bsp (mp/duel1 + misc_bsp "mp/duel1" at 4000 0 0); with --fog also a global fog entry
(fog lump with brushNum -1), the case that overflowed the fog array, as <out>/misc_test_fog.bsp."""
import sys, zipfile, struct, glob, os
base, out = sys.argv[1], sys.argv[2]; fog = "--fog" in sys.argv
b = None
for p in sorted(glob.glob(os.path.join(base, "assets*.pk3"))):
    z = zipfile.ZipFile(p)
    if "maps/mp/duel1.bsp" in z.namelist():
        b = bytearray(z.read("maps/mp/duel1.bsp")); break
o, l = struct.unpack_from("<ii", b, 8)
ent = bytes(b[o:o + l]).rstrip(b"\0") + b'\n{\n"classname" "misc_bsp"\n"bspmodel" "mp/duel1"\n"origin" "4000 0 0"\n}\n\0'
while len(b) % 4: b += b"\0"
struct.pack_into("<ii", b, 8, len(b), len(ent)); b += ent
name = "misc_test.bsp"
if fog:
    while len(b) % 4: b += b"\0"
    f = b"textures/fogs/fog".ljust(64, b"\0") + struct.pack("<ii", -1, 0)
    struct.pack_into("<ii", b, 8 + 8 * 12, len(b), len(f)); b += f
    name = "misc_test_fog.bsp"
open(os.path.join(out, name), "wb").write(b); print(name, len(b))
