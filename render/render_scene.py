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
ACCENT_COLOR = (88, 166, 255)     # blue accent for top bar

FONT_PATHS = [
    # Ubuntu / Debian (GitHub Actions)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    # Windows
    "C:/Windows/Fonts/Arial.ttf",
]


def _find_font(bold: bool = False) -> str | None:
    for path in FONT_PATHS:
        if Path(path).exists():
            return path
    return None


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _find_font(bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _download_image(url: str) -> Image.Image | None:
    """Download an image from URL; return PIL Image or None on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchGPT-Renderer/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        img = Image.open(BytesIO(data)).convert("RGBA")
        return img
    except Exception as exc:
        print(f"  [warn] could not download image: {exc}", flush=True)
        return None


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
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
    """Draw wrapped text lines centred on center_x starting at top_y. Returns bottom y."""
    y = top_y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        draw.text((center_x - text_w // 2, y), line, font=font, fill=color)
        y += (bbox[3] - bbox[1]) + line_spacing
    return y


def render_slide(spec: dict, out_path: Path) -> None:
    """Render a single slide spec to a PNG file."""
    layout = spec.get("layout", "text_only")
    image_url = spec.get("image_url") or None
    headline = spec.get("headline", "")
    supporting_text = spec.get("supporting_text", "")
    text_size = spec.get("text_size", "medium")

    # Font sizes
    h_size = {"large": 68, "medium": 54, "small": 42}.get(text_size, 54)
    s_size = {"large": 34, "medium": 30, "small": 26}.get(text_size, 30)

    canvas = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    h_font = _load_font(h_size, bold=True)
    s_font = _load_font(s_size, bold=False)

    # Top accent bar
    draw.rectangle([(0, 0), (W, 6)], fill=ACCENT_COLOR)

    # Download image if needed
    photo: Image.Image | None = None
    if image_url and layout != "text_only":
        photo = _download_image(image_url)

    if layout == "image_top" and photo:
        # Image: upper 65%; text: lower 35%
        img_h = int(H * 0.65)
        photo_resized = _resize_contain(photo, W, img_h)
        paste_x = (W - photo_resized.width) // 2
        canvas.paste(photo_resized, (paste_x, 8), photo_resized if photo_resized.mode == "RGBA" else None)
        _draw_text_area(draw, headline, supporting_text, h_font, s_font, img_h + 20, W - 120, W // 2)

    elif layout == "image_left" and photo:
        # Image: left 50%; text: right 50%
        img_w = W // 2
        photo_resized = _resize_contain(photo, img_w - 40, H - 80)
        paste_y = (H - photo_resized.height) // 2
        canvas.paste(photo_resized, (20, paste_y), photo_resized if photo_resized.mode == "RGBA" else None)
        _draw_text_area(draw, headline, supporting_text, h_font, s_font,
                        H // 2 - 80, W // 2 - 80, img_w + W // 4)

    elif layout == "split" and photo:
        # Top half: image; bottom half: text (same as image_top but 50/50)
        img_h = H // 2
        photo_resized = _resize_contain(photo, W - 120, img_h - 40)
        paste_x = (W - photo_resized.width) // 2
        canvas.paste(photo_resized, (paste_x, 20), photo_resized if photo_resized.mode == "RGBA" else None)
        _draw_text_area(draw, headline, supporting_text, h_font, s_font, img_h + 20, W - 120, W // 2)

    else:
        # text_only or fallback
        _draw_text_area(draw, headline, supporting_text, h_font, s_font, H // 2 - 80, W - 160, W // 2)

    canvas.save(str(out_path))


def _resize_contain(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """Resize image to fit within max_w × max_h while preserving aspect ratio."""
    ratio = min(max_w / img.width, max_h / img.height)
    new_w = int(img.width * ratio)
    new_h = int(img.height * ratio)
    return img.resize((new_w, new_h), Image.LANCZOS)


def _draw_text_area(
    draw: ImageDraw.ImageDraw,
    headline: str,
    supporting_text: str,
    h_font,
    s_font,
    top_y: int,
    max_w: int,
    center_x: int,
) -> None:
    """Draw headline + supporting text starting at top_y."""
    if headline:
        lines = _wrap_text(draw, headline, h_font, max_w)
        bottom = _draw_text_block(draw, lines, h_font, HEADLINE_COLOR, center_x, top_y, line_spacing=10)
    else:
        bottom = top_y
    if supporting_text:
        lines = _wrap_text(draw, supporting_text, s_font, max_w)
        _draw_text_block(draw, lines, s_font, SUPPORT_COLOR, center_x, bottom + 20, line_spacing=6)


def slide_to_video(png_path: Path, out_mp4: Path, duration_s: float) -> None:
    """Convert a static PNG to a video clip with fade in/out via ffmpeg."""
    fade_d = min(0.4, duration_s * 0.15)
    fade_out_start = max(0.0, duration_s - fade_d)
    vf = (
        f"fade=type=in:start_frame=0:nb_frames={int(24 * fade_d)},"
        f"fade=type=out:start_time={fade_out_start:.2f}:duration={fade_d:.2f}"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(png_path),
        "-vf", vf,
        "-t", f"{duration_s:.3f}",
        "-r", "24",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        str(out_mp4),
    ]
    print(f">> {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)


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

        png_path = frames_dir / f"{i:02d}_{scene_id}.png"
        mp4_path = output_dir / f"{i:02d}.mp4"

        print(f"  [{i:02d}] {scene_id} — layout={spec.get('layout')}, duration={duration_s}s",
              flush=True)
        render_slide(spec, png_path)
        slide_to_video(png_path, mp4_path, duration_s)
        print(f"  -> {mp4_path}", flush=True)


if __name__ == "__main__":
    main()
