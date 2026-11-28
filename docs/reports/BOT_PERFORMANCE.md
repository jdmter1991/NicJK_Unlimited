# Bot AI performance

What the multiplayer bot AI of NicJK Unlimited costs, where the time goes, what was changed and what
it gained. Every number below was measured on the test machine (Intel i7-7700, 4 cores / 8 threads,
Windows 11, RelWithDebInfo x64 build, dedicated server, no human client) with the tools named in
section 10. The machine is shared: other programs were using two to three logical cores during most
runs, so single wall-clock numbers vary by up to about 30% from run to run. Comparisons were therefore
always run back to back at the same point, repeated where it mattered, and checked against counts
that do not depend on machine load (traces per frame, thinks per frame).

"32 bots" means 31 bots: the dedicated server has 32 slots and the 32nd `addbot` of the test roster is
refused, which is the user's own setup (31 bots + 1 player). FFA, sabers only, Force on, skill 5,
bots from the user's roster (`tools/bot_names.ps1`).

## 1. Architecture

One server frame (`SV_Frame`, `codemp/server/sv_main.cpp`) does, in this order:

1. `SV_BotFrame` → `BotAIStartFrame` (`codemp/game/ai_main.c`): bot spawns and the event tracker, then
   **a think for every bot** (`BotAI` → `StandardBotAI` and the newer modules: awareness, world use,
   objectives, Force tactics, learning, tuning), then **for every bot a usercmd** built from its input
   (`BotUpdateInput` → `BotInputToUserCommand`, which also holds the per-frame combat timing, guard,
   cliff checks and move sequences) and handed to the engine (`trap->BotUserCommand`).
2. `GVM_RunFrame` → `G_RunFrame`: entity thinks, and every client's `Pmove`, saber collision and Force
   powers. The bots' usercmds are executed here exactly like a player's.
3. `SV_SendClientMessages`: snapshots.

`BOT_THINK_TIME` is 0, so in the original code every bot thinks in every server frame: at `sv_fps 40`
40 times a second, at `sv_fps 125` 125 times a second.

**AAS is not used.** The brief names `BotMoveToGoal`, `trap_AAS_*`, `AAS_AreaTravelTimeToGoalArea`,
`AAS_PredictClientMovement` and `BotVisible`. None of them is called during play: the game module
never calls `trap->BotLibLoadMap`, `trap->BotLibStartFrame`, `trap->BotMoveToGoal`,
`trap->AAS_AreaTravelTimeToGoalArea` or `trap->AAS_PredictClientMovement` (they exist only as syscall
wrappers in `g_syscalls.c`), so no AAS file is loaded and botlib is used only for the elementary
actions (`EA_*`) that collect a bot's input. The JA multiplayer bots navigate on their own waypoint
graph (`botroutes/<map>.wnt`, `ai_wpnav.c`; 3619 waypoints on naboo_theed) and, where a map has no
route, on probe traces (`BotFallbackNavigation`, bot_features 128). There is no `BotVisible`; line of
sight is `OrgVisible` / `WPOrgVisible` / `OrgVisibleBox`, each one engine trace. "Pathfinding" is the
trail walk `TotalTrailDistance` and the destination choice `GetIdealDestination`; "movement
prediction" is `BotPredictEnemyPosition` (aiming) and `BotPred_BladeHits` (where an enemy blade will
be; pure arithmetic, no traces).

So the bot AI cost is almost entirely **collision traces** issued from game code, plus loops over
clients and entities. The engine's trace accelerator (earlier work, `cm_accel`) already made each
trace cheap; the question is how many are made.

## 2. Profiling

Instrumentation added (commit `2316472c4` and later), all off unless asked for:

| Cvar | Output |
| --- | --- |
| `sv_profile <s>` | `SVPROF`: server frame time avg/max and p50/p95/p99, split into bot AI, game simulation and snapshots; traces and their time per phase; console-output time (taken out of the frame times) |
| `bot_profile <s>` | `BOTPROF`: bot AI ms per frame (avg, p50/p95/p99, max), thread cycles per frame and per bot, bots, thinks per frame, µs per think and per bot per frame, slowest think, think scheduler counters and why bots counted as fighting, waypoint and entity count; per call site in `ai_main.c`: traces, time, worst |
| (same) | `BOTZONE`: every part of the bot frame booked on one of 33 zones (enemy scan, nearest waypoint, waypoint + enemy visibility, waypoint following, destination choice, trail distance, fallback navigation, saber execution, combat movement, obstacle checks, aim, prediction, Force, world use, objectives, usercmd building, ...). Zones nest and report self time, so they add up to the whole bot AI time (97-99% covered); calls, traces and worst inclusive time per zone |
| `bot_profileEval 0` | leaves the long `BOTEVAL` counter block out of `bot_profile` |
| `bot_perfVerify 1` | runs the old code beside each exact optimisation and counts disagreements |
| `com_sampleProfile <ms>` | stack sampler, now also in the dedicated server |

