# JK2 1.02 saber system vs our JKA fork: porting map for `g_jk2_102sabersystem`

Analysis only. No code was changed. Written 2026-11-27.

## 0. Sources, method and conventions

- **JK2 reference:** `E:\jedi academy modding archive\external_study\mvsdk\code\game` (and `code\cgame`) at git `4c7c463`. mvsdk picks 1.02 behaviour at runtime with `jk2gameplay == VERSION_1_02`, and once with `jk2version`/`jk2startversion` (engine and protocol). Only the 1.02 branch is described here. 1.03/1.04 are mentioned only where our JKA code follows them.
- **Our fork:** `E:\jedi academy modding archive\TaystJK_AI_Claude_Code_improvements\TaystJK_AI-Improved-Bots\codemp\game` and `...\codemp\cgame`. `bg_*.c` is built into both game and cgame.
- **Assets compared:**
  - JK2: `E:\SteamLibrary\steamapps\common\Jedi Outcast\GameData\base\assets0.pk3` → `models/players/_humanoid/animation.cfg` (17278 frames, 989 sequences, dated 02-Mar-2002). No later JK2 pk3 replaces it, so 1.02 and 1.04 use the same animation data.
  - Vanilla JKA: `Jedi Academy clean\GameData\Base\assets1.pk3` → `_humanoid/animation.cfg` (21376 frames, 1417 sequences, July 2003).
  - What our test install actually loads: `Jedi Academy TaystJK_AI test\GameData\nicjk\japro-assets.pk3` → a custom `_humanoid/animation.cfg` (51907 bytes) and `_humanoid.gla` (17.7 MB). It is mod-dir content, so it overrides base.
  - Scratch copies and the compare scripts are in the session scratchpad. They are not part of the repo.
- File references use the form `file:function:line`. "mv" means the mvsdk file and "ours" means the fork file. Quoted values are exact copies from the source.
- Style numbers: `FORCE_LEVEL_1/2/3` = blue/yellow/red, which is `SS_FAST/SS_MEDIUM/SS_STRONG` in JKA.

### 0.1 The most important findings (short list)

1. **1.02 damage is a flat amount per hit, not "damage over the swing".** mv `w_saber.c:CheckSaberDamage_1_02:1541`: blue 35, yellow 60, red 100 for any frame of an attack move. The same swing can hit again every 100 ms (`saberAttackWound = level.time + 100`). Starts, returns and transitions only do the 5-point "idle" touch every 200 ms. `G_GetAttackDamage` (the ramp) is 1.03/1.04 only. The famous "damage over swing" in 1.02 is really the repeated 100 ms hits. 1.02 saber hits also **knock the victim back** (`knockback = damage`, see 1.9).
2. **1.02 has no deflections, knockaways or saber-vs-saber broken parries.** Every blocked attack is a straight `BLOCKED_ATK_BOUNCE`. The defender always plays a quadrant parry (`WP_SaberBlockNonRandom`). Whether the defender blocks at all is a random roll against attack level and saber-defence level (mv `w_saber.c:WP_SaberCanBlock:4173-4209`). A red attacker also bounces a defender who is mid-move. Broken parries happen only to the loser of a circle saber lock.
3. **Transitions (chains) use the level-1 (blue) T1 animations for every style and are not sped up or slowed down.** On the server the torso timer for any AFLAG_ACTIVE move is `numFrames*frameLerp - 2*frameLerp - 1`, which is one frame shorter than JKA. Knockaways, broken parries and "reflected" moves are levelled to the style's set (in JKA they are not).
4. **Kata limit:** red may chain only while `saberAttackChainCount <= irand(0,1)`, yellow while `<= irand(2,5)`, and blue without limit (mv `bg_saber.c:PM_SaberKataDone_1_02:697`). When the kata is done no directional attack can be chosen; the move becomes `chain_idle` of the current move.
5. **Special moves are free (no force cost) and are not view-locked.** Red DFA comes only from jumping within 500 ms of starting any attack while moving forward; attack does not need to be held. Yellow DFA needs someone within 200 units in front. A blue lunge also works in the air while crouched. Backstab/back attack works only against clients (`entityNum < MAX_CLIENTS`). Back attacks/backstab +20 and red DFA +40 damage, all unblockable.
6. **Saber collision:** one blade, length 40, from bolt 0 of the saber model. Plain line traces against `MASK_PLAYERSOLID|CONTENTS_LIGHTSABER`. No ghoul2 collision and no box trace. Saber-vs-saber contact is found by hitting the other saber's entity box, which is ±8 units centred 20 units up the blade (`SABER_BOX_SIZE` is 8 in 1.02 and 16 in ours). The server ghoul2 torso animation is set on `upper_lumbar` (`lower_lumbar` in 1.03+ and in ours) with the 1.02 spine-angle formula.
7. **Assets:** every saber sequence the 1.02 code uses (A/S/R/T/B/D/V/H/K levels 1-3, P1, specials, the four JK2 lock and break animations, rolls, `SABERPULL`) has **identical frame count, loop frame and fps** in vanilla JKA and in our custom `japro-assets.pk3` cfg (281 sequences checked, 0 differences). There are two exceptions: `BOTH_SABERFAST_STANCE` and `BOTH_STAND2` are 1 frame in JKA and in our cfg, but 2 frames in JK2. The bone data inside the .gla files was **not** compared (see section 2).
8. The existing jaPRO options (`ST_JK2_DMGSYSTEM`, `ST_JK2RDFA`, `ST_JK2LUNGE`, `ST_NO_REDCHAIN`/`JK2SWINGS`, `ST_FIXYELLOWDFA`, `ST_ALLOW_ROLLCANCEL`) are approximations with **different values** from 1.02 (details in 1.15). The new system must not rely on them.

---

## 1. Rule-by-rule differences

### 1.1 Saber move table (`saberMoveData`), quadrants, transition matrix

| Item | mvsdk 1.02 | Ours now |
|---|---|---|
| Table | mv `bg_saber.c:saberMoveData:100-253`. One table for all JK2 versions (no per-version table exists in `bg_multiversion.c`). | ours `bg_saber.c:saberMoveData:53-363`. The rows JK2 also has hold the same anim, quadrants, blend, blocking, chain_idle, chain_attack and trailLen as JK2, apart from the lower parry anims and the flag macro noted below. |
| Move enum | JK2 order: NONE, READY, DRAW, PUTAWAY, A_*×7, BACKSTAB, BACK, BACK_CR, LUNGE, JUMP_T__B_, FLIP_STAB, FLIP_SLASH, S_*, R_*, T1_*, B1, D1, V1, H1, K1, PARRY, REFLECT | JKA adds `LS_ROLL_STAB` after `LS_A_BACK_CR` and about 40 more specials (dual/staff jump attacks, kicks, katas, stabdowns, pull attacks, ...) between `LS_A_FLIP_SLASH` and `LS_S_TL2BR`. It also adds JA+ rows under `#ifdef _CGAME` at the end. The JK2 range checks (`>= LS_T1_BR__R`, `LS_PARRY_UP..LS_REFLECT_LL`, `LS_S_*`, `LS_A_TL2BR..LS_A_T2B`) keep the same meaning with the JKA enum, because the inserted moves are below `LS_S_TL2BR`. |
| `AFLAG_ACTIVE` | `SETANIM_FLAG_HOLD|SETANIM_FLAG_HOLDLESS` (OVERRIDE commented out, mv:96) | `SETANIM_FLAG_OVERRIDE|SETANIM_FLAG_HOLD|SETANIM_FLAG_HOLDLESS` (ours:49). **Effectively no difference in 1.02:** 1.02 `PM_SetSaberMove` adds OVERRIDE to every move (mv:2004-2012) and HOLD to every move (mv:2057). |
| Lower parries/knockaways/broken parries | "BParry LR" `BOTH_H1_S1_BL`, "BParry LL" `BOTH_H1_S1_BR`, "Knock LR" `BOTH_K1_S1_BL`, "Knock LL" `BOTH_K1_S1_BR`, "Parry LR" `BOTH_P1_S1_BL`, "Parry LL" `BOTH_P1_S1_BR` | `BG_FixSaberMoveData` (ours `bg_saber.c:365`) swaps these to `_BR`/`_BL` when `g_fixSaberMoveData` is set (default **1**, `g_xcvar.h:94`; the cgame reads `CS_LEGACY_FIXES`). **1.02 = the unfixed values.** |
| `transitionMove[8][8]` | mv:255-337 | ours:397-407, same values. |
| `saberMoveTransitionAngle` | mv:599-680 | ours:731-749, same values. |
| `PM_SaberMoveQuadrantForMovement`, `PM_AttackMoveForQuad` | mv:527, mv:339 | ours:667, ours:409, same. |
| `BG_SaberInAttack` | A_* plus BACK, BACK_CR, BACKSTAB, LUNGE, JUMP_T__B_, FLIP_STAB, FLIP_SLASH (mv `bg_panimate.c:64`) | JKA list is longer (all the JKA specials). |
| `BG_SaberInSpecial` | the 7 specials above (mv `bg_panimate.c:85`) | JKA list is longer. |
| `BG_SaberInSpecialAttack(anim)` | `A2_STABBACK1, ATTACK_BACK, CROUCHATTACKBACK1, BUTTERFLY_LEFT/RIGHT, FJSS_TR_BL/TL_BR, LUNGE2_B__T_, FORCELEAP2_T__B_, JUMPFLIPSLASHDOWN1, JUMPFLIPSTABDOWN` (mv:219) | JKA list is longer. |
| `PM_SaberInBounce` | B1_BR..B1_BL and D1_BR..D1_BL (D1_B_ excluded) (mv:577) | same (ours:717) |
| `PM_SaberInBrokenParry` | **1.02: only H1_T_..H1_BL**. V1 ("reflected") counts only from 1.03 on (mv:1029-1040). | V1 and H1 (ours:1545) |
| `PM_GetSaberStance` | blue `BOTH_SABERFAST_STANCE`, yellow `BOTH_STAND2`, red `BOTH_SABERSLOW_STANCE` (mv `bg_pmove.c:241`) | adds saber-file `readyAnim`, dual/staff/Tavion/Desann stances, and `BOTH_STAND1` when the saber is off or lost (ours `bg_pmove.c:469`). |

