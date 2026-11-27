/*
===========================================================================
Copyright (C) 1999 - 2005, Id Software, Inc.
Copyright (C) 2000 - 2013, Raven Software, Inc.
Copyright (C) 2001 - 2013, Activision, Inc.
Copyright (C) 2013 - 2015, OpenJK contributors
Copyright (C) 2015 - 2019, JK2MV contributors (mvsdk, https://jk2mv.org)

This file is part of the OpenJK source code.

OpenJK is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License version 2 as
published by the Free Software Foundation.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, see <http://www.gnu.org/licenses/>.
===========================================================================
*/

// w_saber_jk2.c -- JK2 1.02 saber system (g_jk2_102sabersystem), server only.
//
// Ported from mvsdk code/game/w_saber.c (CheckSaberDamage_1_02, WP_SaberCanBlock, WP_SabersCheckLock,
// WP_SabersCheckLock2 and the 1.02 part of WP_SaberPositionUpdate), taking only the 1.02 code paths.
// Logic and values are copied as they are. Only called while g_jk2_102sabersystem is on.

#include "g_local.h"
#include "bg_local.h"
#include "w_saber.h"

extern qboolean InFront( vec3_t spot, vec3_t from, vec3_t fromAngles, float threshHold );
void WP_SaberBlockNonRandom( gentity_t *self, vec3_t hitloc, qboolean missileBlock );
qboolean PM_InSaberAnim( int anim );
qboolean BG_InSpecialJump( int anim );
qboolean BG_InRoll( playerState_t *ps, int anim );
void G_SaberModelSetup( gentity_t *ent );

#define JK2_SABER_HITDAMAGE 35

// Counters for the bot profile output (bot_profile 60), see G_JK2SaberStats
int jk2SaberStatHits;		// full damage body hits (dmg > 5)
int jk2SaberStatTouches;	// 5 point touches
int jk2SaberStatBlocks;		// body hits that were blocked
int jk2SaberStatClashes;	// saber vs saber contacts
int jk2SaberStatLocks;		// saber locks started
int jk2SaberStatBounces;	// attacker bounced (BLOCKED_ATK_BOUNCE)
// per client, for the bot tactics counters (ai_main.c Bot_JK2Tactics): last full hit made (time,
// saber move, victim) and last block, and totals
int jk2StatHitTime[MAX_CLIENTS], jk2StatHitMove[MAX_CLIENTS], jk2StatHitVictim[MAX_CLIENTS];
int jk2StatBlockTime[MAX_CLIENTS], jk2StatHitsDealt[MAX_CLIENTS], jk2StatHitsTaken[MAX_CLIENTS];
int jk2StatBlocks[MAX_CLIENTS], jk2StatGotBlocked[MAX_CLIENTS];
// why the last WP_SaberCanBlock_JK2 call said no (1-19, in the order of its checks; 0 = unblockable move),
// and per client the last frame its bot was guarding (set by ai_main.c); for the bot counters only
int jk2BlockFail, jk2BotGuardFrame[MAX_CLIENTS], jk2GuardFail[20];

/*
=============================================================================

Saber locks (mv w_saber.c:WP_SabersCheckLock2 / WP_SabersCheckLock)

=============================================================================
*/

typedef enum
{
	JK2LOCK_FIRST = 0,
	JK2LOCK_TOP = JK2LOCK_FIRST,
	JK2LOCK_DIAG_TR,
	JK2LOCK_DIAG_TL,
	JK2LOCK_DIAG_BR,
	JK2LOCK_DIAG_BL,
	JK2LOCK_R,
	JK2LOCK_L,
	JK2LOCK_RANDOM
} jk2SabersLockMode_t;

#define JK2_LOCK_IDEAL_DIST_TOP 32.0f
#define JK2_LOCK_IDEAL_DIST_CIRCLE 48.0f