While the profilers are off each zone costs one integer test. The zone timers cost two QPC reads per
zone entry while on.

**A measurement trap found on the way:** printing the profile reports stalled single frames for 1 to
5 seconds whenever the server's console output went to a redirected file (the sampler showed the
time in `NtWriteFile` under `Com_Printf`). Those stalls were the "maximum frame time" of earlier
measurements. The benchmark now sends the console to `NUL`, and `sv_profile` subtracts the time spent
in `Com_Printf`. After that the 10-second maxima on ffa3 dropped from 300-5000 ms to 7-50 ms.

## 3. Baseline: where the time goes

Original behaviour (instrumented build, all new cvars off), `sv_fps 40`, 60 s measured after 20 s:

| Map | Bots | Server frame avg / p99 / max ms | Bot AI ms/frame | Game ms/frame | µs per bot per frame | Bot AI traces / frame | CPU of a core |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| mp/ffa3 | 8 | 3.07 / 7.2 / 9.3 | 1.12 | 1.80 | 133 | 111 | 16% |
| mp/ffa3 | 16 | 4.79 / 11.1 / 14.8 | 1.77 | 2.67 | 108 | 221 | 20% |
| mp/ffa3 | 24 | 5.96 / 15.7 / 22.6 | 2.27 | 3.24 | 89 | 332 | 23% |
| mp/ffa3 | 31 | 6.25 / 14.6 / 43.4 | 2.46 | 3.23 | 79 | 448 | 26% |
| naboo_theed | 8 | 2.79 / 6.0 / 8.0 | 1.35 | 1.33 | 167 | 89 | 15% |
| naboo_theed | 16 | 5.79 / 11.8 / 13.7 | 3.04 | 2.41 | 186 | 198 | 26% |
| naboo_theed | 24 | 7.15 / 17.4 / 24.9 | 3.65 | 2.95 | 154 | 333 | 33% |
| naboo_theed | 31 | 9.88 / 22.3 / 27.5 | 5.37 | 3.69 | 173 | 441 | 44% |
| mp/ffa3 | 31 (125 Hz) | 3.52 / 4.8 / 8.8 | 1.33 | 1.83 | 43 | 424 | 52% |
| naboo_theed | 31 (125 Hz) | 5.42 / 29.7 / 298.8 | 2.53 | 2.45 | 84 | 424 | 69% |

The bot AI cost is linear in the number of bots: about **14 traces per bot per server frame** on both
maps at every bot count. The per-bot time falls slightly with more bots (warmer caches, fewer cache
misses per trace). On naboo_theed each trace costs 2-3 times as much as on ffa3.

Where the time goes (share of the bot AI self time, 31 bots, `sv_fps 40`):

| Zone | mp/ffa3 | naboo_theed | Notes |
| --- | ---: | ---: | --- |
| enemy scan (`ScanForEnemies`) | 6% | **36%** | every think; candidates in view or hearing sorted by distance, one PVS test and one LOS trace each until one is visible. Naboo: 94 traces per frame, 64 µs per call |
| usercmd building (every frame) | **19%** | 13% | 3.6 traces per bot per frame: the cliff checks (ground ahead before a step or jump) |
| visibility: waypoint + enemy LOS | 16% | 12% | `WPOrgVisible` (2 traces) + enemy `OrgVisible` every think |
| movement: walls, stuck, jump/duck | 13% | 10% | wall probe and `BotTrace_Duck` every think |
| nearest visible waypoint | 11% | 9% | 140-330 µs per call, up to 1.4 ms: every closer waypoint traced in index order |
| saber execution | 10% | 3% | combat traces (wall, obstacle to the enemy) |
| destination choice | 5% | 5% | `GetNearestBadThing` walks every entity on every think |
| trail distance (pathfinding) | 0.4% | 1% | `TotalTrailDistance` is a short index walk; not a cost |
| prediction (enemy position, blades) | 0.7% | <1% | arithmetic only |
| team AI, weapon choice, Force tactics, objectives, world use, learning | < 1% each | | |

Traces account for 45-60% of the bot AI time measured by the engine (`SVPROF botai trace ms`), and
about 70% with the wrapper's own overhead.

`sv_fps 125`, 31 bots: bot AI 1.3 ms (ffa3) and 2.5-3.1 ms (naboo) per 8 ms frame; frame time 3.5 /
5.4-5.8 ms average, p99 4.8 / 8.0 ms. The per-frame work is about the same as at 40 Hz, so the AI cost
per second grows with the frame rate (2.5-3x from 40 to 125 Hz on these runs).

## 4. Optimisations of the measured hot spots

