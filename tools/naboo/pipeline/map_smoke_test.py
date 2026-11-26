"""Smoke test: load every map of the test install with bots and record what happens.
  py map_smoke_test.py <out_dir> [--only name,name] [--bots 8] [--skip-done]
For each map (every maps/*.bsp in GameData/base and GameData/nicjk pk3 files, plus loose maps of devgame_naboo/nicjk
named in --extra) one client process is started as a listen server (+devmap), the bots are added, the game runs
for about 12 seconds, a screenshot is taken with the frame-rate counter on, and the client quits.
Recorded per map in <out_dir>/results.json: exit code (139 = crash, 124 = timeout), seconds, bots that entered,
lines with ERROR / dropped / overflow / exceeded from the log, and the screenshot name.
Only processes started here are stopped. Nothing is written into the game install."""
import sys, os, json, glob, zipfile, subprocess, time, shutil, re
R = r"E:\jedi academy modding archive\TaystJK_AI_Claude_Code_improvements"
D = os.path.join(R, "devgame_naboo"); GD = r"E:\jedi academy modding archive\Jedi Academy TaystJK_AI test\GameData"
out = sys.argv[1]; os.makedirs(os.path.join(out, "shots"), exist_ok=True)
arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
NB = int(arg("--bots", "8")); only = arg("--only"); extra = (arg("--extra", "naboo_theed") or "").split(",")
maps = {}
for d in ("base", "nicjk"):
    for p in sorted(glob.glob(os.path.join(GD, d, "*.pk3"))):
        try:
            z = zipfile.ZipFile(p)
        except Exception:
            continue
        for i in z.infolist():
            n = i.filename
            if n.lower().startswith("maps/") and n.lower().endswith(".bsp"):
                maps[n[5:-4].lower()] = {"pk3": d + "/" + os.path.basename(p), "mb": round(i.file_size / 1048576.0, 1)}
for e in extra:
    if e and os.path.exists(os.path.join(D, "nicjk", "maps", e + ".bsp")):
        maps[e] = {"pk3": "(loose, devgame_naboo)", "mb": round(os.path.getsize(os.path.join(D, "nicjk", "maps", e + ".bsp")) / 1048576.0, 1)}
names = sorted(maps, key=lambda n: (maps[n]["mb"] > 200, n))
if only:
    names = [n for n in names if n in only.lower().split(",")]
bots = [l for l in open(os.path.join(D, "nicjk", "naboo_bots_user31.cfg")).read().splitlines() if l.startswith("addbot")][:NB]
open(os.path.join(D, "nicjk", "smoke.cfg"), "w").write(
    'set sm1 "' + "; wait 12; ".join(bots) + '; wait 2400; cg_drawFPS 1; cg_draw2D 1; ui_openmenu none_x; wait 200; ui_openmenu none_x; wait 5; screenshot; wait 200; quit"\n'
    'set smgo "com_maxfps 125; wait 700; team f; wait 300; god; vstr sm1"\nvstr smgo\n')
rp = os.path.join(out, "results.json")
res = json.load(open(rp)) if os.path.exists(rp) and "--skip-done" in sys.argv else {}
BAD = re.compile(r"ERROR|Hunk_Alloc.* failed|overflow|exceeded|MAX_[A-Z_]+ hit|dropped|couldn't load|Couldn't load", re.I)
IGN = re.compile(r"PlayerChoice|Can't find|cvar|sound|\.wav|\.mp3|shader .* has|route data", re.I)
for k, name in enumerate(names):
    if name in res:
        continue
    sd = os.path.join(D, "nicjk", "screenshots")
    for f in glob.glob(os.path.join(sd, "*.jpg")): os.remove(f)
    lg = os.path.join(D, "nicjk", "qconsole.log")
    if os.path.exists(lg): os.remove(lg)
    t0 = time.time(); to = 900 if maps[name]["mb"] > 200 else 240
    cmd = [os.path.join(D, "nicjk.x86_64.exe"), "+set", "fs_basepath", GD, "+set", "fs_homepath", D, "+set", "fs_game", "nicjk", "+set", "cl_renderer", "rd-vulkant",
           "+set", "r_mode", "-1", "+set", "r_fullscreen", "0", "+set", "r_customwidth", "1280", "+set", "r_customheight", "720", "+set", "net_port", "29181",
           "+set", "logfile", "2", "+set", "g_gametype", "0", "+set", "bot_minplayers", "0", "+devmap", name, "+exec", "smoke.cfg"]
    try:
        p = subprocess.run(cmd, cwd=D, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=to); code = p.returncode
    except subprocess.TimeoutExpired:
        code = 124
        subprocess.run(["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'nicjk*' -and $_.ExecutablePath -like '*devgame_naboo*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"])
    log = open(lg, errors="replace").read() if os.path.exists(lg) else ""
    shots = sorted(glob.glob(os.path.join(sd, "*.jpg"))); sn = None
    if shots:
        sn = re.sub(r"[^a-z0-9_]+", "_", name) + ".jpg"; shutil.copy(shots[-1], os.path.join(out, "shots", sn))
    bad = sorted({l[20:160].strip() for l in log.splitlines() if BAD.search(l) and not IGN.search(l)})
    res[name] = {"pk3": maps[name]["pk3"], "mb": maps[name]["mb"], "exit": code, "seconds": round(time.time() - t0, 1), "bots_entered": len(re.findall(r"entered the game", log)),
                 "loaded": ("CM_LoadMap( maps/" in log), "shot": sn, "log_lines": len(log.splitlines()), "flagged": bad[:12], "last_line": (log.strip().splitlines() or [""])[-1][20:160]}
    json.dump(res, open(rp, "w"), indent=1)
    print("%3d/%d %-34s exit=%s %5.0fs bots=%d shot=%s flagged=%d" % (k + 1, len(names), name, code, res[name]["seconds"], res[name]["bots_entered"], "y" if sn else "n", len(bad)), flush=True)
