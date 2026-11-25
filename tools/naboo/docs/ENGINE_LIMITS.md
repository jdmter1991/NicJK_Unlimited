# ENGINE_LIMITS вЂ” what the engine allows for a map the size of Naboo: Theed

Source read: `TaystJK_AI-Improved-Bots`, branch `TaystJK_AI_Unlimited`, commit `a8e59a123`. Paths are relative to
`codemp/` unless they start with `shared/` or `lib/`. This is a code reading: nothing was built or run for this
document. It complements `..\..\reports\ENGINE_LIMITS.md` (Korriban, older commit); numbers reused from there were
re-read at this commit. Items nobody read are listed under "Not verified" at the end.

Map-side numbers come from `RESEARCH.md` section 1 (measured in the .blend).

## 0. Summary: which limits Naboo actually hits

| # | Limit | Value | Naboo demand | Verdict |
|---|---|---|---|---|
| 1 | Triangles per BSP surface (`ParseTriSurf`) | 999 verts / 5,999 indexes, `ERR_DROP` | 49.1 M triangles would be at least 24,600 surfaces at the cap, in practice far more | BSP surfaces are the wrong container |
| 2 | Draw surfaces per view | 65,536, wraps silently | one per BSP surface or per MD3 surface per entity | exceeded if the map is expressed as surfaces/entities |
| 3 | Render entities per scene | 4,095 (rd-vulkan only; 2,047 elsewhere) | 17,754 mesh objects | exceeded by 4.3x if every object is an entity |
| 4 | cgame static models | 4,000, `ERR_DROP` | 17,754 | exceeded |
| 5 | MD3 per-surface load cap | 999 verts / 1,999 triangles | 442 of 956 meshes have 1,000+ triangles | most meshes need splitting into many surfaces |
| 6 | MD3 coordinate range | +-511.98 units (about +-13 m at 39.37 u/m) | buildings are 20-50 m, terrain 1,536 m | large meshes cannot be MD3 without cutting |
| 7 | Texture size | 2,048 max, power of two, larger is halved | 2 x 4096^2, 3 x 4096x2048, 7 x 3072^2, 1 x 10240x1024 atlas | 13 textures are downsized or resampled by the engine |
| 8 | Texture formats | jpg/png/tga decoded to RGBA8; optional run-time BC3 | 594 textures, 2.95 GB as RGBA8 without mips (3.9 GB with) | no pre-compressed path; VRAM and load time problem |
| 9 | Per-pixel lighting, normal maps, shadows on the world | none | 1,687 materials use normal maps | look cannot be reproduced without new shader work |
| 10 | Far plane | `distanceCull` x 1.732, default 6,000 -> 10,392 units, and bounded by BSP leaf bounds | city is about 17,700 x 31,500 units; terrain 60,500; backdrop 490,000 | must be set explicitly; depends on the BSP's leaves |
| 11 | World coordinate range | +-65,536 (game traces, a few renderer checks) | near terrain 60,500 units wide fits only if centred; far terrain (322,000) and backdrop do not | far scenery must be visual-only |
| 12 | File size through the engine filesystem | under 2 GB per file and per allocation | raw geometry + textures exceed 2 GB if stored uncompressed in one file | cooked data must be split or compressed |
| 13 | Sort key | 32 bits, all used (14 shader, 12 entity, 5 fog, 1 dlight) | 604 distinct materials | fits (16,384 shaders) but nothing can be widened |
| 14 | `MAX_DRAWIMAGES` | 4,096 | 594 source textures | fits |
| 15 | Collision (`cm_load.cpp`) | lumps sized from the file, 2 GiB per allocation | unknown until the collision mesh is built | Korriban proved 1.3 M brushes load |

Rows 1-6 are why "compile it like a normal map" does not work; rows 7-9 are why even a working geometry path
would not look like the source; rows 10-12 constrain any new format.

## 1. BSP surfaces and the world renderer (rd-vulkan)

