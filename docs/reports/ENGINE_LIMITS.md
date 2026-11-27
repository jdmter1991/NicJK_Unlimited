# Engine limits relevant to swtor_korriban and 26 bots

Repo: `TaystJK_AI-Improved-Bots`, branch `claude/korriban-bot-perf`, HEAD `1ef7a9f1f`. Read only; nothing was built.
Paths are relative to `codemp/`. Map counts are from the task brief and `reports/MAP_ANALYSIS.md`; two more were read from the BSP for this note (largest trisoup surface: 999 verts, 5,247 indexes; largest planar face: 25 verts; no patch surfaces).

"Stock" is OpenJK. Where the stock value comes from a diff in this repo it is marked **(diff)**; where the line dates from the initial import commit `14cea1563` and was never touched it is marked **(unchanged since import)**; anything else is marked **(from memory, not verified here)**.

All limits below are **compile-time** `#define`s unless the "Type" column says otherwise.

---

## 1. What commit `1ef7a9f1f` "Increased the map limits x4" changed

`git show 1ef7a9f1f --stat`: 3 files, 27 insertions, 25 deletions.

| File | Change |
|---|---|
| `assets/japro/modelscale.cfg` | Unrelated: `darthmalgus_onslaught 1.15 -> 1.21`, added `darth_malgus_3 1.21` and `sith_master_2 1.10`. |
| `codemp/qcommon/q_shared.h:222` | `MAX_MAP_AREA_BYTES 32 -> 128` |
| `codemp/qcommon/qfiles.h:314-336` | 21 `MAX_MAP_*` defines, each multiplied by 4 (table below). |

| Define (`qfiles.h`) | Before | After | Map count | Under new value? | Referenced by any code? |
|---|---:|---:|---:|---|---|
| `MAX_MAP_MODELS` | 0x400 (1,024) | 0x1000 (4,096) | 109 | yes | **no** |
| `MAX_MAP_BRUSHES` | 0x8000 (32,768) | 0x20000 (131,072) | 1,302,559 | **no, 9.9x over** | **no** |
| `MAX_MAP_ENTITIES` | 0x800 (2,048) | 0x2000 (8,192) | 4,134 | yes | **no** |
| `MAX_MAP_ENTSTRING` | 0x40000 (262,144) | 0x100000 (1,048,576) | 761,260 B | yes | **no** |
| `MAX_MAP_SHADERS` | 0x400 | 0x1000 (4,096) | 291 | yes | **no** |
| `MAX_MAP_AREAS` | 0x100 | 0x400 (1,024) | 1 | yes | **no** |
| `MAX_MAP_FOGS` | 0x100 | 0x400 | 1 | yes | **no** |
| `MAX_MAP_PLANES` | 0x20000 (131,072) | 0x80000 (524,288) | 17,745,374 | **no, 33.8x over** | **no** |
| `MAX_MAP_NODES` | 0x20000 | 0x80000 | 5,323 | yes | **no** |
| `MAX_MAP_BRUSHSIDES` | 0x20000 (131,072) | 0x80000 (524,288) | 16,371,182 | **no, 31.2x over** | **no** |
| `MAX_MAP_LEAFS` | 0x20000 | 0x80000 | 5,433 | yes | **no** |
| `MAX_MAP_LEAFFACES` | 0x20000 | 0x80000 | 46,011 | yes | **no** |
| `MAX_MAP_LEAFBRUSHES` | 0x40000 (262,144) | 0x100000 (1,048,576) | 1,553,593 | **no, 1.48x over** | **no** |
| `MAX_MAP_PORTALS` | 0x20000 | 0x80000 | not in BSP | - | **no** |
| `MAX_MAP_LIGHTING` | 0x800000 | 0x2000000 (32 MB) | 2.2 MB | yes | **no** |
| `MAX_MAP_LIGHTGRID` | 65,535 | 262,140 | 8,085 | yes | **no** |
| `MAX_MAP_LIGHTGRID_ARRAY` | 0x100000 (1,048,576) | 0x400000 | 1,006,400 | yes | **no** |
| `MAX_MAP_VISIBILITY` | 0x600000 | 0x1800000 | 512,520 B | yes | **no** |
| `MAX_MAP_DRAW_SURFS` | 0x20000 (131,072) | 0x80000 | 28,999 | yes | **no** |
| `MAX_MAP_DRAW_VERTS` | 0x80000 (524,288) | 0x200000 (2,097,152) | 2,207,164 | **no, 1.05x over** | **no** |
| `MAX_MAP_DRAW_INDEXES` | 0x80000 (524,288) | 0x200000 (2,097,152) | 1,513,755 stored | yes | **no** |

