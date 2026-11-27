# JK2 1.02 force powers, movement, weapons and match rules vs our JKA fork: porting map for `g_jk2_102sabersystem`

Analysis only. No code was changed. Written 2026-11-27. This is the companion to `JK2_102_COMPARISON.md`, which covers the saber. Saber material is only referenced here, not repeated.

## 0. Sources, method and conventions

- **JK2 reference:** `E:\jedi academy modding archive\external_study\mvsdk\code\game` and `code\cgame` (mvsdk `4c7c463`).
  - mvsdk's plain code is JK2 **1.04**. 1.02 is chosen at runtime by `jk2gameplay == VERSION_1_02` / `!= VERSION_1_04` checks, and once or twice by `jk2startversion` (protocol/client compatibility, not gameplay).
  - Data tables are swapped by `MV_SetGamePlay` (mv `bg_multiversion.c:143-170`): `weaponData = weaponData_1_02`, `forcePowerNeeded = forcePowerNeeded_1_02`.
  - **Everything below describes the 1.02 path only.**
- **Our fork:** `E:\jedi academy modding archive\TaystJK_AI_Claude_Code_improvements\TaystJK_AI-Improved-Bots\codemp\game` and `...\codemp\cgame`. `bg_*.c` is built into both game and cgame.
- **Assets compared:**
  - JK2: `E:\SteamLibrary\steamapps\common\Jedi Outcast\GameData\base\assets0/1/2/5.pk3`.
  - Vanilla JKA: `Jedi Academy clean\GameData\Base\assets0-3.pk3`.
  - What our test install loads: `Jedi Academy TaystJK_AI test\GameData\nicjk\japro-assets.pk3`.
- **Reference format:** `file:function:line`. "mv" means mvsdk and "ours" means the fork. Line numbers are from the files as they are today.
- **Defaults assumed for ours** unless a row says otherwise: `g_tweakForce 0`, `g_tweakWeapons 0`, `g_tweakSaber 0`, `g_flipKick 0`, the movement style MV_JKA, no racemode, `g_unlagged 0`, the damage/velocity scale cvars at 1. Three defaults in ours change behaviour against JK2:
  - `d_projectileGhoul2Collision 1` (g_xcvar.h:51)
  - `g_locationBasedDamage 1` (g_xcvar.h:114)
  - `g_startingWeapons 8` (g_xcvar.h:231)
- **mvsdk fidelity limit.** mvsdk is 1.04 source with 1.02 deltas. There are **no** 1.02 checks in mv `g_weapon.c`, `g_missile.c` or `g_items.c`. So for weapons, "1.02 = 1.04 code + `weaponData_1_02`" is mvsdk's assumption. It cannot be proved from this source. mvsdk also deliberately uses 1.03 code for spectator fly and swim anims (mv `bg_pmove.c:1539, 1550, 2633`), so real 1.02 code for those is not available here.

### 0.1 Corrections to `JK2_102_COMPARISON.md`

1. **§1.13/§1.14 "jump in the air" is reversed.**
   - At mv `bg_pmove.c:PM_CheckJump:982`, 1.02 returns when `upmove < 10` whether on the ground **or** in the air. It is 1.04 that rejects this only on the ground.
   - In addition, mv:967-974 returns early in the air unless you are wall-running.
   - Result: in 1.02 the wall-run flip is the **only** special jump available in the air. The jump-attack block (mv:1293, red DFA / yellow flip) can only be reached from the ground.
2. **§1.14 "crouch/run anims re-set every frame" is wrong.**
   - At mv `bg_pmove.c:PM_Footsteps:2606-2806` the `!= current anim` tests are compiled as always false in 1.02, so the code always takes the `PM_ContinueLegsAnim` branch. The OVERRIDE flag is never set either.
   - Result: in 1.02, run/walk/crouch legs anims **never override** saber, landing, pain or stance legs anims. They wait for `legsTimer`. This affects gameplay timing, not only looks.
3. **The force-speed multiplier is a ramp with a cap per level.**
   - mv `bg_pmove.c:BG_AdjustClientSpeed:4289-4301`: `forceSpeedSmash` is clamped to at least 1.2 and at most `forceSpeedLevels[level]` (1.25/1.5/1.75). Speed is multiplied by it, then it grows by 0.005 **per pmove call**.
   - `ForceSpeed` sets it to 2 at activation (mv `w_force.c:1377`), so it starts at the level cap.
   - `PM_WalkMove` resets it to 1 when `|vx|+|vy| < 200` or when standing still (mv:1661-1682, 1790). After that it climbs again from 1.2, at a rate that depends on the client's command rate.

### 0.2 The most important findings

1. **Force costs and amounts differ in a few places:**
   - Heal costs 25 at every rank (ours 65/60/50) and heals **10/25/50** (ours 5/10/25).
   - Drain costs 10 in the table and **1** per shot (ours 20 and 5).
   - Grip has **no** continuous 1-per-100 ms drain.
   - Absorb upkeep is 1 per **300 ms** (ours 600).
   - Push knockdown is L3 only, within **128 units**, for **1100 ms**, and sets `quickerGetup` (ours `64*(diff-1)` and 700 ms).
   - Mind trick L2 is **360°**, and L3 hits **every client in your PVS** with no radius.
   - Team heal/energize have **no** 2000 ms cooldown.
   - Saber throw is **allowed** in private duels.
2. **Force speed is not "1.7 flat".** It is the ramp in 0.1 item 3. It also **stacks with rage** (×1.3, or ×0.75 during rage recovery). Under rage or speed, **every** held legs anim timer is divided by 1.3 or 1.7, so flips, rolls and getups get shorter. Ours does that only for run/walk.
3. **Grip in 1.02:**
   - the gripper is **not slowed**;
   - the victim **keeps attacking** and keeps the saber lit;
   - L3 needs no line of sight;
   - gripping an Absorb user is **allowed** and feeds that user force every frame.
4. **Force regen runs at most once per server frame** (`debounce = level.time + g_forceRegenTime`, with a strict `<`). At sv_fps 20 and the default 200 ms that is **4 points/s**, not the 5/s our catch-up loop gives. Lightning and drain also tick once per frame, not on a fixed 50 ms clock.
5. **Movement:**
   - The constants are identical (accelerate 10, airaccelerate 1, friction 6, g_speed 250, gravity 800, jump 225, force jump table).
   - The differences are in the rules:
     - no in-air special jumps except the wall-run flip;
     - a 1.02-only **ground wall back-flip** (BOTH_WALL_FLIP_BACK1);
     - wall moves trace `MASK_PLAYERSOLID`, so they work off players;
     - no back-running ×0.75;
     - roll start needs no speed;
     - the 1.02 roll speed formula;
     - the full-box crouch stand-up test;
     - `Dot > 0.99` in slidemove;
     - no stepSlideFix;
     - a pmove_msec clamp of 8..33;
     - movement allowed with the console open;
     - the 1.02 getup block;
     - fall damage with no knockdown branch;
     - the 1.02 kick-flip.
6. **Weapons:**
   - The data tables match except for two rows: the Bryar pistol (ours start pistol is JKA's no-charge WP_BRYAR_PISTOL; JK2's pistol is our WP_BRYAR_OLD) and repeater alt ammo (8 in 1.02, 15 ours).
   - The behaviour differences are:
     - stun baton damage 20 (ours 2);
     - medpac +100 (ours +25);
     - trip mine alt is a **2 s timed mine** (ours a proximity mine);
     - the disruptor fires while moving, unzooms on movement, has range 8192 and **no** ×0.5 zoom slow;
     - the rocket is not shootable and always dives within 128 units;
     - the bowcaster speed spread is 910..1690;
     - weapon raise takes 250 ms;
     - bbox (not Ghoul2) projectile collision;
     - **no location-based damage**;
     - the JK2 spawn loadout: saber or stun baton, plus pistol with 100 blaster ammo, the pistol selected.
7. **Match rules:**
   - spawn is 125 HP / 25 armor in **every** gametype, duel included (ours 100/0 in duel);
   - the private-duel winner keeps their armor and has health raised to max (ours sets armor to 25);
   - a duel breaks at 1024 units (ours: no limit by default);
   - only **one** private duel at a time on the server (ours allows many);
   - dismemberment needs `damage >= 20` on a saber kill (ours 5, plus extra post-death and Ghoul2 rules).
8. **Assets are nearly fine.**
   - Vanilla JKA's animation.cfg matches JK2 for every movement, force, knockdown, getup, wall-run, flip, roll, pain and death anim I checked, apart from BOTH_DEATH16 and the surrender anims.
   - Our **custom japro-assets cfg changes FLIP_F, FORCEJUMP1, FORCELAND1 and LAND1**.
   - 110 of the 116 force/weapon sounds and effects that JK2 references by literal path are byte-identical in JKA. Six differ (§5).
9. **Networking:** no new netfields are needed. The **force speed level is not networked** (only `forcePowerLevel[FP_LEVITATION]` and `[FP_SEE]` are). To predict the 1.02 speed ramp exactly, put the level and the smash value in a stat slot that JK2 mode frees (§6.2).

---

## 1. Force powers

### 1.0 Tables and constants

