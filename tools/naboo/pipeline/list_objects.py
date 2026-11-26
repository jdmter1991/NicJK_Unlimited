"""Blender (headless, read-only): every mesh object of the source as [name, x, y, z, radius, faces] in engine units.
  blender -b --factory-startup --disable-autoexec <file.blend> --python list_objects.py -- <out.json>"""
import sys
import bpy, json
from mathutils import Vector
ORG=Vector((680.0,-50.0,436.0)); U=39.37
out=[]
for ob in bpy.data.objects:
    if ob.type!="MESH": continue
    bb=[ob.matrix_world@Vector(c) for c in ob.bound_box]
    c=sum(bb,Vector())/8; r=max((v-c).length for v in bb)
    out.append([ob.name, (c.x-ORG.x)*U,(c.y-ORG.y)*U,(c.z-ORG.z)*U, r*U, len(ob.data.polygons)])
json.dump(out,open(sys.argv[sys.argv.index("--") + 1],"w"))
print("OBJS",len(out))
