#!/bin/bash
# Long-play test from the Steam install: dedicated server + client, 31 bots, naboo_theed, about an hour.
#   steam_longplay.sh [minutes]          default 62
# * server and client run the Steam install's programs and data (fs_basepath), each with its own scratch home folder
#   under devgame_naboo, so nothing is written into the Steam install and no saved config there is changed
#   (the Steam nicjk.cfg is still read, as in a normal start);
# * timelimit 20: every 20 minutes the match ends, intermission, and "nextmap" loads naboo_theed again on the same
#   server and client processes, so model/image/sound caches and the hunk go through map reloads;
# * cheats on (devmap); the client spectates and follows the bots, switching to the next one every 10-20 s, with the
#   frame-rate counter on, uncapped, 1920 x 1080 window; r_tworldStats 1 logs frame rate and draw counts every second;
# * a game screenshot (the game's own picture, never the screen area) at every switch of the followed bot; after the
#   run the ones taken at the highest logged frame rates are copied to shots/best_<fps>fps_<time>.jpg;
# * memory (working set, private bytes) of both processes every 30 s -> memory.csv.
# Only processes whose command line holds this run's home folders are stopped.
MIN=${1:-62}
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"
G="/b/SteamLibrary/steamapps/common/Jedi Academy/GameData"
OUT="$R/naboo/longplay/$(date +%Y%m%d_%H%M)"; mkdir -p "$OUT/shots"
HS="$R/devgame_naboo/steamlong_srv"; HC="$R/devgame_naboo/steamlong_cli"
rm -rf "$HS" "$HC"; mkdir -p "$HS/nicjk" "$HC/nicjk"
GW=$(cygpath -w "$G"); HSW=$(cygpath -w "$HS"); HCW=$(cygpath -w "$HC")
stop_mine() { powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*steamlong_*' -and (\$_.Name -like 'nicjk*' -or \$_.Name -eq 'powershell.exe') -and \$_.ProcessId -ne \$PID } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null; }

cp "$R/devgame_naboo/nicjk/naboo_server.cfg" "$HS/nicjk/naboo_server.cfg"
cat >> "$HS/nicjk/naboo_server.cfg" <<'EOF'
seta timelimit 20
set g_needpass 0
set g_password ""
set nextmap "devmap naboo_theed"
seta g_doWarmup 0
EOF
powershell -NoProfile -Command ". '$(cygpath -w "$R/tools/bot_names.ps1")'; Get-BotLines -Bots 32" | tr -d '\r' | grep addbot | grep -v -i '"Kyle"' | head -31 > "$HS/nicjk/bots31.cfg"
# (Kyle is on the list but not defined in the Steam install: "Bot 'Kyle' not defined")
echo "bot lines: $(grep -c addbot "$HS/nicjk/bots31.cfg")" | tee "$OUT/summary.txt"

cd "$G"
./nicjkded.x86_64.exe +set fs_homepath "$HSW" +set fs_game nicjk +set dedicated 1 +set net_port 29280 +set logfile 2 \
  +exec naboo_server.cfg +set sv_maxclients 32 +set sv_profile 60 +devmap naboo_theed +exec bots31.cfg > "$OUT/server_stdout.txt" 2>&1 &
sleep 90

# memory sampler
cat > "$OUT/sample_memory.ps1" <<'EOF'
param([string]$Csv, [int]$Minutes)
"time,name,pid,working_set_mb,private_mb" | Out-File -FilePath $Csv -Encoding utf8
$end = (Get-Date).AddMinutes($Minutes)
while ((Get-Date) -lt $end) {
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*steamlong_*' -and $_.Name -like 'nicjk*' } | ForEach-Object {
    $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
    if ($p) { "{0},{1},{2},{3:N0},{4:N0}" -f (Get-Date -Format 'HH:mm:ss'), $p.ProcessName, $p.Id, ($p.WorkingSet64/1MB), ($p.PrivateMemorySize64/1MB) | Out-File -FilePath $Csv -Append -Encoding utf8 }
  }
  Start-Sleep -Seconds 30
}
EOF
powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$OUT/sample_memory.ps1")" -Csv "$(cygpath -w "$OUT/memory.csv")" -Minutes $((MIN + 3)) > /dev/null 2>&1 &

# client
cat > "$HC/nicjk/play.cfg" <<'EOF'
set f1 "follownext; wait 3000; screenshot; wait 1000; vstr f1"
set go "wait 1500; team s; wait 600; cg_draw2D 1; cg_drawFPS 1; com_maxfps 0; r_tworldStats 1; ui_openmenu none_x; wait 100; follownext; wait 200; vstr f1"
vstr go
EOF
cat > "$HC/nicjk/pre.cfg" <<'EOF'
set model NikolayAngelovPrequel/default_hot; set color1 4; set color2 4
set cg_drawFPS 1; set cg_draw2D 1; set r_swapInterval 0
EOF
START=$(date +%s)
timeout $((MIN * 60)) ./nicjk.x86_64.exe +set fs_homepath "$HCW" +set fs_game nicjk +set cl_renderer rd-vulkant +set r_mode -1 +set r_fullscreen 0 \
  +set r_noborder 0 +set r_customwidth 1920 +set r_customheight 1080 +set net_port 29281 +set logfile 2 +exec pre.cfg +connect 127.0.0.1:29280 +exec play.cfg > "$OUT/client_stdout.txt" 2>&1
echo "client exit=$? after $(( ($(date +%s) - START) / 60 )) min" | tee -a "$OUT/summary.txt"
sleep 5; stop_mine; sleep 3
cp "$HS/nicjk/qconsole.log" "$OUT/server_qconsole.log" 2>/dev/null; cp "$HC/nicjk/qconsole.log" "$OUT/client_qconsole.log" 2>/dev/null
cp "$HC"/nicjk/screenshots/*.jpg "$OUT/shots/" 2>/dev/null
# the screenshots taken at the highest frame rates: the fps logged in the second of each screenshot
py - "$OUT" <<'PYEOF'
import sys, os, re, shutil
out = sys.argv[1]; log = open(os.path.join(out, "client_qconsole.log"), errors="replace").read().splitlines()
fps = {}
for l in log:
    m = re.match(r"(\S+ \S+) TWORLD view: (\d+) fps", l)
    if m: fps[m.group(1)] = int(m.group(2))
best = []
for f in sorted(os.listdir(os.path.join(out, "shots"))):
    m = re.match(r"shot(\d{4}-\d\d-\d\d)_(\d\d)-(\d\d)-(\d\d)\.jpg", f)
    if not m: continue
    t = "%s %s:%s:%s" % m.groups()
    v = max([fps.get(t[:-2] + "%02d" % (int(t[-2:]) + d), 0) for d in (-1, 0)] or [0])
    best.append((v, f))
best.sort(reverse=True)
for v, f in best[:12]:
    shutil.copy(os.path.join(out, "shots", f), os.path.join(out, "shots", "best_%04dfps_%s" % (v, f[4:])))
print("screenshots:", len(best), " best:", [v for v, f in best[:12]])
PYEOF
echo "done: $OUT" | tee -a "$OUT/summary.txt"
