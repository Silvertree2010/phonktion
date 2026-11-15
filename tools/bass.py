import numpy as np, scipy.io.wavfile as wf, scipy.signal as ss, sys, os
names='C C# D D# E F F# G G# A A# B'.split()
for p in sys.argv[2:]:
    bpm=float(sys.argv[1]) if sys.argv[1]!='auto' else 143.6
    sr,x=wf.read(p); m=x.astype(float).mean(1); bar=240/bpm; half=bar/2
    seq=[]
    for i in range(int(len(m)/sr/half)):
        sg=m[int(i*half*sr):int((i+1)*half*sr)]
        if np.sqrt((sg**2).mean())<0.05*np.abs(m).max(): seq.append('.'); continue
        f,P=ss.welch(sg,sr,nperseg=min(len(sg),16384)); b=(f>35)&(f<130)
        seq.append(names[int(round(12*np.log2(f[b][np.argmax(P[b])]/440)+69))%12])
    ch=sum(1 for a,b in zip(seq,seq[1:]) if a!=b and '.' not in (a,b))
    print(os.path.basename(p)[:22].ljust(22), f"Wechsel/halbtakt {ch/len(seq):.2f}", ' '.join(seq[16:64]))
