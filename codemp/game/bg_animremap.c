/*
===========================================================================
NicJK Unlimited - per-model animation remapping (animremap.cfg)

How it works
------------
Game code, pmove, bots and the network all talk in animation numbers
(BOTH_*). Each skeleton has a table (bgAllAnims[i].anims) saying which frames
of the .gla an animation number plays. For a model that has remaps we build a
private copy of the humanoid table in which the entry for animation A holds
the frames of animation B. That copy is used only where frames are put on the
model: the client's drawing code and the server's Ghoul2 posing (saber traces).
Animation numbers never change, so every check in the game code, the bots and
stock clients see exactly what they saw before.

Timing: gameplay timers come from pmove, which keeps using the base table, so
by default (mode "fit") the replacement frames are stretched or squeezed to the
original length and the move takes exactly as long as before. Mode "free" plays
the replacement at its own speed (good for looping stances, runs and idles).
Mode "timing" also gives pmove the replacement's length, which changes how long
the move lasts in gameplay; it needs the same cfg on server and client, or the
client's prediction is corrected by the server.

Files (read through the game file system, so they can be loose in the mod
folder or inside a pk3):
  animremap.cfg                          central, lines: model[/skin] FROM TO [mode]
  models/players/<model>/animremap.cfg   per model,  lines: FROM TO [mode]
Central lines override per-model lines for the same animation. A model of "*"
applies to every model. Names ending in '*' map a whole group by prefix, e.g.
"BOTH_A1_* BOTH_A5_*" maps every BOTH_A1_xxx that has a BOTH_A5_xxx.
===========================================================================
*/

#include "qcommon/q_shared.h"
#include "bg_public.h"
#include "bg_local.h"
#include "anims.h"
#include "bg_animremap.h"

#ifdef _GAME
	#include "g_local.h"
#elif defined(_CGAME)
	#include "cgame/cg_local.h"
#endif

extern stringID_table_t animTable[MAX_ANIMATIONS + 1];

#define AR_MAX_ENTRIES		2048
#define AR_MAX_MODELFILES	256
#define AR_MAX_SETS			64
#define AR_MAX_TABLES		48
#define AR_NAME				64

typedef enum {
	AR_FIT,		// replacement stretched to the original length (default)
	AR_FREE,	// replacement at its own speed, gameplay timing unchanged
	AR_TIMING	// replacement at its own speed, gameplay timing from the replacement
} arMode_t;

static const char *arModeNames[] = { "fit", "free", "timing" };

typedef enum {
	AR_SRC_ALL,			// central file, model "*"
	AR_SRC_MODELFILE,	// models/players/<model>/animremap.cfg
	AR_SRC_MODEL,		// central file, model without skin
	AR_SRC_MODELSKIN,	// central file, model/skin
	AR_SRC_COUNT
} arSource_t;

typedef struct {
	char	model[AR_NAME];
	char	skin[AR_NAME];
	short	from, to;
	byte	mode;
	byte	source;
} arEntry_t;

typedef struct {
	char	model[AR_NAME];
	char	skin[AR_NAME];
	int		numRemaps;
	qboolean hasTiming;
	animation_t *visual;	// NULL when numRemaps == 0
	animation_t *pmove;		// NULL unless hasTiming
} arSet_t;

typedef struct {
	char	model[AR_NAME];
	char	skin[AR_NAME];
	int		version;
	int		set;			// -1 = none
} arClientCache_t;

static arEntry_t	ar_entries[AR_MAX_ENTRIES];
static int			ar_numEntries;
static char			ar_modelFiles[AR_MAX_MODELFILES][AR_NAME];
static int			ar_numModelFiles;
static arSet_t		ar_sets[AR_MAX_SETS];
static int			ar_numSets;
static animation_t	ar_tablePool[AR_MAX_TABLES][MAX_TOTALANIMATIONS];
static int			ar_numTables;
static arClientCache_t ar_clients[MAX_CLIENTS];
static int			ar_version = 1;
static qboolean		ar_centralLoaded;
static qboolean		ar_warnedFull;

