#!/bin/bash
# A timed session on the user's Steam install: dedicated server with 31 bots on naboo_theed (position and death
# logging on) and a client at 1920 x 1080 that spectates, follows the bots and takes a screenshot at every switch,
# uncapped with the frame-rate counter on. Scratch home folders, so the user's own settings are not touched.
#   steam_session.sh <minutes> <tag>        results in naboo/steamsessions/<tag>/
# Only processes whose command line holds "steamsess_" are stopped.
MIN=${1:-20}; TAG=${2:-session}
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"
G="/b/SteamLibrary/steamapps/common/Jedi Academy/GameData"
OUT="$R/naboo/steamsessions/$TAG"; mkdir -p "$OUT/shots"
HS="$R/devgame_naboo/steamsess_srv"; HC="$R/devgame_naboo/steamsess_cli"
stop_mine() { powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*steamsess_*' -and \$_.Name -like 'nicjk*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null; }
stop_mine
rm -rf "$HS" "$HC"; mkdir -p "$HS/nicjk" "$HC/nicjk"
cp "$R/devgame_naboo/steamlong_srv/nicjk/naboo_server.cfg" "$R/devgame_naboo/steamlong_srv/nicjk/bots31.cfg" "$HS/nicjk/"
cat > "$HS/nicjk/session.cfg" <<'EOF'
set g_log "session_games.log"
set g_logSync 1
set g_logDeathPos 1
set g_logPlayerPos 2000
set timelimit 0
set fraglimit 0
set bot_profile 300
EOF
cd "$G" || exit 1
./nicjkded.x86_64.exe +set fs_homepath "$(cygpath -w "$HS")" +set fs_game nicjk +set dedicated 1 +set net_port 29480 +set logfile 2 \
  +exec naboo_server.cfg +exec session.cfg +set sv_maxclients 32 +devmap naboo_theed +exec bots31.cfg > /dev/null 2>&1 &
sleep 90
cat > "$HC/nicjk/session_client.cfg" <<'EOF'
set f1 "follownext; wait 4000; screenshot; wait 2000; vstr f1"
set go "wait 1500; team s; wait 600; cg_draw2D 1; cg_drawFPS 1; com_maxfps 0; ui_openmenu none_x; wait 100; follownext; wait 200; vstr f1"
vstr go
EOF
timeout $((MIN * 60)) ./nicjk.x86_64.exe +set fs_homepath "$(cygpath -w "$HC")" +set fs_game nicjk +set cl_renderer rd-vulkant \
  +set r_mode -1 +set r_fullscreen 0 +set r_customwidth 1920 +set r_customheight 1080 +set r_swapInterval 0 +set net_port 29481 \
  +set logfile 2 +connect 127.0.0.1:29480 +exec session_client.cfg > /dev/null 2>&1
echo "client exit=$?"
sleep 3; stop_mine; sleep 2
cp "$HS/nicjk/session_games.log" "$OUT/games.log" 2>/dev/null; cp "$HS/nicjk/qconsole.log" "$OUT/server_qconsole.log" 2>/dev/null
cp "$HC/nicjk/qconsole.log" "$OUT/client_qconsole.log" 2>/dev/null; cp "$HC"/nicjk/screenshots/*.jpg "$OUT/shots/" 2>/dev/null
echo "done: $OUT  ($(ls "$OUT/shots" | wc -l) screenshots, $(grep -c PlayerPos "$OUT/games.log" 2>/dev/null) positions)"
