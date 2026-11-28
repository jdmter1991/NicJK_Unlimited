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

// bg_saber_jk2.c -- JK2 1.02 saber system (g_jk2_102sabersystem), shared by game and cgame.
//
// Ported from mvsdk code/game/bg_saber.c, bg_pmove.c and bg_panimate.c, taking only the
// "jk2gameplay == VERSION_1_02" branches. Logic and values are copied as they are; the only
// changes are the JKA API differences (no ANIM_TOGGLEBIT, PM_SetAnim without blendTime,
// pm->bgClients -> PM_BGEntForNum, saberActive -> saberHolstered). Everything here only runs
// when JK2SABER() is true; with g_jk2_102sabersystem 0 nothing in this file is called.

#include "qcommon/q_shared.h"
#include "bg_public.h"
#include "bg_local.h"

// declared before use (GCC/Clang reject implicit declarations)
extern void BG_SetAnim(playerState_t *ps, animation_t *animations, int setAnimParts, int anim, int setAnimFlags);

#if defined(_GAME)
	#include "g_local.h"
#elif defined(_CGAME)
	#include "cgame/cg_local.h"
#endif

extern saberMoveData_t saberMoveData[LS_MOVE_MAX];
extern int transitionMove[Q_NUM_QUADS][Q_NUM_QUADS];

int PM_irand_timesync( int val1, int val2 );
int PM_SaberMoveQuadrantForMovement( usercmd_t *ucmd );
qboolean PM_SaberInBounce( int move );
qboolean PM_SaberInTransition( int move );
qboolean PM_SaberInParry( int move );
qboolean PM_SaberInReflect( int move );
qboolean BG_SaberInIdle( int move );
qboolean BG_InSaberStandAnim( int anim );
qboolean BG_InSpecialJump( int anim );
qboolean BG_InRoll( playerState_t *ps, int anim );
qboolean BG_InDeathAnim( int anim );
qboolean PM_InKnockDown( playerState_t *ps );
qboolean PM_SpinningAnim( int anim );
int PM_AnimLength( int index, animNumber_t anim );
float PM_GroundDistance( void );
qboolean BG_HasYsalamiri( int gametype, playerState_t *ps );
bgEntity_t *PM_BGEntForNum( int num );
extern int forcePowerNeeded[NUM_FORCE_POWER_LEVELS][NUM_FORCE_POWERS];

/*
=============================================================================

1.02 helpers (mv bg_panimate.c / bg_saber.c)

=============================================================================
*/

// mv bg_panimate.c:BG_SaberInAttack
qboolean BG_SaberInAttack_JK2( int move )
{
	if ( move >= LS_A_TL2BR && move <= LS_A_T2B )
	{
		return qtrue;
	}
	switch ( move )
	{
	case LS_A_BACK:
	case LS_A_BACK_CR:
	case LS_A_BACKSTAB:
	case LS_A_LUNGE:
	case LS_A_JUMP_T__B_:
	case LS_A_FLIP_STAB:
	case LS_A_FLIP_SLASH:
		return qtrue;
		break;
	}
	return qfalse;
}

// mv bg_panimate.c:BG_SaberInSpecial
qboolean BG_SaberInSpecial_JK2( int move )
{
	switch( move )
	{
	case LS_A_BACK:
	case LS_A_BACK_CR:
	case LS_A_BACKSTAB:
	case LS_A_LUNGE:
	case LS_A_JUMP_T__B_:
	case LS_A_FLIP_STAB:
	case LS_A_FLIP_SLASH:
		return qtrue;
	}
	return qfalse;
}

// mv bg_panimate.c:BG_FlippingAnim (JK2 list)
qboolean BG_FlippingAnim_JK2( int anim )
{
	switch ( anim )
	{
	case BOTH_FLIP_F:			//# Flip forward
	case BOTH_FLIP_B:			//# Flip backwards
	case BOTH_FLIP_L:			//# Flip left
	case BOTH_FLIP_R:			//# Flip right
	case BOTH_WALL_RUN_RIGHT_FLIP:
	case BOTH_WALL_RUN_LEFT_FLIP:
	case BOTH_WALL_FLIP_RIGHT:
	case BOTH_WALL_FLIP_LEFT:
	case BOTH_FLIP_BACK1:
	case BOTH_FLIP_BACK2:
	case BOTH_FLIP_BACK3:
	case BOTH_WALL_FLIP_BACK1:
	//Not really flips, but...
	case BOTH_WALL_RUN_RIGHT:
	case BOTH_WALL_RUN_LEFT:
	case BOTH_WALL_RUN_RIGHT_STOP:
	case BOTH_WALL_RUN_LEFT_STOP:
	case BOTH_BUTTERFLY_LEFT:
	case BOTH_BUTTERFLY_RIGHT:
	//
	case BOTH_ARIAL_LEFT:
	case BOTH_ARIAL_RIGHT:
	case BOTH_ARIAL_F1:
	case BOTH_CARTWHEEL_LEFT:
	case BOTH_CARTWHEEL_RIGHT:
	case BOTH_JUMPFLIPSLASHDOWN1:
	case BOTH_JUMPFLIPSTABDOWN:
		return qtrue;
		break;
	}
	return qfalse;
}

// mv bg_panimate.c:BG_SpinningSaberAnim (JK2 list)
qboolean BG_SpinningSaberAnim_JK2( int anim )
{
	switch ( anim )
	{
	//level 1 - FIXME: level 1 will have *no* spins
	case BOTH_T1_BR_BL:
	case BOTH_T1__R__L:
	case BOTH_T1__R_BL:
	case BOTH_T1_TR_BL:
	case BOTH_T1_BR_TL:
	case BOTH_T1_BR__L:
	case BOTH_T1_TL_BR:
	case BOTH_T1__L_BR:
	case BOTH_T1__L__R:
	case BOTH_T1_BL_BR:
	case BOTH_T1_BL__R:
	case BOTH_T1_BL_TR:
	//level 2
	case BOTH_T2_BR__L:
	case BOTH_T2_BR_BL:
	case BOTH_T2__R_BL:
	case BOTH_T2__L_BR:
	case BOTH_T2_BL_BR:
	case BOTH_T2_BL__R:
	//level 3
	case BOTH_T3_BR__L:
	case BOTH_T3_BR_BL:
	case BOTH_T3__R_BL:
	case BOTH_T3__L_BR:
	case BOTH_T3_BL_BR:
	case BOTH_T3_BL__R:
	//level 4
	case BOTH_T4_BR__L:
	case BOTH_T4_BR_BL:
	case BOTH_T4__R_BL:
	case BOTH_T4__L_BR:
	case BOTH_T4_BL_BR:
	case BOTH_T4_BL__R:
	//level 5
	case BOTH_T5_BR_BL:
	case BOTH_T5__R__L:
	case BOTH_T5__R_BL:
	case BOTH_T5_TR_BL:
	case BOTH_T5_BR_TL:
	case BOTH_T5_BR__L:
	case BOTH_T5_TL_BR:
	case BOTH_T5__L_BR:
	case BOTH_T5__L__R:
	case BOTH_T5_BL_BR:
	case BOTH_T5_BL__R:
	case BOTH_T5_BL_TR:
	//special
	//case BOTH_A2_STABBACK1:
	case BOTH_ATTACK_BACK:
	case BOTH_CROUCHATTACKBACK1:
	case BOTH_BUTTERFLY_LEFT:
	case BOTH_BUTTERFLY_RIGHT:
	case BOTH_FJSS_TR_BL:
	case BOTH_FJSS_TL_BR:
	case BOTH_JUMPFLIPSLASHDOWN1:
	case BOTH_JUMPFLIPSTABDOWN:
		return qtrue;
		break;
	}
	return qfalse;
}

