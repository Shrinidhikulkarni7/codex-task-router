"""Rebuild the delivered voice on macOS; preserves clear provider attribution.

For a neural replacement, generate each script.json line with your chosen
authorized provider and replace the corresponding CAF (or update audio.py).
The build never downloads models, signs in or spends credits automatically.
"""
from pathlib import Path
import json,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
VOICE='com.apple.ttsbundle.siri_nicky_en-US_compact'
RATE='0.44'
def main():
    data=json.loads((ROOT/'script.json').read_text())
    with tempfile.TemporaryDirectory(prefix='router-film-voice-') as td:
        binary=Path(td)/'voice'
        subprocess.run(['swiftc','-module-cache-path',str(Path(td)/'modules'),str(ROOT/'source/voice.swift'),'-o',str(binary)],check=True)
        for line in data['lines']:
            out=ROOT/'assets/audio'/f'{line["id"]}.caf'
            subprocess.run([str(binary),VOICE,line['text'],str(out),RATE],check=True)
            p=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(out)]))
            line['duration']=float(p['format']['duration'])
    data['voice']={'provider':'Apple AVFoundation','voice':'Nicky','identifier':VOICE,'sample_rate':22050,'rate':float(RATE),'neural_status':'Not verified; local system voice substituted because cloud providers and Kokoro are unavailable'}
    (ROOT/'assets/audio/timing.json').write_text(json.dumps(data,indent=2)+'\n')
if __name__=='__main__':main()
