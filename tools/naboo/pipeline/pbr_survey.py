"""Blender (read-only): how each material feeds Normal, Roughness, Metallic and Base Color of its Principled BSDF.
  blender -b --factory-startup --disable-autoexec <file.blend> --python pbr_survey.py -- <out.json>
For each input the node chain is walked upstream to the first Image Texture; recorded: image, the channel taken
(Separate Color output or Alpha), the math operations on the way, the Mapping scale and the texture coordinate
source (UV map name, or 'position' for world-projected textures)."""
import bpy, sys, json

out = sys.argv[sys.argv.index("--") + 1]


def coord_source(node, depth=0):
    """Follow the Vector input of an image texture: returns (kind, uv name, scale xy, extra)."""
    scale = [1.0, 1.0]; ops = []
    n = node
    for _ in range(12):
        vin = n.inputs.get("Vector")
        if vin is None or not vin.is_linked:
            return ("uv_default", None, scale, ops)
        src = vin.links[0].from_node
        t = src.bl_idname
        if t == "ShaderNodeMapping":
            s = src.inputs["Scale"].default_value
            scale = [scale[0] * float(s[0]), scale[1] * float(s[1])]
            if src.inputs["Location"].is_linked:
                ops.append("animated_location")
            n = src; continue
        if t == "ShaderNodeUVMap":
            return ("uv", src.uv_map, scale, ops)
        if t == "ShaderNodeTexCoord":
            return ("texcoord_" + vin.links[0].from_socket.name, None, scale, ops)
        if t in ("ShaderNodeCombineXYZ", "ShaderNodeNewGeometry", "ShaderNodeSeparateXYZ", "ShaderNodeVectorMath", "ShaderNodeMath"):
            # world-projected: Geometry.Position -> Separate -> Math(MULTIPLY_ADD) -> Combine
            mul = None
            if t == "ShaderNodeCombineXYZ":
                xin = src.inputs[0]
                if xin.is_linked and xin.links[0].from_node.bl_idname == "ShaderNodeMath":
                    m = xin.links[0].from_node
                    try:
                        mul = [float(m.inputs[1].default_value), float(m.inputs[2].default_value) if len(m.inputs) > 2 else 0.0, m.operation]
                    except Exception:
                        mul = None
            return ("position", None, scale, ops + ([mul] if mul else []))
        return ("other:" + t, None, scale, ops)
    return ("deep", None, scale, ops)


def walk(sock, depth=0):
    """Upstream from an input socket to the first image texture."""
    ops = []
    s = sock
    for _ in range(24):
        if not s.is_linked:
            try:
                v = s.default_value
                v = [round(float(x), 4) for x in v] if hasattr(v, "__len__") else round(float(v), 4)
            except Exception:
                v = None
            return {"const": v, "ops": ops}
        l = s.links[0]; n = l.from_node; t = n.bl_idname
        if t == "ShaderNodeTexImage":
            kind, uvn, scale, cops = coord_source(n)
            return {"image": n.image.name if n.image else None, "size": list(n.image.size) if n.image else None, "socket": l.from_socket.name,
                    "colorspace": n.image.colorspace_settings.name if n.image else None,
                    "ops": ops, "coord": kind, "uv": uvn, "scale": [round(x, 4) for x in scale], "coord_ops": cops}
        if t == "ShaderNodeSeparateColor":
            ops.append("sep." + l.from_socket.name); s = n.inputs[0]; continue
        if t == "ShaderNodeNormalMap":
            ops.append("normalmap(%.2f)" % float(n.inputs["Strength"].default_value)); s = n.inputs["Color"]; continue
        if t == "ShaderNodeBump":
            ops.append("bump"); s = n.inputs["Height"]; continue
        if t == "ShaderNodeMath":
            consts = []
            for i_ in n.inputs:
                if not i_.is_linked:
                    consts.append(round(float(i_.default_value), 4))
            ops.append("math.%s%s" % (n.operation, consts))
            nxt = [i_ for i_ in n.inputs if i_.is_linked]
            s = nxt[0]; continue
        if t in ("ShaderNodeVectorMath", "ShaderNodeCombineXYZ", "ShaderNodeMix", "ShaderNodeMixRGB", "ShaderNodeInvert", "ShaderNodeGamma", "ShaderNodeHueSaturation",
                 "ShaderNodeBrightContrast", "ShaderNodeRGBCurve", "ShaderNodeClamp", "ShaderNodeMapRange", "ShaderNodeValToRGB", "ShaderNodeSeparateXYZ"):
            ops.append(t[10:] + ("." + getattr(n, "blend_type", "") if hasattr(n, "blend_type") else "") + ("." + getattr(n, "operation", "") if hasattr(n, "operation") else ""))
            nxt = [i_ for i_ in n.inputs if i_.is_linked]
            if not nxt:
                return {"const": None, "ops": ops}
            s = nxt[0]; continue
        return {"stop": t, "ops": ops}
    return {"deep": True, "ops": ops}


res = {}
for m in bpy.data.materials:
    if not m.node_tree or m.users == 0:
        continue
    p = next((n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    if p is None:
        continue
    e = {}
    for key in ("Base Color", "Normal", "Roughness", "Metallic", "Alpha", "Specular IOR Level"):
        if key in p.inputs:
            e[key] = walk(p.inputs[key])
    e["uv_layers_hint"] = None
    res[m.name] = e
json.dump(res, open(out, "w"), indent=0)
print("PBRS materials", len(res))
