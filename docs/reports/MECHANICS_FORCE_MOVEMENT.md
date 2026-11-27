# MECHANICS_FORCE_MOVEMENT — force powers, movement/acrobatics, taunts (source audit)

Repo: `TaystJK_AI-Improved-Bots` (TaystJK / jaPRO on OpenJK). Read-only audit, nothing built or run.
All citations are `file:line` relative to `codemp/` (`game/` unless another directory is given).

Status column: **V** = verified by reading the cited code. **D** = number derived by arithmetic from verified constants (not measured in game). **U** = uncertain / only partly traced.

Defaults assumed for "normal FFA play" (all from `game/g_xcvar.h`): `g_movementStyle 1` (=MV_JKA, :242), `g_tweakForce 0` (:215), `g_tweakWeapons 0` (:227), `g_flipKick 0` (:238), `g_fixRoll 0` (:240), `g_fixGetups 0` (:218), `g_forceRegenTime 200` (:102), `g_speed 250` (:156), `g_gravity 800` (:109), `g_maxForceRank 7` (:118), `g_forcePowerDisable 0` (:100), `g_forceDodge 1` (:99), `g_debugMelee 0` (:81), `g_saberRestrictForce 0` (:144), `g_useWhileThrowing 1` (:165), `g_friendlyFire 0` (:105), `g_lightningBlockEnabled 0` (:222), `sv_fps 40` (:177). Race mode (`sess.raceMode`) changes many rules and is ignored here except where noted.

---

## 0. How input reaches the game (usercmd, buttons, generic commands)

### 0.1 usercmd_t — `qcommon/q_shared.h:1443-1452` (V)

| Field | Type | Meaning |
|---|---|---|
| `serverTime` | int | command time |
| `angles[3]` | int | view angles (ANGLE2SHORT, minus `ps.delta_angles`) |
| `buttons` | int | BUTTON_* bitmask |
| `weapon` | byte | selected weapon |
| `forcesel` | byte | selected force power; copied to `ps.fd.forcePowerSelected` in Pmove if `!= 255` and the power is known (`bg_pmove.c:15652-15658`) |
| `invensel` | byte | selected holdable (`bg_pmove.c:15659-15662`) |
| `generic_cmd` | byte | one GENCMD_* per command, 0 = none |
| `forwardmove, rightmove, upmove` | signed char | -127..127; `upmove>0` jump, `upmove<0` crouch |

### 0.2 BUTTON_* — `qcommon/q_shared.h:1365-1389` (V)

| Bit | Value | Client bind (`client/cl_input.cpp`) | Server use |
|---|---|---|---|
| BUTTON_ATTACK | 1 | `+attack` (:1735) | primary attack |
| BUTTON_TALK | 2 | chat balloon | sets EF_TALK (`bg_pmove.c:14568`) |
| BUTTON_USE_HOLDABLE | 4 | `+button2` | use holdable item |
| BUTTON_GESTURE | 8 | `+button3` | basic taunt, see §5 (`bg_pmove.c:11364-11384`) |
| BUTTON_WALKING | 16 | `+speed` | walk flag; force-cleared if \|fwd\| or \|right\| > 64 (`bg_pmove.c:14562-14564`) |
| BUTTON_USE | 32 | `+use` (:1737) | use |
| BUTTON_FORCEGRIP | 64 | `+force_grip` (:1739) | hold = grip (`w_force.c:6012-6015`) |
| BUTTON_ALT_ATTACK | 128 | `+altattack` (:1741) | saber throw / staff kick / alt fire |
| BUTTON_ANY | 256 | any key | — |
| BUTTON_FORCEPOWER | 512 | `+useforce` (:1743) | use `ps.fd.forcePowerSelected` (`w_force.c:6057-6063`) |
| BUTTON_FORCE_LIGHTNING | 1024 | `+force_lightning` (:1745) | hold = lightning (`w_force.c:6027-6030`) |
| BUTTON_FORCE_DRAIN | 2048 | `+force_drain` (:1747) | hold = drain (`w_force.c:6042-6045`) |
| BUTTON_GRAPPLE | 4096 | `+button12` | jaPRO grapple; needs `g_allowGrapple` (default 0) (`g_active.c:5095-5104`) |
| BUTTON_DASH | 8192 | `+button13` | jaPRO dash/dodge/walljump — only MV_WSW / MV_TRIBES (`bg_pmove.c:14879-14882`, `5449-5451`) |
| BUTTON_STRAFEBOT | 16384 | `+button14` | not audited |
| BUTTON_TARGET | 32768 | `+button15` | target laser, needs `g_allowTargetLaser` (`g_active.c:5581`) |

### 0.3 GENCMD_* — `qcommon/q_shared.h:1407-1440` (V). One value per usercmd in `generic_cmd`; the client sets it from `cl.gcmdValue` (`client/cl_input.cpp:1295`). Server dispatch is the `switch` in `ClientThink_real` after `Pmove()` (`g_active.c:5234-5524`).

| # | Enum | Console cmd (`cl_input.cpp:1783-1813`) | Server action (`g_active.c`) | Debounce |
|---|---|---|---|---|
| 1 | GENCMD_SABERSWITCH | `sv_saberswitch` | `Cmd_ToggleSaber_f` (:5246-5251) | 300 ms |
| 2 | GENCMD_ENGAGE_DUEL | `engage_duel` | `Cmd_EngageDuel_f(ent,0)` (:5252-5271); in GT_DUEL/POWERDUEL converted to BUTTON_GESTURE (:5078-5081) | 100 ms |
| 3 | GENCMD_FORCE_HEAL | `force_heal` | `ForceHeal` (:5272-5277) | 300 ms |
| 4 | GENCMD_FORCE_SPEED | `force_speed` | `ForceSpeed(ent,0)` (:5278-5283) | 300 ms |
| 5 | GENCMD_FORCE_THROW | `force_throw` | `ForceThrow(ent,qfalse)` = push (:5284-5286) | none |
| 6 | GENCMD_FORCE_PULL | `force_pull` | `ForceThrow(ent,qtrue)` (:5287-5289) | none |
| 7 | GENCMD_FORCE_DISTRACT | `force_distract` | `ForceTelepathy` (:5290-5295) | 300 ms |
| 8 | GENCMD_FORCE_RAGE | `force_rage` | `ForceRage` (:5296-5301) | 300 ms |
| 9 | GENCMD_FORCE_PROTECT | `force_protect` | `ForceProtect` (:5302-5309) | 300 ms |
| 10 | GENCMD_FORCE_ABSORB | `force_absorb` | `ForceAbsorb` (:5310-5317) | 300 ms |
| 11 | GENCMD_FORCE_HEALOTHER | `force_healother` | `ForceTeamHeal` (:5318-5320) | none (power has 2000 ms) |
| 12 | GENCMD_FORCE_FORCEPOWEROTHER | `force_forcepowerother` | `ForceTeamForceReplenish` (:5321-5323) | none (2000 ms) |
| 13 | GENCMD_FORCE_SEEING | `force_seeing` | `ForceSeeing` (:5324-5329) | 300 ms |
| 14 | GENCMD_USE_SEEKER | `use_seeker` | item (:5330) | — |
| 15 | GENCMD_USE_FIELD | `use_field` | item (:5339) | — |
| 16 | GENCMD_USE_BACTA | `use_bacta` | item (:5348) | — |
| 17 | GENCMD_USE_ELECTROBINOCULARS | `use_electrobinoculars` | item (:5366) | 300 ms |
| 18 | GENCMD_ZOOM | `zoom` | binoculars (:5384) | 300 ms |
| 19 | GENCMD_USE_SENTRY | `use_sentry` | item (:5402) | — |
| 20 | GENCMD_USE_JETPACK | `use_jetpack` | old jetpack toggle, only if `!g_tweakJetpack` (:5411-5433) | 300 ms |
| 21 | GENCMD_USE_BACTABIG | `use_bactabig` | item (:5357) | — |
| 22 | GENCMD_USE_HEALTHDISP | `use_healthdisp` | event only (:5434) | — |
| 23 | GENCMD_USE_AMMODISP | `use_ammodisp` | event only (:5442) | — |
| 24 | GENCMD_USE_EWEB | `use_eweb` | item (:5450) | 300 ms |
| 25 | GENCMD_USE_CLOAK | `use_cloak` | cloak toggle (:5461) | 300 ms |
| 26 | GENCMD_SABERATTACKCYCLE | `saberAttackCycle` | `Cmd_SaberAttackCycle_f` (:5478-5490) | 300 ms (100 ms single saber with ST_FASTCYCLE) |
| 27 | GENCMD_TAUNT | `taunt` | `G_SetTauntAnim(TAUNT_TAUNT)` (:5491) | 1000 ms (shared taunt timer) |
| 28 | GENCMD_BOW | `bow` | `G_SetTauntAnim(TAUNT_BOW)` (:5497) | 1000 ms (shared emote timer) |
| 29 | GENCMD_MEDITATE | `meditate` | `TAUNT_MEDITATE` (:5503) | 1000 ms (emote timer) |
| 30 | GENCMD_FLOURISH | `flourish` | `TAUNT_FLOURISH` (:5509) | 1000 ms (taunt timer) |
| 31 | GENCMD_GLOAT | `gloat` | `TAUNT_GLOAT` (:5515) | 1000 ms (taunt timer) |

Notes (V): none of these are in the server `commands[]` table (`g_cmds.c:8887-9104`); sending e.g. `"taunt"` or `"force_throw"` as a *client command* through `trap->EA_Command` returns "Unknown command" (`g_cmds.c:9125-9130`). They only work as `ucmd.generic_cmd`.

### 0.4 Bot-specific transport facts (V)

