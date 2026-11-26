# Naboo Theed: collision problems (open list)

Collected for the map-fix round; nothing here is fixed yet. Units are engine units (39.37 per metre), positions
as `x y z` in the game's coordinates (`setviewpos x y z` goes there).

## Reported by the user (field test, Steam install, 2026-11-26)

| What | Where | Notes |
|---|---|---|
| Crates you can walk through | not given | see "Crates" below: most crate placements have collision geometry nearby, but the check counts the ground under them too, so whether the crate itself is solid is still to be tested against the brushes |
| Ground by the fence at the river has no collision | river, by a fence | the player fell into the water there |

## Found by checks

### Drawn floors without collision (`tools\visual_vs_collision.py`, 14,505 samples on upward-facing surfaces)

* 84.2 % of the samples have solid within 4 units below the drawn surface, 90.3 % within 16, 92.0 % within 64.
* 1,164 samples (8 %) have no solid within 64 units: 1,142 small patches spread over the map (the worst cells have
  only 2 samples each, so these are many small holes rather than a few large ones). Report:
  `devgame_naboo\nicjk\maps\naboo_theed_floorcheck.json`.
* 1,746 samples lie under a water surface (expected for river and fountain beds; not counted as holes).

### Crates and containers (proximity check against `export\city\collision\collision_tris.npy`)

* 16 placements have no collision triangle within 45 units of their centre: 6 of `container_03_s_a`, 3 of
  `o_container_03_s_a_01`, 3 of `container_03_s_propdress_1x2x2`, 4 of `container_03_s_propdress_08`
  (e.g. at 1201 10194 -499, -33 -8526 14, -589 -7984 9, -1981 -4229 31, 2617 -2093 57, 1548 2770 31).
* All others have triangles nearby, which may be only the floor under them: to be checked with a brush test.

### Collision rules that can explain pass-through props (`tools\naboo_config.json`, "collision")

* objects smaller than 0.35 m get no collision at all;
* objects up to 1.2 m become a single box;
* larger ones are decimated to 20 % of their triangles (200 to 3,000), which can open gaps in thin walls and fences.

## A river with most of its water missing (user, 2026-11-26)

One river shows little of its water surface, and has missing collision as well. Which river is still to be found
(earlier water audit, `export\city\water_audit.json`, found nothing missing, so the check itself missed this case).

## Method for the fixes (user: "use these tests with bots")

Bot runs on a test server log where players die by water, falling and suicide, with positions, so that the bad
spots can be found and fixed, then the same run repeated to see the counts drop.

## Bots in the water and odd spawn points (user, 2026-11-26)

* Bots walk into the water far too often. The map has no bot routes (`botroutes/naboo_theed.wnt`), so bots move
  without waypoints and do not see quay edges. Plan: bot-only clip (`CONTENTS_BOTCLIP`, which the engine supports:
  "do not enter this brush by navigation") along water edges that border walkable ground, written by
  `tools\write_collision_bsp.py` from `export\city\collision\water_boxes.npy`; players are not affected.
* Review all 109 spawn points and remove or move the odd ones (near water edges, in corners, on props).

## Seen in the long-play test (31 bots, Steam install)

First ~10 minutes, deaths by cause (server log): saber 421, dark force 17, suicide 11, falling 5, water 3.
Suicides may be bots killing themselves when stuck; to be matched with positions.

(filled in after the run: bot falls, deaths by falling, bots stuck in or passing through geometry)

### More from the user, watching the long-play run

* Bot "Goku" walked through a chapel-like building: no collision in its walls (likely the decimation to at most
  3,000 triangles per object, see the rules above).
* The big crates have no collision: confirmed by the material check, all container meshes use a cut-out material
  and the collision export keeps opaque materials only.
* One fence floats in the air.
* Bot "Karlach" fell through a hole just in front of the palace interior's main staircase.
* Bots that fall through holes do not die: they land on collision further down (likely the terrain under the
  plazas) and walk around under the map.
