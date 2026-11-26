"""Cooker v1: direct dump -> maps/<name>.tworld (file version 2) + PNG textures + generated shader script.
  py cook_v1.py <export_dir> <mapname> <game_dir>
Adds over v0: material tint, sun/ambient in the header, detail levels (if the dump has them), terrain tiles
with their own detail levels and the scene's baked terrain colour map.
Format: docs/WORLD_FORMAT.md.
"""
import sys, os, json, re, shutil, struct, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "naboo_config.json"), encoding="utf-8"))
export_dir, mapname, game_dir = sys.argv[1], sys.argv[2], sys.argv[3]
UPM = float(cfg["units_per_metre"]); ORG = np.array(cfg["origin_m"], dtype=np.float64)
LIGHT = cfg.get("light", {})
SUN_DIR = np.array(LIGHT.get("sun_dir", [0.756, 0.256, 0.603]), dtype=np.float64); SUN_DIR /= np.linalg.norm(SUN_DIR)
SUN_COL = LIGHT.get("sun_color", [0.62, 0.55, 0.50]); AMB_COL = LIGHT.get("ambient_color", [0.36, 0.39, 0.44])
dump = os.path.join(export_dir, "dump")
scene = json.load(open(os.path.join(dump, "scene.json"), encoding="utf-8"))
mats = json.load(open(os.path.join(dump, "materials.json"), encoding="utf-8"))
# per-object material assignments and the records of those materials (tools/object_materials.py,
# tools/export_object_materials.py)
OBJ_OVERRIDE = {}
_oo = os.path.join(export_dir, "object_materials.json")
if os.path.exists(_oo) and cfg.get("object_materials", True):
    OBJ_OVERRIDE = json.load(open(_oo))["overrides"]
_mso = os.path.join(dump, "materials_objects.json")
if os.path.exists(_mso):
    for _k, _v in json.load(open(_mso, encoding="utf-8")).items():
        mats.setdefault(_k, _v)
_ms = os.path.join(dump, "materials_scatter.json")       # materials only the terrain scatter uses (export_scatter_materials.py)
if os.path.exists(_ms):
    for _k, _v in json.load(open(_ms, encoding="utf-8")).items():
        mats.setdefault(_k, _v)
t0 = time.time()
far_objs = []
fj = os.path.join(dump, "extras", "far.json")
if os.path.exists(fj) and cfg.get("far_scenery", True):
    fd = json.load(open(fj, encoding="utf-8"))
    far_objs = fd["objects"]
    for k_, v_ in fd["materials"].items():
        mats.setdefault(k_, v_)
HAS_DETAIL = os.path.exists(os.path.join(dump, "extras", "ground_detail.png")) and cfg.get("ground_detail", True)
HAS_RIPPLE = os.path.exists(os.path.join(dump, "extras", "water_ripple.png")) and cfg.get("animate", True)
ANIM_WATER, ANIM_SWAY, ANIM_CLOTH, ANIM_FOAM, ANIM_GLOW, ANIM_BILLBOARD, ANIM_WINDOW = 1, 2, 3, 4, 5, 6, 7
# Light decorations ("emissive_additive" materials): the source drives a white emission with the alpha of a texture
# and a strength. Strengths under GLOW_MIN are lamps that are switched off in this (daytime) scene: not drawn.
# The others are drawn unlit and additive; gain = strength clamped to GLOW_GAIN, colour GLOW_COLOR.
EMIS = {}
_es = os.path.join(export_dir, "emission_survey.json")
if os.path.exists(_es):
    EMIS = json.load(open(_es)).get("materials", {})
GLOW_MIN = float(cfg.get("glow_min_strength", 0.05))
GLOW_GAIN = cfg.get("glow_gain_range", [0.45, 0.8])       # the glow is added to the lit lamp glass, so it stays below 1
GLOW_COLOR = cfg.get("glow_color", [1.0, 0.74, 0.42])
# light fixtures whose emission the source's daylight scene sets to nearly zero; they glow where the sky is occluded
GLOW_INDOOR = tuple(cfg.get("glow_indoor_materials", ["LightWall_06", "LightWall_01", "lightwall_01", "LightCeiling_01", "Desklibrary_Emissive"]))
GLOW_SOLID = tuple(cfg.get("glow_solid_materials", ["candle_mat"]))
CRYSTAL = tuple(cfg.get("crystal_glass_materials", ["lambert17|SS_O_NAB_Palace_Chan"]))
GLOW_INDOOR_STRENGTH = float(cfg.get("glow_indoor_strength", 2.6))
# Water classes, matched to the source materials (docs/UPDATE_water_pbr.md):
#   water  river and pond surface: opaque, dark, mirror-like, two scrolling ripple layers (anim 1)
#   basin  fountain bowls: the same surface but see-through (anim 1, blended)
#   foam   falling water: white, alpha from scrolling noise times the mesh's vertex-colour fade (anim 4, blended)
FOAM_TEX = {"waterfall": ("T_ForestBase_Water_Tile_01_N", None), "fountain": ("T_TilingNoises_Curly_01_D", "T_TilingNoises_Simplex_01_D")}
SWAY_BUILDERS = ("vegetation", "canopy", "treestems", "tilingbush", "foliage_card")
CLOTH_WORDS = ("curtain", "banner", "flag", "awning")


def san(s):
    return re.sub(r"[^a-z0-9_]+", "_", s.lower()).strip("_")


def srgb_tint(t):
    return tuple(round(float(min(max(x, 0.0), 1.5)) ** (1.0 / 2.2), 3) for x in t)


# ---- materials -> (engine shader, tint)
tex_dir = os.path.join(game_dir, "textures", "naboo"); os.makedirs(tex_dir, exist_ok=True)
shader_text = {}        # shader name -> script text
materials = []          # (shader name, tint)
mat_index = {}          # (shader name, tint) -> index
mat_of = {}             # blender material name -> index or -1 (dropped)
tex_used = {}
cls_count = {}


BLEND_KINDS = ("blend", "basin", "foam", "glass", "add")


def water_shader(cls, tex=None, tex2=None):
    """Scripts for the water classes. The instanced path only takes the images and the blend state from them."""
    if cls == "foam":
        name = "textures/naboo/foam_%s" % san(tex)[:40]
        st = "\t{\n\t\tmap textures/naboo/%s\n\t\tblendFunc GL_SRC_ALPHA GL_ONE_MINUS_SRC_ALPHA\n\t\trgbGen lightingDiffuse\n\t\talphaGen const 0.35\n\t}\n" % san(tex)
        tex_used[san(tex)] = tex + ".png"
        if tex2:
            st += "\t{\n\t\tmap textures/naboo/%s\n\t\tblendFunc GL_DST_COLOR GL_SRC_COLOR\n\t}\n" % san(tex2)
            tex_used[san(tex2)] = tex2 + ".png"
        head = "\tcull none\n\tpolygonOffset\n"
    else:
        name = "textures/naboo/water_%s" % cls
        blend = "\t\tblendFunc GL_SRC_ALPHA GL_ONE_MINUS_SRC_ALPHA\n\t\talphaGen const 0.45\n" if cls == "basin" else ""
        st = "\t{\n\t\tmap $whiteimage\n%s\t\trgbGen lightingDiffuse\n\t}\n" % blend
        st += "\t{\n\t\tmap textures/naboo/water_nrm\n\t\tblendFunc GL_DST_COLOR GL_SRC_COLOR\n\t\ttcMod scroll 0.03 0.02\n\t}\n"
        tex_used["water_nrm"] = "water_nrm.png"
        head = "\tcull none\n"
    if name not in shader_text:
        shader_text[name] = "%s\n{\n%s%s}\n" % (name, head, st)
    return name


def shader_for(tex, cls, detail_rep=0):
    """cls: opaque, cutout, blend (alpha from texture), water, glass, add (additive glow).
    detail_rep > 0 adds a second stage with the tiling ground detail texture (x2 multiply)."""
    suffix = {"opaque": "o", "cutout": "c", "blend": "b", "water": "w", "glass": "g", "add": "a"}[cls]
    if detail_rep:
        suffix += "d%d" % detail_rep
    if tex:
        name = ("textures/naboo/%s_%s" % (tex, suffix))[:62]
        body = ["\t\tmap textures/naboo/%s" % tex]
    else:
        name = "textures/naboo/flat_%s" % suffix
        body = ["\t\tmap $whiteimage"]
    head = ["\tcull none"]
    if cls == "add":
        body += ["\t\tblendFunc GL_ONE GL_ONE", "\t\trgbGen lightingDiffuse"]
    elif cls in ("blend", "water", "glass"):
        body += ["\t\tblendFunc GL_SRC_ALPHA GL_ONE_MINUS_SRC_ALPHA", "\t\trgbGen lightingDiffuse"]
        if cls == "water":
            body.append("\t\talphaGen const 0.78")
        elif cls == "glass":
            body.append("\t\talphaGen const 0.30")
        else:
            head.append("\tpolygonOffset")
    else:
        body.append("\t\trgbGen lightingDiffuse")
        if cls == "cutout":
            body.append("\t\talphaFunc GE128")
    stage2 = ""
    if cls == "water" and HAS_RIPPLE:
        stage2 = "\t{\n\t\tmap textures/naboo/water_ripple\n\t\tblendFunc GL_DST_COLOR GL_SRC_COLOR\n\t\ttcMod scroll 0.03 0.02\n\t}\n"
        tex_used["water_ripple"] = "water_ripple.png"
    if detail_rep:
        stage2 = "\t{\n\t\tmap textures/naboo/ground_detail\n\t\tblendFunc GL_DST_COLOR GL_SRC_COLOR\n\t\ttcMod scale %d %d\n\t}\n" % (detail_rep, detail_rep)
        tex_used["ground_detail"] = "ground_detail.png"
    if name not in shader_text:
        shader_text[name] = "%s\n{\n%s\n\t{\n%s\n\t}\n%s}\n" % (name, "\n".join(head), "\n".join(body), stage2)
    return name


mat_pbr = {}            # engine material index -> (normal texture name or None, scale, roughness, metallic, flags)
PBR_DEFAULT = (None, 1.0, 0.85, 0.0, 0)
GLOSS_SQUARED = tuple(cfg.get("gloss_squared_materials", ["SS_NAB_PalaceInterio"]))
PBR_SURVEY = {}
_ps = os.path.join(export_dir, "pbr_survey.json")
if os.path.exists(_ps) and cfg.get("pbr", True):
    PBR_SURVEY = json.load(open(_ps))
PBR_TEX_DIR = os.path.join(dump, "textures_pbr")
pbr_tex_used = {}


# Source materials whose colour texture is mapped with the mesh's second UV set (tools/pbr_survey.py). The cooked
# vertex has one UV set, so triangles of these materials take UV1, and a normal map that uses UV0 is left out.
BASE_UV1 = set()
for _k, _e in PBR_SURVEY.items():
    _b = _e.get("Base Color") or {}
    if _b.get("image") and _b.get("uv") == "UV1" and mats.get(_k, {}).get("base_image") == _b["image"]:
        BASE_UV1.add(_k)


# Source materials that tile their colour texture (Mapping scale other than 1): the UVs of their triangles are scaled.
BASE_SCALE = {}
for _k, _e in PBR_SURVEY.items():
    _b = _e.get("Base Color") or {}
    if _b.get("image") and _b.get("coord") == "uv" and mats.get(_k, {}).get("base_image") == _b["image"] and tuple(_b.get("scale", [1, 1])) != (1.0, 1.0):
        BASE_SCALE[_k] = (float(_b["scale"][0]), float(_b["scale"][1]))


