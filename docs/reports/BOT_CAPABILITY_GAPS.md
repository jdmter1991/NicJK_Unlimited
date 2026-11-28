# Bot capability gaps: what the bots can and cannot do today

Read-only source audit of `TaystJK_AI-Improved-Bots`, branch `claude/korriban-bot-perf`. Nothing was built or run.
All line numbers are **current** line numbers. Unless a file is named, a bare number means `codemp/game/ai_main.c`.

Legend for the confidence column:

- **V** = verified by reading the cited lines (control flow and conditions were followed by hand).
- **U** = uncertain: the code was read, but the in-game outcome depends on runtime state that was not measured.

Files read: `codemp/game/ai_main.c`, `ai_main.h`, `ai_util.c`, `codemp/botlib/be_ea.cpp`, `botlib.h`, and the consuming
side in `bg_pmove.c`, `bg_saber.c`, `g_active.c`, `g_main.c`, `g_cmds.c`, `w_force.c`, `qcommon/q_shared.h`, `server/sv_main.cpp`, `server/sv_bot.cpp`.

---

## 0. The findings that matter most

| # | Finding | Where | Conf. |
|---|---|---|---|
| 1 | A bot can only produce 9 usercmd buttons. `generic_cmd`, `forcesel`, `invensel` are always 0 (the usercmd is `memset` to 0 and never filled). | 765, 774-789 | V |
| 2 | In the default AI (`g_newBotAI 0`), every `bs->ideal_viewangles` write made by the combat code is thrown away: `StandardBotAI` ends with `MoveTowardIdealAngles`, which copies `goalAngles` over `ideal_viewangles`. | 15163, 1877-1879 | V |
| 3 | In the default AI, the swing direction chosen with `TAB_MoveforAttackQuad` + `EA_Move` is overwritten by the navigation `EA_Move` later in the same frame. `EA_Move` holds one vector; the last writer wins. | 10691 etc., then 14865, 14881 -> 8704 | V |
| 4 | Kata is rolled first with a chance of at least 75 % and locks the saber routine for 1.2 s. The kata input itself needs `forwardmove == 0 && rightmove == 0`, which the default AI almost never satisfies, so the lockout is usually spent doing nothing special. | 10537-10553, 10454-10464; `bg_saber.c:3099-3101` | V (lockout), U (how often the kata really starts) |
| 5 | Feints are dead code: no caller, and `isFeinting` is never set true. | 8967, 9053, 9054 | V |
| 6 | "Specials" (DFA, lunge, rush, combo...) send their input for exactly one frame, then the routine returns early for 400-1200 ms without sending anything. Multi-step ones (delay attack, style switch, three-swing combo) can never reach their second step. | 10459-10464, 9716-9735, 9738-9761, 9813-9855 | V |
| 7 | Style switching exists, but it is a blind "cycle once" call with a 2 s cooldown, done by calling the server function directly, not through a gencmd. `bs->saberPower` is never written, so every rule that wants strong style is dead. | 9432-9612, `ai_main.h:350` | V |
| 8 | The old stock force-power block in `StandardBotAI` is gone. All offensive/defensive force use now comes from the `NewBotAI_*` functions, which `StandardBotAI` calls directly. | 13856-13874 | V |
| 9 | `EA_Use` does not press the use key. It maps to `BUTTON_USE_HOLDABLE`. The door/button/lift code therefore uses the bot's holdable item, and it also suppresses the random real `BUTTON_USE` for 300-500 ms. | 779, 786-789, 10099-10130 | V |
| 10 | `ACTION_SKI` and botlib's private `ACTION_JUMPEDLASTFRAME` are the same bit (0x0800000). Every think after a jump, the bot presses `BUTTON_DASH`. | `botlib.h:106`, `be_ea.cpp:48, 479-486`, 784 | V (bit collision), U (effect: `PM_CheckDash` returns unless movement style is WSW or Tribes, `bg_pmove.c:5449`; `PM_CheckWallJump` at `bg_pmove.c:14881` was not followed to the end) |
| 11 | No taunt, bow, flourish, gloat or meditate anywhere. `trap->EA_Command` and `trap->EA_Gesture` are never called. | grep: 0 uses | V |
| 12 | `BotFallbackNavigation` declares itself stuck when it moved less than 10 units since the previous call. At 250 u/s that is true for any server frame shorter than 40 ms (sv_fps above 25), so it drops its target every 6 frames and idles 1 s. | 5593, 5604-5611 | V (arithmetic), U (observed behaviour) |

---

## 1. Input path: decision -> usercmd

### 1.1 Frame order

| Step | Where | Conf. |
|---|---|---|
| `SV_Frame` calls `SV_BotFrame` (dedicated) before the game frames | `server/sv_main.cpp:1659, 1673` | V |
| `BotAIStartFrame`: every bot thinks every call (`BOT_THINK_TIME 0`) | 60, 15242-15260 | V |
| `BotAI`: `trap->EA_ResetInput`, copy playerstate to `bs->cur_ps`, then `NewBotAI` if `g_newBotAI` else `StandardBotAI` | 965, 974, 1017-1020 | V |
| Then for every bot: `BotUpdateInput` -> `BotChangeViewAngles` -> `trap->EA_GetInput` -> `BotInputToUserCommand` -> `trap->BotUserCommand` | 15264-15274, 874-896 | V |
| For bots `ClientThink` only stores the command; `ClientThink_real` (Pmove) runs later from `G_RunClient` | `g_active.c:5982, 6117-6121` | V |
| Inside `G_RunFrame`, per client: `WP_ForcePowersUpdate` first, then saber update, then the client think (Pmove) | `g_main.c:4202, 4233` | V |

### 1.2 `trap->EA_*` functions used in ai_main.c (278 calls)

| Function | Calls | What botlib does (`be_ea.cpp`) | Becomes |
|---|---|---|---|
| `EA_Attack` | 52 | sets `ACTION_ATTACK` (172) | `BUTTON_ATTACK` (775) |
| `EA_Alt_Attack` | 10 | `ACTION_ALT_ATTACK` (186) | `BUTTON_ALT_ATTACK` (776) |
| `EA_ForcePower` | 19 | `ACTION_FORCEPOWER` (200) | `BUTTON_FORCEPOWER` (782) |
| `EA_Use` | 4 | `ACTION_USE` (228) | **`BUTTON_USE_HOLDABLE`** (779), not `BUTTON_USE` |
| `EA_Jump` | 30 | sets `ACTION_JUMP` unless the bot jumped on the previous think, in which case it clears it (256-263) | `upmove = 127` (862) |
| `EA_Crouch` | 11 | `ACTION_CROUCH` (298) | `upmove = -127` (864-866) |
| `EA_MoveForward` / `Back` / `Left` / `Right` | 37 / 18 / 25 / 27 | `ACTION_MOVE*` flags (368-410) | `forwardmove` / `rightmove` forced to +-127 (857-860). Back wins over forward, right wins over left. |
| `EA_Move(dir, speed)` | 31 | stores one world-space vector and a speed capped to 400 (418-429) | projected on view forward/right, scaled so the larger axis is 127 (826-855) |
| `EA_MoveUp` / `EA_MoveDown` | 1 / 1 | `ACTION_MOVEUP` / `MOVEDOWN` | **nothing**: `BotInputToUserCommand` never tests these flags |
| `EA_Action(ACTION_SKI)` | 2 (12608, 12701) | ORs the raw flag (326) | `BUTTON_DASH` (784) |
| `EA_SelectWeapon` | 1 (386) | `bi->weapon = weapon` (158); not cleared by `EA_ResetInput` | `ucmd->weapon` (812); `WP_NONE` is replaced by `WP_BRYAR_PISTOL` (803-809) |
| `EA_View` | 1 live (750); 9673 is inside a comment | stores view angles (442) | `ucmd->angles` minus `delta_angles` (815-822) |
| `EA_Say` / `EA_SayTeam` | 1 / 4 | `BotClientCommand("say ...")` -> `SV_ExecuteClientCommand` (`sv_bot.cpp:596`) | chat |
| `EA_GetInput` / `EA_ResetInput` | 1 / 1 | copy out / clear flags, remember "jumped last frame" (459-487) | - |