### 1.2 Transition selection (`PM_SaberAnimTransitionAnim`)

mv `bg_saber.c:371-525`, ours `bg_saber.c:441-597`.

| Case | 1.02 | Ours |
|---|---|---|
| `newmove == curmove` (repeat the same attack) | The KataDone block is **skipped** (mv:419 `if ( newmove == curmove && jk2gameplay != VERSION_1_02 )`). It falls to the normal path, which gives a transition. | calls `PM_SaberKataDone`; when done it returns the return move, otherwise a transition (ours:490-499) |
| curmove is a deflection D1_* | **No transition**: mv:448 `if ( jk2gameplay == VERSION_1_02 ) break;`. retmove stays newmove. | transition (ours:513-521) |
| curmove is K1_*, V1_*, H1_* | **No transition** (mv:477 break) | transition (ours:567-584) |
| curmove is R_*, PARRY_*, REFLECT_* | transition | transition |
| curmove is A_* | transition | transition |

### 1.3 Animation level offset (`PM_SetSaberMove`)

mv `bg_saber.c:1943-2082`, ours `bg_saber.c:4279-4595`.

- **1.02 rule** (mv:1973-1984): if `saberAnimLevel > 1` and the move is not idle, parry, reflect or special, and is **not a transition**, then `anim += (level-1)*SABER_ANIM_GROUP_SIZE`. Bounces, knockaways (K), broken parries (H) and reflected (V) moves **are** levelled. Transitions always use T1.
- **Ours (default):** levelled unless idle, parry, **knockaway**, **broken parry**, reflect or special. **Transitions are levelled** (T2/T3).
- Ours under `JK2SWINGS(ps)` (`ST_NO_REDCHAIN`, ours:4377-4381) already copies the 1.02 levelling rule.
- Chain counter: 1.02 resets `saberAttackChainCount` **only** on `LS_READY` (mv:1949). JKA also resets it on FLIP_STAB/FLIP_SLASH (ours:4288). Both clamp it to 16.
- Override: 1.02 ORs `SETANIM_FLAG_OVERRIDE` for every move (mv:2012 `|| jk2gameplay == VERSION_1_02`) and adds `SETANIM_FLAG_HOLD` to every `PM_SetAnim` call (mv:2057). Even LS_READY gets a hold timer of the stance (n*lerp). Ours: OVERRIDE only for `BG_SaberInSpecial` and not on vehicles (ours:4396-4401). There is no global HOLD.
- Parts: 1.02 never takes the "standing still, so whole body" branch (mv:2042 needs `jk2gameplay != VERSION_1_02`). It plays BOTH only for the 7 specials and for spinning anims. Ours plays the whole body when not moving (ours:4498-4515), has the JKA special list (ours:4455-4492), and has extra arial-legs logic.
- 1.02 has no draw/putaway anim override from saber files, no staff/dual sets, no broken-limb pain events, and no "special: weaponTime = torsoTimer" (ours:4572-4576).
- Stand anim replacement: 1.02 checks `TORSO_DROPWEAP1..TORSO_WEAPONIDLE12` (JK2 enum). Ours checks `..TORSO_WEAPONIDLE10` and also replaces `BOTH_WALK1` and slope anims with the stance (ours:4419-4444).

### 1.4 Animation timers and speeds

**Server/pmove timer:**
- mv `bg_panimate.c:PM_SetAnimFinal:1048-1190`. 1.02 starts with `editAnimSpeed = 0` (mv:1053). `BG_SaberStartTransAnim` multiplies it, so it stays 0, and `if (editAnimSpeed && jk2gameplay == VERSION_1_02)` never runs.
- Torso, HOLD+HOLDLESS (all AFLAG_ACTIVE moves): `dur = numFrames*|frameLerp|; dur -= blendTime + |frameLerp|*2;` with `blendTime` forced to 0 (mv:1061). Timer = `dur-1` if dur > 1, otherwise `|frameLerp|` (mv:1088-1104). That is **(n-2)·lerp - 1**.
- Legs, HOLD+HOLDLESS: `(numFrames-1)*lerp - 2*lerp`, so **(n-3)·lerp - 1** (mv:1150-1154).
- HOLD without HOLDLESS (returns, AFLAG_FINISH, and in 1.02 also idle): `numFrames*lerp`, same in both games.
- Rage divides torso by 1.7 (both). Legs ÷1.3 in rage and ÷1.7 in speed: in 1.02 this applies to **every** held legs anim; ours applies it only to running/walking anims (ours `bg_panimate.c:3046-3057`).
- Ours: `bg_panimate.c:BG_SetAnimFinal:2944-3068`. HOLDLESS = `(n-1)*lerp`, scaled by `BG_SaberStartTransAnim` with `dur += dur - dur*speed`, then -1. So it is **one frame longer than 1.02** for every attack and start, and transitions are rescaled.

**Transition speed:**
- mv `bg_panimate.c:BG_SaberStartTransAnim:1023` gives blue ×1.5 and red ×0.75 for T1/T2/T3. In 1.02 this has **no effect on the pmove timer** (because of editAnimSpeed 0) and **no effect on the client animation** (mv `cgame/cg_players.c:1615` `if ( ci->jk2gameplay != VERSION_1_02 ) BG_SaberStartTransAnim(...)`).
- It **is** applied to the server ghoul2 torso animation (mv `w_saber.c:WP_SaberPositionUpdate:3879`, no version check). In mvsdk 1.02 the server's saber position during transitions therefore runs at 1.5×/0.75× while the client shows 1×. This is reproduced as mvsdk has it; see the uncertain list.
- Ours `bg_panimate.c:2860`: also applies the saber-file `animSpeedScale` to every `BOTH_A1_T__B_..BOTH_ROLL_STAB` anim and broken-limb slowdowns. The cgame applies it as well (ours `cgame/cg_players.c:3670`).
- Bug in our `JK2SWINGS` branch (ours `bg_panimate.c:2862-2875`): `animSpeed = 0;` assigns the local pointer, not `*animSpeed`. The only effect is the early return (no 1.5/0.75 scaling).

**Resulting timings** (both cfgs hold the same values for these anims; lerp = `floor(1000/fps)`; the "JKA" column is our pmove timer without saber `animSpeedScale` and without `JK2SWINGS`):

Attacks (A) and starts (S), AFLAG_ACTIVE:

| move | lvl | anim | n | fps | 1.02 timer ms | ours ms |
|---|---|---|---|---|---|---|
| A TL→BR | 1 | BOTH_A1_TL_BR | 6 | 30 | 131 | 164 |
| A L→R | 1 | BOTH_A1__L__R | 6 | 20 | 199 | 249 |
| A BL→TR | 1 | BOTH_A1_BL_TR | 6 | 30 | 131 | 164 |
| A BR→TL | 1 | BOTH_A1_BR_TL | 6 | 30 | 131 | 164 |
| A R→L | 1 | BOTH_A1__R__L | 7 | 20 | 249 | 299 |
| A TR→BL | 1 | BOTH_A1_TR_BL | 6 | 20 | 199 | 249 |
| A T→B | 1 | BOTH_A1_T__B_ | 8 | 30 | 197 | 230 |
| A TL→BR | 2 | BOTH_A2_TL_BR | 19 | 50 | 339 | 359 |
| A L→R | 2 | BOTH_A2__L__R | 17 | 50 | 299 | 319 |
| A BL→TR | 2 | BOTH_A2_BL_TR | 16 | 50 | 279 | 299 |
| A BR→TL | 2 | BOTH_A2_BR_TL | 13 | 50 | 219 | 239 |
| A R→L | 2 | BOTH_A2__R__L | 16 | 50 | 279 | 299 |
| A TR→BL | 2 | BOTH_A2_TR_BL | 19 | 50 | 339 | 359 |
| A T→B | 2 | BOTH_A2_T__B_ | 11 | 50 | 179 | 199 |
| A TL→BR | 3 | BOTH_A3_TL_BR | 14 | 30 | 395 | 428 |
| A L→R | 3 | BOTH_A3__L__R | 13 | 30 | 362 | 395 |
| A BL→TR | 3 | BOTH_A3_BL_TR | 12 | 30 | 329 | 362 |
| A BR→TL | 3 | BOTH_A3_BR_TL | 12 | 30 | 329 | 362 |
| A R→L | 3 | BOTH_A3__R__L | 9 | 30 | 230 | 263 |
| A TR→BL | 3 | BOTH_A3_TR_BL | 9 | 30 | 230 | 263 |
| A T→B | 3 | BOTH_A3_T__B_ | 27 | 40 | 624 | 649 |
| S (start) | 1 | BOTH_S1_S1_* | 4-8 | 20 | 99-299 | 149-349 |
| S (start) | 2 | BOTH_S2_S1_* | 9-33 | 36-132 | 188-220 | 215-233 |
| S (start) | 3 | BOTH_S3_S1_* | 15-45 | 30-60 | 428-791 | 461-824 |

