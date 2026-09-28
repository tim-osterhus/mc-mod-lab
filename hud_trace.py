"""Structural validation for bounded HUD traces; never a visual verdict."""

import math
import re


MAX_FRAMES = 1200
MAX_KEYFRAMES = 64
MAX_FRAMEBUFFER = (1920, 1080)
MAX_TRACE_SECONDS = 30.0
MAX_TRACE_NANOS = int(MAX_TRACE_SECONDS * 1_000_000_000)


def validate_capture(capture, *, require_value_transitions=False, **kwargs):
    """Validate a saved collector payload, without trusting client values as pixels."""
    capture = _record(capture, "capture")
    metadata = _record(capture.get("metadata"), "metadata")
    frames = capture.get("frames")
    if not isinstance(frames, list) or not frames or len(frames) > MAX_FRAMES:
        raise ValueError("saved capture has no bounded frame list")
    batches = [{**metadata, "frames": frames[i:i + 32]} for i in range(0, len(frames), 32)]
    result = validate_trace(batches, server_samples=capture.get("server_samples"),
                            python_clock_brackets=capture.get("python_clock_brackets"), **kwargs)
    keys = capture.get("keyframes")
    if not isinstance(keys, list):
        raise ValueError("saved keyframe index is missing")
    sequences = [_integer(_record(key, "keyframe").get("sequence"), "keyframe.sequence") for key in keys]
    if sequences != metadata.get("keyframeSequences"):
        raise ValueError("saved keyframes do not match the recorder index")
    retained = set(sequences)
    changes = [(a["sequence"], b["sequence"]) for a, b in zip(frames, frames[1:])
               if isinstance(a.get("target"), dict) and isinstance(b.get("target"), dict)
               and a["target"].get("clientWhiteAura") != b["target"].get("clientWhiteAura")]
    missing = [pair for pair in changes if not set(pair) <= retained]
    if require_value_transitions and missing:
        raise ValueError("value transitions lack adjacent before/after keyframes")
    def visual_key(frame):
        target = frame.get("target")
        return (target.get("clientWhiteAura") if isinstance(target, dict) else None,
                frame["valueRoi"]["rgbSha256"])
    retained_states = {visual_key(frame) for frame in frames if frame["sequence"] in retained}
    unrepresented = sum(visual_key(frame) not in retained_states for frame in frames)
    if require_value_transitions and unrepresented:
        raise ValueError("rendered value ROI states lack an exact retained PNG")
    result.update(value_changes=len(changes), retained_value_pairs=len(changes) - len(missing),
                  unrepresented_value_frames=unrepresented,
                  png_integrity="not_checked")
    return result


