# WORLD_FORMAT — `maps/<name>.tworld`

> **Later state:** this document describes the first prototype (file version 1, one region). Corrected materials,
> file version 2, detail levels, the whole-city export and its benchmark are in `UPDATE_city_v2.md`;
> whole-city collision, spawns and the bot test are in `UPDATE_city_collision.md`.

State: **file version 1 = prototype "v0"** of the design in `ARCHITECTURE.md` section 4. It exists to get the scene
on screen and measure; it will change. Writer: `..\tools\cook_v0.py`. Reader: `codemp/rd-vulkan/tr_tworld.cpp`
(branch `naboo-theed`, commit `d555f9291`).

## Layout (little-endian, packed, sections in this order with no padding)

| Section | Count | Record |
|---|---|---|
| Header (88 bytes) | 1 | `char magic[4]` = "TWLD"; `u32 version` = 1; `u32 numMaterials, numMeshes, numSubmeshes, numInstances, numVerts, numIndexes`; `float mins[3], maxs[3]` (world bounds, engine units); `float unitsPerMetre`; `u32 reserved[7]` |
| Materials | numMaterials | `char shader[64]`: name of an ordinary engine shader |
| Meshes (40 bytes) | numMeshes | `u32 firstVert, numVerts, firstIndex, numIndexes, firstSub, numSubs`; `float center[3], radius` (local bounding sphere) |
| Submeshes (16 bytes) | numSubmeshes | `u32 material`; `u32 firstIndex` (relative to the mesh's first index); `u32 numIndexes`; `u32 reserved` |
| Instances (68 bytes) | numInstances | `u32 mesh`; `float m[12]` row-major 3x4, world = m * (x, y, z, 1); `float center[3], radius` (world bounding sphere) |
| Vertices (32 bytes) | numVerts | `float xyz[3]` (mesh-local, engine units); `float normal[3]`; `float st[2]` (V already flipped for the engine) |
| Indexes | numIndexes | `u32`, relative to the mesh's first vertex; triangles grouped by submesh |

The file size must equal exactly the sum implied by the header counts; the loader rejects the file otherwise and
validates every mesh, submesh, index and instance reference before creating any GPU buffer.

## Materials in v0

Not stored in the file. The cooker writes a normal shader script (`shaders/naboo_<map>.shader`) and PNG textures
(`textures/naboo/*.png`), and the file only names the shaders. Each generated shader is one stage:
`map <base colour>` (or `$whiteimage` with `rgbGen const`), `rgbGen identity`, `cull none`, and `alphaFunc GE128`
for cut-out materials. Blender materials that would look the same in v0 (same base-colour image and class) are
merged: 801 materials in the prototype region became 62 shaders.

## What v0 does not have (and the design does)

Section table and per-section checksums; LOD chains; tangents, vertex colour and second UV set; packed normals;
cluster grid; far-scenery section; lights; environment block; probe grid; materials with normal/roughness maps;
compressed textures (DDS); blended materials (their triangles are dropped by the cooker).

## Measured on the prototype region

| | Value |
|---|---:|
| File size | 87.0 MB (83.0 MiB) |
| Meshes / submeshes / instances / shaders | 326 / 658 / 2,575 / 62 |
| Vertices after welding face corners | 2,144,595 (from 4,437,543 face corners) |
| Triangles: unique / as placed | 1,516,509 / 6,154,255 |
| Draw calls if everything is visible | 3,743 |
| Triangles dropped (blended materials) | 7,074 |
| Cook time (Python) | under a minute (see `export\proto\cook_v0_naboo_proto.json`) |
| Load time in the engine | 2.6-3.0 s (read, validate, 326 vertex + index buffers) |