| Item | JK2 1.02 (mv) | Ours | Same? |
|---|---|---|---|
| `forcePowerNeeded` | `forcePowerNeeded_1_02` bg_pmove.c:135. Heal 25/25/25, Drain 10/10/10. Everything else equals the 1.04 table. | bg_pmove.c:140 = 1.04 table: Heal 65/60/50, Drain 20/20/20 | **No** (heal, drain) |
| Readers of the table | BG_ForcePowerDrain bg_saber.c:37, WP_ForcePowerAvailable w_force.c:639, team powers 1189/1266, absorb conversion 2974/3409 | bg_saber.c:70, 3162, 3169, 3561; w_force.c:663, 1383, 1468, 2543, 2580, 2708, 3744, 4369; ai_main.c:18959-18986. Declared `extern int[..][..]` in bg_local.h:69 and w_saber.h:91 | n/a |
| FORCE_POWER_MAX, GRIP_DRAIN_AMOUNT, MAX_GRIP_DISTANCE, MAX_TRICK_DISTANCE, FORCE_LIGHTNING_RADIUS, MAX_DRAIN_DISTANCE | 100, 30, 256, 512, 300, 512 (w_saber.h:1-7) | identical (w_saber.h:51-57) | Yes |
| forceJumpHeight / forceJumpStrength | {32,96,192,384} / {225,420,590,840} (bg_pmove.c:225, 233) | same, plus two jaPRO levels (bg_pmove.c:228, 238) | Yes (levels 0-3) |
| forceSpeedLevels | {1,1.25,1.5,1.75} (bg_pmove.c:39), used at :4295 | declared at bg_pmove.c:132 and **never used** | **No** |
| bgForcePowerCost, forceMasteryPoints, forcePowerMinRank | bg_misc.c:47, :35; w_force.c:55 | bg_misc.c:318, :306; w_force.c:64 | Yes |

### 1.1 Regen, ranks and allocation

| Item | 1.02 | Ours | Same? |
|---|---|---|---|
| Max force | 100 (WP_SpawnInitForcePowers w_force.c:524) | 100 (:453) | Yes |
| Regen amount | +1 per tick; Boon +6; Jedi Master in GT_JEDIMASTER +4; Holocron mode +1 per holocron carried (WP_ForcePowersUpdate w_force.c:4925-4958) | same (:6102-6116) | Yes |
| g_forceRegenTime | "200" (g_main.c:199) | "200" (g_xcvar.h:103) | Yes |
| Regen schedule | At most once per server frame: `if (debounce < level.time)` … `debounce = level.time + g_forceRegenTime` (w_force.c:4918, 4961). At sv_fps 20 that is one point per 250 ms. | Catch-up loop `debounce += g_forceRegenTime` (:6148-6151), so exactly 5/s. Duel, siege, power-duel, racemode and tribes use other intervals (:6119-6146). | **No** |
| Regen allowed when | No powers active, or only Drain active; saber not in flight (:4916-4918) | also not in BG_SaberInSpecial, not MV_SPEED, tribes rules, FT_FIXGRIPPEDREGEN (:6097-6100) | **No** |
| Debounce while a power runs | untouched | reset to level.time every frame (:6217) | **No** |
| forceUsingAdded (Enlightenment) | not reset in WP_InitForcePowers (:493-501); reset at spawn (:574) | reset in WP_InitForcePowers (:428-430) | Edge case |
| g_maxForceRank | default "6"; 0 means 7 (g_main.c:178) | default "7"; ≤0 or ≥8 forced to 7 | Config only (set 6 for exactness) |
| No saber offense → no defense/throw | 1.02-only, applied **before** the freeSaber bump (bg_misc.c:BG_LegalizedForcePowers:403) | always applied, but **after** the freeSaber bump and fpDisabled (bg_misc.c:821) | Differs only when offense is disabled through fpDisabled |
| Saber throw in a private duel | allowed (bg_misc.c:BG_CanUseFPNow:1335) | not allowed (bg_misc.c:1920, 1932) | **No** |
| Bot force strings | taken from the bot file as-is (w_force.c:228) | basejka bot cheat after legalization: push/pull 3, light absorb 3, skill≥4 extra (WP_InitForcePowers:276-314) | **No** |

### 1.2 Each power

**Heal** (mv ForceHeal w_force.c:1028-1058; ours :1215-1246)

| | 1.02 | Ours |
|---|---|---|
| HP L1/L2/L3 | **10 / 25 / 50** | 5 / 10 / 25 |
| Cost | **25** every rank | 65 / 60 / 50 |

**Levitation / force jump**
- Hold-to-rise formula: mv PM_CheckJump:942-945 and ours :3703-3705, same for MV_JKA.
- Drain while airborne: 5 per 300 ms (L2+) or per 200 ms (L1) in mv (:762-772). Ours is the same except **1** in GT_DUEL/POWERDUEL (:3432-3436).
- 1.02 has no `forceJumpZStart` −0.1 nudge (mv:722 is 1.04-only) and does not require a non-zero ZStart to keep rising (mv:818). Ours always nudges (:2216) and requires it (:3536).
- In-air jump rules: see §0.1 item 1 and §2.

**Speed**
- Duration 10/15/20 s, cost 50: same (ours WP_ForcePowerStart :1019-1030).
- Multiplier: mv ramp (§0.1 item 3); ours flat **1.7** (bg_pmove.c:12137-12140).
- Speed and rage: they stack in 1.02 (mv:4303-4310). Ours uses an `else if` chain, so speed blocks rage; FT_FORCECOMBO gives 2.2 instead (:12128-12148).
- legsTimer scaling: 1.02 divides **every** HOLD legs anim by 1.7 (speed) or 1.3 (rage) (mv bg_panimate.c:1176-1183). Ours does this only for run/walk (ours bg_panimate.c:3052-3063).
- Wall-smash damage: `FORCE_VELOCITY_DAMAGE` is 0 in mv, so it is off. The 1.02 step/smash code in mv `bg_slidemove.c:241-361` still changes stepping and bouncing at high force speed (§2).

**Push / pull** (mv ForceThrow w_force.c:2598; ours :3278)

| Item | 1.02 | Ours | Same? |
|---|---|---|---|
| Blocked while forceHandExtend ≠ NONE | always, including during a getup (:2626) | allowed in a getup unless FT_JK2GETUPS (:3306) | **No** |
| weaponTime gate | `weaponTime > 0` (:2636) | `weaponTime - saberDelay`, g_fixGetups and FT_JK2PULLROLL exceptions (:3317-3329) | No |
| Own hand / lockout | Always overwritten. Pull hand 400 ms; push hand 1000 ms. `PW_DISINT_4 = handTime + 200` for both (:2680-2705) | Set only if NONE. Pull 400 (200 in siege), lockout +200; push lockout `level.time + 1100`; adds PW_PULL (:3376-3412) | **No** (push 1200 vs 1100) |
| Radius, arcs, strength, cost | 1024 radius; L1 trace 512; arc 60° (L2) / 180° (L3); dot ≥ 0.6; strength 256 × level; cost 20 | same | Yes |
| L1 target | added with **no** ForcePowerUsableOn check (:2765) | returns if not usable (:3487-3500) | **No** |
| Knocked-down targets | can be pushed or pulled | blocked unless FT_PUSHPULLKD (ForcePowerUsableOn :631-635) | **No** |
| Teammates | always skipped (:2856) | pushed when g_friendlyFire is on (:3609) | Default same |
| Line of sight | from origin only (:2953) | retries from the eye (:3716-3727) | **No** |
| Counter-push (CanCounterThrow) | fails if hand busy, weaponTime > 0, PW_DISINT_4 active, power unusable, or airborne (:2512-2556) | adds siege facing; weaponTime > 0 returns −1 for guns; charging a weapon returns −1 (:3119-3190, 3866-3870) | **No** |
| Moving target −1 defence level; power-difference reduction 0.2/0.4/0.8; weapon pull within 256 at 30/70/100% | :3000-3092 | same by default | Yes |
| **Knockdown** | L3 only, mod > other, **dirLen ≤ 128**, handExtendTime **+1100**, `quickerGetup = qtrue` (:3099-3113) | `dirLen ≤ 64*((mod-other)-1)`, +700; FT_JK2KNOCKDOWN gives 128 but still +700; needs BG_KnockDownable (:3918-3932) | **No** |
| Missiles | push reflects (G_ReflectMissile), pull does nothing (:3169-3178) | same (+ racemode exception) | Yes |
| Thrown / dropped saber | flying saber is ET_GENERAL and unaffected; a dropped saber is ET_MISSILE + TR_GRAVITY, so push reflects it | same | Yes |
| Push in a saber lock | +1500 ms, lockHits += 2 × level (:2663-2672) | same (:3357-3366) | Yes |
| Bots | must release the button | the push release check is skipped for bots (WP_DoSpecificPower :5099) | **No** |

**Mind trick** (mv ForceTelepathy w_force.c:2290-2430)
- Duration 20/25/30 s: same.
- L1: trace 256, same.
- L2: mv **360°** within a 512 box (:2309-2312); ours **180°** (:2994-2997).
- L3: mv **every client in PVS**, no radius (:2361-2428); ours 360° within a **1024** box with no PVS check (:2998-3002).
- Untrick rules: same (FT_BUFFMINDTRICK is off by default).

**Grip**

