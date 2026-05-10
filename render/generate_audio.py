"""Generate per-scene narration WAV files via Kokoro ONNX TTS.

Usage: python generate_audio.py <narration.json> <output_dir>
narration.json: {"segments": [{"scene_id": "scene_01", "duration_s": 15, "text": "..."}]}
Outputs 00.wav, 01.wav, ... (one per segment in order).
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

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"


def download_if_missing(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 1024:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f">> downloading {url} -> {path}", flush=True)
    urllib.request.urlretrieve(url, path)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: generate_audio.py <narration.json> <output_dir>", file=sys.stderr)
        sys.exit(2)

    narration_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    cache = Path.home() / ".kokoro"
    model_path = cache / "kokoro-v1.0.onnx"
    voices_path = cache / "voices-v1.0.bin"
    download_if_missing(MODEL_URL, model_path)
    download_if_missing(VOICES_URL, voices_path)

    voice = os.environ.get("VOICE", "af_sarah")
    kokoro = Kokoro(str(model_path), str(voices_path))

    segments = json.loads(narration_path.read_text(encoding="utf-8")).get("segments", [])
    if not segments:
        raise RuntimeError("narration.json has no segments")

    for i, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        if not text:
            # silent 1-second placeholder
            samples = np.zeros(24000, dtype=np.float32)
            sr = 24000
        else:
            samples, sr = kokoro.create(text, voice=voice, speed=1.0, lang="en-us")
        out = output_dir / f"{i:02d}.wav"
        sf.write(out, samples, sr)
        print(f"  -> {out} ({len(samples)/sr:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
