# ---------------------------------------------------------------- materials
def _inputs(n):
    return {i.identifier: i for i in n.inputs}


def eval_color(sock, depth=0):
    """Follow the colour path feeding a socket. Returns (image name or None, [r, g, b] constant factor).
    Masks and scalar maths are not followed: only colour-carrying inputs. Unknown mix factors count as 0.3."""
    if not sock.is_linked:
        v = sock.default_value
        try:
            return None, [float(v[0]), float(v[1]), float(v[2])]
        except TypeError:
            return None, [float(v)] * 3
    if depth > 40:
        return None, [1.0, 1.0, 1.0]
    l = sock.links[0]; n = l.from_node; t = n.bl_idname
    if t == "ShaderNodeTexImage":
        if l.from_socket.identifier == "Color" and n.image:
            return n.image.name, [1.0, 1.0, 1.0]
        return None, [0.5, 0.5, 0.5]
    if t == "ShaderNodeRGB":
        return None, [float(x) for x in n.outputs[0].default_value[:3]]
    if t == "ShaderNodeMix" and n.data_type == "RGBA":
        ins = _inputs(n)
        A = eval_color(ins["A_Color"], depth + 1); B = eval_color(ins["B_Color"], depth + 1)
        fs = ins["Factor_Float"]; f = None if fs.is_linked else float(fs.default_value)
        if n.blend_type == "MIX":
            if f is not None and f >= 0.99:
                return B
            if f is not None and f <= 0.01:
                return A
            if A[0]:
                return A
            if B[0]:
                return B
            w = 0.3 if f is None else f
            return None, [A[1][i] * (1 - w) + B[1][i] * w for i in range(3)]
        if n.blend_type == "MULTIPLY":
            w = 1.0 if f is None else f
            if A[0] and B[0]:
                return A
            return (A[0] or B[0]), [A[1][i] * (1 - w + w * B[1][i]) for i in range(3)]
        return A if (A[0] or not B[0]) else B
    if t == "ShaderNodeVectorMath":
        ins = list(n.inputs)
        A = eval_color(ins[0], depth + 1)
        if n.operation == "MULTIPLY":
            B = eval_color(ins[1], depth + 1)
            if A[0] and B[0]:
                return A
            return (A[0] or B[0]), [A[1][i] * B[1][i] for i in range(3)]
        if n.operation == "SCALE":
            sc = _inputs(n).get("Scale")
            k = 1.0 if (sc is None or sc.is_linked) else float(sc.default_value)
            return A[0], [x * k for x in A[1]]
        if A[0]:
            return A
        for i in ins[1:]:
            if i.is_linked:
                B = eval_color(i, depth + 1)
                if B[0]:
                    return B
        return A
    if t in ("ShaderNodeMath", "ShaderNodeSeparateColor", "ShaderNodeSeparateXYZ", "ShaderNodeClamp", "ShaderNodeMapRange", "ShaderNodeRGBToBW", "ShaderNodeValue"):
        return None, [1.0, 1.0, 1.0]      # a scalar (mask, AO, ...) multiplied in: unknown, treated as neutral
    if t in ("ShaderNodeCombineColor", "ShaderNodeCombineXYZ"):
        return None, [(float(i.default_value) if not i.is_linked else 0.5) for i in list(n.inputs)[:3]]
    for nm in ("Color", "Image", "Input"):
        i = n.inputs.get(nm)
        if i is not None:
            return eval_color(i, depth + 1)
    for i in n.inputs:
        if i.is_linked:
            return eval_color(i, depth + 1)
    return None, [1.0, 1.0, 1.0]


def first_image_any(sock):
    seen = set(); stack = [sock]
    while stack:
        s = stack.pop()
        for l in s.links:
            fn = l.from_node
            if fn.name in seen:
                continue
            seen.add(fn.name)
            if fn.bl_idname == "ShaderNodeTexImage" and fn.image:
                return [fn.image.name, l.from_socket.identifier]
            stack.extend(fn.inputs)
    return None


