# MECHANICS_SABER — lightsaber mechanics inventory (TaystJK_AI-Improved-Bots)

Read-only source audit. All paths are relative to `TaystJK_AI-Improved-Bots/codemp/game/`.
Nothing was built or run; every statement is from reading the cited lines.

Status column: **V** = verified by reading the cited code. **U** = uncertain (reason given).

Important scope note: the game module is compiled with `_GAME`. Many JA+ additions in the shared `bg_*.c` files are
inside `#ifdef _CGAME` and therefore **do not exist on the server** (they are client prediction for foreign JA+ servers).
Bots run inside the server, so those moves are listed as not reachable (section 5).

Input vocabulary used below (usercmd_t): `fwd` = forwardmove > 0, `back` = forwardmove < 0, `right` = rightmove > 0,
`left` = rightmove < 0, `jump` = upmove > 0, `crouch` = upmove < 0 (state flag `PMF_DUCKED`), `ATK` = BUTTON_ATTACK,
`ALT` = BUTTON_ALT_ATTACK. "FP n" = force points drained with `BG_ForcePowerDrain(ps, FP_GRIP, n)` (the FP_GRIP
argument is only a label; the override amount is what is subtracted, bg_saber.c:55-131).

Force point costs (bg_saber.c:2309-2311): `SABER_ALT_ATTACK_POWER` = 50 (katas), `SABER_ALT_ATTACK_POWER_LR` = 10
(cartwheel / side butterfly), `SABER_ALT_ATTACK_POWER_FB` = 25 (everything else). Not enough force = `EV_NOAMMO` and the
branch fails (bg_saber.c:133-142).

---

## 1. Saber styles

Enum `saber_styles_t` bg_public.h:1719-1727. Current style is `ps.fd.saberAnimLevel`; `ps.fd.saberAnimLevelBase` is the
"owned" style (dual/staff users in a single-blade stance have Base != Level, which disables specials:
`PM_InSecondaryStyle` bg_saber.c:2450-2461).

| Style | Enum | Who can use it (as coded) | Attack power / damage as coded | Chain limit (PM_SaberKataDone, bg_saber.c:767-864) | Style-only specials | Status |
|---|---|---|---|---|---|---|
| SS_FAST (blue) | 1 | Single saber. Also forced for a dual user with one saber holstered (g_active.c:3638-3643) | Attack power base 1 (w_saber.c:157-174). SP damage level 1 (anims A1, w_saber.c:3051-3063). MP-style damage 10 (w_saber.c:4639-4644). Transition anims x1.5 speed (bg_panimate.c:2903-2906). No run slowdown while attacking forward; x0.75 backwards (bg_pmove.c:12165-12171) | Diagonal/side swings: tolerance 5, then random stop; T2B not limited by this rule (bg_saber.c:835-857) | Lunge `LS_A_LUNGE`, backstab `LS_A_BACKSTAB`, kata `LS_A1_SPECIAL` | V |
| SS_MEDIUM (yellow) | 2 | Single saber | Power base 2. SP level 2 (w_saber.c:3064-3067). MP 40, T2B 30 (w_saber.c:4598-4611). Run x0.85 attacking, x0.60 backwards (bg_pmove.c:12172-12203) | Stops when chain count > irand(2,5); diagonal tolerance 3 (bg_saber.c:842-861) | Flip-over attack `LS_A_FLIP_SLASH` ("yellow DFA"), kata `LS_A2_SPECIAL` | V |
| SS_STRONG (red) | 3 | Single saber | Power base 3. SP level 3 (w_saber.c:3068-3071). MP ramp 30..85, T2B 30..70 (w_saber.c:4529-4560). Transitions x0.75 (bg_panimate.c:2907-2910). Run x0.55 attacking (x0.70 with ST_NO_REDCHAIN), x0.45 backwards, transitions x0.6/x0.4 (bg_pmove.c:12177-12222) | Stops when count > irand(2,3); a following swing must continue momentum (chain angle 135..215), 180 allows 2, else 3 (bg_saber.c:792-831). With ST_NO_REDCHAIN: 1 swing only (bg_saber.c:794-797) | Jump attack `LS_A_JUMP_T__B_` ("red DFA"), kata `LS_A3_SPECIAL` | V |
| SS_DESANN | 4 | Single saber; reachable by cycling in this fork (g_cmds.c:4090-4105); forced by `g_saberDisable` bit 5 or Tribes class 3 (g_active.c:3511-3533) | Power base **4** (raw enum value used, w_saber.c:157). SP level 4 (w_saber.c:3072-3075). MP-style: falls to default 35 (w_saber.c:4455, 4646-4651) | Unlimited (bg_saber.c:777-780) | Kata `LS_A3_SPECIAL` (bg_saber.c:3876-3879). Back attack = `LS_A_BACK` | V |
| SS_TAVION | 5 | Single saber; reachable by cycling in this fork; forced by `g_saberDisable` bit 6 / Tribes (g_active.c:3521-3536) | Power base **5** (w_saber.c:157). SP level 2 (w_saber.c:3076-3079). MP-style default 35 | Unlimited (bg_saber.c:777-780) | Kata `LS_A1_SPECIAL_YODA` (fork addition, bg_saber.c:3870-3872) | V |
| SS_DUAL | 6 | Only with two sabers equipped and both on; forced automatically (g_active.c:3636-3651) | Power base treated as 2 (w_saber.c:160-163). SP level 2 (w_saber.c:3080-3083). MP 30 (w_saber.c:4518-4519). Run x0.85 / x0.60 | Unlimited (bg_saber.c:787-791) | `LS_JUMPATTACK_DUAL`, `LS_SPINATTACK_DUAL`, `LS_DUAL_FB`, `LS_DUAL_LR`, kata `LS_DUAL_SPIN_PROTECT`, `LS_STABDOWN_DUAL` | V |
| SS_STAFF | 7 | Saber with >1 blade / `stylesLearned == 1<<SS_STAFF`, both blades on (g_active.c:3653-3672) | Power base treated as 2 (w_saber.c:164-167). SP level 2 (w_saber.c:3084-3087). MP 30 (w_saber.c:4494-4495) | Unlimited (bg_saber.c:782-786) | Kicks `LS_KICK_*`, `LS_JUMPATTACK_STAFF_RIGHT`, `LS_BUTTERFLY_LEFT/RIGHT`, `LS_A_BACKFLIP_ATK`, `LS_SPINATTACK`, kata `LS_STAFF_SOULCAL`, `LS_STABDOWN_STAFF`. **No saber throw** (ALT = kick, bg_saber.c:3511-3533) | V |

Attack animation choice per style: `anim += (saberAnimLevel-1) * SABER_ANIM_GROUP_SIZE` (bg_saber.c:4348-4390), so real swing
durations come from the animation config, not from C code. Lockout after any swing is `weaponTime = torsoTimer`
(bg_saber.c:4259). Rage doubles server-side saber anim speed (w_saber.c:9056-9059). Status: V.

Attack "power" used for clash resolution = `G_SaberAttackPower` (w_saber.c:152-249): base (above) x2 + 1 when attacking,
plus +1 per `toleranceAmt` units of blade travel (strong 8, medium 16, fast 24, others 16), capped 16; x0.3 with a broken arm.

### How a player switches style

