#!/bin/sh
# Profiled dedicated-server run from devgame_naboo. Refuses to start while a game from devgame_dev is running,
# unless ALLOW_BUSY=1 (use only when the user has said the other game may share the machine).
#   run_server_test.sh <map> <bots cfg> <frames to wait> <log copy path>
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"
D="$R/devgame_naboo"
busy=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"Name like 'taystjk%'\" | Where-Object { \$_.ExecutablePath -like '*devgame_dev*' } | Measure-Object).Count" 2>/dev/null | tr -d '\r')
if [ "$busy" != "0" ] && [ "$ALLOW_BUSY" != "1" ]; then echo "BUSY: a devgame_dev game is running ($busy); not starting"; exit 3; fi
cd "$D" || exit 1
rm -f taystjk/qconsole.log
timeout 300 ./taystjkded.x86_64.exe +set fs_basepath "E:\\jedi academy modding archive\\Jedi Academy TaystJK_AI test\\GameData" +set fs_homepath "$(cygpath -w "$D")" +set fs_game taystjk +set dedicated 1 +set net_port 29180 +exec naboo_server.cfg +set sv_profile 30 +set bot_profile 30 +devmap "$1" +exec "$2" +wait "$3" +quit > server_test.out 2>&1
echo "exit=$?"
grep -aE "SVPROF (window|ms/frame|botai|game )|CM_BuildLeafAccel|ERROR" taystjk/qconsole.log | cut -c21-240 | tail -9
echo "hitch lines: $(grep -ac 'SVPROF HITCH' taystjk/qconsole.log)"
grep -a "Kill:" taystjk/qconsole.log | sed 's/.* by //' | sort | uniq -c
grep -aiE "BOTEVAL (bots found|navigation)" taystjk/qconsole.log | cut -c21-240 | tail -2
[ -n "$4" ] && cp taystjk/qconsole.log "$4"
exit 0