static int AR_AnimLen( const animation_t *a ) {
	return a->numFrames * abs( a->frameLerp );
}

void BG_AnimRemap_SplitModel( const char *modelSkin, char *model, int modelSize, char *skin, int skinSize ) {
	const char *slash;

	model[0] = skin[0] = 0;
	if ( !modelSkin || !modelSkin[0] )
		return;
	slash = strchr( modelSkin, '/' );
	if ( slash ) {
		int len = slash - modelSkin + 1;
		if ( len > modelSize )
			len = modelSize;
		Q_strncpyz( model, modelSkin, len );
		Q_strncpyz( skin, slash + 1, skinSize );
	}
	else {
		Q_strncpyz( model, modelSkin, modelSize );
	}
	if ( !skin[0] )
		Q_strncpyz( skin, "default", skinSize ); // as the client names it
}

static void AR_AddEntry( const char *model, const char *skin, int from, int to, int mode, int source ) {
	arEntry_t *e;

	if ( ar_numEntries >= AR_MAX_ENTRIES ) {
		if ( !ar_warnedFull ) {
			Com_Printf( S_COLOR_YELLOW "AnimRemap: more than %d remaps, the rest are ignored\n", AR_MAX_ENTRIES );
			ar_warnedFull = qtrue;
		}
		return;
	}
	e = &ar_entries[ar_numEntries++];
	Q_strncpyz( e->model, model, sizeof( e->model ) );
	Q_strncpyz( e->skin, skin, sizeof( e->skin ) );
	e->from = from;
	e->to = to;
	e->mode = mode;
	e->source = source;
}

// One line's FROM/TO pair, with '*' prefix groups expanded. Returns entries added.
static int AR_AddPair( const char *model, const char *skin, const char *fromName, const char *toName, int mode, int source, const char *where ) {
	int fromLen = strlen( fromName ), toLen = strlen( toName );

	if ( fromLen > 0 && toLen > 0 && fromName[fromLen - 1] == '*' && toName[toLen - 1] == '*' ) {
		char fromPrefix[AR_NAME], toPrefix[AR_NAME], target[128];
		int i, added = 0;

		Q_strncpyz( fromPrefix, fromName, sizeof( fromPrefix ) );
		fromPrefix[fromLen - 1 < AR_NAME - 1 ? fromLen - 1 : AR_NAME - 1] = 0;
		Q_strncpyz( toPrefix, toName, sizeof( toPrefix ) );
		toPrefix[toLen - 1 < AR_NAME - 1 ? toLen - 1 : AR_NAME - 1] = 0;

		for ( i = 0; i < MAX_ANIMATIONS && animTable[i].name; i++ ) {
			int to;
			if ( Q_stricmpn( animTable[i].name, fromPrefix, strlen( fromPrefix ) ) )
				continue;
			Com_sprintf( target, sizeof( target ), "%s%s", toPrefix, animTable[i].name + strlen( fromPrefix ) );
			to = GetIDForString( animTable, target );
			if ( to < 0 || to == animTable[i].id )
				continue;
			AR_AddEntry( model, skin, animTable[i].id, to, mode, source );
			added++;
		}
		if ( !added )
			Com_Printf( S_COLOR_YELLOW "AnimRemap: %s: %s -> %s matched no animations\n", where, fromName, toName );
		return added;
	}
	else {
		int from = GetIDForString( animTable, fromName );
		int to = GetIDForString( animTable, toName );
		if ( from < 0 || to < 0 ) {
			Com_Printf( S_COLOR_YELLOW "AnimRemap: %s: unknown animation %s\n", where, from < 0 ? fromName : toName );
			return 0;
		}
		AR_AddEntry( model, skin, from, to, mode, source );
		return 1;
	}
}

static int AR_ParseMode( const char *token, const char *where ) {
	int i;
	for ( i = 0; i < ARRAY_LEN( arModeNames ); i++ ) {
		if ( !Q_stricmp( token, arModeNames[i] ) )
			return i;
	}
	Com_Printf( S_COLOR_YELLOW "AnimRemap: %s: unknown mode '%s' (fit, free or timing), using fit\n", where, token );
	return AR_FIT;
}