static qboolean WP_SabersCheckLock2_JK2( gentity_t *attacker, gentity_t *defender, jk2SabersLockMode_t lockMode )
{
	int		attAnim, defAnim = 0;
	float	idealDist = 48.0f;
	vec3_t	attAngles, defAngles, defDir;
	vec3_t	newOrg;
	vec3_t	attDir;
	float	diff = 0;
	trace_t trace;

	//MATCH ANIMS
	if ( lockMode == JK2LOCK_RANDOM )
	{
		lockMode = (jk2SabersLockMode_t)Q_irand( (int)JK2LOCK_FIRST, (int)(JK2LOCK_RANDOM)-1 );
	}
	switch ( lockMode )
	{
	case JK2LOCK_TOP:
		attAnim = BOTH_BF2LOCK;
		defAnim = BOTH_BF1LOCK;
		idealDist = JK2_LOCK_IDEAL_DIST_TOP;
		break;
	case JK2LOCK_DIAG_TR:
		attAnim = BOTH_CCWCIRCLELOCK;
		defAnim = BOTH_CWCIRCLELOCK;
		idealDist = JK2_LOCK_IDEAL_DIST_CIRCLE;
		break;
	case JK2LOCK_DIAG_TL:
		attAnim = BOTH_CWCIRCLELOCK;
		defAnim = BOTH_CCWCIRCLELOCK;
		idealDist = JK2_LOCK_IDEAL_DIST_CIRCLE;
		break;
	case JK2LOCK_DIAG_BR:
		attAnim = BOTH_CWCIRCLELOCK;
		defAnim = BOTH_CCWCIRCLELOCK;
		idealDist = JK2_LOCK_IDEAL_DIST_CIRCLE;
		break;
	case JK2LOCK_DIAG_BL:
		attAnim = BOTH_CCWCIRCLELOCK;
		defAnim = BOTH_CWCIRCLELOCK;
		idealDist = JK2_LOCK_IDEAL_DIST_CIRCLE;
		break;
	case JK2LOCK_R:
		attAnim = BOTH_CCWCIRCLELOCK;
		defAnim = BOTH_CWCIRCLELOCK;
		idealDist = JK2_LOCK_IDEAL_DIST_CIRCLE;
		break;
	case JK2LOCK_L:
		attAnim = BOTH_CWCIRCLELOCK;
		defAnim = BOTH_CCWCIRCLELOCK;
		idealDist = JK2_LOCK_IDEAL_DIST_CIRCLE;
		break;
	default:
		return qfalse;
		break;
	}

	G_SetAnim(attacker, NULL, SETANIM_BOTH, attAnim, SETANIM_FLAG_OVERRIDE|SETANIM_FLAG_HOLD, 0);
	attacker->client->ps.saberLockFrame = bgAllAnims[attacker->localAnimIndex].anims[attAnim].firstFrame+(bgAllAnims[attacker->localAnimIndex].anims[attAnim].numFrames*0.5);

	G_SetAnim(defender, NULL, SETANIM_BOTH, defAnim, SETANIM_FLAG_OVERRIDE|SETANIM_FLAG_HOLD, 0);
	defender->client->ps.saberLockFrame = bgAllAnims[defender->localAnimIndex].anims[defAnim].firstFrame+(bgAllAnims[defender->localAnimIndex].anims[defAnim].numFrames*0.5);

	attacker->client->ps.saberLockHits = 0;
	defender->client->ps.saberLockHits = 0;

	attacker->client->ps.saberLockAdvance = qfalse;
	defender->client->ps.saberLockAdvance = qfalse;

	VectorClear( attacker->client->ps.velocity );
	VectorClear( defender->client->ps.velocity );
	attacker->client->ps.saberLockTime = defender->client->ps.saberLockTime = level.time + 10000;
	attacker->client->ps.saberLockEnemy = defender->s.number;
	defender->client->ps.saberLockEnemy = attacker->s.number;
	attacker->client->ps.weaponTime = defender->client->ps.weaponTime = Q_irand( 1000, 3000 );//delay 1 to 3 seconds before pushing

	VectorSubtract( defender->r.currentOrigin, attacker->r.currentOrigin, defDir );
	VectorCopy( attacker->client->ps.viewangles, attAngles );
	attAngles[YAW] = vectoyaw( defDir );
	SetClientViewAngle( attacker, attAngles );
	defAngles[PITCH] = attAngles[PITCH]*-1;
	defAngles[YAW] = AngleNormalize180( attAngles[YAW] + 180);
	defAngles[ROLL] = 0;
	SetClientViewAngle( defender, defAngles );

	//MATCH POSITIONS (as in 1.02 only the entity origin is set, the playerstate origin is not)
	diff = VectorNormalize( defDir ) - idealDist;//diff will be the total error in dist
	//try to move attacker half the diff towards the defender
	VectorMA( attacker->r.currentOrigin, diff*0.5f, defDir, newOrg );

	trap->Trace( &trace, attacker->r.currentOrigin, attacker->r.mins, attacker->r.maxs, newOrg, attacker->s.number, attacker->clipmask, qfalse, 0, 0 );
	if ( !trace.startsolid && !trace.allsolid )
	{
		G_SetOrigin( attacker, trace.endpos );
		trap->LinkEntity( (sharedEntity_t *)attacker );
	}
	//now get the defender's dist and do it for him too
	VectorSubtract( attacker->r.currentOrigin, defender->r.currentOrigin, attDir );
	diff = VectorNormalize( attDir ) - idealDist;//diff will be the total error in dist
	//try to move defender all of the remaining diff towards the attacker
	VectorMA( defender->r.currentOrigin, diff, attDir, newOrg );
	trap->Trace( &trace, defender->r.currentOrigin, defender->r.mins, defender->r.maxs, newOrg, defender->s.number, defender->clipmask, qfalse, 0, 0 );
	if ( !trace.startsolid && !trace.allsolid )
	{
		G_SetOrigin( defender, trace.endpos );
		trap->LinkEntity( (sharedEntity_t *)defender );
	}

	jk2SaberStatLocks++;

	//DONE!
	return qtrue;
}

#define JK2_TA(e) ((e)->client->ps.torsoAnim)

