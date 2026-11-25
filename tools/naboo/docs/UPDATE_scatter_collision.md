# Update 2026-11-25 (late evening): the whole terrain scatter, placement culling, collision with river beds and water

Engine: branch `naboo-theed`, fifteen local commits, newest `28fd8f74a` (placements culled by grid cells);
nothing pushed. Views: `..\export\city\shots_v14\`, side by side with the source `ref\cmp_scatter.jpg`.

## 1. Scatter: everything the source places on the terrain

`tools\export_scatter_materials.py` exported the 18 materials only the scatter uses (same `material_info` as the
region export) and their textures. The cooker now adds all 21 scatter meshes, none skipped:

| Kind | Source instances | In the port |
|---|---:|---|
| Leaf litter, twigs (Naboo and Takodana), trimmed grass, street debris, flowers, torn branches, oranges, droid wreck parts | 58,003 | one placement each of a shared mesh; lower detail levels keep 25 % and 6 % of the cards |
| Backdrop trees, bushes and ground branches on the near terrain (6-14 triangles each) | 78,180 | merged into 1,165 chunks of 64 m |
| Backdrop trees and bushes on the far terrain (the forested hills) | 547,750 | every fourth kept and drawn twice as large (136,893), merged into 428 chunks of 512 m |

Merged chunks use a twin of each material without the sway animation: a chunk has no single plant base to sway
about. The world file has 76,945 placements, 14.0 M vertices, 622 MB.

`ref\cmp_scatter.jpg`: the hills around the city are wooded as in the source.

## 2. Placement culling (commit `28fd8f74a`)

Every placement used to be tested against the view each frame. They are now sorted into grid cells at load
(small ones, radius up to 160 units, in a 1024-unit grid; the rest in an 8192-unit grid); a cell is rejected as a
whole by the view frustum and, when even its largest placement would fail the size test, by distance.

| 1920 x 1080, five positions, 14,900 frames per pass | FPS |
|---|---:|
| 47,820 placements, before | 382-438 |
| 47,820 placements, with cells (584 cells) | 621-710 |
| 76,945 placements, with cells (801 cells) | 426-452 |

GPU memory in use with everything: 4.8 GB of 8 GB (whole system). Logs: `..\export\city\client_bench_v14.qconsole.log`.
A small game of another session was running during these runs.

Reading: the last step costs frame rate again although placements are culled; that is the scatter being drawn
(triangles and draw calls), not the test loop. Not broken down further.

## 3. Collision: terrain as drawn, river beds, water

`tools\build_collision_terrain.py`:

* removes the old terrain triangles from the collision set (all 247,932 recognised by their grid positions);
* builds the terrain again from the grid the renderer draws, i.e. carved under visible water, in 2 m blocks where
  the 1 m heights lie within 5 cm of the block's two triangles and in 1 m cells elsewhere: 108,230 blocks at 2 m,
  17,174 at 1 m, 353,852 triangles. Steps, kerbs and river banks are exact; flat areas stay cheap;
* writes 2,153 water volumes (21,085 water cells of 2 m merged along rows, 12 m deep).

`tools\write_collision_bsp.py` adds the volumes as brushes with water contents and drops spawn points that are
under water or have no ground within 96 units (2 of 64; they stood on terrain that is now river bed).

| | Before | Now |
|---|---:|---:|
| Collision triangles | 1,143,536 | 1,249,456 |
| Brushes | 817,197 | 899,362 (2,153 water) |
| Time to write the BSP | 35 s | 38 s |
| File | 258.7 MB | 279.2 MB |
| Spawn points, all with ground | 64 | 62 |
| Solid behind sampled triangles | 98.6 % | 98.8 % |
| Walkable-size floors without solid | 0 of 1,408 | 0 of 1,633 |
| 32 bots, server frame | (see earlier notes) | 2.7-3.2 ms |
| Kills / stuck jump-outs / stuck suicides / ledge hops, about 175 s | | 57 / 6 / 1 / 75 |
| Bots found inside solid / drowned | | 0 / 0 |

`maps\naboo_theed.bsp` is the new file; the previous one is `naboo_theed_before_water.bsp`.
Log: `..\export\city\server_water32.qconsole.log`.

**Not checked:** nobody has waded into a river in a client, so the water volumes are verified only by the file's
contents (shader with water contents, 2,153 brushes, surface heights) and by bots not drowning. Swimming, splash
sounds and the under-water view were not looked at. The river bed is 1 m under the surface where the terrain
was carved and deeper where the source terrain already was.

## 4. Open

* A clean benchmark on an idle machine, and a breakdown of what the scatter costs to draw.
* The fountain-view door material; lamps lighting their surroundings; distance haze on geometry.
* The sun shadow map predates the scatter and the chunked trees (they cast no shadows yet).
* Walk the map in a client: scale, rivers, collision at doors and stairs.

## 5. Follow-up the same evening

* **Door in the fountain view: not a texture error.** The window and door family's formula is the texture times a
  constant; the door looks darker in the source because that view lies in shade under the overcast sky.
* **Rivers checked in a client** (`..\export\city\shots_v14\river_player.jpg`): a player teleported onto a carved
  river bed swims, and the game draws its own water rings, so the water volumes are recognised. The bed is 1 m
  under the surface, which is swimming depth for the player model, not wading depth.
* **Solid canopy cards only at the farthest detail level.** Smaller trees reach the middle level a few metres
  away, where the solid cards showed as dark sheets. Side effect: trees inside the city look a little thinner
  from the overview camera than in `shots_v13`.
* **Backdrop tree texture exempt from the coverage boost** (`foliage_alpha_gain_overrides`); with the boost its
  cards were almost solid. Those billboard trees still look like flat sheets from a few metres: they are the
  source's distance trees, placed on the outskirts.
* **Sun shadows rebaked** (1,370 s) with the merged trees as casters; placements under 120 units radius (69,587,
  the ground scatter) cast nothing. Views: `..\export\city\shots_v15\`, `ref\state_v15.jpg`.
* **Benchmark, not clean.** Another session's game was running and the machine was visibly slower than earlier
  in the evening (one map load took 48 s instead of 6 s). 1920 x 1080, same passes: 298-363 FPS with the default
  `r_tworldCullSize 0.004`, 339-392 FPS with 0.012 (small placements dropped three times earlier). So the small
  scatter costs on the order of a tenth of the frame; the earlier 426-452 FPS for the same content shows how
  much the machine state moves these numbers. A clean run is still owed.
  Logs: `..\export\city\client_bench_v15_cull0.004.qconsole.log`, `..._cull0.012.qconsole.log`.

## 6. Haze, lamps, player scale (same night)

Engine commits `44293a9fa` (distance haze) and `f75f34b4a` (local lights); seventeen local commits on
`naboo-theed`, nothing pushed.

* **Distance haze** (`r_tworldHaze`, default 110000 = the distance in world units at which half the view is haze;
  0 = off): geometry fades towards the sky's horizon colour, additive glow fades out. `ref\cmp_haze.jpg`: with it
  the far hills dissolve into the sky as in the source; without it they stand out dark with a hard edge.
* **Local lights** (`r_tworldLamps`, default 1; 0 = off): `tools\write_lights.py` writes `maps\naboo_theed.tlights`
  from the source's light objects, 53 of 78 (the sun and the 24 glows that belong to fire effects left out;
  spot and area lights treated as point lights). Each frame the four nearest the camera are passed to the
  shader and added to the diffuse light on both shading paths.
  **Not demonstrated:** the before/after shot landed against a wall, and in daylight the effect is weak; the
  code runs without artefacts in the standard views, nothing more is claimed.
* **Player scale** (`..\export\city\shots_v16\player_scale.jpg`): the test character next to a fence, a flower pot,
  the fountain and an arcade. Balustrades come to about chest height, doors and arches are a few player heights
  tall; at 39.37 units per metre this looks right. Still one person's reading of four pictures.
* **Benchmark**, two runs, everything on (shadows, PBR, lamps, haze), 1920 x 1080: 310-339 FPS in every pass of
  both runs. Another session's game was running (CPU at 34 % before the start), as in the previous round, so
  this is a consistent figure for the shared machine, not a clean one. The same content measured 426-452 FPS
  earlier in the evening. Logs: `..\export\city\client_bench_v16_run1|2.qconsole.log`.

## 7. Ground at the source's resolution (2026-11-25, night)

Engine commit: see `git log` on `naboo-theed` ("ground with full-resolution tiling layers"); eighteen local commits.

The source terrain is not one texture: mask images blend twelve tiling textures (stone tiles, concrete, pebble
mosaic, gravel, soil, grass) that repeat every 2-8 m at about 2 mm per texel, times a colour map. The earlier
bake put all of that into one 512 px map per 64 m tile (12.5 cm per texel), hence the blurred paving.

Now, per terrain tile (`tools\bake_ground.py`, then `tools\bake_ground_packs.py`):

* **one layer** (10 tiles, open grass): base map + the layer's own colour texture projected from world position;
* **blended** (566 tiles): base map (the formula with every tiling texture at its mean colour), a weight map
  (RGBA = share of the pixel's light from four layers) and a "pack" texture holding the four layers' brightness
  relative to their mean. The four layers are chosen by contrast x (mean share + peak share in any 8 m block),
  so a small patch of a strong pattern (the pebble mosaic by the pond, 1 % of its tile) is kept.
  colour = base x (1 + sum w_i x (2 x pack_i - 1)).

Only the brightness pattern of the layers is kept in a pack; their hue comes from the base map. Measured on
the paving textures: colour deviates by about 0.01 from brightness x mean colour, brightness varies 0.03-0.18.

40 packs (2048 px for periods up to 8 m, 4096 px for 12 m and 24 m): 342 MB of DDS; 566 weight maps: 191 MB.
That is about 0.5 GB more GPU memory than before; **GPU memory and frame rate were not measured again.**
Pack names are numbered (`gp_00` ...): material texture names are limited to 64 characters, longer names
silently failed to load (ground went dark) in the first attempt.

Result: `ref\cmp_ground3.jpg` (source left, game right; spawn street, pond plaza, fountain court), shots in
`shots_v18\`. Paving joints and slabs are sharp in the street, the pebble mosaic by the pond is present.
Differences that remain: the source's street reads a little lighter and greyer in the sun; ground roughness is
now a constant (the pack's alpha carries the fourth layer instead of smoothness); layers beyond the four chosen
per tile fall back to their mean colour.

Also from this round: `tools\visual_vs_collision.py` (do drawn floors have collision): 85 % of sampled level
surfaces have collision within 4 units, 19 of 5,939 samples have none between street level and 3 m below.
Lamp lighting before/after: `shots_v16\lamps_on_off.jpg`.