# Layered materials baked from their source formulas (tools/bake_materials.py): material -> baked texture, and
# for some a separate tiling colour layer.
BAKED = {}
_bk = os.path.join(dump, "baked", "baked.json")
if os.path.exists(_bk) and cfg.get("material_bake_use", True):
    BAKED = json.load(open(_bk))
for _k in list(BASE_SCALE):
    if _k in BAKED:
        del BASE_SCALE[_k]              # the bake already contains the tiling
# bakes that cover several UV units (textures repeating 1.5 or 0.375 times per unit): the mesh UVs are shifted and
# scaled down to that span
BASE_OFFSET = {}
for _k, _b in BAKED.items():
    if int(_b.get("uv_period", 1)) > 1:
        BASE_SCALE[_k] = (1.0 / _b["uv_period"], 1.0 / _b["uv_period"])
        BASE_OFFSET[_k] = tuple(_b.get("uv_offset", [0.0, 0.0]))
mat_tile = {}           # engine material index -> (tile texture name, repeats u, repeats v)
# materials whose whole colour is one texture projected from world position: material -> (image, repeats per metre)
WORLD_PROJ = {}
_cgf = os.path.join(export_dir, "color_graphs.json")
if os.path.exists(_cgf) and cfg.get("world_projected_paving", True):
    for _k, _g in json.load(open(_cgf))["materials"].items():
        _e = _g.get("color")
        try:
            if _e and _e[0] == "tex" and _e[2] == "Color" and _e[3][0] == "combine" and _e[3][1][0] == "math" and _e[3][1][1] == "MULTIPLY_ADD" and _e[3][1][3][0] == "sep" and _e[3][1][3][2] == ["geo", "Position"] and not _k.startswith("Terrain_"):
                WORLD_PROJ[_k] = (_e[1], abs(float(_e[3][1][4][1])))
        except (IndexError, TypeError, KeyError):
            pass
    if WORLD_PROJ:
        from PIL import Image as _ImF
        _gf = os.path.join(dump, "extras", "gnd_flat.png")
        if not os.path.exists(_gf):
            _ImF.new("RGBA", (16, 16), (128, 128, 128, 255)).save(_gf)



def pbr_of(name, m, cls):
    """Physically based values of a source material, from tools/pbr_survey.py (how its Principled BSDF is fed).
    Returns (normal texture, repeats per unit of UV, roughness, metallic, flags); flags 1: roughness = 1 - base
    alpha, 2: metallic = normal map alpha, 4: metallic = normal map blue."""
    e = PBR_SURVEY.get(name)
    if not e:
        return PBR_DEFAULT
    ntex = None; scale = 1.0; rough = 0.7; metal = 0.0; flags = 0
    n = e.get("Normal") or {}
    nimg = None
    # normal maps are sampled with the second UV set of the cooked vertex, which is UV0 wherever the colour
    # texture took UV1 (maps/<name>.tuv2) and the same as the first set everywhere else
    if n.get("image") and "bump" not in n.get("ops", []) and n.get("coord") == "uv" and (n.get("uv") or "UV0") == "UV0":
        stem = os.path.splitext(n["image"])[0]
        if os.path.exists(os.path.join(PBR_TEX_DIR, stem + ".png")):
            nimg = n["image"]; ntex = san(stem)[:44]; scale = (float(n["scale"][0]) or 1.0) / (1.0 if name in BASE_UV1 else BASE_SCALE.get(name, (1.0, 1.0))[0])
            pbr_tex_used[ntex] = stem + ".png"
    if ntex is None and n.get("image") and "bump" in n.get("ops", []) and n.get("coord") == "uv" and (n.get("uv") or "UV0") == "UV0":
        # the source feeds a height map through a Bump node: use the normal map made from it (tools/gen_bump_normals.py)
        stem = os.path.splitext(n["image"])[0] + "_bumpn"
        if os.path.exists(os.path.join(PBR_TEX_DIR, stem + ".png")):
            ntex = san(stem)[:44]; scale = (float(n["scale"][0]) or 1.0) / (1.0 if name in BASE_UV1 else BASE_SCALE.get(name, (1.0, 1.0))[0])
            pbr_tex_used[ntex] = stem + ".png"
    r = e.get("Roughness") or {}
    if r.get("image"):
        if r.get("socket") == "Alpha" and m.get("base_image") == r["image"] and cls == "opaque":
            flags |= 1
    elif isinstance(r.get("const"), (int, float)):
        rough = float(r["const"])
    mt = e.get("Metallic") or {}
    if mt.get("image"):
        if nimg and mt["image"] == nimg:
            if mt.get("socket") == "Alpha":
                flags |= 2
            elif "sep.Blue" in mt.get("ops", []):
                flags |= 4
    elif isinstance(mt.get("const"), (int, float)):
        metal = float(mt["const"])
    if any(w_ in name for w_ in GLOSS_SQUARED):
        # the better-lit palace file computes roughness = (1 - smoothness)^2 and has no metallic input on these
        # materials (tools/gloss_group.py); the main scene's graphs give 1 - smoothness and a metallic mask
        flags = (flags & ~6) | 8; metal = 0.0
    return (ntex, round(scale, 3), round(min(max(rough, 0.0), 1.0), 3), round(min(max(metal, 0.0), 1.0), 3), flags)


def material_index(shader, tint, flags=0, pbr=PBR_DEFAULT, tile=None):
    k = (shader, tint, flags)
    kk = (k, pbr, tile)
    if kk not in mat_index:
        mat_index[kk] = len(materials); materials.append(k); mat_pbr[len(materials) - 1] = pbr
        if tile:
            mat_tile[len(materials) - 1] = tile
    return mat_index[kk]


WATER_BASE = tuple(cfg.get("water_base_linear", [0.02, 0.05, 0.05]))      # Theed_Water base colour in the .blend
GLASS_TINT = tuple(cfg.get("glass_tint", [0.70, 0.80, 0.85]))
GLOW_SCALE = float(cfg.get("glow_scale", 0.35))

FOLIAGE_MATS = set()        # engine materials that are leaf cards (cut-out vegetation)
SOLID_TWIN = {}             # cut-out canopy material -> its opaque twin for the lower detail levels
# Materials the export classed as cut-out by their texture, but whose alpha is a constant 1 in the source: the
# source draws them opaque (the big tree canopies are solid cards there). tools/color_graphs.py, cut-out list.
SOLID_CUTOUT = set()
_cg = os.path.join(export_dir, "color_graphs_cutout.json")
if os.path.exists(_cg) and cfg.get("solid_canopy", True):
    for _k, _g in json.load(open(_cg))["materials"].items():
        _a = _g.get("alpha")
        if _a and _a[0] == "const" and isinstance(_a[1], (int, float)) and _a[1] >= 0.999:
            SOLID_CUTOUT.add(_k)
# growth fixed to walls (vines, creepers): the wind sway bends a plant about its base, which tears these off the
# wall they hang on. Materials used only by such meshes get no sway animation.
STILL_MESHES = tuple(cfg.get("no_sway_meshes", ["vine"]))
_still, _moving = set(), set()
for _mk, _mi in scene["meshes"].items():
    (_still if any(w_ in _mk.lower() for w_ in STILL_MESHES) else _moving).update(x for x in (_mi.get("materials") or []) if x)
