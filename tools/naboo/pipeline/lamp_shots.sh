#!/bin/bash
# Lamp comparison screenshots on the dev build: a local devmap without bots, sun and ambient turned down
# (r_tworldLight 0.25, a dusk-like viewing aid, not a game setting players have), two fixed views, one screenshot each.
# 31 bots from the user's list are in the game (every client test runs at full load).
#   lamp_shots.sh <tag> <renderer_dll> <shadow_dds>
# Installs the given renderer and shadow texture for the run and restores the current ones afterwards.
# Results in naboo/lampshots/<tag>/. Only processes whose command line holds "lampshot_" are stopped.
TAG=$1; RDLL=$2; DDS=$3; VIEWS=$4        # optional: a config of views to use instead of the default ones
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"; D="$R/devgame_naboo"
GD="E:\\jedi academy modding archive\\Jedi Academy TaystJK_AI test\\GameData"
OUT="$R/naboo/lampshots/$TAG"; mkdir -p "$OUT"
cd "$D" || exit 1
cp rd-vulkant_x86_64.dll /tmp/lampshot_rd_keep.dll; cp nicjk/maps/naboo_theed_shadow.dds /tmp/lampshot_dds_keep.dds
cp "$RDLL" rd-vulkant_x86_64.dll; cp "$DDS" nicjk/maps/naboo_theed_shadow.dds
rm -f nicjk/screenshots/*.jpg nicjk/qconsole.log
powershell -NoProfile -Command ". '$(cygpath -w "$R/tools/bot_names.ps1")'; Get-BotLines -Bots 31" | tr -d '' | grep addbot | head -31 > nicjk/lampshot_bots.cfg
if [ -n "$VIEWS" ]; then cp "$VIEWS" nicjk/lampshot.cfg; else
cat > nicjk/lampshot.cfg <<'EOF'
set v1 "setviewpos -672 8900 470 90; wait 600; screenshot; wait 100; vstr v2"
set v2 "setviewpos 360 5400 160 90; wait 600; screenshot; wait 100; vstr v3"
set v3 "setviewpos -672 8900 470 90; r_tworldLamps 0; wait 600; screenshot; wait 100; r_tworldLamps 1; quit"
set go "wait 2500; ui_openmenu none_x; cg_draw2D 1; cg_drawFPS 1; r_tworldLight 0.25; noclip; wait 300; vstr v1"
vstr go
EOF
fi
timeout 300 ./nicjk.x86_64.exe +set fs_basepath "$GD" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set cl_renderer rd-vulkant \
  +set r_mode -1 +set r_fullscreen 0 +set r_customwidth 1920 +set r_customheight 1080 +set logfile 2 +set lampshot_tag 1 \
  +devmap naboo_theed +exec lampshot_bots.cfg +exec lampshot.cfg > /dev/null 2>&1
cp nicjk/screenshots/*.jpg "$OUT/" 2>/dev/null; cp nicjk/qconsole.log "$OUT/client.log" 2>/dev/null
cp /tmp/lampshot_rd_keep.dll rd-vulkant_x86_64.dll; cp /tmp/lampshot_dds_keep.dds nicjk/maps/naboo_theed_shadow.dds
echo "done: $OUT ($(ls "$OUT"/*.jpg 2>/dev/null | wc -l) shots)"; grep -a "LampOcclusion\|local lights\|R_LoadTWorldShadow" "$OUT/client.log" | cut -c1-200
