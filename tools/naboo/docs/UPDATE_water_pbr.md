# Update 2026-11-25 (afternoon): comparison with the .blend, water, fence, PBR, glow, foliage, wrong textures

Engine: branch `naboo-theed`, twelve local commits, newest `95b14ec83`; nothing pushed.
New since the last note: `ab891db85` (water), `c5af4bc66` (physically based path), `95b14ec83` (glow, PBR tuning).

## 0. How the comparison is made

`tools\render_ref.py` renders the source scene with Cycles (GPU, read-only, the .blend is never saved) from game
camera positions; `..\export\city\ref\` holds the reference renders (`ref_*.png`) and side-by-side sheets
(`cmp_*.jpg`, source left). Six views took 17-59 s each. Blender needs about 20 GB of virtual memory for this
scene, so on this 16 GB machine it pages heavily while it runs.

Inventories taken from the .blend (all read-only): `tools\water_inspect.py`, `water_inspect2.py` (water objects,
node formulas), `pbr_survey.py` (how every material feeds colour, normal, roughness, metallic),
`emission_survey.py` (emissive materials, lights), `export_images.py`, `export_water_colors.py`.

## 1. Water

What the source has, and what the port did before:

| Source | Before | Now |
|---|---|---|
| River and ponds (`Theed_Water`): opaque, very dark (0.02, 0.05, 0.05), mirror-like (roughness 0.03), two drifting noise layers as a faint bump | translucent turquoise with a bright, visibly tiling stripe pattern | opaque dark surface, sky colour towards the horizon (Fresnel), the same two noise layers (0.35 and 1.3 per metre, drifting at (0.4, 0.15) and (-0.25, 0.3) m/s), a tight sun glint that the sun shadows mask |
| Fountain bowls: teal, 90 % transmissive, glossy | same turquoise stripes | see-through tinted surface with the same reflection |
| Fountain falls and `Naboo_Waterfalls_01`: white foam, alpha = (n1.r + n2.r) x n3.b [x m.g] x vertex-colour fade x 0.75 with scrolling noise textures | a solid striped teal block | the same formula, the same textures and scroll speeds; the fade travels in the length of the mesh normals |
| Fountain "distortion only" shells: invisible | already dropped | unchanged |

Sky colours for the reflection (zenith, horizon) are measured from the baked sky faces and stored in the world
file header. `r_tworldWaterBump` (default 0.015) sets the ripple slope.

Checked in `ref\cmp2_fountain_top.jpg`, `ref\water_after.jpg`: the river is dark teal from above and picks up the
sky at shallow angles; the fountain is stone with water in the bowl instead of a teal block.

Not matched: the source's water mirrors the buildings around it (ray tracing); the port mirrors a two-colour sky
only, dimmed by 0.7. The koi and lily decals of the garden pond were not examined. River-bed collision and water
volumes for wading are still missing (planned before, not done in this step).

## 2. The "bugged fence" at the first spawn

The terrace behind the fence is 1.2 m higher than the street. The source terrain has 1 m cells; the port drew
the near terrain at 2 m, so the slope between the two levels stuck out from under the fence as jagged mounds.
The closest detail level of the near terrain now uses every vertex (`near_strides` [1, 4, 16] in
`naboo_config.json`). `ref\cmp_spawn_after.jpg`: the mounds are gone, fence base and kerb are clean as in the
source. The sun shadow map was rebaked for the new terrain (1,158 s).

Cost: 9.2 M vertices in the world file (was 7.3 M), 402 MB (was 301 MB).
**Not done:** the collision still uses the 2 m terrain, so near such steps the invisible slope reaches up to a
metre further out than what is drawn.

## 3. Physically based shading (`r_tworldPBR`, default 1; 0 = the classic shading)

* 309 of 426 engine materials have a normal map from the source (212 textures, BC7). It is applied through a
  tangent frame built from screen-space derivatives, so meshes need no tangents.
* Roughness: 1 - alpha of the colour texture where the source does that (182 materials), otherwise the source's
  constant; metallic: a channel of the normal map (119 materials) or the constant.
* Sun (GGX), ambient, and a sky reflection for smooth surfaces. The light is the classic path's light split into
  linear terms, so a rough non-metal is exactly as bright as before.
* Data: `maps\<name>.tpbr` written by the cooker; without it the path still runs with defaults.

`ref\cmp_pbr.jpg` (source, PBR, classic): walls show their stone courses and joints where the classic path is flat.
Cost at 1920 x 1080, five positions, 14,900 frames per pass: PBR 514 and 514 FPS, classic 452 and 552 FPS, i.e. no
difference beyond the spread (`..\export\city\client_bench_pbr.qconsole.log`).

Limits: vegetation and cloth get no normal map (their instance slot is taken by the animation); materials whose
colour uses the second UV set lose a normal map that uses the first; 113 bump-map and 12 world-projected normal
inputs are not used.

## 4. Light decorations

Of the 18 emissive lamp materials, 12 have a strength under 0.05 in this daytime scene (switched off) and are no
longer drawn; 6 glow (hanging lanterns 1.6 and 2.3, a wall light 4.3, the small bulbs 82 and 164). The source
drives a white emission with the alpha of a texture; the port draws that additively and unlit with a warm colour
(`glow_color`, `glow_gain_range`), because the glow is added on top of the lit lamp glass.
`ref\cmp_glow2.jpg`: the lanterns have the source's warm cream glow; the light strings on trees show as dots.

Not done: the lamps do not light their surroundings (the source has 78 light objects, none exported), and the
bulbs on the trees are smaller and dimmer than in the source.

## 5. Foliage density

The source draws leaves with stochastic alpha (coverage = mean alpha); a 0.5 alpha test on mip-mapped alpha drops
most of a thin leaf. `tools\convert_textures_dds.py` now multiplies the alpha of cut-out textures by
`foliage_alpha_gain` (2.2) and uses `texconv -keepcoverage 0.5`, which keeps the share of passing texels constant
down the mip chain. Near trees are fuller (`shots_v12\tree.jpg` against `shots_v9\s2.jpg`).

**Still clearly thinner than the source at distance** (`ref\cmp_final.jpg`, lower pair): the decimated detail
levels of trees destroy the leaf cards. Needs purpose-made tree detail levels; not done. Ground cover (grass) is
generated in the .blend by a geometry-nodes scatter on the terrain and was never exported.

## 6. Wrong textures: doors, and the whole-map check

`pbr_survey.py` records, for every material, which image feeds the colour and with which coordinates. Comparing
that with what the port uses:

| Class | Materials | Status |
|---|---:|---|
| Colour texture mapped with the **second UV set** (palace doors, statue bases, outdoor tables and chairs ...) | 87 (206 meshes, 294,782 triangles) | **fixed**: those triangles take UV1 (`ref\cmp_doors.jpg`) |
| Colour texture **tiled** (Mapping scale other than 1) | 25 (3,455 triangles) | **fixed**: UVs scaled |
| **Layered** materials: concrete, marble, brick, trim-set, roofs ... The source mixes a base, tiling overlays (dirt x5, grunge) and masks; the port shows one image times a tint | about 920 materials on about 11,600 placements | **open**: this is why walls are paler and plainer than the source even with normal maps |
| No image feeds the colour (flat tint) | 254 materials, 7,971 placements | as in the source; some may still need their constant colour checked |
| Colour **projected from world position** (street paving, copper roofs) | 54 materials, 451 placements | **open**: the port uses mesh UVs |

Counts by class: `..\export\city\material_audit.json`.

Also seen in the comparison and not addressed: the source's ground is stone paving with leaf litter while the
port shows the low-resolution terrain colour bake; the source is an overcast scene with haze, the port is brighter
with a blown-out sky; the garden pond view (`ref\cmp_river.jpg`) was not re-shot from the exact camera.

## 7. Players

Test skin: `NikolayAngelovPrequel/default_hot` (white shirt, tan robe), the lightest of the four NikolayAngelov
models (the default skins are black). `shots_v10\sheet_hot.jpg`: bright in the open, darker in the shaded plaza,
bright again there with `r_tworldShadows 0`, so shadowed player lighting works.

Lesson for scripted tests: `r_tworldShadows`, `r_tworldPBR` and the window size are saved between runs. A run
that ends in a debug or off state changes the next one; pass them with `+set` every time.

## 8. State of the files

`devgame_naboo\taystjk\maps\naboo_theed.tworld` (402 MB), `.tshadow`, `_shadow.dds`, `.tpbr` (new);
446 textures as PNG and BC7 DDS (612 MB of DDS). Rebuild order: `cook_v1.py`, `convert_textures_dds.py`,
`bake_sun_shadow.py` (only when geometry changes; it holds the world file open while it runs).
`cook_v1_before_water.py` is the cooker before this step; the `_apply_patch_*.py` files record each change.
