# Collision, map load, waypoint nav and bot frame notes

Repo: `TaystJK_AI-Improved-Bots`, branch `claude/korriban-bot-perf`, HEAD `1ef7a9f1f`. Source was read only; nothing was built or run.
All paths are relative to `codemp/` unless they start with `shared/`. Map facts come from `reports/MAP_ANALYSIS.md` and the task brief.
`ai_main.c` / `ai_main.h` are covered by another document; they are only cited here as callers.

Anything marked **(estimate)** is arithmetic from the code and the map counts, not a measurement.

---

## 1. Path of a game-module trace

### 1.1 Call chain

| Step | Where | What happens |
|---|---|---|
| 1 | `game/g_syscalls.c:259` `JP_Trace` | Fork wrapper used by almost all game code (`OrgVisible`, `OrgVisibleBox`, Pmove via `SV_PMTrace` `game/g_active.c:1564`). Runs `BeginHack` (`:144`), `trap->Trace`, `EndHack` (`:210`). |
| 2 | `game/g_public.h:822` `gameImport_t::Trace` | Native DLL: direct function pointer, set at `server/sv_gameapi.cpp:2888` (`gi.Trace = SV_Trace`). Legacy QVM path: `trap_Trace` `game/g_syscalls.c:265` -> `G_TRACE` case `server/sv_gameapi.cpp:1912`. `G_TRACECAPSULE` `:1918` passes `capsule = qtrue`. |
| 3 | `server/sv_world.cpp:822` `SV_Trace` | World first: `CM_BoxTrace(..., model 0, ...)` `:839`. Returns early only if `fraction == 0` `:841`. Otherwise `SV_ClipMoveToEntities` `:878`. |
| 4 | `qcommon/cm_trace.cpp:1464` `CM_BoxTrace` -> `:1217` `CM_Trace` | `local->checkcount++` `:1228`, `c_traces++` `:1230`, builds `traceWork_t` (symmetric box, 8 corner offsets, whole-move AABB `tw.bounds` `:1313-1334`). |
| 5 | `cm_trace.cpp:1075` `CM_TraceThroughTree` | Recursive BSP descent. Called at `:1438` for every sweep and every zero-length **box** test, and at `:1380` for a zero-length zero-size point against the world. (The "position test" special case at `:1339-1340` requires start == end **and** zero box size, unlike stock Quake 3.) |
| 6 | `cm_trace.cpp:651` `CM_TraceThroughLeaf` | Linear loop over every leaf-brush reference, then every leaf surface (patches). |
| 7 | `cm_trace.cpp:536` `CM_TraceThroughBrush` -> `:456` `CM_PlaneCollision` | AABB reject, then one call per side. |

`JP_Trace` cost in the game module: `BeginHack` and `EndHack` each loop over `level.num_entities` (`g_syscalls.c:192-200`, `:245-253` in the non-duel, non-racemode case), reading `g_entities[i].inuse`, `.client`, `client->ps.duelInProgress`, `client->sess.raceMode`. That is two full entity-array passes per trace, before and after the engine call. It is small next to the brush walk below, but it is paid on every trace.

### 1.2 What scales with brushes per leaf

`CM_TraceThroughLeaf` (`cm_trace.cpp:658-676`), per leaf-brush reference:

1. `brushnum = local->leafbrushes[leaf->firstLeafBrush + k]` (sequential 4-byte read).
2. `b = &local->brushes[brushnum]` (48-byte record, random access into a 62.5 MB array).
3. `if (b->checkcount == local->checkcount) continue;` then `b->checkcount = local->checkcount;` (a **write** to every brush record visited, so every visited cache line is dirtied).
4. `if (!(b->contents & tw->contents)) continue;`
5. `CM_TraceThroughBrush`.
6. `if (!trace.fraction) return;` (only exit before the end of the list).

`CM_TraceThroughBrush` (`cm_trace.cpp:536-619`):

| Question | Answer | Lines |
|---|---|---|
| Per-brush AABB early-out before sides? | **Yes.** Six float compares of `tw->bounds` against `brush->bounds`. | `:553-561` |
| What is `tw->bounds`? | AABB of the **whole** move (start to end, expanded by box size), computed once per trace. It is not shrunk as `trace.fraction` drops and not clipped per leaf. `tw.localBounds` exists in the struct (`cm_local.h:189`) but nothing reads or writes it. | `:1313-1334` |
| Side loop | All `numsides` sides, starting at index 0 (the six axial sides are re-tested), via `CM_PlaneCollision`. Exits on the first side that has the whole move in front of it. | `:572-580`, `:481-484` |
| In-leaf spatial acceleration | **None.** No grid, no sub-tree, no sorting. A leaf is a flat list. | - |
| Early exit when a nearer hit is already known | Only between tree nodes (`if (trace.fraction <= p1f) return;` `:1085`). Inside a leaf every remaining brush is still visited. | - |

**Checkcount:** it exists, but it is broken after the first 65,535 increments.

* `cbrush_t.checkcount` is `unsigned short` (`cm_local.h:72`); `clipMap_t.checkcount` is `int` (`cm_local.h:148`).
* `b->checkcount == local->checkcount` promotes the `unsigned short` to `int`. Once `local->checkcount > 65535` the two can never be equal, so the "already checked in another leaf" test at `cm_trace.cpp:662`, `:223`, `:1019` and `cm_test.cpp:105` is always false. The store truncates.
* The counter increments once per `CM_Trace` (`:1228`), twice per `CM_PositionTest` (`:402`, `:407`) and once per `CM_BoxLeafnums` (`cm_test.cpp:178`, called by every `SV_LinkEntity`, `sv_world.cpp:299`). It passes 65,535 within seconds of play and stays there (it is never reset, `CM_ClearMap` aside).
* Effect: a brush referenced from several leaves is re-tested in every leaf a trace visits. On this map the average is 1.19 references per brush (max 1,562 leaves for one brush), so the extra work is modest, but the mechanism is effectively off. Results stay correct (re-testing is idempotent). `cPatch_t.checkcount` is `int` (`cm_local.h:90`) and is fine; the map has no patches.
* `CM_StoreBrushes` (`cm_test.cpp:91`) would return duplicates for the same reason; no caller of it was found in this tree.