def validate_trace(
    batches,
    *,
    server_samples,
    python_clock_brackets,
    mode="positive",
    expected_target=None,
    minimum_seconds=10.0,
    max_frame_gap_seconds=0.5,
    max_final_frame_age_seconds=0.5,
    server_tps_tolerance=0.1,
):
    """Validate capture coverage, not HUD correctness.

    ``server_samples`` contains the collector's before/after records, each with
    ``requestElapsedNanos``, ``elapsedNanos``, ``serverTick`` and ``snapshot``.
    ``python_clock_brackets`` contains the start/stop request/ack elapsed times.
    Only relative ordering and duration intervals are compared; Python and Java
    clock origins are never aligned.
    """
    minimum_seconds = _finite(minimum_seconds, "minimum_seconds", positive=True)
    max_frame_gap_seconds = _finite(max_frame_gap_seconds, "max_frame_gap_seconds", positive=True)
    max_final_frame_age_seconds = _finite(
        max_final_frame_age_seconds, "max_final_frame_age_seconds", positive=True
    )
    server_tps_tolerance = _finite(server_tps_tolerance, "server_tps_tolerance")
    if minimum_seconds > MAX_TRACE_SECONDS:
        raise ValueError("minimum_seconds exceeds the recorder's 30-second limit")
    if not 0 <= server_tps_tolerance < 1:
        raise ValueError("server_tps_tolerance must be in [0, 1)")
    if not isinstance(mode, str) or mode not in {"positive", "lookaway", "seeded_zero", "other_node"}:
        raise ValueError("mode must be positive, lookaway, seeded_zero, or other_node")
    expected_identity = _target_identity(expected_target, "expected_target") if expected_target is not None else None
    if mode in {"lookaway", "other_node"} and expected_identity is None:
        raise ValueError(f"{mode} mode requires expected_target")

    if not isinstance(batches, (list, tuple)) or not batches:
        raise ValueError("trace batches are empty")

    trace_id = None
    start_sequence = None
    previous_elapsed = -1
    previous_count = -1
    frames = []
    final = None
    frozen_header = None
    for index, raw_batch in enumerate(batches):
        batch = _record(raw_batch, f"batch[{index}]")
        current_id = _text(batch.get("traceId"), f"batch[{index}].traceId")
        current_start = _integer(batch.get("startSequence"), f"batch[{index}].startSequence")
        active = _boolean(batch.get("active"), f"batch[{index}].active")
        reason = _text(batch.get("reason"), f"batch[{index}].reason")
        failure = batch.get("failure")
        if failure is not None:
            raise ValueError(f"batch[{index}] reports capture failure: {failure!r}")
        elapsed = _integer(batch.get("elapsedNanos"), f"batch[{index}].elapsedNanos")
        if elapsed > MAX_TRACE_NANOS:
            raise ValueError("batch elapsedNanos exceeds the recorder's 30-second limit")
        count = _integer(batch.get("frameCount"), f"batch[{index}].frameCount")
        keyframes = _integer_list(batch.get("keyframeSequences"), f"batch[{index}].keyframeSequences")
        batch_frames = batch.get("frames")
        if not isinstance(batch_frames, list) or len(batch_frames) > 32:
            raise ValueError(f"batch[{index}].frames must contain at most 32 frames")
        if count > MAX_FRAMES or len(keyframes) > MAX_KEYFRAMES:
            raise ValueError("trace exceeds recorder frame or keyframe bounds")
        if len(set(keyframes)) != len(keyframes) or keyframes != sorted(keyframes):
            raise ValueError(f"batch[{index}].keyframeSequences are duplicated or unordered")
        if reason == "inconclusive":
            raise ValueError("trace ended inconclusively")
        if active and reason != "recording":
            raise ValueError(f"active batch has unexpected reason: {reason!r}")
        if trace_id is None:
            trace_id, start_sequence = current_id, current_start
        elif current_id != trace_id or current_start != start_sequence:
            raise ValueError("batch trace identity or start sequence changed")
        if elapsed < previous_elapsed or count < previous_count:
            raise ValueError("batch elapsed time or frame count moved backwards")
        header = (current_id, current_start, reason, failure, elapsed, count, tuple(keyframes))
        if active:
            if frozen_header is not None:
                raise ValueError("trace reactivated after its frozen inactive header")
        elif frozen_header is None:
            frozen_header = header
            final = batch
        elif header != frozen_header:
            raise ValueError("inactive page changed the frozen trace header")
        if active and index == len(batches) - 1:
            raise ValueError("final batch is still active")
        if count < len(frames) + len(batch_frames):
            raise ValueError(f"batch[{index}] frameCount is smaller than collected frames")
        previous_elapsed, previous_count = elapsed, count
        frames.extend(batch_frames)

    if final is None:
        raise ValueError("trace has no completed final batch")
    if final.get("reason") != "stopped":
        raise ValueError(f"unexpected trace stop reason: {final.get('reason')!r}")
    if not frames:
        raise ValueError("trace contains no frames")
    if final["frameCount"] != len(frames):
        raise ValueError("collected frame count does not match final frameCount")

    frame_records = []
    previous_sequence = None
    previous_frame_elapsed = None
    geometry = None
    max_gap_ns = int(max_frame_gap_seconds * 1_000_000_000)
    for index, raw_frame in enumerate(frames):
        frame = _record(raw_frame, f"frame[{index}]")
        sequence = _integer(frame.get("sequence"), f"frame[{index}].sequence")
        frame_elapsed = _integer(frame.get("elapsedNanos"), f"frame[{index}].elapsedNanos")
        if frame_elapsed > MAX_TRACE_NANOS:
            raise ValueError("frame elapsedNanos exceeds the recorder's 30-second limit")
        if previous_sequence is None:
            if sequence != start_sequence + 1:
                raise ValueError("first frame sequence is not startSequence + 1")
            if frame_elapsed > max_gap_ns:
                raise ValueError("first frame arrived too late after trace start")
        elif sequence != previous_sequence + 1:
            raise ValueError("duplicate or missing global render sequence")
        if previous_frame_elapsed is not None:
            gap = frame_elapsed - previous_frame_elapsed
            if gap <= 0:
                raise ValueError("frame elapsedNanos is not strictly increasing")
            if gap > max_gap_ns:
                raise ValueError("render frame gap exceeds the configured bound")
        if frame_elapsed > final["elapsedNanos"]:
            raise ValueError("frame elapsedNanos exceeds frozen final elapsedNanos")

        framebuffer_width = _integer(frame.get("framebufferWidth"), f"frame[{index}].framebufferWidth", 1)
        framebuffer_height = _integer(frame.get("framebufferHeight"), f"frame[{index}].framebufferHeight", 1)
        gui_width = _integer(frame.get("guiWidth"), f"frame[{index}].guiWidth", 1)
        gui_height = _integer(frame.get("guiHeight"), f"frame[{index}].guiHeight", 1)
        if framebuffer_width > MAX_FRAMEBUFFER[0] or framebuffer_height > MAX_FRAMEBUFFER[1]:
            raise ValueError("framebuffer exceeds the recorder's 1920x1080 bound")
        if gui_width > framebuffer_width or gui_height > framebuffer_height:
            raise ValueError("GUI dimensions exceed framebuffer dimensions")
        if gui_width < 320 or gui_height < 176:
            raise ValueError("GUI is too small for the complete HUD ROI")
        dimensions = (framebuffer_width, framebuffer_height, gui_width, gui_height)

        language = _text(frame.get("language"), f"frame[{index}].language")
        if language != "en_us":
            raise ValueError("HUD trace language is not en_us")
        for flag in ("screenOpen", "hideGui", "debugVisible"):
            if _boolean(frame.get(flag), f"frame[{index}].{flag}"):
                raise ValueError(f"HUD is obscured by {flag}")
        _integer(frame.get("clientWorldTick"), f"frame[{index}].clientWorldTick")

        panel = _validate_roi(frame.get("panelRoi"), f"frame[{index}].panelRoi",
                              framebuffer_width, framebuffer_height)
        value = _validate_roi(frame.get("valueRoi"), f"frame[{index}].valueRoi",
                              framebuffer_width, framebuffer_height)
        expected_panel = (0, 0, math.ceil(320 * framebuffer_width / gui_width),
                          math.ceil(176 * framebuffer_height / gui_height))
        if panel[:4] != expected_panel:
            raise ValueError("panel ROI is clipped or inconsistent with GUI scaling")
        scale_x = framebuffer_width / gui_width
        scale_y = framebuffer_height / gui_height
        value_left = math.floor(64 * scale_x)
        value_top = math.floor(16 * scale_y)
        expected_value = (
            value_left,
            value_top,
            math.ceil(160 * scale_x) - value_left,
            math.ceil(25 * scale_y) - value_top,
        )
        if value[:4] != expected_value:
            raise ValueError("value ROI is clipped or misaligned with GUI scaling")

        target = _frame_target(frame.get("target"), f"frame[{index}].target")
        identity = _target_identity(target, f"frame[{index}].target") if target is not None else None
        candidate = target.get("whiteLayoutCandidate") if target is not None else False
        if target is not None:
            _boolean(candidate, f"frame[{index}].target.whiteLayoutCandidate")
            aura = target.get("clientWhiteAura")
            if aura is not None:
                _integer(aura, f"frame[{index}].target.clientWhiteAura")
        if mode == "positive":
            if identity is None or target.get("whiteLayoutCandidate") is not True:
                raise ValueError("positive trace lacks a supported fixed White HUD target")
        elif mode == "seeded_zero":
            if identity is None or target.get("whiteLayoutCandidate") is not True:
                raise ValueError("seeded_zero trace lacks a fixed White HUD target")
        elif mode == "other_node":
            if identity is None:
                raise ValueError("other_node trace lacks a target")
            if identity == expected_identity:
                raise ValueError("other_node trace still targets the positive node")
        elif mode == "lookaway" and identity == expected_identity:
            raise ValueError("lookaway trace still targets the positive node")
        if expected_identity is not None and mode in {"positive", "seeded_zero"}:
            if identity != expected_identity:
                raise ValueError("frame target differs from expected_target")
        if index and mode != "lookaway" and identity != frame_records[0]["target_identity"]:
            raise ValueError("target identity changed during fixed-view trace")

        if geometry is None:
            geometry = (dimensions, panel[:4], value[:4])
        elif geometry != (dimensions, panel[:4], value[:4]):
            raise ValueError("frame dimensions or ROI geometry changed during trace")
        frame_records.append({"target_identity": identity})
        previous_sequence, previous_frame_elapsed = sequence, frame_elapsed

    final_elapsed_ns = _integer(final.get("elapsedNanos"), "final.elapsedNanos")
    first_frame_ns = _integer(frames[0].get("elapsedNanos"), "first frame.elapsedNanos")
    last_frame_ns = _integer(frames[-1].get("elapsedNanos"), "last frame.elapsedNanos")
    final_age_ns = final_elapsed_ns - last_frame_ns
    if final_age_ns < 0 or final_age_ns > int(max_final_frame_age_seconds * 1_000_000_000):
        raise ValueError("final frame is stale relative to frozen final elapsedNanos")
    if (final_elapsed_ns < minimum_seconds * 1_000_000_000
            or last_frame_ns - first_frame_ns < minimum_seconds * 1_000_000_000):
        raise ValueError("trace does not contain the required capture duration")

    final_keyframes = _integer_list(final.get("keyframeSequences"), "final.keyframeSequences")
    if (len(final_keyframes) < 2 or len(final_keyframes) > MAX_KEYFRAMES
            or len(set(final_keyframes)) != len(final_keyframes)
            or final_keyframes != sorted(final_keyframes)):
        raise ValueError("final keyframe sequence list is incomplete or invalid")
    captured_sequences = {start_sequence + offset + 1 for offset in range(len(frames))}
    if (any(sequence not in captured_sequences for sequence in final_keyframes)
            or final_keyframes[0] != frames[0]["sequence"]
            or final_keyframes[-1] != frames[-1]["sequence"]):
        raise ValueError("keyframes do not cover the first and final captured frames")

    server_report = _validate_server_samples(
        server_samples, python_clock_brackets, final_elapsed_ns,
        minimum_seconds, server_tps_tolerance,
        expected_identity if mode in {"positive", "seeded_zero"} else None,
    )
    elapsed_seconds = final_elapsed_ns / 1_000_000_000
    frame_span_seconds = (last_frame_ns - first_frame_ns) / 1_000_000_000
    return {
        "capture_status": "complete",
        "visual_status": "unreviewed",
        "mode": mode,
        "trace_id": trace_id,
        "frame_count": len(frames),
        "first_sequence": frames[0]["sequence"],
        "last_sequence": frames[-1]["sequence"],
        "elapsed_seconds": elapsed_seconds,
        "frame_span_seconds": frame_span_seconds,
        "final_frame_age_seconds": final_age_ns / 1_000_000_000,
        "max_frame_gap_seconds": max(
            (frames[i]["elapsedNanos"] - frames[i - 1]["elapsedNanos"])
            for i in range(1, len(frames))
        ) / 1_000_000_000,
        "server_ticks": server_report,
        "target_identity": frame_records[0]["target_identity"] if mode != "lookaway" else None,
        "keyframe_count": len(final_keyframes),
        "pixel_metrics": "recorded_not_interpreted",
    }


