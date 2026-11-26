#!/bin/bash
# Free play for the user on the Steam install: dedicated server (31 bots, naboo_theed, cheats on, no time limit) and
# a plain client with the user's own settings and key bindings, joined as a player; no script drives the client.
# The server stops when the client is closed. Scratch homes: nothing is written into the Steam install.
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"
G="/b/SteamLibrary/steamapps/common/Jedi Academy/GameData"
OUT="$R/naboo/longplay/freeplay_$(date +%Y%m%d_%H%M)"; mkdir -p "$OUT"
HS="$R/devgame_naboo/steamfree_srv"; HC="$R/devgame_naboo/steamfree_cli"
rm -rf "$HS" "$HC"; mkdir -p "$HS/nicjk" "$HC/nicjk"
cp "$R/devgame_naboo/steamlong_srv/nicjk/naboo_server.cfg" "$R/devgame_naboo/steamlong_srv/nicjk/bots31.cfg" "$HS/nicjk/"
cd "$G"
./nicjkded.x86_64.exe +set fs_homepath "$(cygpath -w "$HS")" +set fs_game nicjk +set dedicated 1 +set net_port 29280 +set logfile 2 \
  +exec naboo_server.cfg +set sv_maxclients 32 +set timelimit 0 +devmap naboo_theed +exec bots31.cfg > "$OUT/server_stdout.txt" 2>&1 &
sleep 80
printf 'set go "wait 1500; team f"\nvstr go\n' > "$HC/nicjk/join.cfg"
./nicjk.x86_64.exe +set fs_homepath "$(cygpath -w "$HC")" +set fs_game nicjk +set cl_renderer rd-vulkant +set r_mode -1 +set r_fullscreen 0 \
  +set r_noborder 0 +set r_customwidth 1920 +set r_customheight 1080 +set net_port 29281 +set logfile 2 +connect 127.0.0.1:29280 +exec join.cfg > "$OUT/client_stdout.txt" 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*steamfree_*' -and \$_.Name -like 'nicjk*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
cp "$HS/nicjk/qconsole.log" "$OUT/server_qconsole.log" 2>/dev/null; cp "$HC/nicjk/qconsole.log" "$OUT/client_qconsole.log" 2>/dev/null
cp "$HC"/nicjk/screenshots/*.jpg "$OUT/" 2>/dev/null
echo "done: $OUT"