**Key finding:** none of the 21 `qfiles.h` `MAX_MAP_*` constants is referenced anywhere in the repository (grep over all `.c/.cpp/.h`; the only hits for `MAX_MAP_BRUSHES` and `MAX_MAP_BRUSHSIDES` are the definitions). They are map-compiler limits carried in the header. The engine sizes every lump from `filelen / sizeof` (`qcommon/cm_load.cpp`, `rd-vulkan/tr_bsp.cpp`). The x4 edit to `qfiles.h` therefore changes **no** runtime behaviour, and the five rows where the map exceeds the new value are not a load problem. Raising `MAX_MAP_LIGHTGRID` above 65,535 also cannot be honoured by the file format: the grid index array is `unsigned short` (`rd-vulkan/tr_bsp.cpp:2172`).

The only effective part of the commit is `MAX_MAP_AREA_BYTES`:

| Define | File:line | Before | After | Users | Map |
|---|---|---:|---:|---|---|
| `MAX_MAP_AREA_BYTES` | `qcommon/q_shared.h:222` | 32 (256 areas) | 128 (1,024 areas) | `snapshot_t.areamask` `cgame/cg_public.h:48`; `clSnapshot_t.areamask` `client/client.h:56`; `refdef_t.areamask` `rd-common/tr_types.h:325`; renderer `trRefdef_t` `rd-vulkan/tr_local.h:758`, `rd-vanilla/tr_local.h:547`, `rd-dedicated/tr_local.h:512`; `clientSnapshot_t.areabits` `server/server.h:101`; loops `server/sv_snapshot.cpp:721`, `rd-vulkan/tr_scene.cpp:497`, `rd-vanilla/tr_scene.cpp:424` | 1 area: 1 byte used |

Side effect: it changes the layout of `snapshot_t` and `refdef_t`, which are shared with cgame and the renderer DLLs. Engine, cgame and renderer must all be built from this tree; a stock cgame or renderer binary is ABI-incompatible. The wire format is unaffected (the server sends `areabytes` then that many bytes, `sv_snapshot.cpp:260-261`; the client checks `len > sizeof(areamask)`, `client/cl_parse.cpp:290`).

Two earlier fork commits also changed limits:

| Commit | Change |
|---|---|
| `36a276555` "Increased limits" | `GENTITYNUM_BITS 10 -> 11` (`q_shared.h`), `MAX_SNAPSHOT_ENTITIES 256 -> 512`, `MAX_RELIABLE_COMMANDS 256 -> 512` (`qcommon.h`) |
| `da16eda32` "Update qcommon.h" | `MAX_RELIABLE_COMMANDS 512 -> 256` |

---

## 2. Limit table

### 2.1 Clients, entities, networking