| Item | 1.02 | Ours | Same? |
|---|---|---|---|
| Start cost / range / front check | 30 / 256 / InFront 0.9 below L3 | same | Yes |
| Continuous drain | **none** (the 1 per 100 ms at mv w_force.c:3760-3773 is `!= VERSION_1_02`) | 1 per 100 ms (:4787-4797) | **No** |
| Damage and release | 2/s; after 3 s, 20 (L2) or 40 (L3); release at 5 s (L1) or 4 s (L2/L3) | same (DoGripAction :4406-4576) | Yes |
| Line of sight | only for gripLevel < 3 (:3435-3441) | every level; FT_JK2GRIP removes it at **every** level (:4400) | **No** |
| Gripper speed | unchanged (the ×0.4 at mv bg_pmove.c:4284 is 1.03+) | ×0.4 (×0.8 FT_FASTGRIP) (bg_pmove.c:12110-12123) | **No** |
| Victim speed | ×0.2 (×0.8 with speed, ×0.9 with rage) | same (:12156) | Yes |
| Victim attacks / saber | may attack; saber stays lit | attack stripped (bg_pmove.c:14578-14582); saber turned off (w_force.c:5935), relighting blocked (g_cmds.c:3823) | **No** |
| Grip vs Absorb | allowed; level reduced; absorber gains `(30 or 60)/3 × absorbLevel` force **every frame** (WP_AbsorbConversion called from DoGripAction :3409) | blocked at start (ForcePowerUsableOn :608-621) | **No** |
| Other blocks | none | target in a saber special (:622-627); jetpack off; vehicle eject | Not in JK2 |
| Choke anims | no BOTH_CHOKE3 legs under PM_FLOAT and no "was on ground" via CHOKE3 (mv bg_pmove.c:2236, 2246); no whole-body choke in the air (:3487) | 1.04 behaviour (bg_pmove.c:6796, 6827, 10306-10307) | **No** |
| Lockout | 3000 ms; 1000 ms if a push breaks it | same | Yes |

**Lightning**
- Same values: 1-2 damage per tick, 1 force per tick, needs 25 force to start, L1 is a 500 ms burst and L2+ hold, L1/L2 line 2048, L3 radius 300 with a dot 0.5 cone, cooldown 3000 ms (L1) or 1500 ms.
- Tick rate: mv once per server frame (WP_ForcePowerRun :3842-3866); ours a fixed 50 ms catch-up (:4897-4902). Same only at sv_fps 20.
- Ours adds (not in JK2):
  - `noLightningTime` immunity and +1 force for 100/300/400 ms (:1856-1864, 1893-1903);
  - WP_MELEE double damage at L3 (:1907-1915);
  - saber blocking (g_lightningBlockEnabled, default 0);
  - decloak;
  - g_fixLightning.

**Rage**
- Same: 8/14/20 s, cost 50, −2 HP every 150/300/450 ms, needs ≥ 10 HP, 10 s recovery, damage taken ×0.5 then /(level+1), clients cannot kill you (health floor 1). Refs: mv g_combat.c:3062, 3475-3494; ours g_combat.c:4923-4928, 6092-6126.
- Ours lets `DAMAGE_NO_PROTECTION` bypass the rage rules. JK2 has no such case.
- Fire rate ×0.75 (rage) and ×1.5 (recovery): ours runs it only under `#if _GAME` (bg_pmove.c:11326-11338), so the cgame does not predict it. mv runs it shared (bg_pmove.c:3877-3884).

**Protect**
- Same: 20 s; cost 50/25/10; 1 force per 300 ms; force taken = maxtake × 1/0.5/0.25; HP saved 0.4/0.6/0.8; caps 100/200/400. Refs: mv g_combat.c:3366-3438; ours 5934-6020.
- 1.02 plays the hit sound on every hit (mv:3373-3379); ours has a 400 ms debounce. Sound only.

**Absorb**
- Duration 20 s and cost 50/25/10: same.
- Upkeep: 1 per **300 ms** in 1.02 (mv w_force.c:3897); ours 600 (:4947).
- Conversion: gain = (spent/3) × absorbLevel, minimum 1, cap 100 (mv :724-786). Same by default (ours caps at forcePowerMax, × g_teamAbsorbScale).
- 1.02 hit sound: PDSOUND_ABSORBHIT at the **attacker** origin, no trickedentindex, no debounce (mv :772-783), so the absorber shows no flash. Ours plays it at the absorber with a 400 ms debounce, and the cgame shows a 1 s blue shell (cg_event.c:2967-2973).
- Absorb shell: 1.02 cgame draws it **the whole time absorb is active** (mv cg_players.c:7550). Ours only after a hit, unless `cg_alwaysShowAbsorb` (cg_players.c:17199-17200).
- Drain against an absorber: 1.02 passes `atForceSpent 0`, so the absorber gains nothing (mv :1820). Ours gives +1 per tick unless FT_NODRAINABSORB (:2158-2161).

**Drain**
- Same: 2/3/4 force per hit, heals the user the same amount; victim regen delayed +800 ms, self +500 ms; L1/L2 line 2048; L3 arc 512 with dot 0.5; cooldown 3000/1500 ms.
- Cost per shot: **1** in 1.02 (mv ForceShootDrain :2031); ours **5** (:2518).
- Table cost 10 vs 20: this only affects availability, and the shared ≥ 25 gate dominates.
- Ticks once per frame in mv; ours on a 50 ms catch-up (:4868-4872).

**Team heal / energize**
- Same: radius 256/384/512; amounts and costs 50/33/25 for 1/2/3+ teammates.
- Ours adds a **2000 ms cooldown** (:1309, 1360, 1416, 1466) and scale cvars (default 1).

**Seeing:** 10/20/30 s, cost 20, removes mind trick. Same.

**Saber offense/defense/throw as force powers:** table costs are equal (offense 0, defense 2/1/0, throw 20). The only force-side difference is throw in duels (above). What each rank does in combat is in `JK2_102_COMPARISON.md`.

**Durations and cancel rules:**
- forceAllowDeactivateTime 1500 ms: same.
- WP_ForcePowerStop: logic is the same.
- Ysalamiri / forceDeactivateAll: same (ours adds tempSpectate).

### 1.3 Knockdown and getup (force and movement)

| Item | 1.02 (mv w_force.c:WP_ForcePowersUpdate:4560-4596) | Ours (w_force.c:5716-5804) | Same? |
|---|---|---|---|
| Wait | none; the getup starts when the hand-extend timer runs out | up to 4 s or a roll input, unless FT_JK2GETUPS | **No** |
| Force getup (upmove, levitation > 1) | forceDodgeAnim 2, +800 ms, vz 300 | 500/300, or 800/300 with FT_JK2GETUPS | No without the bit |
| Quicker getup | forceDodgeAnim 3, +600 ms, vz 200 | 500/300, or 600/200 with FT_JK2GETUPS; quickerGetup always cleared (:5776) | No |
| Normal getup | +1000 ms | — | — |
| Weapon state while down | **not** cleared (the clearing at mv:4508-4517 is 1.04-only) | saberMove, weaponTime and weaponstate zeroed (:5716-5724) | **No** |
| Roll getups | not in JK2 | G_SpecialRollGetup always called (:5735) | **No** |
| Getup anim > 4 | 1.02 has no split torso; GETUP1 is used | separate torso (bg_pmove.c:10199-10218) | No (only reachable through 1.04 rules) |

### 1.4 JKA/jaPRO force features that are not in JK2 (disable with the cvar on)

| Feature | Where |
|---|---|
| Gripped player loses attack and saber | bg_pmove.c:14578; w_force.c:5935; g_cmds.c:3823; w_saber.c:298 |
| Absorb blocks grip; no grip on a target in a saber special; no push/pull on knocked-down players | w_force.c:ForcePowerUsableOn:608-635 |
| Lightning extras (noLightningTime, melee ×2, saber block, decloak) | w_force.c:1856-1864, 1877-1881, 1893-1915, 1938-1942 |
| Absorb visuals tied to recent hits (teamPowerEffectTime/TFP_ABSORB) | cg_players.c:17199; server w_force.c:950-956 |
| Team heal/energize 2 s cooldown | w_force.c:1309, 1360, 1416, 1466 |
| Roll getups, the 4 s wait, weapon clearing while down | w_force.c:5572, 5716-5735 |
| Bot force cheat; bot push without releasing the button | w_force.c:276-314, 5099 |
| Siege rules, vehicles, two-handed/dual-saber force restrictions (`saber[].forceRestrictions`, g_saberRestrictForce) | w_force.c:207, 531, 638-649, 807-861, 3138-3154, 6119-6124 |
| 50 ms fixed ticks for drain and lightning; regen catch-up loop | w_force.c:4708, 4868, 4897, 6148 |
| JKA hand extends PRETHROW/POSTTHROW/PRETHROWN/POSTTHROWN/DRAGGING/JEDITAUNT | come from melee and taunts; disabled with WP_MELEE (bg_public.h:214-221) |
| jaPRO options that touch force | g_tweakForce (all FT_*), g_fixLightning, g_fixSaberInGrip, g_fixGetups, g_fixKillCredit, g_teamHealScale/EnergizeScale/AbsorbScale, unlagged, duel types in BG_CanUseFPNow (bg_misc.c:1912-1939) |

How close the existing tweak bits are:
- FT_JK2KNOCKDOWN matches the 128 range but not the 1100 ms or quickerGetup.
- FT_JK2GETUPS matches the 800/300 and 600/200 numbers, but the roll call and the clearing still differ.
- FT_JK2GRIP is **not** 1.02: it drops line of sight at every level.
- FT_NODRAINABSORB matches 1.02.
- FT_FASTGRIP is not 1.02, which has no gripper slow at all.

The new mode must not use any of these bits. It should run its own code paths.

---

## 2. Player movement and physics (non-saber)

Saber-specific movement (speed during swings, rolls during saber starts, DFA/lunge) is covered in `JK2_102_COMPARISON.md` §1.6/§1.13/§1.14, with the corrections in §0.1.

