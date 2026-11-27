/*
===========================================================================
NicJK Unlimited - animremap.cfg "skeleton" lines (renderer side)

    skeleton  MODEL  GLA

makes every .glm in models/players/MODEL/ use GLA (path without or with
.gla) instead of the one named in its header, e.g.

    skeleton  kyle  models/players/_humanoid_vader/_humanoid

The GLA must have the humanoid bones; the game side (bg_animremap.c) checks
that and draws the model with the animation.cfg next to that GLA. Only used
when cg_animRemap or g_animRemap is on, and only when the GLA file exists.
The header's animName is rewritten in the loaded copy of the model, so
G2API_GetGLAName reports the GLA really in use.

Models stay cached: a changed line applies after the model is loaded again
(vid_restart or restarting the game).

Each renderer includes this once, in the file that loads .glm files. It uses
the renderer's import table (ri).
===========================================================================
*/

#pragma once

static void R_AnimRemapGLAOverride( const char *modName, char *animName, int animNameSize )
{
	char model[MAX_QPATH];
	char *buf = NULL;
	const char *p;
	char *line, *next;
	long len;
	int i;

	if ( !ri.Cvar_VariableIntegerValue( "cg_animRemap" ) && !ri.Cvar_VariableIntegerValue( "g_animRemap" ) )
		return;
	if ( !modName || Q_stricmpn( modName, "models/players/", 15 ) )
		return;

	p = modName + 15;
	for ( i = 0; p[i] && p[i] != '/' && p[i] != '\\' && i < (int)sizeof( model ) - 1; i++ )
		model[i] = p[i];
	model[i] = 0;
	if ( !model[0] || ( p[i] != '/' && p[i] != '\\' ) )
		return;

	len = ri.FS_ReadFile( "animremap.cfg", (void **)&buf );
	if ( len <= 0 || !buf )
		return;

	for ( line = buf; line && *line; line = next )
	{
		char key[64], name[MAX_QPATH], gla[MAX_QPATH];
		char *dot;

		next = strchr( line, '\n' );
		if ( next )
			*next++ = 0;
		if ( sscanf( line, "%63s %63s %63s", key, name, gla ) != 3 )
			continue;
		if ( Q_stricmp( key, "skeleton" ) || Q_stricmp( name, model ) )
			continue;

		dot = strrchr( gla, '.' );
		if ( dot && !Q_stricmp( dot, ".gla" ) )
			*dot = 0;
		if ( !Q_stricmp( gla, animName ) )
			break;
		if ( ri.FS_ReadFile( va( "%s.gla", gla ), NULL ) <= 0 )
		{
			ri.Printf( PRINT_ALL, S_COLOR_YELLOW "AnimRemap: skeleton %s %s: no such GLA, %s keeps %s\n", model, gla, modName, animName );
			break;
		}
		ri.Printf( PRINT_ALL, "AnimRemap: %s uses skeleton %s instead of %s (animremap.cfg)\n", modName, gla, animName );
		Q_strncpyz( animName, gla, animNameSize );
		break;
	}
	ri.FS_FreeFile( buf );
}
