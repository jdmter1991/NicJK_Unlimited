"""Summarize sv_hitch_stacks.log: which call chains the server was in during long frames."""
import sys, re, collections

samples = []
cur = None
for line in open(sys.argv[1], encoding="latin-1"):
    if line.startswith("---"):
        cur = []
        samples.append(cur)
    elif cur is not None and line.strip():
        cur.append(re.sub(r"\+0x[0-9a-f]+$", "", line.strip()))
depth = int(sys.argv[2]) if len(sys.argv) > 2 else 7
print("samples", len(samples))
c = collections.Counter()
for s in samples:
    # drop frames below the game/bot entry points to keep chains comparable
    cut = len(s)
    for i, fr in enumerate(s):
        if "SV_Frame" in fr or "Com_Frame" in fr:
            cut = i
            break
    chain = s[:cut][::-1]            # outermost -> innermost
    c[" > ".join(f.split("!")[-1] for f in chain[:depth])] += 1
for k, v in c.most_common(25):
    print(f"{v:5}  {k}")
print("\ninnermost frames:")
c2 = collections.Counter(s[0] for s in samples if s)
for k, v in c2.most_common(15):
    print(f"{v:5}  {k}")

