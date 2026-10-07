"""Original 100 BPM acoustic-style miniature, SFX, narration assembly and mix.

No sampled instruments or third-party music. The oscillators, notes, envelopes,
seeded brush noise and score below are the editable source of the soundtrack.
Requires numpy and FFmpeg. Narration clips are separately replaceable.
"""
from pathlib import Path
import json, subprocess, wave
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'assets/audio'
SR=48000
DURATION=48
N=SR*DURATION
RNG=np.random.default_rng(4217)

def write(name,a):
    a=np.asarray(a)
    if a.ndim==1:a=np.column_stack([a,a])
    with wave.open(str(A/name),'wb') as f:
        f.setnchannels(a.shape[1]);f.setsampwidth(2);f.setframerate(SR)
        f.writeframes((np.clip(a,-1,1)*32767).astype('<i2').tobytes())

def add(dst,sound,at,gain=1,pan=0):
    begin=round(at*SR);end=min(N,begin+len(sound))
    if end<=begin:return
    sound=sound[:end-begin]*gain
    if dst.ndim==2:
        dst[begin:end,0]+=sound*np.sqrt((1-pan)/2)
        dst[begin:end,1]+=sound*np.sqrt((1+pan)/2)
    else:dst[begin:end]+=sound

def note(midi,duration=1.1,kind='pluck'):
    t=np.arange(round(duration*SR))/SR;f=440*2**((midi-69)/12)
    if kind=='bass':
        a=np.sin(2*np.pi*f*t)+.18*np.sin(4*np.pi*f*t)
        env=(1-np.exp(-t*45))*np.exp(-t*4.6)
    elif kind=='bell':
        a=np.sin(2*np.pi*f*t)+.25*np.sin(2*np.pi*f*2.01*t)*np.exp(-t*5)
        env=(1-np.exp(-t*300))*np.exp(-t*4.3)
    else:
        a=sum(np.sin(2*np.pi*f*k*t)*np.exp(-t*k*.8)/(k*k) for k in range(1,6))
        env=(1-np.exp(-t*190))*np.exp(-t*5.5)
    a*=env
    fade=min(len(t)//2,round(.018*SR))
    a[-fade:]*=np.linspace(1,0,fade)
    return a

def main():
    A.mkdir(parents=True,exist_ok=True)
    meta=json.loads((A/'timing.json').read_text())
    voice=np.zeros(N)
    for l in meta['lines']:
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(A/(l['id']+'.caf')),
            '-f','f32le','-ac','1','-ar',str(SR),'-'])
        data=np.frombuffer(raw,dtype='<f4').copy()
        # Remove only trailing silent padding; preserve actual pronunciation.
        voiced=np.flatnonzero(np.abs(data)>.001)
        if len(voiced):data=data[:min(len(data),voiced[-1]+round(.12*SR))]
        l['duration']=len(data)/SR
        end=l['start']+l['duration']
        l['end']=end
        add(voice,data,l['start'])
    for a,b in zip(meta['lines'],meta['lines'][1:]):
        if a['end']>b['start']-.12:raise RuntimeError('Narration overlaps: '+a['id'])
    if meta['lines'][-1]['end']>46.6:raise RuntimeError('Ending needs more breathing room')
    # Predictable headroom; transparent voice normalization, no timbre claims.
    voice*=.74/max(.01,float(np.max(np.abs(voice))))
    write('narration.wav',voice)
    music=np.zeros((N,2));sfx=np.zeros((N,2));beat=.6
    chords=[[60,64,67,71],[57,60,64,67],[53,57,60,64],[55,59,62,67]]
    # 20 bars, alternating plucked ostinato and sparse bell responses.
    for bar in range(20):
        ch=chords[(bar//2)%4];base=bar*4*beat
        for k in range(8):
            add(music,note(ch[[0,2,1,3,2,1,3,2][k]]),base+k*beat/2,.045,(-.45 if k%2==0 else .45))
        for k in [0,2]:add(music,note(ch[0]-24,1.3,'bass'),base+k*beat,.065,-.08)
        if bar%2==1:
            for k,m in enumerate([ch[2]+12,ch[1]+12,ch[0]+12]):
                add(music,note(m,1.2,'bell'),base+(1.5+k*.5)*beat,.020,.3)
        for k in [1,3]:
            tt=np.arange(round(.09*SR))/SR
            brush=RNG.normal(0,1,len(tt));brush=np.convolve(brush,np.ones(7)/7,mode='same')
            add(music,brush*np.exp(-tt*65),base+k*beat,.015,-.2)
    # Phrase endings get a little air; the last chord gently resolves.
    for m in [60,64,67,72]:add(music,note(m,2.2,'bell'),46.1,.036,(m-66)/20)
    mt=np.arange(N)/SR
    fade=np.clip(mt/.65,0,1)*np.clip((48-mt)/1.25,0,1)
    music*=fade[:,None]
    # Restrained paper swishes and wooden clicks, all synthesized.
    for tm,pan in [(0.35,-.4),(1.0,.35),(9,-.2),(14.7,.2),(23.8,-.2),(25.5,.2),(28.3,-.2),(34.7,.2),(40.9,0)]:
        tt=np.arange(round(.33*SR))/SR
        noise=RNG.normal(0,1,len(tt));noise=np.convolve(noise,np.ones(28)/28,mode='same')
        env=np.sin(np.pi*tt/.33)**2
        add(sfx,noise*env,tm,.10,pan)
        add(sfx,note(76,.18,'pluck'),tm+.18,.085,pan)
    for tm in [23.0,24.3,26.7,31.0,32.0,33.0,43.0]:
        add(sfx,note(84,.3,'bell'),tm,.055,.25)
    write('music-original.wav',music)
    write('sfx-original.wav',sfx)
    # Speech-dependent attenuation; broad 1.4k/3k EQ carve below leaves room for
    # speech articulation even between the plucked notes.
    duck=np.ones(N)
    for l in meta['lines']:
        a,b=l['start'],l['end']
        mask=(mt>=a-.16)&(mt<=b+.25)
        ramp=np.minimum(np.clip((mt-a+.16)/.16,0,1),np.clip((b+.25-mt)/.25,0,1))
        duck[mask]=np.minimum(duck[mask],1-.48*ramp[mask])
    write('music-ducked.wav',music*duck[:,None])
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(A/'music-ducked.wav'),
        '-af','equalizer=f=1400:t=q:w=0.8:g=-4,equalizer=f=3000:t=q:w=0.8:g=-3',
        str(A/'music-carved.wav')],check=True)
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(A/'narration.wav'),'-i',str(A/'music-carved.wav'),'-i',str(A/'sfx-original.wav'),
        '-filter_complex','[0:a][1:a][2:a]amix=inputs=3:normalize=0,alimiter=limit=0.88:level=false,loudnorm=I=-16:TP=-1.5:LRA=7[a]',
        '-map','[a]','-ar',str(SR),'-ac','2',str(A/'mix.wav')],check=True)
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(A/'mix.wav'),'-c:a','aac','-b:a','192k',str(A/'mix.m4a')],check=True)
    (A/'timing.json').write_text(json.dumps(meta,indent=2)+'\n')
    def timestamp(t):
        ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    srt='\n\n'.join(f'{i+1}\n{timestamp(l["start"])} --> {timestamp(l["end"])}\n{l["text"]}' for i,l in enumerate(meta['lines']))+'\n'
    (ROOT/'renders/codex-task-router.srt').write_text(srt)
    print(json.dumps({'duration':DURATION,'narration_end':meta['lines'][-1]['end'],'voice':meta['voice'],'lines':[{k:l[k] for k in ['id','start','end']} for l in meta['lines']]},indent=2))

if __name__=='__main__':main()
