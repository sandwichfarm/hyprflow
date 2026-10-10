#!/usr/bin/env python3
"""Caption the three presets in a passing verify-appearance.py recording.

Uses the existing Pillow proof tooling and FFmpeg; leaves the raw recording intact.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

CAPTIONS = {
    "solid": ("Solid stage", "Workspace proportions · reflections and captions"),
    "clear-overlay": ("Clear desktop overlay", "No tint or blur · reflections and captions off"),
    "blurred-tint": ("Blurred desktop overlay", "45% tint · 16px blur · gradient borders"),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Passing appearance proof output")
    parser.add_argument("--font", type=Path, help="Optional TrueType font for captions")
    args = parser.parse_args()
    directory = args.directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    if not manifest["passed"] or [scene["name"] for scene in manifest["video_scenes"]] != list(CAPTIONS):
        parser.error("requires a passing proof with the three recorded presets")
    raw = directory / "configurations-raw.mp4"
    metadata = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration", "-of", "json", str(raw)
    ], text=True))
    width, height = metadata["streams"][0]["width"], metadata["streams"][0]["height"]
    duration = float(metadata["format"]["duration"])
    scenes = manifest["video_scenes"]
    previous_end = 0
    for scene in scenes:
        start, end = scene["start_seconds"], scene["end_seconds"]
        if not all(math.isfinite(value) for value in (start, end)) or not previous_end <= start < end:
            parser.error("recorded preset times must be finite, ordered, and non-overlapping")
        previous_end = end
    # The recorder warms up for five seconds before the timeline starts.
    # Reject compressed recordings instead of placing captions outside the clip.
    if not math.isfinite(duration) or not previous_end - 1 <= duration <= previous_end + 6:
        parser.error("recording duration differs from preset timeline; record with variable framerate")
    fonts = [args.font] if args.font else [Path(p) for p in (
        "/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )]
    font = next((p for p in fonts if p.is_file()), None)
    if not font:
        parser.error("supply --font with an installed TrueType font")
    title_font = ImageFont.truetype(str(font), round(height * .037))
    detail_font = ImageFont.truetype(str(font), round(height * .026))
    offset = max(0, duration - previous_end)
    intervals = []
    output = directory / "configurations.mp4"
    with tempfile.TemporaryDirectory(prefix="hyprflow-captions-") as folder:
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw)]
        filters = []
        for index, scene in enumerate(manifest["video_scenes"]):
            caption = Image.new("RGBA", (width, round(height * .12)))
            draw = ImageDraw.Draw(caption)
            title, detail = CAPTIONS[scene["name"]]
            box_width = min(width - 40, max(draw.textbbox((0, 0), title, font=title_font)[2],
                                            draw.textbbox((0, 0), detail, font=detail_font)[2]) + 32)
            draw.rectangle((20, 0, 20 + box_width, caption.height), fill=(11, 16, 32, 225))
            draw.text((36, 8), title, fill=(242, 239, 233), font=title_font)
            draw.text((36, round(height * .06)), detail, fill=(148, 221, 199), font=detail_font)
            path = Path(folder) / f"{index}.png"
            caption.save(path)
            command.extend(["-loop", "1", "-i", str(path)])
            start = 0 if index == 0 else scene["start_seconds"] + offset
            end = duration if index == 2 else manifest["video_scenes"][index + 1]["start_seconds"] + offset
            input_label = "0:v" if index == 0 else f"v{index - 1}"
            filters.append(f"[{input_label}][{index + 1}:v]overlay=0:H-h-16:enable='between(t,{start:.4f},{end:.4f})'[v{index}]")
            intervals.append({"preset": scene["name"], "start_seconds": start, "end_seconds": end, "title": title, "detail": detail})
        command.extend(["-filter_complex", ";".join(filters), "-map", "[v2]", "-t", str(duration),
                        "-r", "30", "-c:v", "libx264", "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)])
        subprocess.run(command, check=True)
    receipt = {"raw_sha256": digest(raw), "published_sha256": digest(output), "duration_seconds": duration,
               "playback_speed": 1, "captions": intervals}
    (directory / "video.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
