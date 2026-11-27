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

## Recommended: one shared humanoid with extra animations

Every model keeps the one shared `models/players/_humanoid/_humanoid.gla`; new
animations are appended to it once, and `animremap.cfg` picks per model which
animation each move plays. Because the server and every client have the same
file, the server's hit model can be posed with the remapped frames (saber hits
follow what is drawn), stock clients see the model with its normal animations,
and corpses, faces and ragdolls only ever get valid frames.

1. Build the combined GLA with `tools/animremap/gla_build.py BUILDFILE` (see
   `tools/animremap/example_build.txt`): `base` the current shared humanoid,
   `from` any GLA with the humanoid bones (any bone order), `anim NAME NEW_NAME`
   or `frames FIRST COUNT NEW_NAME`, `out humanoid.gla added.cfg [full.cfg]`.
   Base frames keep their numbers; the bone data is shared, so only new poses
   add size. Limit: 65535 frames in total (NicJK's humanoid uses 48591).
2. Ship the new `_humanoid.gla` and `added.cfg` in a pk3 that every player has.
3. In animremap.cfg:

        animset ext  models/players/_humanoid/_humanoid.gla  models/players/_humanoid/added.cfg  0
        kyle    BOTH_SABERFAST_STANCE  ext:DOOKU_FAST_STANCE  free
        desann  BOTH_VICTORY_FAST      ext:VADER_VICTORY_FAST

   Or pass a third `out` file to get a full animation.cfg in which added
   animations named like game animations replace them for every model.

`docs/NICJK_HUMANOID_FRAMES.md` maps what is in NicJK's current humanoid
(stock, SJE pack, the custom merges, the Yoda attacks) and which frames its
animation.cfg uses.

## A model's own animations (its own GLA)

Goal: as in single player, a model can carry its own animation file, so one
model really has different moves from another, while unconfigured models keep
the normal ones.

### What multiplayer does today

* A `.glm` names its GLA in its header (`animName`), and Ghoul2 loads that GLA
  for the model, on the client and on the server.
* Both the client (`CG_RegisterClientModelname`, cg_players.c) and the server
  (`SetupGameGhoul2Model`, g_client.c) **replace a player model with Kyle if its
  GLA path does not contain `players/_humanoid/`**. That check is the "not
  possible in MP" part. A GLA *inside* that folder is accepted: the user's
  Darth Talon pk3 already ships `models/players/_humanoid/talon_face.gla`.
* Whatever the GLA, the animation table is found from the GLA's folder, so
  every GLA in `players/_humanoid/` uses `_humanoid/animation.cfg` (table 0).
  A model's own GLA therefore has to keep the humanoid frame numbers.
* The server poses players with Kyle's model unless `d_perPlayerGhoul2` is on
  (a cheat cvar, off), so saber hits follow `_humanoid.gla` motion, not the
  model's own GLA.
* Animation tables other than 0 are treated as "not humanoid" in about 40
  places (broken limbs, ragdoll, `pm->nonHumanoid`, saber code in w_saber.c and
  bg_pmove.c), so giving a model its own table index is not an option without
  touching all of them.

### Options (both 1 and 2 are implemented)

1. **Separate GLA with its own animation.cfg** - the single-player and
   MovieDuels convention, e.g. `models/players/_humanoid_dooku/_humanoid.gla`
   with `animation.cfg` and `animevents.cfg` next to it. With `cg_animRemap 1`
   (client) / `g_animRemap 1` (server) such a model is accepted instead of being
   replaced by Kyle when its GLA has exactly the humanoid bones (names and
   parents, read from the file) and an animation.cfg. The game keeps treating it
   as humanoid (table 0, so pmove, bots, broken limbs, saber code are
   unchanged); it is drawn with its own table: one-shot moves keep this game's
   length (fit), loops play at their own speed. Its animevents.cfg is read
   against its own frames. Its animation.cfg is read by name with NicJK's own
   reader (MovieDuels' files are 72 KB, more than the stock 60 KB loader takes),
   so single-player-only names are skipped and the few multiplayer animations
   the file lacks fall back to its BOTH_STAND1 (both are listed in the console).
   Remap lines still work on top (a replacement then comes from the model's own
   table). A client without the feature (or a stock client) shows Kyle, as
   before. The server poses Kyle for saber hits unless `d_perPlayerGhoul2` is on.
   **Any model on any such skeleton, from the cfg:** `skeleton MODEL GLA`
   (e.g. `skeleton kyle models/players/_humanoid_vader/_humanoid`) makes the
   renderer load that GLA for the model instead of the one in its `.glm`
   header (rd-common/tr_animremap_gla.h, called where every renderer loads a
   `.glm`: rd-vulkan, rd-vanilla, rd-rend2 and rd-dedicated). From then on it
   is the same as a model that names the GLA itself. Models are cached, so a
   changed line applies after `vid_restart` or a restart. A client whose
   renderer is not NicJK's, or with `cg_animRemap 0`, shows the model as usual.
2. **Model's own GLA = humanoid frames + extra frames appended**. The
   GLA sits in `models/players/_humanoid/` (accepted everywhere, like Talon),
   frames 0..21375 are byte-identical to `_humanoid.gla`, so the stock
   animation.cfg, the server, bots and stock clients work unchanged on it.
   `animset` lines name the appended frames, and remaps point moves at them for
   that model only. Shown only where the entity's Ghoul2 model really uses the
   GLA (checked with `G2API_GetGLAName`); a client without the model or the
   server's Kyle use the normal frames, so nothing ever plays frames a GLA
   does not have.
3. **One bigger shared `_humanoid.gla`** with every model's extra frames
   appended (what MB2 does). Same code as option 2 (animsets point at the one
   GLA). Drawbacks: it replaces a base asset for everybody, the file grows with
   every model's moves, all clients need that pk3 (pure servers: a large
   download), and a mod replacing `_humanoid.gla` itself conflicts. Fine for a
   closed server pack; option 2 is better for per-model pk3s.

### Cost

* Memory: Ghoul2 keeps a whole GLA in memory, once per file name (it is copied
  at load, `R_LoadMDXA`). `_humanoid.gla` is 11.8 MB; a model's own GLA is that
  plus its extra frames (the test one with two cinematics: 18.7 MB). Each extra
  GLA in use costs that much on every client that draws the model. The
  dedicated server does not load it (it poses Kyle).
* Load time: reading the file from the pk3 when the model is first seen.
* Frame limit: animation tables store frame numbers as 16 bits, so a GLA can
  have at most 65535 frames (humanoid uses 21376, MovieDuels' Dooku 54612).
* MovieDuels' GLAs are 26-27 MB each (Dooku 26.6 MB, Yoda 26.9 MB).
* `MAX_ANIM_EVENTS` was raised from 300 to 512 per block: Yoda's
  animevents.cfg has 350, and going over the limit ends the map with an error.
  Client memory for event tables grows from about 1.2 MB to 2 MB.

### Building one

`tools/animremap/gla_append.py OUT.gla INTERNAL_NAME BASE.gla EXTRA.gla ...`
appends the frames of GLAs with the same skeleton (checked: same 53 bones,
same parents) and prints each one's frame offset. Sources can be read straight
from a pk3 (`file.pk3::path/in/pk3.gla`). Then point the model's `.glm` header
(`animName`, 64 bytes at offset 72) at the new GLA, e.g. with a hex editor or
by re-exporting the model, and add an `animremap.cfg` to the model folder:

    animset sour  models/players/_humanoid/_sith.gla  models/players/_humanoid_t1_sour/animation.cfg  33406
    BOTH_SABERFAST_STANCE  sour:BOTH_CIN_10  free

The base game's cinematic GLAs (`_humanoid_kor2`, `_humanoid_yavin1b`, ...)
have the humanoid skeleton and named animation.cfg files, so they work as
sources; note that most cinematic sequences move the whole body away from the
player's origin (root motion), which looks wrong for a stance or taunt.

### Seen while testing

When a player changed model while standing still (same animation number), the
new model showed its bind pose (T-pose) until the next animation change; the
client does not set the animation on the new Ghoul2 instance until then. It
happened with remaps off too; not checked whether stock JA does the same.
`cg_animremap_reload` resets it.

## Code

* `codemp/game/bg_animremap.c/.h` - parser, per-model tables, lookups (new).
* `codemp/game/g_client.c` - remembers each client's model, poses the server
  model with the remapped table, `G_AnimRemap_Pmove` for `timing`.
* `codemp/game/g_active.c` - pmove table (one line).
* `codemp/cgame/cg_players.c` - drawing uses the remapped table.
* `codemp/cgame/cg_predict.c` - prediction table for `timing`.
* `codemp/game/g_svcmds.c`, `codemp/cgame/cg_consolecmds.c` - list/reload.
* `codemp/game/bg_panimate.c` - remaps are cleared with the anim sets.
* `tools/animremap/gla_append.py` - appends whole GLAs (same bone order only).
* `tools/animremap/gla_build.py` + `example_build.txt` - picks named animations
  or frame ranges from any humanoid-bone GLA into one GLA (bones matched by name).
* `codemp/rd-common/tr_animremap_gla.h` + one line in each renderer's `.glm`
  loader (rd-vulkan, rd-vanilla, rd-rend2, rd-dedicated) - `skeleton` lines.
* `codemp/game/bg_public.h` - `MAX_ANIM_EVENTS` 300 -> 512.