Each one is behind `bot_perf` (bitmask). 1, 2 and 4 give exactly the same decisions as before: run
with `bot_perfVerify 1` on naboo_theed (31 bots, 70 s) the old and new code disagreed **0 times** in
3,273 nearest-waypoint searches, 74,579 danger-list checks and 67,245 skipped shield traces.
On mp/ffa3 (31 bots, 70 s): 0 disagreements in 4,572 / 89,165 / 85,758 checks.

| Bit | Change | Effect (31 bots, `sv_fps 40`, medians of 2 back-to-back runs) |
| ---: | --- | --- |
| 1 | **Nearest visible waypoint** nearest first: candidates within 800 sorted by distance, the first visible one wins (same answer: nearest visible, lower index on a tie). The old loop traced every waypoint closer than the best so far, in index order. | traces in that zone −30% (ffa3) / −37% (naboo), zone time −31% / −35% |
| 2 | **Dangerous objects** (`GetNearestBadThing`): the entities that can be dangerous at all are listed once per frame and shared; each bot applies the full old test to those only. | destination-choice zone −78% (ffa3) / −49% (naboo) |
| 4 | **Waypoint visibility**: `WPOrgVisible`'s second trace can only find a shield (`ET_SPECIAL`); it is skipped while none exists. | visibility zone traces −33% (81 → 54 per frame ffa3, 58 → 40 naboo) |
| 8 | **Enemy scan cache**: a candidate the LOS trace found hidden is not re-traced by the same bot for `bot_scanCacheMs` (100 ms). Not exact: someone stepping out of cover can be noticed up to 100 ms later (the separate 10 Hz threat scan, `Bot_Awareness`, is unaffected). | naboo: enemy-scan traces −53%, zone time −48% |

Total (`bot_perf 0 → 7 → 15`, 31 bots, `sv_fps 40`): bot AI traces per frame 436 → 397 → 396 (ffa3),
360 → 347 → 305 (naboo); bot AI time 2.10 → 1.45 ms (ffa3, 7), 3.75 → 3.17 → 2.65 ms (naboo).
At `sv_fps 125`: ffa3 1.73 → 1.52 ms (−12%, `bot_perf 15`), naboo 3.10 → 2.13 ms (−31%); traces per
frame 441 → 396 and 425 → 327.

Considered and not done:
- Caching the per-frame cliff checks or the wall/duck probes: their inputs (bot origin, direction)
  change every frame while the bot moves, so a cache would only be an approximation of the old
  decisions, and these checks prevent falls.
- Sharing enemy line of sight between the two bots of a pair: the two traces are different segments
  (eye to eye versus eye to origin) and the gain is under one trace per think.
- `TotalTrailDistance` prefix sums: measured at 0.4-1% of the time.
- Multithreading: the AI reads and writes game state that `G_RunFrame` and other bots also touch
  (`g_entities`, `level`, botlib input), traces go through the engine's single-threaded collision
  code, and after the changes above the AI is 1-2.5 ms of a 25 ms frame. Not worth the risk.

## 5. Think scheduling: `bot_ai_fps`

`bot_ai_fps N` (default 0 = every server frame, the original) lets a bot that is **not** in a fight
run its decision making N times a second. The bots are spread over the interval by client slot
(slot × interval / 32), so each frame carries about the same share and the order is deterministic.

**What still runs every server frame for every bot:** the usercmd (view angles turned toward the
chosen ones, buttons, movement, the per-frame combat code in `BotInputToUserCommand`: guard and swing
timing, cliff checks, move sequences and intents) — the movement simulation, physics, networking and
snapshots are not touched at all. On a frame without a think the last decision stands; a jump press is
released unless a held jump is wanted (`jumpHoldTime`, `inputHoldUpUntil`), which matches the
press/release pattern the every-frame thinking produced.

**Who thinks every frame regardless** (checked every frame with distances only, no traces), with
`bot_ai_combatFps` (default 0 = every frame) as their rate:
- lost health since its last think (event: it is being hit),
- in the air (jumps, falls, Force jumps over gaps),
- duelling, evading, in a saber lock, in the middle of a move sequence or intent,
- its current enemy alive within `bot_ai_combatDist` (1024), or a gun fight with the enemy in sight,
- any living enemy within `bot_ai_threatDist` (600) — someone coming up from behind.

So blocking, attacking, dodging and the reaction to incoming swings keep the full rate; the
scheduling applies to bots that roam, look for enemies far away, or are dead.

**Medium and low frequency work inside a think** was already on timers in the existing code and was
left as it is: threat awareness 10 Hz (`Bot_Awareness`), destination choice in a fight at most every
100 ms (`destinationGrabTime`), objective waypoint every 1.5 s, entity items every 300 ms, Force
economy and tuning on their own clocks.

Measured, 31 bots, one 60 s run per row (`bot_perf 15` unless stated; the 125 Hz rows were run back to back in one series):

