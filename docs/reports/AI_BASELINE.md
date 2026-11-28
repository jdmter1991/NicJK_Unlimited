# AI_BASELINE — bot AI before any AI change

Measured with the new `bot_profile` cvar on the original `ai_main.c` logic (only the profiling wrappers
added), engine with the collision accelerator on. Dedicated server, `swtor_korriban`, `sv_fps 40`, FFA,
26 bots at skill 5, sabers + force, `g_newBotAI 0` (so `StandardBotAI` is the think function).
Two consecutive 30 s windows.

Without the accelerator the same AI cost 7.5 – 7.8 ms per frame for only 10 bots (see
`PERFORMANCE_DIAGNOSIS.md`); the figures below are what is left once traces are cheap.

## Per frame / per think

| | Window 1 | Window 2 |
|---|---:|---:|
| Server frames | 1,201 | 1,200 |
| Frames in which no bot thought at all | 242 | 242 |
| Bot thinks | 24,934 | 24,908 |
| AI time per frame, average | 3.05 ms | 2.98 ms |
| AI time per frame, worst | 10.6 ms | 23.6 ms |
| One think, average | 146 µs | 143 µs |
| One think, worst | 5.6 ms | 18.5 ms |
| Traces issued from `ai_main.c` per think | 13.8 (max 46) | 13.4 (max 40) |
| Share of AI time spent inside traces | 84 % | 82 % |

The 242 "no-think" frames are the faulty timeout block in `BotAIStartFrame`: one frame in five, no bot
thinks and no bot usercmd is produced.

## Trace cost by function (window 2, 30 s, 24,908 thinks)

| Function | Traces | Per think | Total | Avg | Worst |
|---|---:|---:|---:|---:|---:|
| `OrgVisible` (almost all from `ScanForEnemies`) | 177,255 | 7.12 | 1,913 ms | 10.8 µs | 253 µs |
| `Bot_ExecuteSaberCombat` | 31,786 | 1.28 | 235 ms | 7.4 µs | 436 µs |
| `BotTrace_Duck` | 35,596 | 1.43 | 175 ms | 4.9 µs | 247 µs |
| `BotFallbackNavigation` | 17,980 | 0.72 | 171 ms | 9.5 µs | 328 µs |
| `CheckForFriendInLOF` | 6,832 | 0.27 | 147 ms | 21.5 µs | 348 µs |
| `StandardBotAI` (inline traces) | 20,460 | 0.82 | 121 ms | 5.9 µs | 395 µs |
| `Bot_CheckAndInteractWithObstacle` | 10,400 | 0.42 | 64 ms | 6.2 µs | 179 µs |
| `BotTrace_Strafe` | 6,659 | 0.27 | 38 ms | 5.7 µs | 197 µs |
| `Bot_CheckMovementPaths` | 12,720 | 0.51 | 31 ms | 2.4 µs | 114 µs |
| `NewBotAI_GetMovement` | 10,062 | 0.40 | 20 ms | 1.9 µs | 36 µs |
| `BotCanHitEnemy` | 1,667 | 0.07 | 9 ms | 5.3 µs | 139 µs |

Total AI time in the window was about 3.6 s, so the enemy scan's line-of-sight traces alone were a little
over half of all bot AI time.

## Behaviour observed in the baseline (server log only, no visual inspection)

* Bots find each other and fight: saber and force-lightning kills are logged continuously with 26 bots.
* The map has no waypoint file, so `gWPNum` is 0 and all movement comes from `BotFallbackNavigation`
  and the combat movement code; there are no item or objective goals on this map.
* Bot chat works (taunts and death lines appear).

Nothing here judges movement quality, stuck bots, door use or target switching; that needs a client
connected to the server and has not been done yet.