| Fact | Evidence |
|---|---|
| `BotInputToUserCommand` does `memset(ucmd,0)` and never sets `generic_cmd`, `forcesel`, `invensel`. | `ai_main.c:758-867` (memset :765) |
| Bot action → button mapping: ATTACK→1, ALT_ATTACK→128, GESTURE→8, USE→BUTTON_USE_HOLDABLE(4), WALK→16, FORCEPOWER→512, SKI→BUTTON_DASH; BUTTON_USE(32) is set randomly. FORCEGRIP / FORCE_LIGHTNING / FORCE_DRAIN buttons are never produced by this function. | `ai_main.c:774-789` |
| `ACTION_JUMP` → `upmove=127`; `ACTION_CROUCH` → `upmove=-127`; MOVE* → ±127. | `ai_main.c:857-866` |
| Usercmd is built then submitted: `BotUpdateInput(...)` then `trap->BotUserCommand(client,&bs->lastucmd)`. Anything written to `bs->lastucmd` between those two lines (e.g. `generic_cmd`, `forcesel`, extra buttons) is sent. | `ai_main.c:15272-15273` |
| Bots are thought from `G_RunClient` → `ClientThink_real` (not from `ClientThink`), so the GENCMD switch runs for them too. | `g_active.c:5982-5984`, `6122-6126` |
| Because a bot's `forcesel` is 0 (=FP_HEAL) and not 255, every Pmove resets `ps.fd.forcePowerSelected` to FP_HEAL when the bot knows Heal. Frame order: bot AI (`SV_BotFrame`, `server/sv_main.cpp:1659`) → `G_RunFrame` → `WP_ForcePowersUpdate` (`g_main.c:4202`) → `G_RunClient`/Pmove (`g_main.c:4287`). So the existing bot habit of writing `ps.fd.forcePowerSelected` directly (`ai_main.c:7222…12113`) only holds for the frame in which it is written. | `bg_pmove.c:15652-15658`; order is **U** (read from call sites, not traced at run time) |
| `trap->EA_Command(client, "...")` → `SV_ExecuteClientCommand` → `ClientCommand`. | `botlib/be_ea.cpp:142-145`, `server/sv_bot.cpp:596-598` |
| FP_PUSH via BUTTON_FORCEPOWER ignores the "release the button first" rule for bots only. | `w_force.c:5097` |

---

## 1. Force powers

### 1.1 Global rules

| Rule | Detail | Cite | S |
|---|---|---|---|
| Enum order | FP_HEAL 0, LEVITATION 1, SPEED 2, PUSH 3, PULL 4, TELEPATHY 5, GRIP 6, LIGHTNING 7, RAGE 8, PROTECT 9, ABSORB 10, TEAM_HEAL 11, TEAM_FORCE 12, DRAIN 13, SEE 14, SABER_OFFENSE 15, SABER_DEFENSE 16, SABERTHROW 17 | `qcommon/q_shared.h:368-387` | V |
| Side | Light: HEAL, TELEPATHY, PROTECT, ABSORB, TEAM_HEAL. Dark: GRIP, LIGHTNING, RAGE, TEAM_FORCE, DRAIN. Neutral: LEVITATION, SPEED, PUSH, PULL, SEE, saber powers. Powers of the other side are zeroed. | `bg_misc.c:363-384`, `636-649` | V |
| Rank points | mastery ranks 0..7 = 0/5/10/20/30/50/75/100 points; per-power point cost in `bgForcePowerCost` | `bg_misc.c:306-339` | V |
| Force pool | 100 (`FORCE_POWER_MAX`), set at spawn | `w_saber.h:51`, `w_force.c:451` | V |
| Activation paths | (a) dedicated button (grip/lightning/drain), (b) GENCMD (table 0.3), (c) BUTTON_FORCEPOWER with selected power → `WP_DoSpecificPower` | `w_force.c:6012-6067`, `4992-5190` | V |
| Tap rule for (c) | Non-hold powers set `forceButtonNeedRelease=1`; BUTTON_FORCEPOWER must be released before the next use (cleared only when the button is up). Grip/lightning/drain are hold powers. | `w_force.c:5017-5187`, `6064-6067` | V |
| Usable at all (`WP_ForcePowerUsable`) | Not: race mode outside duel, ysalamiri, dead, spectator/follow/tempSpectate, power in `g_forcePowerDisableFFA` (outside duel), `BG_CanUseFPNow` false, power unknown or level 0, already active (except levitation), two-handed-saber restriction only if `g_saberRestrictForce`; then FP check. | `w_force.c:714-861` | V |
| `BG_CanUseFPNow` | False if ysalamiri, `forceRestricted`/`trueNonJedi`, on emplaced gun, on vehicle, in a normal (non-force) private duel except saber powers/levitation (push only in saber lock), in saber lock (except push), `fallingToDeath`, broken arm (push/pull/grip/lightning/drain). | `bg_misc.c:1890-1990` | V |
| FP check (`WP_ForcePowerAvailable`) | Always true for levitation and for an already-active power; lightning/drain need only FP ≥ 25; else FP ≥ `forcePowerNeeded[level][power]`. | `w_force.c:658-702` | V |
| Target eligibility (`ForcePowerUsableOn`) | Fails if target has ysalamiri, noclip, race mode, is in a duel with someone else / attacker is dueling someone else; grip fails on target with Absorb active or in a saber special; **push/pull fail on a target whose legs are in a knockdown/getup anim** (unless FT_PUSHPULLKD); vehicles only take lightning. | `w_force.c:553-656` | V |
| Regen | +1 FP every `g_forceRegenTime` ms (200) only while **no** power is active (drain alone is allowed), saber not in flight, not in a saber special move. Any other active power (speed, protect, absorb, sight, rage, levitation, grip…) freezes regen. Private duels use `g_saberDuelForceRegenTime`/`g_forceDuelForceRegenTime` (200). | `w_force.c:6095-6216` | V |
| Force boon / Jedi Master | +6 / +4 per tick instead of 1 | `w_force.c:6102-6107` | V |
| Stopped automatically | ysalamiri, `forceDeactivateAll`, tempSpectate, `BG_CanUseFPNow` false, death | `w_force.c:5820-5863`, `5965-5976` | V |
| Mutual exclusion | Starting Protect stops Rage+Absorb; Absorb stops Rage+Protect; Rage stops Protect+Absorb (unless FT_FORCECOMBO). Speed, Sight, Mind Trick combine freely. | `w_force.c:1664-1674`, `1713-1723`, `1778-1788` | V |
| Toggle-off delay | Speed/Sight/Protect/Absorb/Rage/Mind Trick can be switched off by re-triggering only after 1500 ms (`forceAllowDeactivateTime`). | `w_force.c:1585-1606`, `1620-1632`, `1647-1677`, `1697-1726`, `1749-1791`, `2968-2973` | V |
| Common pre-checks for offensive casts | Push/pull/grip/lightning/drain/mind trick all require `forceHandExtend == HANDEXTEND_NONE` and `weaponTime - saberDelay <= 0` (i.e. not mid-swing / not firing). Exceptions: push/pull allowed while in a getup anim; see per-power rows. | `w_force.c:1504-1522`, `1814-1822`, `2074-2082`, `2952-2960`, `3304-3327` | V |

### 1.2 FP cost table — `forcePowerNeeded[level][power]`, `bg_pmove.c:140-226` (V)

| Power | L1 | L2 | L3 | Extra drain while active |
|---|---|---|---|---|
| HEAL | 65 | 60 | 50 | — |
| LEVITATION | 10* | 10* | 10* | *table value unused for normal jumps; see §3 force-jump drain |
| SPEED | 50 | 50 | 50 | none |
| PUSH | 20 | 20 | 20 | — |
| PULL | 20 | 20 | 20 | — |
| TELEPATHY | 20 | 20 | 20 | none |
| GRIP | 30 | 30 | 60 (needed to start) | start drains fixed 30 (`GRIP_DRAIN_AMOUNT`, `w_saber.h:55`, `w_force.c:5057-5061`) + 1 FP / 100 ms (`w_force.c:4785-4789`) |
| LIGHTNING | 1 | 1 | 1 | needs FP ≥ 25 to start/continue; 1 FP at start + 1 FP per 50 ms tick (`w_force.c:1805`, `4888-4900`) |
| RAGE | 50 | 50 | 50 | health, not FP (see row) |
| PROTECT | 50 | 25 | 10 | 1 FP / 300 ms (`w_force.c:4921-4932`) + FP per damage absorbed |
| ABSORB | 50 | 25 | 10 | 1 FP / 600 ms (`w_force.c:4933-4946`) |
| TEAM_HEAL | 50 | 33 | 25 | — |
| TEAM_FORCE | 50 | 33 | 25 | — |
| DRAIN | 20 | 20 | 20 | needs FP ≥ 25; **5 FP per 50 ms tick** whether or not it hits (`w_force.c:2084`, `2516`, `4866-4870`) |
| SEE | 20 | 20 | 20 | none |
| SABER_DEFENSE | 2 | 1 | 0 | per block (saber audit) |
| SABERTHROW | 20 | 20 | 20 | once at throw (`bg_saber.c:3560-3563`) |

### 1.3 Per-power table

