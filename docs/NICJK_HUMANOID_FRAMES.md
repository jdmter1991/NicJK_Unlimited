# NicJK humanoid (_humanoid.gla) frame map

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


