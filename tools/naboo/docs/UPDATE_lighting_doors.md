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