// mv bg_panimate.c:BG_SaberInSpecialAttack (JK2 list)
qboolean BG_SaberInSpecialAttack_JK2( int anim )
{
	switch ( anim )
	{
	case BOTH_A2_STABBACK1:
	case BOTH_ATTACK_BACK:
	case BOTH_CROUCHATTACKBACK1:
	case BOTH_BUTTERFLY_LEFT:
	case BOTH_BUTTERFLY_RIGHT:
	case BOTH_FJSS_TR_BL:
	case BOTH_FJSS_TL_BR:
	case BOTH_LUNGE2_B__T_:
	case BOTH_FORCELEAP2_T__B_:
	case BOTH_JUMPFLIPSLASHDOWN1://#
	case BOTH_JUMPFLIPSTABDOWN://#
		return qtrue;
	}
	return qfalse;
}

// mv bg_saber.c:PM_SaberInBrokenParry, 1.02: the V1 ("reflected") moves do not count
qboolean PM_SaberInBrokenParry_JK2( int move )
{
	if ( move >= LS_H1_T_ && move <= LS_H1_BL )
	{
		return qtrue;
	}
	return qfalse;
}

// mv bg_pmove.c:PM_GetSaberStance
int PM_GetSaberStance_JK2( void )
{
	if (pm->ps->fd.saberAnimLevel == FORCE_LEVEL_2)
	{ //medium
		return BOTH_STAND2;
	}
	if (pm->ps->fd.saberAnimLevel == FORCE_LEVEL_3)
	{ //strong
		return BOTH_SABERSLOW_STANCE;
	}

	//fast
	return BOTH_SABERFAST_STANCE;
}

// The 1.02 move table has the lower parry/knockaway/broken-parry anims unswapped. Our table is
// swapped at load time when g_fixSaberMoveData is set (BG_FixSaberMoveData), so in 1.02 mode
// these six moves always use the original JK2 anims.
static int JK2_MoveAnim( int move )
{
	const char *name;

	if ( move < 0 || move >= LS_MOVE_MAX )
	{
		return saberMoveData[LS_READY].animToUse;
	}

	name = saberMoveData[move].name;
	if ( name && name[0] && (name[0] == 'B' || name[0] == 'K' || name[0] == 'P') )
	{
		if ( !strcmp( name, "BParry LR" ) )	return BOTH_H1_S1_BL;
		if ( !strcmp( name, "BParry LL" ) )	return BOTH_H1_S1_BR;
		if ( !strcmp( name, "Knock LR" ) )	return BOTH_K1_S1_BL;
		if ( !strcmp( name, "Knock LL" ) )	return BOTH_K1_S1_BR;
		if ( !strcmp( name, "Parry LR" ) )	return BOTH_P1_S1_BL;
		if ( !strcmp( name, "Parry LL" ) )	return BOTH_P1_S1_BR;
	}
	return saberMoveData[move].animToUse;
}

// mv bg_pmove.c:PM_SetAnim, the 1.02 extras: special jumps always restart and a roll is never
// interrupted. Only used for pmove anims (the server's G_SetAnim does not go through here).
void PM_SetAnim_JK2( int setAnimParts, int anim, int setAnimFlags )
{
	if (BG_InSpecialJump(anim))
	{
		setAnimFlags |= SETANIM_FLAG_RESTART;
	}

	switch ( pm->ps->legsAnim )
	{ //mv BG_InRoll (JK2 list: only the four rolls)
	case BOTH_ROLL_F:
	case BOTH_ROLL_B:
	case BOTH_ROLL_R:
	case BOTH_ROLL_L:
		if ( pm->ps->legsTimer > 0 )
		{ //never interrupt a roll
			return;
		}
		break;
	}

	BG_SetAnim(pm->ps, pm->animations, setAnimParts, anim, setAnimFlags);
}

#define PM_SetAnim PM_SetAnim_JK2

/*
=============================================================================

Transitions and kata (mv bg_saber.c)

=============================================================================
*/

// mv bg_saber.c:PM_SaberAnimTransitionAnim, 1.02 branches
static int PM_SaberAnimTransitionAnim_JK2( int curmove, int newmove )
{
	int retmove = newmove;
	if ( curmove == LS_READY )
	{//just standing there
		switch ( newmove )
		{
		case LS_A_TL2BR:
		case LS_A_L2R:
		case LS_A_BL2TR:
		case LS_A_BR2TL:
		case LS_A_R2L:
		case LS_A_TR2BL:
		case LS_A_T2B:
			//transition is the start
			retmove = LS_S_TL2BR + (newmove-LS_A_TL2BR);
			break;
		}
	}
	else
	{
		switch ( newmove )
		{
		//transitioning to ready pose
		case LS_READY:
			switch ( curmove )
			{
			//transitioning from an attack
			case LS_A_TL2BR:
			case LS_A_L2R:
			case LS_A_BL2TR:
			case LS_A_BR2TL:
			case LS_A_R2L:
			case LS_A_TR2BL:
			case LS_A_T2B:
				//transition is the return
				retmove = LS_R_TL2BR + (newmove-LS_A_TL2BR);
				break;
			}
			break;
		//transitioning to an attack
		case LS_A_TL2BR:
		case LS_A_L2R:
		case LS_A_BL2TR:
		case LS_A_BR2TL:
		case LS_A_R2L:
		case LS_A_TR2BL:
		case LS_A_T2B:
			//1.02: no kata check for a repeat of the same attack
			if ( saberMoveData[curmove].endQuad == saberMoveData[newmove].startQuad )
			{//new move starts from same quadrant
				retmove = newmove;
			}
			else
			{
				switch ( curmove )
				{
				//1.02: no transition from deflections (LS_D1_*)
				case LS_A_TL2BR:
				case LS_A_L2R:
				case LS_A_BL2TR:
				case LS_A_BR2TL:
				case LS_A_R2L:
				case LS_A_TR2BL:
				case LS_A_T2B:
					retmove = transitionMove[saberMoveData[curmove].endQuad][saberMoveData[newmove].startQuad];
					break;
				//1.02: no transition from knockaways, reflected or broken parries (K1, V1, H1)
				case LS_R_TL2BR:
				case LS_R_L2R:
				case LS_R_BL2TR:
				case LS_R_BR2TL:
				case LS_R_R2L:
				case LS_R_TR2BL:
				case LS_R_T2B:
				//transitioning from a parry/reflection
				case LS_PARRY_UP:
				case LS_PARRY_UR:
				case LS_PARRY_UL:
				case LS_PARRY_LR:
				case LS_PARRY_LL:
				case LS_REFLECT_UP:
				case LS_REFLECT_UR:
				case LS_REFLECT_UL:
				case LS_REFLECT_LR:
				case LS_REFLECT_LL:
					retmove = transitionMove[saberMoveData[curmove].endQuad][saberMoveData[newmove].startQuad];
					break;
				//NB: transitioning from transitions is fine
				}
			}
			break;
		//transitioning to any other anim is not supported
		}
	}

	if ( retmove == LS_NONE )
	{
		return newmove;
	}

	return retmove;
}

// mv bg_saber.c:PM_SaberKataDone_1_02
static qboolean PM_SaberKataDone_1_02( void )
{
	if ( (pm->ps->fd.saberAnimLevel >= FORCE_LEVEL_3 && pm->ps->saberAttackChainCount > PM_irand_timesync( 0, 1 )) ||
		( pm->ps->fd.saberAnimLevel == FORCE_LEVEL_2 && pm->ps->saberAttackChainCount > PM_irand_timesync( 2, 5 ) ) )
	{
		return qtrue;
	}
	return qfalse;
}

