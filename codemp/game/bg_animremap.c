/*
===========================================================================
NicJK Unlimited - per-model animation remapping (per-model-anims-config.cfg)

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

A model's own animations (its own GLA)
--------------------------------------
A player model names its GLA in its .glm header. The game accepts any GLA in
models/players/_humanoid/ (that is how e.g. Darth Talon ships talon_face.gla).
If that GLA is the humanoid one with extra frames appended (tools/animremap/
gla_append.py builds it), the frames below the humanoid count are the normal
animations, so stock clients and the stock animation.cfg keep working, and
    animset NAME  GLA  ANIMATION_CFG  [OFFSET]
gives the appended frames names (read from an animation.cfg, shifted by
OFFSET), usable as replacements written NAME:ANIM. Those replacements are only
shown on an entity whose Ghoul2 model really uses that GLA; anywhere else
(a client without the model, the server's stand-in model) the normal frames
are used, because the extra frames do not exist there.

Files (read through the game file system, so they can be loose in the mod
folder or inside a pk3):
  per-model-anims-config.cfg                          central, lines: model[/skin] FROM TO [mode]
  models/players/<model>/per-model-anims-config.cfg   per model,  lines: FROM TO [mode]
Both can hold animset lines. Central lines override per-model lines for the
same animation. A model of "*" applies to every model. Names ending in '*' map
a whole group by prefix, e.g. "BOTH_A1_* BOTH_A5_*".
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
#define AR_MAX_ANIMSETS		32
#define AR_MAX_SETANIMS		4096
#define AR_NAME				64

typedef enum {
	AR_FIT,		// replacement stretched to the original length (default)
	AR_FREE,	// replacement at its own speed, gameplay timing unchanged
	AR_TIMING	// replacement at its own speed, gameplay timing from the replacement
} arMode_t;

static const char *arModeNames[] = { "fit", "free", "timing" };

typedef enum {
	AR_SRC_ALL,			// central file, model "*"
	AR_SRC_MODELFILE,	// models/players/<model>/per-model-anims-config.cfg
	AR_SRC_MODEL,		// central file, model without skin
	AR_SRC_MODELSKIN,	// central file, model/skin
	AR_SRC_COUNT
} arSource_t;

typedef struct {
	char	model[AR_NAME];
	char	skin[AR_NAME];
	short	from, to;				// to < 0: replacement is setTarget
	char	setTarget[AR_NAME * 2];	// "animset:ANIM", resolved when a model is built
	byte	mode;
	byte	source;
} arEntry_t;

// named animations from an animation.cfg, living in frames of one GLA
typedef struct {
	char	name[AR_NAME];
	char	gla[MAX_QPATH];			// lower case, no extension
	int		first, count;			// range in ar_setAnims
} arAnimset_t;

typedef struct {
	char		name[AR_NAME];
	animation_t	anim;
} arSetAnim_t;

typedef struct {
	char	model[AR_NAME];
	char	skin[AR_NAME];
	char	gla[MAX_QPATH];			// GLA of the entity this table is for
	int		numRemaps;
	qboolean hasTiming;
	animation_t *visual;	// NULL when numRemaps == 0
	animation_t *pmove;		// NULL unless hasTiming
} arSet_t;

typedef struct {
	char	model[AR_NAME];
	char	skin[AR_NAME];
	char	gla[MAX_QPATH];
	int		version;
	int		set;			// -1 = none
} arClientCache_t;

// A model's own skeleton file outside models/players/_humanoid/ (e.g. MovieDuels'
// models/players/_humanoid_dooku/_humanoid.gla) with the humanoid bones and its
// own animation.cfg. Kept until the anim sets are cleared (map change).
#define AR_MAX_SKELS		16
typedef struct {
	char		gla[MAX_QPATH];		// normalized
	qboolean	ok;
	int			slot;				// bgAllAnims slot holding the table (-1 none)
	animation_t	*table;
} arSkel_t;
static arSkel_t		ar_skels[AR_MAX_SKELS];
static int			ar_numSkels;
static animation_t	ar_skelTables[AR_MAX_SKELS][MAX_TOTALANIMATIONS];
extern int			bgNumAllAnims;

static arEntry_t	ar_entries[AR_MAX_ENTRIES];
static int			ar_numEntries;
static char			ar_modelFiles[AR_MAX_MODELFILES][AR_NAME];
static int			ar_numModelFiles;
static arAnimset_t	ar_animsets[AR_MAX_ANIMSETS];
static int			ar_numAnimsets;
static arSetAnim_t	ar_setAnims[AR_MAX_SETANIMS];
static int			ar_numSetAnims;
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

// "models/players/_humanoid/_x.gla" -> "models/players/_humanoid/_x", lower case, forward slashes
static void AR_NormalizeGLA( const char *in, char *out, int size ) {
	char *dot;
	int i;

	Q_strncpyz( out, in ? in : "", size );
	for ( i = 0; out[i]; i++ ) {
		if ( out[i] == '\\' )
			out[i] = '/';
		else if ( out[i] >= 'A' && out[i] <= 'Z' )
			out[i] += 'a' - 'A';
	}
	dot = strrchr( out, '.' );
	if ( dot && !strchr( dot, '/' ) )
		*dot = 0;
}

/*
=================
Own skeletons
=================
*/
#define AR_GLA_HEADER	100		// sizeof( mdxaHeader_t )
#define AR_GLA_MAXSKEL	65536

