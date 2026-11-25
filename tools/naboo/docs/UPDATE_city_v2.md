# Update 2026-11-24 (late): corrected materials, file version 2, whole city

This note records the latest step. `RENDERER.md`, `WORLD_FORMAT.md`, `ASSET_PIPELINE.md`, `BENCHMARKS.md` and
`TODO.md` still describe the earlier v0 state and need this merged in.

Engine: branch `naboo-theed`, commits `d555f9291` and `1275a19cc` (local, not pushed). Built and run.

## Materials

`tools\material_survey.py` dumped every node graph. The base colour of the game shaders is `texture x tint`,
layered by masks; the first exporter followed every input and landed on masks and packed maps. The exporter now
walks only colour-carrying inputs (`eval_color` in `tools\export_region.py`) and returns the base-colour image and
a constant tint. Heuristics, not verified against Blender renders: a mix driven by a mask keeps side A if it has a
texture, otherwise blends constants with weight 0.3; scalars multiplied in count as 1; a textured material whose
tint is darker than 0.30 luminance is lifted to that floor; tints get a 1/2.2 power in the cooker. Cut-out is kept
only when alpha really comes from an image alpha channel (44 materials became opaque).

Whole scene, 1,685 materials on exported meshes: 1,435 opaque, 182 cut-out, 25 blended (dropped), 43 invisible
(dropped); 1,586 have a base-colour image (207 distinct images); 1,285 have a non-neutral tint.

## File version 2 (`tools\cook_v1.py`, `tr_tworld.cpp`)

| Section | Change from version 1 |
|---|---|
| Header (112 bytes) | adds `float sunDir[3]`, `sunColor[3]`, `ambientColor[3]`, `u32 reserved[4]` after `unitsPerMetre` |
| Materials (80 bytes) | `char shader[64]`, `float tint[3]`, `u32 flags` |
| Meshes (60 bytes) | `u32 firstVert, numVerts, firstIndex, numIndexes, numLods`, `u32 lodFirstSub[3]`, `u32 lodNumSubs[3]`, `float center[3], radius` |
| Others | unchanged |

Renderer additions: tint and sun/ambient shading through `rgbGen lightingDiffuse` with a private lighting uniform
per placement and tint (no new SPIR-V); up to 3 detail levels per mesh chosen by radius / distance
(`r_tworldLodSize1` 0.12, `r_tworldLodSize2` 0.035); placements below `r_tworldCullSize` 0.004 skipped;
`r_tworldLight` scales brightness; the per-frame buffer is asked to grow if the uniforms do not fit (not needed in
the runs below).

## Whole-city export and cook

Region `city` = every visible mesh object under 200 m: 17,038 objects, 719 meshes, plus the near-terrain height grid.

| Step | Time | Output |
|---|---:|---|
| Geometry dump + 1,000 generated detail-level meshes (Blender Decimate at 30 % and 8 %) | 1,141 s | 554 MB |
| Textures (208 PNG) | 32 s | 391 MB |
| Cook | 37 s | `naboo_theed.tworld`, 268,452,584 bytes |

Cooked: 836 meshes (144 are 128 m terrain tiles at 2 / 8 / 32 m spacing), 744 with a second level and 543 with a
third, 16,551 placements, 374 materials using 208 shaders, 6.41 M vertices, 5.16 M triangles over all levels.
Placed triangles: 43.0 M at full detail, 4.29 M at the lowest levels. Engine load time 8.7-12.5 s.

## Benchmark (RTX 2070, rd-vulkan, 1920x1080 windowed, vsync off, uncapped, spectator, no bots)

750 logged frames per position, two cycles. Raw log `..\export\city\client_bench_v1.qconsole.log`; screenshots
`..\export\city\shots_v1\`.

| Position | FPS cycle 1 | FPS cycle 2 | ms avg / p99 / max (cycle 2) |
|---|---:|---:|---|
| p1 street level | 278 | 286 | 3.50 / 6 / 9 |
| p2 street level | 154 | 137 | 7.28 / 11 / 13 |
| p3 street level, long view | 192 | 190 | 5.27 / 9 / 10 |
| p4 above the roofs | 327 | 336 | 2.98 / 5 / 6 |
| p5 overview of the whole city | 126 | 136 | 7.37 / 11 / 13 |

The frame log has whole-millisecond resolution: about +-15 % at these frame times. Per view the pass drew roughly
2,000-7,700 placements, 3,800-14,600 draw calls and 2.4-5.7 M triangles (statistics lines from an earlier
screenshot run and this one). Draw calls are now the main cost, so GPU instancing is the next real gain.

## Not done or wrong

| Item | State |
|---|---|
| Collision | **prototype region only**: `naboo_theed.bsp` is a copy of the 150 x 150 m prototype collision BSP. Elsewhere there is nothing to stand on. No bots were run on the whole city |
| Ground | plain colour. The scene's baked terrain colour map is neutral grey inside the city and rendered white when used (cause not investigated); disabled in the cooker |
| LOD artefacts | thin objects (cables, ropes) can become long spikes at lower levels; one is visible in a street-level screenshot. Levels switch by size only and pop |
| Water, glass, decals, lamp glow | blended materials are not exported; canals are empty |
| Sky, far terrain, backdrop | not exported |
| Shadows, player lighting | none; players use the fallback light |
| Scale | still the provisional 39.37 units per metre; for the user to judge in game |
| Textures | 207 PNGs loaded as RGBA8, capped at 2,048 by the engine |
