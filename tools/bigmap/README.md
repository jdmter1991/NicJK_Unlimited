# Maps with a .bsp of 2 GB or more

The engine used to read a map's `.bsp` with 32-bit sizes, so a file of 2 GB or more failed to load
(`Z_Malloc(): Failed to alloc -1187956976 bytes (TAG_BSP_DISKIMAGE)`, or "Can't find map").
On the `64bit` branch the map loader uses 64-bit sizes:

- `FS_FOpenFileReadLarge` / `FS_ReadLarge`: 64-bit file length and reads in 256 MB blocks.
- `Z_MallocLarge`: zone blocks of 2 GB or more (block sizes and per-tag totals are 64-bit).
- `Com_BlockChecksumLarge`: the map checksum for 2 GB or more. Below 2 GB it gives the same value as before,
  so old and new builds still agree on normal maps.
- `lump_t` positions and lengths are unsigned, so lumps can start past 2 GB.
- `map` / `devmap` and the map vote find a 2 GB+ `.bsp` (they no longer judge by the 32-bit length).
- A 2 GB+ `.bsp` stays in memory for the renderer even when memory is low (the renderer's own re-read is 32-bit).

## Limits

- **4 GB**: the BSP format stores lump positions in 32 bits, so a `.bsp` must stay under 4 GB.
- **Loose file only**: the pk3 reader has no zip64, so a file of 2 GB or more can't go in a pk3.
  Put the `.bsp` in `<game>/maps/` next to the pk3s; everything else (textures, models) can stay in pk3s.
- **Memory**: the whole `.bsp` is read into memory (about its file size), plus the collision and render data
  built from it. Expect roughly the file size again on top of the usual memory use.

## Test file

`make_big_bsp_test.py` makes a 2 GB+ copy of any map by inserting padding after its header, so the file is over
2 GB and every lump starts past 2 GB:

    py make_big_bsp_test.py ffa3.bsp maps/bigtest.bsp 2.3

Tested 2026-11-27: `mp/ffa3` padded to 2.31 GB (first lump at 2,469,606,404) loads on the dedicated server and in
the client (rd-vulkant) with 31 bots; Naboo Theed (0.9 GB) and `mp/ffa3` still load, and `mp/ffa3`'s map checksum
is the same as before (-576886454).