STILL_MATS = _still - _moving
for name, m in mats.items():
    cls = m.get("cls", "opaque")
    was_cutout = cls == "cutout"
    solid_far = was_cutout and name in SOLID_CUTOUT and m.get("builder", "") in ("canopy", "foliage_card")
    if was_cutout and name in SOLID_CUTOUT and m.get("builder", "") == "props_sss":
        cls = "opaque"; cls_count["cutout_drawn_opaque"] = cls_count.get("cutout_drawn_opaque", 0) + 1
    a = m.get("alpha_source")
    if cls == "cutout" and a and a[1] != "Alpha":
        cls = "opaque"      # "alpha" driven by a colour channel of a packed map: not a real cut-out
    b = m.get("builder", "")
    if name.startswith("FX_"):
        cls = "invisible"        # distant smoke columns and other effect meshes
    if cls != "invisible":
        if b.startswith("falling_water"):
            cls = "foam"
        elif b.startswith(("fountain_water", "bowl_water")):
            cls = "basin"
        elif "water" in b:
            cls = "water"
        elif b == "glass":
            cls = "glass"
        elif b == "emissive_additive":
            cls = "add"
    if any(name.startswith(w_) for w_ in CRYSTAL):
        # chandelier crystals: glass in the palace file, so translucent here (they were opaque white shapes)
        mat_of[name] = material_index(shader_for(None, "glass"), tuple(cfg.get("crystal_color", [1.0, 0.96, 0.88])), 1 | (int(round(float(cfg.get("crystal_opacity", 0.30)) * 255)) << 8))
        cls_count["crystal_glass"] = cls_count.get("crystal_glass", 0) + 1
        continue
    if any(name.startswith(w_) for w_ in GLOW_SOLID):
        # candle flames and similar: the source gives them no usable material; drawn as a plain warm glow
        gname = "textures/naboo/glow_solid"
        shader_text[gname] = "%s\n{\n\tcull none\n\t{\n\t\tmap $whiteimage\n\t\trgbGen identity\n\t}\n}\n" % gname
        mat_of[name] = material_index(gname, tuple(cfg.get("candle_color", [1.0, 0.888, 0.6])), (ANIM_GLOW << 1) | (200 << 8))      # opaque, self-lit
        cls_count["glow_solid"] = cls_count.get("glow_solid", 0) + 1
        continue
    cls_count[cls] = cls_count.get(cls, 0) + 1
    if cls == "invisible":
        mat_of[name] = -1; continue
    flags = 1 if cls in BLEND_KINDS else 0
    if cfg.get("animate", True):
        if cls in ("water", "basin"):
            flags |= ANIM_WATER << 1
        elif cls == "foam":
            flags |= ANIM_FOAM << 1
        elif cls == "glass":
            flags |= ANIM_WINDOW << 1          # panes show daylight to a viewer indoors
        elif b in SWAY_BUILDERS and name in STILL_MATS:
            cls_count["still_plants"] = cls_count.get("still_plants", 0) + 1
        elif b in SWAY_BUILDERS:
            flags |= ANIM_SWAY << 1
        elif any(w_ in name.lower() for w_ in CLOTH_WORDS):
            flags |= ANIM_CLOTH << 1
    if cls == "basin":
        flags |= int(round(0.45 * 255)) << 8       # opacity for the instanced path (bits 8-15)
    elif cls == "glass":
        flags |= int(round(float(cfg.get("glass_opacity", 0.30)) * 255)) << 8      # the source's panes are dark and mirror-like
    img = m.get("base_image")
    tname = None
    if cls == "add":
        e_ = EMIS.get(name, {})
        st_ = e_.get("strength") if isinstance(e_.get("strength"), (int, float)) else 0.0
        img_ = (e_.get("color_image") or [None])[0]
        indoor_ = st_ < GLOW_MIN and any(w_ in name for w_ in GLOW_INDOOR)
        if indoor_:
            st_ = GLOW_INDOOR_STRENGTH          # switched off in the source's daylight scene: lit indoors only
        if st_ < GLOW_MIN:
            cls_count["glow_off"] = cls_count.get("glow_off", 0) + 1
            mat_of[name] = -1; continue
        if img_ and os.path.exists(os.path.join(dump, "textures", os.path.splitext(img_)[0] + ".png")):
            gt = san(os.path.splitext(img_)[0])[:44]
            tex_used[gt] = os.path.splitext(img_)[0] + ".png"
            gname = "textures/naboo/glow_%s" % gt
            if gname not in shader_text:
                shader_text[gname] = "%s\n{\n\tcull none\n\t{\n\t\tmap textures/naboo/%s\n\t\tblendFunc GL_ONE GL_ONE\n\t\trgbGen identity\n\t}\n}\n" % (gname, gt)
            if indoor_:
                # lamp glass of the indoor fixtures: opaque and self-lit, so nothing shows through it
                gname = "textures/naboo/lampglass_%s" % gt
                shader_text[gname] = "%s\n{\n\tcull none\n\t{\n\t\tmap textures/naboo/%s\n\t\trgbGen identity\n\t}\n}\n" % (gname, gt)
            gain_ = min(max(st_ * 0.35, GLOW_GAIN[0]), GLOW_GAIN[1])
            if indoor_:
                mat_of[name] = material_index(gname, tuple(cfg.get("lamp_glass_color", [1.0, 0.86, 0.62])), (ANIM_GLOW << 1) | (200 << 8))
            else:
                mat_of[name] = material_index(gname, tuple(round(c * gain_, 3) for c in GLOW_COLOR), 1 | (ANIM_GLOW << 1))
            cls_count["glow_indoor" if indoor_ else "glow"] = cls_count.get("glow_indoor" if indoor_ else "glow", 0) + 1
            continue
    if cls in ("water", "basin", "foam"):
        if cls == "foam":
            mat_of[name] = material_index(water_shader("foam", *FOAM_TEX["fountain"]), srgb_tint(m.get("tint", [0.85, 0.92, 0.95])), flags)
        else:
            mat_of[name] = material_index(water_shader(cls), srgb_tint(m.get("tint", WATER_BASE)), flags)
        continue
    if img and cls not in ("water", "glass"):
        tname = san(os.path.splitext(img)[0])[:44]
        tex_used[tname] = os.path.splitext(img)[0] + ".png"
    dirt_ = None
    if cls == "blend" and not img and b == "dirt_decal" and m.get("alpha_source"):
        # dirt decals: the source draws a dark colour through the alpha of a packed map. Without a colour
        # texture they came out as white patches; build one with the dirt colour and that alpha.
        from PIL import Image as _Im
        _src = os.path.join(PBR_TEX_DIR, os.path.splitext(m["alpha_source"][0])[0] + ".png")
        if os.path.exists(_src):
            dirt_ = "dd_" + san(os.path.splitext(m["alpha_source"][0])[0])[:40]
            _dst = os.path.join(dump, "extras", dirt_ + ".png")
            if not os.path.exists(_dst):
                _a = np.asarray(_Im.open(_src).convert("RGBA")).copy()
                _a[..., 0] = 46; _a[..., 1] = 38; _a[..., 2] = 31; _a[..., 3] = (_a[..., 3].astype(np.float32) * float(cfg.get("dirt_decal_opacity", 0.45))).astype(np.uint8)
                _Im.fromarray(_a, "RGBA").save(_dst)
            tname = dirt_; tex_used[dirt_] = os.path.join("..", "extras", dirt_ + ".png")
    if cls == "glass":
        tint = GLASS_TINT
    elif cls == "add":
        tint = tuple(round(x * GLOW_SCALE, 3) for x in srgb_tint(m.get("tint", [1, 1, 1])))
    else:
        tint = srgb_tint(m.get("tint", [1, 1, 1] if img else [0.6, 0.6, 0.6]))
    if dirt_:
        tint = (1.0, 1.0, 1.0)
    if cls == "blend" and b == "decal_color" and not img:
        # flat colour decals (the paving inlays): the source mixes them 15 % over the ground (Mix Shader factor of
        # SS_Naboo_DecalColor_01, read with inspect_material.py); the export does not carry that factor
        flags |= int(round(float(cfg.get("decal_color_opacity", 0.15)) * 255)) << 8
    wp_ = WORLD_PROJ.get(name) if cls == "opaque" else None
    if wp_:
        # paving that the source projects from world position (plazas, landings, quays): drawn like the terrain's
        # tiling layer, at the source's repeats per metre, instead of stretched over the mesh's own UVs
        tt = san(os.path.splitext(wp_[0])[0])[:44]; tex_used[tt] = os.path.splitext(wp_[0])[0] + ".png"
        tex_used["gnd_flat"] = os.path.join("..", "extras", "gnd_flat.png")
        mat_of[name] = material_index(shader_for("gnd_flat", "opaque"), (1.0, 1.0, 1.0), flags, (None, 1.0, 0.85, 0.0, 0), (tt, int(round(wp_[1] * 256.0)), 255))
        cls_count["world_projected"] = cls_count.get("world_projected", 0) + 1
        continue
    bk = BAKED.get(name) if cls == "opaque" else None
    if bk:
        tname = bk["tex"]; tex_used[tname] = os.path.join("..", "baked", bk["tex"] + ".png")
        pb = pbr_of(name, m, cls)
        if bk.get("roughness_baked"):
            pb = (pb[0], pb[1], pb[2], pb[3], pb[4] | 1)        # roughness = 1 - alpha of the baked map
        else:
            pb = (pb[0], pb[1], pb[2], pb[3], pb[4] & ~1)
        tl = None
        if bk.get("tile"):
            tt = san(bk["tile"])[:44]; tex_used[tt] = bk["tile"] + ".png"
            _per = int(bk.get("uv_period", 1))
            tl = (tt, int(round(bk["tile_scale"][0] * _per)), int(round(bk["tile_scale"][1] * _per)))
        mat_of[name] = material_index(shader_for(tname, cls), (1.0, 1.0, 1.0), flags, pb, tl)
        cls_count["baked"] = cls_count.get("baked", 0) + 1
        continue
    mat_of[name] = material_index(shader_for(tname, cls), tint, flags, pbr_of(name, m, "cutout" if was_cutout else cls))
    if was_cutout and b in SWAY_BUILDERS:
        FOLIAGE_MATS.add(mat_of[name])
    if solid_far:
        # the source draws these canopy cards opaque. Up close that reads as flat polygons in the port, so the
        # nearest detail level keeps the cut-out and the lower ones use an opaque twin of the material.
        SOLID_TWIN[mat_of[name]] = material_index(shader_for(tname, "opaque"), tint, flags, pbr_of(name, m, "cutout"))
        cls_count["canopy_solid_at_distance"] = cls_count.get("canopy_solid_at_distance", 0) + 1
NOMAT = material_index(shader_for(None, "opaque"), (0.75, 0.75, 0.75))
bake_info = None
bj = os.path.join(dump, "extras", "terrain_bake.json")
TERRAIN_Q = {}
if os.path.exists(bj) and cfg.get("terrain_bake", True):
    bake_info = json.load(open(bj))
    for ty in range(2):
        for tx in range(2):
            tn = "terrain_bake_%d%d" % (tx, ty)
            if os.path.exists(os.path.join(dump, "extras", tn + ".png")):
                tex_used[tn] = os.path.join("..", "extras", tn + ".png")
                span_m = (bake_info["bounds_m"][2] - bake_info["bounds_m"][0]) / 2.0
                drep = int(round(span_m / float(cfg.get("ground_detail_repeat_m", 2.0)))) if HAS_DETAIL else 0
                TERRAIN_Q[(tx, ty)] = material_index(shader_for(tn, "opaque", drep), (1.0, 1.0, 1.0), drep << 16)
TERRAIN = material_index(shader_for(None, "opaque"), (0.66, 0.64, 0.58))
WATER_MAT = material_index(water_shader("water"), srgb_tint(WATER_BASE), (ANIM_WATER << 1))
FALLS_MAT = material_index(water_shader("foam", *FOAM_TEX["waterfall"]), srgb_tint([0.85, 0.92, 0.95]), 1 | (ANIM_FOAM << 1))

FAR_TERRAIN = None
ftj = os.path.join(dump, "extras", "terrain_far.json")
if cfg.get("far_scenery", True) and os.path.exists(ftj):
    if os.path.exists(os.path.join(dump, "extras", "terrain_far_bake.png")):
        fb = json.load(open(ftj))["bounds_m"]
        tex_used["terrain_far_bake"] = "terrain_far_bake.png"
        frep = int(round((fb[2] - fb[0]) / float(cfg.get("far_detail_repeat_m", 6.0)))) if HAS_DETAIL else 0
        FAR_TERRAIN = material_index(shader_for("terrain_far_bake", "opaque", frep), (1.0, 1.0, 1.0), frep << 16)
    else:
        FAR_TERRAIN = material_index(shader_for(None, "opaque"), (0.45, 0.55, 0.35))

# ---- geometry
V = []; I = []; meshes = []; subs = []
mesh_id = {}
nv_tot = ni_tot = 0
stats = {"loops_in": 0, "tris_lod0": 0, "tris_lod1": 0, "tris_lod2": 0, "tris_dropped": 0}


uv1_stats = {"meshes": 0, "triangles": 0}
UV2 = {}                # mesh index -> second UV set of all its vertices (for normal maps)


def weld_dump(a, slot_names=None):
    lv = a["loop_vert"].astype(np.int64); ln = a["loop_normal"]
    uv = a["uv0"] if "uv0" in a.files else np.zeros((len(lv), 2), np.float32)
    uv0 = uv; swapped = None
    if slot_names and "uv1" in a.files and BASE_UV1:
        use1 = np.array([(sn in BASE_UV1) for sn in slot_names] + [False], bool)
        tm = use1[np.clip(a["tri_mat"].astype(np.int64), 0, len(use1) - 1)]
        if tm.any():
            uv = uv.copy(); loops = a["tri_loops"][tm].ravel()
            uv[loops] = a["uv1"][loops]
            swapped = loops
            uv1_stats["meshes"] += 1; uv1_stats["triangles"] += int(tm.sum())
    if slot_names and BASE_SCALE:
        tmi = np.clip(a["tri_mat"].astype(np.int64), 0, len(slot_names))
        for si, sn in enumerate(slot_names):
            if sn in BASE_SCALE:
                loops = a["tri_loops"][tmi == si].ravel()
                if len(loops):
                    uv = uv.copy(); uv[loops] = (uv[loops] - np.array(BASE_OFFSET.get(sn, (0.0, 0.0)), np.float32)) * np.array(BASE_SCALE[sn], np.float32)
                    uv1_stats["scaled_triangles"] = uv1_stats.get("scaled_triangles", 0) + len(loops) // 3
    two = bool(slot_names) and any(sn in BASE_UV1 for sn in slot_names if sn)
    if two:
        # second set for the normal map: UV0 where the colour took UV1, otherwise the same coordinates
        uv_b = np.array(uv, np.float32, copy=True)
        if swapped is not None:
            uv_b[swapped] = uv0[swapped]
    key = np.empty((len(lv), 8 if two else 6), np.int64)
    key[:, 0] = lv; key[:, 1:4] = np.round(ln * 127.0); key[:, 4:6] = np.round(uv * 8192.0)
    if two:
        key[:, 6:8] = np.round(uv_b * 8192.0)
    uq, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    pos = (a["pos"][lv[first]].astype(np.float64) * UPM).astype(np.float32)
    st = uv[first].copy(); st[:, 1] = 1.0 - st[:, 1]      # Blender V is bottom-up
    if two:
        st2 = uv_b[first].copy(); st2[:, 1] = 1.0 - st2[:, 1]
        st = np.concatenate([st, st2], 1)                 # four columns: add_mesh writes the last two to the .tuv2 file
    return pos, ln[first], st, inv[a["tri_loops"]], len(lv)


