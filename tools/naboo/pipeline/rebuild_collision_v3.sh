#!/bin/bash
# Collision rebuild that keeps the spawn work already in the .map (no spawn tools re-run):
# Blender collision export -> collision terrain -> floor hole fill -> BSP -> floor check -> bot routes.
# The previous collision files are kept in export/city/collision/before_<tag>/. Log naboo/rebuild_<tag>.log
TAG=${1:-v3}
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"; cd "$R/naboo" || exit 1
L="rebuild_$TAG.log"; : > "$L"
step() { echo "== $(date +%H:%M:%S) $*" | tee -a "$L"; }
C=export/city/collision; mkdir -p "$C/before_$TAG"
cp "$C"/collision_tris.npy "$C"/collision_tris_v1.npy "$C"/collision_tris_prefill.npy "$C"/collision_stats.json "$C"/floor_fill.json "$C"/terrain_rebuild.json "$C/before_$TAG/" 2>/dev/null
cp ../devgame_naboo/nicjk/maps/naboo_theed.bsp "$C/before_$TAG/naboo_theed.bsp"; cp export/city/botroutes/naboo_theed.wnt "$C/before_$TAG/"
step export
"/e/blender-5.2.0-windows-x64/blender.exe" -b --factory-startup --disable-autoexec "/e/jedi academy modding archive/Naboo Theed map/Naboo_Theed.blend" --python tools/export_region.py -- tools/naboo_config.json city export/city collision > export/city/collision_${TAG}_export.log 2>&1
grep -a "\[export\] collision" export/city/collision_${TAG}_export.log | cut -c1-400 | tee -a "$L"
step collision_terrain; py tools/build_collision_terrain.py export/city city 2>&1 | grep -v "^ \|^{\|^}" | tail -4 | cut -c1-300 | tee -a "$L"
step floor_fill; py tools/fill_floor_holes.py export/city ../devgame_naboo/nicjk/maps/naboo_theed.tworld 2>&1 | tail -1 | cut -c1-300 | tee -a "$L"
step bsp; py tools/write_collision_bsp.py export/city naboo_theed 2>&1 | grep -i "skirts\|walls\|kill volume\|brushes \|bytes\|error\|Traceback" | cut -c1-200 | tee -a "$L"
cp q3base/base/maps/naboo_theed_own.bsp ../devgame_naboo/nicjk/maps/naboo_theed.bsp
step floorcheck; py tools/visual_vs_collision.py ../devgame_naboo/nicjk naboo_theed city 60000 2>&1 | tail -12 | head -11 | tee -a "$L"
step routes; py tools/make_bot_routes.py export/city naboo_theed export/city/botroutes/naboo_theed.wnt 400 2>&1 | tail -1 | tee -a "$L"
cp export/city/botroutes/naboo_theed.wnt ../devgame_naboo/nicjk/botroutes/
step done