| Map | sv_fps | bot_ai_fps | thinks per frame (of 31) | bot AI traces / frame | bot AI ms / frame | frame ms avg / p99 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| naboo_theed | 40 | 0 (every frame) | 31.0 | 350 | 3.15 | 6.48 / 15.1 |
| naboo_theed | 40 | 10 | 19.9 | 309 | 2.75 | 7.67 / 35.5 |
| naboo_theed | 40 | 15 | 22.2 | 303 | 2.02 | 4.78 / 7.2 |
| naboo_theed | 40 | 20 | 23.5 | 313 | 2.04 | 4.92 / 7.1 |
| naboo_theed | 40 | 30 | 27.6 | 368 | 3.17 | 6.28 / 8.9 |
| naboo_theed | 40 | 60 | 31.0 | 347 | 2.26 | 5.05 / 7.2 |
| mp/ffa3 | 40 | 0 (every frame) | 31.0 | 438 | 1.75 | 4.86 / 7.1 |
| mp/ffa3 | 40 | 10 | 28.6 | 391 | 1.54 | 4.44 / 6.7 |
| mp/ffa3 | 40 | 15 | 28.7 | 387 | 1.50 | 4.40 / 6.5 |
| mp/ffa3 | 40 | 20 | 29.4 | 392 | 1.52 | 4.47 / 7.1 |
| mp/ffa3 | 40 | 30 | 30.1 | 432 | 1.75 | 4.91 / 7.2 |
| mp/ffa3 | 40 | 60 | 31.0 | 431 | 1.71 | 4.79 / 7.0 |
| mp/ffa3 | 125 | 0 (original, `bot_perf 0`) | 31.0 | 434 | 1.46 | 3.96 / 5.9 |
| mp/ffa3 | 125 | 0 (`bot_perf 7`) | 31.0 | 407 | 1.65 | 5.27 / 23.3 |
| mp/ffa3 | 125 | 0 | 31.0 | 386 | 1.40 | 4.16 / 13.1 |
| mp/ffa3 | 125 | 10 | 27.6 | 379 | 1.14 | 3.35 / 6.5 |
| mp/ffa3 | 125 | 15 | 27.6 | 383 | 1.81 | 6.45 / 25.0 |
| mp/ffa3 | 125 | 20 | 27.4 | 428 | 1.71 | 5.88 / 25.1 |
| mp/ffa3 | 125 | 30 | 28.0 | 375 | 1.72 | 5.95 / 22.2 |
| mp/ffa3 | 125 | 60 | 29.3 | 372 | 1.36 | 4.10 / 10.1 |
| naboo_theed | 125 | 0 (original, `bot_perf 0`) | 31.0 | 402 | 2.83 | 5.64 / 14.0 |
| naboo_theed | 125 | 0 (`bot_perf 7`) | 31.0 | 386 | 2.97 | 5.59 / 14.8 |
| naboo_theed | 125 | 0 | 31.0 | 318 | 2.04 | 5.06 / 14.9 |
| naboo_theed | 125 | 10 | 17.5 | 265 | 1.48 | 4.04 / 7.3 |
| naboo_theed | 125 | 15 | 18.9 | 251 | 1.42 | 4.04 / 9.9 |
| naboo_theed | 125 | 20 | 17.8 | 250 | 1.29 | 3.76 / 10.5 |
| naboo_theed | 125 | 30 | 21.2 | 301 | 1.58 | 4.04 / 11.0 |
| naboo_theed | 125 | 60 | 23.3 | 291 | 1.67 | 4.25 / 9.6 |

At `sv_fps 40` a think already happens only every 25 ms, and most bots on these maps are fighting or
jumping at any moment (on naboo 48-58% of bot-frames counted as "in a fight": in the air 30-35%,
enemy near 25-35%, move or duel 20%), so scheduling saves 25-35% of the thinks on naboo and 5-10% on
ffa3. At `sv_fps 125` the non-fighting bots would think every 8 ms; with `bot_ai_fps 20` they think
every 50 ms: on naboo the thinks per frame fall from 31 to 18 and the bot AI time by about half
(2.87 → 1.29 ms with `bot_perf 15`, −55%; an earlier 2-repeat series gave 3.10 → 1.35 ms). On ffa3 at
125 Hz nearly every bot is fighting, so `bot_ai_fps` alone skips only 10-12% of the thinks; the
ffa3 rows of that series also show the machine getting busier halfway through (game time, which no
setting here touches, went from 2.1 to 3.1-4.1 ms), so its milliseconds are not comparable with each
other — the trace counts are (434 → 372-386).

`bot_ai_combatFps 60` (fighting bots at 60 Hz on a 125 Hz server) was also measured: naboo 1.26 ms,
ffa3 0.94 ms bot AI per frame (thinks per frame 10 and 14 of 31), the lowest of all, but it lowers the
think rate of fighting bots and was not A/B-tested; it stays at 0.

There is no clear optimum between 10 and 30 Hz in the measurements (the differences are within the
run-to-run noise); 20 Hz was chosen for the A/B test as the middle value.

