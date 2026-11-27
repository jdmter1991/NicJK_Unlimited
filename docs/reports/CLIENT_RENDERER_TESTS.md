# CLIENT_RENDERER_TESTS — `swtor_korriban`, client connected to a 26-bot dedicated server

Method (`tools\run_client_bench.ps1`): the dev dedicated server runs the map with cheats on and 26 bots;
the dev client connects from the same PC as a spectator, windowed 1920x1080, vsync off, `com_maxfps 0`,
sound muted. A config teleports the camera through five fixed positions with `setviewpos`
(600 frames each, three cycles) and `com_speeds 1` logs every frame. FPS = frames / summed frame time,
first cycle discarded. The view is static at each position and the bots move, so runs differ by a few percent.
Your normal settings come from the installation's `taystjk.cfg` (read-only); the client writes only to
`devgame_dev\clienthome`.

Hardware: Core i7-7700, GeForce RTX 2070, game assets on a SATA hard disk.

Camera positions: p1 (685 180 700), p2 (-3625 -1535 472), p3 (-1185 -2323 448), p4 (1980 -16050 1655), p5 (6311 9527 -4465).

Nobody looked at the picture during these runs: they measure frame time only, not image correctness.

## Results (FPS)

| Run | p1 | p2 | p3 | p4 | p5 |
|---|---:|---:|---:|---:|---:|
| rd-vulkan, before client fixes | 65 | 96 | 101 | 59 | 131 |
| rd-vulkan, after client fixes | 94 | 111 | 133 | 83 | 144 |
| rd-vulkan, after fixes, `r_distanceCull 20000` | 87 | 106 | 127 | 69 | 155 |
| Vanilla OpenGL (`rd-taystjk`), one cycle only | not captured | 25 | 26 | 11 | 33 |
| rd-rend2, stock limits | map does not load: `R_CreateIBO: MAX_IBOS hit` | | | | |
| rd-rend2, VBO/IBO limit raised to 16384 | 7 | 14 | (8) | not reached | not reached |

Server during the client runs (26 bots + 1 human): 6.1 – 6.3 ms per frame, snapshots 1.0 ms, 0 – 3 frames
over 25 ms per 1,200.

Client memory (peak working set): rd-vulkan 2.4 GB, vanilla 2.2 GB, rd-rend2 3.5 GB.

## Where the rd-vulkan frame went (sampling profiler, in-game samples only, before the fixes)

| Share of frame | What |
|---:|---|
| 49 % | render back end (`RB_ExecuteRenderCommands`), of which 12 % was `vk_find_pipeline_ext` |
| 22 % | render front end (`R_RenderView`); 13 % walking world nodes, 11 % `R_CullSurface` |
| 12.6 % | `CG_AddPacketEntities` (11.4 % `CG_Player`: the 26 bots, sabers, Ghoul2) |
| 6.8 % | `CG_DrawMiscStaticModels` (6 % of the frame in `R_inPVS`) |
| 4.5 % | console input polling reached through `Com_Milliseconds` |

## Client fixes made

1. **rd-vulkan pipeline lookup.** `RB_StageIteratorGeneric` looked up a pipeline by definition for every
   stage of every entity and world draw with a linear `memcmp` scan over all pipelines. A hash table now
   remembers the answer; each hit is verified against the stored definition.
2. **Static models.** `CG_DrawMiscStaticModels` did two BSP descents (`R_inPVS`) for each of the 3,900
   models that survived the frustum test. The distance test now runs before the PVS query (same models
   drawn), and rd-vulkan's `R_inPVS` keeps the view origin's cluster for the frame.
3. **Console input poll** limited to once per millisecond (it was a system call on every timer read).
4. **rd-vulkan `tr.ibos` array** was declared with 4069 entries but bounds-checked against 4096; now `MAX_VBOS`.
5. **rd-rend2 `MAX_VBOS` / `MAX_IBOS`** 4096 -> 16384 so the map loads. rend2 is still unusable on this
   map (65 – 131 ms per frame in its front end); not investigated further.

## Draw distance

* The map sets worldspawn `distanceCull 13966` and its global fog shader ends at the same distance
  (`fogparms ( 0.415 0.268 0.181 ) 13966.227` in `shaders/swmap_korriban.shader`).
* `r_distanceCull` overrides the worldspawn value in the renderer. With 20000 (+43 %) rd-vulkan lost
  about 5 – 15 % FPS at four positions (p5 was within noise).
* Not yet verified: whether the larger value is visible at all, since the fog reaches full density at
  13,966 units, and whether cgame's own static-model distance (`cg.distanceCull`) follows the cvar.
  A real draw-distance increase most likely also needs the fog distance raised, which means overriding
  the map's fog shader from a small extra PK3 rather than editing the original.

## Conclusions so far

* rd-vulkan is the only renderer that runs this map well: 83 – 144 FPS with 26 fighting bots after the fixes.
* Vanilla OpenGL is 4 – 7 times slower; rd-rend2 does not load the map without a limit change and is far slower still.
* The server is not the limit for a client: it stays at ~6 ms per 25 ms frame.