/*
=============================================================================

Saber locks (mv bg_saber.c)

=============================================================================
*/

static qboolean JK2_InLockAnim( int anim )
{
	return ( anim == BOTH_BF2LOCK ||
		anim == BOTH_BF1LOCK ||
		anim == BOTH_CWCIRCLELOCK ||
		anim == BOTH_CCWCIRCLELOCK ) ? qtrue : qfalse;
}

static playerState_t *JK2_PSForNum( int num )
{
	bgEntity_t *bgEnt;

	if ( num < 0 || num >= ENTITYNUM_NONE )
	{
		return NULL;
	}
	bgEnt = PM_BGEntForNum( num );
	if ( !bgEnt )
	{
		return NULL;
	}
	return bgEnt->playerState;
}

// mv bg_saber.c:PM_SaberLockBreak
static void PM_SaberLockBreak_JK2( playerState_t *genemy, qboolean victory )
{
	int	winAnim = BOTH_STAND1;
	qboolean punishLoser = qfalse;

	switch ( pm->ps->torsoAnim )
	{
	case BOTH_BF2LOCK:
		pm->ps->saberMove = LS_A_T2B;
		winAnim = BOTH_A3_T__B_;
		if ( !victory )
		{//no-one won
			genemy->saberMove = LS_A_T2B;
		}
		else
		{
			punishLoser = qtrue;
		}
		break;
	case BOTH_BF1LOCK:
		pm->ps->saberMove = LS_K1_T_;
		winAnim = BOTH_K1_S1_T_;
		if ( !victory )
		{//no-one won
			genemy->saberMove = LS_K1_T_;
		}
		else
		{
			punishLoser = qtrue;
		}
		break;
	case BOTH_CWCIRCLELOCK:
		winAnim = BOTH_CWCIRCLEBREAK;
		if ( !victory )
		{//no-one won
		}
		else
		{
			genemy->saberMove = LS_H1_BL;
			genemy->saberBlocked = BLOCKED_PARRY_BROKEN;
			punishLoser = qtrue;
		}
		break;
	case BOTH_CCWCIRCLELOCK:
		winAnim = BOTH_CCWCIRCLEBREAK;
		if ( !victory )
		{//no-one won
		}
		else
		{
			genemy->saberMove = LS_H1_BR;
			genemy->saberBlocked = BLOCKED_PARRY_BROKEN;
			punishLoser = qtrue;
		}
		break;
	}
	PM_SetAnim( SETANIM_BOTH, winAnim, SETANIM_FLAG_OVERRIDE|SETANIM_FLAG_HOLD );

	if (punishLoser)
	{ //someone lost the lock, so punish them by knocking them down
		vec3_t oppDir;

		int strength = 8;

		VectorSubtract(genemy->origin, pm->ps->origin, oppDir);
		VectorNormalize(oppDir);

		genemy->forceHandExtend = HANDEXTEND_KNOCKDOWN;
		genemy->forceHandExtendTime = pm->cmd.serverTime + 1100;
		genemy->forceDodgeAnim = 0; //this toggles between 1 and 0, when it's 1 we should play the get up anim

		genemy->otherKiller = pm->ps->clientNum;
		genemy->otherKillerTime = pm->cmd.serverTime + 5000;
		genemy->otherKillerDebounceTime = pm->cmd.serverTime + 100;

		genemy->velocity[0] = oppDir[0]*(strength*40);
		genemy->velocity[1] = oppDir[1]*(strength*40);
		genemy->velocity[2] = 100;

		pm->checkDuelLoss = genemy->clientNum+1;
	}
	else
	{ //If no one lost, then shove each player away from the other
		vec3_t oppDir;

		int strength = 4;

		VectorSubtract(genemy->origin, pm->ps->origin, oppDir);
		VectorNormalize(oppDir);
		genemy->velocity[0] = oppDir[0]*(strength*40);
		genemy->velocity[1] = oppDir[1]*(strength*40);
		genemy->velocity[2] = 150;

		VectorSubtract(pm->ps->origin, genemy->origin, oppDir);
		VectorNormalize(oppDir);
		pm->ps->velocity[0] = oppDir[0]*(strength*40);
		pm->ps->velocity[1] = oppDir[1]*(strength*40);
		pm->ps->velocity[2] = 150;

		genemy->forceHandExtend = HANDEXTEND_WEAPONREADY;
	}

	pm->ps->weaponTime = 0;
	genemy->weaponTime = 0;

	pm->ps->saberLockTime = genemy->saberLockTime = 0;
	pm->ps->saberLockFrame = genemy->saberLockFrame = 0;
	pm->ps->saberLockEnemy = genemy->saberLockEnemy = 0;

	pm->ps->forceHandExtend = HANDEXTEND_WEAPONREADY;

	PM_AddEvent( EV_JUMP );
	if ( !victory )
	{//no-one won
		BG_AddPredictableEventToPlayerstate(EV_JUMP, 0, genemy);
	}
	else
	{
		if ( Q_irand( 0, 1 ) ) //1.02: unsynced random, as in 1.02
		{
			BG_AddPredictableEventToPlayerstate(EV_JUMP, PM_irand_timesync( 0, 75 ), genemy);
		}
	}
}

// mv bg_saber.c:PM_SaberLocked
static void PM_SaberLocked_JK2( void )
{
	int	remaining = 0;

	playerState_t *genemy = JK2_PSForNum( pm->ps->saberLockEnemy );
	if ( !genemy )
	{
		return;
	}
	if ( JK2_InLockAnim( pm->ps->torsoAnim ) && JK2_InLockAnim( genemy->torsoAnim ) )
	{
		float dist = 0;

		pm->ps->torsoTimer = 0;
		pm->ps->weaponTime = 0;
		genemy->torsoTimer = 0;
		genemy->weaponTime = 0;

		dist = DistanceSquared(pm->ps->origin,genemy->origin);
		if ( dist < 64 || dist > 6400 )
		{//between 8 and 80 from each other
			PM_SaberLockBreak_JK2( genemy, qfalse );
			return;
		}
		if ( (pm->cmd.buttons & BUTTON_ATTACK) || pm->ps->saberLockAdvance )
		{//holding attack
			animation_t *anim;

			if (pm->ps->saberLockAdvance)
			{//tapping
				float		currentFrame;
				int			curFrame;
				int			strength = 1;

				pm->ps->saberLockAdvance = qfalse;

				anim = &pm->animations[pm->ps->torsoAnim];

				currentFrame = pm->ps->saberLockFrame;

				strength = pm->ps->fd.forcePowerLevel[FP_SABER_OFFENSE]+1;

				if ( pm->ps->torsoAnim == BOTH_CCWCIRCLELOCK ||
					pm->ps->torsoAnim == BOTH_BF2LOCK )
				{
					curFrame = floor( currentFrame )-strength;
					//drop my frame one
					if ( curFrame <= anim->firstFrame )
					{//I won!  Break out
						PM_SaberLockBreak_JK2( genemy, qtrue );
						return;
					}
					else
					{
						pm->ps->saberLockFrame = curFrame;
						remaining = curFrame-anim->firstFrame;
					}
				}
				else
				{
					curFrame = ceil( currentFrame )+strength;
					//advance my frame one
					if ( curFrame >= anim->firstFrame+anim->numFrames )
					{//I won!  Break out
						PM_SaberLockBreak_JK2( genemy, qtrue );
						return;
					}
					else
					{
						pm->ps->saberLockFrame = curFrame;
						remaining = anim->firstFrame+anim->numFrames-curFrame;
					}
				}
				if ( !Q_irand( 0, 2 ) ) //1.02: unsynced random, as in 1.02
				{
					PM_AddEvent( EV_JUMP );
				}
			}
			else
			{
				return;
			}

			anim = &pm->animations[genemy->torsoAnim];

			if ( genemy->torsoAnim == BOTH_CWCIRCLELOCK ||
				genemy->torsoAnim == BOTH_BF1LOCK )
			{
				if ( !Q_irand( 0, 2 ) ) //1.02: unsynced random, as in 1.02
				{
					BG_AddPredictableEventToPlayerstate(EV_PAIN, floor((float)80/100*100.0f), genemy);
				}
				genemy->saberLockFrame = anim->firstFrame+remaining;
			}
			else
			{
				genemy->saberLockFrame = anim->firstFrame+anim->numFrames-remaining;
			}
		}
	}
	else
	{//something broke us out of it
		PM_SaberLockBreak_JK2( genemy, qfalse );
	}
}