`CM_TraceThroughTree` detail that multiplies leaf visits (`cm_trace.cpp:1103-1127`): for a non-point trace against a **non-axial** node plane the box offset is hard-coded `offset = 2048` ("this is silly", `:1125`). A player-box trace that is within 2,048 units of a non-axial split plane descends both children. Axial planes use the real extent (`:1106`). The split planes on this map come mostly from the 2,048-unit `_blocksize` grid (axial), so this was not quantified.

Capsule vs box in the sweep: `CM_PlaneCollision` (`:456-529`) always uses the box corner offset `tw->offsets[plane->signbits]` and never reads `tw->sphere`. Against world brushes a capsule sweep is therefore a box sweep in this engine. `tw->sphere.use` matters only in `CM_TestBoxInBrush` (`:156-180`, position test) and in the capsule entity paths (section 1.6).

### 1.3 Brush bounds at load

`CM_BoundBrush` (`qcommon/cm_load.cpp:231-240`), called per brush from `CMod_LoadBrushes` (`:275`):

```
bounds[0][0] = -sides[0].plane->dist;   bounds[1][0] = sides[1].plane->dist;
bounds[0][1] = -sides[2].plane->dist;   bounds[1][1] = sides[3].plane->dist;
bounds[0][2] = -sides[4].plane->dist;   bounds[1][2] = sides[5].plane->dist;
```

It assumes the first six sides are the axial planes in -X +X -Y +Y -Z +Z order (what q3map2 writes). There is no check that `numsides >= 6`, that the planes are axial, or that `firstSide`/`planeNum` are in range.

### 1.4 Structure layouts and memory (x64)

| Struct | Definition | Fields | sizeof x64 | On-disk record |
|---|---|---|---:|---:|
| `cplane_t` | `shared/qcommon/q_math.h:178-184` | `vec3_t normal; float dist; byte type; byte signbits; byte pad[2];` | 20 | `dplane_t` 16 |
| `cbrushside_t` | `qcommon/cm_local.h:61-64` | `cplane_t *plane; int shaderNum;` (+4 pad) | 16 | 12 (RBSP) |
| `cbrush_t` | `qcommon/cm_local.h:66-73` | `int shaderNum; int contents; vec3_t bounds[2]; cbrushside_t *sides; unsigned short numsides; unsigned short checkcount;` (+4 pad) | 48 | `dbrush_t` 12 |
| `cLeaf_t` | `qcommon/cm_local.h:44-53` | `int cluster, area; ptrdiff_t firstLeafBrush; int numLeafBrushes; ptrdiff_t firstLeafSurface; int numLeafSurfaces;` | 40 | - |
| `cNode_t` | `qcommon/cm_local.h:39-42` | `cplane_t *plane; int children[2];` | 16 | - |

Sizes are derived from the declarations (default MSVC/GCC x64 alignment), not from a compiled `sizeof`.

| Array | Allocation (`cm_load.cpp`) | Count on this map | Bytes |
|---|---|---:|---:|
| `cm.planes` | `:343` `(BOX_PLANES + count) * 20` | 17,745,374 + 12 | 354,907,720 (338 MiB) |
| `cm.brushsides` | `:437` `(BOX_SIDES + count) * 16` | 16,371,182 + 6 | 261,939,008 (250 MiB) |
| `cm.brushes` | `:260` `(BOX_BRUSHES + count) * 48` | 1,302,559 + 1 | 62,522,880 (60 MiB) |
| `cm.leafbrushes` | `:381` `(count + BOX_BRUSHES) * 4` | 1,553,593 + 1 | 6,214,376 |
| `cm.leafs` | `:300` `(BOX_LEAFS + count) * 40` | 5,433 + 2 | 217,400 |
| `cm.nodes` | `:208` `count * 16` | 5,323 | 85,168 |
| `cm.visibility` | `:505` | 512,520 B lump | 512,520 |
| `cm.entityString` | `:480` | 761,260 B | 761,260 |
| **Total collision model** | | | **about 687 MB** |

7.4 M of the 17.7 M planes are not referenced by any brush side (10,298,036 are), so about 149 MB of `cm.planes` is never touched by collision.

One brush test that passes the AABB touches three separate arrays: the brush (48 B), `numsides` side records (16 B each) and `numsides` planes through a pointer (20 B each, not contiguous per brush). For a 13-side brush that is up to 48 + 208 + 260 bytes spread over three allocations.

### 1.5 Per-trace cost on this map (estimate)

Leaf-brush entries walked per trace are in `MAP_ANALYSIS.md` section 3 (3,557 mean for a 64-unit ground check, 9,785 mean for a 2,048-unit ray, 27,183 mean for an 8,192-unit ray). Per entry the engine does one index read, one 48-byte record read and write, a contents test and (if contents match) six float compares. The brush array is 62.5 MB, larger than any L3 cache, so cost per entry is dominated by cache behaviour:

| Assumption | Cost per entry | 3,557 entries | 9,785 entries | 27,183 entries |
|---|---:|---:|---:|---:|
| Records in cache | about 3 ns | about 11 us | about 29 us | about 82 us |
| One miss per record | about 40 ns | about 140 us | about 390 us | about 1.1 ms |

Reality sits between the rows and must be measured. For long visibility rays `tw->bounds` is the AABB of the whole ray, so a diagonal ray lets many more brushes through the AABB test into the side loop (MAP_ANALYSIS counts 301 mean, 1,630 max overlapping brushes for 8,192-unit rays).

### 1.6 Other collision entry points