The counts are textual matches of `trap->EA_*` and include a few commented-out lines. `NewBotAI_NF` additionally uses the old spelling `trap_EA_ForcePower` / `trap_EA_Attack` / `trap_EA_MoveBack` / `trap_EA_Jump` (12461, 12488-12491); where that spelling is defined was not traced (**U**).

Never called from the bot code (V, grep): `EA_Command`, `EA_Gesture`, `EA_Talk`, `EA_Respawn`, `EA_DelayedJump`, `EA_EndRegular`.
The only "use" a bot presses on purpose is random: `BUTTON_USE` with about 40 % chance per frame while `bs->noUseTime < level.time` (786-789).

### 1.3 What the usercmd can and cannot contain

| usercmd field / button | Reachable? | How | Conf. |
|---|---|---|---|
| `BUTTON_ATTACK` (1) | yes | `EA_Attack` | V |
| `BUTTON_ALT_ATTACK` (128) | yes | `EA_Alt_Attack` | V |
| `BUTTON_FORCEPOWER` (512) | yes | `EA_ForcePower` | V |
| `BUTTON_USE_HOLDABLE` (4) | yes | `EA_Use` | V |
| `BUTTON_USE` (32) | random only | 786-789 | V |
| `BUTTON_WALKING` (16) | mapper exists (780), nothing sets `ACTION_WALK` | - | V |
| `BUTTON_GESTURE` (8) | mapper exists (778), nothing sets `ACTION_GESTURE` | - | V |
| `BUTTON_DASH` (8192) | yes | `EA_Action(ACTION_SKI)`, and by accident after every jump (finding 10) | V |
| `BUTTON_TALK` (2) | no | mapping commented out (777) | V |
| `BUTTON_FORCEGRIP` (64) | **no** | no ACTION flag, no mapping | V |
| `BUTTON_FORCE_LIGHTNING` (1024) | **no** | same | V |
| `BUTTON_FORCE_DRAIN` (2048) | **no** | same | V |
| `BUTTON_GRAPPLE`, `BUTTON_STRAFEBOT`, `BUTTON_TARGET` | no | same | V |
| `forwardmove`, `rightmove` | yes | `EA_Move` and the four move flags | V |
| `upmove` | only +127 / -127 | jump / crouch. The projected vertical part is forced to 0 (836) | V |
| `weapon` | yes | `EA_SelectWeapon` via `BotSelectWeapon` (379-387) | V |
| `generic_cmd` | **no, always 0** | `memset` at 765, never written. So `GENCMD_SABERATTACKCYCLE`, `GENCMD_SABERSWITCH`, `GENCMD_ENGAGE_DUEL`, `GENCMD_TAUNT/BOW/MEDITATE/FLOURISH/GLOAT`, all `GENCMD_FORCE_*` and `GENCMD_USE_*` (`q_shared.h:1409-1439`, handled at `g_active.c:5234-5522`) are unreachable. | V |
| `forcesel` | **no, always 0** | see 1.5 | V |
| `invensel` | no, always 0 | - | V |

### 1.4 What the bot does instead of gencmds (direct server calls, not input)

| Purpose | Call | Lines |
|---|---|---|
| Change saber style | `Cmd_SaberAttackCycle_f(&g_entities[bs->client])` | 9472-9608 (15 sites), 9728, 9733 |
| Saber on/off | `Cmd_ToggleSaber_f` | 10256, 14027, 14044, 14055 |
| Duel challenge / accept | `Cmd_EngageDuel_f` | 14034, 14046 |
| Suicide (Tribes routes) | `G_Kill` | 12580, 12594, 13241 |

The bot code also writes the playerstate directly, which no player can do:

| Write | Line | Effect |
|---|---|---|
| `ps.fd.forcePowerSelected = FP_x` | about 60 sites (7222 ... 15148) | selects the force power; see 1.5 |
| `ps.weaponTime = 0` | 9927 | kata code cancels its own weapon delay |
| `ps.fd.forcePowersActive &= ~(1 << FP_RAGE)` | 7561 | switches rage off without `WP_ForcePowerStop` |
| `ps.fd.forcePowerLevel[FP_SABERTHROW] = 3` and `forcePowersKnown |= FP_SABERTHROW` | 11837-11838 | gives itself saber throw 3 |
| `ps.fd.forcePowerLevel[FP_TEAM_FORCE] = 3` | 11803 | gives itself team energize 3 |
| `ps.fd.saberAnimLevel = SS_STRONG` | 12444 | `NewBotAI_NF` only |
| `ps.pm_flags |= PMF_JUMP_HELD` | 14982, 12693 | keeps a force jump rising although `EA_Jump` only presses every second think |

### 1.5 Force power selection

- The bot writes `level.clients[bs->client].ps.fd.forcePowerSelected` and presses `BUTTON_FORCEPOWER` in the same think. `WP_ForcePowersUpdate` then runs the selected power (`w_force.c:6057-6063`). **V**
- This works only because of frame order: `WP_ForcePowersUpdate` (`g_main.c:4202`) runs before the bot's Pmove. Pmove then does
  `if (cmd.forcesel != 255 && (forcePowersKnown & (1 << cmd.forcesel))) forcePowerSelected = cmd.forcesel;` (`bg_pmove.c:15652-15657`).
  A bot's `forcesel` is always 0 = `FP_HEAL`, so **every bot that knows Heal has its selection reset to Heal after every Pmove**. Any code that presses the force button without re-selecting in the same think would use Heal on such a bot. **V**
- There is no bot path to the dedicated buttons, so grip, lightning and drain are always used through "select + generic force button". The server accepts that (`w_force.c:4853, 4882, 6020, 6035, 6050`). **V**
- `forceButtonNeedRelease` (`w_force.c:5019-5165`) requires a release between two uses of non-hold powers; bots are exempt only for Push (`w_force.c:5097`). The `level.framenum % 2` gates at 7393, 11938, 12136 provide that release. **V**

### 1.6 View turning

`BotChangeViewAngles` (691-751), called once per server frame from `BotUpdateInput` (883):

| Item | Rule | Lines |
|---|---|---|
| factor, enemy visible | `turnspeed_combat * skill`, times 0.4 / 0.6 / 0.8 for skill <= 1 / 2 / 3 | 697-715 |
| factor, otherwise | `turnspeed` | 718 |
| clamp | factor in [0.001, 1] | 721-724 |
| max turn | `maxturn` degrees per second times frame time; forced to 1800 when `g_newBotAI` is on | 726-733 |
| per axis (pitch, yaw) | `desired = diff * factor`; `speed += (speed - desired)`; clamp to max; `angle += speed`; `speed *= 0.45 * (1 - factor)` | 734-748 |

`ideal_viewangles` is what the turn code chases. In `StandardBotAI` its final value is always `goalAngles` (15163).

---

## 2. Which AI runs

| Setting | Top level | Combat functions actually reached |
|---|---|---|
| `g_newBotAI 0` (default, `g_xcvar.h:349`) | `StandardBotAI` (1020, 13590-15164) | waypoint navigation and weapons are stock-derived; **saber, movement and force in combat come from `NewBotAI_*`** |
| `g_newBotAI 1` | `NewBotAI` (1018, 13201-13585) | same `NewBotAI_*` set, plus `NewBotAI_NF`, `NewBotAI_Tribes`, `NewBotAI_CapRoute`; no waypoint routine of its own except through `NewBotAI_DoAloneStuff` |

`NewBotAI_*` functions that `StandardBotAI` calls itself (V):

