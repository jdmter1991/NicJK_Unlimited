# Update 2026-11-25 (morning): player lighting, own collision BSP writer

Engine: branch `naboo-theed`, eight local commits, newest `ab9ed5cde`; nothing pushed.
Rule followed for every build and test in this step: no game from `devgame_dev` was running.

## 1. Player lighting

The collision BSP has no light grid, so players and other models were lit by the engine's flat fallback
(ambient 150, light from a default direction). `R_SetupEntityLighting` now asks the cooked world first
(`R_TWorldEntityLight`): entities get the same sun direction, sun colour and ambient colour as the buildings, and
both shaders use the same response curve. Commit `ab9ed5cde`.

Checked with a third-person screenshot on `naboo_theed` (`..\export\city\shots_v8\`): the character is shaded
consistently with the scene. This is also the first picture of a player next to the geometry: steps, columns
and arches look plausibly sized at 39.37 units per metre, but that is one view and the scale is still the
user's call.

Limit: no occlusion. A player under an arcade is lit like one in the open, because the world has no shadow
information yet.

Useful side finding: `ui_openmenu <any non-existent name>` closes the join menu reliably, which removes the timing
problem that spoiled many automated screenshots.

## 2. Own collision BSP writer (`tools\write_collision_bsp.py`)

Writes an RBSP version 1 file straight from the collision triangles, with no map compiler:

* one convex brush per triangle (the triangle extruded 4 units behind its plane, clipped to its bounding box),
  sides stored with the six axial box planes first, as the engine's `CM_BoundBrush` requires;
* six sky slabs around everything and six sky quads on their inner faces, referenced from every leaf;
* a kd-tree over brush bounds (median splits, a split is rejected if it would duplicate more than 35 % of the
  brushes, leaves of about 96 brushes; brushes are never cut);
* point entities and worldspawn keys taken from the generated `.map`.

| | q3map2 2.5.17n | own writer |
|---|---:|---:|
| Whole city: time to produce the BSP | 1,467 s | **8.1 s** |
| File size | 332.9 MB | 281.0 MB |
| Brushes | 808,403 | 1,143,291 |
| Leaves / brush references per brush | 2,960 / 1.08 | 36,635 / 2.35 |
| Exact test: solid behind sampled triangles | 98.9 % | 99.9 % |
| Walkable-size floors without solid | 0 of 1,182 | 0 of 709 |
| Spawns with ground beneath | 64 of 64 | 64 of 64 |
| 32 bots, average server frame | 3.4-3.7 ms | 6.1-6.8 ms |
| Bot trace cost | about 3 us | about 5 us |
| Worst frame in the steady windows | 10-14 ms | 18-19 ms |
| Bot counters (about 175 s) | 61 kills, 2 stuck jump-outs, 0 suicides, 198 ledge hops | 61 kills, 6 stuck jump-outs, 1 stuck suicide, 96 ledge hops |

(Prototype region, 16 bots: written in 4.8 s; 3.6-3.8 ms per frame against 2.1-2.2 ms on the q3map2 build.)

Reading: the writer is correct enough to play on and makes iteration on collision almost free, but its output
is currently about twice as expensive at run time and bots catch on geometry more often. Likely reasons, not yet
verified: more brushes (q3map2 evidently merges or drops some), 11 sides on every brush, a deeper tree, and no
edge bevel planes, so box traces meet sharp convex edges early.

**The q3map2-built `naboo_theed.bsp` stays the default.** The writer's output is installed next to it as
`naboo_theed_own.bsp` (collision only; it has no `.tworld` of its own, so it shows no visuals).

Next for the writer: edge bevels, merging coplanar triangles into larger brushes, and a better split heuristic;
then compare traces against the q3map2 build on a fixed set.

## 3. Not done

* Bots still not watched in a client; nobody has walked the map.
* The carved river beds are not in the collision (it was built before the carving).
* Sun shadows, better detail levels: not started.
