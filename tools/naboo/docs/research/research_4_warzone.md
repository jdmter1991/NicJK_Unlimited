## 4. Warzone renderer (`naboo\external\Warzone`, commit `2ecbc42`, 2024-02-13)

Read-only code study of `codemp/rd-warzone/` (1,106 files; about 104k lines of its own `tr_*.cpp`; 232 GLSL
files, about 40k lines). Nothing was built: the renderer cannot be configured on its own
(`rd-warzone/CMakeLists.txt:3-6` aborts unless the top-level script set `InWarzone`) and it links prebuilt
Windows libraries from `lib/` (assimp-vc140, glsl_optimizer, niflib, navlib, bass).
Licence: GPLv2 (`LICENSE`, `LICENSE.txt`), so code could legally be reused in this GPLv2 fork; bundled parts have
their own licences (Intel Masked Occlusion Culling BSD-3, niflib BSD, meshoptimizer MIT; `bass` is proprietary
but belongs to the engine, not the renderer).

Most features are compile-time switches in `tr_local.h:31-224`. Several of the ones that sound most relevant to a
big map are switched off or marked broken in the source, so the table separates what actually runs.

### 4.1 What it does

| Area | What the code does | Evidence | Runs by default? |
|---|---|---|---|
| World buffers | After loading the standard lumps, all world surfaces are sorted (sky, weight, splat, grass, tessellation, water, glow, alpha-test, stage count, shader, ...) and packed into what is in practice **one VBO + one IBO ordered by shader** (cap 1 GB / 256 MB when `ALLOW_HUGE_WORLD_VBO`, default on from mapInfo) | `tr_bsp.cpp:3034-3468`, `:2483-2763`, `tr_mapping.cpp:2117` | yes |
| Vertex format | float3 position, 10:10:10 packed normal, 5 x float2 UV (diffuse + 4 lightmaps), about 56 bytes; **no tangents, no vertex colours** (`__CHEAP_VERTS__`; colours forced to 1); 32-bit indexes | `tr_bsp.cpp:35-50`, `:1476-1477`, `tr_vbo.cpp:33`, `tr_local.h:48`, `:294-295` | yes |
| Draw submission | rend2-style merging of adjacent index ranges into `glMultiDrawElements` (`MAX_MULTIDRAW_PRIMITIVES` 65,536). Indirect draw is compiled out (`__DRAW_INDIRECT__` off) | `tr_surface.cpp:69-73`, `:885-943`, `tr_local.h:52`, `:3077` | merge yes, indirect no |
| `R_MergeLeafSurfaces` | Merges per leaf without comparing shaders, `break`s after the first surface and reads an index array that `R_CreateWorldVBOs` already freed | `tr_bsp.cpp:6175-6537` (`:6294`, `:6458`, `:6454` vs `:3390`) | on (`r_mergeLeafSurfaces 1`); looks broken, not confirmed at runtime |
| Spatial structure | BSP nodes + PVS are kept; no octree. A 16-cell "VBO areas" grid exists but is disabled. Maps without vis fall back to novis | `tr_world.cpp:862-921`, `:1139-1150`, `tr_local.h:115` | - |
| "Occlusion culling" | Not per-object. After the frame it draws up to 18 camera-facing quads at fixed distances (2,048 ... 524,288) inside occlusion queries, at most every 100 ms, reads them back without stalling, and uses the result as a **dynamic far plane** for the whole view. Surfaces beyond 1.75 x that distance are drawn depth-only. `qglGenQueries` is called every probe and never deleted (leak) | `tr_occlusion.cpp:40-42`, `:72-246`, `:328-617`, `tr_main.cpp:1028-1036`, `tr_world.cpp:31-73` | yes |
| Per-node occlusion, Intel MOC | `node->occluded` is tested but never set; `__SOFTWARE_OCCLUSION__` is commented out | `tr_world.cpp:896`, `tr_occlusion.h` | no (dead) |
| Screen-size cull | Surfaces smaller than about 4 pixels (radius / distance) are skipped; each surface's distance is cached and refreshed once per second | `tr_world.cpp:136-178` | yes |
| Mesh LOD | None for world or props; Ghoul2 LODs off. `misc_lodmodel` is parsed but baking/instancing of those models is commented out and marked "Broken" | `tr_bsp.cpp:4324-4362`, `tr_local.h:57-58`, `:73` | no |
| Terrain | Hardware tessellation with distance fall-off | `glsl2/tessellation*`, `tr_world.cpp:211-231` | yes |
| Instancing | `tr_instancing.cpp` is entirely inside `#ifdef __INSTANCED_MODELS__` (off). Grass is generated each frame by tessellation + geometry shader (85 vertices per input triangle). Trees/plants are submitted one refEntity at a time from cgame `.foliage` files; trees switch to billboards with distance on a 512-unit area grid | `tr_local.h:80`, `glsl2/grass2_gs.glsl:3-8`, `cgame/cg_foliage.cpp:794`, `:1852`, `:2017` | instancing no |
| Model formats | IQM, MDR, MD3, GLM, NIF, plus Assimp (obj, fbx, gltf, dae, ...) | `tr_model.cpp:2404-2472` | yes |
| Materials | Material type from a shader keyword or texture-name heuristics; normal maps auto-generated on the GPU from the diffuse texture; map-wide splat control image with triplanar mapping; optional external AI upscaler started with `CreateProcess` | `tr_shader.cpp:3799`, `:4295-4553`, `tr_image.cpp:3646-3720`, `:3932-3970`, `lightallSplat_fp.glsl:785-799` | yes |
| Lighting | Deferred: G-buffer of HDR colour, glow, encoded normal, RGBA32F world position (+ material type), optional detail normal; one full-screen pass looping over at most 64/128 lights; SSAO/HBAO/SSDO/SSR/wetness/moss/snow all read the G-buffer | `tr_fbo.cpp:718-724`, `tr_postprocess.cpp:2852`, `:3349-3391`, `tr_backend.cpp:3345-4110` | yes |
| Sun shadows | 5 cascades at 2,048, refreshed at staggered rates (every frame / 50 ms / 200 ms / 2 s / 10 s, forced when the camera moves) | `tr_scene.cpp:1748-1801`, `tr_image.cpp:5895` | yes |
| Threading | OpenMP at load time only (images, normals, map traces). Per-frame threading is off. One load-time loop writes shared bounds from a `parallel for` (data race) | `tr_bsp.cpp:1444`/`:1464`, `tr_world.cpp:1802` | load only |
| Limits | `MAX_SHADERS` 16,384, `MAX_VBOS`/`IBOS` 4,096, `MAX_DRAWSURFS` 262,144, `MAX_DRAWIMAGES` 32,768, 64-bit sort key. `qfiles.h` is stock: **no extended BSP lumps** | `tr_local.h:337-344`, `:2796-2838`, `qcommon/qfiles.h:287-354` | - |

