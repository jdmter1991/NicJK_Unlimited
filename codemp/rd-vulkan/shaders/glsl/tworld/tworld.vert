#version 450

// Cooked static world ("tworld"), instanced path. One draw call per (mesh detail level, material) with
// instanceCount placements. Per-instance data: three rows of the placement matrix, a tint and parameters.
// Lighting is per vertex: one sun and an ambient colour, taken from the entity uniform block that the
// pass fills once per view. Same response curve as the model shader's "rgbGen lightingDiffuse".

layout(push_constant) uniform Transform {
	mat4 mvp;				// world -> clip
};

layout(set = 0, binding = 2) uniform Entity {
	vec4 ambientLight;
	vec4 directedLight;
	vec4 localLightOrigin;	// xyz: unit vector towards the sun
	vec4 localViewOrigin;
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

layout(location = 0) out vec2 frag_tex_coord;
layout(location = 1) out vec4 frag_color;
layout(location = 2) out vec2 frag_detail_coord;
layout(location = 3) flat out float frag_detail;

out gl_PerVertex {
	vec4 gl_Position;
};

void main() {
	vec4 p = vec4( in_position, 1.0 );
	vec3 world = vec3( dot( in_row0, p ), dot( in_row1, p ), dot( in_row2, p ) );
	vec3 n = normalize( vec3( dot( in_row0.xyz, in_normal ), dot( in_row1.xyz, in_normal ), dot( in_row2.xyz, in_normal ) ) );

	float ndl = dot( n, u_entity.localLightOrigin.xyz );
	vec3 light = u_entity.directedLight.rgb * ( 1.2 * clamp( ndl, 0.001, 1.0 ) )
			   + u_entity.ambientLight.rgb * ( 1.7 * max( ndl, 0.5 ) );

	frag_color = vec4( light * in_tint.rgb, in_tint.a );
	frag_tex_coord = in_tex_coord;
	frag_detail_coord = in_tex_coord * in_params.x;
	frag_detail = in_params.x;
	gl_Position = mvp * vec4( world, 1.0 );
}
