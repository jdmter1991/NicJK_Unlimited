# Update 2026-11-26 (night): ground, buildings, palace interior, far trees, doors

Engine: branch `naboo-theed`, newest commits `83d847886` (ground) and `7111cfdcc` (lighting, occlusion,
billboards, second UV set). Both are in the private backup repository `NicJK_Unlimited-naboo-backup`; nothing
went to the public repository.

Comparison sheets (source render left, game right) are in `..\export\city\ref\`:
`cmp_ground3.jpg`, `cmp_buildings6.jpg`, `cmp_palace5.jpg`, `cmp_round4.jpg`. Game shots: `..\export\city\shots_v17` .. `shots_v27`.

## 1. Why buildings looked flat, and what changed

| Cause | Fix |
|---|---|
| **Brick and stone-course walls baked to a plain colour.** The bake only kept textures that repeat a whole number of times per UV unit; the brick sheet repeats 1.5 times and its banding mask 0.375 times, so both were replaced by their mean. | `bake_materials.py` picks a UV period of 1, 2, 3, 4, 6 or 8 units per material; 196 materials now bake over a larger span (128 at 4, 36 at 2, 32 at 8) and 267 keep a full-resolution tiling layer (was 117). The cooker shifts and scales the mesh UVs to match. |
| **One ambient colour everywhere.** | Ambient light now comes from a sky / ground hemisphere and uses the normal map: walls 0.85, floors 1.15, undersides 0.5. |
| **No occlusion.** | Two bakes: sky occlusion per placement (`bake_sky_occlusion.py` -> `.tsky`, 29,726 placements) and ambient occlusion per vertex of each mesh (`bake_vertex_ao.cpp` -> `.tao`, 8.8 M vertices, 125 s). |
| **Normal maps missing on 201 materials.** 87 use the second UV set for colour and the first for the normal map; 114 feed a height map through a Bump node. | Second UV set in a side file (`.tuv2`, 82 source meshes); normal maps generated from the height maps with the source's own Bump strength and distance (`bump_survey.py`, `gen_bump_normals.py`). |
| **Rough metals came out black** (palace columns are metallic in the source). | Rough metals scatter the light a non-metal would receive. |

Not the cause: the sun / ambient balance. The source is softly lit (overcast); darkening the ambient light matched
two views numerically and made the street views worse, so it was put back near the original
(sun 0.54 0.49 0.445, ambient 0.33 0.355 0.395).

Still different: shaded street fronts are somewhat darker than the source in `cmp_buildings6.jpg`; the patinated
copper panels (a metal) read lighter and flatter than in the source.

## 2. Palace interior

Reference: the separate file `NabooPalace_05_packed.blend` (same objects at the same positions as the main scene:
3,167 of 3,245 matched by name, 99.9 % within 5 cm; one sun and a sky). The main scene's palace is unlit.

* Enclosed placements get ambient x `r_tworldIndoor` (default 0.55), tinted warm, and no direct sun (the baked sun
  shadow map let the sun flood the palace floors).
* Window panes (glass materials) show bright daylight to a viewer who is indoors; the renderer estimates that
  from the occlusion of the placements around the camera.
* Fixtures whose emission the daylight scene sets to nearly zero (wall and ceiling lights, 312 placements in the
  palace) glow where the sky is occluded.
* 15 spawn points on four storeys (`add_palace_spawns.py`); 77 in total.

Not matched: the sun patches under the windows of the reference (direct sun is off indoors); one floor area near
the columns is still too bright.

## 3. Doors

`build_doors.py` -> `doors.json`, MD3 models and `shaders\naboo_doors.shader`; the cooker leaves those placements
out, `write_collision_bsp.py` removes their static collision (524 triangles) and adds one brush model and a
`func_door` entity per leaf.

* Palace entrance: two leaves, each 3 m x 20 m, sliding apart. The source object also contains a blasted-open
  "destroyed" variant; it is dropped.
* One solid leaf inside the palace. The other 41 "door" objects there are frames without a leaf: those doorways
  were already open. City doors are untouched.

Seen in game (`shots_v27\door_test2.jpg`): the entrance opens when a player steps up to it and the hall is visible
through it. **Not seen:** the doors closing again, the interior leaf moving, bots passing. The door models use a
fixed shade instead of the world's lighting.

## 4. Far trees, water, ground

* Backdrop trees and bushes are camera-facing billboards, as in the original game; a static Blender scene cannot
  do that, and up close the source shows the same flat cards (`cmp_round4.jpg`, middle row).
* Water: the canal west of the city exists in the port; it was hidden by oversized trees in one view. The 23
  fountains and the remaining water patches were NOT audited one by one.
* Ground: see `UPDATE_scatter_collision.md` section 7.

## 5. Measurements and open points

* 1920 x 1080, before this night's lighting changes: 312-333 FPS, 4.6 GB GPU memory in use, another game
  server running. **Not measured again** with occlusion, hemisphere ambient and billboards.
* New cvars: `r_tworldIndoor` 0.55, `r_tworldAO` 0.6. Bake order after every cook: `bake_vertex_ao`,
  `bake_sky_occlusion` (both depend on the cooked file; the game refuses a side file whose counts do not match).
* The sun shadow map predates the billboard trees (they cast as flat lines in a rebake).
* A crash was introduced and fixed on the way: the occlusion loader read the file header after its buffer had
  been released.

## 6. Frame-rate correction and optimisation (2026-11-26, about 02:30)

**Every frame rate in these notes up to this point is twice the true value.** They were derived from counting
console `wait` commands as frames, but the client runs the command buffer twice per frame (`Com_Frame`), so
`wait N` lasts about N/2 frames. "312-333 FPS at 1080p" was about 155-165. The in-game counter was right.
Frame rates now come from the renderer itself: `r_tworldStats 1` prints frames per second and the CPU time of the
cooked-world pass once a second (`tools\run_stat.sh`, `run_stat_bots.sh`, `stat_from_log.py`).

2400 x 1350 window, RTX 2070, dedicated server with 31 bots, playing in third person, medians:

| Spot | Before | After |
|---|---:|---:|
| Palace hall | 103 | 110 |
| Palace steps | 218 | 195 |
| Market | 120 | 138 |
| Lantern court | 111 | 137 |

What changed (engine):
* placements are culled once per view instead of once per pass, from a compact record, without square roots:
  4.0 -> 0.85-1.8 ms per frame in the hall;
* the "is the viewer indoors" estimate runs every eighth frame (0.8 -> 0.05 ms);
* the opaque pass is drawn front to back (counting sort on distance): hidden fragments are rejected before shading;
* surfaces facing away from the sun skip the 16 shadow-map lookups;
* interior visibility (`maps\naboo_theed.tportal`, `r_tworldPortal`, `tools\write_portals.py`): inside the palace box
  the city is drawn only through the three front doorways; 23,900 -> 3,900 placements in the hall view. Checked on
  35 interior views with the test off and on: 33 identical, 2 differ in under 0.3 % of the pixels;
* default detail thresholds slightly tighter: `r_tworldCullSize` 0.0055, `r_tworldLodSize1` 0.15, `r_tworldLodSize2` 0.045.

**Not reached:** 125 FPS in the palace hall with 31 bots (110 median, minimum about 100), and minima elsewhere dip
to about 128. Screenshots taken at the moment of capture read lower still (82-131). Not measured: 1440p
fullscreen, 4K, 32 bots, the visual effect of the tighter detail thresholds.

## 7. Rivers and spawn points (2026-11-26, morning)

**Rivers.** A bot was seen leaving the big river through a wall. Two causes found and fixed in
`tools\build_collision_terrain.py`:
* *No river bed.* Over 72,105 m2 the source terrain lies more than 3 m under the water plane, in places 206 m
  (the source only shows the surface). A player sank through the 12 m water volume, fell onto ground far below
  the city and walked up inside it. The collision bed is now never deeper than 3 m below the surface.
* *Walls ending above the bed.* 2,684 wall edges (2.57 km) end under water but above the ground, 87 of them by
  more than a player's height. Each has a collision skirt down to the bed now.
Checked in game: a player dropped at 24 river points, including two where it had fallen through before, stays
within 63 units of the surface at every point with visible water. Not checked: the exact wall where it was seen.

**Spawn points** (`tools\add_palace_spawns.py`, `tools\fix_spawns.py`): 108 in the BSP.
* Palace: 12, on two storeys. Spots under the flights of the grand staircase are rejected now (the nearest
  ceiling must be level over a 120-unit circle); viewed one by one in `shots_v30\spawns_palace.jpg`.
* Forecourt and the streets around the palace: 24 new ones on open, flat ground.
* Cafes: 10, one beside each group of outdoor chairs and tables.
* The 64 older city spawns are unchanged; none has a drawn or collidable surface above it.

## 8. Courtyard inlay, chandeliers, vines, music (2026-11-26, about 11:30)

* **Courtyard "chessboard".** The black meander on the palace landing is 17 colour-decal planes
  (`o_nab_decalplane_01`, material `SS_Naboo_DecalColor_01`). The source mixes them over the paving at 15 %
  (Mix Shader factor, read with the new `tools\inspect_material.py`); the export does not carry that factor, so
  they were drawn solid. `cook_v1.py` now gives such decals 15 % opacity (`decal_color_opacity`). Compared with
  `ref\ref_gnd_court_a.png` in `ref\cmp_ground_v33.jpg`: the inlay is a faint tint, as in the source.
* **Chandeliers.** Read from `NabooPalace_05_packed.blend`: the crystals are glass, the candles a plain warm
  emission (1.0, 0.888, 0.6). The port drew the crystals as opaque white shapes. Now: crystals translucent glass
  (`crystal_glass_materials`, 30 % opacity), candles solid and self-lit in the source's colour. Seen from below in
  `shots_v34\final_check.jpg`. Not compared pixel for pixel with a render of the palace file.
* **Lamp glass** of the indoor wall and ceiling fixtures is opaque and self-lit (it was a see-through additive glow).
* **Vines and other growth on walls** no longer sway: 77 materials used only by meshes with "vine" in the name
  (`no_sway_meshes`). The sway bends a plant about its base, which pulled them off their walls.
* **Paving** of plazas, landings and quays is projected from world position like in the source (12 materials),
  instead of stretched over each mesh's UVs. Fill water no longer leaves an open trench in the garden.
* **Windows.** Outward panes imitate daylight for a viewer indoors; panes between rooms and windows that stand
  open are clear glass. The interior-visibility file may list up to 256 openings (doors always, the 24 nearest
  windows within 3000 units).
* **Music and name.** Worldspawn: `"music" "music/naboo_theed/naboo_theed_music.mp3"`, `"message" "Naboo: Theed
  by Nic Angel"`; `scripts\naboo_theed.arena` and `levelshots\naboo_theed.jpg` added. The log shows the track
  found and started; nobody listened to it.
* **Other map on this build:** `mp/ffa3` loads and draws correctly (`shots_v34\stock_ffa3.jpg`), no errors in the log.
