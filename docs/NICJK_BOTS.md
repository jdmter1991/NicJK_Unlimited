# The bots in NicJK Unlimited

The bots are the original TaystJK / jaPRO bots (`codemp/game/ai_main.c`), extended piece by piece. Every piece sits behind a switch and was compared against the bots without it in live matches before being turned on. Pieces that lost that comparison are still in the code but off.

The bots play by the rules: they press the same keys a player has, their moves start only when the game would accept them from a player, and they see and hear nothing through walls.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `bot_features` | `12577279` | Sum of the switches below. |
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
| 4194304 | no | Walking in a saber fight, running only to close in, chase or get away. Lost its test. |
| 8388608 | yes | Duel timing, from JK2 1.02 duelling: hold at the edge of reach while a swing that will not reach passes, strike at once into a swing that ends, bounces or is parried, strike straight back after blocking, circle at the edge of reach. |
| 16777216 | no | MB2 manual block (only with `g_mb2manualblock 1`): a swing read in time is met with a manual block on the side it comes from, aimed for the perfect block when read well. Lost its test (K/D 0.78 against 1.07 over two 7-minute matches): the direction keys walk the bot into the swing, and only about 3 in 10 matched the swing that landed. |

## Saber systems

### MB2-style manual block: `g_mb2manualblock`

Off by default (`0`). With it off the game plays exactly as base JKA. With `1` the server uses blocking rules modelled on Movie Battles II (MB2 is closed source; the rules follow its community dueling guides), and the bots play by them.

| Action | Input | Effect |
| --- | --- | --- |
| Guard | Hold alt attack, saber lit | Saber hits from the front are blocked, at a cost in block points. You keep your stance's normal pose (as in MB2) and can only walk. Attack while guarding is a manual block, not a swing. |
| Manual block | While guarding, press attack with a direction key (W top, A left, D right, W+A top left, S+A bottom left, and so on) | Shows the parry pose for that side and stays open for 0.4 s, then cannot be used again for 1.5 s. If the swing that lands comes from that side, it costs half the block points. If it is also a perfect block, the attacker's saber is knocked out of his hand, unless he was guarding himself. |
| Perfect block | Guard with your aim on the side the swing comes from (an 8° zone, `g_mb2pbZone`) | Costs nothing, gives you 2 points back, takes 5 from the attacker and bounces his swing. |
| Saber throw | Alt attack + use | As base JKA. |

Block points (0 to 100) are shown in the fuel bar on the right: gold, turning red as they run out, labelled GUARD while guarding and MANUAL while a manual block is open. The server keeps them in the cloak fuel field, so the bar also shows in clients without this build. A block costs `100 × attacker's offence ÷ defender's defence` per saber style (blue 7/55, yellow 9/50, red 12/48, purple 11/48, cyan 8/48, duals 8/50, staff 8/53), more when crouched, in the air, at low saber defence or after a manual block on the wrong side; less against a chained swing. Points come back (`g_mb2bpRegen`, every `g_mb2bpRegenTime` ms) only when not running or attacking. Guarding with no points left gets your saber knocked away and the swing lands. Hits from behind are never blocked.

What the bots do with it: they guard when a saber can reach them, swing without the guard when nothing is about to land, aim for perfect blocks more often at higher skill, use manual blocks with switch 16777216 (off: it lost its test), and back off at walking pace when their points run out.

### JK2 1.02 saber system: `g_jk2_102sabersystem`

Planned: the Jedi Outcast 1.02 saber rules, ported exactly from jk2mv's game code. Off by default.

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
| MB2-style blocking (`g_mb2manualblock 1`) | Bots guard, perfect-block and back off at low block points. In a 24-bot, 7-minute match: about 2,000 guarded hits blocked (about 1 in 9 perfect), 140 got through, 60 disarms. |

## Reading the test output

With `bot_profile` set, the server log gets `BOTPROF` lines (time per function) and `BOTEVAL` lines: kills and deaths per group, what happened in the match (team scores, flags taken and captured, Siege objectives), kills by weapon type, shots and hits, falls, and a counter for nearly every decision described above. They are the basis for every claim on this page.
