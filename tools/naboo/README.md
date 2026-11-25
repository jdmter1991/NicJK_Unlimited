# Naboo: Theed map tools

Everything needed to rebuild or update the `naboo_theed` map from the source Blender scene. The scene itself, the
exported and cooked data, the baked textures and the packaged map are **not** in this repository: they are large,
and publishing the scene's models and textures is a separate decision. The finished map ships as an optional
download with the releases.

* `pipeline/`: the tools. `docs/`: research, formats, measurements and the notes of each work round
  (start with `docs/TODO.md` and the newest `docs/UPDATE_*.md`).
* Engine side: `codemp/rd-vulkan/tr_tworld.cpp` and `codemp/rd-vulkan/shaders/glsl/tworld/` draw the cooked
  world; the BSP only holds collision, entities and the sky box.

## What you need

| Tool | Version used | Notes |
|---|---|---|
| Blender | 5.2.0 LTS | always run with `-b --factory-startup --disable-autoexec`; the .blend is never saved |
| Python | 3.15 with numpy and Pillow | every script outside Blender |
| texconv (DirectXTex) | 2024 release | BC7 texture conversion, https://github.com/microsoft/DirectXTex |
| glslangValidator | 15.3.0 | shader compilation (`compile_tworld_shaders.py`) |
| Visual Studio 2022 Build Tools | - | engine, and `bake_vertex_ao.cpp` (`cl /O2 /EHsc bake_vertex_ao.cpp`) |

Not needed: q3map2. An early step used it (2.5.17n) for collision; `write_collision_bsp.py` replaced it.

## Paths you have to change

The scripts take the export folder and the game folder as arguments. Machine-specific paths remain in:
`run_bot_bench.sh`, `run_server_test.sh` (project root, game install), `convert_textures_dds.py` (texconv),
`compile_tworld_shaders.py` (glslangValidator), and the examples in the docs. `naboo_config.json` holds the
map's settings (scale 39.37 units per metre, origin, bounds, light, bake sizes), not paths.

## Order of work

`<ed>` = export folder (for example `naboo/export/city`), `<game>` = the mod folder (`.../nicjk`).
Blender steps are run as `blender -b --factory-startup --disable-autoexec <file.blend> --python <script> -- <args>`;
several can share one session through `blender_batch.py`.

1. **Export (Blender).** `export_region.py` (meshes, placements, materials, terrain grids, collision triangles),
   `export_extras.py`, `export_extras2.py`, `export_ripple.py`, `export_water_colors.py` (sky, water, far
   scenery), `export_scatter.py`, `export_scatter_materials.py` (ground scatter), `object_materials.py`,
   `export_object_materials.py` (materials assigned on objects), `export_images.py` (single images).
2. **Surveys (Blender).** `color_graphs.py` (material formulas), `pbr_survey.py`, `bump_survey.py`,
   `emission_survey.py`, `water_inspect.py`, `water_inspect2.py`, `palace_inspect.py`, `material_survey.py`,
   `blend_inspect.py`.
3. **Bakes (Python).** `bake_materials.py` (in parts, then `--merge`), `gen_bump_normals.py`,
   `bake_ground.py` then `bake_ground_packs.py`, `bake_sky.py` (Blender).
4. **Cook.** `build_doors.py` (door models and `doors.json`), then `cook_v1.py <ed> naboo_theed <game>`
   (world file, shaders, textures), then `convert_textures_dds.py <game>`.
5. **Collision.** `build_collision_terrain.py`, `add_palace_spawns.py`, `write_collision_bsp.py`.
6. **Bakes that depend on the cooked file** (repeat after every cook): `bake_sun_shadow.py` (only when the
   geometry of the nearest detail level changed), `bake_vertex_ao` (C++), `bake_sky_occlusion.py`,
   `write_lights.py`. The game refuses a side file whose counts do not match the world file.
7. **Checks.** `render_ref.py` (Blender: reference renders from game camera positions), `visual_vs_collision.py`,
   `water_audit.py`, `water_check.py`, `bsp_*.py`, `run_server_test.sh`, `run_bot_bench.sh`.

`matexpr.py` evaluates the exported material formulas; `_materials_block.py` is shared by the exporters.

## Files the game reads

`maps/naboo_theed.bsp` (collision, entities), `.tworld` (meshes, placements, materials), `.tpbr` (material
values), `.tuv2` (second UV set), `.tao` (occlusion per vertex), `.tsky` (sky occlusion per placement),
`.tlights`, `.tshadow` + `naboo_theed_shadow.dds` (sun shadows), `textures/naboo/*`, `shaders/naboo*.shader`,
`models/map_objects/naboo_theed/door_*.md3`. Formats: `docs/WORLD_FORMAT.md` and the headers of the tools.