Returns (`AFLAG_FINISH`) are `n*lerp` in both games, so no difference.

Transitions (1.02 always uses T1; ours uses T(level) with the speed factor):

| trans | T1 n/fps | 1.02 timer, all styles | ours blue (T1 ×1.5) | ours yellow (T2) | ours red (T3 ×0.75) |
|---|---|---|---|---|---|
| BR→R / R→BR / R→TR / TR→R / TR→T / T→TR / T→TL / TL→T / TL→L / L→TL / L→BL / BL→L | 4/±20 | 99 | 74 | 131-164 | 164-205 |
| BR→TR / R→T / TR→BR / TR→TL / T→R / T→L / TL→TR / TL→BL / L→T / BL→TL | 7/±20 | 249 | 149 | 131-197 | 164-246 |
| BR→T / R→TL / TR→L / T→BR / T→BL / TL→R / L→TR / BL→T | 10/±20 | 399 | 224 | 263 | 329 |
| TR→BL | 12/20 | 499 | 274 | 362 | 452 |
| BR→TL / BR→L / BR→BL / R→L / R→BL / TL→BR / L→BR / L→R / BL→BR / BL→R / BL→TR | 13/20 | 549 | 299 | 329-659 | 411-824 |

(The full per-transition list was produced by a script; the ranges above contain every value.)

### 1.5 Attack selection, chaining and kata (`PM_WeaponLightsaber`, `PM_SaberAttackForMovement`)

mv `bg_saber.c:PM_WeaponLightsaber:1356-1941`, ours `bg_saber.c:3300-4278`. mv `PM_SaberAttackForMovement:1229-1345`, ours `2463-2939`.

| Rule | 1.02 | Ours |
|---|---|---|
| Kata limit | `PM_SaberKataDone_1_02` (mv:697-705): `(level>=3 && chain > PM_irand_timesync(0,1)) \|\| (level==2 && chain > PM_irand_timesync(2,5))`. Blue never runs out. It does not look at the chain angle. | `PM_SaberKataDone` (ours:767-864) is the 1.03/1.04 version. Red: `> irand(2,3)` plus the chain-angle rules (`<135`/`>215` stops, 180 allows `>1`, others `>2`). Blue and yellow: the "spinning anim tolerance" (5 for blue, 3 otherwise). Yellow: `> irand(2,5)`. Staff, dual, Tavion and Desann never stop. `JK2SWINGS` stops red after 1. |
| Where the kata check runs | Directional attack (mv:1834-1848): **first** `PM_SaberKataDone_1_02()`. If done, `newmove = chain_idle` of curmove; otherwise `PM_SaberAttackForMovement`. No "repeat of the blocked quadrant uses chain_attack" rule. | Picks the move, then the "repeat of bounced quad → chain_attack" rule, then KataDone (with the `ST_REDDFAFIX` exception) (ours:4178-4192). |
| Broken parry, attack pressed | **no** "must return to ready" rule in 1.02 (mv:1816 needs `!= 1.02`). Falls to the movement attack. | always `LS_READY` (ours:4174-4177). |
| Bounce with no direction | uses `chain_attack`/`chain_idle` with `PM_SaberKataDone_1_02()` (mv:1318-1330) | `PM_SaberKataDone(curmove, chain_attack)` (ours:2886-2896) |
| Ready with no direction | **random** `PM_irand_timesync(LS_A_TL2BR, LS_A_T2B)` (mv:1339) | `LS_A_T2B` (ours:2898-2913; the JK2SWINGS random is under `#if 0`) |
| Parry/reflect → attack (direct) | mv:1774-1797: Q_T→`LS_A_T2B`, **Q_TR→`LS_A_TL2BR`**, **Q_TL→`LS_A_TR2BL`**, Q_BR→`LS_A_BR2TL`, Q_BL→`LS_A_BL2TR` | ours:4132-4151: Q_TR→**`LS_A_TR2BL`**, Q_TL→**`LS_A_TL2BR`** (TR and TL are **swapped**) |
| After saber block: hold parry | parry/reflect: if `weaponTime < 1`, `torsoTimer = weaponTime = SABER_BLOCK_DUR` (150) (mv:1636-1640) | additionally `weaponTime = bg_parryDebounce[defLevel]+200` for saber parries (ours:3658-3662) |
| `BLOCKED_BOUNCE_MOVE` | ignored in 1.02 (mv:1523). It is never set in 1.02 anyway. | restarts saberMove as a bounce (ours:3665-3671) |
| `BLOCKED_PARRY_BROKEN` with no broken move | 1.02 does nothing (the `saberBlocked = 0` reset is 1.03+, mv:1548) | nothing (ours:3690-3692) |
| `BLOCKED_ATK_BOUNCE` | if `saberMove >= LS_T1_BR__R` clear; else with attack held: transition from startQuad to a new quad (repeat-quad avoided with `PM_irand_timesync(Q_BR,Q_BL)`), without attack: return move; `weaponTime = torsoTimer` (mv:1557-1599) | same structure (ours:3696-3745) |
| Respawn | `if ( pm->ps->pm_flags & PMF_RESPAWNED && jk2gameplay == VERSION_1_02 ) return;` (mv:1468): no attack until the buttons are released after spawning | commented out (ours:3591-3597) |
| Knockdown/roll gate | none at the top of the function. `PM_SetAnim` refuses during a roll (mv `bg_panimate.c:1205-1208`), so the saber move does not start. | early branch for knockdown/roll, with JKA roll-stab (ours:3313-3345). `BG_SetAnim` roll guard commented out (ours `bg_panimate.c:3156-3159`). |
| Saber throw start | `ALT_ATTACK && weaponTime < 1 && saberCanThrow && force >= cost && !ysalamiri && BG_CanUseFPNow` (mv:1440-1453). No room check. | JKA adds the room trace `SABER_MIN_THROW_DIST`, `PM_SaberPowerCheck`, kick/kata use of alt attack and the MB2 guard (ours:3530-3567). |
| Guiding anim | always `BOTH_SABERPULL` + `torsoTimer = 1` (mv:1456-1461) | dual-style exceptions (ours:3569-3589) |
| Idle legs anim when no move | WALK1, RUN2, WALK2, else stance (mv:1885-1906; RUN2→stance fix is 1.03+) | larger JKA list (ours:4223-4249) |
| JKA-only content not in JK2 | — | kicks (`PM_KickMoveForConditions`), katas (`PM_CanDoKata`, `LS_A1/2/3_SPECIAL`), stab-downs, pull attacks, dual/staff specials, alt-attack specials (`PM_CheckAltKickAttack`, JA+ alt jumps), roll stab, long-leap attack, `BOTH_FORCELONGLEAP_*` gates (ours:4119-4130), vehicle checks |
| Random numbers | 1.02 uses unsynchronised `Q_irand` in the lock break event (mv:906), the lock pain/jump events (mv:996, 1011) and **flip stab vs flip slash** (mv:1143). Client and server therefore pick independently, which causes mispredictions in 1.02 itself. Everything else uses `PM_irand_timesync`. | `PM_irand_timesync` |

### 1.6 Special moves

