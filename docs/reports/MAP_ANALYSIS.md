# MAP_ANALYSIS — `swtor_korriban`

Source: `GameData\taystjk\zz_swtor_korriban.pk3` (588,127,850 bytes, 3,156 entries, all CRCs OK).
Working copy of the BSP/shader/arena/effects: `korriban_extracted\` (original PK3 untouched).
Everything below was measured from the actual BSP with the scripts in `tools\`
(`pk3_list.py`, `bsp_stats.py`, `bsp_ents.py`, `bsp_tracesim.py`). Nothing here is a runtime measurement.

## 1. PK3 contents

| Type | Files | Uncompressed | Notes |
|---|---:|---:|---|
| `maps/swtor_korriban.bsp` | 1 | 695,499,120 | RBSP version 1 (standard JKA format) |
| `textures/sw_korriban/*.png` | 502 (+6 env, +1 levelshot) | 296 MB | up to ~6 MB per PNG |
| `models/sw/**/*.md3` | 2,601 | 67.5 MB | 390 are referenced by `misc_model_static` |
| `sound/sw/*.wav` | 3 | 6.6 MB | music + 2 ambient |
| `shaders/swmap_korriban.shader` | 1 | 195 KB | |
| `effects/sw_korriban/*.efx` | 40 | 37 KB | 19 used by `fx_runner` |
| `scripts/swtor_korriban.arena` | 1 | 106 B | `ffa holocron jedimaster duel powerduel team` |

**There is no `botroutes/swtor_korriban.wnt`** in the PK3 and no `botroutes` folder in the installation.
The map ships without bot waypoints.

Compiler (from worldspawn): q3map2 `2.5.17n-git-6b0b4b1f`, `-bsp -meta -patchmeta -patchbothsides; -vis -saveprt -fast; -light -fast -filter -patchshadows`,
`_blocksize 2048 2048 0`, `gridsize 320 320 368`, `distanceCull 13966`, fog `fogparms (0.415 0.268 0.181) 13966.227`.

## 2. BSP lumps: reported vs verified

| Item | Compile report | Verified in BSP | Lump bytes |
|---|---:|---:|---:|
| Planes | 17,745,374 | 17,745,374 (3,694,480 axial; 10,298,036 referenced by brush sides) | 283.9 MB |
| Brushes | 1,302,559 | 1,302,559 (1,302,451 world + 108 in submodels) | 15.6 MB |
| **Brush sides** | **24,556,773** | **16,371,182** | 196.5 MB |
| Draw vertices | 2,207,164 | 2,207,164 | 176.6 MB |
| Draw indexes / triangles | 504,585 tris | 1,513,755 indexes = 504,585 tris | 6.1 MB |
| Surfaces | 28,999 | 28,999 (20,055 planar, 8,944 trisoup; 28,993 in world) | 4.3 MB |
| Shaders | 291 | 291 | |
| Nodes / leaves | 5,323 / 5,433 | 5,323 / 5,433 | |
| Leaf-brush refs | — | 1,553,593 | 6.2 MB |
| Leaf-surface refs | — | 46,011 | |
| Brush models | 109 | 109 (world + 101 doors + 7 trains) | |
| Vis clusters / data | 2,002 / 500 KB | 2,002 clusters x 256 bytes = 512,512 B | |
| Lightmaps | 44 | 44 | 2.2 MB |
| Light grid | 8,085 unique / 1,006,400 points | 8,085 x 30 B / 1,006,400 x 2 B index array | 2.3 MB |
| Entity text | 743 KB | 761,260 B (743.4 KiB) | |
| Fogs | — | 1 | |

Differences from the report:

* **Brush sides are 16.37 M, not 24.56 M.** The file physically contains 196,454,184 bytes of 12-byte sides.
  The compile report figure is not what is stored.
* The "2.2 M vertices / 504 K triangles" pair is consistent: the surface headers sum to 4,661,517 indexes,
  but the index lump holds 1,513,755, so surfaces share index ranges (the compiler deduplicated identical
  index runs; the reason was not investigated). The renderer therefore draws up to ~1.55 M triangles
  (4.66 M indexes) from 29 K surfaces, while the "504,585 triangles" figure is only the stored index count / 3.
* All other reported counts match the BSP exactly.

World bounds: (-22496, -20992, -9712) to (24640, 22464, 7848) — **47,136 x 43,456 x 17,560 units**.

## 3. Collision representation (the important part)

| Measurement | Value |
|---|---:|
| Brushes with shader `sw_korriban/floorclip` | 706,504 |
| Brushes with shader `sw_korriban/collision` (`q3map_clipModel`) | 593,066 |
| All other brushes (hint, caulk, doorclip, structural) | 2,989 |
| Sides per brush | mean 12.6, median 13, max 88 |
| Brush bounding box | median ~41 x 41 x 38 units, p99 ~559 x 559 x 654 |
| BSP leaves | 5,433 (2,111 with a vis cluster) |
| Leaf depth | 3 – 68, average 29.7 |
| Leaf largest extent | median 2,048 units, p90 17,544 units |
| Brushes per leaf (leaves with a cluster) | mean 728, median 99, p90 2,303, p99 7,917, **max 22,182** |
| Brush sides reachable from one leaf | p90 5,091, p99 74,844, **max 312,520** |
| Leaves referencing one brush | mean 1.2, max 1,562 |

99.8 % of the collision is a convex decomposition of the visual meshes into ~1.3 M small clip brushes
(about 40 units across). These are detail-like brushes that do not split the BSP, so the tree stays tiny
(5.4 K leaves for a 47 K-unit world, mostly split only by the 2048-unit `_blocksize` grid) and each leaf
is a bucket holding hundreds to tens of thousands of small brushes.

The stock Quake 3 / OpenJK collision code walks every brush reference of every leaf a trace touches.
`tools\bsp_tracesim.py` emulates that leaf selection for traces started at the 32 spawn points
(8 horizontal directions each):

| Typical bot trace | Leaves touched (mean) | Leaf-brush entries walked (mean / p90 / max) | Brushes actually overlapping the trace AABB (mean / p90 / max) |
|---|---:|---:|---:|
| Ground check, 64 units down | 1.0 | 3,557 / 7,352 / 10,310 | 7.0 / 13 / 27 |
| Movement probe, 48 units, player box | 1.1 | 3,820 / 7,619 / 10,310 | 1.1 / 4 / 8 |
| Visibility ray, 512 units | 1.9 | 4,876 / 8,708 / 18,967 | 12.4 / 32 / 139 |
| Visibility ray, 2,048 units | 4.7 | 9,785 / 15,010 / 27,514 | 83 / 230 / 829 |
| Visibility ray, 8,192 units | 14.5 | 27,183 / 46,782 / 61,401 | 301 / 877 / 1,630 |

Brushes in the leaf containing each spawn point: min 187, median 3,284, mean 3,557, max 10,310.

**Reading:** a short trace visits roughly 3,500–5,000 brush records to find the 1–12 that are near it:
a 400x–3,000x overhead per trace that is independent of what the trace is for. Every player move
(several traces per `Pmove`), every bot line-of-sight check, every ground check pays it.
This is a property of the map's collision layout, and it is what makes per-bot trace counts matter so much here.
Whether it dominates the server frame has to be confirmed by runtime profiling (see `PERFORMANCE_DIAGNOSIS.md`).

## 4. Visibility

2,002 clusters, 256 bytes per cluster row. Clusters visible from a cluster: mean 1,629 (**81 %**), median 1,642,
p90 1,977, max 2,002. Compiled with `-vis -fast`. PVS removes about a fifth of the map on average, so:

* the renderer relies on frustum culling and the 13,966-unit `distanceCull`, not on PVS;
* server snapshot culling (`SV_AddEntitiesVisibleFromPoint`) will consider most players/bots mutually visible;
* any AI code that uses `trap->InPVS` as a cheap pre-filter before a trace gets almost no rejection here.

Areas: 1 (no area portals), so doors do not block visibility or sound areas.

## 5. Entities (4,134 total, 761 KB of text)

| Class | Count | Server entity? |
|---|---:|---|
| `misc_model_static` | 3,900 (390 unique models) | see ENGINE_LIMITS — handled client-side in JKA-derived code |
| `func_door` | 101 (each one brush + an MD3 `model2`) | yes, mover |
| `fx_runner` | 63 (19 effect files, `delay 5000`) | yes |
| `info_player_deathmatch` / `info_player_start` | 31 / 1 | spawn spots |
| `path_corner` | 18 | yes |
| `func_train` | 7 (6 lifts, 1 taxi) | yes, mover |
| `misc_model_breakable` | 7 | yes |
| `target_speaker` | 5 (2 sounds) | yes |

No items, weapons, ammo, holocrons, triggers, NPC spawners, jump pads, teleporters or `info_location`.
No `trigger_hurt` / lava / water brushes: contents are only SOLID (plus 4 PLAYERCLIP and 374 hint).
Consequences for bots: there are no item goals at all, so every "go get item/weapon" branch of the AI has
nothing to pick; with no waypoints either, roaming logic has no graph to follow on this map.

All 108 brush entities have exactly one brush each (door/lift clip), so moving-brush collision is cheap.

## 6. Rendering-relevant facts

* 28,999 surfaces, 8,944 of them trisoups carrying 2.12 M of the 2.21 M vertices (max 999 verts/surface — q3map2 `-meta` limit).
* 291 shaders, 44 lightmaps, 1 global fog volume, `distanceCull 13966` matching the fog distance.
* 3,900 static model instances over 390 MD3s on top of the BSP surfaces.
* 296 MB of PNG textures (uncompressed PNG size; GPU footprint depends on resolution and mip chain).
