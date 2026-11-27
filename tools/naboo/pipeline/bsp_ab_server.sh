#!/bin/bash
# Server-only A/B of two collision map files: the dev build's dedicated server with 31 bots on naboo_theed, the same
# bot list, bot_profile over the run, one run per file back to back. Reports load time and the bots' trace costs.
#   bsp_ab_server.sh <minutes> <tag> <a.bsp> <b.bsp>        results in naboo/bsp_ab/<tag>/
# Only processes whose command line holds "bspab_" are stopped.
MIN=${1:-4}; TAG=${2:-ab}; A="$3"; B="$4"
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"
D="$R/devgame_naboo"; GD="E:\\jedi academy modding archive\\Jedi Academy TaystJK_AI test\\GameData"
OUT="$R/naboo/bsp_ab/$TAG"; mkdir -p "$OUT"
stop_mine() { powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*bspab_*' -and \$_.Name -like 'nicjk*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null; }
cp "$D/nicjk/maps/naboo_theed.bsp" "$OUT/installed_before.bsp"
cd "$D" || exit 1
powershell -NoProfile -Command ". '$(cygpath -w "$R/tools/bot_names.ps1")'; Get-BotLines -Bots 32" | tr -d '\r' | grep addbot | head -31 > nicjk/bspab_bots.cfg
for side in a b; do
  if [ "$side" = a ]; then SRC="$A"; else SRC="$B"; fi
  cp "$SRC" nicjk/maps/naboo_theed.bsp
  rm -f nicjk/qconsole.log
  timeout $((MIN * 60 + 60)) ./nicjkded.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set dedicated 1 \
    +set net_port 29390 +set logfile 2 +exec naboo_server.cfg +set sv_maxclients 32 +set timelimit 0 +set fraglimit 0 \
    +set bot_profile $((MIN * 60 - 30)) +set bspab_tag 1 +devmap naboo_theed +exec bspab_bots.cfg > /dev/null 2>&1
  stop_mine; cp nicjk/qconsole.log "$OUT/server_$side.log"
done
cp "$OUT/installed_before.bsp" nicjk/maps/naboo_theed.bsp
echo "done: $OUT"
