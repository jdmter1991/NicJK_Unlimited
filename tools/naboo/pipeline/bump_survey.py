"""Blender (read-only): parameters of the Bump and Normal Map nodes that feed each material's Principled BSDF.
  blender -b --factory-startup --disable-autoexec <file.blend> --python bump_survey.py -- <out.json>
Per material: for the first Bump node upstream of the Normal input its Strength, Distance, Invert and the image
behind Height (name, size, Mapping scale, UV map); for the first Normal Map node its Strength. Also the mean edge
length in metres per UV unit of the first mesh that uses the material (to turn a height in metres into a slope in
texture space)."""
import bpy, sys, json

out = sys.argv[sys.argv.index("--") + 1]


def val(sock):
    try:
        return float(sock.default_value)
    except Exception:
        return None


def upstream_image(sock, depth=0):
    if depth > 14 or not sock.is_linked:
        return None
    n = sock.links[0].from_node
    if n.bl_idname == "ShaderNodeTexImage":
        e = {"image": n.image.name if n.image else None, "size": list(n.image.size) if n.image else None, "socket": sock.links[0].from_socket.name, "scale": [1.0, 1.0], "uv": None}
        v = n.inputs.get("Vector"); k = 0
        while v is not None and v.is_linked and k < 8:
            s = v.links[0].from_node; k += 1
            if s.bl_idname == "ShaderNodeMapping":
                sc = s.inputs["Scale"].default_value; e["scale"] = [e["scale"][0] * float(sc[0]), e["scale"][1] * float(sc[1])]; v = s.inputs.get("Vector"); continue
            if s.bl_idname == "ShaderNodeUVMap":
                e["uv"] = s.uv_map
            break
        return e
    for i in n.inputs:
        if i.is_linked:
            r = upstream_image(i, depth + 1)
            if r:
                return r
    return None


def find(sock, kinds, depth=0):
    if depth > 14 or not sock.is_linked:
        return None
    n = sock.links[0].from_node
    if n.bl_idname in kinds:
        return n
    for i in n.inputs:
        if i.is_linked:
            r = find(i, kinds, depth + 1)
            if r:
                return r
    return None


res = {}
for m in bpy.data.materials:
    if not m.use_nodes or not m.node_tree:
        continue
    bsdf = next((n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    if not bsdf:
        continue
    ns = bsdf.inputs.get("Normal")
    if ns is None or not ns.is_linked:
        continue
    e = {}
    b = find(ns, ("ShaderNodeBump",))
    if b:
        e["bump"] = {"strength": val(b.inputs["Strength"]), "distance": val(b.inputs["Distance"]), "invert": bool(b.invert),
                     "strength_linked": b.inputs["Strength"].is_linked, "distance_linked": b.inputs["Distance"].is_linked,
                     "height": upstream_image(b.inputs["Height"]), "normal_linked": b.inputs["Normal"].is_linked}
    nm = find(ns, ("ShaderNodeNormalMap",))
    if nm:
        e["normal_map"] = {"strength": val(nm.inputs["Strength"]), "space": nm.space, "uv_map": nm.uv_map}
    if e:
        res[m.name] = e
# metres per UV unit for materials with a bump node: first mesh object using the material
want = {k for k, v in res.items() if "bump" in v}
done = set()
for ob in bpy.data.objects:
    if ob.type != "MESH" or not want - done:
        continue
    me = ob.data
    names = [s.material.name if s.material else None for s in ob.material_slots]
    hit = [i for i, n in enumerate(names) if n in want and n not in done]
    if not hit or not me.uv_layers:
        continue
    uv = me.uv_layers[0].data; sc = ob.matrix_world.to_scale()
    for i in hit:
        tot_w = 0.0; tot_u = 0.0; cnt = 0
        for p in me.polygons:
            if p.material_index != i:
                continue
            ls = list(p.loop_indices)
            for a, b_ in zip(ls, ls[1:] + ls[:1]):
                va = me.vertices[me.loops[a].vertex_index].co; vb = me.vertices[me.loops[b_].vertex_index].co
                d = (vb - va); d.x *= sc.x; d.y *= sc.y; d.z *= sc.z
                tot_w += d.length; tot_u += (uv[b_].uv - uv[a].uv).length
            cnt += 1
            if cnt >= 400:
                break
        if tot_u > 1e-9:
            res[names[i]]["metres_per_uv"] = tot_w / tot_u; res[names[i]]["sample_object"] = ob.name; done.add(names[i])
json.dump(res, open(out, "w"), indent=1)
print("bump_survey:", len(res), "materials,", len(want), "with a bump node,", len(done), "with a scale")
