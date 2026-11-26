#!/bin/sh
# Four showcase screenshots: a dedicated server with 31 bots from the user's list, a client that joins it, the
# player spawned in third person (test character, blue saber), frame rate uncapped with the counter on, in a
# bordered window so the title bar shows.
#   take_showcase.sh [width height]        default 2400 1350 (the largest 16:9 window with a title bar on 2560 x 1440)
# Each view is saved twice: the game's own screenshot (client area) and a capture of the whole window with its
# title bar (capture_window.ps1). Only processes started from devgame_naboo are stopped, before and after.
# r_noborder and cg_draw2D are saved between runs, so both are set here.
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"
D="$R/devgame_naboo"; OUT="$R/naboo/export/city/showcase"
GD="E:\\jedi academy modding archive\\Jedi Academy TaystJK_AI test\\GameData"
W=${1:-2400}; H=${2:-1350}
mkdir -p "$OUT"; cd "$D" || exit 1
stop_mine() { powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { (\$_.Name -like 'nicjk*' -and \$_.ExecutablePath -like '*devgame_naboo*') -or (\$_.Name -eq 'powershell.exe' -and \$_.CommandLine -like '*capture_window.ps1*') } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null; }
stop_mine
powershell -NoProfile -Command ". '$(cygpath -w "$R/tools/bot_names.ps1")'; Get-BotLines -Bots 31" | tr -d '\r' > nicjk/naboo_bots_user31.cfg
echo "bot lines: $(grep -c addbot nicjk/naboo_bots_user31.cfg)"

# ---- dedicated server; its console goes to server_showcase.out (no log file, the client writes qconsole.log)
./nicjkded.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set dedicated 1 +set net_port 29180 \
  +exec naboo_server.cfg +set sv_maxclients 32 +set logfile 0 +devmap naboo_theed +exec naboo_bots_user31.cfg > server_showcase.out 2>&1 &
echo "server starting; waiting 75 s for the map and the bots"
sleep 75
echo "bots on the server: $(grep -ac 'entered the game' server_showcase.out)"

# ---- client: palace main hall, palace from the plaza, market, lantern court
cat > nicjk/naboo_showcase.cfg <<'EOF'
set v0 "setviewpos 356 9751 330 -90; ui_openmenu none_x; wait 150; echo FPS_BEGIN hall; wait 900; echo FPS_STOP hall; ui_openmenu none_x; wait 5; screenshot; wait 500; vstr v1"
set v1 "setviewpos 362 6350 340 90; ui_openmenu none_x; wait 150; echo FPS_BEGIN steps; wait 900; echo FPS_STOP steps; ui_openmenu none_x; wait 5; screenshot; wait 500; vstr v2"
set v2 "setviewpos -1800 1380 40 24; ui_openmenu none_x; wait 150; echo FPS_BEGIN market; wait 900; echo FPS_STOP market; ui_openmenu none_x; wait 5; screenshot; wait 500; vstr v3"
set v3 "setviewpos 2620 3640 160 150; ui_openmenu none_x; wait 150; echo FPS_BEGIN court; wait 900; echo FPS_STOP court; ui_openmenu none_x; wait 5; screenshot; wait 500; echo SHOTS_END; quit"
set showgo "com_maxfps 125; wait 2500; team f; wait 900; god; cg_thirdPerson 1; cg_fpls 0; cg_thirdPersonAngle 0; cg_thirdPersonRange 80; cg_draw2D 1; cg_drawFPS 1; com_maxfps 0; wait 400; vstr v0"
vstr showgo
EOF
rm -f nicjk/screenshots/*.jpg nicjk/qconsole.log
powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$R/naboo/tools/capture_window.ps1")" -Watch "$(cygpath -w "$D/nicjk/screenshots")" -Out "$(cygpath -w "$OUT")" -Names palace_interior,palace_outside,market,lantern_court > capture.out 2>&1 &
# the engine cuts the command line at 1024 characters: everything that is not needed before the window opens goes
# into a config file
cat > nicjk/naboo_showcase_pre.cfg <<EOF2
set r_tworldInstancing 1; set r_tworldShadows 1; set r_tworldPBR 1; set r_tworldLamps 1; set r_tworldIndoor 0.55; set r_tworldAO 0.6
set model NikolayAngelovPrequel/default_hot; set color1 4; set color2 4
set cg_thirdPerson 1; set cg_fpls 0; set cg_thirdPersonAngle 0; set cg_thirdPersonRange 80; set cg_drawFPS 1; set cg_draw2D 1
EOF2
timeout 600 ./nicjk.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set cl_renderer rd-vulkant   +set r_mode -1 +set r_fullscreen 0 +set r_noborder 0 +set r_centerWindow 1 +set r_customwidth $W +set r_customheight $H +set r_renderScale 0 +set r_swapInterval 0   +set net_port 29181 +set logfile 2 +exec naboo_showcase_pre.cfg +connect 127.0.0.1:29180 +exec naboo_showcase.cfg > client_showcase.out 2>&1
echo "client exit=$?"
sleep 2; stop_mine
cat capture.out 2>/dev/null | tail -5
i=0
for f in $(ls nicjk/screenshots/shot*.jpg 2>/dev/null | sort); do
  n=$(echo "palace_interior palace_outside market lantern_court" | cut -d' ' -f$((i+1)))
  cp "$f" "$OUT/${n}.jpg"; i=$((i+1))
done
echo "game screenshots: $i"
grep -aiE "ERROR|Server is full|Invalid password|timed out" nicjk/qconsole.log | cut -c21-140 | sort | uniq -c | head -5