| Item | Rule | Citation | Status |
|---|---|---|---|
| Input | `usercmd.generic_cmd = GENCMD_SABERATTACKCYCLE` -> `Cmd_SaberAttackCycle_f` | g_active.c:5478-5490 | V |
| Debounce | 300 ms; 100 ms for single-saber users when `g_tweakSaber & ST_FASTCYCLE` | g_active.c:5480-5487 | V |
| Single saber | Cycles FAST -> MEDIUM -> STRONG -> DESANN -> TAVION -> FAST (DUAL/STAFF skipped). **No FP_SABER_OFFENSE level check in this function** | g_cmds.c:4090-4105 | V |
| Validation | Only per-saber `stylesForbidden` is honoured | g_cmds.c:4124-4128, bg_saberLoad.c:263-341 | V |
| Busy | If `weaponTime > 0` the new style is queued (`saberCycleQueue`) and applied when `weaponTime <= 0` | g_cmds.c:4130-4137, w_saber.c:8716-8724 | V |
| Dual sabers | The command toggles the second saber (holstered 0 <-> 1); with one saber off the style becomes SS_FAST (g_active overrides the SS_STRONG written by the command) | g_cmds.c:3938-3975, g_active.c:3638-3643 | V (override order inferred: U) |
| Staff | The command toggles the second blade; with one blade the style becomes the saber's `singleBladeStyle` | g_cmds.c:3976-4039, g_active.c:3659-3671 | V |
| Server restrictions | `g_saberDisable` bits: 1 no blue, 2 no yellow, 4 no red, 8 no dual, 16 no staff, 32 force Desann, 64 force Tavion | g_local.h:297-303, g_active.c:3508-3593 | V |
| Siege | Class `saberStance` bitmask replaces the cycle | g_cmds.c:4050-4077 | V |
| Saber on/off | `generic_cmd = GENCMD_SABERSWITCH` (300 ms debounce) -> `Cmd_ToggleSaber_f`; refused in flight (knocks saber down instead), during `forceHandExtend`, duel start, saber lock, or `weaponTime >= 1`; holstering sets `weaponTime = 400` | g_active.c:5246-5251, g_cmds.c:3820-3897 | V |
| Auto ignite | Pressing ATK or ALT with sabers off and `weaponTime < 1` ignites | bg_saber.c:3434-3449 | V |

---

## 2. Attacks and special moves a player can trigger

Entry point: `PM_WeaponLightsaber` (bg_saber.c:3300-4277), called every pmove while `ps.weapon == WP_SABER`
(bg_pmove.c:10397-10402). Global gates before any attack is chosen:

| Gate | Effect | Citation | Status |
|---|---|---|---|
| In knockdown or roll | No attacks (only roll stab) | bg_saber.c:3313-3345 | V |
| `saberLockTime > serverTime` | Only lock logic runs | bg_saber.c:3347-3352 | V |
| Kicking anim with `legsTimer > 0` | No interruptions | bg_saber.c:3396-3406 | V |
| Super-break win/lose anim running | No interruptions | bg_saber.c:3408-3415 | V |
| Sabers off | Only ignite | bg_saber.c:3417-3458 | V |
| Saber knocked away (`!saberEntityNum && saberInFlight`) | ATK cleared (kept for dual), ALT cleared | bg_saber.c:3460-3494 | V |
| Own saber in flight | Torso forced to `BOTH_SABERPULL`, return (dual may still swing the other saber) | bg_saber.c:3570-3590 | V |
| Dead | return | bg_saber.c:3601-3603 | V |
| `saberBlocked != 0` | Block/parry/bounce reaction consumes the frame | bg_saber.c:3656-3808 | V |
| `weaponTime > 0` | No new move (kata check happens just before this, but kata itself needs LS_READY/start) | bg_saber.c:3903-3906 | V |
| ALT is cleared before normal attack selection | "never a valid regular saber attack button" | bg_saber.c:4048 | V |
| Jetpack racemode | Both buttons cleared | bg_saber.c:3308-3311 | V |

### 2a. Directional slashes (all styles)

Direction is chosen from movement keys in `PM_SaberAttackForMovement` (bg_saber.c:2463-2939). From `LS_READY` the move is
first played as its start `LS_S_*` (bg_saber.c:444-459), then the attack `LS_A_*` (bg_saber.c:4170-4173), then, if ATK is
released, its return `LS_R_*` (bg_saber.c:4084-4087). A started swing always completes (bg_saber.c:4080-4083).

| Move | Keys + ATK | Citation | Status |
|---|---|---|---|
| `LS_A_T2B` (overhead) | `fwd` only; also `back` only when no back-attack target; also no keys from ready | bg_saber.c:2836, 2881, 2905 | V |
| `LS_A_TL2BR` | `fwd` + `right` | bg_saber.c:2610-2613 | V |
| `LS_A_TR2BL` | `fwd` + `left` | bg_saber.c:2673-2676 | V |
| `LS_A_L2R` | `right` only | bg_saber.c:2618-2621 | V |
| `LS_A_R2L` | `left` only | bg_saber.c:2681-2684 | V |
| `LS_A_BL2TR` | `back` + `right` | bg_saber.c:2614-2617 | V |
| `LS_A_BR2TL` | `back` + `left` | bg_saber.c:2677-2680 | V |

Notes (V): the same quadrant table is used after a bounce (`PM_SaberMoveQuadrantForMovement`, bg_saber.c:667-714).
Force cost: none. Lockout: `weaponTime = torsoTimer` (bg_saber.c:4259). Quirk: in a secondary style (or CPM/Q3-type
movement styles, which set `noSpecials`, bg_saber.c:2526-2533) `fwd`-only + ATK selects no move and the code falls back
to `saberMoveData[curmove].chain_attack` (bg_saber.c:2825-2838, 4204-4209) — derived from the control flow, status U.

### 2b. Chains / combos

| Rule | Citation | Status |
|---|---|---|
| Hold ATK while a swing ends: next attack is picked from the keys held at that moment | bg_saber.c:4178-4180 | V |
| Same direction again: link through `transitionMove[endQuad][startQuad]`, unless the chain is "done", then return | bg_saber.c:489-500, 397-407 | V |
| Different direction whose start quadrant equals the current end quadrant: direct, no transition | bg_saber.c:501-504 | V |
| Otherwise: play the `LS_T1_*` transition, then its `chain_attack` | bg_saber.c:505-526, 4166-4169 | V |
| Chain "done" test per style (limits in section 1); when done the move becomes `chain_idle` (a return). Red DFA is exempt when `ST_REDDFAFIX` | bg_saber.c:4187-4193 | V |
| Chain counter: +1 for every attack move set, reset on `LS_READY` / flip attacks, capped at 16 | bg_saber.c:4288-4300 | V |
| From a parry/reflect: ATK goes straight into the attack matching the parry's end quadrant (riposte) | bg_saber.c:4133-4154 | V |
| After a bounce: repeat of the blocked direction is replaced by the bounce's `chain_attack` | bg_saber.c:4181-4185 | V |
| After a broken parry: always back to ready first (only when `PM_SaberInBrokenParry` is true; it is always false on the server with ST_NO_REDCHAIN) | bg_saber.c:4174-4177, 1545-1562 | V |
| Roll cancels are blocked during attack/start (start allowed with `ST_ALLOW_ROLLCANCEL`) | bg_pmove.c:6273-6297 | V |

### 2c. Special moves (server-reachable)

All rows need `weaponTime <= 0`, saber on, and the global gates above unless stated. "not special" =
`!BG_SaberInSpecialAttack(torsoAnim)`.

