# Per-model animation remapping (animremap.cfg)

The same move can play a different animation depending on the player model,
chosen by a text file you can edit without recompiling. Example: a Sith model
stands in the strong-style stance and uses the strong-style kata, while a Jedi
model with the same saber style keeps the normal ones.

It is off by default. Nothing changes unless `g_animRemap 1` (server) and/or
`cg_animRemap 1` (client) is set and a cfg exists.

## Setup

1. Copy `docs/animremap.cfg` to `GameData/nicjk/animremap.cfg` and remove the
   `//` in front of the lines you want (the file explains the format).
2. Server: `g_animRemap 1`. Client: `cg_animRemap 1`. On a local game set both.
3. After editing: `animremap_reload` (server console / rcon) and
   `cg_animremap_reload` (client), or change map. `animremap_list` and
   `cg_animremap_list` show what is loaded and which clients are remapped.

Line format: `model[/skin]  ANIMATION  REPLACEMENT  [fit|free|timing]`

* `fit` (default): the replacement is stretched or squeezed to the original's
  length. Gameplay timing is exactly unchanged.
* `free`: the replacement plays at its own speed; gameplay timing unchanged.
  Meant for looping stances, idles and runs.
* `timing`: the replacement plays at its own speed and the move also lasts as
  long as the replacement in gameplay. This changes combat timing.

`BOTH_A2_* BOTH_A3_*` maps a whole group by prefix. `*` as the model means every
model. A model can ship its own `models/players/<model>/animremap.cfg` (lines
without the model column); the central file overrides it.

When a model is first seen, the console prints every remap with both lengths and
warns when they differ, e.g.

    AnimRemap: desann/default: BOTH_A2_SPECIAL -> BOTH_A3_SPECIAL (fit): lengths differ, 2800 ms vs 2450 ms, shown over 2793 ms; gameplay timing unchanged

## Design

### What the game does today

Pmove (shared by server and client) picks an animation number (`BOTH_*`) for
every move, e.g. `saberMoveData[LS_A_T2B].animToUse`. The number goes into
`ps->torsoAnim` / `legsAnim` and over the network. Each skeleton has a table,
`bgAllAnims[i].anims`, from its `animation.cfg`, saying which `.gla` frames an
animation number plays and for how long. Move timers (`torsoTimer`, saber move
length) come from that table. Every player model on the stock humanoid skeleton
shares one table (index 0), and dozens of places in the game code test
`localAnimIndex == 0` / `> 1` to mean "humanoid".

### Options considered

1. **Change the animation number** (remap in `PM_SetAnim`). Stock clients would
   see the new animation, but every check of the form `torsoAnim == BOTH_x`
   (saber move logic, knockdowns, rolls, bot AI in `ai_main.c`) would change
   behaviour, and client and server would have to agree exactly. Rejected:
   changes gameplay and breaks bots.
2. **Give remapped models their own animation table index** (`localAnimIndex`).
   Clean data-wise, but about 40 places treat any index other than 0 as
   "not humanoid" (broken limbs, ragdoll, nonHumanoid pmove, saber code), in
   files other sessions are editing. Rejected: too invasive.
3. **Remap only where frames are put on the model** (chosen). Animation numbers,
   pmove, timers, bots and network stay exactly as they are. A per-model copy
   of the humanoid table, with the entry for animation A holding B's frames, is
   used only in the client's drawing (`CG_SetLerpFrameAnimation`, model reset,
   anim-event loop ranges) and the server's Ghoul2 posing (`G_UpdateClientAnims`,
   which saber traces hit). Only the `timing` mode also hands pmove a table with
   B's length, on both server and client prediction.

### Where the cfg lives

Both: one central `GameData/nicjk/animremap.cfg` keyed by model (like
`modelscale.cfg`) and an optional per-model file inside the model's folder so a
model pk3 can carry its own. Central lines win, model/skin beats model beats `*`.
The example ships in `docs/` and not in the nicjk assets pk3, because a pk3 copy
would hide the user's loose file.

### Server and client agreement

* `fit` and `free` never touch pmove, so prediction cannot disagree. A client
  without the cfg, or with `cg_animRemap 0`, or a stock client, simply sees the
  original animations and plays exactly the same game.
* `timing` changes pmove on the server when `g_animRemap 1`. The client uses
  the same table for prediction only when the server's `g_animRemap` (sent in
  serverinfo) is on and the client has the same cfg. If the files differ, or for
  stock clients, the server corrects the client's prediction during those moves
  (a small snap), as with any server-side gameplay change. Ship the cfg in a pk3
  if you use `timing` on a public server.
* The server always remaps with its own file; the client's file only decides
  what that client draws.

### Limits

* Only the humanoid skeleton (`_humanoid`) and real clients (players and bots)
  are remapped; NPCs and custom skeletons keep their animations.
* Facial (head) animations and death ragdoll setup use the original table.
* Up to 64 different model/skin combinations with remaps at once (48 with tables
  in use); more fall back to normal animations with a console warning.
* `fit` rounds the per-frame time to whole milliseconds, so the shown length can
  differ from the original by a few ms (the log shows the shown length); the
  gameplay timer is untouched.

## Code

* `codemp/game/bg_animremap.c/.h` - parser, per-model tables, lookups (new).
* `codemp/game/g_client.c` - remembers each client's model, poses the server
  model with the remapped table, `G_AnimRemap_Pmove` for `timing`.
* `codemp/game/g_active.c` - pmove table (one line).
* `codemp/cgame/cg_players.c` - drawing uses the remapped table.
* `codemp/cgame/cg_predict.c` - prediction table for `timing`.
* `codemp/game/g_svcmds.c`, `codemp/cgame/cg_consolecmds.c` - list/reload.
* `codemp/game/bg_panimate.c` - remaps are cleared with the anim sets.