// fixedModel != NULL: per-model file, lines have no model column.
static void AR_ParseFile( const char *filename, const char *fixedModel ) {
	fileHandle_t f;
	int len, lines = 0, added = 0;
	char *buf;
	const char *p;

	len = trap->FS_Open( filename, &f, FS_READ );
	if ( len <= 0 ) {
		if ( f )
			trap->FS_Close( f );
		return;
	}
	buf = (char *)malloc( len + 1 );
	if ( !buf ) {
		trap->FS_Close( f );
		return;
	}
	trap->FS_Read( buf, len, f );
	buf[len] = 0;
	trap->FS_Close( f );

	p = buf;
	COM_BeginParseSession( filename );
	while ( 1 ) {
		char tok[4][AR_NAME];
		char model[AR_NAME], skin[AR_NAME], where[MAX_QPATH + 16];
		int n = 0, need, mode, source;
		const char *t = COM_ParseExt( &p, qtrue );

		if ( !t || !t[0] )
			break;
		lines++;
		if ( t[0] == '#' || t[0] == ';' ) {
			SkipRestOfLine( &p );
			continue;
		}
		Com_sprintf( where, sizeof( where ), "%s line %d", filename, COM_GetCurrentParseLine() );
		Q_strncpyz( tok[n++], t, AR_NAME );
		while ( 1 ) {
			t = COM_ParseExt( &p, qfalse );
			if ( !t || !t[0] )
				break; // end of line (COM_ParseExt has already stepped over the newline)
			if ( n < 4 )
				Q_strncpyz( tok[n++], t, AR_NAME );
		}

		need = fixedModel ? 2 : 3;
		if ( n < need ) {
			Com_Printf( S_COLOR_YELLOW "AnimRemap: %s: expected %s\n", where,
				fixedModel ? "FROM TO [fit|free|timing]" : "model[/skin] FROM TO [fit|free|timing]" );
			continue;
		}

		if ( fixedModel ) {
			Q_strncpyz( model, fixedModel, sizeof( model ) );
			skin[0] = 0;
			source = AR_SRC_MODELFILE;
		}
		else {
			BG_AnimRemap_SplitModel( tok[0], model, sizeof( model ), skin, sizeof( skin ) );
			if ( !strcmp( model, "*" ) ) {
				skin[0] = 0;
				source = AR_SRC_ALL;
			}
			else {
				source = strchr( tok[0], '/' ) ? AR_SRC_MODELSKIN : AR_SRC_MODEL;
			}
		}
		mode = ( n > need ) ? AR_ParseMode( tok[need], where ) : AR_FIT;
		added += AR_AddPair( model, skin, tok[need - 2], tok[need - 1], mode, source, where );
	}
	free( buf );
	Com_Printf( "AnimRemap: %d remaps from %s\n", added, filename );
}

static void AR_LoadCentral( void ) {
	if ( ar_centralLoaded )
		return;
	ar_centralLoaded = qtrue;
	AR_ParseFile( "animremap.cfg", NULL );
}

static void AR_LoadModelFile( const char *model ) {
	int i;

	if ( !model[0] || strchr( model, '.' ) || strchr( model, '\\' ) )
		return;
	for ( i = 0; i < ar_numModelFiles; i++ ) {
		if ( !Q_stricmp( ar_modelFiles[i], model ) )
			return;
	}
	if ( ar_numModelFiles < AR_MAX_MODELFILES )
		Q_strncpyz( ar_modelFiles[ar_numModelFiles++], model, AR_NAME );
	AR_ParseFile( va( "models/players/%s/animremap.cfg", model ), model );
}

static animation_t *AR_AllocTable( const animation_t *base ) {
	animation_t *t;
	if ( ar_numTables >= AR_MAX_TABLES )
		return NULL;
	t = ar_tablePool[ar_numTables++];
	memcpy( t, base, sizeof( animation_t ) * MAX_TOTALANIMATIONS );
	return t;
}