// Reads a GLA's header and bone list (names and parents) into buf; returns
// the bone count, or -1. Only the start of the file is read.
static int AR_ReadGLASkeleton( const char *path, byte *buf, int bufSize, int *ofsSkelEnd ) {
	fileHandle_t f;
	int len, numBones, ofsFrames;

	len = trap->FS_Open( path, &f, FS_READ );
	if ( len < AR_GLA_HEADER ) {
		if ( f )
			trap->FS_Close( f );
		return -1;
	}
	trap->FS_Read( buf, AR_GLA_HEADER, f );
	if ( memcmp( buf, "2LGA", 4 ) || LittleLong( *(int *)( buf + 4 ) ) != 6 ) {
		trap->FS_Close( f );
		return -1;
	}
	ofsFrames = LittleLong( *(int *)( buf + 80 ) );
	numBones = LittleLong( *(int *)( buf + 84 ) );
	if ( numBones <= 0 || numBones > 256 || ofsFrames <= AR_GLA_HEADER || ofsFrames > bufSize || ofsFrames > len ) {
		trap->FS_Close( f );
		return -1;
	}
	trap->FS_Read( buf + AR_GLA_HEADER, ofsFrames - AR_GLA_HEADER, f );
	trap->FS_Close( f );
	*ofsSkelEnd = ofsFrames;
	return numBones;
}

static qboolean AR_SameSkeleton( const byte *a, int aEnd, const byte *b, int bEnd, int numBones ) {
	int i;
	for ( i = 0; i < numBones; i++ ) {
		int oa = AR_GLA_HEADER + LittleLong( ( (const int *)( a + AR_GLA_HEADER ) )[i] );
		int ob = AR_GLA_HEADER + LittleLong( ( (const int *)( b + AR_GLA_HEADER ) )[i] );
		if ( oa < 0 || ob < 0 || oa + 72 > aEnd || ob + 72 > bEnd )
			return qfalse;
		if ( Q_stricmpn( (const char *)( a + oa ), (const char *)( b + ob ), MAX_QPATH ) )
			return qfalse;
		if ( LittleLong( *(const int *)( a + oa + 68 ) ) != LittleLong( *(const int *)( b + ob + 68 ) ) )
			return qfalse; // parent
	}
	return qtrue;
}