| Function | Lines | Per-leaf behaviour | Notes |
|---|---|---|---|
| `CM_PointContents` | `cm_test.cpp:205-262` | Walks **every** brush of the one leaf containing the point. **No AABB test, no checkcount, no contents mask.** For each brush it tests sides from index 0 with `DotProduct(p, sides[i].plane->normal) > plane->dist` and breaks on the first failure (`:246-253`). | Usually rejects on side 0 to 5, but each brush costs three dependent loads (brush, side, plane) instead of one. Mean 728, max 22,182 brushes per call. Called by `SV_PointContents` `sv_world.cpp:898`. |
| `CM_PointLeafnum_r` | `cm_test.cpp:32-55` | Tree walk only (depth 3 to 68, mean 29.7). Increments `c_pointcontents` `:52`. | Used by `CM_PointContents`, `SV_inPVS` (`server/sv_game.cpp:90`, two walks). |
| `CM_PositionTest` | `cm_trace.cpp:381-416` | `CM_BoxLeafnums_r` into `leafs[MAX_POSITION_LEAFS = 1024]` (`:380`), then `CM_TestInLeaf` per leaf. | Only reached at `:1376`, which needs model 0 with `firstNode == -1`; the world model has `firstNode == 0` (`cm_load.cpp:163-165`), so for the main map this function is **not reached**. "Am I stuck" box tests (start == end, non-zero size) take the normal sweep path and report `startsolid`/`allsolid` from `CM_TraceThroughBrush` `:586-600`. |
| `CM_TestInLeaf` -> `CM_TestBoxInBrush` | `cm_trace.cpp:212-266`, `:109-204` | Same flat loop, same broken checkcount (`:223`), AABB early-out at `:123-154`, then sides **from index 6** (`:159`, `:184`). | Used for zero-size point tests against submodels and the temp box (`:1371`). Stops at first `allsolid`. |
| `CM_BoxLeafnums` | `cm_test.cpp:174-193`, `_r` `:141-167` | Tree walk with `BoxOnPlaneSide`; no brush work. | Called by `SV_LinkEntity` with `MAX_TOTAL_ENT_LEAFS = 128` (`sv_world.cpp:208`, `:299`). A mover larger than 128 leaves keeps only the first 128 plus `lastLeaf`. |
| `CM_TransformedBoxTrace` | `cm_trace.cpp:1478-1565` | Transforms start/end into model space, calls `CM_Trace` on a submodel or the temp box. | Entity clipping. |

### 1.7 Entity clipping (`SV_AreaEntities`, `SV_ClipMoveToEntities`)

| Item | Value | Lines |
|---|---|---|
| Sector tree | `AREA_DEPTH 4`, `AREA_NODES 64`; 31 nodes are actually created (15 interior + 16 leaves). Splits alternate on the longer of X/Y only, never Z. | `sv_world.cpp:75-78`, `:110-143` |
| Built from | World model bounds in `SV_ClearWorld`. | `sv_world.cpp:151-162` |
| Leaf sector size on this map | 47,136 / 4 by 43,456 / 4 = about 11,784 x 10,864 units, full height **(estimate)** | - |
| Entity placement | An entity is linked at the first node whose split plane its absbox crosses, else in a leaf sector. | `sv_world.cpp:347-363` |
| Query | `SV_AreaEntities_r`: every entity on each visited node gets a 6-compare AABB test; both children are visited when the query box straddles. | `sv_world.cpp:392-430` |
| Query box in `SV_Trace` | AABB of the **full** start-to-end move plus 1 unit, not the world-clipped move (the line that would clip it is commented out at `:856`). | `sv_world.cpp:857`, `:867-875` |
| Per returned entity | Skip pass entity / owner rules `:571-601`, contents mask `:605`, `DuelCull` `:614` (`server/duel_cull.cpp:101`), then `CM_TransformedBoxTrace` `:629`. | - |
| Clip model | `SV_ClipHandleForEntity` `sv_world.cpp:39-51`: inline bmodel, or `CM_TempBoxModel` box, or capsule if `SVF_CAPSULE`. | `cm_load.cpp:983-1009` |
| Ghoul2 | Only when `traceFlags & G2TRFLAG_DOGHOULTRACE` and the box was hit. | `sv_world.cpp:710-803` |

How many entities per trace: the server keeps roughly 230 map entities (101 doors, 7 trains, 63 fx_runner, spawn points, path_corners, breakables, speakers; the 3,900 `misc_model_static` are freed at spawn, `game/g_misc.c:439-442`) plus clients and transient missiles. Only those whose absbox overlaps the move AABB and whose `r.contents` matches the mask are clipped. For short movement traces that is 0 to a few; for long diagonal visibility rays the AABB can cover a large part of the map and return most solid entities. All 108 brush entities have one brush each, so each entity clip is one brush test. Entity clipping is cheap here compared with the world leaf walk. `SV_PointContents` (`sv_world.cpp:890-917`) puts an `int touch[MAX_GENTITIES]` (8 KB) on the stack per call.

Capsule paths: `CAPSULE_MODEL_HANDLE` entities go through `CM_TraceCapsuleThroughCapsule` (`cm_trace.cpp:906`) or `CM_TraceBoundingBoxThroughCapsule` (`:968`); position tests through `CM_TestCapsuleInCapsule` (`:275`) / `CM_TestBoundingBoxInCapsule` (`:344`). `SV_PMTrace` passes `capsule = qfalse` (`g_active.c:1565`), so player movement uses boxes.

### 1.8 Existing instrumentation

| Counter | Declared | Incremented | Notes |
|---|---|---|---|
| `c_traces` | `cm_load.cpp:58` | `cm_trace.cpp:1230` (every `CM_Trace`, including entity clips) | OK |
| `c_brush_traces` | `cm_load.cpp:58` | **Never.** No `c_brush_traces++` exists in the tree. | Always prints 0. |
| `c_patch_traces` | `cm_load.cpp:58` | `cm_trace.cpp:436` | 0 on this map (no patches). |
| `c_pointcontents` | `cm_load.cpp:57` | `cm_test.cpp:52` (every `CM_PointLeafnum_r`, so it also counts `SV_inPVS` and leaf lookups) | Over-counts. |

Printing: `com_showtrace 1` (`qcommon/common.cpp:1468`, `CVAR_CHEAT`, so it needs `devmap` or cheats). `Com_Frame` prints one line per frame and zeroes the counters (`common.cpp:1880-1891`):

```
%4i traces  (%ib %ip) %4i points
```

There is no counter for leaf-brush entries walked, brushes passing the AABB, or sides tested. Adding them next to `c_traces` is the natural place.

---

## 2. Map load path

### 2.1 Order and allocations

`SV_SpawnServer` calls `CM_LoadMap( va("maps/%s.bsp", server), qfalse, &checksum )` (`server/sv_init.cpp:597`), then `SV_ClearWorld` (`:615`).

`CM_LoadMap` (`cm_load.cpp:793`) -> `CM_LoadMap_Actual` (`:621`):

