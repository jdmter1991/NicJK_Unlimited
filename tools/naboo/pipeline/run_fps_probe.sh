#!/bin/sh
# Frame-rate probe with bots: a dedicated server with N bots, a spectating client at the four showcase spots,
# 3000 frames each, uncapped, in a 2400 x 1350 window. Extra client settings can be given to switch things off.
#   run_fps_probe.sh <label> <bots> ["a 1; b 0"] [play]      play = spawn as a player in third person instead of spectating
# Only processes started from devgame_naboo are stopped.
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"
D="$R/devgame_naboo"; GD="E:\\jedi academy modding archive\\Jedi Academy TaystJK_AI test\\GameData"
L=$1; N=${2:-31}; EXTRA=$3
cd "$D" || exit 1
stop_mine() { powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -like 'nicjk*' -and \$_.ExecutablePath -like '*devgame_naboo*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null; }
stop_mine
if [ "$N" != "0" ]; then
  powershell -NoProfile -Command ". '$(cygpath -w "$R/tools/bot_names.ps1")'; Get-BotLines -Bots $N" | tr -d '\r' > nicjk/naboo_bots_probe.cfg
else
  : > nicjk/naboo_bots_probe.cfg
fi
./nicjkded.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set dedicated 1 +set net_port 29180 \
  +exec naboo_server.cfg +set sv_maxclients 32 +set logfile 0 +devmap naboo_theed +exec naboo_bots_probe.cfg > server_probe.out 2>&1 &
sleep 70
cat > nicjk/naboo_probe.cfg <<'EOF'
set f0 "setviewpos 356 9751 360 -90; wait 300; echo FPS_BEGIN hall; wait 3000; echo FPS_STOP hall; vstr f1"
set f1 "setviewpos 362 6350 380 90; wait 300; echo FPS_BEGIN steps; wait 3000; echo FPS_STOP steps; vstr f2"
set f2 "setviewpos -1800 1380 80 24; wait 300; echo FPS_BEGIN market; wait 3000; echo FPS_STOP market; vstr f3"
set f3 "setviewpos 2620 3640 200 150; wait 300; echo FPS_BEGIN court; wait 3000; echo FPS_STOP court; echo FPS_END; quit"
set fgo "com_maxfps 125; wait 2500; vstr probe_join; vstr probe_extra; com_maxfps 0; wait 300; vstr f0"
EOF
echo "set probe_extra \"$EXTRA\"" >> nicjk/naboo_probe.cfg
if [ "$4" = "play" ]; then echo 'set probe_join "team f; wait 900; god; cg_thirdPerson 1; cg_fpls 0; cg_thirdPersonAngle 0; cg_thirdPersonRange 80"' >> nicjk/naboo_probe.cfg; else echo 'set probe_join "team s; wait 600; noclip; cg_draw2D 0"' >> nicjk/naboo_probe.cfg; fi
echo "vstr fgo" >> nicjk/naboo_probe.cfg
rm -f nicjk/qconsole.log
timeout 600 ./nicjk.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set cl_renderer rd-vulkant \
  +set r_mode -1 +set r_fullscreen 0 +set r_noborder 0 +set r_customwidth 2400 +set r_customheight 1350 +set r_swapInterval 0 \
  +set model NikolayAngelovPrequel/default_hot +set color1 4 +set net_port 29181 +set logfile 2 +connect 127.0.0.1:29180 +exec naboo_probe.cfg > client_probe.out 2>&1
sleep 1; stop_mine
echo "$L ($N bots): $(py "$R/naboo/tools/fps_from_log.py" nicjk/qconsole.log)"
