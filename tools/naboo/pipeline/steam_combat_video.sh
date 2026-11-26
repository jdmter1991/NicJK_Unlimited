#!/bin/bash
# One-minute combat video from the Steam install: server with 31 bots, a spectating client records a demo while it
# follows bots (switching every ~15 s), then the demo is played back and rendered by the game's own "video" command
# (the game picture only, never the screen) to an MJPEG AVI at 30 frames per second, 1920 x 1080.
#   steam_combat_video.sh [seconds]       default 75 (a little more than a minute, the start is trimmed by the load)
# Uses the scratch homes of steam_longplay.sh; only processes whose command line holds them are stopped.
SEC=${1:-75}
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"
G="/b/SteamLibrary/steamapps/common/Jedi Academy/GameData"
OUT="$R/naboo/longplay/video_$(date +%Y%m%d_%H%M)"; mkdir -p "$OUT"
HS="$R/devgame_naboo/steamlong_srv"; HC="$R/devgame_naboo/steamlong_cli"
HSW=$(cygpath -w "$HS"); HCW=$(cygpath -w "$HC")
stop_mine() { powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*steamlong_*' -and \$_.Name -like 'nicjk*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null; }
stop_mine
rm -f "$HS/nicjk/qconsole.log" "$HC/nicjk/qconsole.log" "$HC/nicjk/nicjk.cfg" "$HS/nicjk/nicjk.cfg"
rm -rf "$HC/nicjk/demos" "$HC/nicjk/videos"
cd "$G"
./nicjkded.x86_64.exe +set fs_homepath "$HSW" +set fs_game nicjk +set dedicated 1 +set net_port 29280 +set logfile 2 \
  +exec naboo_server.cfg +set sv_maxclients 32 +set timelimit 0 +devmap naboo_theed +exec bots31.cfg > "$OUT/server_stdout.txt" 2>&1 &
sleep 90
# record: frame rate capped at 125 so that "wait" counts are a stable clock (two waits per frame)
W=$(( SEC * 125 * 2 ))
cat > "$HC/nicjk/rec.cfg" <<EOF
set f1 "follownext; wait 3750; vstr f1"
set go "com_maxfps 125; wait 1500; team s; wait 600; cg_draw2D 1; cg_drawFPS 0; r_tworldStats 0; ui_openmenu none_x; wait 100; follownext; wait 400; record combat1; vstr f1; wait $W; stoprecord; wait 100; quit"
vstr go
EOF
timeout $(( SEC + 240 )) ./nicjk.x86_64.exe +set fs_homepath "$HCW" +set fs_game nicjk +set cl_renderer rd-vulkant +set r_mode -1 +set r_fullscreen 0 \
  +set r_customwidth 1920 +set r_customheight 1080 +set net_port 29281 +set logfile 2 +connect 127.0.0.1:29280 +exec rec.cfg > "$OUT/rec_stdout.txt" 2>&1
echo "record exit=$?"; stop_mine
ls -la "$HC"/nicjk/demos/ 2>/dev/null
# render: fixed 30 frames per second of game time, whatever the real frame rate
cat > "$HC/nicjk/play.cfg" <<EOF
set go "wait 30; video combat1; wait $(( (SEC + 30) * 30 * 2 )); stopvideo; wait 20; quit"
vstr go
EOF
timeout $(( SEC * 6 + 300 )) ./nicjk.x86_64.exe +set fs_homepath "$HCW" +set fs_game nicjk +set cl_renderer rd-vulkant +set r_mode -1 +set r_fullscreen 0 \
  +set r_customwidth 1920 +set r_customheight 1080 +set logfile 2 +set cl_aviFrameRate 30 +set cl_aviMotionJpeg 1 +set cg_drawFPS 0 \
  +demo combat1 +exec play.cfg > "$OUT/play_stdout.txt" 2>&1
echo "render exit=$?"; stop_mine
cp "$HC"/nicjk/videos/*.avi "$OUT/" 2>/dev/null; cp "$HC/nicjk/qconsole.log" "$OUT/render_qconsole.log" 2>/dev/null
ls -la "$OUT"/*.avi 2>/dev/null
echo "done: $OUT"
