#!/usr/bin/env python3
"""Vaani STT backend: word stream over 16kHz mono audio.

The engine is picked from the model directory: a CTranslate2 Whisper model
(`model.bin` present, faster-whisper) when there is one, else Vosk. A model the
config names must load or the run fails loudly; nothing here falls back to a
different model.

Protocol on stdout (library logs stay on stderr):
  W <t_sec> <word>          one final word
  P <t_sec> <phrase>        current partial phrase (live UI), empty = cleared
  DONE audio=<s> infer=<s> words=<n> model=<dir>

Input: --wav PATH (16kHz mono wav), --stdin (whole raw s16le 16k mono), or
--stream (raw s16le 16k mono fed incrementally; emits P partials while the
caller is still recording, so the UI can show words live).
Exit nonzero on any failure; details go to stderr.
"""

import json
import os
import sys
import time
import wave

CHUNK_FRAMES = 4000
SAMPLE_RATE = 16000
# partial decode cadence and how much of the utterance it re-reads, so the
# live window costs a bounded slice of the audio instead of the whole run.
PARTIAL_EVERY_S = 1.2
PARTIAL_WINDOW_S = 8.0
# The daemon ends a run at 60 s, so a longer stdin/wav is not decoded past it.
MAX_AUDIO_S = 60.0
# 10 ms frame and the RMS floor under which a frame counts as silence.
FRAME = 160
SILENCE_RMS = 164.0  # ~ -46 dBFS


def feed(rec, frames, out):
    """Push PCM bytes; emit one W line per decoded word. Returns infer seconds."""
    words = 0
    infer = 0.0
    t0 = 0  # chunk start time in seconds
    for pcm in frames:
        t = t0
        t0 += len(pcm) / (2 * SAMPLE_RATE)
        s = time.time()
        final = rec.AcceptWaveform(pcm)
        infer += time.time() - s
        if final:
            for w in json.loads(rec.Result()).get("result", []):
                out.write(f"W {float(w.get('start', t)):.2f} {w['word']}\n")
                words += 1
            out.flush()
    return words, infer


def stream(rec, out):
    """Incremental stdin feed: P partials while audio arrives, W for finals.

    Reads with read1 so a partial is emitted as soon as bytes are available
    (the caller is still recording); read() would block for a full chunk.
    Returns (words, infer_secs, audio_secs).
    """
    stdin = sys.stdin.buffer
    audio_secs = 0.0
    infer = 0.0
    words = 0
    while True:
        data = stdin.read1(3200)
        if not data:
            break
        n = len(data) & ~1
        if n == 0:
            continue
        audio_secs += n / (2 * SAMPLE_RATE)
        s = time.time()
        final = rec.AcceptWaveform(data[:n])
        infer += time.time() - s
        if final:
            for w in json.loads(rec.Result()).get("result", []):
                out.write(f"W {float(w.get('start', audio_secs)):.2f} {w['word']}\n")
                words += 1
            out.write("P 0 \n")
        else:
            out.write(
                f"P {audio_secs:.2f} "
                f"{json.loads(rec.PartialResult()).get('partial', '')}\n"
            )
        out.flush()
    for w in json.loads(rec.FinalResult()).get("result", []):
        out.write(f"W {float(w.get('start', audio_secs)):.2f} {w['word']}\n")
        words += 1
    out.write("P 0 \n")
    out.flush()
    return words, infer, audio_secs