| # | Move | Style(s) | Exact trigger | Force / level | Lockout, cancels, notes | Citation | Status |
|---|---|---|---|---|---|---|---|
| 1 | `LS_A_LUNGE` | FAST | `fwd` (no strafe) + ATK, on ground, `PMF_DUCKED`, not special | FP 25 (free with `g_tweakForce & FT_NO_CROUCHATTACK_FP`) | Velocity set to 150 forward; movement forced forward while `legsTimer > 500`; view locked unless ST_JK2LUNGE. Damage window: none in first 150 ms and last 400 ms (SP style) | bg_saber.c:2787-2803, 2011-2021; bg_pmove.c:14447-14458, 14703; w_saber.c:3144-3158 | V |
| 2 | `LS_A_LUNGE` (air, "JK2 lunge") | FAST, DUAL | Same keys but ground not required; only when `g_tweakSaber & ST_JK2LUNGE`, not racemode | FP 25 (same exemption) | Reached only when row 1 failed (i.e. airborne) | bg_saber.c:2804-2824, 1931-1975 | V |
| 3 | `LS_SPINATTACK` | STAFF | Same as row 1 (crouch + `fwd` + ATK on ground) | FP 25 | Movement and view locked for the whole move | bg_saber.c:2022-2025; bg_pmove.c:13548-13555 | V |
| 4 | `LS_SPINATTACK_DUAL` | DUAL | Same as row 1 | FP 25 | Movement and view locked | bg_saber.c:2026-2029; bg_pmove.c:13548-13555 | V |
| 5 | `LS_A_FLIP_SLASH` (yellow DFA) | MEDIUM | `fwd` (no strafe) + ATK while `velocity[2] > 100` and ground distance < 32 (i.e. the first frames of a jump), not in a special jump anim, not special | FP 25 | Velocity = 150 forward (50 with ST_FIXYELLOWDFA), 400 up. Yaw auto-spins 240 deg/s for part of the anim unless ST_FIXYELLOWDFA; no steering. Resets chain count. Damage only between 600 ms after start and 1000 ms before end | bg_saber.c:2712-2730, 1689-1797; bg_pmove.c:14239-14268; w_saber.c:3176-3186 | V |
| 6 | `LS_A_FLIP_STAB` | MEDIUM | Same as row 5, but only chosen (50 %) when `ST_NO_REDCHAIN` (JK2SWINGS) is on | FP 25 | | bg_saber.c:1792-1795 | V |
| 7 | `LS_A_JUMP_T__B_` (red DFA) | STRONG | `fwd` (no strafe) + ATK while `velocity[2] > 100` and ground distance < 32, not special; requires `!(g_tweakSaber & ST_JK2RDFA)` (or racemode) | FP 25 (free with ST_REDDFANOFORCE) | Velocity = 300 forward, 280 up. No strafing/jump during it; view locked unless ST_SPINREDDFA. Must return via `LS_R_T2B`. Chain-done check can turn it into a return unless ST_REDDFAFIX. Damage only from 550 ms after start to 400 ms before end | bg_saber.c:2731-2758, 2114-2190, 4062-4065, 4189-4192; bg_pmove.c:14460-14467, 14699; w_saber.c:3159-3169 | V |
| 8 | `LS_A_JUMP_T__B_` (JK2-style red DFA) | STRONG | Only with `ST_JK2RDFA`, not racemode: already in an attack that started < 500 ms ago, `fwd` + ATK held, press `jump` (pmove path) / ground distance in (0,32) (saber path) | FP 25 | Two code paths | bg_pmove.c:4483-4520; bg_saber.c:2760-2785 | V |
| 9 | `LS_JUMPATTACK_DUAL` | DUAL (primary style) | `fwd` (no strafe) + ATK + `jump` (or `PMF_JUMP_HELD`), on ground or <= 40 above it, `velocity[2] >= 0`, not in attack/transition, `forceHandExtend == NONE`, rage recovery over | FP 25 | Jump is suppressed (`upmove = 0`); pmove drives forward movement and two hops; can turn only on the ground. Damage windows in w_saber.c:3198-3219 | bg_saber.c:2691-2711, 1869-1882, 2066-2069; bg_pmove.c:13372-13416 | V |
| 10 | `LS_JUMPATTACK_STAFF_RIGHT` (forward butterfly) | STAFF | Same as row 9 | FP 25 | Same pmove handling | bg_saber.c:2088-2090; bg_pmove.c:13417-13482 | V |
| 11 | `LS_A_BACKFLIP_ATK` | STAFF | `back` (no strafe) + ATK + `jump`/`PMF_JUMP_HELD`, same state tests as row 9, **FP_LEVITATION >= 2** | No FP drain | `velocity[2] = 500`; mid-anim hop back (100 back, 300 up) with a 50 ms server debounce shared with flip-kick. Disabled in movement style 6 | bg_saber.c:2842-2856, 1799-1839; bg_pmove.c:13493-13547 | V |
| 12 | `LS_JUMPATTACK_ARIAL_RIGHT` / `_LEFT` (cartwheel) | Any single style, DUAL (not STAFF, not secondary style) | `right` / `left` + ATK while `velocity[2] > 20`, ground distance < 70, `jump` or `PMF_JUMP_HELD` (i.e. strafe-jump then attack) | FP 10 | Sideways velocity 190, up 300 (right) / 350 (left). Blocked by saber flag `noCartwheels`, client setting `noCartwheel`, Tribes / CPM-type movement, `JAPRO_RESTRICT_BHOP` | bg_saber.c:2560-2609, 2623-2672, 2523-2552 | V |
| 13 | `LS_BUTTERFLY_RIGHT` / `_LEFT` | STAFF | Same keys as row 12 | FP 10 | Sideways 190, up 350 (right) / 250 (left); pmove forces strafe while `legsTimer > 450` | bg_saber.c:2586-2590, 2649-2653; bg_pmove.c:13431-13448 | V |
| 14 | `LS_STABDOWN` / `_STAFF` / `_DUAL` | Any (by style) | `fwd` (no strafe) + ATK, on ground, and a box trace 164 units along view yaw hits a player/NPC whose `legsAnim` is a knockdown/get-up anim (`BG_InKnockDown`) | FP 25 | Evaluated only after rows 1-10 fail. Movement forced forward until `legsTimer < 800`, then frozen with locked view. Damage applies only if the victim is `BG_InKnockDownOnGround` unless `g_fixGroundStab` != 0. Blocked by saber flag `noStabDown`. Side effect: the check zeroes `velocity[2]` and `upmove` for players | bg_saber.c:2825-2838, 601-665; bg_pmove.c:14323-14338; w_saber.c:4961-4964, 3264-3281 | V |
| 15 | `LS_A_BACKSTAB` | FAST, STAFF | `back` (no strafe) + ATK and `PM_CanBackstab()`, not special | none | Default test: box trace 128 units straight behind hits a player/NPC. `ST_EASYBACKSLASH`: any live player within 128 units and height diff in [-48, +32]. `ST_EASIERBACKSLASH`: always. View locked unless ST_SPINBACKSLASH. Damage window (SP style): none in first 400 ms and last 450 ms | bg_saber.c:2857-2878, 1593-1687; bg_pmove.c:14697-14698; w_saber.c:3094-3108 | V |
| 16 | `LS_A_BACK` (backslash) | MEDIUM, STRONG, DESANN, TAVION, DUAL (also all styles with Tribes weapons) | Same as row 15, standing | none | No damage in last 500 ms | bg_saber.c:2859-2872; w_saber.c:3109-3115 | V |
| 17 | `LS_A_BACK_CR` (crouch backslash, "DBS") | Same as row 16 | Same as row 15 with `PMF_DUCKED` or `crouch` | none | No damage in last 800 ms. Also triggered by ALT in Tribes movement style | bg_saber.c:2865-2868, 3498-3503; w_saber.c:3116-3122 | V |
| 18 | `LS_DUAL_FB` | DUAL | Result of a T2B / back attack when `PM_CheckEnemyPresence` finds someone within 100 units both in front and behind | none | Blocked by saber flag `noMirrorAttacks` or while in a special-attack anim | bg_saber.c:2926-2935, 2230-2253, 2255-2307 | V |
| 19 | `LS_DUAL_LR` | DUAL | Result of an L2R / R2L attack when someone is within 100 units both left and right | none | Same restrictions | bg_saber.c:2914-2925 | V |
| 20 | `LS_ROLL_STAB` | Any | During a forward roll (`legsAnim == BOTH_ROLL_F`) with `legsTimer <= 250`: ATK, saber not in flight | FP 25 | Auto-ignites a fully holstered saber. View locked. Damage only in first 400 ms. Blocked by saber flag `noRollStab` | bg_saber.c:3313-3345, 3175-3193; bg_pmove.c:14282-14286; w_saber.c:3547-3560 | V |
| 21 | Forward roll (prerequisite for row 20) | Any | Crouch while in a running anim with horizontal+vertical speed^2 >= 40000 (30000 with `g_fixRoll 1`; any speed with `g_fixRoll >= 2`) and `fwd`; needs FP_LEVITATION usable, not attacking | none | Refused during attack / special / spin (and during a swing start unless `ST_ALLOW_ROLLCANCEL`); 64-unit clearance trace | bg_pmove.c:8340-8353, 6249-6379 | V |
| 22 | `LS_A1_SPECIAL` (kata) | FAST | ATK + ALT together, on ground, no movement keys, `upmove <= 0`, saber not in flight, `saberMove` is `LS_READY` or a swing start, not already in a kata | FP 50 | Movement is scripted by `PM_MoveForKata`. Counts as special (unblockable). Blocked in secondary style or by saber `kataMove none` | bg_saber.c:3074-3119, 3824-3901; bg_pmove.c:14344-14349 | V |
| 23 | `LS_A2_SPECIAL` | MEDIUM | Same as row 22 | FP 50 | | bg_saber.c:3873-3875 | V |
| 24 | `LS_A3_SPECIAL` | STRONG, DESANN | Same as row 22 | FP 50 | | bg_saber.c:3876-3879 | V |
| 25 | `LS_A1_SPECIAL_YODA` | TAVION | Same as row 22 | FP 50 | Fork addition ("Niksata Edit") | bg_saber.c:3870-3872 | V |
| 26 | `LS_DUAL_SPIN_PROTECT` | DUAL | Same as row 22 | FP 50 | | bg_saber.c:3880-3882 | V |
| 27 | `LS_STAFF_SOULCAL` | STAFF | Same as row 22 | FP 50 | Can be cancelled into a roll while 250 < `legsTimer` < 700 | bg_saber.c:3883-3885; bg_panimate.c:1600-1609; bg_pmove.c:14004-14047 | V |
| 28 | `LS_KICK_F` / `_B` / `_R` / `_L` | STAFF (both blades on) | ALT with `fwd` / `back` / `right` / `left`; `saberMove == LS_READY`, not ducked, `upmove >= 0`, not rolling/kicking, on ground. With no direction key: forward kick only if `g_flipKick` != 0 | none | Also allowed to interrupt a swing **return** (`weaponTime > 0`, `saberBlocked == NONE`, ATK not held, a direction key held). No interruption until the kick anim ends, then instantly ready. Blocked by saber flag `noKicks` | bg_saber.c:3981-4045, 2941-3056, 3511-3533, 3121-3146, 3396-3406 | V |
| 29 | `LS_KICK_F_AIR` / `_B_AIR` / `_R_AIR` / `_L_AIR` | STAFF | Same keys while airborne with ground distance > 64 and > (-velocity[2]) - 64, and not mid-flip | none | If closer to the ground the kick is refused when > 128 up or rising | bg_saber.c:4000-4037 | V |
| 30 | Saber throw (no saberMove; sets `ps.saberInFlight`) | All except STAFF | ALT with `weaponTime < 1`, `ps.saberCanThrow`, FP_SABERTHROW level > 0, no ysalamiri, 80 units clear ahead | FP 20 at every level (bg_pmove.c:181, 202, 223) | Not in racemode. Returns when ALT is released (after 500 ms), after 6 s, or beyond 700 x level units; steerable at level >= 2; 500 ms re-throw delay. While out, the owner cannot swing (dual users keep the second saber) | bg_saber.c:3534-3566, 3156-3173; w_saber.c:9028-9053, 9207-9295, 7679-7716, 7621 | V |
| 31 | Saber lock push | Any | During a lock: each **new press** of ATK (released the frame before) | none | See 2d | g_active.c:5009-5072 | V |