### 2.1 Constants (all equal for normal players)

| Item | 1.02 (mv) | Ours |
|---|---|---|
| stopspeed / duckScale / swimScale / wadeScale | 100 / 0.5 / 0.5 / 0.7 (bg_pmove.c:22-25) | same (:69-72) |
| accelerate / airaccelerate / wateraccelerate / flyaccelerate | 10 / 1 / 4 / 8 (:27-30) | same (:75-78) |
| friction / water / flight / spectator | 6 / 1 / 3 / 5 (:32-35) | same (:84-87) |
| g_speed / g_gravity | 250 / 800 (g_main.c:243-244) | 250 / 800 (g_xcvar.h:159, 110); racemode, tribes and superjump change them (g_active.c:4303-4398) |
| JUMP_VELOCITY / STEPSIZE / MIN_WALK_NORMAL / OVERCLIP / TIMER_LAND | 225 / 18 / 0.7 / 1.001 / 130 | same |
| bbox | ±15, −24..40, crouch 16, dead −8; view 36/12/−16 | same; maxs come from `ps->standheight`/`crouchheight` = 40/16 (g_client.c:4442-4443). **Our model-scale bbox code (g_client.c:~4855, "Apply model scale to bounding boxes") must be skipped in the mode.** |
| pmove_fixed / pmove_msec defaults | 0 / 8 | 0 / 8 |
| **pmove_msec clamp** | **8..33** (g_active.c:1042-1047) | **1..66** (g_active.c:3782-3787; cg_predict.c:1184-1188) |
| Pmove chop | 66 ms, or pmove_msec when fixed (mv:4776-4785) | same, except racemode 8 ms (ours:15936-15955) |
| Snapping | always `trap_SnapVector` | `pmove_float 0` snaps; see §7 for the rounding mode |

### 2.2 Core functions

| Function | 1.02 | Ours | Same? |
|---|---|---|---|
| PM_ClipVelocity | plain Q3 (mv:320-337) | PMF_STUCK_TO_WALL bypass (:1145); `stepSlideFix` (default **1**, g_xcvar.h:162) keeps `out[2]=in[2]` on steep planes while grounded (:1164-1172) | **No** |
| PM_Friction | mv:347-408 | MV_JKA path equal (ours:1183-1340), but a flag carrier swimming gets 0 water friction through `g_flagDrag` (:1317-1322, game only) | mostly |
| PM_Accelerate / PM_CmdScale / PM_WaterMove / PM_SetWaterLevel / PM_GroundTrace | mv:418, 468, 1454, 2413, 2311 | equal for MV_JKA players | Yes |
| PM_AirMove | mv:1574-1641 | adds `PM_GroundSlideOkay` (no clip on steep ground while wall-running or rebounding, ours:5240; slidemove.c:595-616), STUCK_TO_WALL, jetpack | close |
| PM_WalkMove | resets `forceSpeedSmash = 1` when slow or still (mv:1661-1682, 1790) | no reset (ours:5872-6136) | **No** (speed ramp) |
| PM_CheckWaterJump | `if (cont) return` for **any** contents (mv:1409-1413) | only SOLID, PLAYERCLIP and BODY block it (ours:4645-4649) | **No** |
| PM_GroundTraceMissed | no CHOKE3 under PM_FLOAT, CHOKE3 does not count as "was on ground" (mv:2236, 2246); INAIR1 with **SETANIM_FLAG_OVERRIDE** (mv:2262) | always CHOKE3 (ours:6796-6804, 6827); INAIR1 flags **0** (6844) | **No** |
| PM_CheckDuck stand-up | full-box trace with maxs 40, `!allsolid` (mv:2492-2515) | crouchfix on by default (`DF_NO_CROUCHFIX` = 0): 5×5 line traces and `PM_CanStand` (ours:7247-7277, 7414-7429, 7488-7500); JASP crouch-jump for other styles | **No** |
| PM_SlideMove same-plane test | `DotProduct > 0.99` (mv slidemove.c:113-121) | `VectorCompare` (exact) (ours slidemove.c:795); normals flattened under GroundSlideOkay (711-715, 781-786); `PM_ClientImpact` (626-659, 764-767, game only) | **No** |
| PM_StepSlideMove | Force-speed users may step with up-velocity or while allsolid (mv slidemove.c:241-276). Ceiling smash if `pre_z > 480` during a force jump (301-319). Speed wall smash `forceSpeedSmash > 1.3 && totalVel > 500`: bounce ×0.1, z 64; otherwise smash −0.1 per hit (321-361). Damage stays 0 because FORCE_VELOCITY_DAMAGE is 0. | none of that; stepSlideFix=1 (no step onto steep slopes, restores down_o/down_v, 1103-1131, 1225-1232); `BG_InReboundHold` (1019) | **No** |
| Ladders | none | none | Yes |

### 2.3 PM_CheckJump (mv:733-1377 vs ours:3348-4613)

| Rule | 1.02 | Ours | Same? |
|---|---|---|---|
| Blocks | ATST, KNOCKDOWN, RESPAWNED, knockdown/roll anims (mv:735-753) | adds PRETHROWN/POSTTHROWN, jetpack, vehicles (3366-3403) | Yes for JK2 cases |
| Air early return | mv:967-974 (in the air: only wall-run continue) | absent | **No** |
| `upmove < 10` return | in the air too (mv:982) | ground only (3751) | **No** |
| Ground specials weapon | WP_SABER only (mv:1013) | SABER or MELEE (3789) | No |
| Ground forward + jump into a wall | **BOTH_WALL_FLIP_BACK1**: needs levitation > 1, trace 16 forward, vertPush = 840/2.25 + 128, −150 forward (mv:1048-1052) | missing (3960 goes to the backflip) | **No** |
| Wall trace contents | MASK_PLAYERSOLID: runs, flips and kicks also work off players (mv:1067, 1107) | MASK_SOLID unless `g_flipKick > 0` (3980-3983, 248-277) | **No** |
| Wall-run wall normal | no z test | z must be 0..0.4 (4042-4045) | No |
| Side flips | always (mv:1029-1046) | g_flipKick 2/3 variants (3880-3958); SFL_NO_* saber flags | Yes with g_flipKick < 2 |
| In-air wall-run flip | mv:1170-1239 | same values (4123-4191) | Yes |
| In-air run-up flip, FORCEWALLRUNFLIP, wall run-up, rebound/wall grabs | not in 1.02 (mv:1240 is 1.03+) | 4193-4474 | **JKA only** |
| Normal jump | 225, ZStart, EV_JUMP, PM_JumpForDir (mv:1350-1376) | same (4529-4612) | Yes |
| Wall-run steering (PM_AdjustAngleForWallRun) | no normal test; forward rebuilt from the **new** yaw (mv:625-716, 682-683) | normal z 0..0.4; front-wall abort; forward from the pre-snap yaw (1768-1874) | **No** |
| PM_DoSlowFall | wall run with legsTimer > 500: gravity ×0.5, no air control | same | Yes |

### 2.4 Landing, falling, knockdown, kick