| Call | Line | Condition |
|---|---|---|
| `NewBotAI_LSvLS` / `DSvLS` / `LSvDS` / `DSvDS` | 13864-13872 | enemy client exists, was visible last frame, no force-jump charge pending, and (`g_forcePowerDisable` is not 163837/163839, or `g_flipKick`, or weapon is not the saber) (13856-13860) |
| `NewBotAI_DoAloneStuff` | 14089 | only on a frame where `ScanForEnemies` returns a new or 128-units-closer enemy (2683-2709, 14080-14090) |
| `NewBotAI_GetAttack` | 14448 | reaction time elapsed, enemy seen in the last 2 s, enemy visible (14444-14448) |

Those four dispatchers in turn call `NewBotAI_GetAim`, `_Getup`, `_ReactToBeingGripped`, `_Lightning`, `_Raging`, `_Gripkick`, `_Draining`, `_Speeding`, `_Healing`, `_MindTrick`, `_Protecting`, `_Absorbing`, `_SaberThrowing`, `_GetMovement`, `_GetDSForcepower` / `_GetLSForcepower`, `_GetAttack` (12142-12430).

Consequence: with `g_newBotAI 0`, `NewBotAI_GetAttack` (and so `Bot_ExecuteSaberCombat`) can run **twice per frame**: once from the dispatcher (13864-13872) and once at 14448. **V**

Not reached with `g_newBotAI 0`: `NewBotAI_NF` (13484), `NewBotAI_Tribes` (13300), `NewBotAI_CapRoute` (13245), `NewBotAI_ScanForEnemies` (13225). **V**

---

## 3. Saber combat as coded

`SaberCombatHandling` no longer exists in the file (grep: no match). `Bot_ExecuteSaberCombat` (10206-10769) is only called from `NewBotAI_GetAttack` (10803).

### 3.1 Control flow of `Bot_ExecuteSaberCombat`

| Order | Lines | What happens |
|---|---|---|
| 1 | 10214-10215 | `ideal_viewangles` = direction to the enemy origin (discarded later in the default AI) |
| 2 | 10222-10246 | 48-unit box trace forward. If a wall is closer than 24: 50 % `EA_MoveBack`, random yaw +-30 |
| 3 | 10253-10261 | saber holstered and enemy within 60: `Cmd_ToggleSaber_f`, `EA_Attack`, return |
| 4 | 10268-10281 | 70 % (80 % near a wall): `bs->doAttack = 1` if the enemy is within `SABER_ATTACK_RANGE` (128) |
| 5 | 10284-10287 | empty block ("your existing special move logic here") |
| 6 | 10289-10356 | enemy within 200 and a jumpable entity in between: `EA_Jump` + `EA_Move` + 70 % `EA_Attack` |
| 7 | 10359-10372 | `bs->avoidanceTimer` branch. That field is never written, so this is dead |
| 8 | 10383-10431 | per-style range constants. `SS_DUAL` and `SS_STAFF` have no case and get the medium defaults |
| 9 | 10454-10464 | **special lockout**: if `currentSpecial != NONE` and its duration has not elapsed, `return` with no further input |
| 10 | 10478-10480 | enemy beyond `SPECIAL_RANGE` (150-220 by style): return |
| 11 | 10485-10515 | swing memory, `Bot_ExecutePerfectBlocking`, "block this frame" early return |
| 12 | 10522-10538 | `specialChance = 65 + bonuses`, capped at 95 |
| 13 | 10545-10679 | the special ladder, section 3.2 |
| 14 | 10686-10768 | normal attacks: `TAB_MoveforAttackQuad` + `EA_Move` + `EA_Attack` |

### 3.2 The special ladder (first match wins, each sets a lockout)

`specialChance` is at least 65 (10537). The roll for each rung is `Q_irand(1,100) <= specialChance + bonus`.

| Rung | Lines | Range gate | Min. chance | Lockout | Input sent (once) | Status |
|---|---|---|---|---|---|---|
| Kata | 10545-10553 | `dist <= SPECIAL_RANGE` (always true here, see step 10) | **75 %** | 1200 ms | `EA_Attack` + `EA_Alt_Attack`, `weaponTime = 0` (9923-9927), only if dist 40-256, FP >= 50, not already in a kata | broken, see 3.3 |
| Saber dance | 10557-10565 | `dist <= CLOSE_RANGE` (24-36) | 73 % | 800 ms | random left or right quad + attack | one swing; direction overwritten |
| Rush | 10568-10576 | <= 100 | 70 % | 600 ms | `Q_T` quad + attack | one swing; the quad is "backward", see 3.5 |
| DFA | 10579-10595 | <= 200, style medium / strong / dual / staff | 70 % | 1000 ms | `EA_MoveForward` + `EA_Jump` + `EA_Attack`, only if dist 50-200 (9653-9678) | unreliable, see 3.4 |
| Crouch lunge | 10598-10613 | <= 100, style fast / dual / staff | 70 % | 1000 ms | `EA_Crouch` + `EA_MoveForward` + `EA_Attack` (9682-9693) | unreliable, see 3.4 |
| Hurricane | 10616-10624 | <= 90 | 67 % | 700 ms | diagonal quad + attack | one swing |
| Style switch | 10627-10635 | <= 120, enemy vulnerable | 65 % | 400 ms | see 4 | broken |
| Delay attack | 10638-10646 | <= 110, enemy vulnerable | 71 % | 900 ms | one swing | second strike dead (9753-9760: sets a time 300 ms ahead, then tests it in the same call) |
| Convergent | 10649-10657 | <= 100 | 80 % | 800 ms | `Q_B` quad + attack, 60 % a second `EA_Move` forward | one swing |
| Static | 10660-10668 | <= 90, enemy recovering | 73 % | 600 ms | attack with speed-0 move | one swing |
| Three-swing combo | 10671-10679 | <= 120 | 70 % | 1000 ms | three `EA_Attack` in one call, `moveDir` computed but **never passed to `EA_Move`** (9823-9854) | one undirected press |

Because the kata rung comes first, its gate is always true and its chance is >= 75 %, the rungs below it are reached on at most 25 % of unlocked calls. With all bonuses (10525-10534) the kata chance reaches 100 % (95 + 10), so the lower rungs are then never reached. **V**

### 3.3 Kata: re-verification of the architecture-map claim

The claim is **confirmed**, with one addition.

1. On every unlocked call inside `SPECIAL_RANGE`, line 10545 rolls kata with chance `specialChance + 10` >= 75 %. **V**
2. On success it sets `currentSpecial = SPECIAL_KATA`, `specialDuration = 1200`, `lastSpecialTime = level.time` (10547-10549) and returns (10553). **V**
3. For the next 1200 ms line 10459 is true and line 10463 returns. During that time the function still runs steps 1-6 above (so `bs->doAttack` is still set 70 % of frames), but no directional or special input. **V**
4. At expiry, line 10454 clears the special. The separate 600 ms cooldown at 10459 is already over (1200 > 600), so the next call rolls kata again immediately. **V**
5. Addition: the state is set **before** `Bot_ExecuteKataAttack` checks its own preconditions (9904-9920). If FP < 50, dist < 40, or the bot is already in a kata, nothing is pressed but the 1.2 s lockout is still taken. **V**
6. Addition: a kata only starts if `PM_CanDoKata` passes: on the ground, saber ready, attack and alt-attack both down, **`forwardmove == 0`, `rightmove == 0`, `upmove <= 0`**, FP >= 50 (`bg_saber.c:3087-3102`). In the default AI the same frame also carries a navigation `EA_Move` (14865) and usually movement flags from `NewBotAI_GetMovement` (11165, 11188), so `forwardmove`/`rightmove` are normally non-zero and the kata does not start. **V** for the conditions, **U** for how often they happen to be met.
7. When the kata does not start, the frame still carries attack + alt-attack. For a staff, alt-attack is a kick (`bg_saber.c:3981-3996`); for a single saber the alt-attack is checked for a saber throw (`bg_saber.c:3496`). So failed katas plausibly turn into point-blank throws or kicks. **U**

