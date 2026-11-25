# ARCHITECTURE — how to bring Naboo: Theed into the fork

Phase 2 design. Inputs: `RESEARCH.md` (measured scene facts, compilers, Warzone, libraries) and `ENGINE_LIMITS.md`
(engine facts with file:line). Nothing in this document has been built yet. Every performance figure below is a
**budget or an expectation to be tested**, not a measurement; the measured figures are the ones quoted from the
research documents.

## 1. The problem in numbers

| Scene (measured) | Engine (read from code) |
|---|---|
| 17,754 mesh objects placing 956 meshes; 610 meshes account for 17,408 placements | 4,095 render entities, 4,000 static models, no instancing |
| 49.1 M triangles as placed; 8.3 M unique (2.3 M for the city, 5.2 M terrain) | 999 vertices per BSP or MD3 surface, 65,536 draw surfaces per view, one draw surface per BSP surface |
| 604 distinct materials, most mixing several texture sets; 1,687 use normal maps; 27 % of triangles alpha-tested | no normal mapping or per-pixel light; RGBA8 textures up to 2,048, power of two |
| 594 textures, 3.9 GB as RGBA8 with mips | no pre-compressed texture path |
| No LODs, no collision meshes, no spawn points | bots navigate by traces; collision loads any size; per-leaf BVH exists |
| City about 36,000 units across, near terrain 60,500, far scenery up to 1.29 M | +-65,536 world, D24 depth, far plane tied to BSP leaf bounds |

Test machine (from the earlier reports): Core i7-7700, RTX 2070 8 GB, 16 GB RAM, assets on a SATA hard disk.

## 2. Options compared

| | (a) Conventional BSP | (b) Extended BSP | (c) Cooked visual world + collision BSP | (d) BSP + static models (Korriban style) |
|---|---|---|---|---|
| What it is | q3map2 compiles everything into surfaces, vis, lightmaps | same, with raised limits or new lumps | renderer draws a purpose-built file; the BSP holds collision, entities, spawns | BSP for ground/collision, `misc_model_static` MD3s for props |
| Geometry capacity | 999-vertex surfaces; q3map2 `-meta` produced 29 K surfaces for Korriban's 0.5 M stored triangles; Naboo is 16-100x that | needs engine changes in three renderers and a non-standard compiler | unlimited by design; 32-bit indexes | 4,000 statics and 4,095 entities against 17,754 placements; MD3 +-13 m and 999 vertices per surface |
| Instancing | none: every placement is baked, so 49 M triangles are stored and lit individually | none | native: 610 meshes stored once | per-entity draw, no GPU instancing |
| LOD | none | would have to be invented | per mesh, chosen by screen size | MD3 has 3 LOD files per model; engine picks by distance |
| Materials | Quake 3 shader stages; no normal maps | same | own material record and shader | same as (a) |
| Lighting | lightmaps (q3map2 `-light` on tens of millions of triangles: impractical) or vertex light | same | free to choose: baked terms + simple per-pixel sun | one light-grid sample per model: flat |
| Compile time | Korriban-class or worse; vis is useless on an open city (Korriban: 81 % of clusters visible) | same | cooker time dominated by texture compression and LOD generation | same as (a) plus model conversion |
| Works in rd-vanilla / rend2 | yes in principle, at unusable speed (Korriban: vanilla 4-7x slower, rend2 worse) | no | no (rd-vulkan only) | yes, slowly |
| Engine work | none, but it will not fit | large and spread over shared code | one new module in rd-vulkan, a texture loader, one hook in the BSP loader | raise limits, add instancing to the entity path, new model format: comparable work to (c) with a worse result |
| Risk | certain failure on size | high, touches file formats others rely on | new code; shader build tooling; look development | hits four separate limits |

(a) and (b) fail on the same arithmetic: the BSP surface is a small CPU-submitted batch, and this scene needs
thousands of times more geometry than that unit was designed for. (d) is how Korriban works and it is at its limits
there with 3,900 placements; Naboo has 4.5x more placements and meshes that do not fit MD3. Fixing (d) properly
(instancing, bigger models, LOD selection, material upgrade) means building most of (c) inside the entity path,
where every placement still costs cgame and front-end work per frame.

