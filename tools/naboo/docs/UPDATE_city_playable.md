# Update 2026-11-25: holes checked, spawns fixed, water, ground and sky

Engine: branch `naboo-theed`, commits `d555f9291`, `1275a19cc`, `bdda4a979` (local, not pushed).
Screenshots: `..\export\city\shots_v2\`.

## 1. Holes: there are none worth fixing

`UPDATE_city_collision.md` said 29 % of the collision triangles "did not become brushes" and that 2.5 % of walkable
triangles might lack collision. Both statements came from weak tests and are corrected here.

| Test | What it really measures | Result on the city BSP |
|---|---|---|
| brush count vs triangle count | nothing about coverage: the compiler does not emit one brush per triangle | 808,403 brushes for 1,143,536 triangles |
| `bsp_ground_check.py` (brush bounding box below a point) | optimistic and pessimistic at once: a neighbour's box can cover a point, and a box can miss a sloped triangle | not conclusive; kept only for the spawn check |
| **`bsp_solid_under_tris.py`** (new): the point 0.75 units behind a triangle's centre is tested against every plane of every candidate brush, the same question the engine's point-contents test answers | exact for the sampled point | 5,000 random triangles: solid behind 98.9 %, neither side 0.8 % |

By kind: floors 0.1 % without solid, ceilings 0 %, walls 0.7 %, slanted faces 2.3 %. By size: triangles thinner
than 1 unit 10.1 %, 1-4 units 1.9 %, **4 units and larger 0.0 %**. Walkable-size floors (facing up, at least 16
units across): **0 of 1,182 without solid**.

So the only geometry missing collision is slivers thinner than a few units, far narrower than a player
(30 x 30 units). No collision change was made. The compiler log confirms it lists such triangles individually
("was not autoclipped").

Limit of the test: one point per triangle, 5,000 of 1.14 M triangles, and nobody has walked the map.

## 2. Spawns

`build_collision_bsp.py` now filters the 1,315 candidates before spreading them out:

| Step | Candidates left |
|---|---:|
| All ground-level candidates | 1,315 |
| In built-up cells (object collision triangles in the surrounding 60 x 60 m at or above the median) | 659 |
| Largest group connected through neighbouring grid points with at most 3 m height step (a stand-in for "reachable"; 29 groups existed) | 607 |
| Chosen by farthest-point sampling | 64 |

All 64 have a brush within 96 units below (origin 35-91 units above it, median 40).

## 3. Sky boundary and recompile

The six hull brushes now carry a sky shader (`textures/naboo_sys/sky`), so the BSP has 6 sky surfaces and the
renderer draws a sky box wherever nothing else is; the hull stays solid and is the map boundary. Recompiled with
the existing q3map2: same 808,403 brushes, 332.9 MB.

## 4. Visual additions

| Item | How | Measured |
|---|---|---|
| Sky | `tools\export_extras.py sky`: the scene's sky rendered with Cycles from an empty scene into six 1,024-pixel faces in the engine's sky-box orientation; exposure -1.0 (0.0 clipped to white in the engine) | 14 s |
| Ground | `export_extras.py terrain`: the terrain material's base colour baked with Cycles to 4,096 pixels over the 1,536 m terrain, split into 2 x 2 tiles of 2,048; terrain tiles use the quadrant texture | 94 s; 0.375 m per texel, so it is blurry underfoot |
| Water | the two large water meshes (canals/sea 3,289 triangles, waterfalls 4,464) exported separately; water materials on fountains and bowls recognised by shader family; drawn as a flat tinted colour at 78 % opacity | - |
| Glass, decals, lamp glow | blended materials are no longer dropped: glass 30 % opacity, decals alpha-blended with polygon offset, emissive materials additive at 35 % | 8 water, 14 glass, 18 glow and 4 decal materials in the scene |
| Renderer | second draw surface for materials flagged as blended, sorted after opaque geometry; placements inside it are not depth-sorted | commit `bdda4a979` |

Cooked file: 269,662,148 bytes, 853 meshes, 16,811 placements, 381 materials (6 blended), load 18 s in the engine
(up from 9-12 s; the textures grew by the four terrain tiles and six sky faces).

## 5. Tests on the final map

Dedicated server, 32 bots, `sv_fps 40`, about 175 s (`..\export\city\server_prof32_b.qconsole.log`):

| Per 25 ms frame, four 30 s windows | Value |
|---|---|
| Total work, average | 3.42 - 3.70 ms |
| Bot AI / game / snapshots, average | 1.2-1.4 / 1.6-2.1 / 0.4 ms |
| Frames over budget | 0, 0, 2, 0 |
| Worst frames | 9.8, 13.7, 34.7 and 426 ms |

Bot counters: 61 kills, all saber; **0 falling deaths** (2 before), 0 suicides (1 before), 2 stuck jump-outs
(13 before), 76 force jumps, 17 gap jumps, 198 ledge hops, 0 bots found in solid.

The long frames: four hitch lines of 169-426 ms, each a single game frame with only about 550 traces taking
0.7-1.6 ms in total. The time is inside game code outside collision, so the map's collision is not the cause.
What it is was not investigated (it may be the same on other maps).

Client, listen server with 8 bots, 1280x720: 96-119 FPS shown in the screenshots at a 125 cap. The earlier
uncapped benchmark (`UPDATE_city_v2.md`) was not repeated with the blended pass and sky.

## 6. Still wrong or missing

* Large white cone shapes near the palace are still drawn (they are not the emissive materials; not identified yet).
* Ground texture is blurry up close; no detail layer. Water is a flat colour without reflection or movement, and
  the blended pass is not depth-sorted.
* A few stray distant objects float outside the terrain; no far terrain or backdrop beyond the near terrain.
* No shadows; players lit by the fallback light.
* Nobody has walked the map; bots have not been watched; unit scale (39.37 per metre) is still for the user to judge.
* The join menu covered several automated screenshots: `team s` must be sent exactly once, after the menu opens.
