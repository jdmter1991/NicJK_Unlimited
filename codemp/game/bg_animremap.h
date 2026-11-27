/*
===========================================================================
NicJK Unlimited - per-model animation remapping (per-model-anims-config.cfg)

The same move (animation number BOTH_*) can play different frames depending
on the player model, configured by a text file. Off unless g_permodelanims
(server) / cg_permodelanims (client) is set.

Animation numbers sent over the network, every check in the game code, bots
and stock clients are unchanged. Only the frames a model shows for a given
animation number are swapped, and gameplay timing is unchanged unless a line
uses the "timing" mode. See GameData/nicjk/per-model-anims-config.cfg for the format.
===========================================================================
*/

#pragma once

// Drop everything loaded and read the files again on next use.
void BG_AnimRemap_Reload( void );
// Also forget own-skeleton tables (called when the anim sets are cleared).
void BG_AnimRemap_Reset( void );

// A model's own skeleton file outside models/players/_humanoid/ that has the
// humanoid bones and its own animation.cfg next to it (MovieDuels style).
// Such a model is accepted (instead of being replaced by Kyle) only when the
// caller has remaps on; it keeps humanoid gameplay (table 0) and is drawn
// with its own frames. The slot is a bgAllAnims index holding its table,
// for reading its animevents.cfg.
qboolean BG_AnimRemap_OwnSkeleton( const char *gla );
int BG_AnimRemap_OwnSkeletonSlot( const char *gla );

// Print what is loaded (and which models have been built so far).
void BG_AnimRemap_List( void );

// Table used to draw / pose a client's model: the model's remaps applied,
// or bgAllAnims[animIndex].anims when the model has none. Only humanoid
// skeleton tables (animIndex 0) are remapped. gla is the GLA the entity's
// Ghoul2 model really uses (G2API_GetGLAName); replacements from an animset
// are only shown when it is that animset's GLA.
const animation_t *BG_AnimRemap_Visual( int clientNum, int animIndex, const char *model, const char *skin, const char *gla );

// Table pmove should use for this client: differs from the base table only
// when the model has lines in "timing" mode. NULL means use the base table.
animation_t *BG_AnimRemap_Pmove( int clientNum, int animIndex, const char *model, const char *skin, const char *gla );

// Split "model/skin" into its parts (skin "" when missing).
void BG_AnimRemap_SplitModel( const char *modelSkin, char *model, int modelSize, char *skin, int skinSize );

#ifdef _GAME
struct gentity_s;
void G_AnimRemap_SetClientModel( int clientNum, const char *modelSkin );
const animation_t *G_AnimRemap_Visual( struct gentity_s *ent );
animation_t *G_AnimRemap_Pmove( struct gentity_s *ent );
void G_AnimRemap_ListClients( void );
#endif
