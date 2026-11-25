# ASSET_PIPELINE — from the .blend to engine files

> **Later state:** this document describes the first prototype (file version 1, one region). Corrected materials,
> file version 2, detail levels, the whole-city export and its benchmark are in `UPDATE_city_v2.md`;
> whole-city collision, spawns and the bot test are in `UPDATE_city_collision.md`.

State: prototype (roadmap steps 1-2). One region has been exported and its collision compiled and run on the
server. No visual data reaches the engine yet. All numbers below were measured on 2026-11-24 on the prototype region.

## Settings (`..\tools\naboo_config.json`)

| Setting | Value | Status |
|---|---|---|
| `units_per_metre` | 39.37 | **provisional**; could not be judged yet because the map has no visuals (see `TODO.md`) |
| `origin_m` | (680, -50, 436) | scene point that becomes the engine origin |
| region `proto` | centre (700, 50) m, half-size 75 m (150 x 150 m of main street) | - |
| collision rules | name exclusions, box below 1.2 m, skip below 0.35 m, decimate to 20 % (200-3,000 triangles), terrain every 2 m | first guess, too fine (see below) |

Axes: Blender and the engine are both Z-up and right-handed; the transform is `engine = (blender - origin) * units_per_metre`.

## Step 1: export from Blender

```
blender -b --factory-startup --disable-autoexec Naboo_Theed.blend --python tools\export_region.py --
        tools\naboo_config.json proto export\proto  [dump] [collision] [spawns] [textures] [gltf]
```

Selection: mesh objects visible in the view layer whose bounding-box centre lies in the region, excluding objects
200 m or larger; the near terrain is cropped separately as a grid. Prototype region: **2,729 objects using 335
meshes**.

### Intermediate format test (direct dump vs glTF)

