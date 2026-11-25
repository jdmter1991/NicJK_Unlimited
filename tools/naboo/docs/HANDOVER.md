# Naboo: Theed port — hand-over (full scatter, placement culling, collision with water; 2026-11-25 late evening)

Docs: `TaystJK_AI_Claude_Code_improvements\naboo\docs\` — start with `TODO.md`, then the `UPDATE_*.md` notes
(newest: `UPDATE_scatter_collision.md`, before it `UPDATE_walls_ground_trees.md`, `UPDATE_water_pbr.md`).
Reference renders of the .blend and side-by-side sheets: `naboo\export\city\ref\`. Latest game screenshots:
`naboo\export\city\shots_v16\`, `shots_v14\`.

Own areas only: worktree `naboo_src` (branch `naboo-theed`, seventeen local commits d555f9291 .. f75f34b4a, clean,
not pushed), `build_naboo\`, `devgame_naboo\` (server port 29180, client 29181), `naboo\`. Shared checkout,
build_x64, devgame_dev and the game install untouched. The .blend is only ever read.

Machine: 16 GB. As of this note NOTHING from this session is running: no bake, no Blender, no game.

Run the map: `devgame_naboo\taystjk.x86_64.exe +set fs_basepath <GameData> +set fs_homepath <devgame_naboo>
+set fs_game taystjk +set cl_renderer rd-vulkant +set r_tworldInstancing 1 +set r_tworldShadows 1
+set r_tworldPBR 1 +devmap naboo_theed`. Those cvars are saved between runs: always pass them.
Test skin: `model NikolayAngelovPrequel/default_hot`.

State: walls, ground, sky, trees and the whole terrain scatter (leaf litter, twigs, grass, forested hills) match
the source renders closely. 76,945 placements, culled by grid cells; 426-452 FPS at 1080p, 4.8 GB GPU memory in
use. Collision: `naboo_theed.bsp` built from the terrain as drawn (1 m where needed), with carved river beds
and 2,153 water volumes; 62 spawns; 32 bots at 2.7-3.2 ms per server frame, none in solid, none drowned.

Later the same evening: a player swims in a carved river in a client (water volumes work); sun shadows rebaked
with the merged trees; the fountain-view door is not a texture error (shade and overcast sky in the source).

Night: distance haze (r_tworldHaze) and local lights (r_tworldLamps, 53 lamps from the source) added, commits
44293a9fa and f75f34b4a; player scale shots look right. 1080p with everything on: 310-339 FPS in two runs while
another session's game was running.

Open: nobody has walked the whole map; a benchmark on an idle machine; the lamp lighting is not shown in a
before/after picture.

2026-11-25 late night: ground rebuilt at the source's resolution (docs: UPDATE_scatter_collision.md section 7,
picture ref\cmp_ground3.jpg). Engine commit "ground with full-resolution tiling layers" on naboo-theed
(eighteen local commits, clean). About 0.5 GB more GPU memory for ground textures; not re-benchmarked.
Backup: the user wants naboo-theed pushed to a separate PRIVATE repository (not origin). History checked: only
source files, largest blob 23 MB, no configs or assets. Waiting for the user to create the empty private repo.

Divergence naboo-theed vs origin/NicJK_Unlimited (ff7f7ecd8), measured 2026-11-25 ~23:35, read-only:
merge-base 798e4390a; naboo-theed 18 commits ahead (head 83d847886, plus uncommitted renderer work in progress:
second UV set, billboards, sky occlusion, hemisphere ambient, indoor glow), main 13 ahead. Files changed: 17 on the
naboo side (all under codemp/rd-vulkan except codemp/server/sv_main.cpp), 12 on the main side; NONE changed on both.
`git merge-tree --write-tree` of the two heads completes without conflicts. Nothing merged or rebased.

2026-11-26 ~00:40: naboo-theed head 7111cfdcc (lighting, occlusion, billboards, second UV set), pushed to the
private backup remote; worktree clean. Docs: naboo/docs/UPDATE_lighting_doors.md. Palace entrance door opens in
game; 77 spawns (15 in the palace). Stats doc for the map colleague: https://claude.ai/artifact/R1vMteASrq14io3uhiva3w
Still on the old names: devgame_naboo/taystjk, fs_game taystjk, taystjk.x86_64.exe from build_naboo.
Next: rename to nicjk, merge NicJK_Unlimited into naboo-theed.