| Move | 1.02 (mv) | Ours |
|---|---|---|
| **Blue lunge** `LS_A_LUNGE` | `bg_saber.c:1279-1285`: blue + forward only + `PMF_DUCKED` + `weaponTime <= 0`. In 1.02 the ground check is skipped (`groundEntityNum != NONE \|\| jk2gameplay != VERSION_1_04`), so **ducked in the air also lunges**. No special-attack check and **no force cost**. `PM_SaberLungeAttackMove` (mv:1181): forward velocity **150**, `EV_JUMP`. | ours:2788-2804: needs the ground, `!BG_SaberInSpecialAttack` and costs `SABER_ALT_ATTACK_POWER_FB`. Also used by dual/staff (spin attacks). `ST_JK2LUNGE` adds an air variant (ours:2805-2825, velocity 150). |
| **Yellow DFA** `LS_A_FLIP_STAB/SLASH` | Two triggers. (a) `PM_SaberAttackForMovement` (mv:1264-1276): yellow, forward, `velocity[2] > 100`, `PM_GroundDistance() < 32`, `!BG_InSpecialJump`, **`PM_SomeoneInFront`** (a box trace of 200 units, client only). (b) Jump pressed during an attack (mv `bg_pmove.c:1293-1325`): `animLength - torsoTimer < 500`, ground < 32, someone in front. `PM_SaberFlipOverAttackMove` (mv:1098): forward **50**, up 400 + 1.5·zDiff to the target, clamped (200 minimum on the same level, otherwise 100..400), stab or slash by **`Q_irand(0,1)`**, free. | ours:2712-2729: no someone-in-front check (commented out), costs FB power, forward **150** (50 with `ST_FIXYELLOWDFA`), no zDiff adjust (ours:1689-1797), saber-file overrides. The view spins during the flip unless `ST_FIXYELLOWDFA` (ours `bg_pmove.c:14290-14302`). |
| **Red DFA** `LS_A_JUMP_T__B_` | **Only** the jump-during-attack path (mv `bg_pmove.c:1326-1340`): red, `forwardmove > 0`, **attack held OR 1.02** (so not needed in 1.02), ground < 32, `!BG_InSpecialJump`, current move `BG_SaberInAttack` and started < 500 ms ago (`PM_AnimLength - torsoTimer < 500`). `PM_SaberJumpAttackMove` (mv:1195): forward 300, up 280, `forceJumpZStart`, free. +40 damage, unblockable. | ours:2730-2758 JKA "red DFA from AttackForMovement" (`velocity[2] > 100`, costs force) or `ST_JK2RDFA` (ours `bg_pmove.c:4484-4522`: **requires attack held**; ours `bg_saber.c:2760-2786`: costs force). |
| **Backstab / back attacks** | mv:1288-1307: back + `PM_CanBackstab()` (mv:1071: box ±15,±15,±8, 128 back, hit `entityNum < MAX_CLIENTS`). Blue → `LS_A_BACKSTAB`; yellow/red → `LS_A_BACK_CR` if ducked or upmove < 0, else `LS_A_BACK`. Free, unblockable, +20 damage. | ours:2862-2885 same move choice, but `PM_CanBackstab` also accepts NPCs and has the easy/easier-backslash options (ours:1593-1687). The staff backflip comes first. |
| View lock during specials | **None in 1.02** (mv `bg_pmove.c:4578-4582`: the lock applies only when `jk2gameplay != VERSION_1_02`). Turning during lunge, DFA and back attacks is free. | locked unless `ST_SPIN*`/`ST_JK2LUNGE` (ours `bg_pmove.c:14739-14757`). Also the `stiffenedUp` movement lock for back attacks, flips and DFA (ours `bg_pmove.c:14278-14320`). |
| Wall flip back while running up a wall | 1.02 variant: in the wall-jump code `forwardmove > 0 && levitation > 1` → `BOTH_WALL_FLIP_BACK1` (mv `bg_pmove.c:1048`). The separate 1.03 "run up wall and flip" block is off in 1.02 (mv:1240). | JKA wall-run/flip code |
| JKA-only (must be off with the cvar) | — | katas, kicks, stab-down, pull impale, roll stab, butterflies/cartwheels, staff/dual jump attacks, long leap, spin attacks |

### 1.7 Blocking, parry, saber-vs-saber

**Who can block (`WP_SaberCanBlock`)**, mv `w_saber.c:4105-4285`, ours `w_saber.c:10206-10308`.

1.02 order of checks:
1. Returns 0 if:
   - in an attack move;
   - in a saber anim with `!saberBlocked` while not in READY/NONE and outside PARRY..REFLECT;
   - (the broken-parry check is skipped in 1.02, mv:4135);
   - holstered, using ATST, weapon not saber, `WEAPON_RAISING`, saber in flight;
   - holding `BUTTON_ATTACK`.
2. **The 1.02 random block table** (mv:4173-4209):
   - `attackStr == 3`: if defence ≥ 3, fail when `Q_irand(1,10) < 3` (20%); otherwise **always fail** (red cannot be blocked below defence 3).
   - `attackStr == 2 && Q_irand(1,10) < 3` (20%): defence 3 → still blocks; defence 2 → fail when `Q_irand(1,10) < 5` (40%); defence < 2 → fail.
   - `attackStr == 1 && defence == 0 && Q_irand(1,40) < 3` → fail.
3. Then: `SaberAttacking` (1.02 = `BG_SaberInAttack` only), `saberMove != READY && !saberBlocking`, `saberBlockTime >= level.time`, `forceHandExtend != NONE`.
4. `blockFactor`: defence 3 **0.05**, 2 **0.6**, 1 **0.9**, 0 → fail. Thrown saber −0.25. **No −0.25 for a saber attack in 1.02** (mv:4270). Then `InFront(point, origin, viewangles, blockFactor)`.
5. **In 1.02 every successful block calls `WP_SaberBlockNonRandom`** (mv:4280 `if (projectile || jk2gameplay == VERSION_1_02)`), which sets the parry quadrant.

Ours: no random table. Instead the `WP_SaberCanBlockSwing` style check or `japp_saberTweaks` chances. It also checks the knocked-away saber (`!saberEntityNum`) and the broken parry, applies the −0.25 for saber attacks, uses 0.3 at defence 3 when `d_saberGhoul2Collision` (default 1, so **0.3**), and only sets the parry for projectiles.

**`WP_SaberBlockNonRandom`**: mv:3956 and ours:9750 are the same algorithm (eye height, rightdot ±0.3 above the eye, ±0.1 between eye and −20, low split by sign).

**Saber hits a body (`CheckSaberDamage_1_02`, mv:1541-1921):**
- Unblockable if the attacker's move is BACK, BACK_CR, BACKSTAB or JUMP_T__B_.
- If the target is a client, the hit is blockable and `WP_SaberCanBlock(target, endpos, 0, MOD_SABER, qfalse, attackStr)` succeeds:
  - `EV_SABER_BLOCK`.
  - If dmg > 5: lock attempt. If the defender's FP_SABERATTACK level is more than 1 above the attacker's and `Q_irand(1,10) < 9` → `WP_SabersCheckLock`; otherwise `Q_irand(1,10) < 3` → lock attempt.
  - If dmg > 5 the attacker bounces: `weaponTime = 0`, `WEAPON_READY`, `saberBlocked = BLOCKED_ATK_BOUNCE`, `saberBlockTime = level.time + 350 - 100*attackerDefLevel`.
  - `saberAttackWound = level.time + 300`.
  - If the attacker is red, dmg > 5 and the defender's move is not READY/NONE: the defender also gets `BLOCKED_ATK_BOUNCE` and the same blockTime formula with the defender's defence.
- Otherwise: `G_Damage` (see 1.9) and `EV_SABER_HIT`, then `saberAttackWound = level.time + 100`.

**Saber hits a saber (clash branch, mv:1813-1918).** Hitting another `CONTENTS_LIGHTSABER` entity:
- Same-team and duel filters. `EV_SABER_BLOCK`. Returns if the other saber is in flight.
- If the attacker is **not red**: the attacker bounces (blockTime as above). If the other player's `weaponTime < 1` or they are not red: `WP_SaberCanBlock(other, …, attackStr=1)`, which in 1.02 sets their parry.
- If the attacker **is red** and the other's defence ≤ the attacker's style level: if the other's `weaponTime < 1` or they are not red and `WP_SaberCanBlock(...,1)` succeeds with dmg > 5, the other player bounces.
- `saberAttackWound = +300`.
- If dmg > 5: lock attempt at `Q_irand(1,10) < 9`.
- If dmg > 5 and the other's defence ≤ the attacker's level: the other bounces, `saberBlockTime` is set on the **attacker** (sic, mv:1913) and `other.saberAttackWound = +300`.

**Ours** (`CheckSaberDamage` ours:4051-5740):
- Blade-vs-blade geometry (`WP_SabersIntersect`, `G_SabCol_*`), `WP_GetSaberDeflectionAngle` (ours:2004) giving bounces **and D1 deflections**.
- `G_KnockawayForParry` knockaways (ours:2276) and `G_PowerLevelForSaberAnim` power contests that produce broken parries.
- `saberCheckKnockdown_*` saber knock-out-of-hand (ours:7139-7448), MB2 branches, SP-style damage.

None of this exists in 1.02.

**Saber entity box:** `SABER_BOX_SIZE` = `(jk2gameplay == VERSION_1_02 ? 8.0f : 16.0f)` (mv `g_local.h:1311`), placed at `boltOrigin + 20*dir` every frame (mv `w_saber.c:3497`, box set at `3614-3615`). Ours: `#define SABER_BOX_SIZE 16.0f` (ours `w_saber.c:29`).

### 1.8 Saber locks

