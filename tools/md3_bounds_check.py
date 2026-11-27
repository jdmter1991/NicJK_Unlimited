"""Check MD3 frame bounds / radius in a PK3 against the actual vertex extents (frame 0)."""
import sys, zipfile, struct, math

z = zipfile.ZipFile(sys.argv[1])
used = None
if len(sys.argv) > 2:
    import re
    used = set(m.lower() for m in re.findall(r'"model2?"\s+"([^"]+\.md3)"', open(sys.argv[2], encoding="latin-1").read()))
bad_box = bad_sphere = total = 0
worst = []
for info in z.infolist():
    n = info.filename
    if not n.lower().endswith(".md3"):
        continue
    if used is not None and n.lower() not in used:
        continue
    d = z.read(n)
    ident, ver = struct.unpack_from("<4si", d, 0)
    if ident != b"IDP3":
        continue
    flags, nframes, ntags, nsurf, nskins, ofsFrames, ofsTags, ofsSurf, ofsEnd = struct.unpack_from("<9i", d, 72)
    bmin = struct.unpack_from("<3f", d, ofsFrames); bmax = struct.unpack_from("<3f", d, ofsFrames + 12)
    lorg = struct.unpack_from("<3f", d, ofsFrames + 24); radius = struct.unpack_from("<f", d, ofsFrames + 36)[0]
    vmin = [1e30] * 3; vmax = [-1e30] * 3
    maxr = 0.0
    o = ofsSurf
    for _ in range(nsurf):
        sid, sname, sflags, snf, snsh, snv, snt, oTri, oSh, oSt, oXyz, oEnd = struct.unpack_from("<4s64s10i", d, o)
        vs = struct.unpack_from("<%dh" % (snv * 4), d, o + oXyz)
        for i in range(snv):
            p = (vs[i * 4] / 64.0, vs[i * 4 + 1] / 64.0, vs[i * 4 + 2] / 64.0)
            for a in range(3):
                if p[a] < vmin[a]: vmin[a] = p[a]
                if p[a] > vmax[a]: vmax[a] = p[a]
            r = math.dist(p, lorg)
            if r > maxr: maxr = r
        o += oEnd
    total += 1
    box_err = max(max(bmin[a] - vmin[a], vmax[a] - bmax[a]) for a in range(3))   # >0: verts outside header box
    sph_err = maxr - radius                                                       # >0: verts outside header sphere
    if box_err > 1.0: bad_box += 1
    if sph_err > 1.0: bad_sphere += 1
    worst.append((max(box_err, sph_err), n, box_err, sph_err, radius, maxr, lorg))
print(f"models checked {total}; verts outside header box by >1 unit: {bad_box}; outside header sphere by >1 unit: {bad_sphere}")
for w in sorted(worst, reverse=True)[:12]:
    print(f"  {w[1]:60} box_err {w[2]:9.1f} sphere_err {w[3]:9.1f}  radius {w[4]:8.1f} needed {w[5]:8.1f}  localOrigin {tuple(round(x,1) for x in w[6])}")
