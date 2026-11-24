/*
===========================================================================
tr_tworld.cpp -- cooked static world ("tworld"), version 0 prototype

A map may ship maps/<name>.tworld next to its BSP. The file holds a table of
unique meshes, their per-material index ranges and a table of placements
(instances). The BSP keeps collision, entities and spawns; this file is only
drawn.

Version 0 deliberately reuses the existing MD3 vertex-buffer path
(SF_VBO_MDVMESH, vbo_mdv pipelines) and ordinary shader_t materials, so no
new SPIR-V is needed. Each visible placement costs one draw call per
material range: there is no GPU instancing, LOD or lighting yet.

The whole pass is one draw surface (SF_TWORLD) owned by the world entity;
its back-end function culls placements against the view frustum and issues
the draws itself, so the 4095 render-entity and 65536 draw-surface limits do
not apply to placements.
===========================================================================
*/

#include "tr_local.h"

#ifdef USE_VBO_MDV

#define TWORLD_MAGIC	"TWLD"
#define TWORLD_VERSION	1

#pragma pack(push, 1)
typedef struct {
	char		magic[4];
	uint32_t	version;
	uint32_t	numMaterials;
	uint32_t	numMeshes;
	uint32_t	numSubmeshes;
	uint32_t	numInstances;
	uint32_t	numVerts;
	uint32_t	numIndexes;
	float		mins[3];
	float		maxs[3];
	float		unitsPerMetre;
	uint32_t	reserved[7];
} twHeader_t;				// 88 bytes

typedef struct {
	char		shader[64];
} twMaterial_t;

typedef struct {
	uint32_t	firstVert, numVerts;
	uint32_t	firstIndex, numIndexes;
	uint32_t	firstSub, numSubs;
	float		center[3];
	float		radius;
} twMesh_t;					// 40 bytes

typedef struct {
	uint32_t	material;
	uint32_t	firstIndex;		// relative to the mesh's first index
	uint32_t	numIndexes;
	uint32_t	reserved;
} twSubmesh_t;				// 16 bytes

typedef struct {
	uint32_t	mesh;
	float		m[12];			// row-major 3x4: world = m * (x, y, z, 1)
	float		center[3];		// world-space bounding sphere
	float		radius;
} twInstance_t;				// 68 bytes

typedef struct {
	float		xyz[3];
	float		normal[3];
	float		st[2];
} twVertex_t;				// 32 bytes
#pragma pack(pop)

typedef struct {
	shader_t		*shader;
	srfVBOMDVMesh_t	surf;
} tworldSub_t;

typedef struct {
	int				firstSub, numSubs;
} tworldMesh_t;

typedef struct {
	int				mesh;
	float			matrix[16];		// column-major model matrix
	vec3_t			center;
	float			radius;
} tworldInst_t;

typedef struct tworld_s {
	surfaceType_t	surfaceType;	// SF_TWORLD, must be first

	int				numMeshes, numSubs, numInstances;
	tworldMesh_t	*meshes;
	tworldSub_t		*subs;
	tworldInst_t	*instances;

	vec3_t			mins, maxs;
	int				numVerts, numIndexes;

	// statistics of the last view drawn
	int				c_instances, c_draws, c_indexes;
	int				lastStatsTime;
} tworld_t;

static tworld_t	*s_tworld;
static cvar_t	*r_tworld;
static cvar_t	*r_tworldStats;

#define TW_ERR( msg ) { ri.Printf( PRINT_WARNING, "R_LoadTWorld: %s: " msg "\n", name ); ri.FS_FreeFile( buffer ); return; }

