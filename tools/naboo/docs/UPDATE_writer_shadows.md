# Update 2026-11-25 (midday): collision writer brought level with q3map2, baked sun shadows

Engine: branch `naboo-theed`, local commits only, nothing pushed.
Rule followed for every compile, bake at full size and game test: no game from `devgame_dev` was running
(two tests waited for another session's server to finish).

## 1. Collision writer (`tools\write_collision_bsp.py`)

### Why the first version was twice as expensive

Three guesses were on the list (tree, missing bevels, brush count). Measured instead of guessed:

* **Tree granularity is not it.** A much coarser tree (512 leaves of about 2,700 brushes, leaning on the
  engine's per-leaf hierarchy) gave 6.7-8.2 ms per frame with 32 bots, no better than the fine tree
  (6.1-6.8 ms).
* **The brushes are.** `tools\bsp_compare.py` counts, for player-sized boxes around the spawn points, how many
  brushes a trace has to test. The first writer handed a trace 40-50 % more candidates than the q3map2 file.
* **q3map2 merges coplanar triangles.** Looking at its brushes around sample triangles: flat ground made of
  78-unit grid cells comes out as six-sided slabs up to 1024 units wide. That is where its 29 % fewer brushes
  come from, not from dropped geometry. It also extrudes each brush against the dominant axis of its normal
  (not along the normal), which keeps the side faces simple.

### What the writer does now

1. Corners are welded to 1/16 unit.
2. Coplanar neighbouring triangles (shared edge, same plane within 0.05 units) are merged greedily into convex
   polygons, at most 12 corners and 1024 units wide; corners that end up on a straight edge are removed.
   512,357 triangles had a coplanar neighbour; they became 186,259 polygons.
3. One brush per polygon, extruded 4 units against the dominant axis of its normal. Sides: the six exact
   axial box planes first (the engine derives the brush bounds from them), then top, bottom and edge planes
   (axial ones left out), then **edge bevels**: for every edge direction and axis the plane `edge x axis`,
   kept where the whole brush lies behind it and no equal plane exists. Box traces no longer catch early on
   slanted convex edges.
4. Tree, sky hull and entities as before.

The one-brush-per-triangle version is kept as `tools\write_collision_bsp_v1.py`.

### Static comparison (whole city)

| | q3map2 2.5.17n | writer, first version | writer now |
|---|---:|---:|---:|
| Time to produce the BSP | 1,467 s | 8.1 s | 35 s |
| File size | 332.9 MB | 281.0 MB | 258.7 MB |
| Brushes | 808,403 | 1,143,291 | 817,197 |
| Sides per brush (mean) | 12.78 | 11.00 | 13.24 |
| Brush candidates, standing player box (mean) | 1.6 | 2.3 | 1.7 |
| Brush candidates, box swept 64 units (mean / p90) | 8.3 / 16 | 11.7 / 25 | 8.7 / 16 |
| Brush candidates, box swept 256 units (mean) | 72.9 | 111.4 | 75.0 |
| Exact test: solid behind sampled triangles | 98.9 % | 99.9 % | 98.6 % |
| Walkable-size floors without solid | 0 of 1,182 | 0 of 709 | 0 of 1,408 |

The 1.3 % of sampled triangles without solid directly behind them are slivers (shortest altitude under 4 units)
on walls and slopes, where the axis-aligned extrusion leaves the test point outside a very small brush; the
q3map2 file shows the same pattern.

### Run-time comparison (32 bots, dedicated server, about 175 s each)

These two runs were made while another session's bot league server was running on the same machine (with the
user's agreement). The machine alternated between a quiet and a loaded state during both runs, visible in
every counter at once including the snapshot time, which has nothing to do with collision. So the windows are
listed by state, and the figures are not comparable with the earlier tables (3.4-3.7 ms for q3map2 then).

| 30 s windows | q3map2 file | writer now |
|---|---:|---:|
| Quiet windows: server frame | 2.8, 3.1, 3.1 ms | 2.5, 2.6, 2.6 ms |
| Quiet windows: bot trace cost | 2.5-2.7 us | 1.9 us |
| Loaded windows: server frame | 5.4, 5.5 ms | 4.9, 6.0 ms |
| Loaded windows: bot trace cost | 4.0-4.2 us | 3.6-4.8 us |
| Kills / stuck jump-outs / stuck suicides / ledge hops | 65 / 0 / 0 / 222 | 62 / 2 / 0 / 221 |
| Bots found inside solid | 0 | 0 |

(For reference, the first writer version: 6.1-6.8 ms on a quiet machine, 5 us per bot trace, 96 ledge hops.)

Reading: the writer's output now costs the same as q3map2's, within what this noisy pair of runs can show, and
bots move the same way on it (ledge hops 221 against 222; before the bevels 96). A clean pair of runs on an
idle machine was still owed at that point; it follows below.

### Clean comparison after the league (13:20-13:35, no other game running), and the default switch

Two runs per file, alternating (writer, q3map2, q3map2, writer), five 30 s windows each:

| | writer run 1 | writer run 2 | q3map2 run 1 | q3map2 run 2 |
|---|---:|---:|---:|---:|
| Server frame, mean of windows | 6.08 ms | 5.33 ms | 5.56 ms | 5.40 ms |
| Snapshot time (not collision; shows machine speed) | 0.74 ms | 0.63 ms | 0.62 ms | 0.59 ms |
| Frame time / snapshot time | 8.2 | 8.4 | 9.0 | 9.2 |
| Bot trace cost | 4.44 us | 3.90 us | 4.56 us | 4.60 us |
| Bot trace time per frame | 1.22 ms | 1.07 ms | 1.29 ms | 1.28 ms |
| Kills | 65 | 59 | 62 | 63 |
| Stuck jump-outs / stuck suicides | 5 / 0 | 4 / 0 | 5 / 2 | 3 / 0 |
| Ledge hops | 256 | 194 | 214 | 267 |
| Hitch lines | 2 | 2 | 1 | 1 |

The machine itself runs at varying speed with nothing else on it (Balanced power plan; the same server
measured 2.5-3.1 ms in some windows earlier), so absolute frame times differ from the older tables. Between
the two files there is no difference beyond the run-to-run spread, and the writer's traces are slightly
cheaper in both runs.

**`naboo_theed.bsp` is now the writer's file** (identical to `naboo_theed_own.bsp`); the q3map2 build is kept as
`naboo_theed_q3map2.bsp`. Loaded once more under the default name with 8 bots: no bots in solid, no errors.
Logs: `..\export\city\server_clean_own_a|own_b|q3_a|q3_b.qconsole.log`.

Earlier in the day:
Logs: `..\export\city\server_own32_merged.qconsole.log`, `server_q3map2_32_league.qconsole.log`,
`server_own32_leaf4096.qconsole.log`.

## 2. Baked sun shadows

Engine commit `447813534` (branch `naboo-theed`, local).

### Bake (`tools\bake_sun_shadow.py`, no Blender)

Reads the cooked `.tworld` (detail level 0 of every placement), so the shadows match exactly what is drawn.
Every casting triangle is sampled on a regular lattice finer than half a texel and splatted into a depth map
seen from the sun, keeping the nearest depth; isolated texels that stayed deeper than all eight neighbours are
closed afterwards. Blended materials (water, glass, glow) cast nothing; the 11 cutout materials (leaves, ivy)
are tested against the alpha of their texture, which gives dappled shade under trees.

| | |
|---|---|
| Map | 6912 x 4420, 16-bit, 61 MB; 6.02 units (15 cm) per texel; depth step 0.5 units |
| Region | the collision bounds of the city, heights -2600 to 3400 units; outside it everything is lit |
| Input | 41.8 M triangles, 5,979 M samples (531 M removed by alpha) |
| Time | 1,112 s (18.5 min), about 1 GB of memory, one core |
| Texels covered | 94.9 %; pinholes closed 70,381 |

Output: `maps\naboo_theed_shadow.dds` (R16_UNORM) and `maps\naboo_theed.tshadow` (transform plus a 1152 x 1105
copy for CPU lookups). Settings in `naboo_config.json` under `shadow`.

**Why 6912 and not 8192:** the renderer refuses a single image above 64 MB (twice its 32 MB image memory
chunk). The limit was left as it is and the map sized to fit.

### Renderer

* The DDS loader and the upload path accept `R16_UNORM` as a raw data format.
* The cooked-world shaders pass ambient and sun light separately. The fragment shader looks the fragment up in
  the map (moved 2 texels along its normal, depth bias 1.5 texels) and compares against a 4 x 4 block of texels
  with bilinear weights, a soft edge about three texels (45 cm) wide. In shadow the sun part is removed and
  the ambient part stays.
* Players and other models: the sun part of their light is scaled by five lookups around the origin in the
  reduced copy, so walking into shade darkens them gradually.
* Cvars: `r_tworldShadows` (0 off, up to 1 = full strength, default 1), `r_tworldShadowOffset`,
  `r_tworldShadowBias` (in texels, for tuning).
* Only the instanced path (`r_tworldInstancing 1`) has shadows.

### Checked

* Screenshots `..\export\city\shots_v9\`: s0-s4 with shadows, s5 and s6 the same two views without. Building
  shadows fall across the squares, trees throw dappled shade, shaded walls are darker; no striping or
  self-shadowing visible in these five views.
* Frame rate, 1280 x 720 (the resolution this client is currently set to, not the 1080p of the earlier
  tables), five positions, 14,900 frames per pass, alternating: shadows on 15 s and 14 s, off 16 s and 14 s,
  i.e. about 1,000 FPS either way. The cost is below what this measurement resolves (about 7 %).
  Log: `..\export\city\client_bench_shadow.qconsole.log`. The league server was running during it.
* Load: the shadow files add about 1 s.

### Not checked or not done

* Shadowed player lighting is built and loaded but was not looked at in a screenshot.
* Shadows are static: swaying trees and cloth keep a fixed shadow; players and other models cast none.
* Thin objects under about 15 cm (lamp wires, railings) cast weak or broken shadows at this resolution.
* Not looked at: shadow edges close up on steep walls, views in motion, the far terrain (outside the baked
  region it is simply lit).
* No 1080p benchmark with shadows.

## 3. Still open from before

Walking the map, scale, animation strength (user); collision for the carved river beds; better detail levels;
depth precision in motion; the single-frame server hitches (three hitch lines in each run above, in both files).