## 6. Adaptive processing summary

| Rate | What |
| --- | --- |
| every server frame, every bot | usercmd building (aim smoothing, guard, swing timing, cliff checks, move sequences), engine usercmd, `Pmove`, saber collision |
| every frame while fighting / threatened / hurt / airborne | the full think: enemy LOS, saber and Force decisions, evasions, combat movement |
| `bot_ai_fps` when not fighting | the full think: enemy scan, waypoint following, destination choice, world use, objectives |
| 10 Hz (existing) | awareness threat scan |
| ≤ 10 Hz (existing) | destination choice in a fight, item goals (3 Hz), objective waypoint (0.7 Hz) |
| event-driven | health lost → think now; enemy within reach → full rate; enemy found → full rate from the next frame |

## 7. Entity scanning and visibility

- Enemy scan: hidden candidates cached per bot for 100 ms (`bot_perf 8`); visible ones are taken at
  once, as before; the cache is per bot and pair, so a newly visible enemy is found within 100 ms at
  most, and immediately by the threat scan if within its range.
- Danger scan: one shared candidate list per frame (`bot_perf 2`).
- Waypoint visibility: one trace instead of two while there is no shield (`bot_perf 4`).
- Nearest waypoint: nearest-first search (`bot_perf 1`).

## 8. Gameplay

Nothing in the combat path is throttled: a bot within 1024 of its enemy or 600 of any enemy, hit,
airborne or in a move thinks every server frame as before. The A/B quality tests (section 10.3)
compare the whole package against the original in the same match.

## 9. Large maps

naboo_theed: 900 MB BSP, 90,833 collision leaves (all with the trace accelerator: 5.1 M nodes,
188 MB), 3,619 waypoints, about 200 entities. mp/ffa3: 1,825 collision leaves (37 needed the accelerator), 555
waypoints, about 300 entities.