| Limit | Definition | Used at | Kind | In a file format / protocol? | Safe way to lift |
|---|---|---|---|---|---|
| `SHADER_MAX_VERTEXES` 1000, `SHADER_MAX_INDEXES` 6000 | `qcommon/qfiles.h:34-35` | `ParseTriSurf` `ERR_DROP` at `rd-vulkan/tr_bsp.cpp:810-814`; sizes the `tess` arrays (`tr_local.h:2095-2111`); MD3 load check `tr_model.cpp:1040-1053`; same check in rd-vanilla | compile-time | no (q3map2 `-meta` just respects it) | Not worth lifting: `tess` is a fixed CPU staging array used by every non-VBO path. Bypass it with geometry that never enters `tess` |
| `MAX_FACE_POINTS` 64 | `rd-vulkan/tr_local.h:899` | `ParseFace` truncates silently (`tr_bsp.cpp:607-609`) | compile-time | no | n/a |
| `MAX_DRAWSURFS` 0x10000 | `rd-vulkan/tr_local.h:1396` | `R_AddDrawSurf` (`tr_main.cpp:1369-1373`), radix sort scratch (`:1183-1185`), overflow wraps with `DRAWSURF_MASK` and warns "the first ones are not drawn" (`:1680-1687`) | compile-time, static arrays | no | Could be raised (power of two), costs memory per view; better to submit clusters, not surfaces |
| Sort key | `rd-vulkan/tr_local.h:1412-1423`: dlight 1, fog 5 (`QSORT_FOGNUM_SHIFT` 1), entity 12 (`QSORT_REFENTITYNUM_SHIFT` 6), shader 14 (`QSORT_SHADERNUM_SHIFT` 18); `#error` guard at `:1420` | `R_AddDrawSurf`, `R_DecomposeSort`, back-end batch loop `tr_backend.cpp:241-345` | compile-time | no | Full. Raising shaders or entities needs a 64-bit key and a different radix sort |
| `REFENTITYNUM_BITS` 12 -> `MAX_REFENTITIES` 4,095 | `rd-vulkan/CMakeLists.txt:219`, `rd-common/tr_types.h:33-40` | `RE_AddRefEntityToScene` drops with a warning (`rd-vulkan/tr_scene.cpp:213-223`) | compile-time, rd-vulkan only | shared struct sizes with cgame, not on the wire | Already at the sort-key maximum |
| `MAX_SHADERS` 16,384 | `rd-vulkan/tr_local.h:136-137` | `GeneratePermanentShader` only prints on overflow (`tr_shader.cpp:4883`) | compile-time | tied to sort key bits | n/a (604 needed) |
| `MAX_SHADER_STAGES` 8, `NUM_TEXTURE_BUNDLES` 3 | `tr_local.h:349`, `:573` | shader parser | compile-time | no | n/a |
| `MAX_VK_PIPELINES` 2,304 | `rd-vulkan/vk_local.h:92` | `ERR_DROP` at `vk_pipelines.cpp:1884` | compile-time | no | raise the constant if a new pass adds many state combinations |
| `MAX_VBOS` 4,096 | `rd-vulkan/tr_local.h:30` | `ERR_DROP` at `vk_vbo.cpp:558`, `:649`; one VBO per MD3 model per LOD | compile-time | no | `tr.vbos` is declared `[4069]` at `tr_local.h:1697` while the check uses 4,096: latent out-of-bounds write, fix before relying on it |
| `MAX_MOD_KNOWN` 1,024 | `rd-vulkan/tr_local.h:1378` | model registration, shared with BSP inline models | compile-time | no | simple constant, static array |
| `MAX_LIGHTMAPS` 256 | `rd-vulkan/tr_local.h:1393` | lightmap load | compile-time | lightmap index in BSP surfaces | n/a if the world is vertex- or shader-lit |

How the existing world path works, because it sets the cost model:

* **Load.** `RE_LoadWorldMap_Actual` (`tr_bsp.cpp:2314`) checks only `header->version == BSP_VERSION` (`:2374`), loads
  lumps sized from their length, then `R_BuildWorldVBO` (`:2398`). CPU copies of all vertices and `int` indexes stay
  on the hunk (`srfTriangles_t`, `tr_local.h:1073-1091`), and a second CPU copy of every index is kept for the
  short-run path (`vk_vbo.cpp:1540`).
* **World VBO.** One `VkBuffer`, one `vkAllocateMemory` of exactly that size (`vk_alloc_vbo`, `vk_vbo.cpp:1866-1931`).
  Layout is per shader, structure-of-arrays: indexes, `vec4` positions (16 B), `vec4` normals (16 B), then per stage
  4 B colours and 8 B texcoords (`VBO_AddGeometry` `:252-381`). Colours and texcoords are baked at load, so
  `rgbGen vertex`/`exactVertex` world colour is static in the buffer. 32-bit indexes (`tr_local.h:129`). All offsets
  are `int`: under 2 GiB, with `ERR_DROP` overflow checks (`:346-374`).
