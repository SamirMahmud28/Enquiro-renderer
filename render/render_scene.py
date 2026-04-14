"""Parse a Manim source file, find Scene subclasses, render each at 720p30.

Usage: python render_scene.py <scene.py> <output_dir>
Outputs MP4 files named 00_<SceneName>.mp4, 01_<SceneName>.mp4, ... in output order.
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from pathlib import Path


def find_scene_classes(source_path: Path) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    scenes: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = ""
            if isinstance(base, ast.Name):
                name = base.id
            elif isinstance(base, ast.Attribute):
                name = base.attr
            if name in {"Scene", "MovingCameraScene", "ThreeDScene", "ZoomedScene"}:
                scenes.append(node.name)
                break
    return scenes


def render_scene(source: Path, scene_name: str, media_dir: Path) -> Path:
    cmd = [
        "manim",
        "-q", "m",           # medium quality (720p30)
        "--media_dir", str(media_dir),
        "--format", "mp4",
        "--disable_caching",
        str(source),
        scene_name,
    ]
    print(f">> {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)

    # Manim writes to media_dir/videos/<source_stem>/720p30/<SceneName>.mp4
    candidates = list(media_dir.rglob(f"{scene_name}.mp4"))
    if not candidates:
        raise RuntimeError(f"Rendered file for scene {scene_name} not found")
    return candidates[0]


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: render_scene.py <scene.py> <output_dir>", file=sys.stderr)
        sys.exit(2)

    source = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    media_dir = output_dir.parent / "manim_media"

    scenes = find_scene_classes(source)
    if not scenes:
        raise RuntimeError("No Scene subclasses found in source")
    print(f"Found {len(scenes)} scenes: {scenes}", flush=True)

    for i, scene_name in enumerate(scenes):
        mp4 = render_scene(source, scene_name, media_dir)
        dest = output_dir / f"{i:02d}_{scene_name}.mp4"
        shutil.copy2(mp4, dest)
        print(f"  -> {dest}", flush=True)


if __name__ == "__main__":
    main()
