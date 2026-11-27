"""Test file for the 64-bit map loader: a copy of a BSP with padding after its header, so the file is over 2 GB and
every lump starts past 2 GB (the positions are written as unsigned 32-bit values, which an old build reads as negative).
The map itself is unchanged: the same lumps, only further into the file.
  py make_big_bsp_test.py <in.bsp> <out.bsp> [padding_gb]
padding_gb defaults to 2.3. Lump positions must stay below 4 GB, so padding plus the map must be under 4 GB."""
import struct
import sys

src, dst = sys.argv[1], sys.argv[2]
pad = int(float(sys.argv[3]) * (1 << 30)) if len(sys.argv) > 3 else int(2.3 * (1 << 30))
pad -= pad % 4                                  # keep lump data 4-byte aligned
data = open(src, 'rb').read()
ident, version = struct.unpack_from('<4si', data, 0)
nlumps = 18                                     # Raven BSP (RBSP, version 1): 18 lumps
hdr = 8 + nlumps * 8
lumps = [struct.unpack_from('<II', data, 8 + 8 * i) for i in range(nlumps)]
if max(o + l for o, l in lumps) + pad >= 1 << 32:
    sys.exit('padding too large: lumps would end past 4 GB')
out = bytearray(data[:hdr])
for i, (o, l) in enumerate(lumps):
    struct.pack_into('<II', out, 8 + 8 * i, (o + pad) if l else o, l)
with open(dst, 'wb') as f:
    f.write(out)
    chunk = bytes(64 << 20)
    left = pad
    while left:
        n = min(left, len(chunk))
        f.write(chunk[:n])
        left -= n
    f.write(data[hdr:])
total = hdr + pad + len(data) - hdr
print('%s %s version %d: %d bytes -> %s %d bytes (%.2f GB), first lump at %d' % (
    src, ident.decode('latin-1'), version, len(data), dst, total, total / (1 << 30), min(o for o, l in lumps if l) + pad))
