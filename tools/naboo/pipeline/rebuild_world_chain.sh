#!/bin/bash
# Full rebuild after a change to the cooked world (water, materials), keeping the spawn work in the .map:
# cook -> textures -> vertex AO -> sky occlusion -> collision terrain and water volumes -> floor fill -> BSP -> routes
# -> spawns -> BSP -> glow lights -> lamp occlusion -> floor check. Log naboo/rebuild_<tag>.log
TAG=${1:-world}
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"; cd "$R/naboo" || exit 1
G="../devgame_naboo/nicjk"; L="rebuild_$TAG.log"; : > "$L"
step() { echo "== $(date +%H:%M:%S) $*" | tee -a "$L"; }
step cook
py tools/cook_v1.py export/city naboo_theed $G > export/city/cook_$TAG.log 2>&1 || { tail -5 export/city/cook_$TAG.log | tee -a "$L"; exit 1; }
grep -o '"gap_fill": {[^}]*}' export/city/cook_$TAG.log | head -2 | cut -c1-300 | tee -a "$L"
step dds; py tools/convert_textures_dds.py $G 2>&1 | tail -1 | cut -c1-100 | tee -a "$L"
step vertex_ao; build_tools/bake_vertex_ao.exe $G/maps/naboo_theed.tworld $G/maps/naboo_theed.tao 96 24 | cut -c1-90 | tee -a "$L"
step sky_occlusion; py tools/bake_sky_occlusion.py export/city $G naboo_theed city 2>&1 | tail -1 | cut -c1-200 | tee -a "$L"
step collision_terrain; py tools/build_collision_terrain.py export/city city 2>&1 | grep -v "^ \|^{\|^}" | tail -3 | cut -c1-300 | tee -a "$L"
step floor_fill; py tools/fill_floor_holes.py export/city $G/maps/naboo_theed.tworld 2>&1 | tail -1 | cut -c1-300 | tee -a "$L"
step bsp; py tools/write_collision_bsp.py export/city naboo_theed 2>&1 | grep -i "water cells\|bytes\|Traceback\|Error" | cut -c1-200 | tee -a "$L"
step routes; py tools/make_bot_routes.py export/city naboo_theed export/city/botroutes/naboo_theed.wnt 400 2>&1 | tail -1 | tee -a "$L"
step spawns; py tools/centre_spawns.py export/city naboo_theed export/city/objects.json export/city/botroutes/naboo_theed.wnt 2>&1 | tail -1 | tee -a "$L"
step bsp2; py tools/write_collision_bsp.py export/city naboo_theed 2>&1 | grep -i "\"spawns\"\|bytes\|Traceback" | tee -a "$L"
cp q3base/base/maps/naboo_theed_own.bsp $G/maps/naboo_theed.bsp; cp export/city/botroutes/naboo_theed.wnt $G/botroutes/
step glow_lights; py tools/glow_lights.py $G naboo_theed 2>&1 | tail -1 | tee -a "$L"
step lamp_occlusion; py tools/bake_lamp_occlusion.py $G naboo_theed export/city 2>&1 | tail -1 | tee -a "$L"
step floorcheck; py tools/visual_vs_collision.py $G naboo_theed city 60000 2>&1 | grep -a "within_64\|no_collision" | tee -a "$L"
step done
