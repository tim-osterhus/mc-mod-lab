"""Validate saved general render evidence, not its visual meaning."""

import hashlib
from pathlib import Path
import struct

from PIL import Image, ImageChops, ImageOps


def _integer(value, lower, upper):
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise ValueError("animation integer is out of bounds")
    return value


def _png(path, expected_hash, dimensions):
    data = path.read_bytes()
    if not 24 <= len(data) <= 16 * 1024 * 1024 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("animation image is not a bounded PNG")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_hash:
        raise ValueError("animation image digest changed")
    try:
        with Image.open(path) as image:
            if image.format != "PNG" or image.size != dimensions:
                raise ValueError("animation image dimensions disagree with render frame")
            image.load()
            opaque = Image.new("RGBA", image.size, (0, 0, 0, 255))
            pixels = Image.alpha_composite(opaque, image.convert("RGBA")).convert("RGB")
            pixel_digest = hashlib.sha256(struct.pack(">II", *image.size) + pixels.tobytes()).hexdigest()
    except OSError as exc:
        raise ValueError("animation PNG decoding failed") from exc
    return pixel_digest


def contact_sheet(root, keys):
    tile_width, tile_height = 320, 180
    columns = min(4, len(keys))
    rows = (len(keys) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), "#202428")
    for index, key in enumerate(keys):
        with Image.open(Path(root) / key["file"]) as image:
            tile = ImageOps.contain(image.convert("RGB"), (tile_width, tile_height))
            x = (index % columns) * tile_width + (tile_width - tile.width) // 2
            y = (index // columns) * tile_height + (tile_height - tile.height) // 2
            sheet.paste(tile, (x, y))
    return sheet


def validate_capture(capture, root, *, require_motion=False, verify_sheet=False):
    if not isinstance(capture, dict):
        raise ValueError("animation trace is not an object")
    metadata = capture.get("metadata")
    frames = capture.get("frames")
    keys = capture.get("keyframes")
    if (not isinstance(metadata, dict) or metadata.get("mode") != "animation"
            or metadata.get("active") is not False or metadata.get("reason") != "stopped"
            or metadata.get("failure") is not None or not isinstance(frames, list)
            or not 1 <= len(frames) <= 1200 or not isinstance(keys, list)
            or not 1 <= len(keys) <= 64 or any(not isinstance(key, dict) for key in keys)
            or not _integer(metadata.get("frameCount"), 1, 1200) == len(frames)):
        raise ValueError("animation trace is incomplete")
    start = _integer(metadata.get("startSequence"), 0, 2 ** 63 - 1)
    if not isinstance(metadata.get("traceId"), str) or not metadata["traceId"]:
        raise ValueError("animation trace identity is missing")
    elapsed = _integer(metadata.get("elapsedNanos"), 1, 30_000_000_000)
    seconds = _integer(capture.get("requested_seconds"), 2, 10)
    sample_every = _integer(capture.get("sample_every"), 20, 60)
    if not (seconds - 0.5) * 1_000_000_000 <= elapsed <= (seconds + 2) * 1_000_000_000:
        raise ValueError("animation duration does not cover the requested window")
    previous = -1
    by_sequence = {}
    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise ValueError("animation frame is invalid")
        sequence = _integer(frame.get("sequence"), 1, 2 ** 63 - 1)
        frame_time = _integer(frame.get("elapsedNanos"), 1, elapsed)
        width = _integer(frame.get("framebufferWidth"), 1, 1920)
        height = _integer(frame.get("framebufferHeight"), 1, 1080)
        gui_width = _integer(frame.get("guiWidth"), 1, width) if "guiWidth" in frame else width
        gui_height = _integer(frame.get("guiHeight"), 1, height) if "guiHeight" in frame else height
        if (not isinstance(frame.get("screenOpen", False), bool)
                or not isinstance(frame.get("hideGui", False), bool)
                or not isinstance(frame.get("debugVisible", False), bool)
                or gui_width > width or gui_height > height):
            raise ValueError("animation frame metadata is invalid")
        if (sequence != start + index + 1 or frame_time <= previous
                or frame.get("panelRoi") is not None or frame.get("valueRoi") is not None
                or frame.get("target") is not None):
            raise ValueError("animation render sequence or mode data is inconsistent")
        if (index == 0 and frame_time > 500_000_000
                or index > 0 and frame_time - previous > 500_000_000):
            raise ValueError("animation render continuity has a gap")
        previous = frame_time
        by_sequence[sequence] = (width, height)
    if elapsed - previous > 500_000_000:
        raise ValueError("animation last rendered frame is too old")
    sequences = metadata.get("keyframeSequences")
    expected = [frame["sequence"] for index, frame in enumerate(frames)
                if index == 0 or (index + 1) % sample_every == 0 or index == len(frames) - 1]
    if (not isinstance(sequences, list)
            or any(not _integer(sequence, 1, 2 ** 63 - 1) for sequence in sequences)
            or sequences != sorted(set(sequences))
            or sequences != [key.get("sequence") for key in keys]
            or sequences != expected):
        raise ValueError("animation first/last keyframe index is incomplete")
    root = Path(root)
    digests = set()
    total_bytes = 0
    for key in keys:
        sequence = _integer(key.get("sequence"), 1, 2 ** 63 - 1)
        if sequence not in by_sequence or key.get("file") != f"frame-{sequence}.png":
            raise ValueError("animation keyframe does not match a render frame")
        digest = key.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("animation keyframe digest is invalid")
        path = root / key["file"]
        digests.add(_png(path, digest, by_sequence[sequence]))
        total_bytes += path.stat().st_size
        if total_bytes > 32 * 1024 * 1024:
            raise ValueError("animation PNG budget exceeded")
    motion = len(digests) > 1
    if require_motion and not motion:
        raise ValueError("animation retained PNGs do not show pixel change")
    if capture.get("visual_status") != "not_reviewed":
        raise ValueError("animation visual verdict is not independently reviewed")
    if verify_sheet:
        try:
            expected = contact_sheet(root, keys)
            with Image.open(root / "contact-sheet.png") as actual:
                if actual.format != "PNG" or actual.size != expected.size or actual.mode != "RGB":
                    raise ValueError("animation contact sheet format changed")
                if ImageChops.difference(actual, expected).getbbox() is not None:
                    raise ValueError("animation contact sheet is not derived from original PNGs")
        except OSError as exc:
            raise ValueError("animation contact sheet could not be decoded") from exc
    return {"frame_count": len(frames), "keyframe_count": len(keys),
            "motion_observed": motion, "visual_status": "not_reviewed"}
