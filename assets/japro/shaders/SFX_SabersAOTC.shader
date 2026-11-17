sfx_sabers/saber_blade_aotc
{
    notc
    nopicmip
    cull twosided
    sort additive        // <-- Add this line

    {
        map sfx_sabers/saber_blade_aotc
        blendFunc GL_SRC_ALPHA GL_ONE_MINUS_SRC_ALPHA
        rgbGen vertex
        alphaGen vertex
    }
}

gfx/effects/sabers/red_glow_aotc
{
	nopicmip
	notc
	cull	twosided
	{
		map gfx/effects/sabers/red_glow2ep2_theatrical
		blendFunc GL_ONE GL_ONE
		glow
		rgbGen vertex
	}
}

gfx/effects/sabers/orange_glow_aotc
{
	nopicmip
	notc
	cull	twosided
	{
		map gfx/effects/sabers/orange_glow2ep2_theatrical
		blendFunc GL_ONE GL_ONE
		glow
		rgbGen vertex
	}
}

gfx/effects/sabers/yellow_glow_aotc
{
	nopicmip
	notc
	cull	twosided
	{
		map gfx/effects/sabers/yellow_glow2ep2_theatrical
		blendFunc GL_ONE GL_ONE
		glow
		rgbGen vertex
	}
}

gfx/effects/sabers/green_glow_aotc
{
	nopicmip
	notc
	cull	twosided
	{
		map gfx/effects/sabers/green_glow2ep2_theatrical
		blendFunc GL_ONE GL_ONE
		glow
		rgbGen vertex
	}
}

gfx/effects/sabers/blue_glow_aotc
{
	nopicmip
	notc
	cull	twosided
	{
		map gfx/effects/sabers/blue_glow2ep2_theatrical
		blendFunc GL_ONE GL_ONE
		glow
		rgbGen vertex
	}
}

gfx/effects/sabers/purple_glow_aotc
{
	nopicmip
	notc
	cull	twosided
	{
		map gfx/effects/sabers/purple_glow2ep2_theatrical
		blendFunc GL_ONE GL_ONE
		glow
		rgbGen vertex
	}
}

gfx/effects/sabers/RGBglow1ep2_theatrical {
	nopicmip
	notc
	cull twosided
	{
		map gfx/effects/sabers/RGBglow1ep2_theatrical
		blendFunc GL_ONE GL_ONE
		glow
		rgbGen vertex
	}
}