### 3.4 Why the one-frame specials are unreliable

| Move | Engine condition (`bg_saber.c`) | What the bot sends | Problem |
|---|---|---|---|
| Red DFA | forward > 0, **`rightmove == 0`**, strong style, `velocity[2] > 100`, ground distance < 32 (2689, 2738-2743) | forward flag + jump + attack, one frame | `rightmove` comes from the leftover `EA_Move` vector and is non-zero unless that vector is within about 0.45 degrees of the view direction (849, 854); `EA_Jump` is dropped if the bot jumped on the previous think (`be_ea.cpp:256-259`); the attack must be accepted on that exact frame |
| Yellow flip-over ("yellow DFA") | same, medium style (2712-2718), then `PM_SaberFlipOverAttackMove` | same input (DFA rung allows medium) | same |
| Dual / staff jump attack | forward > 0, `rightmove == 0`, jump held, on ground or within 40, not attacking, `weaponTime <= 0` (2691-2703) | same input | same |
| Lunge (fast) / dual, staff crouch attack | forward > 0, `rightmove == 0`, on ground, **already `PMF_DUCKED`**, `weaponTime <= 0` (2787-2792) | crouch + forward + attack, one frame | same `rightmove` problem; needs the duck flag in the same Pmove |
| `Bot_ExecuteLungeAttack` (9874-9898) | - | forward flag + quad `EA_Move` + attack, **no crouch** | cannot produce a lunge at all; it is a plain forward swing |

### 3.5 How the attack direction is really chosen

The engine picks the swing from the usercmd movement at the moment the attack starts (`bg_saber.c:2560-2910`):

| `rightmove` | `forwardmove` | Swing |
|---|---|---|
| > 0 | > 0 / < 0 / 0 | `LS_A_TL2BR` / `LS_A_BL2TR` / `LS_A_L2R` |
| < 0 | > 0 / < 0 / 0 | `LS_A_TR2BL` / `LS_A_BR2TL` / `LS_A_R2L` |
| 0 | > 0 | specials above, else stab-down check, else `LS_A_T2B` |
| 0 | < 0 | staff backflip attack, backstab family if `PM_CanBackstab`, else `LS_A_T2B` |
| 0 | 0 | `LS_A_T2B` |

`TAB_MoveforAttackQuad` (9033-9050) turns a quadrant constant into a world vector: `Q_B` = view forward, `Q_T` = backward, `Q_R` / `Q_L` = right / left, diagonals accordingly. It does not press anything; the caller passes the vector to `EA_Move`.

| Path | Is the chosen quad what reaches the usercmd? | Why | Conf. |
|---|---|---|---|
| `g_newBotAI 0` | **No, except in corner cases** | Both `NewBotAI_GetAttack` calls (13864-13872, 14448) happen before 14865, where `EA_Move(goalMovedir)` replaces the vector; 14881 may replace it again with approach / retreat / strafe (8682-8704). The quad survives only if the movement block is skipped: `beStill`, `WaitingForNow`, wall closer than 16 (`goto skip_movement`, 14789), or the jump branch at 14858-14861. | V |
| `g_newBotAI 1` | Mostly yes | `NewBotAI_GetAttack` (13495) is the last `EA_Move` writer | V |
| both | The `EA_MoveForward/Back/Left/Right` flags set by `NewBotAI_GetMovement` and others override the vector per axis (857-860) | - | V |

So in the default AI the swing direction is a by-product of navigation and spacing, not a decision.

### 3.6 Other saber-related routines

| Routine | Lines | Status | Conf. |
|---|---|---|---|
| `BotCanFeint` | 8967-8995 | never called | V |
| `Bot_ExecuteFeint` | 9053-9099 | never called; `bs->isFeinting` is only ever set to false (9072, 9097); `bs->feintTime` is never written | V |
| `Bot_ExecutePerfectBlocking` | 9216-9311 | called (10496). During enemy swing stages 2-6 it zeroes `EA_Move` (overwritten later), sets pitch -10 and a yaw wiggle (discarded in the default AI) and returns | V |
| `Bot_ExecuteParry` | 9316-9358 | reached only if `shouldParry` is set and the 100 ms window is still open on a later call where the enemy stage is outside 2-6 (9265-9280). The stage that sets it (2) is followed by stages 3-6 for more than 100 ms, so this is effectively dead | V (logic), U (never observed) |
| "reset parry" | 9305-9310 | tests `enemySwingStage == 8`; the analyser only produces 0-7 (9119-9143); `lastBlockTime` is never updated | V |
| "block this frame" | 10499-10515 | returns without attacking, but step 4 has already set `bs->doAttack = 1` on 70 % of frames, and `StandardBotAI` presses attack for it at 15129-15131. `bs->saberDefending`, the only thing that would cancel it (15096-15101), is never written | V |
| `BotExecuteAttack` / `BotShouldAttackNow` / `BotUpdateAttackTiming` | 8583-8602, 8846-8890 | a second, independent attack trigger from `StandardBotAI` (14546-14552): when the enemy is within 128, presses attack with chance `0.5 + 0.1 * skill` subject to a 300-800 ms per-style delay | V |
| combo follow-up | 8875-8880 | needs `lastAttackHitTime > lastAttackTime`; `lastAttackHitTime` is only initialised (1186) | V |
| `bs->isAttacking` | 8701, 8917 | only initialised to false (1191) | V |
| saber lock | 15103-15113 | in a lock: 50 % per frame attack on, else off. That is the whole handling | V |
| saber throw (stock rule) | 14570-14578 | throw not on cooldown, FP_SABERTHROW known, enemy within 30 degrees, 450 < dist < 900, not staff: `doAltAttack = 1` | V |
| guiding a thrown saber | 14579-14582 | condition is `dist > 4500 && dist < 900`: never true | V |
| saber knocked away | 15121-15127 | holds attack to pull it back | V |
| `NewBotAI_SaberThrowing` | 7663-7674 | called while the saber is already in flight (12161-12172, 12238-12249, 12350, 12381): holds alt-attack if dist 500-2500 | V |
| `NewBotAI_GetSaberthrow` | 11826-11854 | enemy knocked down at 500-2500 with <= 50 hp+armor and FP > 40: gives itself throw level 3 and throws | V |
| `Bot_GetStyleAdvantage` | 9375-9427 | never called | V |
| `Bot_TrapSetup`, `Bot_ApplyUltraInstinctAim`, `Bot_GetMixedAttackMove`, `Bot_ShouldPressAttack`, `NewBotAI_GetGroundDodge` | 10936, 10973, 10980, 10993, 10844 | never called | V |
| `MeleeCombatHandling` | 4817-4901 | melee / stun baton only (14587-14590): toggles `meleeStrafeDir` every 0.5-1.8 s and, if the floor is level between both, sets the goal position to the enemy | V |
| `NewBotAI_Flipkick` | 7308-7339 | jump + forward towards the enemy, re-pressing jump between 24 and 48 units of rise. Reached from being gripped (7391), gripping (7444-7447) and once on enemy acquisition when the waypoint is higher (13109) | V |
| `NewBotAI_Gripkick` | 7398-7455 | pitch/yaw choreography while gripping. All of it is `ideal_viewangles` writes, so it is discarded in the default AI; only the movement keys and the held force button survive | V |
| `NewBotAI_NF` | 12432-12563 | only with `g_newBotAI 1` and force disabled. Forces strong style by direct write, contains the only deliberate back-slash and jump-crouch attack code | V |

---

## 4. Saber style handling