Kick effect (V unless noted): damage `irand(10,15)`, multiplied by 0.2 when the kick tweak is active (`d_saberKickTweak`
default 1) (w_saber.c:8158, 8102-8109). Knockdown (`HANDEXTEND_KNOCKDOWN`, 700 ms) only if `G_KickDownable`: with the
tweak on, a target that holds a saber, is on the ground and has `weaponTime <= 0` is **not** knocked down — i.e. kicks
only floor enemies who are mid-swing, airborne, already busy, or not using a saber (w_saber.c:7980-8031). Per-kick
timing windows inside `G_KickSomeMofos` (w_saber.c:8151-8476) were not read line by line: U.

### 2d. Saber locks

| Topic | Rule | Citation | Status |
|---|---|---|---|
| Where allowed | Only between two players in a private duel with each other, or in GT_DUEL; never in GT_POWERDUEL; needs `g_saberLocking` | w_saber.c:1544-1588 | V |
| Preconditions | Both on ground, height diff <= 16, distance 8..80, neither crouched / rolling / in special jump / `forceHandExtend`, sabers in hand, each inside the other's front arc (dot > 0.4), no `SFL_NOT_LOCKABLE` | w_saber.c:1568-1660 | V |
| When rolled | On a blade clash with real damage: `irand(1,20) <= g_saberLockFactor` (default 2). In MP-damage mode also when a body auto-block happens. Then the two torso anims must match one of the listed attack/parry pairs, else 1-in-11 random | w_saber.c:5300-5316, 4996-5027, 1662-1955 | V |
| During lock | `saberLockTime = now + 10000`; view angles forced at the opponent; no movement or turning | w_saber.c:1482; g_active.c:4994-5007; bg_pmove.c:14232-14238 | V |
| How to win | Each fresh ATK press adds `saberLockHits`: FAST 1; MEDIUM/TAVION/DUAL/STAFF 2; STRONG/DESANN 3; while raging `1 + rage level`; minus 1 (50 %) in rage recovery; plus saber `lockBonus`; plus `irand(0, g_saberLockRandomNess)` (default 2). While hits > 0, `saberLockAdvance` is set each frame and the anim frame moves by `FP_SABER_OFFENSE level + 1`; reaching the end of the anim wins | g_active.c:5009-5072; bg_saber.c:1418-1498 | V |
| Result | Win -> `PM_SaberLockBreak(victory)`: super break if `strength + saberLockHits > irand(2,4)`; otherwise, if hits remain, the loser is knocked down (1100 ms) and pushed. No winner (range broken / timeout) -> both shoved apart | bg_saber.c:1199-1304, 1404-1409, 3353-3394 | V |
| Loser disarm | `saberCheckKnockdown_DuelLoss` (call site not traced in this audit) | w_saber.c:7180-7260 | U |
| `weaponTime` 1000-3000 set at lock start | Comment says "delay before pushing", but `PM_SaberLocked` zeroes `weaponTime` every frame, so the delay does not appear to gate pushes | w_saber.c:1485; bg_saber.c:1399-1402 | U |

### 2e. Wall moves / other

No saber move is selected by wall-run or wall-flip code: the only saber fields touched there are `saberMove = LS_NONE`
and clearing ATK (bg_pmove.c:4094-4109, 2811, 6374). Wall flips can register a "flip kick" on a touched player
(`ps.forceKickFlip`, bg_pmove.c:4068-4085; damage handling not audited here). Status: V for "no wall saber attacks",
U for flip-kick details.

---

## 3. Defence

### 3a. Which blocking model is active

`SaberSPStyle(self)` (w_saber.c:3920-3936) decides:

| Condition | Model |
|---|---|
| `g_tweakSaber & ST_JK2_DMGSYSTEM`, or attacker in racemode | MP model |
| `g_tweakSaber & ST_JAPLUS_DMG` | MP model |
| In a private duel: saber duel -> `g_saberDuelSPDamage` (default 1); force duel -> `g_forceDuelSPDamage` (default 0) | SP model if 1 |
| Otherwise `d_saberSPStyleDamage` (default 1) | SP model if 1 |

Defaults from g_xcvar.h:58, 199, 200. So with stock cvars the **SP model** is in force.