| Limit | File:line | This fork | Stock OpenJK | Main users | Need for this map / 26 bots | OK? |
|---|---|---:|---:|---|---|---|
| `MAX_CLIENTS` | `qcommon/q_shared.h:899` | 32 | 32 (unchanged since import) | 582 refs in 75 files; `sv_maxclients` clamp `server/sv_init.cpp:245-252` | 26 bots + humans | yes, up to 6 humans |
| `sv_maxclients` (runtime cvar, `CVAR_LATCH`) | `server/sv_init.cpp:984` | default `"8"` | 8 | `svs.clients`, snapshot pool | must be set to at least 27 before the map loads | **must be raised** |
| `GENTITYNUM_BITS` | `qcommon/q_shared.h:908` | 11 | 10 **(diff, `36a276555`)** | 73 refs: `qcommon/msg.cpp` entity/playerstate netfields | - | changes the network protocol; server and client must be this build |
| `MAX_GENTITIES` | `qcommon/q_shared.h:909` | 2,048 | 1,024 | 194 refs in 56 files (`g_entities`, `sv.svEntities`, `cl.entityBaselines`, `touchlist` in `sv_world.cpp:539`, `:891`, `saved[]` `game/g_syscalls.c:136`) | about 230 map entities + 32 client slots + transient | yes |
| `ENTITYNUM_NONE` / `ENTITYNUM_WORLD` | `q_shared.h:927-928` | 2047 / 2046 | 1023 / 1022 | everywhere | - | any hard-coded 1023/1022 would now be wrong; not audited |
| `MAX_LOGICENTITIES` | `q_shared.h:905` | 3,072 | fork addition (`16f914f5f`) | game only | not used by the BSP entity count as far as checked | - |
| `MAX_MODELS` | `q_shared.h:933` | 512 | 512 (unchanged since import) | `G_ModelIndex` `game/g_utils.c:150`, `CS_MODELS` range `game/bg_public.h:132-133` | Server-registered models only: 101 door `model2`, 7 breakables, player/weapon/item precache. Inline `*N` brush models and `misc_model_static` do **not** use it. Distinct door `model2` count not measured. | very likely yes; unverified count |
| `MAX_SOUNDS` | `q_shared.h:934` | 256 | 256 (unchanged since import) | `G_SoundIndex` `g_utils.c:161` | 2 speaker sounds + door/mover sounds + game precache | yes |
| `MAX_FX` | `q_shared.h:936` | 64 | 64 (unchanged since import) | `G_EffectIndex` `g_utils.c:171`, `CS_EFFECTS` `bg_public.h:147-148` | 19 map effect files + everything the game registers itself (weapons, force, saber, etc.). Index 0 is reserved, so 63 usable. | **tight; total not measured.** Overflow is an `ERR_DROP` in `G_FindConfigstringIndex`. |
| `MAX_CONFIGSTRINGS` | `q_shared.h:950` | 1,700 | 1,700 (unchanged since import) | 21 refs; compile-time check `CS_MAX <= MAX_CONFIGSTRINGS` `bg_public.h:154-157` | fixed layout | yes |
| `MAX_GAMESTATE_CHARS` | `q_shared.h:959` | 16,000 | 16,000 (unchanged since import) | `client/cl_parse.cpp:590`, `client/cl_cgame.cpp:331` (`ERR_DROP` "MAX_GAMESTATE_CHARS exceeded") | Sum of all configstrings. 26 bots add 26 userinfo strings (a few hundred bytes each) plus model/sound/effect names. | **not measured; this is the classic failure with many clients and many precached assets** |
| `MAX_MSGLEN` | `qcommon/qcommon.h:179` | 49,152 | 49,152 (unchanged since import) | 23 refs; gamestate and snapshot buffers `server/sv_client.cpp:516`, `:553`, `server/sv_snapshot.cpp:970`, `qcommon/net_chan.cpp:163` | Gamestate = configstrings + one baseline per non-empty entity | yes for about 260 entities; not measured |
| `MAX_SNAPSHOT_ENTITIES` | `qcommon/qcommon.h:129` | 512 | 256 **(diff, `36a276555`)** | `server/sv_snapshot.cpp:357`, `:396`; pool size `server/sv_init.cpp:274`, `:280`, `:366`, `:369`; `MAX_PARSE_ENTITIES` `client/client.h:89` | Entities visible to one client: up to about 260 here (PVS removes little) | see mismatch below |
| `MAX_ENTITIES_IN_SNAPSHOT` | `cgame/cg_public.h:35` | 256 | 256 (unchanged since import) | `snapshot_t.entities[]` `cg_public.h:54`; truncation in `CL_GetSnapshot` `client/cl_cgame.cpp:134-136`; `cgame/cg_predict.c:34`, `:36`, `:108` | same | **mismatch:** the engine may send 512 but cgame receives at most 256; the rest are dropped with only a `Com_DPrintf`. With about 26 players + 108 movers + 63 fx_runner + misc in view this map can approach 256. |
| `PACKET_BACKUP` | `qcommon/qcommon.h:119` / `:121` | 128 (client and listen builds) / 32 (`DEDICATED`) | 32 (from memory); the split is fork commit `2d3d0eb7f` | 19 refs; snapshot pool, `cl.snapshots`, `cl.parseEntities` | - | yes |
| `MAX_PARSE_ENTITIES` | `client/client.h:89` | 128 x 512 = 65,536 | 32 x 256 = 8,192 | `cl.parseEntities[]` `client/client.h:151` | - | static array of 65,536 `entityState_t` in the client (tens of MB) |
| Snapshot pool (runtime) | `server/sv_init.cpp:274`, `:280`, alloc `:554` | dedicated: `sv_maxclients x PACKET_BACKUP x 512`; listen: `sv_maxclients x 4 x 512` | x 256 | `svs.snapshotEntities` (`new entityState_s[n]`) | 32 clients dedicated: 524,288 entries; listen: 65,536 entries | large: `entityState_t` is roughly 500 bytes by field count (not compiled), so about 260 MB dedicated, 33 MB listen **(estimate)** |
| `svs.nextSnapshotEntities` wrap | `server/sv_main.cpp:1259-1263`, `server/sv_snapshot.cpp:737-741` | restart at `0x7FFFFFFE - numSnapshotEntities` | same | Counter grows by one per entity per snapshot, **bots included** (`SV_BuildClientSnapshot` runs before the bot early-return, `sv_snapshot.cpp:1016`, `:1035`) | 27 clients x about 150 to 250 entities x 40 snapshots/s = 160K to 270K per second **(estimate)** | **forced map restart ("Restarting server due to numSnapshotEntities wrapping") after roughly 2 to 4 hours on one map (estimate)** |
| `MAX_RELIABLE_COMMANDS` | `qcommon/qcommon.h:133` | 256 | 128 (from memory); 256 already carried the "Niksata Edit" tag before `36a276555` | `server/server.h:160`, `client/client.h:217`, `:230`; overflow drop `server/sv_main.cpp:157` | per client 256 x 1,024 B = 262 KB (x3 arrays on the client) | yes; must be a power of two (masking with `MAX_RELIABLE_COMMANDS-1`) and it is |
| `MAX_ENT_CLUSTERS` | `server/server.h:41` | 16 | 16 | `SV_LinkEntity` `server/sv_world.cpp:333` | large movers | yes; overflow falls back to `lastCluster` |
| `MAX_TOTAL_ENT_LEAFS` | `server/sv_world.cpp:208` | 128 | 128 | `SV_LinkEntity` `:299-300` | doors/lifts are single small brushes | yes |
| `AREA_DEPTH` / `AREA_NODES` | `server/sv_world.cpp:75-76` | 4 / 64 | 4 / 64 | entity sector tree | 16 leaf sectors of about 11.8K x 10.9K units | works; coarse for a 47K-unit world |
| `MAX_SPAWN_VARS` / `MAX_SPAWN_VARS_CHARS` | `game/bg_public.h:36-37` | 64 / 4,096 | same | `game/g_spawn.c:1056`, `:1261`; `cgame/cg_spawn.c:411` | per entity, not per map | yes (the map loads) |
| `MAX_TOKEN_CHARS` | `qcommon/q_shared.h:180` | 1,024 | same | `COM_Parse`, entity tokens | longest single key/value | yes |
| `MAX_SPAWN_POINTS` | `game/g_client.c:645`, `:677` | 128 | same | spawn selection arrays | 32 | yes |
| `MAX_BOTS` | `game/bg_public.h:1982` | 1,024 | same | bot info list | 26 | yes |

