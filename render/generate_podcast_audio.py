"""Generate multi-speaker podcast/debate audio via Kokoro ONNX TTS.

Usage: python generate_podcast_audio.py <dialogue.json> <output_dir>

dialogue.json format:
  {"turns": [{"speaker": "Host", "text": "...", "voice": "af_sarah"}, ...]}

Outputs: 00_Host.wav, 01_Expert.wav, ... (one per turn, in order).
Also writes a concat list to output_dir/concat.txt for ffmpeg.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

MODEL_URL  = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

# Fallback voice mapping (if a turn doesn't specify a voice)
SPEAKER_VOICES: dict[str, str] = {
    "Host":      "af_sarah",
    "Expert":    "af_heart",
    "Skeptic":   "bm_george",
    "Moderator": "af_sarah",
    "Proponent": "af_heart",
    "Opponent":  "bm_george",
}
DEFAULT_VOICE = "af_sarah"


def download_if_missing(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 1024:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f">> downloading {url} -> {path}", flush=True)
    urllib.request.urlretrieve(url, path)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: generate_podcast_audio.py <dialogue.json> <output_dir>", file=sys.stderr)
        sys.exit(2)

    dialogue_path = Path(sys.argv[1])
    output_dir    = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    cache       = Path.home() / ".kokoro"
    model_path  = cache / "kokoro-v1.0.onnx"
    voices_path = cache / "voices-v1.0.bin"
    download_if_missing(MODEL_URL, model_path)
    download_if_missing(VOICES_URL, voices_path)

    kokoro = Kokoro(str(model_path), str(voices_path))

    turns = json.loads(dialogue_path.read_text(encoding="utf-8")).get("turns", [])
    if not turns:
        raise RuntimeError("dialogue.json has no turns")

    wav_files: list[Path] = []

    for i, turn in enumerate(turns):
        speaker = turn.get("speaker", "Host")
        text    = (turn.get("text") or "").strip()
        voice   = turn.get("voice") or SPEAKER_VOICES.get(speaker, DEFAULT_VOICE)

        out_path = output_dir / f"{i:02d}_{speaker}.wav"

        if not text:
            # 0.5 s silence placeholder
            samples = np.zeros(12000, dtype=np.float32)
            sr = 24000
        else:
            try:
                samples, sr = kokoro.create(text, voice=voice, speed=1.0, lang="en-us")
            except Exception as exc:
                print(f"  [warn] TTS failed for turn {i} ({speaker}): {exc} — inserting silence", flush=True)
                samples = np.zeros(24000, dtype=np.float32)
                sr = 24000

        sf.write(out_path, samples, sr)
        wav_files.append(out_path)
        print(f"  -> {out_path} ({len(samples)/sr:.1f}s)", flush=True)

    # Write concat list for ffmpeg
    concat_path = output_dir / "concat.txt"
    with concat_path.open("w", encoding="utf-8") as f:
        for wav in wav_files:
            f.write(f"file '{wav.resolve()}'\n")
    print(f">> concat list: {concat_path}", flush=True)


if __name__ == "__main__":
    main()
