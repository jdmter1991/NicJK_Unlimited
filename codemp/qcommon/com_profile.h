/*
===========================================================================
Lightweight server/collision profiling counters.

Enabled with the "sv_profile <seconds>" cvar (0 = off). When enabled the server
prints one SVPROF line every <seconds> with frame-time, bot-AI, game-simulation,
snapshot and world-trace statistics. Counters are plain integers and are always
maintained; timestamps are only taken while profiling is enabled.
===========================================================================
*/
#pragma once

#include <chrono>
#include <cstdint>

enum comProfPhase_e {
	CPROF_OTHER = 0,	// client packets (human usercmds), misc
	CPROF_BOTAI,		// SV_BotFrame -> BotAIStartFrame
	CPROF_GAME,			// GVM_RunFrame (entity think, bot usercmd execution, physics)
	CPROF_SNAPSHOT,		// SV_SendClientMessages
	CPROF_NUM_PHASES
};

typedef struct comProfile_s {
	int			enabled;
	int			phase;

	// SV_Trace / SV_PointContents, split by phase
	uint64_t	svTraces[CPROF_NUM_PHASES];
	uint64_t	svTraceNs[CPROF_NUM_PHASES];		// world + entity clipping
	uint64_t	svWorldTraceNs[CPROF_NUM_PHASES];	// world (CM_BoxTrace model 0) only
	uint64_t	svPointContents[CPROF_NUM_PHASES];
	uint64_t	svPointContentsNs[CPROF_NUM_PHASES];

	// collision-model work (all callers)
	uint64_t	cmLeafVisits;			// leaves handed to CM_TraceThroughLeaf / CM_TestInLeaf
	uint64_t	cmLeafBrushesWalked;	// leaf-brush references iterated
	uint64_t	cmBrushesTested;		// brushes that passed the bounds reject (plane tests run)
	uint64_t	cmAccelNodes;			// accelerator nodes visited (0 when the accelerator is off)

	// slowest single SV_Trace since the server last cleared it (once per frame)
	uint64_t	worstTraceNs;
	float		worstTraceStart[3], worstTraceEnd[3], worstTraceMins[3], worstTraceMaxs[3];
	int			worstTracePhase;
} comProfile_t;

extern comProfile_t com_prof;

static inline uint64_t Com_ProfNowNs( void ) {
	return (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(
		std::chrono::steady_clock::now().time_since_epoch() ).count();
}