| Part | 1.02 | Ours |
|---|---|---|
| When | `WP_SabersCheckLock` (mv `w_saber.c:698-1029`): `g_saberLocking`; both in a private duel with each other or `GT_TOURNAMENT`; \|Δz\| ≤ 16; both on the ground; dist² 64..6400; no special jump, roll, handExtend or duck; mutual `InFront` 0.4. Then the anim pairs: T→B vs anything = LOCK_TOP; diagonals and L/R against the matching attack/parry anims; `ent->s.number == 0 && BLK_WIDE && weaponTime <= 0` "player" shortcut (an SP leftover); otherwise a random lock at `!Q_irand(0,10)`. **The anim comparisons use the raw `torsoAnim`, including `ANIM_TOGGLEBIT`** (all JK2 versions), so they only match when the toggle bit is clear. | ours `w_saber.c:1532-1957`: JKA rules, including NPCs, power duel off, saber knocked away, and JKA lock anims (`G_SaberLockAnim`, `LOCK_IDEAL_DIST_JKA` 46). |
| Lock anims | `BOTH_BF2LOCK`/`BF1LOCK` (top, ideal distance 32), `BOTH_CCWCIRCLELOCK`/`CWCIRCLELOCK` (ideal 48). Start frame = first + numFrames*0.5. `saberLockTime = level.time + 10000`. `weaponTime = Q_irand(1000,3000)` before pushing is allowed (mv:570-696). | JKA style-specific `BOTH_LK_*` anims and super-breaks |
| Advancing | the server counts new attack presses into `saberLockHits` and every 3 presses sets `saberLockAdvance` (mv `g_active.c:1361-1372`). In pmove each advance moves the frame by `FP_SABERATTACK level + 1` (mv `bg_saber.c:PM_SaberLocked:914-1027`). Pushing the anim past its end wins. The enemy frame mirrors. | JKA `saberLockHits` with `g_saberLockRandomNess` (ours `g_active.c:5040-5075`) and `PM_SaberLocked` (ours `bg_saber.c:1365`) |
| Break | `PM_SaberLockBreak` (mv:783-912): top lock → winner `BOTH_A3_T__B_`/`LS_A_T2B` or `BOTH_K1_S1_T_`/`LS_K1_T_`. Circle lock → the loser gets `LS_H1_BL`/`LS_H1_BR` + `BLOCKED_PARRY_BROKEN`. The loser is **knocked down** (`HANDEXTEND_KNOCKDOWN`, 1100 ms, velocity 320 + 100 up). With no winner both are pushed apart (160 + 150 up). `pm->checkDuelLoss`. | JKA `PM_SaberLockBreak(genemy, victory, strength)` with win/lose anims, super-break (ours:1199) |
| Gesture during lock | allowed in 1.02 (mv `bg_pmove.c:3898`) | — |

### 1.9 Damage

All values are from mv `w_saber.c:CheckSaberDamage_1_02:1617-1697`.

| Item | 1.02 |
|---|---|
| Attack hit (`SaberAttacking` = `BG_SaberInAttack(saberMove)` and `saberAttackWound < level.time`) | level 1: `SABER_HITDAMAGE` **35**, level 2: **60**, level 3: **100**. `attackStr` = style level. |
| Touch damage (start, return, transition, idle, parry, ...) | **5**, at most every **200 ms** (`saberIdleWound = level.time + 200`) |
| Repeat hits in one swing | after a body hit `saberAttackWound = level.time + 100` → **hits again every 100 ms** while the blade stays in contact. After a block or clash: +300 ms. |
| Jedi Master | ×2 when dmg > 5 |
| Unblockable bonus | BACK / BACK_CR / BACKSTAB **+20**, JUMP_T__B_ (red DFA) **+40** (after the JM doubling) |
| ATST target | ×0.1 |
| Target without FP_SABERATTACK | ×1.5 when dmg > 5 |
| `g_saberDamageScale` | **not applied in 1.02** (only in the 1.03+ `CheckSaberDamage`, mv:2186) |
| `G_GetAttackDamage` ramp | **not used in 1.02** |
| Knockback | `G_Damage` (mv `g_combat.c:3104-3165`): `knockback = damage` (cap 200), mass 200, `kvel = dir * g_knockback * knockback / 200`. In 1.02 the `g_saberDmgVelocityScale` factor is **not** applied to MOD_SABER (mv:3132), and `pm_time = clamp(2*knockback, 50, 200)` with `PMF_TIME_KNOCKBACK` (mv:3150). With `g_knockback` 1000 a red hit pushes about 500 u/s. |
| Protect | 1.02 plays the protect sound on every hit (no debounce, mv:3373-3382). Amounts are the same. |
| Dismemberment | cosmetic 1.02 differences only: limb box ±3 instead of 6/9, random spin, no extra up velocity, no wrist sparks (mv `g_combat.c:2589-2734`). There is no gameplay effect. |

Ours: per-stance tables in `CheckSaberDamage` (ours:4380-4650) with `G_GetAttackDamage` ramps (ours:2304), `g_*DamageScale` cvars, SP-style damage modes, JA+ damage, `g_saberDmgDelay_*` (ours `g_xcvar.h:140,141,209`). Saber knockback is 0 unless the `DAMAGE_SABER_KNOCKBACK*` flags are set (`g_saberDmgVelocityScale` "0", ours `g_combat.c:5161-5260`).

### 1.10 Saber position, traces, server skeleton

| Item | 1.02 (mv `w_saber.c:WP_SaberPositionUpdate:3325-3930`) | Ours (`w_saber.c:8704-9726`) |
|---|---|---|
| Blade | bolt 0 of ghoul2 instance 1, `VectorMA(boltOrigin, 40, boltAngles, end)` (mv:3488) | per saber/blade `muzzlePoint` + `lengthMax`, `modelScale`, up to 2 sabers × N blades |
| Origin prediction | `properOrigin += normalize(vel) * (|vx|+|vy|+|vz|)*0.08` (mv:3410-3442) | JKA equivalent (check) |
| Trace method | `g_saberInterpolate` (mv default **1**): the 1.02 branch skips the "1 = advanced" method (mv:3651) and uses the "old plain method": `CheckSaberDamage(..., qfalse)`, then if no hit `(..., qtrue)` (mv:3808-3814). With 0 there is a single plain trace. `CheckSaberDamage_1_02`: plain `trap_Trace` line (no mins/maxs) with mask `MASK_PLAYERSOLID|CONTENTS_LIGHTSABER`; the "interpolate" variant traces short segments 8, 9, 17, 25, 33 units behind the hilt (mv:1556-1610). | `d_saberInterpolate` default **0** → `G_SPSaberDamageTraceLerped` unless `ST_NO_MP_SABERLERP` (ours:9675-9682). Box traces `d_saberBoxTraceSize`, ghoul2 collision `d_saberGhoul2Collision` default 1. |
| Ghoul2 collision | never (`G_G2TraceCollide` returns false for `jk2version == VERSION_1_02`; the 1.02 damage function does not call it) | on by default |
| Server torso bone | `upper_lumbar` for torso anims and lock frames in 1.02 (mv:3844, 3895) | `lower_lumbar` (ours `g_client.c:3530, 3623`) |
| Server spine angles | `G_G2ClientSpineAngles_1_02` (mv:180-272) and in `G_G2PlayerAngles` the 1.02 branch: angles from `viewangles` with pitch 0 instead of `legsAngles`, plus the torso multipliers 0.3/0.3/0.4 on yaw/pitch/roll (mv:478-503) | JKA `G_G2PlayerAngles` (ours:967) |
| Server transition anim speed | `BG_SaberStartTransAnim` applied to the server torso anim (mv:3879) | applied (plus saber animSpeedScale) |
| `lastSaberBase_Always` storage | skipped in 1.02 (mv:3479). It is only used by the 1.03+ deflection code. | — |
| Saber lock idle sparks | `EV_SABER_BLOCK` every `Q_irand(400,600)` ms during a lock (mv:3620-3632) | JKA |

### 1.11 Saber throw

mvsdk throw code has no 1.02 branches except two:
- the blocked thrown saber does **not** call `WP_SaberBlockNonRandom` in 1.02 (mv `w_saber.c:2739`). In 1.02 `WP_SaberCanBlock` calls it anyway, so the defender still parries.
- `bolt_Head` bookkeeping, which mvsdk marks as having no gameplay effect.

JK2 values:
- `SABER_THROWN_HIT_DAMAGE` 30, `SABER_THROWN_RETURN_HIT_DAMAGE` 5, `MIN_SABER_SLICE_DISTANCE` 50, `MIN_SABER_SLICE_RETURN_DISTANCE` 30, `SABER_MAX_THROW_DISTANCE` 700 × FP_SABERTHROW level.
- Speed 400 out (mv:3576), 500 when steering at level ≥ 2. `saberAttackWound + 500` per hit. Box ±24/±8 (mv:3566-3567).
- `saberThrowDelay` 500. Throw cost `forcePowerNeeded[level][FP_SABERTHROW]` = 20 at every level in both games.
- A blocked thrown saber returns to its owner (`thrownSaberTouch`). It is **never knocked out of hand or dropped**.

Ours: the same #defines (ours `w_saber.c:6353-6358, 7648`), but adds JKA's `saberKnockOutOfHand`, `saberKnockDown`, `DownedSaberThink`, `saberReactivate` and the MB2 throw block (ours:6419). In 1.02 saber throw is also allowed during a private duel (mv `bg_misc.c:1335`).

### 1.12 Force interactions relevant to the saber

