import numpy as np, scipy.io.wavfile as wf, scipy.signal as ss, sys, os
def load(p):
    sr,x=wf.read(p); x=x.astype(float)
    if x.ndim==1: x=np.stack([x,x],1)
    x/=np.abs(x).max(); return sr,x
names='C C# D D# E F F# G G# A A# B'.split()
def bpm_of(m,sr):
    h=512; f,t,S=ss.stft(m,sr,nperseg=2048,noverlap=2048-h); M=np.abs(S)
    fl=np.maximum(np.diff(np.log1p(M*10),axis=1),0).sum(0); fl-=fl.mean()
    ac=np.correlate(fl,fl,'full')[len(fl)-1:]; lags=np.arange(len(ac))*h/sr
    with np.errstate(divide='ignore'): b=60/lags
    msk=(b>125)&(b<175); return b[msk][np.argmax(ac[msk])], fl, sr/h
def band(x,sr,lo,hi): return ss.sosfilt(ss.butter(4,[lo,hi],'bandpass',fs=sr,output='sos'),x)
for p in sys.argv[1:]:
    sr,x=load(p); m=x.mean(1); s=(x[:,0]-x[:,1])/2
    bpm,fl,fr=bpm_of(m,sr); bar=4*60/bpm; nb=int(len(m)/sr/bar)
    rms=[20*np.log10(np.sqrt((m[int(i*bar*sr):int((i+1)*bar*sr)]**2).mean())+1e-9) for i in range(nb)]
    mx=np.median(sorted(rms)[-max(4,nb//3):])
    lvl=''.join('█' if r>mx-2 else ('▓' if r>mx-5 else ('▒' if r>mx-10 else '░')) for r in rms)
    intro=next(i for i,r in enumerate(rms) if r>mx-2)
    f,P=ss.welch(m,sr,nperseg=32768); bm=(f>200)&(f<2500)
    pc=np.round(12*np.log2(f[bm]/440)+69)%12; ch=np.array([P[bm][pc==k].sum() for k in range(12)]); ch/=ch.max()
    key=' '.join(f"{names[k]}{ch[k]:.2f}" for k in np.argsort(-ch)[:5])
    sb=(f>25)&(f<100); sub=f[sb][np.argmax(P[sb])]
    # Stereo
    def w(lo,hi): 
        mm=band(m,sr,lo,hi); sm=band(s,sr,lo,hi); return 10*np.log10((sm**2).mean()/((mm**2).mean()+1e-12)+1e-12)
    # loud section = bars within 2 dB of max
    loud=[i for i,r in enumerate(rms) if r>mx-2]
    i0=loud[len(loud)//3]; seg=slice(int(i0*bar*sr),int((i0+8)*bar*sr))
    mid=band(m[seg],sr,300,3000); env=np.abs(ss.hilbert(mid)); beat=bar/4
    ph=((np.arange(len(env))/sr)%beat/beat*32).astype(int)
    prof=np.array([env[ph==k].mean() for k in range(32)]); pump=20*np.log10(prof.max()/prof.min())
    crest=20*np.log10(np.abs(m[seg]).max()/np.sqrt((m[seg]**2).mean()))
    # Melodie: dominante Tonhoehe pro 16tel 250-1500 Hz
    s16=beat/4; notes=[]
    for k in range(128):
        a=int((i0*bar+k*s16)*sr); sg=m[a:a+int(s16*sr)]*np.hanning(int(s16*sr))
        F=np.abs(np.fft.rfft(sg,8*len(sg))); ff=np.fft.rfftfreq(8*len(sg),1/sr); bb=(ff>250)&(ff<1500)
        notes.append(int(round(12*np.log2(ff[bb][np.argmax(F[bb])]/440)+69)))
    notes=np.array(notes); rng=notes.max()-notes.min(); upc=len(set(notes%12))
    rep=next((L for L in (8,16,32,48,64) if (notes[L:]==notes[:-L]).mean()>0.6),'>64')
    jumps=np.abs(np.diff(notes)); oct_=(jumps==12).mean()
    # Onsetdichte
    pk,_=ss.find_peaks(fl,height=np.percentile(fl,90),distance=int(fr*0.05)); dens=len(pk)/(len(m)/sr)
    print(f"\n== {os.path.basename(p)}  {len(m)/sr:.0f}s  BPM {bpm:.1f}  Takte {nb}  Intro {intro} Takte")
    print(f"   Key: {key} | Sub-Peak {sub:.0f} Hz | Crest {crest:.1f} dB | Pump {pump:.1f} dB | Onsets/s {dens:.1f}")
    print(f"   Stereo S/M: <120Hz {w(30,120):.1f} | 200-2k {w(200,2000):.1f} | 2k-8k {w(2000,8000):.1f} dB")
    print(f"   Melodie: Umfang {rng} HT, {upc} Tonklassen, Wiederholung alle {rep} 16tel, Oktavsprünge {oct_*100:.0f}%")
    print(f"   Struktur: {lvl}")