// The frames of b, shown in the slot of a.
static animation_t AR_MakeEntry( const animation_t *a, const animation_t *b, int mode ) {
	animation_t e = *b;

	// keep the original's looping: a looping stance stays looping
	if ( a->loopFrames != -1 )
		e.loopFrames = ( b->loopFrames != -1 ) ? b->loopFrames : 0;
	else
		e.loopFrames = -1;

	if ( mode == AR_FIT && a->numFrames > 0 && b->numFrames > 0 ) {
		int lenA = AR_AnimLen( a );
		int lerp = ( lenA + b->numFrames / 2 ) / b->numFrames;
		if ( lerp < 1 )
			lerp = 1;
		if ( lerp > 32767 )
			lerp = 32767;
		e.frameLerp = ( b->frameLerp < 0 ) ? -lerp : lerp;
	}
	return e;
}

static int AR_FindOrBuildSet( const char *model, const char *skin ) {
	static short map[MAX_TOTALANIMATIONS];
	static byte modes[MAX_TOTALANIMATIONS];
	const animation_t *base = bgAllAnims[0].anims;
	arSet_t *set;
	int i, src, count = 0;

	for ( i = 0; i < ar_numSets; i++ ) {
		if ( !Q_stricmp( ar_sets[i].model, model ) && !Q_stricmp( ar_sets[i].skin, skin ) )
			return i;
	}
	if ( !base )
		return -1;
	if ( ar_numSets >= AR_MAX_SETS ) {
		if ( !ar_warnedFull ) {
			Com_Printf( S_COLOR_YELLOW "AnimRemap: more than %d different models in use, the rest play their normal animations\n", AR_MAX_SETS );
			ar_warnedFull = qtrue;
		}
		return -1;
	}

	AR_LoadCentral();
	AR_LoadModelFile( model );

	for ( i = 0; i < MAX_TOTALANIMATIONS; i++ )
		map[i] = -1;

	// apply in order of precedence, later wins
	for ( src = 0; src < AR_SRC_COUNT; src++ ) {
		for ( i = 0; i < ar_numEntries; i++ ) {
			const arEntry_t *e = &ar_entries[i];
			if ( e->source != src )
				continue;
			if ( src != AR_SRC_ALL && Q_stricmp( e->model, model ) )
				continue;
			if ( src == AR_SRC_MODELSKIN && Q_stricmp( e->skin, skin ) )
				continue;
			map[e->from] = e->to;
			modes[e->from] = e->mode;
		}
	}

	set = &ar_sets[ar_numSets];
	memset( set, 0, sizeof( *set ) );
	Q_strncpyz( set->model, model, sizeof( set->model ) );
	Q_strncpyz( set->skin, skin, sizeof( set->skin ) );

	for ( i = 0; i < MAX_TOTALANIMATIONS; i++ ) {
		const animation_t *a, *b;
		int lenA, lenB;

		if ( map[i] < 0 )
			continue;
		a = &base[i];
		b = &base[map[i]];
		if ( b->numFrames <= 0 ) {
			Com_Printf( S_COLOR_YELLOW "AnimRemap: %s%s%s: %s has no frames in the humanoid skeleton, ignored\n",
				model, skin[0] ? "/" : "", skin, GetStringForID( animTable, map[i] ) );
			continue;
		}
		if ( !set->visual ) {
			set->visual = AR_AllocTable( base );
			if ( !set->visual ) {
				Com_Printf( S_COLOR_YELLOW "AnimRemap: out of tables, %s plays its normal animations\n", model );
				break;
			}
		}
		set->visual[i] = AR_MakeEntry( a, b, modes[i] );
		if ( modes[i] == AR_TIMING ) {
			if ( !set->pmove )
				set->pmove = AR_AllocTable( base );
			if ( set->pmove ) {
				set->pmove[i] = AR_MakeEntry( a, b, AR_TIMING );
				set->hasTiming = qtrue;
			}
		}
		count++;

		lenA = AR_AnimLen( a );
		lenB = AR_AnimLen( b );
		if ( modes[i] == AR_TIMING ) {
			Com_Printf( "AnimRemap: %s%s%s: %s -> %s (timing): %s%d ms -> %d ms in gameplay%s\n",
				model, skin[0] ? "/" : "", skin, GetStringForID( animTable, i ), GetStringForID( animTable, map[i] ),
				lenA != lenB ? S_COLOR_YELLOW : "", lenA, lenB, lenA != lenB ? " (move timing changes)" S_COLOR_WHITE : "" );
		}
		else if ( lenA != lenB ) {
			Com_Printf( "AnimRemap: %s%s%s: %s -> %s (%s): " S_COLOR_YELLOW "lengths differ, %d ms vs %d ms" S_COLOR_WHITE ", %s; gameplay timing unchanged\n",
				model, skin[0] ? "/" : "", skin, GetStringForID( animTable, i ), GetStringForID( animTable, map[i] ),
				arModeNames[modes[i]], lenA, lenB,
				modes[i] == AR_FIT ? va( "shown over %d ms", AR_AnimLen( &set->visual[i] ) ) : "shown at its own speed" );
		}
		else {
			Com_Printf( "AnimRemap: %s%s%s: %s -> %s (%s): both %d ms\n",
				model, skin[0] ? "/" : "", skin, GetStringForID( animTable, i ), GetStringForID( animTable, map[i] ),
				arModeNames[modes[i]], lenA );
		}
	}
	set->numRemaps = set->visual ? count : 0;
	return ar_numSets++;
}