| Step | Lines | Notes |
|---|---|---|
| Open and read whole BSP | `:688-693` | `iBSPLen` is `const int` from `FS_FOpenFileRead` (returns `long`, `files.cpp:1531`). `Z_Malloc(iBSPLen, TAG_BSP_DISKIMAGE)`: **695 MB in one malloc**. Kept in `gpvCachedMapDiskImage` for the renderer (`:696-700`). |
| Checksum | `:713` | `Com_BlockChecksum` (MD4) over all 695 MB on every load. |
| Version check | `:722-728` | `BSP_VERSION` only. |
| `CMod_LoadShaders` | `:96-121` | `(1+count) * sizeof(CCMShader)`; 291 shaders. |
| `CMod_LoadLeafs` | `:285-321` | Also derives `numClusters`, `numAreas`; `areaPortals = numAreas * numAreas * 4` (`:320`, 1 area here). |
| `CMod_LoadLeafBrushes` | `:369-389` | Copy with `LittleLong`. Indices not validated. |
| `CMod_LoadLeafSurfaces` | `:396-416` | |
| `CMod_LoadPlanes` | `:328-362` | Computes `type` and `signbits`. |
| `CMod_LoadBrushSides` | `:423-450` | `out->plane = &cm.planes[num]`, `num` not range-checked; `shaderNum` is checked (`:446`). The RBSP `drawSurfNum` is dropped. |
| `CMod_LoadBrushes` | `:249-278` | `out->sides = cm.brushsides + firstSide` not range-checked; `numsides` narrowed to `unsigned short` (`:267`); `CM_BoundBrush` (`:275`). |
| `CMod_LoadSubmodels` | `:129-186` | Per submodel two `Hunk_Alloc`s for brush and surface index lists (`:173`, `:180`). `MAX_SUBMODELS` check at `:145` (after the alloc). |
| `CMod_LoadNodes` | `:195-223` | `planeNum`, children not validated. |
| `CMod_LoadEntityString` | `:458-483` | See 2.3. |
| `CMod_LoadVisibility` | `:491-509` | |
| `CMod_LoadPatches` | `:520-573` | `MAX_PATCH_VERTS 1024` stack array (`:519`, `:527`). Allocates `numSurfaces` pointers; no patches on this map, so `CM_GeneratePatchCollide` is never called. |
| `CM_InitBoxHull` | `:928-972` | Uses the `BOX_*` slack slots. |
| Free or keep disk image | `:761-777` | Freed immediately if `com_dedicated` or `Sys_LowPhysicalMemory()`; otherwise kept until the renderer has loaded the world. |
| `CM_FloodAreaConnections` | `:782` | |

There are **no** `MAX_MAP_*` checks anywhere in `cm_load.cpp`. Every lump is sized from `filelen / sizeof`. The only fixed limits on the collision load path are `MAX_SUBMODELS` (512), `MAX_PATCH_VERTS` (1024, patches only), `MAX_SUB_BSP` (32) and the patch-collide limits in `cm_patch.h`.

### 2.2 Integer width risks

| Site | Expression | Risk | This map |
|---|---|---|---|
| `Hunk_Alloc( int size, ...)` `z_memman_pc.cpp:823`, `Z_Malloc( int iSize, ...)` `:174` | Callers compute `count * sizeof(...)` in `size_t`, then it is narrowed to `int` with no check. | A lump whose in-memory size exceeds 2,147,483,647 bytes wraps silently. Thresholds: planes > 107,374,170; brush sides > 134,217,721; brushes > 44,739,241. | Largest is 354.9 MB (planes): safe, 16.5 % of the limit. |
| `Z_Malloc` `:185` | `int iRealSize = iSize + sizeof(zoneHeader_t) + sizeof(zoneTail_t)` | Same 2 GiB ceiling per allocation. | Safe. |
| `cm_load.cpp:688` | `const int iBSPLen` | A BSP of 2 GiB or more cannot be loaded. | 695 MB: safe. |
| `cm_load.cpp:267` | `out->numsides = LittleLong(in->numSides)` into `unsigned short` | Truncates above 65,535 sides. | Max 88: safe. |
| `cm_local.h:72` vs `:148` | `unsigned short checkcount` vs `int checkcount` | Dedup dead after 65,535 traces (section 1.2). | **Affects this map.** |
| `cm_load.cpp:266`, `:444`, `:215`, `:308-311` | `firstSide`, `planeNum`, `firstLeafBrush`, leaf-brush indices used unchecked | Out-of-range values in a damaged BSP read or write outside the arrays. | Not a count problem; flagged as unchecked input. |
| `cm_load.cpp:232-239` | `sides[0..5]` read without `numsides >= 6` check | Brush with fewer than six sides reads neighbouring sides. | q3map2 output always has six axial sides first. |
| `cm_load.cpp:320` | `cm.numAreas * cm.numAreas * sizeof(int)` | `int * int` first; overflows above 46,340 areas. | 1 area. |

No wrong printf format specifier was found in `cm_load.cpp`, `cm_test.cpp`, `cm_trace.cpp` or `sv_world.cpp` (the few prints there use `%i`/`%f`/`%s` with matching types).

### 2.3 Entity string

| Consumer | Code | Fixed buffers |
|---|---|---|
| Collision load | `CMod_LoadEntityString` `cm_load.cpp:458-483`. First tries `maps/<name>.ent` (`:463-477`); if it exists it **replaces** the BSP entity lump (allocated `len + 1`, NUL-terminated). Otherwise `Hunk_Alloc(l->filelen)` and `memcpy` (`:480-482`): no extra byte, relies on the lump's own trailing NUL. | None. Not checked against `MAX_MAP_ENTSTRING`. |
| Server parse | `sv.entityParsePoint = CM_EntityString()`; `SV_GetEntityToken` `server/sv_gameapi.cpp:612-631` uses `COM_Parse` and `Q_strncpyz` into the caller's buffer. | `COM_Parse` token: `MAX_TOKEN_CHARS 1024` (`q_shared.h:180`). |
| Game parse | `G_ParseSpawnVars` `game/g_spawn.c:1226-1268`, `G_AddSpawnVarToken` `:1050-1065`. Buffers are **per entity**, reset at `:1230-1231`. | `MAX_SPAWN_VARS 64` keys per entity (`bg_public.h:36`), `MAX_SPAWN_VARS_CHARS 4096` bytes per entity (`bg_public.h:37`); both `ERR_DROP` on overflow (`g_spawn.c:1056`, `:1262`). |
| Renderer | `R_LoadEntities` `rd-vulkan/tr_bsp.cpp:2186-2283`: `Hunk_Alloc(l->filelen + 1)` and `strcpy` of the BSP lump (`:2203-2205`); parses only worldspawn. `R_GetEntityToken` `:2290`. Note it copies the **BSP lump**, not an external `.ent`. | `keyname`/`value[MAX_TOKEN_CHARS]`. |
| cgame parse | `CG_ParseEntitiesFromString` `cgame/cg_spawn.c:441-464` through `trap->R_GetEntityToken` (`client/cl_cgameapi.cpp:1783`). | Same `MAX_SPAWN_VARS` / `_CHARS` per entity (`cg_spawn.c:411`). |
| botlib | `BotImport_BSPEntityData` returns `CM_EntityString()` (`server/sv_bot.cpp:398`). Whether botlib copies it into a fixed buffer was not traced. | Not verified. |

