"""Merge per-scene video + audio, then concat all parts into final.mp4.

Usage: python merge.py <scenes_dir> <audio_dir> <output.mp4>

For each index i:
  - scenes_dir/{i:02}_*.mp4 is paired with audio_dir/{i:02}.wav
  - video is padded (freeze last frame) or sped up to match audio duration
  - scene i mixed into parts/{i:02}.mp4
Finally concat all parts via ffmpeg concat demuxer.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(path),
    ])
    return float(json.loads(out)["format"]["duration"])


def run(cmd: list[str]) -> None:
    print(">>", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def mix_one(video: Path, audio: Path, out: Path) -> None:
    v_dur = ffprobe_duration(video)
    a_dur = ffprobe_duration(audio)

    if a_dur > v_dur + 0.1:
        # extend video by freezing the last frame (tpad)
        pad = a_dur - v_dur
        vf = f"tpad=stop_mode=clone:stop_duration={pad:.3f}"
        run([
            "ffmpeg", "-y",
            "-i", str(video), "-i", str(audio),
            "-filter:v", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k",
            "-shortest",
            str(out),
        ])
    else:
        # video longer or equal: just mux, trimming to audio length
        run([
            "ffmpeg", "-y",
            "-i", str(video), "-i", str(audio),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k",
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", f"{a_dur:.3f}",
            str(out),
        ])


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: merge.py <scenes_dir> <audio_dir> <output.mp4>", file=sys.stderr)
        sys.exit(2)

    scenes_dir = Path(sys.argv[1])
    audio_dir = Path(sys.argv[2])
    final_out = Path(sys.argv[3])
    parts_dir = final_out.parent / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    videos = sorted(scenes_dir.glob("*.mp4"))
    audios = sorted(audio_dir.glob("*.wav"))
    if not videos:
        raise RuntimeError("No scene videos found")

    n = min(len(videos), len(audios))
    part_paths: list[Path] = []
    for i in range(n):
        part = parts_dir / f"{i:02d}.mp4"
        mix_one(videos[i], audios[i], part)
        part_paths.append(part)

    # concat demuxer
    list_file = parts_dir / "concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in part_paths),
        encoding="utf-8",
    )
    run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(final_out),
    ])
    print(f"Final: {final_out} ({ffprobe_duration(final_out):.1f}s)", flush=True)


if __name__ == "__main__":
    main()