* Far buildings flicker while the camera follows a running bot (depth precision or detail switching; to check).
* User screenshots: a bot sunk to the waist in the quay paving by the river balustrade (no collision at the paving
  surface; 194 hole samples lie at quay level, the largest group), and a bot walking on the source terrain under
  the palace ("no one should get here"). Fix: close the holes (collision export) and take the terrain collision
  away wherever the city's floors cover it, with a kill volume below, so whoever still falls through dies and the
  death log shows the spot.
* User screenshot: bot "Cultist" far below the whole map, looking up at the underside of the terrain. The map's
  sky box (`naboo_theed.map`, worldspawn) has a solid bottom at z -7936; anyone falling out of the world lands on
  it and walks there. Fix: a kill volume (trigger_hurt) over the whole map just above that floor, below the
  lowest real ground, so falling out of the world kills.
* User screenshot ("a big problem area"): bot "Vader Mcquarrie" in the river below a sheer quay wall with the
  balustrade above; there is no way back up, so a bot that gets in stays there. They get in through the quay
  paving holes along the balustrade (earlier screenshot). Fix: close the paving holes, make the balustrade solid
  for everyone, bot clip along quay edges; check whether a way out of the water exists in the source (steps).
* User screenshot: "the building with stairs and no collision": courtyard with a fountain, curved stone stairs and
  an arcaded building (columns, red curtains in the arches). Likely the same building bot "Goku" walked through.
  To locate from the bot position logs and the source file; check its walls, columns and stairs.
* User screenshot: bot "Reborn" sunk into the quay paving up to its head, next to the balustrade by a stone bench
  (another stretch of the same quay; the paving has no collision at its surface along the balustrade).
* User screenshot (just after the 40-minute map reload): two bots fighting on a dry paved floor at the foot of a
  tall quay wall with a balustrade on top and a bridge in the distance. This is most likely the river whose water
  is missing: the bed is drawn and walkable, the water surface above it is not there. To find in the source which
  water surface covers this channel and why the cook dropped it.
* User screenshot ("missing collision"): the camera following a bot is pressed into a tall quay wall at water
  level, with water on both sides of the view: the bot stands inside the quay wall. The wall's river face has no
  collision (or only far behind the drawn face). Same quay meshes as the paving reports.

## Textures to check (user, free play)

* A tall building wall with pilasters (light grey bases, dark reddish-brown stone between): the stone reads as
  large, soft, smeared blocks without fine detail, unlike the crisp sandstone elsewhere. Likely a baked material
  with the wrong repeat or without its tiling detail layer. To compare with a render of the source at that wall.
* The tour also showed (earlier sessions) the market building and statues as texture/UV suspects; the map-wide
  texture/UV check is still open in TODO.
* User (free play): bot/player walks through a large garden hedge; hedges (clipped walls of foliage) should block.
  New rule: hedge meshes get a simple block collision; bushes, flowers, vines and grass stay passable.