The 761 KB entity string is never copied into a fixed-size buffer on the paths above. `MAX_MAP_ENTSTRING` (`qfiles.h`, now `0x100000`) is not referenced by any code in the repo. `korriban_extracted/maps/` contains a `swtor_korriban.ent`; if a copy sits in `maps/` of the game path, the server and game use it while the renderer and cgame keep using the BSP lump, so the two sides can disagree.

### 2.4 Hunk and zone

| Item | Finding |
|---|---|
| `com_hunkmegs`, `com_zonemegs` | **Do not exist in this fork.** No match for `hunkmegs` or `zonemegs` anywhere under `codemp/`. |
| `Hunk_Alloc` | `return Z_Malloc(size, hunk_tag, qtrue);` (`z_memman_pc.cpp:823-825`). The hunk is a zone tag (`TAG_HUNK_MARK1/2`), not a fixed block. |
| `Z_Malloc` | Plain `malloc`/`calloc` per allocation with a header and tail (`z_memman_pc.cpp:174-200`). On failure it frees the cached BSP image, unused sounds, images and models and retries (`:204-260`). |
| `Hunk_MemoryRemaining` | Returns a made-up `64 MB - used` (`z_memman_pc.cpp:725-727`); it goes negative on this map. Callers that trust it were not audited. |
| Limit | Process address space and RAM only. A 32-bit build could not hold this map; the installed binaries are x86_64. |

Peak during a listen-server load **(estimate)**: 695 MB disk image + 687 MB collision model at the same time, then the renderer builds its world data (2.2 M drawverts, 29 K surfaces, world VBO) before the image is freed. Expect well over 1.5 GB committed during load. A dedicated server frees the image right after the collision load (`cm_load.cpp:765-772`) and settles near 0.7 GB plus the snapshot pool (see ENGINE_LIMITS_NOTES.md).

---

## 3. Waypoint navigation (`game/ai_wpnav.c`, `game/ai_util.c`)

### 3.1 Data structures

| Item | Definition | Value / layout |
|---|---|---|
| `wpneighbor_t` | `qcommon/q_shared.h:541-545` | `int num; int forceJumpTo;` |
| `wpobject_t` | `qcommon/q_shared.h:547-562` | `vec3_t origin; int inuse, index; float weight, disttonext; int flags, associated_entity, forceJumpTo, neighbornum; wpneighbor_t neighbors[MAX_NEIGHBOR_SIZE];` about 300 bytes |
| `gWPArray` | `game/ai_wpnav.c:34` | `wpobject_t *gWPArray[MAX_WPARRAY_SIZE]`, each element `B_Alloc`ed on demand (`:403`). A second copy of the pointer table lives in the engine (`server/sv_bot.cpp:44-45`, filled by `SV_BotWaypointReception` `:79`). |
| `gWPNum` | `game/ai_wpnav.c:35` | Count of used entries. |
| `MAX_WPARRAY_SIZE` | `q_shared.h:533` | 4096 |
| `MAX_NEIGHBOR_SIZE` | `q_shared.h:534` | 32 |
| `MAX_NEIGHBOR_LINK_DISTANCE` | `q_shared.h:536` | 128 units |
| `MAX_NEIGHBOR_FORCEJUMP_LINK_DISTANCE` | `q_shared.h:537` | 400 (defined; `CanForceJumpTo` uses literal 400 at `ai_wpnav.c:1580`) |
| `DEFAULT_GRID_SPACING` | `q_shared.h:539` | 400 (RMG grid) |
| `nodetable` | `ai_wpnav.c:39`, `nodeobject_t` `game/ai_main.h:134-142` | `MAX_NODETABLE_SIZE 16384` (`ai_main.h:34`), `TABLE_BRANCH_DISTANCE 32` (`ai_main.h:33`). Scratch for `ConnectTrail` and RMG. |
| Route file buffer | `ai_wpnav.c:2047`, `:2054` | 524,288 bytes; a longer file is rejected. |

The model is a single ordered **trail**: waypoint `i` is implicitly connected to `i-1` and `i+1`, and `neighbors[]` adds branch links. "Trail distance" is the sum of `disttonext` along the index range (`TotalTrailDistance`, `ai_main.c:1324`), an O(|end - start|) loop, not a graph search.

### 3.2 Loading

| Step | Lines |
|---|---|
| `G_InitBots` -> `LoadPath_ThisLevel` | `game/g_bot.c:1392-1400` -> `ai_wpnav.c:3282` |
| Non-RMG: `LoadPathData(mapname)` | `ai_wpnav.c:3307-3313` |
| File name | `botroutes/<mapname>.wnt` (`:2035`) |
| Text format | Optional first line `l<...> <levelflags>` (`:2059-2079`), then per waypoint `index flags weight (x y z) { n n-fj ... } disttonext\n` (`:2085-2242`). The parser has no bounds checks on `currentVar[2048]`, on `i < len` inside the inner loops, or on `neighbornum < MAX_NEIGHBOR_SIZE` (`:2199`, `:2221`). |
| Post-load | `CalculateSiegeGoals` (siege only), `CalculateWeightGoals`, `CalculateJumpRoutes` (`:2249-2258`). Neighbors come from the file; `CalculatePaths` is **not** run at load. |

### 3.3 No `.wnt` file (this map)

1. `trap->FS_Open` fails, `LoadPathData` prints `Bot route data not found for <map>` and returns 2 (`ai_wpnav.c:2041-2045`).
2. `LoadPath_ThisLevel` does nothing with that result (`:3309-3312`, empty body with a comment).
3. `gWPNum` stays 0. **There is no auto-generation for a normal map.**

Auto-generation exists only for random-mission terrain:

