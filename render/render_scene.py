"""Render slide_specs.json to per-scene MP4 clips using Pillow + ffmpeg.

Usage: python render_scene.py <slide_specs.json> <output_dir>

Each slide spec:
  {
    "scene_id": "scene_01",
    "layout": "image_top|image_left|text_only|split",
    "image_url": "https://..." or null,
    "headline": "...",
    "supporting_text": "...",
    "text_size": "large|medium|small",
    "narration_text": "Full narration text for subtitles.",
    "duration_s": 20
  }

Outputs 00.mp4, 01.mp4, ... in output_dir (same numbering merge.py expects).
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── Constants ──────────────────────────────────────────────────────────────

W, H = 1920, 1080
BG_COLOR = (13, 17, 23)           # #0d1117 dark background
HEADLINE_COLOR = (230, 237, 243)  # near-white
SUPPORT_COLOR = (139, 148, 158)   # muted grey
ACCENT_COLOR = (88, 166, 255)     # blue accent bar

FONT_PATHS = [
    # Ubuntu / Debian (GitHub Actions)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    # Windows
    "C:/Windows/Fonts/Arial.ttf",
]


def _find_font() -> str | None:
    for path in FONT_PATHS:
        if Path(path).exists():
            return path
    return None


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _find_font()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _download_image(url: str) -> Image.Image | None:
    """Download image from URL; composite transparent PNGs on white. Returns RGB Image."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchGPT-Renderer/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        img = Image.open(BytesIO(data)).convert("RGBA")

        # Composite on white so transparent-background paper figures
        # don't bleed black onto the dark canvas
        white_bg = Image.new("RGB", img.size, (255, 255, 255))
        white_bg.paste(img, mask=img.split()[3])
        return white_bg
    except Exception as exc:
        print(f"  [warn] could not download image: {exc}", flush=True)
        return None