| Aspect | SP model (default) | MP model | Citation | Status |
|---|---|---|---|---|
| Body auto-block (`WP_SaberCanBlock`) against saber swings | **Not used** — the call is skipped | Used | w_saber.c:4982-4986 | V |
| What stops a swing | Only real blade-to-blade contact: the attacker's trace must hit the defender's saber entity box (`CONTENTS_LIGHTSABER`) and `WP_SabersIntersect` must confirm | Saber box hit confirmed by `G_SaberCollide`, or body auto-block | w_saber.c:5170-5213 | V |
| Damage formula | `2.5 x level` (level from the animation, table at w_saber.c:3039-3564), x2 outside duel/siege gametypes, x blade travel distance x (1 - trace fraction) x 0.033; x1.5 against clients | Fixed per style/move table (w_saber.c:4453-4654), special-move ramps (4707-4774) | w_saber.c:4283-4433, 5036-5042 | V |
| Idle / return blade touching a body | 1 damage only during a return (or always if the cvar is 2) | 10 x `g_saberDamageScale` during a return; else `g_saberTouchDmg` | w_saber.c:4657-4701 | V |

### 3b. Body auto-block rules (MP model only) — `WP_SaberCanBlock`, w_saber.c:9949-10051 (V)

Returns "no block" when any of these hold:

- defender's `saberMove` is an attack, or `SaberAttacking()` (9957-9961);
- defender is in a saber anim that is not ready/parry/reflect and has no `saberBlocked` (9963-9966);
- defender is in a broken parry (9968); saber knocked away, off, in flight, or weapon not saber, or still raising (9971-9984);
- **defender's own usercmd has BUTTON_ATTACK held** (9986);
- `saberMove != LS_READY` and `saberBlocking` is 0 (10013); `saberBlockTime >= now` (10016); `forceHandExtend != NONE` (10019);
- FP_SABER_DEFENSE level 0 (10035-10036).

Arc: `InFront(hitPoint, origin, viewangles, blockFactor)`; blockFactor = 0.9 / 0.6 / 0.3 for defence level 1 / 2 / 3
(0.05 at level 3 if `d_saberGhoul2Collision` is 0), minus 0.25 against a saber, minus another 0.25 against a thrown saber
(10022-10045). Smaller factor = wider arc, so level 3 vs a swing needs dot > 0.05 (almost the full front half).

Style gate: with `japp_saberTweaks 1`, chance = clamp(min, (1 - (theirLevel - ourLevel) / parity) x scale, max) with
levels FAST/STAFF/DUAL 1, MEDIUM/TAVION 2, STRONG/DESANN 3 (9930-9947, 9995-10007; defaults 0.0 / 0.75 / 0.5 / 3.0,
g_xcvar.h:208-212). Otherwise, with `ST_REDUCE_SABERBLOCK`, no block when the attacker's pierce level >= ours
(9892-9927, 10009-10011).

### 3c. Blade contact (both models)

| Topic | Rule | Citation | Status |
|---|---|---|---|
| Saber entity is solid | While owner holds an ignited saber, is alive and has FP_SABER_OFFENSE > 0 | w_saber.c:347-393 | V |
| Blade box removed | While the owner is in a broken parry or a super-break lose anim (swings pass straight through) — unless `g_saberAlwaysBlock` (1 = everyone, 2 = NPCs only) or the saber has `SFL2_ALWAYS_BLOCK` | w_saber.c:444-547 | V |
| Blade box size | Bounding box of all active blades, so where the blade is held matters; no facing test | w_saber.c:578-648 | V |
| Random pass-through | `g_reducesaberblock` percent chance to ignore a blade contact (MP model); `ST_REDUCE_SABERBLOCK` ignores it when attacker pierce level >= defender's | w_saber.c:5197-5198, 5215-5218 | V |
| No blocking across duels / racemode | | w_saber.c:5182-5187, 5234-5244 | V |
| Parry reaction | Defender gets `saberBlocked = BLOCKED_*` chosen from hit location (`WP_SaberBlockNonRandom`), pmove turns it into `LS_PARRY_*` | w_saber.c:5574-5584, 9723-9794; bg_saber.c:3748-3777 | V |
| Parry recovery time | `weaponTime = bg_parryDebounce[defence level] + 200` = 700 / 500 / 350 / 250 ms for level 0 / 1 / 2 / 3 | bg_saber.c:3148-3154, 3656-3662 | V |

### 3d. What breaks a block / who wins a clash (`blockStuff`, w_saber.c:5282-5709, V)

| Situation | Outcome | Lines |
|---|---|---|
| Attacker is in any special move (`BG_SaberInSpecial`) | Attack is "unblockable": skips auto-block; a blade contact crushes the parry into a broken parry (not with ST_NO_REDCHAIN) | 4707-4712, 5569-5572, 5681-5686 |
| Defender idle, attacker `attackStr + FP_SABER_OFFENSE > defender style (dual/staff = 2) + FP_SABER_DEFENSE` | Parry crushed -> broken parry (not with ST_NO_REDCHAIN) | 5574-5590 |
| Defender idle otherwise | Clean parry; attacker may be deflected/bounced (`WP_GetSaberDeflectionAngle`) | 5591-5594, 5697-5704, 2003-2273 |
| Attacker power < 3 (not strong-like), random 70 % (30 % if deflect failed), defender power > 2 or defence level 3 | Defender performs a knockaway; attacker thrown into a broken-parry/reflected anim, possible disarm check | 5368-5414 |
| Both attacking, attacker power > defender power (or equal and 20 %) | Defender forced into broken parry; disarm check | 5596-5616 |
| Both attacking, equal power | Both bounce (`BLOCKED_ATK_BOUNCE`) | 5619-5654 |
| Both attacking, defender stronger | Attacker forced into broken parry; disarm check | 5655-5678 |
| Defender attacking (non-special), generic case | `attackAdv = (attackStr + bonus + my offence) - (defendStr + his offence)`: > 1 defender knocked away, 1 defender bounces, < 1 attacker knocked away | 5474-5543 |
| Disarm (`saberCheckKnockdown_BrokenParry`) | Only if other's base power > mine: +2 or more -> 70 %, +1 -> 30 %; disabled by ST_NO_REDCHAIN and (MP model) ST_REDUCE_SABERBLOCK. Disarmed saber stays away 3 s unless ATK is pressed to pull it sooner | 7264-7350, 6989-6996, 6914-6918 |

Knockdown sources seen in saber code (V): lost saber lock (1100 ms, bg_saber.c:1236-1255), staff kick toss (700 ms,
w_saber.c:8022-8030), grapple finish (1300 ms, w_saber.c:8904-8908). `BG_KnockDownable` only excludes vehicles and
emplaced guns (bg_pmove.c:373-392).

### 3e. How to avoid being hit (timing visible from the enemy's state)

| Fact | Citation | Status |
|---|---|---|
| A swing deals full damage only while `SaberAttacking(enemy)`: `saberMove` is an attack with `weaponstate == WEAPON_FIRING` and `saberBlocked == BLOCKED_NONE`, or any special move. Starts (`LS_S_*`), transitions and returns are not attacks (transitions damage only for sabers flagged for it) | w_saber.c:1121-1144, 4272-4278 | V |
| SP model: damage scales with how far the blade moved this frame, so the fast middle of a swing hurts most and a slow blade barely hurts | w_saber.c:4415-4426 | V |
| SP model: special moves have explicit zero-damage windows at the start and end (by `torsoTimer`), e.g. red DFA 550 ms / 400 ms, yellow flip 600 ms / 1000 ms, lunge 150 ms / 400 ms, backstab 400 ms / 450 ms, backslash last 500 ms, crouch backslash last 800 ms, katas 200 ms / 600-700 ms (300 ms for medium), roll stab after 400 ms | w_saber.c:3092-3561 | V |
| Per-hit debounce: `saberAttackWound = now + 100` after a body hit (MP model) and `g_saberDmgDelay_Wound` after a clash; idle touches every `g_saberDmgDelay_Idle` (350 ms) | w_saber.c:5161-5167, 5708, 4966 | V |
| Enemy in broken parry, bounce, knockaway or parry cannot attack until `weaponTime` (= `torsoTimer`) runs out | bg_saber.c:3665-3695, 3742-3744 | V |
| Enemy is committed during specials: view angles and/or movement locked (lunge, DFA, back attacks, spin attacks, stab down, kicks, roll stab) | bg_pmove.c:13372-13555, 14239-14346, 14447-14467, 14697-14704 | V |