| Question | Answer | Lines | Conf. |
|---|---|---|---|
| Does the bot change style? | Yes | `Bot_SelectOptimalSaberStyle` 9432-9612; called at 10800, 13336, 14539 | V |
| How | `Cmd_SaberAttackCycle_f` called directly. One call = one step of the cycle fast -> medium -> strong -> Desann -> Tavion -> fast for a single saber (`g_cmds.c:4090-4105`); for a staff or dual sabers it toggles the second blade instead (`g_cmds.c:3938-4038`) | - | V |
| Can it pick a target style? | No. Every rule says "if current is not X, cycle once". The bot arrives at X only by cycling again after the cooldown | 9471-9608 | V |
| Cooldown | 2000 ms, and only when the bot's saber move is `LS_NONE` or `LS_READY` and it is not in a kata | 9447-9456 | V |
| Staff / dual | never switched by this function | 9459-9461 | V |
| `bs->saberPower` | read at 9498, 9519, 9563-9565, 9592, **never written anywhere** (`ai_main.h:350`). Every "go to strong" rule is dead | - | V |

Rules, in order:

| Enemy | Rule | Lines |
|---|---|---|
| human | own health < 40: want fast | 9470-9476 |
| human | enemy strong or Desann: want fast. Enemy fast: want medium. Enemy medium or Tavion: want strong (dead), else want fast | 9479-9528 |
| human | then return if the enemy style is 1-5 | 9537-9539 |
| bot | own health < 40: want fast | 9547-9553 |
| bot | if `level.time > lastStyleSwitchTime + random(8000..15000)`: pick a random available style and cycle once if it differs, then return. The random draw is repeated every frame, so this fires at about 8 s | 9556-9575 |
| both (fall-through) | dist <= 80: want fast. dist >= 120: want strong (dead), else want medium. Between: enemy health > 50 wants medium, else fast | 9583-9611 |

Because the fall-through rules run every 2 s and depend on distance, a bot fighting a bot keeps cycling through all five styles including Desann and Tavion.

`Bot_ExecuteStyleSwitch` (9716-9735): for staff / dual with saber offense > 1 it cycles once, sets `styleSwitchTime = level.time + 200` and immediately tests `level.time >= styleSwitchTime`, which is false, so the switch back never happens. For a single saber it does nothing but still costs the 400 ms lockout. **V**

---

## 5. Force powers

Activation is always "write `forcePowerSelected`, press `EA_ForcePower`" unless noted. There are no cooldown fields in the bot code for force powers; the only pacing is `level.framenum % 2` and the engine's own rules.
The whole offensive/defensive selection is skipped while the bot's FP is below 10 (12145, 12277, 12335, 12394) and when `g_forcePowerDisable` is 163837 or 163839 (12269, 12327, 12386, 12427).

Selection is "highest weight wins, strictly greater than all others" (11886-11909, 12073-12100); ties select nothing.
In saber range (<= 128, saber out, enemy visible) push, pull, rage and mind trick weights are zeroed (11875-11884, 12062-12071).

| Power | Decided by | Condition (summary) | Defects | Conf. |
|---|---|---|---|---|
| **Push** | `NewBotAI_GetPush` 11585-11609 | weight 100 only if enemy is "pullable", own health < 25, dist < 160, enemy has a saber and is airborne; never while Protect is on | very narrow; projectile push is dead (`bs->doForcePush` set at 2960, never read) | V |
| | `NewBotAI_Getup` 7296-7300 | knocked down and enemy within 200 or being gripped | fine | V |
| | `NewBotAI_ReactToBeingGripped` 7355-7377 | being gripped, no Absorb known, FP >= 20, enemy within 50 degrees, health < 30 | line 7373 tests the Pull disable bit for Push | V |
| **Pull** | `NewBotAI_GetPull` 11511-11583 | weight 100 to disarm a gun user within 200; with `g_flipKick` and saber/melee: pull knocked-down or airborne enemies; otherwise small weight for a level, close enemy | - | V |
| | being gripped 7361-7370 | health >= 30 | - | V |
| **Grip** | `NewBotAI_GetGrip` 11758-11790 | FP >= 50, within `MAX_GRIP_DISTANCE`, enemy FP < 20 and (jumping, speeding or saber knocked), or enemy in a strong-style swing | once active, `NewBotAI_Gripkick` (12220, 12312) holds the button but its aim choreography is discarded in the default AI and it never re-selects Grip | V |
| **Lightning** | `NewBotAI_GetLightning` 11611-11680 | FP >= 30, enemy visible, 80 < dist <= 1500; base weight 100 | once active, `NewBotAI_Lightning` (7457-7501) holds it; it stops if the enemy starts any saber move (7478) | V |
| **Drain** | `NewBotAI_GetDrain` 11714-11747 | FP >= 21, within `MAX_DRAIN_DISTANCE`, own health < 100, enemy has FP, no Absorb | once active, `NewBotAI_Draining` (7503-7511) presses the button without selecting Drain (selection is commented out at 7505); the dispatcher then returns, so no movement or attack decision that frame (12225-12227, 12317-12319) | V |
| **Rage** | `NewBotAI_GetRage` 11682-11712 | weight 2 (+15 if health < 50, +5 if enemy uses push/pull/grip), FP >= 60 | `else if (ourHealth < 25)` is unreachable (11702-11705). While Rage is active the DS dispatchers call `NewBotAI_Raging` and **return** (12215-12218, 12307-12310), skipping `NewBotAI_GetMovement` and force selection. `NewBotAI_Raging` turns Rage on only if FP is exactly 100 (7582-7585) and forces it off by clearing the active bit (7561) | V |
| **Speed** | 11911-11918, 12102-12109 | nothing else selected, dist > 90, **enemy has Absorb on**, health <= 100, FP >= 50 | while Speed is active `NewBotAI_Speeding` (7531-7537) presses Speed again if health < 90 **or FP <= 100**, which is practically always, and `ForceSpeed` on an active power stops it (`w_force.c:1585-1589`). Speed is switched off right after it starts | V |
| **Heal** | `NewBotAI_GetHeal` 11989-12005 | health < 100 and FP >= 50; weight `(FP - health + 101) / 2` | also `NewBotAI_DoAloneStuff` 12810-12813 on enemy acquisition | V |
| **Protect** | `NewBotAI_GetProtect` 7236-7268 | not active, FP >= 12, about to be hit by a thrown saber, or enemy swinging within 120 with its blade tip more than 48 away | line 7238 adds the **enemy's** armor to the bot's own health. `NewBotAI_Protecting` (7595-7625) only ever switches it off | V |
| **Absorb** | `NewBotAI_GetAbsorb` 7202-7234 | enemy using Drain or Lightning (100), holding a gun near an enemy (75), or low health vs. a force user | `NewBotAI_Absorbing` (7627-7646) only switches it off | V |
| **Mind trick** | `NewBotAI_GetTelepathy` 11942-11987 | not active, enemy visible within 400, own health >= 70, FP >= 20 | the selection test at 12093 does not compare against Protect. `NewBotAI_MindTrick` (7513-7529) re-presses while it is active and health <= 50 | V |
| **Team heal** | `NewBotAI_GetTeamHeal` 12007-12040; stock rule 15052-15059, 15073-15080 | team game, a weaker teammate within 512 / a friend in the line of fire with health <= 50 | the stock rule writes the selection late in the frame and so overrides whatever the dispatcher selected | V |
| **Team energize** | `NewBotAI_GetTeamEnergize` 11792-11824; stock rule 15060-15065, 15081-15086 | team game, weaker player within 512 | the loop does not check the team (compare 12023); gives itself level 3 (11803); not gated by `!useTheForce` (11920), so it overrides the earlier choice | V |
| **Force jump** | waypoint flags: `WPConstantRoutine` 1707-1730, 1749-1761 | jump-flagged waypoint more than 40 above | the "charge" is converted to holding jump for half the charge time (14953-14957); the `FP_LEVITATION` branch at 15146-15150 can never run because `forceJumpChargeTime` was cleared at 14950/14956. Only `NewBotAI_NF` selects Levitation (12460) | V |
| **Saber throw** | section 3.6 | - | - | V |
| **Sense (See)** | - | never used | - | V |
| **Saber offense / defense** | passive | read for style availability only (9436) | - | V |

