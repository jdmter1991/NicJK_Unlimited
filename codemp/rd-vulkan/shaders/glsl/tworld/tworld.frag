#version 450

// Cooked static world, instanced path: one texture times the lit, tinted vertex colour, with an optional
// tiling detail layer (mean grey 0.5, applied as a x2 multiply). Water (animation type 1) uses the second
// texture as a ripple pattern: two layers scroll over world-space coordinates and modulate the brightness.
// Alpha test uses the same specialization constants as the generic fragment shader.

layout(set = 1, binding = 0) uniform sampler2D texture0;
layout(set = 2, binding = 0) uniform sampler2D texture1;	// detail or ripple pattern; a white image when unused

layout(location = 0) in vec2 frag_tex_coord;
layout(location = 1) in vec4 frag_color;
layout(location = 2) in vec2 frag_detail_coord;
layout(location = 3) flat in float frag_detail;
layout(location = 4) flat in vec4 frag_texscale;
layout(location = 5) in vec2 frag_world_xy;
layout(location = 6) flat in vec2 frag_anim;		// x animation type, y time

layout(location = 0) out vec4 out_color;

layout (constant_id = 0) const int alpha_test_func = 0;
layout (constant_id = 1) const float alpha_test_value = 0.0;

void main() {
	vec4 base = texture( texture0, frag_tex_coord );

	if ( alpha_test_func == 1 ) {
		if ( base.a == alpha_test_value ) discard;
	} else if ( alpha_test_func == 2 ) {
		if ( base.a >= alpha_test_value ) discard;
	} else if ( alpha_test_func == 3 ) {
		if ( base.a < alpha_test_value ) discard;
	}

	// The engine brightens uncompressed textures on upload (intensity, and gamma / overbright when the
	// display cannot do it). Pre-compressed textures skip that step, so the same curve is applied here.
	if ( frag_texscale.w > 0.5 ) {
		base.rgb = pow( min( base.rgb * frag_texscale.x, vec3( 1.0 ) ), vec3( frag_texscale.y ) ) * frag_texscale.z;
	}

	if ( frag_detail > 0.0 ) {
		base.rgb *= texture( texture1, frag_detail_coord ).rgb * 2.0;
	}

	vec4 color = base * frag_color;

	if ( frag_anim.x > 0.5 && frag_anim.x < 1.5 ) {
		float t = frag_anim.y;
		float r1 = texture( texture1, frag_world_xy * 0.0040 + vec2( t * 0.030, t * 0.021 ) ).r;
		float r2 = texture( texture1, frag_world_xy * 0.0093 + vec2( -t * 0.027, t * 0.035 ) ).r;
		float ripple = r1 * r2 * 4.0;					// mean about 1
		color.rgb *= 0.70 + 0.30 * ripple;
		color.rgb += vec3( 0.55, 0.60, 0.62 ) * pow( clamp( ripple - 1.15, 0.0, 1.0 ), 2.0 ) * 1.6;	// glints
	}

	out_color = color;
}