### 2.2 Collision model

| Limit | File:line | This fork | Stock | Users | Map | OK? |
|---|---|---:|---:|---|---|---|
| `MAX_SUBMODELS` | `qcommon/cm_local.h:30` | 512 | 512 (unchanged since import) | `CMod_LoadSubmodels` `cm_load.cpp:145` (`ERR_DROP`); `BOX_MODEL_HANDLE` 511, `CAPSULE_MODEL_HANDLE` 510 (`cm_local.h:31-32`); `CM_ClipHandleToModel` `cm_load.cpp:829-876` | 109 | yes. Effective maximum is 510: handles 510 and 511 are reserved and the check at `:145` does not account for that. |
| `MAX_SUB_BSP` | `q_shared.h:938` | 32 | 32 | `SubBSP[]` `cm_load.cpp:80` | 0 | yes |
| `MAX_PATCH_VERTS` | `cm_load.cpp:519` | 1,024 | 1,024 | `CMod_LoadPatches` stack array `:527`, check `:555` | no patches | n/a |
| `MAX_FACETS` | `qcommon/cm_patch.h:66` | 1,024 | 1,024 | `cm_patch.cpp:991`, `:1059`, `:1105` | no patches | n/a |
| `MAX_PATCH_PLANES` | `qcommon/cm_patch.h:67` | 4,096 | 2,048 (source comment "Was 2048 on vanilla jka", commit `8cd79903c`) | `cm_patch.cpp:411`, `:478`, `:532`, `:1246-1247` | no patches | n/a |
| `MAX_GRID_SIZE` (collision) | `qcommon/cm_patch.h:90` | 129 | 129 | `cm_patch.cpp:985`, `:1176` | no patches | n/a |
| `MAX_POSITION_LEAFS` | `qcommon/cm_trace.cpp:380` | 1,024 | 1,024 | `CM_PositionTest` (not reached for the world model, see COLLISION_AND_NAV_NOTES 1.6) | - | n/a |
| `MAX_MAP_BOUNDS` | `qcommon/cm_polylib.h:44` | 65,535 | 65,535 | `cm_patch.cpp:788-794`, `cm_polylib.cpp` (patch winding code only) | world spans -22,496..24,640 | yes |
| `MAX_WORLD_COORD` / `WORLD_SIZE` | `q_shared.h:54-56` | +-65,536 / 131,072 | same | game/cgame trace lengths | 47,136 wide | yes |
| `cbrush_t.numsides` type | `cm_local.h:71` | `unsigned short` | same | `cm_load.cpp:267` narrows `LittleLong(in->numSides)` unchecked | max 88 sides | yes |
| `cbrush_t.checkcount` type | `cm_local.h:72` vs `clipMap_t.checkcount` `:148` | `unsigned short` vs `int` | same | `cm_trace.cpp:223`, `:662`, `:1019`, `cm_test.cpp:105` | - | **bug: duplicate-test avoidance stops working after 65,535 traces** |
| `Hunk_Alloc(int)` / `Z_Malloc(int)` | `qcommon/z_memman_pc.cpp:823`, `:174` | 2 GiB per allocation | same | every `CMod_Load*` | largest 354.9 MB (planes) | yes; wraps silently above 107.4 M planes or 134.2 M brush sides |
| Hunk / zone size | `z_memman_pc.cpp` | unlimited (`malloc` per block). **`com_hunkmegs` and `com_zonemegs` do not exist in this fork.** | same design in OpenJK MP (from memory) | - | about 687 MB collision + 695 MB cached BSP image during load | needs a 64-bit process and RAM |

