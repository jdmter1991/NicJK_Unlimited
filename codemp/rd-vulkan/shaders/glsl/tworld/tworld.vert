#version 450

// Cooked static world ("tworld"), instanced path. One draw call per (mesh detail level, material) with
// instanceCount placements. Per-instance data: three rows of the placement matrix, a tint and parameters.
// Lighting: one sun and an ambient colour, taken from the entity uniform block that the pass fills once
// per view. Same response curve as the model shader's "rgbGen lightingDiffuse". The ambient and the sun
// part go to the fragment shader separately, so that it can remove the sun part where the baked sun
// shadow map says the point is occluded.
//
// Animation (in_params.z): 0 none, 1 water (fragment shader), 2 vegetation swaying in the wind,
// 3 cloth hanging from its top edge, 4 falling water / foam (fragment shader). Time is u_entity.ambientLight.a.
// Foam meshes carry a fade factor in the length of their normals (0.25 = fully faded .. 1).

layout(push_constant) uniform Transform {
	mat4 mvp;				// world -> clip
};

layout(set = 0, binding = 2) uniform Entity {
	vec4 ambientLight;		// rgb ambient colour, a: time in seconds
	vec4 directedLight;
	vec4 localLightOrigin;	// xyz: unit vector towards the sun
	vec4 localViewOrigin;	// reused: x intensity, y 1/gamma, z overbright scale for textures that were not light-scaled
	mat4 modelMatrix;		// reused for the sun shadow map: [0] [1] world -> texel x, y; [2] world -> depth 0..1;
							// [3] x: receiver offset along its normal (units), y: depth bias, z: shadow strength (0 = off)
} u_entity;

layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;
layout(location = 2) in vec2 in_tex_coord;

layout(location = 3) in vec4 in_row0;		// per instance
layout(location = 4) in vec4 in_row1;
layout(location = 5) in vec4 in_row2;
layout(location = 6) in vec4 in_tint;		// rgb tint, a opacity
layout(location = 7) in vec4 in_params;		// x: > 0 detail texture repeats per unit of UV; < 0: the second texture is a
											//    normal map with -x repeats per unit of UV (physically based path); 0: neither
											// y: packed: bit 0 = the base texture is pre-compressed and still needs the light
											//    scale; + 2 * tile repeats in U + 1024 * tile repeats in V (0 = no tiling layer)
											// z: animation type
											// w: reference height in mesh space (base for vegetation, top for cloth);
											//    foam: 1 = second noise texture; otherwise packed material values for the
											//    physically based path: roughness * 255 + 256 * metallic * 255 + 65536 * flags

layout(location = 0) out vec2 frag_tex_coord;
layout(location = 1) out vec4 frag_color;
layout(location = 2) out vec2 frag_detail_coord;
layout(location = 3) flat out float frag_detail;
layout(location = 4) flat out vec4 frag_texscale;	// x intensity, y 1/gamma, z overbright scale, w 1 = apply
layout(location = 5) out vec3 frag_world;
layout(location = 6) flat out vec2 frag_anim;		// x animation type, y time
layout(location = 7) out vec3 frag_sun;				// sun part of the light times the tint
layout(location = 8) out vec3 frag_shadow;			// shadow map texel x, y and depth
layout(location = 9) out float frag_fade;			// foam: the mesh's fade factor
layout(location = 10) flat out float frag_ref;		// in_params.w
layout(location = 11) out vec3 frag_normal;			// world-space normal
layout(location = 12) flat out vec3 frag_tint;
layout(location = 13) flat out vec2 frag_tile;		// repeats of the tiling colour layer per unit of UV, 0 = none

out gl_PerVertex {
	vec4 gl_Position;
};

void main() {
	vec4 p = vec4( in_position, 1.0 );
	vec3 world = vec3( dot( in_row0, p ), dot( in_row1, p ), dot( in_row2, p ) );
	vec3 n = normalize( vec3( dot( in_row0.xyz, in_normal ), dot( in_row1.xyz, in_normal ), dot( in_row2.xyz, in_normal ) ) );

	float time = u_entity.ambientLight.a;
	int anim = int( in_params.z + 0.5 );

	if ( anim == 2 ) {
		// vegetation: the whole plant leans with slow gusts, more the higher above its base; leaves flutter a little
		float h = max( in_position.z - in_params.w, 0.0 );
		float phase = dot( vec2( in_row0.w, in_row1.w ), vec2( 0.0031, 0.0047 ) );	// per placement
		float sway = sin( time * 1.1 + phase ) * 0.6 + sin( time * 2.3 + phase * 1.7 ) * 0.4;
		float flutter = sin( time * 5.0 + dot( in_position, vec3( 0.11, 0.13, 0.17 ) ) );
		world.xy += vec2( 0.8, 0.6 ) * ( sway * h * 0.012 );
		world += n * ( flutter * min( h, 60.0 ) * 0.004 );
	} else if ( anim == 3 ) {
		// cloth: pinned along its top edge, waves travel across it, stronger towards the bottom
		float h = max( in_params.w - in_position.z, 0.0 );
		float wave = sin( time * 1.7 + dot( world.xy, vec2( 0.020, 0.027 ) ) + in_position.z * 0.05 )
				   + 0.5 * sin( time * 3.1 + in_position.z * 0.11 );
		world += n * ( wave * min( h, 120.0 ) * 0.025 );
	}

	float ndl = dot( n, u_entity.localLightOrigin.xyz );
	vec3 sunLight = u_entity.directedLight.rgb * ( 1.2 * clamp( ndl, 0.001, 1.0 ) );
	vec3 ambLight = u_entity.ambientLight.rgb * ( 1.7 * max( ndl, 0.5 ) );

	frag_color = vec4( ambLight * in_tint.rgb, in_tint.a );
	frag_sun = sunLight * in_tint.rgb;

	// look the receiver up a little in front of its surface: removes self-shadowing without a large depth bias
	vec4 sp = vec4( world + n * u_entity.modelMatrix[3].x, 1.0 );
	frag_shadow = vec3( dot( u_entity.modelMatrix[0], sp ), dot( u_entity.modelMatrix[1], sp ), dot( u_entity.modelMatrix[2], sp ) );
	frag_tex_coord = in_tex_coord;
	frag_detail_coord = in_tex_coord * in_params.x;
	frag_detail = in_params.x;
	float py = in_params.y;
	float tv = floor( py / 1024.0 );
	float tu = floor( ( py - tv * 1024.0 ) * 0.5 );
	frag_tile = vec2( tu, tv );
	frag_texscale = vec4( u_entity.localViewOrigin.xyz, py - tv * 1024.0 - tu * 2.0 );
	frag_world = world;
	frag_fade = clamp( ( length( in_normal ) - 0.25 ) / 0.75, 0.0, 1.0 );
	frag_ref = in_params.w;
	frag_normal = n;
	frag_tint = in_tint.rgb;
	frag_anim = vec2( in_params.z, time );
	gl_Position = mvp * vec4( world, 1.0 );
}
