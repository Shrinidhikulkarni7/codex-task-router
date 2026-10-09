"""Build the offline player, HyperFrames entry, and caption sidecar."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "renders"


def main():
    OUT.mkdir(exist_ok=True)
    session = json.loads((ROOT / "assets/session.json").read_text())
    captions = json.loads((ROOT / "assets/captions.json").read_text())
    script = (ROOT / "source/film.js").read_text()
    data = "window.DEMO_SESSION=" + json.dumps(session) + ";window.DEMO_CAPTIONS=" + json.dumps(captions) + ";"
    art = data + script
    player = (ROOT / "source/player.html").read_text().replace("/*__ART__*/", art)
    (OUT / "player.html").write_text(player)
    entry = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Codex Task Router — terminal replay</title>
<style>html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:#F3F0E8}#art,#art svg{display:block;width:100%;height:100%}</style></head><body>
<div id="terminal-demo" data-composition-id="terminal-demo" data-no-timeline data-width="1080" data-height="1920" data-duration="35" data-fps="30"><div id="art" class="clip" data-start="0" data-duration="35" data-track-index="0"></div></div>
<script>/*__ART__*/</script><script>
window.renderAt=t=>{document.getElementById('art').innerHTML=TerminalDemo.frame(t);};
window.addEventListener('hf-seek',e=>renderAt(e.detail.time));renderAt(0);window.filmReady=true;
</script></body></html>'''
    (ROOT / "index.html").write_text(entry.replace("/*__ART__*/", art))
    def stamp(t):
        ms = round(t*1000)
        return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"
    srt = "\n\n".join(f"{i}\n{stamp(c['start'])} --> {stamp(c['end'])}\n" + "\n".join(c['lines']) for i,c in enumerate(captions,1)) + "\n"
    (OUT / "terminal-demo.srt").write_text(srt)
    print(json.dumps({"duration":35,"fps":30,"width":1080,"height":1920,"player_bytes":len(player.encode()),"audio":"intentional silence"}))


if __name__ == "__main__":
    main()