| Item | 1.02 | Ours |
|---|---|---|
| Saber defence level | used only in `WP_SaberCanBlock` (random table + blockFactor) and in `saberBlockTime = 350 - 100*def` | JKA uses it in many places (parry debounce `bg_parryDebounce`, power contests, missile block) |
| Saber offence level | allowed styles (cycle up to the level); lock push strength (`level+1` frames); lock-trigger bias (`defender.FP_SABERATTACK - attacker > 1`) | JKA power levels |
| Force point allocation | 1.02: if FP_SABERATTACK < 1 then FP_SABERDEFEND and FP_SABERTHROW are forced to 0 (mv `bg_misc.c:403-407`) | — |
| Push knockdown | level-3 push against a weaker push level knocks down at distance ≤ 128 for 1100 ms (mv `w_force.c:3106-3112`, the 1.02/1.03 rule) | JKA/jaPRO rules |
| Grip | 1.02: the gripper is **not** slowed (the 0.4 is 1.03+, mv `bg_pmove.c:4284`); grip drain differs (mv `w_force.c:3760`) | ×0.4 or ×0.8 (`FT_FASTGRIP`) |
| Absorb/heal/drain numbers | 1.02 table `forcePowerNeeded_1_02` (mv `bg_pmove.c:135-238`); absorb debounce 300 vs 600 (mv `w_force.c:3897`); team heal 50/25/10 (mv `w_force.c:1036-1056`); drain cost 1 (mv:2031) | these are force-system changes, not saber. **Outside the scope of this cvar** unless you decide otherwise. |
| Missile block/reflect | same structure: one projectile per `saberBlockTime`, defence level −1 when jumping or running back; deflect at level 2, reflect at level 3 (mv `g_missile.c:370-420` vs ours `g_missile.c:628-676`). There is **no** `WP_SaberStartMissileBlockCheck` pre-block in JK2. | ours runs `WP_SaberStartMissileBlockCheck` every frame (ours `g_main.c:4253, 4320`) |
| Kick-flip knockdown | 1.02 always allows the 30% knockdown on the kicked player, even a red attacker mid-swing (mv `g_active.c:1622`) | JKA |

### 1.13 Movement during swings (pmove)

| Rule | 1.02 | Ours |
|---|---|---|
| Back-running ×0.75 | no (1.04 only, mv `bg_pmove.c:4279`) | ×0.75 unless `JK2SWINGS`, `ST_ALLOW_ROLLCANCEL`, racemode or movement style (ours:12098-12107) |
| Attacking while running backwards | blue ×0.75, yellow ×0.60, red ×0.45 | same (+staff/dual 0.60) |
| Spinning saber anim (legs) | ×0.5 for all styles (red ×0.3 is 1.03+, mv:4347) | red ×0.3 unless `JK2SWINGS` |
| Attacking while running | yellow ×0.85, red **×0.70** (mv:4364) | red ×0.55 unless `JK2SWINGS` |
| Red in a transition | no slowdown (mv:4371 is 1.03+) | ×0.6 forward / ×0.4 back unless `JK2SWINGS` |
| Force speed | ramp `forceSpeedSmash` 1.2 → `forceSpeedLevels[level]`, +0.005 per frame (all JK2 versions) | flat ×1.7 (or ×2.2 with combo) |
| Roll during an attack start | allowed in 1.02 (mv `bg_pmove.c:1921`); not during an attack, special attack or spinning anim | blocked during start unless `ST_ALLOW_ROLLCANCEL` (ours `bg_pmove.c:6274-6289`) |
| Roll speed | `legsTimer/1.5` (back `/2.5`), cap 600, needs speed > 200 (mv:4380-4395) | `GetFixRoll` variants (ours:12227-12300) |
| Jumping while attacking | allowed; it triggers the special jump attacks (1.6) | JKA has its own jump code, jetpack, wall runs, etc. |
| Jump when in the air | 1.02 does not reject `upmove < 10` while airborne (mv:982) and has the wall-run jump special case (mv:967-974) | JKA |
| Choke float anim | 1.02 differs (mv:2236-2246) | — |
| Crouch/run anim restarts | 1.02 re-sets the legs anim every frame without the `!= current` guards (mv:2617-2798, cosmetic) | — |
| Talk while moving | `BUTTON_TALK` does not stop 1.02 clients (engine-protocol based, mv:4546) | — |

### 1.14 Other 1.02-specific quirks

- **ANIM_TOGGLEBIT quirk:** in 1.02 `BG_FlippingAnim` and `BG_SpinningSaberAnim` compare the anim **including** the toggle bit (mv `bg_panimate.c:117, 154`). When called with `ps->legsAnim`/`ps->torsoAnim` (speed rule, roll check, set-move body parts, server spine angles) they return false whenever the bit is set. JKA has no toggle bit in `torsoAnim`/`legsAnim`. It has `torsoFlip`/`legsFlip`, but those change only when the **same** anim restarts (ours `bg_panimate.c:BG_StartLegsAnim:2720`, `BG_StartTorsoAnim:2793`), whereas JK2 flips on **every** start (mv `bg_panimate.c:925, 990`). Exact emulation needs our own toggle tracking (see 3.6 and 4).
- **`PM_SetAnim` in 1.02** adds RESTART for special jumps and refuses to change anims during a roll (mv:1199-1209). Ours has both commented out (`bg_panimate.c:3146-3159`).
- **1.02 cgame torso split** is `upper_lumbar` (mv `cgame/cg_players.c:1652`), with no torso/legs frame sync (1645) and 1.02 spine angles (2852, 2877).
- Folklore items in the brief:
  - "yellow DFA" and "saber lock" are covered above.
  - "fast backslash" has **no dedicated code** in mvsdk. In 1.02 the back attack has no view lock, a timer 2 frames shorter than the full anim, and is free and unblockable, which is probably what the name refers to.

### 1.15 Existing jaPRO options compared with real 1.02

| Option | What it does | Differences from 1.02 |
|---|---|---|
| `ST_JK2_DMGSYSTEM` (`g_local.h:271`, used in `w_saber.c:3920`, `4531-4641`, `5136`) | flat damages, 100 ms rehit, no ghoul2 collision | values: blue **20** (1.02: 35), red DBS **140** (1.02: 120), yellow back/DBS **140** (1.02: 80), red DFA **120** (1.02: 140), blue lunge **40** (1.02: 35), blue backstab **25** (1.02: 55). Correct: yellow 60, red 100, red back 120, yellow flip 60. Still uses JKA blocking, deflections, knockaways and broken parries. |
| `ST_NO_REDCHAIN` → `JK2SWINGS` (`bg_local.h:123-125`) | 1.02 levelling, red kata stops after 1, 1.02 speed factors, transition speed skip | the red rule is not the 1.02 `> irand(0,1)`, yellow/blue kata rules are 1.04, timer is (n-1) instead of (n-2), the pointer bug noted in 1.4 |
| `ST_JK2RDFA` (`bg_pmove.c:4484`, `bg_saber.c:2733,2762`) | red DFA from a jump during an attack | needs attack held (1.02 does not); the `AttackForMovement` variant costs force and needs ground distance > 0 |
| `ST_JK2LUNGE` (`bg_saber.c:2806`, `bg_pmove.c:14745`) | air lunge + turning during the lunge | 1.02 uses one lunge path (ground or air, ducked) and it is free |
| `ST_FIXYELLOWDFA` | forward 50, no spin | 1.02 also adds zDiff, needs someone in front, is free |
| `ST_ALLOW_ROLLCANCEL` | roll during a start, no back-run slowdown | close to 1.02 for those two rules |
| `ST_SPINREDDFA`/`ST_SPINBACKSLASH` | no view lock | 1.02 has no view lock for any special, including the lunge |

### 1.16 MB2 manual-block interaction points

- pmove guard: `bg_pmove.c:14170-14200` (alt attack held = guard, `userInt3`, removes `BUTTON_ATTACK` while guarding).
- Damage: `w_saber.c:4983-4989` (`G_MB2SaberBlock` replaces `WP_SaberCanBlock`), clash `5193`, thrown saber `6419`.
- Implementation: `w_saber.c:9978-10204`. Bots: `ai_main.c:760, 1679, 1771-1810`. cgame HUD/prediction: `cg_draw.c:10341, 11610`, `cg_servercmds.c:251`. Cloak exception: `g_main.c:4198`.
- **Conflict:** in 1.02 alt attack is saber throw and blocking is automatic. Recommendation: when `g_jk2_102sabersystem` is on, MB2 is ignored (`MB2BLOCK()` returns false and `g_mb2manualblock` checks are skipped). Print a warning if both are set.

---

## 2. Assets

**Animations used by the 1.02 moves:**
- `BOTH_A1..A3_*` (7 attacks per level), `BOTH_S1..S3_S1_*` (starts), `BOTH_R1..R3_*_S1` (returns).
- `BOTH_T1_*` (42 transitions; T2/T3 are never used for chains in 1.02).
- `BOTH_B1..B3_*` (bounces), `BOTH_D1..D3_*` (deflections, which 1.02 never triggers), `BOTH_V1..V3_*`, `BOTH_H1..H3_*` (broken parries after a lock loss), `BOTH_K1..K3_*` (knockaways; in 1.02 only the lock top-win uses `BOTH_K1_S1_T_`), `BOTH_P1_S1_*` (parries and reflects).
- Specials: `BOTH_A2_STABBACK1, BOTH_ATTACK_BACK, BOTH_CROUCHATTACKBACK1, BOTH_LUNGE2_B__T_, BOTH_FORCELEAP2_T__B_, BOTH_JUMPFLIPSTABDOWN, BOTH_JUMPFLIPSLASHDOWN1`.
- Stances: `BOTH_STAND1, BOTH_STAND2, BOTH_SABERFAST_STANCE, BOTH_SABERSLOW_STANCE, BOTH_STAND1TO2, BOTH_STAND2TO1`.
- Locks: `BOTH_BF1LOCK, BOTH_BF2LOCK, BOTH_CWCIRCLELOCK, BOTH_CCWCIRCLELOCK, BOTH_CWCIRCLEBREAK, BOTH_CCWCIRCLEBREAK`.
- Other: `BOTH_SABERPULL`, `BOTH_ROLL_*`.