/*
=================
R_LoadTWorld

Called once per map after the BSP has loaded. bspName is "maps/<name>.bsp".
=================
*/
void R_LoadTWorld( const char *bspName )
{
	char			name[MAX_QPATH];
	byte			*buffer = NULL;
	long			len;
	const twHeader_t	*h;
	const twMaterial_t	*fmat;
	const twMesh_t		*fmesh;
	const twSubmesh_t	*fsub;
	const twInstance_t	*finst;
	const twVertex_t	*fvert;
	const uint32_t		*findex;
	shader_t		**shaders;
	tworld_t		*tw;
	uint32_t		i, j;
	size_t			need;
	int				startTime;

	s_tworld = NULL;

	r_tworld = ri.Cvar_Get( "r_tworld", "1", CVAR_ARCHIVE_ND, "Draw the cooked static world (maps/<name>.tworld) when a map has one" );
	r_tworldStats = ri.Cvar_Get( "r_tworldStats", "0", CVAR_TEMP, "Print cooked-world draw statistics once per second" );

	if ( !vk.vboMdvActive )
		return;

	COM_StripExtension( bspName, name, sizeof( name ) );
	Q_strcat( name, sizeof( name ), ".tworld" );

	len = ri.FS_ReadFile( name, (void **)&buffer );
	if ( len <= 0 || !buffer )
		return;		// most maps have none

	startTime = ri.Milliseconds();

	if ( len < (long)sizeof( twHeader_t ) )
		TW_ERR( "file too short" );

	h = (const twHeader_t *)buffer;
	if ( memcmp( h->magic, TWORLD_MAGIC, 4 ) || h->version != TWORLD_VERSION )
		TW_ERR( "wrong magic or version" );

	need = sizeof( twHeader_t )
		+ (size_t)h->numMaterials * sizeof( twMaterial_t )
		+ (size_t)h->numMeshes * sizeof( twMesh_t )
		+ (size_t)h->numSubmeshes * sizeof( twSubmesh_t )
		+ (size_t)h->numInstances * sizeof( twInstance_t )
		+ (size_t)h->numVerts * sizeof( twVertex_t )
		+ (size_t)h->numIndexes * sizeof( uint32_t );
	if ( need != (size_t)len )
		TW_ERR( "size does not match the header counts" );

	fmat	= (const twMaterial_t *)( h + 1 );
	fmesh	= (const twMesh_t *)( fmat + h->numMaterials );
	fsub	= (const twSubmesh_t *)( fmesh + h->numMeshes );
	finst	= (const twInstance_t *)( fsub + h->numSubmeshes );
	fvert	= (const twVertex_t *)( finst + h->numInstances );
	findex	= (const uint32_t *)( fvert + h->numVerts );

	// validate every range before touching the GPU
	for ( i = 0; i < h->numMeshes; i++ ) {
		const twMesh_t *m = &fmesh[i];
		if ( (uint64_t)m->firstVert + m->numVerts > h->numVerts || (uint64_t)m->firstIndex + m->numIndexes > h->numIndexes
			|| (uint64_t)m->firstSub + m->numSubs > h->numSubmeshes || m->numVerts == 0 )
			TW_ERR( "mesh range out of bounds" );
		for ( j = 0; j < m->numSubs; j++ ) {
			const twSubmesh_t *s = &fsub[m->firstSub + j];
			if ( s->material >= h->numMaterials || (uint64_t)s->firstIndex + s->numIndexes > m->numIndexes )
				TW_ERR( "submesh range out of bounds" );
		}
		for ( j = 0; j < m->numIndexes; j++ ) {
			if ( findex[m->firstIndex + j] >= m->numVerts )
				TW_ERR( "vertex index out of bounds" );
		}
	}
	for ( i = 0; i < h->numInstances; i++ ) {
		if ( finst[i].mesh >= h->numMeshes )
			TW_ERR( "instance mesh out of bounds" );
	}

	tw = (tworld_t *)ri.Hunk_Alloc( sizeof( *tw ), h_low );
	tw->surfaceType = SF_TWORLD;
	tw->numMeshes = h->numMeshes;
	tw->numSubs = h->numSubmeshes;
	tw->numInstances = h->numInstances;
	tw->numVerts = h->numVerts;
	tw->numIndexes = h->numIndexes;
	VectorCopy( h->mins, tw->mins );
	VectorCopy( h->maxs, tw->maxs );
	tw->meshes = (tworldMesh_t *)ri.Hunk_Alloc( sizeof( tworldMesh_t ) * h->numMeshes, h_low );
	tw->subs = (tworldSub_t *)ri.Hunk_Alloc( sizeof( tworldSub_t ) * ( h->numSubmeshes + 1 ), h_low );
	tw->instances = (tworldInst_t *)ri.Hunk_Alloc( sizeof( tworldInst_t ) * ( h->numInstances + 1 ), h_low );

	// materials are ordinary shaders (scripts generated by the cooker)
	shaders = (shader_t **)ri.Hunk_AllocateTempMemory( sizeof( shader_t * ) * ( h->numMaterials + 1 ) );
	for ( i = 0; i < h->numMaterials; i++ ) {
		char sname[MAX_QPATH];
		Q_strncpyz( sname, fmat[i].shader, sizeof( sname ) );
		shaders[i] = R_FindShader( sname, lightmapsNone, stylesDefault, qtrue );
		if ( !shaders[i] )
			shaders[i] = tr.defaultShader;
	}

	// one vertex buffer and one index buffer per mesh, in the MD3 VBO layout
	for ( i = 0; i < h->numMeshes; i++ ) {
		const twMesh_t *m = &fmesh[i];
		const int stride = sizeof( vec4_t ) + sizeof( vec4_t ) + sizeof( vec2_t ) + sizeof( vec4_t );
		const int dataSize = stride * m->numVerts;
		byte *data = (byte *)Z_Malloc( dataSize, TAG_TEMP_WORKSPACE, qtrue );
		byte *p = data;
		char bufName[MAX_QPATH];
		VBO_t *vbo;
		IBO_t *ibo;

		for ( j = 0; j < m->numVerts; j++, p += stride ) {
			const twVertex_t *v = &fvert[m->firstVert + j];
			float *out = (float *)p;
			out[0] = v->xyz[0]; out[1] = v->xyz[1]; out[2] = v->xyz[2]; out[3] = 0.0f;
			out[4] = v->normal[0]; out[5] = v->normal[1]; out[6] = v->normal[2]; out[7] = 0.0f;
			out[8] = v->st[0]; out[9] = v->st[1];
		}

		Com_sprintf( bufName, sizeof( bufName ), "tworld_%u", i );
		vbo = R_CreateVBO( bufName, data, dataSize );
		ibo = R_CreateIBO( bufName, (const byte *)( findex + m->firstIndex ), sizeof( uint32_t ) * m->numIndexes );
		Z_Free( data );

		vbo->offsets[0] = 0;
		vbo->offsets[5] = sizeof( vec4_t );
		vbo->offsets[2] = sizeof( vec4_t ) * 2;
		vbo->offsets[8] = sizeof( vec4_t ) * 2 + sizeof( vec2_t );

		tw->meshes[i].firstSub = m->firstSub;
		tw->meshes[i].numSubs = m->numSubs;

		for ( j = 0; j < m->numSubs; j++ ) {
			const twSubmesh_t *s = &fsub[m->firstSub + j];
			tworldSub_t *out = &tw->subs[m->firstSub + j];

			out->shader = shaders[s->material];
			out->surf.surfaceType = SF_VBO_MDVMESH;
			out->surf.vbo = vbo;
			out->surf.ibo = ibo;
			out->surf.indexOffset = s->firstIndex;
			out->surf.numIndexes = s->numIndexes;
			out->surf.numVerts = m->numVerts;
			out->surf.minIndex = 0;
			out->surf.maxIndex = m->numVerts - 1;
		}
	}
	ri.Hunk_FreeTempMemory( shaders );

	for ( i = 0; i < h->numInstances; i++ ) {
		const twInstance_t *in = &finst[i];
		tworldInst_t *out = &tw->instances[i];
		float *mm = out->matrix;

		out->mesh = in->mesh;
		mm[0] = in->m[0];  mm[1] = in->m[4];  mm[2] = in->m[8];   mm[3] = 0.0f;
		mm[4] = in->m[1];  mm[5] = in->m[5];  mm[6] = in->m[9];   mm[7] = 0.0f;
		mm[8] = in->m[2];  mm[9] = in->m[6];  mm[10] = in->m[10]; mm[11] = 0.0f;
		mm[12] = in->m[3]; mm[13] = in->m[7]; mm[14] = in->m[11]; mm[15] = 1.0f;
		VectorCopy( in->center, out->center );
		out->radius = in->radius;
	}

	ri.Printf( PRINT_ALL, "R_LoadTWorld: %s: %u meshes, %u submeshes, %u instances, %u materials, %u verts, %u tris, %.1f MB file, %i ms\n",
		name, h->numMeshes, h->numSubmeshes, h->numInstances, h->numMaterials, h->numVerts, h->numIndexes / 3,
		len / ( 1024.0f * 1024.0f ), ri.Milliseconds() - startTime );

	ri.FS_FreeFile( buffer );
	s_tworld = tw;
}

