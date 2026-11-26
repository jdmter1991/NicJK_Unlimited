#!/bin/sh
# Real frame rates at the four showcase spots without bots (devmap), from the renderer's own once-per-second count.
#   run_stat.sh <label> <width> <height> ["+set a 1 +set b 0"]
# Note: the console command "wait N" does NOT wait N frames here (the command buffer runs twice per frame), so
# frame rates must never be derived from wait counts.
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"; D="$R/devgame_naboo"
cd "$D" || exit 1
rm -f nicjk/qconsole.log
timeout 400 ./nicjk.x86_64.exe +set fs_basepath "E:\jedi academy modding archive\Jedi Academy TaystJK_AI test\GameData" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set cl_renderer rd-vulkant +set r_mode -1 +set r_fullscreen 0 +set r_noborder 0 +set r_customwidth $2 +set r_customheight $3 +set r_swapInterval 0 +set logfile 2 +set net_port 29181 $4 +devmap naboo_theed +exec naboo_stat.cfg > t.out 2>&1
echo "== $1"; py "$R/naboo/tools/stat_from_log.py" nicjk/qconsole.log
