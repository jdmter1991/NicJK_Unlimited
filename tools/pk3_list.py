"""List a PK3 (zip) archive: integrity, per-extension totals, largest files, maps."""
import sys, zipfile, collections, os

path = sys.argv[1]
print("file:", path, "size:", os.path.getsize(path))
with zipfile.ZipFile(path) as z:
    infos = z.infolist()
    print("entries:", len(infos))
    by_ext = collections.defaultdict(lambda: [0, 0, 0])
    by_top = collections.defaultdict(lambda: [0, 0, 0])
    for i in infos:
        if i.is_dir():
            continue
        ext = os.path.splitext(i.filename)[1].lower() or "(none)"
        e = by_ext[ext]; e[0] += 1; e[1] += i.file_size; e[2] += i.compress_size
        parts = i.filename.split("/")
        top = "/".join(parts[:2]) if len(parts) > 2 else parts[0] if len(parts) > 1 else "(root)"
        t = by_top[top]; t[0] += 1; t[1] += i.file_size; t[2] += i.compress_size
    print("\n== by extension (count, uncompressed, compressed)")
    for k, v in sorted(by_ext.items(), key=lambda kv: -kv[1][1]):
        print(f"{k:12} {v[0]:6} {v[1]:14,} {v[2]:14,}")
    print("\n== by top dirs")
    for k, v in sorted(by_top.items(), key=lambda kv: -kv[1][1])[:40]:
        print(f"{k:50} {v[0]:6} {v[1]:14,} {v[2]:14,}")
    print("\n== 25 largest")
    for i in sorted(infos, key=lambda i: -i.file_size)[:25]:
        print(f"{i.file_size:14,} {i.compress_size:14,} {i.filename}")
    print("\n== non-asset files (bsp/shader/cfg/txt/wnt/arena/bot/efx/etc.)")
    keep = {".bsp", ".shader", ".cfg", ".txt", ".wnt", ".arena", ".bot", ".efx", ".mtr", ".nav", ".str", ".menu", ".sab", ".npc", ".veh", ".map", ".srf", ".prt", ".lin", ".ent", ".dat", ".json", "(none)"}
    for i in infos:
        ext = os.path.splitext(i.filename)[1].lower() or "(none)"
        if not i.is_dir() and ext in keep:
            print(f"{i.file_size:14,} {i.filename}")
    if "--test" in sys.argv:
        bad = z.testzip()
        print("\nCRC test:", "OK" if bad is None else f"BAD: {bad}")