| Condition | Lines |
|---|---|
| Cvar `RMG` non-zero (`game/g_xcvar.h:175`, default `"0"`) | `ai_wpnav.c:3290` |
| and `bot_normgpath` == 0 (registered `"1"`, `CVAR_CHEAT`) | `:3292-3299` |
| `BeginAutoPathRoutine` (`:3221`): collects `info_player_deathmatch` with `origin[2] < 1280` and CTF flags, `G_RMGPathing`, `trap->BotCalculatePaths` | `:3229-3277` |
| `G_RMGPathing` (`:3055`) needs an entity with classname `terrain` and `eType == ET_TERRAIN`; otherwise prints `Error: RMG with no terrain!` and returns | `:3068-3074` |
| Then: grid of 400-unit nodes dropped by 3,000-unit box traces (`:3092-3129`), `G_RecursiveConnection` between consecutive spawn points (`:3162`), `G_BackwardAttachment` (`:2984`, caps at `gWPNum < 3900`, `:3034`) | |

Korriban has no terrain entity, so forcing `RMG 1` would not produce waypoints either.

`ConnectTrail` (`:1016`) is a 32-unit flood fill, but it only bridges two **existing** consecutive waypoints, and only from `RepairPaths` (`:1482`), which is only called from `SavePathData` (`:2416`, the `bot_wp_save` command) and from `G_RMGPathing` (`:3208`, where `ConnectTrail` returns immediately for RMG, `:1039-1048`).

Manual authoring: `bot_wp_edit 1` (`CVAR_CHEAT`, `ai_main.c:15046`) sets `gBotEdit` (`ai_wpnav.c:3315-3324`); commands are handled in `AcceptBotCommand` (`:3428`): `bot_wp_add`, `bot_wp_rem`, `bot_wp_addflagged`, `bot_wp_switchflags`, `bot_wp_tele`, `bot_wp_spawntele`, `bot_wp_killoneways`, `bot_wp_save`.

With `gWPNum == 0`: `GetNearestVisibleWP` (`ai_main.c:1235`) loops zero times and returns -1 without tracing; `CalculateWeightGoals`, `FlagObjects` and `BotWaypointRender` do nothing. What the AI does when it has no waypoint is in `ai_main.c` (other document).

### 3.4 Lookups

| Function | Where | Algorithm | Traces |
|---|---|---|---|
| `GetNearestVisibleWP(org, ignore)` | `ai_main.c:1235-1278` | Linear scan of all `gWPNum`. Candidate must be nearer than the best so far (starts at 800 units, 300 for RMG), pass `BotPVSCheck`, then `OrgVisibleBox` with a 30x30x2 box. | One box trace per candidate that beats the running best. Worst case every waypoint within 800 units. |
| `GetNearestVisibleWPToItem` | `ai_wpnav.c:1829-1868` | Same, 64-unit radius, +-15 Z, `trap->InPVS` first. | Called per item entity from `CalculateWeightGoals` (`:1951`). No items on this map. |
| `TotalTrailDistance(start, end, bs)` | `ai_main.c:1324` | Sum of `disttonext` over the index range; -1 on a one-way flag or hole. | None. |
| `CalculatePaths` | `ai_wpnav.c:1635-1725` | O(N^2) over all pairs with `NotWithinRange` (index difference > 5). Link if distance < 128, same integer Z and `OrgVisibleBox` 30x30x30, or `CanForceJumpTo`. Stops at 32 neighbors. | Only run by `bot_wp_save` (`:2422`). Engine twin `SV_BotCalculatePaths` (`server/sv_bot.cpp:97-183`, force-jump disabled) is used for RMG. |
| `CalculateWeightGoals` | `ai_wpnav.c:1870-1963` | Loops all `level.num_entities`, string-compares classnames, nearest waypoint per item. | Via `GetNearestVisibleWPToItem`. |
| `CalculateJumpRoutes` | `ai_wpnav.c:1965-2017` | One pass, height differences only. If waypoint 0 has `WPFLAG_JUMP` it reads `gWPArray[-1]` (`:1982`), an out-of-bounds read of the pointer table. | None. |

### 3.5 Every trace call site

`ai_util.c` contains **no** trace, point-contents or PVS calls (it is the allocator wrappers `:37-181`, personality/chat parsing `:183-896`, and `Bot_UpdateEnemySwingMemory` `:898`).

`ai_wpnav.c`:

| Line | Function | Trace | Loop bound / trigger |
|---:|---|---|---|
| 833 | `CanGetToVector` | Box 30x30x0, `MASK_SOLID` | Called from `ConnectTrail` `:1166` and four times per node (`:1184`, `:1215`, `:1246`, `:1277`). |
| 854, 876, 883 | old `CanGetToVectorTravel` | - | `#if 0`, dead code. |
| 936 | `CanGetToVectorTravel` | Box, `MASK_PLAYERSOLID` | `while (!initialDone \|\| didMove)` (`:927`): repeats until no progress or the step is used up; no hard iteration cap. |
| 973, 983 | same, stair check | Box x2 (both lines trace `trFrom -> trTo`; `trDown` at `:981` is computed and never used) | Once per iteration that did not move. |
| 1107 | `ConnectTrail` | Point, 4,096 units down | Once per call. |
| 1180, 1211, 1242, 1273 | `ConnectTrail` expansion (+X, -X, +Y, -Y) | Point, 4,096 units down, each followed by `NodeHere` (O(nodenum) scan, `:805`) and `CanGetToVector` | Outer `while (nodenum < 16384 && !foundit && cancontinue)` (`:1119`); inner `while (i < prenodestart)` (`:1159`). Up to 16,384 nodes x 4 directions x 2 traces = **131,072 traces per ConnectTrail**, half of them 4,096-unit rays. |
| 1386 area | `ConnectTrail` backtrack | `CanGetToVectorTravel` per node | `while (failsafe < 16384 ...)` (`:1383`). |
| 1446, 1467 | `DoorBlockingSection` | Point x2 between two waypoints | Once per consecutive pair that fails the checks in `RepairPaths`. |
| 1514 | `RepairPaths` | `OrgVisible` (point, `ai_main.c:1113`) | `while (i < gWPNum)`; reads `gWPArray[i+1]` at the last index. |
| 1546, 1550 | `OrgVisibleCurve` | Box 30x30x30 x2 | From `CanForceJumpTo` (`:1616`) after cheap rejects, inside the N^2 loop of `CalculatePaths`. |
| 1701 | `CalculatePaths` | `OrgVisibleBox` 30x30x30 | N^2 pairs, traced only if distance < 128 and same integer Z. |
| 1787 | `CalculateSiegeGoals` | via `GetNearestVisibleWP` | Per `info_siege_objective`; siege only. |
| 1857 | `GetNearestVisibleWPToItem` | `OrgVisibleBox` 30x30x0 | Per item x waypoints within 64 units. |
| 2323, 2360 | `FlagObjects` | Box 30x30x10, flag to waypoint | `while (i < gWPNum)` twice, traced only when nearer than best. CTF flags only; from `bot_wp_save` / RMG. |
| 2672 | `G_RecursiveConnection` | Point, `CONTENTS_SOLID` | Recursive over the RMG grid, 4 directions; RMG only. No depth cap (stack depth up to node count). |
| 3112 | `G_RMGPathing` | Player-size box, 3,000 units down | Terrain bounds / 400 squared, capped at 16,384; RMG only. |

