"""Entity-lump statistics for an RBSP. argv[1]=bsp, optional argv[2]=output .ent path."""
import sys, struct, re, collections

path = sys.argv[1]
with open(path, "rb") as f:
    f.seek(8)
    off, ln = struct.unpack("<ii", f.read(8))
    f.seek(off)
    text = f.read(ln).rstrip(b"\0").decode("latin-1")
if len(sys.argv) > 2:
    open(sys.argv[2], "w", encoding="latin-1", newline="").write(text)

ents = []
for block in re.findall(r"\{([^{}]*)\}", text):
    ents.append(dict(re.findall(r'"([^"]*)"\s+"([^"]*)"', block)))
print("entities", len(ents), "text bytes", ln)
cc = collections.Counter(e.get("classname", "?") for e in ents)
for k, v in cc.most_common():
    print(f"{v:6} {k}")

print("\nworldspawn:", {k: v for k, v in ents[0].items()})

def uniq(cls, key):
    return collections.Counter(e.get(key, "") for e in ents if e.get("classname") == cls)

for cls, key in (("misc_model_static", "model"), ("fx_runner", "fxFile"), ("target_speaker", "noise"), ("misc_model", "model")):
    u = uniq(cls, key)
    if u:
        print(f"\n{cls}: {sum(u.values())} instances, {len(u)} unique {key}; top:")
        for k, v in u.most_common(8):
            print(f"   {v:5} {k}")

bm = [e for e in ents if e.get("model", "").startswith("*")]
print("\nbrush-model entities:", len(bm), collections.Counter(e["classname"] for e in bm))
print("keys used per class (sample):")
seen = {}
for e in ents:
    c = e.get("classname")
    seen.setdefault(c, collections.Counter()).update(e.keys())
for c, ks in seen.items():
    print("  ", c, dict(ks))
for cls in ("func_door", "info_player_deathmatch", "fx_runner"):
    s = [e for e in ents if e.get("classname") == cls][:2]
    for e in s:
        print("sample", e)
