"""Find sprites in oracle screenshots and measure overlays against their base picture (docs/play/buildings.md 7c,
re/oracle/scenarios/overlays.txt). Library, used from python:

    import sys; sys.path.insert(0, "tools"); from oracle_match import *
    S = screen("re/oracle/runs/overlays-check/w420_150/t170.bmp")
    find(S, tmpl("Zeus_General", 1139))                         # [(score, x, y, opaque px)] of the guardpost base
    report(S, bx, by, 118, 108, 2, loop_cands(2958, 53), -5 + 59, 8)   # each loop frame: rel offset vs prediction

A pixel matches when every channel is within `tol` of the sprite (magenta/transparent pixels ignored); the
exe draws RGB565, so tol 10. Prediction: P = (0, base_h - 15*(n+1)); loop frames at P + (dx - ax, dy - ay)."""
import json, os, sys
import numpy as np
from PIL import Image
import oracle  # noqa: E402  (shot paths: .bmp -> .png, tools/oracle.py)
Z = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/'
_at={}
def meta(file, idx):
    if file not in _at:
        a=json.load(open(Z+f'extracted/sprites/{file}/atlas.json'))
        _at[file]={e['index']:e for e in a['images']}
    return _at[file][idx]
_tc={}
def tmpl(file, idx):
    k=(file,idx)
    if k not in _tc:
        e=meta(file,idx)
        im=np.asarray(Image.open(Z+f'extracted/sprites/{file}/{e["png"]}').convert('RGBA')).astype(np.int16)
        assert im.shape[1]==e['width'] and im.shape[0]==e['height'], (file,idx,im.shape,e)
        _tc[k]=im
    return _tc[k]
def screen(p): return np.asarray(Image.open(oracle.shot(p)).convert('RGB')).astype(np.int16)
def score_at(S, T, x, y, tol=10):
    h,w=T.shape[:2]; H,W=S.shape[:2]
    m=T[...,3]==255
    x0,y0=max(x,0),max(y,0); x1,y1=min(x+w,W),min(y+h,H)
    if x1<=x0 or y1<=y0: return 0,0
    sub=S[y0:y1,x0:x1]; t=T[y0-y:y1-y,x0-x:x1-x]; mm=m[y0-y:y1-y,x0-x:x1-x]
    ok=(np.abs(sub-t[...,:3]).max(-1)<=tol)&mm
    n=mm.sum()
    return (ok.sum()/n if n else 0), n
def find(S, T, tol=10, thr=0.6, K=24, seed=1, region=None):
    """all positions (x,y) of top-left where >=thr of opaque pixels match"""
    h,w=T.shape[:2]; H,W=S.shape[:2]
    ys,xs=np.nonzero(T[...,3]==255)
    if len(ys)==0: return []
    rng=np.random.default_rng(seed); sel=rng.choice(len(ys),min(K,len(ys)),replace=False)
    if region: rx0,ry0,rx1,ry1=region
    else: rx0,ry0,rx1,ry1=-w+1,-h+1,W-1,H-1
    cnt=np.zeros((ry1-ry0+1,rx1-rx0+1),np.int16)
    for i in sel:
        py,px=ys[i],xs[i]; c=T[py,px,:3]
        ok=(np.abs(S-c).max(-1)<=tol)
        # position (x,y) -> pixel (x+px,y+py)
        X=np.arange(rx0,rx1+1)+px; Y=np.arange(ry0,ry1+1)+py
        vx=(X>=0)&(X<W); vy=(Y>=0)&(Y<H)
        sub=np.zeros_like(cnt,dtype=bool)
        sub[np.ix_(vy,vx)]=ok[np.ix_(Y[vy],X[vx])]
        cnt+=sub
    need=max(3,int(len(sel)*thr*0.8))
    cy,cx=np.nonzero(cnt>=need)
    res=[]
    for yy,xx in zip(cy,cx):
        x,y=xx+rx0,yy+ry0
        s,n=score_at(S,T,x,y,tol)
        if s>=thr and n>=min(40,(T[...,3]==255).sum()): res.append((round(float(s),3),x,y,int(n)))
    res.sort(reverse=True)
    # nms
    out=[]
    for r in res:
        if all(abs(r[1]-o[1])>3 or abs(r[2]-o[2])>3 for o in out): out.append(r)
    return out


def best_of(S, cands, bx, by, pad=60, w=118, h=140, thr=0.7, tol=10):
    """cands: list of (label, file, idx). search region around base; return sorted matches (score,label,relx,rely,n)"""
    out=[]
    for lab,f,i in cands:
        T=tmpl(f,i); th,tw=T.shape[:2]
        reg=(bx-pad-tw, by-pad-th, bx+w+pad, by+h+pad)
        for s,x,y,n in find(S,T,tol=tol,thr=thr,region=reg)[:2]:
            out.append((s,lab,int(x-bx),int(y-by),n,tw,th))
    out.sort(key=lambda r:(-r[0]))
    return out
def loop_cands(first, frames, dirs=1, dir=0, file='SprAmbient'):
    return [(f'{file}:{first+k*dirs+dir}(k{k})', file, first+k*dirs+dir) for k in range(frames)]
def pred_loop(base_h, n, dx, dy, file, idx):
    e=meta(file,idx); return (dx-e['anchor_x'], base_h-15*(n+1)+dy-e['anchor_y'])
def report(S, bx, by, bw, bh, n, cands, dx, dy, anchors=True, pad=60, thr=0.6):
    r=best_of(S,cands,bx,by,pad=pad,w=bw,h=bh,thr=thr)
    for s,lab,rx,ry,npx,tw,th in r[:4]:
        idx=int(lab.split(':')[1].split('(')[0]); f=lab.split(':')[0]
        if anchors: p=pred_loop(bh,n,dx,dy,f,idx)
        else: p=(dx, bh-15*(n+1)+dy)
        print(f'  {lab} score {s} n={npx} at rel ({rx},{ry}) pred {p} err ({rx-p[0]},{ry-p[1]})')
    return r