// animation.cfg (any size) into a full table, by the names this game knows
static int AR_ReadAnimationCfg( const char *path, animation_t *table ) {
	fileHandle_t f;
	char *buf, *line, *next;
	int len, i, found = 0;

	for ( i = 0; i < MAX_TOTALANIMATIONS; i++ ) {
		table[i].firstFrame = 0;
		table[i].numFrames = 0;
		table[i].loopFrames = -1;
		table[i].frameLerp = 100;
	}
	len = trap->FS_Open( path, &f, FS_READ );
	if ( len <= 0 ) {
		if ( f )
			trap->FS_Close( f );
		return 0;
	}
	buf = (char *)malloc( len + 1 );
	if ( !buf ) {
		trap->FS_Close( f );
		return 0;
	}
	trap->FS_Read( buf, len, f );
	buf[len] = 0;
	trap->FS_Close( f );

	for ( line = buf; line && *line; line = next ) {
		char name[AR_NAME];
		int first, count, loop, anim;
		float fps;

		next = strchr( line, '\n' );
		if ( next )
			*next++ = 0;
		if ( sscanf( line, "%63s %d %d %d %f", name, &first, &count, &loop, &fps ) != 5 )
			continue;
		anim = GetIDForString( animTable, name );
		if ( anim < 0 || anim >= MAX_ANIMATIONS || first < 0 || first > 65535 || count < 0 )
			continue; // names only single player has, comments
		if ( fps == 0 )
			fps = 1;
		table[anim].firstFrame = first;
		table[anim].numFrames = count;
		table[anim].loopFrames = loop;
		table[anim].frameLerp = ( fps < 0 ) ? floor( 1000.0f / fps ) : ceil( 1000.0f / fps );
		found++;
	}
	free( buf );
	return found;
}

static arSkel_t *AR_FindSkel( const char *glaIn ) {
	static byte humanoidSkel[AR_GLA_MAXSKEL], skel[AR_GLA_MAXSKEL];
	char gla[MAX_QPATH], folderCfg[MAX_QPATH];
	const animation_t *humanoid = bgAllAnims[0].anims;
	arSkel_t *s;
	char *slash;
	int i, hBones, bones, hEnd, end, found, missing = 0;

	AR_NormalizeGLA( glaIn, gla, sizeof( gla ) );
	if ( !gla[0] || strstr( gla, "players/_humanoid/" ) )
		return NULL; // the normal skeleton folder: nothing special
	// note: this must not need the humanoid table; the first model a client
	// registers is checked before that table is loaded
	for ( i = 0; i < ar_numSkels; i++ ) {
		if ( !strcmp( ar_skels[i].gla, gla ) )
			return ar_skels[i].ok ? &ar_skels[i] : NULL;
	}
	if ( ar_numSkels >= AR_MAX_SKELS )
		return NULL;
	s = &ar_skels[ar_numSkels++];
	memset( s, 0, sizeof( *s ) );
	Q_strncpyz( s->gla, gla, sizeof( s->gla ) );
	s->slot = -1;

	hBones = AR_ReadGLASkeleton( "models/players/_humanoid/_humanoid.gla", humanoidSkel, sizeof( humanoidSkel ), &hEnd );
	bones = AR_ReadGLASkeleton( va( "%s.gla", gla ), skel, sizeof( skel ), &end );
	if ( bones <= 0 || bones != hBones || !AR_SameSkeleton( humanoidSkel, hEnd, skel, end, bones ) ) {
		Com_Printf( S_COLOR_YELLOW "AnimRemap: %s.gla is not a humanoid skeleton (%d bones, humanoid %d, or different bones); the model is replaced as usual\n", gla, bones, hBones );
		return NULL;
	}

	Q_strncpyz( folderCfg, gla, sizeof( folderCfg ) );
	slash = strrchr( folderCfg, '/' );
	if ( !slash )
		return NULL;
	Q_strncpyz( slash, "/animation.cfg", sizeof( folderCfg ) - ( slash - folderCfg ) );
	s->table = ar_skelTables[s - ar_skels];
	found = AR_ReadAnimationCfg( folderCfg, s->table );
	if ( found <= 0 ) {
		Com_Printf( S_COLOR_YELLOW "AnimRemap: %s.gla has no readable %s; the model is replaced as usual\n", gla, folderCfg );
		return NULL;
	}
	// animations this game knows that the file lacks: the model's standing idle
	// (named in the console when the humanoid table says this game uses them)
	for ( i = 0; i < MAX_ANIMATIONS; i++ ) {
		if ( s->table[i].numFrames > 0 )
			continue;
		if ( humanoid && humanoid[i].numFrames > 0 ) {
			if ( missing < 8 )
				Com_Printf( "AnimRemap: %s: no %s, using its BOTH_STAND1\n", folderCfg, GetStringForID( animTable, i ) );
			missing++;
		}
		s->table[i] = s->table[BOTH_STAND1];
	}
	// a slot so the model's animevents.cfg is read against its own frames, and so
	// a plain BG_ParseAnimationFile of this cfg finds it instead of reading the file
	if ( bgNumAllAnims < MAX_ANIM_FILES ) {
		s->slot = bgNumAllAnims++;
		bgAllAnims[s->slot].anims = s->table;
		Q_strncpyz( bgAllAnims[s->slot].filename, folderCfg, sizeof( bgAllAnims[s->slot].filename ) );
	}
	s->ok = qtrue;
	Com_Printf( "AnimRemap: own skeleton %s.gla: humanoid bones, %d animations from %s (%d missing)\n", gla, found, folderCfg, missing );
	return s;
}