### 2.3 Waypoints / bot nav

| Limit | File:line | Value | Stock | Users | Map | OK? |
|---|---|---:|---:|---|---|---|
| `MAX_WPARRAY_SIZE` | `qcommon/q_shared.h:533` | 4,096 | 4,096 (unchanged since import) | 13 refs: `game/ai_wpnav.c:34`, `:392`, `:426`, `:1519`; `server/sv_bot.cpp:45`; `ai_main.c` | no `.wnt`, 0 waypoints | n/a now. A 47K x 43K map cannot be area-covered with 4,096 points. |
| `MAX_NEIGHBOR_SIZE` | `q_shared.h:534` | 32 | 32 | `wpobject_t.neighbors[]`; `CalculatePaths` stop `ai_wpnav.c:1715`. `LoadPathData` does **not** check it (`:2199-2221`). | - | unchecked on load |
| `MAX_NEIGHBOR_LINK_DISTANCE` | `q_shared.h:536` | 128 | 128 | `ai_wpnav.c:1592`, `:1640`; `sv_bot.cpp:101` | - | - |
| `MAX_NODETABLE_SIZE` | `game/ai_main.h:34` | 16,384 | 16,384 | `ai_wpnav.c:39`, `:1025`, `:1078`, `:1119`, `:3094` | - | - |
| Route file size | `ai_wpnav.c:2047`, `:2054`, `:2426` | 524,288 bytes (literal) | same | `LoadPathData`, `SavePathData` | - | a full 4,096-point file can exceed it |
| Auto-path cap | `ai_wpnav.c:3034` | 3,900 (literal) | same | `G_BackwardAttachment` (RMG only) | - | n/a |
| `MAX_SPAWNPOINT_ARRAY` | `ai_wpnav.c:2513` | 64 | same | `BeginAutoPathRoutine` `:3239`, `:3246` write `gSpawnPoints[gSpawnPointNum++]` with **no bound check** | RMG only | n/a |

### 2.4 cgame: `misc_model_static`

| Question | Answer |
|---|---|
| Server entity? | **No.** `SP_misc_model_static` on the server is `G_FreeEntity( ent );` (`game/g_misc.c:439-442`, spawn table `game/g_spawn.c:576`). Each one is allocated by `G_Spawn` and freed immediately during `G_SpawnEntitiesFromString`. They cost no entity slot, no configstring, no snapshot bandwidth and no server collision. |
| Who creates them? | cgame parses the entity string itself: `CG_Init` -> `CG_ParseEntitiesFromString` (`cgame/cg_main.c:3352`, `cgame/cg_spawn.c:441-464`) using `trap->R_GetEntityToken` (renderer copy of the BSP entity lump, `rd-vulkan/tr_bsp.cpp:2290`). `SP_misc_model_static` in cgame: `cg_spawn.c:169-232` (table `:278`). |
| Cap | `MAX_STATIC_MODELS 4000` (`cgame/cg_local.h:2292`), array `cgs.miscStaticModels[]` (`cg_local.h:2421`). `ERR_DROP` "MAX_STATIC_MODELS(%i) hit" at `cg_spawn.c:182-184` and `cg_main.c:317-318` (`CG_MiscEnt`, an engine-pushed variant via `CGVM_MiscEnt` `client/cl_cgameapi.cpp:284`; what triggers it was not traced). Stock OpenJK: 4000 (from memory; line is from commit `b319c52fd`). |
| This map | 3,900 instances: **100 below the cap.** |
| Other hard failures | No `model` key -> `ERR_DROP` (`cg_spawn.c:188-190`). Model fails to load -> `ERR_DROP` (`cg_spawn.c:207-211`). |
| Collision | None from the model itself. Collision for these meshes comes from the baked clip brushes in the BSP. |
| Per-frame cost | `CG_DrawMiscStaticModels` (`cgame/cg_draw.c:11926-11972`, called `:12031`) loops over **all** 3,900 every frame: frustum sphere test, `trap->R_InPVS`, then distance test `VectorLength(diff) - radius <= cg.distanceCull` (`:11967-11968`), then `R_AddRefEntityToScene`. No spatial structure. |
| Related renderer limits | `MAX_REFENTITIES` 2,047 per scene (`rd-common/tr_types.h:30-34`, `REFENTITYNUM_BITS 11`); extra entities are dropped with a developer print (`rd-vulkan/tr_scene.cpp:211-212`). Statics share this budget with players, sabers, effects and movers. `MAX_MOD_KNOWN` 1,024 (`rd-vulkan/tr_local.h:1378`, check `rd-vulkan/tr_model.cpp:179`): 390 unique static MD3s + 108 inline bmodels + world + players, weapons, items. Total not measured. |

### 2.5 Renderer world load (rd-vulkan; rd-vanilla is the same unless noted)