VCOL_CACHE = {}


def apply_vcol(mesh_name, a, pos_units, nrm):
    """Foam meshes: store the mesh's vertex-colour fade (red of Color0, exported by export_water_colors.py) in the
    length of the normal, 0.25 (fully faded) .. 1.0. The vertex shader normalises normals, so nothing else changes."""
    fn = os.path.join(dump, "extras", "vcol_%s.npz" % san(mesh_name))
    if not os.path.exists(fn):
        return nrm, 0
    if fn not in VCOL_CACHE:
        v = np.load(fn)
        VCOL_CACHE[fn] = {tuple(k): float(r) for k, r in zip(np.round(v["pos"].astype(np.float64) * 1000).astype(np.int64).tolist(), v["r"].tolist())}
    tab = VCOL_CACHE[fn]
    keys = np.round(pos_units.astype(np.float64) / UPM * 1000).astype(np.int64).tolist()
    r = np.array([tab.get(tuple(k), -1.0) for k in keys])
    hit = int((r >= 0).sum()); r[r < 0] = 1.0
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    return (nrm / np.maximum(ln, 1e-9) * (0.25 + 0.75 * r[:, None])).astype(np.float32), hit


vcol_stats = {}


def add_mesh(name, lods):
    """lods: list of (pos, nrm, st, tris, tri_mat_index) ; tri_mat_index < 0 drops the triangle"""
    global nv_tot, ni_tot
    vparts = []; iparts = []; lod_first = []; lod_num = []; uv2parts = []; has_uv2 = False
    vbase = 0; ibase = 0; allpos = []
    for li, (pos, nrm, st, tris, tk) in enumerate(lods):
        keep = tk >= 0
        if li == 0:
            stats["tris_dropped"] += int((~keep).sum())
        tris = tris[keep]; tk = tk[keep]
        if len(tris) == 0:
            if li == 0:
                return False
            break
        order = np.argsort(tk, kind="stable"); tris = tris[order]; tk = tk[order]
        used = np.unique(tris); remap = np.full(len(pos), -1, np.int64); remap[used] = np.arange(len(used))
        pos = pos[used]; nrm = nrm[used]; st = st[used]; tris = remap[tris] + vbase
        cuts = np.flatnonzero(np.diff(tk)) + 1
        starts = np.concatenate([[0], cuts]); ends = np.concatenate([cuts, [len(tris)]])
        lod_first.append(len(subs))
        for s, e in zip(starts, ends):
            subs.append((int(tk[s]), int(ibase + s * 3), int((e - s) * 3)))
        lod_num.append(len(subs) - lod_first[-1])
        vert = np.zeros(len(pos), dtype=[("xyz", "<f4", 3), ("n", "<f4", 3), ("st", "<f4", 2)])
        vert["xyz"] = pos; vert["n"] = nrm; vert["st"] = st[:, :2]
        uv2parts.append(np.asarray(st[:, -2:], "<f4")); has_uv2 = has_uv2 or st.shape[1] == 4
        vparts.append(vert); iparts.append(tris.astype("<u4").ravel())
        vbase += len(pos); ibase += tris.size
        stats["tris_lod%d" % li] += len(tris)
        if li == 0:
            allpos = pos
    c = (allpos.min(0) + allpos.max(0)) / 2; r = float(np.linalg.norm(allpos - c, axis=1).max())
    V.extend(vparts); I.extend(iparts)
    mesh_id[name] = len(meshes)
    if has_uv2:
        UV2[len(meshes)] = np.concatenate(uv2parts)
    nl = len(lod_first)
    meshes.append({"fv": nv_tot, "nv": vbase, "fi": ni_tot, "ni": ibase, "nl": nl,
                   "lf": lod_first + [0] * (3 - nl), "ln": lod_num + [0] * (3 - nl), "c": c.astype(np.float32), "r": r,
                   "lod0_tris": int(iparts[0].size // 3), "lod_tris": [int(x.size // 3) for x in iparts], "subs0": lod_num[0]})
    nv_tot += vbase; ni_tot += ibase
    return True


# Leaf cards do not survive mesh decimation: the generated detail levels of trees lose most of their canopy.
# For the lower detail levels of foliage, a share of the cards is kept and each kept card is enlarged about its
# centre by 1 / sqrt(share), which keeps the covered area; trunks and other parts still come from the decimated
# mesh. Cards are taken as consecutive triangle pairs.
FOLIAGE_KEEP = cfg.get("foliage_lod_keep", [0.40, 0.12])
foliage_stats = {"meshes": 0, "cards_lod0": 0, "cards_lod1": 0, "cards_lod2": 0}


def foliage_lod(lod0, lodk, keep, seed, solid=False):
    pos, nrm, st, tris, tk = lod0
    fol = np.isin(tk, list(FOLIAGE_MATS))
    ft = tris[fol]; ftk = tk[fol]
    unit = np.arange(len(ft)) // 2
    nu = int(unit.max()) + 1 if len(ft) else 0
    rng = np.random.default_rng(seed)
    pick = rng.random(nu) < keep
    if nu and not pick.any():
        pick[rng.integers(nu)] = True
    sel = pick[unit]
    kt = ft[sel]; ku = unit[sel]
    vp = pos[kt].astype(np.float64)                         # (T,3,3): every kept triangle gets its own corners
    cen = np.zeros((nu, 3)); cnt = np.zeros(nu)
    np.add.at(cen, ku, vp.sum(1)); np.add.at(cnt, ku, 3.0)
    cen = cen / np.maximum(cnt, 1.0)[:, None]
    sc = 1.0 / np.sqrt(keep)
    vp = cen[ku][:, None, :] + (vp - cen[ku][:, None, :]) * sc
    fpos = vp.reshape(-1, 3).astype(np.float32); fnrm = nrm[kt].reshape(-1, 3); fst = st[kt].reshape(-1, st.shape[1])
    ftri = np.arange(len(kt) * 3, dtype=np.int64).reshape(-1, 3)
    if lodk is not None:
        kpos, knrm, kst, ktris, ktk = lodk
        other = ~np.isin(ktk, list(FOLIAGE_MATS))
    else:
        kpos, knrm, kst, ktris, ktk = pos, nrm, st, tris, tk
        other = ~fol
    otris = ktris[other]; otk = ktk[other]
    used = np.unique(otris) if len(otris) else np.zeros(0, np.int64)
    remap = np.full(len(kpos), -1, np.int64); remap[used] = np.arange(len(used))
    npos = np.concatenate([kpos[used], fpos]); nnrm = np.concatenate([knrm[used], fnrm]); nst = np.concatenate([kst[used], fst])
    ntris = np.concatenate([remap[otris], ftri + len(used)]) if len(otris) else ftri + len(used)
    fk = np.array([SOLID_TWIN.get(int(x), int(x)) for x in ftk[sel]], np.int64) if (SOLID_TWIN and solid) else ftk[sel]
    ntk = np.concatenate([otk, fk]) if len(otris) else fk
    return (npos, nnrm, nst, ntris, ntk), nu, int(pick.sum())


def build_scene_mesh(name, info, mat_names, out_name):
    """one source mesh with the given material per slot -> a cooked mesh called out_name"""
    slot = np.array([(mat_of.get(mn, NOMAT) if mn else NOMAT) for mn in (mat_names)] + [NOMAT], dtype=np.int64)
    lods = []
    for fn in [info["file"]] + list(info.get("lods", [])):
        a = np.load(os.path.join(dump, "meshes", fn))
        if len(a["tri_loops"]) == 0:
            continue
        pos, nrm, st, tris, nl = weld_dump(a, mat_names)
        nrm, hit_ = apply_vcol(name, a, pos, nrm)
        if hit_:
            vcol_stats[name] = vcol_stats.get(name, 0) + hit_
        if not lods:
            stats["loops_in"] += nl
        tk = slot[np.clip(a["tri_mat"].astype(np.int64), 0, len(slot) - 1)]
        lods.append((pos, nrm, st, tris, tk))
    if lods and FOLIAGE_MATS and cfg.get("foliage_lods", True) and np.isin(lods[0][4], list(FOLIAGE_MATS)).sum() >= 8:
        new = [lods[0]]
        for li_, keep_ in enumerate(FOLIAGE_KEEP[:2]):
            # only the farthest level uses the opaque canopy twin: smaller trees reach the middle level a few metres away
            lk_, nu_, kept_ = foliage_lod(lods[0], lods[li_ + 1] if len(lods) > li_ + 1 else None, float(keep_), len(meshes) * 7 + li_, solid=(li_ == 1))
            new.append(lk_)
            foliage_stats["cards_lod%d" % (li_ + 1)] += kept_
            if li_ == 0:
                foliage_stats["cards_lod0"] += nu_
        foliage_stats["meshes"] += 1
        lods = new
    if lods:
        add_mesh(out_name, lods[:3])


for name, info in scene["meshes"].items():
    build_scene_mesh(name, info, info["materials"] or [None], name)
# objects whose material slots differ from their mesh's (the red market awnings, the individual paintings,
# banners, curtains): one variant of the mesh per distinct material list
VARIANT_OF = {}
_variants = {}
for _on, _ov in OBJ_OVERRIDE.items():
    _mk = _ov["mesh"]
    if _mk not in scene["meshes"] or any(_m and mat_of.get(_m) is None for _m in _ov["object"]):
        continue
    _key = (_mk, tuple(_ov["object"]))
    if _key not in _variants:
        _vn = "%s#%d" % (_mk, len(_variants))
        build_scene_mesh(_mk, scene["meshes"][_mk], list(_ov["object"]) or [None], _vn)
        _variants[_key] = _vn if _vn in mesh_id else None
    if _variants[_key]:
        VARIANT_OF[_on] = _variants[_key]
# palace windows (export/palace_windows.json, classified from the collision: is there a roof on both sides of the
# pane?). Panes that look outside imitate daylight indoors (the glass material's window animation). Panes between
# two rooms, the windows that stand open and the chandeliers' glass are ordinary clear glass instead.
_pw = os.path.join(export_dir, "palace_windows.json")
if os.path.exists(_pw) and cfg.get("palace_clear_windows", True):
    CLEAR_MESHES = tuple(cfg.get("clear_glass_meshes", ["o_nab_palacewindow_open", "o_nab_palace_chandelier"]))
    for _w in json.load(open(_pw)):
        _mk = _w["mesh"]
        if not (_w["inner"] or _mk.startswith(CLEAR_MESHES)) or _mk not in scene["meshes"]:
            continue
        _names = list(scene["meshes"][_mk]["materials"] or [None])
        _new = []
        for _mn in _names:
            if _mn and mats.get(_mn, {}).get("builder") == "glass" and mat_of.get(_mn, -1) >= 0:
                _cn = _mn + "#clear"
                if _cn not in mat_of:
                    mat_of[_cn] = material_index(shader_for(None, "glass"), (0.80, 0.86, 0.86), 1 | (int(round(0.14 * 255)) << 8))
                _new.append(_cn)
            else:
                _new.append(_mn)
        _key = (_mk, tuple(_new))
        if _key not in _variants:
            _vn = "%s#%d" % (_mk, len(_variants))
            build_scene_mesh(_mk, scene["meshes"][_mk], _new, _vn)
            _variants[_key] = _vn if _vn in mesh_id else None
        if _variants[_key]:
            VARIANT_OF[_w["name"]] = _variants[_key]

# ---- instances
inst = []
skipped_inst = 0
# opening doors are game entities (tools/build_doors.py), not part of the static world
_dj = os.path.join(export_dir, "doors.json")
DOOR_SKIP = set(json.load(open(_dj))["skip_instances"]) if os.path.exists(_dj) and cfg.get("doors_enabled", True) else set()
for o in scene["instances"]:
    mid = mesh_id.get(VARIANT_OF.get(o.get("name"), o["mesh"]))
    if mid is None or o.get("name") in DOOR_SKIP:
        skipped_inst += 1; continue
    M = np.array(o["matrix"], dtype=np.float64)
    R = M[:3, :3]; t = (M[:3, 3] - ORG) * UPM
    c = R @ meshes[mid]["c"].astype(np.float64) + t; r = meshes[mid]["r"] * float(np.linalg.norm(R, axis=0).max())
    inst.append((mid, np.concatenate([R[0], [t[0]], R[1], [t[1]], R[2], [t[2]]]).astype(np.float32), c.astype(np.float32), r))
# ---- terrain scatter (tools/export_scatter.py): leaf litter, twigs ... placed by geometry nodes in the source.
# Only source meshes whose materials are all known are added, as ordinary placements of one shared mesh; their
# lower detail levels keep a share of the cards (they are small, so the renderer uses those from a few metres on).
scatter_stats = {"added": {}, "chunked": {}, "skipped_unknown_material": {}}
SC_MAX_TRIS = int(cfg.get("scatter_chunk_max_tris", 16))        # meshes up to this size are merged into chunks
SC_CELL = {"Terrain_Near": float(cfg.get("scatter_chunk_near_m", 64.0)), "Terrain_Far": float(cfg.get("scatter_chunk_far_m", 512.0))}
SC_KEEP0 = {"Terrain_Near": 1.0, "Terrain_Far": float(cfg.get("scatter_far_keep", 0.25))}     # far: fewer, larger plants
SC_LOD_KEEP = cfg.get("scatter_chunk_lod_keep", [0.4, 0.15])
static_twin = {}


def static_material(mi):
    """the same material without the sway animation: a merged chunk has no single plant base to sway about"""
    if mi not in static_twin:
        sh_, ti_, fl_ = materials[mi]
        static_twin[mi] = material_index(sh_, ti_, fl_ & ~(7 << 1), mat_pbr.get(mi, PBR_DEFAULT)) if (fl_ >> 1) & 7 == ANIM_SWAY else mi
    return static_twin[mi]


billboard_twin = {}
BILLBOARD_MESHES = tuple(cfg.get("billboard_meshes", ["ms_naboobase_backdroptree", "ms_naboobase_backdropbush"]))


def billboard_material(mi):
    """the same material drawn as a camera-facing billboard (animation type 6)"""
    if mi not in billboard_twin:
        sh_, ti_, fl_ = materials[mi]
        billboard_twin[mi] = material_index(sh_, ti_, (fl_ & ~(7 << 1)) | (ANIM_BILLBOARD << 1), mat_pbr.get(mi, PBR_DEFAULT))
    return billboard_twin[mi]


def scatter_chunks(it, pos, nrm, st, tris, tk):
    Ms = np.load(os.path.join(dump, "scatter", "scatter_%d.npy" % it["index"])).reshape(-1, 3, 4).astype(np.float64)
    cell_m = SC_CELL.get(it["parent"], 64.0); keep0 = SC_KEEP0.get(it["parent"], 1.0)
    rng = np.random.default_rng(4242 + it["index"])
    if keep0 < 1.0:
        Ms = Ms[rng.random(len(Ms)) < keep0]
    bill = it["mesh"].startswith(BILLBOARD_MESHES) and cfg.get("billboards", True)
    tk = np.array([(billboard_material(int(x)) if bill else static_material(int(x))) for x in tk], np.int64)
    max_off = 0.0
    cx = np.floor(Ms[:, 0, 3] / cell_m).astype(np.int64); cy = np.floor(Ms[:, 1, 3] / cell_m).astype(np.int64)
    key = cx * 100003 + cy
    order = np.argsort(key, kind="stable"); Ms = Ms[order]; key = key[order]
    cuts = np.flatnonzero(np.diff(key)) + 1
    starts = np.concatenate([[0], cuts]); ends = np.concatenate([cuts, [len(key)]])
    P64 = pos.astype(np.float64); nv = len(pos); n_chunks = 0; n_inst = 0; n_tris = 0
    base_scale = 1.0 / np.sqrt(keep0)
    for a_, b_ in zip(starts, ends):
        Mc = Ms[a_:b_]
        org = (Mc[:, :, 3].mean(0) - ORG) * UPM
        lods_ = []
        for li_, keep_ in enumerate([1.0] + [float(k_) for k_ in SC_LOD_KEEP[:2]]):
            sel_ = Mc if keep_ >= 1.0 else Mc[rng.random(len(Mc)) < keep_]
            if len(sel_) == 0:
                sel_ = Mc[:1]
            sc_ = base_scale / np.sqrt(keep_)
            R = sel_[:, :, :3]; t = (sel_[:, :, 3] - ORG) * UPM - org
            Pw = np.einsum("nij,vj->nvi", R * sc_, P64) + t[:, None, :]
            Nw = np.einsum("nij,vj->nvi", R, nrm.astype(np.float64))
            Nw /= np.maximum(np.linalg.norm(Nw, axis=2, keepdims=True), 1e-9)
            n_ = len(sel_)
            T_ = (tris[None, :, :] + (np.arange(n_, dtype=np.int64) * nv)[:, None, None]).reshape(-1, 3)
            if bill:
                # billboard: every vertex sits at its plant's base (plus its height); the offset in the card's own
                # frame goes to the second UV set and the renderer turns the card towards the camera
                s_ = np.linalg.norm(R[:, :, 0], axis=1) * sc_
                Pw = np.repeat(t[:, None, :], nv, 1).copy(); Pw[:, :, 2] += s_[:, None] * P64[None, :, 2]
                off_ = (s_[:, None, None] * P64[None, :, :2]).reshape(-1, 2)
                max_off = max(max_off, float(np.abs(off_).max()))
                st_ = np.concatenate([np.tile(st[:, :2], (n_, 1)), off_.astype(np.float32)], 1)
                lods_.append((Pw.reshape(-1, 3).astype(np.float32), np.tile(nrm, (n_, 1)).astype(np.float32), st_, T_, np.tile(tk, n_)))
            else:
                lods_.append((Pw.reshape(-1, 3).astype(np.float32), Nw.reshape(-1, 3).astype(np.float32), np.tile(st, (n_, 1)), T_, np.tile(tk, n_)))
            if li_ == 0:
                n_tris += len(T_)
        mname = "__scatterchunk_%d_%d" % (it["index"], n_chunks)
        if add_mesh(mname, lods_):
            mid = mesh_id[mname]
            meshes[mid]["r"] += max_off * 1.5            # the cards reach beyond the plant bases the sphere was built from
            inst.append((mid, np.array([1, 0, 0, org[0], 0, 1, 0, org[1], 0, 0, 1, org[2]], np.float32),
                         (meshes[mid]["c"].astype(np.float64) + org).astype(np.float32), meshes[mid]["r"]))
            n_chunks += 1; n_inst += len(Mc)
    scatter_stats["chunked"]["%s on %s" % (it["mesh"], it["parent"])] = {"instances": int(n_inst), "chunks": int(n_chunks), "tris_lod0": int(n_tris)}

sj_ = os.path.join(dump, "scatter", "scatter.json")
if os.path.exists(sj_) and cfg.get("scatter", True):
    for it in json.load(open(sj_))["items"]:
        mnames = [mn for mn in it["materials"] if mn]
        if not mnames or any(mat_of.get(mn, -1) < 0 for mn in mnames):
            scatter_stats["skipped_unknown_material"][it["mesh"]] = it["instances"]; continue
        a = np.load(os.path.join(dump, "scatter", "scatter_mesh_%d.npz" % it["index"]))
        if len(a["tri_loops"]) == 0:
            continue
        pos, nrm, st, tris, nl = weld_dump(a, it["materials"])
        slot = np.array([mat_of.get(mn, NOMAT) if mn else NOMAT for mn in it["materials"]] + [NOMAT], dtype=np.int64)
        tk = slot[np.clip(a["tri_mat"].astype(np.int64), 0, len(slot) - 1)]
        if len(tris) <= SC_MAX_TRIS:
            scatter_chunks(it, pos, nrm, st, tris, tk)
            continue
        if it["parent"] != "Terrain_Near":
            continue
        lod0 = (pos, nrm, st, tris, tk)
        saved = set(FOLIAGE_MATS); FOLIAGE_MATS.update(int(x) for x in np.unique(tk))
        lods_ = [lod0]
        for li_, keep_ in enumerate(cfg.get("scatter_lod_keep", [0.25, 0.06])):
            lods_.append(foliage_lod(lod0, None, float(keep_), 977 + it["index"] * 3 + li_)[0])
        FOLIAGE_MATS.clear(); FOLIAGE_MATS.update(saved)
        mname = "__scatter_%d_%s" % (it["index"], it["mesh"])
        if not add_mesh(mname, lods_):
            continue
        mid = mesh_id[mname]
        Ms = np.load(os.path.join(dump, "scatter", "scatter_%d.npy" % it["index"])).reshape(-1, 3, 4).astype(np.float64)
        for M in Ms:
            R = M[:3, :3]; t = (M[:3, 3] - ORG) * UPM
            c = R @ meshes[mid]["c"].astype(np.float64) + t; r = meshes[mid]["r"] * float(np.linalg.norm(R, axis=0).max())
            inst.append((mid, np.concatenate([R[0], [t[0]], R[1], [t[1]], R[2], [t[2]]]).astype(np.float32), c.astype(np.float32), r))
        scatter_stats["added"][it["mesh"]] = {"instances": int(len(Ms)), "tris": [int(x) for x in meshes[mid]["lod_tris"]]}
n_obj_inst = len(inst)

# ---- water must stay visible: carve the terrain under it
# tools/water_check.py --save rasterises the water meshes on a 2 m grid (dump/extras/water_height.npz).
WATER = None
wp_ = os.path.join(dump, "extras", "water_height.npz")
if os.path.exists(wp_) and cfg.get("carve_water", True):
    w_ = np.load(wp_)
    WATER = (w_["water"].astype(np.float64), float(w_["x0"]), float(w_["y0"]), float(w_["cell"]))
carve_stats = {}
WATER_FILL = None       # (mask of generated cells, heights)
if WATER is not None and float(cfg.get("water_gap_m", 16.0)) > 0:
    # The source water is a set of patches that do not quite meet: thin dry slits cross the rivers.
    # Morphological closing of the water raster: dilate by half the gap width carrying the surface height
    # along, erode back, and keep the cells that were dry before. They become generated water.
    wr_ = WATER[0]; rcells = max(1, int(round(float(cfg.get("water_gap_m", 16.0)) / 2.0 / WATER[3])))
    mask0 = ~np.isnan(wr_)
    zsum = np.where(mask0, wr_, 0.0); cnt = mask0.astype(np.float64); m = mask0.copy()
    for _ in range(rcells):
        zs = zsum.copy(); cs = cnt.copy(); mm = m.copy()
        for sl_a, sl_b in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))), ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                           ((slice(None), slice(1, None)), (slice(None), slice(None, -1))), ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
            add = m[sl_b] & ~m[sl_a]
            zs[sl_a] += np.where(add, zsum[sl_b] / np.maximum(cnt[sl_b], 1e-9), 0.0); cs[sl_a] += add; mm[sl_a] |= m[sl_b]
        new = mm & ~m
        zsum = np.where(new, zs, zsum); cnt = np.where(new, cs, cnt)
        zsum = np.where(new, zsum / np.maximum(cnt, 1e-9), zsum); cnt = np.where(new, 1.0, cnt)
        m = mm
    er = m.copy()
    for _ in range(rcells):
        e2 = er.copy()
        e2[1:, :] &= er[:-1, :]; e2[:-1, :] &= er[1:, :]; e2[:, 1:] &= er[:, :-1]; e2[:, :-1] &= er[:, 1:]
        er = e2
    fill = er & ~mask0
    zfill = zsum / np.maximum(cnt, 1e-9)
    wr_[fill] = zfill[fill]
    WATER_FILL = (fill, zfill)
    carve_stats["gap_fill"] = {"gap_m": float(cfg.get("water_gap_m", 16.0)), "cells_added": int(fill.sum()), "area_m2": float(fill.sum() * WATER[3] ** 2),
                               "source_cells": int(mask0.sum())}


