# NicJK humanoid (_humanoid.gla) frame map

## Current clean humanoid (22438 frames, 12.4 MB)

Rebuilt with `tools/animremap/gla_build.py` from the stock JKA humanoid (`gla_merge/basejka humanoid`,
identical to the game's assets1.pk3), then Niksata's custom animations and the Yoda attacks copied frame for frame
from the previous NicJK humanoid (byte-identical, verified), then the 23.04.2019 versions of four Palpatine
animations, which differ from the merged ones (verified: up to 23-68 degrees), from
`niksata_anims23.04.2019.gla`. The SJE pack (26273 frames that NicJK's animation.cfg never used) is gone, so every
custom frame number moved down by 26273 (old 47649 = new 21376).

| Frames | Content |
|---|---|
| 0 - 21375 | stock Jedi Academy humanoid |
| 21376 - 21965 | Niksata custom animations (old 47649 - 48238) |
| 21966 - 22317 | Yoda attacks (old 48239 - 48590) |
| 22318 - 22437 | 23.04.2019 versions: Palpatine stance 2 + overhead, l_r, tr_bl, full 40-frame t_rl |

`animation.cfg` is now the stock one (plus stock stand-ins for NicJK's three extra names, BOTH_SABERTAVION_STANCE,
BOTH_SABERDESANN_STANCE and BOTH_A1_SPECIAL_YODA), with every custom animation listed as comments at the end.
NicJK's previous versions of the 17 entries that differed from stock are in `animation_nicjk.cfg`
(renumbered); `docs/per-model-anims-config.cfg` gives them to Niksata's models (NikolayAngelov*, DarkNicangell*) through
animremap, so with `cg_permodelanims 1` / `g_permodelanims 1` those models play exactly what NicJK played before and
every other model plays the stock animations.

| Frames | Count | Name in animation.cfg comments |
|---|---|---|
| 21376 - 21377 | 2 | NIK_WARRIOR_STANCE_SINGLE |
| 21378 - 21378 | 1 | NIK_WARRIOR_STANCE_DUAL |
| 21379 - 21401 | 23 | NIK_FORCE_CHARGE |
| 21402 - 21412 | 11 | NIK_FORCE_CHARGE_ATTACK |
| 21413 - 21442 | 30 | NIK_SMASH |
| 21443 - 21486 | 44 | NIK_ASSAULT |
| 21487 - 21516 | 30 | NIK_VICIOUS_SLASH |
| 21517 - 21550 | 34 | NIK_OBLITERATE |
| 21551 - 21581 | 31 | NIK_AEGIS_ASSAULT |
| 21582 - 21622 | 41 | NIK_CRUSHING_BLOW |
| 21623 - 21623 | 1 | NIK_GUARDIAN_STANCE |
| 21624 - 21662 | 39 | NIK_DUAL_FURIOUS_STRIKE |
| 21663 - 21705 | 43 | NIK_PALPATINE_CHARGE |
| 21706 - 21746 | 41 | NIK_ANNIHILATE |
| 21747 - 21760 | 14 | NIK_PALPATINE_TURN_L_R |
| 21761 - 21800 | 40 | NIK_PALPATINE_STANCE1_STAB |
| 21801 - 21829 | 29 | NIK_PALPATINE_R_L |
| 21830 - 21871 | 42 | NIK_PALPATINE_STANCE2_OVERHEAD |
| 21872 - 21889 | 18 | NIK_PALPATINE_BR_TL |
| 21890 - 21908 | 19 | NIK_PALPATINE_L_R |
| 21909 - 21922 | 14 | NIK_PALPATINE_TL_BR |
| 21923 - 21941 | 19 | NIK_PALPATINE_TR_BL |
| 21942 - 21965 | 24 | NIK_PALPATINE_T_RL |
| 21966 - 22020 | 55 | NIK_YODA_A1_SPECIAL |
| 22021 - 22065 | 45 | NIK_YODA_BL_TR |
| 22066 - 22115 | 50 | NIK_YODA__L__R |
| 22116 - 22164 | 49 | NIK_YODA_TL_BR |
| 22165 - 22215 | 51 | NIK_YODA_BR_TL |
| 22216 - 22270 | 55 | NIK_YODA_BL__R |
| 22271 - 22315 | 45 | NIK_YODA__R__L |
| 22316 - 22317 | 2 | NIK_YODA_END |
| 22318 - 22359 | 42 | NIK_PALPATINE_STANCE2_OVERHEAD_2019 |
| 22360 - 22378 | 19 | NIK_PALPATINE_L_R_2019 |
| 22379 - 22397 | 19 | NIK_PALPATINE_TR_BL_2019 |
| 22398 - 22437 | 40 | NIK_PALPATINE_T_RL_2019 |

---

# Previous NicJK humanoid (48591 frames) - kept for reference

Generated from `assets/japro/models/players/_humanoid/_humanoid.gla` (48591 frames, the GLA in `japro-assets.pk3`), the source GLAs in `gla_merge` and the coordinate notes. Frames were matched bone by bone (by bone name; the source files store the same 53 bones in another order).

## Layers

| NicJK frames | Content |
|---|---|
| 0 - 21375 | stock Jedi Academy humanoid (identical, frame for frame) |
| 21376 - 47648 | SJE animation pack (the humanoid all the custom merges were built on) |
| 47649 - 48238 | Niksata custom animations, merged one by one with glamerge (001-022) |
| 48239 - 48590 | Yoda attacks (`yoda_anims_only.gla`) |

glamerge appends a file's frames *without its frame 0*, so source frame k is at NicJK frame offset+k (k >= 1).

## Custom blocks

| NicJK frames | Count | Animation | Source file (frame 1 onward) | Frames identical | Used by NicJK animation.cfg |
|---|---|---|---|---|---|
| 47649 - 47650 | 2 | warrior stance single | `001.both_warrior_single_sje - Copy/both_warrior_single2.gla` | 0 of 2 frames all 53 bones (rest close: re-saved copy) | BOTH_SABERDESANN_STANCE 47650 1 |
| 47651 - 47651 | 1 | warrior stance dual | `002.both_warrior_dual_sje - Copy/both_warrior_dual2.gla` | 0 of 1 frames all 53 bones (rest close: re-saved copy) | BOTH_SABERDUAL_STANCE 47651 1 |
| 47652 - 47674 | 23 | force charge | `003.both_force_charge_sje - Copy/both_force_charge2.gla` | 0 of 23 frames all 53 bones (rest close: re-saved copy) | BOTH_FORCEJUMP1 47652 23 |
| 47675 - 47685 | 11 | force charge attack (landing) | `004.force_charge_landing_sje - Copy/force_charge_landing2.gla` | 0 of 11 frames all 53 bones (rest close: re-saved copy) | BOTH_FORCELAND1 47675 11, BOTH_LAND1 47675 11 |
| 47686 - 47715 | 30 | smash / dual smash | `005.both_warrior_smash_sje - Copy/both_warrior_smash2.gla` | 0 of 30 frames all 53 bones (rest close: re-saved copy) | - |
| 47716 - 47759 | 44 | assault | `006.both_assault_sje - Copy/both_assault3.gla` | 44 of 44 frames all 53 bones | - |
| 47760 - 47789 | 30 | vicious slash | `007.both_vicious_slash_sje - Copy/both_vicious_slash.gla` | 0 of 30 frames all 53 bones (rest close: re-saved copy) | - |
| 47790 - 47823 | 34 | obliterate | `008.both_obliterate_sje - Copy/both_obliterate3.gla` | 34 of 34 frames all 53 bones | - |
| 47824 - 47854 | 31 | aegis assault (from notes; no source file in gla_merge) | - | - | - |
| 47855 - 47895 | 41 | crushing blow (from notes; no source file in gla_merge) | - | - | - |
| 47896 - 47896 | 1 | jedi guardian stance (from notes; no source file in gla_merge) | - | - | BOTH_SABERTAVION_STANCE 47896 1 |
| 47897 - 47935 | 39 | dual furious strike (from notes; no source file in gla_merge) | - | - | - |
| 47936 - 47978 | 43 | Palpatine charge (spin attack) | `012.palpatine_spin_attack - Copy/palpatine_spin_attack3.gla` | 43 of 43 frames all 53 bones | BOTH_FLIP_F 47936 33 |
| 47979 - 47982 | 4 | annihilate, frames 1-5 | `013.both_annihilate - Copy/both_annihilate1-5.gla` | 4 of 4 frames all 53 bones | - |
| 47983 - 47986 | 4 | annihilate, frames 6-9 (single-frame files; by the notes annihilate is 47979 + 41 frames) | - | - | - |
| 47987 - 48016 | 30 | annihilate, frames 10-39 | `013.both_annihilate - Copy/both_annihilate10-39.gla` | 30 of 30 frames all 53 bones | - |
| 48017 - 48019 | 3 | annihilate, frames 40-42 (single-frame files) | - | - | - |
| 48020 - 48033 | 14 | Palpatine l_r turn | `014.palpatine_t_rl1 - Copy/palpatine_t_rl1-3.gla` | 14 of 14 frames all 53 bones | - |
| 48034 - 48073 | 40 | Palpatine stance 1 + stab | `015.Palpatine_stab+stance/palpatine_stab+stance3old.gla` | 40 of 40 frames all 53 bones | BOTH_STAND2 48035 1 |
| 48074 - 48102 | 29 | Palpatine r_l | `016.Palpatine_R_L/palpatine_r_l3.gla` | 29 of 29 frames all 53 bones | - |
| 48103 - 48144 | 42 | Palpatine stance 2 + overhead | `017.Palpatine_overhead/palpatine_overhead3.gla` | 21 of 42 frames all 53 bones (rest close: re-saved copy) | BOTH_SABERFAST_STANCE 48103 1 |
| 48145 - 48162 | 18 | Palpatine br_tl | `018.Palpatine_BR_TL/palpatine_br_tl3.gla` | 18 of 18 frames all 53 bones | - |
| 48163 - 48181 | 19 | Palpatine l_r | `019.Palpatine_L_R/palpatine_l_r3.gla` | 4 of 19 frames all 53 bones (rest close: re-saved copy) | - |
| 48182 - 48195 | 14 | Palpatine tl_br | `020.Palpatine_TL_BR/palpatine_tl_br3.gla` | 14 of 14 frames all 53 bones | - |
| 48196 - 48214 | 19 | Palpatine tr_bl | `021.Palpatine_TR_BL/palpatine_tr_bl3.gla` | 5 of 19 frames all 53 bones (rest close: re-saved copy) | - |
| 48215 - 48238 | 24 | Palpatine t_rl (cut short by the Yoda block) | `022.Palpatine_T_RL_2-17/palpatine_t_rl_2-173.gla` | 13 of 24 frames all 53 bones (rest close: re-saved copy) | - |
| 48239 - 48590 | 352 | Yoda attacks | `Niksata vanilla humanoid with yoda attacks/yoda_anims_only.gla` | 352 of 352 frames all 53 bones | BOTH_T5_BL_TR 48294 45, BOTH_T5_BL__R 48489 55, BOTH_T5_BR_TL 48438 51, BOTH_T5_TL_BR 48389 49, BOTH_T5__L__R 48339 50, BOTH_T5__R__L 48544 45, BOTH_A1_SPECIAL_YODA 48239 55 |

## What NicJK's animation.cfg uses

| Layer | animation.cfg entries starting there |
|---|---|
| stock (0 - 21375) | 1404 |
| SJE (21376 - 47648) | 0 |
| custom (47649 - 48238) | 9 |
| Yoda (48239 - 48590) | 7 |

### Entries in the custom block

| Entry | First | Frames | Loop | FPS |
|---|---|---|---|---|
| BOTH_FLIP_F | 47936 | 33 | -1 | 30 |
| BOTH_FORCEJUMP1 | 47652 | 23 | -1 | 30 |
| BOTH_FORCELAND1 | 47675 | 11 | -1 | 20 |
| BOTH_LAND1 | 47675 | 11 | -1 | 20 |
| BOTH_SABERDUAL_STANCE | 47651 | 1 | -1 | 20 |
| BOTH_SABERFAST_STANCE | 48103 | 1 | 1 | 30 |
| BOTH_STAND2 | 48035 | 1 | 1 | 30 |
| BOTH_SABERTAVION_STANCE | 47896 | 1 | -1 | 30 |
| BOTH_SABERDESANN_STANCE | 47650 | 1 | -1 | 20 |

### Entries in the Yoda block

| Entry | First | Frames | Loop | FPS |
|---|---|---|---|---|
| BOTH_T5_BL_TR | 48294 | 45 | -1 | 30 |
| BOTH_T5_BL__R | 48489 | 55 | -1 | 30 |
| BOTH_T5_BR_TL | 48438 | 51 | -1 | 30 |
| BOTH_T5_TL_BR | 48389 | 49 | -1 | 30 |
| BOTH_T5__L__R | 48339 | 50 | -1 | 30 |
| BOTH_T5__R__L | 48544 | 45 | -1 | 30 |
| BOTH_A1_SPECIAL_YODA | 48239 | 55 | -1 | 30 |

### Entries in the SJE block