rend2: `codemp/rd-rend2/` holds only `G2_*.cpp` and `tr_init.cpp`; the rest of the renderer is in `shared/rd-rend2/` (`codemp/rd-rend2/CMakeLists.txt:8`). Its loader was only grepped, not read in full:

| rend2 item | File:line | Value |
|---|---|---|
| Default `tr.distanceCull` | `shared/rd-rend2/tr_bsp.cpp:2933` | **12000** (vulkan and vanilla use 6000) |
| `distanceCull` key / `r_distanceCull` override | `shared/rd-rend2/tr_bsp.cpp:2994-2997` | same logic as the other renderers |
| `zFar` | `shared/rd-rend2/tr_main.cpp:877-880` | same clamp formula |
| Trisoup vertex/index cap at load | `shared/rd-rend2/tr_bsp.cpp` | no `SHADER_MAX_VERTEXES` / `SHADER_MAX_INDEXES` check found by grep |
| `MAX_FACE_POINTS` / `MAX_GRID_SIZE` | `shared/rd-rend2/tr_local.h:1748`, `:1751` | 64 / 65 |
| `MAX_MOD_KNOWN` / `MAX_DRAWIMAGES` / `MAX_DRAWSURFS` / `MAX_VBOS` | `shared/rd-rend2/tr_local.h:2278`, `:2291`, `:2295`, `:72` | 1,024 / 2,048 / 65,536 / 4,096 |
| Light-grid index array | `shared/rd-rend2/tr_bsp.cpp:2910` | `unsigned short` |

The table below is rd-vulkan.

| Limit / check | File:line | Value | Map | OK? |
|---|---|---:|---:|---|
| `SHADER_MAX_VERTEXES` | `qcommon/qfiles.h:34` | 1,000 | max 999 verts in one trisoup | yes, by 1. `ParseTriSurf` errors when `numVerts >= 1000` (`rd-vulkan/tr_bsp.cpp:810-812`, `rd-vanilla/tr_bsp.cpp:537-539`). |
| `SHADER_MAX_INDEXES` | `qcommon/qfiles.h:35` | 6,000 | max 5,247 indexes in one trisoup | yes. Check `rd-vulkan/tr_bsp.cpp:813-815`. Also sizes the `tess` arrays (`rd-vulkan/tr_local.h:2095-2111`). |
| `MAX_FACE_POINTS` | `rd-vulkan/tr_local.h:899` | 64 | max 25 | yes (over-limit faces are truncated with a warning, `tr_bsp.cpp:607-610`) |
| `MAX_PATCH_SIZE` / `MAX_GRID_SIZE` | `rd-vulkan/tr_local.h:901-902` | 32 / 65 | no patches | n/a |
| `MAX_LIGHTMAPS` | `rd-vulkan/tr_local.h:1393` | 256 | 44 | yes |
| `MAX_SHADERS` | `rd-vulkan/tr_local.h:136-137` | 16,384 (`1 << 14`) | 291 map shaders | yes |
| `MAX_DRAWIMAGES` | `rd-vulkan/tr_local.h:1392` (vanilla `:882`: 2,048) | 4,096 | not measured | - |
| `MAX_MOD_KNOWN` | `rd-vulkan/tr_local.h:1378` | 1,024 | see 2.4 | not measured |
| `MAX_DRAWSURFS` | `rd-vulkan/tr_local.h:1396` | 65,536 per view | 28,999 world surfaces + one per MD3 surface per visible static + players | can be reached with most of the map in view; overflow is clamped at `rd-vulkan/tr_main.cpp:1655-1656`, surfaces are silently lost. Not measured. |
| `MAX_REFENTITIES` | `rd-common/tr_types.h:34` | 2,047 | up to 3,900 statics | see 2.4 |
| `MAX_VBOS` | `rd-vulkan/tr_local.h:30` | 4,096 | world uses one VBO | yes |
| World VBO size | `rd-vulkan/vk_vbo.cpp:1445-1446`, `:1465-1535` | `int vbo_size`, `int ibo_size` | up to 2.2 M verts x (shader `svarsSize` + 32 B) + 4.66 M indexes x 4 B | fits in `int`; a single buffer of roughly 150 to 300 MB **(estimate)**. `r_vbo` default `"1"` (`rd-vulkan/tr_init.cpp:962`, latched). |
| Light grid | `rd-vulkan/tr_bsp.cpp:2164-2177` | `numGridArrayElements = bounds[0]*bounds[1]*bounds[2]` (`int`), array of `unsigned short` | 1,006,400 entries, 8,085 points | yes. Hard format limit of 65,535 distinct grid points. |
| Surfaces / verts / indexes lumps | `rd-vulkan/tr_bsp.cpp:1644-1656` | sized from the lump, no cap | 28,999 / 2,207,164 / 1,513,755 | yes |
| Entity lump copy | `rd-vulkan/tr_bsp.cpp:2203-2205` | `Hunk_Alloc(filelen + 1)` + `strcpy` | 761 KB | yes |
| `r_maxpolys` / `r_maxpolyverts` (runtime cvars) | `rd-vulkan/tr_init.cpp:223-224`, `:907-908`, clamp `:1087-1088` | 32,000 / 128,000; values above the default are clamped **down** (`Q_min`) | effects/marks only | - |

