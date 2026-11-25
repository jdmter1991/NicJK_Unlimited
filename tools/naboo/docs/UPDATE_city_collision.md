# Update 2026-11-24 (night): whole-city collision, spawns, 32-bot test

Map `naboo_theed` now has its own collision BSP covering the city, 64 generated spawn points, and was run with 32
bots on the dedicated server. No engine source changed in this step (engine at `1275a19cc`).

## Collision set (retuned)

Per-region settings in `tools\naboo_config.json` (`regions.city.collision`), compared with the prototype:

| Rule | Prototype | City |
|---|---|---|
| Objects become their bounding box below | 1.2 m | 3.0 m |
| Objects skipped below | 0.35 m | 0.6 m |
| Decimation target per mesh | 20 % of the opaque triangles, 200-3,000 | 4 %, 60-800 |
| Terrain | 2 m grid of the crop | 2 m grid inside the collision bounds |
| Collision bounds | the region | x 420..1000 m, y -520..330 m (580 x 850 m = 22,800 x 33,500 units) |

| Export result | Value |
|---|---:|
| Objects in / outside bounds / skipped by name / too small / no opaque triangles | 17,038 / 324 / 709 / 754 / 2,988 |
| Boxed / decimated / kept as is | 5,913 / 5,285 / 1,065 |
| Source triangles as placed -> opaque only | 39.2 M -> 25.8 M |
| Collision triangles: objects + terrain | 898,869 + 247,932 = 1,143,536 (3,265 degenerate dropped) |
| Export time | 409 s |

That is about 8 times fewer triangles per source triangle than the prototype settings (1.14 M instead of the
roughly 4.5 M those would have produced), but still more than the 0.6-0.8 M aimed for.

## Compile

`py tools\build_collision_bsp.py export\city naboo_theed` (existing q3map2 2.5.17n, BSP stage only):

| | Value |
|---|---:|
| Compile time | 1,467 s (24.5 min) |
| Output | `naboo_theed.bsp`, 332,926,736 bytes, RBSP version 1 |
| Brushes / sides / planes | 808,403 / 10,332,443 / 12,218,752 |
| Nodes / leaves | 2,958 / 2,960; up to 7,297 brushes in one leaf |
| Input triangles that did not become a brush | 335,000 of 1,143,536 (29 %) |

New check `tools\bsp_ground_check.py` (brush bounds from each brush's axial planes):

| Check | Prototype BSP | City BSP |
|---|---|---|
| Spawns with a brush within 96 units below | 24 of 24 | 64 of 64 (gap from origin: 22-93 units, median 40) |
| Large upward-facing input triangles (sample of 1,500) with no brush within 24 units below | 22 (1.5 %) | 38 (2.5 %) |

So the triangles q3map2 drops are mostly small or thin ones; a few percent of walkable-size ground triangles are
missing a brush, which means **small holes in the ground are possible**. Where they are and whether a player can
fall through was not examined; the 2 falling deaths in the bot run may or may not be related.

## Spawns

Rays on a 14 m grid over the collision bounds (2,460 points, 497 s), kept when the surface is level, has headroom
and side clearance, and lies at most 2.5 m above the terrain (keeps roofs and balconies out): 1,315 candidates;
64 chosen by farthest-point sampling. Weakness seen in the client: farthest-point sampling pushes spawns to the
edges, so some are on the empty hillside outside the built-up area. They are valid ground, but poor places to start.

## 32 bots, dedicated server

`sv_fps 40`, FFA, sabers only, 32 skill-5 bots, about 175 s. Raw log `..\export\city\server_prof32.qconsole.log`.
Load: see the `CM_BuildLeafAccel` line in the log.

| Per 25 ms frame | Window 1 (includes bots joining) | Window 2 |
|---|---:|---:|
| Total work avg (max) | 4.47 ms (424) | 3.36 ms (12.2) |
| Bot AI avg (max) | 1.88 (407) | 1.41 (4.7) |
| Game simulation avg (max) | 2.12 (151) | 1.57 (6.3) |
| Snapshots avg (max) | 0.46 (68) | 0.37 (1.3) |
| Frames over budget | 7 of 1,121 | 0 of 1,200 |
| Bot traces per frame / cost | 318 / 3.1 us | 315 / 3.0 us |
| Game traces per frame / cost | 310 / 1.5 us | 306 / 1.4 us |

Window 1 contains several long hitches (up to 424 ms, one "525 msec frame time" warning). The hitch lines show
many game frames run in one server frame (catch-up) and one 19.5 ms trace; the cause was not investigated, and
the user's own server was running on the machine at the time. Window 2 is clean.

Bot counters over the run: 53 kills (50 saber, 2 falling, 1 suicide), 80 force jumps over obstacles, 13 gap jumps,
48 ledge hops, 13 stuck jump-outs, 1 stuck suicide, 9 idle bots set moving, 0 bots found inside solid.

## Client

Listen server with 8 bots, 1280x720, three spawn positions (`..\export\city\shots_collision\`): the map loads with
both files (317 MB BSP + 256 MiB world), 91-109 FPS shown in the screenshots at a 125 cap. No bot happened to be in
view, so **bots have still not been watched moving on this map**.

Defects visible in these screenshots: several large white cone shapes near the palace (effect or light-shaft
meshes whose material was classified opaque; they should be excluded), plain ground, no sky.

## What this does and does not establish

* Established: the whole city is solid for players and bots, spawns have ground, 32 bots run at about 3.4 ms per
  frame in steady state, bots move, jump and fight without getting stuck in solid.
* Not established: absence of holes; behaviour of the invisible boundary (the hull walls); whether the simplified
  collision matches the visuals closely enough at doors, stairs and railings (nobody has walked it); the cause of
  the start-up hitches; scale.