## 3. Recommendation: (c) with instancing as a first-class concept

**A cooked world file drawn by a new static-world module in rd-vulkan, plus a collision-only RBSP for physics,
entities and spawns.** The BSP stays a completely standard file, so the dedicated server, botlib, the game module
and the other renderers need no changes.

Reasons, in order of weight:

1. It is the only option whose capacity matches the scene without touching shared formats.
2. The scene is 83 % repeated geometry. A format with a mesh table and a placement table stores 8.3 M triangles
   instead of 49.1 M and lets the GPU draw repeats with instanced calls. None of the BSP-based options can express that.
3. The renderer hook is small and isolated: `RE_LoadWorldMap` already knows `maps/<name>`; if `maps/<name>.tworld`
   exists it loads it and adds one pass. No renderer/cgame interface change (`ENGINE_LIMITS.md` section 8).
4. Per-frame CPU work becomes proportional to visible placements and materials (thousands), not surfaces (tens of
   thousands to millions), which is where rd-vulkan spent 70 % of its frame on Korriban.
5. It leaves the collision problem independent, so each half can be built and tested alone.

Complexity: this is the largest single piece of new renderer code in the fork so far (estimate 2,500-4,000 lines of
C++ in rd-vulkan plus two shader pairs, and a cooker of similar size). It is contained in new files.

### 3.1 Relation to the ".kworld" description

The user was given a description of an unreleased third-party cooked-world format. Its source is not available;
nothing here reproduces it, and its internals are not known. Taken as an idea list, this design agrees with it on:
a section table, clusters with bounds, LOD chains tagged with geometric error and chosen by projected size, baked
materials, BC7 textures with mip chains, an environment text block, and collision/spawns kept in a separate BSP.
It deliberately differs where the measurements say so:

| Point | Reference idea (as described) | This design | Why |
|---|---|---|---|
| Repeated geometry | spatial clusters of merged triangles | mesh table + instance table; merged clusters only for unique geometry (terrain, backdrop, one-off buildings) | 40.8 M of 49.1 M triangles are repeats |
| Textures | stored in the world file | separate standard DDS files referenced by name | keeps every file under the engine's 2 GB limit, lets textures be shared, inspected and re-encoded without recooking geometry, and gives the engine a generally useful DDS loader |
| Distant scenery | not described | separate "far" section drawn in its own depth range | backdrop is 0.5 M units away; D24 depth and the +-65,536 world cannot hold it |
| Player lighting | not described | probe grid section sampled for entities | a collision-only BSP has no light grid, so players would be flat-lit |
| Vertex | position/normal/tangent/UV/material index | no per-vertex material index; one index range per material per mesh LOD | range-per-material allows one pipeline bind per material and smaller vertices |
| Area lights | point/spot/area | point and spot only at first; area lights converted by the cooker | the forward pass has a small light budget; 20 area lights are all palace interior fixtures |

## 4. Cooked world format (`maps/<name>.tworld`), version 1 draft

Little-endian, read front to back in chunks (the renderer file API has no seek). All offsets 64-bit in the header,
but the cooker refuses to write a file of 2 GB or more. To be finalised in `WORLD_FORMAT.md` when the first cooker runs.

