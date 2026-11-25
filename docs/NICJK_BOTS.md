# The bots in NicJK Unlimited

The bots are the original TaystJK / jaPRO bots (`codemp/game/ai_main.c`), extended piece by piece. Every piece sits behind a switch and was compared against the bots without it in live matches before being turned on. Pieces that lost that comparison are still in the code but off.

The bots play by the rules: they press the same keys a player has, their moves start only when the game would accept them from a player, and they see and hear nothing through walls.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `bot_features` | `4188671` | Sum of the switches below. |
| `bot_fixes` | `1` | Corrections to old bot code (memory safety, Force power selection). |
| `bot_profile <seconds>` | `0` | Prints the cost of the bot AI and the `BOTEVAL` counters every so many seconds. |
| `bot_abTest <n>` | `0` | Testing: client slots `0..n-1` play with `bot_abBase`, slots `n..2n-1` with `bot_features`. `BOTEVAL` then reports kills and deaths per group. |
| `bot_abBase` | `0` | The feature set of the first group in an A/B test. |
| `bot_tuneExplore` | `1` | `0` plays the tuned values exactly and learns nothing (for measuring). |
| `bot_tuneEpisode` | `180` | Seconds a bot plays one set of values before it is scored. |

### `bot_features` switches

| Value | On | What it does |
| ---: | :---: | --- |
| 1 | yes | The Force power a bot picked is the one it uses. |
| 2 | yes | Taunts, bows and flourishes after a kill when nothing threatens. |
| 4 | yes | The saber swing direction the bot chose is the one the game gets. |
| 8 | yes | Katas only when one can start and has a chance to land. |
| 16 | yes | Saber stance chosen from what the enemy is doing. |
| 32 | yes | Jump attacks, lunges, roll stabs, back attacks and stab-downs entered with the exact input each needs. |
| 64 | yes | No hesitation in saber range. |
| 128 | yes | Finding the way on maps without bot routes: steering round obstacles, jumping ledges and gaps, doors, getting unstuck. |
| 256 | yes | Evading katas, specials and heavy swings; breaking off when badly hurt. |
| 512 | no | Tactics from a player-written saber guide. Lost its test. |
| 1024 | no | Strafe-swing counters from the same guide. Lost its test. |
| 2048 | yes | Blade prediction: the bot sees where a blade will be and steps out of its path. Reaction time depends on skill. |
| 4096 | no | Learning swing directions from results. Showed no gain. |
| 8192 | yes | Force powers and saber throw used at the ranges and in the situations where the game's code makes them work. |
| 16384 | yes | Stepping in when the bot's own swing is predicted to fall short. |
| 32768 | yes | Tuning by play: distances, timings and chances are adjusted from kills and deaths over many matches and kept in `bottune.dat`. |
| 65536 | yes | All-round awareness: nearby enemies are noticed in any direction, and the bot turns on the bigger threat. |
| 131072 | yes | Force economy: stop and recover at low Force; break a grip with a push at the gripper. |
| 262144 | yes | Guns: lead the target, keep a distance that suits the weapon, release charged shots. |
| 524288 | yes | The world: the use key on doors and buttons that need it, touch buttons, lifts, shoot-to-open, use-triggers. |
| 1048576 | yes | Objectives: flag jobs in Capture the Flag and Capture the Ysalamiri, objectives and classes in Siege. |
| 2097152 | yes | No stepping or jumping off cliffs. |

## How well it works

Measured in bot-against-bot matches on a dedicated server. One match is noisy: two identical groups of 12 bots can differ by 20% in kills over seven minutes, so results were repeated before a switch was turned on.

| Area | State |
| --- | --- |
| Saber fighting, Force use, awareness | Each switch that is on won or held its own in repeated A/B matches. |
| Free For All on a huge map without bot routes | Works. Bots find each other, use doors, get unstuck or respawn. |
| Team Free For All | Works. No kills of teammates in any test. |
| Capture the Flag | Bots take and capture flags (2 captures in a 12-minute, 16-bot match on a stock map, where the old bots captured none). Carriers still die too often. |
| Capture the Ysalamiri | Shares the flag logic. Not yet measured in a long match. |
| Guns | In gun-only matches the gun logic holds its own. Hit rate is about 25%; rocket lock-on and sniper zoom are not implemented. |
| Siege | Bots find the objective, pick classes and use explosives on what needs them, but did not complete an objective in the test matches. Work in progress. |
| Doors and switches that need the use key | Implemented, but not exercised by any test map so far. |
| Lifts | Bots board and ride them on stock maps. |

## Reading the test output

With `bot_profile` set, the server log gets `BOTPROF` lines (time per function) and `BOTEVAL` lines: kills and deaths per group, what happened in the match (team scores, flags taken and captured, Siege objectives), kills by weapon type, shots and hits, falls, and a counter for nearly every decision described above. They are the basis for every claim on this page.