def close_water_gaps(wr_, rcells):
    """morphological closing of the water raster, carrying the surface height: returns (new cells, heights)"""
    mask0 = ~np.isnan(wr_)
    zsum = np.where(mask0, wr_, 0.0); cnt = mask0.astype(np.float64); m = mask0.copy()
    for _ in range(rcells):
        zs = np.zeros_like(zsum); cs = np.zeros_like(cnt); mm = m.copy()
        for sl_a, sl_b in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))), ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                           ((slice(None), slice(1, None)), (slice(None), slice(None, -1))), ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
            add = m[sl_b] & ~m[sl_a]
            zs[sl_a] += np.where(add, zsum[sl_b], 0.0); cs[sl_a] += add; mm[sl_a] |= m[sl_b]
        new = mm & ~m
        zsum = np.where(new, zs / np.maximum(cs, 1.0), zsum)
        m = mm
    er = m.copy()
    for _ in range(rcells):
        e2 = er.copy()
        e2[1:, :] &= er[:-1, :]; e2[:-1, :] &= er[1:, :]; e2[:, 1:] &= er[:, :-1]; e2[:, :-1] &= er[:, 1:]
        er = e2
    return er & ~mask0, zsum


FAR_GAP = float(cfg.get("far_water_gap_m", 56.0))
tg_ = os.path.join(dump, "meshes", "terrain_grid.npz")
if WATER is not None and WATER_FILL is not None and FAR_GAP > float(cfg.get("water_gap_m", 16.0)):
    # Outside the city the river patches are further apart. Close wider gaps there, but not inside the near
    # terrain, where a wide closing would flood islands and quays.
    wr_ = WATER[0]
    fill2, z2 = close_water_gaps(wr_, max(1, int(round(FAR_GAP / 2.0 / WATER[3]))))
    if os.path.exists(tg_):
        gn_ = np.load(tg_)["grid"]
        nb_ = (float(gn_[0, 0, 0]), float(gn_[0, 0, 1]), float(gn_[-1, -1, 0]), float(gn_[-1, -1, 1]))
        xs_ = WATER[1] + np.arange(wr_.shape[1]) * WATER[3]; ys_ = WATER[2] + np.arange(wr_.shape[0]) * WATER[3]
        in_near_ = ((ys_ > nb_[1]) & (ys_ < nb_[3]))[:, None] & ((xs_ > nb_[0]) & (xs_ < nb_[2]))[None, :]
        fill2 &= ~in_near_
    wr_[fill2] = z2[fill2]
    WATER_FILL = (WATER_FILL[0] | fill2, np.where(fill2, z2, WATER_FILL[1]))
    carve_stats["gap_fill_far"] = {"gap_m": FAR_GAP, "cells_added": int(fill2.sum()), "area_m2": float(fill2.sum() * WATER[3] ** 2)}


