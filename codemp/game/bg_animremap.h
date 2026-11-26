/*
===========================================================================
NicJK Unlimited - per-model animation remapping (animremap.cfg)

The same move (animation number BOTH_*) can play different frames depending
on the player model, configured by a text file. Off unless g_animRemap
(server) / cg_animRemap (client) is set.

Animation numbers sent over the network, every check in the game code, bots
and stock clients are unchanged. Only the frames a model shows for a given
animation number are swapped, and gameplay timing is unchanged unless a line
uses the "timing" mode. See GameData/nicjk/animremap.cfg for the format.
===========================================================================
*/

#pragma once

// Drop everything loaded and read the files again on next use.
void BG_AnimRemap_Reload( void );

// Print what is loaded (and which models have been built so far).
void BG_AnimRemap_List( void );

// Table used to draw / pose a client's model: the model's remaps applied,
// or bgAllAnims[animIndex].anims when the model has none. Only humanoid
// skeleton tables (animIndex 0) are remapped.
const animation_t *BG_AnimRemap_Visual( int clientNum, int animIndex, const char *model, const char *skin );

// Table pmove should use for this client: differs from the base table only
// when the model has lines in "timing" mode. NULL means use the base table.
animation_t *BG_AnimRemap_Pmove( int clientNum, int animIndex, const char *model, const char *skin );

// Split "model/skin" into its parts (skin "" when missing).
void BG_AnimRemap_SplitModel( const char *modelSkin, char *model, int modelSize, char *skin, int skinSize );

#ifdef _GAME
struct gentity_s;
void G_AnimRemap_SetClientModel( int clientNum, const char *modelSkin );
const animation_t *G_AnimRemap_Visual( struct gentity_s *ent );
animation_t *G_AnimRemap_Pmove( struct gentity_s *ent );
void G_AnimRemap_ListClients( void );
#endif
