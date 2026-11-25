# BENCHMARKS — Naboo

> **Later state:** this document describes the first prototype (file version 1, one region). Corrected materials,
> file version 2, detail levels, the whole-city export and its benchmark are in `UPDATE_city_v2.md`;
> whole-city collision, spawns and the bot test are in `UPDATE_city_collision.md`.

Only measured results. Machine: Core i7-7700, 16 GB RAM, RTX 2070 (from the earlier reports). Engine: branch
`naboo-theed` at `798e4390a` (no source changes), RelWithDebInfo x64, run from `devgame_naboo\`.

## 2026-11-24: prototype collision map, dedicated server, 16 bots

Map `naboo_proto`: collision only (436,293 brushes, 5.83 M brush sides, 453 leaves, no vis, no light grid, no draw
surfaces apart from none-visible hull faces), 150 x 150 m of main street, 24 spawn points. `sv_fps 40` (25 ms budget),
FFA, sabers only, 16 skill-5 bots, no human client, about 100 s per run. Raw log:
`..\export\proto\server_prof16.qconsole.log`.

Load: `CM_BuildLeafAccel: 53 of 453 leafs accelerated (largest 26019 brushes), 285073 nodes, 447757 refs, 10.4 MB,
0 unbounded refs, 330 ms`.

Two consecutive 30 s windows:

| Per 25 ms frame | Window 1 | Window 2 |
|---|---:|---:|
| Total work avg (max) | 2.24 ms (5.27) | 2.08 ms (4.42) |
| Bot AI avg (max) | 0.74 (3.80) | 0.67 (2.94) |
| Game simulation avg (max) | 1.34 (3.47) | 1.25 (3.46) |
| Snapshots avg (max) | 0.16 (0.70) | 0.15 (0.36) |
| Frames over budget | 0 of 1,201 | 0 of 1,201 |
| Bot traces per frame / average cost | 118.5 / 4.3 us | 117.1 / 3.8 us |
| Game traces per frame / average cost | 158.3 / 2.5 us | 159.2 / 2.2 us |
| BVH nodes visited per frame | 16,121 | 15,181 |
| Brushes plane-tested per frame | 511 | 389 |

Bot behaviour counters over the run: 20 kills (all saber), 192 hops over low ledges, 29 force jumps over high
obstacles, 1 gap jump, 0 stuck jump-outs, 0 stuck suicides, 0 bots found inside solid.

Reading: with the per-leaf BVH the collision cost on this map is small (about 0.75 ms of trace time per frame for
16 bots), comparable per trace to Korriban (about 3 us).

Limits of this result:

* Nobody watched the bots: there was no client run (the user's own game session was using the machine), so "bots
  move around" rests on the counters above, not on observation.
* It is one small region; the whole map is about 8 times more geometry.
* An earlier run on the first compile (brushes mis-rotated, bots on the hull floor) gave similar frame times and
  20-28 kills; those figures were discarded because the map was wrong.

## 2026-11-24: cooked world v0 in rd-vulkan, prototype region, client

Engine `naboo-theed` at `d555f9291`. Listen server, spectator camera, no bots, 1920x1080 windowed, vsync off,
`com_maxfps 0`, two cycles of five fixed camera positions, 400 logged frames each. Raw log:
`..\export\proto\client_bench_v0.qconsole.log`. Details and per-view draw counts in `RENDERER.md`.

| Position | Cycle 1 FPS | Cycle 2 FPS |
|---|---:|---:|
| p1 | 677 | 702 |
| p2 | 439 | 418 |
| p3 (worst view: 5.6 M triangles, 3,267 draws) | 374 | 347 |
| p4 | 842 | 714 |
| p5 | 676 | 582 |

Precision warning: the frame log records whole milliseconds, so frame times of 1-3 ms are coarse and these figures
can be off by tens of percent. Wall-clock timestamps (one-second resolution) put every segment between roughly
200 and 800 FPS. Treat the result as "several hundred FPS on this region", not as the digits shown.

Cooked world load: 2.6-3.0 s for an 83 MiB file (326 meshes).

## Not measured yet

A properly timed client benchmark (longer segments, with bots), memory and VRAM, whole-map numbers, 32 bots.