`BotWaypointRender` (`:243-366`) does no traces; it spawns `G_TestLine` temp entities, only while `gBotEdit` is set, and is called every `BotAIStartFrame` from `ai_main.c:14970`.

### 3.6 Cost estimates for a map this size

| Scenario | Estimate |
|---|---|
| Runtime today (no `.wnt`) | Zero cost from `ai_wpnav.c`: every loop is bounded by `gWPNum == 0`. |
| Coverage limit | 4,096 waypoints. Consecutive points more than 400 units apart get auto-bridged on save (`RepairPaths`, `maxDistFactor 400`, `:1487`), so one trail covers at most about 1.6 M units of path. Enough for routes through the map, not for area coverage of 47K x 43K units. |
| File size | A waypoint line is roughly 90 to 250 bytes (six `%f` fields plus up to 32 neighbors). 4,096 lines can exceed the 524,288-byte cap, which makes `LoadPathData` refuse the file (`:2047-2052`), and `SavePathData` builds the text in the same 524,288-byte buffer (`:2426`). Budget about 2,000 to 3,000 waypoints or raise the cap. |
| `GetNearestVisibleWP` with N waypoints | N distance computations (4,096 -> a few microseconds) plus one `BotPVSCheck` and one box trace per candidate that beats the running best: typically 2 to 10 traces of up to 800 units. From MAP_ANALYSIS, a 512-unit ray walks about 4,900 leaf-brush entries, so one lookup is on the order of 10K to 50K brush-record visits, roughly 0.05 to 2 ms depending on cache state **(estimate)**. PVS rejects little on this map (81 % mutual visibility). With 26 bots each calling it several times per think, this would be a first-order cost. |
| `CalculatePaths` on save | 4,096^2 = 16.8 M pair iterations, traces only for same-Z pairs within 128 units. Seconds, one-off. |
| `ConnectTrail` on save | Up to 131,072 traces per gap, half of them 4,096-unit vertical rays through leaves holding thousands of brushes. Tens of seconds to minutes per unbridged gap **(estimate)**; `bot_wp_distconnect 0` and `bot_wp_visconnect 0` (`ai_main.c:15048-15049`) disable the triggers. |

---

## 4. How the server drives bots

### 4.1 Frame flow

| Step | Where | Notes |
|---|---|---|
| `Com_Frame` computes `minMsec`, sleeps, calls `SV_Frame(msec)` | `qcommon/common.cpp:1726-1783`, `:1806` | Dedicated: `minMsec = SV_FrameMsec()` (`:1750`), about one `SV_Frame` per server tick. Listen server: `minMsec = 1000 / com_maxfps` (`:1757-1758`), one `SV_Frame` per **client** frame. |
| `SV_Frame` | `server/sv_main.cpp:1186` | `frameMsec = 1000 / sv_fps * timescale` (`:1232-1236`). |
| Listen server bot call | `sv_main.cpp:1247` | `if (!com_dedicated->integer) SV_BotFrame( sv.time + sv.timeResidual );` Runs on **every** `SV_Frame` call, i.e. at client frame rate, before the tick loop. |
| Dedicated bot call | `sv_main.cpp:1290` | `if (com_dedicated->integer) SV_BotFrame( sv.time );` Also once per `SV_Frame` call. |
| `SV_BotFrame` | `server/sv_bot.cpp:605-612` | `if (!bot_enable) return;` then `GVM_BotAIStartFrame(time)` (`sv_gameapi.cpp:140-146`). |
| `BotAIStartFrame` | `game/ai_main.c:14913` | For each bot: `BotAI(i, thinktime)` when `botthink_residual >= thinktime` (`:14995-15001`), then **every call**: `BotUpdateInput` and `trap->BotUserCommand` (`:15015-15016`). |
| `BOT_THINK_TIME` | `game/ai_main.c:60` | `#define BOT_THINK_TIME 0`. With 0, `thinktime = elapsed_time` (`:14986-14987`), so every bot runs full `BotAI` on every `BotAIStartFrame` call. There is no stagger (`BotScheduleBotThink` multiplies by 0, `:858`). |
| `trap->BotUserCommand` | `sv_gameapi.cpp:1240-1242` (`gi.BotUserCommand` `:3062`) | `SV_ClientThink(&svs.clients[clientNum], ucmd)` -> `GVM_ClientThink` (`server/sv_client.cpp:1628`, `sv_gameapi.cpp:110-118`). |
| `ClientThink` | `game/g_active.c:5939` | Copies the usercmd (`trap->GetUsercmd` `:5944`). `ClientThink_real` is called here only for **non-bots** (`:5982-5984`). For a bot this call just stores the command. |
| Tick loop | `sv_main.cpp:1293-1300` | `while (sv.timeResidual >= frameMsec) { ...; GVM_RunFrame(sv.time); }` |
| `G_RunFrame` | `game/g_main.c:3547` | Entity loop `:3790`; clients go through `G_RunClient` (`:4287`). `ClientEndFrame` loop `:4373-4383`. |
| `G_RunClient` | `g_active.c:6034` | Returns early for non-bots (`:6117-6119`). For bots: `pers.cmd.serverTime = level.time; ClientThink_real( ent );` (`:6120-6121`). **This is where a bot's movement runs: once per server tick.** |
| `ClientThink_real` -> `Pmove` | `g_active.c:3455`, `Pmove` `:5176`, `pmove.trace = SV_PMTrace` `:4911` | `msec = ucmd->serverTime - ps.commandTime` (`:3767`), capped at 200. Bot tracemask adds `CONTENTS_MONSTERCLIP` (`:4905-4906`). |
| Snapshots | `sv_main.cpp:1314` -> `SV_SendClientMessages` `sv_snapshot.cpp:1078` -> `SV_SendClientSnapshot` `:969` | `SV_BuildClientSnapshot` (`:1016`) runs **for bots too**; the bot early-return is after it (`:1035-1040`). |

