"""Blender (headless, read-only): every emissive part of the source as [object, material, x, y, z, size, colour] in
 engine units.  blender -b --factory-startup --disable-autoexec <file.blend> --python list_emissive_parts.py -- <out.json>"""
import sys
import bpy, json, collections
from mathutils import Vector
ORG=Vector((680.0,-50.0,436.0)); U=39.37
out=[]; cnt=collections.Counter()
for ob in bpy.data.objects:
    if ob.type!="MESH" or ob.hide_render: continue
    me=ob.data; mats=me.materials
    idx=[i for i,m in enumerate(mats) if m and "emissive" in m.name.lower()]
    if not idx: continue
    M=ob.matrix_world
    for i in idx:
        P=[M@me.vertices[v].co for p in me.polygons if p.material_index==i for v in p.vertices]
        if not P: continue
        c=sum(P,Vector())/len(P); size=max((p-c).length for p in P)*2
        col=[1.0,0.85,0.6]
        m=mats[i]
        if m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type=="BSDF_PRINCIPLED" and "Emission Color" in n.inputs: col=list(n.inputs["Emission Color"].default_value)[:3]
        out.append([ob.name, m.name, (c.x-ORG.x)*U,(c.y-ORG.y)*U,(c.z-ORG.z)*U, size*U, col]); cnt[m.name.split("|")[0]]+=1
json.dump(out,open(sys.argv[sys.argv.index("--") + 1],"w"))
print("EMI",len(out),cnt.most_common(15))
