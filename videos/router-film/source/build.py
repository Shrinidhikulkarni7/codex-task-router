"""Build the completely self-contained player and HyperFrames composition."""
from pathlib import Path
import base64,json

ROOT=Path(__file__).resolve().parents[1]
def main():
    script=(ROOT/'source/film.js').read_text()
    meta=json.loads((ROOT/'assets/audio/timing.json').read_text())
    audio=base64.b64encode((ROOT/'assets/audio/mix.m4a').read_bytes()).decode()
    player='''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codex Task Router — Keep the thread</title>
<style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#293936;color:#F5EEDD;font:16px system-ui,sans-serif}
main{max-width:1400px;margin:auto}#picture{width:100%;aspect-ratio:16/9;background:#F5EEDD;overflow:hidden}#picture svg{display:block;width:100%;height:100%}
.controls{display:flex;align-items:center;gap:15px;padding:14px 20px}button{background:#F5EEDD;border:0;border-radius:7px;color:#293936;padding:10px 17px;cursor:pointer;font:inherit}button:focus-visible,input:focus-visible{outline:3px solid #E5B958;outline-offset:3px}input{flex:1;min-width:40px;accent-color:#E5B958}#clock{font-variant-numeric:tabular-nums;white-space:nowrap}.note{font-size:13px;line-height:1.6;opacity:.8;padding:0 20px 16px;margin:0}
#caption{min-height:2.8em;text-align:center;line-height:1.4;padding:0 15px;font-size:17px;max-width:1000px;margin:auto}
body.export{background:#F5EEDD;overflow:hidden}body.export main{max-width:none}body.export .controls,body.export .note,body.export #caption{display:none}
@media(max-width:600px){.controls{gap:8px;padding:10px}button{padding:8px}#caption{font-size:14px}.note{font-size:11px}}
</style></head><body>
<main aria-label="Animated Codex Task Router film"><div id="picture"></div>
<audio id="mix" preload="auto" src="data:audio/mp4;base64,__AUDIO__"></audio>
<div class="controls"><button id="play" aria-label="Play video">Play</button><button id="restart" aria-label="Restart video">Restart</button><input id="seek" type="range" min="0" max="48" step="0.033333" value="0" aria-label="Video position"><span id="clock">0:00 / 0:48</span><button id="mute" aria-label="Mute audio">Sound on</button></div>
<p id="caption" aria-live="off"></p>
<p class="note">Illustrated policy examples, not a live screen recording. Narration: Apple Nicky (installed system voice; neural model status unverified). Original illustrations, lettering, music and sound design. No network access is needed to play this file.</p>
</main><script>__FILM__</script><script>
const lines=__LINES__;
const sound=document.getElementById('mix'),picture=document.getElementById('picture'),seek=document.getElementById('seek'),play=document.getElementById('play');
let raf=0,lastFrame=-1;
const isExport=new URLSearchParams(location.search).has('render');if(isExport)document.body.classList.add('export');
window.renderAt=function(seconds){const t=Math.max(0,Math.min(48,Number(seconds)||0));const frame=Math.min(1439,Math.floor(t*30+1e-7));if(frame!==lastFrame){picture.innerHTML=RouterFilm.frame(frame/30);lastFrame=frame;}seek.value=t;document.getElementById('clock').textContent='0:'+String(Math.floor(t)).padStart(2,'0')+' / 0:48';const line=lines.find(l=>t>=l.start&&t<l.end);document.getElementById('caption').textContent=line?line.text:'';return frame;};
function tick(){renderAt(sound.currentTime);if(!sound.paused)raf=requestAnimationFrame(tick);}
async function toggle(){if(sound.paused){if(sound.currentTime>=47.95)sound.currentTime=0;await sound.play();play.textContent='Pause';play.setAttribute('aria-label','Pause video');tick();}else{sound.pause();cancelAnimationFrame(raf);play.textContent='Play';play.setAttribute('aria-label','Play video');}}
play.addEventListener('click',()=>toggle().catch(e=>{document.getElementById('caption').textContent='Audio playback needs a click: '+e.message;}));
document.getElementById('restart').addEventListener('click',()=>{sound.currentTime=0;renderAt(0);});
seek.addEventListener('input',()=>{sound.currentTime=Number(seek.value);renderAt(sound.currentTime);});
sound.addEventListener('seeked',()=>renderAt(sound.currentTime));
sound.addEventListener('ended',()=>{cancelAnimationFrame(raf);renderAt(48);play.textContent='Replay';play.setAttribute('aria-label','Replay video');});
document.getElementById('mute').addEventListener('click',e=>{sound.muted=!sound.muted;e.target.textContent=sound.muted?'Sound off':'Sound on';e.target.setAttribute('aria-label',sound.muted?'Unmute audio':'Mute audio');});
document.addEventListener('keydown',e=>{if(e.code==='Space'&&!['INPUT','BUTTON'].includes(document.activeElement.tagName)){e.preventDefault();toggle();}});
renderAt(0);window.filmReady=true;
</script></body></html>'''
    player=player.replace('__AUDIO__',audio).replace('__FILM__',script).replace('__LINES__',json.dumps(meta['lines']))
    (ROOT/'renders/player.html').write_text(player)
    # Native seek event, no GSAP or framework dependency in the artwork.
    comp='''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Keep the thread</title><style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#F5EEDD}#router-film{width:100%;height:100%}#art,#art svg{display:block;width:100%;height:100%}</style></head><body>
<div id="router-film" data-composition-id="router-film" data-no-timeline data-width="1920" data-height="1080" data-duration="48" data-fps="30"><div id="art" class="clip" data-start="0" data-duration="48" data-track-index="0"></div><audio id="film-mix" src="assets/audio/mix.m4a" data-start="0" data-duration="48" data-track-index="1" data-volume="1"></audio></div>
<script>__FILM__</script><script>window.renderAt=t=>{document.getElementById('art').innerHTML=RouterFilm.frame(t);};window.addEventListener('hf-seek',e=>renderAt(e.detail.time));renderAt(0);</script></body></html>'''
    (ROOT/'index.html').write_text(comp.replace('__FILM__',script))
    print(json.dumps({'player_bytes':(ROOT/'renders/player.html').stat().st_size,'duration':48,'embedded_audio':True,'external_assets':False}))

if __name__=='__main__':main()