* **Front end.** `R_RecursiveWorldNode` (`tr_world.cpp:1223-1352`) tests four side frustum planes per node; there is
  no far-plane or distance cull. Each visible leaf loops its marksurfaces into `R_AddWorldSurface` (`:340`): one
  draw surface per BSP surface, VBO or not.
* **Back end.** VBO surfaces only queue an item id. `VBO_PrepareQueues` (`vk_vbo.cpp:1818-1852`) sorts the ids and
  merges consecutive ones; runs of at least `MIN_IBO_RUN` 320 indexes (`:55`) become one `vkCmdDrawIndexed`, all
  shorter runs are memcpy'd every frame into a 4 MB (8 MB hi) host buffer (`vk_local.h:104-105`) and drawn in one call.
  No indirect or multi-draw.
* **Per-frame CPU cost** therefore scales with the number of BSP surfaces: node walk, per-surface dedup and cull,
  `R_AddDrawSurf`, a radix sort of up to 65,536 keys, per-surface decode and queue push, an int sort per batch, the
  short-run memcpy. On Korriban (29 K surfaces) this was 22 % of the frame in the front end plus 49 % in the back
  end before the earlier fixes (`..\..\reports\CLIENT_RENDERER_TESTS.md`).

## 2. Static models

| Limit | Definition | Used at | Kind | Format/protocol | Safe way to lift |
|---|---|---|---|---|---|
| `MAX_STATIC_MODELS` 4,000 | `cgame/cg_local.h:2292` | `SP_misc_model_static` `ERR_DROP` (`cgame/cg_spawn.c:170-234`); per-frame linear loop `CG_DrawMiscStaticModels` (`cgame/cg_draw.c:11926-11989`) | compile-time, cgame | no (cgame only; the server frees these entities, `game/g_misc.c:439-442`) | Raising it only moves the wall to the 4,095 render-entity limit |
| MD3 surface load cap 999 verts / 1,999 triangles | `rd-vulkan/tr_model.cpp:1040-1053` | load fails with a warning, even on the VBO path | compile-time (derives from `SHADER_MAX_*`) | no | Could be relaxed for the VBO-only path, but CPU fallbacks (shadows, lit surfaces) still use `tess` |
| `MD3_XYZ_SCALE` 1/64, `short` coordinates | `qcommon/qfiles.h:78-87` | MD3 vertex decode | **file format** | yes: +-511.98 units, 1/64 unit steps | cannot be lifted without a new model format |
| `MD3_MAX_LODS` 3 | same | `name_1.md3`, `name_2.md3` (`tr_model.cpp:67-113`), `R_ComputeLOD` (`tr_mesh.cpp:157-230`) | compile-time | file naming convention | n/a |
| `MD3_MAX_SURFACES` 64, `MD3_MAX_VERTS` 4,096, `MD3_MAX_TRIANGLES` 8,192 | same | not enforced by the loader | - | nominal | - |

MD3 has a GPU path in rd-vulkan: `R_BuildMD3` (`vk_vbo.cpp:1180-1327`) builds one VBO/IBO per model per LOD, 56 B per
vertex with an unused tangent slot, drawn by `RB_SurfaceVBOMDVMesh` (`tr_surface.cpp:2257`) when `r_vbo_models 1`
(default). There is no instancing: each entity costs a cull, LOD pick, light-grid sample, fog loop, one draw surface
and at least one draw call per surface, plus an entity uniform block (`tr_backend.cpp:924-946`). Lighting is one
light-grid sample per model; the model VBO has no colour stream, so per-vertex baked light is not possible on this path.
Formats accepted by rd-vulkan are md3, glm, gla only (`tr_model.cpp:140-152`).

## 3. Textures and materials