qboolean WP_SabersCheckLock_JK2( gentity_t *ent1, gentity_t *ent2 )
{
	float dist;
	qboolean	ent1BlockingPlayer = qfalse;
	qboolean	ent2BlockingPlayer = qfalse;

	if (!g_saberLocking.integer)
	{
		return qfalse;
	}

	if (!ent1->client || !ent2->client)
	{
		return qfalse;
	}

	if (!ent1->client->ps.duelInProgress ||
		!ent2->client->ps.duelInProgress ||
		ent1->client->ps.duelIndex != ent2->s.number ||
		ent2->client->ps.duelIndex != ent1->s.number)
	{ //only allow saber locking if two players are dueling with each other directly
		if (level.gametype != GT_DUEL)
		{
			return qfalse;
		}
	}

	if ( fabs( ent1->r.currentOrigin[2]-ent2->r.currentOrigin[2] ) > 16 )
	{
		return qfalse;
	}
	if ( ent1->client->ps.groundEntityNum == ENTITYNUM_NONE ||
		ent2->client->ps.groundEntityNum == ENTITYNUM_NONE )
	{
		return qfalse;
	}
	dist = DistanceSquared(ent1->r.currentOrigin,ent2->r.currentOrigin);
	if ( dist < 64 || dist > 6400 )
	{//between 8 and 80 from each other
		return qfalse;
	}

	if (BG_InSpecialJump(ent1->client->ps.legsAnim))
	{
		return qfalse;
	}
	if (BG_InSpecialJump(ent2->client->ps.legsAnim))
	{
		return qfalse;
	}

	if (BG_InRoll(&ent1->client->ps, ent1->client->ps.legsAnim))
	{
		return qfalse;
	}
	if (BG_InRoll(&ent2->client->ps, ent2->client->ps.legsAnim))
	{
		return qfalse;
	}

	if (ent1->client->ps.forceHandExtend != HANDEXTEND_NONE ||
		ent2->client->ps.forceHandExtend != HANDEXTEND_NONE)
	{
		return qfalse;
	}

	if ((ent1->client->ps.pm_flags & PMF_DUCKED) ||
		(ent2->client->ps.pm_flags & PMF_DUCKED))
	{
		return qfalse;
	}

	if (!InFront( ent1->client->ps.origin, ent2->client->ps.origin, ent2->client->ps.viewangles, 0.4f ))
	{
		return qfalse;
	}
	if (!InFront( ent2->client->ps.origin, ent1->client->ps.origin, ent1->client->ps.viewangles, 0.4f ))
	{
		return qfalse;
	}

	//T to B lock
	if ( JK2_TA(ent1) == BOTH_A1_T__B_ ||
		JK2_TA(ent1) == BOTH_A2_T__B_ ||
		JK2_TA(ent1) == BOTH_A3_T__B_ ||
		JK2_TA(ent1) == BOTH_A4_T__B_ ||
		JK2_TA(ent1) == BOTH_A5_T__B_ )
	{//ent1 is attacking top-down
		return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_TOP );
	}

	if ( JK2_TA(ent2) == BOTH_A1_T__B_ ||
		JK2_TA(ent2) == BOTH_A2_T__B_ ||
		JK2_TA(ent2) == BOTH_A3_T__B_ ||
		JK2_TA(ent2) == BOTH_A4_T__B_ ||
		JK2_TA(ent2) == BOTH_A5_T__B_ )
	{//ent2 is attacking top-down
		return WP_SabersCheckLock2_JK2( ent2, ent1, JK2LOCK_TOP );
	}

	//1.02 (all JK2 versions): an SP leftover that favours client 0, kept as it was
	if ( ent1->s.number == 0 &&
		ent1->client->ps.saberBlocking == BLK_WIDE && ent1->client->ps.weaponTime <= 0 )
	{
		ent1BlockingPlayer = qtrue;
	}
	if ( ent2->s.number == 0 &&
		ent2->client->ps.saberBlocking == BLK_WIDE && ent2->client->ps.weaponTime <= 0 )
	{
		ent2BlockingPlayer = qtrue;
	}

	//TR to BL lock
	if ( JK2_TA(ent1) == BOTH_A1_TR_BL ||
		JK2_TA(ent1) == BOTH_A2_TR_BL ||
		JK2_TA(ent1) == BOTH_A3_TR_BL ||
		JK2_TA(ent1) == BOTH_A4_TR_BL ||
		JK2_TA(ent1) == BOTH_A5_TR_BL )
	{//ent1 is attacking diagonally
		if ( ent2BlockingPlayer )
		{//player will block this anyway
			return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_DIAG_TR );
		}
		if ( JK2_TA(ent2) == BOTH_A1_TR_BL ||
			JK2_TA(ent2) == BOTH_A2_TR_BL ||
			JK2_TA(ent2) == BOTH_A3_TR_BL ||
			JK2_TA(ent2) == BOTH_A4_TR_BL ||
			JK2_TA(ent2) == BOTH_A5_TR_BL ||
			JK2_TA(ent2) == BOTH_P1_S1_TL )
		{//ent2 is attacking in the opposite diagonal
			return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_DIAG_TR );
		}
		if ( JK2_TA(ent2) == BOTH_A1_BR_TL ||
			JK2_TA(ent2) == BOTH_A2_BR_TL ||
			JK2_TA(ent2) == BOTH_A3_BR_TL ||
			JK2_TA(ent2) == BOTH_A4_BR_TL ||
			JK2_TA(ent2) == BOTH_A5_BR_TL ||
			JK2_TA(ent2) == BOTH_P1_S1_BL )
		{//ent2 is attacking in the opposite diagonal
			return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_DIAG_BL );
		}
		return qfalse;
	}

	if ( JK2_TA(ent2) == BOTH_A1_TR_BL ||
		JK2_TA(ent2) == BOTH_A2_TR_BL ||
		JK2_TA(ent2) == BOTH_A3_TR_BL ||
		JK2_TA(ent2) == BOTH_A4_TR_BL ||
		JK2_TA(ent2) == BOTH_A5_TR_BL )
	{//ent2 is attacking diagonally
		if ( ent1BlockingPlayer )
		{//player will block this anyway
			return WP_SabersCheckLock2_JK2( ent2, ent1, JK2LOCK_DIAG_TR );
		}
		if ( JK2_TA(ent1) == BOTH_A1_TR_BL ||
			JK2_TA(ent1) == BOTH_A2_TR_BL ||
			JK2_TA(ent1) == BOTH_A3_TR_BL ||
			JK2_TA(ent1) == BOTH_A4_TR_BL ||
			JK2_TA(ent1) == BOTH_A5_TR_BL ||
			JK2_TA(ent1) == BOTH_P1_S1_TL )
		{//ent1 is attacking in the opposite diagonal
			return WP_SabersCheckLock2_JK2( ent2, ent1, JK2LOCK_DIAG_TR );
		}
		if ( JK2_TA(ent1) == BOTH_A1_BR_TL ||
			JK2_TA(ent1) == BOTH_A2_BR_TL ||
			JK2_TA(ent1) == BOTH_A3_BR_TL ||
			JK2_TA(ent1) == BOTH_A4_BR_TL ||
			JK2_TA(ent1) == BOTH_A5_BR_TL ||
			JK2_TA(ent1) == BOTH_P1_S1_BL )
		{//ent1 is attacking in the opposite diagonal
			return WP_SabersCheckLock2_JK2( ent2, ent1, JK2LOCK_DIAG_BL );
		}
		return qfalse;
	}

	//TL to BR lock
	if ( JK2_TA(ent1) == BOTH_A1_TL_BR ||
		JK2_TA(ent1) == BOTH_A2_TL_BR ||
		JK2_TA(ent1) == BOTH_A3_TL_BR ||
		JK2_TA(ent1) == BOTH_A4_TL_BR ||
		JK2_TA(ent1) == BOTH_A5_TL_BR )
	{//ent1 is attacking diagonally
		if ( ent2BlockingPlayer )
		{//player will block this anyway
			return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_DIAG_TL );
		}
		if ( JK2_TA(ent2) == BOTH_A1_TL_BR ||
			JK2_TA(ent2) == BOTH_A2_TL_BR ||
			JK2_TA(ent2) == BOTH_A3_TL_BR ||
			JK2_TA(ent2) == BOTH_A4_TL_BR ||
			JK2_TA(ent2) == BOTH_A5_TL_BR ||
			JK2_TA(ent2) == BOTH_P1_S1_TR )
		{//ent2 is attacking in the opposite diagonal
			return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_DIAG_TL );
		}
		if ( JK2_TA(ent2) == BOTH_A1_BL_TR ||
			JK2_TA(ent2) == BOTH_A2_BL_TR ||
			JK2_TA(ent2) == BOTH_A3_BL_TR ||
			JK2_TA(ent2) == BOTH_A4_BL_TR ||
			JK2_TA(ent2) == BOTH_A5_BL_TR ||
			JK2_TA(ent2) == BOTH_P1_S1_BR )
		{//ent2 is attacking in the opposite diagonal
			return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_DIAG_BR );
		}
		return qfalse;
	}

	if ( JK2_TA(ent2) == BOTH_A1_TL_BR ||
		JK2_TA(ent2) == BOTH_A2_TL_BR ||
		JK2_TA(ent2) == BOTH_A3_TL_BR ||
		JK2_TA(ent2) == BOTH_A4_TL_BR ||
		JK2_TA(ent2) == BOTH_A5_TL_BR )
	{//ent2 is attacking diagonally
		if ( ent1BlockingPlayer )
		{//player will block this anyway
			return WP_SabersCheckLock2_JK2( ent2, ent1, JK2LOCK_DIAG_TL );
		}
		if ( JK2_TA(ent1) == BOTH_A1_TL_BR ||
			JK2_TA(ent1) == BOTH_A2_TL_BR ||
			JK2_TA(ent1) == BOTH_A3_TL_BR ||
			JK2_TA(ent1) == BOTH_A4_TL_BR ||
			JK2_TA(ent1) == BOTH_A5_TL_BR ||
			JK2_TA(ent1) == BOTH_P1_S1_TR )
		{//ent1 is attacking in the opposite diagonal
			return WP_SabersCheckLock2_JK2( ent2, ent1, JK2LOCK_DIAG_TL );
		}
		if ( JK2_TA(ent1) == BOTH_A1_BL_TR ||
			JK2_TA(ent1) == BOTH_A2_BL_TR ||
			JK2_TA(ent1) == BOTH_A3_BL_TR ||
			JK2_TA(ent1) == BOTH_A4_BL_TR ||
			JK2_TA(ent1) == BOTH_A5_BL_TR ||
			JK2_TA(ent1) == BOTH_P1_S1_BR )
		{//ent1 is attacking in the opposite diagonal
			return WP_SabersCheckLock2_JK2( ent2, ent1, JK2LOCK_DIAG_BR );
		}
		return qfalse;
	}
	//L to R lock
	if ( JK2_TA(ent1) == BOTH_A1__L__R ||
		JK2_TA(ent1) == BOTH_A2__L__R ||
		JK2_TA(ent1) == BOTH_A3__L__R ||
		JK2_TA(ent1) == BOTH_A4__L__R ||
		JK2_TA(ent1) == BOTH_A5__L__R )
	{//ent1 is attacking l to r
		if ( ent2BlockingPlayer )
		{//player will block this anyway
			return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_L );
		}
		if ( JK2_TA(ent2) == BOTH_A1_TL_BR ||
			JK2_TA(ent2) == BOTH_A2_TL_BR ||
			JK2_TA(ent2) == BOTH_A3_TL_BR ||
			JK2_TA(ent2) == BOTH_A4_TL_BR ||
			JK2_TA(ent2) == BOTH_A5_TL_BR ||
			JK2_TA(ent2) == BOTH_P1_S1_TR ||
			JK2_TA(ent2) == BOTH_P1_S1_BL )
		{//ent2 is attacking or blocking on the r
			return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_L );
		}
		return qfalse;
	}
	if ( JK2_TA(ent2) == BOTH_A1__L__R ||
		JK2_TA(ent2) == BOTH_A2__L__R ||
		JK2_TA(ent2) == BOTH_A3__L__R ||
		JK2_TA(ent2) == BOTH_A4__L__R ||
		JK2_TA(ent2) == BOTH_A5__L__R )
	{//ent2 is attacking l to r
		if ( ent1BlockingPlayer )
		{//player will block this anyway
			return WP_SabersCheckLock2_JK2( ent2, ent1, JK2LOCK_L );
		}
		if ( JK2_TA(ent1) == BOTH_A1_TL_BR ||
			JK2_TA(ent1) == BOTH_A2_TL_BR ||
			JK2_TA(ent1) == BOTH_A3_TL_BR ||
			JK2_TA(ent1) == BOTH_A4_TL_BR ||
			JK2_TA(ent1) == BOTH_A5_TL_BR ||
			JK2_TA(ent1) == BOTH_P1_S1_TR ||
			JK2_TA(ent1) == BOTH_P1_S1_BL )
		{//ent1 is attacking or blocking on the r
			return WP_SabersCheckLock2_JK2( ent2, ent1, JK2LOCK_L );
		}
		return qfalse;
	}
	//R to L lock
	if ( JK2_TA(ent1) == BOTH_A1__R__L ||
		JK2_TA(ent1) == BOTH_A2__R__L ||
		JK2_TA(ent1) == BOTH_A3__R__L ||
		JK2_TA(ent1) == BOTH_A4__R__L ||
		JK2_TA(ent1) == BOTH_A5__R__L )
	{//ent1 is attacking r to l
		if ( ent2BlockingPlayer )
		{//player will block this anyway
			return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_R );
		}
		if ( JK2_TA(ent2) == BOTH_A1_TR_BL ||
			JK2_TA(ent2) == BOTH_A2_TR_BL ||
			JK2_TA(ent2) == BOTH_A3_TR_BL ||
			JK2_TA(ent2) == BOTH_A4_TR_BL ||
			JK2_TA(ent2) == BOTH_A5_TR_BL ||
			JK2_TA(ent2) == BOTH_P1_S1_TL ||
			JK2_TA(ent2) == BOTH_P1_S1_BR )
		{//ent2 is attacking or blocking on the l
			return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_R );
		}
		return qfalse;
	}
	if ( JK2_TA(ent2) == BOTH_A1__R__L ||
		JK2_TA(ent2) == BOTH_A2__R__L ||
		JK2_TA(ent2) == BOTH_A3__R__L ||
		JK2_TA(ent2) == BOTH_A4__R__L ||
		JK2_TA(ent2) == BOTH_A5__R__L )
	{//ent2 is attacking r to l
		if ( ent1BlockingPlayer )
		{//player will block this anyway
			return WP_SabersCheckLock2_JK2( ent2, ent1, JK2LOCK_R );
		}
		if ( JK2_TA(ent1) == BOTH_A1_TR_BL ||
			JK2_TA(ent1) == BOTH_A2_TR_BL ||
			JK2_TA(ent1) == BOTH_A3_TR_BL ||
			JK2_TA(ent1) == BOTH_A4_TR_BL ||
			JK2_TA(ent1) == BOTH_A5_TR_BL ||
			JK2_TA(ent1) == BOTH_P1_S1_TL ||
			JK2_TA(ent1) == BOTH_P1_S1_BR )
		{//ent1 is attacking or blocking on the l
			return WP_SabersCheckLock2_JK2( ent2, ent1, JK2LOCK_R );
		}
		return qfalse;
	}
	if ( !Q_irand( 0, 10 ) )
	{
		return WP_SabersCheckLock2_JK2( ent1, ent2, JK2LOCK_RANDOM );
	}
	return qfalse;
}