* User ("geometry is not right here"): on a terrace by curved stairs and a balustrade, the tiled floor folds up
  into a soft slope toward the railing. Looks like a ground surface (terrain or the world-projected "virtual
  terrain" paving) poking up through the terrace paving. To compare with the source: cut or lower that surface.
* User (free play): a dim enclosed pocket with tiled floor fading into dirt, a sloped stone block and a closed
  city door with a round emblem, walls all around and a dark ceiling: probably a space under or behind a terrace
  that is reachable through the raised ground beside the balustrade. Not meant to be walkable; close its entrance.
* User ("ground texture"): open paving seen from above shows a straight hard seam: one side darker than the
  other, with the tile pattern continuous across it. Likely two paving placements with different lighting: the
  sky occlusion (`.tsky`) is one value per placement, so neighbouring ground pieces can differ by a step.
  Fix to try: per-vertex sky occlusion for large ground pieces, or no indoor darkening for open ground.
* User: a lamp post you can stand on top of: posts under 1.2 m across become one box as wide as the lamp head and
  as tall as the post (also an invisible wall around the slim post). Rule: tall slim objects (lamp posts, banner
  poles, bollards) get a thin eight-sided column solid instead of a box.
* User ("this door is blocked"): an open metal garden gate between two stone pillars (river/market side) cannot be
  walked through although both leaves stand open. The gate object (frame and leaves) becomes one solid block over
  the whole opening. Rule: gates keep their real parts (leaves, posts), never one block over the opening.
* User (free play): in a canal, only a narrow ribbon of water runs along the foot of the tall quay wall; the rest of
  the channel is a dry, sloped sandy bank rising above the water. So the water surface is there, but the ground of
  the bed (terrain) sticks out above it over most of the channel. Probably the "river with most of its water
  missing" and the dry paved channel. Fix: lower (carve) the bed under the whole water surface, as for the other
  rivers, and its collision with it.
* User (free play): by the garden fountain pool, a flat teal water patch lies on the paving outside the pool, with
  hard straight edges. Looks like one of the water patches the cook generates to fill trenches ("fill water"),
  placed where the paving is level with it. Fix: drop generated water where solid paving lies at or above it;
  check every generated patch against the source the same way.
* User (free play, river from above): a patch of grass, paving and sand path sticks up through the river surface
  with a jagged stair-step edge, plus a row of small pale triangles poking through the water nearby. The stair-step
  edge is the cell grid of the terrain lowering under water: a block of cells was not lowered, and coarse terrain
  triangles at its edge reach above the surface. Fix: lower every terrain vertex inside each water surface (plus a
  margin) to below the bed depth, at vertex level rather than per cell, then check that no ground lies above any
  water surface. Same cause as the canal whose bank rises above the water.
* User ("textures look blurry here"): the cliff by the waterfall, seen up close: rock and moss are soft and smeared.
  Large cliff meshes carry one unique texture stretched over a big area; the source adds a tiling rock detail layer
  (and detail normals) on top, which the port probably lacks for these materials. To check: the cliff materials'
  bake size and whether their tiling detail layer and normal map survived the bake.
* User ("and no collision"): inside the waterfall cliff: the player passes into the rock. Collision is only built
  inside the playable bounds (`collision_bounds_m` of the city region); objects outside (324 skipped) get none, and
  the cliff is likely one of them while still reachable. Fix: either extend the collision bounds to every surface a
  player can reach, or put an invisible boundary wall (player clip) at the edge of the playable area so scenery
  without collision cannot be reached. Prefer the boundary wall plus collision for any scenery inside it.
* User ("bugged textures"): beside the round building's curved steps, a large paving area is a flat pinkish-beige
  colour with no tiles or detail at all, while the paving next to it shows proper stone tiles. Candidates: one of
  the 12 world-projected paving materials drawn without its tiling layer (the base "gnd_flat" colour only), or a
  material whose texture was not found and fell back to its plain colour. To identify with `tools\world_probe.py`
  at that spot.
* User (free play): at a balustrade wall, a black crate lies tilted and half sunk into the paving (a placement that
  probably rested on something missing, or rotated wrongly), and the wall base shows a lighter rectangular block in
  the middle with hard edges (same per-placement lighting step as the paving seam). Check the crate's placement
  against the source.
* User ("a lot of colour-mismatched stone"): open paving where the same stone tiles change brightness and tint in
  bands and patches with straight edges. Two causes to separate: the per-placement lighting step (sky occlusion,
  see the seam above) and neighbouring paving drawn with different materials (world-projected paving with its own
  base colour next to mesh-textured paving of the same stone). Fix: per-vertex sky occlusion for ground pieces, and
  match the base colour and roughness of the world-projected paving to the baked paving of the same stone.
* User (free play): open ground where four rectangles of the same paving meet in a straight cross, each with a
  clearly different brightness and tint (light grey, mid grey, brown). This is the corner of four baked terrain
  ground tiles (`gt_<x>_<y>`, e.g. gt_7_15 / gt_8_15 / gt_7_16 / gt_8_16 as found earlier): each tile is baked on its
  own and they do not match. Fix: bake the ground tiles with the same exposure and colour scale, then blend a strip
  along every tile border; verify by sampling the colour on both sides of every border.
