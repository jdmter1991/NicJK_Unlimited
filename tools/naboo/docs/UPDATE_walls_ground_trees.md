# Update 2026-11-25 (evening): walls, ground, sky, trees and street scatter from the source's own formulas

Engine: branch `naboo-theed`, fourteen local commits, newest `d0d0d69c8`; nothing pushed.
New: `a8246ca89` (tiling colour layer), `d0d0d69c8` (foliage light factor).
All comparisons are against Cycles renders of the .blend from the same cameras (`..\export\city\ref\`,
source on the left of every `cmp_*.jpg`). Final views of this step: `..\export\city\shots_v13\`,
side by side `ref\cmp_v13.jpg`, `ref\cmp_ground_sky.jpg`, `ref\state_v13.jpg`.

## 1. Walls: materials baked from their source formulas

A wall material in the source is a formula: several colour textures, masks, tints, tiling overlays and
world-projected grunge mixed by a node graph. The port used one image times a tint, and for the brick family
that image was the plain plaster layer, not the stone-block texture that actually shows.

* `tools\color_graphs.py` (Blender, read-only) writes the Base Color, Roughness, Alpha and Metallic graph of
  every used material as a nested expression, with exact texture coordinates, and saves every image they use
  (403 images, 647 MB).
* `tools\matexpr.py` evaluates such an expression in numpy, in linear light as Blender does.
* `tools\bake_materials.py` bakes every material whose colour is more than one texture times a constant:
  **1,233 source materials into 437 maps** (1024 x 1024, colour in RGB, smoothness in alpha), none unsupported.
* **Tiling layer.** Where the formula is a colour texture repeating several times over the UV square times
  everything else, baking would blur it. 69 maps therefore store "everything else" and keep the repeating
  texture as a separate layer; the renderer draws base x tile x 2 (commit `a8246ca89`, descriptor set 4).

What a bake cannot contain is replaced by the texture's mean value and listed per map in
`dump\baked\baked.json` (`approximated`): textures at a non-whole scale (not periodic over the UV square), textures
projected from world position (the concrete family's grunge), vertex colours. Dirt on upward faces is evaluated
for a vertical wall, i.e. off.

Result (`ref\cmp_walls.jpg`): sandstone courses, alternating arch stones and carved ornaments in the source's
colours.

## 2. Ground: the terrain's splat formula per tile

The source terrain mixes twelve tiling textures (four kinds of stone tiles, gravel, concrete, rubble, grass, mud,
soil) by four 3072 x 3072 mask images and multiplies by a colour map. `tools\bake_ground.py` evaluates that in
world space per terrain tile of 64 m: 476 tiles with hard surfaces at 1024 x 1024 (6.3 cm per texel), 100 soft
tiles at 256 x 256, each with a 4-texel border of its surroundings so neighbours meet without a seam.
The cooker now cuts the near terrain into those 576 tiles. Smoothness is in alpha, so paving has its own
roughness on the physically based path.

Bake time was 58-76 minutes per third while another project's job used all cores; the first version sampled
each mask once per channel and was several times slower still (fixed with a sample cache).

## 3. Sky

The first sky bake rendered only the world background with the "Standard" view transform: a saturated blue sky
with 12-41 % of some faces clipped to white. The source shows that background through its height fog with the
AgX view transform. `tools\bake_sky.py` renders the six faces with only the height fog kept and the scene's own
view settings: soft, hazy, nothing clipped. The first faces are kept in `dump\extras\sky_first_bake\`.
(A first attempt with a looser filter let lamp posts and trees into the faces; discarded.)

## 4. Trees

Three separate causes, found one after the other:

1. **Detail levels.** Mesh decimation destroys leaf cards. The lower detail levels of foliage now keep a share
   of the cards (60 % and 25 %) and enlarge each kept card by 1 / sqrt(share); trunks still come from the
   decimated mesh. 132 meshes, 239,070 cards.
2. **Light.** The source's leaf colour is just the texture; its canopies are dark because leaves shade each
   other. `r_tworldFoliageLight` (default 0.6) reduces the ambient light on swaying vegetation, and the sun by
   half as much.
3. **Solid canopy cards.** 11 canopy and foliage-card materials have a constant alpha of 1 in the source: the
   big tree crowns are opaque cards there. Drawn opaque everywhere they read as flat green polygons close up,
   so the nearest detail level keeps the cut-out and the lower ones use an opaque twin of the material.
   (10 banner and curtain materials with constant alpha are now simply opaque.)

Result: leafy and darker up close, dense dark masses from above and at distance (`ref\cmp_canopy.jpg` shows the
all-opaque intermediate state; `ref\state_v13.jpg` the final one).

## 5. Street scatter ("grass")

The source generates its ground cover with a geometry-nodes scatter on the terrain, switched off for the
viewport, which is why earlier exports never saw it. `tools\export_scatter.py`: 683,923 instances of 21 meshes.

| On the near terrain | Instances | Triangles each | In the port |
|---|---:|---:|---|
| Leaf litter | 25,108 | 362 | **added** |
| Twigs (Naboo) | 5,212 | 782 | **added** |
| Droid wreck parts b, c | 141 | 5,216-7,976 | **added** |
| Twigs (Takodana) | 18,714 | 923 | material not exported |
| Ground branches | 25,213 | 13-14 | material not exported |
| Trimmed grass | 7,400 | 268 | material not exported |
| Backdrop trees and bushes | 52,967 | 6-12 | material not exported |
| Street debris, flowers, torn branches, oranges, wreck parts a, d | 1,388 | | material not exported |

On the far terrain: 342,292 backdrop trees and 205,458 bushes (the forested hills of the source); not added.

The added meshes are ordinary placements of one shared mesh (no extra geometry memory); being small, the renderer
shows their thinned detail levels from a few metres on. The world file now has 47,820 placements.

## 6. Cost

| | Before this step | Now |
|---|---:|---:|
| 1920 x 1080, five positions, 14,900 frames per pass | about 450-550 FPS | 382-438 FPS |
| The same before the scatter was added | | 466-532 FPS |
| GPU memory in use while running (whole system) | not measured | 4.3 GB of 8 GB (before the scatter) |
| Textures on disk, BC7 | 612 MB, 446 files | 1.7 GB, 1,457 files |
| World file | 402 MB | 453 MB |
| Placements | 16,927 | 47,820 |

The drop comes with the 30,000 scatter placements: every placement is tested on the CPU each frame.
Log: `..\export\city\client_bench_v13.qconsole.log`. A small game of another session was running on the
machine during the benchmark.

## 7. Open

* The remaining scatter needs its materials and textures exported (one more Blender pass), then the same cook
  step; the far backdrop trees need a batched form, not 548,000 separate placements.
* Placement culling on the CPU should become hierarchical before more scatter is added.
* The sun shadow map was not rebaked after the scatter and the canopy changes (geometry of the nearest detail
  level is unchanged, so existing shadows are still right; leaf litter casts none).
* Collision still uses the 2 m terrain and has no river beds or water volumes.
* The fountain-view door is still a flat teal with dark stripes (`ref\cmp_v13.jpg`, lower right); the source's
  is dark and panelled. Not investigated.
* Paving looks soft at shallow angles with the default anisotropy of 2; `r_ext_max_anisotropy 16` is a user
  setting.
* GPU memory is the next limit: 476 ground tiles at 1024 and 437 wall maps. `hard_share` in `naboo_config.json`
  decides how many ground tiles get the high resolution.
* Lamps still do not light their surroundings; no distance haze on geometry, only in the sky.

## 8. Rebuild order

`color_graphs.py` (Blender) -> `bake_materials.py --part i/4` x 4, then `--merge` -> `bake_ground.py --tiles ...`
in parts, then `--merge` -> `cook_v1.py` -> `convert_textures_dds.py` -> `bake_sun_shadow.py` when geometry of the
nearest detail level changed. The `_apply_patch_*.py` files record every cooker and engine change of the day.
