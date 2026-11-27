# BOT_OVERHAUL_PLAN — combat, movement, navigation and adaptive AI

Scope: the "Ultimate Bot AI" brief on top of the earlier performance brief. Everything is done inside the
existing `ai_main.c` / `ai_main.h` (there is no `botfallbacknavigation.c`; `BotFallbackNavigation` is a
function in `ai_main.c`). Nothing is replaced wholesale.

## Audit results (step 1 of the brief, done)

| Document | Content |
|---|---|
| `MECHANICS_SABER.md` | 43 player-reachable saber attacks/specials, 7 styles, exact triggers, defence rules, observable enemy state |
| `MECHANICS_FORCE_MOVEMENT.md` | every Force power with activation, cost, range and counters; movement numbers; taunt commands; usercmd buttons and generic commands |
| `BOT_CAPABILITY_GAPS.md` | what the bots do today, through which input path, and a mechanic-by-mechanic gap table |
| `AI_ARCHITECTURE.md` | function index and per-frame flow of `ai_main.c` (line numbers predate the profiling code) |

All three inventories were produced by reading the source; nothing in them was runtime-tested.

## Findings that shape the plan

1. **The input path was the bottleneck.** `BotInputToUserCommand` could only produce ATTACK, ALT_ATTACK,
   FORCEPOWER, the holdable-item key, a random USE, DASH, movement and weapon. No generic command
   (style cycle, taunts, direct Force powers), no `forcesel`, no BUTTON_FORCEGRIP / FORCE_LIGHTNING /
   FORCE_DRAIN. Extended in the first implementation step (below).
2. **Many combat inputs never reach the game.** Navigation overwrites the swing-direction movement keys,
   `StandardBotAI` ends with `MoveTowardIdealAngles` which discards combat aim writes, and the "special
   move ladder" presses an input for one frame and then locks itself out for 0.4–1.2 s.
3. **Kata logic is rolled first with a ≥75 % chance and locks the bot out for 1.2 s** even when the kata
   cannot start (it needs zero movement input and 50 FP). Feints are dead code.
4. **Style switching exists but is blind**: it cycles once every 2 s and cannot aim for a style.
5. **Never attempted by the default AI:** roll, roll stab, stab-down on a knocked-down enemy, back attacks,
   butterflies/cartwheels, backflip attack, staff kicks, wall run/flip, Force Sight, every taunt.
6. **Defence:** with stock settings there is no body auto-block for swings; only blade contact blocks. The
   bot's "block" decision is undone by its own attack flag later in the frame.
7. **The user is happy with current combat and movement.** Every behaviour change therefore sits behind a
   feature bit and is compared against the unchanged behaviour before it becomes a default.

## Method for every change

* New ability = one bit in `bot_features`; behaviour-changing correction = one bit in `bot_fixes`.
* `bot_abTest 1` gives the features to odd-numbered clients only and prints `BOTEVAL` lines (kills/deaths
  per group) with `bot_profile`. A control run with identical groups measures the built-in bias of the
  odd/even split (different bot characters land in each group).
* A feature becomes default-on only when it does not lower the kill/death balance of its group and the
  user has looked at it in game.
* `bot_profile` / `sv_profile` after each step; 26 bots must stay well inside the 25 ms frame.

## Implementation order

| # | Step | Status |
|---|---|---|
| 0 | Input path: generic commands, held buttons, `forcesel`; feature bits; A/B evaluation (`bot_abTest N`, two blocks of N identical characters) | done, commit `02e8dc244` |
| 1 | Contextual taunts (after a kill, when safe), `bot_features` 2 | done, default on; not yet seen on screen |
| 2 | Force selection sent like a real client, `bot_features` 1 | done, default on; A/B showed no harm |
| 3 | Saber swing direction through a combat input intent applied after navigation, `bot_features` 4 | built, commit `3cdf09ee2`, default on since the 9-minute run of features 15 (110 kills / 101 deaths vs 89 / 104 for the old behaviour); alone it was neutral in a short run; chains not done |
| 4 | Kata gating, `bot_features` 8: attempted only when the engine can start one, with the exact input it needs | done, default on: 20 of 21 attempts started (old logic: 524 rolls, each a 1.2 s lockout); kills/deaths 48/41 vs 26/33 in one 150 s run. Other special rungs (DFA, lunge, combo) still use one-frame inputs |
| 5 | Targeted style selection through `GENCMD_SABERATTACKCYCLE`, `bot_features` 16 | built, commit after `3cdf09ee2`, default OFF: works mechanically (102 changes by 12 bots in 7 min) but the group using it did slightly worse (55/63 vs 62/58). The fixed counter rules are the weak part; style choice should come from measured results (step 11) |
| 6 | Missing specials: stab-down on knocked-down enemy, back attacks, lunge, DFA variants, roll and roll stab, staff/dual specials and kicks | planned |
| 7 | Defence and reactions: read enemy `saberMove` / anims, back-step and side-step windows, thrown-saber and push/pull responses, get-up choices; reaction delay by skill | planned |
| 8 | Force tactics: held grip/lightning/drain through the real buttons, push/pull knockdown follow-ups, defensive powers, fix Speed self-cancel and Rage conditions | planned |
| 9 | Fallback navigation: gap detection and jump planning from the measured jump numbers (141 u flat, 96/192/384 u force jump), per-bot stuck recovery, back-off after failed searches, real USE key for doors | planned |
| 10 | Sensory memory and threat scoring (last seen position, pursuit, multi-enemy awareness) | planned |
| 11 | Adaptive scoring: per-opponent success counters for attacks, styles and powers with bounded memory | planned |
| 12 | Personalities and skill scaling of reaction, precision and tactic choice | planned |

## Known limits of validation

* Bot-versus-bot kill/death balance is the only automatic measure; it says nothing about how fights look.
  Anything visual needs the user's eyes (`tools\watch_bots.ps1`).
* No bot-versus-skilled-human test can be run from here.
* Animation lengths are data, not code, so timing windows for follow-ups have to be measured in game.
