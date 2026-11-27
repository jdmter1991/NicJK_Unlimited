"""Inclusive function shares from com_samples.log, restricted to in-game frames
(samples whose stack contains CG_DrawActiveFrame, RB_ExecuteRenderCommands or CL_Frame, excluding loading)."""
import sys, collections

samples = []
cur = None
for line in open(sys.argv[1], encoding="latin-1"):
    if line.startswith("---"):
        cur = []
        samples.append(cur)
    elif cur is not None and line.strip():
        cur.append(line.strip().split("!")[-1])
game = [s for s in samples if any(f in ("CL_Frame", "SV_Frame") for f in s)
        and not any(f in ("CL_ParseGamestate", "CL_InitCGame", "CL_Shutdown") for f in s)]
n = len(game)
print("in-game samples", n, "of", len(samples))
inc = collections.Counter()
selfc = collections.Counter()
for s in game:
    for f in set(s):
        inc[f] += 1
    selfc[s[0]] += 1
top = int(sys.argv[2]) if len(sys.argv) > 2 else 60
print("\ninclusive %:")
for f, c in inc.most_common(top):
    print(f"  {100.0 * c / n:5.1f}  {f}")
print("\nself %:")
for f, c in selfc.most_common(30):
    print(f"  {100.0 * c / n:5.1f}  {f}")