---

## 4. Observable enemy state (server side)

A bot lives in the server, so `g_entities[n].client->ps` (full `playerState_t`) is directly readable. The subset that is
also networked to other clients in `entityState_t` (i.e. what a human could legitimately see) is copied in
`BG_PlayerStateToEntityState` (bg_misc.c:3056-3153).

| Field | Meaning for a duelling bot | In entityState? | Citation | Status |
|---|---|---|---|---|
| `ps.saberMove` | Current `saberMoveName_t`; classify with the helpers below | yes (`s.saberMove`) | bg_misc.c:3080; set bg_saber.c:4585 | V |
| `ps.torsoAnim`, `ps.legsAnim` | Actual animations; needed for lock/kata/roll/knockdown tests | yes | bg_misc.c:3067-3068 | V |
| `ps.torsoTimer`, `ps.legsTimer` | Time left in the anim; drives damage windows and recovery | not in the lines audited | w_saber.c:3047-3049 | U (network status not checked) |
| `ps.weaponTime` | > 0 = cannot start a new saber move | no (playerState only) | bg_saber.c:3903-3906 | V |
| `ps.weaponstate` | `WEAPON_FIRING` during swings; used by `SaberAttacking` | no | w_saber.c:1135-1137 | V |
| `ps.saberBlocked` | Pending block/bounce/broken-parry reaction (`BLOCKED_*`) | no | bg_saber.c:3656-3801 | V |
| `ps.saberBlocking` | `BLK_NO/TIGHT/WIDE` of current move (from `saberMoveData`) | no | bg_saber.c:4586 | V |
| `ps.fd.saberAnimLevel` | Style in use | yes (`s.fireflag`) | bg_misc.c:3146 | V |
| `ps.fd.saberAnimLevelBase`, `saberDrawAnimLevel` | Owned style / queued style | no | w_saber.c:8704-8714 | V |
| `ps.saberAttackChainCount` | Swings chained so far (0..16) | no | bg_saber.c:4288-4300 | V |
| `ps.saberHolstered` | 0 on, 1 one blade/saber off, 2 off | yes | bg_misc.c:3094; bg_pmove.c:356-371 | V |
| `ps.saberInFlight`, `ps.saberEntityNum` | Thrown (`saberEntityNum != 0`) or knocked away (`== 0`) | yes | bg_misc.c:3078-3079; bg_saber.c:3460 | V |
| `ps.saberLockTime`, `saberLockEnemy`, `saberLockFrame`, `saberLockHits`, `saberLockAdvance` | Lock state and progress | `saberLockFrame` as `s.forceFrame` | bg_misc.c:3056; g_active.c:4994-5072 | V |
| `ps.forceHandExtend`, `forceHandExtendTime` | `HANDEXTEND_KNOCKDOWN` etc.; blocks auto-block and locks | no | w_saber.c:10019, 1623-1627 | V |
| `ps.groundEntityNum` | Airborne test (`ENTITYNUM_NONE`) | not checked | bg_saber.c:624 | U (network status not checked) |
| `ps.pm_flags & PMF_DUCKED` | Crouched (no lock, lunge possible) | no | w_saber.c:1629-1633 | V |
| `ps.fd.forcePower`, `forcePowerLevel[FP_SABER_OFFENSE/DEFENSE/SABERTHROW/LEVITATION]` | Whether specials are affordable; clash maths | no | bg_saber.c:133-142 | V |
| `ps.brokenLimbs` | Arm broken: power x0.3, slower anims | yes | bg_misc.c:3153; w_saber.c:222-226 | V |
| `ps.saberEventFlags` | `SEF_HITENEMY / HITWALL / PARRIED / BLOCKED / DEFLECTED / LOCK_WON` feedback for the owner | no | w_saber.c:4849, 5153, 5555, 5584-5585; bg_saber.c:1259 | V |
| `client->pers.cmd.buttons` | Enemy's last buttons (the server itself uses it for the "holding attack = no auto-block" rule); a human cannot see this | no | w_saber.c:9986 | V |

Classification helpers:

| Helper | True when | Location | Status |
|---|---|---|---|
| `BG_SaberInAttackPure(move)` | One of the 7 directional `LS_A_*` | bg_panimate.c:256-263 | V |
| `BG_SaberInAttack(move)` | Directional attack or any special/kick/kata | bg_panimate.c:264-336 | V |
| `BG_SaberInSpecial(move)` | Any special (these are "unblockable") | bg_panimate.c:368-435 | V |
| `BG_SaberInKata(move)` / `BG_InKataAnim(anim)` | Kata moves / anims | bg_panimate.c:338-366 | V |
| `BG_KickMove(move)` / `BG_KickingAnim(anim)` | Staff kicks | bg_panimate.c:437-467, 731 | V |
| `BG_SaberInIdle(move)` | NONE / READY / DRAW / PUTAWAY | bg_panimate.c:469-481 | V |
| `BG_InExtraDefenseSaberMove(move)` | Spin attacks, katas, dual jump attack (always knock a thrown saber down) | bg_panimate.c:483-500; w_saber.c:7367-7374 | V |
| `BG_SaberInSpecialAttack(anim)` | Special-attack animations | bg_panimate.c:656 | V (body not read: U for exact list) |
| `BG_SpinningSaberAnim(anim)` | Spin anims (slow movement) | bg_panimate.c:548 | U (body not read) |
| `PM_SaberInStart(move)` | `LS_S_*` wind-up | bg_panimate.c:1343-1350 | V |
| `PM_SaberInTransition(move)` | `LS_T1_*` | bg_panimate.c:1784-1791 | V |
| `PM_SaberInReturn(move)` / `BG_SaberInReturn(move)` | `LS_R_*` recovery | bg_panimate.c:1352-1364 | V |
| `BG_SaberInTransitionAny(move)` | Start, transition or return | bg_panimate.c:1793-1808 | V |
| `PM_SaberInBounce(move)` | `LS_B1_*` / `LS_D1_*` | bg_saber.c:717-728 | V |
| `PM_SaberInDeflect(move)` | `LS_D1_*` | bg_panimate.c:1307-1314 | V |
| `PM_SaberInParry(move)` | `LS_PARRY_*` | bg_panimate.c:1316-1323 | V |
| `PM_SaberInKnockaway(move)` | `LS_K1_*` | bg_panimate.c:1325-1332 | V |
| `PM_SaberInReflect(move)` | `LS_REFLECT_*` | bg_panimate.c:1334-1341 | V |
| `PM_SaberInBrokenParry(move)` | `LS_V1_*` / `LS_H1_*` — **always false on the server when ST_NO_REDCHAIN is set** | bg_saber.c:1545-1562 | V |
| `SaberAttacking(ent)` (static) | The server's own "is doing damage" test | w_saber.c:1121-1144 | V |
| `BG_InRoll(ps, anim)` | Roll / get-up-roll anim with `legsTimer > 0` | bg_panimate.c:926-949 | V |
| `BG_InKnockDown(anim)` | Knockdown or any get-up anim (no timer test) | bg_pmove.c:12414-12463 | V |
| `PM_InKnockDown(ps)` | Same but get-ups only while `legsTimer` runs | bg_panimate.c:1375-1427 | V |
| `BG_InKnockDownOnGround(ps)` | Lying phase (stab-down victim test) | bg_panimate.c:1154 | U (body not read) |
| `BG_InSaberLock(anim)` / `BG_SaberLockBreakAnim` / `BG_SuperBreakWinAnim` / `BG_SuperBreakLoseAnim` | Lock states | bg_panimate.c:1101, 1668, 1639, 1611 | U (bodies not read) |
| `BG_InSpecialJump(anim)`, `BG_FlippingAnim(anim)` | Flip / wall-move anims | bg_panimate.c:92, 502 | U (bodies not read) |
| `BG_SabersOff(ps)` | Saber fully off | bg_pmove.c:356-371 | V |
| `G_PowerLevelForSaberAnim(ent, saberNum, mySaberHit)` (static) | Per-anim damage level incl. start/end dead windows | w_saber.c:3039-3564 | V |
| `saberMoveData[move]` | anim, start/end quadrant, blocking type, `chain_idle`, `chain_attack` | bg_saber.c:151-363 | V |