| Power (enum, side) | Activation (hold/tap) | Duration | Range / arc per level | Own-state requirements (beyond 1.1) | Effect on target, numbers | Counters / immunity | Code-derived tactical notes | Cite | S |
|---|---|---|---|---|---|---|---|---|---|
| **Heal** (FP_HEAL, light) | GENCMD 3 or FORCEPOWER; tap; instant | instant | self | health > 0 and < max | +5 / +10 / +25 HP (L1/L2/L3) | — | L3 = 25 HP for 50 FP. No hand-extend or weapon-time check: usable mid-swing. | `w_force.c:1203-1259` | V |
| **Jump** (FP_LEVITATION, neutral) | hold `upmove ≥ 10` after a normal jump | until landing | self | see §3 | — | — | everyone has at least L1 outside Siege (`w_force.c:5670-5681`) | §3 | V |
| **Speed** (FP_SPEED, neutral) | GENCMD 4 or FORCEPOWER; tap toggles | 10 / 15 / 20 s | self | not carrying a force-disabling siege item | `ps.speed × 1.7` (flat, level-independent). `forceSpeedLevels[]` is defined but not referenced elsewhere. | — | Blocks own FP regen for its whole duration. Cannot be cancelled in the first 1.5 s. While gripped, speed-active victims move at ×0.8 instead of ×0.2. | `w_force.c:1578-1611`, `1014-1040`; `bg_pmove.c:12137-12140`, `12156-12163`, `132-138` | V |
| **Push** (FP_PUSH, neutral) | GENCMD 5 (no debounce) or FORCEPOWER; tap | caster hand-extend 1000 ms; `PW_DISINT_4` 1100 ms (blocks next push/pull) | L1: single target under crosshair, trace 512 from eye (`radius/2`). L2: clients must pass `InFieldOfVision(viewangles, 60, …)`, L3: 180 (helper not read, so whether the number is a full or half angle is **U**), plus hard filters for everything: `dot(dir,forward) ≥ 0.6` (~53° half-angle), bbox-edge distance < 1024, in PVS, clear LOS (origin or eye). | hand-extend NONE (or KNOCKDOWN while in a getup anim), `weaponTime-saberDelay ≤ 0` (exception: BROLL getups only if `g_fixGetups>1`), not within 1100 ms of previous push / 600 ms of previous pull, `saberInFlight` only blocks if `g_useWhileThrowing 0` | Velocity **set** (xy) to `dir × max(16, 256×level − 0.7×dist)` (after counter reduction); z = same formula if victim z-velocity is 0 (min 128), else replaced. Sets `otherKiller` (kill credit) 5 s. No damage. **Missiles in cone are reflected** (`G_ReflectMissile`: ownership transferred, aimed back at the firer ±0.2 random; rockets stop homing). Not stuck det packs / trip mines; resting thermals handled separately. Pushes force-usable doors/buttons/func_static. | Target's own Push level is the defence (`otherPushPower`), **minus 1 if the target has any forward/right input**. If target can counter (`CanCounterThrow`: hand-extend NONE, on ground, `weaponTime ≤ 0`, push usable) and level ≥ attacker's: no movement. If lower: strength ×0.2 / ×0.6 / ×0.8 for level difference 1 / 2 / ≥3. Absorb active: lowers attacker's effective level by absorb level and refunds FP to the target. Teammates immune when `g_friendlyFire 0`. Knocked-down targets immune (default). | **Knockdown only if** effective level 3, target not already knocked down, `BG_KnockDownable`, and distance ≤ `64 × ((level − targetPushLevel) − 1)`: ≤128 u vs effective defence 0, ≤64 u vs defence 1, never vs defence ≥2. Defence used here ignores whether the target could actually counter. Knockdown = `HANDEXTEND_KNOCKDOWN` for 700 ms, `quickerGetup`. In a saber lock, push instead adds `2×level` lock hits. Push **breaks a grip on the caster** if the gripper is in the cone and push level ≥ gripper's grip level (gripper gets 1 s grip lockout). | `w_force.c:3276-4204`, `3117-3188`, `3263-3269`; `g_missile.c:43-103` | V |
| **Pull** (FP_PULL, neutral) | GENCMD 6 or FORCEPOWER; tap | caster hand-extend 400 ms; `PW_DISINT_4`/`PW_PULL` for 600 ms | same selection as push | same as push (also allowed during a getup anim; only push gets a torso animation overlay, pull changes no animation there) | Velocity set toward caster with same magnitude formula. **Disarm**: if target within 256 u, not a teammate, and `canPullWeapon` (target did not fully counter), chance 30 % / 70 % / 100 % by effective level to `TossClientWeapon` toward the puller (not saber/melee/pistol-and-below; not in duels). Missiles: nothing (pull branch is empty). | same as push (uses target's Pull level) | Knockdown rule identical to push (same code path, level 3 at close range). Pull does not reflect projectiles. SP-style "pull attack" (`PM_CheckPullAttack`) is compiled out on the server (`#if 0`). | `w_force.c:3374-3391`, `3872-3910`; `g_combat.c:506-535`; `bg_saber.c:2314-2341` | V |
| **Mind Trick** (FP_TELEPATHY, light) | GENCMD 7 or FORCEPOWER; tap toggles | 20 / 25 / 30 s; caster hand-extend 1000 ms | L1: one client hit by a 256-u trace from the eye. L2: every enemy client in a ±512 box and inside a 180° view arc. L3: ±1024 box, 360°. No LOS test at L2/L3. | hand-extend NONE, `weaponTime-saberDelay ≤ 0`, not carrying red/blue flag | Caster becomes invisible to the tricked clients (bit masks `forceMindtrickTargetIndex1-4`). | Target with Sight active is un-tricked each frame; target with ysalamiri; teammates never tricked. **Any offensive action by the caster (`dangerTime` updated by push/pull/grip/lightning/drain/saber throw…) while in PVS + visible un-tricks that target.** Power ends when no target remains tricked. | Costs 20 FP only if at least one target was tricked (L2/L3) | `w_force.c:2937-3110`, `4650-4704`, `150-156`, `1049-1070` | V |
| **Grip** (FP_GRIP, dark) | **hold** BUTTON_FORCEGRIP, or hold FORCEPOWER with grip selected | max 5 s (L1) / 4 s (L2, L3); caster hand-extend FORCE_HOLD | start: trace 256 u (`MAX_GRIP_DISTANCE`) from eye along view, must hit a client. Maintained while distance ≤ 256, target within `InFront` 0.9 cone (L1/L2 only; L3 has no cone), and LOS (unless FT_JK2GRIP). | hand-extend NONE, `weaponTime-saberDelay ≤ 0`, `forceGripUseTime` expired (3 s after any grip ends; 1 s if broken by push) | 2 dmg/s (no armor). L2: victim lifted (`PM_FLOAT`, z-vel 30). L3: victim dragged toward a point 128 u in front of the caster (+16 z), velocity 8…700 u/s by distance, updated every 300 ms. At >3000 ms held (L2/L3): one-time 20 (L2) / 40 (L3) dmg and victim `HANDEXTEND_CHOKE` for 2000 ms. Victim state: `forceGripCripple` → speed ×0.2, BUTTON_ATTACK/ALT_ATTACK stripped, saber forced off (unless `g_fixSaberInGrip`), jetpack off. Caster speed ×0.4 while gripping. | Cannot start on a target with Absorb active, already gripped/crippled, or in a saber special move. Absorb during grip lowers effective level (0 ends it). Victim's push/pull breaks it when level ≥ grip level. Teammates immune without friendly fire. | **Grip-to-drop:** L3 lets the caster steer the victim with the view direction; releasing (button up, timeout, FP 0, LOS/cone lost) restores `PM_NORMAL` so the victim falls from wherever it is; `otherKiller` credit lasts 5 s. Victim keeps force powers, so a gripped player can still push. | `w_force.c:1494-1576`, `4337-4576`, `4245-4274`, `4778-4798`, `5927-5943`; `bg_pmove.c:12110-12123`, `12156-12163`, `14547-14551` | V |
| **Lightning** (FP_LIGHTNING, dark) | **hold** BUTTON_FORCE_LIGHTNING or FORCEPOWER; L1 = fixed 500 ms burst, L2/L3 continue while held | L1 500 ms; L2/L3 until release / FP < 25 | L1/L2: single hitscan trace 2048 u from `ps.origin` (not eye). L3: every damageable entity within radius 300 (`FORCE_LIGHTNING_RADIUS`) with `dot ≥ 0.5` (60° half-angle), PVS + LOS. | FP ≥ 25, hand-extend NONE, `weaponTime-saberDelay ≤ 0`, cooldown after stop: 3000 ms (L1) / 1500 ms (L2, L3) | 1–2 damage per 50 ms tick (20–40 dps), MOD_FORCE_DARK, goes through normal armor rules; ×2 if caster holds WP_MELEE and has L3. Electrify effect; decloaks. | Absorb: effective level 0 → no damage and 400 ms immunity; otherwise 1 dmg per tick with 300/100 ms immunity windows. Optional saber block (`g_lightningBlockEnabled`, default **0**): blocking saber user pays 5 FP per tick and takes 0. Teammates immune without friendly fire. | Caster is locked in FORCE_HOLD hand-extend, so no saber swings while channeling. | `w_force.c:1799-1835`, `1837-1945`, `1947-2065`, `4275-4290`, `4873-4902`; `w_saber.c:10086-10150` | V |
| **Rage** (FP_RAGE, dark) | GENCMD 8 or FORCEPOWER; tap toggles | 8 / 14 / 20 s | self | health ≥ 10, not in rage recovery | Self: −2 HP every 150 / 300 / 450 ms (cannot kill: floors at 1 HP and stops). Speed ×1.3. Saber anim speed ×2. Weapon `addTime` ×0.75. Incoming damage ×0.5 and then `take /= (level+1)`; **client-inflicted damage cannot reduce a raging target below 1 HP** (unless DAMAGE_NO_PROTECTION). Saber-lock hits +level. | — | After it ends: 10 s recovery — speed ×0.75, weapon time ×1.5, cannot re-rage. | `w_force.c:1742-1797`, `1085-1106`, `4291-4297`, `4805-4843`; `g_combat.c:4913-4919`, `6082-6117`; `bg_pmove.c:12141-12148`, `11327-11332`; `w_saber.c:9056-9059`; `g_active.c:5019-5021` | V |
| **Protect** (FP_PROTECT, light) | GENCMD 9 or FORCEPOWER; tap toggles | 20 s | self | — | Per hit, with `capped = min(damage, 100 / 200 / 400)`: damage taken = `capped × (60 % / 40 % / 20 %)` (the part above the cap is removed entirely), FP cost = `capped × 1 / 0.5 / 0.25` (halved with force boon). If FP goes below 0 the shortfall comes back as damage and FP is set to 0. | DAMAGE_NO_PROTECTION bypasses | Stops Rage and Absorb on activation. | `w_force.c:1640-1688`, `1107-1115`; `g_combat.c:5922-6012` | V |
| **Absorb** (FP_ABSORB, light) | GENCMD 10 or FORCEPOWER; tap toggles | 20 s | self | — | Against lightning / drain / grip / push / pull only: attacker's effective level −= absorb level; absorber gains `(FP spent / 3) × absorb level` FP. Grip cannot even start. | — | Level-3 absorb fully negates level-3 push/pull/lightning/drain/grip. | `w_force.c:1690-1740`, `863-957`, `606-619` | V |
| **Team Heal** (FP_TEAM_HEAL, light) | GENCMD 11 or FORCEPOWER; tap | instant; 2000 ms debounce | sphere radius 256 / 384 / 512, PVS | needs ≥1 damaged teammate in range (`OnSameTeam`) | +50 / +33 / +25 HP to each (1 / 2 / ≥3 targets) × `g_teamHealScale`; FP spent only on success | — | no effect outside team gametypes | `w_force.c:1286-1391` | V |
| **Team Energize** (FP_TEAM_FORCE, dark) | GENCMD 12 or FORCEPOWER; tap | instant; 2000 ms debounce | same radii | teammate with FP < 100 in range | +50 / +33 / +25 FP × `g_teamEnergizeScale` | — | — | `w_force.c:1393-1492` | V |
| **Drain** (FP_DRAIN, dark) | **hold** BUTTON_FORCE_DRAIN or FORCEPOWER; L1 fixed 500 ms, L2/L3 while held | L1 500 ms; else until release / FP < 25 | L1/L2: hitscan trace 2048 u from `ps.origin`. L3: radius 512 (`MAX_DRAIN_DISTANCE`), `dot ≥ 0.5`, PVS + LOS. | FP ≥ 25, hand-extend NONE, `weaponTime-saberDelay ≤ 0`, cooldown 3000 ms (L1) / 1500 ms | Per 50 ms tick: target loses 2 / 3 / 4 **FP**; caster gains the same amount of **health**; target's regen delayed 800 ms. Caster pays 5 FP per tick and own regen is delayed 500 ms. Does nothing to a target with 0 FP. | Absorb reduces/negates (and feeds the absorber). Teammates immune without friendly fire. | Net FP-negative for the caster (5 spent per tick); it is a health-gain / FP-denial tool. | `w_force.c:2067-2101`, `2103-2276`, `2279-2525`, `4310-4329`, `4844-4872` | V |
| **Sight** (FP_SEE, neutral) | GENCMD 13 or FORCEPOWER; tap toggles | 10 / 20 / 30 s | self | — | Removes the user from every mind-tricker's target list. With `g_forceDodge 1` and Sight **L3 active**: automatic dodge of hitscan shots (`Jedi_DodgeEvasion`) when on ground, `weaponTime ≤ 0`, hand-extend NONE, hit not on legs/feet — sets `HANDEXTEND_DODGE` 300 ms. | — | Dodge is automatic, not a player input. Callers are in `g_weapon.c:834, 1147, 4825` (weapon side not audited → **U** which weapons). | `w_force.c:1613-1638`, `1141-1162`, `4659-4664`, `6232-6360` | V/U |
| **Saber Throw** (FP_SABERTHROW, neutral) | BUTTON_ALT_ATTACK with saber (non-staff style) | see §2.4 | see §2.4 | see §2.4 | see §2.4 | | | §2.4 | V |

### 1.4 Force-related cvars

| Cvar (default) | Effect | Cite | S |
|---|---|---|---|
| `g_forcePowerDisable` (0) | Bitmask by FP_* enum; powers removed in `BG_LegalizedForcePowers`; change re-inits all clients | `bg_misc.c:652-656`; `g_cvar.c:401-411`; `w_force.c:241-248` | V |
| `g_forcePowerDisableFFA` (0) | Same bitmask, but only blocks use **outside** private duels | `w_force.c:743-745` | V |
| `g_maxForceRank` (7) | Rank cap; ≤0 or ≥8 reset to 7 | `w_force.c:164-168` | V |
| `g_forceRegenTime` (200) | ms per FP point | `w_force.c:6100` | V |
| `g_saberDuelForceRegenTime` / `g_forceDuelForceRegenTime` (200) | regen in NF / FF private duels | `w_force.c:6138-6143` | V |
| `g_forceDodge` (1) | 0 off; 1 = Sight L3 dodge; 2 = Speed-based random dodge | `w_force.c:6241-6294` | V |
| `g_saberRestrictForce` (0) | if 1, two-handed/dual sabers ignited block push/pull/trick/grip/lightning/drain | `w_force.c:805-859` | V |
| `g_useWhileThrowing` (1) | if 0, no push/pull while saber is in flight | `w_force.c:3309-3312` | V |
| `g_fixSaberInGrip` (0) | 0 = gripped victim's saber is forced off each frame; ≥3 lets them re-ignite | `w_force.c:5933-5936`; `g_cmds.c:3823-3829` | V |
| `g_fixLightning` (0) | ≥1: non-absorbing victims gain FP from lightning; >1: damage fixed 1; 3: no melee ×2 | `w_force.c:884-921`, `1869-1872`, `1910-1911` | V |
| `g_fixGetups` (0) | ≥1 grip, >1 push/pull allowed during BROLL getups despite weaponTime | `w_force.c:1512`, `3317` | V |
| `g_lightningBlockEnabled` (0), `g_lightningBlockCost` (5), `g_lightningBlockReduction` (0.7) | fork addition: saber-blocking stance negates lightning for FP. `g_lightningBlockReduction` is not referenced in `WP_SaberBlockLightning`. | `w_saber.c:10086-10150` | V |
| `g_teamHealScale`, `g_teamEnergizeScale`, `g_teamAbsorbScale` (1) | multipliers | `w_force.c:1347-1355`, `1454-1462`, `938-939` | V |
| `g_godChat` (0) | in FFA, chatting players cannot use / be hit by force | `w_force.c:576-581` | V |

`g_tweakForce` bits (`g_local.h:247-270`), all off by default:

| Bit | Name | Effect | Cite | S |
|---|---|---|---|---|
| 1<<0 | FT_NO_CROUCHATTACK_FP | crouch special attacks cost no FP | `bg_saber.c:2799`, `2820` | V |
| 1<<1 | FT_FIX_PROJ_PUSH | pushed missiles go where the pusher aims (±0.1) instead of back at owner | `g_missile.c:84-91` | V |
| 1<<2 | FT_PUSHPULLKD | push/pull may hit knocked-down players | `w_force.c:629-633` | V |
| 1<<3 | FT_GRIPABSORB | grip gives no FP to an absorber | `w_force.c:878-879` | V |
| 1<<4 | FT_FORCECOMBO | protect/absorb/rage may stack; speed+rage = speed ×2.2 | `w_force.c:1664`, `1713`, `1778`; `bg_pmove.c:12128-12134` | V |
| 1<<5 | FT_PULLSTRENGTH | pull adds to velocity instead of replacing it | `w_force.c:3999-4002`, `4020-4021` | V |
| 1<<6 | FT_JK2GRIP | grip not broken by lost LOS | `w_force.c:4398-4402` | V |
| 1<<7 | FT_FASTGRIP | gripper speed ×0.8 instead of ×0.4 | `bg_pmove.c:12116-12122` | V |
| 1<<8 | FT_PUSHPULLITEMS | push/pull moves ammo/armor/health items | `w_force.c:4070-4098` | V |
| 1<<9 | FT_FIXDRAINCOF | L3 drain cone origin raised, cone 0.7 | `w_force.c:2294-2296`, `2360-2374` | V |
| 1<<10 | FT_JK2KNOCKDOWN | push/pull knockdown at ≤128 u regardless of level difference | `w_force.c:3923-3924` | V |
| 1<<11 | FT_JK2GETUPS | no push during getup, no roll getups, immediate getup logic with longer timers | `w_force.c:3304`, `5733-5766` | V |
| 1<<12 | FT_JK2PULLROLL | push/pull allowed while rolling | `w_force.c:3321-3324` | V |
| 1<<13 | FT_NODRAINABSORB | absorber gains nothing from drain | `w_force.c:2156-2159` | V |
| 1<<14 | FT_GRIPDURINGROLL | grip allowed while rolling | `w_force.c:1515` | V |
| 1<<15 | FT_WEAKPULL | pull acts as level 1, strength 64, costs 60 FP | `w_force.c:3366-3367`, `3425-3428` | V |
| 1<<16 | FT_NERFED_WEAPPULL | pull-disarm range 128 instead of 256 (unless victim rages) | `w_force.c:3874-3876` | V |
| 1<<17 | FT_WEAPON_PULLRESIST | target firing/charging a gun takes half push/pull | `w_force.c:3864-3868` | V |
| 1<<18 | FT_NORAGEFIRERATE | rage fire-rate bonus only for saber/melee | `bg_pmove.c:11327-11332` | V |
| 1<<19 | FT_BUFFMINDTRICK | trick only broken by attacks when target is within 60° of caster's view | `w_force.c:4670-4680` | V |
| 1<<20 | FT_BUFFMELEE | melee grapple tweak (not audited) | `bg_pmove.c:14313` | U |
| 1<<21 | FT_DRAINDMGNERF | L3 drain takes 3 FP, gives 4 HP | `w_force.c:2145-2148` | V |
| 1<<22 | FT_FIXGRIPPEDREGEN | allows regen while gripped and floating | `w_force.c:6095` | V |
| 1<<23 | FT_FIXLINEDRAIN | L3 drain becomes a 512-u box trace with chaining | `w_force.c:2298`, `2408-2512` | V |

---

## 2. Combination-relevant facts (victim states and timers)

### 2.1 Knockdown life cycle (`HANDEXTEND_KNOCKDOWN`)

| Phase | What is true | Cite | S |
|---|---|---|---|
| Sources | Push/pull L3 at close range: timer **700 ms**, `quickerGetup=qtrue` (`w_force.c:3923-3930`). `G_Knockdown()`: **1100 ms** (`g_combat.c:4661-4670`). Staff/melee kick `G_TossTheMofo`: **700 ms** + z-vel 200 (`w_saber.c:8008-8032`). Flipkick (`g_flipKick>0` only): **1100 ms**, 30 % chance by default (`g_active.c:5613-5799`). | as listed | V |
| While timer runs (`forceHandExtendTime ≥ level.time`) | Victim: `saberMove=0`, no saber block, `weaponTime=0`, `weaponstate=READY`, zoom cleared every frame. `ps.speed = 0`. Cannot jump. Body treated as ducked (crouch hull). Legs anim BOTH_KNOCKDOWN1. | `w_force.c:5706-5722`; `bg_pmove.c:12090-12095`, `3379-3384`, `7430-7459`, `10196-10235` | V |
| Follow-up rule | Default: push/pull cannot affect a victim whose legs are in a knockdown/getup anim (`BG_InKnockDown`), so a second push does nothing; other damage works. Grip is not blocked by this rule. | `w_force.c:629-633`; `bg_pmove.c:12414-12463` | V |
| When timer expires, victim input decides (checked every frame) | **Direction key held** (exactly one axis): roll getup BOTH_GETUP_BROLL_R/L/F/B, hand-extend cleared → victim is in `BG_InRoll` (crouch hull, cannot jump). **Jump held (no direction)**: force getup, `forceDodgeAnim=2`, +500 ms (no jump-level requirement on this path). **No input**: stays down up to **4000 ms more**, then `quickerGetup` → getup anim 3 for 500 ms with z-vel 300, else normal getup 1000 ms. | `w_force.c:5570-5625`, `5723-5775` | V |
| Attacker window | Minimum helpless time = knockdown timer (700 or 1100 ms) + chosen getup (≥ 500 ms force getup, or roll getup anim length — anim lengths are data, not in code). An idle/AFK victim is helpless for timer + 4000 ms + getup. | derived from rows above | D |
| Victim options while down | Push and pull pass the hand-extend check while the legs are in a getup anim (push additionally plays on the torso, `forceDodgeAnim += 8`). While still lying in BOTH_KNOCKDOWN1 they are refused. | `w_force.c:3304-3307`, `3400-3407` | V |
| Fall damage while knocked down | Landing with legs in a pure knockdown anim: damage threshold drops to delta > 14 and damage = delta × 1 (not × 0.16). | `g_active.c:1936-1957` | V |

### 2.2 Push / pull / grip aftermath

| Situation | State left behind | Cite | S |
|---|---|---|---|
| Pusher | `HANDEXTEND_FORCEPUSH` 1000 ms (no attacks: `PM_Weapon` returns early while hand-extend ≠ NONE), then `HANDEXTEND_WEAPONREADY` → `weaponTime += 250`. So ≈1250 ms before the pusher can swing/fire. `PW_DISINT_4` 1100 ms blocks further push/pull and counter-throws. | `w_force.c:3394-3409`; `bg_pmove.c:10103-10139`, `10140-10325`; `w_force.c:5798-5801` | V |
| Puller | `HANDEXTEND_FORCEPULL` 400 ms (200 ms in Siege with saber) + 250 ms raise ≈ 650 ms. `PW_DISINT_4`/`PW_PULL` = 600 ms. | `w_force.c:3374-3391` | V |
| Pushed/pulled victim (no knockdown) | Velocity replaced; `pushEffectTime` 600 ms; `otherKiller` for 5 s (2 s with `g_fixKillCredit`). No stun: the victim keeps full control (normal air control applies). | `w_force.c:3970-4024` | V |
| Victim who countered | Forced into FORCEPUSH (1000 ms) / FORCEPULL (400 ms) hand-extend + `PW_DISINT_4` +200 ms — i.e. a successful counter still locks the defender's weapon for that time. | `w_force.c:3808-3831` | V |
| Pull-to-saber | Pull sets velocity toward the puller; the puller is free again after ≈650 ms, the victim is not stunned. At ≤256 u gun users can lose the weapon (30/70/100 %). Saber users cannot be disarmed by pull. | `w_force.c:3872-3910`; `g_combat.c:531-534` | V |
| Grip release | Victim: `forceGripChangeMovetype = PM_NORMAL` immediately; `forceGripCripple` clears when `forceGripBeingGripped` (level.time+1000, refreshed every frame of the grip) expires → up to 1 s of ×0.2 speed and no attack/alt-attack after release. After the 3-s squeeze: `HANDEXTEND_CHOKE` for 2000 ms. Gripper: 3 s grip cooldown, hand-extend cleared. | `w_force.c:4245-4274`, `4413-4477`, `5927-5943`; `bg_pmove.c:14547-14551` | V |
| Breaking a grip (victim) | `ForceThrow` with the gripper inside the push/pull selection and effective level ≥ gripper's grip level → gripper's grip stopped, gripper `forceGripUseTime = +1000`. Victim must itself satisfy the push pre-checks (hand-extend NONE etc.). | `w_force.c:3954-3968` | V |

### 2.3 Other victim timers

| Event | Timer | Cite | S |
|---|---|---|---|
| Lightning hit | `electrifyTime = +800 ms` (visual), refreshed every 400 ms | `w_force.c:1932-1935` | V |
| Drain hit | target `forcePowerRegenDebounceTime = +800 ms` | `w_force.c:2217` | V |
| Sight dodge | `HANDEXTEND_DODGE` 300 ms, `ps.speed = 0` during it | `w_force.c:6343-6345`; `bg_pmove.c:12085-12088` | V |
| Wall-jump push-off | attacker has `PMF_TIME_KNOCKBACK`, `pm_time = 500` (no control for 0.5 s) | `bg_pmove.c:2188-2193` | V |
| Landing | `legsTimer = TIMER_LAND` (130 ms) | `bg_pmove.c:6578`; `bg_local.h:30` | V |

### 2.4 Saber throw and return

| Item | Detail | Cite | S |
|---|---|---|---|
| Trigger | BUTTON_ALT_ATTACK with WP_SABER, style not SS_STAFF (staff kicks instead), `weaponTime < 1`, `ps.saberCanThrow`, FP_SABERTHROW level > 0, `BG_CanUseFPNow`, FP ≥ 20, and an 80-u (`SABER_MIN_THROW_DIST`) saber-box trace forward must be clear. Not in race mode. In MV_TRIBES alt-attack is a saber move instead. | `bg_saber.c:3496-3566`, `3156-3173`; `w_saber.h:89` | V |
| Cost | 20 FP once, at the moment of throw | `bg_saber.c:3560-3563` | V |
| Flight | Initial velocity 400 u/s along view. Level ≥ 2: re-aimed toward the crosshair trace point at 500 u/s; level 3 trace also hits players (MASK_PLAYERSOLID). | `w_saber.c:9275`, `7714-7749` | V |
| Return | Auto-return when: ALT_ATTACK released ≥ 500 ms after the throw; out > 6000 ms; ysalamiri; force use blocked; distance ≥ 700 × throw level (700 / 1400 / 2100). After return: `saberThrowDelay = +500 ms` (300 ms on one path), `saberCanThrow` false until then. | `w_saber.c:7621`, `7679-7712`, `6908`, `7472`, `7557`, `9028` | V |
| Damage | `SABER_THROWN_HIT_DAMAGE 30`, return pass 5 | `w_saber.c:6330-6331` | V (constants only; damage application not traced → U for final numbers) |
| While in flight | No FP regen (`w_force.c:6098`). Torso locked in BOTH_SABERPULL (no saber attacks) except dual-saber users. Push/pull still allowed (`g_useWhileThrowing 1`). `sv_saberswitch` knocks the flying saber down. Cannot start a private duel. | `bg_saber.c:3570-3591`; `g_cmds.c:3832-3839`, `4271-4272` | V |
| Lost saber | If knocked out of the air: retrievable by holding BUTTON_ATTACK after `SABER_RETRIEVE_DELAY` 3000 ms; forced return after 20 s (`MAX_LEAVE_TIME`). | `w_saber.c:6989-6996`, `6914-6921`, `6816` | V |

---

## 3. Movement and acrobatics

Default physics for normal FFA is **MV_JKA** (`g_movementStyle 1`). `PM_GetMovePhysics` returns `g_movementStyle` for non-racers if it is one of SIEGE/JKA/QW/CPM/Q3/PJK/WSW/SP/SLICK/OCPM/TRIBES (`bg_pmove.c:442-467`). `/move <style>` is refused unless `g_raceMode` is on (`g_cmds.c:6727-6730`). `g_tweakJump` and `g_dodge*` cvars **do not exist** in this codebase (grep of `game/` returned nothing).

### 3.1 Movement table (MV_JKA unless stated)

| Mechanic | Trigger inputs | State requirements | Result / numbers | Cooldown | Cite | S |
|---|---|---|---|---|---|---|
| Run | `forwardmove/rightmove` ±127 | on ground | `ps.speed = g_speed` (250); ground accel 10, friction 6, stop speed 100 | — | `g_active.c:4299`; `bg_pmove.c:69-84` | V |
| Backpedal | `forwardmove < 0`, no BUTTON_WALKING, on ground | — | speed ×0.75 (187.5) | — | `bg_pmove.c:12098-12107` | V |
| Walk | \|move\| ≤ 64 (+BUTTON_WALKING) | — | wishspeed scales with command magnitude: 64/127 × 250 ≈ 126 | — | `bg_pmove.c:1596-1628`, `14562-14564` | D |
| Crouch | `upmove < 0` | not rolling, not on vehicle | `PMF_DUCKED`; hull top 40 → 16 (`crouchheight`), viewheight 12; wishspeed ≤ speed × 0.5 (125). Stands up only if the standing hull fits. | — | `bg_pmove.c:7430-7519`, `6020-6024`, `70`; `bg_public.h:74-81` | V |
| Air control | move keys in air | — | `PM_Accelerate(wishdir, wishspeed, pm_airaccelerate = 1.0)` — the standard Quake-3 formula, so strafe-jump speed gain exists but there is no CPM air-control and no auto-bunnyhop | — | `bg_pmove.c:5164`, `5228-5231`, `76` | V |
| Jump | `upmove ≥ 10` (bots: 127), must have been released since the last jump (`PMF_JUMP_HELD` cleared when `upmove < 10`) | on ground; not knocked down / thrown, not in roll, not `PMF_RESPAWNED`, not jetpacking; disruptor zoom blocks jump | `velocity[2] = JUMP_VELOCITY (225)`; sets `forceJumpZStart` | none (re-press required) | `bg_pmove.c:3379-3403`, `3751-3766`, `4533-4612`, `14732-14735`, `14522-14526`; `bg_public.h:62` | V |
| Force jump | keep `upmove ≥ 10` held after leaving the ground | `PM_ForceJumpingUp`: in air, `PMF_JUMP_HELD`, levitation level > 0, `velocity[2] > 0`, not in special-jump anim / saber special, no ysalamiri, `BG_CanUseFPNow`; FP > 0 once above 32 u; `g_onlyBhop`/RESTRICT_BHOP disables it | Each frame while `curHeight < forceJumpHeight[level]`: `velocity[2] = ((H − cur)/H × forceJumpStrength[level]) / 10 + 225`. H = 96 / 192 / 384 (L1/L2/L3), strength 420 / 590 / 840. On reaching H (or releasing / FP 0) z-velocity is capped at 225 and the player coasts. Levitation becomes "active" once above 32 u. | — | `bg_pmove.c:1672-1718`, `3519-3746`, `228-246` | V |
| Force jump FP drain | automatic while levitation active | — | every 200 ms (L1) / 300 ms (L2, L3): `jumpDrain` = 20 / 16 / 12 / 8 / 6 / 4 for z-vel > 250 / 200 / 150 / 100 / 50 / 0, **divided by jump level**; 0 when falling. The "duel uses 1 instead of 5" argument is ignored by `BG_ForcePowerDrain` for levitation, so duel gametypes drain the same. | — | `bg_pmove.c:3428-3450`; `bg_saber.c:55-123` | V |
| Charged force jump (`ForceJump`) | BUTTON_FORCEPOWER with FP_LEVITATION selected | — | **Unreachable for players**: selection of FP_LEVITATION is reset to 0 every frame for non-NPCs, and the server rewrites `forcesel == FP_LEVITATION` to 255. | — | `w_force.c:5651-5652`, `6057-6063`; `server/sv_client.cpp:1728-1731` | V |
| Double jump | — | — | Not in MV_JKA. A +100 z "double jump" exists only for QW/CPM/OCPM/Q3/PJK/WSW/RJ*/SLICK/BOTCPM styles. | — | `bg_pmove.c:4535-4568` | V |
| Backflip | `upmove > 0` + `forwardmove < 0`, no BUTTON_ATTACK | on ground, saber or melee, levitation > 0, flips allowed by saber | BOTH_FLIP_BACK1; xy velocity set to −150 × forward; z = 225 + 128 = 353; marks levitation active | — | `bg_pmove.c:3786-3800`, `3960-3969`, `4059-4066`, `4089-4115` | V |
| Wall run (side) | `upmove > 0` + `forwardmove > 0` + `rightmove ≠ 0` | on ground, saber/melee, levitation ≥ L2, wall within 16 u on the strafe side with `0 ≤ normal.z ≤ 0.4` and facing (dot > 0.7) | BOTH_WALL_RUN_RIGHT/LEFT; z = 590/2 + 128 = 423; then `PM_AdjustAngleForWallRun` locks yaw parallel to the wall and sets speed 250 (fwd held) / 175 / 100 (back) while `legsTimer > 500`; half gravity (`PM_DoSlowFall`) | — | `bg_pmove.c:3865-3879`, `3915-3924`, `4009-4046`, `1768-1874`, `533-541`, `14873-14877` | V |
| Wall-run flip-off | press jump again during the wall run | `legsTimer` between 400 and animLen−400, wall still within 16 u | BOTH_WALL_RUN_*_FLIP; xy ×0.5 then ±150 away from the wall | — | `bg_pmove.c:4123-4191` | V |
| Wall flip (side) | `upmove > 0` + `rightmove ≠ 0` + `forwardmove == 0` | on ground, saber/melee, levitation ≥ L2, wall (or, with `g_flipKick`, a player) within 16 u on that side | BOTH_WALL_FLIP_RIGHT/LEFT; xy set to 150 away from the wall; z = 590/2.25 + 128 ≈ 390. Hitting a client sets `forceKickFlip` (damage only matters with flipkick rules, see below). | `g_flipKick 2`: 50 ms | `bg_pmove.c:3881-3912`, `3926-3957`, `4047-4058`, `4069-4085` | V |
| Wall run up / back flip (front) | in air: release jump, then `upmove > 0` + `forwardmove > 0` | saber/melee, levitation ≥ L2, walkable ground ≤ 80 u below, legs anim BOTH_JUMP1 or BOTH_INAIR1, wall within 32 u ahead (dot > 0.7 or non-bmodel entity) | L2: BOTH_WALL_FLIP_BACK1, velocity −150 × fwd, z += 150. L3: BOTH_FORCEWALLRUNFLIP_START, z = 840/2 = 420, then runs up the wall at z-vel 300 while `forwardmove > 0`; ends by flipping back (−300 fwd, +200 z) or, if a ledge is found, BOTH_FORCEWALLRUNFLIP_ALT (100 fwd, +400 z) onto it. Costs "5" → actual drain by velocity table. | — | `bg_pmove.c:4316-4392`, `1884-2014`, `4193-4240` | V |
| Wall grab + wall jump | in air: release jump, then `upmove > 0` + a direction key toward a wall | levitation **L3**, saber/melee, not in a special jump (rebounds and backflips allowed), `velocity[2] > −1200`, height above jump start < 418 − 168 = 250 u, vertical wall (\|normal.z\| ≤ 0.2) within 8 u in the pushed direction, not moving away from it | `PMF_STUCK_TO_WALL`, BOTH_FORCEWALLREBOUND_*; held against the wall (no gravity) while `legsTimer > 100`; then auto push-off: xy = 200 away from wall, z = 840/2.5 = 336, `pm_time 500` no-control. Holding on indefinitely needs `g_debugMelee > 1` (default 0). No offensive force powers while stuck only if `g_debugMelee`. | height cap only | `bg_pmove.c:4396-4474`, `2023-2210`, `2222-2235`, `2016-2021`; `w_force.c:785-803` | V |
| Roll | `upmove < 0` while running (`forwardmove` → forward roll, or back roll if `PMF_BACKWARDS_RUN`; else `rightmove` sign → side roll) | on ground, legs in a **running** anim and speed² ≥ 40000 (≥ 200 u/s) (`g_fixRoll 0`); weapon saber or melee (guns need WT_ALLOW_GUNROLL); not attacking / spinning / starting an attack; no ysalamiri; `BG_CanUseFPNow(LEVITATION)`; 64-u crouch-hull trace in the roll direction clear; not `client->pers.noRoll` | Sets BOTH_ROLL_F/B/R/L, `PMF_ROLLING` (crouch hull, normal view height), `saberMove = LS_NONE`. Speed = `legsTimer/1.5` (cap 600) while `legsTimer > 800`, then `legsTimer/5`; back roll `/2.5` then `/6`. Input is overridden by `BG_CmdForRoll`. Cannot jump while rolling. | none in code (re-roll needs a running anim again) | `bg_pmove.c:8340-8444`, `6249-6379`, `12354-12383`, `14553-14556`, `3400-3403` | V |
| Roll invulnerability | — | — | **None.** The only roll special-cases found: rolling players cannot be put in a saber lock (`w_saber.c:1614-1621`) and a death-anim special case (`g_combat.c:993`). No `BG_InRoll` test in `G_Damage`. | — | grep `BG_InRoll` over `g_combat.c`, `w_saber.c`, `g_weapon.c`, `g_missile.c` | V |
| Landing roll | be ducked (`upmove < 0`) at touchdown with a move key held | landing delta ≥ 2, not knocked down, hand-extend NONE, `PM_TryRoll` succeeds | fall delta ÷ 3 (after the ×2 for being ducked → net ×2/3) | — | `bg_pmove.c:6471-6474`, `6608-6637` | V |
| Cartwheel / aerial | BUTTON_ATTACK + `rightmove ≠ 0` + jump (`upmove > 0` or jump still held) | saber, single-saber styles, `velocity[2] > 20`, ground distance < 70, FP ≥ 10, not in a secondary style, cartwheels allowed by saber and by `pers.noCartwheel` | xy set to ±190 sideways; z = 300 (right) / 350 (left); move LS_JUMPATTACK_ARIAL_RIGHT/LEFT (the CART variant is dead code behind `if (1)`). Costs 10 FP. | — | `bg_saber.c:2560-2608`, `2623-2672`, `2309-2311`, `2523-2558` | V |
| Butterfly (staff) | same inputs with SS_STAFF | as above | LS_BUTTERFLY_RIGHT (z 350) / LEFT (z 250); 10 FP | — | `bg_saber.c:2586-2590`, `2649-2653` | V |
| Staff kicks | BUTTON_ALT_ATTACK with SS_STAFF, saber on | `saberMove == LS_READY`, not ducked, `upmove ≥ 0`, not already kicking/rolling | `rightmove` → LS_KICK_R/L; `forwardmove` → LS_KICK_F/B; no direction → nothing unless `g_flipKick` (then front kick). In air with ground distance > 64: air variants. Movement is frozen during the kick. Hit: `G_KickTrace` — damage ×0.2 when `d_saberKickTweak` (default 1) applies, knock-back, and knockdown 700 ms only if the target is not already down and is **not** an idle grounded saber user (`G_KickDownable`). | — | `bg_saber.c:3979-4047`, `2941-3056`, `3121-3146`; `w_saber.c:7980-8143`; `bg_pmove.c:14299-14308` | V (kick damage values per move not audited → U) |
| Melee kicks / katas | — | — | Saber/melee attack moves; out of scope here (saber audit). `g_debugMelee 0` by default. | | | U |
| Flip-kick | wall-flip / forward-flip inputs against a player | `g_flipKick ≥ 1` (default **0**) | Forward flipkick branch is entirely inside `GetFlipkick() >= 1`; side wall-flip traces only hit players when flipkick is on (trace mask). Server damage/knockdown in `g_active.c:5613-5799`. **Disabled by default.** | `STAT_DASHTIME 200` on victim | `bg_pmove.c:4243-4311`, `3978-3983`, `248-277` | V |
| Knockdown get-ups | after the knockdown timer: direction key → roll getup; jump → force getup (500 ms); nothing → up to 4 s on the floor | see §2.1 | see §2.1 | — | `w_force.c:5570-5625`, `5723-5775` | V |
| Dash / dodge (jaPRO) | BUTTON_DASH (+BUTTON_WALKING and WASD for dodge) | **MV_WSW or MV_TRIBES only**; on ground, `weaponTime ≤ 0`, `STAT_DASHTIME == 0` | dash: forward 250×1.9/1.28 ≈ 371 u/s (or current speed), z 280; dodge: speed×1.25 in key direction, z 180 | 800 ms (WSW) / 1050 ms (Tribes) | `bg_pmove.c:5437-5500`, `5258-5308`, `14879-14882` | V — **not available in default MV_JKA** |
| jaPRO wall-jump (wsw) | BUTTON_DASH in air next to a wall | **MV_WSW only** | z ≥ 370, speed ≥ 200 | 1600 ms | `bg_pmove.c:5549-5646` | V — not available in MV_JKA |
| Grapple hook | BUTTON_GRAPPLE | `g_allowGrapple` (default 0) | — | `g_hookFloodProtect` 600 ms | `g_active.c:5088-5119` | V — disabled by default |
| Speed modifiers | — | — | Force speed ×1.7; rage ×1.3; rage recovery ×0.75; gripping ×0.4; being gripped ×0.2; disruptor zoom ×0.5; saber attack while moving ×0.85 (medium/dual/staff) / ×0.55 (strong); spinning saber anim ×0.5 (×0.3 strong); attacking while backpedalling ×0.75 / ×0.60 / ×0.45; saber `moveSpeedScale` | — | `bg_pmove.c:12110-12222`, `12385-12398` | V |
| Movement locks | — | — | Zero move input during: kicks, grapple moves, last 800 ms of stab-down, pull attacks, meditate, force-land anims (`stiffenedUp`); lunge forces forward; knockdown/dodge set speed 0. | — | `bg_pmove.c:14299-14445`, `14533-14538` | V |

### 3.2 Movement styles (enum `bg_public.h:565-591`)

| Value | Style | Notes for default servers | S |
|---|---|---|---|
| 0 | MV_SIEGE | base | V |
| **1** | **MV_JKA** | **default (`g_xcvar.h:242`)** | V |
| 2 | MV_QW | QW air accel 0.7, ramp/force-jump scaling | V |
| 3 | MV_CPM | no force jump, no rolls, no wall moves, jump vel 270 | V |
| 4 | MV_Q3 | as CPM without air control | V |
| 5 | MV_PJK | | V |
| 6 | MV_WSW | dash, dodge, walljump; jump vel 280 | V |
| 7-11 | MV_RJQ3, MV_RJCPM, MV_SWOOP, MV_JETPACK, MV_SPEED | race styles; fall back to MV_SIEGE/MV_JKA when used as `g_movementStyle` (`bg_pmove.c:447-452`) | V |
| 12 | MV_SP | SP physics (accel 12, air accel 4) | V |
| 13-18 | MV_SLICK, MV_BOTCPM, MV_COOP_JKA, MV_OCPM, MV_TRIBES, MV_SURF | | V |

---

## 4. Numbers for navigation

| Quantity | Value | Source | S |
|---|---|---|---|
| Run speed | 250 u/s (`g_speed`) | `g_xcvar.h:156`; `g_active.c:4299` | V |
| Backpedal / crouch / walk | 187.5 / 125 / ≈126 u/s | §3.1 | V / V / D |
| Force speed | 425 u/s (250 × 1.7) | `bg_pmove.c:12137-12140` | D |
| Gravity | 800 (`g_gravity`, `DEFAULT_GRAVITY`); racers use 750 | `g_xcvar.h:109`; `bg_public.h:57`; `g_active.c:4374-4382` | V |
| Jump velocity | 225 (`JUMP_VELOCITY`) | `bg_public.h:62` | V |
| Normal jump apex | 225² / (2×800) = **31.6 u** (table comment says 32) | derived; `bg_pmove.c:230` | D |
| Normal jump air time / flat distance at 250 u/s | 0.5625 s / **≈141 u** (no strafe gain, level landing) | derived | D |
| Force jump hold height (`forceJumpHeight`) | L0 32, **L1 96, L2 192, L3 384** (+2 unused entries of 1570) | `bg_pmove.c:228-236` | V |
| Force jump apex incl. coast | hold height + 31.6 ≈ **128 / 224 / 416 u** | derived (cap 225 then ballistic) | D |
| "Reach" heights in code (`forceJumpHeightMax`: +18 step +24 crouch) | 66 / 130 / 226 / 418 | `bg_pmove.c:2222-2228` | V |
| Force jump strength table | 225 / 420 / 590 / 840 (/840 / 960 unused levels) | `bg_pmove.c:238-246` | V |
| Force jump flat distance at 250 u/s | ≈ 310 / 445 / 685 u for L1 / L2 / L3 (ascent at ~245-270 u/s, coast, free fall) | derived estimate | D (rough) |
| Player hull | x/y ±15; z −24 … +40 standing, +16 crouched | `bg_pmove.c:7376-7380`; `bg_public.h:74-76` | V |
| View height | 36 standing (`40 − 4`), 12 crouched (the "//26" comment in the header is stale) | `bg_public.h:77-81` | V |
| Step height | 18 (`STEPSIZE`) | `bg_public.h:51` | V |
| Max walkable slope | `MIN_WALK_NORMAL 0.7` → steeper than ≈45.6° is not ground | `bg_local.h:28`; `bg_pmove.c:6896` | V |
| Wall-run surface | `0 ≤ normal.z ≤ 0.4`; wall grab `|normal.z| ≤ 0.2` | `bg_pmove.c:4045`, `4462` | V |
| Fall delta | `delta = (landing z-speed)² × 0.0001`; ×2 if ducked; ×0.25 / ×0.5 in waist / ankle water; none fully submerged | `bg_pmove.c:6441-6474`, `6591-6602` | V |
| Fall damage threshold | event sent if delta > 7; damage only if delta > 44 → landing speed > 663 u/s → **free-fall drop > 275 u** (ducked without roll: > 137.5 u; ducked with roll: > 412 u) | `bg_pmove.c:6642-6700`; `g_active.c:1944-1950` | V + D |
| Fall damage amount | `delta × 0.16` (no armor); Siege: `delta × 1` above 60; capped by `g_maxFallDmg` (default 0 = no cap); disabled by `dmflags & 8` | `g_active.c:1952-1971`; `bg_public.h:1377` | V |
| Force-jump landing | landing at or above jump start height: delta capped at 8 (no damage). Landing lower: delta reduced by `0.3 × (forceJumpHeight[level] − drop)`. | `bg_pmove.c:6651-6682` | V |
| Roll trace length | 64 u ahead, crouch hull raised by 18 | `bg_pmove.c:6338-6377` | V |

---

## 5. Taunts and character actions

### 5.1 Base taunts (GENCMD / button)

| Action | How a player issues it | Restrictions | Cooldown | Bot route | Cite | S |
|---|---|---|---|---|---|---|
| Gesture taunt | BUTTON_GESTURE (`+button3`) | `torsoTimer < 1`, hand-extend NONE, `legsTimer < 1`, `weaponTime < 1`, not in saber lock | hand-extend TAUNT 1000 ms | **`trap->EA_Gesture`** already maps to BUTTON_GESTURE (`ai_main.c:778`) | `bg_pmove.c:11363-11384` | V |
| Taunt | `taunt` → GENCMD_TAUNT (27) | same idle conditions (`torsoTimer`, `legsTimer`, `weaponTime < 1`, hand-extend NONE, no saber lock). Anim by weapon/style; fast/Tavion styles holster the saber, dual/staff ignite. Hand-extend TAUNT for the anim length only if on ground; EV_TAUNT sound always. | 1000 ms (taunt timer shared with flourish/gloat) | set `lastucmd.generic_cmd = 27` | `g_active.c:3073-3165`, `3319-3332`, `5491-5496` | V |
| Bow | `bow` → GENCMD_BOW (28) | same idle conditions; holsters saber | 1000 ms (emote timer shared with meditate) | `generic_cmd = 28` | `g_active.c:3166-3186`, `5497-5502` | V |
| Meditate | `meditate` → GENCMD_MEDITATE (29) | same; holsters saber; movement input zeroed while in BOTH_MEDITATE; any attack/alt/force button or `upmove` ends it (BOTH_MEDITATE_END) | 1000 ms (emote timer) | `generic_cmd = 29` | `g_active.c:3187-3213`, `5503-5508`; `bg_pmove.c:14349-14403` | V |
| Flourish | `flourish` → GENCMD_FLOURISH (30) | saber only (no anim otherwise); ignites saber | 1000 ms (taunt timer) | `generic_cmd = 30` | `g_active.c:3214-3260`, `5509-5514` | V |
| Gloat | `gloat` → GENCMD_GLOAT (31) | saber only | 1000 ms (taunt timer) | `generic_cmd = 31` | `g_active.c:3261-3318`, `5515-5520` | V |
| Base-duel restriction | — | Only if `g_emotesDisable` has bit `E_BASEDUEL` (enum index 21): taunts refused while moving, and bow/meditate/flourish/gloat refused outside GT_DUEL/POWERDUEL. Default 0 → **all five work in FFA**, unlike base JKA. | — | — | `g_active.c:3077-3091`; `g_local.h:406-427` | V |
| Full-body taunt cancel | pressing attack, alt-attack, any force button or jump | — | — | — | `bg_pmove.c:14349-14367`; `w_force.c:992-999` | V |

### 5.2 Saber / duel actions

| Action | Issue | Restrictions | Bot route | Cite | S |
|---|---|---|---|---|---|
| Saber on/off | `sv_saberswitch` → GENCMD 1 | saber weapon, hand-extend NONE, `weaponTime < 1`, not in saber lock / duel countdown; not while gripped and holstered; turning off sets `weaponTime 400`; if saber in flight it is dropped instead | `generic_cmd = 1` | `g_cmds.c:3820-3897` | V |
| Saber style cycle | `saberAttackCycle` → GENCMD 26 | alive, saber weapon (rest of function not audited) | `generic_cmd = 26` | `g_cmds.c:3902-3929`; `g_active.c:5478-5490` | V/U |
| Private duel (saber only) | `engage_duel` → GENCMD 2 | `g_privateDuel 1`; not GT_DUEL/POWERDUEL/team games; holding saber; no jetpack item; saber not in flight; not knocked down; not already dueling; target = client within 256 u along view, alive, holding saber, not dueling. Accepting = same command at the challenger within 2000 ms. On start: both sabers holstered, `weaponTime 400`, FP refilled, rage/protect/speed/trick/absorb/sight stopped. | `generic_cmd = 2` | `g_cmds.c:4245-4482`, `4526-4534`; `g_active.c:5252-5271` | V |
| Full-force duel | client command `engage_fullforceduel` | same as above with dueltype 1 (force powers allowed) | `trap->EA_Command(client,"engage_fullforceduel")` | `g_cmds.c:4162-4165`, `8987` | V |
| Gun duel | client command `engage_gunduel [weapon]` | `g_allowGunDuel 1` | `EA_Command` | `g_cmds.c:4167-4242`, `8988` | V |

### 5.3 jaPRO emotes (server client commands, available to ordinary players)

All go through `DoEmote` (`g_cmds.c:6313-6356`). Common restrictions (V): `weaponTime ≤ 1`, `saberMove ≤ 1`, **no force power active**, on ground, not in a private duel, not knocked down, not rolling, not race mode, **gametype must be GT_FFA**. Table flags `CMD_NOINTERMISSION|CMD_ALIVE` (`g_cmds.c:8890-8942`). **No cooldown.** Each can be disabled by its bit in `g_emotesDisable` (default 0). "Freeze" emotes hold the pose until movement, attack/alt-attack, BUTTON_DASH or being gripped (`g_active.c:4013-4022`); issuing the same command again toggles it off. "Holster" emotes switch the saber off. Bots can issue every one with `trap->EA_Command(client, "<cmd>")`.

| Command | Anim | Freeze | Holster | Disable bit | Cite (`g_cmds.c`) | S |
|---|---|---|---|---|---|---|
| `amsit` | BOTH_SIT1 | yes | yes | E_SIT | 6358-6365 | V |
| `amsit2` | BOTH_SIT3 | yes | yes | E_SIT | 6367-6374 | V |
| `amsit3` | BOTH_SIT6 | yes | yes | E_SIT | 6376-6383 | V |
| `amsit4` | BOTH_SIT2 | yes | yes | E_SIT | 6385-6392 | V |
| `amsit5` | BOTH_SLEEP6STOP | yes | yes | E_SIT | 6548-6555 | V |
| `amsurrender` | TORSO_SURRENDER_START | yes | yes | E_SURRENDER | 6394-6401 | V |
| `amcheer` | BOTH_TUSKENTAUNT1 | no | yes | E_CHEER | 6403-6410 | V |
| `amtaunt` | BOTH_ALORA_TAUNT | no | no | E_TAUNT | 6412-6419 | V |
| `amtaunt2` | BOTH_SCEPTER_HOLD | no | no | E_TAUNT | 6539-6546 | V |
| `amvictory` | BOTH_TAVION_SCEPTERGROUND | no | no | E_VICTORY | 6421-6428 | V |
| `amrage` | BOTH_FORCE_RAGE | no | no | E_RAGE | 6430-6437 | V |
| `amsmack` | BOTH_TOSS1 | no | no | E_SMACK | 6439-6446 | V |
| `amcower` | BOTH_COWER1 | no | yes | E_COWER | 6448-6455 | V |
| `amnoisy` | BOTH_SONICPAIN_HOLD | no | yes | E_NOISY | 6458-6465 | V |
| `amhug` | BOTH_HUGGER1 | no | yes | E_HUG | 6467-6474 | V |
| `ambeg` | BOTH_KNEES1 | yes | yes | E_BEG | 6476-6483 | V |
| `ambeg2` | BOTH_KNEES2 | yes | yes | E_BEG2 | 6485-6492 | V |
| `ambernie` | BOTH_FORCE_DRAIN_GRABBED | yes | no | E_BERNIE | 6494-6501 | V |
| `ambreakdance` … `ambreakdance4` | BOTH_FORCE_GETUP_B2 / B4 / B5 / B6 | no | yes | E_BREAKDANCE | 6503-6537 | V |
| `amsleep` | BOTH_SLEEP1 | yes | yes | E_SLEEP | 6557-6564 | V |
| `amdance` | BOTH_STEADYSELF1 | no | yes | E_DANCE | 6566-6573 | V |
| `ampoint` | BOTH_STAND5TOAIM | yes | no | E_POINT | 6575-6582 | V |
| `amsignal` … `amsignal4` | TORSO_HANDSIGNAL1-4 | no | no | E_SIGNAL | 6599-6629 | V |
| `amflip` | style-dependent saber flourish (BOTH_STAND1TO2 / STAND2TO1 / S1_S7 / SHOWOFF_STAFF / SHOWOFF_FAST) | no | no | E_SABERFLIP | 6631-6658 | V (branch conditions not read line by line → U) |
| `amslap` | BOTH_FORCEGRIP3THROW | no | no | E_SLAP | 6660-6667 | V |
| `amrun` | jawa-run toggle (returns early for jaPRO clients) | — | — | E_JAWARUN | 6669-6703 | U |
| `amkiss` | — | — | — | — | **not present** in this codebase (no match in `game/`) | V |
| `amsheev` | — | — | — | — | function exists (6585) but its table entry is commented out (`g_cmds.c:8936`) → unreachable | V |

### 5.4 Other player commands that affect movement (all restricted)

| Command | Restriction | Cite | S |
|---|---|---|---|
| `jump <1-3>` | race mode only | `g_cmds.c:6856-6902` | V |
| `move <style>` | `g_raceMode` only | `g_cmds.c:6705-6730` | V |
| `crouchjump` | race + practice mode only | `g_cmds.c:7097-7125` | V |
| `haste`, `hide`, `launch`, `warp`, `blink`, `ysal`, `practice`, `rocketchange`, `jetpack`, `throwflag`, `thrownade`, `spot` | exist in the table (`g_cmds.c:8946-9102`); bodies not audited for this report | — | U |
| `kill` | CMD_ALIVE | `g_cmds.c:9009` | V |

---

## 6. Disabled, unreachable or changed versus base JKA

| Item | Status in this fork | Cite | S |
|---|---|---|---|
| Lightning saber block | **Fork addition** ("Niksata Edit"), off by default (`g_lightningBlockEnabled 0`). | `w_force.c:1875-1879`, `1916`; `w_saber.c:10086-10150`; `g_xcvar.h:222-224` | V |
| Bow / meditate / flourish / gloat in FFA | Allowed by default (base JKA limits them to Duel); base behaviour only with `g_emotesDisable` bit E_BASEDUEL. | `g_active.c:3077-3091` | V |
| Taunt debounce | Per-category 1000 ms server debounce on GENCMD taunts/emotes; 300 ms on most force GENCMDs; none on push/pull. | `g_active.c:5247-5520` | V |
| Bots and push | Bots may re-trigger push through BUTTON_FORCEPOWER without releasing the button. | `w_force.c:5097` | V |
| Push/pull selection lag compensation | Optional (`g_unlagged` bit), default 0. | `w_force.c:3513-3514`, `3586-3587` | V |
| Push/pull on knocked-down targets | Base rule kept (immune); switchable with FT_PUSHPULLKD. | `w_force.c:629-633` | V |
| Teammate push/pull | Allowed when friendly fire is on (jaPRO change). | `w_force.c:3607-3610` | V |
| Private duels | NF duel (type 0), full-force duel (type 1) and gun duels (type ≥ 2); duelists are isolated from outside force powers. | `w_force.c:583-604`; `bg_misc.c:1912-1962` | V |
| Pull attack (SP stab/swing after pull) | Compiled out on the server (`#if 0`); only a cgame JA+ compatibility path remains. | `bg_saber.c:2316-2446` | V |
| Charged force jump | Unreachable (see §3.1). `ForceJumpCharge` comment: "I guess this is unused now". | `w_force.c:2527-2528`, `5651-5652` | V |
| Duel "cheaper jump" | The 1-vs-5 drain argument has no effect (levitation drain ignores the amount). | `bg_pmove.c:3432-3440`; `bg_saber.c:77-121` | V |
| `forceSpeedLevels[]` | Defined, not used; speed is a flat ×1.7. | `bg_pmove.c:132-138`, `12137-12140` | V |
| `g_lightningBlockReduction` | Registered, not read by the block function. | `g_xcvar.h:224`; `w_saber.c:10086-10150` | V |
| Flipkick | Present (jaPRO/JA+ style) but off (`g_flipKick 0`). | `g_xcvar.h:238`; `bg_pmove.c:4267` | V |
| Dash / dodge / wsw wall-jump / double jump / ramp jump / overbounce | Only in non-default movement styles. | `bg_pmove.c:5449-5451`, `5576-5577`, `4535-4568`, `6732-6735` | V |
| Grapple hook, target laser | Off by default (`g_allowGrapple 0`, `g_allowTargetLaser 0`). | `g_xcvar.h:252`, `320` | V |
| Roll variants | `g_fixRoll 0` = base roll speeds; 1-3 change the speed threshold (≥ 173 u/s, or none) and speed curve. Private FF duels force type 3, NF duels type 0. | `bg_pmove.c:279-323`, `8349-8353`, `12233-12383` | V |
| `g_tweakJump`, `g_dodge`, `amkiss` | Do not exist here. | grep over `game/` | V |
| Tribes mode (`g_tweakWeapons` bit 27 / MV_TRIBES) | Repurposes Protect, Absorb ("overdrive"), Push, lightning button (thrust/blink) and alt-attack; ignore unless that mode is enabled. | `w_force.c:670-678`, `1678-1683`, `1728-1734`, `4947-4985`, `5069-5092`; `bg_pmove.c:14884-14898` | V |
| Race mode | Force powers unusable outside duels, FP regen 25 ms, no fall damage, no emotes; gravity 750. | `w_force.c:716-717`, `6135-6137`; `g_active.c:1923-1924`, `4382`; `g_cmds.c:6329-6332` | V |
| `sv_fps` default | 40 (base 20). Lightning/drain ticks are decoupled from it by a fixed 50 ms debounce loop. | `g_xcvar.h:177`; `w_force.c:4706`, `4866-4870`, `4895-4900` | V |

---

## 7. Not covered / open points

| Topic | Why |
|---|---|
| Saber attack moves, katas, DFA, lunges, kick damage per move | belongs to the saber audit; only the acrobatic triggers were read |
| Exact animation lengths (knockdown, getup, roll, taunt) | stored in animation data (`BG_AnimLength`), not in code |
| Thrown-saber damage application | only the constants and return rules were read |
| Which weapons call `Jedi_DodgeEvasion` | callers located (`g_weapon.c:834`, `1147`, `4825`) but not read |
| Force-jump horizontal distances | derived from formulas, not measured |
| Frame ordering claim in §0.4 (forcesel reset for bots) | read from call sites only |
