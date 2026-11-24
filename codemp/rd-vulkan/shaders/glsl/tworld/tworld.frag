#version 450

// Cooked static world, instanced path: one texture times the lit, tinted vertex colour, with an optional
// tiling detail layer (mean grey 0.5, applied as a x2 multiply). Alpha test uses the same specialization
// constants as the generic fragment shader.

layout(set = 1, binding = 0) uniform sampler2D texture0;
layout(set = 2, binding = 0) uniform sampler2D texture1;	// detail; a white image when unused

layout(location = 0) in vec2 frag_tex_coord;
layout(location = 1) in vec4 frag_color;
layout(location = 2) in vec2 frag_detail_coord;
layout(location = 3) flat in float frag_detail;

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

	if ( frag_detail > 0.0 ) {
		base.rgb *= texture( texture1, frag_detail_coord ).rgb * 2.0;
	}

	out_color = base * frag_color;
}