def trim_trailing_silence(pcm):
    """Drop trailing near-silent 10 ms frames; empty when there is no speech.

    Whisper hallucinates fluent text on silence, and the daemon hands it the
    end-of-speech wait as part of the utterance, so that tail is cut here
    rather than trusted to `no_speech_prob` (which reads 0.0 at temperature 0).
    The leading edge is left alone on purpose: without it Whisper invents a
    first word ("Eggie took an internship...").
    """
    import numpy as np

    a = np.frombuffer(pcm[: len(pcm) & ~1], np.int16).astype(np.float32)
    if a.size < FRAME:
        return pcm
    n = a.size // FRAME
    frames = a[: n * FRAME].reshape(n, FRAME)
    rms = np.sqrt((frames**2).mean(axis=1))
    floor = max(SILENCE_RMS, float(np.abs(a).max()) * 0.02)
    loud = np.nonzero(rms > floor)[0]
    if loud.size == 0:
        return b""
    end = (int(loud[-1]) + 1) * FRAME
    return frames[: end // FRAME].astype(np.int16).tobytes()


def load_whisper(model_dir):
    """Open a CTranslate2 Whisper model (see `class Whisper`)."""
    preload_cuda_libs()
    return Whisper(model_dir)


def preload_cuda_libs():
    """ctranslate2 dlopens cuBLAS/cuDNN by soname, and the pip `nvidia-*-cu12`
    wheels keep them outside the default search path. Loading them by absolute
    path first is what lets those sonames resolve; without this a CUDA build
    loads and then fails at the first encode. Absent wheels are not an error.
    """
    import ctypes
    import glob
    import sysconfig

    base = os.path.join(sysconfig.get_paths()["purelib"], "nvidia")
    for lib in sorted(glob.glob(os.path.join(base, "*", "lib", "*.so*"))):
        try:
            ctypes.CDLL(lib)
        except OSError:
            pass


class Whisper:
    """faster-whisper model on CUDA fp16, or CPU int8 when CUDA cannot decode.

    A CUDA build can load fine and then fail at the first encode when its
    cuBLAS/cuDNN libs are missing, so the fallback also happens at decode time
    and only costs speed: the words still come out.
    """

    def __init__(self, model_dir):
        self.dir = model_dir
        self.model = self._open(True)

    def _open(self, cuda):
        from faster_whisper import WhisperModel

        if not cuda:
            return WhisperModel(self.dir, device="cpu", compute_type="int8")
        try:
            return WhisperModel(self.dir, device="cuda", compute_type="float16")
        except Exception as e:  # no CUDA runtime, no GPU, or VRAM taken
            print(f"{self.dir}: cuda fp16 unavailable ({e}); using cpu int8", file=sys.stderr)
            return self._open(False)

    def decode(self, pcm, beam, timestamps=False):
        """Decode s16le bytes -> [(t_sec, word)], and the infer seconds."""
        try:
            return self._decode(pcm, beam, timestamps)
        except RuntimeError as e:
            print(f"{self.dir}: cuda decode failed ({e}); using cpu int8", file=sys.stderr)
            self.model = self._open(False)
            return self._decode(pcm, beam, timestamps)

    def _decode(self, pcm, beam, timestamps):
        import numpy as np

        pcm = trim_trailing_silence(pcm)
        if not pcm:
            return [], 0.0  # nothing above the noise floor: nothing to decode
        audio = np.frombuffer(pcm[: len(pcm) & ~1], np.int16).astype(np.float32) / 32768.0
        s = time.time()
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            task="transcribe",
            beam_size=beam,
            # temperature 0 pins one pass: the default fallback ladder re-decodes
            # at six temperatures whenever a chunk fails its thresholds (silence,
            # or the first second of speech), turning a 0.4s decode into 3-4s.
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
            without_timestamps=not timestamps,
        )
        words = []
        for seg in segments:  # lazy: the decode happens as this is walked
            # Whisper invents words for silence even at temperature 0 and reports
            # no_speech_prob 0.0, so the tap's silent tail is trimmed above
            # instead of being trusted to a threshold.
            # shortcut: one timestamp per segment instead of a word_timestamps
            # pass (which roughly doubles the decode); upgrade when the overlay
            # needs per-word timing inside a segment.
            t = seg.start if timestamps else 0.0
            for w in seg.text.replace("\u200b", "").split():
                words.append((t, w))
        return words, time.time() - s


def whisper_batch(model, pcm, out):
    """Whole utterance -> W lines. Returns (words, infer_secs)."""
    words, infer = model.decode(pcm[: int(MAX_AUDIO_S * 2 * SAMPLE_RATE)], 5, True)
    for t, w in words:
        out.write(f"W {t:.2f} {w}\n")
    out.flush()
    return len(words), infer