- **Render geometry does not matter to the bots.** Bot AI cost is traces × cost per trace. What the
  BSP adds is collision brushes: a bot trace on naboo costs 2-3x one on ffa3 (3.7-10 µs against
  1.3-5.4 µs in the engine's own trace timer, varying with machine load), because each trace visits
  more leaves and tests more brushes (`SVPROF cm per frame`).
- **The number of traces per bot is the same** (about 14 per bot per frame) on both maps. What the
  big map changes is *which* parts trace: on the open, long-sighted naboo streets the enemy scan has
  many candidates in view that are behind walls, each a failed LOS trace every think — a third of the
  AI time; on ffa3 bots find each other quickly and the scan is 6%.
- **Waypoint count** matters only to the nearest-waypoint search (the old loop made about 10 traces per
  search on naboo and 30 on ffa3, where waypoints are denser around the bots); the trail walk and destination choice are index walks and stay cheap.
  The route graph is not searched per frame (no A* at run time), so route size does not scale the cost.
- No AAS on any map, so AAS area or reachability counts are not a factor; no map or navigation limits
  were added.
- Memory: the static caches added are 32 KB (waypoint candidates), 4 KB (bot × bot scan cache) and
  4 KB (entity list), allocated once; nothing is allocated during play.

## 10. Benchmarks and validation

### 10.1 Tools

- `tools/bot_perf_bench.ps1 -DevDir <dir> -Map <map> -Bots <n> [-SvFps 40] [-Extra "+set ..."]`: one
  run, server console to `NUL`, archived cvars removed, learned tables restored from `-Seed`, windows
  after the warm-up averaged into one JSON line (`perf_results.jsonl`).
- `tools/bot_perf_matrix.ps1`: maps × bot counts × rates × cvar sets, sets back to back per point.
- `tools/bot_perf_ab.ps1`: A/B quality matches, both slot orientations.

### 10.2 Before / after

`sv_fps 40`, 60 s after a 20 s warm-up, all settings of a row group run back to back:

| Map | Bots | Settings | Frame ms avg / p99 | Bot AI ms / frame (p99) | µs per bot per frame | Game ms / frame | Bot AI traces / frame | Thinks / frame |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: |
| mp/ffa3 | 8 | original (`bot_perf 0`) | 0.91 / 1.7 | 0.40 (0.68) | 49 | 0.47 | 111 | 8.0 |
| mp/ffa3 | 8 | new default (`bot_perf 7`) | 0.91 / 1.7 | 0.35 (-11%) (0.59) | 43 | 0.50 | 95 | 8.0 |
| mp/ffa3 | 16 | original (`bot_perf 0`) | 1.91 / 3.0 | 0.68 (1.18) | 42 | 1.09 | 219 | 16.0 |
| mp/ffa3 | 16 | new default (`bot_perf 7`) | 1.88 / 3.4 | 0.65 (-4%) (1.09) | 40 | 1.10 | 201 | 16.0 |
| mp/ffa3 | 24 | original (`bot_perf 0`) | 3.25 / 4.9 | 1.16 (1.81) | 48 | 1.82 | 333 | 24.0 |
| mp/ffa3 | 24 | new default (`bot_perf 7`) | 3.00 / 4.5 | 1.02 (-12%) (1.60) | 42 | 1.72 | 305 | 24.0 |
| mp/ffa3 | 31 | original (`bot_perf 0`) | 4.12 / 6.0 | 1.51 (2.34) | 49 | 2.22 | 433 | 31.0 |
| mp/ffa3 | 31 | new default (`bot_perf 7`) | 4.05 / 6.0 | 1.48 (-2%) (2.27) | 47 | 2.20 | 415 | 31.0 |
| naboo_theed | 8 | original (`bot_perf 0`) | 1.16 / 1.9 | 0.60 (1.10) | 75 | 0.51 | 89 | 8.0 |
| naboo_theed | 8 | new default (`bot_perf 7`) | 1.19 / 2.0 | 0.66 (+9%) (1.13) | 81 | 0.49 | 84 | 8.0 |
| naboo_theed | 16 | original (`bot_perf 0`) | 2.72 / 4.0 | 1.55 (2.61) | 97 | 1.02 | 199 | 16.0 |
| naboo_theed | 16 | new default (`bot_perf 7`) | 2.44 / 3.5 | 1.25 (-20%) (2.01) | 78 | 1.05 | 178 | 16.0 |
| naboo_theed | 24 | original (`bot_perf 0`) | 4.55 / 7.0 | 2.51 (4.12) | 109 | 1.72 | 325 | 24.0 |
| naboo_theed | 24 | new default (`bot_perf 7`) | 4.21 / 6.1 | 2.36 (-6%) (3.54) | 97 | 1.55 | 323 | 24.0 |
| naboo_theed | 31 | original (`bot_perf 0`) | 5.85 / 7.8 | 3.17 (4.62) | 103 | 2.21 | 449 | 31.0 |
| naboo_theed | 31 | new default (`bot_perf 7`) | 5.54 / 9.0 | 2.94 (-7%) (4.90) | 96 | 2.13 | 415 | 31.0 |
| mp/ffa3 | 31 | `bot_perf 15` + `bot_ai_fps 20` | 3.97 / 5.9 | 1.35 (-11%) (2.12) | 44 | 2.24 | 394 | 29.3 |
| naboo_theed | 31 | `bot_perf 15` + `bot_ai_fps 20` | 4.71 / 6.5 | 2.08 (-34%) (3.27) | 67 | 2.16 | 320 | 24.2 |

`sv_fps 125` (8 ms budget), 60 s after a 20 s warm-up, all settings of a row group run back to back:

| Map | Bots | Settings | Frame ms avg / p99 | Bot AI ms / frame (p99) | µs per bot per frame | Game ms / frame | Bot AI traces / frame | Thinks / frame |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: |
| mp/ffa3 | 31 | original (`bot_perf 0`) | 3.96 / 5.9 | 1.48 (2.25) | 47 | 2.06 | 434 | 31.0 |
| mp/ffa3 | 31 | new default (`bot_perf 7`) | 5.27 / 23.3 | 1.66 (+12%) (3.01) | 53 | 3.13 | 407 | 31.0 |
| mp/ffa3 | 31 | `bot_perf 15` | 4.16 / 13.1 | 1.40 (-6%) (4.15) | 45 | 2.33 | 386 | 31.0 |
| mp/ffa3 | 31 | `bot_perf 15`, `bot_ai_fps 10` | 3.35 / 6.5 | 1.11 (-25%) (2.73) | 37 | 1.88 | 379 | 27.6 |
| mp/ffa3 | 31 | `bot_perf 15`, `bot_ai_fps 15` | 6.45 / 25.0 | 1.81 (+22%) (5.82) | 59 | 4.11 | 383 | 27.6 |
| mp/ffa3 | 31 | `bot_perf 15`, `bot_ai_fps 20` | 5.88 / 25.1 | 1.76 (+19%) (5.43) | 55 | 3.66 | 428 | 27.4 |
| mp/ffa3 | 31 | `bot_perf 15`, `bot_ai_fps 30` | 5.95 / 22.2 | 1.73 (+17%) (4.93) | 56 | 3.67 | 375 | 28.0 |
| mp/ffa3 | 31 | `bot_perf 15`, `bot_ai_fps 60` | 4.10 / 10.1 | 1.33 (-11%) (2.82) | 44 | 2.35 | 372 | 29.3 |
| naboo_theed | 31 | original (`bot_perf 0`) | 5.64 / 14.0 | 2.87 (6.09) | 91 | 2.32 | 402 | 31.0 |
| naboo_theed | 31 | new default (`bot_perf 7`) | 5.59 / 14.8 | 2.80 (-2%) (6.27) | 96 | 2.29 | 386 | 31.0 |
| naboo_theed | 31 | `bot_perf 15` | 5.06 / 14.9 | 2.07 (-28%) (4.92) | 68 | 2.53 | 318 | 31.0 |
| naboo_theed | 31 | `bot_perf 15`, `bot_ai_fps 10` | 4.04 / 7.3 | 1.47 (-49%) (2.79) | 48 | 2.07 | 265 | 17.5 |
| naboo_theed | 31 | `bot_perf 15`, `bot_ai_fps 15` | 4.04 / 9.9 | 1.48 (-49%) (3.17) | 46 | 2.09 | 251 | 18.9 |
| naboo_theed | 31 | `bot_perf 15`, `bot_ai_fps 20` | 3.76 / 10.5 | 1.29 (-55%) (3.38) | 42 | 2.00 | 250 | 17.8 |
| naboo_theed | 31 | `bot_perf 15`, `bot_ai_fps 30` | 4.04 / 11.0 | 1.59 (-45%) (3.88) | 51 | 1.98 | 301 | 21.2 |
| naboo_theed | 31 | `bot_perf 15`, `bot_ai_fps 60` | 4.25 / 9.6 | 1.68 (-42%) (3.70) | 54 | 2.05 | 291 | 23.3 |

Reading the tables:
- These "original" rows were measured in the same series as the new ones, on a quieter machine than
  the baseline in section 3 (which is why they are lower than there); compare within a row group.
- **Default (`bot_perf 7`)**: bot AI traces −4 to −10% at every point; bot AI time −2 to −20%
  (one point +9%, naboo 8 bots, inside the noise). Exactly the same decisions.
- **Opt-in (`bot_perf 15` + `bot_ai_fps 20`)**, 31 bots: `sv_fps 40` −11% (ffa3) / −34% (naboo);
  `sv_fps 125` naboo −55%.
- The **goal of 32 bots at 125 Hz**: the average frame was already inside the 8 ms budget (ffa3 4.0 ms,
  naboo 5.6 ms); with the opt-in settings naboo drops to 3.8 ms average. The p99 on naboo stays around
  10-15 ms: those frames are spread over AI and game time and over machine load, not one hot spot.
  Of the remaining frame, the game simulation (`Pmove`, saber collision; 2.0-2.3 ms) is as large as
  the bot AI and was outside this work.
- Process CPU of the original build against this build: naboo_theed, 31 bots, `sv_fps 40`, the untouched
  `8f8373e2f` binaries against this build with its defaults, alternating twice: process CPU 37% / 30%
  (original) against 42% / 40% (this build), bot AI 4.5 / 4.2 ms against 5.0 / 7.1 ms. **This pair is
  not usable**: it ran while the machine got busy (the game simulation, which nothing here changes,
  went from 3.0 to 3.9-4.9 ms between the runs). The load-independent count is consistent with the
  rest: bot AI traces per frame 442 / 436 (original) against 401 / 410 (this build). The before/after
  comparisons above use the same build with the new cvars at 0, which runs the original code paths.

### 10.3 Quality (A/B)

24 bots (two groups of the same 12 characters, `bot_abTest 12`), 7-minute FFA matches, each played
twice with the tested settings in group B (slots 12-23) and twice in group A (slots 0-11), because
slots 12-23 do worse with identical settings. Tested package: `bot_perf 15` (enemy-scan cache) +
`bot_ai_fps 20` (scheduling); the other group had `bot_perf 7` + `bot_ai_fps 0` (bits 1, 2, 4 are
global and give the same decisions anyway). Kills / deaths (K/D):

| Map, rate | Match | Group A | Group B | Tested in |
| --- | --- | --- | --- | --- |
| mp/ffa3, `sv_fps 125` | 1 | 249/262 (0.95) | 273/270 (1.01) | B |
| | 2 | 240/276 (0.87) | 307/279 (1.10) | B |
| | 3 | 272/284 (0.96) | 265/265 (1.00) | A |
| | 4 | 285/284 (1.00) | 271/274 (0.99) | A |
| | **total** | tested **1137/1117 = 1.02** | original **1025/1077 = 0.95** | |
| naboo_theed, `sv_fps 40` | 1 | 74/82 (0.90) | 68/71 (0.96) | B |
| | 2 | 73/69 (1.06) | 80/93 (0.86) | B |
| | 3 | 75/80 (0.94) | 76/82 (0.93) | A |
| | 4 | 71/84 (0.85) | 63/64 (0.98) | A |
| | **total** | tested **294/328 = 0.90** | original **286/297 = 0.96** | |

Deaths by falling (all bots, whole match): 0-1 per match in every match, either setting.

Reading: on ffa3 at 125 Hz, where the scheduler skips more than half of the bot-frames, the tested
group did not do worse (K/D 1.02 against 0.95). On naboo_theed the tested group was 7% lower; with only
about 300 kills per side that is inside the match-to-match spread (one match each way went 0.86 and
1.06), but it is not evidence of "no loss" either. **Decision:** only the exact optimisations
(`bot_perf 7`) are on by default. `bot_perf 15` and `bot_ai_fps 20` stay opt-in; recommended for
servers running above 40 Hz, where their gain is large (section 5), after a longer test on the maps in
use.

## 11. Implementation

Files: `codemp/game/ai_main.c` (profiler zones, `bot_perf`, scheduler), `codemp/server/sv_main.cpp`
(percentiles, console time), `codemp/qcommon/common.cpp` (sampler in the dedicated server, print
timer), `codemp/qcommon/com_profile.h`, `tools/bot_perf_*.ps1`, `docs/NICJK_BOTS.md`.

No allocations at run time, no new threads, no change to the network protocol, snapshots, `Pmove` or
any player-facing code, nothing renderer-specific (Vulkan / OpenGL unaffected). Compiles with MSVC x64
with no new warnings; all functions are declared before use (`/we4013`). Linux/macOS: the thread-cycle
counter is Windows-only and reads 0 elsewhere.

### Cvars

| Cvar | Default | Meaning |
| --- | --- | --- |
| `bot_perf` | `7` | Optimisations, sum of: 1 nearest waypoint nearest first, 2 shared danger list, 4 shield trace skipped while no shield exists (1, 2, 4 exact, on by default), 8 enemy-scan cache (opt-in). `0` = the original code paths. |
| `bot_scanCacheMs` | `100` | Lifetime of a "hidden" result of the enemy scan with `bot_perf` 8. |
| `bot_perfBase` | `-1` | `bot_perf` 8 for the baseline group of an A/B test (`-1` = as `bot_perf`). |
| `bot_perfVerify` | `0` | `1`: run the old code beside bits 1, 2, 4 and count disagreements (testing). |
| `bot_ai_fps` | `0` | Think rate of bots that are not fighting; `0` = every server frame (original). Recommended `20` on servers above 40 Hz. |
| `bot_ai_combatFps` | `0` | Think rate of fighting bots; `0` = every server frame (original). |
| `bot_ai_combatDist` | `1024` | Current enemy closer than this = fighting. |
| `bot_ai_threatDist` | `600` | Any enemy closer than this = fighting. |
| `bot_ai_fpsBase` | `-1` | `bot_ai_fps` of the baseline group in an A/B test. |
| `bot_profile` | `0` | Seconds between `BOTPROF` / `BOTZONE` / `BOTEVAL` reports. |
| `bot_profileEval` | `1` | `0` leaves out the `BOTEVAL` block. |
| `sv_profile` | `0` | Seconds between `SVPROF` reports (now with percentiles and console time). |
| `com_sampleProfile` | `0` | Stack sampler interval in ms (now also in the dedicated server). |

### Build

As before: `cmake -S . -B build -G "Visual Studio 17 2022" -A x64 -DBuildPortableVersion=ON ...`,
`cmake --build build --config RelWithDebInfo --target jampgamex86_64 nicjkded.x86_64` (the game module
holds the AI; the engine change only touches profiling).

## 12. Limitations and possible regressions

- **Machine noise.** The test PC ran other heavy programs during the measurements; single runs vary
  by up to 30%. Conclusions rest on back-to-back comparisons, repeats, and load-independent counts
  (traces and thinks per frame). Absolute milliseconds will differ on another machine.
- **`bot_perf` 8** changes timing: an enemy stepping out of cover can be noticed up to 100 ms later
  by the scan. It is off by default: in the A/B package test it showed no loss on ffa3 but 7% lower
  K/D on naboo_theed (inside the noise of 4 matches, but not proof of no loss). It was not tested on
  its own, separately from `bot_ai_fps`.
- **`bot_ai_fps`** (off by default): bots that are not fighting decide less often. Things they do on
  their way (roaming, door and lift use, picking a destination, noticing an enemy beyond 600 units)
  react up to one interval later; a bot entering the threat or combat range is back at the full rate
  in the next frame. Per-think random choices (for example "50% chance to attack" style code in the
  older AI) happen less often for non-fighting bots. On frames without a think the old input is
  repeated, which for a roaming bot means the same movement keys; jumps are released.
- At `sv_fps 40` the scheduler gains little (most bots are fighting or airborne on the test maps); its
  value is at higher server rates.
- The remaining cost is dominated by work that was deliberately not touched: the per-frame cliff
  checks in the usercmd and the per-think wall and duck probes (they keep bots from falling), and
  the game simulation (`G_RunFrame`: Pmove, saber collision), which at 31 bots costs as much as or
  more than the AI.
- Only FFA with sabers on ffa3 and naboo_theed was benchmarked; CTF/Siege and gun matches use the
  same code paths but were not timed.
- The profiler zone wrappers add one call level to 13 functions (no measurable cost when off).
