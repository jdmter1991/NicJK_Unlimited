# PERFORMANCE_DIAGNOSIS — Korriban with bots

All numbers are runtime measurements from a dedicated server (`taystjkded.x86_64.exe`, RelWithDebInfo, x64)
started from an isolated dev directory against the real installation's assets (read-only), map
`swtor_korriban`, `sv_fps 40` (25 ms frame budget), FFA, sabers only (`g_weaponDisable 524279`), force
enabled, bots at skill 5 from `bots_test.cfg` names. No human client was connected in any run, so nothing
here says anything about client FPS or the renderers.

## 1. Where the time went in the original build

Process CPU of the unmodified fork (`devgame_baseline`, one 60 s window per row after 45 s warm-up):

| Bots | CPU of one core | Average work per 25 ms frame | Worst 1 s |
|---:|---:|---:|---:|
| 0 | 0.4 % | 0.1 ms | 5 % |
| 5 | 62.5 % | 15.6 ms | 99 % |
| 10 | 85.5 % | 21.4 ms | 100 % |
| 15 | 99.0 % | 24.8 ms | 100 % (saturated) |

The server is single-threaded; at 15 bots it has no idle time left, so it can no longer hold 40 Hz.
20 and 26 bots were not measured on the untouched build (the script failed on a locked log file; with the
server already saturated at 15 they would only show 100 %).

Same code with the profiling counters added and the accelerator switched off (`cm_accel 0`), 10 bots:

| Per frame (10 bots, stock collision path) | Value |
|---|---:|
| Total work | 20.0 – 23.5 ms (max 104 ms) |
| Bot AI (`SV_BotFrame`) | 7.5 – 7.8 ms, of which **7.3 – 7.5 ms inside traces** (59 – 69 traces, 105 – 128 µs each) |
| Game simulation (`G_RunFrame`) | 12.3 – 15.5 ms, of which 6.7 – 7.9 ms in ~130 traces (52 – 59 µs each) **and 4.8 – 6.7 ms in ~20 `PointContents` calls (~250 µs each)** |
| Snapshots | 0.25 ms |
| Leaf-brush records walked | 0.95 – 1.09 million per frame |
| Brushes that actually reached plane tests | ~9,000 – 9,700 per frame (under 1 %) |

So **about 95 % of server time was world collision** (traces + point-contents), and over 99 % of the
brushes each query looked at were rejected by the bounds test. Bot decision logic itself, snapshots and
entity processing were all small. This matches the static prediction in `MAP_ANALYSIS.md` §3.

Why it is so expensive on this map specifically: the collision is ~1.3 M small clip brushes that do not
split the BSP, so leaves hold thousands of brushes, and `CM_TraceThroughLeaf` / `CM_TestInLeaf` /
`CM_PointContents` walk every one of them (`CM_PointContents` does not even have the bounds reject —
it runs plane tests on every brush of the leaf).

## 2. Fix: per-leaf brush hierarchy (engine, `codemp/qcommon/cm_*`)

* At map load, every leaf with 24 or more brushes gets a bounding-volume hierarchy over its brush list
  (`CM_BuildLeafAccel`). Korriban: 1,519 of 5,433 leaves, 989,037 nodes, 36 MB, built in ~0.9 s.
* A trace asks the hierarchy for the brushes whose bounds overlap the trace bounds, sorts them back into
  their original leaf order and hands them to the unmodified brush code. The selection test is the same
  bounds test the brush code already used to reject a brush.
* For moving traces the hierarchy and the per-brush check also use a swept test (segment vs. box grown by
  the trace half-size + 1 unit), which is what makes long diagonal line-of-sight traces cheap.
* `cbrush_t::checkcount` was an `unsigned short` compared against an `int` that passes 65,535 within
  seconds, so the "already tested in another leaf" skip silently stopped working; it is now an `int`.
* `cm_accel 0` switches back to the stock walk at runtime. `cm_accelVerify 1` runs every trace both ways and
  reports any difference.

Correctness check: `cm_accelVerify 1` with 10 fighting bots for 60 s — **500,000 traces compared,
0 mismatches** (fraction, endpos, plane, contents, surface flags, startsolid/allsolid).
On those identical traces: stock **84 µs** average, accelerated **3.2 µs**; worst single trace 12.1 ms vs 0.48 ms.

`CM_PointContents` uses the same hierarchy (a point can only be inside brushes whose bounds contain it).
It is not covered by `cm_accelVerify`; its equivalence rests on the argument above, not on a runtime comparison.

## 3. Result

`devgame_dev`, accelerator on, steady-state 30 s windows (see `BENCHMARKS.md` for all rows):

| Bots | Total ms/frame avg | Worst frame | Bot AI avg | Game avg | Snapshots avg | Process CPU |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 2.0 – 2.2 | 7 – 8 ms | 0.84 – 0.94 | 0.95 – 1.0 | 0.25 | 13 % |
| 20 | 4.7 – 6.7 | see note | 2.0 – 3.0 | 2.1 – 3.2 | 0.57 | 22 % |
| 26 | 6.4 – 6.8 | 27 – 30 ms | 2.7 – 3.0 | 2.9 – 3.1 | 0.77 | 25 – 29 % |

At 26 bots, 1 – 6 frames out of every 1,200 exceeded the 25 ms budget (worst 30 ms). Bots were fighting
throughout (kill lines in the server log).

Note on hitches: early runs showed 0.3 – 1.6 s stalls. The stack sampler (`sv_hitchStacks`) put 248 of 281
samples inside `Com_Printf → CON_Print → fputs → NtWriteFile`: the server blocks on every console line
(each kill, each bot chat line), and my harness was redirecting that output to a file on the E: hard disk.
With the redirect on the SSD the stalls are gone (26 bots, 2 minutes, worst frame 30 ms). This was a test
artifact, but the mechanism is real: console/log writes are synchronous on the game thread, so a slow
disk or a blocked console can stall a live server the same way.

## 4. What is left after the fix (26 bots, per frame)

| Item | Cost |
|---|---:|
| Bot AI total | ~2.8 ms avg, spikes to 22 – 24 ms |
| of which traces | ~2.0 ms (286 traces, 7 µs each) |
| Game simulation | ~3.0 ms (371 traces at 2.8 µs = 1.0 ms; rest is saber/G2/Pmove logic) |
| Snapshots | ~0.77 ms (bots get full snapshots built) |

The remaining spikes are bot-AI frames: all bots think every server frame with no staggering, and some
paths burst to ~90 traces (see `AI_ARCHITECTURE_ai_main.md`). That, the per-trace entity loops in
`JP_Trace`, and the AI bugs listed there are the next targets.

## 5. Not yet measured

* Client FPS, GPU load, renderer comparison (rd-vulkan / rd-rend2 / vanilla), draw distance: no client run yet.
* Network traffic and snapshot sizes with human clients.
* Runs longer than 2 minutes; memory growth over time.
* Listen-server behaviour (there `SV_BotFrame` runs every client frame, not every server frame).