| Limit | Definition | Used at | Kind | Safe way to lift |
|---|---|---|---|---|
| `MAX_TEXTURE_SIZE` 2,048 | `rd-vulkan/tr_local.h:49` | clamp `vk_init.cpp:463-465`; images halved until they fit (`vk_image.cpp:630-634`) | compile-time | raise to the device limit (query `maxImageDimension2D`), no format impact |
| Power-of-two only | `vk_image.cpp:606-617` | CPU resample; `r_roundImagesDown` default 1 rounds **down** | runtime cvar | make it optional per image; Vulkan has no such restriction |
| Loaders | `rd-common/tr_image_load.cpp:93-95` | jpg, png, tga | compile-time | add a container loader (DDS or KTX2) plus an upload path for block-compressed data |
| Compression | `vk_image.cpp:641-646`, `:723-731` | run-time BC3 via stb_dxt when `r_ext_compress_textures 1` (default 0); otherwise RGBA8 | runtime cvar | pre-compressed BC7/BC1/BC5 upload is new code |
| Mipmaps | `R_MipMap`, CPU, per image at load | - | - | read stored mip chains instead |
| Image memory | `IMAGE_CHUNK_SIZE` 32 MB x `MAX_IMAGE_CHUNKS` 256 (`vk_local.h:122-123`) | about 8 GB total; one image up to 2 chunks; `ERR_DROP` beyond (`vk_image.cpp:1151`, `:1178`) | compile-time | adequate |
| `MAX_DRAWIMAGES` 4,096 | `tr_local.h:1392`; also sizes the descriptor pool (`vk_pipelines.cpp:102`) | compile-time | adequate (594 needed) |
| Anisotropy | `r_ext_max_anisotropy` default 2, range 1-16 (`tr_init.cpp:930-931`) | runtime cvar | set in a map config |

Capabilities:

* A world surface without a lightmap is lit only by its baked vertex colours (`LIGHTMAP_BY_VERTEX` -> `rgbGen
  exactVertex`, `tr_shader.cpp:4933-4975`). The light grid lights entities only.
* `alphaFunc` (cut-out) exists as `USE_ATEST` + a `discard_mode` specialisation constant
  (`shaders/glsl/gen_frag.tmpl:94-109`); `cull none` is `face_culling` in `Vk_Pipeline_Def`; fog has its own shader
  variants.
* There is **no normal mapping, no PBR, no shadow maps** in rd-vulkan. The only per-pixel lighting is the dynamic
  light pass (`light_vert.tmpl`/`light_frag.tmpl`, `r_dlightMode 2`).
* SPIR-V is precompiled and checked in (`shaders/spirv/shader_data.c`, 15.2 MB of C arrays), regenerated by hand with
  `shaders/compile.bat`, which calls `%VULKAN_SDK%\Bin\glslangValidator.exe` and has a Visual Studio 2019 path
  hard-coded. It is not a CMake step. **Any new shader needs the Vulkan SDK (glslangValidator) on this machine;
  whether it is installed was not checked.**
* Adding a vertex format has precedent: `vbo_mdv`, `vbo_ghoul2` and surface sprites each added a
  `Vk_Pipeline_Def` flag (`vk_local.h:445-469`), a binding block in `vk_push_vertex_input_binding_attribute`
  (`vk_pipelines.cpp:258`), shader variants and a bind function (`vk_shade_geometry.cpp:219`).

## 4. Coordinates, depth and distance

| Limit | Definition | Used at | Kind | Format/protocol | Notes |
|---|---|---|---|---|---|
| `MAX_WORLD_COORD` +-65,536, `WORLD_SIZE` 131,072 | `qcommon/q_shared.h:54-56` | some game/cgame trace lengths, renderer submodel bounds; nothing in `cm_*` clamps | compile-time | no | Collision itself is plain floats |
| `MAX_MAP_BOUNDS` 65,535 | `qcommon/cm_polylib.h:44` | patch winding code only | compile-time | no | irrelevant without patches |
| Float precision | 32-bit floats everywhere; `SURFACE_CLIP_EPSILON` 0.125 (`cm_local.h:178`) | traces | - | - | float spacing is about 0.004 units at 32,768 and 0.008 at 65,536 (arithmetic, not measured in game): fine for collision, visible as vertex jitter only well beyond that |
| Network origin encoding | `FLOAT_INT_BITS` 13, `FLOAT_INT_BIAS` 4,096 (`qcommon/msg.cpp:1039-1040`) | integral values in -4,096..4,095 are sent in 13 bits, others as full 32-bit floats (`:1128-1147`) | compile-time | **network protocol** | lossless at any coordinate; a large map only costs more bandwidth |
| Far plane | `zFar = clamp(2048, tr.distanceCull * 1.732, farthest corner of visited leaf bounds)` (`rd-vulkan/tr_main.cpp:519`) | projection, sky box size (`zFar/1.75`, `tr_sky.cpp:311`, `:762`) | runtime | worldspawn key `distanceCull` (default 6,000, `tr_bsp.cpp:2199`); `r_distanceCull` works only if the key exists (`:2261-2262`) | With a small collision BSP the leaf bounds, not the visual world, decide the far plane unless the new world pass extends them |
| Depth buffer | D24 first, D32F fallback (`vk_instance.cpp:375-396`); standard (not reversed) depth; `r_znear` default 4 (`tr_init.cpp:831-832`) | - | runtime | no | reversed depth exists but is disabled (`USE_REVERSED_DEPTH` commented out at `vk_local.h:75`, with a note about missing decals). With near 4 and far above about 60,000 units, 24-bit depth will z-fight on distant coplanar detail (decals, trim) |
| Server snapshot cull | `g_svCullDist` from worldspawn `distanceCull`, default 6,000 (`game/g_spawn.c:1475-1476`, `server/sv_snapshot.cpp:587-600`) | which entities a client receives | runtime | no | must be set for a map this wide or distant players vanish |
| Entity sector tree | `AREA_DEPTH` 4, `AREA_NODES` 64 (`server/sv_world.cpp:76-77`) | entity linking | compile-time | no | 16 sectors over model 0 bounds; coarse but functional |