Practical classification: "mid-swing" = `SaberAttacking`; "winding up" = `PM_SaberInStart`; "recovering" =
`PM_SaberInReturn`, bounce, deflect, knockaway, parry with `weaponTime > 0`; "open" = broken parry / super-break lose
(blade box removed), `forceHandExtend == HANDEXTEND_KNOCKDOWN`, `BG_InKnockDown(legsAnim)`, saber away
(`saberInFlight`), saber off, or locked into a special with view lock.

---

## 5. Disabled, unreachable or changed versus base JKA

| Item | Finding | Citation | Status |
|---|---|---|---|
| Style cycling | Rewritten ("Niksata Edit"): single-saber users cycle through DESANN and TAVION too, with no FP_SABER_OFFENSE level limit | g_cmds.c:3902-4138 | V |
| Style validation | `WP_UseFirstValidSaberStyle` / `WP_SaberStyleValidForSaber` rewritten; all styles valid unless the saber forbids them | bg_saberLoad.c:263-399 | V |
| New kata | `LS_A1_SPECIAL_YODA` (anim `BOTH_A1_SPECIAL_YODA`) for SS_TAVION, added to the enum, move table and classifiers | bg_public.h:1500; bg_saber.c:223, 3870-3872; bg_panimate.c:314, 343, 360 | V |
| Desann/Tavion attack power | `G_SaberAttackPower` uses the raw enum (4 and 5), so both out-power STRONG in clash maths; Tavion's SP damage level is still 2 | w_saber.c:157-174, 3072-3079 | V |
| `WP_SaberCanBlock` | Rewritten with the `japp_saber*` chance system; only reached in the MP damage model | w_saber.c:9949-10051, 4982-4986 | V |
| `g_saberAlwaysBlock` | New: keeps the blade box active during broken parries (1 all, 2 NPC only) | w_saber.c:444-462, 483-495 | V |
| MP damage table | jaPRO rewrite with per-style scale cvars (`g_blueDamageScale`, `g_yellowDamageScale`, `g_redDamageScale`, `g_backslashDamageScale`, `g_redDFADamageScale`); the base "x0.5 vs saber users" reduction is commented out | w_saber.c:4453-4654, 5064-5085 | V |
| Pull attacks `LS_PULL_ATTACK_STAB/SWING` | Server: `#if 0`; only a `_CGAME` JA+ prediction path exists -> not reachable | bg_saber.c:2314-2448 | V |
| `LS_JUMPATTACK_CART_LEFT/RIGHT` | Dead branch (`if (1)` always picks the arial) | bg_saber.c:2599-2606, 2662-2669 | V |
| `LS_JUMPATTACK_STAFF_LEFT` | Selection commented out | bg_saber.c:2075-2090 | V |
| `LS_A_FLIP_STAB` | Only with ST_NO_REDCHAIN (50 %); otherwise always `LS_A_FLIP_SLASH` | bg_saber.c:1783-1796 | V |
| `LS_HILT_BASH`, `LS_KICK_S`, `LS_KICK_BF`, `LS_KICK_RL` | Selection is commented out or `_CGAME`-only | bg_saber.c:2945-3006, 3025-3032 | V |
| `LS_LEAP_ATTACK` (long leap) | The start anim is only set under `_CGAME` -> not reachable on the server | bg_pmove.c:3624-3629; bg_saber.c:4120-4132 | V |
| `LS_SPINATTACK_ALORA`, `LS_SPINATTACK_JAPLUS`, `LS_MELEE_*`, `LS_JUMP_BACK*`, `LS_FLIP_STAB` | `_CGAME`-only (JA+ compatibility) | bg_saber.c:354-362, 1841-1876, 3210-3298 | V |
| `LS_UPSIDE_DOWN_ATTACK`, `LS_SWOOP_ATTACK_*`, `LS_TAUNTAUN_ATTACK_*` | No code in `codemp/game` sets them (table/classifier entries only) | grep over codemp/game | V for this directory |
| Saber flag `noBackAttack` (`SFL_NO_BACK_ATTACK`) | Parsed but never tested -> not enforced | bg_saberLoad.c:1234; bg_saber.c:2857-2878 | V |
| Random idle attack | Removed: no keys = overhead | bg_saber.c:2897-2911 | V |
| Staff neutral ALT | Does nothing unless `g_flipKick` (then forward kick) | bg_saber.c:3043-3053 | V |
| Roll stab / stab down / kicks / katas / cartwheels | Present as in base JKA | section 2c | V |

### jaPRO / fork cvars that change saber rules

`g_tweakSaber` bits (g_local.h:273-294):

| Bit | Value | Name | Effect found in code | Citation | Status |
|---|---|---|---|---|---|
| 0 | 1 | ST_NO_MP_SABERLERP | Skips the lerped damage trace in the MP model | w_saber.c:9650 | V |
| 1 | 2 | ST_JK2_DMGSYSTEM | Forces MP model with JK2 fixed damages (e.g. red 100, DFA 120) and immediate knockback | w_saber.c:3919-3924, 4529-4560, 5132-5144 | V |
| 2 | 4 | ST_REDUCE_SABERBLOCK | Weaker-or-equal style cannot block (MP model); disables broken-parry disarm | w_saber.c:9913-9927, 7276-7277 | V |
| 3 | 8 | ST_REDUCE_SABERDROP | Thrown saber is not knocked down when blocked (MP model) | w_saber.c:7398-7399 | V |
| 4 | 16 | ST_ALLOW_ROLLCANCEL | Roll allowed during a swing start; removes the 0.75 backwards-run slowdown | bg_pmove.c:6273-6297, 12098-12107 | V |
| 5 | 32 | ST_NO_REDCHAIN | "JK2 swings": strong chains 1 swing, no broken parries/knockaways/disarms from clashes, different transition handling, yellow flip may be the stab | bg_local.h:117; bg_saber.c:794-797, 1548, 1792; w_saber.c:5368, 5415, 5514, 5569, 5587, 5602, 7279; bg_panimate.c:2860-2875 | V |
| 6 | 64 | ST_FIXED_SABERSWITCH | Changes weapon-switch timing to the saber | bg_pmove.c:9111, 11476 | V (effect details U) |
| 7 | 128 | ST_EASYBACKSLASH | Back attack needs only a player within 128 units (height window) | bg_saber.c:1605-1633 | V |
| 8 | 256 | ST_JK2RDFA | Red DFA uses the JK2 trigger (during a swing) | bg_saber.c:2731-2785; bg_pmove.c:4483-4520 | V |
| 9 | 512 | ST_FIXYELLOWDFA | Yellow flip: 50 instead of 150 forward speed, no auto-spin | bg_saber.c:1730-1737; bg_pmove.c:14253-14263 | V |
| 10 | 1024 | ST_SPINREDDFA | View not locked during red DFA | bg_pmove.c:14699-14700 | V |
| 11 | 2048 | ST_SPINBACKSLASH | View not locked during back attacks | bg_pmove.c:14697-14702 | V |
| 12 | 4096 | ST_JK2LUNGE | Air lunge for FAST/DUAL; view not locked during lunge | bg_saber.c:2804-2824; bg_pmove.c:14703-14704 | V |
| 13 | 8192 | ST_REDDFAFIX | Red DFA is not cancelled by the chain-done rule | bg_saber.c:4189-4192 | V |
| 14 | 16384 | ST_REDDFANOFORCE | Red DFA costs no force | bg_saber.c:2752-2755 | V |
| 15 | 32768 | ST_EASIERBACKSLASH | Back attack always available | bg_saber.c:1602-1603 | V |
| 16 | 65536 | ST_SABERGUN | Changes the lerped SP damage trace condition | w_saber.c:5721 | U (not read further) |
| 17 | 131072 | ST_FASTCYCLE | 100 ms style-cycle debounce for single sabers | g_active.c:5481-5484 | V |
| 18 | 262144 | ST_NEWSPSABERDMG | SP damage without blade-speed term, per-move factors | w_saber.c:4380-4405 | V |
| 19 | 524288 | ST_DUNESABER | SP damage inversely scaled by blade speed | w_saber.c:4364-4379 | V |
| 20 | 1048576 | ST_NEWSPSABERDMGCAP | SP damage with blade travel capped at 30 | w_saber.c:4406-4414 | V |
| 21 | 2097152 | ST_JAPLUS_DMG | JA+ MP damage table, MP model everywhere | w_saber.c:3925-3927, 3959-4032, 4459-4462 | V |

