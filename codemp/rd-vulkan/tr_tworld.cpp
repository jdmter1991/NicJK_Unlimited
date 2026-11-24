/*
===========================================================================
tr_tworld.cpp -- cooked static world ("tworld"), prototype

A map may ship maps/<name>.tworld next to its BSP. The file holds a table of
unique meshes, their per-material index ranges and a table of placements
(instances). The BSP keeps collision, entities and spawns; this file is only
drawn.

This prototype deliberately reuses the existing MD3 vertex-buffer path
(SF_VBO_MDVMESH, vbo_mdv pipelines) and ordinary shader_t materials, so no
new SPIR-V is needed. Each visible placement costs one draw call per
material range (no GPU instancing).

File version 2 adds: a constant tint per material, a sun and an ambient
colour (applied through "rgbGen lightingDiffuse" with a private entity
uniform per placement), up to three levels of detail per mesh chosen by
projected size, and culling of placements that are too small on screen.

Materials flagged as blended (water, glass, decals, glow) are drawn by a
second draw surface that sorts with the other blended shaders, after all
opaque geometry; within it placements are not depth-sorted.

The whole pass is one draw surface (SF_TWORLD) owned by the world entity;
its back-end function culls placements against the view frustum and issues
the draws itself, so the 4095 render-entity and 65536 draw-surface limits do
not apply to placements.
===========================================================================
*/

#include "tr_local.h"

#ifdef USE_VBO_MDV

#define TWORLD_MAGIC	"TWLD"
#define TWORLD_VERSION	2
#define TWORLD_MAX_LODS	3

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
	float		sunDir[3];		// unit vector pointing towards the sun
	float		sunColor[3];
	float		ambientColor[3];
	uint32_t	reserved[4];
} twHeader_t;				// 112 bytes

typedef struct {
	char		shader[64];
	float		tint[3];
	uint32_t	flags;			// TWMAT_*
} twMaterial_t;				// 80 bytes

#define TWMAT_BLEND		1		// drawn in the blended pass
// flags bits 8-15: opacity * 255 (0 = opaque); bits 16-31: detail texture repeats per unit of UV (0 = none).
// The detail texture is the image of the material shader's second stage.

typedef struct {
	uint32_t	firstVert, numVerts;
	uint32_t	firstIndex, numIndexes;
	uint32_t	numLods;
	uint32_t	lodFirstSub[TWORLD_MAX_LODS];
	uint32_t	lodNumSubs[TWORLD_MAX_LODS];
	float		center[3];
	float		radius;
} twMesh_t;					// 60 bytes

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
	int				tintIndex;		// index into tworld_t::tints
	int				pass;			// 0 opaque, 1 blended
	uint32_t		pipeline[2];	// instanced pipeline index + 1 (normal view, mirror view); 0 = not created yet
	srfVBOMDVMesh_t	surf;
} tworldSub_t;

typedef struct {
	int				numLods;
	int				lodFirstSub[TWORLD_MAX_LODS];
	int				lodNumSubs[TWORLD_MAX_LODS];
	int				lodPassMask[TWORLD_MAX_LODS];	// bit 0: has opaque ranges, bit 1: has blended ranges
} tworldMesh_t;

typedef struct {
	int				mesh;
	float			matrix[16];		// column-major model matrix
	vec3_t			center;
	float			radius;
} tworldInst_t;

typedef struct tworld_s {
	surfaceType_t	surfaceType;	// SF_TWORLD, must be first: the opaque pass
	surfaceType_t	blendSurfaceType;	// SF_TWORLD again: the blended pass
	shader_t		*blendSortShader;	// a blended material's shader, used only to sort the blended pass

	int				numMeshes, numSubs, numInstances;
	tworldMesh_t	*meshes;
	tworldSub_t		*subs;
	tworldInst_t	*instances;

	vec3_t			mins, maxs;
	int				numVerts, numIndexes;

	int				numTints;
	vec3_t			*tints;			// one per material
	float			*alphas;		// one per material: opacity for the instanced path
	float			*details;		// one per material: detail repeats per unit of UV, 0 = none

	// instanced path, per-frame scratch
	int				*visInst;		// visible placement indexes
	byte			*visLod;
	int				*batchCount, *batchStart, *batchCursor;	// per submesh
	int				*subOrder;		// submesh indexes sorted by shader
	vec3_t			sunDir, sunColor, ambientColor;

	// statistics of the last view drawn
	int				c_instances, c_draws, c_indexes, c_small, c_lod[TWORLD_MAX_LODS], c_uboFail;
	int				lastStatsTime;
} tworld_t;

