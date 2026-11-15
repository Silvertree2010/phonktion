import numpy as np, scipy.io.wavfile as wf, scipy.signal as ss, sys
sr,x=wf.read(sys.argv[1]); x=x.astype(float).mean(1)
f,P=ss.welch(x,sr,nperseg=32768); b=(f>200)&(f<2500); f,P=f[b],P[b]
pc=np.round(12*np.log2(f/440)+69)%12; names='C C# D D# E F F# G G# A A# B'.split()
ch=np.array([P[pc==k].sum() for k in range(12)]); ch/=ch.max()
print(' '.join(f"{n}:{v:.2f}" for n,v in sorted(zip(names,ch),key=lambda z:-z[1])))