/*
=============================================================================

Blocking (mv w_saber.c:WP_SaberCanBlock, 1.02 path)

=============================================================================
*/

int WP_SaberCanBlock_JK2( gentity_t *self, vec3_t point, int dflags, int mod, qboolean projectile, int attackStr )
{
	qboolean thrownSaber = qfalse;
	float blockFactor = 0;

	if (!self || !self->client || !point)
	{
		{ jk2BlockFail = 1; return 0; }
	}

	if (attackStr == 8 || attackStr == 999)
	{ //thrown saber (8 in JK2, 999 in our JKA thrown-saber code)
		attackStr = 0;
		thrownSaber = qtrue;
	}

	if (BG_SaberInAttack_JK2(self->client->ps.saberMove))
	{
		{ jk2BlockFail = 2; return 0; }
	}

	if (PM_InSaberAnim(self->client->ps.torsoAnim) && !self->client->ps.saberBlocked &&
		self->client->ps.saberMove != LS_READY && self->client->ps.saberMove != LS_NONE)
	{
		if ( self->client->ps.saberMove < LS_PARRY_UP || self->client->ps.saberMove > LS_REFLECT_LL )
		{
			{ jk2BlockFail = 3; return 0; }
		}
	}

	//1.02: no broken parry check

	if (self->client->ps.saberHolstered)
	{
		{ jk2BlockFail = 4; return 0; }
	}

	if (self->client->ps.weapon != WP_SABER)
	{
		{ jk2BlockFail = 5; return 0; }
	}

	if (self->client->ps.weaponstate == WEAPON_RAISING)
	{
		{ jk2BlockFail = 6; return 0; }
	}

	if (self->client->ps.saberInFlight)
	{
		{ jk2BlockFail = 7; return 0; }
	}

	if ((self->client->pers.cmd.buttons & BUTTON_ATTACK))
	{ //don't block when the player is trying to slash, if it's a projectile or he's doing a very strong attack
		{ jk2BlockFail = 8; return 0; }
	}

	//This is how blocks were decided before the 1.03 patch
	if (attackStr == FORCE_LEVEL_3)
	{
		if (self->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE] >= FORCE_LEVEL_3)
		{
			if (Q_irand(1, 10) < 3)
			{
				{ jk2BlockFail = 9; return 0; }
			}
		}
		else
		{
			{ jk2BlockFail = 10; return 0; }
		}
	}

	if (attackStr == FORCE_LEVEL_2 && Q_irand(1, 10) < 3)
	{
		if (self->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE] >= FORCE_LEVEL_3)
		{
			//do nothing for now
		}
		else if (self->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE] >= FORCE_LEVEL_2)
		{
			if (Q_irand(1, 10) < 5)
			{
				{ jk2BlockFail = 11; return 0; }
			}
		}
		else
		{
			{ jk2BlockFail = 12; return 0; }
		}
	}

	if (attackStr == FORCE_LEVEL_1 && !self->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE] &&
		Q_irand(1, 40) < 3)
	{ //if I have no defense level at all then I might be unable to block a level 1 attack (but very rarely)
		{ jk2BlockFail = 13; return 0; }
	}

	if (BG_SaberInAttack_JK2(self->client->ps.saberMove))
	{ //attacking, can't block now (1.02 SaberAttacking)
		{ jk2BlockFail = 14; return 0; }
	}

	if (self->client->ps.saberMove != LS_READY &&
		!self->client->ps.saberBlocking)
	{
		{ jk2BlockFail = 15; return 0; }
	}

	if (self->client->ps.saberBlockTime >= level.time)
	{
		{ jk2BlockFail = 16; return 0; }
	}

	if (self->client->ps.forceHandExtend != HANDEXTEND_NONE)
	{
		{ jk2BlockFail = 17; return 0; }
	}

	if (self->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE] == FORCE_LEVEL_3)
	{
		blockFactor = 0.05f;
	}
	else if (self->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE] == FORCE_LEVEL_2)
	{
		blockFactor = 0.6f;
	}
	else if (self->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE] == FORCE_LEVEL_1)
	{
		blockFactor = 0.9f;
	}
	else
	{ //for now we just don't get to autoblock with no def
		{ jk2BlockFail = 18; return 0; }
	}

	if (thrownSaber)
	{
		blockFactor -= 0.25f;
	}

	//1.02: no extra -0.25 for blocking a saber

	if (!InFront( point, self->client->ps.origin, self->client->ps.viewangles, blockFactor )) //orig 0.2f
	{
		{ jk2BlockFail = 19; return 0; }
	}

	//1.02: every successful block sets the parry
	WP_SaberBlockNonRandom(self, point, projectile);
	return 1;
}