| Rule | 1.02 | Ours | Same? |
|---|---|---|---|
| PM_CrashLand delta formula, ×2 ducked, water ×0.25/×0.5, event > 7, cap 600, force-jump clamp | mv:1982-2179 | same | Yes |
| Landing anim | `PM_ForceLegsAnim(LAND1/LANDBACK1)` if inAirAnim, then legsTimer 130 | also FORCEJUMP* → LAND* on **SETANIM_BOTH OVERRIDE+HOLD** (6509-6531); A7 kick landings; TIMER_LAND skipped during FORCELAND* (6575-6578); FORCELAND stiffen (14481-14487, 8484-8491) | **No** |
| Landing roll | allowed with **any** forceHandExtend (mv:2083 is 1.04-only) | requires HANDEXTEND_NONE (6611) | **No** |
| Fall damage (server) | ignore delta ≤ 44; damage = delta × 0.16 (mv g_active.c:754-783) | in a knockdown anim the threshold is 14 and damage = delta × 1; `g_maxFallDmg`; siege; racemode none (ours g_active.c:1913-1978) | **No** while knocked down |
| Kick-flip (jumping off someone's head) | always (mv g_active.c:1619-1642): damage = speed × 0.05; 30% chance of knockdown for 1100 ms; push strength × 40 with z 200 | red attacker gets a weak 25×/125 push; g_nonRandomKnockdown, g_flipKickDamageScale, BG_KnockDownable, glitch-kick (g_active.c:5620-5800) | **No** |
| Dodge (Jedi_DodgeEvasion) | mv w_force.c:4981-5100 | identical apart from ATST and `g_forceDodge` options (ours :6234-6355) | Yes |

### 2.5 BG_AdjustClientSpeed (non-saber parts; mv:4200-4401 vs ours:12065-12399)

| Rule | 1.02 | Ours |
|---|---|---|
| Back-running ×0.75 | none (mv:4279 is 1.04-only) | yes, unless JK2SWINGS or ST_ALLOW_ROLLCANCEL (12098-12107) |
| Speed / rage | ramp; both stack (§1.2) | flat 1.7; `else if` |
| Gripper ×0.4 | none | yes |
| Disruptor zoom | none | ×0.5 (12150-12154) |
| Grip victim | 0.9 / 0.8 / 0.2 | same |
| Roll speed | only if speed > 200: `BG_CmdForRoll`; back `legsTimer/2.5`, else `/1.5`; cap 600 (mv:4384-4400) | different formula (base speed > 50, `/1.5` then `/5` below 800 ms; fixroll variants); CmdForRoll always called from PmoveSingle (14590-14593) |
| Saber `moveSpeedScale` | none | applied (12385-12398); 1.0 for stock sabers |

### 2.6 Rolls, animations and the rest of pmove

| Rule | 1.02 | Ours |
|---|---|---|
| Roll trigger | ducked + `PM_RunningAnim` + not InRoll; **no speed test** (mv:2693) | needs \|v\|² ≥ 40000 (ours:8350-8353) |
| PM_TryRoll | saber only (mv:1919-1930) | saber or melee, gunroll option, noRoll, SFL_NO_ROLLS (6249-6379) |
| PM_SetAnim | never interrupt a roll; RESTART for special jumps (mv bg_panimate.c:1199-1207) | both commented out (ours bg_panimate.c:3147-3158) |
| BG_InSpecialJump | 12 anims (mv bg_panimate.c:15-34) | adds WALL_RUN_*_STOP, DFA anims, butterflies, cartwheels, rebounds (ours bg_panimate.c:93-168); this changes landing timers and jump gating |
| Run/walk/crouch anims | always ContinueLegsAnim; never OVERRIDE; RUN1/RUNBACK1/WALK1/WALKBACK1/CROUCH1*; idle STAND1 when holstered, else WeaponReadyAnim (mv:2606-2806) | OVERRIDE when legs are in saber/landing/pain/stance anims (8203-8218); `!= current` restarts; slope and staff/dual anims |
| Special jump, roll, roll-complete | **forces `cmd.weapon = ps.weapon = WP_SABER`** (mv:3507-3513) | sets `weaponTime = legsTimer` (10327-10348) |
| Taunt | `weaponTime = 100` (mv:3907) | commented out (11383) |
| Disruptor | no movement while charging alt; any movement or jump unzooms (mv:4092-4130, 4504-4512) | charge cancelled on move; jump blocked when zoomed; ×0.5 speed; unzoom block commented out (11826-11868, 14551-14569) |
| Saber lock | `forwardmove = 50`, no stiffen (mv:4629-4634) | 14274-14280, 14803-14808 |
| BUTTON_TALK | a 1.02 client can move with the console open (mv:4546, keyed on `jk2startversion`) | movement always zeroed (14640-14647) |
| ROLL view angle | untouched | forced to 0 (15925-15927); matters only for cheat clients |

### 2.7 JKA-only movement (not in JK2) to disable in the mode

- In-air run-up flip, FORCEWALLRUNFLIP, rebound/wall grab (PMF_STUCK_TO_WALL): ours:4193-4474, 14714-14734.
- Kicks (A7), katas, butterflies, cartwheels, long leap, stab-down, pull impale: saber report §1.6.
- g_flipKick extras, JASP crouch-jump, dash/dodge/walljump (BUTTON_DASH): 14921-14924.
- Jetpack, grapple, vehicles, swoop, tribes/thrust, NPC head bounce: 14849-15022, 15300-15515, 15360-15380, 15648-15666.
- Slope stand anims, staff/dual run anims: PM_Footsteps 8298-8914.
- Getup rolls (BOTH_GETUP_*ROLL): w_force.c:5735; BG_CmdForRoll 11955-12058.
- All jaPRO movement styles: the mode must force MV_JKA, no racemode, and `STAT_MOVEMENTSTYLE = MV_JKA`.

---

## 3. Weapons, items, damage

### 3.1 Data tables

| Item | 1.02 (mv) | Ours | Same? |
|---|---|---|---|
| weaponData | `weaponData_1_02` bg_weapons.c:28 | bg_weapons.c weaponData | All JK2 rows equal **except**: WP_BRYAR_PISTOL (ours ammoLow 0, energy 0, fireTime 800, alt 0/800, no charge; JK2 15/2/400, alt 2/400, altChargeSubTime 200, altChargeSub 1, altMaxCharge 1500, which equals ours WP_BRYAR_OLD), and WP_REPEATER altEnergyPerShot (**8** in 1.02, 15 ours and 1.04) |
| ammoData maxima | 0/100/300/300/300/25/800/10/10/10 | same | Yes |
| Weapon enum | NONE, STUN_BATON, SABER, BRYAR … DET_PACK, EMPLACED, TURRET | adds WP_MELEE (index 2), WP_CONCUSSION, WP_BRYAR_OLD. **All weapon indices from SABER upward are shifted by one**, so `g_weaponDisable` masks from JK2 configs do not carry over | n/a |
| g_weapon.c #defines | mv:15-97, 1689-1868 | equal except STUN_BATON_DAMAGE **2** (JK2 20); ours wraps values in g_weaponDamageScale / g_projectileVelocityScale / g_splashDamageScale | Yes at scale 1, except the baton |
| Muzzle points | rocket `{12,8,0}` (mv bg_weapons.c:22) | rocket `{12,8,-4}` (ours bg_weapons.c:43); also used by the lock trace | **No** |
| No code writes weaponData or forcePowerNeeded at runtime in ours (grep) | — | — | so they can be patched safely at init |

### 3.2 Per weapon (only differences listed; everything not listed matched value by value)

| Weapon | Difference (1.02 → ours) |
|---|---|
| Stun baton | damage **20** → 2 (mv g_weapon.c:95/2576; ours :137/5119). Trace, range and electrify are identical. |
| Bryar pistol | JK2 `weapon_bryar_pistol` = WP_BRYAR_PISTOL with charge. In ours the item `weapon_bryar_pistol` maps to **WP_BRYAR_OLD** (JK2 behaviour) and JKA's WP_BRYAR_PISTOL is the no-charge pistol. Charge formula is equal (count 1..5; ×1.5 or ×count·1.7; box 0.5·count). Ours `WP_FireBryarPistol` multiplies damage by the **velocity** scale cvar (g_weapon.c:371-372; harmless at 1.0). |
| E-11 | equal (2300/20, alt ±1.6°) |
| Disruptor | range **8192** → 32768 (ours g_weapon.c:774, 1016). Ghoul2 trace by default in ours. Alt charge formula equal (70 + count, max 130, traces 1/2/3). JK2 charges while moving; ours requires standing still (bg_pmove.c:9412-9416). JK2 fires while zoomed and moving; ours blocks it (10718-10723). JK2 unzooms on movement; ours does not (11826-11837) and adds ×0.5 speed and a 1000 ms unzoom lockout (11792). |
| Bowcaster | primary velocity 1300·(**crandom**·0.3+1) = **910..1690** (mv:866) → `Q_flrand(0,1)`, i.e. 1300..1690 (ours:1578). Charge, damage and alt equal. |
| Repeater | alt ammo 8 vs 15 (table). Damage, splash and velocity equal (Siege radius 80 is JKA only). |
| DEMP2 | equal for players (health damage /3 after armor). Ours adds electrify and decloak effects, ×2/×5 against droids, jetpack shutdown. |
| Flechette | equal |
| Rocket | Ours rocket is **shootable** (health 10, die = RocketDie, ours :3237-3250); JK2's is not. JK2 pushes the rocket down within 128 **always**; ours only when the target is on the ground (2898-2908). Lock: JK2 locks on both sides through PM_DoChargedWeapons, clients only (mv bg_pmove.c:2977-3040); ours game side locks **only in racemode** (bg_pmove.c:9368-9380) while the cgame always predicts a lock; ours also locks NPCs and skips cloaked targets. Lock time 750 ms is equal. |
| Thermal | equal |
| Trip mine | primary equal. **Alt**: JK2 timed mine: touch explodes, blows 2000 ms after sticking (`laserTrapExplode`, mv g_weapon.c:2031-2037), not shootable. Ours: proximity mine (enemy within 128), 30 s auto, shootable, armed sound (ours 3855, 3980-4002). `WT_JK2_STYLE_ALT_TRIPMINE` only drops the 30 s timer. |
| Det pack | ours spawns +8 forward (drop_charge :4363); stick-normal bug `vNor[1]` vs `vNor[2]` (mv:2222 / ours:4228); JKA stick rules for breakables and movers |
| Emplaced gun | MOD_BLASTER + DEATH_KNOCKBACK (JK2) vs MOD_VEHICLE + HEAVY_WEAP_CLASS; JK2 has ±1.6° alt spread, ours none; ours adds a yaw constraint of 60 and a different use condition |

### 3.3 Common projectile and damage code

| Item | 1.02 | Ours | Same? |
|---|---|---|---|
| Missile spawn | `CreateMissile` (mv g_missile.c:271), no prestep, no inheritance | `CreateMissileNew` (ours :350), unlagged nudge and inheritance cvars (off by default) | Same at defaults; the mode must force them off |
| Collision | bbox `trap_Trace` | Ghoul2 per-poly when `d_projectileGhoul2Collision` (default **1**; ours g_missile.c:1227-1250) | **No** |
| Bounce count | decremented after the bounce (mv:189-193) | before (ours:171-174) | small |
| Saber blade contact | `WP_SaberCanBlock` unconditionally (mv g_missile.c:437) | `WP_SaberBlockNonRandom` only if `weaponTime <= 0`, plus a `s.bolt1` dimension check (ours 680-695) | **No** (coordinate with the saber port) |
| Body block / reflect | def1 kills, def2 deflects, def3 reflects; ±0.2 random | same (ours adds CONC exclusion and SEF_DEFLECTED) | Yes |
| **Location damage** | **none in JK2 MP** (G_GetHitLocation is used only for dismemberment and dodge) | `G_LocationBasedDamageModifier` (ours g_combat.c:4549, applied at 5082 **before** knockback): head ×1.3, hand ×0.6, foot ×0.5, leg ×0.7, arm ×0.85; `g_locationBasedDamage` default 1 | **No** |
| Knockback | min(damage, 200); kvel = dir · g_knockback(1000) · kb / 200; pm_time = clamp(2·kb, 50, 200) (mv g_combat.c:3104-3160) | same formula, but on location-scaled damage; saber velocity-scale rule (saber report §1.9) | No while location damage is on |
| Armor (CheckArmor) | ARMOR_PROTECTION 0.5, ARMOR_REDUCTION_FACTOR 0.5 (mv g_combat.c:2222-2268) | identical (ours :3199-3251) apart from a vehicle branch | Yes |
| Handicap scale | `damage * attackerMaxHealth / 100` | same | Yes |
| Self damage | ×0.5 | `g_selfDamageScale` default 0.5 | Yes |
| trueJedi splash | ×0.5 (1.02) | ×0.75 | Only with g_jediVmerc (1.02 never sets trueJedi at spawn) |
| DEMP2 vs health | /3 after armor, minimum 1 | /3 | Yes |
| Rage, protect, absorb | §1.2 | §1.2 | — |
| Health/armor countdown above max | −1 per second each (mv g_active.c:ClientTimerActions:682-702) | identical (ours :1752-1770) | Yes |
| Max health | 100 (handicap ≤ 100) | 100 | Yes |

### 3.4 Dismemberment (g_dismember default "0" in both)

| Item | 1.02 | Ours |
|---|---|---|
| When | only on death by MOD_SABER (mv g_combat.c:player_die:2170-2173); also the saber-lock loser at 999 (mv g_active.c:1408) | death by MOD_SABER or heavy melee, or any MOD with `g_dismember >= 101` (ours g_combat.c:3044-3052); dead NPCs again with ≥ 102 (6211-6220); gib at ≥ 103 |
| Chance / minimum | `Q_irand(0,100) > g_dismember` returns; **damage < 20** returns (mv:2885-2895) | same chance; **damage < 5** (ours:4454-4462) |
| Hit location | `G_GetHitLocation` bbox method (mv:2898-2944) | Ghoul2 surface when `d_saberGhoul2Collision` and a surface hit this frame (ours:4465ff) |
| Limb physics in 1.02 | box ±3; no +100 z for head/waist; random angular delta ±300 (waist ±60); no wrist sparks (mv:2589-2715) | JKA box −6..6/−9..6, +100 z, JKA spin |

### 3.5 Holdables, items, loadout

| Item | 1.02 | Ours | Same? |
|---|---|---|---|
| Medpac | **+100** (mv g_items.c:31, 1079) | +25 (ours g_items.c:63, 1220) | **No** |
| Seeker, sentry, shield, binoculars | 30 s / 15 dmg; 10 dmg / r800 / 60 s; 250 hp, −10 per tick; zoom 40 | same (shield orientation-2 maxs `height` vs `height>>1`, ours g_items.c:350 vs mv 288) | Nearly |
| Holdables in a private duel | usable (mv bg_pmove.c:3204 is 1.04-only) | blocked (PM_ItemUsable) | **No** |
| BG_CanItemBeGrabbed armor | up to `max_health * giTag` (large shield up to 200) (mv bg_misc.c:1698) | up to max_health only (ours bg_misc.c:2383); thermal/tripmine/detpack refused at full ammo (2362) | **No** |
| Item quantities and respawn times | — | identical | Yes |
| Powerups (enlightenment light/dark, boon, ysalamiri) | 25 s | same | Yes |
| **Spawn loadout** | Saber if FP_SABERATTACK, else stun baton; plus Bryar unless weapons are disabled (duel default `g_duelWeaponDisable 1`); Jedi Master gets the stun baton; selected weapon = **Bryar**; AMMO_BLASTER 100; no holdables (mv g_client.c:1935-1980, 2118-2130) | `GiveClientWeapons` (ours g_client.c:3988) uses `g_startingWeapons` (default 8 = saber only); no saber → WP_MELEE (4557); Jedi Master → WP_MELEE (4572); saber selected; AMMO_BLASTER 100 only if `g_startingWeapons == 0` (4715); `GiveClientItems` (3762) | **No** |
| Weapon raise | +250 ms (mv bg_pmove.c:2935) | game +50 (+25 fast switch, +1250 ST_FIXED_SABERSWITCH), cgame +250 (bg_pmove.c:9106-9122). Server and client already disagree here. | **No** |
| Weapon drop | +200 | +200 | Yes |

**JKA-only weapons and items, proposal with the cvar on:**
- WP_CONCUSSION: disable.
- WP_MELEE: disable, and give WP_STUN_BATON where JK2 does.
- JKA WP_BRYAR_PISTOL: never give; use WP_BRYAR_OLD as "the pistol".
- HI_MEDPAC_BIG, HI_JETPACK, HI_HEALTHDISP, HI_AMMODISP, HI_EWEB, HI_CLOAK, ammo_all: disable.

Gate each one in G_SpawnItem/G_ItemDisabled, G_Give (g_cmds.c:477), GiveClientWeapons, TossClientWeapon, BG_CanItemBeGrabbed, cgame CG_WeaponSelectable (cg_weapons.c:1138) and bot weapon choice (ai_main.c:3054, 9398, 9431, 9566, 10202, 17202). JK2 maps' `item_datapad` does not exist in ours; this is harmless.

---

## 4. Match rules

| Rule | 1.02 (mv) | Ours | Same? |
|---|---|---|---|
| Spawn health/armor | **125 HP / 25 armor in every gametype**: `MAX_HEALTH*1.25`, `MAX_HEALTH*0.25` (g_client.c:2164-2167) | 125/25 in FFA/team; **duel and power duel 100/0** (g_xcvar `g_duelStartArmor`), siege classes, tribes, racemode (ours g_client.c:4757-4842) | **No** in GT_DUEL |
| Spawn invulnerability | `g_spawnInvulnerability 3000`; removed when you fire, alt-fire, start a saber attack, use lightning or drain, start a force power, or throw the saber (mv g_active.c:784-803; w_force.c:1566, 1790, 3245, 3389; w_saber.c:3585) | same default and the same removal points (ours g_active.c:1978-1998, w_force.c:1842, 2110, 4199, 4348, w_saber.c:9318) | Yes |
| Respawn | 1700 ms after death (1000 if gibbed); attack or use to respawn; `g_forcerespawn 60` (mv g_combat.c:2130; g_active.c:1653-1672) | same 1700 / 1000; `g_forceRespawn 60`; siege/powerduel forced (ours g_active.c:5806-5840) | Yes (outside siege/powerduel) |
| Private duel: start | `/engage_duel`: `g_privateDuel`; **not in GT_TOURNAMENT or team modes**; saber out and not thrown; trace 256 at MASK_PLAYERSOLID; **refused if any other private duel is running** (`G_OtherPlayersDueling`); 10 s `privateDuelTime` after a duel; challenge window 5 s; both sabers holstered with weaponTime 400; 2 s freeze, then sabers on (mv g_cmds.c:Cmd_EngageDuel_f:2229-2360; g_active.c:1120-1167) | jaPRO `Cmd_EngageDuel_f(ent, dueltype)` with saber/force/gun duel types (ours g_cmds.c:4245ff); `G_OtherPlayersDueling` is compiled out (4141-4158, inside `#if`), so many duels can run at once | **No** |
| Private duel: damage filter | only the duel partner, and only MOD_SABER (mv g_combat.c:3036-3059) | dueltype-dependent (ours g_combat.c:4879-4900) | Same for saber duels |
| Private duel: end | winner health raised to max **if below** it, **armor untouched**, spawn invulnerability; partner gone → end; **distance ≥ 1024 ends it** (mv g_active.c:1169-1225) | winner health = max and **armor = 25** (ours g_active.c:4517-4518); distance check only with `g_duelDistanceLimit` (default 0) (4558-4566) | **No** |
| Saber throw in duel; holdables in duel | allowed / allowed | not allowed / not allowed | **No** (§1.1, §3.5) |
| Saber locks in duels | `g_saberLocking 1`; lock code in the saber report §1.8 | — | see saber report |
| Jedi Master | JM gets full force and the stun baton (no guns); regen +4; damage filter: non-masters cannot hurt each other while a master exists without friendly fire (mv g_combat.c:3213-3221) | same filter and regen; JM given WP_MELEE (ours g_client.c:4572) | **No** (weapon) |
| Holocron | regen +1 per holocron carried; g_MaxHolocronCarry | same code paths | Not compared beyond regen |
| Gametypes | FFA, Holocron, Jedi Master, Tournament, (Single), Team, CTF, CTY | adds Power Duel and Siege | Not in JK2: refuse the mode in Siege and Power Duel, or ignore it there |
| Drowning, lava, slime | P_WorldEffects: drown 2..15 per second, lava 30 × waterlevel, slime 10 × waterlevel | identical apart from tempSpectate/racemode guards (ours g_active.c:887ff) | Yes |
| Telefrag | G_KillBox | identical apart from the "not yourself / not your vehicle" guards | Yes |
| Damage/knockback cvars | g_knockback 1000, g_friendlySaber 0, g_saberDmgVelocityScale 0, g_jediVmerc 0, g_forcerespawn 60, g_spawnInvulnerability 3000 | same defaults | Yes |

---

## 5. Assets

**Animation timing** (animation.cfg numFrames/loop/fps, 233 non-saber sequences checked: run/walk/crouch/stand, jumps, lands, force jumps/lands, flips, wall runs/flips, rolls, knockdowns, getups, dodges, choke, force-power anims, pains, deaths, swim, torso/legs):

| Compared with JK2 assets0.pk3 | Differences |
|---|---|
| Vanilla JKA assets1.pk3 | Only BOTH_DEATH16 (41 → 23 frames), TORSO_SURRENDER_START/STOP (fps 20 → 10), and 4 JK2 anims JKA lacks (PAIN19, PAIN20, STAND1_REELO, WALK10). **All movement, force, knockdown and getup anims are identical.** |
| Our `nicjk/japro-assets.pk3` | Same as above, **plus BOTH_FLIP_F (11 f @20 → 33 f @30), BOTH_FORCEJUMP1 (17 @20 → 23 @30), BOTH_FORCELAND1 (14 → 11), BOTH_LAND1 (5 → 11)**. These lengths change the landing timer, how long the flip lasts, and force-jump gating. |

The `.gla` bone data was not compared, so poses may differ even where timings match (as in the saber report).

**Sounds and effects:**
- I collected every literal `effects/…`, `sound/weapons/…`, `sound/effects/…` and `sound/player/…` path that mv game/cgame reference: 116 exist in both games.
- **110 are byte-identical (same CRC and size).**
- **6 differ:** `effects/blaster/deflect.efx`, `sound/effects/bumpfield.wav`, `sound/weapons/bryar/fire.wav`, `sound/weapons/disruptor/altcharge.wav`, `sound/weapons/force/jump.mp3` and `jump.wav`.
- Paths built at runtime with `va()` were not checked.
- JK2 references a few files that neither base game ships (`sound/weapons/force/lightninghit.wav`, `sound/weapons/rocket/missileloop.wav`, `rocklf1a.wav`, `saber/saberhum.wav`). Those are dead references in JK2 too.
- **Cosmetic but not exact:** weapon models and skins, HUD art (the JK2 `gfx/hud/*` prongs and ticks exist only in JK2), shaders (`gfx/effects/forcepush`, saber glow shaders, `gfx/misc/*shield*`; these are shader names, and JKA defines its own versions), the absorb and protect shells (JKA shaders), and the force push distortion.

**What JK2 behaviour depends on:**
- The absorb shell must be drawn whenever absorb is active (cgame rule, §1.2).
- The 1.02 absorb-hit event has no `trickedentindex` (cg_event.c needs to accept it).
- The kick-flip punch sounds (`sound/weapons/melee/punch1-4`) are registered in mv cgame. Ours registers swing sounds instead; check that the punch files are present in JKA.

---

## 6. Porting plan

### 6.1 Principle and cvar

- This is the same approach as the saber report §3. **There is one cvar.** `g_jk2_102sabersystem` should cover saber, force, movement, weapons and rules, because the user wants "the whole combat" to be 1.02. Give it `CVAR_SERVERINFO|CVAR_ARCHIVE|CVAR_LATCH` (g_xcvar.h, next to g_mb2manualblock at :311).
- Macro in `bg_local.h` next to `MB2BLOCK()` (117-119):
  - `#define JK2MODE() (g_jk2_102sabersystem.integer != 0)` for game;
  - `(cgs.jk2_102sabersystem != 0)` for cgame.
- cgame plumbing:
  - `cg_local.h:2379`: `int jk2_102sabersystem;`
  - `cg_servercmds.c:251`: `cgs.jk2_102sabersystem = atoi(Info_ValueForKey(info, "g_jk2_102sabersystem"));`
- **Mode-local option masks.** At every jaPRO switch read in shared or combat code, use for example `int tweakForce = JK2MODE() ? 0 : g_tweakForce.integer;`. Do the same for g_tweakWeapons, g_tweakSaber, g_flipKick, g_fixRoll, stepSlideFix, crouchfix (DF_NO_CROUCHFIX), g_locationBasedDamage, d_projectileGhoul2Collision, d_saberGhoul2Collision, unlagged, g_selfDamageScale (0.5), the scale cvars, g_teamHealScale/EnergizeScale/AbsorbScale, g_fixLightning, g_fixGetups, g_fixSaberInGrip, g_forceDodge, g_maxFallDmg, g_nonRandomKnockdown and g_flipKickDamageScale. This is cheaper and safer than touching each cvar.
- **Force MV_JKA**, no racemode, no tribes. `STAT_MOVEMENTSTYLE = MV_JKA` at spawn. Refuse or ignore the mode in GT_SIEGE and GT_POWERDUEL.
- **Data tables.** Add `void BG_JK2SetTables(qboolean on)` in bg_weapons.c/bg_pmove.c, called from G_InitGame and from the cgame after the serverinfo parse (the cvar is latched, so it is stable per map). It patches:
  - `forcePowerNeeded[1..3][FP_HEAL] = 25` and `[FP_DRAIN] = 10`;
  - `weaponData[WP_REPEATER].altEnergyPerShot = 8`;
  - `WP_MuzzlePoint[WP_ROCKET_LAUNCHER][2] = 0`;
  - and restores the originals when off.

  No other code writes these tables, so this is safe, and it keeps every reader unchanged.

### 6.2 Networking

- **No new netfields.** Every field used above already exists and is sent, except one thing: `fd.forcePowerLevel[FP_SPEED]` and `fd.forceSpeedSmash` are **not** in the engine's playerState field list. Only `forcePowerLevel[FP_LEVITATION]` (2 bits) and `[FP_SEE]` (2 bits) are sent (engine `codemp/qcommon/msg.cpp:1370, 1440`).
- Without them the cgame would clamp smash to `forceSpeedLevels[0] = 1` and mispredict speed. (Real JK2 probably did the same; see §7. Exact server behaviour is the goal, and prediction should match the server.)
- **Proposal:** in JK2 mode, `STAT_WJTIME` and `STAT_DASHTIME` are free, because wall-jump and dash do not exist in JK2. Store:
  - `stats[STAT_WJTIME] = speed level`, set at force power init;
  - `stats[STAT_DASHTIME] = (int)(forceSpeedSmash * 1000)`.

  The server writes both in `BG_AdjustClientSpeed`. The cgame reads them back into `ps->fd` before pmove (or `BG_AdjustClientSpeed` reads the stats directly in mode). The 16 stats and 16 persistant slots stay as they are.
- Everything else is already networked: forcePowersActive, forceRageRecoveryTime, forceGripCripple, forceHandExtend, forceDodgeAnim (forceHandExtendTime and quickerGetup are server-only, as in JK2), legsTimer/torsoTimer, weaponTime, zoomMode, rocketLock*, duelInProgress.

### 6.3 Changes per file (each gated by `JK2MODE()`)

**Shared `bg_pmove.c`**
1. `BG_JK2SetTables` (tables above).
2. `PM_ClipVelocity` 1164: no stepSlideFix. `PM_Friction` 1317: no flag drag. `PM_AirMove` 5240: no GroundSlideOkay.
3. `PM_SetForceJumpZStart` 2216: no −0.1 nudge.
4. `PM_AdjustAngleForWallRun` 1796-1855: 1.02 steering.
5. `PM_CheckJump`:
   - drain 5 in duels too (3432);
   - no ZStart requirement (3536);
   - the 1.02 air return (after 3745);
   - unconditional `upmove < 10` (3751);
   - WP_SABER only (3789);
   - add WALL_FLIP_BACK1 before 3960;
   - MASK_PLAYERSOLID and no wall-normal test (3980, 4042);
   - side flips ignore g_flipKick;
   - skip 4193-4474;
   - the JK2 jump-attack block from the saber report.
6. `PM_CheckWaterJump` 4647: `if (cont)`.
7. `PM_WalkMove`: forceSpeedSmash resets (mv:1661-1682, 1790).
8. `PM_TryRoll` 6274/6300: 1.02 rule, saber only.
9. `PM_CrashLand`: skip 6476-6531; TIMER_LAND unconditional (6575); landing roll with any handExtend (6611).
10. `PM_GroundTraceMissed` 6796/6827/6844: 1.02 choke and INAIR rules.
11. `PM_CheckDuck` 7414/7488: full-box stand test.
12. `PM_Footsteps` 8203-8914: no OVERRIDE, ContinueLegsAnim only, JK2 anim set, roll trigger with no speed test, no FORCELAND wait.
13. `PM_DoChargedWeapons`: disruptor charges while moving (9412); rocket lock on both sides, clients only (9230, 9368-9380).
14. `PM_FinishWeaponChange` 9106-9122: +250 on both sides.
15. `PM_Weapon`:
    - no split getup torso (10199);
    - no air full-body choke (10307);
    - force WP_SABER during special jumps and rolls (10327, mv:3507-3513);
    - fire while zoomed and moving (10718);
    - rage fire rate shared, not `_GAME` only (11326);
    - zoom rules (11790-11868).
16. `PM_Animate` 11383: taunt `weaponTime = 100`.
17. `BG_AdjustClientSpeed` 12065-12399:
    - no back-run, gripper or zoom slow;
    - speed ramp via the stats (§6.2), stacking with rage;
    - 1.02 roll formula;
    - no moveSpeedScale.
18. `PmoveSingle`:
    - no unconditional CmdForRoll (14590);
    - no FORCELAND stiffen (14481);
    - do not strip attack while gripped (14578);
    - saber-lock `forwardmove = 50`;
    - BUTTON_TALK pass-through (14640, decide);
    - skip jetpack, dash, grapple, wall-jump and head bounce (14714-15022, 15371, 15648).
19. `PM_ItemUsable`: holdables allowed in a duel.
20. `Pmove` 15925: no racemode msec.

**Shared `bg_slidemove.c`**
- `PM_SlideMove` 795: `Dot > 0.99`. 711/781: no GroundSlideOkay. 764: decide about `PM_ClientImpact`.
- `PM_StepSlideMove`: no stepSlideFix (1103-1131, 1225-1233); no ReboundHold (1019); port the mv force-speed step and smash and the ceiling smash (mv slidemove.c:241-361).

**Shared `bg_panimate.c`**
- `BG_SetAnimFinal` 3052: the /1.3 and /1.7 scaling applies to every HOLD legs anim.
- `BG_SetAnim` 3147-3158: RESTART on special jumps, never interrupt a roll.
- `BG_InSpecialJump` 93: the JK2 list of 12.

**Shared `bg_misc.c`**
- `BG_CanUseFPNow` 1914-1939: throw allowed in duels.
- `BG_LegalizedForcePowers`: 1.02 order of the offense rule.
- `BG_CanItemBeGrabbed` 2362/2383: JK2 armor cap; no full-ammo refusal; refuse JKA-only items and weapons.

**Server `w_force.c`**
- skip the bot cheat (276-314);
- ForcePowerUsableOn: no absorb/special/knockdown blocks (608-635);
- WP_AbsorbConversion (880-958): cap 100, sound at the attacker, no debounce, no gift to non-absorbers;
- ForceHeal: 10/25/50;
- team heal/energize: no cooldown;
- ForceGrip, ForceLightning, ForceDrain: plain `weaponTime > 0`;
- ForceLightningDamage: no JKA extras;
- ForceDrainDamage: absorber gains 0;
- ForceShootDrain: cost 1;
- ForceTelepathy: L2 360°, L3 PVS (port mv:2361-2428, about 70 lines);
- CanCounterThrow: 1.02 version;
- ForceThrow: hand-extend block, own hand extend always set, 1200 ms push lockout, L1 without the usable check, no teammates, no eye retrace, no items/func_static, knockdown 128 / 1100 ms / quickerGetup;
- WP_ForcePowerRun: no grip drain; absorb 300; lightning and drain once per frame;
- DoGripAction: line of sight only below L3; absorb conversion every frame;
- WP_DoSpecificPower 5099: bots release push;
- WP_ForcePowersUpdate: 1.02 getup block (no wait, no rolls, no clearing); saber stays lit while gripped (5935); 1.02 regen once per frame (6097-6217).

**Server `g_combat.c`**
- no location damage (5076-5083);
- trueJedi ×0.5 (5290-5311);
- dismemberment: damage ≥ 20, saber kills only, bbox hit location, 1.02 limb physics (3044-3052, 3614-3830, 4421-4545, 6211-6220);
- protect sound on every hit;
- DAMAGE_NO_PROTECTION: decide.

**Server `g_weapon.c`**
- stun baton damage 20;
- disruptor range 8192 and bbox trace;
- bowcaster `Q_flrand(-1,1)`;
- rocketThink: unconditional push-down, plain velocity;
- WP_FireRocket: rocket not shootable;
- laserTrapStick alt = timed 2000 ms;
- drop_charge without +8;
- emplaced: MOD and alt spread;
- the Bryar velocity-scale bug (harmless).

**Server `g_missile.c`**
- bbox trace (1227);
- bounce decrement order (171);
- blade-contact block through the saber port's `WP_SaberCanBlock_JK2` (685-695);
- no flag punt (768);
- no inheritance or nudge (350).

**Server `g_items.c`**
- medpac 100 (63/1220);
- shield `height>>1` (350);
- suppress JKA-only items (3388/3406).

**Server `g_client.c`**
- spawn 125/25 in all gametypes (4757-4842);
- 1.02 loadout replacing GiveClientWeapons and 4552-4600 (saber or stun baton, + WP_BRYAR_OLD, pistol selected, 100 blaster ammo, JM stun baton);
- skip the model-scale bbox (~4855);
- `g_weaponDisable` bit translation for JK2 masks (optional).

**Server `g_active.c`**
- fall damage (1937-1967);
- kick-flip (5620-5800);
- pmove_msec clamp 8..33 (3782, also cg_predict.c:1184);
- duel end: health raised to max only, armor untouched, 1024 distance always (4470-4570).

**Server `g_cmds.c`**
- Cmd_EngageDuel_f in mode: the JK2 rules (one duel per server, so re-enable G_OtherPlayersDueling; FFA only; saber only; 256 trace; 10 s lockout);
- G_Give: refuse JKA-only items;
- saber style cycle (saber report).

**cgame**
- serverinfo flag;
- absorb shell always while absorb is active (cg_players.c:17199);
- absorb-hit event without trickedentindex (cg_event.c:2967);
- hide JKA-only weapons (cg_weapons.c:1138);
- read the speed stats for prediction;
- the saber report's cgame items.

**Bots (`ai_main.c`)**
- force-cost thresholds (18959-18986);
- weapon choice without CONC/MELEE/new Bryar, using WP_BRYAR_OLD;
- rocket alt lock;
- disruptor zoom while moving;
- push must be released;
- no wall-jump, dash or kick sequences;
- the saber report §3.6.

### 6.4 Rough size (on top of the saber port's ~3,000 lines)

| Area | Lines (estimate) |
|---|---|
| Force (`w_force.c` gating, the telepathy L3 port, regen, getups, throw rules) | 500-700 |
| Movement (`bg_pmove`, `bg_slidemove`, `bg_panimate`; mostly gating, plus the ported smash and step code, wall-flip-back, footsteps branch) | 600-900 |
| Weapons, items, loadout, damage, dismemberment | 400-600 |
| Match rules (duel, spawn, fall, kick) | 150-250 |
| Tables, cvar, cgame, prediction stats | 100-150 |
| Bots | 200-400 |
| **Total** | **about 2,000-3,000 lines**, about 5,000-6,000 including the saber port. The work is mostly gating; the real ports are ForceTelepathy L3, the 1.02 getups, StepSlideMove force-speed, the loadout and the JK2 duel command. |

---

## 7. Uncertain / needs testing

1. **mvsdk is 1.04 source with 1.02 deltas.** Weapons and missiles have no 1.02 checks at all. Any untracked 1.02 difference there is invisible. Spectator fly and swim anims are 1.03 code in mvsdk on purpose.
2. **SnapVector rounding.** JK2 x86 rounds to nearest (FPU). OpenJK's `SnapVector` truncates on x64, Linux and MinGW builds (`shared/qcommon/q_math.c:1245-1270`). That gives slightly lower jumps and different speed decay. Check which engine build ships; consider a round-to-nearest snap in bg code while the mode is on.
3. **Force speed on the client in real JK2.** If JK2 also did not network the speed level, JK2 clients mispredicted speed, and the server was authoritative. Our stat-based plan predicts it correctly, which is better than 1.02 but not identical in feel. Test on a real 1.02 server if possible.
4. **sv_fps.** Regen (4/s at sv_fps 20), lightning and drain ticks, and the absorb/grip-from-absorb gains depend on the frame rate in 1.02. "Exact" assumes sv_fps 20, which is JK2's default. Confirm our server's sv_fps.
5. **Rocket lock in ours.** By reading the code, the server never locks outside racemode while the cgame predicts a lock. Test whether homing rockets work at all today.
6. **Weapon raise time.** Game +50 vs cgame +250 in ours (bg_pmove.c:9119 vs 9121). Check whether this is intended jaPRO fast-switch or a prediction bug.
7. **Custom anims.** FLIP_F, FORCEJUMP1, FORCELAND1 and LAND1 in `japro-assets.pk3` differ from JK2/JKA. Exact timing needs the vanilla values. Patching numFrames at load in the mode would replay a subset of the custom `.gla` frames, so poses would still differ. Decide between vanilla assets in mode (a separate pk3 or skeleton) or accepting the difference.
8. **BUTTON_TALK.** JK2 keys it on the client protocol, not on gameplay. Allowing movement with the console open is the 1.02 feel but helps "chat-walk" abuse. Decide.
9. **ZStart = 0 "hold jump over slopes"** and the in-air jump rules: test on ramps and walls, especially together with the custom anims.
10. **Grip vs Absorb** gives the absorber a large force gain every frame in 1.02. Confirm in game that this is wanted, since it is the 1.02 behaviour.
11. **PM_ClientImpact** (breakable brushes): turning it off in mode changes map behaviour; keeping it gives a small server-only difference.
12. **ANIM_TOGGLEBIT** emulation (saber report §1.14) interacts with InRoll, InSpecialJump and FlippingAnim. Test rolls and flips once both are ported.
13. **Det pack splash radius** and the emplaced weaponData row were only read as "equal on both sides"; re-read them if a test shows a difference.
14. **Jedi Master and Holocron** were compared only for regen, the damage filter and the loadout.
15. **`quickerGetup` and `forceHandExtendTime` are not networked** (OpenJK msg.cpp sends `forceHandExtend` and `forceDodgeAnim` only). The getup choice is made in server-only `w_force.c` code and reaches the client through `forceDodgeAnim`, so this matches how JK2 works. No action is needed. Just do not move getup decisions into the shared code.
16. **Bots**: re-tune once costs, regen and push change. Bot force-use thresholds assume JKA costs.