def _bilinear_z(g, X, Y):
    gx0, gy0 = g[0, 0, 0], g[0, 0, 1]; dx = g[0, 1, 0] - g[0, 0, 0]; dy = g[1, 0, 1] - g[0, 0, 1]
    fx = (X - gx0) / dx; fy = (Y - gy0) / dy
    inside = (fx >= 0) & (fx <= g.shape[1] - 1) & (fy >= 0) & (fy <= g.shape[0] - 1)
    ix = np.clip(np.floor(fx).astype(np.int64), 0, g.shape[1] - 2); iy = np.clip(np.floor(fy).astype(np.int64), 0, g.shape[0] - 2)
    tx = np.clip(fx - ix, 0, 1); ty = np.clip(fy - iy, 0, 1)
    z = g[iy, ix, 2] * (1 - tx) * (1 - ty) + g[iy, ix + 1, 2] * tx * (1 - ty) + g[iy + 1, ix, 2] * (1 - tx) * ty + g[iy + 1, ix + 1, 2] * tx * ty
    return z, inside


def carve_under_water(g, reach_m, label, exclude=None, tol=None):
    """Lower grid vertices to water level - depth wherever water is visible there, i.e. the water surface is
    above the terrain or within the tolerance below it. reach_m > 0 also carves vertices within that distance
    of visible water (a coarse grid cannot resolve a narrow river). Returns the mask of carved vertices."""
    carved = np.zeros(g.shape[:2], bool)
    if WATER is None:
        return carved
    wr, wx0, wy0, wc = WATER
    tol = float(cfg.get("water_carve_tolerance_m", 0.3)) if tol is None else tol
    depth = float(cfg.get("water_carve_depth_m", 1.0))
    jj, ii = np.nonzero(~np.isnan(wr))
    X = wx0 + ii * wc; Y = wy0 + jj * wc; wz = wr[jj, ii]
    tz, inside = _bilinear_z(g, X, Y)
    if exclude is not None:
        inside &= ~((X > exclude[0]) & (X < exclude[2]) & (Y > exclude[1]) & (Y < exclude[3]))
    vis = inside & (wz - tz > -tol)
    if WATER_FILL is not None:
        # generated water (gap fill) used to be forced visible, which dug trenches through roads and gardens
        # where the source's water runs under the ground; it now follows the same rule as the source's water
        pass
    n_in = int(inside.sum()); hidden_before = int((inside & (wz - tz <= 0)).sum()); shallow = int((vis & (wz - tz < depth)).sum())
    vr = np.full(wr.shape, np.nan); vr[jj[vis], ii[vis]] = wz[vis]          # visible water surface height
    reach = int(round(reach_m / wc))
    ix = np.rint((g[:, :, 0] - wx0) / wc).astype(np.int64); iy = np.rint((g[:, :, 1] - wy0) / wc).astype(np.int64)
    best = np.full(g.shape[:2], np.nan)
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            jx = ix + dx; jy = iy + dy
            ok = (jx >= 0) & (jx < wr.shape[1]) & (jy >= 0) & (jy < wr.shape[0])
            v = np.full(g.shape[:2], np.nan); v[ok] = vr[jy[ok], jx[ok]]
            best = np.where(np.isnan(best), v, np.where(np.isnan(v), best, np.minimum(best, v)))
    carved = ~np.isnan(best)
    target = best - depth
    lower = carved & (g[:, :, 2] > target)
    g[:, :, 2][lower] = target[lower]
    tz2, _ = _bilinear_z(g, X, Y)
    carve_stats[label] = {"water_samples": n_in, "visible_before": int(vis.sum()), "visible_but_shallower_than_depth": shallow,
                          "vertices_lowered": int(lower.sum()), "visible_water_still_under_terrain": int((vis & (wz - tz2 <= 0)).sum())}
    return carved


# ---- terrain: tiles of a height grid, several strides as detail levels
IDENT = np.array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0], np.float32)
terrain_tiles = 0


def build_terrain(g, tile, strides, mat_for_tile, uv_for_tile, prefix, hole=None, carved=None):
    """g: (side, side, 3) metres indexed [y][x]. hole = (x0, y0, x1, y1) metres: triangles entirely inside are left out."""
    side = g.shape[0]
    dzdx = np.gradient(g[:, :, 2], axis=1) / np.gradient(g[:, :, 0], axis=1)
    dzdy = np.gradient(g[:, :, 2], axis=0) / np.gradient(g[:, :, 1], axis=0)
    nrm_g = np.stack([-dzdx, -dzdy, np.ones_like(dzdx)], -1); nrm_g /= np.linalg.norm(nrm_g, axis=-1, keepdims=True)
    x0, y0 = g[0, 0, 0], g[0, 0, 1]; x1, y1 = g[-1, -1, 0], g[-1, -1, 1]
    uv_g = np.stack([(g[:, :, 0] - x0) / (x1 - x0), (g[:, :, 1] - y0) / (y1 - y0)], -1)      # 0..1 over the grid, v up
    n = 0
    for ty in range(0, side - 1, tile):
        for tx in range(0, side - 1, tile):
            lods = []
            tmat = mat_for_tile(tx, ty, side)
            ye = min(ty + tile, side - 1); xe = min(tx + tile, side - 1)
            for st_ in strides:
                ys = np.arange(ty, ye + 1, st_); xs = np.arange(tx, xe + 1, st_)
                if ys[-1] != ye:
                    ys = np.append(ys, ye)
                if xs[-1] != xe:
                    xs = np.append(xs, xe)
                sub = g[np.ix_(ys, xs)]; h, w = sub.shape[:2]
                if carved is not None and st_ > 1:
                    # a coarse vertex takes the lowest carved height in its neighbourhood, so a river narrower
                    # than the spacing is not filled in by the detail level
                    hw = st_ // 2; stp = max(1, st_ // 8)
                    zmin = sub[:, :, 2].copy()
                    for dy in range(-hw, hw + 1, stp):
                        yy = np.clip(ys + dy, 0, side - 1)
                        for dx in range(-hw, hw + 1, stp):
                            xx = np.clip(xs + dx, 0, side - 1)
                            c_ = carved[np.ix_(yy, xx)]
                            if c_.any():
                                zmin = np.where(c_, np.minimum(zmin, g[:, :, 2][np.ix_(yy, xx)]), zmin)
                    sub[:, :, 2] = zmin
                Pm = sub.reshape(-1, 3)
                P = ((Pm - ORG) * UPM).astype(np.float32)
                N = nrm_g[np.ix_(ys, xs)].reshape(-1, 3).astype(np.float32)
                T = uv_for_tile(uv_g[np.ix_(ys, xs)].reshape(-1, 2).astype(np.float64), tx, ty, side).astype(np.float32)
                idx = np.arange(h * w).reshape(h, w)
                a_ = idx[:-1, :-1].ravel(); b_ = idx[:-1, 1:].ravel(); c_ = idx[1:, :-1].ravel(); d_ = idx[1:, 1:].ravel()
                tris = np.concatenate([np.stack([a_, b_, d_], 1), np.stack([a_, d_, c_], 1)]).astype(np.int64)
                if hole is not None:
                    inside = (Pm[:, 0] > hole[0]) & (Pm[:, 0] < hole[2]) & (Pm[:, 1] > hole[1]) & (Pm[:, 1] < hole[3])
                    tris = tris[~inside[tris].all(1)]
                if len(tris) == 0:
                    break
                lods.append((P, N, T, tris, np.full(len(tris), tmat, np.int64)))
            if not lods:
                continue
            nm = "%s_%d_%d" % (prefix, tx, ty)
            if add_mesh(nm, lods):
                mid = mesh_id[nm]
                inst.append((mid, IDENT, meshes[mid]["c"], meshes[mid]["r"])); n += 1
    return n