| | Direct dump (`dump\`) | glTF (`region.glb`) |
|---|---|---|
| Export time | 19.0 s geometry + 9.7 s for 55 base-colour textures | 286.9 s |
| Size | 189 MB geometry (uncompressed .npz) + 126 MB PNG | 504 MB (103 MB geometry + 400 MB of 366 PNG images) |
| Instancing kept | yes: 335 meshes, 2,729 placements with matrices | yes: 342 meshes, 2,729 nodes |
| Geometry | 1,479,181 unique triangles (6,148,767 as placed), 4,437,543 face corners, positions, split normals, 2 UV sets, vertex colour, per-triangle material | positions, normals, up to 3 UV sets, 2 colour sets; 841 primitives |
| Materials | 801; class: 592 opaque, 175 cut-out, 34 blended; base-colour image found for 753 (55 distinct images); shader family (`builder`) and game shader name kept | 808; base-colour texture on 762, normal texture on 767; alpha mode 646 opaque, 140 blend, 22 mask; **custom properties not exported** (no `extras`) |
| Reader needed in the cooker | numpy-style arrays, trivial | a glTF library (cgltf or tinygltf) |

**Decision: the direct dump is the intermediate format.** It is 15 times faster, keeps the shader-family metadata
the material translation needs, and classifies cut-out materials the way the scene does (the glTF exporter marked
140 materials as blended and only 22 as alpha-tested, which would put most vegetation in the slow blended path).
glTF stays useful as a cross-check: it found a base-colour texture for 9 more materials than the dump's simple
graph walk, so that walk has a small gap to close, and a .glb can be opened in any viewer.

Layout of `dump\`: `meshes\NNNN.npz` (arrays `pos`, `tri_verts`, `tri_loops`, `tri_mat`, `loop_vert`, `loop_normal`,
`uv0`, `uv1`, `color`), `meshes\terrain_crop.npz`, `scene.json` (mesh table, instance list with 4x4 matrices,
collection, `blueprint`), `materials.json`, `textures\*.png`. Units are metres; scaling happens in the cooker.

Extrapolation (arithmetic, not measured): the region holds 12.5 % of the scene's placed triangles, so a whole-map
dump should take a few minutes and roughly 1.5 GB of geometry before cooking.

## Step 2: collision export and BSP

Inside the same Blender run (`collision` step), per unique mesh:

1. keep only triangles whose material is opaque (drops leaves, flowers, curtains, decals);
2. skip objects by name (`nocollision`, `decal`, `leak`, effects, ...) and objects under 0.35 m;
3. meshes under 1.2 m become their bounding box;
4. other meshes are decimated with Blender's Decimate modifier on a temporary in-memory copy;
5. placements are applied, the terrain crop is added, everything is converted to engine units and written as
   `collision\collision_tris.npy`.

| Measure (prototype region) | Value |
|---|---:|
| Objects in / skipped by name / too small / no opaque triangles | 2,729 / 122 / 83 / 776 |
| Boxed / decimated / kept as is | 501 / 860 / 387 |
| Source triangles as placed -> opaque only | 5,961,409 -> 3,755,189 |
| Collision triangles out (objects + terrain) | 552,860 + 11,552 = 564,001 after dropping 411 degenerate |
| Time | 168 s |
| Median triangle area | 19 square units (about 6 x 6 units): far finer than collision needs |
| Triangles thinner than 1 unit | 52,743 |

Then `py tools\build_collision_bsp.py export\proto naboo_proto`:

* writes 61 OBJ chunks (1,024-unit cells, at most 20,000 triangles each) to `q3base\base\models\naboo_col\`,
  shaders `textures/naboo_sys/col` and `hull` (nodraw, solid), and `q3base\base\maps\naboo_proto.map` with a
  6-brush hull, `_blocksize 1024 1024 0`, one `misc_model` (spawnflags 2) per chunk and the spawn entities;
* runs the existing `q3map2.exe -game ja -fs_basepath naboo\q3base -meta` (BSP stage only).

| Result | Value |
|---|---:|
| Compile time | 408 s |
| Output | `naboo_proto.bsp`, 180.6 MB, RBSP version 1 |
| Brushes / sides / planes | 436,293 / 5,832,001 / 6,472,500 (13.4 sides per brush) |
| Nodes / leaves | 451 / 453; up to 26,019 brushes in one leaf |
| Triangles that did not become brushes | 127,708 of 564,001 (23 %); the q3map2 log gives no reason. Thin and tiny triangles are the likely cause; **whether this leaves holes was not checked** |
| "Entity leaked" | reported and irrelevant here (no vis or light stage) |

Findings:

* **This q3map2 build reads OBJ as Y-up**: a first compile put every brush at (x, -z, y). The trace simulation
  caught it (spawn points sat in empty leaves). The script now writes vertices as (x, z, -y), and the second compile
  has brushes where the triangles are. Any other model route (ASE, MD3) must be checked the same way.
* `.map` texture names must not carry the `textures/` prefix.
* As predicted in `RESEARCH.md` 3.2, the tree is poor (453 leaves for 436 K brushes); the engine's per-leaf BVH
  makes it usable (see `BENCHMARKS.md`).
* **The collision set is far too dense.** Scaled to the whole map these settings would give about 4.5 M triangles
  and a BSP well over 1 GB. The next iteration must cut it by roughly 5-10x: lower decimation targets, convex
  hulls or boxes for props up to a few metres, and no thin triangles. That is also the argument for the own RBSP
  writer, which can merge coplanar triangles instead of emitting one brush each.

## Spawn candidates (prototype)

`spawns` step: rays cast straight down on a 6 m grid against the visual scene; a point is kept when the surface
is nearly level (normal z above 0.94), there is 3 m of headroom and 1.5 m of horizontal clearance at three heights.
576 grid points gave 189 candidates in 89 s. `build_collision_bsp.py` keeps those within 12 m of the median height
(street level) and picks 24 by farthest-point sampling, facing the region centre, 40 units above the ground. All
24 were checked against the collision triangles: ground 35.6-40.3 units below each origin.

## Not built yet

Cooker, `.tworld` writer, texture encoding, LODs, material translation, whole-map export.
