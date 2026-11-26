#!/bin/sh
# Real frame rates with bots: dedicated server with N bots, client playing in third person at the four spots.
#   run_stat_bots.sh <label> <bots> <width> <height> ["a 1; b 0"]
# Frame rates come from the renderer's own once-per-second count (never from wait counts).
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"
D="$R/devgame_naboo"; GD="E:\jedi academy modding archive\Jedi Academy TaystJK_AI test\GameData"
L=$1; N=$2; W=$3; H=$4; EXTRA=$5
cd "$D" || exit 1
stop_mine() { powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -like 'nicjk*' -and \$_.ExecutablePath -like '*devgame_naboo*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null; }
stop_mine
powershell -NoProfile -Command ". '$(cygpath -w "$R/tools/bot_names.ps1")'; Get-BotLines -Bots $N" | tr -d '\r' > nicjk/naboo_bots_probe.cfg
./nicjkded.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set dedicated 1 +set net_port 29180 \
  +exec naboo_server.cfg +set sv_maxclients 32 +set logfile 0 +devmap naboo_theed +exec naboo_bots_probe.cfg > server_probe.out 2>&1 &
sleep 70
cat > nicjk/naboo_probe.cfg <<EOF2
set f0 "setviewpos 356 9751 330 -90; wait 600; echo STAT hall; wait 2400; vstr f1"
set f1 "setviewpos 362 6350 340 90; wait 600; echo STAT steps; wait 2400; vstr f2"
set f2 "setviewpos -1800 1380 40 24; wait 600; echo STAT market; wait 2400; vstr f3"
set f3 "setviewpos 2620 3640 160 150; wait 600; echo STAT court; wait 2400; echo STAT end; quit"
set fgo "com_maxfps 125; wait 2500; team f; wait 900; god; cg_thirdPerson 1; cg_fpls 0; cg_thirdPersonAngle 0; cg_thirdPersonRange 80; cg_draw2D 1; cg_drawFPS 1; r_tworldStats 1; $EXTRA; com_maxfps 0; wait 300; vstr f0"
vstr fgo
EOF2
rm -f nicjk/qconsole.log
timeout 600 ./nicjk.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set cl_renderer rd-vulkant \
  +set r_mode -1 +set r_fullscreen 0 +set r_noborder 0 +set r_customwidth $W +set r_customheight $H +set r_swapInterval 0 \
  +set model NikolayAngelovPrequel/default_hot +set color1 4 +set net_port 29181 +set logfile 2 +connect 127.0.0.1:29180 +exec naboo_probe.cfg > client_probe.out 2>&1
sleep 1; stop_mine
echo "== $L ($N bots, ${W}x$H)"; py "$R/naboo/tools/stat_from_log.py" nicjk/qconsole.log | cut -c1-48
grep -a "TWORLD cpu" nicjk/qconsole.log | awk 'NR%5==3' | cut -c21-110 | head -6
