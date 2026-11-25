# BOT_NAVIGATION — spawns and bot movement on Naboo

> **Later state:** this document describes the first prototype (file version 1, one region). Corrected materials,
> file version 2, detail levels, the whole-city export and its benchmark are in `UPDATE_city_v2.md`;
> whole-city collision, spawns and the bot test are in `UPDATE_city_collision.md`.

State: first server test on the prototype region (2026-11-24). No waypoint file, no navmesh; bots use the fork's
trace-based navigation unchanged.

## What was tested

16 bots on `naboo_proto` (collision-only BSP of 150 x 150 m of main street), dedicated server, about 100 s.

| Counter (from the server's own bot statistics) | Value |
|---|---:|
| Kills | 20, all by saber |
| Hops over low ledges | 192 |
| Force jumps over high obstacles | 29 |
| Jumps across gaps | 1 |
| Stuck jump-outs / stuck suicides | 0 / 0 |
| Bots found standing in solid and respawned | 0 |
| Falling deaths | 0 |

So bots spawned on the ground, moved, climbed kerbs and steps, found each other and fought, with no stuck or
in-solid events. **This was not watched in a client**, and one region with 24 spawns says little about crossing
the whole city (canals, long stairs, the palace).

## Spawn points

Generated, not authored: see `ASSET_PIPELINE.md` ("Spawn candidates"). 24 points, farthest-point sampled at street
level, each verified to have collision ground 35.6-40.3 units below its origin. Known weaknesses of the prototype
method: candidates come from the visual scene (a point on a surface that is excluded from collision would have no
floor; none of the 24 was), there is no check that a spawn is reachable from the others, and facing is simply
towards the region centre.

## A mistake worth remembering

The first compile had all brushes rotated (the compiler read the OBJ files as Y-up). The server still ran, bots
still "fought" (on the hull floor) and frame times looked excellent. Only the trace simulation
(`tools\bsp_tracesim.py`: zero brushes under every spawn) and the profile line "accel nodes 0" exposed it.
A kill count is not evidence that a map works; ground-under-spawn checks and the ledge/jump counters are better.

## Next

1. Watch the bots in a client once visuals exist (or with a debug draw of collision).
2. Reachability check between spawns (flood over walkable collision surfaces) in the spawn generator.
3. Whole-map test with 32 bots, using the same counters plus distance travelled per bot.
4. Decide on Recast navmesh only if the whole-map counters show stuck events or bots failing to leave their area.