static tworld_t	*s_tworld;
static cvar_t	*r_tworld;
static cvar_t	*r_tworldStats;
static cvar_t	*r_tworldCullSize;
static cvar_t	*r_tworldLodSize1;
static cvar_t	*r_tworldLodSize2;
static cvar_t	*r_tworldLight;
static cvar_t	*r_tworldInstancing;

static const tworldSub_t *s_sortSubs;
static int TW_CompareSubs( const void *a, const void *b )
{
	const shader_t *sa = s_sortSubs[*(const int *)a].shader, *sb = s_sortSubs[*(const int *)b].shader;
	if ( sa != sb )
		return ( sa < sb ) ? -1 : 1;
	return *(const int *)a - *(const int *)b;
}

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
	uint32_t		i, j, l;
	size_t			need;
	int				startTime;

	s_tworld = NULL;

	r_tworld = ri.Cvar_Get( "r_tworld", "1", CVAR_ARCHIVE_ND, "Draw the cooked static world (maps/<name>.tworld) when a map has one" );
	r_tworldStats = ri.Cvar_Get( "r_tworldStats", "0", CVAR_TEMP, "Print cooked-world draw statistics once per second" );
	// sizes are bounding-sphere radius divided by distance (roughly 1/1000 per pixel of radius at 1080p)
	r_tworldCullSize = ri.Cvar_Get( "r_tworldCullSize", "0.004", CVAR_ARCHIVE_ND, "Cooked world: skip placements smaller than this (radius / distance)" );
	r_tworldLodSize1 = ri.Cvar_Get( "r_tworldLodSize1", "0.12", CVAR_ARCHIVE_ND, "Cooked world: use detail level 1 below this size (radius / distance)" );
	r_tworldLodSize2 = ri.Cvar_Get( "r_tworldLodSize2", "0.035", CVAR_ARCHIVE_ND, "Cooked world: use detail level 2 below this size (radius / distance)" );
	r_tworldLight = ri.Cvar_Get( "r_tworldLight", "1", CVAR_ARCHIVE_ND, "Cooked world: brightness scale of the sun and ambient light" );

	r_tworldInstancing = ri.Cvar_Get( "r_tworldInstancing", "1", CVAR_ARCHIVE_ND, "Cooked world: 1 = one instanced draw per mesh level and material, 0 = one draw per placement through the model path" );

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
		TW_ERR( "wrong magic or version (this build reads version 2)" );

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
			|| m->numVerts == 0 || m->numLods < 1 || m->numLods > TWORLD_MAX_LODS )
			TW_ERR( "mesh range out of bounds" );
		for ( l = 0; l < m->numLods; l++ ) {
			if ( (uint64_t)m->lodFirstSub[l] + m->lodNumSubs[l] > h->numSubmeshes )
				TW_ERR( "mesh detail level out of bounds" );
			for ( j = 0; j < m->lodNumSubs[l]; j++ ) {
				const twSubmesh_t *s = &fsub[m->lodFirstSub[l] + j];
				if ( s->material >= h->numMaterials || (uint64_t)s->firstIndex + s->numIndexes > m->numIndexes )
					TW_ERR( "submesh range out of bounds" );
			}
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
	VectorCopy( h->sunDir, tw->sunDir );
	VectorNormalize( tw->sunDir );
	VectorCopy( h->sunColor, tw->sunColor );
	VectorCopy( h->ambientColor, tw->ambientColor );
	tw->meshes = (tworldMesh_t *)ri.Hunk_Alloc( sizeof( tworldMesh_t ) * h->numMeshes, h_low );
	tw->subs = (tworldSub_t *)ri.Hunk_Alloc( sizeof( tworldSub_t ) * ( h->numSubmeshes + 1 ), h_low );
	tw->instances = (tworldInst_t *)ri.Hunk_Alloc( sizeof( tworldInst_t ) * ( h->numInstances + 1 ), h_low );
	tw->numTints = h->numMaterials;
	tw->tints = (vec3_t *)ri.Hunk_Alloc( sizeof( vec3_t ) * ( h->numMaterials + 1 ), h_low );

	// materials are ordinary shaders (scripts generated by the cooker) plus a constant tint
	shaders = (shader_t **)ri.Hunk_AllocateTempMemory( sizeof( shader_t * ) * ( h->numMaterials + 1 ) );
	for ( i = 0; i < h->numMaterials; i++ ) {
		char sname[MAX_QPATH];
		Q_strncpyz( sname, fmat[i].shader, sizeof( sname ) );
		shaders[i] = R_FindShader( sname, lightmapsNone, stylesDefault, qtrue );
		if ( !shaders[i] )
			shaders[i] = tr.defaultShader;
		VectorCopy( fmat[i].tint, tw->tints[i] );
		if ( ( fmat[i].flags & TWMAT_BLEND ) && !tw->blendSortShader && shaders[i] != tr.defaultShader )
			tw->blendSortShader = shaders[i];
	}
	tw->alphas = (float *)ri.Hunk_Alloc( sizeof( float ) * ( h->numMaterials + 1 ), h_low );
	for ( i = 0; i < h->numMaterials; i++ ) {
		const uint32_t a = ( fmat[i].flags >> 8 ) & 255;
		tw->alphas[i] = a ? a / 255.0f : 1.0f;
	}
	tw->details = (float *)ri.Hunk_Alloc( sizeof( float ) * ( h->numMaterials + 1 ), h_low );
	for ( i = 0; i < h->numMaterials; i++ )
		tw->details[i] = (float)( ( fmat[i].flags >> 16 ) & 0xffff );

	// the far plane and the cull distance must cover the cooked world, whatever the BSP's worldspawn says
	{
		vec3_t size;
		float need;
		VectorSubtract( h->maxs, h->mins, size );
		need = VectorLength( size ) / 1.732f;
		if ( need < 1.0e6f && tr.distanceCull < need )
			tr.distanceCull = need;
	}
	tw->visInst = (int *)ri.Hunk_Alloc( sizeof( int ) * ( h->numInstances + 1 ), h_low );
	tw->visLod = (byte *)ri.Hunk_Alloc( h->numInstances + 1, h_low );
	tw->batchCount = (int *)ri.Hunk_Alloc( sizeof( int ) * ( h->numSubmeshes + 1 ) * 3, h_low );
	tw->batchStart = tw->batchCount + h->numSubmeshes + 1;
	tw->batchCursor = tw->batchStart + h->numSubmeshes + 1;
	tw->subOrder = (int *)ri.Hunk_Alloc( sizeof( int ) * ( h->numSubmeshes + 1 ), h_low );
	tw->blendSurfaceType = SF_TWORLD;

	// one vertex buffer and one index buffer per mesh (all detail levels), in the MD3 VBO layout
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

		tw->meshes[i].numLods = m->numLods;
		for ( l = 0; l < m->numLods; l++ ) {
			tw->meshes[i].lodFirstSub[l] = m->lodFirstSub[l];
			tw->meshes[i].lodNumSubs[l] = m->lodNumSubs[l];

			for ( j = 0; j < m->lodNumSubs[l]; j++ ) {
				const twSubmesh_t *s = &fsub[m->lodFirstSub[l] + j];
				tworldSub_t *out = &tw->subs[m->lodFirstSub[l] + j];

				out->shader = shaders[s->material];
				out->tintIndex = s->material;
				out->pass = ( fmat[s->material].flags & TWMAT_BLEND ) ? 1 : 0;
				tw->meshes[i].lodPassMask[l] |= 1 << out->pass;
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
	}
	ri.Hunk_FreeTempMemory( shaders );

	for ( i = 0; i < h->numSubmeshes; i++ )
		tw->subOrder[i] = i;
	s_sortSubs = tw->subs;
	qsort( tw->subOrder, h->numSubmeshes, sizeof( int ), TW_CompareSubs );

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

	ri.Printf( PRINT_ALL, "R_LoadTWorld: %s: %u meshes, %u submeshes, %u instances, %u materials, %u verts, %u tris (all detail levels), %.1f MB file, %i ms\n",
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

	if ( s_tworld->blendSortShader )
		R_AddDrawSurf( &s_tworld->blendSurfaceType, s_tworld->blendSortShader, 0, 0 );
}

/*
=================
RB_TWorldInstanced

Instanced path: cull and pick detail levels as usual, then group the visible
placements by (mesh level, material) range, write one 64-byte record per
placement into the per-frame buffer and issue one instanced draw per group.
Returns qfalse only when the path is not available.
=================
*/
typedef struct {
	float	row0[4], row1[4], row2[4];
	float	tint[4];
	float	params[4];		// x: detail repeats per unit of UV
} twInstData_t;				// 80 bytes

static qboolean RB_TWorldInstanced( tworld_t *tw, const int pass )
{
	const cplane_t	*frustum = backEnd.viewParms.frustum;
	const qboolean	cull = (qboolean)( !r_nocull->integer );
	const float		cullSize = r_tworldCullSize->value;
	const float		lodSize1 = r_tworldLodSize1->value;
	const float		lodSize2 = r_tworldLodSize2->value;
	const float		light = r_tworldLight->value;
	const float		*viewOrg = backEnd.viewParms.ori.origin;
	const int		mirror = ( backEnd.viewParms.portalView == PV_MIRROR ) ? 1 : 0;
	int				i, j, p, numVis = 0, total = 0, run = 0, draws = 0, indexes = 0;
	uint32_t		bufOffset, uboOffset;
	twInstData_t	*data;
	vkUniformEntity_t u = {};

	if ( vk.geometry_buffer_size_new )
		return qtrue;		// the per-frame buffer is being replaced; nothing can be drawn from it this frame

	if ( pass == 0 ) {
		tw->c_instances = tw->c_draws = tw->c_indexes = tw->c_small = tw->c_uboFail = 0;
		tw->c_lod[0] = tw->c_lod[1] = tw->c_lod[2] = 0;
	}

	Com_Memset( tw->batchCount, 0, sizeof( int ) * tw->numSubs );

	for ( i = 0; i < tw->numInstances; i++ ) {
		const tworldInst_t *inst = &tw->instances[i];
		const tworldMesh_t *mesh = &tw->meshes[inst->mesh];
		vec3_t	d;
		float	dist;
		int		lod = 0;

		if ( cull ) {
			for ( p = 0; p < 4; p++ ) {
				if ( DotProduct( inst->center, frustum[p].normal ) - frustum[p].dist < -inst->radius )
					break;
			}
			if ( p < 4 )
				continue;
		}

		VectorSubtract( inst->center, viewOrg, d );
		dist = VectorLength( d ) - inst->radius;
		if ( dist > 1.0f ) {
			const float size = inst->radius / dist;
			if ( size < cullSize ) {
				if ( pass == 0 )
					tw->c_small++;
				continue;
			}
			if ( mesh->numLods > 2 && size < lodSize2 )
				lod = 2;
			else if ( mesh->numLods > 1 && size < lodSize1 )
				lod = 1;
		}

		if ( !( mesh->lodPassMask[lod] & ( 1 << pass ) ) )
			continue;

		tw->visInst[numVis] = i;
		tw->visLod[numVis] = (byte)lod;
		numVis++;

		for ( j = 0; j < mesh->lodNumSubs[lod]; j++ ) {
			const int s = mesh->lodFirstSub[lod] + j;
			if ( tw->subs[s].pass == pass && tw->subs[s].surf.numIndexes ) {
				tw->batchCount[s]++;
				total++;
			}
		}

		if ( pass == 0 ) {
			tw->c_instances++;
			tw->c_lod[lod]++;
		}
	}

	if ( !total )
		return qtrue;

	data = (twInstData_t *)vk_reserve_uniform( (size_t)total * sizeof( twInstData_t ), &bufOffset );
	VectorScale( tw->ambientColor, light, u.ambientLight );
	VectorScale( tw->sunColor, light, u.directedLight );
	VectorCopy( tw->sunDir, u.localLightOrigin );
	uboOffset = data ? vk_append_uniform( &u, sizeof( u ), vk.uniform_entity_item_size ) : ~0U;

	if ( !data || uboOffset == ~0U ) {
		// per-frame buffer too small: skip the cooked world this frame and ask for a bigger buffer
		tw->c_uboFail++;
		if ( !vk.geometry_buffer_size_new && vk.geometry_buffer_size < ( 256u << 20 ) )
			vk.geometry_buffer_size_new = vk.geometry_buffer_size * 2;
		return qtrue;
	}

	for ( i = 0; i < tw->numSubs; i++ ) {
		tw->batchStart[i] = tw->batchCursor[i] = run;
		run += tw->batchCount[i];
	}

	for ( i = 0; i < numVis; i++ ) {
		const tworldInst_t *inst = &tw->instances[tw->visInst[i]];
		const tworldMesh_t *mesh = &tw->meshes[inst->mesh];
		const int lod = tw->visLod[i];
		const float *m = inst->matrix;

		for ( j = 0; j < mesh->lodNumSubs[lod]; j++ ) {
			const int s = mesh->lodFirstSub[lod] + j;
			const tworldSub_t *sub = &tw->subs[s];
			twInstData_t *out;

			if ( sub->pass != pass || !sub->surf.numIndexes )
				continue;

			out = &data[tw->batchCursor[s]++];
			out->row0[0] = m[0]; out->row0[1] = m[4]; out->row0[2] = m[8];  out->row0[3] = m[12];
			out->row1[0] = m[1]; out->row1[1] = m[5]; out->row1[2] = m[9];  out->row1[3] = m[13];
			out->row2[0] = m[2]; out->row2[1] = m[6]; out->row2[2] = m[10]; out->row2[3] = m[14];
			VectorCopy( tw->tints[sub->tintIndex], out->tint );
			out->tint[3] = tw->alphas[sub->tintIndex];
			out->params[0] = tw->details[sub->tintIndex];
			out->params[1] = out->params[2] = out->params[3] = 0.0f;
		}
	}

	// world matrix in the push constants, dynamic state, our lighting uniform
	Com_Memcpy( vk_world.modelview_transform, backEnd.viewParms.world.modelViewMatrix, 64 );
	vk_update_mvp( NULL );
	vk_tworld_set_dynamic_state();
	vk_tworld_reset_descriptors();
	vk_update_descriptor( VK_DESC_UNIFORM, vk.cmd->uniform_descriptor );
	vk_update_descriptor_offset( VK_DESC_UNIFORM_ENTITY_BINDING, uboOffset );

	for ( i = 0; i < tw->numSubs; i++ ) {
		const int s = tw->subOrder[i];
		const int count = tw->batchCount[s];
		tworldSub_t *sub = &tw->subs[s];
		const shaderStage_t *stage;
		image_t *image;
		VkBuffer bufs[2];
		VkDeviceSize offs[2];

		if ( !count )
			continue;

		stage = sub->shader->stages[0];
		if ( !stage )
			continue;

		if ( !sub->pipeline[mirror] ) {
			Vk_Pipeline_Def def;
			Com_Memset( &def, 0, sizeof( def ) );
			def.shader_type = TYPE_TWORLD;
			def.state_bits = stage->stateBits;
			def.face_culling = sub->shader->cullType;
			def.polygon_offset = sub->shader->polygonOffset;
			def.mirror = (qboolean)mirror;
			sub->pipeline[mirror] = vk_find_pipeline_ext( 0, &def, qfalse ) + 1;
		}

		image = stage->bundle[0].image[0] ? stage->bundle[0].image[0] : tr.whiteImage;

		vk_bind_pipeline( sub->pipeline[mirror] - 1 );
		vk_update_descriptor( VK_DESC_TEXTURE0, image->descriptor_set );
		{
			const shaderStage_t *ds = ( tw->details[sub->tintIndex] > 0.0f ) ? sub->shader->stages[1] : NULL;
			image_t *detail = ( ds && ds->bundle[0].image[0] ) ? ds->bundle[0].image[0] : tr.whiteImage;
			vk_update_descriptor( VK_DESC_TEXTURE0 + 1, detail->descriptor_set );
		}
		vk_bind_descriptor_sets();

		if ( sub->shader->polygonOffset )
			qvkCmdSetDepthBias( vk.cmd->command_buffer, r_offsetUnits->value, 0.0f, r_offsetFactor->value );

		bufs[0] = sub->surf.vbo->buffer;	offs[0] = 0;
		bufs[1] = vk.cmd->vertex_buffer;	offs[1] = (VkDeviceSize)bufOffset + (VkDeviceSize)tw->batchStart[s] * sizeof( twInstData_t );
		qvkCmdBindVertexBuffers( vk.cmd->command_buffer, 0, 2, bufs, offs );
		vk_bind_index_buffer( sub->surf.ibo->buffer, 0, VK_INDEX_TYPE_UINT32 );
		qvkCmdDrawIndexed( vk.cmd->command_buffer, sub->surf.numIndexes, count, sub->surf.indexOffset, 0, 0 );

		draws++;
		indexes += sub->surf.numIndexes * count;
	}

	vk_tworld_reset_descriptors();

	if ( pass == 0 ) {
		tw->c_draws = draws;
		tw->c_indexes = indexes;
	}
	return qtrue;
}

/*
=================
RB_SurfaceTWorld

Back end: cull placements, pick a detail level, set the model-view matrix and
a private lighting uniform per placement, and draw each material range
through the normal stage iterator.
=================
*/
void RB_SurfaceTWorld( void *surface )
{
	tworld_t		*tw = s_tworld;
	const int		pass = ( tw && surface == (void *)&tw->blendSurfaceType ) ? 1 : 0;
	shader_t		*savedShader = tess.shader;
	const int		savedFog = tess.fogNum;
	const uint32_t	savedWorldUbo = vk.cmd->entity_ubo_offset[REFENTITYNUM_WORLD];
	const cplane_t	*frustum = backEnd.viewParms.frustum;
	const qboolean	cull = (qboolean)( !r_nocull->integer );
	const float		cullSize = r_tworldCullSize->value;
	const float		lodSize1 = r_tworldLodSize1->value;
	const float		lodSize2 = r_tworldLodSize2->value;
	const float		light = r_tworldLight->value;
	const float		*viewOrg = backEnd.viewParms.ori.origin;
	float			modelView[16];
	int				i, j, p;

	if ( !tw )
		return;

	// finish whatever batch was open (normally nothing: our dummy shader has no geometry)
	RB_EndSurface();

	if ( r_tworldInstancing->integer && RB_TWorldInstanced( tw, pass ) ) {
		RB_BeginSurface( savedShader, savedFog );
		goto stats;
	}

	if ( pass == 0 ) {
		tw->c_instances = tw->c_draws = tw->c_indexes = tw->c_small = tw->c_uboFail = 0;
		tw->c_lod[0] = tw->c_lod[1] = tw->c_lod[2] = 0;
	}

	for ( i = 0; i < tw->numInstances; i++ ) {
		const tworldInst_t *inst = &tw->instances[i];
		const tworldMesh_t *mesh = &tw->meshes[inst->mesh];
		vec3_t	d;
		float	dist, size;
		int		lod = 0, lastTint = -1;

		if ( cull ) {
			for ( p = 0; p < 4; p++ ) {
				if ( DotProduct( inst->center, frustum[p].normal ) - frustum[p].dist < -inst->radius )
					break;
			}
			if ( p < 4 )
				continue;
		}

		// projected size: radius over distance to the surface of the bounding sphere
		VectorSubtract( inst->center, viewOrg, d );
		dist = VectorLength( d ) - inst->radius;
		if ( dist > 1.0f ) {
			size = inst->radius / dist;
			if ( size < cullSize ) {
				if ( pass == 0 )
					tw->c_small++;
				continue;
			}
			if ( mesh->numLods > 2 && size < lodSize2 )
				lod = 2;
			else if ( mesh->numLods > 1 && size < lodSize1 )
				lod = 1;
		}

		if ( !( mesh->lodPassMask[lod] & ( 1 << pass ) ) )
			continue;		// nothing of this placement belongs to this pass

		myGlMultMatrix( inst->matrix, backEnd.viewParms.world.modelViewMatrix, modelView );
		Com_Memcpy( vk_world.modelview_transform, modelView, 64 );
		vk_update_mvp( NULL );

		if ( pass == 0 ) {
			tw->c_instances++;
			tw->c_lod[lod]++;
		}

		for ( j = 0; j < mesh->lodNumSubs[lod]; j++ ) {
			tworldSub_t *sub = &tw->subs[mesh->lodFirstSub[lod] + j];

			if ( !sub->surf.numIndexes || sub->pass != pass )
				continue;

			// lighting uniform: sun and ambient multiplied by the material tint, normals rotated by the placement
			if ( sub->tintIndex != lastTint ) {
				const float *tint = tw->tints[sub->tintIndex];
				vkUniformEntity_t u = {};
				uint32_t ofs;

				u.ambientLight[0] = tw->ambientColor[0] * tint[0] * light;
				u.ambientLight[1] = tw->ambientColor[1] * tint[1] * light;
				u.ambientLight[2] = tw->ambientColor[2] * tint[2] * light;
				u.directedLight[0] = tw->sunColor[0] * tint[0] * light;
				u.directedLight[1] = tw->sunColor[1] * tint[1] * light;
				u.directedLight[2] = tw->sunColor[2] * tint[2] * light;
				VectorCopy( tw->sunDir, u.localLightOrigin );
				u.localLightOrigin[3] = 0.0f;		// directional
				Com_Memcpy( u.modelMatrix, inst->matrix, sizeof( u.modelMatrix ) );

				ofs = vk_append_uniform( &u, sizeof( u ), vk.uniform_entity_item_size );
				if ( ofs != ~0U ) {
					vk.cmd->entity_ubo_offset[REFENTITYNUM_WORLD] = ofs;
					lastTint = sub->tintIndex;
				} else {
					// per-frame buffer full: keep the previous uniform for this frame and ask for a
					// bigger buffer, which the frame code creates before the next frame
					tw->c_uboFail++;
					if ( !vk.geometry_buffer_size_new && vk.geometry_buffer_size < ( 256u << 20 ) )
						vk.geometry_buffer_size_new = vk.geometry_buffer_size * 2;
				}
			}

			RB_BeginSurface( sub->shader, 0 );
			RB_SurfaceVBOMDVMesh( &sub->surf );
			RB_EndSurface();

			tw->c_draws++;
			tw->c_indexes += sub->surf.numIndexes;
		}
	}

	// back to the world matrix, the world lighting uniform and the batch the caller expects
	vk.cmd->entity_ubo_offset[REFENTITYNUM_WORLD] = savedWorldUbo;
	Com_Memcpy( vk_world.modelview_transform, backEnd.viewParms.world.modelViewMatrix, 64 );
	vk_update_mvp( NULL );
	RB_BeginSurface( savedShader, savedFog );

stats:
	if ( pass == 0 && r_tworldStats && r_tworldStats->integer && backEnd.viewParms.portalView == PV_NONE ) {
		const int now = ri.Milliseconds();
		if ( now - tw->lastStatsTime >= 1000 ) {
			tw->lastStatsTime = now;
			ri.Printf( PRINT_ALL, "TWORLD view: %i of %i instances (lod %i/%i/%i, %i too small), %i draws, %i tris%s\n",
				tw->c_instances, tw->numInstances, tw->c_lod[0], tw->c_lod[1], tw->c_lod[2], tw->c_small,
				tw->c_draws, tw->c_indexes / 3, tw->c_uboFail ? " UNIFORM BUFFER FULL" : "" );
		}
	}
}

#else // !USE_VBO_MDV

void R_LoadTWorld( const char *bspName ) {}
void R_AddTWorldSurface( void ) {}
void RB_SurfaceTWorld( void *surface ) {}

#endif