Stray press: if `forceJumpChargeTime` is still pending at the start of a frame, `useTheForce` is set (13850-13854) and line 15154-15156 presses the force button with whatever power is selected, which is Heal for any bot that knows it (1.5). This needs an early return on the previous frame, so it should be rare. **U**

Reactions tied to force:

| Situation | Function | Behaviour | Conf. |
|---|---|---|---|
| Being gripped | `NewBotAI_ReactToBeingGripped` 7341-7396 | Absorb if known, else pull / push at the gripper, else switch own Speed off; plus `NewBotAI_Flipkick`. Only in the DSvDS and LSvDS dispatchers (12154, 12205, 12343, 12367): **a bot fighting a light-side enemy has no grip reaction path**, which is consistent since light side has no Grip | V |
| Knocked down | `NewBotAI_Getup` 7270-7306 | `EA_Jump` (lands every second think), then Protect / Absorb / Push | V |

---

## 6. Defence and reactions

| Mechanism | Lines | What it does | Status | Conf. |
|---|---|---|---|---|
| Reaction time | 13936-13950, 14444, 13490 | `reflex / skill` ms (0-2000) counted from the last frame with no enemy; gates only the `NewBotAI_GetAttack` call at 14448 and the aim update at 14464-14518. The dispatcher call at 13864-13872 is **not** gated, so the bot already attacks and uses force before its reaction time has passed | active | V |
| Incoming swing: back-step | `Bot_ShouldBackstepForSwing` 10950-10967 | enemy torso timer 60-180 ms and dist < 105 | called only at 11229, which is unreachable when the saber is out and dist <= 100 (early return 11140-11196). So it applies only between 100 and 105 units or with another weapon | V |
| Adaptive dodge direction | `Bot_GetAdaptiveDodgeDir` 10875-10930 | weighs remembered left / right / top swings | used at 11231 and 11385 (strafe side) | V |
| Swing memory | `ai_util.c:898-957` | adds a weight every frame the enemy is in a swing, decays by 0.88 per call | called twice per frame in the default AI (10485, 11124), so decay is frame-rate dependent | V |
| `Bot_EvadeSwingArc` | 11008-11020 | back if dist < 110, forward if > 180, 30 % random side step | used | V |
| Close-range spacing with saber | 11140-11196 | dist > 90 forward, dist < 80 back, 80-90 nothing | used; this is the bot's whole footwork inside 100 units | V |
| Spacing band beyond 100 | 11270-11360 | wants 85-130 against a saber, 30-70 otherwise | used | V |
| Strafe bursts | 11367-11422 | 30-80 % chance to strafe for 400-800 ms | used, but only beyond the band above | V |
| `Bot_CheckRearThreat` | 11022-11028 | enemy behind: forward + yaw 180 (yaw discarded in default AI) | used | V |
| `Bot_CheckMovementPaths` | 11033-11111 | side probes when the way ahead is blocked | `AngleVectors(viewangles, forward, right, left)` puts the **up** vector in `left`, then negates `right`: the "left" probe goes up and the "right" probe goes left (11037-11038) | V |
| Thrown saber | `NewBotAI_GetAim` 7080-7114 | aims at an enemy saber in flight within 200 | writes `goalAngles` / `ideal_viewangles`, both overwritten later in the default AI (14246-14275, 14504-14515, 15163) | V |
| Projectiles | `GetNearestBadThing` 2919-, used by `GetIdealDestination` 4196 | runs away from splash projectiles; `doForcePush` for others is dead | partly active | V |
| Blocking blaster fire | 15096-15101 | would stop attacking to block | dead (`saberDefending` never set) | V |
| `BotTrace_Jump` | 1972-2075, used 14906 | jump over an obstacle, a pit, or a low wall towards the enemy | the caller overwrites the function's 1.5-2 s cooldown with `jumpTime = level.time + 100` (14908) | V |
| `BotTrace_Duck` | 2078-, used 14910 | duck under an obstacle | only with no enemy within 200, 10 % chance (14913-14919) | V |
| `BotTrace_Strafe` | 1890-1967, used 14925 | side-step around an obstacle | active (`BOT_STRAFE_AVOIDANCE` defined at 1882) | V |
| Running away | `BotIsAChickenWuss` 2825-2915 | health below `BOT_RUN_HEALTH`, melee, or saber without `saberspecialist`, etc. | used by `GetIdealDestination` (4391) and camping (1816) | V |

Where each skill value is read:

| Value | Read at | Use |
|---|---|---|
| `settings.skill` | 699-713 (turn factor), 2958 (dead push), 5251 (aim error), 8368 and 8382 (prediction), 8635 (attack delay), 8755 (strafe chance), 8864 (attack chance), 13936 (reaction); `w_force.c:282, 291` (free force levels at skill >= 4) | |
| `skills.reflex` | 13936 | reaction delay |
| `skills.accuracy` | 5251 | random aim offset in degrees, `accuracy / skill`, re-rolled every 200-700 ms (5306-5324) |
| `skills.perfectaim` | 5217 | disables the offset |
| `skills.turnspeed`, `turnspeed_combat`, `maxturn` | 701-726 | section 1.6 |

---

## 7. Movement

| Topic | Where | Behaviour | Conf. |
|---|---|---|---|
| Base movement | 14855-14866 | `EA_Move` towards `goalPosition` (the current waypoint, 14236) at full speed | V |
| Range keeping with saber | `BotDynamicCombatMovement` 8664-8707, called at 14881 and via 8906 | optimal distance by style 40-80 (8710-8737); outside +-32 moves straight in or out; inside, strafes with chance `0.1 + 0.05 * skill` | V |
| "Circle strafe" | `BotCombatStrafe` 8763-8805 | one `EA_Move` to the side; the direction is re-rolled randomly each call (8836-8841), so it does not hold a side | V |
| Melee strafe with saber | 14884-14904 | 40 % per frame, direction `bs->meleeStrafeDir`. That field is only toggled by `MeleeCombatHandling` (melee weapons) and `NewBotAI` (13479), so with a saber in the default AI it stays on one side | V |
| `BotGetWeaponRange` | 2788-2822 | saber = `BWEAPONRANGE_SABER`; used to pick the combat branch (14530, 14587) | V |
| Jumping | 14948-14989 | `jumpTime` = tap, `jumpHoldTime` = hold; while held and airborne the code forces `PMF_JUMP_HELD` (14982) | V |
| Force jump | section 5 | waypoint-driven only | V |
| Crouching | 14991-14994 | `duckTime`, set by duck-flagged waypoints (1701-1704), camping (14260) and `BotTrace_Duck` | V |
| Rolling | - | no code presses crouch-while-running on purpose; rolls can only happen as a side effect of ducking while moving | V (absence) |
| Wall run / wall flip | - | no code | V (absence) |
| Stuck handling in `StandardBotAI` | 14729-14853 | wall within 16: strafe 60 % / back 40 %, after 3 in a row jump and turn 90. Every second: moved < 16 -> counter; at 2 turn 180 + jump, at 3 jump in a random direction. State is per bot only with `bot_fixes 2` (13620) | V |

### 7.1 `BotFallbackNavigation` (5562-5789)

Called when there is no current waypoint and the weapon is the saber (14345-14348), in the RMG "lost" state (14373), and from `NewBotAI_DoAloneStuff` (13028).