/*
=============================================================================

Special moves (mv bg_saber.c)

=============================================================================
*/

#define JK2_BACK_STAB_DISTANCE 128

// mv bg_saber.c:PM_CanBackstab (only clients count)
static qboolean PM_CanBackstab_JK2( void )
{
	trace_t tr;
	vec3_t flatAng;
	vec3_t fwd, back;
	vec3_t trmins = {-15, -15, -8};
	vec3_t trmaxs = {15, 15, 8};

	VectorCopy(pm->ps->viewangles, flatAng);
	flatAng[PITCH] = 0;

	AngleVectors(flatAng, fwd, 0, 0);

	back[0] = pm->ps->origin[0] - fwd[0]*JK2_BACK_STAB_DISTANCE;
	back[1] = pm->ps->origin[1] - fwd[1]*JK2_BACK_STAB_DISTANCE;
	back[2] = pm->ps->origin[2] - fwd[2]*JK2_BACK_STAB_DISTANCE;

	pm->trace(&tr, pm->ps->origin, trmins, trmaxs, back, pm->ps->clientNum, MASK_PLAYERSOLID);

	if (tr.fraction != 1.0 && tr.entityNum >= 0 && tr.entityNum < MAX_CLIENTS)
	{ //We don't have real entity access here so we can't do an indepth check. But if it's a client and it's behind us, I guess that's reason enough to stab backward
		return qtrue;
	}

	return qfalse;
}

// mv bg_saber.c:PM_SaberFlipOverAttackMove
static saberMoveName_t PM_SaberFlipOverAttackMove_JK2( trace_t *tr )
{
	vec3_t fwdAngles, jumpFwd;
	float zDiff = 0;
	playerState_t *psData;

	VectorCopy( pm->ps->viewangles, fwdAngles );
	fwdAngles[PITCH] = fwdAngles[ROLL] = 0;
	AngleVectors( fwdAngles, jumpFwd, NULL, NULL );
	VectorScale( jumpFwd, 50, pm->ps->velocity );
	pm->ps->velocity[2] = 400;

	psData = JK2_PSForNum( tr->entityNum );

	//go higher for enemies higher than you, lower for those lower than you
	if (psData)
	{
		zDiff = psData->origin[2] - pm->ps->origin[2];
	}
	else
	{
		zDiff = 0;
	}
	pm->ps->velocity[2] += (zDiff)*1.5f;

	//clamp to decent-looking values
	if ( zDiff <= 0 && pm->ps->velocity[2] < 200 )
	{//if we're on same level, don't let me jump so low, I clip into the ground
		pm->ps->velocity[2] = 200;
	}
	else if ( pm->ps->velocity[2] < 100 )
	{
		pm->ps->velocity[2] = 100;
	}
	else if ( pm->ps->velocity[2] > 400 )
	{
		pm->ps->velocity[2] = 400;
	}

	PM_SetForceJumpZStart(pm->ps->origin[2]);//so we don't take damage if we land at same height

	PM_AddEvent( EV_JUMP );
	pm->ps->fd.forceJumpSound = 1;
	pm->cmd.upmove = 0;

	if ( Q_irand( 0, 1 ) ) //1.02: unsynced random, as in 1.02
	{
		return LS_A_FLIP_STAB;
	}
	else
	{
		return LS_A_FLIP_SLASH;
	}
}

#define JK2_FLIPHACK_DISTANCE 200

// mv bg_saber.c:PM_SomeoneInFront (only clients count)
static qboolean PM_SomeoneInFront_JK2( trace_t *tr )
{ //Also a very simplified version of the sp counterpart
	vec3_t flatAng;
	vec3_t fwd, back;
	vec3_t trmins = {-15, -15, -8};
	vec3_t trmaxs = {15, 15, 8};

	VectorCopy(pm->ps->viewangles, flatAng);
	flatAng[PITCH] = 0;

	AngleVectors(flatAng, fwd, 0, 0);

	back[0] = pm->ps->origin[0] + fwd[0]*JK2_FLIPHACK_DISTANCE;
	back[1] = pm->ps->origin[1] + fwd[1]*JK2_FLIPHACK_DISTANCE;
	back[2] = pm->ps->origin[2] + fwd[2]*JK2_FLIPHACK_DISTANCE;

	pm->trace(tr, pm->ps->origin, trmins, trmaxs, back, pm->ps->clientNum, MASK_PLAYERSOLID);

	if (tr->fraction != 1.0 && tr->entityNum >= 0 && tr->entityNum < MAX_CLIENTS)
	{
		return qtrue;
	}

	return qfalse;
}

// mv bg_saber.c:PM_SaberLungeAttackMove
static saberMoveName_t PM_SaberLungeAttackMove_JK2( void )
{
	vec3_t fwdAngles, jumpFwd;

	VectorCopy( pm->ps->viewangles, fwdAngles );
	fwdAngles[PITCH] = fwdAngles[ROLL] = 0;
	//do the lunge
	AngleVectors( fwdAngles, jumpFwd, NULL, NULL );
	VectorScale( jumpFwd, 150, pm->ps->velocity );
	PM_AddEvent( EV_JUMP );

	return LS_A_LUNGE;
}

// mv bg_saber.c:PM_SaberJumpAttackMove
static saberMoveName_t PM_SaberJumpAttackMove_JK2( void )
{
	vec3_t fwdAngles, jumpFwd;

	VectorCopy( pm->ps->viewangles, fwdAngles );
	fwdAngles[PITCH] = fwdAngles[ROLL] = 0;
	AngleVectors( fwdAngles, jumpFwd, NULL, NULL );
	VectorScale( jumpFwd, 300, pm->ps->velocity );
	pm->ps->velocity[2] = 280;
	PM_SetForceJumpZStart(pm->ps->origin[2]);//so we don't take damage if we land at same height

	PM_AddEvent( EV_JUMP );
	pm->ps->fd.forceJumpSound = 1;
	pm->cmd.upmove = 0;

	return LS_A_JUMP_T__B_;
}

