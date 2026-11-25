# Update 2026-11-25 (night): DDS textures, far-terrain fixes, animation

Engine: branch `naboo-theed`, seven local commits, newest `448d1a2b3`; nothing pushed.
Screenshots: `..\export\city\shots_v5\` (terrain check), `shots_v6\` (animation frames and overviews).

## 1. DDS textures (approved download)

* `texconv.exe` from the DirectXTex release page (966,480 bytes, version 2026.5.8.1, valid Microsoft signature) is
  in `naboo\external\texconv\`. It encodes BC7 on the GPU (DirectCompute on the RTX 2070).
* Engine: `R_FindImageFile` first looks for `<name>.dds` and uploads its blocks and mip chain as they are (BC1,
  BC3 or BC7; DX10 header or DXT1/DXT5). No decode, no CPU mip generation, no power-of-two or 2,048 limit. The
  upload code handles any 4x4 block format; `textureCompressionBC` is enabled when the device offers it.
  Commit `6acbc890a`.
* Tool: `py tools\convert_textures_dds.py <game_dir>`: 231 textures in 77 s, 343 MB of DDS including mips.

Two things that went wrong on the way, both fixed:

| Problem | Cause | Fix |
|---|---|---|
| Everything too dark with DDS | texconv converted the sRGB-tagged PNGs to linear values for the UNORM target | `--ignore-srgb` |
| (found while looking) | the engine **refuses** to load images that are not power-of-two ("Refusing to load non-power-2-dims"), which is why the scene's own terrain colour map rendered white earlier | DDS files are not subject to that check |

A light-scale correction for pre-compressed textures was also added to the cooked-world shader (the engine bakes
intensity/gamma into uncompressed textures at upload when the display cannot apply gamma); it is inactive in the
configuration tested here.

Measured, same benchmark (1920x1080, instancing on, anisotropy 16):

| | PNG | DDS |
|---|---:|---:|
| GPU memory above the idle desktop | about 2.5 GB | about 1.6 GB |
| Process private memory | 4.3 GB | 3.4 GB |
| Renderer start to world loaded | 35 s | 26 s |
| FPS p1-p5 | 522 / 401 / 449 / 551 / 419 | 528 / 371 / 439 / 562 / 416 |

## 2. "Floating buildings" and missing terrain: two bugs

| Symptom | Cause | Fix |
|---|---|---|
| Far terrain drawn plain white, so backdrop buildings looked like they floated in haze | the cooker created the far-terrain material after it had written the shader script and copied textures: the material had no shader and no texture | material created earlier; the cooker now fails if any material appears after the script is written |
| Distant terrain, water and mountains cut off at about 2.6 km | the far-plane adjustment had a 1e6-unit safety limit; the cooked bounds reach about +-19 km (+-770,000 units) because of the backdrop | limit raised to 8e6 units |
| Black specks along the edge of the near terrain | far terrain (16 m grid) poking through the near terrain (1-2 m grid) where they overlap, showing the dark part of its bake | far-terrain vertices under the near terrain are lowered by 4 m |

Checked afterwards from 9,000 units up in four directions and from directly above the city: terrain is continuous
to the mountains, the backdrop buildings sit on it, rivers and canals have water. Heights were also compared
numerically: every backdrop building's lowest point is within a few metres of the far terrain height under it.

Still visible: where two water surfaces overlap, the blended pass draws both and the patch looks lighter; the sky
is plain and pale near the horizon when seen from high up (that is what the source panorama contains there).
"Missing water" was not reproduced after these fixes; if it is still missing somewhere, a position
(`viewpos` in the console) would let me look at that exact spot.

## 3. Animation

Material flags carry an animation type; the instanced shader does the work (the fallback path does not animate).

| Type | Applied to | What moves |
|---|---|---|
| Water | all water materials (canals, sea, waterfalls, fountains, bowls) | two layers of a ripple texture (made from the game's water normal map) scroll in world space and modulate brightness, with glints |
| Vegetation | materials of the vegetation, canopy, tree-stem, bush and foliage-card shader families (15 cooked materials) | the plant leans in slow gusts, more with height above the mesh base; leaves flutter slightly along their normal |
| Cloth | materials named curtain, banner, flag or awning (6 cooked materials) | waves across the surface, stronger towards the bottom, pinned at the top edge |

Verification: two frames taken a moment apart from the same camera at the fountain square. Mean absolute pixel
difference per screen region (0-255): 18.6 and 19.8 in the fountain-water and tree-crown regions, 3-9 around the
curtains and foliage, 0.0 in the regions showing only the door and column. So water and vegetation move and static
geometry does not; the curtain motion was not isolated from the foliage around it, and **nobody has watched the
motion**, so amplitude and speed are untuned guesses.

Frame rate with everything on (DDS, animation, far scenery, anisotropy 16), second cycle:
p1 499, p2 370, p3 402, p4 507, p5 362 FPS (`..\export\city\client_bench_v6.qconsole.log`).

## 4. Not done

* Bots still not watched; nobody has walked the map; unit scale undecided.
* Tree trunks sway together with the crown from the base, with no per-tree stiffness; cloth is not real cloth.
* Water has no reflection or transparency variation; overlapping water surfaces are not merged.
* Depth precision with the far plane now at about 2.6 million units and a 24-bit depth buffer has not been
  examined in motion.
* Collision BSP and spawns unchanged.