terr = scene.get("terrain_grid")
near_bounds = None
if terr:
    g = np.load(os.path.join(dump, "meshes", terr["file"]))["grid"].astype(np.float64)
    near_bounds = (g[0, 0, 0], g[0, 0, 1], g[-1, -1, 0], g[-1, -1, 1])

    # ground baked per terrain tile from the source's terrain material (tools/bake_ground.py)
    GROUND = None
    _gj = os.path.join(dump, "ground", "ground.json")
    if os.path.exists(_gj) and cfg.get("ground_bake_use", True):
        GROUND = json.load(open(_gj))
    ground_mats = {}

    def near_mat(tx, ty, side):
        gt = GROUND["tiles"].get("%d,%d" % (tx, ty)) if GROUND else None
        if gt:
            if (tx, ty) not in ground_mats:
                tex_used[gt["tex"]] = os.path.join("..", "ground", gt["tex"] + ".png")
                gtile = None; gpbr = None
                if gt.get("pack"):
                    # several blended tiling layers: brightness pack projected from world position (code 254) and a
                    # weight map in the second texture slot (tools/bake_ground_packs.py)
                    tex_used[gt["pack"]] = os.path.join("..", "ground", gt["pack"] + ".png")
                    tex_used[gt["weights"]] = os.path.join("..", "ground", gt["weights"] + ".png")
                    gtile = (gt["pack"], int(round(gt["pack_scale"] * 256.0)), 254)
                    gpbr = (gt["weights"], 1.0, 0.85, 0.0, 0)
                elif gt.get("tile"):
                    # the dominant tiling layer of this terrain tile, projected from world position by the renderer:
                    # repeats per metre * 256 in the first value, 255 in the second marks the projection
                    gtn = san(gt["tile"])[:44]; tex_used[gtn] = gt["tile"] + ".png"
                    gtile = (gtn, int(round(gt["tile_scale"] * 256.0)), 255)
                ground_mats[(tx, ty)] = material_index(shader_for(gt["tex"], "opaque"), (1.0, 1.0, 1.0), 0,
                                                       gpbr or (None, 1.0, 0.85, 0.0, 0 if gtile else 1), gtile)
            return ground_mats[(tx, ty)]
        half = (side - 1) // 2
        return TERRAIN_Q.get((1 if tx >= half else 0, 1 if ty >= half else 0), TERRAIN)

    def near_uv(T, tx, ty, side):
        gt = GROUND["tiles"].get("%d,%d" % (tx, ty)) if GROUND else None
        if gt:
            n_ = float(gt["size"]); pd_ = float(GROUND["pad"]); cells_ = float(min(tx + GROUND["tile_cells"], side - 1) - tx)
            cells_y = float(min(ty + GROUND["tile_cells"], side - 1) - ty)
            fx = (T[:, 0] * (side - 1) - tx) / cells_; fy = (T[:, 1] * (side - 1) - ty) / cells_y
            return np.stack([(pd_ + fx * (n_ - 2 * pd_)) / n_, (pd_ + (1.0 - fy) * (n_ - 2 * pd_)) / n_], 1)
        half = (side - 1) // 2
        qx = 1 if tx >= half else 0; qy = 1 if ty >= half else 0
        if (qx, qy) in TERRAIN_Q:
            return np.stack([np.clip(T[:, 0] * 2 - qx, 0.0005, 0.9995), 1.0 - np.clip(T[:, 1] * 2 - qy, 0.0005, 0.9995)], 1)
        return np.stack([T[:, 0], 1.0 - T[:, 1]], 1)

    near_carved = carve_under_water(g, 0.0, "near")
    # for the collision build (tools/build_collision_terrain.py): the terrain as drawn, and the water surface
    np.savez(os.path.join(dump, "extras", "terrain_near_carved.npz"), grid=g.astype(np.float32))
    if WATER is not None:
        np.savez(os.path.join(dump, "extras", "water_final.npz"), water=WATER[0].astype(np.float32), x0=WATER[1], y0=WATER[2], cell=WATER[3],
                 fill=(WATER_FILL[0] if WATER_FILL is not None else np.zeros(WATER[0].shape, bool)))
    terrain_tiles += build_terrain(g, int(GROUND["tile_cells"]) if GROUND else int(terr.get("tile_cells", 128)), cfg.get("near_strides", terr.get("strides", [2, 8, 32])), near_mat, near_uv, "__terrain", carved=near_carved)
else:
    tc_info = scene.get("terrain_crop")
    if tc_info:
        tc = np.load(os.path.join(dump, "meshes", tc_info["file"]))
        if len(tc["tri_verts"]):
            p_ = ((tc["pos"].astype(np.float64) - ORG) * UPM).astype(np.float32)
            n_ = np.zeros_like(p_); n_[:, 2] = 1.0
            if add_mesh("__terrain", [(p_, n_, (tc["pos"][:, :2] / 4.0).astype(np.float32), tc["tri_verts"].astype(np.int64), np.full(len(tc["tri_verts"]), TERRAIN, np.int64))]):
                mid = mesh_id["__terrain"]
                inst.append((mid, IDENT, meshes[mid]["c"], meshes[mid]["r"])); terrain_tiles = 1

# ---- far scenery: far terrain (with a hole where the near terrain is) and the large backdrop meshes
far_tiles = 0; far_meshes = 0
fg = os.path.join(dump, "extras", "terrain_far_grid.npz")
if os.path.exists(fg) and cfg.get("far_scenery", True):
    gf = np.load(fg)["grid"].astype(np.float64)
    if FAR_TERRAIN is None:
        FAR_TERRAIN = TERRAIN
    hole = None
    if near_bounds:
        m_ = 2.0 * abs(gf[0, 1, 0] - gf[0, 0, 0])
        hole = (near_bounds[0] + m_, near_bounds[1] + m_, near_bounds[2] - m_, near_bounds[3] - m_)
        cov = (gf[:, :, 0] > near_bounds[0] + 1.0) & (gf[:, :, 0] < near_bounds[2] - 1.0) & (gf[:, :, 1] > near_bounds[1] + 1.0) & (gf[:, :, 1] < near_bounds[3] - 1.0)
        gf[:, :, 2][cov] -= float(cfg.get("far_terrain_sink_m", 4.0))
    far_carved = carve_under_water(gf, float(cfg.get("far_water_reach_m", 8.0)), "far", exclude=near_bounds,
                                   tol=float(cfg.get("far_water_carve_tolerance_m", 2.0)))
    far_tiles = build_terrain(gf, int(cfg.get("far_tile_cells", 64)), cfg.get("far_strides", [1, 4, 16]),
                              lambda tx, ty, side: FAR_TERRAIN, lambda T, tx, ty, side: np.stack([T[:, 0], 1.0 - T[:, 1]], 1), "__farterrain", hole, carved=far_carved)
for it in far_objs:
    a = np.load(os.path.join(dump, "extras", it["file"]))
    if len(a["tri_loops"]) == 0:
        continue
    pos, nrm, st, tris, nl = weld_dump(a)
    slot = np.array([(mat_of.get(mn, NOMAT) if mn else NOMAT) for mn in (it["materials"] or [None])] + [NOMAT], dtype=np.int64)
    tk = slot[np.clip(a["tri_mat"].astype(np.int64), 0, len(slot) - 1)]
    if add_mesh("__far_" + it["name"], [(pos, nrm, st, tris, tk)]):
        mid = mesh_id["__far_" + it["name"]]
        M = np.array(it["matrix"], dtype=np.float64); R = M[:3, :3]; t = (M[:3, 3] - ORG) * UPM
        c = R @ meshes[mid]["c"].astype(np.float64) + t; r = meshes[mid]["r"] * float(np.linalg.norm(R, axis=0).max())
        inst.append((mid, np.concatenate([R[0], [t[0]], R[1], [t[1]], R[2], [t[2]]]).astype(np.float32), c.astype(np.float32), r))
        far_meshes += 1

# ---- extras exported separately (large water meshes)
extras_n = 0
xj = os.path.join(dump, "extras", "extras.json")
if os.path.exists(xj):
    for it in json.load(open(xj)):
        a = np.load(os.path.join(dump, "extras", it["file"]))
        if len(a["tri_loops"]) == 0:
            continue
        pos, nrm, st, tris, nl = weld_dump(a)
        xmat = FALLS_MAT if "fall" in it["name"].lower() else WATER_MAT
        nrm, hit_ = apply_vcol(it["name"] + "_mesh", a, pos, nrm)
        if hit_:
            vcol_stats[it["name"]] = hit_
        if add_mesh("__extra_" + it["name"], [(pos, nrm, st, tris, np.full(len(tris), xmat, np.int64))]):
            mid = mesh_id["__extra_" + it["name"]]
            M = np.array(it["matrix"], dtype=np.float64); R = M[:3, :3]; t = (M[:3, 3] - ORG) * UPM
            c = R @ meshes[mid]["c"].astype(np.float64) + t; r = meshes[mid]["r"] * float(np.linalg.norm(R, axis=0).max())
            inst.append((mid, np.concatenate([R[0], [t[0]], R[1], [t[1]], R[2], [t[2]]]).astype(np.float32), c.astype(np.float32), r))
            extras_n += 1

# ---- generated water that closes the gaps between the source patches
if WATER_FILL is not None and WATER_FILL[0].any():
    fill, zfill = WATER_FILL; wx0_, wy0_, wc_ = WATER[1], WATER[2], WATER[3]
    quads = []
    rows = np.flatnonzero(fill.any(1))
    for j in rows:
        xs_ = np.flatnonzero(fill[j])
        cuts = np.flatnonzero(np.diff(xs_) > 1) + 1
        for run in np.split(xs_, cuts):
            i0, i1 = int(run[0]), int(run[-1])
            xa = wx0_ + (i0 - 0.5) * wc_ - 0.3; xb = wx0_ + (i1 + 0.5) * wc_ + 0.3
            ya = wy0_ + (j - 0.5) * wc_ - 0.3; yb = wy0_ + (j + 0.5) * wc_ + 0.3      # 0.3 m overlap hides cracks
            za = float(zfill[j, i0]); zb = float(zfill[j, i1])
            quads.append(((xa, ya, za), (xb, ya, zb), (xb, yb, zb), (xa, yb, za)))
    if quads:
        Q = np.array(quads, dtype=np.float64).reshape(-1, 3)
        P = ((Q - ORG) * UPM).astype(np.float32)
        N_ = np.zeros_like(P); N_[:, 2] = 1.0
        T_ = (Q[:, :2] / 8.0).astype(np.float32)
        base = np.arange(len(quads), dtype=np.int64)[:, None] * 4
        tris = np.concatenate([base + np.array([0, 1, 2]), base + np.array([0, 2, 3])])
        if add_mesh("__water_fill", [(P, N_, T_, tris, np.full(len(tris), WATER_MAT, np.int64))]):
            mid = mesh_id["__water_fill"]
            inst.append((mid, IDENT, meshes[mid]["c"], meshes[mid]["r"])); extras_n += 1
            carve_stats["gap_fill"]["quads"] = len(quads)