### 2.6 Draw distance

| Name | Kind | Default | Where | Effect |
|---|---|---|---|---|
| `distanceCull` | worldspawn key | 6000 if the key is absent (`rd-vulkan/tr_bsp.cpp:2199`, `rd-vanilla/tr_bsp.cpp:1896`; 12000 in rend2, `shared/rd-rend2/tr_bsp.cpp:2933`); this map sets **13966** | renderer: `tr_bsp.cpp:2259-2264`; server game: `game/g_spawn.c:1475-1476` | Sets `tr.distanceCull` (renderer) and, separately, the server snapshot cull distance. |
| `r_distanceCull` | cvar, `CVAR_ARCHIVE_ND` | `"0"` | `rd-vulkan/tr_init.cpp:877`, `rd-vanilla/tr_init.cpp:1715`, `rd-rend2/tr_init.cpp:1655` | Non-zero overrides the worldspawn value, **but only inside the `distanceCull` key branch** (`tr_bsp.cpp:2261-2262`). On a map with no `distanceCull` key the cvar is ignored and 6000 is used. Read once at map load. |
| `r_zfar` | - | - | - | **Does not exist** in this tree (no match). |
| `tr.viewParms.zFar` | computed | - | `R_SetFarClip` `rd-vulkan/tr_main.cpp:472-520`, `rd-vanilla/tr_main.cpp:472-475` | `zFar = clamp( 2048, tr.distanceCull * 1.732, distance to farthest corner of the visible bounds )`. For this map: at most 13,966 x 1.732 = 24,189 units. Only feeds the projection matrix (`tr_main.cpp:610-630`) and the sky box size (`tr_sky.cpp:311`, `:762`). |
| `r_znear` | cvar | `"4"`, range 0.001..10 | `rd-vulkan/tr_init.cpp:831-832` | Near plane (`tr_main.cpp:559`). |
| `r_nocull` | cvar, `CVAR_CHEAT` | `"0"` | `rd-vulkan/tr_init.cpp:885`; `tr_main.cpp:62`, `:132`, `:170`; `tr_world.cpp:122`, `:1246-1248` | Disables frustum culling. |
| `r_cullRoofFaces`, `r_roofCullCeilDist` | cvars, `CVAR_CHEAT` | `"0"`, `"256"` | `rd-vulkan/tr_init.cpp:846-847`, `tr_world.cpp:149-222` | Automap helper, not a distance cull. |
| `cg.distanceCull` | cgame variable | `trap->R_GetDistanceCull()` at init (`cgame/cg_main.c:3350`; engine `client/cl_cgameapi.cpp:1782`, renderer `rd-vulkan/tr_init.cpp:1239`) | `cgame/cg_draw.c:11968` | Distance cull for `misc_model_static` (centre distance minus radius). Also crosshair trace length (`cg_draw.c:9312`). |
| `g_cullDistance` / `g_svCullDist` | game global / server global | `"6000.0"` if no key (`g_spawn.c:1475`); server default -1 = off (`server/sv_snapshot.cpp:409`) | `trap->SetServerCull` `g_spawn.c:1476` -> `server/sv_gameapi.cpp:651-653`; test `server/sv_snapshot.cpp:587-601` | Server drops an entity from a client's snapshot when `distance - bbox diagonal >= cullDist`. With 13,966 on a 47K map this is the main thing limiting how many of the 26 bots each client receives. |

Code paths that do **not** use the cull distance: `R_RecursiveWorldNode` culls BSP nodes against the four side frustum planes only (`rd-vulkan/tr_world.cpp:1246-1262`, initial `planeBits` 15 at `:1534`); `frustum[4]` is the near plane (`tr_main.cpp:556-560`). There is no far-plane or distance test for world surfaces on the CPU. Geometry beyond `zFar` is clipped by the GPU after being submitted. With 81 % average cluster visibility, the world surface count per frame is bounded by the view frustum and little else. In rd-vanilla `tr.distanceCull` also sets the fog end (`rd-vanilla/tr_shade.cpp:1593-1607`).

Only the names in this table were searched for. Other possible draw-distance or LOD controls (for example model LOD cvars) were not looked for.

---

## 3. Flagged: unchecked counts, narrow types, overflow

