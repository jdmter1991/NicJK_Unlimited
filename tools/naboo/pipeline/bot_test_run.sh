#!/bin/bash
# One bot test run on the development build: dedicated server with 31 bots on naboo_theed (cheats on, no time
# limit, position and death logging), a spectating client at 1920 x 1080 that follows the bots and takes a game
# screenshot at every switch (the game's own picture), uncapped with the frame-rate counter on.
#   bot_test_run.sh <minutes> <tag>          e.g. bot_test_run.sh 20 run1
# Results in naboo/bottests/<tag>/: games log of the server (PlayerPos / DeathPos / Kill lines), client console log,
# screenshots, memory.csv. Then: py bot_test_analyze.py naboo/bottests/<tag>
# Only processes whose command line holds "bottest_" are stopped.
MIN=${1:-20}; TAG=${2:-run}
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"
D="$R/devgame_naboo"; GD="E:\\jedi academy modding archive\\Jedi Academy TaystJK_AI test\\GameData"
OUT="$R/naboo/bottests/$TAG"; mkdir -p "$OUT/shots"
stop_mine() { powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*bottest_*' -and \$_.Name -like 'nicjk*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null; }
stop_mine
cd "$D" || exit 1
powershell -NoProfile -Command ". '$(cygpath -w "$R/tools/bot_names.ps1")'; Get-BotLines -Bots 32" | tr -d '\r' | grep addbot | head -31 > nicjk/bottest_bots.cfg
cat > nicjk/bottest_server.cfg <<'EOF'
set g_log "bottest_games.log"
set g_logSync 1
set g_logDeathPos 1
set g_logPlayerPos 2000
set timelimit 0
set fraglimit 0
EOF
rm -f nicjk/bottest_games.log nicjk/screenshots/*.jpg nicjk/qconsole.log
./nicjkded.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set dedicated 1 +set net_port 29380 \
  +set logfile 0 +exec naboo_server.cfg +exec bottest_server.cfg +set sv_maxclients 32 +set bottest_tag 1 +devmap naboo_theed +exec bottest_bots.cfg > "$OUT/server_stdout.txt" 2>&1 &
sleep 90
cat > nicjk/bottest_client.cfg <<'EOF'
set f1 "follownext; wait 3000; screenshot; wait 1000; vstr f1"
set go "wait 1500; team s; wait 600; cg_draw2D 1; cg_drawFPS 1; com_maxfps 0; r_tworldStats 1; ui_openmenu none_x; wait 100; follownext; wait 200; vstr f1"
vstr go
EOF
cat > "$OUT/sample_memory.ps1" <<'EOF'
param([string]$Csv, [int]$Minutes)
"time,name,pid,working_set_mb,private_mb" | Out-File -FilePath $Csv -Encoding utf8
$end = (Get-Date).AddMinutes($Minutes)
while ((Get-Date) -lt $end) {
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*bottest_*' -and $_.Name -like 'nicjk*' } | ForEach-Object {
    $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
    if ($p) { "{0},{1},{2},{3:N0},{4:N0}" -f (Get-Date -Format 'HH:mm:ss'), $p.ProcessName, $p.Id, ($p.WorkingSet64/1MB), ($p.PrivateMemorySize64/1MB) | Out-File -FilePath $Csv -Append -Encoding utf8 }
  }
  Start-Sleep -Seconds 30
}
EOF
powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$OUT/sample_memory.ps1")" -Csv "$(cygpath -w "$OUT/memory.csv")" -Minutes $((MIN + 2)) > /dev/null 2>&1 &
timeout $((MIN * 60)) ./nicjk.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set cl_renderer rd-vulkant \
  +set r_mode -1 +set r_fullscreen 0 +set r_noborder 0 +set r_customwidth 1920 +set r_customheight 1080 +set r_swapInterval 0 +set net_port 29381 \
  +set logfile 2 +set bottest_tag 1 +connect 127.0.0.1:29380 +exec bottest_client.cfg > "$OUT/client_stdout.txt" 2>&1
echo "client exit=$?"
sleep 3; stop_mine; sleep 2
cp nicjk/bottest_games.log "$OUT/games.log" 2>/dev/null; cp nicjk/qconsole.log "$OUT/client_qconsole.log" 2>/dev/null
cp nicjk/screenshots/*.jpg "$OUT/shots/" 2>/dev/null
echo "done: $OUT  ($(ls "$OUT/shots" | wc -l) screenshots, $(grep -c PlayerPos "$OUT/games.log" 2>/dev/null) positions)"