# ---- textures and shader scripts (after all materials exist)
def make_water_nrm(dst, size=512, units=8.0, seed=7):
    """Tileable noise for the water ripples: R = height (mean 0.5), G/B = d height / d x, y per noise unit, stored as
    g * 0.08 + 0.5. The image spans `units` noise units; four octaves, amplitudes halving (as the source's noise)."""
    rng = np.random.default_rng(seed)
    u = (np.arange(size) + 0.5) / size; U, Vv = np.meshgrid(u, u)
    h = np.zeros((size, size)); gx = np.zeros_like(h); gy = np.zeros_like(h)
    for o_ in range(4):
        f0 = units * (2 ** o_); amp = 0.5 ** o_
        for _ in range(14):
            ang = rng.uniform(0, 2 * np.pi); rad = f0 * rng.uniform(0.7, 1.3)
            fx, fy = int(round(rad * np.cos(ang))), int(round(rad * np.sin(ang)))
            if fx == 0 and fy == 0:
                continue
            ph = rng.uniform(0, 2 * np.pi); arg = 2 * np.pi * (fx * U + fy * Vv) + ph
            h += amp * np.cos(arg); s_ = -amp * np.sin(arg) * 2 * np.pi / units
            gx += s_ * fx; gy += s_ * fy
    k = 0.18 / h.std(); h = h * k + 0.5; gx *= k; gy *= k
    img = np.stack([h, gx * 0.08 + 0.5, gy * 0.08 + 0.5], -1)
    from PIL import Image
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).save(dst)
    return {"height_std": 0.18, "gradient_std_per_unit": [float(gx.std()), float(gy.std())], "clipped_share": float(((img < 0) | (img > 1)).mean())}


water_nrm_info = None
if "water_nrm" in tex_used:
    water_nrm_info = make_water_nrm(os.path.join(dump, "extras", "water_nrm.png"))
for tname, src in pbr_tex_used.items():           # normal maps: copied next to the other textures, used only as .dds
    s_ = os.path.join(PBR_TEX_DIR, src); d_ = os.path.join(tex_dir, tname + ".png")
    if not os.path.exists(d_) or os.path.getsize(d_) != os.path.getsize(s_):
        shutil.copyfile(s_, d_)
missing_tex = []
for tname, src in tex_used.items():
    s = os.path.join(dump, "textures", src)
    if not os.path.exists(s):
        s = os.path.join(dump, "extras", os.path.basename(src))
    if not os.path.exists(s):
        s = os.path.join(dump, "textures_all", os.path.basename(src))
    if os.path.exists(s):
        d = os.path.join(tex_dir, tname + ".png")
        if not os.path.exists(d) or os.path.getsize(d) != os.path.getsize(s):
            shutil.copyfile(s, d)
    else:
        missing_tex.append(src)
os.makedirs(os.path.join(game_dir, "shaders"), exist_ok=True)
with open(os.path.join(game_dir, "shaders", "naboo_%s.shader" % mapname), "w") as f:
    f.write("// generated by naboo/tools/cook_v1.py - do not edit\n")
    for s_ in shader_text.values():
        f.write(s_)
N_SHADERS_WRITTEN = len(shader_text)
# sky: six faces rendered from the Blender world, and the run-time copy of the sky shader the BSP hull uses
env_dir = os.path.join(tex_dir, "env"); os.makedirs(env_dir, exist_ok=True)
sky_faces = 0
for suf in ("rt", "lf", "bk", "ft", "up", "dn"):
    src = os.path.join(dump, "extras", "sky_%s.png" % suf)
    if os.path.exists(src):
        shutil.copyfile(src, os.path.join(env_dir, "sky_%s.png" % suf)); sky_faces += 1
with open(os.path.join(game_dir, "shaders", "naboo_sys.shader"), "w") as f:
    f.write("// generated by naboo/tools/cook_v1.py - do not edit\n"
            "textures/naboo_sys/sky\n{\n\tsurfaceparm sky\n\tsurfaceparm noimpact\n\tsurfaceparm nolightmap\n"
            "\tskyParms textures/naboo/env/sky 512 -\n}\n"
            "textures/naboo_sys/col\n{\n\tsurfaceparm nodraw\n}\ntextures/naboo_sys/hull\n{\n\tsurfaceparm nodraw\n}\ntextures/naboo_sys/water\n{\n\tsurfaceparm nodraw\n\tsurfaceparm water\n\tsurfaceparm nonsolid\n}\n")


# ---- write
allc = np.array([i[2] for i in inst]); allr = np.array([i[3] for i in inst])
nb_ = len(inst) - extras_n
mins = (allc[:nb_] - allr[:nb_, None]).min(0); maxs = (allc[:nb_] + allr[:nb_, None]).max(0)
out = os.path.join(game_dir, "maps", mapname + ".tworld"); os.makedirs(os.path.dirname(out), exist_ok=True)
sky_rgb = [0, 0]
try:
    from PIL import Image
    up = np.asarray(Image.open(os.path.join(dump, "extras", "sky_up.png")).convert("RGB"), np.float64)
    zen = up[up.shape[0] // 4: 3 * up.shape[0] // 4, up.shape[1] // 4: 3 * up.shape[1] // 4].reshape(-1, 3).mean(0)
    hz = []
    for suf in ("rt", "lf", "bk", "ft"):
        sd = np.asarray(Image.open(os.path.join(dump, "extras", "sky_%s.png" % suf)).convert("RGB"), np.float64)
        hz.append(sd[int(sd.shape[0] * 0.40): int(sd.shape[0] * 0.49)].reshape(-1, 3).mean(0))      # just above the horizon
    hor = np.mean(hz, 0)
    pack = lambda c: (int(round(c[0])) << 16) | (int(round(c[1])) << 8) | int(round(c[2]))
    sky_rgb = [pack(zen), pack(hor)]
except Exception as e_:
    print("sky colours not computed:", e_)
with open(out, "wb") as f:
    # reserved[0], [1]: sky colour at the zenith and just above the horizon (0xRRGGBB, display space), for reflections
    # reserved[2], [3]: the scene origin x, y in metres as floats (world-projected ground textures)
    f.write(struct.pack("<4sIIIIIII6ff9f2I2f", b"TWLD", 2, len(materials), len(meshes), len(subs), len(inst), nv_tot, ni_tot,
                        *mins.tolist(), *maxs.tolist(), UPM, *SUN_DIR.tolist(), *SUN_COL, *AMB_COL, sky_rgb[0], sky_rgb[1], float(ORG[0]), float(ORG[1])))
    for sname, tint, flags in materials:
        f.write(struct.pack("<64s3fI", sname.encode("ascii"), *tint, flags))
    for m in meshes:
        f.write(struct.pack("<5I3I3I4f", m["fv"], m["nv"], m["fi"], m["ni"], m["nl"], *m["lf"], *m["ln"], *m["c"].tolist(), m["r"]))
    for s in subs:
        f.write(struct.pack("<4I", s[0], s[1], s[2], 0))
    for i in inst:
        f.write(struct.pack("<I12f4f", i[0], *i[1].tolist(), *i[2].tolist(), i[3]))
    for v in V:
        f.write(v.tobytes())
    for ix in I:
        f.write(ix.tobytes())

with open(os.path.join(game_dir, "maps", mapname + ".tuv2"), "wb") as f:
    f.write(struct.pack("<4sII", b"TUV2", 1, len(UV2)))
    for mi_, u_ in sorted(UV2.items()):
        assert len(u_) == meshes[mi_]["nv"]
        f.write(struct.pack("<II", mi_, len(u_))); f.write(u_.tobytes())
with open(os.path.join(game_dir, "maps", mapname + ".tpbr"), "wb") as f:
    f.write(struct.pack("<4sII", b"TPBR", 2, len(materials)))
    for i_ in range(len(materials)):
        nt, sc_, ro_, me_, fl_ = mat_pbr.get(i_, PBR_DEFAULT)
        tl_ = mat_tile.get(i_)
        f.write(struct.pack("<64s3fI", (("textures/naboo/" + nt) if nt else "").encode("ascii"), sc_, ro_, me_, fl_))
        f.write(struct.pack("<64s2f", (("textures/naboo/" + tl_[0]) if tl_ else "").encode("ascii"), float(tl_[1]) if tl_ else 0.0, float(tl_[2]) if tl_ else 0.0))
pbr_stats = {"baked_source_materials": len([1 for k_ in BAKED if k_ in mat_of]), "materials_with_tiling_layer": len(mat_tile),
             "materials_with_normal_map": sum(1 for v in mat_pbr.values() if v[0]), "normal_textures": len(pbr_tex_used),
             "roughness_from_base_alpha": sum(1 for v in mat_pbr.values() if v[4] & 1), "metallic_from_map": sum(1 for v in mat_pbr.values() if v[4] & 6),
             "metallic_constant_above_half": sum(1 for v in mat_pbr.values() if v[3] > 0.5)}
size = os.path.getsize(out)
rep = {"seconds": round(time.time() - t0, 1), "file": out, "bytes": size, "under_2GB": size < 2 ** 31 - 1,
       "blender_materials": len(mats), "classes": cls_count, "engine_materials": len(materials), "engine_shaders": len(shader_text),
       "textures": len(tex_used), "missing_textures": missing_tex, "blended_materials": sum(1 for m_ in materials if m_[2] & 1),
       "scatter": scatter_stats, "foliage_detail_levels": foliage_stats, "second_uv_set": {"materials": len(BASE_UV1), "tiled_materials": len(BASE_SCALE), **uv1_stats}, "pbr": pbr_stats, "water_nrm": water_nrm_info, "sky_zenith_horizon_rgb": ["%06x" % x for x in sky_rgb], "foam_vertex_colour_hits": vcol_stats,
       "animated_materials": {"foam": sum(1 for m_ in materials if (m_[2] >> 1) & 7 == 4), "water": sum(1 for m_ in materials if (m_[2] >> 1) & 7 == 1), "sway": sum(1 for m_ in materials if (m_[2] >> 1) & 7 == 2), "cloth": sum(1 for m_ in materials if (m_[2] >> 1) & 7 == 3)},
       "water_carving": carve_stats,
       "sky_faces": sky_faces, "terrain_bake_tiles": len(TERRAIN_Q), "extra_meshes": extras_n, "far_terrain_tiles": far_tiles, "far_meshes": far_meshes,
       "meshes": len(meshes), "meshes_with_lod1": sum(1 for m in meshes if m["nl"] > 1), "meshes_with_lod2": sum(1 for m in meshes if m["nl"] > 2),
       "submeshes": len(subs), "instances": len(inst), "object_instances": n_obj_inst, "terrain_tiles": terrain_tiles,
       "instances_skipped_no_geometry": skipped_inst, "verts": nv_tot, "tris_all_lods": ni_tot // 3,
       "tris_instanced_lod0": int(sum(meshes[i[0]]["lod_tris"][0] for i in inst)),
       "tris_instanced_lowest_lod": int(sum(meshes[i[0]]["lod_tris"][-1] for i in inst)),
       "draws_if_all_visible_lod0": int(sum(meshes[i[0]]["subs0"] for i in inst)),
       "bounds_units": [mins.round(1).tolist(), maxs.round(1).tolist()], **stats}
json.dump(rep, open(os.path.join(export_dir, "cook_v1_%s.json" % mapname), "w"), indent=1)
print(json.dumps(rep, indent=1))