// mv bg_saber.c:PM_SaberAttackForMovement, 1.02 branches
static saberMoveName_t PM_SaberAttackForMovement_JK2( saberMoveName_t curmove )
{
	saberMoveName_t newmove = LS_INVALID;

	if ( pm->cmd.rightmove > 0 )
	{//moving right
		if ( pm->cmd.forwardmove > 0 )
		{//forward right = TL2BR slash
			newmove = LS_A_TL2BR;
		}
		else if ( pm->cmd.forwardmove < 0 )
		{//backward right = BL2TR uppercut
			newmove = LS_A_BL2TR;
		}
		else
		{//just right is a left slice
			newmove = LS_A_L2R;
		}
	}
	else if ( pm->cmd.rightmove < 0 )
	{//moving left
		if ( pm->cmd.forwardmove > 0 )
		{//forward left = TR2BL slash
			newmove = LS_A_TR2BL;
		}
		else if ( pm->cmd.forwardmove < 0 )
		{//backward left = BR2TL uppercut
			newmove = LS_A_BR2TL;
		}
		else
		{//just left is a right slice
			newmove = LS_A_R2L;
		}
	}
	else
	{//not moving left or right
		if ( pm->cmd.forwardmove > 0 )
		{//forward= T2B slash
			if (pm->ps->fd.saberAnimLevel == FORCE_LEVEL_2 &&
				pm->ps->velocity[2] > 100 &&
				PM_GroundDistance() < 32 &&
				!BG_InSpecialJump(pm->ps->legsAnim))
			{ //FLIP AND DOWNWARD ATTACK
				trace_t tr;

				if (PM_SomeoneInFront_JK2(&tr))
				{
					newmove = PM_SaberFlipOverAttackMove_JK2(&tr);
				}
			}
			else if (pm->ps->fd.saberAnimLevel == FORCE_LEVEL_1 &&
				(pm->ps->pm_flags & PMF_DUCKED) &&
				pm->ps->weaponTime <= 0)
			{ //LUNGE (weak) - 1.02: also in the air
				newmove = PM_SaberLungeAttackMove_JK2();
			}
			else
			{
				newmove = LS_A_T2B;
			}
		}
		else if ( pm->cmd.forwardmove < 0 )
		{//backward= T2B slash//B2T uppercut?
			if (PM_CanBackstab_JK2())
			{ //BACKSTAB (attack varies by level)
				if (pm->ps->fd.saberAnimLevel >= FORCE_LEVEL_2)
				{//medium and higher attacks
					if ( (pm->ps->pm_flags&PMF_DUCKED) || pm->cmd.upmove < 0 )
					{
						newmove = LS_A_BACK_CR;
					}
					else
					{
						newmove = LS_A_BACK;
					}
				}
				else
				{ //weak attack
					newmove = LS_A_BACKSTAB;
				}
			}
			else
			{
				newmove = LS_A_T2B;
			}
		}
		else if ( PM_SaberInBounce( curmove ) )
		{//bounces should go to their default attack if you don't specify a direction but are attacking
			if ( PM_SaberKataDone_1_02() )
			{
				newmove = saberMoveData[curmove].chain_idle;
			}
			else
			{
				newmove = saberMoveData[curmove].chain_attack;
			}
		}
		else if ( curmove == LS_READY )
		{//Not moving at all, shouldn't have gotten here...?
			//1.02: a random attack (synced with the client)
			newmove = PM_irand_timesync(LS_A_TL2BR, LS_A_T2B);
		}
	}

	return newmove;
}

/*
=============================================================================

PM_SetSaberMove_JK2 (mv bg_saber.c:PM_SetSaberMove, 1.02 branches)

=============================================================================
*/

void PM_SetSaberMove_JK2( short newMove )
{
	unsigned int setflags = saberMoveData[newMove].animSetFlags;
	int	anim = JK2_MoveAnim( newMove );
	int parts = SETANIM_TORSO;

	if ( newMove == LS_READY )
	{//finished with a kata reset attack counter
		pm->ps->saberAttackChainCount = 0;
	}
	else if ( BG_SaberInAttack_JK2( newMove ) )
	{//continuing with a kata, increment attack counter
		pm->ps->saberAttackChainCount++;
	}

	if (pm->ps->saberAttackChainCount > 16)
	{ //for the sake of being able to send the value over the net within a reasonable bit count
		pm->ps->saberAttackChainCount = 16;
	}

	if ( pm->ps->fd.saberAnimLevel > FORCE_LEVEL_1 &&
			!BG_SaberInIdle( newMove ) && !PM_SaberInParry( newMove ) && !PM_SaberInReflect( newMove ) && !BG_SaberInSpecial_JK2(newMove))
	{//readies, parries and reflections have only 1 level
		//increment the anim to the next level of saber anims
		if ( !PM_SaberInTransition( newMove ) )
		{//FIXME: only have level 1 transitions for now
			anim += (pm->ps->fd.saberAnimLevel-FORCE_LEVEL_1) * SABER_ANIM_GROUP_SIZE;
		}
	}

	// If the move does the same animation as the last one, we need to force a restart...
	if ( JK2_MoveAnim( pm->ps->saberMove ) == anim && newMove > LS_PUTAWAY)
	{
		setflags |= SETANIM_FLAG_RESTART;
	}

	//saber torso anims should always be highest priority (1.02: every move)
	setflags |= SETANIM_FLAG_OVERRIDE;

	if ( BG_InSaberStandAnim(anim) || anim == BOTH_STAND1 )
	{
		anim = pm->ps->legsAnim;

		if ((anim >= BOTH_STAND1 && anim <= BOTH_STAND4TOATTACK2) ||
			(anim >= TORSO_DROPWEAP1 && anim <= TORSO_WEAPONIDLE10))
		{ //If standing then use the special saber stand anim
			anim = PM_GetSaberStance_JK2();
		}

		if (pm->ps->pm_flags & PMF_DUCKED)
		{ //Playing torso walk anims while crouched makes you look like a monkey
			anim = PM_GetSaberStance_JK2();
		}

		if (anim == BOTH_WALKBACK1 || anim == BOTH_WALKBACK2)
		{ //normal stance when walking backward so saber doesn't look like it's cutting through leg
			anim = PM_GetSaberStance_JK2();
		}

		parts = SETANIM_TORSO;
	}

	if ( newMove == LS_A_LUNGE
		|| newMove == LS_A_JUMP_T__B_
		|| newMove == LS_A_BACKSTAB
		|| newMove == LS_A_BACK
		|| newMove == LS_A_BACK_CR
		|| newMove == LS_A_FLIP_STAB
		|| newMove == LS_A_FLIP_SLASH )
	{
		parts = SETANIM_BOTH;
	}
	else if ( BG_SpinningSaberAnim_JK2( anim ) )
	{//spins must be played on entire body
		parts = SETANIM_BOTH;
	}
	//1.02: never "standing still, so whole body"

	PM_SetAnim(parts, anim, setflags|SETANIM_FLAG_HOLD);

	if ( pm->ps->torsoAnim == anim )
	{//successfully changed anims
	//special check for *starting* a saber swing
		//playing at attack
		if ( BG_SaberInAttack_JK2( newMove ) || BG_SaberInSpecialAttack_JK2( anim ) )
		{
			if ( pm->ps->saberMove != newMove )
			{//wasn't playing that attack before
				PM_AddEvent(EV_SABER_ATTACK);
			}
		}

		pm->ps->saberMove = newMove;
		pm->ps->saberBlocking = saberMoveData[newMove].blocking;

		pm->ps->torsoAnim = anim;

		if (pm->ps->weaponTime <= 0)
		{
			pm->ps->saberBlocked = BLOCKED_NONE;
		}
	}
}

/*
=============================================================================

PM_WeaponLightsaber_JK2 (mv bg_saber.c:PM_WeaponLightsaber, 1.02 branches)

=============================================================================
*/