**Results of comparing animation.cfg** (fields: frame count, loop frame, fps; target frame ignored because the .gla files are laid out differently):

| Comparison | Same | Different |
|---|---|---|
| JK2 vs vanilla JKA, all leveled saber sets (A/S/R/T/B/D/V/H/K levels 1-3, P1) | 257 | 0 |
| JK2 vs vanilla JKA, specials/stances/locks/rolls/pull | 84 | 0 (4 non-saber JK2 sequences are missing in JKA) |
| JK2 vs **our loaded `nicjk/japro-assets.pk3`**, all of the above | 280 | **2**: `BOTH_SABERFAST_STANCE` (JK2 2 frames, loop -1, 60 fps; ours 1 frame, loop 1, 30 fps), `BOTH_STAND2` (JK2 2 frames, loop 0, 20 fps; ours 1 frame, loop 1, 30 fps) |
| vanilla JKA vs our loaded cfg | 1394 | 13 (none used by 1.02 saber moves except the two stances; the others are FLIP_F, FORCEJUMP1, FORCELAND1, LAND1, SABERDUAL_STANCE, T5_*) |

- The JKA `animation.cfg` row order differs from JK2's. That is irrelevant because the code looks anims up by name or enum. Our `anims.h` enum ranges used by the 1.02 code (`SABER_ANIM_GROUP_SIZE = BOTH_A2_T__B_ - BOTH_A1_T__B_`, `BOTH_T1_BR__R..BOTH_T1_BL_TL`, `BOTH_P1_S1_T_` offsets) are laid out the same way as in JK2.
- Timing (frames × lerp) is therefore reproducible exactly from our current assets, apart from the two stance anims. In 1.02 the ready move holds the torso for the stance length: JK2 blue 32 ms, yellow 100 ms; ours 33 ms and 33 ms.

**What cannot be checked or matched from these files alone:**
1. **Bone data.** The JKA .gla (11.8 MB vanilla, 17.7 MB in our `japro-assets.pk3`) was re-exported, and ours was also modified by the user (the archive has several "Niksata" humanoid variants). Frame counts match, but whether each frame's pose (and so the hand/saber bolt path) is the same as JK2's 9.98 MB .gla was **not** verified. Saber hit detection depends on that path. JK2's `_humanoid.gla` is available at `Jedi Outcast\GameData\base\assets0.pk3` (a copy is also inside the test install's `base\0-assets0.pk3`, where JKA's `assets1.pk3` overrides it).
2. **Skeleton split.** 1.02 splits the torso at `upper_lumbar`. JKA's skeleton has that bone, but JKA anims were authored for the `lower_lumbar` split. Using upper_lumbar with JKA anims is possible, but the blend at the waist may look different than in JK2.
3. **Saber model.** JK2 uses one fixed hilt (`models/weapons2/saber/saber_w.glm`, bolt 0) and length 40. JKA hilts come from `.sab` files with their own bolt (`*blade1`) position, and our players use custom hilts.

**Options:**
- (A) **Recommended first:** use the current JKA/custom .gla and the same timings. All gameplay rules are exact. Pose paths are "JKA/custom" and only approximately JK2.
- (B) Write a small offline tool that decompresses the frames of the 281 sequences from both .gla files and compares the bone matrices of the hand/saber chain. That tells us whether (A) is already pose-exact.
- (C) If they differ, ship a JK2-pose saber animation set. JK2's .gla cannot be loaded by JKA's skeleton directly (different bone count and version). It would have to be retargeted with the GLA tools in the archive (`gla_merge`, `JKA_Studio-gla-animations`) into a new `_humanoid` set, either as new sequences used only in 1.02 mode or by replacing the level-1-3 sequences. Redistributing JK2 assets also has licensing implications.
- For the hilt: in 1.02 mode force blade length 40 and take the muzzle from blade 0 of saber 1. Optionally force the stock JKA single hilt for exact bolt placement.

---

## 3. Porting plan

Principle: **separate code paths, chosen once per call**, instead of hundreds of inline `if`s through JKA logic. With the cvar at 0 none of the new code runs, so nothing changes.

### 3.1 The cvar and how the client learns it

- `g_xcvar.h`: `XCVAR_DEF( g_jk2_102sabersystem, "0", NULL, CVAR_SERVERINFO|CVAR_ARCHIVE|CVAR_LATCH, qtrue )`. Latching to map restart is advised, because swapping it mid-swing would mix states.
- `cgame/cg_local.h`: `int jk2_102sabersystem;` next to `mb2manualblock` (cg_local.h:2379). `cgame/cg_servercmds.c:251` area: `cgs.jk2_102sabersystem = atoi(Info_ValueForKey(info, "g_jk2_102sabersystem"));`.
- `bg_local.h` next to `MB2BLOCK()` (117-121): `#define JK2SABER() ( g_jk2_102sabersystem.integer != 0 )` for game and `( cgs.jk2_102sabersystem != 0 )` for cgame.
- **Networking: no new netfields needed.** Every field the 1.02 code uses already exists and is sent in JKA:
  - `saberMove` 32, `saberBlocked` 8, `saberAttackChainCount` 4, `saberLockTime/Frame/Enemy/Advance`, `torsoTimer` 16, `fd.saberAnimLevel` 4, `saberHolstered` 2, `torsoFlip/legsFlip` 1 (qcommon `msg.cpp:1338-1462`).
  - `saberBlocking`, `saberIdleWound`, `saberAttackWound`, `saberBlockTime` and `saberLockHits` are server-only in both games.
  - Note: `saberAttackChainCount` is clamped to 16 but sent in 4 bits, so 16 wraps to 0 on the client. This already happens in JKA and probably in JK2 too (check).

### 3.2 New file `codemp/game/bg_saber_jk2.c` (game + cgame; add to both CMakeLists)

Port verbatim from mv `bg_saber.c`, taking only the 1.02 branches:
- `PM_SaberAnimTransitionAnim_JK2` (mv:371-525 with the 1.02 breaks)
- `PM_SaberKataDone_1_02` (697)
- `PM_SaberAttackForMovement_JK2` (1229-1345; lunge, flip, backstab with the client-only `PM_CanBackstab_JK2`, `PM_SomeoneInFront`)
- `PM_SaberFlipOverAttackMove_JK2` (1098, with zDiff via `PM_BGEntForNum`/`bgClients`)
- `PM_SaberLungeAttackMove_JK2` (1181), `PM_SaberJumpAttackMove_JK2` (1195)
- `PM_SaberLocked_JK2` (914), `PM_SaberLockBreak_JK2` (783)
- `PM_WeaponLightsaber_JK2` (1356-1941), `PM_SetSaberMove_JK2` (1943-2082)

Adaptation notes:
- `ANIM_TOGGLEBIT` masks become plain comparisons. `PM_SetAnim` takes 3 args in JKA (no blendTime).
- `saberActive` → `!saberHolstered` / `BG_SabersOff`. `bgGlobalAnimations` → `pm->animations`.
- `pm->bgClients[n]` → `PM_BGEntForNum(n)->playerState`.
- The `Q_irand` calls at mv:906, 996, 1011, 1143 stay `Q_irand` for exactness (they mispredict in 1.02 too). Alternative: `PM_irand_timesync`. **Decide** (section 4).
- Parry LR/LL anims: helper `JK2_MoveAnim(move)` that returns the unfixed `_BL`/`_BR` anims no matter what `g_fixSaberMoveData` says.

Small helpers with 1.02 semantics: `BG_SaberInAttack_JK2`, `BG_SaberInSpecial_JK2`, `BG_SaberInSpecialAttack_JK2`, `PM_SaberInBrokenParry_JK2`, `PM_GetSaberStance_JK2`. In 1.02 mode the JKA-only moves cannot happen, so the JKA versions give the same answer for JK2 moves. They still differ on V1 for broken parry, so use the `_JK2` helpers inside the JK2 path.

### 3.3 Changes in existing shared files (each gated by `JK2SABER()`)