/*
=============================================================================

Damage (mv w_saber.c:CheckSaberDamage_1_02)

=============================================================================
*/

static qboolean JK2_SaberAttacking( gentity_t *self )
{ //mv w_saber.c:SaberAttacking, 1.02
	return BG_SaberInAttack_JK2( self->client->ps.saberMove );
}

static void JK2_BlockTE( gentity_t *te )
{ //our JKA EV_SABER_BLOCK/EV_SABER_HIT handlers also read the saber and blade number
	te->s.weapon = 0;//saberNum
	te->s.legsAnim = 0;//bladeNum
}

static qboolean CheckSaberDamage_JK2( gentity_t *self, vec3_t saberStart, vec3_t saberEnd, qboolean doInterpolate )
{
	trace_t tr;
	vec3_t dir;
	int dmg = 0;
	int attackStr = 0;
	qboolean idleDamage = qfalse;
	qboolean didHit = qfalse;

	if (self->client->ps.saberHolstered)
	{
		return qfalse;
	}

	if (doInterpolate)
	{ //This didn't quite work out like I hoped. But it's better than nothing. Sort of.
	  //(1.02: the old saber position is computed but never used for the trace, so it is left out here)
		vec3_t saberDif;
		int traceTests = 0;
		float trDif = 8;

		VectorSubtract(saberStart, saberEnd, saberDif);
		VectorNormalize(saberDif);

		saberEnd[0] = saberStart[0] - (saberDif[0]*trDif);
		saberEnd[1] = saberStart[1] - (saberDif[1]*trDif);
		saberEnd[2] = saberStart[2] - (saberDif[2]*trDif);

		JP_Trace(&tr, saberEnd, NULL, NULL, saberStart, self->s.number, (MASK_PLAYERSOLID|CONTENTS_LIGHTSABER), qfalse, 0, 0);

		trDif++;

		while (tr.fraction == 1.0 && traceTests < 4 && tr.entityNum >= ENTITYNUM_NONE)
		{
			VectorSubtract(saberStart, saberEnd, saberDif);
			VectorNormalize(saberDif);

			saberEnd[0] = saberStart[0] - (saberDif[0]*trDif);
			saberEnd[1] = saberStart[1] - (saberDif[1]*trDif);
			saberEnd[2] = saberStart[2] - (saberDif[2]*trDif);

			JP_Trace(&tr, saberEnd, NULL, NULL, saberStart, self->s.number, (MASK_PLAYERSOLID|CONTENTS_LIGHTSABER), qfalse, 0, 0);

			traceTests++;
			trDif += 8;
		}
	}
	else
	{
		JP_Trace(&tr, saberStart, NULL, NULL, saberEnd, self->s.number, (MASK_PLAYERSOLID|CONTENTS_LIGHTSABER), qfalse, 0, 0);
	}

	if (JK2_SaberAttacking(self) &&
		self->client->ps.saberAttackWound < level.time)
	{ //this animation is that of the last attack movement, and so it should do full damage
		dmg = JK2_SABER_HITDAMAGE;//*self->client->ps.fd.saberAnimLevel;

		if (self->client->ps.fd.saberAnimLevel == 3)
		{
			dmg = 100;
		}
		else if (self->client->ps.fd.saberAnimLevel == 2)
		{
			dmg = 60;
		}

		attackStr = self->client->ps.fd.saberAnimLevel;
	}
	else if (self->client->ps.saberIdleWound < level.time)
	{ //just touching, do minimal damage and only check for it every 200ms (mainly to cut down on network traffic for hit events)
		dmg = 5;
		self->client->ps.saberIdleWound = level.time + 200;
		idleDamage = qtrue;
	}

	if (!dmg)
	{
		return qfalse;
	}

	if (dmg > 5 && self->client->ps.isJediMaster)
	{ //give the Jedi Master more saber attack power
		dmg *= 2;
	}

	VectorSubtract(saberEnd, saberStart, dir);
	VectorNormalize(dir);

	//rww - I'm saying || tr.startsolid here, because otherwise your saber tends to skip positions and go through
	//people, and the compensation traces start in their bbox too. Which results in the saber passing through people
	//when you visually cut right through them. Which sucks.

	if ((tr.fraction != 1 || tr.startsolid) &&
		tr.entityNum < ENTITYNUM_MAX_NORMAL &&
		g_entities[tr.entityNum].takedamage &&
		tr.entityNum != self->s.number)
	{
		gentity_t *te;
		qboolean unblockable = qfalse;

		if (idleDamage &&
			g_entities[tr.entityNum].client &&
			OnSameTeam(self, &g_entities[tr.entityNum]) &&
			!g_friendlySaber.integer)
		{
			return qfalse;
		}

		if (g_entities[tr.entityNum].inuse && g_entities[tr.entityNum].client &&
			g_entities[tr.entityNum].client->ps.duelInProgress &&
			g_entities[tr.entityNum].client->ps.duelIndex != self->s.number)
		{
			return qfalse;
		}

		if (g_entities[tr.entityNum].inuse && g_entities[tr.entityNum].client &&
			self->client->ps.duelInProgress &&
			self->client->ps.duelIndex != g_entities[tr.entityNum].s.number)
		{
			return qfalse;
		}

		didHit = qtrue;

		if (self->client->ps.saberMove == LS_A_BACK ||
			self->client->ps.saberMove == LS_A_BACK_CR ||
			self->client->ps.saberMove == LS_A_BACKSTAB ||
			self->client->ps.saberMove == LS_A_JUMP_T__B_)
		{
			unblockable = qtrue;
			if (self->client->ps.saberMove == LS_A_JUMP_T__B_)
			{ //do extra damage for special unblockables
				dmg += 40;
			}
			else
			{
				dmg += 20;
			}
		}

		jk2BlockFail = 0;
		if (g_entities[tr.entityNum].client && !unblockable && WP_SaberCanBlock_JK2(&g_entities[tr.entityNum], tr.endpos, 0, MOD_SABER, qfalse, attackStr))
		{
			te = G_TempEntity( tr.endpos, EV_SABER_BLOCK );
			VectorCopy(tr.endpos, te->s.origin);
			VectorCopy(tr.plane.normal, te->s.angles);
			te->s.eventParm = 1;
			JK2_BlockTE(te);

			jk2SaberStatBlocks++;
			if (tr.entityNum < MAX_CLIENTS && self->s.number < MAX_CLIENTS)
			{
				jk2StatBlockTime[tr.entityNum] = level.time;
				jk2StatBlocks[tr.entityNum]++;
				jk2StatGotBlocked[self->s.number]++;
			}

			if (dmg > 5)
			{
				if ((g_entities[tr.entityNum].client->ps.fd.forcePowerLevel[FP_SABER_OFFENSE] - self->client->ps.fd.forcePowerLevel[FP_SABER_OFFENSE]) > 1 &&
					Q_irand(1, 10) < 9) //used to be < 7
				{ //Just got blocked by someone with a decently higher attack level, so enter into a lock (where they have the advantage due to a higher attack lev)
					if (WP_SabersCheckLock_JK2(self, &g_entities[tr.entityNum]))
					{
						self->client->ps.saberBlocked = BLOCKED_NONE;
						g_entities[tr.entityNum].client->ps.saberBlocked = BLOCKED_NONE;
						return didHit;
					}
				}
				else if (Q_irand(1, 10) < 3)
				{ //Just got blocked by someone with a decently higher attack level, so enter into a lock (where they have the advantage due to a higher attack lev)
					if (WP_SabersCheckLock_JK2(self, &g_entities[tr.entityNum]))
					{
						self->client->ps.saberBlocked = BLOCKED_NONE;
						g_entities[tr.entityNum].client->ps.saberBlocked = BLOCKED_NONE;
						return didHit;
					}
				}
			}

			//our attack was blocked, so bounce back?
			if (dmg > 5)
			{
				self->client->ps.weaponTime = 0;
				self->client->ps.weaponstate = WEAPON_READY;
				self->client->ps.saberBlocked = BLOCKED_ATK_BOUNCE;

				self->client->ps.saberBlockTime = level.time + (350 - (self->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE]*100));//300;
				jk2SaberStatBounces++;
			}
			self->client->ps.saberAttackWound = level.time + 300;

			if (self->client->ps.fd.saberAnimLevel >= FORCE_LEVEL_3 && dmg > 5 && g_entities[tr.entityNum].client->ps.saberMove != LS_READY && g_entities[tr.entityNum].client->ps.saberMove != LS_NONE)
			{
				g_entities[tr.entityNum].client->ps.weaponTime = 0;
				g_entities[tr.entityNum].client->ps.weaponstate = WEAPON_READY;
				g_entities[tr.entityNum].client->ps.saberBlocked = BLOCKED_ATK_BOUNCE;

				g_entities[tr.entityNum].client->ps.saberBlockTime = level.time + (350 - (g_entities[tr.entityNum].client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE]*100));//300;
			}

			//NOTE: Actual blocking is handled in WP_SaberCanBlock
		}
		else
		{
			//(JK2 cut the damage to an ATST pilot to 0.1; there are no ATST players here)

			if (g_entities[tr.entityNum].client && !g_entities[tr.entityNum].client->ps.fd.forcePowerLevel[FP_SABER_OFFENSE])
			{ //not a "jedi", so make them suffer more
				if (dmg > 5)
				{ //don't bother increasing just for idle touch damage
					dmg *= 1.5;
				}
			}

			if (dmg > 5)
			{
				jk2SaberStatHits++;
				if (tr.entityNum < MAX_CLIENTS && self->s.number < MAX_CLIENTS)
				{
					jk2StatHitTime[self->s.number] = level.time;
					jk2StatHitMove[self->s.number] = self->client->ps.saberMove;
					jk2StatHitVictim[self->s.number] = tr.entityNum;
					jk2StatHitsDealt[self->s.number]++;
					jk2StatHitsTaken[tr.entityNum]++;
					if (jk2BotGuardFrame[tr.entityNum] && jk2BotGuardFrame[tr.entityNum] >= level.time - 100 && jk2BlockFail >= 0 && jk2BlockFail < 20)
					{
						jk2GuardFail[jk2BlockFail]++;
					}
				}
			}
			else
			{
				jk2SaberStatTouches++;
			}

			G_Damage(&g_entities[tr.entityNum], self, self, dir, tr.endpos, dmg, 0, MOD_SABER);

			te = G_TempEntity( tr.endpos, EV_SABER_HIT );
			VectorCopy(tr.endpos, te->s.origin);
			VectorCopy(tr.plane.normal, te->s.angles);
			JK2_BlockTE(te);

			if (!te->s.angles[0] && !te->s.angles[1] && !te->s.angles[2])
			{ //don't let it play with no direction
				te->s.angles[1] = 1;
			}

			if (g_entities[tr.entityNum].client)
			{
				te->s.eventParm = 1;
			}
			else
			{
				te->s.eventParm = 0;
			}

			self->client->ps.saberAttackWound = level.time + 100;
		}
	}
	else if ((tr.fraction != 1 || tr.startsolid) &&
		tr.entityNum < ENTITYNUM_MAX_NORMAL &&
		(g_entities[tr.entityNum].r.contents & CONTENTS_LIGHTSABER) &&
		g_entities[tr.entityNum].r.contents != -1)
	{ //saber clash
		gentity_t *te;
		gentity_t *otherOwner = &g_entities[g_entities[tr.entityNum].r.ownerNum];

		if (otherOwner &&
			otherOwner->inuse &&
			otherOwner->client &&
			OnSameTeam(self, otherOwner) &&
			!g_friendlySaber.integer)
		{
			return qfalse;
		}

		if (otherOwner && otherOwner->client &&
			otherOwner->client->ps.duelInProgress &&
			otherOwner->client->ps.duelIndex != self->s.number)
		{
			return qfalse;
		}

		if (otherOwner && otherOwner->client &&
			self->client->ps.duelInProgress &&
			self->client->ps.duelIndex != otherOwner->s.number)
		{
			return qfalse;
		}

		didHit = qtrue;
		jk2SaberStatClashes++;

		te = G_TempEntity( tr.endpos, EV_SABER_BLOCK );

		VectorCopy(tr.endpos, te->s.origin);
		VectorCopy(tr.plane.normal, te->s.angles);
		te->s.eventParm = 1;
		JK2_BlockTE(te);

		if (otherOwner && otherOwner->client && otherOwner->client->ps.saberInFlight)
		{
			return qfalse;
		}

		if (self->client->ps.fd.saberAnimLevel < FORCE_LEVEL_3)
		{
			self->client->ps.weaponTime = 0;
			self->client->ps.weaponstate = WEAPON_READY;
			self->client->ps.saberBlocked = BLOCKED_ATK_BOUNCE;
			self->client->ps.saberBlockTime = level.time + (350 - (self->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE]*100));//300;
			jk2SaberStatBounces++;

			if (otherOwner && otherOwner->client)
			{
				if (otherOwner->client->ps.weaponTime < 1 || otherOwner->client->ps.fd.saberAnimLevel < FORCE_LEVEL_3)
				{
					WP_SaberCanBlock_JK2(otherOwner, tr.endpos, 0, MOD_SABER, qfalse, 1);
				}
			}
		}
		else if (otherOwner && otherOwner->client && otherOwner->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE] <= self->client->ps.fd.saberAnimLevel)
		{ //block
			if (otherOwner->client->ps.weaponTime < 1 || otherOwner->client->ps.fd.saberAnimLevel < FORCE_LEVEL_3)
			{
				if (WP_SaberCanBlock_JK2(otherOwner, tr.endpos, 0, MOD_SABER, qfalse, 1) && dmg > 5)
				{
					otherOwner->client->ps.weaponTime = 0;
					otherOwner->client->ps.weaponstate = WEAPON_READY;
					otherOwner->client->ps.saberBlocked = BLOCKED_ATK_BOUNCE;
					otherOwner->client->ps.saberBlockTime = level.time + (350 - (otherOwner->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE]*100));//300;
				}
			}
		}

		self->client->ps.saberAttackWound = level.time + 300;

		if (dmg > 5)
		{
			if (Q_irand(1, 10) < 9) //used to be < 7
			{
				if (otherOwner && otherOwner->client && WP_SabersCheckLock_JK2(self, otherOwner))
				{
					self->client->ps.saberBlocked = BLOCKED_NONE;
					otherOwner->client->ps.saberBlocked = BLOCKED_NONE;
					return didHit;
				}
			}
		}

		if (dmg > 5)
		{ //we clashed into this person's saber while attacking, so make them feel it too
			if (otherOwner && otherOwner->client && otherOwner->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE] <= self->client->ps.fd.saberAnimLevel)
			{
				otherOwner->client->ps.weaponTime = 0;
				otherOwner->client->ps.weaponstate = WEAPON_READY;
				otherOwner->client->ps.saberBlocked = BLOCKED_ATK_BOUNCE;

				self->client->ps.saberBlockTime = level.time + (350 - (self->client->ps.fd.forcePowerLevel[FP_SABER_DEFENSE]*100));//300; (sic, 1.02 sets the attacker's)

				otherOwner->client->ps.saberAttackWound = level.time + 300;
			}
		}
	}

	return didHit;
}