// 1.02 saber throw check (mv bg_saber.c:1442-1448 with mv bg_misc.c:BG_CanUseFPNow, where 1.02
// also allows the throw in a private duel). Our BG_CanUseFPNow is the JKA/jaPRO one, so the
// 1.02 rules are written out here.
static qboolean JK2_CanThrowSaberNow( void )
{
	playerState_t *ps = pm->ps;

	if ( BG_HasYsalamiri( pm->gametype, ps ) )
	{
		return qfalse;
	}
	if ( ps->forceRestricted || ps->trueNonJedi )
	{
		return qfalse;
	}
	if ( ps->saberLockFrame || ps->saberLockTime > pm->cmd.serverTime )
	{
		return qfalse;
	}
	if ( ps->fallingToDeath )
	{
		return qfalse;
	}
	if ( ps->weaponstate == WEAPON_RAISING || ps->weaponstate == WEAPON_DROPPING )
	{
		return qfalse;
	}
	return qtrue;
}

void PM_WeaponLightsaber_JK2( void )
{
	int			addTime;
	qboolean	delayed_fire = qfalse;
	int			anim=-1, curmove, newmove=LS_NONE;

	qboolean checkOnlyWeap = qfalse;

 	if ( pm->ps->saberLockTime > pm->cmd.serverTime )
	{
		pm->ps->saberMove = LS_NONE;
		PM_SaberLocked_JK2();
		return;
	}
	else
	{
		if ( JK2_InLockAnim( pm->ps->torsoAnim ) || pm->ps->saberLockFrame )
		{
			if (pm->ps->saberLockEnemy < ENTITYNUM_NONE &&
				pm->ps->saberLockEnemy >= 0)
			{
				playerState_t *en;

				en = JK2_PSForNum( pm->ps->saberLockEnemy );

				if (en)
				{
					PM_SaberLockBreak_JK2(en, qfalse);
					return;
				}
			}

			if ( JK2_InLockAnim( pm->ps->torsoAnim ) || pm->ps->saberLockFrame )
			{
				pm->ps->torsoTimer = 0;
				PM_SetAnim(SETANIM_TORSO,BOTH_STAND1,SETANIM_FLAG_OVERRIDE);
				pm->ps->saberLockFrame = 0;
			}
		}
	}

	if (pm->ps->saberHolstered)
	{
		if (pm->ps->saberMove != LS_READY)
		{
			PM_SetSaberMove_JK2( LS_READY );
		}

		if (pm->ps->legsAnim != pm->ps->torsoAnim)
		{
			PM_SetAnim(SETANIM_TORSO,pm->ps->legsAnim,SETANIM_FLAG_OVERRIDE);
		}

		if (BG_InSaberStandAnim(pm->ps->torsoAnim))
		{
			PM_SetAnim(SETANIM_TORSO,BOTH_STAND1,SETANIM_FLAG_OVERRIDE);
		}

		if (pm->ps->weaponTime < 1 && ((pm->cmd.buttons & BUTTON_ALT_ATTACK) || (pm->cmd.buttons & BUTTON_ATTACK)))
		{
			if (pm->ps->duelTime < pm->cmd.serverTime)
			{
				pm->ps->saberHolstered = 0;
				PM_AddEvent(EV_SABER_UNHOLSTER);
			}
		}

		if ( pm->ps->weaponTime > 0 )
		{
			pm->ps->weaponTime -= pml.msec;
		}

		checkOnlyWeap = qtrue;
		goto weapChecks;
	}

	if ((pm->cmd.buttons & BUTTON_ALT_ATTACK) &&
		pm->ps->weaponTime < 1 &&
		pm->ps->saberCanThrow &&
		pm->ps->fd.forcePower >= forcePowerNeeded[pm->ps->fd.forcePowerLevel[FP_SABERTHROW]][FP_SABERTHROW] &&
		JK2_CanThrowSaberNow()
		)
	{ //might as well just check for a saber throw right here
		//This will get set to false again once the saber makes it back to its owner game-side
		if (!pm->ps->saberInFlight)
		{
			pm->ps->fd.forcePower -= forcePowerNeeded[pm->ps->fd.forcePowerLevel[FP_SABERTHROW]][FP_SABERTHROW];
		}

		pm->ps->saberInFlight = qtrue;
	}

	if ( pm->ps->saberInFlight )
	{//guiding saber
		PM_SetAnim(SETANIM_TORSO, BOTH_SABERPULL, SETANIM_FLAG_OVERRIDE|SETANIM_FLAG_HOLD);
		pm->ps->torsoTimer = 1;
		return;
	}

	// don't allow attack until all buttons are up (1.02)
	if ( pm->ps->pm_flags & PMF_RESPAWNED ) {
		return;
	}

	// check for dead player
	if ( pm->ps->stats[STAT_HEALTH] <= 0 ) {
		return;
	}

	if (pm->ps->weaponstate == WEAPON_READY ||
		pm->ps->weaponstate == WEAPON_IDLE)
	{
		if (pm->ps->saberMove != LS_READY && pm->ps->weaponTime <= 0 && !pm->ps->saberBlocked)
		{
			PM_SetSaberMove_JK2( LS_READY );
		}
	}

	if( pm->ps->torsoAnim == BOTH_RUN2 ||
		pm->ps->torsoAnim == BOTH_RUN1 )
	{
		if (pm->ps->torsoAnim != pm->ps->legsAnim)
		{
			PM_SetAnim(SETANIM_TORSO,pm->ps->legsAnim,SETANIM_FLAG_OVERRIDE);
		}
	}

	// make weapon function
	if ( pm->ps->weaponTime > 0 ) {
		pm->ps->weaponTime -= pml.msec;

		if (pm->ps->saberBlocked && pm->ps->torsoAnim != JK2_MoveAnim(pm->ps->saberMove))
		{ //rww - keep him in the blocking pose until he can attack again
			PM_SetAnim(SETANIM_TORSO,JK2_MoveAnim(pm->ps->saberMove),saberMoveData[pm->ps->saberMove].animSetFlags|SETANIM_FLAG_HOLD);
			return;
		}
	}
	else
	{
		pm->ps->weaponstate = WEAPON_READY;
	}

	// Now we react to a block action by the player's lightsaber.
	if ( pm->ps->saberBlocked )
	{
		int firstSet = 0;

		if (!pm->ps->weaponTime)
		{
			firstSet = 1;
		}

		switch ( pm->ps->saberBlocked )
		{
			case BLOCKED_BOUNCE_MOVE:
				//1.02: ignored (never set in 1.02)
				break;
			case BLOCKED_PARRY_BROKEN:
				//whatever parry we were is in now broken, play the appropriate knocked-away anim
				{
					int nextMove;

					if ( PM_SaberInBrokenParry_JK2( pm->ps->saberMove ) )
					{//already have one...?
						nextMove = pm->ps->saberMove;
					}
					else
					{
						switch ( pm->ps->saberMove )
						{ //mv bg_saber.c:PM_BrokenParryForParry
						case LS_PARRY_UP:	nextMove = LS_H1_T_;	break;
						case LS_PARRY_UR:	nextMove = LS_H1_TR;	break;
						case LS_PARRY_UL:	nextMove = LS_H1_TL;	break;
						case LS_PARRY_LR:	nextMove = LS_H1_BL;	break;
						case LS_PARRY_LL:	nextMove = LS_H1_BR;	break;
						case LS_READY:		nextMove = LS_H1_B_;	break;
						default:			nextMove = LS_NONE;		break;
						}
					}
					if ( nextMove != LS_NONE )
					{
						PM_SetSaberMove_JK2( nextMove );
						pm->ps->weaponTime = pm->ps->torsoTimer;
					}
					//1.02: otherwise nothing
				}
				break;
			case BLOCKED_ATK_BOUNCE:
				// If there is absolutely no blocked move in the chart, don't even mess with the animation.
				// OR if we are already in a block or parry.
				if (pm->ps->saberMove >= LS_T1_BR__R)
				{//an actual bounce?  Other bounces before this are actually transitions?
					pm->ps->saberBlocked = BLOCKED_NONE;
				}
				else
				{
					int bounceMove;

					if ( pm->cmd.buttons & BUTTON_ATTACK )
					{//transition to a new attack
						int newQuad = PM_SaberMoveQuadrantForMovement( &pm->cmd );
						while ( newQuad == saberMoveData[pm->ps->saberMove].startQuad )
						{//player is still in same attack quad, don't repeat that attack because it looks bad,
							newQuad = PM_irand_timesync( Q_BR, Q_BL );
						}//else player is switching up anyway, take the new attack dir
						bounceMove = transitionMove[saberMoveData[pm->ps->saberMove].startQuad][newQuad];
					}
					else
					{//return to ready
						if ( saberMoveData[pm->ps->saberMove].startQuad == Q_T )
						{
							bounceMove = LS_R_BL2TR;
						}
						else if ( saberMoveData[pm->ps->saberMove].startQuad < Q_T )
						{
							bounceMove = LS_R_TL2BR+saberMoveData[pm->ps->saberMove].startQuad-Q_BR;
						}
						else// if ( saberMoveData[pm->ps->saberMove].startQuad > Q_T )
						{
							bounceMove = LS_R_BR2TL+saberMoveData[pm->ps->saberMove].startQuad-Q_TL;
						}
					}
					PM_SetSaberMove_JK2( bounceMove );

					pm->ps->weaponTime = pm->ps->torsoTimer;//+saberMoveData[bounceMove].blendTime+SABER_BLOCK_DUR;

				}
				break;
			case BLOCKED_UPPER_RIGHT:
				PM_SetSaberMove_JK2( LS_PARRY_UR );
				break;
			case BLOCKED_UPPER_RIGHT_PROJ:
				PM_SetSaberMove_JK2( LS_REFLECT_UR );
				break;
			case BLOCKED_UPPER_LEFT:
				PM_SetSaberMove_JK2( LS_PARRY_UL );
				break;
			case BLOCKED_UPPER_LEFT_PROJ:
				PM_SetSaberMove_JK2( LS_REFLECT_UL );
				break;
			case BLOCKED_LOWER_RIGHT:
				PM_SetSaberMove_JK2( LS_PARRY_LR );
				break;
			case BLOCKED_LOWER_RIGHT_PROJ:
				PM_SetSaberMove_JK2( LS_REFLECT_LR );
				break;
			case BLOCKED_LOWER_LEFT:
				PM_SetSaberMove_JK2( LS_PARRY_LL );
				break;
			case BLOCKED_LOWER_LEFT_PROJ:
				PM_SetSaberMove_JK2( LS_REFLECT_LL);
				break;
			case BLOCKED_TOP:
				PM_SetSaberMove_JK2( LS_PARRY_UP );
				break;
			case BLOCKED_TOP_PROJ:
				PM_SetSaberMove_JK2( LS_REFLECT_UP );
				break;
			default:
				pm->ps->saberBlocked = BLOCKED_NONE;
				break;
		}

		if (pm->ps->saberBlocked != BLOCKED_ATK_BOUNCE && pm->ps->saberBlocked != BLOCKED_PARRY_BROKEN && pm->ps->weaponTime < 1)
		{
			pm->ps->torsoTimer = SABER_BLOCK_DUR;
			pm->ps->weaponTime = pm->ps->torsoTimer;
		}

		if (firstSet)
		{
			return;
		}

		// Charging is like a lead-up before attacking again.  This is an appropriate use, or we can create a new weaponstate for blocking
		pm->ps->weaponstate = WEAPON_READY;

		// Done with block, so stop these active weapon branches.
		return;
	}

weapChecks:
	// check for weapon change
	// can't change if weapon is firing, but can change again if lowering or raising
	if ( pm->ps->weaponTime <= 0 || pm->ps->weaponstate != WEAPON_FIRING ) {
		if ( pm->ps->weapon != pm->cmd.weapon ) {
			PM_BeginWeaponChange( pm->cmd.weapon );
		}
	}

	if ( pm->ps->weaponTime > 0 )
	{
		return;
	}

	// *********************************************************
	// WEAPON_DROPPING
	// *********************************************************

	// change weapon if time
	if ( pm->ps->weaponstate == WEAPON_DROPPING ) {
		PM_FinishWeaponChange();
		return;
	}

	// *********************************************************
	// WEAPON_RAISING
	// *********************************************************

	if ( pm->ps->weaponstate == WEAPON_RAISING )
	{//Just selected the weapon
		pm->ps->weaponstate = WEAPON_IDLE;
		if(pm->ps->legsAnim == BOTH_WALK1 )
		{
			PM_SetAnim(SETANIM_TORSO,BOTH_WALK1,SETANIM_FLAG_NORMAL);
		}
		else if(pm->ps->legsAnim == BOTH_RUN2 )
		{
			PM_SetAnim(SETANIM_TORSO,BOTH_RUN2,SETANIM_FLAG_NORMAL);
		}
		else if(pm->ps->legsAnim == BOTH_WALK2 )
		{
			PM_SetAnim(SETANIM_TORSO,BOTH_WALK2,SETANIM_FLAG_NORMAL);
		}
		else
		{
			PM_SetAnim(SETANIM_TORSO,PM_GetSaberStance_JK2(),SETANIM_FLAG_NORMAL);
		}

		if (pm->ps->weaponstate == WEAPON_RAISING)
		{
			return;
		}

	}

	if (checkOnlyWeap)
	{
		return;
	}

	// *********************************************************
	// Check for WEAPON ATTACK
	// *********************************************************

	if(!delayed_fire)
	{
		// Start with the current move, and cross index it with the current control states.
		if ( pm->ps->saberMove > LS_NONE && pm->ps->saberMove < LS_MOVE_MAX )
		{
			curmove = pm->ps->saberMove;
		}
		else
		{
			curmove = LS_READY;
		}
		// check for fire
		if ( !(pm->cmd.buttons & (BUTTON_ATTACK)) )
		{
			if (pm->ps->weaponTime != 0)
			{//Still firing
				pm->ps->weaponstate = WEAPON_FIRING;
			}
			else if ( pm->ps->weaponstate != WEAPON_READY )
			{
				pm->ps->weaponstate = WEAPON_IDLE;
			}
			//Check for finishing an anim if necc.
			if ( curmove >= LS_S_TL2BR && curmove <= LS_S_T2B )
			{//started a swing, must continue from here
				newmove = LS_A_TL2BR + (curmove-LS_S_TL2BR);
			}
			else if ( curmove >= LS_A_TL2BR && curmove <= LS_A_T2B )
			{//finished an attack, must continue from here
				newmove = LS_R_TL2BR + (curmove-LS_A_TL2BR);
			}
			else if ( PM_SaberInTransition( curmove ) )
			{//in a transition, must play sequential attack
				newmove = saberMoveData[curmove].chain_attack;
			}
			else if ( PM_SaberInBounce( curmove ) )
			{//in a bounce
				newmove = saberMoveData[curmove].chain_idle;//oops, not attacking, so don't chain
			}
			else
			{//FIXME: what about returning from a parry?
				PM_SetSaberMove_JK2( LS_READY );
				return;
			}
		}

		// ***************************************************
		// Pressing attack, so we must look up the proper attack move.

		if ( pm->ps->weaponTime > 0 )
		{	// Last attack is not yet complete.
			pm->ps->weaponstate = WEAPON_FIRING;
			return;
		}
		else
		{
			int	both = qfalse;

			if ( curmove >= LS_PARRY_UP && curmove <= LS_REFLECT_LL )
			{//from a parry or deflection, can go directly into an attack (?)
				switch ( saberMoveData[curmove].endQuad )
				{
				case Q_T:
					newmove = LS_A_T2B;
					break;
				case Q_TR:
					newmove = LS_A_TL2BR;
					break;
				case Q_TL:
					newmove = LS_A_TR2BL;
					break;
				case Q_BR:
					newmove = LS_A_BR2TL;
					break;
				case Q_BL:
					newmove = LS_A_BL2TR;
					break;
				//shouldn't be a parry that ends at L, R or B
				}
			}

			if ( newmove != LS_NONE )
			{//have a valid, final LS_ move picked, so skip findingt he transition move and just get the anim
				anim = JK2_MoveAnim( newmove );
			}

			//FIXME: diagonal dirs use the figure-eight attacks from ready pose?
			if ( anim == -1 )
			{
				//FIXME: take FP_SABER_OFFENSE into account here somehow?
				if ( PM_SaberInTransition( curmove ) )
				{//in a transition, must play sequential attack
					newmove = saberMoveData[curmove].chain_attack;
				}
				else if ( curmove >= LS_S_TL2BR && curmove <= LS_S_T2B )
				{//started a swing, must continue from here
					newmove = LS_A_TL2BR + (curmove-LS_S_TL2BR);
				}
				else
				{//get attack move from movement command (1.02: broken parries do not have to return to ready)
					if ( PM_SaberKataDone_1_02() )
					{//we came from a bounce and cannot chain to another attack because our kata is done
						newmove = saberMoveData[curmove].chain_idle;
					}
					else
					{
						saberMoveName_t checkMove = PM_SaberAttackForMovement_JK2((saberMoveName_t)curmove);
						if (checkMove != LS_INVALID)
						{
							newmove = checkMove;
						}
					}
				}

				if ( newmove != LS_NONE )
				{
					//Now get the proper transition move
					newmove = PM_SaberAnimTransitionAnim_JK2( curmove, newmove );

					anim = JK2_MoveAnim( newmove );
				}
			}

			if (anim == -1)
			{//not side-stepping, pick neutral anim
				// Add randomness for prototype?
				newmove = saberMoveData[curmove].chain_attack;

				anim = JK2_MoveAnim( newmove );

				if ( !pm->cmd.forwardmove && !pm->cmd.rightmove && pm->cmd.upmove >= 0 && pm->ps->groundEntityNum != ENTITYNUM_NONE )
				{//not moving at all, so set the anim on entire body
					both = qtrue;
				}

			}

			if ( anim == -1)
			{
				if(pm->ps->legsAnim == BOTH_WALK1 )
				{
					anim = BOTH_WALK1;
				}
				else if(pm->ps->legsAnim == BOTH_RUN2 )
				{
					anim = BOTH_RUN2;
				}
				else if(pm->ps->legsAnim == BOTH_WALK2 )
				{
					anim = BOTH_WALK2;
				}
				else
				{
					anim = PM_GetSaberStance_JK2();
				}

				//1.02: no "running anim while not moving" fix
				newmove = LS_READY;
			}

			PM_SetSaberMove_JK2( newmove );

			if ( both )
			{
				PM_SetAnim(SETANIM_LEGS,anim,SETANIM_FLAG_OVERRIDE|SETANIM_FLAG_HOLD);
			}

			//don't fire again until anim is done
			pm->ps->weaponTime = pm->ps->torsoTimer;
		}
	}

	// *********************************************************
	// WEAPON_FIRING
	// *********************************************************

	pm->ps->weaponstate = WEAPON_FIRING;

	addTime = pm->ps->weaponTime;

	pm->ps->saberAttackSequence = pm->ps->torsoAnim;
	if ( !addTime )
	{
		addTime = weaponData[pm->ps->weapon].fireTime;
	}
	pm->ps->weaponTime = addTime;
}

