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

## 2026-11-26, about 03:30: bots, four resolutions, frame-time consistency

Machine: Intel 16-thread CPU (see BUILD.md), 16 GB RAM, GeForce RTX 2070 8 GB, 2560 x 1440 screen. Idle otherwise.
Engine `naboo-theed` after the culling / front-to-back / interior-visibility commit. `tools\run_bench.sh`:
dedicated server with 31 bots from the user's list (skill 5), client spectating at five fixed viewpoints and then
following a bot, about 4,000 frames each, uncapped; figures from the renderer's frame-time recorder
(`r_tworldBench`). One run per resolution (not yet repeated). 4K is rendered at 3840 x 2160 into a 2560 x 1440 window.

Average FPS / 1 % low FPS / worst frame ms:

| Viewpoint | 1280 x 720 | 1920 x 1080 | 2560 x 1440 | 3840 x 2160 |
|---|---|---|---|---|
| Palace hall | 111 / 78 / 19 | 111 / 73 / 321 | 113 / 82 / 39 | 99 / 70 / 34 |
| Avenue from the palace | 114 / 85 / 30 | 107 / 77 / 23 | 114 / 62 / 61 | 93 / 74 / 30 |
| Market | 147 / 103 / 21 | 142 / 100 / 22 | 140 / 95 / 36 | 103 / 64 / 31 |
| Lantern court | 158 / 114 / 22 | 155 / 118 / 19 | 146 / 78 / 401 | 100 / 87 / 75 |
| Overview from above | 187 / 138 / 11 | 172 / 105 / 550 | 189 / 125 / 14 | 140 / 121 / 20 |
| Following a bot | 185 / 114 / 26 | 195 / 133 / 13 | 185 / 100 / 26 | 125 / 64 / 30 |

GPU memory in use 6.3-6.5 GB of 8 GB; GPU load 63 % at 720p, 77 % at 1080p, 90 % at 1440p, 100 % at 4K.

**Target (125 FPS in the 1 % low) is not met at any resolution.** Reading:
* 720p to 1440p have the same frame times: the limit is the processor, one thread. Only 4K is limited by the
  graphics card.
* Engine timers at 720p with 31 bots: client frame 9-10 ms, of which the renderer front end 0.7-1.7 ms and the
  cooked-world pass 2.6-3.7 ms (cull 1.0-1.8, fill 0.5-0.7, draw 1.1). The same hall view without bots took 6.3 ms,
  so the bots cost roughly 3 ms per frame on the client whether or not they are in view (the map has no
  visibility data, so every player is always sent and processed). That part is not split further.
* Single frames of 300-550 ms occurred three times in 24 sections; cause not found.

Server alone, bots only (`run_bench.sh server`): 31 bots entered although 32 were requested (the reason was not
found; no "bot not found" line). 4.7-5.0 ms per server frame on average (budget 25 ms at sv_fps 40), worst frame
19 ms, none over budget, 2 hitch lines. So 32 bots were not measured.

### Later the same night: repeat run, and what the detail thresholds are worth

A second 1080p run of the same benchmark (with the look-neutral culling change of commit `fcbe57588`) came out
*slower* than the first (avenue 107 -> 88 average, market 142 -> 109, following a bot 195 -> 105). The machine
was at 20-26 % processor load from other programs at the time, and the limit is one processor thread, so single
runs of this benchmark differ by tens of percent. **A change is only measured when both variants run back to
back in one session.** Done that way (1650 frames each, twice, 31 bots, 1080p; average / 1 % low FPS):

| Viewpoint | Approved detail (0.004 / 0.12 / 0.035) | Tighter (0.0055 / 0.15 / 0.045) |
|---|---|---|
| Avenue | 89 / 59 and 85 / 53 | 100 / 56 and 107 / 64 |
| Market | 155 / 77 and 143 / 103 | 153 / 108 and 157 / 108 |
| Hall | 112 / 61 and 116 / 91 | 120 / 85 and 120 / 93 |

The tighter thresholds are worth 10-20 % on the avenue and little elsewhere. The user chose to keep the look, so
the approved values are the defaults again. The culling change itself has no back-to-back measurement.

### Collision: walls over the carved river bed

A bot was seen coming out of the water through a canal wall. Cause found in the data: carving the river bed
lowered the ground under 2,046 wall edges (1.76 km) that used to stand on it, leaving gaps of 0.82 m on average
and up to 3.6 m under the walls. `build_collision_terrain.py` now adds a collision skirt from each such edge to
0.4 m below the carved ground (4,092 triangles). BSP rewritten (900,691 brushes, 77 spawns); 31 bots ran five
minutes on it without errors. **Not verified at the place where it was seen** (the place is not known).
