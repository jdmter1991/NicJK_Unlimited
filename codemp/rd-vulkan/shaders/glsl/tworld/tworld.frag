#version 450

// Cooked static world, instanced path: one texture times the lit, tinted vertex colour, with an optional
// tiling detail layer (mean grey 0.5, applied as a x2 multiply).
// Water (animation type 1), after the source scene's material: a dark, mirror-like surface. The second texture
// holds a tiling noise (R height, G/B its gradient); two layers of it (0.35 and 1.3 per metre, drifting at
// (0.4, 0.15) and (-0.25, 0.3) m/s) tilt the normal slightly. The surface shows its own dark colour looking down
// and the sky colour towards the horizon (Fresnel), plus a tight sun glint.
// Falling water / foam (animation type 4): white, alpha = (n1.r + n2.r) * n3.b [* m.g] * fade * 0.75 with three
// scrolling samples of the first texture and optionally one of the second, as in the source material.
// Alpha test uses the same specialization constants as the generic fragment shader.
// Sun shadows: a baked depth map seen from the sun (16-bit, one channel). The fragment's depth in sun space
// is compared against a 4x4 block of texels with bilinear weights (a 3x3 box of bilinear lookups).

layout(set = 1, binding = 0) uniform sampler2D texture0;
layout(set = 2, binding = 0) uniform sampler2D texture1;	// detail or ripple pattern; a white image when unused
layout(set = 3, binding = 0) uniform sampler2D texture2;	// sun shadow depth map; a white image when unused

layout(set = 0, binding = 0) uniform TWorld {
	vec4 eye;				// xyz: camera position (world units), w: metres per world unit
	vec4 skyZenith;			// rgb: sky colour straight up, a: water ripple slope scale
	vec4 skyHorizon;		// rgb: sky colour just above the horizon
	vec4 spare;
} u_tw;

layout(set = 0, binding = 2) uniform Entity {
	vec4 ambientLight;
	vec4 directedLight;
	vec4 localLightOrigin;
	vec4 localViewOrigin;
	mat4 modelMatrix;		// [3] x: receiver offset, y: depth bias, z: shadow strength (0 = off)
} u_entity;

layout(location = 0) in vec2 frag_tex_coord;
layout(location = 1) in vec4 frag_color;
layout(location = 2) in vec2 frag_detail_coord;
layout(location = 3) flat in float frag_detail;
layout(location = 4) flat in vec4 frag_texscale;
layout(location = 5) in vec3 frag_world;
layout(location = 6) flat in vec2 frag_anim;		// x animation type, y time
layout(location = 7) in vec3 frag_sun;
layout(location = 8) in vec3 frag_shadow;
layout(location = 9) in float frag_fade;
layout(location = 10) flat in float frag_ref;

// share of the sun that reaches the fragment: 1 = fully lit
float sun_visibility() {
	float strength = min( u_entity.modelMatrix[3].z, 1.0 );
	if ( strength <= 0.0 )
		return 1.0;
	ivec2 size = textureSize( texture2, 0 );
	vec2 uv = frag_shadow.xy - 0.5;
	if ( uv.x < 1.0 || uv.y < 1.0 || uv.x > float( size.x ) - 3.0 || uv.y > float( size.y ) - 3.0 )
		return 1.0;										// outside the baked region
	ivec2 base = ivec2( floor( uv ) );
	vec2 f = fract( uv );
	float ref = frag_shadow.z - u_entity.modelMatrix[3].y;
	vec4 wx = vec4( 1.0 - f.x, 1.0, 1.0, f.x );
	vec4 wy = vec4( 1.0 - f.y, 1.0, 1.0, f.y );
	float lit = 0.0;
	for ( int j = 0; j < 4; j++ ) {
		for ( int i = 0; i < 4; i++ ) {
			float d = texelFetch( texture2, base + ivec2( i - 1, j - 1 ), 0 ).r;
			lit += ( ref <= d ) ? wx[i] * wy[j] : 0.0;
		}
	}
	return 1.0 - strength * ( 1.0 - lit / 9.0 );
}

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

	float vis = sun_visibility();
	vec3 lit = frag_color.rgb + frag_sun * vis;
	vec4 color = vec4( base.rgb * lit, base.a * frag_color.a );

	if ( frag_anim.x > 0.5 && frag_anim.x < 1.5 ) {
		float t = frag_anim.y;
		vec2 pm = frag_world.xy * u_tw.eye.w;			// metres
		vec3 n1 = texture( texture1, ( pm + t * vec2( 0.40, 0.15 ) ) * ( 0.35 / 8.0 ) ).rgb;
		vec3 n2 = texture( texture1, ( pm + t * vec2( -0.25, 0.30 ) ) * ( 1.30 / 8.0 ) ).rgb;
		vec2 grad = ( ( n1.gb - 0.5 ) * 0.35 + ( n2.gb - 0.5 ) * 1.30 ) / 0.08;	// height change per metre
		vec3 N = normalize( vec3( -grad * u_tw.skyZenith.a, 1.0 ) );
		vec3 V = normalize( u_tw.eye.xyz - frag_world );
		float F = 0.02 + 0.98 * pow( 1.0 - max( dot( N, V ), 0.0 ), 5.0 );
		vec3 R = reflect( -V, N );
		vec3 sky = mix( u_tw.skyHorizon.rgb, u_tw.skyZenith.rgb, pow( clamp( R.z, 0.0, 1.0 ), 0.5 ) );
		float glint = pow( max( dot( R, u_entity.localLightOrigin.xyz ), 0.0 ), 1500.0 ) * 3.0 * vis;
		color.rgb = lit * ( 1.0 - F ) + sky * ( F * 0.7 ) + u_entity.directedLight.rgb * glint;	// 0.7: part of what a real surface would mirror is buildings, not sky
		color.a = mix( frag_color.a, 1.0, F );
	} else if ( frag_anim.x > 3.5 ) {
		float t = frag_anim.y;
		vec2 uv = vec2( frag_tex_coord.x, 1.0 - frag_tex_coord.y );		// the source's UV space (V up)
		vec2 c1 = uv * vec2( 1.50, 0.50 ) + t * vec2( -0.012, 0.06 );
		vec2 c2 = uv * vec2( 1.25, 0.25 ) + t * vec2( 0.006, 0.12 );
		vec2 c3 = uv * vec2( 0.80, 0.20 ) + t * vec2( 0.012, 0.12 );
		float a = ( texture( texture0, vec2( c1.x, 1.0 - c1.y ) ).r + texture( texture0, vec2( c2.x, 1.0 - c2.y ) ).r )
				* texture( texture0, vec2( c3.x, 1.0 - c3.y ) ).b;
		if ( frag_ref > 0.5 ) {
			vec2 c4 = uv * vec2( 0.50, 0.05 ) + t * vec2( 0.0024, 0.012 );
			a *= texture( texture1, vec2( c4.x, 1.0 - c4.y ) ).g;
		}
		a = clamp( a * frag_fade * 0.75, 0.0, 1.0 );
		color = vec4( lit + vec3( 0.25, 0.28, 0.30 ) * a, a );
	}

	// debugging aid (r_tworldShadows 2 / 3): the stored map depth / the receiver depth as repeating grey bands
	if ( u_entity.modelMatrix[3].z >= 1.5 ) {
		float v = ( u_entity.modelMatrix[3].z >= 2.5 ) ? frag_shadow.z : texelFetch( texture2, ivec2( floor( frag_shadow.xy ) ), 0 ).r;
		color = vec4( vec3( fract( v * 64.0 ) ), 1.0 );
	}

	out_color = color;
}