/*
=============================================================================

Jump attacks (mv bg_pmove.c:PM_CheckJump:1293-1345, 1.02 branches)

=============================================================================
*/

void PM_CheckJumpAttack_JK2( void )
{
	// The 1.02 PM_CheckJump returns before its jump-attack block in these cases (mv bg_pmove.c:746,
	// 967-973, 981-990), so the red DFA and yellow flip start from a jump off the ground (or off a
	// wall run), never from a jump press in mid-air.
	if ( pm->ps->pm_flags & PMF_RESPAWNED )
	{
		return;
	}
	if ( pm->ps->groundEntityNum == ENTITYNUM_NONE &&
		(pm->ps->fd.forcePowersActive & (1 << FP_LEVITATION)) &&
		pm->ps->legsAnim != BOTH_WALL_RUN_LEFT && pm->ps->legsAnim != BOTH_WALL_RUN_RIGHT )
	{
		return;
	}
	if ( pm->cmd.upmove < 10 )
	{
		return;
	}
	if ( pm->ps->pm_flags & PMF_JUMP_HELD )
	{
		return;
	}

	if ( pm->cmd.upmove > 0
		&& pm->ps->weapon == WP_SABER
		&& (pm->ps->weaponTime > 0||pm->cmd.buttons&BUTTON_ATTACK) )
	{//okay, we just jumped and we're in an attack
		if ( !BG_InRoll( pm->ps, pm->ps->legsAnim )
			&& !PM_InKnockDown( pm->ps )
			&& !BG_InDeathAnim(pm->ps->legsAnim)
			&& !BG_FlippingAnim_JK2( pm->ps->legsAnim )
			&& !PM_SpinningAnim( pm->ps->legsAnim )
			&& !BG_SaberInSpecialAttack_JK2( pm->ps->torsoAnim )
			&& ( BG_SaberInAttack_JK2( pm->ps->saberMove ) ) )
		{//not in an anim we shouldn't interrupt
			//see if it's not too late to start a special jump-attack
			float animLength = PM_AnimLength( 0, (animNumber_t)pm->ps->torsoAnim );
			if ( animLength - pm->ps->torsoTimer < 500 )
			{//just started the saberMove
				//check for special-case jump attacks
				if ( pm->ps->fd.saberAnimLevel == FORCE_LEVEL_2 )
				{//using medium attacks
					if (PM_GroundDistance() < 32 &&
						!BG_InSpecialJump(pm->ps->legsAnim))
					{ //FLIP AND DOWNWARD ATTACK
						trace_t tr;

						if (PM_SomeoneInFront_JK2(&tr))
						{
							PM_SetSaberMove_JK2(PM_SaberFlipOverAttackMove_JK2(&tr));
							pml.groundPlane = qfalse;
							pml.walking = qfalse;
							pm->ps->pm_flags |= PMF_JUMP_HELD;
							pm->ps->groundEntityNum = ENTITYNUM_NONE;
							VectorClear(pml.groundTrace.plane.normal);

							pm->ps->weaponTime = pm->ps->torsoTimer;
						}
					}
				}
				else if ( pm->ps->fd.saberAnimLevel == FORCE_LEVEL_3 )
				{//using strong attacks
					if ( pm->cmd.forwardmove > 0 && //going forward
						//1.02: attack does not need to be held
						PM_GroundDistance() < 32 &&
						!BG_InSpecialJump(pm->ps->legsAnim))
					{//strong attack: jump-hack
						PM_SetSaberMove_JK2( PM_SaberJumpAttackMove_JK2() );
						pml.groundPlane = qfalse;
						pml.walking = qfalse;
						pm->ps->pm_flags |= PMF_JUMP_HELD;
						pm->ps->groundEntityNum = ENTITYNUM_NONE;
						VectorClear(pml.groundTrace.plane.normal);

						pm->ps->weaponTime = pm->ps->torsoTimer;
					}
				}
			}
		}
	}
}

#undef PM_SetAnim