## 5. Collision loader and the minimum BSP

`CM_LoadMap` order (`qcommon/cm_load.cpp:738-754`): shaders, leafs, leafbrushes, leafsurfaces, planes, brushsides,
brushes, models, nodes, entities, visibility, patches, then `CM_BuildLeafAccel`.

| Fact | Evidence |
|---|---|
| Must be non-empty (else `ERR_DROP` "Map with no ..."): shaders, leafs, planes, models, nodes | `cm_load.cpp` loaders |
| May be empty: leafbrushes, leafsurfaces, brushsides, brushes, entities, visibility (treated as all-visible), surfaces | same |
| Collision never reads fogs, lightmaps, light grid, light array or draw indexes; surfaces/drawverts only for `MST_PATCH` | `CMod_LoadPatches` `:499-548` |
| Accepted format: version 1 ("RBSP"); the ident bytes are not checked; IBSP 46 is rejected | `qfiles.h:307-309` |
| `maps/<name>.ent` silently replaces the BSP entity lump | `:443-459` |
| A dedicated server reads the whole BSP with one `FS_Read` into `Z_Malloc` and checksums it; it never loads the BSP in a renderer | `:691-698`, `:719` |
| All lump counts come from the file; index fields are not bounds-checked; allocations are `int`-sized (2 GiB each) | `..\..\reports\ENGINE_LIMITS.md` section 3 |
| `MAX_SUBMODELS` 512 (510 usable) | `cm_local.h:30` |
| Leaf accelerator: leaves with at least 24 brushes get a BVH (4 items per node, 32 B nodes, at most 4,096 candidates per query); `cm_accel`, `cm_accelVerify` cvars | `cm_local.h:68-70`, `cm_load.cpp:1186-1311` |

rd-vulkan with a collision-only BSP (code reading, **not run**): zero draw surfaces is handled (the VBO builder prints
"no static surfaces" and returns, `vk_vbo.cpp:1508-1511`); no vis and no lightmaps are handled; an empty light grid
ends with `lightGridData = NULL` (`tr_bsp.cpp:2166-2170`), so entities (players) fall back to default lighting. A
light grid therefore has to be supplied some other way or players will be flat-lit.

## 6. Entities, config strings, network

Unchanged from `..\..\reports\ENGINE_LIMITS.md` section 2.1 and re-read only where marked there: `MAX_GENTITIES`
2,048 (`GENTITYNUM_BITS` 11, protocol), `MAX_CLIENTS` 32, `MAX_MODELS` 512, `MAX_SOUNDS` 256, `MAX_FX` 64,
`MAX_CONFIGSTRINGS` 1,700, `MAX_GAMESTATE_CHARS` 16,000, `MAX_SNAPSHOT_ENTITIES` 512 vs cgame's 256,
`MAX_SPAWN_POINTS` 128. A static scenery map with spawn points and a few effects is far below all of these; they
only matter if doors, movers or many `fx_runner` entities are added later (the scene has 194 effect emitters).

## 7. Files and memory

