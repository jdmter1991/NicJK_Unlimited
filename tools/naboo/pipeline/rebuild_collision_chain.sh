#!/bin/bash
# Collision only: Blender collision export -> collision terrain -> spawns -> BSP -> floor check. Log naboo/rebuild_<tag>.log
TAG=${1:-coll}
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"; cd "$R/naboo" || exit 1
L="rebuild_$TAG.log"; : > "$L"
step() { echo "== $(date +%H:%M:%S) $*" | tee -a "$L"; }
step export
"/e/blender-5.2.0-windows-x64/blender.exe" -b --factory-startup --disable-autoexec "/e/jedi academy modding archive/Naboo Theed map/Naboo_Theed.blend" --python tools/export_region.py -- tools/naboo_config.json city export/city collision > export/city/collision_${TAG}_export.log 2>&1
grep -a "\[export\] collision" export/city/collision_${TAG}_export.log | cut -c1-400 | tee -a "$L"
step collision_terrain; py tools/build_collision_terrain.py export/city city 2>&1 | grep -v "^ \|^{\|^}" | tail -4 | cut -c1-300 | tee -a "$L"
step palace_spawns; py tools/add_palace_spawns.py export/city naboo_theed 2>&1 | tail -1 | cut -c1-120 | tee -a "$L"
step fix_spawns; py tools/fix_spawns.py export/city naboo_theed 2>&1 | grep -v Warning | head -1 | cut -c1-300 | tee -a "$L"
step bsp; py tools/write_collision_bsp.py export/city naboo_theed 2>&1 | grep -i "bot walls\|kill volume\|brushes \|bytes\|error\|Traceback" | cut -c1-200 | tee -a "$L"
cp q3base/base/maps/naboo_theed_own.bsp ../devgame_naboo/nicjk/maps/naboo_theed.bsp
step floorcheck; py tools/visual_vs_collision.py ../devgame_naboo/nicjk naboo_theed city 60000 2>&1 | tail -12 | head -11 | tee -a "$L"
step done