| # | Where | Issue | Hits this map? |
|---|---|---|---|
| 1 | `qcommon/cm_local.h:72` vs `:148`; compare at `cm_trace.cpp:662`, `:223`, `:1019`, `cm_test.cpp:105` | 16-bit `cbrush_t.checkcount` compared with a 32-bit counter. Dedup is dead after 65,535 traces. | **Yes**, always. Costs repeated brush tests for brushes that straddle leaves (1.19 refs per brush on average). |
| 2 | `cgame/cg_public.h:35` (256) vs `qcommon/qcommon.h:129` (512) | Engine snapshot limit was doubled, cgame limit was not. `CL_GetSnapshot` silently truncates (`client/cl_cgame.cpp:134-136`). | Possible when more than 256 entities are in a client's snapshot. |
| 3 | `server/sv_main.cpp:1259-1263` | `nextSnapshotEntities` approaches 2^31 faster with 512-entity snapshots and 26 bot snapshots per frame; the server restarts the map. | Yes, after hours on one map (estimate in 2.1). |
| 4 | `cgame/cg_local.h:2292` | `MAX_STATIC_MODELS 4000` vs 3,900 instances: 100 spare, `ERR_DROP` on overflow. | Close. |
| 5 | `qcommon/q_shared.h:936` | `MAX_FX 64` with 19 map effects plus all game-registered effects. | Not measured. |
| 6 | `qcommon/q_shared.h:959` | `MAX_GAMESTATE_CHARS 16000` with 27+ client userinfo strings. | Not measured. |
| 7 | `qcommon/qfiles.h:34` | `SHADER_MAX_VERTEXES 1000` vs 999-vertex trisoups; test is `>=`. | Passes by exactly one vertex (q3map2 `-meta` cap). |
| 8 | `qcommon/z_memman_pc.cpp:174`, `:823` | `int` size parameters; callers pass `size_t` products with no range check. | No (max 355 MB). |
| 9 | `qcommon/cm_load.cpp:267` | `numsides` narrowed from 32-bit to `unsigned short`, unchecked. | No (max 88). |
| 10 | `qcommon/cm_load.cpp:215`, `:266`, `:308-311`, `:386-387`, `:443-444` | Plane, side, brush and leaf-brush indexes from the file are used without bounds checks (only `shaderNum` is validated, `:270`, `:446`). | Not a size issue; a damaged file would corrupt memory instead of erroring. |
| 11 | `qcommon/cm_load.cpp:231-240` | `CM_BoundBrush` assumes at least six sides with the axial planes first. | No. |
| 12 | `qcommon/cm_load.cpp:480-482` | BSP entity lump copied into exactly `filelen` bytes; termination depends on the lump's own trailing NUL. `Hunk_Alloc` zero-fills but adds no spare byte. | No, as long as q3map2 wrote the NUL. |
| 13 | `qcommon/cm_load.cpp:145` | `MAX_SUBMODELS` check ignores the two reserved handles (510, 511) and runs after the allocation. | No (109). |
| 14 | `rd-vulkan/tr_bsp.cpp:2172` | Light-grid index array is `unsigned short`; `MAX_MAP_LIGHTGRID 262140` in `qfiles.h` is not representable. | No (8,085). |
| 15 | `rd-vulkan/tr_bsp.cpp:2261-2262` (same in vanilla `:1958-1959`) | `r_distanceCull` only applies when the map has a `distanceCull` key. | Map has the key, so the cvar works here. |
| 16 | `game/ai_wpnav.c:2110-2238` | `.wnt` parser: no bounds on `currentVar[2048]`, on `i < len` in inner loops, or on `neighbornum` (32). | Only if a route file is added. |
| 17 | `game/ai_wpnav.c:3239`, `:3246` | `gSpawnPoints[64]` filled without a bound check. | RMG only. |
| 18 | `qcommon/common.cpp:1885-1886`, `cm_trace.cpp` | `c_brush_traces` is printed by `com_showtrace` but never incremented. | Always prints 0. |
| 19 | `qcommon/z_memman_pc.cpp:725-727` | `Hunk_MemoryRemaining` returns `64 MB - hunk usage`, negative on this map. Callers not audited. | Yes (value is negative). |

Wrong printf format specifiers: none found in the files read for this note (`cm_load.cpp`, `cm_test.cpp`, `cm_trace.cpp`, `sv_world.cpp`, the print calls in `rd-vulkan/tr_bsp.cpp`, `ai_wpnav.c` trace-related code). A repo-wide format audit was not done.

Not found / not verified, stated explicitly:

* `com_hunkmegs`, `com_zonemegs`, `r_zfar`: not present in this tree.
* Stock OpenJK values marked "from memory" were not checked against an OpenJK checkout.
* `sizeof(entityState_t)` and the struct sizes in COLLISION_AND_NAV_NOTES.md were derived from declarations, not compiled.
* Totals of game-registered effects, models, images and the gamestate size for this map were not measured; they need a running server (`configstrings` / a debug print).
* Whether botlib copies the entity string into a fixed buffer (`BotImport_BSPEntityData`, `server/sv_bot.cpp:398`) was not traced.
* Code that may hard-code 1024 / 1023 / 10-bit entity numbers after the `GENTITYNUM_BITS` change was not audited.
