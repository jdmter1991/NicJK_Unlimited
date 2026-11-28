
## 5. Libraries considered for the cooker

Checked on the projects' GitHub pages on 2026-11-24. The pages did not show the date of the latest commit, and several
release dates were shown without a year; those cells say so. Nothing was downloaded.

| Library | Purpose | Licence (as shown) | Latest release | State | Usable as a small library? |
|---|---|---|---|---|---|
| zeux/meshoptimizer | simplification with error output, vertex-cache/overdraw optimisation, meshlets, buffer compression | MIT | v1.3, 25 Sep (year not shown) | active (4,295 commits) | yes: one header + C++ sources, add only what is used |
| richgel999/bc7enc_rdo | BC1-BC7 encoder | MIT or Unlicense (the bundled `bc7e.ispc` is Apache-2.0) | no releases | not archived | yes: drop-in .cpp files |
| microsoft/DirectXTex (`texconv`) | BC1-BC7 encode, DDS read/write, mip generation | MIT | "may2026", 8 May 2026 | active | library and command-line tool. GPU BC7 encoding was not confirmed from the page |
| GPUOpen-Tools/compressonator | BC1-BC7, CLI and SDK | MIT-style text in `license/license.txt` (sub-licence files not read) | V4.6.0, 20 Oct (year not shown) | not archived | both |
| GameTechDev/ISPCTextureCompressor | BC7 encoder | MIT | none | **archived 23 Sep 2024, discontinued** | not recommended |
| BinomialLLC/basis_universal | supercompressed textures, UASTC -> BC7 | Apache-2.0 | v2.50 | active | yes, but adds a transcode step at load |
| KhronosGroup/KTX-Software | KTX2 container | **not determined** (licence page failed to load twice) | v4.4.2 | active | yes |
| recastnavigation/recastnavigation | navmesh generation and path queries | Zlib | 1.6.0 | active | yes, dependency-free C++ |
| kmammou/v-hacd | convex decomposition | BSD-3-Clause | v4.1.0 | README says deprecated and archived | header-only; no longer maintained |
| SarahWeiii/CoACD | convex decomposition | MIT | 1.0.14 | active | library, CLI and pip package |
| jkuhlmann/cgltf | glTF reader | MIT | v1.15 | active | single header |
| syoyo/tinygltf | glTF reader/writer | MIT | v3.1.0, 7 Nov 2026 | active | small C sources |

All licences in the table except the undetermined KTX one are compatible with distributing a GPLv2 engine or a
separate tool (MIT, BSD, Zlib, Unlicense; Apache-2.0 is compatible with GPLv3 but **not with GPLv2-only**, which
matters only for code linked into the engine, not for an offline cooker). The cooker is a separate program, so the
engine itself needs no new third-party code if the cooked format is simple (raw vertex/index sections, standard
BC blocks).

Choices these facts support: meshoptimizer for LOD generation and index/vertex ordering; BC7/BC5/BC1 written by a
maintained encoder (DirectXTex `texconv` as a tool, or bc7enc_rdo as source) into a container the engine reads
directly; Recast only if trace-based bot navigation proves insufficient; CoACD rather than V-HACD if convex
decomposition is needed for collision.
