# TODO / status — Korriban bot performance project

Branch `claude/korriban-bot-perf` (local only, nothing pushed), two commits on top of `1ef7a9f1f`:

1. `ae580c494` Collision: per-leaf brush hierarchy for world traces, server profiling
2. `733952165` Bot AI: profiling, cheaper enemy scan, no dropped bot frames

## Done and measured (dedicated server, no client)

| Item | Result |
|---|---|
| Map verified from the real PK3/BSP | `MAP_ANALYSIS.md` |
| Original fork built (x64, all targets) and run on Korriban | saturates one core at 15 bots |
| Collision accelerator (`cm_accel`) | 84 µs -> 3.2 µs per trace, 0 mismatches in 500,000 compared traces |
| `sv_profile`, `bot_profile`, `sv_hitchStacks`, `sv_crashStacks` | working |
| Enemy scan rewrite | 7.1 -> 1.2 line-of-sight traces per think, same selection rule |
| Dropped bot frames removed | bots think 40/s instead of ~32/s |
| 26 bots | ~5.5 ms average per 25 ms frame, 0 – 3 frames over budget per 1,200, kills logged throughout |

## Open problems

1. **Server crash: found and fixed (commit `8116fccc8`).** `sv_crashStacks` caught it: `Com_Printf -> CON_Print ->
   CON_Show -> WriteConsoleOutput`. `CON_Show` ignored a failed `GetConsoleScreenBufferInfo` (hidden or
   redirected console) and used uninitialized values to offset into a stack buffer. All four crashes logged
   on 23-24 Nov have the same fault address, so `sv_hitchStacks` was not the cause. After the fix: 7.5 minutes
   of 26 bots with profile output every 5 s, no crash. A user-observed "connection interrupted" was this crash.
2. **Console/log output blocks the game thread.** Every kill line and bot chat line goes through
   `Com_Printf -> CON_Print -> fputs(stderr)` synchronously. With output on a hard disk this produced
   0.3 – 1.6 s stalls; on the SSD it still shows up as the ~18 – 20 ms worst-case frames that remain.
   Needs a buffered/asynchronous console and log writer in the engine.
3. **Client tested for frame time only** (`CLIENT_RENDERER_TESTS.md`, commit `a7945bfb5`): rd-vulkan 83 - 144 FPS
   with 26 bots after three client fixes; vanilla OpenGL 11 - 33 FPS; rd-rend2 unusable. Nobody has watched
   the picture or the bots: image correctness, draw distance appearance, bot movement, door use and stuck
   bots are still unjudged, and no network/snapshot-size numbers exist.
4. **No waypoints for Korriban.** `botroutes/swtor_korriban.wnt` does not exist, so bots only have
   `BotFallbackNavigation` and combat movement; there is no long-distance navigation on a 47,000-unit map.
   This is the biggest behavioural gap and needs either an authored route file or a route generator.
5. **Longest run so far is 2.5 minutes.** No memory-growth or multi-hour stability data.
   (`ENGINE_LIMITS.md` flags `svs.nextSnapshotEntities` forcing a map restart after a few hours with many bots.)

## Next steps, in order

AI (`ai_main.c`), using `bot_profile` after each step:

* Staggered scheduling: enemy scan and fallback navigation on per-bot offsets instead of every frame,
  with combat reactions kept every frame.
* `NewBotAI_GetAttack` / `Bot_ExecuteSaberCombat` run twice per think; `Bot_CheckAndInteractWithObstacle`
  retraces every frame because its cooldown is only set on success; `BotTrace_Duck` 1.3 traces per think.
* Bugs found by reading that are not fixed yet (see `AI_ARCHITECTURE.md` §10): `BotTrace_Jump` always
  returns 0; a `VectorMA` that traces toward the world origin in `BotFallbackNavigation`; wrong
  `AngleVectors` argument order in two movement probes; stuck/backup `static` variables shared by all
  bots; `level.clients[-1]` read; `gWPArray` indexed before its bounds check; `bot_state_t` leaked on
  reconnect; second `i <= MAX_CLIENTS` loop.
* Sensory memory (last seen position / time per enemy) so a lost enemy is pursued instead of rescanned.
* Threat scoring beyond "nearest visible".

Engine:

* Asynchronous console/log writer (problem 2).
* `JP_Trace` walks all entities twice per trace for the duel/race hack; skip when nobody is dueling or racing.
* Snapshots are built for bots (0.75 ms per frame at 26 bots).
* `CM_TraceThroughTree` uses a fixed 2048-unit offset for box traces against non-axial node planes.

Client / renderer / network (needs a client run):

* Compare rd-vulkan, rd-rend2 and vanilla on Korriban; measure with 26 bots.
* Draw distance: the map sets worldspawn `distanceCull 13966` and a fog of the same distance;
  `r_distanceCull` overrides it (see `ENGINE_LIMITS.md` §2.6). Not tuned yet.
* `CG_DrawMiscStaticModels` loops all 3,900 static models every frame with no spatial structure;
  `MAX_STATIC_MODELS` is 4,000, so the map has 100 spare.
* cgame `MAX_ENTITIES_IN_SNAPSHOT` (256) vs engine `MAX_SNAPSHOT_ENTITIES` (512) mismatch.

Documents still to write: `AI_OPTIMIZATION.md`, `AI_BEHAVIOR_TESTS.md`, `KORRIBAN_CONFIGURATION.md`,
`NETWORKING.md` (none of these have enough measured content yet).

## How to reproduce

```
tools\run_bench.ps1 -DevDir <...>\devgame_dev -Bots 26 -Warmup 30 -Duration 120 -QuietConsole `
    -Extra "+set sv_profile 30 +set bot_profile 30 +set sv_crashStacks 1"
```

Output: `devgame_dev\bench_<tag>.qconsole.log` (SVPROF / BOTPROF lines) and `devgame_dev\bench_results.jsonl`.
`cm_accel 0` gives the stock collision path; `cm_accelVerify 1` compares both on every trace.
The original installation is only read (`fs_basepath`); all writes go to the dev directory.