def _resize_contain(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    ratio = min(max_w / img.width, max_h / img.height)
    new_w, new_h = int(img.width * ratio), int(img.height * ratio)
    return img.resize((new_w, new_h), Image.LANCZOS)


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    color: tuple,
    center_x: int,
    top_y: int,
    line_spacing: int = 8,
) -> int:
    y = top_y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        draw.text((center_x - text_w // 2, y), line, font=font, fill=color)
        y += (bbox[3] - bbox[1]) + line_spacing
    return y


def _draw_text_area(
    draw: ImageDraw.ImageDraw,
    headline: str,
    supporting_text: str,
    h_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    s_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    top_y: int,
    max_w: int,
    center_x: int,
) -> None:
    bottom = top_y
    if headline:
        lines = _wrap_text(draw, headline, h_font, max_w)
        bottom = _draw_text_block(draw, lines, h_font, HEADLINE_COLOR, center_x, top_y, 10)
    if supporting_text:
        lines = _wrap_text(draw, supporting_text, s_font, max_w)
        _draw_text_block(draw, lines, s_font, SUPPORT_COLOR, center_x, bottom + 20, 6)


def render_slide(spec: dict, out_path: Path) -> None:
    layout = spec.get("layout", "text_only")
    image_url = spec.get("image_url") or None
    headline = spec.get("headline", "")
    supporting_text = spec.get("supporting_text", "")
    text_size = spec.get("text_size", "medium")

    h_size = {"large": 68, "medium": 54, "small": 42}.get(text_size, 54)
    s_size = {"large": 34, "medium": 30, "small": 26}.get(text_size, 30)

    canvas = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)
    h_font = _load_font(h_size)
    s_font = _load_font(s_size)

    # Top accent bar
    draw.rectangle([(0, 0), (W, 6)], fill=ACCENT_COLOR)

    photo: Image.Image | None = None
    if image_url and layout != "text_only":
        photo = _download_image(image_url)

    if layout == "image_top" and photo:
        img_h = int(H * 0.62)
        resized = _resize_contain(photo, W - 40, img_h - 20)
        paste_x = (W - resized.width) // 2
        canvas.paste(resized, (paste_x, 12))
        _draw_text_area(draw, headline, supporting_text, h_font, s_font,
                        img_h + 24, W - 120, W // 2)

    elif layout == "image_left" and photo:
        img_w = W // 2
        resized = _resize_contain(photo, img_w - 60, H - 80)
        paste_y = (H - resized.height) // 2
        canvas.paste(resized, (30, paste_y))
        _draw_text_area(draw, headline, supporting_text, h_font, s_font,
                        H // 2 - 80, W // 2 - 80, img_w + W // 4)

    elif layout == "split" and photo:
        img_h = H // 2
        resized = _resize_contain(photo, W - 120, img_h - 40)
        paste_x = (W - resized.width) // 2
        canvas.paste(resized, (paste_x, 20))
        _draw_text_area(draw, headline, supporting_text, h_font, s_font,
                        img_h + 20, W - 120, W // 2)

    else:
        _draw_text_area(draw, headline, supporting_text, h_font, s_font,
                        H // 2 - 80, W - 160, W // 2)

    canvas.save(str(out_path))


# ── Subtitle helpers ───────────────────────────────────────────────────────

def _fmt_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_srt(text: str, duration_s: float, srt_path: Path) -> None:
    """Split narration text into ~10-word chunks and write a timed SRT file."""
    words = text.split()
    if not words:
        srt_path.write_text("", encoding="utf-8")
        return

    chunk_size = 10
    chunks = [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)]
    time_per_chunk = duration_s / len(chunks)

    lines: list[str] = []
    for i, chunk in enumerate(chunks):
        start = i * time_per_chunk
        end = (i + 1) * time_per_chunk
        lines += [
            str(i + 1),
            f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}",
            chunk,
            "",
        ]

    srt_path.write_text("\n".join(lines), encoding="utf-8")


# ── Video encoding ─────────────────────────────────────────────────────────

def slide_to_video(
    png_path: Path,
    out_mp4: Path,
    duration_s: float,
    narration_text: str = "",
) -> None:
    """Encode a static PNG to MP4. No fade animations. Optionally burns subtitles."""
    vf_filters: list[str] = []

    # Burn subtitles if narration text is provided
    if narration_text.strip():
        srt_path = png_path.with_suffix(".srt")
        _write_srt(narration_text, duration_s, srt_path)
        # force_style: white text, semi-transparent black box, bottom margin
        srt_escaped = str(srt_path.resolve()).replace("\\", "/")
        vf_filters.append(
            f"subtitles='{srt_escaped}'"
            ":force_style='FontSize=13,PrimaryColour=&H00FFFFFF,"
            "BackColour=&H80000000,BorderStyle=4,Outline=0,Shadow=0,MarginV=40'"
        )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(png_path),
        "-t", f"{duration_s:.3f}",
        "-r", "24",
    ]
    if vf_filters:
        cmd += ["-vf", ",".join(vf_filters)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", str(out_mp4)]

    print(f">> {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)


# ── Entry point ────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: render_scene.py <slide_specs.json> <output_dir>", file=sys.stderr)
        sys.exit(2)

    specs_path = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = output_dir.parent / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    specs: list[dict] = json.loads(specs_path.read_text(encoding="utf-8"))
    if not specs:
        raise RuntimeError("slide_specs.json is empty")

    print(f"Rendering {len(specs)} slides…", flush=True)

    for i, spec in enumerate(specs):
        duration_s = float(spec.get("duration_s", 20))
        scene_id = spec.get("scene_id", f"scene_{i:02d}")
        narration_text = spec.get("narration_text", "")

        png_path = frames_dir / f"{i:02d}_{scene_id}.png"
        mp4_path = output_dir / f"{i:02d}.mp4"

        print(
            f"  [{i:02d}] {scene_id} — layout={spec.get('layout')}, "
            f"duration={duration_s}s, subtitles={'yes' if narration_text else 'no'}",
            flush=True,
        )
        render_slide(spec, png_path)
        slide_to_video(png_path, mp4_path, duration_s, narration_text)
        print(f"  -> {mp4_path}", flush=True)


if __name__ == "__main__":
    main()
