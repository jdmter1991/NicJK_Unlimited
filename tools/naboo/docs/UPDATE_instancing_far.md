# Update 2026-11-25 (later): GPU instancing, ground detail, cleanup, far scenery, Vulkan settings

Engine: branch `naboo-theed`, five local commits, newest `06b06cd05` (instancing) and the detail/far-plane commit
after it; nothing pushed. Screenshots: `..\export\city\shots_v3\`.

## 1. GPU instancing

| Piece | What |
|---|---|
| Shaders | `codemp/rd-vulkan/shaders/glsl/tworld/tworld.vert|.frag`, compiled by `naboo\tools\compile_tworld_shaders.py` with RenderDoc's `glslangValidator` into `shaders/spirv/tworld_data.c` (kept apart from the renderer's generated `shader_data.c`; the renderer's own `compile.bat` does not scan that sub-folder) |
| Pipeline | new `TYPE_TWORLD`; vertex binding 0 = mesh vertices in the existing 56-byte model layout, binding 1 = one 80-byte record per placement (three matrix rows, tint + opacity, parameters). Blend, alpha test, culling and polygon offset still come from the material's ordinary shader, so the generated shader scripts stay the single source of material state |
| Pass | visible placements are grouped by (mesh detail level, material); records are written into the per-frame buffer; one `vkCmdDrawIndexed` with an instance count per group, groups ordered by shader. Sun and ambient come from one uniform block per view; lighting is per vertex |
| Switch | `r_tworldInstancing` (default 1); 0 keeps the previous one-draw-per-placement path. Note: it is an archived cvar, so a test run with 0 leaves 0 in the config |

Same views, same map, 1920x1080, uncapped, spectator, no bots, 750 frames per position, second cycle
(`..\export\city\client_bench_inst1|inst0.qconsole.log`):

| Position | Instancing off | Instancing on | Draw calls (example view) |
|---|---:|---:|---|
| p1 | 227 | 577 | |
| p2 | 126 | 427 | 9,866 -> 1,542 for the same street view |
| p3 | 146 | 471 | |
| p4 | 237 | 600 | |
| p5 (whole city) | 115 | 441 | |

Frame times are 1.7-2.4 ms with instancing, logged in whole milliseconds, so the "on" column is good to about
+-25 %; the ratio (roughly 2.5-3.8x) is not in doubt.

## 2. Ground detail and cleanup

* **Detail layer:** a neutral grain texture (512 pixels, mean 0.5, made from the game's fine-gravel texture by
  `export_extras2.py detail`) is multiplied x2 over the baked ground colour, repeating every 2 m on the near
  terrain and every 6 m on the far terrain. In the instanced shader it is a second texture; in the fallback path
  it is an ordinary second shader stage.
* **White cones removed:** they were the game's distant smoke-column effect meshes (`fxcol_*`, materials `FX_*`);
  materials whose name starts with `FX_` are now skipped.
* Not fixed: the baked ground is still 0.375 m per texel under the grain; water is a flat colour; the blended pass
  is not depth-sorted; LOD spikes on thin objects.

## 3. Draw distance: the whole map is drawn

| Added | How | Size |
|---|---|---|
| Far terrain | `export_extras2.py far`: 512 x 512 height grid over 8.2 km, base colour baked to 2,048 pixels; cooked as 64 tiles with 16 / 64 / 256 m spacing as detail levels, with a hole where the near terrain is | 64 tiles |
| Backdrop | every visible mesh of 200 m or more that the region export skipped (cliffs, backdrop towers and buildings, spaceport, canal foundations), with their own materials and textures; no detail levels | 61 placements, about 0.9 M triangles |
| Far plane | the renderer raises `tr.distanceCull` at load to cover the cooked bounds, so nothing is clipped; depth buffer and near plane unchanged | - |

Cooked file now: 314,910,568 bytes, 975 meshes, 16,926 placements, 387 materials; 44.6 M placed triangles at full
detail, 5.2 M at the lowest levels. Engine load of the world file about 17 s.

Result with everything on (`..\export\city\client_bench_v3.qconsole.log`), second cycle:
p1 522, p2 401, p3 449, p4 551, p5 419 FPS; per view roughly 2,100-5,400 placements, 1,200-1,800 draw calls and
2.7-4.9 M triangles. Memory while running: process private 4.3 GB (working set 1.4 GB), GPU memory about 2.5 GB
above the idle desktop (3.8 GB used of 8 GB against 1.3 GB after exit).

Not checked: depth precision at distance (near plane 4, far plane now several hundred thousand units, 24-bit
depth). No flicker is visible in the six screenshots, which is not the same as looking at it in motion.

## 4. Vulkan settings: what the measurements say

| Candidate | Test | Result | Decision |
|---|---|---|---|
| Frame rate | above | 400-550 FPS at 1080p on the RTX 2070 | no renderer change needed for speed |
| Anisotropic filtering 16x (`r_ext_max_anisotropy 16`, default 2) | same benchmark | 535 / 426 / 456 / 551 / 421 FPS: no measurable cost | recommended for this map (sharper ground at shallow angles); it is a user setting, not changed in code |
| Run-time texture compression (`r_ext_compress_textures 1`, BC3 by the engine) | same run | map load from renderer start to world loaded went from 35 s to 44 s; GPU memory was **not captured** (the sample was taken after the run ended) | not adopted |
| Pre-compressed textures (DDS, BC7/BC1) | not built | would cut the 2.5 GB of GPU memory and most of the texture load time; needs an encoder (DirectXTex `texconv` or similar) that is not on this machine | needs the user's approval for a download |
| Texture size cap 2,048 | - | affects the 13 largest source textures only | left |

## 5. Not done

* Bots still not watched in a client; nobody has walked the map; unit scale undecided.
* No shadows; players lit by the fallback light (no probe grid).
* The uncapped benchmark has no bots or players in view.
* Automated screenshots depend on fragile timing of the join menu (`team s` must arrive once, after the menu opens).