qboolean BG_AnimRemap_OwnSkeleton( const char *gla ) {
	return AR_FindSkel( gla ) ? qtrue : qfalse;
}

int BG_AnimRemap_OwnSkeletonSlot( const char *gla ) {
	arSkel_t *s = AR_FindSkel( gla );
	return s ? s->slot : -1;
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

static int AR_FindAnimset( const char *name ) {
	int i;
	for ( i = 0; i < ar_numAnimsets; i++ ) {
		if ( !Q_stricmp( ar_animsets[i].name, name ) )
			return i;
	}
	return -1;
}

// "SET:ANIM" -> index into ar_setAnims, or -1
static int AR_FindSetAnim( const char *target, int *animsetOut ) {
	char setName[AR_NAME];
	const char *colon = strchr( target, ':' );
	int s, i, len;

	if ( !colon )
		return -1;
	len = colon - target + 1;
	Q_strncpyz( setName, target, len < AR_NAME ? len : AR_NAME );
	s = AR_FindAnimset( setName );
	if ( s < 0 )
		return -1;
	for ( i = ar_animsets[s].first; i < ar_animsets[s].first + ar_animsets[s].count; i++ ) {
		if ( !Q_stricmp( ar_setAnims[i].name, colon + 1 ) ) {
			if ( animsetOut )
				*animsetOut = s;
			return i;
		}
	}
	return -1;
}

// animset NAME GLA ANIMATION_CFG [OFFSET]: read animation.cfg lines "name first count loop fps"
static void AR_LoadAnimset( const char *name, const char *gla, const char *cfgPath, int offset, const char *where ) {
	fileHandle_t f;
	arAnimset_t *set;
	char *buf, *line, *next;
	int len, added = 0;

	if ( AR_FindAnimset( name ) >= 0 )
		return; // already loaded (central and model file may both name it)
	if ( ar_numAnimsets >= AR_MAX_ANIMSETS ) {
		Com_Printf( S_COLOR_YELLOW "AnimRemap: %s: more than %d animsets, %s ignored\n", where, AR_MAX_ANIMSETS, name );
		return;
	}
	len = trap->FS_Open( cfgPath, &f, FS_READ );
	if ( len <= 0 ) {
		if ( f )
			trap->FS_Close( f );
		Com_Printf( S_COLOR_YELLOW "AnimRemap: %s: animset %s: cannot read %s\n", where, name, cfgPath );
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

	set = &ar_animsets[ar_numAnimsets++];
	memset( set, 0, sizeof( *set ) );
	Q_strncpyz( set->name, name, sizeof( set->name ) );
	AR_NormalizeGLA( gla, set->gla, sizeof( set->gla ) );
	set->first = ar_numSetAnims;

	for ( line = buf; line && *line; line = next ) {
		char animName[AR_NAME];
		int first, count, loop;
		float fps;

		next = strchr( line, '\n' );
		if ( next )
			*next++ = 0;
		if ( sscanf( line, "%63s %d %d %d %f", animName, &first, &count, &loop, &fps ) != 5 )
			continue; // comments, blank lines, other formats
		if ( animName[0] == '/' )
			continue;
		if ( ar_numSetAnims >= AR_MAX_SETANIMS ) {
			Com_Printf( S_COLOR_YELLOW "AnimRemap: more than %d animset animations, the rest are ignored\n", AR_MAX_SETANIMS );
			break;
		}
		first += offset;
		if ( first < 0 || count < 0 || first + count > 65535 ) {
			Com_Printf( S_COLOR_YELLOW "AnimRemap: %s: %s:%s frames %d..%d out of range\n", where, name, animName, first, first + count );
			continue;
		}
		if ( fps == 0 )
			fps = 1;
		Q_strncpyz( ar_setAnims[ar_numSetAnims].name, animName, AR_NAME );
		ar_setAnims[ar_numSetAnims].anim.firstFrame = first;
		ar_setAnims[ar_numSetAnims].anim.numFrames = count;
		ar_setAnims[ar_numSetAnims].anim.loopFrames = loop;
		ar_setAnims[ar_numSetAnims].anim.frameLerp = ( fps < 0 ) ? floor( 1000.0f / fps ) : ceil( 1000.0f / fps );
		ar_numSetAnims++;
		added++;
	}
	set->count = added;
	free( buf );
	Com_Printf( "AnimRemap: animset %s: %d animations from %s at frame offset %d, shown only on models using %s\n",
		name, added, cfgPath, offset, set->gla );
}

static void AR_AddEntry( const char *model, const char *skin, int from, int to, const char *setTarget, int mode, int source ) {
	arEntry_t *e;

	if ( ar_numEntries >= AR_MAX_ENTRIES ) {
		if ( !ar_warnedFull ) {
			Com_Printf( S_COLOR_YELLOW "AnimRemap: more than %d remaps, the rest are ignored\n", AR_MAX_ENTRIES );
			ar_warnedFull = qtrue;
		}
		return;
	}
	e = &ar_entries[ar_numEntries++];
	memset( e, 0, sizeof( *e ) );
	Q_strncpyz( e->model, model, sizeof( e->model ) );
	Q_strncpyz( e->skin, skin, sizeof( e->skin ) );
	e->from = from;
	e->to = to;
	if ( setTarget )
		Q_strncpyz( e->setTarget, setTarget, sizeof( e->setTarget ) );
	e->mode = mode;
	e->source = source;
}

// One line's FROM/TO pair, with '*' prefix groups expanded. Returns entries added.
static int AR_AddPair( const char *model, const char *skin, const char *fromName, const char *toName, int mode, qboolean modeGiven, int source, const char *where ) {
	int fromLen = strlen( fromName ), toLen = strlen( toName );

	if ( !strcmp( fromName, "*" ) && toLen > 2 && !strcmp( toName + toLen - 2, ":*" ) ) {
		// "* SET:*": every animation of the animset that has a game animation's
		// name replaces that animation. Without a mode, loops (stances, walks,
		// runs, in-air) play at their own speed and the rest keep this game's length.
		char setName[AR_NAME];
		int s, i, added = 0;

		Q_strncpyz( setName, toName, toLen - 1 < AR_NAME ? toLen - 1 : AR_NAME );
		s = AR_FindAnimset( setName );
		if ( s < 0 ) {
			Com_Printf( S_COLOR_YELLOW "AnimRemap: %s: animset %s must be declared (animset line) before \"* %s\"\n", where, setName, toName );
			return 0;
		}
		for ( i = ar_animsets[s].first; i < ar_animsets[s].first + ar_animsets[s].count; i++ ) {
			char target[AR_NAME * 2];
			int id = GetIDForString( animTable, ar_setAnims[i].name );
			if ( id < 0 )
				continue;
			Com_sprintf( target, sizeof( target ), "%s:%s", setName, ar_setAnims[i].name );
			AR_AddEntry( model, skin, id, -1, target,
				modeGiven ? mode : ( ar_setAnims[i].anim.loopFrames != -1 ? AR_FREE : AR_FIT ), source );
			added++;
		}
		return added;
	}

	if ( strchr( toName, ':' ) ) {
		// replacement from an animset; resolved when the model is built (the
		// animset may be declared later, in the model's own file)
		int from = GetIDForString( animTable, fromName );
		if ( from < 0 ) {
			Com_Printf( S_COLOR_YELLOW "AnimRemap: %s: unknown animation %s\n", where, fromName );
			return 0;
		}
		AR_AddEntry( model, skin, from, -1, toName, mode, source );
		return 1;
	}

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
			AR_AddEntry( model, skin, animTable[i].id, to, NULL, mode, source );
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
		AR_AddEntry( model, skin, from, to, NULL, mode, source );
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
	int len, added = 0;
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
		char tok[5][MAX_QPATH];
		char model[AR_NAME], skin[AR_NAME], where[MAX_QPATH + 16];
		int n = 0, need, mode, source;
		const char *t = COM_ParseExt( &p, qtrue );

		if ( !t || !t[0] )
			break;
		if ( t[0] == '#' || t[0] == ';' ) {
			SkipRestOfLine( &p );
			continue;
		}
		Com_sprintf( where, sizeof( where ), "%s line %d", filename, COM_GetCurrentParseLine() );
		Q_strncpyz( tok[n++], t, MAX_QPATH );
		while ( 1 ) {
			t = COM_ParseExt( &p, qfalse );
			if ( !t || !t[0] )
				break; // end of line (COM_ParseExt has already stepped over the newline)
			if ( n < 5 )
				Q_strncpyz( tok[n++], t, MAX_QPATH );
		}

		if ( !Q_stricmp( tok[0], "skeleton" ) ) {
			// skeleton MODEL GLA: read by the renderer when the model is loaded
			// (rd-common/tr_animremap_gla.h); the model then shows up here with
			// that GLA and is drawn with the animation.cfg next to it
			continue;
		}
		if ( !Q_stricmp( tok[0], "animset" ) ) {
			if ( n < 4 ) {
				Com_Printf( S_COLOR_YELLOW "AnimRemap: %s: expected animset NAME GLA ANIMATION_CFG [OFFSET]\n", where );
				continue;
			}
			AR_LoadAnimset( tok[1], tok[2], tok[3], n > 4 ? atoi( tok[4] ) : 0, where );
			continue;
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
		added += AR_AddPair( model, skin, tok[need - 2], tok[need - 1], mode, n > need ? qtrue : qfalse, source, where );
	}
	free( buf );
	Com_Printf( "AnimRemap: %d remaps from %s\n", added, filename );
}

static void AR_LoadCentral( void ) {
	if ( ar_centralLoaded )
		return;
	ar_centralLoaded = qtrue;
	AR_ParseFile( "per-model-anims-config.cfg", NULL );
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
	AR_ParseFile( va( "models/players/%s/per-model-anims-config.cfg", model ), model );
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

// "model" matches exactly; "model*" matches every model whose name starts with "model"
static qboolean AR_ModelMatch( const char *pattern, const char *model ) {
	int len = strlen( pattern );
	if ( len > 1 && pattern[len - 1] == '*' )
		return Q_stricmpn( pattern, model, len - 1 ) ? qfalse : qtrue;
	return Q_stricmp( pattern, model ) ? qfalse : qtrue;
}

static int AR_FindOrBuildSet( const char *model, const char *skin, const char *gla ) {
	static short map[MAX_TOTALANIMATIONS];	// index into ar_entries
	const animation_t *base = bgAllAnims[0].anims;
	const animation_t *skelFrames;			// where replacement BOTH_* frames come from
	arSet_t *set;
	int i, src, count = 0;
	qboolean report;

	for ( i = 0; i < ar_numSets; i++ ) {
		if ( !Q_stricmp( ar_sets[i].model, model ) && !Q_stricmp( ar_sets[i].skin, skin ) && !strcmp( ar_sets[i].gla, gla ) )
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

	// print the lengths only the first time this model/skin is built
	report = qtrue;
	for ( i = 0; i < ar_numSets; i++ ) {
		if ( !Q_stricmp( ar_sets[i].model, model ) && !Q_stricmp( ar_sets[i].skin, skin ) )
			report = qfalse;
	}

	for ( i = 0; i < MAX_TOTALANIMATIONS; i++ )
		map[i] = -1;

	// apply in order of precedence, later wins
	for ( src = 0; src < AR_SRC_COUNT; src++ ) {
		for ( i = 0; i < ar_numEntries; i++ ) {
			const arEntry_t *e = &ar_entries[i];
			if ( e->source != src )
				continue;
			if ( src != AR_SRC_ALL && !AR_ModelMatch( e->model, model ) )
				continue;
			if ( src == AR_SRC_MODELSKIN && Q_stricmp( e->skin, skin ) )
				continue;
			map[e->from] = i;
		}
	}

	set = &ar_sets[ar_numSets];
	memset( set, 0, sizeof( *set ) );
	Q_strncpyz( set->model, model, sizeof( set->model ) );
	Q_strncpyz( set->skin, skin, sizeof( set->skin ) );
	Q_strncpyz( set->gla, gla, sizeof( set->gla ) );

	// a model on its own skeleton file: every animation comes from its own
	// animation.cfg; one-shot moves keep this game's length (fit), loops play
	// at their own speed (free), so gameplay timing is unchanged
	skelFrames = base;
	{
		arSkel_t *own = AR_FindSkel( gla );
		if ( own ) {
			int differ = 0;
			skelFrames = own->table;
			set->visual = AR_AllocTable( base );
			if ( set->visual ) {
				for ( i = 0; i < MAX_ANIMATIONS; i++ ) {
					if ( own->table[i].numFrames <= 0 )
						continue;
					if ( base[i].numFrames <= 0 ) {
						set->visual[i] = own->table[i];
						continue;
					}
					set->visual[i] = AR_MakeEntry( &base[i], &own->table[i], own->table[i].loopFrames != -1 ? AR_FREE : AR_FIT );
					if ( AR_AnimLen( &base[i] ) != AR_AnimLen( &own->table[i] ) )
						differ++;
					count++;
				}
				if ( report )
					Com_Printf( "AnimRemap: %s%s%s uses its own skeleton %s: %d animations from it, %d with a different length than here (moves keep this game's length, loops play at their own speed)\n",
						model, skin[0] ? "/" : "", skin, gla, count, differ );
			}
		}
	}

	for ( i = 0; i < MAX_TOTALANIMATIONS; i++ ) {
		const arEntry_t *e;
		const animation_t *a, *b;
		char toName[AR_NAME * 2];
		qboolean showHere = qtrue;
		int lenA, lenB, mode;

		if ( map[i] < 0 )
			continue;
		e = &ar_entries[map[i]];
		mode = e->mode;
		a = &base[i];

		if ( e->to >= 0 ) {
			b = &skelFrames[e->to];
			Q_strncpyz( toName, GetStringForID( animTable, e->to ), sizeof( toName ) );
			if ( b->numFrames <= 0 ) {
				if ( report )
					Com_Printf( S_COLOR_YELLOW "AnimRemap: %s%s%s: %s has no frames in the humanoid skeleton, ignored\n",
						model, skin[0] ? "/" : "", skin, toName );
				continue;
			}
		}
		else {
			int animset = -1, s = AR_FindSetAnim( e->setTarget, &animset );
			if ( s < 0 ) {
				if ( report )
					Com_Printf( S_COLOR_YELLOW "AnimRemap: %s%s%s: %s not found (no animset with that name and animation)\n",
						model, skin[0] ? "/" : "", skin, e->setTarget );
				continue;
			}
			b = &ar_setAnims[s].anim;
			Q_strncpyz( toName, e->setTarget, sizeof( toName ) );
			// the frames exist only in the animset's GLA
			showHere = !strcmp( ar_animsets[animset].gla, gla ) ? qtrue : qfalse;
			if ( b->numFrames <= 0 )
				continue;
		}

		if ( showHere ) {
			if ( !set->visual ) {
				set->visual = AR_AllocTable( base );
				if ( !set->visual ) {
					Com_Printf( S_COLOR_YELLOW "AnimRemap: out of tables, %s plays its normal animations\n", model );
					break;
				}
			}
			set->visual[i] = AR_MakeEntry( a, b, mode );
			count++;
		}
		if ( mode == AR_TIMING ) {
			// timing only needs the length, which is the same wherever the frames are
			if ( !set->pmove )
				set->pmove = AR_AllocTable( base );
			if ( set->pmove ) {
				set->pmove[i] = AR_MakeEntry( a, b, AR_TIMING );
				set->hasTiming = qtrue;
			}
		}

		if ( !report )
			continue;
		lenA = AR_AnimLen( a );
		lenB = AR_AnimLen( b );
		if ( mode == AR_TIMING ) {
			Com_Printf( "AnimRemap: %s%s%s: %s -> %s (timing): %s%d ms -> %d ms in gameplay%s\n",
				model, skin[0] ? "/" : "", skin, GetStringForID( animTable, i ), toName,
				lenA != lenB ? S_COLOR_YELLOW : "", lenA, lenB, lenA != lenB ? " (move timing changes)" S_COLOR_WHITE : "" );
		}
		else if ( lenA != lenB ) {
			animation_t shown = AR_MakeEntry( a, b, mode );
			Com_Printf( "AnimRemap: %s%s%s: %s -> %s (%s): " S_COLOR_YELLOW "lengths differ, %d ms vs %d ms" S_COLOR_WHITE ", %s; gameplay timing unchanged\n",
				model, skin[0] ? "/" : "", skin, GetStringForID( animTable, i ), toName,
				arModeNames[mode], lenA, lenB,
				mode == AR_FIT ? va( "shown over %d ms", AR_AnimLen( &shown ) ) : "shown at its own speed" );
		}
		else {
			Com_Printf( "AnimRemap: %s%s%s: %s -> %s (%s): both %d ms\n",
				model, skin[0] ? "/" : "", skin, GetStringForID( animTable, i ), toName,
				arModeNames[mode], lenA );
		}
	}
	set->numRemaps = set->visual ? count : 0;
	return ar_numSets++;
}

static const arSet_t *AR_SetForClient( int clientNum, int animIndex, const char *model, const char *skin, const char *glaIn ) {
	char gla[MAX_QPATH];
	int set;

	if ( animIndex != 0 || !model || !model[0] || !bgAllAnims[0].anims )
		return NULL;
	if ( !skin )
		skin = "";
	AR_NormalizeGLA( glaIn, gla, sizeof( gla ) );

	if ( clientNum >= 0 && clientNum < MAX_CLIENTS ) {
		arClientCache_t *c = &ar_clients[clientNum];
		if ( c->version != ar_version || Q_stricmp( c->model, model ) || Q_stricmp( c->skin, skin ) || strcmp( c->gla, gla ) ) {
			Q_strncpyz( c->model, model, sizeof( c->model ) );
			Q_strncpyz( c->skin, skin, sizeof( c->skin ) );
			Q_strncpyz( c->gla, gla, sizeof( c->gla ) );
			c->version = ar_version;
			c->set = AR_FindOrBuildSet( c->model, c->skin, c->gla );
		}
		set = c->set;
	}
	else {
		set = AR_FindOrBuildSet( model, skin, gla );
	}

	if ( set < 0 )
		return NULL;
	return &ar_sets[set];
}

const animation_t *BG_AnimRemap_Visual( int clientNum, int animIndex, const char *model, const char *skin, const char *gla ) {
	const arSet_t *set = AR_SetForClient( clientNum, animIndex, model, skin, gla );
	if ( set && set->numRemaps )
		return set->visual;
	return bgAllAnims[animIndex].anims;
}

animation_t *BG_AnimRemap_Pmove( int clientNum, int animIndex, const char *model, const char *skin, const char *gla ) {
	const arSet_t *set = AR_SetForClient( clientNum, animIndex, model, skin, gla );
	if ( set && set->hasTiming )
		return set->pmove;
	return NULL;
}

void BG_AnimRemap_Reload( void ) {
	ar_numEntries = 0;
	ar_numModelFiles = 0;
	ar_numAnimsets = 0;
	ar_numSetAnims = 0;
	ar_numSets = 0;
	ar_numTables = 0;
	ar_centralLoaded = qfalse;
	ar_warnedFull = qfalse;
	ar_version++;
}

void BG_AnimRemap_Reset( void ) {
	// the anim sets were cleared: own-skeleton tables and their slots are gone too
	ar_numSkels = 0;
	BG_AnimRemap_Reload();
}

void BG_AnimRemap_List( void ) {
	int i;

	AR_LoadCentral();
	Com_Printf( "AnimRemap: %d remap lines, %d animsets loaded, %d models built\n", ar_numEntries, ar_numAnimsets, ar_numSets );
	for ( i = 0; i < ar_numAnimsets; i++ )
		Com_Printf( "  animset %s: %d animations, GLA %s\n", ar_animsets[i].name, ar_animsets[i].count, ar_animsets[i].gla );
	for ( i = 0; i < ar_numSets; i++ ) {
		Com_Printf( "  %s%s%s (GLA %s): %d animations remapped%s\n", ar_sets[i].model, ar_sets[i].skin[0] ? "/" : "", ar_sets[i].skin,
			ar_sets[i].gla[0] ? ar_sets[i].gla : "unknown", ar_sets[i].numRemaps, ar_sets[i].hasTiming ? ", some with gameplay timing" : "" );
	}
}