Sidecar files it reads next to the BSP (all optional, no BSP format change): `maps/<map>.mapInfo` (INI with
about 150 tuning keys: vis range, occlusion tolerances, splat scales, sun/sky), `maps/<map>.cubemaps` (probe
positions only; cubemaps are rendered at load), `*.climate`, `foliage/<map>.foliage` (instance position, normal,
type, angle, scale; read by cgame), and several generated TGA images (height map, road map) produced by CPU traces.

`tools/` holds a BSP/Assimp-to-OBJ converter (`wzModelConverter`), an OBJ texture-atlas baker (`WzBaker`), a
vendored meshoptimizer (its use in the renderer, `__MESH_OPTIMIZATION__`, is off) and ModView. Nothing there
builds collision or a navmesh; the renderer's Recast hook is `#if 0` (`tr_mapping.cpp:3776`).

### 4.2 Worth adapting to rd-vulkan

| Idea | Why | Cost |
|---|---|---|
| World geometry sorted by material into one static vertex/index buffer, one contiguous index range per material per cluster | Removes the per-surface CPU work that dominates rd-vulkan's front end on Korriban; this is what the cooked world does by construction | part of the cooked-world design |
| Coalescing adjacent visible ranges into few draws (Vulkan: one `vkCmdDrawIndexed` per run, or multi-draw-indirect) | Draw-call count becomes proportional to materials x visible clusters, not surfaces | small |
| Screen-size culling (skip clusters under N pixels) | Free once clusters have bounding spheres; pairs naturally with LOD selection by projected size | small |
| Staggered shadow-cascade refresh | Only relevant if sun shadows are added later; the schedule itself is renderer-independent | later phase |
| Per-map text sidecar for tuning | Matches the "environment block" idea; lets values be tuned without recooking | small |
| Packed 10:10:10 normals | Halves normal/tangent storage; standard practice | small |
| Tree billboards beyond a distance | The Naboo scene has 83-99 instances each of 9-15k-triangle trees; an impostor LOD is the cheapest far representation | cooker work, later |

### 4.3 Not worth adapting

| Idea | Reason |
|---|---|
| Deferred lighting, G-buffer post chain (SSAO, SSR, wetness, moss, snow) | Needs a G-buffer with a 32-bit float position target; rd-vulkan is a forward renderer. A separate project, not a map port |
| Far-plane occlusion probe | It only shortens the far plane for the whole view, needs a depth pre-pass, leaks queries as written. In a city, per-cluster culling against a coarse occluder set would do more; start with frustum + distance + screen-size and measure first |
| Geometry-shader grass | 85 vertices per triangle per frame; geometry shaders are slow on most GPUs and the terrain here already has 4.7 M triangles |
| `R_MergeLeafSurfaces`, model instancing, lodmodel baking, VBO areas, indirect draw, GLSL cache | Disabled or visibly broken in the source; nothing to port |
| Dropping vertex colours (`__CHEAP_VERTS__`) | 166 Naboo meshes carry a `Color0` attribute and baked vertex lighting is the cheapest lighting option available in a forward renderer |
| Auto-generated normal maps, AI upscaler | The Naboo materials already ship authored normal maps (1,687 of 1,807 materials have a linked normal input) |
| OpenMP loops | Load-time only and one of them is a data race; the user's rule is no unsafe multithreading |
