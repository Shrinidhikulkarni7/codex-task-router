import AVFoundation
import Foundation

// Render one line through a locally installed Apple voice. This does not
// download a voice or claim that an unspecified Apple voice is neural.
let args = CommandLine.arguments
if args.count < 4 { fputs("usage: voice VOICE_ID TEXT OUTPUT.caf [RATE]\n", stderr); exit(2) }
guard let voice = AVSpeechSynthesisVoice(identifier: args[1]) else {
    fputs("Requested voice is not available\n", stderr); exit(3)
}
let utterance = AVSpeechUtterance(string: args[2])
utterance.voice = voice
utterance.rate = args.count > 4 ? Float(args[4]) ?? 0.48 : 0.48
utterance.pitchMultiplier = 1.02
let synthesizer = AVSpeechSynthesizer()
var output: AVAudioFile?
var finished = false
var samples: AVAudioFramePosition = 0
synthesizer.write(utterance) { buffer in
    guard let pcm = buffer as? AVAudioPCMBuffer else { return }
    if pcm.frameLength == 0 { finished = true; return }
    do {
        if output == nil {
            output = try AVAudioFile(forWriting: URL(fileURLWithPath: args[3]),
                                     settings: pcm.format.settings)
        }
        try output?.write(from: pcm)
        samples += AVAudioFramePosition(pcm.frameLength)
    } catch { fputs("Audio write failed: \(error)\n", stderr); exit(4) }
}
let deadline = Date(timeIntervalSinceNow: 45)
while !finished && Date() < deadline { RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.02)) }
if !finished || samples == 0 { fputs("Voice synthesis did not produce audio\n", stderr); exit(5) }
print("\(voice.identifier): \(samples) frames written")