def material_info(m):
    d = {"name": m.name, "blend_method": getattr(m, "blend_method", ""), "builder": m.get("builder", ""),
         "shader": m.get("shader", ""), "base_image": None, "tint": [1.0, 1.0, 1.0], "normal_image": None, "alpha_linked": False,
         "alpha_source": None, "transparent_node": False, "translucent_node": False, "images": []}
    nt = m.node_tree
    if not nt:
        d["cls"] = "opaque"; return d
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            d["images"].append(n.image.name)
        elif n.bl_idname == "ShaderNodeBsdfPrincipled":
            img, tint = eval_color(n.inputs["Base Color"])
            tint = [min(max(x, 0.0), 2.0) for x in tint]
            lum = 0.2126 * tint[0] + 0.7152 * tint[1] + 0.0722 * tint[2]
            d["tint_raw"] = [round(x, 4) for x in tint]
            if img and lum < 0.30:
                # products of several unknown-weight tint constants come out far too dark; keep the hue, lift the level
                k = 0.30 / max(lum, 1e-4); tint = [min(x * k, 2.0) for x in tint]
            d["base_image"] = img; d["tint"] = [round(x, 4) for x in tint]
            ni = first_image_any(n.inputs["Normal"]); d["normal_image"] = ni[0] if ni else None
            d["alpha_linked"] = n.inputs["Alpha"].is_linked
            d["alpha_source"] = first_image_any(n.inputs["Alpha"]) if d["alpha_linked"] else None
            d["alpha_default"] = float(n.inputs["Alpha"].default_value)
        elif n.bl_idname == "ShaderNodeBsdfTransparent":
            d["transparent_node"] = True
        elif n.bl_idname == "ShaderNodeBsdfTranslucent":
            d["translucent_node"] = True
        elif n.bl_idname == "ShaderNodeMixShader" and d.get("mix_alpha_source") is None:
            d["mix_alpha_source"] = first_image_any(n.inputs[0])
    if d["alpha_source"] is None and d["transparent_node"]:
        d["alpha_source"] = d.get("mix_alpha_source")
    b = d["builder"]
    invisible = "(invisible)" in b or b in ("fog_card", "placeholder") or b.startswith("fog_billboard")
    d["cls"] = "invisible" if invisible else ("blend" if d["blend_method"] == "BLEND" else ("cutout" if (d["alpha_linked"] or d["transparent_node"]) else "opaque"))
    return d


MAT = {}
for me in meshes.values():
    for m in me.materials:
        if m and m.name not in MAT:
            MAT[m.name] = material_info(m)
if "materials" in steps:
    import collections
    os.makedirs(os.path.join(outdir, "dump"), exist_ok=True)
    json.dump(MAT, open(os.path.join(outdir, "dump", "materials.json"), "w", encoding="utf-8"), indent=1)
    REPORT["materials"] = {"count": len(MAT), "classes": dict(collections.Counter(m["cls"] for m in MAT.values())),
                           "with_base_image": sum(1 for m in MAT.values() if m["base_image"]),
                           "distinct_base_images": len(set(m["base_image"] for m in MAT.values() if m["base_image"])),
                           "tinted": sum(1 for m in MAT.values() if max(abs(x - 1.0) for x in m["tint"]) > 0.02),
                           "cutout_alpha_from_other_image": sum(1 for m in MAT.values() if m["cls"] == "cutout" and m["alpha_source"] and m["alpha_source"][0] != m["base_image"]),
                           "cutout_alpha_from_colour_channel": sum(1 for m in MAT.values() if m["cls"] == "cutout" and m["alpha_source"] and m["alpha_source"][1] != "Alpha"),
                           "cutout_no_alpha_source": sum(1 for m in MAT.values() if m["cls"] == "cutout" and not m["alpha_source"])}
    save_report(); print("[export] materials", REPORT["materials"], flush=True)