| Section | Content |
|---|---|
| Header | magic, version, unit scale used, origin shift, world bounds, playable bounds, counts, section table (id, offset, size, CRC32) |
| Environment | UTF-8 text: sun direction/colour/intensity, ambient sky/ground colours, fog colour/density/height terms, exposure, far distance, sky texture name. Text so it can be overridden by `maps/<name>.tworld.env` without recooking |
| Materials | per material: class (opaque, cut-out, blended, emissive, water), two-sided flag, wind/foliage parameters, alpha cut-off, texture names (base colour, normal, roughness/metal/AO pack), tiling, base colour and roughness/metal factors, emissive colour. Optional second layer + mask for the brick/concrete families (section 6) |
| Meshes | per mesh: bounding sphere and box, LOD count; per LOD: geometric error, vertex range, per-material index ranges |
| Vertices | 32 bytes: position 3 x float; normal 10:10:10:2; tangent 10:10:10 + handedness; UV0 2 x float; colour RGBA8 (vertex colour or baked occlusion). Optional second stream: UV1 2 x half for the 174 meshes that use it |
| Indexes | 32-bit, vertex-cache optimised, relative to the mesh LOD's vertex range |
| Instances | mesh id, 3x4 transform, bounding sphere, flags (no-shadow, mirrored), tint/probe colour RGBA8, optional per-instance baked-light stream offset |
| Clusters | a two-level grid (cells of about 32 m) over instances, with cell bounds; unique geometry (terrain tiles, one-off buildings) is stored as meshes with a single instance, so one path draws everything |
| Far | meshes and instances of visual-only distant scenery (far terrain, backdrop, water plane, sky), in a scaled coordinate space |
| Lights | point/spot: position, direction, cone, colour, radius |
| Probes | regular grid of ambient + directed light for entity lighting, same layout idea as the BSP light grid |

Size expectation (arithmetic from measured counts, before LODs): at most 19.7 M vertices x 32 B = 630 MB if no face
corners merged; unique positions are 6.8 M, so the real figure lies between 216 MB and 630 MB. Indexes 8.3 M x 3 x 4 B
= 100 MB. The near terrain alone is 2.36 M vertices and should be decimated to a fraction of that. LOD chains add
roughly a third. Instances: 17,754 x about 64 B = 1.1 MB. Target for the whole geometry file: under 600 MB.

## 5. Cooker

Two stages, so that the slow, Blender-dependent part runs rarely.