Other cvars (defaults from g_xcvar.h):

| Cvar | Default | Effect | Citation | Status |
|---|---|---|---|---|
| `d_saberSPStyleDamage` | 1 | Selects SP damage/blocking model | g_xcvar.h:58; w_saber.c:3935 | V |
| `g_saberDuelSPDamage` / `g_forceDuelSPDamage` | 1 / 0 | Same, inside saber / force private duels | g_xcvar.h:199-200; w_saber.c:3929-3934 | V |
| `g_saberDamageScale` | 1 | Scales all real saber damage | w_saber.c:4787-4789 | V |
| `g_blueDamageScale`, `g_yellowDamageScale`, `g_redDamageScale` | 1 | MP-model per-style scales | g_xcvar.h:202-204; w_saber.c:4529-4644 | V |
| `g_backslashDamageScale`, `g_redDFADamageScale` | 1 | MP-model back attack / red DFA scales | g_xcvar.h:195, 205; w_saber.c:4471-4650 | V |
| `g_saberTouchDmg` | 0 | Idle blade contact damage (MP model) | w_saber.c:4685-4698 | V |
| `g_saberDmgDelay_Idle` / `_Wound` / `_Hit` | 350 / 0 / 0 | Damage debounces (idle touch, after clash, per attacker-target) | g_xcvar.h:137-138, 206; w_saber.c:4966-4978, 5708 | V |
| `g_saberDmgVelocityScale` | 0 | Knockback from saber damage | g_combat.c:5153, 5242 | U (not read) |
| `g_reducesaberblock` | 0 | Percent chance a blade contact is ignored (MP model) | w_saber.c:5215-5218 | V |
| `g_maxSaberDefense` | -1 | Caps FP_SABER_DEFENSE level | bg_misc.c:829-830 | V |
| `g_saberAlwaysBlock` | 0 | See section 3c | g_xcvar.h:207 | V |
| `japp_saberTweaks`, `japp_saberBlockChanceMax/Min/Scale`, `japp_saberBlockStanceParity` | 0, 0.75, 0.0, 0.5, 3.0 | Stance-based auto-block chance (MP model) | g_xcvar.h:208-212; w_saber.c:9995-10007 | V |
| `g_saberLocking`, `g_saberLockFactor`, `g_saberLockRandomNess` | 1, 2, 2 | Lock enable / chance / push randomness | g_xcvar.h:140-142; w_saber.c:1549, 5302-5304; g_active.c:5054-5056 | V |
| `g_saberDisable` | 0 | Style bitmask (section 1) | g_local.h:297-303 | V |
| `g_fixGroundStab` | 0 | 0: stab down damages only grounded victims; > 1 lowers its MP damage | w_saber.c:4961-4964, 4476-4523 | V |
| `d_saberKickTweak` | 1 | Kick damage x0.2 and knockdown immunity for ready saber users | w_saber.c:4034-4047, 7980-8006, 8102-8105 | V |
| `g_flipKick` | 0 | Enables neutral staff kick; wall-flip kick variants | bg_saber.c:3045-3052; bg_pmove.c:3884-3940 | V / U for kick variants |
| `g_fixRoll` | 0 | Roll speed requirement (section 2c row 21) | bg_pmove.c:8349-8353 | V |
| `g_tweakForce & FT_NO_CROUCHATTACK_FP` (bit 0) | 0 | Lunge / crouch spin attacks cost no force | g_local.h:247; bg_saber.c:2798-2801 | V |
| `g_fixSaberInGrip` | 0 | Saber toggle while gripped | g_cmds.c:3823-3829 | V |
| `g_fixSaberDisarmBonus` | 1 | Second saber's `disarmBonus` counts | w_saber.c:7245-7250 | V |
| `g_fixSaberMoveData` | 1 | Swaps mirrored LR/LL parry anims | bg_saber.c:365-395 | V |
| `d_saberGhoul2Collision` | 1 | Per-poly collision; changes level-3 auto-block arc (0.3 vs 0.05) | w_saber.c:10025-10029 | V |
| `g_saberTraceSaberFirst`, `d_saberInterpolate`, `d_saberBoxTraceSize`, `d_saberAlwaysBoxTrace` | 0, 0, 0, 0 | Trace details of the damage check | w_saber.c:4061, 4110, 9491-9520 | V (effects not analysed) |
| `g_allowSaberSwitch` | 0 | Lets players change saber hilt/type by command | g_cmds.c:4776, 5766 | U (command bodies not read) |

---

## Counts

Server-reachable attack / special saber moves (`saberMoveName_t` values a player can cause through inputs): **43**

- 7 directional attacks: `LS_A_TL2BR, LS_A_L2R, LS_A_BL2TR, LS_A_BR2TL, LS_A_R2L, LS_A_TR2BL, LS_A_T2B`
- 3 back attacks: `LS_A_BACKSTAB, LS_A_BACK, LS_A_BACK_CR`
- 1 `LS_ROLL_STAB`, 1 `LS_A_LUNGE`, 1 `LS_A_JUMP_T__B_`, 2 `LS_A_FLIP_STAB / LS_A_FLIP_SLASH`
- 3 dual: `LS_JUMPATTACK_DUAL, LS_DUAL_FB, LS_DUAL_LR`; 2 cartwheels: `LS_JUMPATTACK_ARIAL_LEFT / _RIGHT`
- 4 staff jump moves: `LS_JUMPATTACK_STAFF_RIGHT, LS_BUTTERFLY_LEFT, LS_BUTTERFLY_RIGHT, LS_A_BACKFLIP_ATK`
- 2 crouch spins: `LS_SPINATTACK, LS_SPINATTACK_DUAL`
- 8 kicks: `LS_KICK_F/B/R/L` and `LS_KICK_F_AIR/B_AIR/R_AIR/L_AIR`
- 3 stab downs: `LS_STABDOWN, LS_STABDOWN_STAFF, LS_STABDOWN_DUAL`
- 6 katas: `LS_A1_SPECIAL, LS_A1_SPECIAL_YODA, LS_A2_SPECIAL, LS_A3_SPECIAL, LS_DUAL_SPIN_PROTECT, LS_STAFF_SOULCAL`

Not counted (entered automatically by the system, not chosen by the player): `LS_READY/DRAW/PUTAWAY`, starts `LS_S_*`,
returns `LS_R_*`, transitions `LS_T1_*`, bounces `LS_B1_*`, deflections `LS_D1_*`, reflected `LS_V1_*`, broken parries
`LS_H1_*`, knockaways `LS_K1_*`, parries `LS_PARRY_*`, missile reflects `LS_REFLECT_*`. Saber throw and lock pushes are
mechanics without their own `saberMoveName_t`.

## Things not audited (honest gaps)

- Animation lengths (swing durations per style) live in the animation config, not in C; no numbers are given here.
- `G_KickSomeMofos` per-kick timing windows, `WP_GetSaberDeflectionAngle` internals, `WP_SaberStartMissileBlockCheck`
  (projectile deflection), thrown-saber damage (`CheckThrownSaberDamaged`), flip-kick damage, and the duel-loss disarm call site.
- Whether `torsoTimer` / `groundEntityNum` are networked to other clients.
- Spawn-time style assignment (g_client.c:4120) and the saber-change commands.