| Limit | Evidence | Consequence |
|---|---|---|
| Renderer file API has no seek: `FS_ReadFile` (whole file into `Z_Malloc(len+1)`), `FS_FOpenFileRead`, `FS_Read(int)`, `FS_FCloseFile` | `rd-common/tr_public.h:289-301` | a cooked file is read front to back; sections must be ordered for streaming |
| `Z_Malloc(int)`, `Hunk_Alloc(int)`, file lengths `int`/`long` | `qcommon/z_memman_pc.cpp:174`, `:823` | under 2 GB per file and per allocation |
| pk3 opened through the 32-bit `unzOpen` path; entry offsets `unsigned long` (32-bit on Windows) | `lib/minizip/unzip.c:698-700`, `qcommon/files.cpp:2464` | pk3 archives are limited to 4 GB, entries to 2 GB in practice |
| `FS_Read` from a pk3 entry is incremental; `FS_Seek` in a zip re-opens and reads forward | `files.cpp:1932`, `:2015-2078` | store big cooked files uncompressed in the pk3, or loose in the game folder |
| No memory mapping, no async I/O | grep | load is synchronous; chunked reads keep peak memory down |
| Staging buffer 2 MB (24 MB hi) | `rd-vulkan/vk_local.h:107-108` | large uploads are looped through it |
| Machine: 16 GB RAM, RTX 2070 (8 GB VRAM), SATA hard disk for assets | `..\..\reports\CLIENT_RENDERER_TESTS.md`, `systeminfo` | the real budget: roughly 2-3 GB of VRAM for this map's textures and geometry |

## 8. Extension points

* Renderer interface `REF_API_VERSION 9` (`rd-common/tr_public.h:33`), compared for equality in every renderer
  (`rd-vulkan/tr_init.cpp:1299-1302`); `refexport_t` has a trailing `ext` sub-struct (`:244-246`). cgame interface
  `CGAME_API_VERSION 2` with the same pattern (`cgame/cg_public.h:26`, `:476-720`).
* **No interface change is needed for a sidecar file.** cgame calls `trap->R_LoadWorld("maps/<name>.bsp")`
  (`cgame/cg_main.c:1339`) and the renderer keeps `tr.worldDir = "maps/<name>"` (`tr_bsp.cpp:2362-2366`), so
  `RE_LoadWorldMap` can look for `maps/<name>.<ext>` itself. rd-vanilla, rend2 and the dedicated server are untouched.

## 9. rd-vanilla and rend2 in brief

* **rd-vanilla** (`rd-taystjk`, the default `cl_renderer`, `client/cl_main.cpp:2744`): no VBOs, everything through the
  `tess` arrays and `qglDrawElements` (`rd-vanilla/tr_shade.cpp:180-189`); same 999/5,999 trisoup limit; 2,048 images;
  2,047 entities. 4-7x slower than rd-vulkan on Korriban.
* **rend2** (`shared/rd-rend2/`, marked experimental): interleaved packed vertices in several VBO/IBOs split at
  64 MB / 16 MB, tangents, leaf-surface merging and multi-draw, no per-trisoup cap, `MAX_VBOS`/`MAX_IBOS` 16,384; has
  normal/specular mapping, cubemaps and 3 sun-shadow cascades. It took 65-131 ms per frame in its front end on
  Korriban, so its feature set is attractive and its performance is not.
* Only rd-vulkan would draw a cooked world. On the other two renderers the map would show collision-BSP geometry
  only (nothing, if the BSP has no draw surfaces) unless a low-detail fallback is compiled into the BSP.

## 10. Not verified

* Whether a zero-surface, no-vis RBSP actually loads and renders in rd-vulkan (code reading only).
* Where `MAX_DRAWIMAGES` is enforced; behaviour after the `MAX_SHADERS` warning; any clamp of the fog count to the
  5-bit sort-key field; `numAreas == 0` behaviour.
* Vulkan SDK: `VULKAN_SDK` is not set and `C:\VulkanSDK` does not exist, but `glslangValidator.exe` copies exist on disk (for example `E:\RenderDoc\plugins\spirv\glslangValidator.exe`), found by a full disk search; whether one of them compiles this renderer's shaders with `compile.bat` has not been tried.
* Depth precision and float jitter figures are arithmetic, not observations.
* GPU limits of the RTX 2070 (`maxImageDimension2D`, BC7 support) were not queried; both are standard on that card.