| Aspect | Detail | Lines |
|---|---|---|
| State | per-client statics: `explorationTarget`, `explorationTimer`, `stuckCounter`, `lastPosition`, `lastWallHitTime`, `lastMovementDirection` | 5568-5573 |
| Combat | returns 0 immediately if an enemy is visible | 5576-5578 |
| Stuck test | moved < 10 units since the last call, or commanded direction not aligned with the target direction (it always is, the same vector is stored at 5754) -> counter; above 5 the target is dropped and no new one is chosen for 1 s | 5593-5616 |
| Wall | 32-unit box trace forward; wall within 20 | 5628-5630, 5645 |
| Ledge | point trace from 64 ahead and 50 up, 300 down; a ledge if nothing is hit or the drop is over 120 | 5633-5642 |
| Response | at most every 500 ms: compare side clearance (32 units; without `bot_fixes 1` the probes are aimed wrongly, 5652-5663), check both sides for ledges, turn 60 left / right or 180; then always move backwards | 5646-5705 |
| Target choice | up to 12 random tries: random heading, 150-400 units, same height, accepted by `IsPositionReachable` | 5730-5750 |
| `IsPositionReachable` | box trace must cover 70 % of the way; ground sampled every 100 units, rejecting drops over 150 and rises over 100; final height difference at most 200 | 5960-6031 |
| Movement | `EA_Move` to the target, `goalAngles` towards it, `goalPosition` 250 ahead | 5753-5764 |
| Gaps | never jumped; a gap is treated as a ledge and avoided | - |
| Doors, lifts, buttons | none here. Only the random `BUTTON_USE` (786-789) | - |
| Emergency branch | needs `stuckCounter > 20`, but the counter is reset when it passes 5 | 5768, 5607-5609: dead |

### 7.2 `Bot_CheckAndInteractWithObstacle` (9938-10203)

| Aspect | Detail | Lines | Conf. |
|---|---|---|---|
| Callers | only `NewBotAI_GetMovement`: saber and dist <= 100 (11143), or dist > 200 (11202). That function returns at once without an enemy (11119), so this never runs while exploring | - | V |
| Jump over (combat) | requires `heightDif > 48` and, two lines later, the same quantity `< 48` | 10006, 10020, 10031: dead | V |
| Jump over (no combat) | same contradiction with 30 | 10071, 10080, 10082: dead | V |
| Doors | within 80 of a `func_door` without spawnflag 1: `EA_Use` | 10092-10109 | V |
| Buttons | `func_button`, `trigger_multiple`, `target_switch`: `EA_Use` | 10112-10119 | V |
| Lifts | `func_plat`, `func_train`, `func_elevator` within 32 vertically: `EA_Use` | 10122-10132 | V |
| The `EA_Use` problem | `EA_Use` = `BUTTON_USE_HOLDABLE` (779), and each branch sets `noUseTime`, which blocks the random real use key (786) | 10100, 10117, 10129 | V |
| Break it | in combat with saber / melee / explosives: `EA_Attack` and return | 10135-10145 | V |
| Avoid sideways | unreachable with a saber (previous row returns); `AngleVectors(..., NULL, left, right)` puts **up** in `right` | 10148-10199 | V |

### 7.3 Dead helper code (no caller in any `game/*.c` file)

| Function | Line |
|---|---|
| `CombatBotAI` (and through it `ShouldSecondaryFire`) | 5409, 5328 |
| `SmartExploration`, and through it `FollowGroundContours`, `MoveTowardLastWaypoint`; `ExpandingSpiralSearch` is reached only from it | 5794, 5819, 5916, 5887 |
| `StrafeTracing` (the only writer of `meleeStrafeDisable`) | 6436 |
| `BotWeaponCanLead` | 4905 |
| `BotCanFeint`, `Bot_ExecuteFeint` | 8967, 9053 |
| `Bot_GetStyleAdvantage` | 9375 |
| `NewBotAI_GetGroundDodge`, `Bot_TrapSetup`, `Bot_ApplyUltraInstinctAim`, `Bot_GetMixedAttackMove`, `Bot_ShouldPressAttack` | 10844, 10936, 10973, 10980, 10993 |
| `NewBotAI_StrafeJump` | 12710 |
| `NewBotAI_GetWait` | 11750 (commented out) |
| `BotSelectMelee` | 6273 (call commented out at 13931) |

`Bot_SetForcedMovement` (6964) is called from `g_cmds.c` only.

---

## 8. Personality and skill data