/*
=============================================================================

Hooks for WP_SaberPositionUpdate (mv w_saber.c:3488-3839, 1.02 path)

=============================================================================
*/

#define JK2_SABER_LENGTH	40.0f
#define JK2_SABER_BOX_SIZE	8.0f

// Blade end and saber entity box for the 1.02 single 40 unit blade from blade 0 of saber 0.
void WP_JK2SaberGeometry( gentity_t *self, gentity_t *mySaber, vec3_t boltOrigin, vec3_t boltDir, vec3_t end )
{
	VectorMA( boltOrigin, JK2_SABER_LENGTH, boltDir, end );

	if (mySaber && ((mySaber->r.contents & CONTENTS_LIGHTSABER) || mySaber->r.contents == 0) && !self->client->ps.saberInFlight)
	{ //place it roughly in the middle of the saber..
		VectorMA( boltOrigin, 20, boltDir, mySaber->r.currentOrigin );
	}
}

void WP_JK2SaberBox( gentity_t *saberent )
{
	VectorSet( saberent->r.mins, -JK2_SABER_BOX_SIZE, -JK2_SABER_BOX_SIZE, -JK2_SABER_BOX_SIZE );
	VectorSet( saberent->r.maxs, JK2_SABER_BOX_SIZE, JK2_SABER_BOX_SIZE, JK2_SABER_BOX_SIZE );
}