| Stage | Tool | Input -> output |
|---|---|---|
| 1. Export | Python inside Blender 5.2 (background mode) | .blend -> intermediate folder: one binary blob per unique mesh (positions, split normals, UVs, colours, material indexes via `foreach_get`), `scene.json` (placements with matrices, collection, `blueprint`, flags), `materials.json` (family from the `builder` property, texture names, parameters), textures unpacked once as PNG |
| 2. Cook | standalone C++ command-line tool (`naboo\cooker\`) | intermediate -> `.tworld`, `.dds` textures, collision export, spawn candidates, report |

Intermediate format: **to be chosen by test in the first step**, between (i) the direct dump above and (ii) Blender's
glTF exporter. The expectation is that (i) wins: glTF export of 17,754 objects with 1,807 node materials is slow,
flattens the custom material graphs to whatever the exporter recognises, and needs a glTF reader in the cooker. The
test is to export the same prototype region both ways and record time, size and what material data survives.

Cook steps: weld vertices and build tangents (MikkTSpace-compatible), optimise index order and generate LODs with
meshoptimizer (MIT) recording each LOD's error, split the near terrain into tiles with their own LODs, bake or map
materials (section 6), encode textures (BC7 for colour with alpha or high quality, BC1 for plain opaque colour, BC5
for normals) with full mip chains using DirectXTex `texconv` or bc7enc_rdo (both MIT-family; choose by encode time
on this CPU), build the cluster grid, write the file, print a report (triangles per LOD, bytes per section, texture
memory).

Scale and axes: Blender is Z-up, right-handed, like the engine, so the mapping is a uniform scale and an origin
shift (to about x 680, y -50, z 436 m). The scale (35.6 to 39.37 units per metre) is fixed in the prototype by
comparing a player model with doors and stairs.

Texture budget: 594 textures are 0.98 GB as BC7/BC5 with mips at full size. With prop textures capped at 1,024 and
the 3,072/4,096 terrain and backdrop textures kept, the target is under 700 MB of VRAM. The engine needs: a DDS
loader, upload of pre-compressed mip chains, and the 2,048 clamp and power-of-two rule relaxed for those images.

## 6. Materials and lighting

The source look is physically based with normal maps, 5 shadow-casting light types and global illumination. The
engine has none of that. The plan is staged so that each stage is a usable map.

| Stage | Material data | Lighting | Engine work |
|---|---|---|---|
| M0 (prototype) | one base-colour texture per material (the image feeding base colour; 137 distinct images), cut-out from alpha, two-sided from class | unlit x vertex/instance tint, global fog | new pass, one vertex format, one opaque + one cut-out pipeline |
| M1 | + normal map, roughness/metal pack | per-pixel sun (N.L) + hemisphere ambient + simple specular; baked ambient occlusion in the vertex colour | shader only |
| M2 | two-layer blend with mask for the brick/concrete/trim families (re-expressed from their node graphs per `builder`); terrain from the scene's own baked `near_colour`/`far_colour` maps plus tiling detail | baked sun visibility per instance (low-frequency, in the cooker by ray casting), or cascaded sun shadow maps | cooker work, or a shadow pass |
| M3 | emissive, water, effects placement as `fx_runner` entities | point/spot lights for the palace interior (small fixed budget per cluster) | optional |

M0 exists to prove the pipeline end to end and to measure geometry cost before any look work. Whether sun shadows
are baked or dynamic is deliberately left open until M1 can be looked at; baked visibility is cheaper at run time
and has no moving objects to worry about except players, who would not cast shadows on the world either way.

Vegetation (13.2 M triangles, 27 %): alpha-tested, two-sided, drawn after opaque geometry front to back; it is the
main overdraw risk. LODs for trees end in a cross-plane impostor generated by the cooker.

## 7. Renderer integration (rd-vulkan)

New files `rd-vulkan/tr_tworld.cpp`, `vk_tworld.cpp`, shader templates `tworld_vert/frag`. Existing files get hooks only.

| Topic | Design |
|---|---|
| Load | `RE_LoadWorldMap`: after the BSP, try `maps/<name>.tworld`. Read section by section; upload vertices and indexes through the existing staging path into 1-4 device-local buffers (each under 2 GB; `int` offsets avoided in the new code). Textures through the new DDS path. No CPU copy of vertices is kept; the instance and cluster tables stay in RAM |
| Buffers | static: vertex, index. Per frame: one instance buffer (transform + tint) filled by the CPU for visible instances, sized for the worst case (17,754 x 64 B = 1.1 MB) |
| Culling (CPU) | per frame: frustum-test grid cells, then instance spheres inside partially visible cells; distance and screen-size reject (the Warzone idea); pick a LOD from projected error. 17,754 sphere tests is small enough to do brute force first and optimise only if the profile says so |
| Batching | visible (mesh LOD, material) pairs are bucketed; each bucket is one `vkCmdDrawIndexed` with `instanceCount` > 1. Upper bound on draws: distinct visible mesh-LOD x material ranges, order of 1,000-2,000, independent of how many placements are visible |
| Order | opaque by pipeline then material; cut-out after opaque; blended last. Drawn before the BSP entity/draw-surface list so players, sabers and effects depth-test against it normally |
| Far scenery | drawn first with its own projection (scaled space, own near/far), then depth is cleared and the main scene is drawn. This is the 3D-skybox technique and keeps D24 precision for the playable area |
| Far plane | the module supplies the cooked world's bounds to `R_SetFarClip`, so the far plane no longer depends on the collision BSP's leaves; worldspawn sets `distanceCull` for entity and snapshot culling |
| Entity lighting | when a cooked world with a probe section is loaded, entity light sampling reads the probes instead of the missing BSP light grid |
| What stays on the CPU | culling, LOD choice, bucket sort, instance buffer fill. No per-triangle or per-surface work. Single-threaded, like the rest of the front end; no new threads |
| Not in version 1 | GPU-driven culling, indirect draws, occlusion culling, streaming. Each is a later optimisation to be justified by a measurement |
| Dynamic lights, decals on the world | saber marks and dynamic lights use BSP surfaces today; on cooked geometry they would not appear in version 1. Listed as a known gap |
| Other renderers | rd-vanilla and rend2 show only what the BSP contains. A low-detail visible fallback can be compiled into the BSP later if wanted |

Expected performance, to be tested: GPU load is dominated by triangle count after LOD and by alpha-tested overdraw.
On Korriban the same card drew up to 1.55 M triangles through a far less efficient path at 83-144 FPS. A budget of
3-5 M triangles per frame after culling and LOD is the design target for 60 FPS at 1080p on the RTX 2070; whether
the scene can be brought under that with acceptable LOD quality is the main open performance question.

Prerequisite: compiling new SPIR-V needs `glslangValidator`. No Vulkan SDK is installed, but copies of the tool exist
on disk (for example `E:\RenderDoc\plugins\spirv\glslangValidator.exe`). Step 0 checks that one of them rebuilds an
existing shader correctly; only if that fails is an SDK download needed, which would need the user's approval.

## 8. Collision BSP

Source: a **separate, simplified collision export** from the cooker, not the render meshes.

| Rule | Basis |
|---|---|
| Exclude objects whose name contains "nocollision" (228), decals (320), effect emitters, leaves/flowers/vines, objects under about 0.5 m (772), backdrop, sky, water surface | names and sizes measured in the scene |
| Buildings, walls, stairs, fences, statues, large props: use a low LOD of the render mesh (meshoptimizer, error bound of a few units) | LOD chain already produced by the cooker |
| Trees: trunk only | separate stem materials exist (`SS_Naboo_TreeStems`) |
| Terrain: the near terrain inside the playable bounds, decimated with a tight error near walkable areas | regular grid, simplifies well |
| Invisible boundary: clip walls around the playable area | keeps players and bots out of the visual-only world |

How many collision triangles result is unknown until the export runs; the instanced total will be reported by the
prototype. For scale: Korriban's 1.3 M triangle-brushes load and run at about 3 microseconds per trace with the BVH.

Compiler, two steps:

1. **Prototype: the existing `Netradiant\q3map2.exe` (2.5.17n).** The cooker writes a `.map` with a caulk hull and a
   coarse grid of structural brushes (so the tree gets real leaves), and `misc_model` entities with spawnflag 2
   pointing at exported collision OBJ chunks. `-game ja -meta`, no `-vis`, no `-light`. This is the same route the
   Korriban map took, so its output is known to load.
2. **Production: an own RBSP writer in the cooker.** Emits planes, brushes with bevels, a kd-tree of nodes and
   leaves over brush bounds, one model, shaders and the entity string; merges coplanar triangles into larger convex
   brushes where possible. No caps, no dependency on a compiler binary without source, tree quality under our
   control. Verified by loading in the engine and by comparing traces against the q3map2 version of the same region.

WzMap (built here, writes stock RBSP) is the fallback if q3map2 2.5.17n hits a limit before the own writer exists.

Leaks do not matter (no vis, no light stage). Surface flags for footsteps come from the collision shader names
(stone, grass, water, metal).

## 9. Spawn points and bot navigation

The source has no gameplay data, so spawns are generated and then reviewed.

* Candidates: sample the collision export for upward-facing surfaces with slope under about 35 degrees inside the
  playable bounds; keep points where a player box (30 x 30 x 64 units plus headroom) is free and the ground is at
  least a few metres wide.
* Selection: farthest-point sampling to at most 64-100 points (engine limit 128), with a minimum separation and a
  facing direction towards open space; split into two team sets by map half for team modes.
* Override: empties named `spawn_*` in a small companion .blend, or a text file, replace generated points; the
  original .blend is never edited.
* Validation in the engine: a server-side check that boxes at every spawn are not in solid and have ground below
  (the bot code already respawns a bot that starts in solid; that should never trigger on this map).
* Entities are written to the BSP entity string; `maps/<name>.ent` allows changing them without recompiling.

Bots: the first test uses the existing trace-based navigation unchanged (`BotFallbackNavigation`), measuring time
stuck, distance covered and falls with the existing `watch_bots.ps1` approach. If that is not good enough in a city
with canals and stairs, the next step is a Recast navmesh (Zlib licence) built from the collision export and
converted to waypoints (limit 4,096) or queried directly. That is a later decision, taken with numbers.

## 10. Roadmap

Each step ends with something built and tested; documents named in brackets are updated when the step is real.

| # | Step | Done when |
|---|---|---|
| 0 | Set-up: own worktree `naboo_src` (branch `naboo-theed`), `build_naboo\`, isolated game directory; confirm the unmodified branch builds and runs Korriban from there | client and server start from the isolated directory [`BUILD.md`] |
| 1 | Export prototype: one representative region (main street and plaza, about 150 x 150 m around x 700, y 0) exported both as a direct dump and as glTF | export time, sizes and material coverage recorded; intermediate format chosen [`ASSET_PIPELINE.md`] |
| 2 | Collision prototype: collision export of that region -> `.map` -> existing q3map2 -> RBSP; load on the dedicated server and in rd-vulkan | a player can walk the region in a map with no visuals; trace timing recorded; scale factor chosen by eye against a player model [`BOT_NAVIGATION.md`, `BENCHMARKS.md`] |
| 3 | Cooker v0: meshes, instances, base-colour textures as DDS, no LODs | `.tworld` written; section sizes reported [`WORLD_FORMAT.md`] |
| 4 | Renderer v0 (stage M0): load and draw the region, instanced, frustum-culled, unlit | screenshot matches the Blender viewport in layout; FPS and draw counts recorded [`RENDERER.md`] |
| 5 | LODs, cluster grid, screen-size culling; whole city exported | whole-map FPS at fixed camera positions with the existing client benchmark method |
| 6 | Terrain tiles, far scenery pass, environment block, fog | no depth artefacts at the horizon; frame cost of the far pass recorded |
| 7 | Whole-map collision, generated spawns, 32-bot server benchmark | server ms per frame and bot movement statistics |
| 8 | Lighting stage M1, then M2; probe grid for players | reviewed by eye by the user |
| 9 | Own RBSP writer; packaging as pk3 parts under 2 GB | traces agree with the q3map2 build on a test set |

**Proposed first build: steps 0-2**, because they need no new renderer code and no SDK, and they answer the three
questions everything else depends on: how long export takes and which intermediate format to use, how big the
collision set really is, and what scale feels right.

## 11. Open risks and unknowns

| Risk | Why it matters | How it gets resolved |
|---|---|---|
| Shader compiler | no Vulkan SDK installed; a `glslangValidator` from RenderDoc exists but is untried with this renderer's build script | test in step 0; SDK download (with approval) only if it fails |
| Material translation | 1,220 materials have more than 40 nodes; a wrong translation looks wrong everywhere | M0 uses base colour only; families are translated one at a time and compared with Blender renders |
| Look without real lighting | the scene relies on shadows and bounce light; flat lighting may look poor | staged M1/M2; decision between baked and dynamic sun shadows after M1 |
| Alpha-tested vegetation overdraw | 27 % of triangles | measure in step 5; impostor LODs, distance fade |
| Triangle budget | 49 M placed triangles must come down to a few million per frame | LOD quality on over-detailed props (49 K-triangle crate piles) is likely fine; buildings are the test |
| Collision size and quality | unknown triangle count; one brush per triangle from q3map2 | step 2 measures it; own writer in step 9 |
| Zero-surface RBSP in rd-vulkan | read as supported, never run | step 2 |
| Depth precision | D24, near plane 4 | far pass with its own depth range; reversed depth is disabled in this renderer for a stated reason |
| Scale | 35.6 vs 39.37 units per metre changes every exported coordinate | step 2, by eye, before the whole map is cooked |
| Geometry-node scatter | produced no instances in background mode; if grass was expected it is not in the export | ask the user whether ground cover is wanted; check in the interactive viewport |
| Missing scenes | README describes Sunset and Dusk variants that are not in this file | only the Cloudy look can be reproduced from this file |
| File size | pk3 and allocations are limited to 2 GB | geometry and textures in separate files; cooker refuses oversize output |
| Dynamic lights and saber marks on cooked geometry | not supported in version 1 | known gap; revisit after M1 |
| Asset origin | the meshes and textures are extracted from a commercial game | fine for private use; any public release of the map would distribute those assets and is the user's decision (nothing is published without approval in any case) |