def whisper_stream(model, out):
    """Incremental stdin feed for Whisper: cheap tail partials, then one final.

    Same read1 discipline as the Vosk path (a P is emitted while the caller is
    still recording), but each partial decodes only the last
    PARTIAL_WINDOW_S of audio so the cost stays bounded.
    Returns (words, infer_secs, audio_secs).
    """
    stdin = sys.stdin.buffer
    pcm = bytearray()
    audio_secs = 0.0
    infer = 0.0
    last_partial = 0.0
    while True:
        data = stdin.read1(3200)
        if not data:
            break
        n = len(data) & ~1
        if n == 0:
            continue
        pcm += data[:n]
        audio_secs += n / (2 * SAMPLE_RATE)
        if audio_secs - last_partial < PARTIAL_EVERY_S:
            continue
        last_partial = audio_secs
        tail = bytes(pcm[int(max(0.0, audio_secs - PARTIAL_WINDOW_S) * 2 * SAMPLE_RATE) :])
        words, took = model.decode(tail, 1)
        infer += took
        out.write(f"P {audio_secs:.2f} {' '.join(w for _, w in words)}\n")
        out.flush()
    words, took = model.decode(bytes(pcm), 5, True)
    infer += took
    for t, w in words:
        out.write(f"W {t:.2f} {w}\n")
    out.write("P 0 \n")
    out.flush()
    return len(words), infer, audio_secs


def main():
    args = sys.argv[1:]
    mode = "wav"
    if "--wav" in args:
        wav_path = args[args.index("--wav") + 1]
    elif "--stream" in args:
        wav_path, mode = None, "stream"
    elif "--stdin" in args:
        wav_path, mode = None, "stdin"
    else:
        print("usage: transcribe.py --wav PATH | --stdin | --stream", file=sys.stderr)
        return 2
    use_stdin = mode == "stdin"

    model_dir = os.environ.get(
        "VAANI_STT_MODEL",
        "/home/saptodeep/Projects/Kyuma/models/vosk-model-small-en-us-0.15",
    )
    if not os.path.isdir(model_dir):
        print(f"model dir not found: {model_dir}", file=sys.stderr)
        return 1

    # The engine comes from the directory contents, so `stt_model` may name a
    # Vosk model or a CTranslate2 Whisper one (DOCS/configuration.md).
    whisper = os.path.isfile(os.path.join(model_dir, "model.bin"))
    if whisper:
        model = load_whisper(model_dir)
    else:
        from vosk import KaldiRecognizer, Model

        model = Model(model_dir)
        rec = KaldiRecognizer(model, SAMPLE_RATE)
        rec.SetWords(True)

    if mode == "stream":
        if whisper:
            words, infer, audio_secs = whisper_stream(model, sys.stdout)
        else:
            words, infer, audio_secs = stream(rec, sys.stdout)
        sys.stdout.write(
            f"DONE audio={audio_secs:.2f} infer={infer:.2f} words={words} model={model_dir}\n"
        )
        sys.stdout.flush()
        return 0

    if use_stdin:
        data = sys.stdin.buffer.read()
        n = len(data) & ~1
        frames = [data[i : i + 8000] for i in range(0, n, 8000) if data[i : i + 8000]]
        audio_secs = n / (2 * SAMPLE_RATE)
    else:
        try:
            wf = wave.open(wav_path, "rb")
        except (OSError, wave.Error) as e:
            print(f"bad wav {wav_path}: {e}", file=sys.stderr)
            return 2
        with wf:
            if wf.getframerate() != SAMPLE_RATE or wf.getnchannels() != 1:
                print(
                    f"{wav_path}: need 16kHz mono, "
                    f"got {wf.getframerate()}Hz x{wf.getnchannels()}",
                    file=sys.stderr,
                )
                return 2
            audio_secs = wf.getnframes() / wf.getframerate()
            frames = []
            while True:
                d = wf.readframes(CHUNK_FRAMES)
                if not d:
                    break
                frames.append(d)

    if whisper:
        words, infer = whisper_batch(model, b"".join(frames), sys.stdout)
        sys.stdout.write(
            f"DONE audio={audio_secs:.2f} infer={infer:.2f} words={words} model={model_dir}\n"
        )
        sys.stdout.flush()
        return 0

    words, infer = feed(rec, frames, sys.stdout)
    s = time.time()
    for w in json.loads(rec.FinalResult()).get("result", []):
        sys.stdout.write(f"W {float(w.get('start', audio_secs)):.2f} {w['word']}\n")
        words += 1
    infer += time.time() - s
    sys.stdout.write(
        f"DONE audio={audio_secs:.2f} infer={infer:.2f} words={words} model={model_dir}\n"
    )
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
