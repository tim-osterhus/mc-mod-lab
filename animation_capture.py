"""Collect short, bounded rendered sequences and a review contact sheet."""

import hashlib
import time
from pathlib import Path

import animation_trace
import hud_capture
import lab
import scenario_v2


def _sheet(destination, keys):
    sheet = animation_trace.contact_sheet(destination, keys)
    path = destination / "contact-sheet.png"
    sheet.save(path, format="PNG", optimize=True)
    return path


def capture(identity, action, destination, wall_deadline, cancel_event=None):
    destination = Path(destination)
    destination.mkdir()
    start = scenario_v2.scenario_request(identity, "action", "animation_start",
                                         {"sample_every": action["sample_every"]})["result"]
    scenario_v2._validate_action_ack(start, "animation_start")
    trace_id = start["traceId"]
    try:
        end = min(time.monotonic() + action["seconds"], wall_deadline)
        while time.monotonic() < end:
            if cancel_event is not None and cancel_event.is_set():
                raise lab.LabError("animation capture cancelled", "fail")
            time.sleep(max(0, min(0.1, end - time.monotonic())))
        if time.monotonic() >= wall_deadline:
            raise lab.LabError("animation capture exceeded scenario wall limit", "fail")
    finally:
        stopped = scenario_v2.scenario_request(identity, "action", "animation_stop",
                                               {"trace_id": trace_id})["result"]
        scenario_v2._validate_action_ack(stopped, "animation_stop")
        if stopped["traceId"] != trace_id:
            scenario_v2._mark_uncertain(identity)
            raise lab.LabError("animation stop changed trace identity", "fail")
    frames, cursor, metadata = [], 0, None
    while True:
        if time.monotonic() >= wall_deadline or (cancel_event is not None and cancel_event.is_set()):
            raise lab.LabError("animation collection cancelled or exceeded wall limit", "fail")
        batch = scenario_v2.scenario_request(identity, "observe", "hud_batch",
                 {"trace_id": trace_id, "after_sequence": cursor, "limit": 32})["result"]
        if (not isinstance(batch, dict) or batch.get("traceId") != trace_id
                or batch.get("mode") != "animation" or batch.get("active") is not False
                or not isinstance(batch.get("frames"), list) or len(batch["frames"]) > 32):
            raise lab.LabError("stopped animation batch unavailable")
        header = {key: value for key, value in batch.items() if key != "frames"}
        if metadata is not None and metadata != header:
            raise lab.LabError("animation metadata changed during collection")
        metadata = header
        for frame in batch["frames"]:
            sequence = frame.get("sequence") if isinstance(frame, dict) else None
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= cursor:
                raise lab.LabError("animation cursor did not progress")
            frames.append(frame)
            cursor = sequence
        if len(frames) > 1200:
            raise lab.LabError("animation frame budget exceeded")
        if not batch["frames"]:
            break
    payload = {"schema_version": 1, "metadata": metadata, "frames": frames,
               "keyframes": [], "visual_status": "not_reviewed",
               "requested_seconds": action["seconds"], "sample_every": action["sample_every"]}
    capture_file = destination / "capture.json"
    lab.write_json(capture_file, payload)
    if (metadata.get("reason") != "stopped" or metadata.get("failure")
            or metadata.get("frameCount") != len(frames) or not frames):
        raise lab.LabError("animation trace is incomplete; metadata retained")
    keys = metadata.get("keyframeSequences")
    if not isinstance(keys, list) or not 1 <= len(keys) <= 64:
        raise lab.LabError("animation keyframe index unavailable")
    by_sequence = {frame["sequence"]: frame for frame in frames}
    total = 0
    for sequence in keys:
        if time.monotonic() >= wall_deadline or (cancel_event is not None and cancel_event.is_set()):
            raise lab.LabError("animation keyframe collection cancelled or exceeded wall limit", "fail")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence not in by_sequence:
            raise lab.LabError("animation keyframe has no rendered frame")
        png, width, height = hud_capture._keyframe(identity, trace_id, sequence)
        frame = by_sequence[sequence]
        if (width, height) != (frame.get("framebufferWidth"), frame.get("framebufferHeight")):
            raise lab.LabError("animation PNG dimensions disagree with render frame")
        total += len(png)
        if total > 32 * 1024 * 1024:
            raise lab.LabError("animation PNG budget exceeded")
        name = f"frame-{sequence}.png"
        (destination / name).write_bytes(png)
        payload["keyframes"].append({"sequence": sequence, "file": name,
                                     "sha256": hashlib.sha256(png).hexdigest()})
        lab.write_json(capture_file, payload)
    try:
        result = animation_trace.validate_capture(payload, destination,
                                                  require_motion=action["require_motion"])
    except ValueError as exc:
        raise lab.LabError(str(exc), "fail") from exc
    try:
        sheet = _sheet(destination, payload["keyframes"])
    except OSError as exc:
        raise lab.LabError("animation contact sheet could not be rendered", "fail") from exc
    result.update(capture_file=destination.name + "/capture.json",
                  contact_sheet=destination.name + "/" + sheet.name)
    return result