// The 1.02 damage traces (g_saberInterpolate default 1 = the "old plain method" in 1.02: a straight
// trace, and if it hits nothing the short "interpolate" traces along the blade).
void WP_JK2SaberDamage( gentity_t *self, vec3_t boltOrigin, vec3_t end )
{
	vec3_t	endCopy;

	if ( self->client->ps.saberInFlight || self->client->ps.saberHolstered )
	{
		return;
	}

	VectorCopy( end, endCopy ); //CheckSaberDamage_JK2 moves the end point in its interpolate path
	if ( self->client->hasCurrentPosition )
	{
		if ( !CheckSaberDamage_JK2( self, boltOrigin, endCopy, qfalse ) )
		{
			CheckSaberDamage_JK2( self, boltOrigin, endCopy, qtrue );
		}
	}
	else
	{
		CheckSaberDamage_JK2( self, boltOrigin, endCopy, qfalse );
	}
}

/*
=============================================================================

Staff/dual handling: JK2 had one single-bladed saber and three styles

=============================================================================
*/

qboolean G_SetSaber( gentity_t *ent, int saberNum, char *saberName, qboolean siegeOverride );

// Called every ClientThink while g_jk2_102sabersystem is on. A second saber or a multi-bladed
// saber is replaced by the default single saber, and the style is kept to blue/yellow/red within
// the player's saber offence level (JK2: styles cycle up to FP_SABERATTACK).
void G_JK2SaberCheckSingle( gentity_t *ent )
{
	gclient_t *client = ent->client;
	int maxLevel;

	if ( !client || ent->s.eType != ET_PLAYER || client->sess.sessionTeam == TEAM_SPECTATOR )
	{
		return;
	}

	if ( client->saber[1].model[0] || client->saber[0].numBlades > 1 || (client->saber[0].saberFlags & SFL_TWO_HANDED) )
	{
		char userinfo[MAX_INFO_STRING] = {0};

		G_LogPrintf( "JK2SABER: client %d (%s): saber %s + %s replaced by the single saber %s\n", (int)(ent-g_entities),
			client->pers.netname, client->saber[0].name, client->saber[1].model[0] ? client->saber[1].name : "none", DEFAULT_SABER );
		trap->GetUserinfo( ent-g_entities, userinfo, sizeof( userinfo ) );
		G_SetSaber( ent, 0, DEFAULT_SABER, qfalse );
		G_SetSaber( ent, 1, "none", qfalse );
		trap->SetUserinfo( ent-g_entities, userinfo );
		ClientUserinfoChanged( ent-g_entities );
		G_SaberModelSetup( ent );
		if ( client->ps.saberHolstered == 1 )
		{
			client->ps.saberHolstered = 0;
		}
	}

	maxLevel = client->ps.fd.forcePowerLevel[FP_SABER_OFFENSE];
	if ( maxLevel < FORCE_LEVEL_1 )
	{
		maxLevel = FORCE_LEVEL_1;
	}
	if ( maxLevel > FORCE_LEVEL_3 )
	{
		maxLevel = FORCE_LEVEL_3;
	}

	if ( client->ps.fd.saberAnimLevel < FORCE_LEVEL_1 || client->ps.fd.saberAnimLevel > maxLevel )
	{
		int lvl = client->ps.fd.saberAnimLevel;
		if ( lvl < FORCE_LEVEL_1 || lvl > FORCE_LEVEL_3 )
		{ //staff/dual/Desann/Tavion: use the closest JK2 style
			lvl = (lvl == SS_DESANN) ? FORCE_LEVEL_3 : (lvl == SS_STAFF ? FORCE_LEVEL_2 : FORCE_LEVEL_1);
		}
		if ( lvl > maxLevel )
		{
			lvl = maxLevel;
		}
		client->ps.fd.saberAnimLevel = client->ps.fd.saberDrawAnimLevel = client->ps.fd.saberAnimLevelBase = lvl;
	}
	if ( client->ps.fd.saberAnimLevelBase != client->ps.fd.saberAnimLevel && client->ps.weaponTime <= 0 )
	{
		client->ps.fd.saberAnimLevelBase = client->ps.fd.saberAnimLevel;
	}
	if ( client->saberCycleQueue && (client->saberCycleQueue < FORCE_LEVEL_1 || client->saberCycleQueue > maxLevel) )
	{
		client->saberCycleQueue = 0;
	}
}