Two different rates result:

| Work | Rate | 26 bots, `sv_fps 40` |
|---|---|---:|
| Bot movement (`ClientThink_real` + `Pmove`, from `G_RunClient`) | once per server tick | 1,040 per second |
| Bot AI (`BotAI`, i.e. all of the AI's own traces) plus `BotUpdateInput` and `SV_ClientThink` | once per `SV_Frame` call, because `BOT_THINK_TIME` is 0 | dedicated: about 1,040 per second; **listen server: 26 x client frame rate** (3,250 per second at 125 fps) |

On a listen server the time passed in is `sv.time + sv.timeResidual` (`sv_main.cpp:1247`), which advances every rendered frame, so `elapsed_time` is non-zero every call and every bot thinks every rendered frame. The AI rate is then tied to `com_maxfps`, not to `sv_fps`.

`BotAIStartFrame` also has a guard at `ai_main.c:14917-14923` that skips the whole call when more than 100 ms of wall time passed since `last_frame_time`; where `last_frame_time` is otherwise updated is in the other document's scope.

### 4.2 Cvars

| Cvar | Default | Flags | Where | Effect |
|---|---|---|---|---|
| `sv_fps` | `"40"` | `CVAR_SERVERINFO`, range 0..1000 | `server/sv_init.cpp:1014-1015` | Server tick rate. Reset to 10 if < 1 (`sv_main.cpp:1227-1229`). |
| `bot_enable` | `"1"` | `CVAR_LATCH` | `server/sv_game.cpp:140-141`, `sv_bot.cpp:656` | 0 skips `SV_BotFrame`. |
| `bot_thinktime` | `"100"` | `CVAR_CHEAT` | `server/sv_bot.cpp:668` | Registered by the engine only. The game uses the `BOT_THINK_TIME 0` macro instead, so this cvar has **no effect**. |
| `bot_pause` | `"0"` | `CVAR_CHEAT` | `sv_bot.cpp:676` | Registered; no reader found in `game/` by grep of `ai_main.c`. |
| `bot_minplayers` | `"0"` | `CVAR_SERVERINFO` | `game/g_bot.c:1396` | Auto-fill bots. |
| `g_synchronousClients` | (game cvar) | | `g_active.c:5982`, `:6117` | Only affects humans. |
| `pmove_fixed`, `pmove_msec` | | | `g_active.c:3778-3810`, `:4916-4917` | `pmove_msec` clamped to 1..66. |
| `com_maxfps` | registration line not located | | used `common.cpp:1757-1758` | Caps the listen-server `SV_Frame` rate, and therefore the bot AI rate. |
| `sv_hibernateTime`, `sv_hibernateFPS` | `"0"`, `"2"` | | `sv_init.cpp:1066-1067`, `sv_main.cpp:1197-1213` | With no humans connected the server can drop to 2 fps; bots count as non-human. Leave `sv_hibernateTime 0` for bot-only benchmarks. |
| `timescale` | `"1"` | `CVAR_SYSTEMINFO` | `common.cpp:1466` | Multiplies `frameMsec`. |

### 4.3 Where time can be measured

| Mechanism | Where | What it gives |
|---|---|---|
| `com_speeds 1` | `common.cpp:1470` (no cheat flag); print at `:1863-1875` | One line per frame: `frame:%i all:%3i sv:%3i ev:%3i cl:%3i gm:%3i rf:%3i bk:%3i` in whole milliseconds. |
| `time_game` | set at `sv_main.cpp:1281-1307` | Starts **after** the listen-server `SV_BotFrame` at `:1247`, so on a listen server bot AI time is not in `gm` (bot `Pmove` is, since it runs inside `G_RunFrame`); the AI lands in `sv` (`sv = timeBeforeEvents - timeBeforeServer - time_game`, `common.cpp:1867-1870`). On a dedicated server the bot call at `:1290` is inside the window, so it is in `gm`. |
| `com_showtrace 1` | `common.cpp:1468` (`CVAR_CHEAT`), print `:1880-1891` | Traces / patch traces / leaf lookups per frame (section 1.8). |
| `sv_showghoultraces 1` | `sv_init.cpp:1027`, `sv_world.cpp:752` | Prints each Ghoul2 trace; non-`FINAL_BUILD` only. |
| `trap->Milliseconds()` | `g_public.h:769` | 1 ms resolution wall clock, already used in `g_main.c:2965`, `:3294`, `:4454`. |
| `trap->PrecisionTimerStart/End` | `g_public.h:770-771`, `sv_gameapi.cpp:633-645`, `qcommon/timing.h:29-63` | `__rdtsc` delta on Windows (0 elsewhere); allocates a `timing_c` with `new` per start. Units are TSC ticks, not time. |
| `_G_FRAME_PERFANAL` | `g_main.c:3363` (commented out); timers at `:3783`, `:4355-4436`, print `:4442-4449` | Compile-time: per-phase split of `G_RunFrame` (ItemRun, ROFF, ClientEndframe, GameChecks, Queues). |
| `PATH_TIME_DEBUG` | `ai_wpnav.c:3051-3053`, `:3076-3078`, `:3210-3214` | `_DEBUG` only, RMG pathing only. |
| `timeInPVS` / `timeInTrace` style accumulators | - | **Not present** in this tree (no match for `timeInPVS`, `timeInTrace`, `numInTrace`). |

Suggested insertion points for new timers (no code was changed): around `GVM_BotAIStartFrame` in `SV_BotFrame` (`sv_bot.cpp:611`); around `CM_BoxTrace` and `SV_ClipMoveToEntities` in `SV_Trace` (`sv_world.cpp:839`, `:878`); inside `CM_TraceThroughLeaf` for counts (`cm_trace.cpp:658`); around `SV_BuildClientSnapshot` (`sv_snapshot.cpp:1016`); and around `BotAI` versus `BotUpdateInput`/`BotUserCommand` in `BotAIStartFrame` (`ai_main.c:15001`, `:15015-15016`). `Sys_Milliseconds` is too coarse for single traces; accumulate a high-resolution counter per frame and print it with the `com_speeds` line.
