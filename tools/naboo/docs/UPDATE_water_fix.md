# Update 2026-11-25: missing water in the rivers

Cooker-only change (`tools\cook_v1.py`, `tools\water_check.py`); no engine change, no new commit.
Map of the problem: `..\export\city\water_map.png`. Screenshots after the fix: `..\export\city\shots_v7\`.

## What was wrong (measured)

`tools\water_check.py` rasterises the two water meshes on a 2 m grid (850,241 samples, 3.40 km2) and compares the
water surface with the terrain height under it.

| Finding | Number |
|---|---|
| Water at or below the terrain at full resolution | near terrain 57.9 %, far terrain 49.8 % |
| Near terrain: split is clean | 55 % more than 1 m below ground (the mesh extends under the land), 40 % more than 0.5 m above, under 5 % in between |
| Far terrain: not clean | 12 % of the water within 1 m of the terrain surface (median depth 0.04 m): the 16 m terrain grid cannot resolve the river beds |
| Coarser terrain detail levels bury more | far terrain hidden share 49.8 % -> 58.6 % (64 m spacing) -> 71.4 % (256 m); near terrain 58.0 % -> 66.1 % (32 m) |
| The source water mesh has gaps | the rivers are separate patches that do not meet: thin dry slits cross them (white breaks in `water_map.png`) |
| A pond west of the city | entirely 0-2 m under the coarse far terrain, so not drawn at all |

So there were three separate causes of "missing water patches": gaps in the source mesh, river beds the coarse
terrain does not carve, and terrain detail levels filling the rivers in at distance.

## Fix

| Step | What the cooker does | Result |
|---|---|---|
| Close gaps | morphological closing of the water raster, carrying the surface height: gaps up to 16 m everywhere, up to 56 m outside the near terrain (inside the city a wide closing would flood islands and quays). New cells become generated water quads | 4,213 + 12,500 cells = about 66,900 m2 of added water, 2,550 quads in a `__water_fill` mesh |
| Carve | terrain vertices are lowered to 1 m below the water wherever the water is at or above the ground, or within a tolerance below it (0.3 m near, 2 m far); on the far grid also vertices within 8 m of such water | 46,498 near and 4,293 far vertices lowered |
| Keep rivers open in detail levels | a coarse-level vertex takes the lowest carved height in its neighbourhood, so a river narrower than the spacing is not filled in | applies to all three levels of both terrains |

Check after carving, by the same sampling: of the water meant to be visible, 0 near samples and 2,156 of 464,796
far samples (0.5 %) are still under the full-resolution terrain; those are river edges between a carved and an
uncarved 16 m vertex.

Looked at in the engine from five distant high viewpoints and from directly above the city (`shots_v7\`): the
rivers are continuous, the break that remained with the 16 m setting is closed, the ponds and the western lake
are drawn, the city canals are full.

## Limits

* The far rivers are a few metres wider than in the source where vertices next to the water were carved.
* The generated water is flat per row of cells; where it bridges two patches at different heights there is a step.
* Overlapping source patches still draw twice (lighter patch), because the blended pass is not merged or sorted.
* Collision is unchanged: the BSP terrain is the uncarved one, so the ground under shallow water is up to about
  1 m higher for players than it looks. Rivers outside the collision bounds have no collision at all.
* Checked from above and from a distance, not by walking the banks.