def _validate_server_samples(
    samples, clock_brackets, trace_elapsed_ns, minimum_seconds, tolerance, expected_identity
):
    if not isinstance(samples, (list, tuple)) or len(samples) != 2:
        raise ValueError("server_samples must contain before and after records")
    brackets = _record(clock_brackets, "python_clock_brackets")
    start_request = _integer(brackets.get("start_request_ns"), "start_request_ns")
    start_ack = _integer(brackets.get("start_ack_ns"), "start_ack_ns")
    stop_request = _integer(brackets.get("stop_request_ns"), "stop_request_ns")
    stop_ack = _integer(brackets.get("stop_ack_ns"), "stop_ack_ns")
    if not start_request <= start_ack < stop_request <= stop_ack:
        raise ValueError("Python start/stop request brackets are unordered")
    capture_min_ns = stop_request - start_ack
    capture_max_ns = stop_ack - start_request
    if capture_min_ns < minimum_seconds * 1_000_000_000:
        raise ValueError("Python clock brackets do not prove the required capture duration")
    if capture_max_ns > MAX_TRACE_NANOS:
        raise ValueError("Python clock brackets exceed the recorder's 30-second limit")
    if not capture_min_ns <= trace_elapsed_ns <= capture_max_ns:
        raise ValueError("Java trace duration falls outside Python start/stop duration bounds")

    parsed = []
    for index, raw in enumerate(samples):
        sample = _record(raw, f"server_samples[{index}]")
        snapshot = sample.get("snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError(f"server_samples[{index}].snapshot must be an object")
        if snapshot.get("serverAuthoritative") is not True:
            raise ValueError(f"server_samples[{index}] snapshot is not server-authoritative")
        if snapshot.get("stateSource") != "integrated_server_block_entity":
            raise ValueError(f"server_samples[{index}] snapshot has the wrong state source")
        tick = _integer(sample.get("serverTick"), f"server_samples[{index}].serverTick")
        snapshot_tick = _integer(snapshot.get("serverTick"),
                                 f"server_samples[{index}].snapshot.serverTick")
        if snapshot_tick != tick:
            raise ValueError(f"server_samples[{index}] tick disagrees with its snapshot")
        snapshot_identity = {
            "blockId": _text(snapshot.get("blockId"),
                             f"server_samples[{index}].snapshot.blockId"),
            "x": _integer(snapshot.get("x"), f"server_samples[{index}].snapshot.x",
                          minimum=-(2 ** 31), maximum=2 ** 31 - 1),
            "y": _integer(snapshot.get("y"), f"server_samples[{index}].snapshot.y",
                          minimum=-(2 ** 31), maximum=2 ** 31 - 1),
            "z": _integer(snapshot.get("z"), f"server_samples[{index}].snapshot.z",
                          minimum=-(2 ** 31), maximum=2 ** 31 - 1),
            "dimension": _optional_text(snapshot.get("dimension"),
                                        f"server_samples[{index}].snapshot.dimension"),
        }
        if expected_identity is not None:
            for field in ("blockId", "x", "y", "z"):
                if snapshot_identity[field] != expected_identity[field]:
                    raise ValueError(
                        f"server_samples[{index}] block identity disagrees with expected_target"
                    )
            if (snapshot_identity["dimension"] is not None
                    and snapshot_identity["dimension"] != expected_identity["dimension"]):
                raise ValueError(
                    f"server_samples[{index}] dimension disagrees with expected_target"
                )
        if parsed and snapshot_identity != parsed[0]["identity"]:
            raise ValueError("authoritative server samples changed block identity")
        parsed.append({
            "tick": tick,
            "identity": snapshot_identity,
            "request_start": _integer(sample.get("requestElapsedNanos"),
                                       f"server_samples[{index}].requestElapsedNanos"),
            "response_end": _integer(sample.get("elapsedNanos"),
                                     f"server_samples[{index}].elapsedNanos"),
        })
        if parsed[-1]["response_end"] < parsed[-1]["request_start"]:
            raise ValueError(f"server_samples[{index}] request window is reversed")
    before, after = parsed
    if before["tick"] >= after["tick"]:
        raise ValueError("authoritative server ticks did not increase")
    if before["response_end"] > start_request:
        raise ValueError("before server request does not finish before start request")
    if after["request_start"] < stop_ack:
        raise ValueError("after server request does not start after stop acknowledgement")
    shortest_span_ns = after["request_start"] - before["response_end"]
    longest_span_ns = after["response_end"] - before["request_start"]
    if shortest_span_ns <= 0 or longest_span_ns < shortest_span_ns:
        raise ValueError("server request windows do not establish an ordered sample interval")
    tick_delta = after["tick"] - before["tick"]
    slowest_rate = tick_delta / (longest_span_ns / 1_000_000_000)
    fastest_rate = tick_delta / (shortest_span_ns / 1_000_000_000)
    accepted = [20.0 * (1 - tolerance), 20.0 * (1 + tolerance)]
    if slowest_rate < accepted[0] or fastest_rate > accepted[1]:
        raise ValueError(
            "server tick rate cannot be proven within the configured 20 TPS tolerance "
            f"from request-window uncertainty ({slowest_rate:.2f}-{fastest_rate:.2f} TPS)"
        )
    return {
        "before": before["tick"],
        "after": after["tick"],
        "delta": tick_delta,
        "ticks_per_second_bounds": [slowest_rate, fastest_rate],
        "accepted_ticks_per_second": accepted,
        "tolerance_fraction": tolerance,
        "shortest_sample_span_seconds": shortest_span_ns / 1_000_000_000,
        "longest_sample_span_seconds": longest_span_ns / 1_000_000_000,
        "capture_duration_bounds_seconds": [
            capture_min_ns / 1_000_000_000, capture_max_ns / 1_000_000_000
        ],
    }


def _validate_roi(value, name, framebuffer_width, framebuffer_height):
    roi = _record(value, name)
    x = _integer(roi.get("x"), f"{name}.x")
    y = _integer(roi.get("y"), f"{name}.y")
    width = _integer(roi.get("width"), f"{name}.width", 1)
    height = _integer(roi.get("height"), f"{name}.height", 1)
    candidates = _integer(roi.get("whiteCandidatePixels"), f"{name}.whiteCandidatePixels")
    digest = _text(roi.get("rgbSha256"), f"{name}.rgbSha256")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError(f"{name}.rgbSha256 must be a lowercase SHA-256 digest")
    if x + width > framebuffer_width or y + height > framebuffer_height:
        raise ValueError(f"{name} is clipped by the framebuffer")
    if candidates > width * height:
        raise ValueError(f"{name}.whiteCandidatePixels exceeds ROI area")
    return x, y, width, height, candidates, digest


def _frame_target(value, name):
    if value is None:
        return None
    target = _record(value, name)
    _text(target.get("dimension"), f"{name}.dimension")
    for axis in ("x", "y", "z"):
        _integer(target.get(axis), f"{name}.{axis}", minimum=-(2 ** 31), maximum=2 ** 31 - 1)
    block_id = target.get("blockId")
    if block_id is not None:
        _text(block_id, f"{name}.blockId")
    aura = target.get("clientWhiteAura")
    if aura is not None:
        _integer(aura, f"{name}.clientWhiteAura")
    _boolean(target.get("whiteLayoutCandidate"), f"{name}.whiteLayoutCandidate")
    return target


def _target_identity(value, name):
    target = _record(value, name)
    return {
        "dimension": _text(target.get("dimension"), f"{name}.dimension"),
        "x": _integer(target.get("x"), f"{name}.x", minimum=-(2 ** 31), maximum=2 ** 31 - 1),
        "y": _integer(target.get("y"), f"{name}.y", minimum=-(2 ** 31), maximum=2 ** 31 - 1),
        "z": _integer(target.get("z"), f"{name}.z", minimum=-(2 ** 31), maximum=2 ** 31 - 1),
        "blockId": _optional_text(target.get("blockId"), f"{name}.blockId"),
    }


def _integer_list(value, name):
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return [_integer(item, f"{name}[{index}]") for index, item in enumerate(value)]


def _record(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _integer(value, name, minimum=0, maximum=2 ** 63 - 1):
    if (isinstance(value, bool) or not isinstance(value, int)
            or (minimum is not None and value < minimum)
            or (maximum is not None and value > maximum)):
        raise ValueError(f"{name} must be an integer in range")
    return value


def _finite(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        value = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _boolean(value, name):
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_text(value, name):
    return None if value is None else _text(value, name)
