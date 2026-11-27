#!/bin/bash
# Full rebuild after a collision export: cook (visual) -> DDS -> vertex AO -> (sky occlusion if the placements
# changed) -> collision terrain -> palace and forecourt spawns -> collision BSP -> floor check. Logs to naboo/rebuild_<tag>.log
TAG=${1:-v2}
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"; cd "$R/naboo" || exit 1
L="rebuild_$TAG.log"; : > "$L"
step() { echo "== $(date +%H:%M:%S) $*" | tee -a "$L"; }
step cook; cp ../devgame_naboo/nicjk/maps/naboo_theed.tsky export/city/naboo_theed.tsky.keep
py tools/cook_v1.py export/city naboo_theed ../devgame_naboo/nicjk > export/city/cook_$TAG.log 2>&1 || { tail -5 export/city/cook_$TAG.log | tee -a "$L"; exit 1; }
grep -o '"water_carving": {[^}]*}\|"missing_textures": [^]]*]' export/city/cook_$TAG.log | head -3 | cut -c1-300 | tee -a "$L"
step dds; py tools/convert_textures_dds.py ../devgame_naboo/nicjk 2>&1 | tail -1 | cut -c1-100 | tee -a "$L"
step vertex_ao; build_tools/bake_vertex_ao.exe ../devgame_naboo/nicjk/maps/naboo_theed.tworld ../devgame_naboo/nicjk/maps/naboo_theed.tao 96 24 | cut -c1-90 | tee -a "$L"
step sky_check
py - >> "$L" 2>&1 <<'PY'
import struct
t=open("../devgame_naboo/nicjk/maps/naboo_theed.tworld","rb").read(32); n=struct.unpack_from("<4sIIIIIII",t,0)[5]
s=open("../devgame_naboo/nicjk/maps/naboo_theed.tsky","rb").read(16)
print("tworld placements", n, "tsky header", s[:16])
PY
step collision_terrain; py tools/build_collision_terrain.py export/city city 2>&1 | grep -v "^ \|^{\|^}" | tail -4 | cut -c1-300 | tee -a "$L"
step palace_spawns; py tools/add_palace_spawns.py export/city naboo_theed 2>&1 | tail -1 | cut -c1-200 | tee -a "$L"
step fix_spawns; py tools/fix_spawns.py export/city naboo_theed 2>&1 | head -1 | cut -c1-300 | tee -a "$L"
step bsp; py tools/write_collision_bsp.py export/city naboo_theed 2>&1 | grep -i "bot walls\|kill volume\|brushes \|written\|bytes\|error\|Traceback" | cut -c1-200 | tee -a "$L"
ls -la q3base/base/maps/naboo_theed_own.bsp | awk '{print "bsp bytes", $5}' | tee -a "$L"
cp q3base/base/maps/naboo_theed_own.bsp ../devgame_naboo/nicjk/maps/naboo_theed.bsp
step floorcheck; py tools/visual_vs_collision.py ../devgame_naboo/nicjk naboo_theed city 60000 2>&1 | tail -12 | head -11 | tee -a "$L"
step done
