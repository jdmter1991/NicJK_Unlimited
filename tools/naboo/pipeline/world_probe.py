"""Which materials cover the level ground in a box of the cooked world.
  py world_probe.py <tworld> x0 x1 y0 y1 z0 z1"""
import numpy as np, struct, collections, sys
w=np.memmap(sys.argv[1],dtype=np.uint8,mode="r"); x0,x1,y0,y1,z0,z1=map(float,sys.argv[2:8])
magic,ver,nmat,nmesh,nsub,ninst,nvert,nidx=struct.unpack_from("<4sIIIIIII",w,0); o=112
mats=np.frombuffer(w,dtype=[("shader","S64"),("tint","<f4",3),("flags","<u4")],count=nmat,offset=o); o+=nmat*80
meshes=np.frombuffer(w,dtype=[("fv","<u4"),("nv","<u4"),("fi","<u4"),("ni","<u4"),("nl","<u4"),("lfs","<u4",3),("lns","<u4",3),("c","<f4",3),("r","<f4")],count=nmesh,offset=o); o+=nmesh*60
subs=np.frombuffer(w,dtype=[("mat","<u4"),("fi","<u4"),("ni","<u4"),("res","<u4")],count=nsub,offset=o); o+=nsub*16
insts=np.frombuffer(w,dtype=[("mesh","<u4"),("m","<f4",12),("c","<f4",3),("r","<f4")],count=ninst,offset=o); o+=ninst*68
verts=np.frombuffer(w,dtype=[("xyz","<f4",3),("n","<f4",3),("st","<f4",2)],count=nvert,offset=o); o+=nvert*32
idx=np.frombuffer(w,dtype="<u4",count=nidx,offset=o)
C=insts["c"]; acc=collections.Counter(); cx,cy=(x0+x1)/2,(y0+y1)/2; rr=np.hypot(x1-x0,y1-y0)/2
near=np.flatnonzero((np.hypot(C[:,0]-cx,C[:,1]-cy)<insts["r"]+rr))
for ii in near:
    me=meshes[insts["mesh"][ii]]; M=insts["m"][ii].reshape(3,4).astype(float)
    V=verts["xyz"][me["fv"]:me["fv"]+me["nv"]].astype(float)@M[:,:3].T+M[:,3]
    for s in range(int(me["lfs"][0]),int(me["lfs"][0])+int(me["lns"][0])):
        sb=subs[s]; t=idx[me["fi"]+sb["fi"]:me["fi"]+sb["fi"]+sb["ni"]].reshape(-1,3).astype(np.int64)
        c=V[t].mean(1); n=np.cross(V[t[:,1]]-V[t[:,0]],V[t[:,2]]-V[t[:,0]]); ar=np.linalg.norm(n,axis=1)/2
        m=(c[:,0]>x0)&(c[:,0]<x1)&(c[:,1]>y0)&(c[:,1]<y1)&(c[:,2]>z0)&(c[:,2]<z1)&(np.abs(n[:,2])>0.9*2*np.maximum(ar,1e-9))
        if m.any(): acc[(mats[sb["mat"]]["shader"].decode()[:56],tuple(np.round(mats[sb["mat"]]["tint"],2)),hex(int(mats[sb["mat"]]["flags"])), round(float(c[m][:,2].mean())), int(insts["mesh"][ii]))]+=float(ar[m].sum())
for k,v in acc.most_common(16): print(int(v),k)
