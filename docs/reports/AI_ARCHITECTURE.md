# Bot AI architecture map: codemp/game/ai_main.c (+ ai_main.h)

Repo `TaystJK_AI-Improved-Bots`, branch `claude/korriban-bot-perf`. ai_main.c is 15,093 lines / 420 KB; ai_main.h is 595 lines. Source was read only; nothing was built or run.

**Coverage.** Every line of both files was read, in seven regions (1-2700, 2690-5800, 5790-8700, 8680-11215, 11205-12945, 12940-15093, plus git history and cvars). Sections 5-7 and 10 are kept per region, so each note sits next to the lines it was read from. Trace totals in section 4b are estimates from reading, not measurements.

**`JP_Trace` is the trace call.** Most call sites use `JP_Trace` (g_syscalls.c:259), which wraps `trap->Trace` in BeginHack/EndHack: two full loops over `level.num_entities` per call, on top of the collision trace itself. A few sites call `trap->Trace` directly. Both are counted as traces below.

## Key facts

| Fact | Where |
|---|---|
| Every bot runs its full think on every `BotAIStartFrame` call; `BOT_THINK_TIME` is 0 and `bot_thinktime` is never read | ai_main.c:60, 14913 |
| A "timeout" block in `BotAIStartFrame` skips one whole bot frame about every 100 ms | ai_main.c:14917-14924 |
| `g_newBotAI` picks `NewBotAI` (12943), otherwise `StandardBotAI` (13332) | ai_main.c:820-823 |
| With gWPNum == 0, `GetNearestVisibleWP` returns -1 with no traces and `GetIdealDestination` returns at once, so all waypoint, CTF, siege and bad-thing logic is skipped | ai_main.c:1262, 3963 |
| With gWPNum == 0, navigation is `BotFallbackNavigation`: 2 traces per call at minimum, up to about 86 while it searches for a target, with no back-off | ai_main.c:5336, called from 14085 and 12770 |
| `ScanForEnemies` runs every frame per bot because its gate is a tautology | ai_main.c:13818-13821, 2453 |
| `NewBotAI_GetAttack` runs twice per bot per frame, so `Bot_ExecuteSaberCombat`'s traces are paid twice | ai_main.c:13052-13060 and 13237; 14186 |
| `BotTrace_Jump` always returns 0 before tracing, because `dist` is the length of a normalised vector | ai_main.c:1776-1791 |
| The only profiling is a `_DEBUG` `trap->Milliseconds` print around the think, with 1 ms resolution | ai_main.c:817-833 |

## 1. Entry points and lifecycle

All line refs are ai_main.c unless another file is named.

### Call chain and rate
- `SV_Frame` (server/sv_main.cpp) -> `SV_BotFrame(time)` (server/sv_bot.cpp:605; returns if `!bot_enable` or `!svs.gameStarted`) -> `GVM_BotAIStartFrame` (server/sv_gameapi.cpp:140) -> `BotAIStartFrame` (14913; exported g_main.c:4606 / vmMain g_main.c:4691).
- Listen server (`!com_dedicated`): sv_main.cpp:1247 calls `SV_BotFrame(sv.time + sv.timeResidual)` on EVERY `SV_Frame` call, i.e. every client/render frame (com_maxfps), BEFORE and independent of the `while (sv.timeResidual >= frameMsec)` game loop at sv_main.cpp:1293. So on a listen server bots think at render fps, not sv_fps.
- Dedicated: sv_main.cpp:1290 calls `SV_BotFrame(sv.time)` once per `SV_Frame` call, just before the game-sim loop. `Com_Frame` (qcommon/common.cpp:1749-1750) sleeps `SV_FrameMsec()` on dedicated, so this is approximately once per server frame (sv_fps). If SV_Frame is entered without sv.time advancing, elapsed_time is 0 and bots still think (see below).
- Also called 4 times while loading a map (server/sv_init.cpp:634 in a loop, 694).
- Bot movement itself is applied once per game frame: `trap->BotUserCommand` -> `SV_BotUserCommand` -> `SV_ClientThink` (sv_gameapi.cpp:1240-1242) only stores the cmd; `ClientThink` skips `ClientThink_real` for SVF_BOT (g_active.c:5982) and `G_RunClient` runs it once per G_RunFrame with `pers.cmd.serverTime = level.time` (g_active.c:6117-6121).

### BotAISetup (15027-15068), called from G_InitGame g_main.c:462
1. 15029-15049 register cvars: bot_forcepowers, bot_forgimmick, bot_honorableduelacceptance, bot_pvstype, bot_getinthecarrr (non-FINAL_BUILD), bot_nogoals + bot_debugmessages (_DEBUG only), bot_attachments, bot_camp, bot_wp_info, bot_wp_edit, bot_wp_clearweight, bot_wp_distconnect, bot_wp_visconnect. 15051 Cvar_Update(bot_forcepowers).
2. 15055 `if (restart) return qtrue` (map_restart keeps botstates).
3. 15060 `memset(botstates, 0, sizeof(botstates))` (pointers dropped without B_Free).
4. 15062 `trap->BotLibSetup()`; failure returns qfalse.
- No loops, no per-bot work. `numbots` (line 65) is not reset here.
- The engine cvar `bot_thinktime` (sv_bot.cpp:668, default 100) is NOT read anywhere in the game module (grep: only that one registration). It has no effect.

### BotAIShutdown (15075-15093), called from G_ShutdownGame g_main.c:670
- restart: loop i<MAX_CLIENTS (15082), `BotAIShutdownClient(botstates[i]->client, restart)` for in-use bots (frees move/goal/weapon states, memsets the bot_state_t, numbots--; 1012-1045). Bot library kept.
- non-restart: only `trap->BotLibShutdown()` (15090). botstates memory is not freed here and numbots is not touched.

### BotAIStartFrame (14913-15020), step by step
1. 14917-14924 "timeout protection": `current_time = trap->Milliseconds()`; `if (current_time - last_frame_time > 100) { last_frame_time = current_time; return qtrue; }`. `last_frame_time` is a static that is ONLY written inside this branch. Effect: the first call after every 100 ms of wall-clock time is skipped entirely (no AI, no usercmd, no G_CheckBotSpawn, no UpdateEventTracker). See F_bugs. `BotAI_Print` is an empty stub (356) so nothing is printed.
2. 14926-14944 loop i<MAX_CLIENTS that only executes `continue` statements: dead validation loop (redundant bounds check at 14928).
3. 14951-14962 once per 1000 ms of level.time (`gUpdateVars`): Cvar_Update for bot_pvstype, bot_camp, bot_attachments, bot_forgimmick, bot_honorableduelacceptance, bot_getinthecarrr.
4. 14964 `G_CheckBotSpawn()` (g_bot.c:777: G_CheckMinimumPlayers + spawn queue loop) every call.
5. 14967-14971 `if (gBotEdit)` (waypoint editor, set in ai_wpnav.c:3319): Cvar_Update(bot_wp_info) + `BotWaypointRender()` (ai_wpnav.c:243). Off in normal play.
6. 14973 `UpdateEventTracker()` (2332): loop 32 clients copying ps.eventSequence/events into gBotEventTracker; every call.
7. 14978-14981 `if (BOT_THINK_TIME != lastbotthink_time)`: BOT_THINK_TIME is `#define ... 0` (line 60) and the static starts at 0, so `BotScheduleBotThink()` is never called from here (it is called from BotAISetupClient:961; with BOT_THINK_TIME 0 it sets every residual to 0).
8. 14983-14987 `elapsed_time = time - local_time; local_time = time; thinktime = (elapsed_time > 0) ? elapsed_time : 0`.
9. 14990-15004 AI loop over MAX_CLIENTS: for each in-use botstate, `botthink_residual += elapsed_time; if (botthink_residual >= thinktime) { botthink_residual -= thinktime; if (CON_CONNECTED) BotAI(i, thinktime/1000.0f); }`. Because thinktime == elapsed_time, the test is always true -> EVERY bot runs full AI on EVERY non-skipped BotAIStartFrame call. There is no staggering, no level.time gate, no throttle. `gDeactivated` is not tested here (only inside StandardBotAI at 13360; NewBotAI ignores it).
10. 15007-15017 input loop over MAX_CLIENTS: for each connected bot `BotUpdateInput(bs, time, elapsed_time)` (677: add delta angles, `BotChangeViewAngles` toward ideal_viewangles, `trap->EA_GetInput`, `BotInputToUserCommand` (561) into bs->lastucmd) then `trap->BotUserCommand(client, &bs->lastucmd)`. Sent every non-skipped call, regardless of whether the bot thought. On skipped calls (step 1) nothing is sent and the game reuses the previous pers.cmd.
- `BotAIRegularUpdate` (706, trap->BotUpdateEntityItems every 0.3 s) is defined but has NO callers (grep).

### BotAI (740-841) wrapper per bot
- 744-759 validation; 768 `trap->EA_ResetInput`; 777 `BotAI_GetClientState` (memcpy of the whole playerState_t, 386); 780-801 drain server commands (parsed and ignored); 803-814 view angles, ltime, origin, eye.
- 817-833 `#ifdef _DEBUG` `trap->Milliseconds()` around the think + `trap->Cvar_Update(&bot_debugmessages)` and optional Com_Printf per bot per frame.
- 820-823 `g_newBotAI.integer ? NewBotAI : StandardBotAI` (g_newBotAI default "0", g_xcvar.h:349).


## 2. Per-bot per-frame call order

### 2a. StandardBotAI per-frame call order

(13332-14904). "T:" = trace cost of the step. Every step runs each think unless a gate is given.

1. 13353-13358 function-level `static` locals (shared by ALL bots): lastStuckCheckPos, lastStuckCheckTime, stuckCounter, lastUnstuckDirection (unused), lastBackupTime/consecutiveBackups (shadowed at 14482-14483).
2. 13360-13367 `gDeactivated` -> clear wpCurrent/currentEnemy/wpDestination, return.
3. 13369-13378 spectator -> same clear, return.
4. 13381-13436 (non-FINAL_BUILD) `bot_getinthecarrr`: vehicle debug, loop MAX_GENTITIES (13405), return.
5. 13438-13499 `bot_forgimmick`: clear state, scripted movement / forceMove_*, return.
6. 13501-13504 init lastDeadTime.
7. 13506-13550 dead (`health < 1`): BotDeathNotify + death chat once (13510-13530), clear wpCurrent/currentEnemy/wpDestination/wpCamping/wpCampingTo/wpStoreDest and wp timers, 50% EA_Attack to respawn, return. T: 0.
8. 13552 save goalAngles -> preFrameGAngles; 13554-13555 doAttack = doAltAttack = 0.
9. 13558-13565 `isSquadLeader ? CommanderBotAI(bs) : BotDoTeamplayAI(bs)`. CommanderBotAI only does work in GT_CTF/CTY/SIEGE/TEAM (4574-4588; teamplay variant loops MAX_CLIENTS). T: 0 (teamplay); CTF/Siege not determined.
10. 13567-13570 no enemy -> frame_Enemy_Vis = 0.
11. 13572-13583 drop revengeEnemy / currentEnemy whose client is neither CON_CONNECTED nor CON_CONNECTING.
12. 13585-13592 fjHalt = 0; `forceJumpChargeTime > level.time` -> useTheForce = 1.
13. 13594-13612 if currentEnemy && client && frame_Enemy_Vis (value left from the PREVIOUS think) && forceJumpChargeTime < level.time, and (force not fully disabled || g_flipKick || weapon != saber): call NewBotAI_LSvLS / DSvLS / LSvDS / DSvDS (11884-12172): NewBotAI_GetAim, getup/grip reactions, active-power handlers, NewBotAI_GetMovement (10860), NewBotAI_GetDS/LSForcepower, NewBotAI_GetAttack (10513 -> Bot_SelectOptimalSaberStyle + Bot_ExecuteSaberCombat when holding saber). T: GetMovement up to ~9 line traces (estimate, 6 sites + Bot_CheckMovementPaths 3), force handlers 0-1, SaberCombat 1-3.
14. 13614-13616 doingFallback = 0; deathActivitiesDone = 0.
15. 13618-13624 BotUseInventoryItem -> 50% EA_Use.
16. 13626-13668 weapon selection: out of ammo -> BotTryAnotherWeapon (return if switched). Else forceWeaponSelect handling, plantContinue (doAttack), det pack select, BotSelectChoiceWeapon (return if newly selected) or BotSelectIdealWeapon (return if switching).
17. 13674-13688 reaction = skills.reflex / settings.skill clamped 0..2000 ms; while no enemy `timeToReact = level.time + reaction`.
18. 13690-13693 det pack alt-fire.
19. 13695-13708 camping timeout / cancel when enemy visible.
20. 13710-13714 waypoint timeout: drop wpCurrent if `wpSeenTime < level.time || wpTravelTime < level.time`.
21. 13716-13743 enemy forget: if `enemySeenTime < level.time || !PassStandardEnemyChecks` -> kill chat, currentEnemy = NULL.
22. 13745-13802 `bot_honorableduelacceptance` duel challenge/accept logic (enemy with holstered saber within 400u in 100deg FOV); sets beStill +100 ms.
23. 13806-13816 waypoint acquisition: `if (!wpCurrent) wp = GetNearestVisibleWP(origin, client)`; on success wpSeenTime = +1500, wpTravelTime = +10000. No retry timer. T: 1 box trace per WP within 800u that is in PVS and closer than best (0 when gWPNum == 0).
24. 13818-13829 enemy scan: condition is a tautology -> `ScanForEnemies(bs)` every think. If it returns an index: currentEnemy = that ent, enemySeenTime = +ENEMY_FORGET_MS (10000, ai_main.h:76), and `NewBotAI_DoAloneStuff(bs, thinktime)` is called (13827). T: scan = 1 unbounded line trace per candidate in FOV/heard and closer than running best; DoAloneStuff = see section 6.
25. 13831-13844 squad leader bookkeeping: BotScanForLeader (loop 32) while leaderless; become leader when squadCannotLead < level.time; leaders clear squadLeader.
26. 13847-13896 waypoint visibility (only if wpCurrent): frame_Waypoint_Len; `WPOrgVisible` (T: 1-2 lines). visResult 2 (blocked by door/mover) -> wpSeenTime = 0, wpDestination = NULL, wpDestIgnoreTime = +5000, flip wpDirection.
27. 13898-13930 enemy visibility: frame_Enemy_Len; `OrgVisible(eye, enemy eye)` (T: 1 unbounded line) -> frame_Enemy_Vis, lastEnemySpotted, hereWhenSpotted, lastVisibleEnemyIndex = enemy entnum, hitSpotted = 0. No enemy -> lastVisibleEnemyIndex = ENTITYNUM_NONE.
28. 13933-13936 visible -> enemySeenTime = +10000.
29. 13938-14080 waypoint branch (wpCurrent != NULL):
    - 13941 WPConstantRoutine (may NULL wpCurrent -> return at 13945). T: 0.
    - 13948-13961 CheckForFunc for WAITFORFUNC / NOMOVEFUNC flags (T: 0-2 lines 64u), beStill +500.
    - 13963-13973 if waypoint visible or NOVIS: wpSeenTime = +1500 (+5000 RMG).
    - 13974 goalPosition = wpCurrent->origin; 13975-13982 goalWPIndex = index -/+ 1.
    - 13984-14014 goalAngles: camping target, else next waypoint (point prediction), else current waypoint.
    - 14016-14019 `if (destinationGrabTime < level.time) GetIdealDestination(bs)`.
    - 14021-14028 TotalTrailDistance(wpCurrent, wpDestination) == -1 -> drop destination, destinationGrabTime +10000.
    - 14030-14079 touch test (frame_Waypoint_Len < 32, RMG larger): WPTouchRoutine, advance to next index if valid and PassWayCheck, else drop destination and flip direction.
30. 14081-14087 no waypoint: `if (weapon == WP_SABER) doingFallback = BotFallbackNavigation(bs)`. Non-saber bots get NO fallback. T: 0 / 2-6 / up to ~80+.
31. 14089-14104 RMG only: area-change tracking, sets iHaveNoIdeaWhereIAmGoing.
32. 14106-14116 `iHaveNoIdeaWhereIAmGoing > level.time && !currentEnemy` (RMG only in practice): restore goalAngles, wpCurrent = NULL, BotFallbackNavigation again, jump timers.
33. 14118-14171 RMG only: jump toward high waypoints / flags.
34. 14173-14180 bs->doingFallback = doingFallback.
35. 14182-14257 fire/aim block, gate: `timeToReact < level.time && currentEnemy && enemySeenTime > level.time + 8000` (enemy seen in the last 2 s):
    - visible: 14186 NewBotAI_GetAttack (T: SaberCombat 1-3 with saber; second call this frame if step 13 ran).
    - not visible: keep charging if weaponstate CHARGING / CHARGING_ALT (14188-14195).
    - 14197-14200 clamp destinationGrabTime to level.time + 100.
    - 14202-14210 headlevel.
    - not visible: 14215 OrgVisible(eye, lastEnemySpotted) (T: 1 line) -> aim at last spot; flechette alt-fire block (broken, see F_bugs).
    - visible: 14242-14248 BotPredictEnemyPosition -> goalAngles; 14255 BotAimOffsetGoalAngles.
36. 14259-14262 saber in flight -> saberThrowTime = +4..10 s.
37. 14267-14331 saber / melee (gate: currentEnemy, no visibility requirement):
    - saber range weapon: Bot_SelectOptimalSaberStyle; if frame_Enemy_Len <= 128: BotUpdateAttackTiming, BotUpdateDynamicMovement, BotShouldAttackNow (T: 0-1 box) -> BotExecuteAttack; BotShouldStrafeInCombat -> meleestrafe. Saber throw decision 14308-14320.
    - melee range weapon and <= 256u: MeleeCombatHandling (T: 3 box 4096u down), meleestrafe = 1.
38. 14333-14359 chat: while a chat is pending and no visible enemy -> RETURN (bot idles until chatTime); otherwise send EA_Say / EA_SayTeam, BotReplyGreetings.
39. 14361 CTFFlagMovement (T: 0-1).
40. 14363-14383 shootGoal (objective): aim, EntityVisibleBox (T: 0-1), doAttack.
41. 14385-14445 det pack / trip mine: BotCheckDetPacks if planted; else planting logic when enemy lost (BotSelectChoiceWeapon, BotSurfaceNear T: 1; may return at 14431/14436); else clear forceWeaponSelect.
42. 14447-14462 Jedi Master saber pickup (T: 0-1).
43. 14464-14677 movement block, gate `beStill < level.time && !WaitingForNow(bs, goalPosition) && !fjHalt`:
    - 14471-14477 wall check: box trace 32u along view forward (T: 1, every time).
    - 14479-14530 wall < 16u: consecutive-backup logic (function statics shared by all bots); 3rd time: jump + yaw +90 + MoveTowardIdealAngles + RETURN (14510); otherwise 60% strafe / 40% back, beStill = +300, `goto skip_movement`.
    - 14534-14593 stuck detection once per 1000 ms GLOBALLY (statics shared by all bots): jump / random move / 180 turn.
    - 14595-14606 goalMovedir = normalize(goalPosition - origin); `trap->EA_Move(client, goalMovedir, 5000)` unless mid-jump (beStill +200).
    - 14610-14618 if attacking: BotMovementDuringAttack; `goto skip_movement` while attackRecoveryTime > level.time.
    - 14621 BotDynamicCombatMovement.
    - 14624-14644 melee strafe (40% per frame) when in saber range and not attacking.
    - 14646 BotTrace_Jump (T: effectively 0) -> jumpTime +100.
    - 14650 else BotTrace_Duck (T: 2, up to ~14) -> 10% duck.
    - 14665 else BotTrace_Strafe (T: 1-3) -> EA_MoveRight/Left.
44. 14679-14684 forceJumpChargeTime -> jumpTime = 0.
45. `skip_movement:` 14688-14729 jump prep/hold handling, EA_Jump, EA_MoveForward while holding jump, PMF_JUMP_HELD.
46. 14731-14734 EA_Crouch while duckTime.
47. 14736-14770 dangerousObject: aim + EntityVisibleBox (T: 0-1) + doAttack.
48. 14772-14828 friend in line of fire: if PrimFiring/AltFiring -> CheckForFriendInLOF (T: 1 box 2048u), suppress fire, team heal/energize; ELSE in team gametypes -> CheckForFriendInLOF every think (14811).
49. 14830-14867 attack vetoes: det pack already planted, saberDefending vs blockable weapon, saber lock mashing (50%), botChallengingTime, saber knocked away.
50. 14869-14876 EA_Attack / EA_Alt_Attack.
51. 14878-14901 force use: FP_LEVITATION while charging jump, else EA_ForcePower if bot_forcepowers && !g_forcePowerDisable.
52. 14903 MoveTowardIdealAngles: ideal_viewangles = goalAngles (1669).

### 2b. NewBotAI per-frame call order

(12943-13327)

1. 12952 isCamper = 0.
2. 12954-12956 racemode -> return.
3. 12958-12961 dead -> EA_Attack (respawn), return.
4. 12963-12964 amfreeze -> return.
5. 12966-12978 target selection: g_newBotAITarget < 0 (default) -> `closestID = NewBotAI_ScanForEnemies(bs)` (12856: loop 32, PassStandardEnemyChecks + InPVS + PassLovedOneCheck, score = distance x health factor, gripper gets priority; NO line-of-sight, NO FOV, NO max range; `hasEnemyDist` is always 0 so no stickiness). Else forced target id with connection check. T: 0.
6. 12980-12989 MV_TRIBES: suicide if no route and no enemy; `NewBotAI_CapRoute` (return if handled).
7. 12991-12998 `closestID == -1` -> `NewBotAI_DoAloneStuff(bs, thinktime)`, return.
8. 13000-13002 frame_Enemy_Vis = 0; headlevel.
9. 13004-13027 visibility / enemy choice:
    - DEMP2 or forced target or `OrgVisible(eye, enemy origin)` (T: 1 unbounded line) -> currentEnemy = closest, frame_Enemy_Vis = 1, lastVisibleEnemyIndex = level.time (used as a TIMESTAMP here).
    - else PERS_ATTACKER passes PassStandardEnemyChecks -> currentEnemy = attacker, `OrgVisible(eye, attacker head)` (T: 1) -> frame_Enemy_Vis; lastVisibleEnemyIndex = level.time regardless of the result (13018).
    - else currentEnemy = closest; if lastVisibleEnemyIndex older than 10 s -> DoAloneStuff, return.
10. 13029 enemySeenTime = level.time + 10000 (unconditional); 13030 frame_Enemy_Len = NewBotAI_GetDist.
11. 13032-13039 `!frame_Enemy_Vis && frame_Enemy_Len > 300` -> DoAloneStuff, return.
12. 13041-13044 Tribes + jetpack -> NewBotAI_Tribes, return.
13. 13049-13227 combat (gate: force not fully disabled || g_flipKick || weapon != saber; else `NewBotAI_NF(bs)` at 13226, 0 traces):
    - 13050-13061 NewBotAI_LSvLS / DSvLS / LSvDS / DSvDS (GetAim, GetMovement, force, GetAttack). T: as 2a step 13.
    - 13067 if frame_Enemy_Vis:
        - saber range weapon (13069-13114): Bot_SelectOptimalSaberStyle; <= 128u: BotUpdateAttackTiming, BotUpdateDynamicMovement, BotShouldAttackNow (T: 0-1) -> BotExecuteAttack; saber throw decision.
        - melee range weapon <= 256u (13118-13123): MeleeCombatHandling (T: 3).
        - 13129-13160 four box traces 32u fwd/back/left/right (T: 4, every think).
        - 13163-13217 distance-banded movement (<64 retreat, <128 circle strafe, <256 approach, else approach).
        - 13220-13222 1.5% flip meleeStrafeDir.
14. 13232-13308 "timing and aiming", gate `timeToReact < level.time && currentEnemy && enemySeenTime > level.time + 8000`. enemySeenTime was just set at 13029 so that part is always true; timeToReact is never written by NewBotAI (only by StandardBotAI 13687), so normally always true.
    - visible: 13237 NewBotAI_GetAttack AGAIN (T: SaberCombat 1-3); clamp destinationGrabTime; headlevel; 13254 `if (!frame_Enemy_Vis)` is unreachable here (dead OrgVisible at 13257); else BotPredictEnemyPosition -> goalAngles, BotAimOffsetGoalAngles. NOTE: NewBotAI never calls MoveTowardIdealAngles, so goalAngles written here is not copied to ideal_viewangles by this function.
    - not visible: keep charging (13300-13307).
15. 13310-13313 saber in flight -> saberThrowTime.
16. 13320 Bot_CheckAndInteractWithObstacle call is commented out.
- NewBotAI does not reset doAttack/doAltAttack, does not honour gDeactivated / spectator / bot_forgimmick, does not run chat, CTF, squad, det pack, friend-in-LOF or waypoint logic except through DoAloneStuff.


## 3. Function index (every function in ai_main.c)

| Name | Line | Approx. lines | Purpose | Callers and frequency | Cost: traces and loops |
|---|---|---|---|---|---|
| ValidBotClient (static) | ai_main.c:145 | 7 | bounds + inuse + CON_CONNECTED check for a client index | UNUSED (no call site in codemp/game) | none |
| BotStraightTPOrderCheck | ai_main.c:153 | 28 | apply a teamplay order to bs (squadLeader/teamplayState) | BotOrder 264, 286 only; event-only (and BotOrder itself has no caller) | none |
| BotSelectWeapon | ai_main.c:182 | 9 | trap->EA_SelectWeapon wrapper (ignores <= WP_NONE) | 5810, 5822, 5874, 5988, 6023, 6043, 10525, 12518; per-frame via weapon-select paths (outside region) | 1 EA syscall |
| BotReportStatus | ai_main.c:192 | 15 | team-say current state description | BotOrder 260, 282; event-only | none |
| BotOrder | ai_main.c:209 | 92 | accept a team order from a human team leader | no caller found in codemp/game (*.c,*.h); only declared g_local.h:2032 -> effectively UNUSED | loop i<MAX_CLIENTS (276) when clientnum==-1 |
| BotMindTricked | ai_main.c:303 | 47 | is bot in enemy's mind-trick bitmask | 2129 (PassStandardEnemyChecks), 2318 (BotCanHear), 2485+2487 (ScanForEnemies loop), 5027, 12917; per-frame, several times per candidate | none; no bounds check on enemyClient |
| BotAI_Print | ai_main.c:356 | 1 | no-op stub (`{ return; }`) | 745,751,757,772,893,899,905,912,14921; all error paths are silent | none |
| IsTeamplay | ai_main.c:360 | 9 | gametype >= GT_TEAM | 2430, 2434, 6112, 6394, 6430 | none |
| BotAI_GetClientState | ai_main.c:375 | 14 | memcpy client ps into bs->cur_ps | BotAI 777; per bot per server frame | 1 memcpy sizeof(playerState_t) |
| BotAI_GetEntityState | ai_main.c:395 | 11 | copy entityState if linked/visible | only BotAI_GetSnapshotEntity 421 (itself unused) -> UNUSED | memset+memcpy |
| BotAI_GetSnapshotEntity | ai_main.c:412 | 13 | Q3 leftover snapshot iterator | UNUSED | 1 syscall |
| BotEntityInfo | ai_main.c:431 | 3 | trap->AAS_EntityInfo wrapper | UNUSED | 1 syscall |
| NumBots | ai_main.c:440 | 3 | returns numbots | UNUSED in codemp/game (declared ai_main.h:540) | none |
| AngleDifference | ai_main.c:449 | 12 | signed angle diff | 540 (BotChangeViewAngles, 2x per frame per bot), 1698+1699 (BotTrace_Strafe), 11134 | none |
| BotChangeViewAngle | ai_main.c:467 | 21 | step one angle toward ideal (Q3 leftover) | UNUSED | none |
| BotChangeViewAngles | ai_main.c:494 | 61 | turn viewangles toward ideal_viewangles with skill-scaled speed; g_newBotAI forces maxchange 1800 (531) | BotUpdateInput 686; per bot per server frame (not throttled) | loop i<2; 1 EA_View syscall |
| BotInputToUserCommand | ai_main.c:561 | 110 | convert bot_input_t to usercmd; random BUTTON_USE 40% of frames when noUseTime < level.time (589); `u = 0` edit (639) | BotUpdateInput 694; per bot per server frame | AngleVectors, 1 Q_irand; no traces here (BUTTON_USE may trigger TryUse trace in game code - not verified) |
| BotUpdateInput | ai_main.c:677 | 23 | apply delta angles, turn, EA_GetInput, build usercmd | BotAIStartFrame 15015; per bot per server frame | 2 syscalls (EA_View, EA_GetInput) |
| BotAIRegularUpdate | ai_main.c:706 | 6 | 0.3s-throttled trap->BotUpdateEntityItems | UNUSED | - |
| RemoveColorEscapeSequences | ai_main.c:718 | 15 | strip color codes in place | BotAI 787, once per queued server command per bot per frame (result is discarded - all branches at 789-800 are empty) | O(strlen) |
| BotAI | ai_main.c:740 | 102 | per-bot think: reset EA input, copy ps, drain server cmds, set origin/eye, call NewBotAI or StandardBotAI | BotAIStartFrame 15001; per bot per server frame (BOT_THINK_TIME 0 at line 60 => no throttling), minus frames skipped by the 14920 "timeout" | 1 ps memcpy; while-loop over pending server commands (each a syscall, buf[1024]); debug: 2x trap->Milliseconds + Cvar_Update per bot per frame |
| BotScheduleBotThink | ai_main.c:848 | 14 | stagger botthink_residual (all 0 since BOT_THINK_TIME==0) | BotAISetupClient 961; BotAIStartFrame 14980 (never fires: static lastbotthink_time==0==BOT_THINK_TIME) | loop MAX_CLIENTS |
| PlayersInGame | ai_main.c:863 | 20 | count connected clients | BotAISetupClient 999; event-only | loop MAX_CLIENTS |
| BotAISetupClient | ai_main.c:889 | 117 | allocate + init bot_state_t, personality, botlib states, greeting chat | g_bot.c:855; event-only (bot connect) | B_Alloc (BG_Alloc pool, never freed); BotUtilizePersonality (file parse, ai_util.c); 2 MAX_CLIENTS loops |
| BotAIShutdownClient | ai_main.c:1012 | 34 | free botlib move/goal/weapon states, memset bs, numbots-- | g_client.c:5191; BotAIShutdown 15084; event-only | none; does not free/NULL botstates[client] |
| BotResetState | ai_main.c:1055 | 36 | wipe bs except ms/gs/ws/cur_ps/settings/inuse/client/entitynum/entergame_time | BotAILoadMap 1102 only; event-only | 2 memcpy of playerState_t, 5 botlib syscalls |
| BotAILoadMap | ai_main.c:1097 | 12 | BotResetState on all in-use bots | g_main.c:463 (G_InitGame); event-only | loop MAX_CLIENTS |
| OrgVisible | ai_main.c:1113 | 13 | line-of-sight test | 2485 (ScanForEnemies loop, per frame), 6597, 7217, 7252, 7263, 13004, 13016, 13257, 13913, 14215, 14457; external: ai_wpnav.c:1514, w_force.c:4667/5212/5345 | 1 line trace MASK_SOLID, unbounded length |
| WPOrgVisible | ai_main.c:1128 | 30 | LOS to waypoint, plus force-field (ET_SPECIAL) ownership check; returns 0/1/2 | StandardBotAI 13870; per bot per frame whenever bs->wpCurrent (no timer) | 1 line trace MASK_SOLID; +1 line trace MASK_PLAYERSOLID when first is clear => normally 2 traces/frame/bot |
| OrgVisibleBox | ai_main.c:1160 | 20 | hull visibility (line if RMG) | 1269 (GetNearestVisibleWP loop); external ai_wpnav.c:1701, 1857 | 1 box trace MASK_SOLID (caller box 30x30x2) |
| CheckForFunc | ai_main.c:1184 | 31 | is there a func_* entity within 64u below org | WaitingForNow 2546, 2552 (per frame, distance-gated); StandardBotAI 13950, 13957 (per frame while wpCurrent has WAITFORFUNC / NOMOVEFUNC flag, no timer) | 1 line trace MASK_SOLID 64u down + strstr on classname |
| BotPVSCheck | ai_main.c:1217 | 16 | RMG: distance<=5000; else trap->InPVS | 1269 (GetNearestVisibleWP loop), 2474 (ScanForEnemies loop), 2775 (GetNearestBadThing loop), 3671, 3696, 3720, 12894 | 1 trap->InPVS (two leaf lookups in engine) |
| GetNearestVisibleWP | ai_main.c:1235 | 46 | nearest in-use waypoint within 800u (300 RMG) that is in PVS and box-visible | 13808 (StandardBotAI, EVERY frame while !bs->wpCurrent, no timer); 12570 (NewBotAI_DoAloneStuff, every call while !wpCurrent); 2949, 3015, 3514, 3791, 3795, 4122, 4145, 4201 (CTF/Siege/JM/GetIdealDestination, gated by bs->destinationGrabTime at 14016; inner gating outside region); ai_wpnav.c:1787 | loop i<gWPNum with VectorLength each; per candidate closer than current best: 1 InPVS + 1 box trace (30x30x2, MASK_SOLID, <800u). Worst case = number of PVS-visible WPs within 800u (if iterated far-to-near). gWPNum==0 => 0 traces, returns -1 |
| PassWayCheck | ai_main.c:1288 | 34 | may bot step to WP windex (one-way flags, force-jump level) | 12593, 14058; on waypoint touch (per frame while within touch distance) | none; no index bounds check |
| TotalTrailDistance | ai_main.c:1324 | 67 | sum disttonext between two WP indices; -1 if invalid/one-way | 14023 (StandardBotAI, EVERY frame when wpCurrent && wpDestination, no timer); 1434, 1438 (CheckForShorterRoutes); 2951, 3017, 4124, 4147, 4203; 3924 (inside GetBestIdleGoal loop over gWPNum => O(gWPNum^2) worst) | loop abs(start-end) <= gWPNum; no traces |
| CheckForShorterRoutes | ai_main.c:1394 | 87 | on touching a WP, see if a neighbor gives a shorter trail to wpDestination; switch wpCurrent | WPTouchRoutine 1660 only; event (WP touch), gated by bs->wpSwitchTime (3000 ms, set 1464) | (1 + neighbornum) x TotalTrailDistance => O(neighbors * gWPNum); no traces |
| WPConstantRoutine | ai_main.c:1484 | 71 | per-frame handling of DUCK/JUMP/forceJumpTo flags on wpCurrent | 13941 (StandardBotAI, per frame with wpCurrent); 12601 (NewBotAI_DoAloneStuff) | none |
| BotCTFGuardDuty | ai_main.c:1557 | 14 | CTF defender? | WPTouchRoutine 1606 | none |
| WPTouchRoutine | ai_main.c:1576 | 88 | on reaching wpCurrent: travel timer, jump flag, camping setup, destination reached, CheckForShorterRoutes | 14043 (per frame while frame_Waypoint_Len < touch dist), 12586 | no traces; may call BotIsAChickenWuss, CheckForShorterRoutes |
| MoveTowardIdealAngles | ai_main.c:1667 | 4 | copy goalAngles -> ideal_viewangles | 13424, 14506, 14577, 14903 (per frame) | none |
| BotTrace_Strafe | ai_main.c:1680 | 78 | obstacle ahead? try side-step right then left | StandardBotAI 14665; per frame per bot in movement block (14464) when BotTrace_Jump and BotTrace_Duck both return 0 | 0 traces (airborne or yaw diff > 60); else 1-3 box traces (30x30x48 box, MASK_PLAYERSOLID, 32u) |
| BotTrace_Jump | ai_main.c:1762 | 104 | intended: jump over obstacle / pit / fence | StandardBotAI 14646; per frame per bot in movement block | AS WRITTEN: always returns 0 at 1790 with 0 traces (dist is length of a normalized vector). If fixed: 2-6 box traces/frame (30x30x50, MASK_PLAYERSOLID, 48-128u) |
| BotTrace_Duck | ai_main.c:1868 | 193 | overhead obstacle? with ledge/wall/altitude sanity checks | StandardBotAI 14650; per frame per bot in movement block (since Jump always returns 0) | 1 trace (lower box blocked) / 2 traces (common, head clear) / up to 14 traces when head box blocked: 2 box + 4 line (ledge) + 4 box (wall) + 1 box + 1 line 256u + 2 box. Two fixed loops i<4 |
| PassStandardEnemyChecks | ai_main.c:2063 | 115 | validity filter for a potential enemy | 2250, 2474 (ScanForEnemies loop), 2796, 6826, 12894, 13011, 13719; per frame, per candidate | none; OnSameTeam + BotMindTricked |
| BotDamageNotification | ai_main.c:2180 | 81 | record lastHurt/lastAttacked, maybe adopt attacker as enemy | g_combat.c:5903, 5907; event-only (each damage on a bot) | 1 loop MAX_CLIENTS |
| BotCanHear | ai_main.c:2264 | 66 | sound/footstep/event based hearing radius test | ScanForEnemies 2485 (only evaluated when FOV test fails or bot is mind-tricked) | none; indexes gBotEventTracker[en->s.number] unchecked |
| UpdateEventTracker | ai_main.c:2332 | 19 | copy ps.eventSequence/events for all clients | BotAIStartFrame 14973; once per server frame | loop MAX_CLIENTS |
| InFieldOfVision | ai_main.c:2353 | 41 | pitch+yaw within fov/2 (mutates `angles`) | 2485, 5248, 7099, 7111, 7117, 13103, 13759, 14310, 14377, 14764 + many game files | none |
| PassLovedOneCheck | ai_main.c:2397 | 52 | bot attachment ("love") filter | 2255, 2474, 2798, 6139, 6827, 12894, 13513, 13520, 13522, 13732 | loop i<bs->lovednum (<=4) with strcmp |
| ScanForEnemies | ai_main.c:2453 | 66 | pick nearest visible/heard valid enemy client | StandardBotAI 13821; EVERY frame per bot (gate at 13818-13819 is always true) | loop i<=MAX_CLIENTS (33 iterations); per valid non-team candidate 1 InPVS; per candidate that is nearer than current pick and (in 90-deg FOV or heard): 1 line trace MASK_SOLID eye->origin, unbounded. Worst case 31 traces + 31 InPVS per bot per frame |
| WaitingForNow | ai_main.c:2520 | 39 | standing on an elevator at wpCurrent? | StandardBotAI 14464; per frame when bs->beStill < level.time | 0 or 1 CheckForFunc (64u line) |
| BotGetWeaponRange | ai_main.c:2562 | 35 | weapon -> range class | 2658, 3461, 3462, 4089, 5206, 5213, 13069, 13118, 14268, 14325, 14738 | none |
| BotIsAChickenWuss | ai_main.c:2599 | 91 | should the bot flee | 1606 (WPTouchRoutine), 4165 (GetIdealDestination); self-gated by bs->chickenWussCalculationTime (10 s) | none |
| GetNearestBadThing | ai_main.c:2693 | ~135 (body runs past line 2700) | nearest dangerous projectile/sentry within 800u; may set enemy to projectile owner | GetIdealDestination 3970; gated by (level.time - bs->escapeDirTime) > 4000 and by caller's destinationGrabTime gate (14016) | loop i<level.num_entities; per qualifying entity 1 InPVS + 1 line trace MASK_SOLID (2775-2777) |
| GetNearestBadThing | ai_main.c:2693 | 134 | Find nearest dangerous projectile/explosive/enemy sentry within 800u (x0.5 for non-explosive weapons); also sets doForcePush, may set currentEnemy to projectile owner, sets dontGoBack | Only GetIdealDestination:3970. Per-frame when bs->wpCurrent != NULL, gated by `destinationGrabTime < level.time` (14016) and `level.time - escapeDirTime > 4000` (3968). NEVER runs when gWPNum==0 | Loop 0..level.num_entities (2705). Per qualifying ent within range: 1 trap->InPVS (2775) + 1 line trace MASK_SOLID <=800u (2777). Worst = N_projectiles InPVS + line traces. Up to 4 OnSameTeam calls per ent |
| BotDefendFlag | ai_main.c:2829 | 32 | CTF: set wpDestination = own flag WP if farther than BASE_GUARD_DISTANCE | CTFTakesPriority:3301 only (ctfState DEFENDER) | 0 traces, no loops |
| BotGetEnemyFlag | ai_main.c:2863 | 32 | CTF: set wpDestination = enemy flag WP | CTFTakesPriority:3309 only | 0 traces, no loops |
| BotGetFlagBack | ai_main.c:2897 | 63 | CTF: find enemy carrying our flag, route to nearest WP to him | CTFTakesPriority:3317 only (ctfState RETRIEVAL); WP search gated by bs->wpDestSwitchTime (2938) | Loop MAX_CLIENTS (2915). GetNearestVisibleWP (2949) = O(gWPNum) InPVS+box trace; TotalTrailDistance (2951). Timer only re-armed on success, so failure repeats every call |
| BotGuardFlagCarrier | ai_main.c:2963 | 63 | CTF: find teammate carrying enemy flag, route to nearest WP to him | CTFTakesPriority:3329 only (ctfState GUARDCARRIER); gated by wpDestSwitchTime (3004) | Same as BotGetFlagBack: loop MAX_CLIENTS (2981) + GetNearestVisibleWP (3015) + TotalTrailDistance (3017) |
| BotGetFlagHome | ai_main.c:3028 | 32 | CTF: set wpDestination = own flag WP when carrying | CTFTakesPriority:3341 only | 0 traces |
| GetNewFlagPoint | ai_main.c:3061 | 63 | Re-point global flagRed/flagBlue to nearest WP with clear box LOS to a dropped flag | CTFTakesPriority:3211, 3220; every call while a flag is FL_DROPPED_ITEM (no timer, per bot) | 1 box trace (30x30x10, MASK_SOLID, <=128u) at 3084 if current point within 128u; else loop 0..gWPNum (3092) with 1 box trace per WP closer than current best (3099). Worst O(gWPNum) box traces per bot per call |
| CTFTakesPriority | ai_main.c:3126 | 231 | CTF nav priority: weapon gather, refresh flag points, recompute ctfState, dispatch to BotDefendFlag/GetEnemyFlag/GetFlagBack/GuardFlagCarrier/GetFlagHome | GetIdealDestination:4018 only (per-frame with wpCurrent, gated destinationGrabTime); returns 0 immediately if not GT_CTF/GT_CTY (3147) | Loop MAX_CLIENTS (3234). Optional GetBestIdleGoal (3155), 0-2 GetNewFlagPoint, sub-function costs |
| EntityVisibleBox | ai_main.c:3358 | 17 | Box/line visibility test that also passes if the hit entity == ignore2 | Siege_TargetClosestObjective:3445; StandardBotAI:14378 (shootGoal), 14765 (dangerousObject) - both per-frame when those pointers are set | 1 trace MASK_SOLID (3362); box if mins/maxs non-NULL (3445 uses 2x2x2), line at 14378/14765 |
| Siege_TargetClosestObjective | ai_main.c:3377 | 98 | Siege: choose closest objective WP with given flag, set shootGoal/touchGoal | SiegeTakesPriority:3662, 3713 | Loop 0..gWPNum (3401) unless current dest still valid (3395). 0-1 box trace via EntityVisibleBox (3445) when goal takedamage and dist < 1024 |
| Siege_DefendFromAttackers | ai_main.c:3476 | 46 | Siege: set wpDestination to WP nearest the closest living enemy; destinationGrabTime +10000 on success | SiegeTakesPriority:3664, 3689 | Loop MAX_CLIENTS (3488). GetNearestVisibleWP (3514) = O(gWPNum) InPVS + box traces |
| Siege_CountDefenders | ai_main.c:3524 | 26 | Count bot teammates in SIEGESTATE_DEFENDER | SiegeTakesPriority:3645 | Loop MAX_CLIENTS, 0 traces |
| Siege_CountTeammates | ai_main.c:3552 | 23 | Count clients on our team | SiegeTakesPriority:3646 | Loop MAX_CLIENTS, 0 traces |
| SiegeTakesPriority | ai_main.c:3578 | 165 | Siege nav priority: weapon gather, pick attacker/defender state, target objective or defend, validate shootGoal LOS | GetIdealDestination:4026 only; returns 0 if not GT_SIEGE (3591) | 2 MAX_CLIENTS loops when not attacker team; sub-function costs; if shootGoal: 1 InPVS (3671/3696/3720) + 1 line trace MASK_SOLID (3677/3702/3726); optional GetBestIdleGoal (3606) |
| JMTakesPriority | ai_main.c:3746 | 73 | Jedi Master: route to JM holder or loose saber | GetIdealDestination:4034 only; returns 0 if not GT_JEDIMASTER (3752); WP lookup gated by destinationGrabTime (3787), re-armed +4000 only on success | Loop MAX_CLIENTS (3766); 1 GetNearestVisibleWP (3791 or 3795) |
| BotHasAssociated | ai_main.c:3822 | 55 | Does bot already own the item tied to a goal waypoint | GetBestIdleGoal:3922 (inside gWPNum loop) | 0 traces, O(1) |
| GetBestIdleGoal | ai_main.c:3881 | 63 | Pick highest weight-minus-distance WPFLAG_GOALPOINT waypoint; returns -1 if !wpCurrent (3889) or randomNav | CTFTakesPriority:3155; SiegeTakesPriority:3606; GetIdealDestination:4174, 4222 (4222 gated by !wpDestination && wpDestSwitchTime). Declared ai_main.h:550. Uses bs->randomNavTime (3896) | Loop 0..gWPNum (3916); TotalTrailDistance per goal WP (3924), itself O(path length) => up to O(gWPNum * path). 0 traces. 0 work when gWPNum==0 |
| GetIdealDestination | ai_main.c:3947 | 283 | Master nav-destination chooser (see B_notes) | StandardBotAI:14018 only, inside `if (bs->wpCurrent)` block (13938), gated `destinationGrabTime < level.time` (14016) - effectively per-frame when on waypoints. Never reached with gWPNum==0; never called by NewBotAI path | GetNearestBadThing (num_entities loop); CTF/Siege/JM functions; up to 1 GetNearestVisibleWP (4122 / 4145 / 4201, each gated wpDestSwitchTime); up to 2 GetBestIdleGoal (4174, 4222) |
| CommanderBotCTFAI | ai_main.c:4233 | 164 | Squad leader assigns ctfState to squad members | CommanderBotAI:4578 | 2 loops MAX_CLIENTS (4269, 4315) + squad loop <= MAX_CLIENTS (4339). 0 traces |
| CommanderBotSiegeAI | ai_main.c:4399 | 64 | Squad leader forces siegeState on up to half the team | CommanderBotAI:4582 | 1 loop MAX_CLIENTS (4409) + squad loop. 0 traces |
| BotDoTeamplayAI | ai_main.c:4465 | 13 | Non-leader: apply forced teamplayState; REGROUP drops leader | StandardBotAI:13564, per-frame when !bs->isSquadLeader (all gametypes) | O(1), 0 traces |
| CommanderBotTeamplayAI | ai_main.c:4480 | 92 | GT_TEAM leader: send helper to weakest teammate, periodic regroup (squadRegroupInterval 45-65s) | CommanderBotAI:4586 | 1 loop MAX_CLIENTS (4493) + squad loop. 0 traces |
| CommanderBotAI | ai_main.c:4574 | 15 | Dispatch commander AI by gametype (CTF/CTY, SIEGE, TEAM; nothing in FFA/duel) | StandardBotAI:13560, per-frame, no timer, when bs->isSquadLeader | See sub-functions; O(1) in FFA |
| MeleeCombatHandling | ai_main.c:4591 | 83 | Melee: toggle strafe dir (meleeStrafeTime 500-1800ms); set goalPosition = enemy origin only if floor height under self, enemy and midpoint are identical | NewBotAI:13120; StandardBotAI:14327. Per-frame while weapon range == MELEE and frame_Enemy_Len <= MELEE_ATTACK_RANGE (256). No timer on the traces | 3 box traces (30x30x56, MASK_SOLID, 4096u straight down, passEnt -1) at 4642, 4649, 4664. No loops |
| BotWeaponCanLead | ai_main.c:4679 | 35 | Lead factor per weapon | UNUSED (no call sites in codemp/game) | O(1) |
| G_NewBotAIGetProjectileSpeed | ai_main.c:4715 | 50 | Projectile speed table per weapon/alt * g_projectileVelocityScale | G_NewBotAIAimLeading:4779 only | O(1) |
| G_NewBotAIAimLeading | ai_main.c:4771 | 131 | Predict enemy position from velocity * ETA, gravity compensation, saber "poke/wiggle" aim; writes bs->goalAngles | NewBotAI_GetAim:6879 only (NewBotAI_GetAim is called per-frame from NewBotAI combat routines 11889..12457). Not used by StandardBotAI directly | 0 or 1 line trace MASK_SOLID passEnt NONE: 4818 (projectile weapon + enemy airborne, not force-jumping up, no jetpack; length = lead + gravity drop) or 4843 (DEMP2 alt; ~1024u down + 0.5s lead). Saber (speed 0) = 0 traces |
| BotAimLeading | ai_main.c:4905 | 78 | Legacy lead: offset headlevel along enemy velocity; writes goalAngles | UNUSED: only references are 6849 (// commented) and 6865 (inside /* */ block 6858-6870) | 0 traces |
| BotAimOffsetGoalAngles | ai_main.c:4985 | 115 | Skill-based random aim wobble, re-rolled every 200-700ms | NewBotAI:13297; StandardBotAI:14255. Per-frame when aiming at enemy without lead; internal timer bs->aimOffsetTime (4996, 5098) | 0 traces; loop of 3 |
| ShouldSecondaryFire | ai_main.c:5102 | 79 | Decide alt-fire (0 no / 1 hold / 2 release charge) | CombatBotAI:5284 only => effectively UNUSED | 0 traces |
| CombatBotAI | ai_main.c:5183 | 139 | Legacy fire decision by range/FOV; sets doAttack/doAltAttack | UNUSED (no call sites) | 0 traces; InFieldOfVision only |
| BotFallbackNavigation | ai_main.c:5336 | 219 | No-waypoint wander: wall/ledge probe, random reachable target 150-400u, EA_Move toward it (see B_notes) | NewBotAI_DoAloneStuff:12770 (per-frame when !destination && weapon==WP_SABER); StandardBotAI:14085 (per-frame when wpCurrent==NULL && weapon==WP_SABER - the normal case on a no-waypoint map); StandardBotAI:14111 (RMG only, iHaveNoIdeaWhereIAmGoing; can be a 2nd call in the same frame). No timer on the 2 base traces | Early out 0 traces if enemy visible (5350). Otherwise min 2 (1 box 32u MASK_PLAYERSOLID 5403 + 1 line 300u MASK_SOLID 5413). Wall/ledge with cooldown expired: 6 (adds 2 box 5424/5428 with bogus END near world origin + 2 line 300u 5439/5447). Target generation: loop 12 x IsPositionReachable => worst 2 + 12*7 = 86 traces in one frame |
| SmartExploration | ai_main.c:5559 | 21 | Try FollowGroundContours, then ExpandingSpiralSearch, then MoveTowardLastWaypoint | UNUSED (no call sites) | Worst 35 + 720 + 1 = 756 traces |
| FollowGroundContours | ai_main.c:5584 | 64 | Sample ground in 7 "directions" x 5 distances; aim at farthest valid | SmartExploration:5564 only => dead code | 7 x up to 5 line traces (600u down, MASK_SOLID) at 5610: best 7, worst 35 |
| ExpandingSpiralSearch | ai_main.c:5652 | 25 | Test 12 angles at radii 100..800 for a reachable spot | SmartExploration:5569 only => dead code | 8 radii x 12 angles = 96 IsPositionReachable; best 4 traces, all-fail-on-box 96 box traces, worst 720 traces |
| MoveTowardLastWaypoint | ai_main.c:5681 | 40 | Head toward bs->lastKnownWaypointPos if box path clear | SmartExploration:5574 only => dead code. bs->lastKnownWaypointPos is never written anywhere (only ai_main.h:452 decl + reads 5682-5689) => always returns qfalse | 0 traces in practice; else 1 box trace (30x30x32, MASK_PLAYERSOLID, <=300u) at 5708 |
| IsPositionReachable | ai_main.c:5725 | 72 | Box LOS to target (fraction >= 0.7) + ground/ledge probes every 100u + final ground probe | BotFallbackNavigation:5507 (inside 12-iteration loop), 5544 (unreachable branch, see bugs); ExpandingSpiralSearch:5664 (dead) | 1 box trace (30x30x32, MASK_PLAYERSOLID, full distance) 5733; loop checks=(int)(dist/100)+1 line traces 400u down MASK_SOLID (5758); 1 final line trace 400u (5787). For dist 150-400: best 1, worst 4-7. For dist d: worst (int)(d/100)+3 |
| BotTryAnotherWeapon | ai_main.c:5798 | 32 | Out of ammo: select first owned weapon with ammo, else weapon 1 | StandardBotAI 13628; per think but only when current weapon ammo < energyPerShot (13626) | 0 traces; loop <= WP_NUM_WEAPONS |
| BotWeaponSelectable | ai_main.c:5832 | 15 | Has weapon + primary ammo? | BotSelectIdealWeapon (5914-5975), NewBotAI_GetTribesWeapon, NewBotAI_GetWeapon (many else-if sites); per think via those | 0 traces; O(1) |
| BotWeaponSelectableAltFire | ai_main.c:5848 | 15 | Has weapon + alt ammo? | same three callers as above; per think | 0 traces; O(1) |
| BotSelectIdealWeapon | ai_main.c:5865 | 133 | Weight-based best weapon + distance overrides (frame_Enemy_Len) | StandardBotAI 13664 only; per think when not out of ammo and no forceWeaponSelect result. Early-out 5873 forces saber when g_newBotAI | 0 traces; loop WP_NUM_WEAPONS + <=6 O(1) checks |
| BotSelectChoiceWeapon | ai_main.c:6000 | 36 | Check (and optionally select) a specific weapon; returns 0/1/2 | StandardBotAI 13654 (when bs->forceWeaponSelect), 14396, 14397, 14425 (mine/detpack planting branch, gated by bs->plantTime < level.time, enemy not visible) | 0 traces; loop <= WP_NUM_WEAPONS (pointless loop: only i==weapon matters) |
| BotSelectMelee | ai_main.c:6038 | 13 | Force weapon 1 | unused-never-called (only call is commented out 13669) | 0 |
| GetLoveLevel | ai_main.c:6053 | 44 | Lookup love level of another bot by netname | CheckForFriendInLOF 6399 (only on trace hit of a client), BotScanForLeader 6430 (inside MAX_CLIENTS loop) | 0 traces; loop bs->lovednum with strcmp |
| BotLovedOneDied | ai_main.c:6099 | 74 | React (chat/revenge) to loved bot's death | BotDeathNotify 6188 only; event-only | 0 traces; calls PassLovedOneCheck (lovednum strcmp loop), BotDoChat |
| BotDeathNotify | ai_main.c:6174 | 25 | Tell all bots that love us that we died | StandardBotAI 13512; event-only (health<1 and !bs->deathActivitiesDone) | 0 traces; loop MAX_CLIENTS x lovednum strcmp |
| StrafeTracing | ai_main.c:6201 | 87 | Wall/ledge checks for melee strafe; sets bs->meleeStrafeDisable / meleeStrafeDir | unused-never-called (Grep whole codemp: only the definition) | If it were called: 30% RNG gate (6208), then 2 box traces 32u (6220, 6225) + 1 box trace 32u (6269) + 1 line trace 32u down (6280), all MASK_SOLID |
| PrimFiring | ai_main.c:6290 | 16 | Is primary fire effectively pressed (accounts for charging) | StandardBotAI 14772, 14779; per think | 0 |
| KeepPrimFromFiring | ai_main.c:6308 | 16 | Cancel primary fire | StandardBotAI 14781; only when friend in LOF | 0 |
| AltFiring | ai_main.c:6326 | 16 | Is alt fire effectively pressed | StandardBotAI 14773, 14783; per think | 0 |
| KeepAltFromFiring | ai_main.c:6344 | 16 | Cancel alt fire | StandardBotAI 14785; only when friend in LOF | 0 |
| CheckForFriendInLOF | ai_main.c:6362 | 46 | Trace along view dir to find teammate/loved bot in line of fire | StandardBotAI 14775 (per think whenever PrimFiring or AltFiring) and 14811 (else-branch: EVERY think when level.gametype >= GT_TEAM and not firing). No timer | 1 BOX trace (6x6x6), 2048u, MASK_PLAYERSOLID (6386); no loops |
| BotScanForLeader | ai_main.c:6409 | 31 | Adopt another squad-leader bot as leader | StandardBotAI 13833; per think while !bs->squadLeader && !bs->isSquadLeader (13831); no timer | 0 traces; loop MAX_CLIENTS (OnSameTeam, GetLoveLevel) |
| BotReplyGreetings | ai_main.c:6442 | 27 | Make up to 4 other bots answer a greeting | StandardBotAI 14356; event-only (bs->doChat == 2 and bs->chatTime elapsed) | 0 traces; loop MAX_CLIENTS + BotDoChat |
| CTFFlagMovement | ai_main.c:6471 | 77 | Detour to grab a dropped flag within BOT_FLAG_GET_DISTANCE (256) | StandardBotAI 14361; per think, unconditional call; body does work only if flagRed && flagBlue and wpDestination is a flag | 0-1 BOX trace (30x30x14), <=256u, MASK_SOLID (6535); only when a dropped flag is within 256u and bs->wantFlag path did not early-return |
| BotCheckDetPacks | ai_main.c:6550 | 52 | Detonate own detpack when enemy is near it | StandardBotAI 14387; per think while bs->cur_ps.hasDetPackPlanted; no timer | G_Find loop over all entities (level.num_entities, strcmp classname) until own detpack found (6558); + 0-1 OrgVisible line trace <=256u MASK_SOLID (6597) |
| BotUseInventoryItem | ai_main.c:6604 | 51 | Pick a holdable item to use (medpac/seeker/sentry/shield) | StandardBotAI 13618; per think | 0 traces; O(1); writes level.clients[].ps.stats[STAT_HOLDABLE_ITEM] (6651) |
| BotSurfaceNear | ai_main.c:6657 | 20 | Is there a surface 64u ahead (for planting mines/detpacks) | StandardBotAI 14414; gated by bs->plantTime < level.time, enemy lost from view, has mine/detpack, near bs->hereWhenSpotted | 1 LINE trace 64u MASK_SOLID (6668) |
| BotWeaponBlockable | ai_main.c:6679 | 23 | Can saber block that weapon's projectiles | StandardBotAI 14838; per think when doAttack && saber && saberDefending | 0 |
| Bot_SetForcedMovement | ai_main.c:6707 | 45 | Toggle bs->forceMove_* (debug cmd) | g_cmds.c 4706, 4719, 4732, 4745, 4758; event-only (console commands) | 0 |
| NewBotAI_GetStrafeAim | ai_main.c:6753 | 44 | Strafe-jump aim angle while bs->runningLikeASissy | NewBotAI_GetAim 6808 only; per think when runningLikeASissy | 0 traces; sqrt + acos |
| NewBotAI_GetAim | ai_main.c:6798 | 85 | Aim at nearest in-flight enemy saber (<200u) else lead-aim at enemy chest | NewBotAI_DSvDS 11889/11940, DSvLS 12021/12037, LSvDS 12079/12103, LSvLS 12138/12154, NF 12179, Tribes 12446, StrafeJump 12457. Per think whenever a visible enemy exists (XvX called from NewBotAI 13050-13060 AND StandardBotAI 13600-13610) | 0 traces here; loop i <= MAX_CLIENTS (33 iters, cheap saberInFlight filter first; then OnSameTeam + PassStandardEnemyChecks + PassLovedOneCheck); calls G_NewBotAIAimLeading (4771, outside region) |
| NewBotAI_GetDist | ai_main.c:6884 | 11 | Distance eye -> enemy origin | NewBotAI 13030 (per think), NewBotAI_Absorbing 7375 | 0 |
| NewBotAI_GetTimeToInRange | ai_main.c:6897 | 46 | Simulate ms until bot and enemy are within range | NewBotAI_Gripkick 7186 only (while FP_GRIP active and on world ground) | 0 traces; loop attempts = sv_fps*maxTime/1000 (=3 for 30fps,100ms) |
| NewBotAI_GetAbsorb | ai_main.c:6945 | 33 | Weight for activating Absorb | NewBotAI_Getup 7030, NewBotAI_GetLSForcepower 11796; per think (LS bots) | 0; side effect: writes forcePowerSelected (6965) |
| NewBotAI_GetProtect | ai_main.c:6979 | 33 | Weight for activating Protect | NewBotAI_Getup 7034, NewBotAI_GetLSForcepower 11797; per think (LS bots) | 0 |
| NewBotAI_Getup | ai_main.c:7013 | 37 | Knockdown recovery: jump + protect/absorb/push | all XvX + NF (11892, 11943, 12024, 12040, 12082, 12106, 12141, 12157, 12182); only while forceHandExtend == HANDEXTEND_KNOCKDOWN | 0 |
| NewBotAI_Flipkick | ai_main.c:7051 | 32 | Jump/wall-kick input sequence | ReactToBeingGripped 7134, Gripkick 7187/7190, StrafeJump 12459, DoAloneStuff 12851 | 0 |
| NewBotAI_ReactToBeingGripped | ai_main.c:7084 | 56 | Absorb/push/pull + flipkick when gripped | DSvDS 11897/11948, LSvDS 12086/12110; while fd.forceGripBeingGripped > level.time | 0 traces; InFieldOfVision math |
| NewBotAI_Gripkick | ai_main.c:7141 | 58 | View-angle choreography + kick while gripping | DSvDS 11963, DSvLS 12055; while FP_GRIP active | 0 traces; calls GetTimeToInRange (3-iter loop) |
| NewBotAI_Lightning | ai_main.c:7200 | 45 | Keep lightning held, aim with jitter, range keep | DSvDS 11953, DSvLS 12045; per think while FP_LIGHTNING active | 1 OrgVisible line trace eye->enemy origin, <=1500u (7217), after cheap early-outs |
| NewBotAI_Draining | ai_main.c:7246 | 9 | Keep drain held | DSvDS 11968, DSvLS 12060; per think while FP_DRAIN active | 0-1 OrgVisible line trace (7252), unbounded length (enemy distance), short-circuited by health<100 etc. |
| NewBotAI_MindTrick | ai_main.c:7256 | 17 | Re-press telepathy when hurt | LSvDS 12118; only while FP_TELEPATHY already active | 0-1 OrgVisible line trace (7263), gated health <= 50 and enemy FP > 0 and !absorb |
| NewBotAI_Speeding | ai_main.c:7274 | 7 | Presses force (FP_SPEED) while speed active | DSvDS 11973, DSvLS 12065, LSvDS 12114, LSvLS 12162 | 0 |
| NewBotAI_Raging | ai_main.c:7282 | 55 | Toggle rage off (FP<10 or health>=50) / on | DSvDS 11958 (11977 unreachable after return at 11959), DSvLS 12050; only while FP_RAGE active in cur_ps | 0; writes level.clients[].ps.fd.forcePowersActive (7304) |
| NewBotAI_Protecting | ai_main.c:7338 | 31 | Decide to toggle Protect off | LSvDS 12120, LSvLS 12164; while FP_PROTECT active | 0 |
| NewBotAI_Absorbing | ai_main.c:7370 | 20 | Decide to toggle Absorb off | LSvDS 12122, LSvLS 12166; while FP_ABSORB active | 0 |
| NewBotAI_Healing | ai_main.c:7391 | 14 | Press heal if health<75 and FP>30 and heal not active | LSvDS 12116 only, and only when FP_HEAL IS active -> inner condition (!active) contradicts caller gate: effectively no-op | 0 |
| NewBotAI_SaberThrowing | ai_main.c:7406 | 12 | Hold alt-attack while saber in flight and 500<=dist<=2500 | DSvDS 11914/11991, LSvDS 12093/12124 (others via Grep: none in DSvLS/LSvLS); while cur_ps.saberInFlight | 0 |
| BS_GroundDistance | ai_main.c:7419 | 4 | origin z - forceJumpZStart | NewBotAI_NF 12244 (12217 commented) | 0 |
| NewBotAI_GetSpeedTowardsEnemy | ai_main.c:7424 | 22 | Signed sqrt of dot(diff, velocity) | NewBotAI_NF 12177 (10516 commented); per think in NF mode | 0 |
| NewBotAI_GetTribesWeapon | ai_main.c:7448 | 151 | Distance-tier weapon table for Tribes mode; sets doAltAttack/altChargeTime | NewBotAI_GetAttack 10522 (when g_tweakWeapons & WT_TRIBES); per think with enemy | 0 traces; <=~14 O(1) checks |
| NewBotAI_GetWeapon | ai_main.c:7600 | 372 | Weapon table by enemy weapon class x distance tier; sets doAltAttack/altChargeTime/ChargeTime | NewBotAI_GetAttack 10524; per think with enemy (GetAttack is called from every XvX/NF/Tribes) | 0 traces; <=~14 O(1) checks |
| NewBotAI_GetAltCharge | ai_main.c:7973 | 16 | Alt charge state 0/1/2/3 | NewBotAI_GetAttack 10558 | 0 |
| NewBotAI_GetCharge | ai_main.c:7990 | 16 | Primary charge state 0/1/2/3 | NewBotAI_GetAttack 10572 | 0 |
| BotCanHitEnemy | ai_main.c:8008 | 42 | Predicted enemy pos within saber reach (128/141/154u), 60deg cone, clear path | BotShouldAttack 8066, BotCanAttackNow 8318. Reached up to 3x per think (see C_notes e) | 1 BOX trace (16x16x16), <=~154u, MASK_PLAYERSOLID (8044) per call, after distance+cone early-outs; calls BotPredictEnemyPosition |
| BotShouldAttack | ai_main.c:8052 | 16 | Enemy not blocking/throwing + BotCanHitEnemy | BotShouldAttackNow 8602 | 1 box trace via BotCanHitEnemy |
| BotPredictEnemyPosition | ai_main.c:8070 | 46 | Pattern-based enemy position prediction + random jitter | BotCanHitEnemy 8019, BotUpdateAttackTiming 8628, NewBotAI 13286, StandardBotAI 14244; per think (several times) | 0 traces; mutates bs->lastEnemyVelocity / enemyMovementHistoryTime via BotAnalyzeMovementPattern; 2x Q_irand |
| BotGetPredictionTime | ai_main.c:8118 | 16 | 0.15s + skill*0.03 + distance bonus | BotPredictEnemyPosition 8082 | 0 |
| BotAnalyzeMovementPattern | ai_main.c:8136 | 46 | Classify enemy motion 0-4 from velocity delta | BotPredictEnemyPosition 8088 | 0; timer bs->enemyMovementHistoryTime (100 ms staleness) |
| BotPredictStrafingMovement | ai_main.c:8184 | 30 | Strafe prediction | BotPredictEnemyPosition 8093 | 0 |
| BotPredictJumpingMovement | ai_main.c:8216 | 33 | Ballistic prediction | BotPredictEnemyPosition 8096 | 0 |
| BotPredictRetreatingMovement | ai_main.c:8251 | 21 | "Retreat" prediction | BotPredictEnemyPosition 8099 | 0 |
| BotPredictChargingMovement | ai_main.c:8274 | 22 | "Charge" prediction | BotPredictEnemyPosition 8102 | 0 |
| BotCanAttackNow | ai_main.c:8298 | 25 | nextAttackTime / weaponstate / attackRecoveryTime / blocking gates, then BotCanHitEnemy | BotExecuteAttack 8327, BotShouldAttackNow 8598 | 0-1 box trace (via BotCanHitEnemy) after timer gates bs->nextAttackTime, bs->attackRecoveryTime |
| BotExecuteAttack | ai_main.c:8325 | 20 | EA_Attack + set nextAttackTime/attackRecoveryTime/lastAttackTime/comboWindow | NewBotAI 13090, StandardBotAI 14289; only after BotShouldAttackNow true | 1 more box trace (re-runs BotCanAttackNow) |
| BotGetAttackDelay | ai_main.c:8347 | 39 | Delay by saber style and skill (min 300ms) | BotExecuteAttack 8331 | 0 |
| BotGetCurrentAttackType | ai_main.c:8388 | 16 | 1/2/3 by distance | BotExecuteAttack 8342 | 0 |
| BotDynamicCombatMovement | ai_main.c:8406 | 44 | Close/back off to optimal distance or strafe; EA_Move | BotUpdateDynamicMovement 8648; StandardBotAI 14621 (per think in movement section) | 0 traces; RNG via BotShouldStrafeInCombat |
| BotGetOptimalCombatDistance | ai_main.c:8452 | 28 | 40-80u by saber style | BotDynamicCombatMovement 8421, BotMovementDuringAttack 8669 | 0 |
| BotShouldStrafeInCombat | ai_main.c:8482 | 21 | RNG (10% + 5%*skill) strafe decision | BotDynamicCombatMovement 8436, StandardBotAI 14293 | 0; timer bs->attackRecoveryTime |
| BotCombatStrafe | ai_main.c:8505 | 43 | Pick strafe dir, set combatStrafeTime, EA_Move | BotDynamicCombatMovement 8437, BotUpdateDynamicMovement 8643 | 0 |
| BotSelectStrafeDirection | ai_main.c:8550 | 36 | 1-4 direction (evade if enemy WEAPON_FIRING else random circle) | BotCombatStrafe 8516 | 0 |
| BotShouldAttackNow | ai_main.c:8588 | 24 | Vis + range (<=192) + BotCanAttackNow + BotShouldAttack + RNG | NewBotAI 13089, StandardBotAI 14288; per think when saber-range weapon and frame_Enemy_Len <= 128 | up to 2 box traces (8598 then 8602) |
| BotUpdateAttackTiming | ai_main.c:8614 | 19 | Combo window attack; pre-aim at predicted pos when nextAttackTime within 200ms | NewBotAI 13085, StandardBotAI 14284; per think in saber range | 0 traces |
| BotUpdateDynamicMovement | ai_main.c:8635 | 16 | Continue combat strafe; call BotDynamicCombatMovement when nextAttackTime < now+500 | NewBotAI 13086, StandardBotAI 14285; per think in saber range | 0 traces |
| BotMovementDuringAttack | ai_main.c:8653 | 26 | Forward/back to optimal distance during attack windup | StandardBotAI 14612; per think when doAttack or doAltAttack | 0 |
| BotEnemyInRecovery | ai_main.c:8683 | 25 | Enemy in post-swing recovery (torsoTimer window) | BotEnemyVulnerable 8763, Bot_ExecuteDefensiveCounter 9608, Bot_ExecuteSaberCombat 10233 | 0 |
| BotEnemyInRecovery | ai_main.c:8683 | 25 | True if enemy saberMove != LS_READY with torsoTimer 1..299, or special move (lunge/DFA/flip) with torsoTimer 1..399 | BotEnemyVulnerable 8763 (per call); Bot_ExecuteSaberCombat 10233 (per GetAttack call that passes the special/range gates); Bot_ExecuteDefensiveCounter 9608 | 0 traces, no loops |
| BotCanFeint | ai_main.c:8709 | 29 | Random feint eligibility test (saber, dist<=140, idle saber) | UNUSED - never called (only definition in whole codemp tree) | 0 traces; up to 3 Q_irand; derefs bs->currentEnemy unguarded |
| BotEnemySwinging | ai_main.c:8740 | 18 | True if enemy saberMove in LS_A_TL2BR..LS_S_BL2TR or lunge/DFA/flip | Bot_ExecuteSaberCombat 10235; Bot_ExecuteFeint 8813 (dead) | 0 traces |
| BotEnemyVulnerable | ai_main.c:8759 | 14 | True if enemy recovering, saberMove==LS_READY, or airborne | Bot_ExecuteSaberCombat 10234; NewBotAI_GetAttack 10555 (non-saber path, per call) | 0 traces |
| TAB_MoveforAttackQuad | ai_main.c:8775 | 18 | Converts saber quadrant Q_* to a world move dir from bs->viewangles (1 AngleVectors) | ~40 call sites in Bot_Execute* and Bot_ExecuteSaberCombat (10251, 10432, 10478, 10506); at most ~3 per frame | 0 traces; 1 AngleVectors |
| Bot_ExecuteFeint | ai_main.c:8795 | 47 | Feint retreat then counter-swing state machine keyed on bs->isFeinting / feintTime | UNUSED - never called; bs->isFeinting is never set qtrue anywhere | 0 traces |
| Bot_AnalyzeEnemyAttack | ai_main.c:8846 | 108 | Fills bs->blocking: enemySwingStage 0..7 from torsoTimer, enemyAttackPower, enemyMoving, enemyStance | Only Bot_ExecutePerfectBlocking 8962 (once per SaberCombat call reaching 10238) | 0 traces; 1 VectorLength |
| Bot_ExecutePerfectBlocking | ai_main.c:8958 | 96 | During enemy swing stage 2..6: zero EA_Move, force pitch -10, yaw wiggle, arm parry flag; else run parry / staff-overwhelm retreat+jump | Only Bot_ExecuteSaberCombat 10238 | 0 traces; 1 AngleVectors (result unused), 1 Q_flrand |
| Bot_ExecuteParry | ai_main.c:9058 | 43 | Counter-swing in quad chosen from enemy saberMove, EA_Move 8000 + EA_Attack, bump blockConfidence | Only Bot_ExecutePerfectBlocking 9020 (gated by shouldParry && level.time < parryWindow; practically almost unreachable, see notes) | 0 traces |
| Bot_InitPerfectBlocking | ai_main.c:9105 | 8 | memset bs->blocking, confidence 0.5 | ai_main.c:964 (bot setup, event-only) | none |
| Bot_GetStyleAdvantage | ai_main.c:9117 | 53 | Lookup table style-vs-style advantage float | UNUSED - never called (only prototype ai_main.h:472) | none |
| Bot_SelectOptimalSaberStyle | ai_main.c:9174 | 181 | Decide whether to call Cmd_SaberAttackCycle_f (cycle one style step) based on enemy style (humans), random variety timer (bots), then distance | NewBotAI_GetAttack 10542 (every GetAttack call with saber); NewBotAI 13078 and StandardBotAI 14277 (per frame when enemy and saber range type). So 2-3 calls per bot per frame. Internally gated by bs->lastStyleSwitchTime + 2000 and saberMove idle | 0 traces; Q_irand(8000,15000) re-rolled each call in bot-vs-bot branch |
| Bot_ExecuteSaberDance | ai_main.c:9360 | 21 | Random left/right quad EA_Move 3000 + attack if dist<=80 | Bot_ExecuteSaberCombat 10305 | 0 traces |
| Bot_ExecuteRushAttack | ai_main.c:9382 | 12 | Q_T quad move 4000 + attack if dist<=100 | Bot_ExecuteSaberCombat 10316 | 0 traces |
| Bot_ExecuteDFA | ai_main.c:9395 | 28 | forward+jump+attack if 50<=dist<=200 | Bot_ExecuteSaberCombat 10334 | 0 traces; unused uninitialised locals |
| Bot_ExecuteCrouchLunge | ai_main.c:9424 | 14 | crouch+forward+attack if dist<=100 | Bot_ExecuteSaberCombat 10352 | 0 traces |
| Bot_ExecuteHurricane | ai_main.c:9439 | 18 | Q_TL or Q_TR move 3500 + attack if dist<=90 | Bot_ExecuteSaberCombat 10364 | 0 traces |
| Bot_ExecuteStyleSwitch | ai_main.c:9458 | 21 | For staff/dual with offense level>1: one Cmd_SaberAttackCycle_f (switch-back code unreachable) | Bot_ExecuteSaberCombat 10375 | 0 traces |
| Bot_ExecuteDelayAttack | ai_main.c:9480 | 24 | One random-quad strike (second delayed strike unreachable) if dist<=110 | Bot_ExecuteSaberCombat 10386 | 0 traces |
| Bot_ExecuteConvergentAttack | ai_main.c:9505 | 27 | Q_B strike move 5000, 60% overwrite with forward move 2000, if dist<=100 | Bot_ExecuteSaberCombat 10397 | 0 traces |
| Bot_ExecuteStaticAttack | ai_main.c:9533 | 21 | Attack with EA_Move speed 0; 30% small move toward enemy, if dist<=90 | Bot_ExecuteSaberCombat 10408 | 0 traces |
| Bot_ExecuteThreeSwingCombo | ai_main.c:9555 | 43 | Picks 1 of 6 patterns; computes 3 moveDirs but never EA_Moves; net effect = EA_Attack | Bot_ExecuteSaberCombat 10419 | 0 traces; 3 AngleVectors wasted |
| Bot_ExecuteDefensiveCounter | ai_main.c:9599 | 16 | If enemy in recovery, 60%: Q_B move 5000 + attack (dist<=120) | Bot_ExecuteSaberCombat 10446 | 0 traces |
| Bot_ExecuteLungeAttack | ai_main.c:9616 | 26 | forward + quad BR/BL/B by enemy side + attack, only 95<=dist<=140 | Bot_ExecuteSaberCombat 10461 (caller requires dist<=LUNGE_MAX which is 80..110, so only reachable 95..110 in strong/desann/medium(95)) | 0 traces |
| Bot_ExecuteKataAttack | ai_main.c:9643 | 32 | attack+alt_attack if 40<=dist<=256, FP>=50, saber, not already in kata; writes ps.weaponTime=0 | Bot_ExecuteSaberCombat 10294 (>=75% of calls that reach the special roll) | 0 traces |
| Bot_CheckAndInteractWithObstacle | ai_main.c:9680 | 266 | Trace 128u ahead for a non-world, non-client entity; classify by classname; jump (dead code), use door/button/plat, attack obstacle, or side-step | NewBotAI_GetMovement 10885 and 10944 only. Gate: bs->noUseTime < level.time && bs->lastObstacleTime < level.time-3000 (lastObstacleTime only refreshed on qtrue return, so on the common qfalse result it runs EVERY movement frame). 10320 and 10033 are commented out | 1 line trace 128u always; +2 line traces 64u in combat-avoid branch (non-melee/explosive weapons only); trace at 9784 unreachable. Up to ~15 Q_stricmp/strstr on classname when an entity is hit. No loops |
| Bot_ExecuteSaberCombat | ai_main.c:9948 | 564 | Main saber attack brain: wall probe, emergency ignite, obstacle-jump probe, special-move lockout, block/counter, special roll cascade, basic swings | Only NewBotAI_GetAttack 10545. GetAttack is called up to 2x per bot per frame (see NewBotAI_GetAttack row) | Always 1 BOX trace 48u (JP_Trace 9971, before every early-out); +1 line trace up to 200u (10052) when enemy visible and dist<=200; +1 line trace ~68u (10069) if a low entity is in the way. Best 1 / typical 2 / worst 3 per call. No loops |
| NewBotAI_GetAttack | ai_main.c:10513 | 72 | Pick weapon, bail on gates, saber -> style select + Bot_ExecuteSaberCombat; guns -> charge/fire logic | NewBotAI_DSvDS 11935/12013, DSvLS 12032/12071, LSvDS 12098/12130, LSvLS 12149/12171 (per frame while engaged); NewBotAI_Tribes 12447; NewBotAI 13237 and StandardBotAI 14186 (per frame, gated bs->timeToReact < level.time, enemySeenTime, frame_Enemy_Vis). NewBotAI calls XvY (13052-13060) AND 13237 in the same frame -> 2 calls/frame; same in StandardBotAI (13602-13610 + 14186) | Own body 0 traces; calls NewBotAI_GetWeapon/GetTribesWeapon (out of region, 7600) each call; saber path = Bot_ExecuteSaberCombat cost (1-3 traces) |
| NewBotAI_GetGroundDodge | ai_main.c:10586 | 15 | Strafe by bs->forceMove_Right, re-roll direction every frame in second half of each 1.5s | UNUSED - never called | 0 traces |
| Bot_ClearForcedMovement | ai_main.c:10604 | 7 | Zero forceMove_Forward/Right/Up | NewBotAI_GetMovement 10874 (per call when weapon is saber) | none |
| Bot_GetAdaptiveDodgeDir | ai_main.c:10617 | 56 | Choose dodge dir -1/1/2 from swing memory; enemy-velocity term is NaN (div by zero) | NewBotAI_GetMovement 10973 (when backstep triggers) and 11127 (when bs->strafeExpireTime expires and strafe roll passes) | 0 traces; 1 AngleVectors |
| Bot_TrapSetup | ai_main.c:10678 | 13 | Random 4-way step | UNUSED - never called | none |
| Bot_ShouldBackstepForSwing | ai_main.c:10692 | 18 | True if enemy mid-swing (torsoTimer 61..179) and dist<105 | NewBotAI_GetMovement 10971 (per call reaching generic path) | none |
| Bot_ApplyUltraInstinctAim | ai_main.c:10715 | 6 | Random jitter on ideal_viewangles | UNUSED - never called | none |
| Bot_GetMixedAttackMove | ai_main.c:10722 | 12 | Random LS_A_* move id | UNUSED - never called | none |
| Bot_ShouldPressAttack | ai_main.c:10735 | 10 | True if enemy idle/ending swing and dist<130 | UNUSED - never called | none |
| Bot_EvadeSwingArc | ai_main.c:10750 | 13 | Back if dist<110, forward if >180, 30% random side step | NewBotAI_GetMovement 10934, 10981, 11059 | none |
| Bot_CheckRearThreat | ai_main.c:10764 | 7 | If frontDot < -0.6: move forward and add 180 to ideal yaw | NewBotAI_GetMovement 11209 (end of generic path) | none |
| Bot_CheckMovementPaths | ai_main.c:10775 | 79 | 3 probes (forward 64u, "left" 32u, "right" 32u); if front blocked strafe/jump/back and return qtrue | NewBotAI_GetMovement 10951 (every call on generic path, NO timer gate), plus again at 11058 or 11085 in same frame when short retreat/advance probe is blocked | 3 LINE traces every call, MASK_PLAYERSOLID (includes CONTENTS_BODY): 64u fwd(+24 rise), 32u along AngleVectors "up" (mis-named left), 32u along actual left (mis-named right). No loops |
| NewBotAI_GetMovement | ai_main.c:10860 | 351 | Combat movement: saber close path (dist<=100) with fwd/back probes; else obstacle check, path check, swing dodge, range band, strafe bursts, spacing, rear threat | NewBotAI_DSvDS 11933/12010, DSvLS 12030/12068, LSvDS 12096/12127, LSvLS 12147/12168 - once per bot per frame while engaged (XvY called from NewBotAI 13052-13060 and StandardBotAI 13602-13610). No timer gate | Saber close path: 0-1 line trace 32u + obstacle fn (1-3) => best 0, typical 2, worst 3. Generic path: 3 (CheckMovementPaths) + optional obstacle fn 1-3 (dist>200) + 0-1 probe (32u or 16u) + optional 3 more (second CheckMovementPaths) => best 3, typical 4, worst 8. All line traces, MASK_PLAYERSOLID. No loops |
| (tail of previous function, ends 11210; only `Bot_CheckRearThreat(bs, frontDot)` at 11209 falls in region) | ai_main.c:11205 | 6 | closing lines of the big attack/movement function that starts before the region | n/a (belongs to region D) | none in these 6 lines; Bot_CheckRearThreat (10764) does 3 line traces at 10795/10800/10805 (outside region) |
| BG_InRoll3 | ai_main.c:11212 | 20 | switch on anim: true for getup-roll and roll anims | only NewBotAI_IsEnemyPullable (11247) | 0 traces, 0 loops |
| NewBotAI_IsEnemyPullable | ai_main.c:11233 | 19 | enemy can be pulled/pushed (not absorbing, we have >=20 FP, enemy knocked down / low FP / draining / rolling / groundEntityNum != ENTITYNUM_NONE-1) | GetPull (11294), GetPush (11345); per combat think via GetDS/GetLSForcepower | 0 traces, 0 loops. Derefs bs->currentEnemy->client unchecked |
| NewBotAI_GetPull | ai_main.c:11253 | 73 | weight 0..100+ for FP_PULL | GetDSForcepower (11608), GetLSForcepower (11794); every combat think with FP>=10 | 0 traces, 0 loops |
| NewBotAI_GetPush | ai_main.c:11327 | 25 | weight 0 or 100 for FP_PUSH (only to shove off an airborne saberist when our HP<25, dist<160) | GetDSForcepower (11609), GetLSForcepower (11795); every combat think | 0 traces, 0 loops |
| NewBotAI_GetLightning | ai_main.c:11353 | 70 | weight for FP_LIGHTNING (base 100, range 81..1500, FP>=30, modifiers, Q_irand jitter) | GetDSForcepower (11612); every DS combat think | 0 traces, 0 loops, 1 Q_irand |
| NewBotAI_GetRage | ai_main.c:11424 | 31 | weight for FP_RAGE (base 2, FP>=60) | GetDSForcepower (11613); every DS combat think | 0 traces, 0 loops |
| NewBotAI_GetDrain | ai_main.c:11456 | 34 | weight for FP_DRAIN (dist<=512, visible, FP>=21, HP<100 -> 120-HP) | GetDSForcepower (11610); every DS combat think | 0 traces, 0 loops |
| NewBotAI_GetGrip | ai_main.c:11500 | 33 | weight for FP_GRIP (dist<=256, FP>=50) | GetDSForcepower (11611); every DS combat think | 0 traces, 0 loops |
| NewBotAI_GetTeamEnergize | ai_main.c:11534 | 33 | sums weight over nearby (<512) clients with less FP/HP; no team check | GetDSForcepower (11662); every DS combat think, but returns 0 before the loop unless power known and g_gametype >= GT_TEAM | 0 traces; 1 loop i<MAX_CLIENTS (32), body is compares + VectorLengthSquared. Writes ps.fd.forcePowerLevel every call (11545) |
| NewBotAI_GetSaberthrow | ai_main.c:11568 | 29 | returns 100 and presses alt-attack when saber out, dist 500..2500, enemy knocked down, FP>40, enemy HP+armor<=50 | GetDSForcepower (11667), GetLSForcepower (11860); every combat think | 0 traces, 0 loops. Side effects: ps writes 11579-11580, EA_Alt_Attack 11583 |
| NewBotAI_GetDSForcepower | ai_main.c:11598 | 85 | dark-side chooser: 6 weights, strict-max wins, sets ps.fd.forcePowerSelected, EA_ForcePower on odd level.framenum | NewBotAI_DSvDS (12012), NewBotAI_DSvLS (12070); every combat think when FP>=10 and g_forcePowerDisable not 163837/163839. No bs-> timer | 0 traces; 1 MAX_CLIENTS loop via GetTeamEnergize (team gametypes only); 1 unused vectoangles (11606) |
| NewBotAI_GetTelepathy | ai_main.c:11684 | 46 | weight for FP_TELEPATHY (visible, dist<=400, HP>=70, FP>=20, + Q_irand(0,10)) | GetLSForcepower (11799); every LS combat think | 0 traces, 0 loops |
| NewBotAI_GetHeal | ai_main.c:11731 | 17 | weight for FP_HEAL = ((FP-HP)+101)/2 when HP<100 and FP>=50 | GetLSForcepower (11798); every LS combat think | 0 traces, 0 loops |
| NewBotAI_GetTeamHeal | ai_main.c:11749 | 34 | sums weight over same-team clients within 512 with less FP/HP | GetLSForcepower (11854), only if no power chosen yet; returns 0 before loop unless power known and g_gametype >= GT_TEAM | 0 traces; 1 loop i<MAX_CLIENTS (32) |
| NewBotAI_GetLSForcepower | ai_main.c:11784 | 99 | light-side chooser: pull/push/absorb/protect/heal/telepathy weights, strict-max wins, EA_ForcePower on odd level.framenum | NewBotAI_LSvDS (12129), NewBotAI_LSvLS (12170); every combat think when FP>=10 and force not fully disabled. No bs-> timer | 0 traces; 1 MAX_CLIENTS loop via GetTeamHeal (team gametypes, only if nothing chosen); GetAbsorb (6945) / GetProtect (6979) are outside region; 1 unused vectoangles (11792) |
| NewBotAI_DSvDS | ai_main.c:11884 | 131 | per-frame combat driver, dark bot vs dark enemy: aim, getup, grip reaction, active-power handlers, movement, force choice, attack | NewBotAI (13060) every combat think; StandardBotAI (13610) every think with a visible enemy and bs->forceJumpChargeTime < level.time | no direct traces/loops; cost is in callees outside region: GetAim (6798), GetMovement, GetAttack (10513), NewBotAI_Lightning (7200: 1 OrgVisible at 7217), NewBotAI_Draining (7246: OrgVisible at 7252) |
| NewBotAI_DSvLS | ai_main.c:12016 | 57 | same driver, dark bot vs light enemy (no grip-reaction, no saber-throw block) | NewBotAI (13054); StandardBotAI (13604); same frequency as above | no direct traces/loops; callees as above |
| NewBotAI_LSvDS | ai_main.c:12074 | 58 | same driver, light bot vs dark enemy (grip reaction, speed/heal/mindtrick/protect/absorb handlers, saber throw) | NewBotAI (13058); StandardBotAI (13608) | no direct traces/loops; NewBotAI_MindTrick (7256) has OrgVisible at 7263 (outside region) |
| NewBotAI_LSvLS | ai_main.c:12133 | 40 | same driver, light bot vs light enemy | NewBotAI (13052); StandardBotAI (13602) | no direct traces/loops |
| NewBotAI_NF | ai_main.c:12174 | 132 | no-force saber duel logic (forces SS_STRONG, range bands 325/200, backslash, jump/crouch) | NewBotAI (13226) only: every combat think when force is fully disabled (g_forcePowerDisable 163837/163839), g_flipKick off and weapon is saber | 0 direct traces, 0 loops; 1 sqrt; callees GetSpeedTowardsEnemy (7424), GetAim, BS_GroundDistance (7419) outside region |
| NewBotAI_CapRoute | ai_main.c:12308 | 78 | CTF/Tribes scripted cap route playback: steps through redRouteList/blueRouteList positions, sets velocity toward next point | NewBotAI (12987), every think but only when g_movementStyle == MV_TRIBES; returns qfalse immediately unless GT_CTF and pers.activeCapRoute | 1 box trace per call when a route is active (12369: player box, CONTENTS_BODY mask only, origin -> next route point); 0 loops |
| NewBotAI_Tribes | ai_main.c:12387 | 64 | Tribes/jetpack combat: hold jump while jetting or FP>98, ACTION_SKI, then runs the whole StandardBotAI plus GetAim and GetAttack | NewBotAI (13042): every combat think when MV_TRIBES and g_startingItems has HI_JETPACK | no direct traces; calls StandardBotAI (13332) in full = all of its traces/loops, plus GetAim/GetAttack |
| NewBotAI_StrafeJump | ai_main.c:12452 | 32 | GetAim + Flipkick, forward + alternate left/right every 500 ms | unused - never called (only the definition matches in codemp/game) | 0 direct traces, 0 loops; `distance` param unused |
| NewBotAI_DoAloneStuff | ai_main.c:12485 | 370 | no-enemy behaviour: saber select, turn off/turn on self powers, waypoint follow, else item seek via EntitiesInBox, else fallback wander, with jump/pit probes | NewBotAI 12993 (every think with no target), 13023 (target hidden >10 s), 13034 (target not visible and >300 away); StandardBotAI 13827 (each think in which ScanForEnemies returns an enemy; the gate at 13818-13819 is always true once currentEnemy is set). No bs-> timer gates the call | per call: 1 GetNearestVisibleWP while wpCurrent is NULL (loop gWPNum, 0 when no waypoints); 1 trap->EntitiesInBox (2048x2048x512 box, cap 256) whenever no waypoint destination + loop over numEnts (<=256, breaks at first acceptable item); box traces: destination path 2 best / 4 worst (48u, 48u, 48u, ~107u, MASK_SOLID); no-destination path BotFallbackNavigation (5336; 2 traces typical, 6 at a wall/ledge, up to 2 + 12x7 = 86 when it must pick a new target) and, only if that returns 0 or weapon is not saber, 1 best / 3 worst 48u box traces |
| NewBotAI_ScanForEnemies | ai_main.c:12856 | 84 | pick target client: nearest by distance scaled by enemy health (0.25..1), gripper wins instantly, Jedi Master forced to distance 1 | NewBotAI (12967), every think when g_newBotAITarget < 0. No timer | 0 traces; 1 loop i<MAX_CLIENTS (32); per client passing PassStandardEnemyChecks: 1 BotPVSCheck (= 1 trap->InPVS unless RMG && bot_pvstype), PassLovedOneCheck (loop <= bs->lovednum, strcmp), 1 VectorLength (sqrt), 1 vectoangles (unused result), BotMindTricked. Worst = 31 InPVS per bot per think |
| NewBotAI (starts 12943; body is outside region) | ai_main.c:12943 | 3 in region | top-level new-AI think | BotAI (821) when g_newBotAI is set, every bot think | not mapped here (region ends 12945) |
| NewBotAI | ai_main.c:12943 | ~385 (12943-13327) | "New" per-bot think (g_newBotAI != 0): pick closest enemy (no LOS/FOV requirement), run force-side combat routine (NewBotAI_XvY) + inline 4-direction combat movement, else NewBotAI_DoAloneStuff | BotAI (ai_main.c:821), once per bot per BotAIStartFrame call when g_newBotAI.integer | Always: NewBotAI_ScanForEnemies (12967; loop 32 clients, InPVS each, 0 traces). Enemy found: 1 OrgVisible line trace unbounded length (13004), +1 (13016) if not visible and PERS_ATTACKER valid. Enemy visible: XvY (GetAim loop <=MAX_CLIENTS + GetMovement est. up to ~9 line traces incl. Bot_CheckMovementPaths 3 + GetAttack->Bot_ExecuteSaberCombat 1-3) + 4 box traces 32u (13144-13159) + BotShouldAttackNow->BotCanHitEnemy 1 box (13089, <=128u) or MeleeCombatHandling 3 box 4096u (13120) + second NewBotAI_GetAttack (13237; 1-3 again). No enemy / not visible and >300u: NewBotAI_DoAloneStuff (12993/13023/13034): EntitiesInBox 2048x2048x512 + 2-4 box traces, or BotFallbackNavigation (2 .. ~80+) + 1-3 box traces |
| StandardBotAI | ai_main.c:13332 | ~1573 (13332-14904) | Classic JKA per-bot think (g_newBotAI == 0), heavily modified: waypoint following, enemy scan, inline calls into NewBotAI_XvY combat, saber/melee handling, wall/stuck checks, jump/duck/strafe traces, firing, force use | BotAI (ai_main.c:823), once per bot per BotAIStartFrame call when !g_newBotAI.integer | Every frame: GetNearestVisibleWP if !wpCurrent (13808; loop gWPNum, InPVS + 1 box trace per WP within 800u; 0 if gWPNum==0); ScanForEnemies UNCONDITIONALLY (13821; loop 33 slots, InPVS each valid enemy, 1 line trace per candidate closer than running best and in FOV/heard); BotScanForLeader loop 32 (13833, only while leaderless); WPOrgVisible 1-2 (13870, if wpCurrent); OrgVisible 1 (13913, if currentEnemy); CheckForFunc 0-2 (13950/13957); GetIdealDestination (14018); BotFallbackNavigation (14085, only !wpCurrent && saber: 0 / 2-6 / ~80+); OrgVisible (14215, enemy known not visible); BotShouldAttackNow 0-1 box (14288); MeleeCombatHandling 3 box (14327); CTFFlagMovement 0-1; EntityVisibleBox 0-1 (14378, 14765); OrgVisible (14457 JM only); wall box trace 32u (14476) every moving frame; BotTrace_Jump 0 (14646); BotTrace_Duck 2-14 (14650); BotTrace_Strafe 1-3 (14665); CheckForFriendInLOF 1 box 2048u (14775 when firing, 14811 EVERY frame in team gametypes). Plus, when enemy visible last frame: NewBotAI_XvY (13600-13610) and NewBotAI_GetAttack (14186) |
| BotAIStartFrame | ai_main.c:14913 | ~108 (14913-15020) | Server-frame entry point for all bots: cvar refresh (1/s), bot spawn queue, waypoint editor render, event tracker, run BotAI for every bot, then build+send a usercmd for every bot | vmMain/ge export (g_main.c:4606, 4691) <- GVM_BotAIStartFrame (sv_gameapi.cpp:140) <- SV_BotFrame (sv_bot.cpp:605-611) <- SV_Frame once per call (sv_main.cpp:1247 listen server: every SV_Frame = every client frame; sv_main.cpp:1290 dedicated: once per SV_Frame, Com_Frame sleeps SV_FrameMsec so ~sv_fps); also 4x during SV_SpawnServer (sv_init.cpp:634, 694) | 3 loops over MAX_CLIENTS (14926 no-op validation loop; 14990 AI; 15007 input) + UpdateEventTracker loop MAX_CLIENTS (2338) + G_CheckBotSpawn (loop BOT_SPAWN_QUEUE_DEPTH + G_CheckMinimumPlayers). No traces itself. trap->Milliseconds once per call |
| BotAISetup | ai_main.c:15027 | ~42 (15027-15068) | Register bot cvars; on non-restart memset botstates[] and trap->BotLibSetup | G_InitGame (g_main.c:462), once per map load / map_restart | No loops, no traces |
| BotAIShutdown | ai_main.c:15075 | ~19 (15075-15093) | restart: BotAIShutdownClient for each in-use bot; non-restart: trap->BotLibShutdown only | G_ShutdownGame (g_main.c:670), once | Loop MAX_CLIENTS only when restart; no traces |
| (macro) _ADVANCEDBOTSHIT | ai_main.c:12941 | 1 | #define 1; selects NewBotAI_DoAloneStuff vs (commented-out) StandardBotAI fallback at 12992-12996, 13033-13037 | compile time | n/a |
| (global) gUpdateVars | ai_main.c:14906 | 1 | next level.time at which BotAIStartFrame re-reads bot cvars (14951-14962, every 1000 ms) | BotAIStartFrame | n/a |

## 4. Trace inventory

### 4a. Every call site

| Line | Call (mask, box or line, distance) | Enclosing function | In loop (bound) | Timer or condition gate | Notes |
|---|---|---|---|---|---|
| ai_main.c:1117 | JP_Trace line, MASK_SOLID, org1->org2 unbounded | OrgVisible | no (callers loop: ScanForEnemies) | none inside | generic LOS; ignore passed through (ScanForEnemies passes -1) |
| ai_main.c:1133 | JP_Trace line, MASK_SOLID, bot origin -> wpCurrent origin | WPOrgVisible | no | caller 13870: every frame with bs->wpCurrent | always executed |
| ai_main.c:1137 | JP_Trace line, MASK_PLAYERSOLID, same segment | WPOrgVisible | no | only if 1133 was clear (the common case) | second trace exists only to detect ET_SPECIAL force fields; doubles the per-frame cost |
| ai_main.c:1166 | JP_Trace line, MASK_SOLID | OrgVisibleBox | no (caller loops gWPNum) | RMG.integer only | |
| ai_main.c:1170 | JP_Trace box (caller mins/maxs; 30x30x2 from GetNearestVisibleWP), MASK_SOLID | OrgVisibleBox | no (caller loops gWPNum) | !RMG | |
| ai_main.c:1194 | JP_Trace line, MASK_SOLID, 64u straight down | CheckForFunc | no | callers: 2546/2552 distance-gated, 13950/13957 WP-flag-gated; no timers | result entity classname strstr "func_" |
| ai_main.c:1231 | trap->InPVS(p1,p2) | BotPVSCheck | no (callers loop) | skipped when RMG.integer && bot_pvstype.integer | |
| ai_main.c:1269 | BotPVSCheck (InPVS) then OrgVisibleBox (box 30x30x2, MASK_SOLID, < bestdist: 800u / 300u RMG) | GetNearestVisibleWP | yes: i < gWPNum | per WP: only if flLen < bestdist (shrinks as better WPs found); short-circuit PVS before trace | distance computed with VectorLength (sqrt) for every WP; gWPNum==0 => nothing runs |
| ai_main.c:1717 | JP_Trace box (-15,-15,-8)..(15,15,DEFAULT_MAXS_2), MASK_PLAYERSOLID, 32u toward goal | BotTrace_Strafe | no | on ground and yaw within 60 deg of move dir | other bots block this trace (PLAYERSOLID) |
| ai_main.c:1734 | JP_Trace same box, shifted 32u right, 32u | BotTrace_Strafe | no | only if 1717 hit | |
| ai_main.c:1749 | JP_Trace same box, shifted 32u left, 32u | BotTrace_Strafe | no | only if 1734 hit | |
| ai_main.c:1795 | JP_Trace box (-15,-15,-18)..(15,15,32), MASK_PLAYERSOLID, 64u | BotTrace_Jump | no | UNREACHABLE: function returns at 1790 (dist<64 always) | dead code |
| ai_main.c:1805 | JP_Trace same box, +32 z, 64u | BotTrace_Jump | no | unreachable; would need 1795 fraction<0.5 | dead code |
| ai_main.c:1824 | JP_Trace same box, 128u fwd / 96 down | BotTrace_Jump | no | unreachable | dead code |
| ai_main.c:1834 | JP_Trace same box, +32 z, 128u | BotTrace_Jump | no | unreachable; needs 1824 fraction==1 | dead code |
| ai_main.c:1845 | JP_Trace same box, 48u | BotTrace_Jump | no | unreachable; needs enemy visible && dist<512 | dead code |
| ai_main.c:1855 | JP_Trace same box, +40 z, 80u | BotTrace_Jump | no | unreachable; needs 1845 fraction<0.7 | dead code |
| ai_main.c:1889 | JP_Trace box (-15,-15,-23)..(15,15,8), MASK_PLAYERSOLID, 4u toward goal | BotTrace_Duck | no | none (always) | if blocked -> return 0 (1 trace total) |
| ai_main.c:1908 | JP_Trace box (-15,-15,0)..(15,15,32) at origin+31, MASK_PLAYERSOLID, 4u | BotTrace_Duck | no | only if 1889 clear | if clear -> return 0 (2 traces total, common case) |
| ai_main.c:1949 | JP_Trace line, MASK_PLAYERSOLID, origin -> 32u sideways + 64 down (~72u) | BotTrace_Duck | yes: fixed i<4 | only if 1908 blocked | 4 traces; >=2 "ledges" -> return |
| ai_main.c:1991 | JP_Trace box (0..32 high) MASK_PLAYERSOLID, 24u in 4 directions | BotTrace_Duck | yes: fixed i<4 | after ledge test passes | 4 traces |
| ai_main.c:2010 | JP_Trace same box, 48u up | BotTrace_Duck | no | nearWall >= 1 | |
| ai_main.c:2026 | JP_Trace line, MASK_PLAYERSOLID, 256u down | BotTrace_Duck | no | after wall test | altitude test |
| ai_main.c:2042 | JP_Trace box, 48u up | BotTrace_Duck | no | groundDistance <= 96 | identical segment/box to 2010 (duplicate work when nearWall>=1) |
| ai_main.c:2048 | JP_Trace box, 32u fwd + 24 up | BotTrace_Duck | no | same as 2042 | |
| ai_main.c:2474 | BotPVSCheck(enemy origin, bs->eye) -> trap->InPVS | ScanForEnemies | yes: i <= MAX_CLIENTS (33) | after client/team/PassStandardEnemyChecks filters; caller gate 13818 always true => every frame | 1 InPVS per valid enemy candidate |
| ai_main.c:2485 | OrgVisible(bs->eye, enemy ps.origin, ignore -1): line MASK_SOLID unbounded | ScanForEnemies | yes: i <= MAX_CLIENTS | distcheck < closest && (FOV 90 && !mindtricked, or BotCanHear) | trace is spent BEFORE the 128u stickiness test (2491/2503), so with a current enemy every in-FOV candidate (incl. the current enemy) is traced and then rejected, `closest` never shrinks |
| ai_main.c:2546 | CheckForFunc(bs->origin, bs->client): line 64u down | WaitingForNow | no | xy dist to wpCurrent < 16 && frame_Waypoint_Len > 100 | |
| ai_main.c:2552 | CheckForFunc(bs->origin, bs->client): line 64u down | WaitingForNow | no | xy dist < 64 && frame_Waypoint_Len > 64 | |
| ai_main.c:2775 | BotPVSCheck(bs->origin, ent->s.pos.trBase) | GetNearestBadThing (starts 2693, call is just past line 2700) | yes: i < level.num_entities | dangerous-entity filter && glen < bestdist*factor | caller gated by escapeDirTime (3968) |
| ai_main.c:2777 | JP_Trace line, MASK_SOLID, bot origin -> projectile | GetNearestBadThing | yes: i < level.num_entities | after 2775 PVS pass | |
| (none) | trap->Trace direct, trap->PointContents, trap->EntitiesInBox, G_Find, G_RadiusList, EntityVisibleBox | - | - | - | no call sites of these in lines 1-2700 (EntityVisibleBox is defined at 3358) |
| g_syscalls.c:259 (context) | JP_Trace = BeginHack + trap->Trace + EndHack | - | each of BeginHack/EndHack loops i < level.num_entities (g_syscalls.c:194, 248) on the normal non-duel/non-race path | - | every JP_Trace row above also costs 2 x O(level.num_entities) entity scans; passEntityNum -1 indexes g_entities[-1] (g_syscalls.c:166, 188) |
| ai_main.c:2775 | BotPVSCheck(bs->origin, ent->s.pos.trBase) = trap->InPVS | GetNearestBadThing | yes (level.num_entities) | only for dangerous ents with glen < 800*factor; caller gated by wpCurrent != NULL, destinationGrabTime, escapeDirTime+4000 | short-circuits before the trace |
| ai_main.c:2777 | JP_Trace line, MASK_SOLID, <=800u (<=400u for non-explosive) | GetNearestBadThing | yes (level.num_entities) | same as above and InPVS passed | one per qualifying projectile/sentry per bot per frame |
| ai_main.c:2949 | GetNearestVisibleWP(carrier origin, 0) | BotGetFlagBack | no (itself O(gWPNum) InPVS + box trace) | bs->wpDestSwitchTime < level.time; CTF RETRIEVAL only | timer re-armed only on success (2954) => repeats every call on failure |
| ai_main.c:3015 | GetNearestVisibleWP(carrier origin, 0) | BotGuardFlagCarrier | no | bs->wpDestSwitchTime < level.time; CTF GUARDCARRIER only | same failure-repeat as 2949 |
| ai_main.c:3084 | JP_Trace box 30x30x10, MASK_SOLID, <=128u (WP_KEEP_FLAG_DIST) | GetNewFlagPoint | no | bestdist <= 128; called while flag is FL_DROPPED_ITEM | passEnt = flag entity |
| ai_main.c:3099 | JP_Trace box 30x30x10, MASK_SOLID, WP->flag distance (< current best) | GetNewFlagPoint | yes (gWPNum) | testdist < bestdist | up to gWPNum box traces per bot per call per dropped flag; no timer; result is global (flagRed/flagBlue) but recomputed by every bot |
| ai_main.c:3362 | JP_Trace MASK_SOLID, box if mins/maxs given else line; caller-defined length | EntityVisibleBox | no | none | called from 3445 (2x2x2 box, <1024u), 14378 and 14765 (NULL mins/maxs = line) |
| ai_main.c:3445 | EntityVisibleBox box 2x2x2, MASK_SOLID, < BOT_MIN_SIEGE_GOAL_SHOOT (1024u) | Siege_TargetClosestObjective | no | goalent->takedamage && testdistance < 1024; Siege only | 1 box trace |
| ai_main.c:3514 | GetNearestVisibleWP(enemy origin, -1) | Siege_DefendFromAttackers | no | an enemy exists; Siege only; sets destinationGrabTime +10000 only on success | O(gWPNum) |
| ai_main.c:3671 | BotPVSCheck(bs->origin, dif) | SiegeTakesPriority | no | attacker with no objective && bs->shootGoal | |
| ai_main.c:3677 | JP_Trace line MASK_SOLID to shootGoal centre | SiegeTakesPriority | no | PVS passed | |
| ai_main.c:3696 | BotPVSCheck(bs->origin, dif) | SiegeTakesPriority | no | defender && bs->shootGoal | |
| ai_main.c:3702 | JP_Trace line MASK_SOLID to shootGoal centre | SiegeTakesPriority | no | PVS passed | |
| ai_main.c:3720 | BotPVSCheck(bs->origin, dif) | SiegeTakesPriority | no | other siegeState && bs->shootGoal | |
| ai_main.c:3726 | JP_Trace line MASK_SOLID to shootGoal centre | SiegeTakesPriority | no | PVS passed | |
| ai_main.c:3791 | GetNearestVisibleWP(JM client origin, entnum) | JMTakesPriority | no | GT_JEDIMASTER, bs->destinationGrabTime < level.time | re-armed +4000 only on success |
| ai_main.c:3795 | GetNearestVisibleWP(saber ent currentOrigin, entnum) | JMTakesPriority | no | same as 3791 (saber not held) | |
| ai_main.c:4122 | GetNearestVisibleWP(revengeEnemy origin, 0) | GetIdealDestination | no | revengeEnemy alive && bs->wpDestSwitchTime < level.time | timer +5-10s only on success |
| ai_main.c:4145 | GetNearestVisibleWP(squadLeader origin, 0) | GetIdealDestination | no | squadLeader alive && wpDestSwitchTime < level.time | timer +5-10s only on success |
| ai_main.c:4201 | GetNearestVisibleWP(currentEnemy origin, 0) | GetIdealDestination | no | currentEnemy, not (too close or chicken), bChicken != 2, wpDestSwitchTime < level.time | timer +1-5s (0.3-1s in GT_SINGLE_PLAYER) only on success |
| ai_main.c:4642 | JP_Trace box 30x30x56, MASK_SOLID, 4096u down from enemy origin, passEnt -1 | MeleeCombatHandling | no | currentEnemy; caller: melee weapon && frame_Enemy_Len <= 256 | per-frame, no timer |
| ai_main.c:4649 | JP_Trace box 30x30x56, MASK_SOLID, 4096u down from bot origin | MeleeCombatHandling | no | same | per-frame |
| ai_main.c:4664 | JP_Trace box 30x30x56, MASK_SOLID, 4096u down from midpoint | MeleeCombatHandling | no | same | per-frame |
| ai_main.c:4818 | JP_Trace line MASK_SOLID, headlevel -> predicted spot minus gravity drop, passEnt ENTITYNUM_NONE | G_NewBotAIAimLeading | no | projectileSpeed != 0 && enemy airborne && not force-jumping upward && no jetpack | per-frame in NewBotAI aim; never for saber (speed 0) |
| ai_main.c:4843 | JP_Trace line MASK_SOLID, headlevel -> (0.5s lead, -1024 z) | G_NewBotAIAimLeading | no | projectileSpeed == 0 && weapon == WP_DEMP2 && doAltAttack && (enemy grounded or falling) | |
| ai_main.c:5403 | JP_Trace box 30x30x40 (mins z -8), MASK_PLAYERSOLID, 32u forward | BotFallbackNavigation | no | every call unless (currentEnemy && frame_Enemy_Vis) | unconditional, per-frame per wandering bot |
| ai_main.c:5413 | JP_Trace line MASK_SOLID, 300u down from origin+64fwd+50up | BotFallbackNavigation | no | same | unconditional |
| ai_main.c:5424 | JP_Trace box 30x30x40, MASK_PLAYERSOLID, from bs->origin to (forward + 32*right) | BotFallbackNavigation | no | (wallDistance < 20 or ledge) && lastWallHitTime < level.time (500ms cooldown) | BUG: end is a point within ~33u of world origin (0,0,0), so trace length = distance from bot to map origin |
| ai_main.c:5428 | JP_Trace box 30x30x40, MASK_PLAYERSOLID, from bs->origin to (forward - 32*right) | BotFallbackNavigation | no | same | same BUG |
| ai_main.c:5439 | JP_Trace line MASK_SOLID, 300u down, 32u left | BotFallbackNavigation | no | same | |
| ai_main.c:5447 | JP_Trace line MASK_SOLID, 300u down, 32u right | BotFallbackNavigation | no | same | |
| ai_main.c:5507 | IsPositionReachable(testPos) (1 box + up to 6 line traces) | BotFallbackNavigation | yes (12 attempts, break on first success) | !hasTarget && lastWallHitTime < level.time | worst 84 traces in one frame; retried EVERY frame while no direction passes (no back-off) |
| ai_main.c:5544 | IsPositionReachable(200u random dir) | BotFallbackNavigation | no | stuckCounter > 20 - unreachable (counter is reset at > 5) | dead branch |
| ai_main.c:5610 | JP_Trace line MASK_SOLID, 600u down | FollowGroundContours | yes (7 dirs x up to 5 dists) | none | dead code (SmartExploration uncalled) |
| ai_main.c:5664 | IsPositionReachable(testPos) | ExpandingSpiralSearch | yes (8 radii x 12 angles = 96) | none | dead code |
| ai_main.c:5708 | JP_Trace box 30x30x32, MASK_PLAYERSOLID, <=300u | MoveTowardLastWaypoint | no | lastKnownWaypointPos != 0 (never set) | dead code |
| ai_main.c:5733 | JP_Trace box 30x30x32 (mins z 0), MASK_PLAYERSOLID, origin -> targetPos (150-400u from 5507) | IsPositionReachable | no | none | returns qfalse if fraction < 0.7 |
| ai_main.c:5758 | JP_Trace line MASK_SOLID, 400u down (from +50) | IsPositionReachable | yes ((int)(pathDistance/100)+1 = 2..5 for 150-400u) | box trace passed | last iteration duplicates previous when distance is a multiple of 100 |
| ai_main.c:5787 | JP_Trace line MASK_SOLID, 400u down at target | IsPositionReachable | no | all path checks passed | duplicates the last 5758 trace (same XY/Z when target z == origin z, true for all callers) |
| (none in 2690-5800) | direct trap->Trace, trap->PointContents, trap->EntitiesInBox, OrgVisible, OrgVisibleBox, WPOrgVisible, CheckForFunc, G_Find | - | - | - | all traces in the region go through JP_Trace; InPVS only via BotPVSCheck |
| ai_main.c:6220 | JP_Trace MASK_SOLID, BOX (-15,-15,-22)..(15,15,32), 32u left | StrafeTracing | no | 30% RNG (6208) | DEAD: StrafeTracing is never called anywhere in codemp |
| ai_main.c:6225 | JP_Trace MASK_SOLID, BOX same, 32u right | StrafeTracing | no | 30% RNG (6208) | DEAD (see above) |
| ai_main.c:6269 | JP_Trace MASK_SOLID, BOX same, 32u to chosen side | StrafeTracing | no | after both-sides-blocked early return (6229) | DEAD; duplicates one of the two traces above (same start/end as 6220 or 6225) |
| ai_main.c:6280 | JP_Trace MASK_SOLID, LINE, 32u down from side point | StrafeTracing | no | only if 6269 trace clear | DEAD; ledge check |
| ai_main.c:6386 | JP_Trace MASK_PLAYERSOLID, BOX (-3..3)^3, 2048u along view dir from bs->eye | CheckForFriendInLOF | no | none inside. Callers: 14775 (PrimFiring or AltFiring) and 14811 (every think if level.gametype >= GT_TEAM and not firing) | LIVE and effectively per-think in team gametypes; longest trace in region; box trace vs players + world |
| ai_main.c:6535 | JP_Trace MASK_SOLID, BOX (-15,-15,-7)..(15,15,7), <=256u (BOT_FLAG_GET_DISTANCE) | CTFFlagMovement | no | flagRed && flagBlue, wpDestination is a flag, that flag is dropped, distance <= 256 | LIVE but rare (CTF, dropped flag nearby); runs every think while condition holds until bs->wantFlag path takes over? NOTE: wantFlag is never set here, so trace repeats each think while within 256u |
| ai_main.c:6558 | G_Find(dp, FOFS(classname), "detpack") | BotCheckDetPacks | yes: while loop over all entities (level.num_entities, strcmp each) until own detpack found | caller gate bs->cur_ps.hasDetPackPlanted (14385); no timer | O(num_entities) string compares per think while a detpack is planted |
| ai_main.c:6597 | OrgVisible (LINE, MASK_SOLID), enemy origin -> detpack, < 256u (BOT_PLANT_BLOW_DISTANCE; short-circuit on enLen first) | BotCheckDetPacks | no | enemy valid + (frame_Enemy_Vis or plant < 5s old via bs->plantContinue), enLen <= myLen, enLen < 256 | sets bs->plantKillEmAll = level.time + 500 |
| ai_main.c:6668 | JP_Trace MASK_SOLID, LINE, 64u forward from bs->origin | BotSurfaceNear | no | caller 14414: bs->plantTime < level.time, enemy lost, has mine/detpack, bs->plantDecided / distance checks | cheap, rare |
| ai_main.c:7217 | OrgVisible (LINE, MASK_SOLID) bs->eye -> enemy ps.origin, <= 1500u | NewBotAI_Lightning | no | FP_LIGHTNING active (caller), enemy valid, len <= 1500, FP >= 25, enemy FP > 0, enemy not absorbing | REDUNDANT with bs->frame_Enemy_Vis: NewBotAI already traced the same segment at 13004 this think |
| ai_main.c:7252 | OrgVisible (LINE, MASK_SOLID) bs->eye -> enemy ps.origin, unbounded length | NewBotAI_Draining | no | FP_DRAIN active (caller); own health < 100, enemy FP != 0, enemy not absorbing (short-circuit order) | REDUNDANT with bs->frame_Enemy_Vis (same endpoints as 13004) |
| ai_main.c:7263 | OrgVisible (LINE, MASK_SOLID) bs->eye -> enemy ps.origin, unbounded length | NewBotAI_MindTrick | no | FP_TELEPATHY active (caller 12117), health <= 50, enemy FP > 0, enemy not absorbing | REDUNDANT with bs->frame_Enemy_Vis |
| ai_main.c:8044 | JP_Trace MASK_PLAYERSOLID, BOX (-8..8)^3, bs->origin -> predicted enemy pos, <= 128u (x1.1 dual = 140.8, x1.2 staff = 153.6) | BotCanHitEnemy | no | enemy client valid, distance <= maxRange, 60deg view cone | Called up to 3x in one think: BotShouldAttackNow->BotCanAttackNow (8598), BotShouldAttackNow->BotShouldAttack (8602), BotExecuteAttack->BotCanAttackNow (8327). Each call re-predicts with fresh random jitter so results are not identical. Upstream gates: frame_Enemy_Len <= 128 (13083/14282), bs->nextAttackTime, bs->attackRecoveryTime, weaponstate |
| (none) | trap->Trace direct, trap->PointContents, trap->InPVS, BotPVSCheck, trap->EntitiesInBox, EntityVisibleBox, OrgVisibleBox, CheckForFunc, GetNearestVisibleWP | - | - | - | No call sites of these kinds exist in 5790-8700 |
| ai_main.c:9698 | trap->Trace LINE, MASK_PLAYERSOLID & ~CONTENTS_BODY, origin+24 -> 128u along view forward (pitch included) +24 z | Bot_CheckAndInteractWithObstacle | no | Caller gate only: noUseTime < level.time && lastObstacleTime < level.time-3000 (lastObstacleTime set only when fn returns qtrue => effectively every frame while nothing is found). 10885: saber && dist<=100; 10944: dist>200 | Result used only if tr.entityNum < ENTITYNUM_WORLD (world hits ignored). Good candidate for a real time gate |
| ai_main.c:9784 | trap->Trace LINE, MASK_PLAYERSOLID, origin+24 -> 32u fwd +48 z | Bot_CheckAndInteractWithObstacle | no | inCombat && isObstacle && heightDif>48 && dist<150 && (absmax[2]-origin[2] < 48) | UNREACHABLE: heightDif (9748) and the 9773 test are the same quantity, >48 and <48 contradict |
| ai_main.c:9901 | trap->Trace LINE, MASK_PLAYERSOLID & ~CONTENTS_BODY, 64u fwd from origin+64*left(+24) | Bot_CheckAndInteractWithObstacle | no | inCombat && isObstacle and weapon NOT saber/melee/rocket/thermal/detpack (those return at 9885); not door/button/plat | "left" is a correct left vector here |
| ai_main.c:9910 | trap->Trace LINE, same mask, 64u fwd from origin+64*"right"(+24) | Bot_CheckAndInteractWithObstacle | no | same as 9901 | "right" is actually the UP vector (AngleVectors arg order at 9892) so this probes 64u above the bot |
| ai_main.c:9971 | JP_Trace BOX mins(-15,-15,-8) maxs(15,15,32), MASK_PLAYERSOLID, origin -> 48u view forward | Bot_ExecuteSaberCombat | no | NONE - first statement, runs before every early return (holstered 10002, avoidance 10113, special-active 10205, out of range 10221) | Only box trace in region. Includes CONTENTS_BODY so the enemy itself counts as "wall" at dist < ~24+. Runs up to 2x per bot per frame (GetAttack double call) |
| ai_main.c:10052 | trap->Trace LINE, MASK_PLAYERSOLID & ~CONTENTS_BODY, origin+24 -> dist (<=200u) toward enemy +24 z | Bot_ExecuteSaberCombat | no | currentEnemy && frame_Enemy_Vis && dist<=200; no timer | Result used only for non-world entity hits. Also runs while a special is active |
| ai_main.c:10069 | trap->Trace LINE, MASK_PLAYERSOLID, origin+24 -> 48u toward enemy +48 z | Bot_ExecuteSaberCombat | no | 10052 hit fraction<0.8 on entityNum<ENTITYNUM_WORLD and obstacle absmax[2]-origin[2] < 64 | Rare |
| ai_main.c:10795 | trap->Trace LINE, MASK_PLAYERSOLID, origin+24 -> 64u fwd +24 z | Bot_CheckMovementPaths | no | none (every call) | Includes BODY: enemy/teammates in front count as blocked |
| ai_main.c:10800 | trap->Trace LINE, MASK_PLAYERSOLID, origin+24 -> 32u along "left" | Bot_CheckMovementPaths | no | none | "left" is the UP vector (AngleVectors(…, forward, right, left) at 10779): probes 32u upward, nearly useless |
| ai_main.c:10805 | trap->Trace LINE, MASK_PLAYERSOLID, origin+24 -> 32u along "right" | Bot_CheckMovementPaths | no | none | "right" was negated at 10780 so this probes actual LEFT; true right side is never probed |
| ai_main.c:10904 | trap->Trace LINE, MASK_PLAYERSOLID, origin+24 -> 32u fwd +24 z | NewBotAI_GetMovement | no | weapon saber && dist<=100 && dist>90 | per frame in that band |
| ai_main.c:10927 | trap->Trace LINE, MASK_PLAYERSOLID, origin+24 -> 32u back +24 z | NewBotAI_GetMovement | no | weapon saber && dist<80 | per frame in close saber fight |
| ai_main.c:11051 | trap->Trace LINE, MASK_PLAYERSOLID, origin+24 -> 32u back +24 z | NewBotAI_GetMovement | no | generic path, dist < adjustedMin-10 | if blocked -> second Bot_CheckMovementPaths (3 more traces, duplicates of 10951 call) |
| ai_main.c:11078 | trap->Trace LINE, MASK_PLAYERSOLID, origin+24 -> 32u fwd +24 z | NewBotAI_GetMovement | no | generic path, dist > adjustedMax-20 | mostly redundant with 10795 (64u fwd) done microseconds earlier; if blocked -> second Bot_CheckMovementPaths |
| ai_main.c:11180 | trap->Trace LINE, MASK_PLAYERSOLID, origin+24 -> 16u fwd +24 z | NewBotAI_GetMovement | no | strafeDir==0 && dist>115 | UNREACHABLE: code only gets here when dist <= adjustedMax-20 <= 110 |
| ai_main.c:11198 | trap->Trace LINE, MASK_PLAYERSOLID, origin+24 -> 16u back +24 z | NewBotAI_GetMovement | no | strafeDir==0 && dist<105 (in-band, no strafe burst) | |
| (calls) ai_main.c:10885 | Bot_CheckAndInteractWithObstacle -> 1-3 line traces | NewBotAI_GetMovement | no | saber && dist<=100 && noUseTime < level.time && lastObstacleTime < level.time-3000 | see 9698 |
| (calls) ai_main.c:10944 | Bot_CheckAndInteractWithObstacle -> 1-3 line traces | NewBotAI_GetMovement | no | same timers && dist>200 (the !bs->currentEnemy half is always false here) | |
| (calls) ai_main.c:10951 | Bot_CheckMovementPaths -> 3 line traces | NewBotAI_GetMovement | no | none | every frame on generic path |
| (calls) ai_main.c:11058 / 11085 | Bot_CheckMovementPaths -> 3 line traces | NewBotAI_GetMovement | no | short probe blocked (fraction<0.8) | same-frame repeat of 10951 |
| (none) | No trap->PointContents, trap->InPVS, trap->EntitiesInBox, OrgVisible*, BotPVSCheck, BotCanHitEnemy or G_Find call sites exist in 8680-11215 | - | - | - | Also no for/while loops at all in the region (no O(MAX_CLIENTS) / O(num_entities) scans) |
| ai_main.c:12369 | JP_Trace, BOX (-15,-15,DEFAULT_MINS_2)..(15,15,DEFAULT_MAXS_2), mask CONTENTS_BODY only, ps.origin -> next cap-route point (length = one route step, unbounded) | NewBotAI_CapRoute | no | only when g_movementStyle == MV_TRIBES (caller 12980), level.gametype == GT_CTF and pers.activeCapRoute != 0 (12313); then every think | not a world-solid trace (bodies only); hit -> route abandoned |
| ai_main.c:12570 | GetNearestVisibleWP(bs->origin, bs->client) (loop over gWPNum; per candidate BotPVSCheck + OrgVisibleBox at 1269) | NewBotAI_DoAloneStuff | no | `shouldNavigate \|\| !bs->wpCurrent` (12568) and `!bs->wpCurrent` (12569); no timer | with gWPNum == 0 returns -1, so wpCurrent stays NULL and this is re-called on EVERY DoAloneStuff call (0 traces, pure call overhead) |
| ai_main.c:12612 | trap->EntitiesInBox(mins, maxs, radiusEnts, 256); box = origin +/- (1024,1024,256) i.e. 2048 x 2048 x 512 | NewBotAI_DoAloneStuff | no (result then looped 12613, bound numEnts <= 256, break at first accepted item) | `!destination` (12608) = no waypoint destination; no timer | with gWPNum == 0 this runs on every DoAloneStuff call for every enemy-less bot. Buffer int radiusEnts[256] (12487) matches maxcount 256 |
| ai_main.c:12709 | JP_Trace, BOX (-15,-15,-8)..(15,15,32), MASK_SOLID, origin -> origin + 48 * dir-to-destination | NewBotAI_DoAloneStuff | no | `destination` (12696); every call with a destination | obstacle probe; always paid on the destination path |
| ai_main.c:12719 | JP_Trace, same BOX, MASK_SOLID, 48u, start/end raised +24 | NewBotAI_DoAloneStuff | no | destination && previous tr.fraction < 0.9 (12711) | low-fence jump test |
| ai_main.c:12732 | JP_Trace, same BOX, MASK_SOLID, 48u, start/end raised +40 | NewBotAI_DoAloneStuff | no | destination && obstacle && fence test fraction <= 0.7 (12727) | wall jump test; else random strafe |
| ai_main.c:12755 | JP_Trace, same BOX, MASK_SOLID, origin -> origin + 96 * dir, z - 48 (about 107u) | NewBotAI_DoAloneStuff | no | `destination` (12696); every call with a destination | pit probe; fraction == 1.0 -> jump (bs->jumpTime cooldown 1500 ms gates only the jump, not the trace) |
| ai_main.c:12770 | (indirect) BotFallbackNavigation(bs) at 5336: JP_Trace box 32u MASK_PLAYERSOLID (5403) + line 300u down MASK_SOLID (5413) always; +2 box 32u (5424, 5428) +2 line 300u (5439, 5447) at wall/ledge when lastWallHitTime < level.time; target generation loop of up to 12 attempts x IsPositionReachable (5725: 1 box 150..400u at 5733 + up to 5 line 400u at 5758 + 1 line 400u at 5787) | NewBotAI_DoAloneStuff | callee loop: 12 attempts | `!destination` (12768) && weapon == WP_SABER (12769); no timer in DoAloneStuff | this is the normal per-think path for a saber bot on a map with no waypoints and no wanted item nearby. Callee is outside region; listed because it dominates the cost |
| ai_main.c:12786 | JP_Trace, BOX (-15,-15,-8)..(15,15,32), MASK_SOLID, origin -> origin + 48 * forward(ideal_viewangles) | NewBotAI_DoAloneStuff | no | `!destination` and (weapon != saber or BotFallbackNavigation returned 0) | fallback obstacle probe |
| ai_main.c:12796 | JP_Trace, same BOX, MASK_SOLID, 48u, +24 | NewBotAI_DoAloneStuff | no | previous fraction < 0.9 (12788) | fence test |
| ai_main.c:12809 | JP_Trace, same BOX, MASK_SOLID, 48u, +40 | NewBotAI_DoAloneStuff | no | fence test fraction <= 0.7 (12804) | wall test; else random yaw turn 45..135 |
| ai_main.c:12894 | BotPVSCheck(ent->client->ps.origin, bs->eye) = trap->InPVS (1231) unless RMG && bot_pvstype (distance test) | NewBotAI_ScanForEnemies | YES: for i < MAX_CLIENTS (12890) | evaluated only after `ent->inuse && PassStandardEnemyChecks` short-circuit; no timer; whole function runs every NewBotAI think when g_newBotAITarget < 0 | up to 31 InPVS per bot per think; N bots in FFA = N*(N-1) InPVS per server frame of bot thinks (25 bots = 600) |
| ai_main.c:12445 | (indirect) StandardBotAI(bs, thinktime) - full legacy AI incl. its own traces | NewBotAI_Tribes | no | MV_TRIBES && jetpack starting item (13041) | only in Tribes mode |
| (none) | no trap->Trace, trap->PointContents, direct trap->InPVS, OrgVisible*, G_Find call sites exist in 11205-12945 | - | - | - | the only direct trap->Trace near the region is 11198 (just before it); force-power deciders (11233-11882) do zero traces and rely on bs->frame_Enemy_Vis / bs->frame_Enemy_Len computed in NewBotAI (13004-13030) |
| ai_main.c:12967 | NewBotAI_ScanForEnemies(bs) -> loop i<MAX_CLIENTS (12890), BotPVSCheck/trap->InPVS per valid enemy (12894), 0 traces | NewBotAI | callee loops 32 | g_newBotAITarget.integer < 0 (default -1) -> every think | No LOS, FOV or range limit: on a map where PVS culls nothing it returns an enemy whenever any valid enemy exists anywhere |
| ai_main.c:12972 | level.maxclients bounds test on g_newBotAITarget | NewBotAI | no | g_newBotAITarget >= 0 | then indexes level.clients[closestID] with closestID possibly -1 (12975) - see F_bugs |
| ai_main.c:12993 | NewBotAI_DoAloneStuff -> GetNearestVisibleWP (12570), trap->EntitiesInBox 2048x2048x512 (12612), JP_Trace box MASK_SOLID 48u/48u/48u/96u (12709,12719,12732,12755) or BotFallbackNavigation (12770) + box 48u x1-3 (12786,12796,12809) | NewBotAI | no | closestID == -1 | every think while no enemy |
| ai_main.c:13004 | OrgVisible(bs->eye, enemy ps.origin) - line, MASK_SOLID, unbounded (bot to closest enemy anywhere on map) | NewBotAI | no | skipped if weapon==WP_DEMP2 (forcedFireMode!=1) or g_newBotAITarget>=0; else every think with an enemy | Longest/most expensive single trace in NewBotAI; runs for every bot every think |
| ai_main.c:13016 | OrgVisible(bs->eye, attacker head) - line, MASK_SOLID, unbounded | NewBotAI | no | 13004 failed AND PassStandardEnemyChecks(PERS_ATTACKER) | second long trace on same frame |
| ai_main.c:13023 | NewBotAI_DoAloneStuff (see 12993) | NewBotAI | no | closest not visible, no valid attacker, lastVisibleEnemyIndex older than 10 s | |
| ai_main.c:13034 | NewBotAI_DoAloneStuff (see 12993) | NewBotAI | no | !frame_Enemy_Vis && frame_Enemy_Len > 300 | the normal "enemy exists but no LOS" path, every think |
| ai_main.c:13052-13060 | NewBotAI_LSvLS/DSvLS/LSvDS/DSvDS -> NewBotAI_GetAim (loop <=MAX_CLIENTS, 0 traces), NewBotAI_GetMovement (line traces MASK_PLAYERSOLID at 10904,10927,11051,11078,11180,11198 + Bot_CheckMovementPaths 3 lines), force powers (0-1 OrgVisible), NewBotAI_GetAttack -> Bot_ExecuteSaberCombat (9971 box + 10052/10069 lines) | NewBotAI | no | reached when enemy visible, or not visible but <=300u; gate at 13049 (force not fully disabled, or g_flipKick, or weapon != saber) | exact per-call count of GetMovement not determined here (other agent) |
| ai_main.c:13089 | BotShouldAttackNow -> BotShouldAttack -> BotCanHitEnemy: JP_Trace box MASK_PLAYERSOLID bot->enemy (8044), <=~150u | NewBotAI | no | frame_Enemy_Vis && saber range weapon && frame_Enemy_Len <= 128, and BotCanAttackNow timing | 0-1 trace |
| ai_main.c:13120 | MeleeCombatHandling: 3 box traces MASK_SOLID 4096u straight down (4642,4649,4664) | NewBotAI | no | frame_Enemy_Vis && melee-range weapon && frame_Enemy_Len <= 256 | every think in that state |
| ai_main.c:13144 | JP_Trace box(-15,-15,-8 / 15,15,32) MASK_PLAYERSOLID, 32u forward | NewBotAI | no | currentEnemy && frame_Enemy_Vis (13067), every think | 4 traces 13144-13159 always together, no timer |
| ai_main.c:13149 | JP_Trace same box, 32u backward | NewBotAI | no | same | |
| ai_main.c:13154 | JP_Trace same box, 32u left | NewBotAI | no | same | |
| ai_main.c:13159 | JP_Trace same box, 32u right | NewBotAI | no | same | |
| ai_main.c:13237 | NewBotAI_GetAttack (second call this frame) -> Bot_ExecuteSaberCombat (9971, 10052, 10069) | NewBotAI | no | timeToReact < level.time && enemySeenTime > level.time+8000 (always true, see notes) && frame_Enemy_Vis | duplicates the GetAttack done inside XvY |
| ai_main.c:13257 | OrgVisible(bs->eye, bs->lastEnemySpotted, -1) line | NewBotAI | no | `if (!bs->frame_Enemy_Vis)` nested inside `if (bs->frame_Enemy_Vis)` (13234/13254) | DEAD CODE - never executes |
| ai_main.c:13405 | while (i < MAX_GENTITIES) scan for vehicle | StandardBotAI | loop 1024 | #ifndef FINAL_BUILD && bot_getinthecarrr.integer && bot not in vehicle | debug only; 0 traces |
| ai_main.c:13808 | GetNearestVisibleWP(bs->origin, bs->client): loop gWPNum; per WP <800u: InPVS + OrgVisibleBox 1 box MASK_SOLID | StandardBotAI | callee loop gWPNum | !bs->wpCurrent - no timer; re-runs every think until a WP is found | gWPNum==0: loop body never runs, returns -1 every think, 0 traces |
| ai_main.c:13821 | ScanForEnemies: while (i <= MAX_CLIENTS) (2472); InPVS per valid enemy (2474); OrgVisible line MASK_SOLID bot eye -> enemy origin (2485), unbounded | StandardBotAI | callee loop 33 | condition at 13818-13819 is ALWAYS TRUE ((!currentEnemy) OR (currentEnemy)) -> every think, no timer | traces = number of candidates that are closer than running best AND (in 90deg FOV or heard). Worst 31, typical 0-3 |
| ai_main.c:13827 | NewBotAI_DoAloneStuff (see 12993) | StandardBotAI | no | only on frames where ScanForEnemies returns != -1 (new acquisition or switch to enemy 128u closer) | one-frame burst; also overwrites ideal_viewangles/EA_Move for that frame |
| ai_main.c:13833 | BotScanForLeader: while (i < MAX_CLIENTS) (6419) | StandardBotAI | callee loop 32 | !squadLeader && !isSquadLeader | 0 traces; stops once bot becomes leader (13836-13839) |
| ai_main.c:13560 | CommanderBotAI -> (GT_TEAM) CommanderBotTeamplayAI loop MAX_CLIENTS (4493); CTF/Siege variants | StandardBotAI | callee loop 32 | bs->isSquadLeader; only in GT_TEAM/CTF/CTY/SIEGE (no-op in FFA) | 0 traces in teamplay variant; CTF/Siege variants not determined |
| ai_main.c:13870 | WPOrgVisible(bot, origin, wpCurrent->origin): 1 line MASK_SOLID + 1 line MASK_PLAYERSOLID | StandardBotAI | no | bs->wpCurrent, every think | never runs when gWPNum==0 |
| ai_main.c:13913 | OrgVisible(bs->eye, eorg) line MASK_SOLID, bot eye -> enemy eye, unbounded | StandardBotAI | no | bs->currentEnemy, every think (for up to ENEMY_FORGET_MS 10 s after last sight) | duplicate of the trace ScanForEnemies may have just done on same enemy |
| ai_main.c:13950 | CheckForFunc(wpCurrent->origin, -1) line 64u down | StandardBotAI | no | wpCurrent && WPFLAG_WAITFORFUNC | |
| ai_main.c:13957 | CheckForFunc(wpCurrent->origin, -1) line 64u down | StandardBotAI | no | wpCurrent && WPFLAG_NOMOVEFUNC | |
| ai_main.c:14018 | GetIdealDestination(bs) (GetNearestBadThing loop level.num_entities, GetNearestVisibleWP, GetBestIdleGoal) | StandardBotAI | callee loops | wpCurrent && destinationGrabTime < level.time; combat clamps destinationGrabTime to level.time+100 (14197-14200) | never runs when gWPNum==0 |
| ai_main.c:14085 | BotFallbackNavigation(bs): 0 if enemy visible; else box 32u fwd (5403) + line 300u down (5413); +4 (5424-5447) on wall/ledge; up to 12 x IsPositionReachable; SmartExploration | StandardBotAI | no | !bs->wpCurrent && bs->cur_ps.weapon == WP_SABER, every think, no timer at call site | THE main nav cost when gWPNum==0 (saber bots only) |
| ai_main.c:14111 | BotFallbackNavigation(bs) (second possible call same frame) | StandardBotAI | no | iHaveNoIdeaWhereIAmGoing > level.time && !currentEnemy; that timer is only set under RMG.integer (14102) | never fires on non-RMG maps |
| ai_main.c:14186 | NewBotAI_GetAttack -> Bot_ExecuteSaberCombat (9971 box, 10052/10069 lines) | StandardBotAI | no | timeToReact < level.time && enemySeenTime > level.time+8000 && frame_Enemy_Vis | second GetAttack per frame (first inside XvY at 13602-13610) |
| ai_main.c:14215 | OrgVisible(bs->eye, bs->lastEnemySpotted, -1) line MASK_SOLID | StandardBotAI | no | same gate as 14186 but !frame_Enemy_Vis (enemy seen within last 2 s, now hidden) | |
| ai_main.c:13600-13610 | NewBotAI_LSvLS/DSvLS/LSvDS/DSvDS (see 13052) | StandardBotAI | no | currentEnemy && client && frame_Enemy_Vis (previous frame's value) && forceJumpChargeTime < level.time && gate 13598 | |
| ai_main.c:14288 | BotShouldAttackNow -> BotCanHitEnemy 1 box trace (8044) | StandardBotAI | no | currentEnemy && saber-range weapon && frame_Enemy_Len <= 128 | 0-1 |
| ai_main.c:14327 | MeleeCombatHandling 3 box traces 4096u down | StandardBotAI | no | currentEnemy && melee-range weapon && frame_Enemy_Len <= 256 (no visibility requirement here) | |
| ai_main.c:14361 | CTFFlagMovement(bs) 0-1 trace | StandardBotAI | no | every think (unless early chat return 14335) | |
| ai_main.c:14378 | EntityVisibleBox(bs->origin, NULL, NULL, dif) line MASK_SOLID to shootGoal centre | StandardBotAI | no | bs->shootGoal alive && (!enemy or enemy >256u) && within 30deg FOV | siege/objective |
| ai_main.c:14387 | BotCheckDetPacks: G_Find loop + up to 1 OrgVisible (6597) | StandardBotAI | callee loop entities | bs->cur_ps.hasDetPackPlanted | |
| ai_main.c:14414 | BotSurfaceNear 1 line trace (6668) | StandardBotAI | no | enemy lost sight, plantTime elapsed, has mine/detpack, near last-seen spot | |
| ai_main.c:14457 | OrgVisible(bs->origin, gJMSaberEnt origin) line, <256u | StandardBotAI | no | GT_JEDIMASTER only, saber ent within 256u | |
| ai_main.c:14464 | WaitingForNow -> CheckForFunc 0-1 line 64u down (2546/2552) | StandardBotAI | no | bs->beStill < level.time; returns 0 immediately if !wpCurrent | 0 when gWPNum==0 |
| ai_main.c:14476 | JP_Trace box(-15,-15,-8 / 15,15,32) MASK_PLAYERSOLID 32u along VIEW forward | StandardBotAI | no | beStill < level.time && !WaitingForNow && !fjHalt (fjHalt is always 0) -> essentially every think; hit <16u sets beStill +300 ms | identical trace to BotFallbackNavigation 5403 and (NewBotAI) 13144 on the same frame |
| ai_main.c:14646 | BotTrace_Jump(bs, goalPosition) nominal 2-6 box, effectively 0 | StandardBotAI | no | same block as 14476, not reached if wall <16u (goto 14529) or attackRecoveryTime (14616) | |
| ai_main.c:14650 | BotTrace_Duck(bs, goalPosition) 2 box, up to ~14 | StandardBotAI | no | BotTrace_Jump returned 0 -> effectively every moving think | 2 traces/frame minimum |
| ai_main.c:14665 | BotTrace_Strafe(bs, goalPosition) 1-3 box | StandardBotAI | no | Jump==0 && Duck==0; inside: on ground and facing goal within 60deg | |
| ai_main.c:14765 | EntityVisibleBox(bs->origin, NULL, NULL, dangerousObject origin) line MASK_SOLID | StandardBotAI | no | dangerousObject valid, no visible enemy, mid/long range weapon, >256u, within 30deg | |
| ai_main.c:14775 | CheckForFriendInLOF 1 box MASK_PLAYERSOLID 2048u (6386) | StandardBotAI | no | PrimFiring(bs) or AltFiring(bs) | |
| ai_main.c:14811 | CheckForFriendInLOF 1 box MASK_PLAYERSOLID 2048u | StandardBotAI | no | NOT firing && level.gametype >= GT_TEAM -> every think in team games | constant 1 long box trace per bot per frame in TFFA/CTF/Siege |
| ai_main.c:14926 | for (i = 0; i < MAX_CLIENTS; i++) validation loop | BotAIStartFrame | loop 32 | every call | body is only `continue` statements - does nothing; 14928 bounds check is redundant |
| ai_main.c:14973 | UpdateEventTracker: while (i < MAX_CLIENTS) (2338) | BotAIStartFrame | callee loop 32 | every call | reads level.clients[i] for all 32 slots |
| ai_main.c:14990 | for (i = 0; i < MAX_CLIENTS; i++) -> BotAI(i, thinktime) | BotAIStartFrame | loop 32 | botthink_residual >= thinktime (always true with BOT_THINK_TIME 0) && CON_CONNECTED | the per-bot think dispatch |
| ai_main.c:15007 | for (i = 0; i < MAX_CLIENTS; i++) -> BotUpdateInput + trap->BotUserCommand | BotAIStartFrame | loop 32 | CON_CONNECTED | every call, independent of thinking |
| ai_main.c:15082 | for (i = 0; i < MAX_CLIENTS; i++) -> BotAIShutdownClient | BotAIShutdown | loop 32 | restart only | |

### 4b. Estimated worst-case traces per bot per frame

All numbers are ESTIMATES built from the callee costs supplied plus the sites read in this region. k = ScanForEnemies line traces (0..31; typically 0-3). GetMovement's "<=9" is an upper bound from counting trace sites (10904, 10927, 11051, 11078, 11180, 11198 + Bot_CheckMovementPaths 3), not a measured figure.

| AI | Path | Contributing call sites | Typical (est.) | Worst (est.) |
|---|---|---|---|---|
| Standard | Idle roaming with waypoints | 13821 scan k; 13870 WPOrgVisible 1-2; 13950/13957 0-2; 14018 GetIdealDestination (periodic; GetNearestBadThing + GetNearestVisibleWP); 14361 0-1; 14464 0-1; 14476 1; 14650 2-14; 14665 1-3; 14811 1 (team) | 6-9 + k | ~25 + k + GetIdealDestination |
| Standard | Idle, no waypoints, saber | 13821 k; 14085 fallback 2 / 6 / ~80+; 14476 1; 14650 2-14; 14665 1-3; 14811 0-1 | 6-9 + k | ~100+ + k |
| Standard | Idle, no waypoints, gun | 13821 k; 14476 1; 14650 2-14; 14665 1-3 | 4-6 + k | ~18 + k |
| Standard | Has enemy, gun, visible | 13821 k (>=1); 13913 1; 13600-13610 XvY GetMovement <=9 + force 0-1; 14476 1; 14650 2-14; 14665 1-3; 14775 1 | 8-15 | ~30 + k |
| Standard | Saber combat, visible, close | 13821 k (>=1); 13913 1; XvY GetMovement <=9 + SaberCombat 1-3; 14186 SaberCombat 1-3; 14288 0-1; 14476 1; 14650 2-14; 14665 1-3 | 10-20 | ~35 + k |
| NewBotAI | Idle with waypoints (DoAloneStuff) | 12709-12755 2-4 box | 2-4 | 4 (+2 if an enemy exists: 13004, 13016) |
| NewBotAI | Idle, no waypoints | 12612 EntitiesInBox; 12709-12755 2-4 or 12770 fallback 2..~80+ and 12786-12809 1-3; +13004/13016 1-2 if any enemy exists | 3-8 | ~90+ |
| NewBotAI | Enemy visible, gun (only if bot has no saber: 12517 / 5873 force saber) | 13004 1; XvY GetMovement <=9 + force 0-1; 13120 Melee 3 (melee weapon); 13144-13159 4 | 7-12 | ~18 |
| NewBotAI | Saber combat | 13004 1; XvY GetMovement <=9 + SaberCombat 1-3; 13089 0-1; 13144-13159 4; 13237 SaberCombat 1-3 | 9-15 | ~22 |

Multiply by bots x BotAIStartFrame rate (every SV_Frame; see section 1). Example: 25 bots x 40 Hz x ~8 traces = ~8000 traces/s in the idle no-waypoint case before spikes.


## 5-7. Perception, navigation and combat

### Inline logic in StandardBotAI and NewBotAI (lines 12940-15093)


#### Enemy selection and stickiness - StandardBotAI
- Acquisition: ScanForEnemies every think (13818-13829). Candidate must be a non-team client passing PassStandardEnemyChecks (2063), in PVS, PassLovedOneCheck, closer than best, (in 90deg FOV and not mind-tricking) or BotCanHear, and OrgVisible. With a current enemy, a new one must be at least 128u closer than frame_Enemy_Len (2469, 2491, 2503).
- Also acquired outside this region by BotDamageNotification (2243-2259) when the bot has no enemy.
- Stickiness: enemySeenTime = level.time + ENEMY_FORGET_MS (10000) on acquisition (13826) and on every think where the enemy is visible (13935). Enemy is dropped at 13718-13742 when enemySeenTime expires or PassStandardEnemyChecks fails (dead, spectator, teammate, duel, etc.), and at 13579-13583 on disconnect.
- Per-frame facts set at 13898-13930: frame_Enemy_Len, frame_Enemy_Vis, lastEnemySpotted, hereWhenSpotted, lastVisibleEnemyIndex (entity number).
- revengeEnemy only validated for connection state (13572-13577) and cleared with "KilledHatedOne" chat (13721-13731).
- Reaction: timeToReact = level.time + clamp(reflex / skill, 0, 2000) refreshed every think while there is no enemy (13674-13688), so the bot may fire only `reaction` ms after acquiring.

#### Aiming / firing - StandardBotAI
- Fire gate 14182: `timeToReact < level.time && currentEnemy && enemySeenTime > level.time + 8000` -> enemy must have been visible within the last 2 s.
- Visible: NewBotAI_GetAttack (weapon pick via NewBotAI_GetWeapon/GetTribesWeapon + BotSelectWeapon; saber -> Bot_ExecuteSaberCombat; guns -> EA_Attack/EA_Alt_Attack directly with charge logic, 10513-10584). Aim = BotPredictEnemyPosition (8070, skill-based lead) -> goalAngles, then BotAimOffsetGoalAngles (4985). Applied at 14903 via MoveTowardIdealAngles; BotChangeViewAngles (494) then turns at skill-dependent speed each BotUpdateInput.
- Not visible: aims at lastEnemySpotted if OrgVisible (14215); keeps charged weapons charging (14188-14195).
- Because the XvY routine (13600-13610) calls NewBotAI_GetAim, which may write ideal_viewangles directly, and 14903 then overwrites ideal_viewangles with goalAngles, which of the two aim systems wins in Standard mode is: goalAngles (verified for the overwrite; what GetAim writes was not read here).
- Final fire decision is the doAttack/doAltAttack flags (14830-14876) IN ADDITION to any EA_Attack already issued inside NewBotAI_GetAttack / saber combat; vetoes at 14830-14867 only affect the flags, not EA calls already made.
- Friendly-fire guard: CheckForFriendInLOF (14775) cancels via KeepPrimFromFiring/KeepAltFromFiring.
- Force powers: `useTheForce` path (14883-14901) only for force jump and team heal/energize; offensive powers are issued inside the NewBotAI_XvY routines.

#### Enemy selection - NewBotAI
- Re-selected from scratch every think by NewBotAI_ScanForEnemies (health-weighted nearest, no LOS, no stickiness: hasEnemyDist is always 0 at 12862/12871), then overridden by PERS_ATTACKER when the nearest is not visible (13010-13019).
- lastVisibleEnemyIndex is used as a timestamp (13007, 13018, 13022) - conflicts with its entity-number use in StandardBotAI and DoAloneStuff.
- enemySeenTime is set unconditionally (13029), so the 2-second "recently seen" gate at 13232 is meaningless; timeToReact is not maintained, so there is no reaction delay.
- Aim: NewBotAI_GetAim inside XvY; the goalAngles prediction at 13284-13297 is not applied by NewBotAI itself.
- Attack: NewBotAI_GetAttack is executed twice per think when the enemy is visible (inside XvY and at 13237).

### 6. Navigation: Behaviour when gWPNum == 0

Facts: GetNearestVisibleWP returns -1 with 0 traces, bs->wpCurrent stays NULL forever, GetIdealDestination / WPConstantRoutine / WPOrgVisible / WaitingForNow never do work. `iHaveNoIdeaWhereIAmGoing` is only set under RMG.integer (14102).

### StandardBotAI
Every think, in order:
1. 13808 GetNearestVisibleWP: 0 traces (called every think, no back-off).
2. 13821 ScanForEnemies: 33-slot loop, InPVS per valid enemy, 1 unbounded line trace per candidate that is closer than the running best and in the 90deg FOV or audible. No timer.
3. 13847, 13938 waypoint blocks skipped.
4. 14083 `weapon == WP_SABER` -> BotFallbackNavigation; otherwise nothing sets goalPosition.
5. 14361 CTFFlagMovement 0-1.
6. 14464 movement block (WaitingForNow returns 0 at 2524): wall box trace (14476) + EA_Move toward goalPosition + BotTrace_Jump (0) + BotTrace_Duck (2..14) + BotTrace_Strafe (1-3).
7. 14811 team gametypes: CheckForFriendInLOF 1 box 2048u.

| State | What runs | Traces per think |
|---|---|---|
| Idle, no enemy, saber | ScanForEnemies k + BotFallbackNavigation (2; +4 on wall/ledge when its timer allows; up to 12 x IsPositionReachable ~80+ when it needs a new exploration target; SmartExploration more) + wall 1 + Duck 2 + Strafe 1-3 (+1 LOF in team games, +0-1 CTF) | typical ~6-9 + k (estimate); spike frames ~90-100+ (estimate) |
| Idle, no enemy, gun (non-saber) | ScanForEnemies k + wall 1 + Duck 2 + Strafe 1-3. No fallback navigation at all: goalPosition is whatever it last was (zero-initialised bot_state -> world origin), bot walks toward it via EA_Move 14605 | ~4-6 + k (estimate) |
| Enemy known, not visible (up to 10 s, ENEMY_FORGET_MS) | ScanForEnemies k + OrgVisible 13913 (1) + OrgVisible 14215 (1, only during the first 2 s) + BotFallbackNavigation as idle (saber; it only bails when the enemy is visible, 5350) + movement block 4-6; MeleeCombatHandling 3 if melee weapon and <=256u | ~8-12 + k typical (estimate); same spikes as idle |
| Enemy visible | ScanForEnemies k (the current enemy itself is normally traced again) + 13913 (1) + XvY (GetMovement est. <=9, force 0-1, SaberCombat 1-3) + GetAttack 14186 (SaberCombat 1-3) + BotShouldAttackNow 0-1 + BotFallbackNavigation 0 + wall 1 + Duck 2-14 + Strafe 1-3 + LOF 1 when firing | ~10-20 typical, ~60 worst (estimates) |

One-frame burst: on the think where ScanForEnemies returns a new enemy, NewBotAI_DoAloneStuff also runs (13827): EntitiesInBox + 2-4 box traces, or BotFallbackNavigation + 1-3.
Timers that limit it: none at the call sites. Only beStill (wall hit: +300 ms at 14528; skips the whole movement block including Duck/Strafe traces) and BotFallbackNavigation's internal timers.

### NewBotAI
Every think:
1. 12967 NewBotAI_ScanForEnemies: 0 traces, 32 InPVS at most. With PVS culling nothing and no range limit, closestID != -1 whenever any valid enemy exists on the map.
2. 13004 OrgVisible to that enemy: 1 line trace across whatever distance separates them (plus 13016 if blocked and PERS_ATTACKER is valid).
3. Not visible and > 300u (the common case on a huge map) -> NewBotAI_DoAloneStuff (12485):
    - 12512-12515 frame_Enemy_Vis forced 0; 12517 switch to saber if available.
    - 12568-12576 GetNearestVisibleWP: 0 traces, wpCurrent stays NULL -> destination = false.
    - 12608-12671 `trap->EntitiesInBox` over a 2048 x 2048 x 512 box (up to 256 ents) EVERY think, looking for a wanted item.
    - 12676-12691 "enemy tracking" branch: effectively dead (compares lastVisibleEnemyIndex to an entity number AND to level.time, see F_bugs).
    - item found: 12709 box 48u (+12719, +12732 if blocked) + 12755 pit check box -> 2-4 box traces; then turn/move toward item (12840-12853).
    - no item: 12769 saber -> BotFallbackNavigation (2 .. ~80+); if it returns nonzero -> return; if 0 (or non-saber): 12786 box 48u (+12796, +12809) -> 1-3 box traces, EA_MoveForward, random yaw wander (12825-12832).

| State | Traces per think |
|---|---|
| No valid enemy anywhere (closestID -1) | EntitiesInBox + (item: 2-4) or (BotFallbackNavigation 2..~80+, then 1-3 if it returned 0). Typical ~3-6 (estimate) |
| Enemy exists, no LOS, > 300u | 1-2 long line traces + the row above. Typical ~4-8 (estimate), spikes ~90+ |
| Enemy visible (or hidden but <= 300u) | 1 (13004) [+1 13016] + XvY (GetMovement est. <=9, force 0-1, SaberCombat 1-3) + BotShouldAttackNow 0-1 or Melee 3 + 4 box (13144-13159, visible only) + GetAttack again (1-3). Typical ~9-15, worst ~22 (estimates) |

Timers: none in NewBotAI itself; the 10 s lastVisibleEnemyIndex window (13022) only chooses between falling through and DoAloneStuff.


### Region notes, lines 1-2700

#### (a) Lifecycle functions (ai_main.c 1-2700, plus the driver at 14913 for context)

| Function | Lines | What it does |
|---|---|---|
| BotAISetupClient | 889-1005 | Bounds check (892); refuse if `botstates[client] && inuse` (898); entity check (904); **always** `B_Alloc(sizeof(bot_state_t))` (910) and memset (915); copy settings (919); default weapon weights (924-938); `BotUtilizePersonality` (940, ai_util.c, file parse); duel saber weight (942-945); botlib goal/weapon/move states (948-957); `inuse=1`, `setupcount=4`, `numbots++` (953-958); `BotScheduleBotThink` (961); `Bot_InitPerfectBlocking` (964); redundant zeroing of already-memset fields (967-997); greeting chat if `PlayersInGame()` (999). `restart` param unused. Called from g_bot.c:855. |
| BotAIShutdownClient | 1012-1045 | Bounds check; the `bs`/`inuse` check is duplicated verbatim (1019-1023 and 1025-1029); frees botlib move/goal/weapon states (1031-1035); memset bs (1038); `numbots--`. Does NOT `B_Free` nor NULL `botstates[client]`. Called from g_client.c:5191 and BotAIShutdown 15084. |
| BotResetState | 1055-1090 | Saves settings, cur_ps, inuse, client, entitynum, ms/gs/ws, entergame_time; memset whole struct; restores those; resets botlib states. Everything else (skills, botWeaponWeights, loved[], forceinfo, canChat/chatFrequency, blocking, all timers) is wiped and NOT re-initialised. Only caller: BotAILoadMap. |
| BotAILoadMap | 1097-1108 | For each in-use bot: BotResetState + setupcount=4. Called from g_main.c:463. |
| BotAI | 740-841 | Bounds/inuse/entity checks (744-759); `trap->EA_ResetInput` (768); duplicate bs check (770-774); `BotAI_GetClientState` memcpy of playerState (777); drains `trap->BotGetServerCommand` (780-801; all command branches empty, so the loop + RemoveColorEscapeSequences only discards); adds delta angles (803-805); sets ltime/thinktime/origin/eye (807-814); calls `NewBotAI` if `g_newBotAI.integer` else `StandardBotAI` (820-823; g_newBotAI default "0", g_xcvar.h:349); `_DEBUG` timing (817-833); subtracts delta angles (836-838). |
| BotScheduleBotThink | 848-861 | Sets `botthink_residual = BOT_THINK_TIME * botnum / numbots` = 0 for all (BOT_THINK_TIME is 0, line 60). No staggering exists. |
| BotUpdateInput | 677-699 | Per bot per server frame (15015): add delta angles, `BotChangeViewAngles(bs, elapsed/1000)`, `trap->EA_GetInput`, respawn hack, `BotInputToUserCommand(..., bs->noUseTime)`, subtract delta angles. |
| BotInputToUserCommand | 561-670 | Action flags -> buttons (577-587); random `BUTTON_USE` with 40% chance per frame when `useTime(=bs->noUseTime) < level.time` (589-592); WP_NONE -> bryar (606-612); angles minus delta (618-625); movement from `bi->dir` projected on forward/right, `u` forced to 0 (639, Niksata edit) so vertical move only comes from ACTION_JUMP/ACTION_CROUCH (665-669). |
| BotChangeViewAngles | 494-554 | factor = turnspeed, or turnspeed_combat*skill*(0.4/0.6/0.8/1.0) when enemy visible (500-522), clamped [0.001,1]; maxchange = skills.maxturn, **overridden to 1800 if g_newBotAI** (531-533), times thinktime; per-axis (pitch,yaw) critically-undamped speed update (537-551); `trap->EA_View` (553). |
| BotAIStartFrame (driver, outside region) | 14913-15020 | Per server frame: "timeout" early return (14918-14924); no-op validation loop (14926-14944); cvar updates 1/s (14951); `UpdateEventTracker` (14973); for each bot: `BotAI(i, thinktime)` every frame (14990-15004); then `BotUpdateInput` + `trap->BotUserCommand` (15007-15017). |

Per-frame order for one bot: UpdateEventTracker (once) -> BotAI -> StandardBotAI/NewBotAI -> BotUpdateInput -> BotChangeViewAngles -> BotInputToUserCommand -> trap->BotUserCommand.

#### (b) Perception

**PassStandardEnemyChecks (2063-2177)** - returns 0 for: null (2065), non-client (2070), raceMode (2075), PM_NOCLIP (2078), `g_newBotAITarget < -1` and target is a bot (2081), dead (2084), !takedamage (2089), doingFallback with LEVELFLAG_IGNOREINFALLBACK (2094), intermission/spectator (2102), not connected (2109), !s.solid (2114), self (2119), teammate (2124), mind-tricked by current enemy and > 64u away (2129-2145), duel exclusivity both ways (2147-2155), Jedi Master rules: FF off or > 350u (2157-2174). No traces. Uses 2 VectorLength at most.

**ScanForEnemies (2453-2518)**

| Aspect | Value / line |
|---|---|
| Loop bound | `while (i <= MAX_CLIENTS)` (2472): 33 iterations, index 32 is the first non-client entity |
| Candidate filter order (2474) | i != self, `.client`, !OnSameTeam (redundant with 2124), PassStandardEnemyChecks, BotPVSCheck(enemy origin, bs->eye) -> trap->InPVS, PassLovedOneCheck |
| Distance | 3D `VectorLength(enemy ps.origin - bs->eye)`; no max range; must be `< closest` (starts 999999) |
| FOV | `InFieldOfVision(bs->viewangles, 90, a)` = +-45 deg on BOTH pitch and yaw, and not mind-tricked (2485) |
| Hearing | else `BotCanHear(bs, ent, distcheck)` |
| LOS | `OrgVisible(bs->eye, enemy ps.origin, -1)`: 1 line trace MASK_SOLID to enemy origin (not head), evaluated last in the && chain (2485) |
| Mind-trick | if tricked: accept only if dist < 256 or `level.time - dangerTime < 100` (2489) |
| Stickiness | `hasEnemyDist = bs->frame_Enemy_Len` if currentEnemy (2467-2470); new target accepted only if `!hasEnemyDist || distcheck < hasEnemyDist - 128` (2491, 2503). Applied AFTER the trace. The current enemy itself never passes (dist is not 128 closer than itself) so with an enemy the function returns -1 unless someone is 128u+ closer |
| `noAttackNonJM` | always qfalse (2461), dead variable |
| Caller | StandardBotAI 13821; gate 13818-13819 contains `|| (bs->currentEnemy ...)` alongside `|| !bs->currentEnemy` => always true => every frame per bot |
| Cost | up to 31 InPVS + up to 31 line traces per bot per frame (25 bots FFA: ~600 InPVS + up to ~600 traces/frame worst case; typical = enemies inside the 90 deg cone and PVS) |

**BotCanHear (2264-2329)** - no traces. Radius: `ps.otherSoundLen` if `otherSoundTime > level.time` (2273); 256 if `footstepTime > level.time` (2279); else last tracked event if `gBotEventTracker[n].eventTime >= level.time` (2285): EV_GLOBAL_SOUND 256, EV_FIRE_WEAPON/ALT_FIRE/SABER_ATTACK 512, steps/footsteps 256, jump/roll 256, default 999999 (2290-2316; note the default means "any other event is heard at any range"). Mind-tricked: radius /4 (2318-2321). Heard if `endist <= minlen`.

**UpdateEventTracker (2332-2350)** - once per server frame, loop MAX_CLIENTS, copies `ps.eventSequence`, `events[0..1]`, sets `eventTime = level.time + 0.5` (float, 0.5 ms). Since BotAI runs in the same frame, event hearing is valid for exactly the frame the event was seen. Reads `level.clients[i]` for unconnected slots too (harmless).

**BotDamageNotification (2180-2260)** - event (g_combat.c:5903/5907). Ignores NPC victim/attacker (2191-2199). If attacker is a bot: set its `lastAttacked`, clear same `lastAttacked` on all other bots (loop MAX_CLIENTS 2208); else clear on all bots (2224). Sets victim `bs->lastHurt` (2243). If no currentEnemy and attacker passes PassStandardEnemyChecks and PassLovedOneCheck: currentEnemy = attacker, enemySeenTime = level.time + 10000 (2250-2259).

#### (c) Waypoint helpers

| Function | Lines | Behaviour | Cost |
|---|---|---|---|
| GetNearestVisibleWP | 1235-1280 | bestdist 800 (300 RMG); box (-15,-15,-1)..(15,15,1); for each in-use WP: VectorLength, and if nearer than best: BotPVSCheck (skipped in RMG) then OrgVisibleBox. **gWPNum==0: loop body never runs, returns -1, zero traces/InPVS.** Callers then leave wpCurrent NULL and (13806) call it again every frame - free with 0 WPs, but on a map WITH waypoints a bot with no visible WP within 800u re-runs the full O(gWPNum) scan + traces every frame with no timer. | O(gWPNum) sqrt; traces = number of successively-nearer PVS-visible candidates |
| PassWayCheck | 1288-1321 | 0 if WP missing/not in use; RMG flag WPs always pass; one-way flags vs bs->wpDirection (1304-1311); needs force-jump level if WP is > 64u above wpCurrent and has forceJumpTo (1313-1318). No bounds check on windex. | O(1) |
| TotalTrailDistance | 1324-1390 | Walks indices from min(start,end) to max, summing `disttonext`; -1 on invalid WP (1345) or wrong-direction one-way flag when !RMG (1350-1357). `bs` unused (force-jump code is `#if 0`). Assumes one linear trail (index order). | O(abs(end-start)), no traces; called every frame at 14023 |
| CheckForShorterRoutes | 1394-1480 | Sets wpDirection from index compare (1411-1418); gated by `bs->wpSwitchTime > level.time` (1421) and neighbornum (1427); compares own trail distance with each neighbor's (1436-1459), needs 64u gain and sufficient FP_LEVITATION; on switch: wpCurrent = neighbor, wpSwitchTime = +3000 (1463-1464), force-jump charge setup (1466-1478). | (1+neighbors) x O(gWPNum) |
| WPConstantRoutine | 1484-1554 | Every frame with wpCurrent: DUCK flag -> duckTime +100 (1491); JUMP flag: if heightDif > 40 and has levitation and not fully charged/airborne -> forceJumpChargeTime +1000, jumpPrep, beStill +300, wpSeenTime >= +600 (1506-1520); if heightDif > 64 and no levitation -> drop wpCurrent and reverse direction (1521-1535); forceJumpTo -> keep charging (1539-1553). | O(1), no traces |
| WPTouchRoutine | 1576-1663 | wpTravelTime = +10000 (1585); NOMOVEFUNC -> noUseTime +4000 (1587); JUMP flag without forceJumpTo -> jumpTime +100 (1599); camping setup if isCamper && bot_camp && (chicken/guard/isCamper==2) && snipe flag && ranged weapon (1606-1634), isCamping = 30-45 s; cancel camping with melee (1635-1641); destination reached -> wpDestination NULL, destinationGrabTime +500 (fleeing) / +3500 (1643-1657); else CheckForShorterRoutes (1660). | O(1) + CheckForShorterRoutes |

#### (d) BotTrace_Strafe / Jump / Duck - exact trace counts

All traces are JP_Trace, MASK_PLAYERSOLID, passEntity = bs->client. Call order in StandardBotAI 14646-14676: Jump, else Duck, else Strafe.

| Function | Best case | Typical | Worst case | Trace lines |
|---|---|---|---|---|
| BotTrace_Strafe (1680) | 0 (airborne 1689, or yaw off by > 60 deg 1698) | 1 box (path clear, 1717) | 3 box (1717 hit, 1734 hit, 1749) | 1717, 1734, 1749 |
| BotTrace_Jump (1762) AS WRITTEN | 0 | 0 | 0 - always returns 0 at 1790 (or 1772) | 1795-1855 unreachable |
| BotTrace_Jump if `dist` bug were fixed | 2 box (1795 + 1824; or 1795+1805 and return 1) | 2 | 6 box (1795, 1805, 1824, 1834, 1845, 1855) | - |
| BotTrace_Duck (1868) | 1 box (1889 blocked) | 2 box (1889 clear, 1908 clear -> return 0) | 14 = 2 box + 4 line (1949 x4) + 4 box (1991 x4) + 1 box (2010) + 1 line 256u (2026) + 2 box (2042, 2048) | see A_traces |
| BotTrace_Duck early exits when head box blocked | - | 6 (nearLedge >= 2 at 1959) | 11 (2013), 12 (2030, or 11 without wall trace) | - |

Per-bot per-frame total of the trio as the code stands: typical 2 (Duck) + 1 (Strafe) = 3 box traces; worst 14 + 0 (Strafe only runs if Duck returns 0: worst Duck-returns-0 path is 14, then Strafe up to 3 => 17).

Other per-frame trace sources from this region in StandardBotAI: WPOrgVisible 2 line traces (13870), ScanForEnemies 0-31 line traces + InPVS (13821), CheckForFunc 0-3 (13950, 13957, 14464).

#### (e) bot_state_t (ai_main.h:179-458)

"Throttle" = a time value compared against level.time that rate-limits work. "No ref" = no `bs->field` match in codemp/game/*.c (other access spellings such as `botstates[i]->field` were only spot-checked).

| Group | Fields | Notes |
|---|---|---|
| Core / botlib | inuse, botthink_residual, client, entitynum, cur_ps, lastucmd, settings, thinktime, origin, eye, ms, gs, ws, viewangles, ideal_viewangles, viewanglespeed | botthink_residual is the only think-rate throttle and is neutralised by BOT_THINK_TIME 0. `thinktime`, `ltime`, `setupcount`, `entergame_time` are write-only (807, 809, 955/1103, 956). `velocity`: no ref |
| Entities | currentEnemy, revengeEnemy, squadLeader, lastHurt, lastAttacked, wantFlag, touchGoal, shootGoal, dangerousObject, chatObject, chatAltObject | raw gentity_t pointers, never validated on client disconnect in this region |
| Waypoint nav | wpCurrent, wpDestination, wpStoreDest, wpCamping, wpCampingTo, wpDirection, goalAngles, goalMovedir, goalPosition, staticFlagSpot, frame_Waypoint_Len, frame_Waypoint_Vis, lastSignificantAreaChange, lastKnownWaypointPos, wpSpecial (no ref) | |
| Nav THROTTLE timers (float) | destinationGrabTime (gates GetIdealDestination 14016), wpSeenTime, wpTravelTime, wpDestSwitchTime, wpSwitchTime (gates CheckForShorterRoutes 1421), wpDestIgnoreTime, chickenWussCalculationTime (gates BotIsAChickenWuss 2636), escapeDirTime (gates GetNearestBadThing 3968), dontGoBack, randomNavTime (int), lastSignificantChangeTime, iHaveNoIdeaWhereIAmGoing | floats holding level.time ms |
| Enemy perception | lastEnemySpotted, hereWhenSpotted, lastVisibleEnemyIndex (holds a TIME, see 13007), hitSpotted, enemySeenTime (THROTTLE-like forget timer), timeToReact, frame_Enemy_Len, frame_Enemy_Vis, lastEnemyPos, lastEnemyTime, lastEnemyVelocity, enemyMovementHistoryTime, lastEnemyDistance (init only, 997), numEnemies (no ref) | There is NO timer throttling ScanForEnemies, WPOrgVisible or the BotTrace_* calls |
| Movement timers | beStill (gates movement block 14464), duckTime, jumpTime, jumpHoldTime, jumpPrep, forceJumping, jDelay, forceJumpChargeTime (#ifndef FORCEJUMP_INSTANTMETHOD), noUseTime (gates random USE, 589), meleeStrafeTime, meleeStrafeDir, meleeStrafeDisable, strafeDir, strafeExpireTime, combatStrafeTime, combatStrafeDir, noJumpTime, lastObstacleTime, noRetreatTime, avoidanceDirection, avoidanceTimer | No ref: forwardDir, forwardDirExpire, strafeDirExpire, evadeSideCooldown, stuckTurnTime, useTime, obstacleMemory[8], obstacleMemoryIndex, stuckCounter, lastValidPosition, lastPositionTime, forceJumpTime, nextAllowedJumpTime, jumpReleaseTime |
| Forced movement | forceMove_Forward, forceMove_Right, forceMove_Up | |
| Aim | aimOffsetTime (throttle), aimOffsetAmtYaw, aimOffsetAmtPitch, uiDodgeBias / uiAimJitter / uiLastEnemyDir (all no ref) | |
| Camping | isCamper, isCamping (float timer), campStanding, randomNav | |
| Chat | canChat, chatFrequency, currentChat[128], chatTime, chatTime_stored, doChat, chatTeam | |
| Weapons / attack | ChargeTime, altChargeTime, doAttack, doAltAttack, forceWeaponSelect, virtualWeapon, plantTime, plantDecided, plantContinue, plantKillEmAll, botWeaponWeights[], doForcePush, nextAttackTime, attackRecoveryTime, lastAttackTime, lastAttackType, comboWindow, lastAttackHitTime, isAttacking, delayAttackTime | lastComboTime, nextSpecialMoveTime, lastSpecialMoveTime: init-only (986, 988, 989) |
| Saber | saberSpecialist, saberDefending, saberDefendDecideTime, saberBFTime, saberThrowTime, saberPower (qboolean but assigned at 9240/9261/9305-9307/9334, values not inspected), botChallengingTime, feintTime, isFeinting, swingMemoryLeft/Right/Back (int), recentSwingMemoryLeft/Right/Back (float), lastSwingUpdateTime, blocking (botBlocking_t), lastDanceTime (write at 9379 only), styleSwitchTime, lastStyleSwitchTime, lastKataTime, kataStreak, currentSpecial, lastSpecialTime, specialDuration | No ref: saberBTime, saberSTime, saberPowerTime |
| Personality / social | skills (botskills_t), loved[4], lovednum, loved_death_thresh, revengeHateLevel, deathActivitiesDone, forceinfo[2048], runningLikeASissy, runningToEscapeThreat, lastDeadTime | forceinfo is 2 KB per bot |
| Team state | isSquadLeader, squadRegroupInterval, squadCannotLead, ctfState, siegeState, teamplayState, jmState, state_Forced | |
| Fallback | doingFallback | |

Type / struct oddities:

- ai_main.h:390-395: **anonymous struct** inside bot_state_t injecting `weapon`, `saberMove`, `torsoTimer`, `groundEntityNum` directly into the bs namespace (C11 / MSVC extension). None has a `bs->` reference; `bs->weapon` and `bs->groundEntityNum` are easy to confuse with `bs->cur_ps.weapon` / `bs->cur_ps.groundEntityNum`.
- ai_main.h:164-176: `botBlocking_t` is a tagless typedef struct (fine, but cannot be forward-declared).
- swingMemoryLeft/Right/Back are `int` (377-379) while recentSwingMemory* are `float` (415-417); both sets are updated with the same float math in ai_util.c:918-957.
- Float fields used as millisecond timers against integer `level.time` (242-261, 273, 286, 293-302): float has 24-bit mantissa, so above level.time = 16,777,216 ms (~4.66 h uptime on one map) `level.time + 100` style offsets start losing 1-2 ms precision; int timers elsewhere in the same struct.
- `lastVisibleEnemyIndex` (237) is used as a timestamp (13007, 13018, 13022).
- `boteventtracker_t.eventTime` is float and set to `level.time + 0.5` (2345).
- `forceJumpChargeTime` exists only `#ifndef FORCEJUMP_INSTANTMETHOD` (357-359), changing struct layout by a define.
- Duplicate stuck-tracking concepts: struct fields stuckCounter/lastValidPosition/lastPositionTime (425-427, no ref) versus function-`static` variables in StandardBotAI (13353-13358) that are shared by all bots.
- ai_main.h has prototypes for functions that are per-bot state consumers but no include guard besides `#pragma once`; `extern vmCvar_t bot_pvstype` is not declared in the header although defined at ai_main.c:82.

### Region notes, lines 2690-5800

#### (a) GetIdealDestination (ai_main.c:3947) - priority order

Only caller: StandardBotAI:14018, inside `if (bs->wpCurrent)` (13938), gated by `bs->destinationGrabTime < level.time` (14016). Not called from the NewBotAI path at all.

| # | Lines | Step | Gate / timer | Cost |
|---|---|---|---|---|
| 0 | 3954-3961 | _DEBUG only: bot_nogoals cvar => return | debug build | Cvar_Update |
| 1 | 3963-3966 | **`if (!bs->wpCurrent) return;`** | - | nothing else runs |
| 2 | 3968-3975 | badthing = GetNearestBadThing | `level.time - escapeDirTime > 4000` | num_entities loop, InPVS + line trace per threat |
| 3 | 3977-3985 | dangerousObject = badthing if shootable | - | - |
| 4 | 3987-3990 | return if no badthing and wpDestIgnoreTime active | bs->wpDestIgnoreTime | - |
| 5 | 3992-4005 | dontGoBack active: stash wpDestination in wpStoreDest, clear, return; else restore | bs->dontGoBack (set +1500 at 2819) | - |
| 6 | 4007-4016 | camping: wpDestination = wpCamping, return | bs->wpCamping | - |
| 7 | 4018-4025 | CTFTakesPriority => return | GT_CTF/CTY | MAX_CLIENTS loop, GetNewFlagPoint traces |
| 8 | 4026-4033 | SiegeTakesPriority => return | GT_SIEGE | see below |
| 9 | 4034-4037 | JMTakesPriority (does NOT return, falls through) | GT_JEDIMASTER | GetNearestVisibleWP |
| 10 | 4039-4085 | badthing: runningLikeASissy +100, stash dest, maybe reverse wpDirection and step wpCurrent to index+-1, return | bs->escapeDirTime (500-1000ms) | reads gWPArray[index+-1] unchecked |
| 11 | 4108-4130 | revengeEnemy alive: route to WP nearest him | bs->wpDestSwitchTime (+5-10s on success) | GetNearestVisibleWP + TotalTrailDistance |
| 12 | 4131-4153 | else squadLeader alive: route to leader | wpDestSwitchTime (+5-10s on success) | same |
| 13 | 4154-4217 | else currentEnemy: if too close for weapon range or chicken => flee (idle goal if > 400u, else neighbour WP farther from enemy); else chase via nearest WP | chase gated wpDestSwitchTime (+1-5s; 0.3-1s GT_SINGLE_PLAYER) and bChicken != 2 | GetBestIdleGoal or GetNearestVisibleWP |
| 14 | 4219-4228 | no destination: GetBestIdleGoal | `!wpDestination && wpDestSwitchTime < level.time` | gWPNum loop x TotalTrailDistance |

**When bs->wpCurrent is NULL (always, when gWPNum == 0):** the function is never even called (call site is inside `if (bs->wpCurrent)` at 13938) and would return at 3963 anyway. Consequences on a no-waypoint map: GetNearestBadThing never runs (no grenade/detpack avoidance, no dangerousObject, no doForcePush from 2734), CTF/Siege/JM priorities never run, wpDestination stays NULL. Zero cost from this whole region except the functions listed in (b)/(c).

#### GetBestIdleGoal (3881)
Returns -1 at once if !wpCurrent (3889). Every 5-15s (bs->randomNavTime, skipped when isCamper == 2) rolls randomNav (40% on); randomNav => -1. Otherwise loops all gWPNum, for each in-use WPFLAG_GOALPOINT whose weight beats the current best and whose item the bot lacks (BotHasAssociated), calls TotalTrailDistance(wpCurrent->index, i) and scores weight - dist/10000. No traces. No own timer: callers at 3155/3606 run it every frame during the post-respawn weapon-gather window; 4222 runs it every frame while wpDestination is NULL and wpDestSwitchTime expired.

#### CTF priority (CTFTakesPriority 3126, helpers 2829-3123)
- Not CTF/CTY => 0 (3147).
- Pistol-only and recently respawned: go to GetBestIdleGoal WP, return 1 (3152-3165).
- Requires flagRed/flagBlue/eFlagRed/eFlagBlue (3192).
- Dropped flags: GetNewFlagPoint per dropped flag (3209-3225) = up to gWPNum box traces, every bot, every call, no timer.
- !ctfState => 0 (3227). MAX_CLIENTS loop counts team/attackers (3234).
- State: carrying => GETFLAGHOME or RETRIEVAL; state_Forced overrides (3294).
- Dispatch: DEFENDER -> BotDefendFlag; ATTACKER -> BotGetEnemyFlag; RETRIEVAL -> BotGetFlagBack; GUARDCARRIER -> BotGuardFlagCarrier; GETFLAGHOME -> BotGetFlagHome. BotGetFlagBack/BotGuardFlagCarrier do a MAX_CLIENTS loop + GetNearestVisibleWP (gated wpDestSwitchTime, 1-5s on success).

#### Siege priority (SiegeTakesPriority 3578)
Not siege => 0. Weapon-gather as CTF. Attacking team => ATTACKER; else DEFENDER unless defenders > teammates/3 (2 MAX_CLIENTS loops). ATTACKER: Siege_TargetClosestObjective (gWPNum loop, 0-1 box trace); if none, Siege_DefendFromAttackers (MAX_CLIENTS loop + GetNearestVisibleWP, destinationGrabTime +10s on success). DEFENDER: Siege_DefendFromAttackers. Any state with shootGoal: InPVS + 1 line trace. Always returns 1.

#### Jedi Master priority (JMTakesPriority 3746)
Not JM, or bot is the JM => 0. MAX_CLIENTS loop to find the JM; target = JM or gJMSaberEnt; GetNearestVisibleWP gated by destinationGrabTime (+4000 on success). Returns 1 but caller continues.

#### Commander AI (4233-4588)
CommanderBotAI is called per frame (StandardBotAI:13560, no timer) for every bot with isSquadLeader; non-leaders run BotDoTeamplayAI (13564). CTF: 2 MAX_CLIENTS loops, alternates squad between defend/guard and attack/retrieve. Siege: forces own siegeState on up to half of team. GT_TEAM: sends one bot to assist teammate with health < 50, regroup every 45-65s (squadRegroupInterval). FFA/duel: no-op. No traces anywhere.

#### (b) Combat helpers

| Function | What it does | Gates | Traces |
|---|---|---|---|
| MeleeCombatHandling 4591 | Flip meleeStrafeDir every 500-1800ms (meleeStrafeTime); measure floor Z under enemy, self and midpoint; only if all three int-truncated Z values are equal set goalPosition = enemy origin | currentEnemy (4604). Callers 13120 / 14327: weapon range MELEE and frame_Enemy_Len <= 256. No timer on traces | 3 box traces (30x30x56) each 4096u down, every frame |
| BotWeaponCanLead 4679 | Lead factor table | - | 0. UNUSED |
| G_NewBotAIGetProjectileSpeed 4715 | Speed table; branch at 4746 is unreachable (shadowed by 4734) | - | 0 |
| G_NewBotAIAimLeading 4771 | ETA = frame_Enemy_Len / speed; predicted = headlevel + vel*ETA; + gravity drop for arcing weapons; airborne enemy: clamp to max force-jump height or trace along fall path; hitscan: lead 4u; DEMP2 alt: aim at ground 0.5s ahead; saberMove >= 4: add blade-tip offset and wiggle yaw/pitch; writes goalAngles | currentEnemy->client (4776). Called per frame from NewBotAI_GetAim:6879 | 0 normally; 1 line trace at 4818 or 4843 (see B_traces). Saber-only bots: 0 |
| BotAimLeading 4905 | Legacy lead by 0.9*dist*lead*vtotal*0.0012 along enemy velocity | - | 0. UNUSED (callers commented out) |
| BotAimOffsetGoalAngles 4985 | If perfectaim return; while aimOffsetTime active add stored yaw/pitch offset; else recompute accVal = accuracy/skill (x7 if mind-tricked, / revengeHateLevel, 0 if enemy stationary, +25%/+15% for motion, clamp 0..90) and roll new offsets for 200-700ms | bs->aimOffsetTime; callers 13297, 14255 | 0 |
| ShouldSecondaryFire 5102 | Ammo check; rocket lock charge logic; per-weapon range rules for alt fire | only from CombatBotAI | 0. dead |
| CombatBotAI 5183 | Saber/melee: attack in range; guns: FOV check (40/60/160, x2 under 128u), thermal charge logic, ShouldSecondaryFire | - | 0. UNUSED |

#### (c) No-waypoint navigation

Call graph (whole-file grep):
- BotFallbackNavigation: NewBotAI_DoAloneStuff:12770; StandardBotAI:14085; StandardBotAI:14111 (RMG.integer only - iHaveNoIdeaWhereIAmGoing is only set at 14102 under RMG).
- IsPositionReachable: BotFallbackNavigation:5507, 5544; ExpandingSpiralSearch:5664.
- SmartExploration: **never called**. Therefore FollowGroundContours (5564), ExpandingSpiralSearch (5569), MoveTowardLastWaypoint (5574) are **never executed**.

#### BotFallbackNavigation (5336) step by step
Static per-client state (function-local, MAX_CLIENTS each, never reset): explorationTarget, explorationTimer (init flag only), stuckCounter, lastPosition, lastWallHitTime, lastMovementDirection (5342-5347).

1. 5350: enemy visible => return 0 (0 traces).
2. 5355: first-ever call for this slot => init statics.
3. 5367-5390: if a target exists: stuckCounter++ when moved < 10u since last call OR dot(targetDir, lastMovementDirection) < 0.3; at > 5 clear target, counter = 0, lastWallHitTime = now+1000. Otherwise counter = 0.
4. 5392: lastPosition = origin.
5. 5403: box trace 32u forward (view yaw+pitch) => wallDistance. 5413: line trace 300u down at 64u ahead => isLedgeAhead (no hit, or floor > 120u below the +50 start, i.e. > 70u below feet-origin).
6. 5419: wall < 20u or ledge: if cooldown expired (5420) 2 box + 2 line traces, turn ideal_viewangles yaw -60 / +60 / +180, clear target, cooldown 500ms. Always EA_Move backward at speed 2000 and return 1.
7. 5478-5492: existing target farther than 50u => keep (hasTarget); else clear.
8. 5495-5515: no target and cooldown expired: up to 12 random (angle 0-359, dist 150-400) IsPositionReachable tests; first success becomes target.
9. 5518-5530: hasTarget: goalAngles = dir, EA_Move at 3500, goalPosition = origin + 250*dir, return 1.
10. 5533-5551: "emergency" branch needs stuckCounter > 20 - unreachable.
11. return 0.

Trace count per call:

| Situation | Box | Line | Total |
|---|---|---|---|
| enemy visible | 0 | 0 | 0 |
| has target, path clear (steady state) | 1 | 1 | 2 |
| wall/ledge, cooldown active | 1 | 1 | 2 |
| wall/ledge, cooldown expired | 3 (2 of them map-origin length) | 3 | 6 |
| needs target, first attempt succeeds | 2 | 4-7 | 6-9 |
| needs target, all 12 blocked at box test | 13 | 1 | 14 |
| needs target, 12 fail at last ground probe (worst) | 13 | 1 + 12*6 = 73 | 86 |
| no target, wall cooldown active (after stuck reset) | 1 | 1 | 2, returns 0 |

No back-off when all 12 attempts fail: the 12-attempt search repeats the next frame. With 25 bots on a ledge-heavy map this is up to 25 x 86 traces per frame.

#### IsPositionReachable (5725)
1. 5733 box trace origin->target (30x30x32, MASK_PLAYERSOLID); fraction < 0.7 => false.
2. 5747 checks = (int)(dist/100)+1; for i=1..checks: line trace 400u down from +50 at min(i*100, dist); fail if no hit, drop > 150, or rise > 100.
3. 5787 final line trace at target; fail if no hit or |ground z - origin z| > 200.
Best 1 trace (fail), success = (int)(d/100)+3 traces: 150u => 4, 250u => 5, 399u => 6, 400u => 7. No static state.

#### SmartExploration (5559) - never called
Runs the three below in order, returning on first success. Only sets goalPosition/goalAngles; does not EA_Move.

#### FollowGroundContours (5584) - never called
7 angles {0,+-30,+-60,+-90}; per angle up to 5 line traces (600u down) at 100..500u, stop at first hit within 200u of bot Z. Picks farthest valid among indices 1..6 (index 0 traced but ignored). Best 7 traces, worst 35. No static state.

#### ExpandingSpiralSearch (5652) - never called
Radii 100..800 step 100, 12 angles each, IsPositionReachable per point, first success wins. Best 4 traces; worst 12 * sum(r/100+3 for r=100..800) = 12*60 = 720 traces. No static state.

#### MoveTowardLastWaypoint (5681) - never called
Returns false if lastKnownWaypointPos is zero (it is never assigned anywhere) or within 50u; else 1 box trace up to 300u, success if fraction >= 0.7. In practice always 0 traces and false.

### Region notes, lines 5790-8700

#### Region C overview (ai_main.c 5790-8700)

Dispatch context (outside region, read to classify callers): BotAI 820-823 runs `NewBotAI` if `g_newBotAI.integer` else `StandardBotAI`, once per bot think. Both paths call the `NewBotAI_{LS,DS}v{LS,DS}` functions when an enemy client is visible (NewBotAI 13050-13060; StandardBotAI 13598-13611), so most `NewBotAI_*` functions in this region run in BOTH modes. `NewBotAI_Tribes` (12445) calls `StandardBotAI` and then `NewBotAI_GetAim` + `NewBotAI_GetAttack`.

Trace budget of the whole region per bot think (live code only):

| Source | Traces | When |
|---|---|---|
| CheckForFriendInLOF 6386 | 1 box, 2048u, MASK_PLAYERSOLID | StandardBotAI: every think in team gametypes (14811), or whenever firing (14775) |
| BotCanHitEnemy 8044 | up to 3 box, <=154u, MASK_PLAYERSOLID | saber weapon, enemy visible and within 128u, attack timers elapsed |
| Lightning/Draining/MindTrick 7217/7252/7263 | 1 line each | only while that force power is active; redundant with frame_Enemy_Vis |
| CTFFlagMovement 6535 | 1 box <=256u | CTF with dropped flag within 256u |
| BotCheckDetPacks 6558/6597 | G_Find entity scan + 1 line | while own detpack planted |
| BotSurfaceNear 6668 | 1 line 64u | mine/detpack planting branch |
| StrafeTracing 6220-6280 | (4) | never - dead code |

No trap->InPVS / PointContents / EntitiesInBox / gWPNum loops exist in this region. Loops are MAX_CLIENTS (BotDeathNotify 6179, BotScanForLeader 6419, BotReplyGreetings 6447, NewBotAI_GetAim 6824) or WP_NUM_WEAPONS (5804, 5878, 6007), plus the G_Find entity scan (6558).

#### (a) Weapon selection

| Function | Line | Used by | Logic | Cost / notes |
|---|---|---|---|---|
| BotTryAnotherWeapon | 5798 | StandardBotAI 13628 (current weapon out of ammo) | first weapon index 1..WP_NUM_WEAPONS-1 with ammo >= energyPerShot and owned; fallback weapon 1 | loop only; sets bs->virtualWeapon, BotSelectWeapon |
| BotWeaponSelectable / AltFire | 5832 / 5848 | the three selectors below | owned bit + ammo >= energyPerShot / altEnergyPerShot | O(1) |
| BotSelectIdealWeapon | 5865 | StandardBotAI 13664 only | 5873: if g_newBotAI and has saber -> always saber, return 0. Else max bs->botWeaponWeights[i] (thermal only if enemy < 700), then distance overrides: >1000 disruptor/demp2/blaster; 300-900 blaster/repeater(alt ammo)/disruptor; <150 flechette/repeater/rocket/concussion/blaster/disruptor; bryar+enemy<300 -> saber | no traces; runs every StandardBotAI think (no timer). Returns 1 on switch, which makes StandardBotAI `return` early that think (13666) |
| BotSelectChoiceWeapon | 6000 | 13654, 14396, 14397, 14425 | has-weapon check (note `>` not `>=` at 6009) + optional select; returns 2 when newly selected | loop is redundant (only i == weapon can match) |
| BotSelectMelee | 6038 | none (commented 13669) | dead | - |
| NewBotAI_GetWeapon | 7600 | NewBotAI_GetAttack 10524 (every think with enemy, both AI modes via XvX) | 3 enemy-weapon classes (saber 7614; splash weapons 7729; other 7843) x 3 distance tiers with gaps (hysteresis padding); sets bs->doAltAttack, bs->altChargeTime (800 bryar_old / 1200 pistol / 2100 demp2 / 50 if enemy holds DEMP2), bs->ChargeTime (thermal 1250). Honors level.clients[].forcedFireMode | no traces; long else-if chains of O(1) checks. Result is passed to BotSelectWeapon every think at 10525 (no change detection) |
| NewBotAI_GetTribesWeapon | 7448 | NewBotAI_GetAttack 10522 when g_tweakWeapons & WT_TRIBES | distance tiers >3000, 800-2800, <600; uses jetpackFuel gating for blaster/bryar_old | no traces |
| NewBotAI_GetAltCharge / GetCharge | 7973 / 7990 | NewBotAI_GetAttack 10558 / 10572 | 0 no ammo, 1 keep charging, 2 release (charged longer than bs->altChargeTime / bs->ChargeTime), 3 not charging | O(1); timers: level.time - cur_ps.weaponChargeTime vs bs->altChargeTime / bs->ChargeTime |

In StandardBotAI the order per think is: XvX (which runs NewBotAI_GetAttack -> NewBotAI_GetWeapon -> BotSelectWeapon, 10525) and later BotSelectIdealWeapon (13664) -> BotSelectWeapon. Two independent selectors can therefore issue conflicting weapon selects in the same think when g_newBotAI is 0.

#### (b) StrafeTracing, CheckForFriendInLOF, BotCheckDetPacks, BotSurfaceNear, CTFFlagMovement

| Function | Line | Live? | Traces | Gate | Optimization relevance |
|---|---|---|---|---|---|
| StrafeTracing | 6201 | DEAD (no call site in codemp) | 3 box 32u + 1 line 32u | 30% RNG | Zero current cost. Side effect of being dead: bs->meleeStrafeDisable is only ever written here (6231-6285), so the check at 14629 is always true and bs->meleeStrafeDir is never flipped by wall/ledge logic |
| CheckForFriendInLOF | 6362 | LIVE | 1 box 6^3, 2048u, MASK_PLAYERSOLID | none internal; 14811 makes it unconditional per think in gametype >= GT_TEAM | Prime candidate for a timer (e.g. 100-200 ms cache of result) or for skipping when no teammate is within the view cone |
| BotCheckDetPacks | 6550 | LIVE | G_Find scan + <=1 line | bs->cur_ps.hasDetPackPlanted | Entity scan each think; could cache the detpack entity pointer |
| BotSurfaceNear | 6657 | LIVE | 1 line 64u | planting branch (bs->plantTime, bs->plantDecided) | negligible |
| CTFFlagMovement | 6471 | LIVE (called every think 14361) | <=1 box <=256u | flag globals + distance | negligible outside CTF; in CTF repeats each think while within 256u of a dropped flag because bs->wantFlag is never assigned in this function (only cleared at 6500/6505/6510) |

#### (c) Aim: NewBotAI_GetAim / NewBotAI_GetStrafeAim

- NewBotAI_GetAim (6798): sets bs->hitSpotted = qfalse; if bs->runningLikeASissy -> NewBotAI_GetStrafeAim and return (before any enemy NULL check). Otherwise requires currentEnemy->client (6812).
- Saber-in-flight scan (6823-6842): only when the bot's own saber is not in flight. Loop `while (i <= MAX_CLIENTS)` = 33 iterations. Per-iteration filter order: i != self, client != NULL, saberInFlight (cheap, rejects almost all), then OnSameTeam, PassStandardEnemyChecks (no traces), PassLovedOneCheck. Distance uses saber entity s.pos.trBase vs bs->cur_ps.origin, squared; candidate needs saber->s.pos.trTime != 0.
- If closest saber < 200u and (enemy further than 200u or the thrower is the current enemy): aim at saber trBase, hitSpotted = qtrue (6844-6857). Else normal aim: enemy origin + viewheight - 16 (+24 if own saber in flight) -> G_NewBotAIAimLeading (4771).
- Ends with VectorCopy(goalAngles, ideal_viewangles) (6881).
- Cost: zero traces; 33-iteration loop per think. With 25 bots = 825 cheap iterations per think round; not a hotspot.
- NewBotAI_GetStrafeAim (6753): computes angle to enemy chest into goalAngles, then optimal strafe angle via acos((baseSpeed - baseSpeed*0.008)/currentSpeed) - 45 + 1 + bot_strafeOffset; newAngle by forceMove_Forward/Right; then OVERWRITES goalAngles[YAW] with bs->aimOffsetAmtYaw + newAngle (6792). No traces. See C_bugs for NaN and NULL issues.

#### (d) Force-power "state" functions

All are called from the XvX functions only while the corresponding condition is already true in bs->cur_ps (power active, knocked down, gripped). None has its own timer. All select the power by writing level.clients[bs->client].ps.fd.forcePowerSelected and pressing trap->EA_ForcePower.

| Function | Line | Called when (caller lines) | Traces | Behaviour |
|---|---|---|---|---|
| NewBotAI_Getup | 7013 | forceHandExtend == HANDEXTEND_KNOCKDOWN (11892, 11943, 12024, 12040, 12082, 12106, 12141, 12157, 12182) | 0 | EA_Jump; protect if gripped and falling; else absorb / protect by weight; else push if enemy < 200 or gripped |
| NewBotAI_Flipkick | 7051 | 7134, 7187, 7190, 12459, 12851 | 0 | forward+jump when on world ground or forceJumpZStart < 16; crouch during red overhead; second jump tap when 24-48u above jump start on odd frames |
| NewBotAI_ReactToBeingGripped | 7084 | fd.forceGripBeingGripped > level.time (11897, 11948, 12086, 12110) | 0 | priority chain absorb > push/pull > pull > push > toggle speed; then Flipkick; EA_ForcePower on odd level.framenum |
| NewBotAI_Gripkick | 7141 | FP_GRIP active (11963, 12055) | 0 | pitch/yaw choreography by gripTime (level.time - enemy fd.forceGripStarted): <1000, <2000, <2200, <4000; Flipkick; always EA_ForcePower. Loop of 3 iterations via GetTimeToInRange |
| NewBotAI_Lightning | 7200 | FP_LIGHTNING active (11953, 12045) | 1 line (7217) | early-outs then OrgVisible; aim jitter via Q_irand; keep 180-280u; hold power |
| NewBotAI_Draining | 7246 | FP_DRAIN active (11968, 12060) | 0-1 line (7252) | hold power while health < 100 and enemy has FP and no absorb and visible |
| NewBotAI_MindTrick | 7256 | FP_TELEPATHY active (12118, LSvDS only) | 0-1 line (7263) | re-press telepathy if health <= 50 and FP > 25 |
| NewBotAI_Speeding | 7274 | FP_SPEED active (11973, 12065, 12114, 12162) | 0 | presses force with FP_SPEED selected if health < 90 or FP <= 100 |
| NewBotAI_Raging | 7282 | FP_RAGE active (11958, 12050; 11977 unreachable) | 0 | off if FP < 10 (plus direct clear of forcePowersActive bit, 7304) or health >= 50; "turn on" block needs !rageActive so is effectively unreachable from these callers |
| NewBotAI_Protecting | 7338 | FP_PROTECT active (12120, 12164) | 0 | toggle off if enemy not visible, far and low FP, enemy saber dropped and enemy FP < 35, or > 1024u |
| NewBotAI_Absorbing | 7370 | FP_ABSORB active (12122, 12166) | 0 | toggle off if not visible, or far/enemy low FP and not gripped, or enemy saber dropped with FP < 35 |
| NewBotAI_Healing | 7391 | FP_HEAL active (12116) | 0 | inner test requires FP_HEAL NOT active -> no-op |
| NewBotAI_SaberThrowing | 7406 | cur_ps.saberInFlight (11914, 11991, 12093, 12124) | 0 | hold EA_Alt_Attack while 500 <= frame_Enemy_Len <= 2500 |

Perf: the only traces here are 7217/7252/7263 and all three test the same segment (bs->eye -> enemy ps.origin, MASK_SOLID, ignore bs->client) that NewBotAI already evaluated into bs->frame_Enemy_Vis at 13004 in the same think. Replacing them with bs->frame_Enemy_Vis removes one line trace per think for every bot holding lightning/drain.

#### (e) "Enhanced combat" block 8008-8678

None of these functions is dead: every one is reachable from NewBotAI (13085-13090, 13286) and/or StandardBotAI (14244, 14284-14293, 14612, 14621). Reachability table:

| Function | Line | Direct callers | Live? | Timers / state used |
|---|---|---|---|---|
| BotCanHitEnemy | 8008 | BotShouldAttack 8066, BotCanAttackNow 8318 | live | none (1 box trace 8044) |
| BotShouldAttack | 8052 | BotShouldAttackNow 8602 | live | enemy ps.saberBlockTime vs level.time |
| BotPredictEnemyPosition | 8070 | 8019, 8628, 13286 (NewBotAI), 14244 (StandardBotAI) | live | via 8088: bs->enemyMovementHistoryTime, bs->lastEnemyVelocity |
| BotGetPredictionTime | 8118 | 8082 | live | none |
| BotAnalyzeMovementPattern | 8136 | 8088 | live | bs->enemyMovementHistoryTime (100 ms), bs->lastEnemyVelocity |
| BotPredictStrafing/Jumping/Retreating/ChargingMovement | 8184/8216/8251/8274 | 8093/8096/8099/8102 | live | none |
| BotCanAttackNow | 8298 | 8327, 8598 | live | bs->nextAttackTime, bs->attackRecoveryTime, cur_ps.saberBlockTime |
| BotExecuteAttack | 8325 | 13090, 14289 | live | writes bs->nextAttackTime (now+300..800 ms), bs->attackRecoveryTime (0.8x), bs->lastAttackTime, bs->lastAttackType, bs->comboWindow (0.3x) |
| BotGetAttackDelay | 8347 | 8331 | live | none |
| BotGetCurrentAttackType | 8388 | 8342 | live (result bs->lastAttackType is write-only in ai_main.c: only 984, 8342) | none |
| BotDynamicCombatMovement | 8406 | 8648, 14621 | live | bs->attackRecoveryTime, bs->isAttacking |
| BotGetOptimalCombatDistance | 8452 | 8421, 8669 | live | none |
| BotShouldStrafeInCombat | 8482 | 8436, 14293 | live | bs->attackRecoveryTime; RNG |
| BotCombatStrafe | 8505 | 8437, 8643 | live | writes bs->combatStrafeTime (now+300/400), bs->combatStrafeDir (write-only: 991, 8543) |
| BotSelectStrafeDirection | 8550 | 8516 | live | none; RNG |
| BotShouldAttackNow | 8588 | 13089, 14288 | live | via BotCanAttackNow |
| BotUpdateAttackTiming | 8614 | 13085, 14284 | live | bs->comboWindow, bs->lastAttackHitTime, bs->lastAttackTime, bs->nextAttackTime |
| BotUpdateDynamicMovement | 8635 | 13086, 14285 | live | bs->combatStrafeTime, bs->nextAttackTime |
| BotMovementDuringAttack | 8653 | 14612 | live | bs->isAttacking, bs->attackRecoveryTime |
| BotEnemyInRecovery | 8683 | 8763, 9608, 10233 | live | enemy ps.torsoTimer |

Dead sub-paths inside live functions (verified by Grep of the whole file):
- bs->isAttacking is only ever assigned qfalse (992). So `!bs->isAttacking` at 8443 is always true and the early return at 8659 never fires.
- bs->lastAttackHitTime is only ever assigned 0 (987). So the combo EA_Attack at 8619-8620 can never execute.
- bs->combatStrafeDir and bs->lastAttackType are never read.

Call tree and trace count for one think in saber range (frame_Enemy_Len <= 128, lines 13083-13091 or 14282-14290):

| Step | Call | BotPredictEnemyPosition calls | Box traces (8044) |
|---|---|---|---|
| 1 | BotUpdateAttackTiming | 0-1 (if nextAttackTime < now+200) | 0 |
| 2 | BotUpdateDynamicMovement -> BotCombatStrafe / BotDynamicCombatMovement | 0 | 0 |
| 3 | BotShouldAttackNow -> BotCanAttackNow -> BotCanHitEnemy | 1 | 0-1 |
| 4 | BotShouldAttackNow -> BotShouldAttack -> BotCanHitEnemy | 1 | 0-1 |
| 5 | BotExecuteAttack -> BotCanAttackNow -> BotCanHitEnemy | 1 | 0-1 |
| 6 | (StandardBotAI only) 14244 aim, 14612, 14621 | 1 | 0 |

So up to 3 identical-purpose box traces per think, each only after the timer gates in BotCanAttackNow (nextAttackTime, weaponstate READY/IDLE, attackRecoveryTime) and the distance/cone tests pass. After a successful BotExecuteAttack, nextAttackTime blocks further traces for 300-800 ms. If the RNG at 8606-8608 fails (attackChance = 0.5 + 0.1*skill; always passes for skill >= 5) the 2 traces repeat next think. Caching one BotCanHitEnemy result per think (keyed on level.time) would cut this to 1.

Because BotAnalyzeMovementPattern overwrites bs->lastEnemyVelocity on every call (8158), only the FIRST BotPredictEnemyPosition call in a think can classify strafing/jumping/retreating; later calls in the same think see velChange == 0 and return 4 (speed > 150) or 0. Combined with fresh Q_irand jitter (8112-8113), the up-to-5 predictions per think disagree with each other.

Movement conflicts (no traces, behaviour only): in StandardBotAI one think can issue EA_Move at 14605 (goal), 8546 (strafe via 8643), 8446 (via 8648), 8546/8446 again via 14621, plus EA_MoveForward/Back from 14612 -> 8673/8676.

### Region notes, lines 8680-11215

#### Region D overview (ai_main.c 8680-11215)

- 16 trace call sites total (15 trap->Trace line, 1 JP_Trace box). Zero loops, zero PVS/PointContents/EntitiesInBox/G_Find/OrgVisible/BotCanHitEnemy.
- Call frequency: NewBotAI (13052-13060) and StandardBotAI (13602-13610) call one NewBotAI_XvY per frame, which calls NewBotAI_GetMovement once and NewBotAI_GetAttack once. Then NewBotAI 13237 / StandardBotAI 14186 call NewBotAI_GetAttack AGAIN in the same frame (gate: timeToReact < level.time, enemySeenTime, frame_Enemy_Vis). So Bot_ExecuteSaberCombat can run 2x per bot per frame.
- Estimated traces per saber bot per frame in a close duel (dist<=100, enemy visible): GetMovement 1 (obstacle fn, no effective cooldown) + 1 (fwd/back probe) = 2; SaberCombat 2 x (1 box + 1 line) = 4. Total ~6 (worst 3 + 6 = 9). At 25 bots: ~150-225 traces/frame from this region.
- Gun bot / mid-range (generic movement path): 3 (CheckMovementPaths) + 0-1 + optional 1 (obstacle fn when dist>200) + optional 3 = 3-8; attack path 0 traces in region.
- Timer names requested but NOT present in this region: strafeDirExpire, forwardDirExpire, evadeSideCooldown. Actual timers used here: strafeExpireTime, noUseTime, lastObstacleTime, noJumpTime, noRetreatTime, lastStyleSwitchTime, lastSpecialTime/specialDuration, blocking.parryWindow/lastParryTime, avoidanceTimer (never set).

#### (a) Bot_ExecuteSaberCombat (9948-10511)

| # | Lines | Step | Gate / probability | Traces |
|---|---|---|---|---|
| 1 | 9956-9957 | ideal_viewangles = angles to enemy from eye (derefs currentEnemy->client unguarded; caller guards) | always | 0 |
| 2 | 9964-9975 | Wall probe: BOX trace 48u forward; nearWall = fraction*48 < 24 | always, no timer | 1 box |
| 3 | 9978-9988 | nearWall: 50% EA_MoveBack; ideal yaw += Q_irand(-30,30) | nearWall | 0 |
| 4 | 9995-10003 | Emergency ignite: Cmd_ToggleSaber_f + EA_Attack, return | saberHolstered && dist<=60 | 0 |
| 5 | 10010-10023 | bs->doAttack = 1 | 80% if nearWall else 70%, and dist <= SABER_ATTACK_RANGE (128) | 0 |
| 6 | 10026-10029 | empty block (burns one Q_irand) | - | 0 |
| 7 | 10039-10078 | Obstacle-to-enemy line trace; if low non-world entity (<64 high) in the way, second trace; sets shouldJumpOverObstacle | enemy visible && dist<=200 | 1 line (+1) |
| 8 | 10081-10098 | Jump + EA_Move toward enemy 4000, 70% attack; does not return | shouldJumpOverObstacle | 0 |
| 9 | 10101-10114 | Avoidance strafe, 25% attack, return | bs->avoidanceTimer > level.time - avoidanceTimer is never written anywhere => dead | 0 |
| 10 | 10125-10173 | Per-style ranges: SABER_RANGE 40/50/60, CLOSE_RANGE 24/32/36, LUNGE_MIN 50/65/75, LUNGE_MAX 80/95/110, SPECIAL_RANGE 150/190/220 (fast,tavion / medium,default(staff,dual) / strong,desann) | - | 0 |
| 11 | 10196-10198 | Expire special when level.time - lastSpecialTime >= specialDuration | - | 0 |
| 12 | 10201-10208 | If a special is active: RETURN (no commands issued for the 400-1200 ms duration). The "600 ms cooldown" branch does nothing (falls through, specials still allowed) | currentSpecial != 0 | 0 |
| 13 | 10220-10222 | return if dist > SPECIAL_RANGE | | 0 |
| 14 | 10227 | Bot_UpdateEnemySwingMemory (ai_util.c:898; also called from GetMovement 10866 => decay applied 2-3x per frame) | | 0 |
| 15 | 10233-10238 | enemyRecovering / Vulnerable / Swinging; Bot_ExecutePerfectBlocking (may zero EA_Move, set pitch -10, yaw wiggle, parry, or back+jump) | | 0 |
| 16 | 10241-10257 | shouldBlock = enemySwinging && (blockConfidence<0.2 or enemyAttackPower>18); if stage 2..6: 80% counter (Q_B, move 6000, attack) when enemyRecovering, then return either way | | 0 |
| 17 | 10264-10280 | specialChance = 65 + bonuses (conf>0.4:+25, vulnerable:+30, recovering:+20, enemy hp lower:+15, dist<=100:+20, swing memory +8/+8/+5), capped 95 | | 0 |
| 18 | 10287-10421 | Special cascade, first hit wins and returns. Each sets currentSpecial/specialDuration/lastSpecialTime BEFORE calling Bot_Execute* (which may itself bail on range/FP) | see table below | 0 |
| 19 | 10428-10436 | Basic swing: quad Q_irand(Q_R,Q_L), move 5000, attack | dist<=SABER_RANGE && 70% | 0 |
| 20 | 10443-10451 | Defensive counter: Bot_ExecuteDefensiveCounter if blockConfidence>0.2 && 90%; return regardless | enemySwinging && dist<SABER_RANGE | 0 |
| 21 | 10454-10464 | Lunge: Bot_ExecuteLungeAttack 65% (85% if enemy healthier) | LUNGE_MIN<=dist<=LUNGE_MAX && enemyVulnerable; callee additionally requires 95<=dist<=140 | 0 |
| 22 | 10470-10484 | Close range: 98% attack with quad (recovering ? Q_irand(Q_BR,Q_B) : Q_irand(Q_R,Q_L)); return | dist<=CLOSE_RANGE | 0 |
| 23 | 10490-10510 | Edge pressure: 85% (95% if enemy hp > mine*1.1) attack pattern 0..2 | dist<=SABER_RANGE | 0 |

Special cascade (step 18). P = Q_irand(1,100) <= specialChance + bonus, specialChance is 65..95:

| Order | Line | Special | Extra condition | Chance | Duration ms | Callee own gate |
|---|---|---|---|---|---|---|
| 1 | 10287 | KATA | dist<=SPECIAL_RANGE (always true here) | 75-100% | 1200 | dist 40..256, FP>=50, weapon saber, not already in kata |
| 2 | 10299 | DANCE | dist<=CLOSE_RANGE | 73-100% | 800 | dist<=80 |
| 3 | 10310 | RUSH | dist<=100 | 70-100% | 600 | dist<=100 |
| 4 | 10321 | DFA | dist<=200, style medium/strong/dual/staff | 70-100% | 1000 | dist 50..200 |
| 5 | 10340 | CROUCHLUNGE | dist<=100, style fast/dual/staff | 70-100% | 1000 | dist<=100 |
| 6 | 10358 | HURRICANE | dist<=90 | 67-97% | 700 | dist<=90 |
| 7 | 10369 | STYLE_SWITCH | dist<=120 && enemyVulnerable | 65-95% | 400 | staff/dual && offense>1 |
| 8 | 10380 | DELAY_ATTACK | dist<=110 && enemyVulnerable | 71-100% | 900 | dist<=110 |
| 9 | 10391 | CONVERGENT | dist<=100 | 80-100% | 800 | dist<=100 |
| 10 | 10402 | STATIC | dist<=90 && enemyRecovering | 73-100% | 600 | dist<=90 |
| 11 | 10413 | COMBO | dist<=120 | 70-100% | 1000 | dist<=120 |

Consequences (verified by reading): kata is rolled first with >=75% chance on every un-locked call, so the bot spends most time in SPECIAL_KATA lockout (1.2 s of no saber commands from this function) even when the kata could not fire (FP<50, dist<40). Steps 19-23 are reached at most ~25% x (1-P)^n of un-locked calls. No feint is ever chosen (Bot_ExecuteFeint/BotCanFeint are dead code).

Traces per call: best 1 (box only: enemy not visible or dist>200), typical 2, worst 3. All three run BEFORE the special-lockout return at 10205, so they are paid even on frames where the function does nothing. Cheap wins: move step 12/13 early-outs above steps 2 and 7; time-gate or cache the box trace; dedupe the second GetAttack call per frame.

#### (b) Blocking / parry system

- Bot_AnalyzeEnemyAttack (8846): stage from enemy ps.torsoTimer: 0 idle; >400:1; >300:2; >200:3; >100:4; >50:5; >25:6; else 7. Stage 8 is never produced. enemyAttackPower = base (7 for stages 3-5, 5 for 2/6, 3 otherwise) x stance (strong/desann 1.5, staff 1.3, dual 1.2, medium/tavion 1.1, fast 1.0) x speed (>200:1.3, >100:1.1, else ducked 0.8) x 2. Range 6..27.3. No traces.
- Bot_ExecutePerfectBlocking (8958), called once per un-locked SaberCombat call (10238):
  1. Stage 2..6: EA_Move zero vector (later EA_Move calls in SaberCombat override it), ideal pitch forced to -10 (absolute, overrides aim; in Quake angles negative pitch is UP although comment says down), ideal yaw += Q_flrand(+-5/10/15); if stage==2 and lastParryTime older than 500 ms: shouldParry=qtrue, parryWindow=level.time+100; return.
  2. Else if shouldParry && level.time < parryWindow: Bot_ExecuteParry; return.
  3. Else if enemyAttackPower>10 && enemy staff: EA_MoveBack, EA_Jump if on ground, blockConfidence -= 0.1 (no lower clamp); return. (Power is 0 when enemy idle, and stages 2-6 returned earlier, so only stages 1 and 7: 3*1.3*2=7.8, x1.3 running = 10.14 => only vs running staff user.)
  4. Else "reset parry" if stage==8 - unreachable.
- Bot_ExecuteParry (9058): counter quad by enemy saberMove (L2R/TL2BR -> Q_BR; R2L/TR2BL -> Q_BL; T2B -> Q_irand(Q_R,Q_L); else Q_B), EA_Move 8000, EA_Attack, lastParryTime, blockStreak++, blockConfidence += 0.2 capped 1.0. Reachability: shouldParry is armed only in stage 2 and stage 2..6 frames return before the parry branch; the 100 ms window expires long before stage 7 (>=275 ms of torsoTimer later). Only reachable if the enemy's move leaves stages 2..6 within 100 ms of a stage-2 frame (swing interrupted/chained). Effectively near-dead, so blockConfidence stays at 0.5 (init) or only drifts down.
- blocking.lastBlockTime is never updated after init (9110).
- Bot_SelectOptimalSaberStyle (9174): no traces. Early outs: in kata (9189); own saberMove not NONE/READY or lastStyleSwitchTime+2000 not elapsed (9194); current style staff/dual (9201). Human enemy: hp<40 -> want FAST; else counter table (strong/desann -> fast; fast -> medium; medium/tavion -> strong if offense>2 && bs->saberPower else fast); returns if enemy style in SS_FAST..SS_TAVION. Bot enemy: hp<40 -> FAST; variety switch when level.time > lastStyleSwitchTime + Q_irand(8000,15000) (re-rolled each call => fires close to 8 s). Fallback distance rule: <=80 fast; >=120 strong (enemy hp>60) or medium; between: medium (enemy hp>50) or fast. Every "switch" is a single Cmd_SaberAttackCycle_f (next style in cycle, not the target style), so it converges over several 2 s steps or oscillates. Called 2-3x per frame (10542 via each GetAttack, plus 13078/14277).
- Bot_GetStyleAdvantage (9117): pure table, never called.

#### (c) Bot_CheckAndInteractWithObstacle (9680-9945)

1. 9686-9699: line trace from origin+24, 128u along full view forward (+24 z), mask PLAYERSOLID without BODY. Always executed.
2. 9701: proceed only if tr.entityNum < ENTITYNUM_WORLD && fraction<1 (world brushes are ignored; ENTITYNUM_NONE/WORLD indexing is safe).
3. 9705-9707: reject entities with client, s.NPC_class, or classname containing "player"/"npc".
4. 9716-9740: classify by classname: obstacle = func_breakable, func_glass, misc_model_breakable, func_static, misc_model, misc_model_ghoul; wall = func_wall, func_static, misc_model; fence = func_fence, "fence*", or model path containing "fence". Up to 12 Q_stricmp + strstr.
5. 9744-9805 combat jump: requires absmax[2]-origin[2] > 48 AND < 48 -> inner block (incl. trace 9784) unreachable.
6. 9809-9831 non-combat jump: requires > 30 AND < 30 -> unreachable.
7. 9834-9851 func_door: spawnflags&1 -> qfalse; within 80u: EA_Use, noUseTime = +500, face door, qtrue; else qfalse.
8. 9854-9861 func_button / trigger_multiple / target_switch: EA_Use, noUseTime +300, qtrue (triggers are not solid to this mask; target_switch is not a solid entity).
9. 9864-9874 func_plat / func_train / func_elevator within 32 z: EA_Use, noUseTime +500, qtrue.
10. 9877-9887 in combat + obstacle + weapon saber/melee/rocket/thermal/detpack: EA_Attack, qtrue (includes func_static / misc_model, i.e. indestructible geometry).
11. 9890-9941 in combat + obstacle, other weapons: 2 line traces 64u (left, and mis-named "right" = up), EA_Move 3000 sideways or back, face enemy, qtrue.

Note EA_Use maps to BUTTON_USE_HOLDABLE (ai_main.c:582), while the real BUTTON_USE is pressed randomly only when noUseTime < level.time (589). So steps 7-9 fire the holdable item and suppress the real use button for 300-500 ms.

Traces: best 1, worst 3 (9784 unreachable). Gate (in caller): noUseTime < level.time && lastObstacleTime < level.time-3000, but lastObstacleTime is only updated when the function returns qtrue (10886, 10945) or by CheckMovementPaths jump (10841). In open space it returns qfalse and therefore runs every frame: saber bots at dist<=100 (10885) and any bot at dist>200 (10944).

#### (d) NewBotAI_GetAttack (10513-10584)

1. 10518: return if !bs->client (client number 0!), no enemy, or enemy has no client.
2. 10521-10525: weapon = NewBotAI_GetTribesWeapon or NewBotAI_GetWeapon (7600, outside region); BotSelectWeapon - every call.
3. 10527: return if bs->runningLikeASissy. 10529: return if isCamper and not charging. 10533: return if enemy invulnerableTimer active.
4. 10538-10547 saber: Bot_SelectOptimalSaberStyle then Bot_ExecuteSaberCombat, return. NOT gated by frame_Enemy_Vis for the calls coming from NewBotAI_XvY.
5. 10549: return if enemy not visible (except WP_DEMP2).
6. 10553-10583 guns (only if !isCamper and current weapon == chosen weapon): enemyVulnerable = BotEnemyVulnerable; alt path uses NewBotAI_GetAltCharge (1 => hold alt; 3 => alt-fire when level.framenum % fireRate != 0); primary path uses NewBotAI_GetCharge likewise. fireRate = vulnerable ? 1 : 2, and x % 1 is always 0 => never fires when the enemy is "vulnerable"; otherwise fires on odd frames only.

Traces in region: 0 for guns; saber = Bot_ExecuteSaberCombat (1-3). Called up to 2x per bot per frame.

#### (e) NewBotAI_GetMovement (10860-11210) and Bot_CheckMovementPaths (10775-10853)

Bot_CheckMovementPaths: 3 line traces every call (no timer): forward 64u (+24 z), "left" 32u, "right" 32u, MASK_PLAYERSOLID incl. bodies, blocked = fraction<0.8. Because of the AngleVectors argument order at 10779, "left" is the up vector and "right" (negated) is actual left. If front blocked: both sides clear -> strafe by sign of dot(toEnemy, right) (sign inverted, see bugs) or random if no enemy; one side clear -> strafe there; none clear -> no enemy: EA_Jump if noJumpTime < level.time && lastObstacleTime < level.time-2000 (sets noJumpTime +1000, lastObstacleTime now); else EA_MoveBack if noRetreatTime < level.time (sets +500). Returns qtrue whenever front is blocked.

NewBotAI_GetMovement ordered outline:

| # | Lines | Step | Gate | Traces |
|---|---|---|---|---|
| 1 | 10861 | return if no enemy / no enemy client | | 0 |
| 2 | 10866-10870 | Bot_UpdateEnemySwingMemory; lastEnemyPos = enemy origin; lastEnemyTime = level.time | always | 0 |
| 3 | 10873-10875 | Bot_ClearForcedMovement | weapon saber | 0 |
| 4 | 10882-10938 | SABER CLOSE PATH, always returns | weapon saber && dist<=100 | |
| 4a | 10884-10889 | Bot_CheckAndInteractWithObstacle; on qtrue set lastObstacleTime, return | noUseTime < level.time && lastObstacleTime < level.time-3000 | 1-3 |
| 4b | 10892-10914 | dist>90: probe 32u fwd; clear -> forward, else random strafe | | 1 |
| 4c | 10915-10936 | dist<80: probe 32u back; clear -> back, else Bot_EvadeSwingArc | | 1 |
| 4d | - | 80<=dist<=90: nothing | | 0 |
| 5 | 10943-10948 | Obstacle fn, return on qtrue | same timers && dist>200 | 1-3 |
| 6 | 10951 | Bot_CheckMovementPaths, return if front blocked | none | 3 |
| 7 | 10956-10962 | toEnemy (flat), frontDot | | 0 |
| 8 | 10971-11007 | Dodge: if Bot_ShouldBackstepForSwing (enemy torsoTimer 61..179, dist<105): Bot_EvadeSwingArc + adaptive dir (-1 left, 1 right, 2 back; Q_irand(-1,1) fallback may give 0 = none); random jump branch unreachable (needs dist>150); return | | 0 |
| 9 | 11012-11036 | Range band: default 30..70; own hp<40: +20; enemy has saber: 85..130 (overrides hp shift); enemy hp<30: -10 | | 0 |
| 10 | 11039-11063 | Too close (dist < min-10): probe 32u back; clear -> back; else second Bot_CheckMovementPaths, else EvadeSwingArc; return | | 1 (+3) |
| 11 | 11066-11102 | Too far (dist > max-20): probe 32u fwd; clear -> forward; else second Bot_CheckMovementPaths, else diagonal toward enemy side; return | | 1 (+3) |
| 12 | 11109-11154 | Strafe burst re-roll when strafeExpireTime < level.time: chance 0.5 (0.7 vs saber, 0.8 own hp<50, 0.3 enemy hp<40, last wins); dir: enemy >45 deg off -> opposite side, else Bot_GetAdaptiveDodgeDir (may be 2 or 0); strafeExpireTime = now + Q_irand(400,800). If roll fails strafeDir=0 and timer NOT advanced (re-rolled every frame) | | 0 |
| 13 | 11157-11165 | strafeDir==1 -> right, any other non-zero (incl. 2) -> left; forward if frontDot>0.3 && dist>100 | | 0 |
| 14 | 11166-11204 | No strafe: dist>115 fwd probe 16u (unreachable), dist<105 back probe 16u then back | | 0-1 |
| 15 | 11209 | Bot_CheckRearThreat: frontDot < -0.6 -> forward and ideal yaw += 180 | | 0 |

In-band interval reaching steps 12-15 is [min-10, max-20]: [75,110] vs saber enemy (but saber-wielding bots at dist<=100 never get here, so only 100<dist<=110), [20,50] default, [40,70] low hp.

Traces per call: saber close path best 0 (dist 80..90 with obstacle gate closed), typical 2, worst 3-4 (obstacle fn 1 + probe 1; or obstacle fn 3 then return). Generic path best 3, typical 4, worst 8 (1 obstacle + 3 + 1 + 3). Cheap wins: real cooldown for the obstacle fn on failure; time-slice/cached Bot_CheckMovementPaths (e.g. every 100-200 ms, stagger by client num); drop the duplicate second call; drop 11078 (redundant with 10795).

#### (f) Bot_Execute* call status (grep of whole codemp tree)

| Function | Called? |
|---|---|
| Bot_ExecuteFeint (8795) | NEVER called (and bs->isFeinting never set true) |
| Bot_ExecutePerfectBlocking (8958) | yes, 10238 |
| Bot_ExecuteParry (9058) | yes, 9020 (practically unreachable gate) |
| Bot_ExecuteSaberDance, RushAttack, DFA, CrouchLunge, Hurricane, StyleSwitch, DelayAttack, ConvergentAttack, StaticAttack, ThreeSwingCombo, KataAttack | yes, each once from Bot_ExecuteSaberCombat cascade (10294-10419) |
| Bot_ExecuteDefensiveCounter (9599) | yes, 10446 |
| Bot_ExecuteLungeAttack (9616) | yes, 10461 |
| Bot_ExecuteSaberCombat (9948) | yes, 10545 only |

Other never-called functions in region: BotCanFeint (8709), Bot_GetStyleAdvantage (9117), NewBotAI_GetGroundDodge (10586), Bot_TrapSetup (10678), Bot_ApplyUltraInstinctAim (10715), Bot_GetMixedAttackMove (10722), Bot_ShouldPressAttack (10735).

### Region notes, lines 11205-12945

#### (a) Force-power decision (ai_main.c:11233-11882, drivers 11884-12172)

Zero traces anywhere in this block. All deciders read `bs->frame_Enemy_Vis` and `bs->frame_Enemy_Len`, which NewBotAI fills once per think (13000-13030). No `bs->` timers are used; everything is re-evaluated every combat think.

Drivers (who calls the chooser):

| Driver | Line | FP<10 branch | Early-return handlers before chooser (FP>=10) | Chooser |
|---|---|---|---|---|
| DSvDS | 11884 | GetAim, Getup, grip-react, saber-in-flight block, GetMovement, GetAttack (11887-11937) | knockdown 11942, gripped 11947, lightning active 11952, rage active 11957, grip active 11962, drain active 11967 (all return); speed 11972; saber-in-flight 11980-12008 | GetDSForcepower 12012 |
| DSvLS | 12016 | GetAim, Getup, GetMovement, GetAttack | knockdown, lightning, rage, grip, drain (return); speed | GetDSForcepower 12070 |
| LSvDS | 12074 | GetAim, Getup, grip-react, SaberThrowing, GetMovement, GetAttack | knockdown, gripped (return); speed/heal/mindtrick/protect/absorb/saberthrow handlers (no return) | GetLSForcepower 12129 |
| LSvLS | 12133 | GetAim, Getup, GetMovement, GetAttack | knockdown (return); speed/protect/absorb | GetLSForcepower 12170 |

Chooser gate in all four: `g_forcePowerDisable.integer != 163837 && != 163839` (12011, 12069, 12128, 12169). Order in every driver: GetAim -> handlers -> GetMovement -> chooser -> GetAttack.

Weights (0 = not usable):

| Power | Func:line | Hard gates (return 0) | Value |
|---|---|---|---|
| Pull | GetPull 11253 | disabled/unknown, dist>640, dist<50, not visible, enemy absorbing, FP<21 | base = max(1, ourHP - hisHP); 0.1 if enemy saber in flight; x0.2 if enemy swinging non-strong; x0.1 if we are alt-charging; x0.5 each for our absorb/protect. Returns 100 if dist<200 and enemy holds a gun (11289); if IsEnemyPullable + saber/melee + g_flipKick: 100 when hisHP<=20 and dist<250, weight*2 if knocked down, weight (LS needs dist<250 and FP>32); else "pull stun": FP*0.1 when height diff in (-20,40), dist<100, FP>=60 |
| Push | GetPush 11327 | disabled/unknown, dist>640, not visible, enemy absorbing, FP<20, we have protect on | 100 only if IsEnemyPullable, ourHP<25, dist<160, enemy has saber and enemy groundEntityNum == ENTITYNUM_NONE; else 0 |
| Drain | GetDrain 11456 | disabled/unknown, dist>512, not visible, enemy absorbing, FP<21, enemy FP==0, alt-charge >700 ms | enemy saber in flight: 70 if ourHP>40 and hisForce>10, 0 if ourHP<=40; else if ourHP<100: 120 - ourHP; else 0 |
| Grip | GetGrip 11500 | disabled/unknown, dist>256, not visible, enemy absorbing, FP<50 | if hisForce<20 and (enemy levitating/speeding/saber knocked): 100 when hisHP<52 else weight-10 (weight 100, or 90 if alt-charging); if enemy in strong swing and we are not alt-charging: ourHP - hisForce; else 0 |
| Lightning | GetLightning 11353 | disabled/unknown, not visible, dist<50, dist>1500, FP<30, dist<=80 | 100; +20 at dist 206..306; -40 if enemy HP<40 and dist<=200; +30 if our HP<50 and dist>=100; -50 if enemy knocked down; -20 with 2/11 chance (Q_irand) |
| Rage | GetRage 11424 | disabled/unknown, (weapon==WP_NONE and dist<300), FP<60 | 2; +15 if HP<50; +5 if enemy using push/pull/grip. Max 22 |
| Team Energize | GetTeamEnergize 11534 | disabled/unknown, g_gametype<GT_TEAM | sum over clients within 512 with FP<=ours and HP<=ours of (100 - theirFP)*0.5 (no team filter) |
| Absorb / Protect | GetAbsorb 6945 / GetProtect 6979 | outside region | outside region |
| Heal | GetHeal 11731 | disabled/unknown, HP>=100, FP<50 | ((FP - HP) + 101) * 0.5 |
| Telepathy | GetTelepathy 11684 | disabled/unknown, already active, not visible, dist>400, HP<70, FP<20 | 50 (HP>=90) or 25 (HP>=70); +20 dist<150 / +10 dist<250; + Q_irand(0,10) |
| Team Heal | GetTeamHeal 11749 | disabled/unknown, g_gametype<GT_TEAM | sum over same-team clients within 512 with FP<=ours, HP<=ours of HP*0.5 |
| Saber throw | GetSaberthrow 11568 | weapon!=saber, dist outside 500..2500, enemy not knocked down, FP<=40, enemy HP+armor>50 | 100 (and presses EA_Alt_Attack itself at 11583) |

Selection rule, DS (11628-11651): if/else-if chain in order push, pull, lightning, grip, drain, rage; a power is selected only if its weight is STRICTLY greater than all five others and > 0 (minWeight 0). A tie for the top weight selects nothing. Before the chain, when holding a saber with a visible enemy within SABER_ATTACK_RANGE (128, ai_main.h:71), push/pull/rage weights are zeroed (11617-11626).

Selection rule, LS (11815-11842): chain push, pull, absorb, protect, telepathy, heal. The push/pull/absorb/protect/heal tests do not include telepathyWeight, and the telepathy test (11835) omits protectWeight. In saber range push/pull/telepathy are zeroed (11804-11813).

Post-chain overrides:
- Speed (11653-11660, 11844-11851): only if nothing chosen, speed known/enabled, dist>90, enemy has Absorb active, our HP<=100 and FP>=50.
- DS 11662: `GetTeamEnergize > 0` overrides whatever was chosen (unconditional).
- LS 11854: Team Heal only if nothing chosen.
- Saber throw (11667-11678, 11860-11873): if GetSaberthrow > 0, press alt-attack again when visible and knocked down; DS requires dist 500..900, LS 500..2500.
- Fire (11680, 11878): `useTheForce && (level.framenum % 2) && enemy invulnerableTimer expired` -> trap->EA_ForcePower. The chosen power is written straight to `level.clients[bs->client].ps.fd.forcePowerSelected`.

Cost summary: O(1) arithmetic per think, plus one 32-iteration client loop in team gametypes (GetTeamEnergize always for DS, GetTeamHeal for LS only when nothing chosen). Not a perf target.

NF (12174-12305): used instead of the XvY drivers when force is fully disabled, g_flipKick is off and weapon is saber (13049/13225). Forces ps.fd.saberAnimLevel = SS_STRONG (12186). dist>=325 forward; dist<=200: jump/crouch/forward while swinging, backslash if tweak cvars allow (12214), else strafe right + attack or backpedal-jump; mid range with closing speed>=125: jump/crouch attack; else forward. No traces.

#### (b) NewBotAI_DoAloneStuff (ai_main.c:12485-12854)

Callers: NewBotAI 12993 (ScanForEnemies returned -1: every think with no target), 13023 (closest enemy not visible, last attacker invalid, not seen for 10 s), 13034 (enemy not visible and farther than 300); StandardBotAI 13827. No timer gates any call. Nothing in the function itself is throttled either; the only timers are `bs->jumpTime` (jump cooldowns 1500/2000 ms, gate the jump key only, not the traces) and `level.time % 1000 > 500` (force key 12562, Flipkick 12850).

Ordered outline:

| Step | Lines | What |
|---|---|---|
| 0 | 12486-12491 | locals; `int radiusEnts[256]`; mins/maxs = +/-(1024,1024,256) |
| 1 | 12496-12515 | shouldNavigate = no enemy, or enemy not visible, or enemy dist > 1024. If shouldNavigate and an enemy exists: `bs->frame_Enemy_Vis = 0` |
| 2 | 12517-12518 | switch to saber if selectable |
| 3 | 12521-12524 | if Speed active and FP<=0: select FP_SPEED + EA_ForcePower (toggle off) |
| 4 | 12527-12563 | FP>=10 only: Speed active -> nothing; Rage active and HP>=30 -> select Rage; Light side: Protect active -> select Protect, Absorb active -> select Absorb (i.e. toggle them off), else Heal if known, HP<100, FP>50; Dark side nothing. Key pressed only when `level.time % 1000 > 500` (12562) |
| 5 | 12568-12603 | Priority 1 waypoints: if `shouldNavigate \|\| !wpCurrent`: if no wpCurrent call GetNearestVisibleWP (12570); if wpCurrent: destination = wp origin; within BOT_WPTOUCH_DISTANCE (32) -> WPTouchRoutine, step index +/-1 via PassWayCheck or flip wpDirection; WPConstantRoutine (12601). None of WPTouchRoutine/PassWayCheck/WPConstantRoutine (1576/1288/1484) contain traces |
| 6 | 12608-12671 | Priority 2 items, only if no destination: EntitiesInBox + loop (details below) |
| 7 | 12676-12691 | Priority 3 last-seen enemy spot, only if no destination, enemy set and not visible, and `lastVisibleEnemyIndex == currentEnemy->s.number && lastVisibleEnemyIndex > level.time - 10000` (see bugs: effectively dead) |
| 8 | 12696-12763 | if destination: obstacle/fence/wall/pit box traces (12709, 12719, 12732, 12755), jump or random strafe |
| 9 | 12768-12835 | if no destination: saber -> BotFallbackNavigation (12770), return if it returns nonzero. Otherwise 48u obstacle probe (12786), fence (12796), wall (12809) or random yaw turn; EA_MoveForward; 30% chance yaw +/-90 else yaw -2..+4; return |
| 10 | 12840-12853 | destination movement: ideal_viewangles = angles to destination (+1 yaw), ~10% strafe right / ~9% strafe left, Flipkick if destination more than STEPSIZE above and time gate, EA_MoveForward |

Exactly what happens with gWPNum == 0 (no waypoint file):
1. `bs->wpCurrent` is NULL forever, so the block at 12568 is entered on every call and GetNearestVisibleWP (12570) is called every call; it returns -1 (zero iterations, zero traces). `destination` stays qfalse.
2. Step 6 therefore runs on EVERY call: `trap->EntitiesInBox(mins, maxs, radiusEnts, 256)` (12612) over a 2048 x 2048 x 512 box centred on the bot.
3. If an acceptable item is in the list: destination = `hit->s.origin` -> step 8 (2..4 box traces) -> step 10 (run straight at it).
4. Else step 7 (practically never true), then step 9: BotFallbackNavigation every call for saber bots; if it returns 0, 1..3 more box traces and blind forward movement with random yaw.

EntitiesInBox details (12609-12670):
- Box: mins/maxs offset by bs->origin (12609-12610): +/-1024 in X/Y, +/-256 in Z.
- Buffer `int radiusEnts[256]`, maxcount 256: consistent, no overflow.
- Iteration: `for (i = 0; i < numEnts; i++)` in the order the engine returns; the loop `break`s at the FIRST entity passing the filters (12669). No distance sort, no nearest selection, no visibility/PVS/trace check.
- Filters (continue): not ET_ITEM (12617); `hit->nextthink` nonzero (12620, respawning/scheduled); wrong-side enlightenment powerup (12623-12632); weapon already owned (12634-12638); ammo: blaster/powercell/metal bolts >=300, rockets >=25, every other ammo type skipped (12640-12656); health when HP>=100 (12658); armor when armor>=100 (12661); all holdables (12664). Not filtered: IT_TEAM (flags), other powerups.
- Frequency: once per DoAloneStuff call with no waypoint destination = once per think per idle bot on a waypoint-less map. With 25 bots plus items in range, each call returns and scans up to 256 entity numbers (all nearby players, movers, triggers, missiles included) before finding or not finding an item.

Traces per call:

| Path | Best | Worst | Lines |
|---|---|---|---|
| destination (waypoint or item) | 2 box (obstacle 48u clear + pit ~107u) | 4 box (obstacle, fence +24, wall +40, pit) | 12709, 12719, 12732, 12755 |
| no destination, saber, BotFallbackNavigation returns 1 with existing exploration target | 2 (1 box 32u + 1 line 300u) | 2 | 5403, 5413 |
| no destination, saber, wall or ledge ahead | 2 (when lastWallHitTime not expired) | 6 (2 + 2 box 32u + 2 line 300u) | 5403, 5413, 5424, 5428, 5439, 5447 |
| no destination, saber, needs a new exploration target | 2 + 1 box + 3 line (first attempt OK at 150u) = 6 | 2 + 12 x 7 = 86 (12 attempts x (1 box up to 400u + up to 5 ground lines 400u + 1 final line)); typical failed attempt costs 1 box trace | 5497-5514, 5733, 5758, 5787 |
| no destination, BotFallbackNavigation returned 0 or weapon not saber | +1 box 48u | +3 box 48u | 12786, 12796, 12809 |

Absolute worst for one call on a waypoint-less map: 1 EntitiesInBox + 86 (fallback target search, all fail) + 3 = 89 traces. Steady state while wandering with a valid exploration target: 1 EntitiesInBox + 2 traces. The emergency branch at 5533 (`stuckCounter > 20`) cannot be reached because stuckCounter is reset to 0 when it exceeds 5 (5381-5383).

Note BotFallbackNavigation returns 0 immediately when `currentEnemy && frame_Enemy_Vis` (5350); that happens when DoAloneStuff is reached from StandardBotAI 13827 with a visible enemy within 1024.

#### (c) NewBotAI_ScanForEnemies (ai_main.c:12856-12939)

- Called from NewBotAI 12967 every think when `g_newBotAITarget.integer < 0`. No timer.
- Early exits: current enemy is the Jedi Master -> return -1 (12874-12876). GT_JEDIMASTER with a master and we are not it: friendly fire off -> noAttackNonJM; on -> closest = 128 (12878-12887).
- Loop: `for (i = 0; i < MAX_CLIENTS; i++)` (12890), i.e. 32 slots regardless of level.numConnectedClients (the sortedClients variant is commented out at 12889/12891).
- Per-slot test order (12894): `ent && ent->inuse && PassStandardEnemyChecks(bs, ent) && BotPVSCheck(ent->client->ps.origin, bs->eye) && PassLovedOneCheck(bs, ent)`. PassStandardEnemyChecks (2063-2177, no traces) rejects non-clients, racemode, noclip, bots when g_newBotAITarget < -1, dead, !takedamage, spectators, disconnected, non-solid, self, teammates, mind-trickers beyond 64u, foreign duelists, JM rules. So InPVS runs once per live enemy client per bot per think.
- No visibility trace in the scan (comment at 12907 says so). The LOS check is done once on the winner in NewBotAI: OrgVisible at 13004, plus a second OrgVisible at 13016 for the last attacker when the winner is hidden.
- Target rule: if a client is gripping us (`forceGripEntityNum == our clientNum`) pick it and break (12896-12899). Otherwise score = distance(eye -> their origin) * normalizedHealth, where normalizedHealth = 0.25 + (hp-1)*0.75/99, plus (100 - ourHealth)*0.005, capped at 1 (12895-12909). Jedi Master scores 1 (12912). Lowest score wins. If the bot is mind-tricked by the candidate, it only counts when score < 256 or the candidate's dangerTime is within 100 ms (12917-12918).
- Hysteresis (`hasEnemyDist - 128`, 12919/12928) is dead code: hasEnemyDist is always 0 (12862, 12871), so the target can flip every think.
- Returns client index or -1. FOV is ignored.
- g_newBotAITarget handling (in NewBotAI, 12966-12978, just outside region): < 0 -> scan; value < -1 additionally makes PassStandardEnemyChecks ignore bots (2081); >= 0 -> that client number is used directly with only a connected check, and the OrgVisible test at 13004 is short-circuited (`g_newBotAITarget.integer >= 0` forces frame_Enemy_Vis = 1). No alive/team/spectator check for a forced target.

Scaling: 25 FFA bots = 25 x 32 loop iterations and up to 25 x 24 = 600 trap->InPVS per round of thinks, plus 25..50 OrgVisible line traces in NewBotAI.

#### (d) CapRoute / Tribes / StrafeJump

| Func | Lines | Summary |
|---|---|---|
| NewBotAI_CapRoute | 12308-12385 | Reached only when g_movementStyle == MV_TRIBES (12980-12988). Returns qfalse unless GT_CTF and `pers.activeCapRoute` set. Reads `redRouteList/blueRouteList[activeCapRoute-1].pos[activeCapRouteSequence]`, increments the sequence; at end of route clears the route and G_Kill()s the bot. Presses ACTION_SKI, yaw = velocity direction, fakes jetting on a 500 ms toggle. One player-box JP_Trace with CONTENTS_BODY only (12369) from origin to the next point: if anything is hit the route is dropped; otherwise ps.velocity is overwritten with (newSpot - origin) * 40 (12376-12377). Returns qtrue, which ends the think. |
| NewBotAI_Tribes | 12387-12450 | Reached at 13042 when MV_TRIBES and g_startingItems includes HI_JETPACK, with an enemy. Holds jump while the jetpack is flaming/active or FP > 98, presses ACTION_SKI, then calls the entire StandardBotAI (12445), then NewBotAI_GetAim and NewBotAI_GetAttack. Cost = StandardBotAI + GetAim + GetAttack. |
| NewBotAI_StrafeJump | 12452-12483 | Never called. GetAim, Flipkick, forward, and left/right alternating on `level.time % 1000 > 500`. |

## 8. Bot cvars and related engine facts

The bot_state_t field table, grouped by purpose with throttle timers flagged, is in the region notes for lines 1-2700 above.

### G (cont.). Bot cvars, JP_Trace, BotAIStartFrame caller

All paths relative to `codemp/`. Line numbers are HEAD of branch `claude/korriban-bot-perf`. "ai_main.c uses" lists every `.integer/.value` reference found by grep.

### C.1 bot_* cvars registered by the game module in bot code

| Name | Default | Flags | Registered | Used in ai_main.c (lines) | Controls |
|---|---|---|---|---|---|
| bot_forcepowers | 1 | CVAR_CHEAT | game/ai_main.c:15029 (BotAISetup), Cvar_Update once at 15051 only | 14894 | Gate for the stock force-power usage block at the end of StandardBotAI (`bot_forcepowers && !g_forcePowerDisable`). Not refreshed per frame. |
| bot_forgimmick | 0 | CVAR_CHEAT | ai_main.c:15030; updated 14956 | 13438, 13445, 13450, 13460 | Debug gimmick mode in StandardBotAI (bot stands and uses force on player). |
| bot_honorableduelacceptance | 0 | CVAR_ARCHIVE | ai_main.c:15031; updated 14957 | 13745 | Bots accept private-duel challenges (with `g_privateDuel`, 13749). Block is marked Niksata Edit (13745-13802). |
| bot_pvstype | 1 | CVAR_CHEAT | ai_main.c:15032; updated 14953 | 1219 | BotPVSCheck: on RMG maps use a 1024u distance check instead of trap->InPVS. |
| bot_getinthecarrr | 0 | 0 | ai_main.c:15034, only `#ifndef FINAL_BUILD`; updated 14959 | 13382, 13390, 13394, 13411 | Debug: bots try to board vehicles (StandardBotAI). |
| bot_nogoals | 0 | CVAR_CHEAT | ai_main.c:15038, only `#ifdef _DEBUG`; updated 3955 | 3957 | Debug: GetIdealDestination returns without picking goals. |
| bot_debugmessages | 0 | CVAR_CHEAT | ai_main.c:15039, only `#ifdef _DEBUG`; updated 827 | 829 | Debug: prints "Single AI frametime: %i" per bot think (see C.5). |
| bot_attachments | 1 | 0 | ai_main.c:15042; updated 14955 | 2419, 6073, 6134 | Enables the "loved one"/attachment logic (PassLovedOneCheck, GetLoveLevel, BotLovedOneDied). |
| bot_camp | 1 | 0 | ai_main.c:15043; updated 14954 | 1606 | Allows camping at WPFLAG_SNIPEORCAMP waypoints (WPTouchRoutine). |
| bot_wp_info | 1 | 0 | ai_main.c:15045; updated 14969 when gBotEdit | none (ai_wpnav.c:315) | Waypoint editor: show info for nearest waypoint. |
| bot_wp_edit | 0 | CVAR_CHEAT | ai_main.c:15046; updated ai_wpnav.c:3315 | none (ai_wpnav.c:3317 sets gBotEdit) | Waypoint edit mode; when on, BotAIStartFrame calls BotWaypointRender every frame (ai_main.c:14967-14971). |
| bot_wp_clearweight | 1 | 0 | ai_main.c:15047; updated ai_wpnav.c:1877 | none (ai_wpnav.c:1879) | Clear waypoint weights when recalculating paths. |
| bot_wp_distconnect | 1 | 0 | ai_main.c:15048; updated ai_wpnav.c:1501 | none (ai_wpnav.c:1514) | Waypoint auto-connect by distance. |
| bot_wp_visconnect | 1 | 0 | ai_main.c:15049; updated ai_wpnav.c:1502 | none (ai_wpnav.c:1514) | Waypoint auto-connect by visibility. |
| bot_normgpath | 1 | CVAR_CHEAT | game/ai_wpnav.c:3292, only when `RMG.integer` (declared ai_main.c:83) | none (ai_wpnav.c:3296) | 0 = auto-generate waypoint path on random (RMG) maps. |
| bot_minplayers | 0 | CVAR_SERVERINFO | game/g_bot.c:1396 (also engine Cvar_Get server/sv_bot.cpp:681) | none (g_bot.c:653-669) | Auto add/remove bots to keep this many players (G_CheckMinimumPlayers). |

### C.2 jaPRO / TaystJK bot cvars from the XCVAR table (game/g_xcvar.h, section "//JAPRO BOTS" line 346)

| Name | Default | Flags | Registered | Used in ai_main.c (lines) | Controls |
|---|---|---|---|---|---|
| g_newBotAI | 0 | CVAR_ARCHIVE (announce) | g_xcvar.h:349 | 531, 820, 5873 | 1 = `BotAI` dispatches to jaPRO `NewBotAI` instead of `StandardBotAI` (820-823); raises view-angle maxchange to 1800 (531); forces saber selection in BotSelectIdealWeapon (5873). Also g_cmds.c:8302. |
| g_newBotAITarget | -1 | CVAR_ARCHIVE | g_xcvar.h:350 | 2081, 12966, 12970, 13004 | <0: NewBotAI scans for enemies itself; >=0: forced target client number, visibility test skipped (13004); < -1: bots never target other bots (PassStandardEnemyChecks 2081). |
| bot_strafeOffset | 0 | CVAR_ARCHIVE (announce) | g_xcvar.h:348 | 6772 | Added to optimal strafe angle in NewBotAI_GetStrafeAim. Also bg_pmove.c:15507, bg_slidemove.c:829-830. |
| bot_nochat | 0 | CVAR_ARCHIVE (announce) | g_xcvar.h:347 (engine also Cvar_Get server/sv_bot.cpp:675) | none (ai_util.c:361) | Disables bot chat. |
| bot_maxbots | 0 | CVAR_ARCHIVE | g_xcvar.h:351 | none (g_bot.c:666, 670, 1155) | Cap on number of bots for bot_minplayers and addbot. |
| bot_team | 0 | CVAR_ARCHIVE (announce) | g_xcvar.h:352 | none (g_bot.c:1020, 1022; g_client.c:3170, 3174) | Forces team for added bots. |
| bot_s1..bot_s6 | 16, 24, 48, 0.5, 0, 64 | CVAR_ARCHIVE (announce) | g_xcvar.h:356-361 ("//testing") | none | No `.integer/.value` reference found in codemp/game or cgame .c files (unused test cvars). |

Requested names that do NOT exist as game cvars: there is no `g_newBotAI*` cvar other than the two above.

### C.3 Engine-side bot cvars (server/sv_bot.cpp SV_BotInitCvars, Cvar_Get)

| Name | Default | Flags | Registered | Used by ai_main.c | Notes |
|---|---|---|---|---|---|
| bot_enable | 1 | CVAR_LATCH (sv_game.cpp:140), 0 (sv_bot.cpp:656) | server/sv_game.cpp:140, server/sv_bot.cpp:656 | no | Master switch; `SV_BotFrame` returns if 0 (sv_bot.cpp:606). Read by game via Cvar_VariableIntegerValue at g_bot.c:1142, 1324; g_main.c:461, 669. |
| bot_thinktime | 100 | CVAR_CHEAT | server/sv_bot.cpp:668 | **no** | Not read by the game module. ai_main.c hard-codes `#define BOT_THINK_TIME 0` (line 60), used at 858, 14978-14987: thinktime = elapsed_time, so every bot runs `BotAI()` on every BotAIStartFrame call. |
| bot_pause | 0 | CVAR_CHEAT | sv_bot.cpp:676 | no | Registered only. |
| bot_developer, bot_debug, bot_maxdebugpolys, bot_groundonly, bot_reachability, bot_visualizejumppads, bot_forceclustering, bot_forcereachability, bot_forcewrite, bot_aasoptimize, bot_saveroutingcache, bot_reloadcharacters, bot_testichat, bot_testrchat, bot_testsolid, bot_testclusters, bot_fastchat, bot_report, bot_grapple, bot_rocketjump, bot_challenge, bot_interbreedchar/bots/cycle/write, bot_highlightarea | various | mostly 0 / CVAR_CHEAT | sv_bot.cpp:255-263, 657-685 | no | Q3 botlib/AAS legacy cvars; not referenced by ai_main.c. |

### C.4 Non-bot cvars referenced inside ai_main.c

All registered through the XCVAR table in game/g_xcvar.h.

| Name | Default | Flags | g_xcvar.h line | Used in ai_main.c (lines) | What the bot code uses it for |
|---|---|---|---|---|---|
| g_forcePowerDisable | 0 | SERVERINFO, ARCHIVE | 100 | 6948, 6984, 7040, 7092, 7098, 7110, 7116, 11257, 11330, 11358, 11430, 11460, 11504, 11538, 11653, 11691, 11736, 11753, 11844, 12011, 12069, 12128, 12169, 13049, 13598, 14894 (33 refs) | Per-power bitmask checks in every NewBotAI_Get* force weight; values 163837/163839 (all powers off) select the no-force `NewBotAI_NF` path (13049, 13598). |
| g_tweakWeapons | 0 | ARCHIVE | 227 | 4706-4756, 4791-4796, 7658, 7696, 7707, 7766, 7814, 7880, 7920, 7923, 10521, 10559 (28 refs) | Projectile speed per weapon (G_NewBotAIGetProjectileSpeed), weapon choice (NewBotAI_GetWeapon), WT_TRIBES attack path. |
| g_projectileVelocityScale | 1 | ARCHIVE | 231 | 4763 | Scales projectile speed for aim leading. |
| g_projectileInheritance | 0 | ARCHIVE | 233 | 4782, 4785 | Aim leading with inherited shooter velocity. |
| g_gravity | 800 | none | 109 | 4812 | Projectile drop in G_NewBotAIAimLeading. |
| sv_fps | 40 | ARCHIVE, SERVERINFO | 177 | 6902, 6905 | NewBotAI_GetTimeToInRange: tick = 1000/sv_fps; simulation loop runs `sv_fps * maxTime * 0.001` iterations. |
| RMG | 0 | none | 175 | 1164, 1219, 1244, 1269, 1295, 1350, 13849, 13965, 14030, 14041, 14089, 14118 | Random-map mode: alternate waypoint search (GetNearestVisibleWP etc.) and RMG navigation branches in StandardBotAI. Also 11 refs in ai_wpnav.c. |
| g_newBotAI / g_newBotAITarget / bot_strafeOffset | | | 349 / 350 / 348 | see C.2 | |
| g_flipKick | 0 | ARCHIVE | 238 | 11294, 13049, 13598 | Allows pull-to-kick weighting and full force-fight path. |
| g_tweakSaber | 0 | ARCHIVE | 193 | 12214 (x2) | ST_EASYBACKSLASH / ST_SPINBACKSLASH in NewBotAI_NF. |
| g_backslashDamageScale | 1 | ARCHIVE | 195 | 12214 (x2) | Backslash attempt threshold in NewBotAI_NF. |
| g_movementStyle | 1 | ARCHIVE | 242 | 12980, 13041 | MV_TRIBES -> NewBotAI_Tribes / cap routes. |
| g_startingItems | 0 | ARCHIVE | 283 | 13041 | Jetpack bit for the Tribes path. |
| g_friendlyFire | 0 | ARCHIVE | 105 | 2162, 12880 | Team-mate filtering in enemy checks / NewBotAI_ScanForEnemies. |
| g_gametype | 0 | SERVERINFO, LATCH | 108 | 11542, 11757 | Team-energize / team-heal weights return 0 below GT_TEAM. |
| g_privateDuel | 1 | ARCHIVE | 128 | 13749 | Duel acceptance block. |
| g_speed | 250 | none | 156 | 12455 | Appears only inside a commented-out line. |
| g_gunGame, g_tweakForce | | | 235, 215 | none at HEAD | Were used by jaPRO code in NewBotAI_GetAttack / GetDSForcepower; removed by 87e4f14fc. |

Owner-added cvars (87e4f14fc) and where they are actually read:

| Name | Default | Flags | g_xcvar.h | ai_main.c | Read at |
|---|---|---|---|---|---|
| g_lightningBlockEnabled | 0 | ARCHIVE | 222 | not used (only `extern` in ai_main.h:498) | game/w_saber.c:10093 |
| g_lightningBlockCost | 5 | ARCHIVE | 223 | not used (extern ai_main.h:499) | game/w_saber.c:10104 |
| g_lightningBlockReduction | 0.7 | ARCHIVE | 224 | not used (extern ai_main.h:500) | no `.value/.integer` reference found in game/*.c |
| g_saberAlwaysBlock | 0 | ARCHIVE | 207 | not used | game/w_saber.c:445, 453 |
| japp_saberTweaks | 0 | ARCHIVE | 208 | not used | game/w_saber.c:9995 |
| japp_saberBlockChanceMax / Min / Scale, japp_saberBlockStanceParity | 0.75 / 0.0 / 0.5 / 3.0 | none | 209-212 | not used | game/w_saber.c (block-chance model after 9995) |

Summary: the owner's AI has **no tuning cvars of its own**. All ranges, cooldowns and probabilities in the 71 new functions are hard-coded constants; none of the per-frame trace work can be turned off by cvar. Cvar_Update for the vmCvar_t bot cvars happens once per second (gUpdateVars, ai_main.c:14951-14962).

### C.5 JP_Trace

Defined at **game/g_syscalls.c:259**:

```c
void JP_Trace( trace_t *results, const vec3_t start, const vec3_t mins, const vec3_t maxs, const vec3_t end, int passEntityNum, int contentmask, int capsule, int traceFlags, int useLod ) {
	BeginHack(passEntityNum);
	trap->Trace( results, start, mins, maxs, end, passEntityNum, contentmask, capsule, traceFlags, useLod );
	EndHack(passEntityNum);
}
```

What it does beyond `trap->Trace` (BeginHack ~g_syscalls.c:140-204, EndHack 211-256, both static inline):

1. Before the trace it loops over **all `level.num_entities`** (not just clients) and temporarily rewrites `r.ownerNum` so that entities the tracer must not collide with (duelers, racemode players) are skipped; after the trace a second full loop restores `r.ownerNum` from a `saved[]` array.
2. Three cases keyed on `passEntityNum`: tracer is in a duel; tracer is in racemode; otherwise (the normal bot case) every in-use client entity with `duelInProgress` or `sess.raceMode` is made non-solid to the tracer.
3. The duel and racemode branches run `Q_stricmp(classname, "laserTrap"/"detpack"/"func_door"/"func_plat")` on matching ET_GENERAL / ET_MOVER entities, in both loops.
4. The default branch tests `g_entities[i].inuse && g_entities[i].client && (duelInProgress || raceMode)` for every entity, twice per trace.
5. Net cost per JP_Trace = 1 engine trace + 2 x O(level.num_entities) passes. ai_main.c has 68 JP_Trace call sites at HEAD (37 before the owner's commit) versus 15 direct `trap->Trace` calls.

### C.6 Who calls BotAIStartFrame, and timing code

| Step | File:line |
|---|---|
| Definition | game/ai_main.c:14913 `int BotAIStartFrame(int time)` (prototype game/g_local.h:2052) |
| Game export | game/g_main.c:4606 `ge.BotAIStartFrame = BotAIStartFrame;` (legacy vmMain dispatch g_main.c:4691) |
| Engine wrapper | server/sv_gameapi.cpp:140-145 `GVM_BotAIStartFrame` |
| Caller | server/sv_bot.cpp:605-612 `SV_BotFrame(int time)` (returns early if `!bot_enable` or `!svs.gameStarted`) |
| SV_BotFrame callers | server/sv_main.cpp:1247 (listen server: once per SV_Frame, before the sim loop, `sv.time + sv.timeResidual`); server/sv_main.cpp:1290 (dedicated: once per SV_Frame, before `GVM_RunFrame` loop); server/sv_init.cpp:634 and 694 (map spawn) |

Inside BotAIStartFrame each bot gets `BotAI()` on every call (BOT_THINK_TIME is 0, ai_main.c:60, 14986-14987) plus `BotUpdateInput` + `trap->BotUserCommand` (15012-15023).

Profiling / timing code that exists:

| Location | What | Active? |
|---|---|---|
| game/ai_main.c:817-831 | `start/end = trap->Milliseconds()` around `NewBotAI/StandardBotAI`; `Com_Printf("Single AI frametime: %i\n")` when `bot_debugmessages` | Only in `_DEBUG` builds (whole block is `#ifdef _DEBUG`; the cvar is also only registered in _DEBUG). 1 ms resolution, per bot. |
| game/ai_main.c:14916-14922 | Owner's "timeout protection" using `trap->Milliseconds()` | Always active. Not a profiler: it makes BotAIStartFrame return early once per ~100 ms wall-clock (see G.5); its warning goes to `BotAI_Print`, an empty stub (ai_main.c:356). |
| server/sv_main.cpp:1281-1307 | `com_speeds`: `time_game = Sys_Milliseconds() - startTime` | Measures SV_CalcPings + SV_BotFrame (dedicated call at 1290) + GVM_RunFrame together. On a listen server the SV_BotFrame call at 1247 is before `startTime` and is not included. |

There is no per-function or per-trace profiling, no trace counter, and no bot-AI-specific timing in release builds.

## 9. Fork owner additions versus stock JKA / jaPRO code

### G. Fork owner additions vs stock code (codemp/game/ai_main.c)

### G.1 History and working-tree state

Branch `claude/korriban-bot-perf`. `git log --follow -- codemp/game/ai_main.c` (newest first):

| Commit | Date | Author | Subject | ai_main.c +/- | Whole commit |
|---|---|---|---|---|---|
| f63de193e | 2026-11-08 | jdmter1991 | Update ai_main.c | +2 / -4 | 1 file |
| 42d86f339 | 2026-10-07 | jdmter1991 | Update ai_main.c | +37 / -37 | 1 file |
| 87e4f14fc | 2026-08-08 | jdmter1991 | TaystJK_AI | +5930 / -1587 (ai_main.h +207 / -35) | 108 files, +10368 / -2409 |
| f1257e1b1 | 2025-10-01 | tayst | Strafehelper tweaks (#260) | last upstream TaystJK commit touching the file | |
| 829a59ad0 ... fd60c90af | 2024-03..05 | tayst / videoP / taysta | jaPRO bot cap-route AI, crash fixes, warnings | upstream | |

- No newer commit touches ai_main.c: f63de193e is the top of the file's history. 47 commits exist in `f63de193e..HEAD`; none of them touch `codemp/game/` at all.
- Working tree: `git status` = "nothing to commit, working tree clean"; `git diff --stat` is empty. **No uncommitted changes.**
- File size: 10,752 lines before 87e4f14fc; 15,093 lines at HEAD (ai_main.h 595 lines).
- Caveat on the +5930/-1587 numstat: 87e4f14fc also re-formatted the entire file (`type *x` -> `type* x`, spaces around operators, re-indented comments). `git diff -w` still reports +5480 / -1133, but after stripping all whitespace, `//` comments and lone braces per function, only **27 pre-existing functions have real code changes** (table G.4); every other pre-existing function differs in formatting only.
- Owner marker comments: `grep -c "Niksata" ai_main.c` = **162 lines** (all are `// Niksata Edit` variants). Other files at HEAD: ai_main.h 56, w_saber.c 20, g_client.c 10, bg_panimate.c 10, g_xcvar.h 9, bg_pmove.c 8, bg_saberLoad.c 7, bg_saber.c 4, g_cmds.c 4, ai_util.c 2, g_bot.c 2, w_force.c 2. The markers are NOT exhaustive (many of the 71 new functions carry no marker), so the function tables below are the reliable inventory.

### G.2 The three layers in ai_main.c

| Layer | Origin | Identifying functions | Entry point |
|---|---|---|---|
| Raven stock (JKA SDK / OpenJK) | Raven | `StandardBotAI`, `BotAI`, `BotAIStartFrame`, `BotAISetup*`, `BotTrace_Strafe/Jump/Duck`, `WPTouchRoutine`, `WPConstantRoutine`, `GetIdealDestination`, `CTFTakesPriority`, `SiegeTakesPriority`, `CombatBotAI`, `MeleeCombatHandling`, `SaberCombatHandling` (removed by owner), `StrafeTracing`, `BotFallbackNavigation`, `BotSelectIdealWeapon`, `Commander*AI` | `BotAI()` -> `StandardBotAI()` when `g_newBotAI 0` (ai_main.c:820-823) |
| jaPRO "NewBotAI" (present before 87e4f14fc) | jaPRO (videoP), via TaystJK | 47 functions prefixed `NewBotAI` (incl. `NewBotAI` itself, `NewBotAI_GetAim/GetStrafeAim/GetMovement/GetAttack/GetWeapon/GetTribesWeapon/DSvDS/DSvLS/LSvDS/LSvLS/NF/CapRoute/Tribes/StrafeJump/DoAloneStuff/ScanForEnemies`, force weights `GetPull/GetPush/GetDrain/GetGrip/GetHeal/GetAbsorb/GetProtect/...`) plus `G_NewBotAIGetProjectileSpeed`, `G_NewBotAIAimLeading`, `Bot_SetForcedMovement`, `BS_GroundDistance` | `BotAI()` -> `NewBotAI()` when `g_newBotAI 1` |
| Fork owner (jdmter1991, "Niksata Edit") | 87e4f14fc, 42d86f339, f63de193e | 71 new functions (G.3): `Bot_Execute*` saber system, `Bot*Predict*`, `Bot*Attack*` timing, exploration helpers, 6 new `NewBotAI_*` force functions | Called from both `NewBotAI()` and `StandardBotAI()` |

Layer mixing introduced by the owner: stock `StandardBotAI` now calls jaPRO/owner code directly: `NewBotAI_LSvLS/DSvLS/LSvDS/DSvDS` at ai_main.c:13602-13610, `NewBotAI_DoAloneStuff` at 13827, `NewBotAI_GetAttack` at 14186, and the owner saber-timing / movement functions in 14241-14661. So `g_newBotAI 0` no longer means "pure Raven AI".

### G.3 New functions added by the owner

All 71 were added in 87e4f14fc; 42d86f339 and f63de193e add none.
Removed by owner: `SaberCombatHandling` (Raven stock saber logic).
Outside ai_main.c: `Bot_UpdateEnemySwingMemory` in codemp/game/ai_util.c:898 (called from ai_main.c:10227 and 10866). `Bot_ShouldParry` is declared at ai_main.h:466 but has no definition in ai_main.c / ai_util.c.

| Function | Line in HEAD ai_main.c | Length (lines up to next function) |
|---|---|---|
| ValidBotClient | 145 | 8 |
| SmartExploration | 5559 | 25 |
| FollowGroundContours | 5584 | 68 |
| ExpandingSpiralSearch | 5652 | 29 |
| MoveTowardLastWaypoint | 5681 | 44 |
| IsPositionReachable | 5725 | 73 |
| NewBotAI_Lightning | 7200 | 46 |
| NewBotAI_MindTrick | 7256 | 18 |
| NewBotAI_Healing | 7391 | 15 |
| BotCanHitEnemy | 8008 | 44 |
| BotShouldAttack | 8052 | 18 |
| BotPredictEnemyPosition | 8070 | 48 |
| BotGetPredictionTime | 8118 | 18 |
| BotAnalyzeMovementPattern | 8136 | 48 |
| BotPredictStrafingMovement | 8184 | 32 |
| BotPredictJumpingMovement | 8216 | 35 |
| BotPredictRetreatingMovement | 8251 | 23 |
| BotPredictChargingMovement | 8274 | 24 |
| BotCanAttackNow | 8298 | 27 |
| BotExecuteAttack | 8325 | 22 |
| BotGetAttackDelay | 8347 | 41 |
| BotGetCurrentAttackType | 8388 | 18 |
| BotDynamicCombatMovement | 8406 | 46 |
| BotGetOptimalCombatDistance | 8452 | 30 |
| BotShouldStrafeInCombat | 8482 | 23 |
| BotCombatStrafe | 8505 | 45 |
| BotSelectStrafeDirection | 8550 | 38 |
| BotShouldAttackNow | 8588 | 26 |
| BotUpdateAttackTiming | 8614 | 21 |
| BotUpdateDynamicMovement | 8635 | 18 |
| BotMovementDuringAttack | 8653 | 30 |
| BotEnemyInRecovery | 8683 | 26 |
| BotCanFeint | 8709 | 31 |
| BotEnemySwinging | 8740 | 19 |
| BotEnemyVulnerable | 8759 | 16 |
| TAB_MoveforAttackQuad | 8775 | 20 |
| Bot_ExecuteFeint | 8795 | 51 |
| Bot_AnalyzeEnemyAttack | 8846 | 112 |
| Bot_ExecutePerfectBlocking | 8958 | 100 |
| Bot_ExecuteParry | 9058 | 47 |
| Bot_InitPerfectBlocking | 9105 | 12 |
| Bot_GetStyleAdvantage | 9117 | 57 |
| Bot_SelectOptimalSaberStyle | 9174 | 186 |
| Bot_ExecuteSaberDance | 9360 | 22 |
| Bot_ExecuteRushAttack | 9382 | 13 |
| Bot_ExecuteDFA | 9395 | 29 |
| Bot_ExecuteCrouchLunge | 9424 | 15 |
| Bot_ExecuteHurricane | 9439 | 19 |
| Bot_ExecuteStyleSwitch | 9458 | 22 |
| Bot_ExecuteDelayAttack | 9480 | 25 |
| Bot_ExecuteConvergentAttack | 9505 | 28 |
| Bot_ExecuteStaticAttack | 9533 | 22 |
| Bot_ExecuteThreeSwingCombo | 9555 | 44 |
| Bot_ExecuteDefensiveCounter | 9599 | 17 |
| Bot_ExecuteLungeAttack | 9616 | 27 |
| Bot_ExecuteKataAttack | 9643 | 37 |
| Bot_CheckAndInteractWithObstacle | 9680 | 268 |
| Bot_ExecuteSaberCombat | 9948 | 565 |
| Bot_ClearForcedMovement | 10604 | 13 |
| Bot_GetAdaptiveDodgeDir | 10617 | 61 |
| Bot_TrapSetup | 10678 | 14 |
| Bot_ShouldBackstepForSwing | 10692 | 23 |
| Bot_ApplyUltraInstinctAim | 10715 | 7 |
| Bot_GetMixedAttackMove | 10722 | 13 |
| Bot_ShouldPressAttack | 10735 | 15 |
| Bot_EvadeSwingArc | 10750 | 14 |
| Bot_CheckRearThreat | 10764 | 11 |
| Bot_CheckMovementPaths | 10775 | 85 |
| NewBotAI_GetLightning | 11353 | 71 |
| NewBotAI_GetRage | 11424 | 32 |
| NewBotAI_GetTelepathy | 11684 | 47 |

Largest: `Bot_ExecuteSaberCombat` (565 lines, 9948), `Bot_CheckAndInteractWithObstacle` (268, 9680), `Bot_SelectOptimalSaberStyle` (186, 9174), `Bot_AnalyzeEnemyAttack` (112, 8846), `Bot_ExecutePerfectBlocking` (100, 8958), `Bot_CheckMovementPaths` (85, 10775), `IsPositionReachable` (73, 5725), `NewBotAI_GetLightning` (71, 11353), `FollowGroundContours` (68, 5584).

### G.4 Pre-existing functions with real (non-formatting) changes in 87e4f14fc

"+/-" = changed statements after stripping whitespace, comments and lone braces (87e4f14fc~1 vs HEAD).

| Function (HEAD line) | Layer | +/- | What changed |
|---|---|---|---|
| BotInputToUserCommand (561) | Raven | +3/-2 | Vertical move component zeroed: `u = fabs(forward[2])*bi->dir[2]` replaced by `u = 0`; crouch branch braced. |
| BotAI (740) | Raven | +14/-4 | Added client-index / botstate / entity guards that call `BotAI_Print` (an empty stub, ai_main.c:356). Dispatch `g_newBotAI ? NewBotAI : StandardBotAI` unchanged (820-823). |
| BotAISetupClient (889) | Raven | +41/-4 | Bounds/entity/alloc checks; calls `Bot_InitPerfectBlocking`; zero-initialises ~28 new bot_state_t fields (swing memory, forced movement, attack timing, strafe, kata, enemy velocity history). |
| BotAIShutdownClient (1012) | Raven | +5/-0 | Index and inuse guards. |
| BotTrace_Jump (1762) | Raven | +45/-30 | Rewritten. Was 2 JP_Trace (body + head height). Now up to 6 box JP_Traces per call: 64u obstacle + clearance, 128u gap probe + clearance, and a 48u/80u combat-jump pair when enemy visible; sets `bs->jumpTime` +1500..2000 ms; early-out when `jumpTime > level.time+500`. `dist = VectorLength(forward)` is computed after `VectorNormalize(forward)`. |
| BotTrace_Duck (1868) | Raven | +79/-0 | Added in front of the stock duck traces: 4 ledge-probe line JP_Traces, 4 wall-probe box JP_Traces, 1 wall-height trace, 1 256u ground-distance trace, 2 above/forward traces (up to ~12 extra traces per call). Returns 0 near ledges / walls / when high above ground. |
| CombatBotAI (5183) | Raven | +4/-0 | Only 4 forward declarations of the exploration helpers inserted. |
| BotFallbackNavigation (5336) | Raven | +124/-20 | Rewritten from "1 trace, walk forward or turn randomly" into an exploration state machine with per-client static arrays (explorationTarget, stuckCounter, lastPosition, lastWallHitTime, lastMovementDirection). Per call: 1 forward box trace + 1 ledge line trace; on wall/ledge +2 box +2 ledge traces; with no target, up to 12 random candidates each tested by `IsPositionReachable`. Return semantics changed (enemy visible returns 0; was 2). |
| StrafeTracing (6201) | Raven | +27/-11 | Returns immediately on 70% of calls (`Q_irand(1,10) > 3`); adds 2 box JP_Traces (left/right 32u) to pick the freer side; `meleeStrafeDisable` shortened from 500-1500 ms to 100-300 ms. |
| NewBotAI_Getup (7013) | jaPRO | +2/-1 | Rage-on-getup block commented out. |
| NewBotAI_Speeding (7274) | jaPRO | +1/-1 | Threshold `health<50 or FP<20` -> `health<90 or FP<=100`. |
| NewBotAI_Raging (7282) | jaPRO | +22/-1 | New rage management (drop at FP<10 or health>=50; activate only <=250u, health<50, saber, FP==100). |
| NewBotAI_SaberThrowing (7406) | jaPRO | +4/-0 | Throw only inside 500-2500u. |
| NewBotAI_GetAttack (10513) | jaPRO | +8/-56 | jaPRO per-side saber attack logic deleted; saber branch is now `Bot_SelectOptimalSaberStyle(bs); Bot_ExecuteSaberCombat(bs);`. Gun fire rate: every frame if `BotEnemyVulnerable`, else every 2nd frame. |
| NewBotAI_GetMovement (10860) | jaPRO | +174/-130 | Largely rewritten: `Bot_UpdateEnemySwingMemory`, `Bot_ClearForcedMovement`, `Bot_CheckAndInteractWithObstacle` (3 s cooldown), `Bot_GetAdaptiveDodgeDir`, `Bot_EvadeSwingArc`, `Bot_CheckRearThreat`; 6 `trap->Trace` path-validation line traces; IDEAL_MIN/MAX range constants. |
| NewBotAI_GetSaberthrow (11568) | jaPRO | +4/-1 | Requires 500-2500u (was <400u). |
| NewBotAI_GetDSForcepower (11598) | jaPRO | +29/-13 | Adds lightning and rage weights (`NewBotAI_GetLightning`, `NewBotAI_GetRage`); zeroes push/pull/rage inside SABER_ATTACK_RANGE; old gun-rage block removed. |
| NewBotAI_GetLSForcepower (11784) | jaPRO | +21/-5 | Adds mind-trick weight (`NewBotAI_GetTelepathy`); zeroes push/pull/telepathy in saber range; speed/absorb conditions changed. |
| NewBotAI_DSvDS (11884) | jaPRO | +41/-0 | Low-FP (<10) path, saber-in-flight handling, lightning/rage upkeep, throw distance bands. |
| NewBotAI_DSvLS (12016) | jaPRO | +14/-0 | Low-FP path, lightning/rage upkeep. |
| NewBotAI_LSvDS (12074) | jaPRO | +17/-0 | Low-FP path, saber-in-flight, heal and mind-trick upkeep. |
| NewBotAI_LSvLS (12133) | jaPRO | +8/-0 | Low-FP path. |
| NewBotAI_NF (12174) | jaPRO | +6/-4 | Selects FP_LEVITATION + `trap_EA_ForcePower`; ground crouch commented out; a previously commented saberMove branch re-enabled. |
| NewBotAI_DoAloneStuff (12485) | jaPRO | +130/-16 | Adds waypoint navigation when enemy is absent / not visible / >1024u (`GetNearestVisibleWP`, `WPTouchRoutine`, `WPConstantRoutine`), last-seen-position chase, obstacle jumping with up to 4 box JP_Traces per call on the waypoint path and up to 3 on the `BotFallbackNavigation` path; speed/rage upkeep. |
| NewBotAI (12943) | jaPRO | +133/-21 | Removed the "any human active in last 120 s" early-out for racemode bots; out-of-sight threshold 8096 -> 300; added saber timing calls (`Bot_SelectOptimalSaberStyle`, `BotUpdateAttackTiming`, `BotUpdateDynamicMovement`, `BotShouldAttackNow`, `BotExecuteAttack`), saber throw window 450-900u, melee handling, and 4 box JP_Traces (fwd/back/left/right 32u) for combat movement. |
| StandardBotAI (13332) | Raven | +147/-146 | 22 marker lines. NewBotAI_* side fights (13594-13612); honorable-duel block (13745-13802); `NewBotAI_DoAloneStuff` (13827); saber check (14083-14086); `NewBotAI_GetAttack` (14186); aiming with `BotPredictEnemyPosition` (14241-14253); saber timing block (14264-14331); wall check (14479-14530); stuck detection/recovery (14532-14593); `BotDynamicCombatMovement` movement system (14609-14661); `skip_movement:` label (14686). |
| BotAIStartFrame (14913) | Raven | +15/-0 | See G.5. |

Formatting-only (no code change): BotTrace_Strafe, WPTouchRoutine, WPConstantRoutine, GetIdealDestination, CTFTakesPriority, SiegeTakesPriority, NewBotAI_GetAim, NewBotAI_GetStrafeAim, NewBotAI_GetWeapon, NewBotAI_CapRoute, BotAISetup, and all remaining pre-existing functions.

Trace call sites in ai_main.c: `JP_Trace` 37 before 87e4f14fc -> 68 at HEAD; direct `trap->Trace` 15 at HEAD.

### G.5 BotAIStartFrame "timeout protection" added by the owner (ai_main.c:14916-14942)

```c
static int last_frame_time = 0;
int current_time = trap->Milliseconds();
if (current_time - last_frame_time > 100) {  // 100ms timeout
    BotAI_Print(PRT_WARNING, "BotAIStartFrame: Frame timeout\n");
    last_frame_time = current_time;
    return qtrue;  // Continue but skip this frame
}
```

`last_frame_time` is assigned only inside the `if`, so the condition is true once per ~100 ms of wall-clock time regardless of load; on that call the function returns before G_CheckBotSpawn, any `BotAI()` think, `BotUpdateInput` and `trap->BotUserCommand`. All bots therefore skip roughly one server frame every 100 ms. The message is never shown because `BotAI_Print` is an empty stub (ai_main.c:356). The following `for (i < MAX_CLIENTS)` loop (14924-14942) only `continue`s and has no effect.

### G.6 Commits 2 and 3

| Commit | Functions touched | Change |
|---|---|---|
| 42d86f339 (+37/-37) | BotDynamicCombatMovement (~8452), Bot_ExecuteSaberCombat (~10126), NewBotAI_GetMovement (~11011-11065) | Tuning only: per-style `baseDistance` reduced (96->64, 64->40, 80->56, 96->72, 72->56, 88->72); SABER_RANGE / CLOSE_RANGE / LUNGE_MIN / LUNGE_MAX / SPECIAL_RANGE lowered per style; IDEAL_MIN/MAX 50/100 -> 30/70; thresholds `dist < adjustedMin - 10`, `dist > adjustedMax - 20`. |
| f63de193e (+2/-4) | Bot_ExecutePerfectBlocking (8977) | Four calls `trap->EA_MoveRight/Left/Forward/Back(bs->client, 0)` replaced by `vec3_t stopMove = {0,0,0}; trap->EA_Move(bs->client, stopMove, 0.0f);`. |

### G.7 Other codemp/game files touched by 87e4f14fc

| File | +/- | Bot-relevant content |
|---|---|---|
| ai_main.h | +207/-35 | New `botBlocking_t` struct; many new `bot_state_t` fields (feint, swing memory, strafe/forward dir timers, blocking, kata/style timers, attack timing, enemy velocity history, obstacleMemory[8], stuckCounter, jump timers); prototypes for blocking/style functions; `extern vmCvar_t g_lightningBlockEnabled/Cost/Reduction` (498-500). |
| ai_util.c | +69/-0 | `Bot_UpdateEnemySwingMemory` (898): decaying left/right/top enemy swing counters. |
| g_bot.c | +40/-0 | In G_AddBot (after line 975): reads `cp_sbRGB1/2` from bot info, converts "r,g,b" to a packed int, sets userinfo `c3`/`c4` (RGB sabers for bots). |
| g_xcvar.h | +9/-0 | `g_saberAlwaysBlock`, `japp_saberTweaks`, `japp_saberBlockChanceMax/Min/Scale`, `japp_saberBlockStanceParity` (207-212); `g_lightningBlockEnabled/Cost/Reduction` (222-224). No new bot_* cvar. |
| w_saber.c | +220/-48 | `g_saberAlwaysBlock` (445, 453), `japp_saberTweaks` block-chance model (9995), saber lightning block (`g_lightningBlockEnabled` 10093, `g_lightningBlockCost` 10104). Gameplay rules, not bot-specific. |
| w_force.c | +26/-18 | Force power tweaks (2 marker lines). |
| g_client.c | +313/-150 | `LoadModelScaleConfig` / `GetModelScale` and userinfo handling (10 marker lines). |
| g_cmds.c | +77/-59 | Misc (4 marker lines). `g_newBotAI.integer` check at g_cmds.c:8302. |
| bg_pmove.c +15/-5, bg_saber.c +7/-3, bg_panimate.c +10/-0, bg_saberLoad.c +66/-66, anims.h +3/-0, bg_public.h +1/-0 | | Saber / animation additions, not bot AI. |

The other 93 of the 108 files in 87e4f14fc are outside codemp/game.

## 10. Bugs and hazards

Each item is tagged "verified by reading" or "suspected" by the reader of that region.

### Lines 1-2700

- **[verified by reading] BotTrace_Jump is dead (CONFIRMED).** ai_main.c:1776-1778 does `VectorSubtract(traceto, origin, forward); VectorNormalize(forward); dist = VectorLength(forward);` so dist is 1.0 (or 0.0). `if (dist < 64) return 0;` at 1789-1790 is therefore always taken. All six traces (1795-1855) are unreachable, the function always returns 0, and `dist < 512` at 1843 is moot. Fix would be `dist = VectorNormalize(forward);`. Side effects today: the caller (14646-14676) always falls through to BotTrace_Duck every frame, then BotTrace_Strafe.
- **[verified by reading] If BotTrace_Jump is fixed, its cooldown will not work.** It sets `bs->jumpTime = level.time + 2000` (1815, 1837, 1858) and gates on `bs->jumpTime > level.time + 500` (1771), but the caller immediately overwrites `bs->jumpTime = level.time + 100` when it returns 1 (14646-14648). Fixing `dist` alone would add 2-6 box traces per bot per frame with no throttle.
- **[verified by reading] ScanForEnemies loops `i <= MAX_CLIENTS` (CONFIRMED), ai_main.c:2472.** Iteration i==32 touches g_entities[32] (first non-client entity; has `.client` if it is an NPC/vehicle). Consequences when that entity has a client: `BotCanHear` reads `gBotEventTracker[32]` (2285/2290), one past the MAX_CLIENTS-sized array (line 76); `PassLovedOneCheck` reads `botstates[32]` (2414) when `bs->lovednum != 0`; the function can return 32 and StandardBotAI will set currentEnemy to an NPC (13825).
- **[verified by reading] ScanForEnemies runs every frame for every bot.** The gate at 13818-13819 is `enemySeenTime < level.time || !frame_Enemy_Vis || !currentEnemy || (currentEnemy)`, which is a tautology. Combined with the next item this is the largest avoidable trace source in the region.
- **[verified by reading] ScanForEnemies spends the LOS trace before the stickiness test.** `OrgVisible` is in the condition at 2485; the `distcheck < hasEnemyDist - 128` test is inside at 2491/2503. With a current enemy, every in-FOV/heard PVS candidate is traced and then rejected, and because `closest` is only lowered on acceptance, nothing prunes later candidates. The current enemy itself is also traced here and always rejected. `!OnSameTeam` at 2474 duplicates 2124. `noAttackNonJM` (2461) is never set.
- **[verified by reading] ignore = -1 passed into JP_Trace indexes g_entities[-1].** `OrgVisible(..., -1)` at 2485 (also 13257, 14215), `CheckForFunc(..., -1)` at 13950/13957, `GetNearestVisibleWP(..., -1)` at 3514 reach `BeginHack(-1)`/`EndHack(-1)` in g_syscalls.c:166, 188, 225, 242, which evaluate `g_entities[entityNum].client` / `.inuse` without a lower-bound check. Out-of-bounds read; a non-NULL garbage `.client` would be dereferenced (`->sess.raceMode`).
- **[verified by reading] Every JP_Trace costs two O(level.num_entities) scans** (g_syscalls.c:194-202 and 248-255) on the normal non-duel path, on top of the trace. Bot traces could call trap->Trace directly when no client is dueling/racing (a per-frame cached flag).
- **[verified by reading] B_Alloc per bot is never freed and is re-done on every (re)connect (CONFIRMED).** BotAIShutdownClient (1031-1042) memsets the state but leaves `botstates[client]` pointing at it; BotAISetupClient only refuses when `botstates[client]->inuse` (898) and otherwise unconditionally allocates a new block (910), orphaning the old one. Stock code reused the block (`if (!botstates[client]) ... B_Alloc`). B_Alloc is `BG_Alloc` (ai_util.c:98-100; BOT_ZMALLOC is not defined anywhere under codemp), a bump pool of MAX_POOL_SIZE (bg_misc.c:3226-3230) with no free. Every bot add/kick/map_restart leaks sizeof(bot_state_t); pool exhaustion behaviour not determined (depends on BG_Alloc).
- **[verified by reading] Duplicated checks (CONFIRMED).** BotAI: `bs = botstates[client]; if (!bs || !bs->inuse)` at 749-753 and again 770-774. BotAIShutdownClient: identical block at 1019-1023 and 1025-1029. Harmless, dead code. BotAIStartFrame 14926-14944 is a loop whose every path is `continue` (no effect).
- **[verified by reading] swingMemory* are int but used as floats (CONFIRMED).** Declared int at ai_main.h:377-379; assigned `0.0f` at ai_main.c:967-969 (harmless); but ai_util.c:918/926/933 add 1.0 or 1.5 and 939-941 multiply by 0.88 with truncation back to int every update: 1 -> 0, 2 -> 1, a 1.5 weight adds only 1. The "total" memory therefore decays to 0 almost immediately, unlike the float recentSwingMemory* (415-417).
- **[verified by reading] `_DEBUG` timing in BotAI (817-833).** `trap->Milliseconds()` is integer milliseconds, so a single bot's AI frame nearly always prints 0 or 1; it is useless for sub-ms profiling. It measures only the NewBotAI/StandardBotAI call for one bot (excludes BotUpdateInput, the server-command drain, UpdateEventTracker). It also calls `trap->Cvar_Update(&bot_debugmessages)` per bot per frame and, when enabled, a Com_Printf per bot per frame, which perturbs the thing measured. Not compiled in release. For profiling, accumulate across all bots in BotAIStartFrame with a high-resolution timer and count traces.
- **[verified by reading] BotAIStartFrame "timeout protection" drops whole bot frames periodically (outside region, 14917-14924, affects BotAI/BotUpdateInput).** `last_frame_time` is only updated inside the `> 100` branch, so it measures time since the last skip, not since the last frame. Result: once per ~100 ms a full frame returns early with no BotAI, no BotUpdateInput and no trap->BotUserCommand for any bot (1 frame in 3 at sv_fps 20, 1 in 5 at sv_fps 40). The first call ever is also skipped.
- **[verified by reading] No think throttling at all.** `BOT_THINK_TIME` is 0 (line 60); BotScheduleBotThink (858) yields residual 0; 14997 is always true. Every bot runs full AI every server frame. The staggering machinery exists and could be reused for perf (set BOT_THINK_TIME, or stagger only the perception/trace parts).
- **[verified by reading] WPTouchRoutine indexes gWPArray out of bounds.** 1609-1618: `lastNum = index + 1` or `index - 1` then `gWPArray[lastNum]` with no bounds check; index 0 travelling forward gives gWPArray[-1]. Reached only on the camping path (isCamper && bot_camp && snipe/camp flag, 1606).
- **[verified by reading] PassWayCheck / CheckForShorterRoutes do no index bounds checks.** PassWayCheck(1290) dereferences gWPArray[windex]; caller 14054-14058 tests `gWPArray[desiredIndex]` before `desiredIndex >= 0`, and caller 12592-12593 never range-checks. CheckForShorterRoutes uses `gWPArray[newwpindex]->neighbors[i].num` unchecked (1438).
- **[verified by reading] CheckForShorterRoutes treats an unreachable neighbor as "shorter".** 1440: `checklen < bestlen - 64 || bestlen == -1`. When a neighbor's TotalTrailDistance is -1 (one-way/invalid) and bestlen > 63, `-1 < bestlen - 64` is true, so bestlen becomes -1 and bestindex the unreachable neighbor; after that `bestlen == -1` accepts every later neighbor. 1461 checks bestindex, not length. Gameplay impact (bots switching onto dead-end branches): suspected.
- **[verified by reading] WPOrgVisible issues a second full trace every frame (1137)** whenever the first is clear, only to detect ET_SPECIAL force fields. Called unconditionally per bot per frame at 13870.
- **[verified by reading] TotalTrailDistance is called every frame at 14023** (wpCurrent && wpDestination) with no timer: O(gWPNum) per bot per frame; and inside GetBestIdleGoal's gWPNum loop (3916-3924) giving O(gWPNum^2).
- **[verified by reading] GetNearestVisibleWP is retried every frame with no back-off** while `!bs->wpCurrent` (13806-13808, 12568-12570). Zero cost when gWPNum == 0, but O(gWPNum) + traces per bot per frame on waypointed maps where the bot has no visible WP within 800u.
- **[verified by reading] BotTrace_Duck inefficiencies/logic.** Traces 2010 and 2042 are the same segment and box (tracefrom_mod -> +48 z) and both run when nearWall >= 1. `fwd` is overwritten with the VIEW direction at 1922 (including pitch), so the forward check at 2046-2048 and the ledge/wall probes are relative to where the bot looks, not to `traceto`. Up to 14 traces run before the caller applies a 10% random chance and enemy-distance test (14653-14656); those cheap tests should come first.
- **[verified by reading] BotTrace_Strafe asymmetry.** 1728 offsets `from[2]` by `right[2]*16` while x/y and `to` use 32; 1741-1747 then subtract 64 on all axes. Negligible because right[2] is ~0. `DEFAULT_MINS_2` replaced by -8 (1682).
- **[verified by reading] UpdateEventTracker event lifetime is 0.5 ms.** 2345 `eventTime = level.time + 0.5`; BotCanHear 2285 tests `< level.time`. Event-based hearing works only in the frame the event is recorded (inherited from stock). BotCanHear's `default: minlen = 999999` (2313-2315) means any non-listed recent event is "heard" at unlimited range.
- **[verified by reading] BotResetState wipes personality.** 1073 clears skills, botWeaponWeights, loved[], forceinfo, chat settings, blocking state; nothing restores them (BotAILoadMap 1102-1103 only sets setupcount, which nothing reads). `skills.maxturn` becomes 0 so a reset bot cannot turn unless g_newBotAI (531). Whether any bot is ever `inuse` when BotAILoadMap runs (g_main.c:463): suspected not on normal map load, not determined for all restart paths.
- **[verified by reading] BotAI server-command loop does nothing.** 789 compares against `"cp "` after the space was replaced by NUL (784) so it can never match; all branches are empty. The loop is still needed to drain the queue, but RemoveColorEscapeSequences (787) is wasted work.
- **[verified by reading] BotAI_Print is a no-op (356)**, so every "error"/"fatal" diagnostic in setup/shutdown/BotAI is silent.
- **[verified by reading] BotInputToUserCommand presses USE at random** 40% of frames (589-592, `Q_irand(1,10) < 5`) whenever noUseTime has expired. [suspected] each press runs the game's use/TryUse trace for that client; with 25 bots this is a steady extra trace load (game-side rate limit not checked).
- **[verified by reading] BotMindTricked has no bounds check on enemyClient (303-349)** and `if (!fd)` (314) can never be true (address of a member).
- **[verified by reading] CheckForFunc `if (!fent)` (1203) can never be true.** [suspected] `strstr(fent->classname, "func_")` (1208) will crash if the hit entity has a NULL classname.
- **[verified by reading] BotChangeViewAngles: `g_newBotAI` forces maxchange = 1800 deg/s (531-533)** regardless of skill; `viewanglespeed += (viewanglespeed - desired)` (542) is the stock formula. Not a perf issue.
- **[verified by reading] ValidBotClient (145) is static and unused** (compiler warning); BotOrder, BotAIRegularUpdate, BotChangeViewAngle, BotAI_GetEntityState, BotAI_GetSnapshotEntity, BotEntityInfo, NumBots have no callers in codemp/game.
- **[verified by reading] Function-static state shared by all bots (outside region, seen while tracing callers).** StandardBotAI declares `static` lastStuckCheckPos/lastStuckCheckTime/stuckCounter/lastUnstuckDirection/lastBackupTime/consecutiveBackups at 13353-13358 and again at 14482-14483; with 25 bots these are one shared set, so stuck detection compares one bot's position with another's. Per-bot fields for this already exist unused in bot_state_t (ai_main.h:423-429).
- **[suspected] Stale gentity_t pointers.** currentEnemy/lastHurt/lastAttacked/squadLeader etc. are raw pointers into g_entities; nothing in lines 1-2700 clears them when the referenced client disconnects (PassStandardEnemyChecks re-validates currentEnemy at 13719 only).
- **[suspected] Float timers lose precision** after ~4.66 h of level.time (2^24 ms): `float` fields like wpSeenTime, beStill, duckTime (ai_main.h:242-261) compared with int level.time.

### Lines 2690-5800

- **[verified by reading] BotFallbackNavigation side-wall traces use a direction as an end point** - 5423 `VectorMA(forward, 32, right, end)` and 5427 `VectorMA(forward, -32, right, end)` build `end` from the unit `forward` vector, not `bs->origin`. `end` is a point within ~33u of world (0,0,0). The box traces at 5424/5428 therefore run from the bot to the map origin (length = bot's distance from origin, potentially thousands of units, MASK_PLAYERSOLID box = most expensive kind). `rightDistance/leftDistance = tr.fraction * 32` (5425, 5429) are meaningless, so the left/right choice at 5451-5460 is effectively random. `leftDir, rightDir` (5422) are unused.
- **[verified by reading] stuckCounter emergency branch is unreachable** - counter is incremented at 5379 and reset to 0 as soon as it exceeds 5 (5381-5383) or on any good frame (5388); it can never exceed 6, so `stuckCounter > 20` (5533) is never true. Lines 5533-5551 and the IsPositionReachable call at 5544 are dead.
- **[verified by reading] stuck detection compares against commanded, not actual, movement** - lastMovementDirection is set to the commanded moveDir toward the target (5519), so `movementAlignment` (5376) is ~1 whenever a target exists; only the `movedDistance < 10` term matters.
- **[suspected] `movedDistance < 10.0f` is per-call, not per-time** - 5367/5378 measure displacement since the previous call. At ~250 u/s a bot moves < 10u per call whenever it thinks more often than 25 times/sec, so the counter would hit 6 in six calls, clearing the target and blocking new targets for 1000ms (5384) during which the function returns 0. Depends on bot think interval (not in my region).
- **[verified by reading] BotFallbackNavigation can run twice in one frame** - 14085 and 14111 can both execute in the same StandardBotAI call (RMG only). The second call sees movedDistance == 0 (lastPosition updated at 5392) => guaranteed stuckCounter++ and doubled traces.
- **[verified by reading] No back-off on failed target search** - 5495-5515: if all 12 IsPositionReachable attempts fail, nothing is recorded; the full search (up to 84 traces) repeats on the next call. lastWallHitTime is not advanced.
- **[verified by reading] Static per-client arrays never reset** - 5342-5347 are function-local statics, so nothing outside can clear them; explorationTimer is only an init flag (5355-5357). A bot reconnecting into the same client slot, or after map_restart (if the game module is not reloaded), inherits stale explorationTarget/lastPosition/lastWallHitTime. lastWallHitTime holds an absolute level.time, so a stale value larger than the new level.time blocks wall response and target generation until time catches up. Self-heals for the target (cleared when stuck or reached).
- **[verified by reading] gWPArray[index-1] / [index+1] without bounds checks** - 4051-4058 (`tempInt = wpCurrent->index +/- 1`, then `gWPArray[tempInt]`) and 4181-4195 (`gWPArray[cWPIndex - 1]`, `gWPArray[cWPIndex + 1]`). With index 0 this reads gWPArray[-1] (out of bounds, whatever precedes the array); with index == MAX_WPARRAY_SIZE-1 (4096, q_shared.h:533) it reads past the end. Index gWPNum is in-bounds but relies on the slot being NULL. Only reachable with waypoints loaded.
- **[verified by reading] BotGetFlagBack / BotGuardFlagCarrier dereference bs->wpCurrent unchecked** - 2951 and 3017 `TotalTrailDistance(bs->wpCurrent->index, ...)`. Currently safe only because the sole call chain (GetIdealDestination -> CTFTakesPriority) returns at 3963 when wpCurrent is NULL; and `tempInt != -1` short-circuits first when gWPNum == 0. Latent crash if called from elsewhere. Same pattern at 4124, 4147, 4203 (guarded by 3963).
- **[verified by reading] ExpandingSpiralSearch uses vectoangles on an absolute position** - 5666 `vectoangles(testPos, bs->goalAngles)`; should be the direction testPos - bs->origin. Dead code today (SmartExploration is never called).
- **[suspected] FollowGroundContours rotates the wrong vector** - 5601 `RotatePointAroundVector(testDir, forward, up, angles[i])`; with the standard q_math signature (dst, dir, point, degrees) this rotates `up` around the `forward` axis, giving directions fanned in the roll plane (up/sideways), not yaw-rotated forward. Signature not re-read (definition is outside codemp/game). `forward`/`up` also include view pitch. Dead code today.
- **[verified by reading] SmartExploration, FollowGroundContours, ExpandingSpiralSearch, MoveTowardLastWaypoint are dead code** - no call site of SmartExploration in codemp/game. bs->lastKnownWaypointPos (ai_main.h:452) is never written, so MoveTowardLastWaypoint would always return qfalse.
- **[verified by reading] CombatBotAI, ShouldSecondaryFire, BotWeaponCanLead, BotAimLeading are unused** - no live call sites (BotAimLeading references at 6849/6865 are commented out).
- **[verified by reading] IsPositionReachable does redundant traces** - final ground probe (5782-5787) repeats the last loop probe (5758) because the last loop iteration clamps to pathDistance and all callers pass target z == origin z; when distance is an exact multiple of 100 the last two loop iterations are identical too. 1-2 wasted line traces per successful call.
- **[verified by reading] WP-lookup timers are only re-armed on success** - 2949-2955, 3015-3021, 4122-4128, 4145-4151, 4201-4215, 3791-3814: when GetNearestVisibleWP returns -1 or TotalTrailDistance fails, wpDestSwitchTime/destinationGrabTime is not advanced, so the O(gWPNum) InPVS + box-trace scan repeats every frame for as long as the target has no visible/reachable waypoint. Waypoint maps only.
- **[verified by reading] GetNewFlagPoint has no timer and is per-bot** - 3209-3225: while a flag lies dropped every CTF bot re-scans all waypoints with box traces (3092-3110) on every GetIdealDestination call, although the result is a shared global (flagRed/flagBlue).
- **[verified by reading] GetNearestBadThing treats client 0 specially** - `ent->r.ownerNum > 0` at 2745, 2753, 2761, 2769 excludes owner 0 from the teammate exemption, so teammates of client 0 still flee his rockets/detpacks/mines/thermals. Also it mutates state (doForcePush 2734, currentEnemy 2805, dontGoBack 2819) from what looks like a query.
- **[verified by reading] MeleeCombatHandling traces every frame with no caching** - 4642, 4649, 4664: three 4096u box traces per frame per melee bot within 256u of its enemy, only to compare three integer floor heights; result only sets goalPosition (4671).
- **[verified by reading] G_NewBotAIAimLeading uses the bot's own forceJumpZStart for the enemy** - 4802 `bs->cur_ps.fd.forceJumpZStart` should be the enemy's; the clamp at 4803-4804 is therefore wrong. Also 4888-4891 both branches add +20 yaw (no-op conditional).
- **[verified by reading] G_NewBotAIGetProjectileSpeed has an unreachable branch** - 4746 (repeater alt + WT_TRIBES = 2000) is shadowed by 4734-4739.
- **[verified by reading] BotAimOffsetGoalAngles divides by bs->settings.skill** - 5025; skill 0 would give inf/NaN before the clamp at 5064 (NaN would then reach `(int)accVal` at 5082). Depends on skill never being 0.
- **[verified by reading] BotFallbackNavigation wall probe follows view pitch** - 5399 uses bs->viewangles for forward, so when the bot looks up/down the 32u wall trace (5403) and 64u ledge probe (5408) are tilted and the backward EA_Move (5467-5468) has a vertical component.

### Lines 5790-8700

- **[verified by reading] NewBotAI_GetAim loop bound `i <= MAX_CLIENTS` (6824).** Iterates i = 0..32. g_entities[32] is a valid array slot (no OOB on g_entities) but is not a player slot; if that entity has a client (NPC/vehicle) with saberInFlight, 6827 calls PassLovedOneCheck, which reads `botstates[ent->s.number]` (2414) = botstates[32], one past the end of `bot_state_t* botstates[MAX_CLIENTS]` (63). Reachability of the OOB read (entity 32 having a client with a thrown saber) is suspected, the off-by-one itself is verified.
- **[verified by reading] `saberOwner` (6802) is declared uninitialized but is NOT actually read uninitialized.** Its only read (6844) is behind `saberDistance < 200 * 200 &&`, and saberDistance only drops below its 9999999 initial value in the same block that assigns saberOwner (6834-6837). Compiler warning only; initialize to -1 to be safe.
- **[suspected] NewBotAI_GetAim uses `saber->s.pos.trBase` (6831, 6852) as the saber position.** For a moving trajectory trBase is the start point, not the current position (r.currentOrigin); also `dist`/`saberDistance` are int holding squared floats.
- **[verified by reading] NewBotAI_GetStrafeAim dereferences `bs->currentEnemy->client->ps.origin` at 6759 before the `if (bs->currentEnemy->client)` check at 6761, and with no check of bs->currentEnemy at all.** NewBotAI_GetAim calls it at 6808 BEFORE its own NULL check at 6812. Crash needs runningLikeASissy set with no enemy client; callers 12446 (NewBotAI_Tribes, after StandardBotAI which can NULL currentEnemy at 13582) and 12457 (NewBotAI_StrafeJump) do not guard. Reachability suspected.
- **[verified by reading] NaN in NewBotAI_GetStrafeAim (6770).** `acos((baseSpeed - baseSpeed*0.008) / currentSpeed)`: currentSpeed == 0 -> division by zero (inf or NaN); any currentSpeed < 0.992*baseSpeed -> argument > 1 -> acos returns NaN. The range check at 6774 (`< 0 || > 360`) is false for NaN, so NaN flows into newAngle (6779-6787) and bs->goalAngles[YAW] / bs->ideal_viewangles (6792-6794) whenever forceMove_Right != 0.
- **[verified by reading] NewBotAI_GetStrafeAim discards the yaw toward the enemy.** 6766 stores the enemy angle in goalAngles, then 6792 overwrites goalAngles[YAW] with `bs->aimOffsetAmtYaw + newAngle` (the comment at 6768 says the enemy angle should be the base).
- **[verified by reading] Unchecked `bs->currentEnemy->client` dereferences (currentEnemy NULL-checked or not, client never):** NewBotAI_GetDist 6889; NewBotAI_GetTimeToInRange 6910/6912; NewBotAI_GetAbsorb 6961, 6969; NewBotAI_GetProtect 6981 (in an initializer, before every early-out), 7000, 7003; NewBotAI_ReactToBeingGripped 7089; NewBotAI_Gripkick 7144; NewBotAI_Draining 7252; NewBotAI_Protecting 7356; NewBotAI_Absorbing 7375/7380; NewBotAI_GetSpeedTowardsEnemy 7432; NewBotAI_GetTribesWeapon 7541 (checked later at 7587); BotGetCurrentAttackType 8394; BotDynamicCombatMovement 8416; BotCombatStrafe 8512; BotSelectStrafeDirection 8558/8565; BotMovementDuringAttack 8665; BotPredict*Movement 8190-8293. Current callers (XvX at 13050/13594, NewBotAI_GetAttack 10518) guarantee a client, so crash is suspected only where StandardBotAI holds a non-client currentEnemy (e.g. 14267 checks only `bs->currentEnemy`).
- **[verified by reading] BotPredictEnemyPosition inverted guard (8076-8077):** `if (!bs->currentEnemy || !bs->currentEnemy->client) { VectorCopy(bs->currentEnemy->client->ps.origin, ...)` dereferences exactly the pointer it just found to be NULL. Callers 13284, 14242 and 8625 check only `bs->currentEnemy`, not `->client`.
- **[verified by reading] `groundEntityNum == ENTITYNUM_NONE - 1` (7064, 7186, 7189).** q_shared.h 927-928: ENTITYNUM_NONE = MAX_GENTITIES-1, ENTITYNUM_WORLD = MAX_GENTITIES-2, so the expression equals ENTITYNUM_WORLD: "standing on world brush". A bot standing on a mover/func_ entity or another player is treated as airborne: 7189 then calls Flipkick every think, and 7064 will not start the jump. Compare 6971 which correctly uses `== ENTITYNUM_NONE` for "in air".
- **[verified by reading] NewBotAI_Raging force-clears `level.clients[bs->client].ps.fd.forcePowersActive &= ~(1 << FP_RAGE)` (7304)** directly from AI code, bypassing the game's force-power stop path (so whatever that path does - duration/recovery bookkeeping, looping sound - is skipped; the exact skipped side effects are suspected, not read here). It also presses EA_ForcePower with FP_RAGE selected in the same think (7299-7300), so the usercmd may try to toggle rage again after the bit was already cleared.
- **[verified by reading] NewBotAI_Raging "turn on" block (7320-7335) is unreachable in practice.** The function is only called when cur_ps has FP_RAGE active (11957, 11976, 12049-12050) and the block requires `!rageActive`; also `ourFP == 100` (7328) is an exact-equality test. The second call site 11976-11978 is unreachable because 11957-11959 returns.
- **[verified by reading] Division/modulo by zero in NewBotAI_GetTimeToInRange.** 6902 `1000 / sv_fps.integer` is an integer division (crash if sv_fps is 0); if sv_fps > 1000, tick = 0 and 6915 `maxTime % (int)tick` is a modulo by zero and 6918-6924 divide velocities by 0. Whether sv_fps can take those values depends on cvar limits (suspected).
- **[suspected] NewBotAI_GetTimeToInRange unit error (6918-6924):** velocity (units/s) is divided by tick (ms per frame) instead of by sv_fps. Numerically close only near sv_fps 30 (33 vs 30); at sv_fps 20 it under-steps by 2.5x, at 40 it over-steps by 1.6x.
- **[verified by reading] AI code writes directly to level.clients[].ps:** STAT_HOLDABLE_ITEM 6651; fd.forcePowerSelected at 6965, 7021, 7031, 7035, 7041, 7094, 7101, 7105, 7112, 7118, 7124, 7224, 7267, 7277, 7299, 7311, 7332, 7365, 7386, 7400; fd.forcePowersActive 7304. Note 6965: NewBotAI_GetAbsorb, a weight "getter", has the side effect of changing forcePowerSelected even when the caller ends up choosing another power.
- **[verified by reading] NewBotAI_GetProtect computes `totalhealth` from the ENEMY's armor (6981):** `g_entities[bs->client].health + bs->currentEnemy->client->ps.stats[STAT_ARMOR]`.
- **[verified by reading] Missing shift in saber ownership test: `bs->cur_ps.stats[STAT_WEAPONS] & WP_SABER` (7849, 7883, 7927)** instead of `& (1 << WP_SABER)` as used at 7640, 7685, 7719, 7754, 7792, 7837. Tests low weapon bits instead of the saber bit.
- **[verified by reading] NewBotAI_GetTribesWeapon copy-paste conditions.** 7469 and 7504 use `(weapon == WP_BRYAR_OLD && fuel == 100) || (weapon == WP_BRYAR_OLD && fuel > 10)` (first term should be `!=`, compare 7466/7499), so bryar_old is never switched TO. 7544 has the same pattern for WP_BLASTER. 7541-7544: the thermal `if` is followed by a plain `if`/else-if chain that overwrites bestWeapon = WP_THERMAL whenever any later branch matches.
- **[verified by reading] CheckForFriendInLOF `tr.entityNum <= MAX_CLIENTS` (6388)** admits entity 32; 6399 then indexes `botstates[trent->s.number]` = botstates[32], one past the array end (reached if entity 32 has a client and the bot is not in teamplay/same team).
- **[verified by reading] CheckForFriendInLOF is an untimed 2048u box trace run every think in team gametypes (14809-14811)** even when the bot is not firing. Performance hazard, see C_traces.
- **[verified by reading] StrafeTracing (6201) is never called.** bs->meleeStrafeDisable is written only inside it, so the gate at 14629 is always open and melee strafing (14632-14640) has no wall or ledge check at all.
- **[verified by reading] BotCanHitEnemy runs up to 3 times per think (8598 -> 8318, 8602 -> 8066, 13090/14289 -> 8327 -> 8318)**, each with its own box trace (8044) and its own randomized prediction, so the three answers can differ within one think.
- **[verified by reading] BotAnalyzeMovementPattern is not idempotent within a think (8153-8159).** It overwrites bs->lastEnemyVelocity on each call, so the 2nd..5th BotPredictEnemyPosition call of the same think sees velChange == 0 and can only return 0 or 4. Also, if the function was not called for > 100 ms it just reseeds and returns 0 (8147-8151).
- **[verified by reading] BotPredictStrafingMovement overshoot (8206-8212).** In the "mixed movement" branch strafeDir is an un-normalized velocity vector and strafeAmount = |strafeDir| * t, so the offset is |v|^2 * t * 1.2 (e.g. v = 250, t = 0.3 -> 22500 units). Prediction lands far outside saber range, so BotCanHitEnemy fails its distance test (8032) and aiming at 13286/14244/8628 swings toward a bogus point.
- **[verified by reading] BotPredictJumpingMovement gravity sign (8229):** rising branch ADDS 0.5*800*t^2 to z; it should subtract.
- **[suspected] BotPredictRetreatingMovement / BotPredictChargingMovement labels are inverted (8257-8262, 8280-8285).** toBot points from enemy to bot; "retreating" fires when the enemy moves TOWARD the bot (dot > 0), "charging" when it moves away (dot < -50).
- **[verified by reading] Dead state in the enhanced-combat block.** bs->isAttacking is only ever set to qfalse (992) -> 8443 test always true, 8659 return never taken. bs->lastAttackHitTime is only ever 0 (987) -> combo attack at 8619-8620 never fires. bs->combatStrafeDir (8543) and bs->lastAttackType (8342) are never read.
- **[verified by reading] BotUpdateDynamicMovement self-extending strafe (8641-8644).** While combatStrafeTime > level.time it calls BotCombatStrafe every think, which re-rolls the direction (8578 Q_irand) and resets combatStrafeTime to now+300/400 (8542). Once started, the strafe never times out while the enemy stays visible in range, and its direction can flip every think.
- **[suspected] BotDynamicCombatMovement may pass an uninitialized moveDir to EA_Move (8437-8446)** if BotCombatStrafe hits its `default: return` (8537-8538). BotSelectStrafeDirection only returns 0 when currentEnemy is NULL, which 8408 excludes, so currently unreachable.
- **[verified by reading] NewBotAI_ReactToBeingGripped wrong disable bit (7116):** the "can push and not pull" branch tests `g_forcePowerDisable & (1 << FP_PULL)` but uses FP_PUSH. Also 7092: when absorb is known but forcePower < 12 the else-if chain is consumed and no push/pull fallback is tried.
- **[suspected] NewBotAI_Flipkick `enemySwing` uses the bot's own `bs->cur_ps.torsoTimer` (7054)** although the name and use imply the enemy's torsoTimer.
- **[verified by reading] NewBotAI_Healing is a no-op (7391-7404):** only called when FP_HEAL is active (12115-12116) but its body requires FP_HEAL not active (7398).
- **[suspected] NewBotAI_Speeding condition is always true (7276):** `health < 90 || forcePower <= 100` - forcePower is normally capped at 100, so the bot presses the force button with FP_SPEED selected every think while speed is active (possible immediate toggle-off).
- **[verified by reading] BotCheckDetPacks does an untimed G_Find entity scan every think while a detpack is planted (6558, caller 14385-14387).**
- **[verified by reading] BotScanForLeader is an untimed MAX_CLIENTS loop every StandardBotAI think for every bot without a squad leader (13831-13833).** No traces; cheap but constant.
- **[verified by reading] CTFFlagMovement never assigns bs->wantFlag** (only clears it at 6500, 6505, 6510), so the first block (6485-6511) only ever clears, and the box trace at 6535 repeats every think while a dropped flag is within 256u.
- **[suspected] NewBotAI_GetSpeedTowardsEnemy (7434-7441)** takes sqrt of a dot product with an un-normalized direction vector; the result is not a speed.
- **[verified by reading] Two weapon selectors per StandardBotAI think:** NewBotAI_GetAttack 10525 calls BotSelectWeapon unconditionally every think, and BotSelectIdealWeapon (13664) may select a different weapon later in the same think when g_newBotAI is 0.

### Lines 8680-11215

- **[verified by reading] PERF: NewBotAI_GetAttack runs twice per bot per frame.** NewBotAI calls NewBotAI_XvY (13052-13060, each ends in GetMovement + GetAttack) and then GetAttack again at 13237; StandardBotAI does the same (13602-13610 then 14186). Bot_ExecuteSaberCombat's box trace 9971 and line trace 10052 are therefore paid twice, special-move rolls happen twice, and Bot_UpdateEnemySwingMemory decay (10227, 10866) is applied up to 3x per frame.
- **[verified by reading] PERF: Bot_CheckAndInteractWithObstacle "3000 ms cooldown" is not a cooldown.** Gate at 10884/10943 tests bs->lastObstacleTime, which is only set when the function returns qtrue (10886, 10945). On the normal qfalse result the 128u trace (9698) runs every frame for saber bots at dist<=100 and all bots at dist>200.
- **[verified by reading] PERF: traces before early-outs in Bot_ExecuteSaberCombat.** Box trace 9971 and line traces 10052/10069 execute before the "special active -> return" (10203-10205) and "dist > SPECIAL_RANGE -> return" (10220) checks, i.e. on frames where the function issues no commands.
- **[verified by reading] PERF: Bot_CheckMovementPaths (3 traces) is ungated** (10951 every generic-path frame) and is called a second time in the same frame at 11058/11085 with identical inputs; probe 11078 (32u fwd) is nearly redundant with 10795 (64u fwd).
- **[verified by reading] Wrong AngleVectors argument order, Bot_CheckMovementPaths 10779-10780.** `AngleVectors(bs->viewangles, forward, right, left)` puts the UP vector in `left`; `right` is then negated, becoming actual LEFT. Trace 10800 probes straight up, 10805 probes left, the true right side is never probed; `enemyDot = DotProduct(toEnemy, right)` (10815) is sign-inverted so the bot strafes away from the enemy's side; `!leftBlocked -> EA_MoveLeft` is driven by "is there headroom".
- **[verified by reading] Wrong AngleVectors argument order, Bot_CheckAndInteractWithObstacle 9892-9893.** `AngleVectors(bs->viewangles, NULL, left, right)`: `left` gets RIGHT then is negated (ok), `right` gets UP. Trace 9910 starts 64u above the bot and avoidDir (9918/9925) can be the up vector passed to EA_Move.
- **[verified by reading] Unreachable jump logic in Bot_CheckAndInteractWithObstacle.** 9762 requires heightDif (= absmax[2]-origin[2], 9748) > 48 and 9773 requires the same quantity < 48; 9822 requires > 30 and 9824 < 30. Blocks 9774-9802 (incl. trace 9784) and 9825-9828 never execute; `jumpCheck` (9769-9770) unused.
- **[verified by reading] EA_Use does not press "use".** BotInputToUserCommand maps ACTION_USE to BUTTON_USE_HOLDABLE (582); real BUTTON_USE is only pressed randomly while noUseTime < level.time (589). Door/button/plat handling at 9841-9842, 9858-9859, 9870-9871 therefore activates the bot's holdable item and simultaneously suppresses BUTTON_USE for 300-500 ms.
- **[verified by reading] Kata lockout.** 10287: kata rolled first with chance specialChance+10 >= 75% whenever dist <= SPECIAL_RANGE (always true after 10220). State is set (10289-10291, 1200 ms) before Bot_ExecuteKataAttack, which silently returns when dist<40, FP<50 or already in kata (9646-9662). While currentSpecial != 0 the function returns at 10205 without issuing any command. Net: bot idles from this function for 1.2 s at a time; later cascade entries and basic swings (10428+) are rarely reached.
- **[verified by reading] Special cooldown is a no-op.** 10201-10208: when currentSpecial == NONE and within 600 ms of lastSpecialTime the if-body does nothing; specials are still rolled (comment says otherwise).
- **[verified by reading] bs->avoidanceTimer / avoidanceDirection never written** (only read at 10101-10106; declared ai_main.h:428-429). Branch 10101-10114 is dead.
- **[verified by reading] Direct playerState write from AI:** 9669 `g_entities[bs->client].client->ps.weaponTime = 0` (bypasses weapon timing; not predicted). Also direct command calls Cmd_SaberAttackCycle_f (9214-9351, 9470, 9475) and Cmd_ToggleSaber_f (9998) from AI code.
- **[verified by reading] Unreachable "delayed" code.** 9471/9474: styleSwitchTime = level.time+200 then `if (level.time >= styleSwitchTime)` - never true, style never switched back. 9495/9497: same pattern, second strike 9498-9501 never runs. Bot_ExecuteStyleSwitch also overwrites bs->styleSwitchTime that is initialised for another purpose at 978.
- **[suspected] Bot_ExecuteStyleSwitch on staff/dual:** Cmd_SaberAttackCycle_f for dual/staff toggles a blade rather than changing style; without the switch-back the bot may stay single-bladed.
- **[verified by reading] enemySwingStage == 8 never produced** (8861-8885 yields 0..7), so reset-parry block 9047-9052 is dead; blocking.lastBlockTime is never updated after 9110.
- **[verified by reading] Parry nearly unreachable.** shouldParry armed only in stage 2 (9007) with a 100 ms window, but stages 2..6 return at 9012 before the parry branch 9019; stage 7 arrives >=275 ms later. Bot_ExecuteParry runs only if the enemy move leaves stages 2-6 within 100 ms. blockConfidence therefore never rises (only 9094 increases it) and has no lower clamp at 9038.
- **[verified by reading] ideal pitch overwritten:** 8990 sets ideal_viewangles[PITCH] = -10 absolutely during enemy swings, discarding aim at the enemy computed at 9957. [suspected] sign: negative pitch looks up in Q3 angles, comment says "look down".
- **[verified by reading] Gun fire-rate modulo bug.** 10566-10568 and 10578-10580: fireRate = enemyVulnerable ? 1 : 2; `level.framenum % 1` is always 0 so the bot NEVER fires (charge==3 weapons) while BotEnemyVulnerable is true (enemy airborne, saberMove==LS_READY, or in recovery); otherwise fires only on odd frames. Intent was the opposite.
- **[verified by reading] `!bs->client` treated as invalid (10518).** bs->client is the client number; a bot in slot 0 never attacks via this function.
- **[verified by reading] Division by zero -> NaN in Bot_GetAdaptiveDodgeDir 10634-10635.** NewBotAI_GetMovement sets lastEnemyPos/lastEnemyTime to current values (10869-10870) before both calls (10973, 11127), so enemyVel = 0 * (1/0) = NaN; the comparisons at 10639/10642 are always false. Enemy-movement prediction never works. (If called from elsewhere with lastEnemyTime == level.time same result.)
- **[verified by reading] randomFactor has no effect** (10654-10657: same value added to all three probabilities).
- **[verified by reading] Q_irand over quad enum ranges.** Enum order (bg_public.h:1645-1652) is Q_BR=0,Q_R,Q_TR,Q_T,Q_TL,Q_L,Q_BL,Q_B=7. `Q_irand(Q_R, Q_L)` (9079, 9490, 10431, 10477, 10502) yields R,TR,T,TL,L (not just sides); `Q_irand(Q_BR, Q_B)` (10477, 10501) yields any of the 8 quads (not "down" quads).
- **[verified by reading] Bot_ExecuteThreeSwingCombo never moves:** 9567-9594 compute moveDir three times but never call EA_Move; result is a plain EA_Attack. 3 wasted AngleVectors.
- **[verified by reading] Bot_ExecuteLungeAttack range mismatch:** callee requires 95<=dist<=140 (9621) but caller requires dist<=LUNGE_MAX (80/95/110) (10454); lunge impossible in fast/tavion style, only dist==95 in medium, 95..110 in strong/desann.
- **[verified by reading] Unreachable branches in NewBotAI_GetMovement:** 10999-11004 (needs !currentEnemy or dist>150, but dodge requires dist<105; both arms call EA_Jump anyway); 11168-11185 incl. trace 11180 (needs dist>115 but code is reached only when dist <= adjustedMax-20 <= 110); `!bs->currentEnemy` at 10943 and 10838 (within GetMovement call path, enemy is non-NULL after 10861).
- **[verified by reading] strafeDir value 2 ("dodge back") treated as left:** 11146 stores Bot_GetAdaptiveDodgeDir result (can be 2) and 11158-11159 maps anything != 1 to EA_MoveLeft. When the strafe roll fails (11151-11153) strafeExpireTime is not advanced, so the roll repeats every frame.
- **[verified by reading] Bot_CheckRearThreat (10768) adds 180 to ideal yaw every frame** while frontDot < -0.6 (oscillation until the view catches up).
- **[verified by reading] MASK_PLAYERSOLID includes CONTENTS_BODY** in 9971, 10795-10805, 10904, 10927, 11051, 11078, 11198: the enemy and teammates count as walls. [suspected effect] nearWall (9975) becomes true whenever the enemy is within ~24u+bbox in front, triggering the 50% back-off and random yaw +-30 (9981-9987) in every close duel; CheckMovementPaths reports frontBlocked on the enemy and short-circuits dodge/strafe logic.
- **[verified by reading] NULL-deref hazards (currently masked by callers):** Bot_SelectOptimalSaberStyle derefs bs->currentEnemy->health at 9177 before its own NULL test at 9182 and ->client at 9209 with no test (callers 10542, 13078, 14277 check currentEnemy; 13072/14271 already deref client). Bot_ExecutePerfectBlocking checks currentEnemy but derefs ->client at 8985; Bot_ExecuteParry 9065, Bot_ShouldBackstepForSwing 10695-10696, Bot_ShouldPressAttack 10739, Bot_ExecuteFeint 8817, BotCanFeint 8724/8730, Bot_GetAdaptiveDodgeDir 10634, Bot_ExecuteConvergent/Static/Lunge 9514/9549/9630, Bot_ExecuteSaberCombat 9956 all deref currentEnemy->client without a local check.
- **[suspected] Stale enemy pointer:** nothing in this region checks bs->currentEnemy->inuse / health>0 / connected; enemy ->health and ->client->ps are read on trust (e.g. 9177, 10270, 10456, 11033). Depends on upstream validation each frame.
- **[verified by reading] g_entities[tr.entityNum] indexing is safe** at 9702 and 10057 (both guarded by entityNum < ENTITYNUM_WORLD); the `!hitEnt` / `obstacle &&` tests (9705, 10059) are always-true address checks. No ENTITYNUM_NONE/WORLD indexing bug in this region.
- **[verified by reading] Uninitialised / unused locals:** Bot_ExecuteDFA 9398-9399 and Bot_ExecuteCrouchLunge 9427-9428 declare enemyPos, botPos, moveDir, angles unused (botPos would be read uninitialised if the commented block 9404-9415 were re-enabled); `quad` at 10498 has no default case (all 3 cases covered, compiler warning only); Bot_ExecutePerfectBlocking computes toEnemy/right/forward (8984-8987) and `dist` (8964) unused; Bot_ExecuteConvergentAttack toEnemy (9514-9515) unused; Bot_ExecuteSaberCombat `up` unused; availableStyles initialiser (9299) overwritten.
- **[verified by reading] Bot_SelectOptimalSaberStyle cycles blindly:** each decision calls Cmd_SaberAttackCycle_f once (next style, not target) and stamps lastStyleSwitchTime; vs-human SS_MEDIUM/SS_TAVION case (9240-9248, 9261-9269) with offense<=2 wants FAST while the fast-counter case wants MEDIUM, so styles can ping-pong every 2 s. `Q_irand(8000,15000)` at 9298 is re-rolled per call (2-3 calls/frame), collapsing the interval to ~8 s. In the variety branch a random target style only decides whether to cycle, not where to.
- **[verified by reading] Combat "destroy obstacle" attacks indestructible entities:** 9877-9886 fires at func_static / misc_model / func_wall-classified hits and returns qtrue, which makes GetMovement return with no movement (10887/10946).
- **[suspected] Unhittable classnames:** trigger_multiple and target_switch (9855-9856) are not solid to MASK_PLAYERSOLID & ~CONTENTS_BODY, so those branches likely never match.
- **[verified by reading] Dead code inventory (never called):** BotCanFeint 8709, Bot_ExecuteFeint 8795 (isFeinting never set true), Bot_GetStyleAdvantage 9117, NewBotAI_GetGroundDodge 10586, Bot_TrapSetup 10678, Bot_ApplyUltraInstinctAim 10715, Bot_GetMixedAttackMove 10722 (its `default` also unreachable), Bot_ShouldPressAttack 10735. Empty block 10026-10029 burns a Q_irand.

### Lines 11205-12945

- **[verified by reading] Per-think EntitiesInBox with no throttle on waypoint-less maps** (12568-12612). With gWPNum == 0, wpCurrent is never set, `destination` stays false, so `trap->EntitiesInBox` over a 2048x2048x512 box plus GetNearestVisibleWP (12570) run on every DoAloneStuff call for every idle bot. No timer or cache.
- **[verified by reading] Item choice is "first in list", with no reachability or LOS check** (12613-12670). The loop breaks on the first acceptable ET_ITEM; `hit->s.origin` becomes the destination even through walls/floors (box is +/-256 in Z). The bot then runs straight at it every think (only 48u obstacle probes, random strafes). IT_TEAM items (flags) and non-enlightenment powerups are not filtered.
- **[suspected] Bot can park on or under an item it cannot pick up** (12617-12668): an item that passes the filters but is never consumed (flag of own team, weapon pickup blocked by server settings) stays first in the list forever; no give-up timer exists.
- **[verified by reading] "Enemy tracking" branch is effectively dead** (12677-12678). It requires `lastVisibleEnemyIndex == currentEnemy->s.number` AND `lastVisibleEnemyIndex > level.time - 10000`. NewBotAI stores `level.time` in that field (13007, 13018), StandardBotAI stores an entity number (13918) or ENTITYNUM_NONE (13929). The field is used with two incompatible meanings; the condition only holds in the first ~10 s of a map (StandardBotAI) or never (NewBotAI). Same confusion at 13022.
- **[verified by reading] gWPArray out-of-bounds index** (12589-12592): `desiredIndex = index +/- 1` is used as `gWPArray[desiredIndex]` with no bounds check; index -1 when walking backwards from waypoint 0, and index gWPNum at the far end. Only reachable when waypoints exist.
- **[verified by reading] ScanForEnemies returns -1 when the current enemy is the Jedi Master** (12874-12876). The caller treats -1 as "nobody here" and runs DoAloneStuff (12991-12993), so the comment "The Jedi Master must die" produces the opposite behaviour in NewBotAI.
- **[verified by reading] Target hysteresis is dead** (12862, 12870-12872, 12919, 12928): hasEnemyDist is always 0, so the "only switch if 128 closer" rule never applies and the target can change every think.
- **[verified by reading] Wasted work in ScanForEnemies**: `vectoangles(a, a)` at 12910 result is never used; loop runs all 32 slots instead of connected clients (12889-12892); trap->InPVS per live enemy per bot per think with no timer (12894).
- **[verified by reading] Out-of-bounds read for forced target** (12972-12976, 3 lines past the region, relevant to g_newBotAITarget): closestID is set to -1 when out of range and then `cl = &level.clients[closestID]` / `cl->pers.connected` is read with index -1. `!cl` can never be true. Also `level.clients[g_newBotAITarget]` gets no alive/spectator/self check, and 13004 forces frame_Enemy_Vis = 1 for a forced target without any LOS test.
- **[verified by reading] currentEnemy->client dereferenced before the NULL check** in GetDSForcepower (11605 vs check at 11618-11619) and GetLSForcepower (11791 vs 11805-11806); the later checks are redundant. All weight functions (11234, 11254, 11267, 11338, 11414, 11450, 11457, 11501, 11578) dereference `bs->currentEnemy->client` unchecked. Callers do guarantee a client enemy today (13001/13050, 13594), so this is a hazard, not a live crash.
- **[verified by reading] GetLightning inconsistent NULL handling** (11395 checks `bs->currentEnemy`, 11414 dereferences `bs->currentEnemy->client` unconditionally).
- **[verified by reading] GetRage unreachable branch** (11444-11447): `else if (ourHealth < 25)` can never run because `ourHealth < 50` catches it first. Gate at 11436 (`weapon == WP_NONE && dist < 300`) does not match its comment.
- **[verified by reading] Strict-greater selection drops ties** (11628-11651, 11815-11842): two powers sharing the top weight (several return exactly 100) select nothing that think.
- **[verified by reading] LS chain ignores telepathy in the other comparisons and telepathy ignores protect** (11815-11839): push/pull/absorb/protect/heal never compare against telepathyWeight; telepathy test at 11835 omits protectWeight. Telepathy can be beaten by a lower weight earlier in the chain.
- **[verified by reading] Team Energize has no team filter and overrides any chosen power** (11547-11564 vs TeamHeal's check at 11765; override at 11662-11665 is not guarded by `!useTheForce`). It can energize enemies in team games. `!&g_entities[i]` (11550, 11763) is always false.
- **[verified by reading] Direct playerState writes from AI code**: forcePowerLevel[FP_TEAM_FORCE] = 3 on every call (11545, marked "hack"); forcePowerLevel[FP_SABERTHROW] = 3 and forcePowersKnown |= SABERTHROW (11579-11580, grants a power); forcePowerSelected (11629-11663, 11816-11855, 12202, 12522-12553); saberAnimLevel = SS_STRONG (12186); ps.velocity overwritten in CapRoute (12376-12377); bs->frame_Enemy_Vis cleared inside DoAloneStuff (12514).
- **[verified by reading] GetSaberthrow is a "getter" with side effects** (11583): it presses EA_Alt_Attack itself, then both callers press it again (11675, 11870). DS caller limits to 500..900 (11670) while the getter and LS caller use 500..2500 (11574-11575, 11864).
- **[verified by reading] DSvDS freezes while its saber is in flight outside 500..2500** (11916-11930 and 11993-12007): every non-range branch returns before GetMovement/GetAttack, so the bot only aims. In-range case calls SaberThrowing and continues. LSvDS has no such returns (12092, 12123).
- **[verified by reading] Duplicate/unreachable Rage handler in DSvDS** (11976-11978 after the returning check at 11957-11960).
- **[verified by reading] Unused computations each think**: `a_fo` vectoangles in both choosers (11605-11606, 11791-11792); `speed` in NF computed before the knockdown return (12177).
- **[verified by reading] CapRoute array indexing unchecked** (12320-12327, 12334-12343): `activeCapRoute - 1` is used as an index with no upper bound check against the route list size; `activeCapRouteSequence` is only checked against `.length`. Velocity scale 40 hard-codes a frame rate (comment "sv_fps ?", 12377). Trace mask is CONTENTS_BODY only, so world geometry between route points is ignored.
- **[verified by reading] DoAloneStuff toggles OFF Protect/Absorb/Rage rather than managing them** (12534-12551): selecting an already-active power and pressing the force key on the 500 ms window. Intentional or not, Rage is cancelled whenever HP >= 30.
- **[verified by reading] DoAloneStuff called from StandardBotAI on every think that has an enemy** (13818-13827): the condition ends with `|| (bs->currentEnemy)`, so it is always true once an enemy exists; DoAloneStuff then presses movement keys in addition to StandardBotAI's own movement.
- **[verified by reading] NewBotAI_Tribes runs the full StandardBotAI inside NewBotAI** (12445), doubling AI cost per think in Tribes mode and letting two movement systems issue inputs.
- **[verified by reading] NewBotAI_StrafeJump is dead code** (12452-12483): no callers; `distance` unused.
- **[verified by reading] Mixed syscall styles** `trap_EA_ForcePower` / `trap_EA_Attack` / `trap_EA_MoveBack` / `trap_EA_Jump` (12203, 12230, 12232, 12233) next to `trap->EA_*`; depends on a macro/wrapper existing elsewhere (not checked).
- **[verified by reading] No int function in the region is missing a return**: GetPull falls through to `return 0` at 11324 from the light-side branch (11304-11307); GetDrain falls through to 11485 when saber in flight, HP>40, hisForce<=10. EntitiesInBox buffer (256, line 12487) matches the count passed (12612): no overflow.
- **[suspected] Fallback emergency branch unreachable** (outside region, 5533 vs 5379-5383): stuckCounter is reset at >5, so `> 20` never holds; the target generator (up to 12 x 7 traces, 5497-5514) can re-run every think while all attempts fail, with only lastWallHitTime as a gate.

### Lines 12940-15093

- **[verified by reading] BotAIStartFrame "timeout protection" drops bot frames periodically (ai_main.c:14917-14924).** `last_frame_time` is only assigned inside the `> 100` branch, never on a normal frame. Result: the first call after every 100 ms of wall-clock time returns early - no AI, no `BotUpdateInput`/`trap->BotUserCommand`, no `G_CheckBotSpawn`, no `UpdateEventTracker`. At sv_fps 20 that is 1 call in 3 (or 1 in 2 with timer jitter), at sv_fps 40 1 in 5, at sv_fps 10 about every other call or worse. `local_time` (14984) is not updated on skipped calls, so the next call sees a doubled elapsed_time. The very first call is always skipped (static starts at 0). The warning is invisible because `BotAI_Print` is an empty stub (ai_main.c:356).
- **[verified by reading] No think throttle at all.** `BOT_THINK_TIME` is 0 (ai_main.c:60), so `thinktime == elapsed_time` and `botthink_residual >= thinktime` (14997) is always true: every bot runs full AI on every BotAIStartFrame call. The engine cvar `bot_thinktime` (sv_bot.cpp:668) is never read by the game. On a listen server BotAIStartFrame is called every client frame (sv_main.cpp:1247), not every server frame.
- **[verified by reading] Dead validation loop in BotAIStartFrame (14926-14944).** Body contains only `continue`; the `i < 0 || i >= MAX_CLIENTS` test at 14928 is redundant with the loop bounds. Pure waste (32 iterations per call).
- **[verified by reading] BotAIStartFrame 15000 / 15011 dereference `g_entities[i].client` without a NULL check** (the dead loop above was presumably meant to guard this). Only safe while every in-use botstate has a client.
- **[verified by reading] StandardBotAI function-level statics are shared by all bots (13353-13358, 14482-14483).** `lastStuckCheckPos`, `lastStuckCheckTime`, `stuckCounter` (used 14534-14593) and `lastBackupTime`, `consecutiveBackups` (14482-14530) are single globals. With more than one bot the stuck check runs for whichever bot arrives first each second and compares its origin with a different bot's last position, so stuck detection is effectively random; the backup counter mixes all bots' wall hits. The outer `lastBackupTime`/`consecutiveBackups` (13357-13358) and `lastUnstuckDirection` (13356) are unused (shadowed / never read).
- **[verified by reading] Backup counter logic inverted (14485-14492).** Comment says "if we haven't backed up recently" but the code resets the counter when a backup happened within the last 2 s and increments it otherwise, so "3 consecutive backups" can only be reached by wall hits spaced more than 2 s apart.
- **[verified by reading] ScanForEnemies runs unconditionally (13818-13819).** `... || !bs->currentEnemy || (bs->currentEnemy)` is a tautology (the saber/range part is commented out). Costs a 33-slot loop plus line traces every think for every bot, and re-traces the current enemy that 13913 traces again.
- **[verified by reading] StandardBotAI calls NewBotAI_DoAloneStuff when a new enemy is acquired (13827).** DoAloneStuff issues its own EA_MoveForward / jump / ideal_viewangles and traces, then StandardBotAI continues and issues its own movement on the same frame. Looks unintended (conflicting inputs + a burst of traces / EntitiesInBox).
- **[verified by reading] NewBotAI_GetAttack executed twice per think** when the enemy is visible: once inside NewBotAI_LSvLS/DSvLS/LSvDS/DSvDS (11935, 12013, 12032, 12071, 12098, 12130, 12149, 12171) and again at 13237 (NewBotAI) / 14186 (StandardBotAI). Doubles Bot_ExecuteSaberCombat traces and can double-issue attack inputs.
- **[verified by reading] Out-of-bounds read in NewBotAI forced-target path (12970-12977).** If `g_newBotAITarget >= level.maxclients`, closestID is set to -1 and then `cl = &level.clients[closestID]` / `cl->pers.connected` reads `level.clients[-1]`. `!cl` can never be true. The forced target is also not checked for self, death, spectator or team before `g_entities[closestID].client->ps` is used at 13001.
- **[verified by reading] gWPArray indexed before / without bounds checks.** 14002: `gWPArray[goalWPIndex]` where goalWPIndex = `wpCurrent->index - 1` can be -1 (index 0 with wpDirection set) or == gWPNum. 14054-14057: `gWPArray[desiredIndex]` and `->inuse` are evaluated BEFORE the `desiredIndex < gWPNum && desiredIndex >= 0` tests. (Same pattern with no bounds test at all in NewBotAI_DoAloneStuff 12592, outside this region.)
- **[verified by reading] `lastVisibleEnemyIndex` has two incompatible meanings.** StandardBotAI stores an entity number (13918, 13929; read at 13635, 14389); NewBotAI stores level.time (13007, 13018; read as a time at 13022). NewBotAI_DoAloneStuff 12677-12678 requires it to equal the enemy's entity number AND be greater than level.time - 10000, which is only possible in the first ~10 s of a map, so its "enemy tracking" priority is dead code. Switching g_newBotAI at runtime also leaves garbage in the field.
- **[verified by reading] NewBotAI 13018 refreshes lastVisibleEnemyIndex even when the attacker is NOT visible** (assignment is outside the `if (OrgVisible...)` at 13016), so the 10 s abandon timer at 13022 never expires while PERS_ATTACKER stays a valid enemy.
- **[verified by reading] Dead code: OrgVisible at 13257** sits in `if (!bs->frame_Enemy_Vis)` nested inside `if (bs->frame_Enemy_Vis)` (13234/13254). The whole "aim at last spotted position" branch never runs in NewBotAI.
- **[verified by reading] Flechette alt-fire check broken (13268-13269, 14226-14227).** `mLen = VectorLength(a) > 128;` stores 0 or 1, so `mLen > 128 && mLen < 1024` is never true.
- **[verified by reading] Impossible conditions.** 13110 and 14317: `frame_Enemy_Len > 4500 && frame_Enemy_Len < 900`. 13787-13788: `botChallengingTime > level.time && botChallengingTime < (level.time - 2000)` (duel challenge timeout never fires, so a bot that holstered its saber to challenge is not re-armed by this branch).
- **[verified by reading] NULL-dereference written into the else branches at 13249-13252 and 14207-14210:** `if (bs->currentEnemy->client) {...} else { VectorCopy(bs->currentEnemy->client->ps.origin, headlevel); }`. Reached only if currentEnemy is a non-client entity (suspected unreachable today since every assignment in this region uses client slots). 14271 (`bs->currentEnemy->client->ps.origin`) and 14202 likewise assume a client without checking, unlike 13900.
- **[verified by reading] NewBotAI gate at 13232 is vacuous.** enemySeenTime is set to level.time + 10000 unconditionally at 13029, so `enemySeenTime > level.time + 8000` is always true; timeToReact is never updated by NewBotAI, so no reaction delay exists (it keeps whatever value StandardBotAI or the zeroed state left).
- **[verified by reading] NewBotAI never resets doAttack / doAltAttack** (StandardBotAI does at 13554-13555). 13107/13111 set doAltAttack = 1 and nothing in NewBotAI clears it; NewBotAI_GetAttack reads it at 10557. Whether another callee clears it: not determined.
- **[verified by reading] NewBotAI ignores gDeactivated, spectator state and bot_forgimmick** (StandardBotAI handles them at 13360-13499). A NewBotAI bot moved to spectator still runs ScanForEnemies / DoAloneStuff traces.
- **[verified by reading] NewBotAI writes goalAngles (13262, 13289, 13294) + BotAimOffsetGoalAngles (13297) but never calls MoveTowardIdealAngles**, so BotPredictEnemyPosition's work is not applied by this function (wasted CPU; aim comes from NewBotAI_GetAim).
- **[verified by reading] Stale entity pointers - partial validation only.** g_entities is a static array so these never dangle in memory, but they can refer to a slot reused by a different player. Checked: currentEnemy and revengeEnemy for connection state (13572-13583) in StandardBotAI only. NOT checked for disconnect/reuse anywhere in this region: `lastHurt` (13510-13522; BotDamageNotification 2243 sets it, nothing clears it), `lastAttacked` (13723, 13733), `squadLeader` (13831-13844: only NULL tests, never validates the entity is still connected or on the team), `chatObject`, `shootGoal` (14363-14365: health/takedamage only, no inuse), `wpCamping`/`wpCampingTo` (13986 dereferences wpCampingTo without a NULL check). NewBotAI leaves `bs->currentEnemy` untouched on every early return to DoAloneStuff (12991-12998), and DoAloneStuff then reads it (12499, 12676-12677) with no validity check.
- **[verified by reading] ScanForEnemies loops `i <= MAX_CLIENTS` (2472, callee of 13821)**, examining g_entities[32], which is not a client slot (an NPC there could be picked as an enemy); also `tr.entityNum <= MAX_CLIENTS` at 6388. Outside the region but on its per-frame path.
- **[verified by reading] Non-saber bots have no navigation at all without waypoints in StandardBotAI.** BotFallbackNavigation is gated on `weapon == WP_SABER` (14083); otherwise goalPosition is never written (zero-initialised bot_state -> world origin, or a stale value) and 14595-14605 moves the bot toward it while still paying the wall/duck/strafe traces.
- **[verified by reading] Early returns skip the tail of the frame.** 14510 (third wall hit) returns before jump/crouch/fire/force handling; 14335 (pending chat) returns before all movement; 13630/13661/13666 (weapon switch) return before enemy scan and movement. 14505-14506: `ideal_viewangles[YAW] += 90` followed by MoveTowardIdealAngles, which overwrites ideal_viewangles with goalAngles (1669), so the 90-degree turn is discarded (same at 14576-14577 for the 180-degree turn; 14524 is overwritten at 14903).
- **[verified by reading] `fjHalt` is set to 0 (13585) and never changed**, so `!fjHalt` at 14464 is dead; `forceHostile` is only ever 0, so 14787 and 14878 are dead.
- **[verified by reading] Duplicate identical traces on one frame.** The 32u forward player-box trace is done at 5403 (BotFallbackNavigation), again at 14476 (StandardBotAI) and at 13144 (NewBotAI); enemy LOS is traced in ScanForEnemies (2485) and again at 13913 (and inside force-power helpers 7217/7252/7263).
- **[verified by reading] _DEBUG profiling in BotAI (817-833) is too coarse to be useful.** It brackets only the NewBotAI/StandardBotAI call (placement is correct; BotUpdateInput, client-state copy and server-command drain are excluded), but `trap->Milliseconds()` has 1 ms resolution, so a single bot's think nearly always prints 0 or 1. It calls `trap->Cvar_Update(&bot_debugmessages)` once per bot per frame, and with the cvar on it prints one line per bot per frame, which itself distorts timing. No per-frame total is accumulated.
- **[verified by reading] Memory: bot_state_t blocks are never freed.** BotAIShutdownClient (1038-1040) memsets the state and leaves the pointer in botstates[]; BotAISetupClient (898-910) then B_Allocs a NEW block because `inuse` is false, orphaning the old one - one leaked bot_state_t per bot (re)connect. BotAIShutdown non-restart (15089-15091) frees nothing and BotAISetup (15060) memsets the pointer table. Whether a global B_Alloc cleanup (ai_util.c:156-180) runs at game shutdown: not determined.
- **[verified by reading] BotAIShutdown non-restart path does not call BotAIShutdownClient** (15089-15091), so move/goal/weapon states are not released through the game and `numbots` is not decremented. Harmless only if the game module is reloaded (globals reset) - not determined.
- **[suspected] numbots can go stale / division by zero.** BotScheduleBotThink divides by numbots (858). numbots is incremented before the only live call (958-961) so it is safe today, but it is never reset in BotAISetup, and the BotAIStartFrame call site (14978-14981) is unreachable while BOT_THINK_TIME is the constant 0. If BOT_THINK_TIME is ever made non-zero, the first frame with zero bots would not divide (loop finds no in-use bot), but a mismatch between numbots and in-use states would give wrong staggering.
- **[suspected] 13011 uses PERS_ATTACKER as an entity index without range validation** (`&g_entities[attacker]`). Values are normally 0..ENTITYNUM_WORLD so the address is in range and PassStandardEnemyChecks rejects non-clients, but an NPC attacker (index >= MAX_CLIENTS with a client) would be accepted as currentEnemy.
- **[suspected] 13522 `botstates[bs->lastHurt->s.number]`** relies on lastHurt always being a real client slot (BotDamageNotification 2196 rejects NPC attackers); any other writer of lastHurt would make this an out-of-bounds read.
- **[suspected] 13594 uses frame_Enemy_Vis from the previous think** (it is recomputed only at 13913), so the XvY combat routine runs one frame late on acquisition and one frame too long after LOS is lost.

