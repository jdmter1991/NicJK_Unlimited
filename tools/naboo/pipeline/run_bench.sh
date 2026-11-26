#!/bin/sh
# Benchmark on naboo_theed with bots, uncapped: per viewpoint the average, the 1 % low and the worst frame, from the
# renderer's own frame-time recorder (r_tworldBench). Never from wait counts: "wait N" is about N/2 frames here.
#   run_bench.sh client <label> <win_w> <win_h> [render_w render_h]   dedicated server with 31 bots + this client
#                                                                     spectating at five fixed viewpoints, then
#                                                                     following a bot
#   run_bench.sh server <label>                                       32 bots on the dedicated server alone (the game
#                                                                     has 32 client slots, so no client can join)
# Bots: the user's list through tools\bot_names.ps1, skill 5. About two minutes of play before measuring.
# A render size larger than the window uses r_renderWidth / r_renderHeight; the size the renderer really used is
# printed in every TWBENCH line. Only processes started from devgame_naboo are stopped.
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"
D="$R/devgame_naboo"; OUT="$R/naboo/export/city/bench"; GD="E:\\jedi academy modding archive\\Jedi Academy TaystJK_AI test\\GameData"
mkdir -p "$OUT"; cd "$D" || exit 1
stop_mine() { powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -like 'nicjk*' -and \$_.ExecutablePath -like '*devgame_naboo*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null; }
other=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object { (\$_.Name -like 'nicjk*' -or \$_.Name -like 'taystjk*' -or \$_.Name -eq 'blender.exe') -and \$_.ExecutablePath -notlike '*devgame_naboo*' } | Measure-Object).Count" | tr -d '\r\n ')
[ "$other" != "0" ] && echo "NOTE: $other other game/Blender process(es) running during this benchmark"
stop_mine
MODE=$1; L=$2
if [ "$MODE" = "server" ]; then
  powershell -NoProfile -Command ". '$(cygpath -w "$R/tools/bot_names.ps1")'; Get-BotLines -Bots 32" | tr -d '\r' > nicjk/naboo_bots_bench.cfg
  # the dedicated server prints to its own console, not to stdout: its log file is read instead (no client runs here)
  rm -f nicjk/qconsole.log
  timeout 330 ./nicjkded.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set dedicated 1 +set net_port 29180     +exec naboo_server.cfg +set sv_maxclients 32 +set logfile 2 +set sv_profile 30 +devmap naboo_theed +exec naboo_bots_bench.cfg > /dev/null 2>&1
  stop_mine
  cp nicjk/qconsole.log "$OUT/server32_$L.qconsole.log"
  echo "== server alone, 32 bots ($L): clients entered $(grep -ac 'entered the game' nicjk/qconsole.log), hitch lines $(grep -ac 'SVPROF HITCH' nicjk/qconsole.log)"
  grep -aE "SVPROF (window|ms/frame)" nicjk/qconsole.log | tail -8 | cut -c21-220
  grep -aiE "Unable to find bot|Bot not found" nicjk/qconsole.log | cut -c21-120 | sort | uniq -c | head -5
  exit 0
fi
W=$3; H=$4; RW=${5:-0}; RH=${6:-0}
powershell -NoProfile -Command ". '$(cygpath -w "$R/tools/bot_names.ps1")'; Get-BotLines -Bots 31" | tr -d '\r' > nicjk/naboo_bots_bench.cfg
./nicjkded.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set dedicated 1 +set net_port 29180 \
  +exec naboo_server.cfg +set sv_maxclients 32 +set logfile 0 +set sv_profile 30 +devmap naboo_theed +exec naboo_bots_bench.cfg > "$OUT/server31_$L.out" 2>&1 &
sleep 75
# five fixed viewpoints, about 30 s each at 130 fps (longer when slower), then one section following a bot
cat > nicjk/naboo_bench2.cfg <<'EOF'
set b0 "setviewpos 356 9751 360 -90; wait 400; r_tworldBench hall; wait 8000; vstr b1"
set b1 "setviewpos 362 6500 380 -90; wait 400; r_tworldBench avenue; wait 8000; vstr b2"
set b2 "setviewpos -1800 1380 80 24; wait 400; r_tworldBench market; wait 8000; vstr b3"
set b3 "setviewpos 2620 3640 200 150; wait 400; r_tworldBench court; wait 8000; vstr b4"
set b4 "setviewpos 669 3583 1400 42; wait 400; r_tworldBench overview; wait 8000; vstr b5"
set b5 "r_tworldBench 0; noclip; follownext; wait 400; r_tworldBench follow; wait 8000; r_tworldBench 0; wait 20; quit"
set bgo "com_maxfps 125; wait 9000; team s; wait 600; noclip; cg_draw2D 1; cg_drawFPS 1; com_maxfps 0; wait 300; vstr b0"
vstr bgo
EOF
EXTRA="+set r_renderScale 0"
[ "$RW" != "0" ] && EXTRA="+set r_fbo 1 +set r_renderWidth $RW +set r_renderHeight $RH +set r_renderScale 1"
NB=0; [ "$W" -ge 2560 ] && NB=1
rm -f nicjk/qconsole.log
( sleep 150; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader > "$OUT/gpu_$L.txt" 2>/dev/null ) &
timeout 900 ./nicjk.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set cl_renderer rd-vulkant \
  +set r_mode -1 +set r_fullscreen 0 +set r_noborder $NB +set r_customwidth $W +set r_customheight $H $EXTRA +set r_swapInterval 0 +set r_tworldCullSize 0.004 +set r_tworldLodSize1 0.12 +set r_tworldLodSize2 0.035 \
  +set net_port 29181 +set logfile 2 +connect 127.0.0.1:29180 +exec naboo_bench2.cfg > client_bench.out 2>&1
sleep 1; stop_mine; wait
cp nicjk/qconsole.log "$OUT/client31_$L.qconsole.log"
echo "== $L: 31 bots + spectating client, window ${W}x$H render ${RW}x$RH, GPU at 150 s: $(cat "$OUT/gpu_$L.txt" 2>/dev/null)"
grep -a "TWBENCH" nicjk/qconsole.log | cut -c21-190
echo "server: hitch lines $(grep -ac 'SVPROF HITCH' "$OUT/server31_$L.out"); $(grep -aE 'SVPROF ms/frame' "$OUT/server31_$L.out" | tail -1 | cut -c1-160)"
