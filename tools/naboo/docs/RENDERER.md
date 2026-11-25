# RENDERER — cooked world pass in rd-vulkan

> **Later state:** this document describes the first prototype (file version 1, one region). Corrected materials,
> file version 2, detail levels, the whole-city export and its benchmark are in `UPDATE_city_v2.md`;
> whole-city collision, spawns and the bot test are in `UPDATE_city_collision.md`.

State: prototype v0, branch `naboo-theed`, commit `d555f9291` (local only). Built and run on 2026-11-24.

## What was added

| File | Change |
|---|---|
| `codemp/rd-vulkan/tr_tworld.cpp` (new) | `R_LoadTWorld` (load + validate + GPU buffers), `R_AddTWorldSurface` (front end), `RB_SurfaceTWorld` (back end), cvars `r_tworld` (default 1) and `r_tworldStats` |
| `tr_bsp.cpp` | after the BSP has loaded, call `R_LoadTWorld( "maps/<name>.bsp" )`, which looks for `maps/<name>.tworld` |
| `tr_world.cpp` | `R_AddWorldSurfaces` calls `R_AddTWorldSurface()` |
| `tr_local.h`, `tr_surface.cpp` | new surface type `SF_TWORLD` and its table entry |
| `tr_shade.cpp` | `RB_EndSurface` no longer applies the 1,000-vertex / 6,000-index `tess` array limits to model vertex-buffer draws, which never use those arrays |
| `CMakeLists.txt` | new source file |

No renderer/cgame interface change, no new SPIR-V, no change outside `rd-vulkan`. A map without a `.tworld` file
behaves exactly as before (the loader returns when the file is absent).

## How v0 draws

* Load: the whole file is read, checked, and each mesh gets one vertex buffer and one index buffer in the layout
  the existing MD3 buffer path uses (56 bytes per vertex: position, normal, UV, unused tangent). Materials are
  resolved with `R_FindShader`.
* Front end: one draw surface for the entire cooked world, attached to the world entity with the default opaque
  shader; the cooked bounds are added to the view's visible bounds so the far plane covers them.
* Back end (`RB_SurfaceTWorld`): for every placement, a sphere test against the four side frustum planes; for each
  visible one, the model-view matrix is replaced and pushed, and each material range is drawn with
  `RB_BeginSurface` / `RB_SurfaceVBOMDVMesh` / `RB_EndSurface`, i.e. through the normal stage iterator and the
  existing `vbo_mdv` pipelines.

So placements are **not** render entities and not draw surfaces: the 4,095 and 65,536 limits do not apply. The
price in v0 is one draw call per visible placement per material range, no GPU instancing, no LOD, no distance cull.

## Results (prototype region, RTX 2070, rd-vulkan)

Screenshots: `..\export\proto\shots_v0\` (1280x720). Buildings, roofs, steps, columns, trees and planters are in
the right places and at consistent scale; instancing data, UVs and cut-out transparency work.

| Camera | Placements drawn (of 2,575) | Draw calls | Triangles |
|---|---:|---:|---:|
| s0 street level | 757 | 1,203 | 2.29 M |
| s1 street level | 1,847 | 2,625 | 4.27 M |
| s2 street level, looking across the region | 2,161 | 3,267 | 5.63 M |
| s3 above the roofs | 430 | 785 | 1.62 M |
| s4 high, looking along the street | 939 | 1,470 | 2.93 M |

Frame rate at 1920x1080, uncapped, spectator camera, no bots (`..\export\proto\client_bench_v0.qconsole.log`),
second cycle: p1 about 700, p2 about 420, p3 about 350, p4 about 710, p5 about 580 FPS. **These are approximate**:
the per-frame log has whole-millisecond resolution and each segment was only 400 frames; a wall-clock check
(segments of 400 frames lasted about 1-2 s) confirms the order of magnitude, not the digits. The worst view
(5.6 M triangles, 3,267 draws) ran at roughly 2.9 ms per frame.

Also confirmed by this run: **a BSP with no visible surfaces, no vis data, no lightmaps and no light grid loads and
runs in rd-vulkan** ("...no static surfaces for VBO" is printed and the map works). It also loaded in the vanilla
OpenGL renderer during a mis-configured first attempt, where the cooked world is simply not drawn.

## Known defects of v0 (all visible in the screenshots)

| Defect | Cause | Fix belongs to |
|---|---|---|
| Wrong colours on some materials (yellow doors, rainbow tree trunks) | the base-colour lookup takes the first image feeding the colour input; for layered game shaders that can be a mask or packed map | material translation per shader family (roadmap M1/M2) |
| White, washed-out walls | unlit `rgbGen identity` with the engine's overbright settings; several materials tile a pale base under detail layers that v0 ignores | lighting stage, material translation |
| Props using the texture-array atlas look wrong | `props_array` materials index a 10,240 x 1,024 atlas; v0 maps the whole atlas | material translation |
| Flat green ground | terrain crop drawn with a constant colour | terrain step |
| Grey background, no sky | the BSP has no sky surface and the far scenery is not exported | far-scenery step |
| Everything two-sided | every shader uses `cull none` | check winding, then cull opaque materials |
| No fog, no dynamic lights or saber marks on cooked geometry | by design in v0 | later |
| Players are lit by the fallback (no light grid) | collision-only BSP | probe grid |

## Next for the renderer

1. A longer, properly timed benchmark (and with bots) before drawing conclusions from the FPS figures.
2. Distance and screen-size culling, then LODs: the region alone reaches 5.6 M triangles per view.
3. Real instancing (own pipeline, per-instance buffer) once the draw-call count becomes the cost; on this region
   it is not yet.
4. DDS textures: the 54 PNGs load as RGBA8 capped at 2,048 with CPU mip generation.
