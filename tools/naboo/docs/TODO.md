# TODO — Naboo: Theed port

Roadmap: `ARCHITECTURE.md` section 10. Status as of 2026-11-25. Latest results, newest first:
`UPDATE_scatter_collision.md` (whole terrain scatter, placement culling, collision with river beds and water),
`UPDATE_walls_ground_trees.md` (walls, ground, sky, trees and street scatter from the source's formulas),
`UPDATE_water_pbr.md` (comparison with the .blend: water, fence, PBR, glow, foliage, wrong textures, whole-map audit),
`UPDATE_writer_shadows.md` (collision writer level with q3map2, baked sun shadows),
`UPDATE_lighting_bspwriter.md` (player lighting, own collision BSP writer),
`UPDATE_water_fix.md` (missing river water), `UPDATE_dds_terrain_animation.md` (DDS textures, far-terrain fixes,
animation), `UPDATE_instancing_far.md` (GPU instancing, ground detail, far scenery, Vulkan settings),
`UPDATE_city_playable.md` (holes, spawns, water, ground, sky), `UPDATE_city_collision.md` (whole-city collision;
its hole figures are corrected in the newer note), `UPDATE_city_v2.md` (materials, file version 2, whole-city
visuals). The older documents describe the first prototype; `UPDATE_instancing_far.md` predates the far-plane fix
(its far-plane and commit figures are superseded by the later notes).

Rule for this machine (16 GB): before any Blender job, compile or game test, check that no game from
`devgame_dev` is running and wait for it to end, unless the user has said the machine may be shared
(`ALLOW_BUSY=1` for `run_server_test.sh`; then about 5 build jobs at most and 3 GB left free).

## Done

- [x] Phase 1-2 documents: `RESEARCH.md`, `ENGINE_LIMITS.md`, `ARCHITECTURE.md`
- [x] Own worktree `naboo_src` (branch `naboo-theed`, seventeen local commits up to `f75f34b4a`), `build_naboo\`, `devgame_naboo\`
- [x] Export pipeline from Blender: direct dump, materials with tint, generated detail levels, terrain grids, extras (sky, ground bakes, water, detail and ripple textures, far scenery)
- [x] Cooked world file version 2 with a renderer pass in rd-vulkan: tint, sun shading, detail levels, blended pass, GPU instancing, detail layer, animation
- [x] Whole map drawn to the mountains: about 360-510 FPS at 1080p on the RTX 2070, about 1.6 GB GPU memory with BC7 DDS textures
- [x] Water: gaps in the source mesh filled, terrain carved under visible water at every detail level
- [x] Whole-city collision BSP (808 K brushes) with a sky boundary; exact test finds no missing collision on walkable-size floors
- [x] 64 spawns inside the built-up, connected area; 32 bots at about 3.4 ms per server frame, no falling deaths

- [x] Players lit by the cooked world's sun and ambient
- [x] Own RBSP collision writer: merges coplanar triangles and adds edge bevels like q3map2; whole city in 35 s instead of 24 min, same brush count and trace workload, same server cost within a noisy pair of runs
- [x] Baked sun shadows: 6912 x 4420 depth map from the cooked world, soft per-pixel lookup, no measurable frame-rate cost at 720p

- [x] Reference renders from the .blend at game camera positions (`tools
ender_ref.py`, `export\city
ef\`)
- [x] Water after the source: dark mirror-like river, see-through fountain bowls, foam for falls and waterfalls
- [x] Near terrain at the source's 1 m resolution (fixes the mounds along fences)
- [x] Optional physically based shading with the source's normal maps (`r_tworldPBR`), no measurable cost
- [x] Glowing lanterns and light strings; fuller near foliage
- [x] Wrong textures: second UV set (87 materials) and tiled textures (25) fixed

- [x] Walls: 1,233 layered materials baked from their source formulas (437 maps, 69 with a tiling layer)
- [x] Ground: terrain splat formula baked per 64 m tile (476 tiles at 6.3 cm per texel)
- [x] Sky re-rendered with the source's height fog and tone mapping
- [x] Trees: foliage detail levels, foliage light, solid canopy cards at distance
- [x] Street scatter: leaf litter and twigs (30,461 placements)

- [x] Whole terrain scatter: 58,003 placements plus trees, bushes and branches merged into 1,593 chunks
- [x] Placements culled by grid cells in the renderer
- [x] Collision from the terrain as drawn (1 m where needed), carved river beds, 2,153 water volumes

- [x] Rivers checked in a client (player swims); sun shadows rebaked with the hill trees
- [x] Distance haze and local lamp lights in the renderer

## In progress

- [ ] Walk the whole map in a client: doors, stairs, bridges, river banks
- [ ] Benchmark on an idle machine (310-339 FPS at 1080p while another game was running)
- [ ] Show the lamp lighting in a before/after picture, tune its strength

## For the user to do or decide

- [ ] Walk the map and judge the unit scale (now 39.37 units per metre): `devgame_naboo\taystjk.x86_64.exe ... +set cl_renderer rd-vulkant +devmap naboo_theed`
- [ ] Watch the animation and say whether water, trees and curtains need more or less movement
- [ ] `r_ext_max_anisotropy 16` is recommended for this map (no measurable cost); it is a user setting
- [ ] Is ground cover (grass) wanted? Only the "Cloudy" scene exists in this .blend

## Next in the plan

- [ ] Lamps lighting their surroundings (78 light objects in the .blend, none exported); overcast look and haze of the source scene
- [ ] Shadow edges close up
- [ ] Better detail levels (error-bounded, no spikes on thin objects); detail levels for the backdrop cliffs (0.7 M triangles without any)
- [ ] Collision for the carved river beds and for rivers outside the current collision bounds

## Open problems

- [ ] Nobody has walked the map or watched bots on it; collision vs visuals at doors, stairs, railings is unchecked
- [ ] Depth precision at distance not examined in motion (near plane 4, far plane about 2.6 million units, 24-bit depth)
- [ ] Single-frame server hitches of 170-430 ms inside game code (not collision); cause unknown
- [ ] Overlapping water patches draw twice; the blended pass is not depth-sorted; ground bake is 0.375 m per texel under the grain
- [ ] Tints not checked against Blender renders; no separate check for mesh errors beyond the terrain bugs found
- [ ] Benchmarks have no bots or players in view
- [ ] Korriban was never run from `devgame_naboo\`

## Open after the night of 2026-11-26 (see UPDATE_lighting_doors.md)
- [ ] Doors: confirm they close again, the interior leaf moves, bots pass; light the door models like the world
- [ ] Buildings: shaded street fronts still darker than the source; copper panels
- [ ] Palace: sun patches under the windows; one floor area too bright
- [ ] Water: audit the 23 fountains and all water patches one by one against the source
- [ ] Benchmark again with the new lighting; rebake sun shadows for the billboard trees
- [ ] Switch folders and programs to the NicJK names; merge NicJK_Unlimited into naboo-theed
