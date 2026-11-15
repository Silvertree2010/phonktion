import numpy as np, sys
W,H=1080,1080
img=np.zeros((H,W,3))
r=np.linspace(2.8,4.0,W*3)
x=np.full_like(r,0.5)
for _ in range(800): x=r*x*(1-x)
acc=np.zeros((H,W))
for _ in range(1500):
    x=r*x*(1-x)
    xi=((r-2.8)/1.2*(W-1)).astype(int); yi=((1-x)*(H*0.7)+H*0.12).astype(int)
    np.add.at(acc,(yi,xi),1)
a=np.log1p(acc); a/=a.max()
# Farbe: Ordnung kalt -> Chaos heiss
u=np.linspace(0,1,W)[None,:]
img[...,0]=a*(0.3+0.9*u); img[...,1]=a*(0.9-0.6*u); img[...,2]=a*(1.0-0.8*u)
img=np.clip(img,0,1)
sys.stdout.buffer.write(b"P6 %d %d 255\n"%(W,H)+(img*255).astype(np.uint8).tobytes())