/*
=================
R_AddTWorldSurface

Front end: one draw surface for the whole cooked world, and its bounds added
to the visible bounds so the far plane covers it.
=================
*/
void R_AddTWorldSurface( void )
{
	if ( !s_tworld || !r_tworld || !r_tworld->integer )
		return;

	AddPointToBounds( s_tworld->mins, tr.viewParms.visBounds[0], tr.viewParms.visBounds[1] );
	AddPointToBounds( s_tworld->maxs, tr.viewParms.visBounds[0], tr.viewParms.visBounds[1] );

	R_AddDrawSurf( &s_tworld->surfaceType, tr.defaultShader, 0, 0 );
}

/*
=================
RB_SurfaceTWorld

Back end: cull placements, set the model-view matrix per placement and draw
each material range through the normal stage iterator.
=================
*/
void RB_SurfaceTWorld( void *surface )
{
	tworld_t		*tw = (tworld_t *)surface;
	shader_t		*savedShader = tess.shader;
	const int		savedFog = tess.fogNum;
	const cplane_t	*frustum = backEnd.viewParms.frustum;
	const qboolean	cull = (qboolean)( !r_nocull->integer );
	float			modelView[16];
	int				i, j, p;

	// finish whatever batch was open (normally nothing: our dummy shader has no geometry)
	RB_EndSurface();

	tw->c_instances = tw->c_draws = tw->c_indexes = 0;

	for ( i = 0; i < tw->numInstances; i++ ) {
		const tworldInst_t *inst = &tw->instances[i];
		const tworldMesh_t *mesh = &tw->meshes[inst->mesh];

		if ( cull ) {
			for ( p = 0; p < 4; p++ ) {
				if ( DotProduct( inst->center, frustum[p].normal ) - frustum[p].dist < -inst->radius )
					break;
			}
			if ( p < 4 )
				continue;
		}

		myGlMultMatrix( inst->matrix, backEnd.viewParms.world.modelViewMatrix, modelView );
		Com_Memcpy( vk_world.modelview_transform, modelView, 64 );
		vk_update_mvp( NULL );

		tw->c_instances++;

		for ( j = 0; j < mesh->numSubs; j++ ) {
			tworldSub_t *sub = &tw->subs[mesh->firstSub + j];

			if ( !sub->surf.numIndexes )
				continue;

			RB_BeginSurface( sub->shader, 0 );
			RB_SurfaceVBOMDVMesh( &sub->surf );
			RB_EndSurface();

			tw->c_draws++;
			tw->c_indexes += sub->surf.numIndexes;
		}
	}

	// back to the world matrix and the batch the caller expects
	Com_Memcpy( vk_world.modelview_transform, backEnd.viewParms.world.modelViewMatrix, 64 );
	vk_update_mvp( NULL );
	RB_BeginSurface( savedShader, savedFog );

	if ( r_tworldStats && r_tworldStats->integer && backEnd.viewParms.portalView == PV_NONE ) {
		const int now = ri.Milliseconds();
		if ( now - tw->lastStatsTime >= 1000 ) {
			tw->lastStatsTime = now;
			ri.Printf( PRINT_ALL, "TWORLD view: %i of %i instances, %i draws, %i tris\n",
				tw->c_instances, tw->numInstances, tw->c_draws, tw->c_indexes / 3 );
		}
	}
}

#else // !USE_VBO_MDV

void R_LoadTWorld( const char *bspName ) {}
void R_AddTWorldSurface( void ) {}
void RB_SurfaceTWorld( void *surface ) {}

#endif
