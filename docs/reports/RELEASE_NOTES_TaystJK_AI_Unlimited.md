Build of branch `TaystJK_AI_Unlimited` at commit `96eb4ad71` (Windows x64, portable, RelWithDebInfo).

Developed and measured on the `swtor_korriban` map (1.3 million collision brushes, 3,900 static models) with 26 bots.

## Server
- **World collision accelerator.** Leaves holding thousands of small clip brushes are indexed at map load, so a trace only tests the brushes near it. Results are identical to the stock code (500,000 live traces compared, 0 differences); average trace cost went from 84 µs to 3.2 µs. `cm_accel 0` switches it off, `cm_accelVerify 1` compares both paths.
- Korriban with bots, dedicated, `sv_fps 40`: the original build used a whole CPU core at 15 bots; this build runs 26 fighting bots at about 5.5 ms of a 25 ms frame.
- Fixed a random dedicated-server crash in the Windows console code (hidden or redirected console).

## Bot AI
- Enemy scan applies its cheap rules first and traces nearest-first: same target choice, 7.1 → 1.2 line-of-sight traces per think.
- Removed a faulty timeout that made every bot skip thinking and input on about one frame in five.
- Memory-safety fixes: out-of-range entity index in the duel/race trace wrapper, a bot state block leaked on every connect, a null dereference in enemy prediction, two loops running one past the client array.
- `bot_fixes` (bitmask, default 1): 1 = fallback navigation probes the walls beside the bot instead of tracing toward the map origin; 2 = stuck detection per bot instead of shared by all bots (off by default).

## Client (rd-vulkan)
- Render entity limit per frame raised from 2,047 to 4,095. Large scenes with many static models plus players no longer drop models (flickering / disappearing geometry).
- MD3 models whose header bounding box does not contain their vertices are corrected at load, so they are no longer culled while visible.
- Static models with their test point in solid are no longer randomly hidden.
- Pipeline lookup cache and cheaper static-model culling: 59–131 fps → 83–144 fps at five test positions with 26 bots (i7-7700, RTX 2070, 1920×1080).
- `cg_forceFxInterval` (default 16 ms): force lightning and drain effects are started at most once per interval per player instead of every frame, removing the FPS drop while they are used.
- One warning per map when render entities or draw surfaces are dropped; `r_showLimits 1` shows peak use.

## Diagnostics
`sv_profile <s>`, `bot_profile <s>`, `r_showLimits 1`, `sv_crashStacks 1`, `sv_hitchStacks <ms>`, `com_sampleProfile <ms>` (the last three are Windows-only debugging aids).

## Notes
- rd-vulkan is the renderer to use on very large maps. The vanilla OpenGL and rend2 renderers keep the 2,047 entity limit; rend2 received a buffer-limit increase so it can load Korriban but is far too slow on it.
- Install: extract over a TaystJK installation's `GameData` folder (back up the existing binaries first). Game assets are not included.
