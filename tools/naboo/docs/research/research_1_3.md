# RESEARCH — Naboo: Theed port, Phase 1

Everything here was measured or read on this machine on 2026-11-24. Unknowns are marked. Nothing was modified in
the shared checkout, `build_x64\`, `devgame_dev\` or the game install; the .blend was opened read-only and never saved.

Contents: 1 the Blender scene, 2 engine (summary; detail in `ENGINE_LIMITS.md`), 3 map compilers, 4 Warzone renderer,
5 libraries.

## 1. The Blender scene

File: `E:\jedi academy modding archive\Naboo Theed map\Naboo_Theed.blend`, 1,977,668,090 bytes.
Tool: Blender 5.2.0 LTS found at `E:\blender-5.2.0-windows-x64\` (14 Blender versions are on E:; no download was
needed). The file was saved by 5.2 (file version 5.2.44). Run headless with `--factory-startup --disable-autoexec`.
Scripts: `..\tools\blend_inspect.py`, `..\tools\blend_inspect2.py`; raw output `..\export\blend_inspect*.json`.

### 1.1 Origin and structure

The file contains a text block `README_Naboo_Theed`. According to it the scene is `Levels/MP/Naboo_01` from the game,
built by a tool chain called FrostyCLI `blend-export` plus a `build_scene.py`; 1 unit = 1 m; Blender (x, y, z) =
Frostbite (x, z, y); materials are node translations of the game's pixel shaders; textures are the game's own at
full resolution. The README mentions three scenes (Cloudy, Sunset, Dusk); **this file contains only one,
`Theed_Cloudy`.**

| Item | Value |
|---|---|
| Scenes | 1 (`Theed_Cloudy`), metric, scale 1.0, render engine Cycles, view transform AgX |
| Collections | 31; one per game layer. Excluded from the view layer: `GameModes` (2 objects), `FB_Art_Palace_Ruins` (418, the destroyed palace state), `Backdrop_Landingstrip` (6). Hidden: `TerrainScatter_Sources` (23), `FX_Sources` (7) |
| Objects | 17,832: 17,754 mesh, 78 lights. No cameras, curves, armatures or empties |
| Hierarchy | flat: no parenting, no collection instances, no linked libraries |
| Mesh datablocks | 956 (182 of them are empty effect-emitter placeholders with 0 vertices) |
| Custom properties | objects carry `blueprint` (17,526), `variation` (2,495), `fx_effect`/`fx_emitter` (194); meshes `frostbite_mesh`, `shaders`; materials `shader`, `textures`, `values`, `builder` (1,781) |
| Orphans | none (0 meshes, materials or images with zero users) |
| Modifiers | 184 geometry-node modifiers: 182 effect emitters and 2 terrain scatter groups. Evaluating the dependency graph in background mode produced **0 generated instances** and left triangle counts unchanged, so the scatter (grass etc.) contributes no geometry as the file stands. Whether it would in the interactive viewport was not tested |

### 1.2 Geometry

| Measure | Value |
|---|---:|
| Unique mesh data: vertices / triangles / faces | 6,764,555 / 8,302,078 / 5,690,416 |
| Unique face corners (upper bound for GPU vertices after splitting on normals and UVs) | 19,682,910 |
| Triangles counting every object ("instanced") | 49,149,503 |
| ... of which in the view layer | 48,134,890 |
| Meshes used by more than one object | 610, used by 17,408 objects |
| Triangles that are repeats of shared mesh data | 40,847,425 (83 %) |
| Byte-identical duplicate meshes not sharing data | 7 pairs, 6,869 redundant triangles (negligible) |
| Objects with non-uniform scale / negative scale (mirrored) | 626 / 6 |
| Objects at scale 1.0 | 13,145 of 17,832 |
| Meshes with custom split normals | 766 (every real mesh from the game) |
| UV layers per mesh | 0: 190, 1: 592, 2: 156, 3: 18 |
| Meshes with a vertex colour attribute (`Color0`) | 166 |
| Tangents | not stored (Blender derives them from UVs); must be generated at export |
| LODs | **none**: no object or mesh name contains "lod"; the export holds one detail level per mesh |

Triangles per mesh datablock: 0: 182; 1-99: 104; 100-999: 228; 1,000-9,999: 353; 10,000-99,999: 87;
100,000+: 2 (the two terrains).

Where the triangles are (instanced):

| Collection | Objects | Triangles | Unique meshes | Unique triangles |
|---|---:|---:|---:|---:|
| `Art_Exterior` (the city) | 14,403 | 36,230,405 | 515 | 2,262,727 |
| `Terrain` | 2 | 5,222,784 | 2 | 5,222,784 |
| `FB_Art_Palace` | 1,908 | 4,619,788 | 248 | 817,303 |
| `Cloudy` | 296 | 1,273,689 | 10 | 51,797 |
| `FB_Art_Palace_Ruins` (excluded) | 418 | 971,687 | 8 | 37,085 |
| `Naboo_01` (backdrop etc.) | 382 | 540,945 | 54 | 146,852 |
| `FantasyBattle` | 21 | 147,231 | 9 | 114,044 |
| all others | 324 | 142,974 | - | - |

So the city is 36 M triangles built from only 2.26 M triangles of unique geometry: a 16:1 instancing ratio.
Examples: `o_nab_building_01_a_combined_01` 25,623 triangles x 62; `o_nat_nab_treepoplarlarge_01` 15,495 x 83;
`lightwall_06_a` 4,650 x 258; `o_nab_boxpile_02` 49,388 x 27 (a pile of crates 2.6 m wide with 49 K triangles:
source detail far beyond what this engine needs).

Terrain: `Terrain_Near` is a regular grid, 2,362,369 vertices (1,537 x 1,537), 4,718,592 triangles, 1,536 x 1,536 m at
1 m spacing, 304 m of height range. `Terrain_Far` is 262,144 vertices (512 x 512), 504,192 triangles over
8,177 x 8,177 m at 16 m spacing. Both are plain height grids and simplify extremely well.

### 1.3 Extents and scale

| Region | Extent (m) | At 39.37 units/m (1 unit = 1 inch) |
|---|---|---|
| Dense city: 5th-95th percentile of object centres | x 532..811, y -407..235 (280 x 640) | 11,000 x 25,300 |
| 1st-99th percentile | x 0..913, y -500..289 | 36,000 x 31,000 |
| Ground level in the city (object minimum z, 5th-95th percentile) | 434..452 m | - |
| `Terrain_Near` | 1,536 x 1,536, centred near (948, -158) | 60,500 x 60,500 |
| `Theed_Water` | 8,303 x 6,610 | 327,000 x 260,000 |
| `Terrain_Far` | 8,177 x 8,177 | 322,000 |
| Backdrop meshes (8) | up to 12,421 each, centred about 10 km out | 489,000 |
| Sky mesh `Meshp_Sky_Cottonball_01` | 14,781 wide at z 16,893 | 582,000 |
| Everything | 32,768 x 32,768 x 18,238 | 1,290,000 |

The scale factor is a choice, not a measurement: a JKA player is 64 units tall and a human about 1.8 m, giving
35.6 units/m; the usual mapping convention of 1 unit = 1 inch gives 39.37. **It has to be settled by standing a
player model next to a door in the prototype.** At either value the playable city (at most about 36,000 units across)
fits inside the +-65,536 range once the origin is moved to the city centre (about x 680, y -50, z 436 m); the near
terrain just fits; water, far terrain, backdrop and sky cannot be in collision space and must be drawn as
visual-only distant geometry.

Object sizes (largest bounding-box side): under 0.5 m: 772; 0.5-2 m: 5,222; 2-10 m: 8,471; 10-50 m: 2,979;
50-200 m: 230; 200 m+: 80.

### 1.4 Materials

| Measure | Value |
|---|---:|
| Material datablocks | 1,807 (977 carry a `.001`-style suffix) |
| Distinct by full node-graph signature (nodes, values, links, images, blend mode) | **604** |
| Distinct by set of images + blend mode | 364 |
| Distinct base-colour images | 137 (116 materials have no base-colour image) |
| Blend mode | 1,714 hashed (opaque or cut-out), 93 alpha-blended |
| Backface culling | off on all 1,807 (every material is two-sided in the file) |
| Principled inputs driven by textures | base colour 1,691, normal 1,687, roughness 1,641, metallic 321, alpha 216, emission 4 |
| Node count | 1-5: 68; 6-15: 32; 16-40: 487; over 40: 1,220 |
| Image nodes per material | 0: 64; 1: 69; 2: 387; 3: 192; 4: 123; 5: 146; 6: 800; 8: 25; 36: 1 (near terrain) |
| Material slots per mesh | 1: 371; 2: 207; 3: 66; 4: 51; 5 or more: 79 (max 21) |

Triangles by material class (instanced):

| Class | Materials | Triangles |
|---|---:|---:|
| Opaque | 1,456 | 34,296,214 |
| Cut-out with translucency (vegetation: leaves, flowers, bushes) | 210 | 13,170,304 |
| Cut-out | 40 | 1,404,200 |
| Alpha-blended with emission (effects, light glows) | 30 | 170,664 |
| Opaque with emission | 8 | 81,627 |
| Alpha-blended (decals, water, glass) | 63 | 26,494 |

**27 % of all triangles are alpha-tested vegetation.** Largest shader families by triangles: `SS_VegetationPreset`
9.7 M, `SS_PropsMetallicPreset` 8.4 M, `SS_Naboo_Concrete_01` 7.3 M, terrain 5.2 M, canopy 2.2 M, brick 1.9 M,
palace interior 1.9 M, tree stems 1.9 M.

The node graphs are not simple "image into Principled" graphs: the typical city material mixes two tiling texture
sets by masks and vertex data (1,220 materials have more than 40 nodes; 35,539 Math nodes in total). They cannot be
exported by reading sockets; they have to be **baked or re-expressed per shader family** using the `builder`
property (brick, concrete, marble, trimset, copperroof, props_array, vegetation, canopy, generic, ...). The near
terrain is a splat material: 6 mask images (3,072^2) blending about 15 tiling colour/normal sets.

### 1.5 Textures

| Measure | Value |
|---|---:|
| Images | 594: 593 packed in the .blend, 1 generated; **0 missing**, 0 external |
| Source format | 585 PNG, 7 DDS (effect atlases and the sky panorama), 1 EXR |
| Colour space | 294 sRGB, 298 non-colour (normals, masks) |
| Total pixels | 736,668,049 = 2.95 GB as RGBA8 without mips, about 3.9 GB with mips |
| Sizes | 1024^2: 137; 256^2: 97; 512^2: 91; 2048^2: 81; 128^2: 36; 3072^2: 7; 4096x2048: 3; 4096^2: 2; 10240x1024: 1 (texture-array atlas) |
| Non-power-of-two | 9: the atlas, a 1089x33 colour LUT, 7 terrain images at 3072^2 |
| Name suffixes | `_CS` 177 (colour + smoothness), `_NAM` 95 and `_N` 85 (normal variants), `_C` 46, ... |

Packed byte sizes could not be read: `Image.packed_file.size` crashed Blender 5.2 on this file (C++ exception), so
that call was removed from the script.

At BC7/BC5 with mips the same pixels are about 0.98 GB (1 byte per pixel x 4/3); with a 1,024 cap on prop textures
considerably less. The engine today would load them as RGBA8, clamp at 2,048 and round non-power-of-two sizes down
(`ENGINE_LIMITS.md` section 3).

### 1.6 Lights, environment, effects, special objects

* Lights: 78 = 36 point, 21 spot, 20 area, 1 sun. Sun `Sun_Cloudy`: strength 5.0, colour (1.0, 0.88, 0.82), travelling
  direction (-0.756, -0.256, -0.603). Game light type and attenuation radius are kept in custom properties.
* World: `Sky_Cloudy`, a panorama image `T_Naboo_Cloudy_alt3_01.dds`. A height-fog volume object (`HeightFog_Cloudy`,
  8,200 x 8,200 x 640 m) carries the game's fog formula in a note. A node group holds the game's colour-grading LUT.
* Water: one mesh `Theed_Water`, 3,289 triangles; waterfalls 4,464 triangles; fountain meshes. Animated by drivers.
* Effects: 194 emitter objects (smoke, fire, mist, butterflies, birds, leaves, fountain splashes) with the game
  effect name in `fx_effect`. They are placement data for `fx_runner`-style entities, not geometry.
* Name patterns: 228 objects contain "nocollision" (the game marked them non-colliding: a ready-made hint for the
  collision export), 320 decals, 343 backdrop, 116 "proxy", 77 "leak", 8 "billboard", 3 "InvalidateLightPlane",
  2 "GrenadeBlockerCSG".
* **No gameplay data**: no spawn points, objectives or collision meshes were exported. `GameModes` holds only two
  grenade-blocker boxes. Spawns and collision have to be authored or generated.

### 1.7 What this means

1. The scene is an instancing problem (17.4 K placements of 610 meshes), a terrain problem (5.2 M grid triangles) and
   a material problem (604 complex graphs, 27 % alpha-tested), in that order. Raw unique geometry is modest: 2.3 M
   triangles for the whole city.
2. There are no LODs and the props are over-detailed for this engine; LODs must be generated.
3. Materials need a baking/translation step per shader family; a generic exporter will not capture them.
4. Collision and spawns do not exist in the source and are new work.

## 2. Engine

Detail, file:line references and the full limit tables are in `ENGINE_LIMITS.md`. The findings that drive the design:

| Finding | Consequence |
|---|---|
| A BSP triangle surface is capped at 999 vertices / 5,999 indexes, and the renderer issues one draw surface per BSP surface with 65,536 per view | BSP surfaces cannot carry tens of millions of triangles |
| Render entities are capped at 4,095 (rd-vulkan), static models at 4,000 in cgame, and each entity costs CPU work plus at least one draw call per surface with no instancing | 17,754 placements cannot be entities |
| MD3 coordinates are 16-bit at 1/64 unit (+-512 units, about +-13 m) and surfaces load-fail above 999 vertices | most Naboo meshes do not fit the model format |
| rd-vulkan's world VBO stores per-shader, per-stage streams with baked colours, 32-bit indexes, in one buffer | a precedent for static GPU geometry, but tied to the BSP surface model |
| No normal mapping, PBR, shadow maps or per-pixel lighting except dynamic lights | the look needs either baked vertex lighting or new shaders |
| Textures: jpg/png/tga -> RGBA8, 2,048 max, power of two, CPU mips; optional run-time BC3 | 3.9 GB of RGBA8 would be requested for this map; needs a pre-compressed path |
| Far plane = `distanceCull` x 1.732, bounded by the BSP's visited leaf bounds; D24 standard depth, near 4 | a visual world larger than the BSP must extend the bounds itself; depth precision is a risk beyond about 60,000 units |
| Collision loads from lump sizes with no caps, accepts empty surface/vis lumps, and has the per-leaf BVH from the Korriban work | a collision-only RBSP is a supported input in principle (not run-tested) |
| The renderer can find `maps/<name>.<ext>` next to the BSP with no interface change | a sidecar file needs no cgame/engine API change and leaves the other renderers and the server untouched |
| Files and allocations are limited to under 2 GB; the renderer file API has no seek | cooked data must be chunked and ordered for sequential reads |
| SPIR-V is precompiled by a manual batch file needing `glslangValidator`; no Vulkan SDK is installed (no `VULKAN_SDK`, no `C:\VulkanSDK`), but `glslangValidator.exe` copies exist on disk (for example `E:\RenderDoc\plugins\spirv\glslangValidator.exe`), found by a full disk search; whether one of them compiles this renderer's shaders with `compile.bat` has not been tried | new shaders probably need no download; to be confirmed by recompiling one existing shader and comparing |

## 3. Map compilers

Sources in `..\external\`; build output in `..\external\_build\`. No clone was modified; nothing was downloaded.

### 3.1 What exists on this machine

| Compiler | State | Evidence |
|---|---|---|
| `E:\jedi academy modding archive\Netradiant\q3map2.exe` | **ready to use** | banner `Q3Map (ydnar) - v2.5.17n-git-68ecbed`, NetRadiant 1.6.0n, x64, dated 2026-01-14. Compiled a one-room test map with `-game ja -meta` to a 7,224-byte file starting `RBSP`, version 1. Same version family as the Korriban compiler string (`2.5.17n-git-6b0b4b1f`). This is the netradiant-custom line, not the cloned source |
| WzMap (`external\WzMap`, commit `cab1910`, 2021-08-11) | **built here** | `msbuild WzMap64.sln /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143`: 0 errors, 222 warnings, 62 s. `external\_build\wzmap\bin\WzMap.exe`. The same test map compiled to a 24,352-byte `RBSP` version 1 file |
| NetRadiant q3map2 from the cloned source (Xonotic fork, `c00084b`, 2026-09-01) | **did not configure** | `cmake -G "Visual Studio 17 2022" -DBUILD_RADIANT=OFF`: `Could not find GLIB`, `Could NOT find PkgConfig`, `Could NOT find LibXml2`. Also needs JPEG, PNG, WebP, Minizip. Building it needs a dependency download (vcpkg or MSYS2); not done |
| `GtkRadiant 1.5 Complete\q3map2.exe` | present | v2.5.17 from 2007, 32-bit era; not tested |

None of the output files was loaded in the engine.

### 3.2 q3map2 (NetRadiant, Xonotic fork) architecture

C, GPLv2 (picomodel, ddslib BSD). Stages selected on the command line: BSP (default), `-vis`, `-light`, `-convert`
(ase, obj, gltf, map), `-info`, `-minimap`, and others (`main.c:2221-2293`). 25 game targets including `ja` and `jk2`
(`game_ja.h`: ident RBSP, version 1). Model input through picomodel: 3ds, ase, gltf, iqm, lwo, md2, md3, mdc, ms3d,
obj. No FBX.

Limits (`q3map2.h`):

| Item | Value | Real cap? |
|---|---|---|
| Planes, brushes, brush sides, nodes, leaf-brush refs, models, shaders, draw indexes | none | no: reallocated on demand (`writebsp.c:148-710`, `map.c:116`) |
| `MAX_MAP_LEAFS` | 131,072 | **yes**: static array, `Error` at `writebsp.c:214` |
| `MAX_MAP_DRAW_SURFS` | 131,072 | yes (`surface.c:56`) |
| `MAX_BUILD_SIDES` / `MAX_BRUSH_SIDES` | 1,024 | per brush, .map brushes only |
| `MAX_MODELS` (distinct model files) | 2,048 | yes (`model.c:160`) |
| `MIN/MAX_WORLD_COORD` | +-65,536 | **yes, compile-time**; brushes outside are rejected (`brush.c:224`) |

How triangles become collision (`model.c`, `InsertModel` `:213`): a `misc_model` with spawnflag 2, or a shader with
`q3map_clipModel`, produces **one detail brush per triangle**: the triangle plane, three side planes and a back
plane `clipDepth` (default 2 units) behind it, then `AddBrushBevels` adds axial and edge bevels. That is the 12.6
sides per brush measured on Korriban. Extended spawnflags choose other extrusion shapes (along face normal, vertex
normals, downwards, pyramidal, axial back plane). There is no merging of coplanar triangles into larger brushes.

Two structural facts matter for a collision-only map:

* The BSP tree is built only from **structural** brush faces, and `_blocksize` splits apply only inside their
  bounds (`facebsp.c:100-112`, `:338`). Triangle-model brushes are added after the tree exists (`bsp.c:395`) and
  are merely sorted into existing leaves. With no structural hull there is a single leaf holding every brush. That
  is exactly the Korriban pathology (5,433 leaves, up to 22,182 brushes in one leaf) that the per-leaf BVH in this
  fork was written to rescue.
* There is no switch for "emit no draw surfaces"; it has to be done with nodraw shaders (not tested).

### 3.3 WzMap

A fork of BloodMap, itself q3map2 2.5.16 (GtkRadiant 1.5 era), by the Warzone author; compiled as C++ with OpenMP.
No licence file in the repository; source headers say GPL v2 or later. Last commit 2021-08-11.

| Aspect | WzMap |
|---|---|
| Output | stock RBSP version 1: same 18 lumps, same struct layouts (only lump offset/length are `uint32_t`); marker string "Compiled with WzMap" |
| Limits (`q3map2.h:518-542`) | fixed caps, preallocated at start-up (about 5.2 GB shown in the banner): brushes 2,097,152; brush sides 33.5 M; planes 67.1 M; nodes/leafs/leaf-brushes 8.39 M each; draw surfaces 2.1 M; models 4,096; shaders 2,048; `MAX_MODELS` 512; world +-65,536 |
| Additions | Recast/Detour navmesh stage (`-nav`, `-navmesh`), foliage generation, `-optimize`, `-smooth`, OpenCL lightmapper, Assimp model loading (needs a bundled VS2015 DLL), climate files |
| Collision extras (`model.c:1094`, `:2307-2585`; none tested) | per-model override files looked up automatically (`<model>_collision.obj`, `_collision_convex`, `_collision_box`); surfaces named `collision` inside a model; generated convex hull, mesh decimation and box fallbacks; culling of small solids |
| Still the same | one 5-side-plus-bevels brush per triangle, no merging; tree from structural brushes only |
| Removed | `-onlyents` |
| Baggage | Warzone-specific behaviour (decorations, climate ini, forced shaders, small-solid culling) that would need switching off |

### 3.4 Assessment as collision-BSP compiler

| Option | For | Against |
|---|---|---|
| Existing `q3map2.exe` 2.5.17n | zero build work; proven at 1.3 M brushes on Korriban; standard tool the colleague already uses | cannot be patched (no matching source here); one brush per triangle; tree quality depends on a hand-made structural hull; real limits unknown |
| WzMap | builds here; patchable; `_collision` override and decimation hooks | 2 M brush cap unless edited; 5 GB preallocation on a 16 GB machine; old code base with Warzone behaviour to disable; unmaintained since 2021 |
| NetRadiant source | cleanest, dynamic arrays | not buildable here without downloading dependencies; 131,072 leaf cap |
| **Own RBSP collision writer** | full control over partition quality (a kd-tree over brush bounds instead of structural faces), no caps, no brush splitting, fits a Python/C++ cooker; can merge coplanar triangles and emit convex pieces directly | new code: plane de-duplication, brush bevels (the fiddly part, about 200 lines in `map.c:630`), node/leaf emit; correctness must be proven against the engine |

For a collision-only BSP nearly all of q3map2's BSP stage (face BSP, portals, flood fill, surface/meta/fog/T-junction
processing) is irrelevant. What remains is small. Recommendation, argued in `ARCHITECTURE.md`: use the **existing
q3map2.exe for the first playable prototype** (lowest risk, known-good output), and write the own collision writer
as the production path once the prototype shows where q3map2's output is weak. WzMap is the fallback and a source
of ideas (collision override naming, Recast integration), not the base.