// mv g_cmds.c:Cmd_SaberAttackCycle_f: blue -> yellow -> red, up to the saber offence level,
// queued while the saber is busy.
void Cmd_SaberAttackCycle_JK2( gentity_t *ent )
{
	int selectLevel = 0;

	if ( !ent || !ent->client )
	{
		return;
	}

	if (ent->client->saberCycleQueue)
	{ //resume off of the queue if we haven't gotten a chance to update it yet
		selectLevel = ent->client->saberCycleQueue;
	}
	else
	{
		selectLevel = ent->client->ps.fd.saberAnimLevel;
	}

	selectLevel++;
	if ( selectLevel > ent->client->ps.fd.forcePowerLevel[FP_SABER_OFFENSE] )
	{
		selectLevel = FORCE_LEVEL_1;
	}

	if (ent->client->ps.weaponTime <= 0)
	{ //not busy, set it now
		ent->client->ps.fd.saberAnimLevelBase = ent->client->ps.fd.saberAnimLevel = selectLevel;
	}
	else
	{ //can't set it now or we might cause unexpected chaining, so queue it
		ent->client->saberCycleQueue = selectLevel;
	}
	ent->client->sess.saberLevel = selectLevel;
}

// Totals for the bot profile output
void G_JK2SaberStats( char *buf, int bufSize )
{
	Com_sprintf( buf, bufSize, "JK2SABER hits %d touches %d blocked %d clashes %d bounces %d locks %d",
		jk2SaberStatHits, jk2SaberStatTouches, jk2SaberStatBlocks, jk2SaberStatClashes, jk2SaberStatBounces, jk2SaberStatLocks );
}