static const arSet_t *AR_SetForClient( int clientNum, int animIndex, const char *model, const char *skin ) {
	int set;

	if ( animIndex != 0 || !model || !model[0] || !bgAllAnims[0].anims )
		return NULL;
	if ( !skin )
		skin = "";

	if ( clientNum >= 0 && clientNum < MAX_CLIENTS ) {
		arClientCache_t *c = &ar_clients[clientNum];
		if ( c->version != ar_version || Q_stricmp( c->model, model ) || Q_stricmp( c->skin, skin ) ) {
			Q_strncpyz( c->model, model, sizeof( c->model ) );
			Q_strncpyz( c->skin, skin, sizeof( c->skin ) );
			c->version = ar_version;
			c->set = AR_FindOrBuildSet( c->model, c->skin );
		}
		set = c->set;
	}
	else {
		set = AR_FindOrBuildSet( model, skin );
	}

	if ( set < 0 || !ar_sets[set].numRemaps )
		return NULL;
	return &ar_sets[set];
}

const animation_t *BG_AnimRemap_Visual( int clientNum, int animIndex, const char *model, const char *skin ) {
	const arSet_t *set = AR_SetForClient( clientNum, animIndex, model, skin );
	if ( set )
		return set->visual;
	return bgAllAnims[animIndex].anims;
}

animation_t *BG_AnimRemap_Pmove( int clientNum, int animIndex, const char *model, const char *skin ) {
	const arSet_t *set = AR_SetForClient( clientNum, animIndex, model, skin );
	if ( set && set->hasTiming )
		return set->pmove;
	return NULL;
}

void BG_AnimRemap_Reload( void ) {
	ar_numEntries = 0;
	ar_numModelFiles = 0;
	ar_numSets = 0;
	ar_numTables = 0;
	ar_centralLoaded = qfalse;
	ar_warnedFull = qfalse;
	ar_version++;
}

void BG_AnimRemap_List( void ) {
	int i;

	AR_LoadCentral();
	Com_Printf( "AnimRemap: %d remap lines loaded, %d models built\n", ar_numEntries, ar_numSets );
	for ( i = 0; i < ar_numSets; i++ ) {
		Com_Printf( "  %s%s%s: %d animations remapped%s\n", ar_sets[i].model, ar_sets[i].skin[0] ? "/" : "", ar_sets[i].skin,
			ar_sets[i].numRemaps, ar_sets[i].hasTiming ? ", some with gameplay timing" : "" );
	}
}