`bot_settings_t` (`g_local.h:2040-2045`): `personalityfile`, `skill` (float, from the bot's userinfo, `g_bot.c:852`), `team`.
Default personality file: `botfiles/default.jkb` (`g_bot.c:975`). Loaded by `BotUtilizePersonality` (`ai_util.c:638-892`), called from the client setup at 1139.

`GeneralBotInfo` group:

| Key | Field | Default | Loaded (`ai_util.c`) | Used |
|---|---|---|---|---|
| `reflex` | `skills.reflex` | 100 | 688-695 | 13936 |
| `accuracy` | `skills.accuracy` | 10 | 697-704 | 5251 |
| `turnspeed` | `skills.turnspeed` | 0.01 | 706-713 | 718 |
| `turnspeed_combat` | `skills.turnspeed_combat` | 0.05 | 715-722 | 701-713 |
| `maxturn` | `skills.maxturn` | 360 | 724-731 | 726 |
| `perfectaim` | `skills.perfectaim` | 0 | 733-740 | 5217 |
| `chatability` | `canChat` | 0 | 742-749, cleared at 808 if the chat section fails to load | `ai_util.c:364`, 6707 |
| `chatfrequency` | `chatFrequency` | 5 | 751-758 | `ai_util.c:379` (chat if `Q_irand(1,10) <= value`) |
| `hatelevel` | `loved_death_thresh` | 3 | 760-767 | 6384-6398 |
| `camper` | `isCamper` | 0 | 769-776 | 1816, 4120; **reset to 0 every frame by `NewBotAI`** (13210) |
| `saberspecialist` | `saberSpecialist` | 0 | 778-785 | 2888 only (does not run away just for holding a saber) |
| `forceinfo` | `forceinfo` | `DEFAULT_FORCEPOWERS` | 787-794 | `w_force.c:236-237` copies it over the client's force string; at skill >= 4 the server then raises some powers to 3 (`w_force.c:274-295`) |

`BotWeaponWeights` group (`ai_util.c:812-879`): `WP_STUN_BATON` (also sets `WP_MELEE`), `WP_SABER`, `WP_BRYAR_PISTOL`, `WP_BLASTER`, `WP_DISRUPTOR`, `WP_BOWCASTER`, `WP_REPEATER`, `WP_DEMP2`, `WP_FLECHETTE`, `WP_ROCKET_LAUNCHER`, `WP_THERMAL`, `WP_TRIP_MINE`, `WP_DET_PACK`. Defaults at 1123-1143. Used by `BotSelectIdealWeapon` (6116-6129).

`EmotionalAttachments` group (`ai_util.c:883`, parsed at 541-596): name + level pairs into `bs->loved[]`; used by `PassLovedOneCheck` (2607) and `GetLoveLevel` (6288).

`BEGIN_CHAT_GROUPS` (`ai_util.c:598-636`): everything after this marker is a list of named chat groups.

There are no personality keys for saber style, aggression, special-move preference, force preference or taunting. Sample file checked: `botfiles/malgus3.jkb` inside `GameData/base/zz_swtor_darth_malgus_3botfiles.pk3`.

---

## 9. Taunts and chat

| Trigger | Section | Line | `always` |
|---|---|---|---|
| Bot joins while players are in game | `GeneralGreetings` | 1200 | 0 |
| Another bot greeted | `ResponseGreetings` | 6712 | 0 |
| Order accepted | `OrderAccepted` | 465, 487 | 1 / 0 |
| Died | `Died` | 13780 | 0 |
| Killed by a loved bot that does not love back | `KilledOnPurposeByLove` | 13788 | 0 |
| Killed the revenge target | `KilledHatedOne` | 13990 | 1 |
| Killed an enemy | `Killed` | 14000 | 0 |
| Loved one killed by another loved one | `LovedOneKilledLovedOne` | 6378 | 0 |
| Hate threshold reached | `Hatred` | 6394 | 1 |
| Loved one killed | `BelovedKilled` | 6403 | 0 |

`BotDoChat` (`ai_util.c:348-539`) is blocked by `bot_nochat`, `canChat == 0`, a chat already pending, or a non-English `se_language`. The line is sent later with `EA_Say` / `EA_SayTeam` (14605-14620) after a typing delay (`ai_util.c:533`), and dropped if an enemy becomes visible first (14599-14603).
`BotReportStatus` (389-403) sends team-state lines with `EA_SayTeam`.

Animated taunts: **none**. No `EA_Gesture`, no `EA_Command`, no gencmd, no call to `G_SetTauntAnim`, no `amtaunt`-style command (grep over `ai_main.c`, `ai_util.c`, `g_bot.c`). **V**

Legitimate routes that exist but are unused: `usercmd.generic_cmd` (would need `BotInputToUserCommand` to fill it), `ACTION_GESTURE` -> `BUTTON_GESTURE` (778; handled in `PM_Animate`, `bg_pmove.c:11364`), and `trap->EA_Command` for console commands such as `amtaunt` (`g_cmds.c:8938`).

---

## 10. Gap table: player mechanics versus bot status

"Default AI" means `g_newBotAI 0`.

| Mechanic | Used correctly | Attempted but broken (why) | Never attempted |
|---|---|---|---|
| Switch to fast | | Blind single cycle, 2 s cooldown; reached only by cycling (9471-9608) | |
| Switch to medium | | same | |
| Switch to strong | | Every rule also requires `bs->saberPower`, never set (9498, 9519, 9563, 9592); strong is only passed through while cycling | |
| Desann / Tavion styles | | Entered unintentionally by the cycle (`g_cmds.c:4090-4105`) | |
| Staff: one blade / two blades, dual: one saber / two | | `Bot_ExecuteStyleSwitch` toggles once and never back (9726-9735) | |
| Directional slash selection | With `g_newBotAI 1` (last `EA_Move` writer) | Default AI: quad vector overwritten at 14865 / 14881; direction is a navigation by-product | |
| Combos / chains | | Three-swing combo presses attack once with no direction (9823-9854); follow-up needs `lastAttackHitTime`, never set (8877); specials lock the routine instead of chaining | |
| Lunge (fast crouch-forward) | | One-frame input, needs `rightmove == 0` and the duck flag (9682-9693; `bg_saber.c:2787-2792`). `Bot_ExecuteLungeAttack` never crouches (9874-9898) | |
| Yellow DFA (flip-over attack) | | One-frame forward+jump+attack, needs `rightmove == 0`; jump is dropped every second think (9653-9678) | |
| Red DFA | | same | |
| Dual / staff jump attack | | same input, same problems | |
| Backflip attack (staff, back + jump + attack) | | | X |
| Butterflies / cartwheels (side + jump + attack) | | | X |
| Katas (all styles) | | Needs zero movement (`bg_saber.c:3099-3101`), which the default AI almost never has; state is locked for 1.2 s even when nothing is pressed (10545-10553, 9904-9920); `weaponTime = 0` is written directly (9927) | |
| Roll stab | | | X |
| Stab-down on a knocked-down enemy | | | X (can happen by chance on a forward swing, `bg_saber.c:2825-2832`) |
| Backstab / back-slash variants | | | X in the default AI (only `NewBotAI_NF`, 12472-12481, `g_newBotAI 1` with force disabled) |
| Saber throw | Stock rule 14570-14578; knocked-down finisher 11826-11854 (by granting itself level 3) | Guiding rule impossible (14579); `NewBotAI` never presses for `doAltAttack` (13365 sets it, nothing consumes it) | |
| Staff kicks (alt-attack + direction) | | | X (happen only as a side effect of the kata press) |
| Flip kick (jaPRO jump kick) | `NewBotAI_Flipkick` when gripped, when gripping, on acquisition (7308-7339) | | |
| Saber lock | | Random 50 % attack per frame, no deliberate mashing or push (15103-15113) | |
| Block (stop attacking, face the swing) | | Early return at 10514 is undone by `doAttack` set at 10272-10280 and pressed at 15129; aim changes discarded at 15163; `saberDefending` never set | |
| Parry / counter | | Window logic cannot fire (9265-9280); stage 8 never produced (9305) | |
| Feint | | | X (code exists, never called) |
| Push | Narrow rules (11603-11606, 7296-7300, 7355-7377) | Projectile push dead (2960) | |
| Pull | X (11511-11583) | | |
| Grip | Selection and hold work (11758-11790, 7454) | Grip-kick aim discarded in the default AI | |
| Lightning | X (11611-11680, 7457-7501) | | |
| Drain | Works for dark-side bots | Hold relies on a selection it does not make (7505-7510); no movement while draining | |
| Rage | | On only at exactly 100 FP (7585); freezes combat movement while active (12215-12218); forced off by clearing the bit (7561) | |
| Speed | | Needs the enemy to have Absorb on (11912, 12103) and is cancelled the next frame (7533-7535) | |
| Heal | X (11989-12005) | | |
| Protect | X on, timed off (7236-7268, 7595-7625) | Uses the enemy's armor in its own health sum (7238) | |
| Absorb | X (7202-7234, 7627-7646) | | |
| Mind trick | X (11942-11987) | | |
| Team heal | X (12007-12040, 15052-15080) | | |
| Team energize | | No team check in the weight loop; self-granted level 3 (11803-11812) | |
| Force sense | | | X |
| Dedicated grip / lightning / drain buttons | | | X (no mapping exists) |
| Force jump | Hold-jump at jump-flagged waypoints (1707-1730, 14953-14989) | Levitation branch dead (15146-15150); never used tactically in combat | |
| Wall run / wall flip | | | X |
| Roll | | | X |
| Crouch | Waypoint flags and low obstacles (14991-14994) | | Never as a combat tool in the default AI |
| Get up from knockdown | `NewBotAI_Getup` (7270-7306) | Jump lands only every second think (`be_ea.cpp:256-259`) | No directional get-up or roll get-up |
| Dodge an incoming swing | | Back-step test reachable only outside 100 units (10950-10967 vs. 11140-11196) | |
| Use doors / lifts / buttons | | `EA_Use` presses the holdable key and blocks the real use key (779, 10099-10130) | |
| Taunt / bow / flourish / gloat / meditate | | | X |
| Duel challenge / accept | X, optional (`bot_honorableduelacceptance`, 14007-14064), by direct call | Timeout test `> level.time && < level.time - 2000` is impossible (14049-14050) | |

---

## 11. Ten gaps worth closing first

1. **Give `BotInputToUserCommand` the missing outputs**: `generic_cmd`, `forcesel` (and stop the Heal reset, `bg_pmove.c:15652`), the three dedicated force buttons, a real `BUTTON_USE`. Everything else can then go through input instead of direct server calls and playerstate writes.
2. **Make the movement keys part of the attack decision.** One owner for `forwardmove` / `rightmove` on the frame an attack starts, so direction, DFA, lunge, kata and kicks become possible (fix for findings 3, 4, 6).
3. **Stop discarding `ideal_viewangles`** in the default AI (15163), or route all combat aim through `goalAngles`.
4. **Replace the special ladder**: kata must not be first and unconditional, the lockout must not be taken when nothing was sent, and multi-frame moves need a small state machine instead of a one-frame press.
5. **Targeted style selection** (repeat the cycle until the wanted style is reached, or a set-style input), and delete or set `bs->saberPower`.
6. **Real defence**: honour the block decision (do not set `doAttack` first), make the back-step reachable inside 100 units, and fix the parry window.
7. **Fix the split `ACTION_SKI` / `ACTION_JUMPEDLASTFRAME` bit** and the alternate-frame jump, so held jumps and jump-attacks are deterministic.
8. **Repair the broken force behaviours**: Speed, Rage, Drain hold, team energize, and remove the self-granted force levels.
9. **Door / lift / button use and fallback navigation**: real use key, reachable jump-over test, frame-rate independent stuck test.
10. **Add the never-attempted moves** once 1 and 2 exist: roll, roll stab, stab-down, backstab family, butterflies / cartwheels, backflip attack, staff kicks, wall moves, and taunts via gencmd.
