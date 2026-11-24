#version 450

// Cooked static world ("tworld"), instanced path. One draw call per (mesh detail level, material) with
// instanceCount placements. Per-instance data: three rows of the placement matrix, a tint and parameters.
// Lighting is per vertex: one sun and an ambient colour, taken from the entity uniform block that the
// pass fills once per view. Same response curve as the model shader's "rgbGen lightingDiffuse".
//
// Animation (in_params.z): 0 none, 1 water (fragment shader), 2 vegetation swaying in the wind,
// 3 cloth hanging from its top edge. Driven by the time in u_entity.localViewOrigin.w.

layout(push_constant) uniform Transform {
	mat4 mvp;				// world -> clip
};

layout(set = 0, binding = 2) uniform Entity {
	vec4 ambientLight;		// rgb ambient colour, a: time in seconds
	vec4 directedLight;
	vec4 localLightOrigin;	// xyz: unit vector towards the sun
	vec4 localViewOrigin;	// reused: x intensity, y 1/gamma, z overbright scale for textures that were not light-scaled
	mat4 modelMatrix;
} u_entity;

layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;
layout(location = 2) in vec2 in_tex_coord;

layout(location = 3) in vec4 in_row0;		// per instance
layout(location = 4) in vec4 in_row1;
layout(location = 5) in vec4 in_row2;
layout(location = 6) in vec4 in_tint;		// rgb tint, a opacity
layout(location = 7) in vec4 in_params;		// x: detail texture repeats per unit of UV (0 = no detail layer)
											// y: 1 = the base texture is pre-compressed and still needs the light scale
											// z: animation type
											// w: reference height in mesh space (base for vegetation, top for cloth)

layout(location = 0) out vec2 frag_tex_coord;
layout(location = 1) out vec4 frag_color;
layout(location = 2) out vec2 frag_detail_coord;
layout(location = 3) flat out float frag_detail;
layout(location = 4) flat out vec4 frag_texscale;	// x intensity, y 1/gamma, z overbright scale, w 1 = apply
layout(location = 5) out vec2 frag_world_xy;
layout(location = 6) flat out vec2 frag_anim;		// x animation type, y time

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
	vec3 light = u_entity.directedLight.rgb * ( 1.2 * clamp( ndl, 0.001, 1.0 ) )
			   + u_entity.ambientLight.rgb * ( 1.7 * max( ndl, 0.5 ) );

	frag_color = vec4( light * in_tint.rgb, in_tint.a );
	frag_tex_coord = in_tex_coord;
	frag_detail_coord = in_tex_coord * in_params.x;
	frag_detail = in_params.x;
	frag_texscale = vec4( u_entity.localViewOrigin.xyz, in_params.y );
	frag_world_xy = world.xy;
	frag_anim = vec2( in_params.z, time );
	gl_Position = mvp * vec4( world, 1.0 );
}