- `bg_pmove.c:10400` (`PM_Weapon`): `if (JK2SABER() && pm->ps->weapon == WP_SABER) PM_WeaponLightsaber_JK2(); else PM_WeaponLightsaber();`.
- `bg_pmove.c:PM_CheckJump:3348`: the JK2 jump-attack block (mv:1293-1345: yellow flip with someone in front, red jump-hack without needing attack held, 500 ms window). Disable the JKA jump attacks (`ST_JK2RDFA` block at 4484) and the JKA wall-run-flip / 1.03 run-up-wall variants. Use the 1.02 wall-flip-back rule (mv:1048).
- `bg_pmove.c:BG_AdjustClientSpeed:12065`: a JK2 branch with the 1.02 factors from 1.13. The 1.02 force-speed ramp and grip-no-slow belong here only if force rules are in scope.
- `bg_pmove.c:PM_TryRoll:6249`: 1.02 rule (no block on start) and the 1.02 roll speed in `BG_AdjustClientSpeed`.
- `bg_pmove.c:PmoveSingle:14270-14320, 14739-14757`: no view lock and no `stiffenedUp` for JK2 specials in 1.02 mode.
- `bg_panimate.c:BG_SetAnimFinal:2944`: 1.02 timers (torso `(n-2)*lerp-1`, legs `(n-3)*lerp-1`, no speed scaling, rage/speed legs divisors on every held legs anim).
- `bg_panimate.c:BG_SetAnim:3125`: 1.02 RESTART for special jumps and the roll guard.
- `bg_panimate.c:BG_SaberStartTransAnim:2860`: JK2 mode = only the T1/T2/T3 1.5/0.75 rule (no saber animSpeedScale, no broken limbs), used **only** by the server ghoul2 torso (3.4). The pmove timer and the cgame do not use it.
- `bg_panimate.c` toggle emulation (only if exact `BG_SpinningSaberAnim`/`BG_FlippingAnim` behaviour is wanted): in JK2 mode flip `torsoFlip`/`legsFlip` on **every** anim start, and give the JK2 copies of those two functions a `flip` argument that returns false when the flip is set. This changes no netfields. The cgame already treats a flip change as a restart, and a new anim restarts anyway. **Needs testing.**
- `bg_misc.c` force point validation: 1.02 rule "no saber attack → no defence/throw" (mv `bg_misc.c:403`), and allow throw in duels (mv:1335).
- `bg_saber.c`: the `BG_FixSaberMoveData` callers stay as they are; the JK2 path uses its own anim helper.

### 3.4 Server only

New file `codemp/game/w_saber_jk2.c`:
- `CheckSaberDamage_JK2(self, start, end, doInterpolate)`: verbatim port of mv `CheckSaberDamage_1_02:1541-1921`.
  - Use the real `G_Damage`. Fill the JKA tempent fields: `te->s.weapon = 0` (saberNum), `te->s.legsAnim = 0` (bladeNum).
  - Keep duel/team filters. Keep `g_friendlySaber`, or our equivalent if renamed.
- `WP_SaberCanBlock_JK2` (mv:4105-4285, 1.02 path). Call our existing `WP_SaberBlockNonRandom` (same algorithm).
- `WP_SabersCheckLock_JK2`/`WP_SabersCheckLock2_JK2` (mv:570-1029, JK2 lock anims, distances 32/48).
- `G_G2ClientSpineAngles_1_02` + the 1.02 part of `G_G2PlayerAngles` (mv:180-272, 478-503).

`w_saber.c:WP_SaberPositionUpdate:8704`: in JK2 mode:
- one blade only, length 40, saber entity box ±8 at +20;
- `g_saberInterpolate`-style "plain" double trace calling `CheckSaberDamage_JK2` (treat `d_saberInterpolate` 0 as "plain" or add `g_jk2_102interpolate` default 1 = JK2 default; **decide**);
- no ghoul2 collision, no SP lerp, no `WP_SaberStartMissileBlockCheck`, no MB2.
- Sabers: force the single saber. With the cvar on, the server forces saber 2 off and refuses staff/dual styles (dual/staff players get their first saber as a single blade). That matches "JK2 has no staff/dual". Alternative: allow the hilts but treat them as single blades.

Other server files:
- `g_client.c:3530, 3623` (server torso anim): `upper_lumbar` in JK2 mode, plus the server transition speed from mv:3879.
- `g_combat.c:G_Damage:5117-5260`: JK2 mode skips the `g_saberDmgVelocityScale`/knockback-flag logic for MOD_SABER (plain knockback, `pm_time` rule). 1.02 protect sound without debounce (optional).
- `g_active.c:5040-5075` (lock hits): the 1.02 rule from mv `g_active.c:1361-1372` (3 new presses → advance).
- `g_active.c` kick-flip knockdown (1.02 always): optional.
- `g_cmds.c:Cmd_SaberAttackCycle_f:3902`: in JK2 mode cycle only blue→yellow→red, limited by `FP_SABERATTACK`, with `saberCycleQueue` while `weaponTime > 0` (as JK2). No Desann/Tavion/dual/staff.
- Saber throw (`w_saber.c:6353-7790`): in JK2 mode never knock the saber out of hand or drop it (skip `saberKnockOutOfHand`, `saberKnockDown`, `saberCheckKnockdown_*`). Use the JK2 `CheckThrownSaberDamaged`/`saberFirstThrown`/`saberBackToOwner` logic (ported or gated).
- `g_missile.c`: same block rules. Just skip `WP_SaberStartMissileBlockCheck` in JK2 mode.
- `g_main.c` / `g_cvar.c`: warn and ignore MB2 when both cvars are on. JK2 mode also ignores `g_tweakSaber` saber bits, `japp_saberTweaks`, `d_saberSPStyleDamage`, `g_*DamageScale`, `g_saberDmgDelay_*` (they do not apply on the JK2 path).

### 3.5 cgame only

- `cg_players.c:3670`: skip `BG_SaberStartTransAnim` for the visual speed in JK2 mode (mv `cg_players.c:1615`).
- `cg_players.c:3720` and similar torso `SetBoneAnim` calls: `upper_lumbar` in JK2 mode. Also the 1.02 spine angles in the cgame equivalent of mv `cg_players.c:2852-2877`, and no torso/legs frame sync (mv:1645).
- Saber rendering: single blade, length 40, and the trail. Visual only, but the blade should match the server's 40.
- HUD: hide MB2 block points in JK2 mode.

### 3.6 Bots (`ai_main.c`), required by the plan

- Stance choice: only `SS_FAST/MEDIUM/STRONG` in JK2 mode (style evaluation at ai_main.c:730-792, 11615, 11957, 12064, 12533, 12745-12790).
- Specials: red DFA = jump within 500 ms of starting an attack while moving forward. Yellow DFA = jump attack when the enemy is within 200 units in front. Lunge = crouch + forward + attack with blue (also in the air). Back attack when the enemy is within 128 units behind. Remove kata, kick and staff/dual sequences (`BOTSEQ_*`, ai_main.c:2241) in JK2 mode.
- Defence: in 1.02 blocking is automatic but **not while holding attack** (mv:4160). Bots should release attack when they need to block, and know that red cannot be blocked below defence 3.
- Chain rules: red chains at most 1-2 attacks, yellow 3-6, blue without limit.
- Turn off the MB2 bot code when JK2 mode is on.

### 3.7 Rough size

- `bg_saber_jk2.c` about 1,300 lines (mostly a direct port).
- `w_saber_jk2.c` about 1,000 lines (damage 380, block 180, locks 460, spine 100).
- Hooks in about 14 existing files, about 300-400 lines.
- Bots about 300-500 lines.
- cgame about 100 lines.
- Total about **3,000 lines**, mostly ported, plus testing. A pose-exact .gla (option B/C) is a separate asset project.

---

## 4. Uncertain / needs testing

1. **mvsdk's 1.02 is a reconstruction.** Where mvsdk gates code by `jk2gameplay`, it assumes the reverse-engineered behaviour (for example its comment at mv `w_saber.c:3479` "I do not know for sure..."). Treat mvsdk as the reference, as the brief says.
2. **Server transition speed in 1.02** (mv:3879 applies `BG_SaberStartTransAnim` to the server ghoul2 torso, while the client shows 1×). It is reproduced as written, but it is unclear whether original 1.02 behaved like this.
3. **Pose data in the .gla** (section 2 B). Not verified; it decides whether hit paths are exact.
4. **upper_lumbar split with JKA anims**: visual blending and the effect on the saber path.
5. **Toggle-bit emulation** (1.14): whether flipping `torsoFlip/legsFlip` on every start causes visible anim restarts or prediction issues in our cgame, and whether JK2's starting toggle state at spawn matters.
6. **`Q_irand` vs `PM_irand_timesync`** for flip stab/slash and lock events. `Q_irand` is exact but mispredicts on the client.
7. **Interpolate default:** JK2's `g_saberInterpolate` default is 1 (= "plain" double trace in 1.02). Our `d_saberInterpolate` is 0 and `CVAR_CHEAT`.
8. **Hilt bolt and length:** blade length 40 with JKA/custom hilts; whether forcing the stock hilt is needed.
9. **`saberAttackChainCount` 4-bit wrap at 16** (prediction only; it is reset at ready).
10. **Engine:** the 1.02 damage path is designed for `sv_fps 20`/50 ms frames (100 ms rehit, 200 ms idle). If our servers run at a higher sv_fps, the server-side position and trace sampling differs from JK2. Check the server frame rate.
11. **Bot behaviour** in the 1.02 block rules, especially "not holding attack while blocking".
12. **The `ent->s.number == 0` lock shortcut** in `WP_SabersCheckLock` (an SP leftover in all JK2 versions): keep it for exactness? It favours client 0.
13. **Stance anims** `BOTH_SABERFAST_STANCE`/`BOTH_STAND2` length differ from JK2 (32/100 ms vs 33/33 ms). This only affects the ready-hold torso timer. Can be matched by hard-coding the JK2 values in JK2 mode, if wanted.
14. **Force-system 1.02 changes** (speed ramp, grip, absorb, push distance, force point rules) are listed in 1.12 but kept **out of scope**. Decide whether "1.02 saber gameplay" includes them.
15. **Missile reflection** looks the same; not tested.
