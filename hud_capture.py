"""Collect bounded rendered evidence; collection alone is not visual acceptance."""

import hashlib
import http.client
import json
import os
from pathlib import Path
import struct
import time

import lab
import scenario_v2


def _keyframe(identity, trace_id, sequence):
    lab.listening_socket(identity["pid"], identity["port"])
    token = os.environ.get("MC_MOD_LAB_TOKEN", "")
    if len(token) < 32 or "\n" in token or "\r" in token:
        raise lab.LabError("capture session token unavailable")
    connection = http.client.HTTPConnection("127.0.0.1", identity["port"], timeout=5)
    payload = {"schema_version": 2, "kind": "observe", "name": "hud_keyframe",
               "params": {"trace_id": trace_id, "sequence": sequence}}
    try:
        connection.request("POST", "/api/scenario/v2", json.dumps(payload).encode("ascii"),
                           {"Content-Type": "application/json", "Authorization": "Bearer " + token})
        response = connection.getresponse()
        if response.status != 200 or response.getheader("Content-Type") != "image/png":
            raise lab.LabError("trace keyframe unavailable")
        png = response.read(16 * 1024 * 1024 + 1)
        if len(png) > 16 * 1024 * 1024 or len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
            raise lab.LabError("trace keyframe is not a bounded PNG")
        width, height = struct.unpack(">II", png[16:24])
        if not 1 <= width <= 1920 or not 1 <= height <= 1080:
            raise lab.LabError("trace keyframe dimensions exceed capture budget")
        return png, width, height
    except (OSError, http.client.HTTPException) as exc:
        raise lab.LabError("trace keyframe transport failed") from exc
    finally:
        connection.close()


def capture(identity, action, destination, wall_deadline, cancel_event=None):
    destination = Path(destination)
    destination.mkdir()
    block = {"type": "aura_block_server", **{k: action[k] for k in ("x", "y", "z")}}
    samples = []
    started = time.monotonic_ns()
    def sample():
        request_ns = time.monotonic_ns() - started
        envelope, value = scenario_v2._scenario_observation(identity, block)
        samples.append({"requestElapsedNanos": request_ns, "elapsedNanos": time.monotonic_ns() - started,
                        "serverTick": envelope["server_tick_after"], "snapshot": value})
    sample()
    start_request_ns = time.monotonic_ns() - started
    start = scenario_v2.scenario_request(identity, "action", "hud_start", {})
    start_ack_ns = time.monotonic_ns() - started
    trace_id = start["result"]["traceId"]
    trigger = None
    try:
        if action.get("trigger") == "drop_selected":
            trigger = scenario_v2.scenario_request(identity, "action", "drop_selected", {"count": 1})
        scenario_v2._wait_ticks(identity, action["seconds"] * 20, wall_deadline, cancel_event)
    finally:
        stop_request_ns = time.monotonic_ns() - started
        stopped = scenario_v2.scenario_request(identity, "action", "hud_stop", {"trace_id": trace_id})
        stop_ack_ns = time.monotonic_ns() - started
        if stopped["result"]["traceId"] != trace_id:
            scenario_v2._mark_uncertain(identity)
            raise lab.LabError("capture stop acknowledgement changed trace identity", "fail")
    sample()
    frames, cursor, metadata = [], 0, None
    while True:
        if time.monotonic() >= wall_deadline or (cancel_event is not None and cancel_event.is_set()):
            raise lab.LabError("capture collection cancelled or exceeded wall limit", "fail")
        batch = scenario_v2.scenario_request(identity, "observe", "hud_batch",
                    {"trace_id": trace_id, "after_sequence": cursor, "limit": 32})["result"]
        if (not isinstance(batch, dict) or batch.get("traceId") != trace_id or batch.get("active") is not False
                or not isinstance(batch.get("frames"), list) or len(batch["frames"]) > 32):
            raise lab.LabError("stopped trace batch unavailable")
        header = {key: value for key, value in batch.items() if key != "frames"}
        if metadata is not None and metadata != header:
            raise lab.LabError("stopped trace metadata changed during collection")
        metadata = header
        for frame in batch["frames"]:
            sequence = frame.get("sequence") if isinstance(frame, dict) else None
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= cursor:
                raise lab.LabError("trace cursor did not progress")
            frames.append(frame)
            cursor = sequence
        if len(frames) > 1200:
            raise lab.LabError("trace frame budget exceeded")
        if not batch["frames"]:
            break
    payload = {"schema_version": 1, "metadata": metadata, "frames": frames,
               "server_samples": samples, "visual_status": "not_reviewed", "keyframes": []}
    payload["python_clock_brackets"] = {"start_request_ns": start_request_ns, "start_ack_ns": start_ack_ns,
                                        "stop_request_ns": stop_request_ns, "stop_ack_ns": stop_ack_ns,
                                        "clock_note": "Python elapsed anchor is independent of Java trace elapsedNanos"}
    if trigger is not None:
        payload["trigger"] = trigger
    trace_file = destination / "trace.json"
    lab.write_json(trace_file, payload)
    if metadata.get("failure") or metadata.get("reason") == "inconclusive" or not frames:
        raise lab.LabError("renderer trace is incomplete; evidence retained")
    if metadata.get("frameCount") != len(frames):
        raise lab.LabError("renderer trace count is incomplete")
    keys = metadata.get("keyframeSequences")
    if not isinstance(keys, list) or not 1 <= len(keys) <= 64 or len(set(keys)) != len(keys):
        raise lab.LabError("trace keyframe index unavailable")
    total = 0
    by_sequence = {frame["sequence"]: frame for frame in frames}
    for sequence in keys:
        if time.monotonic() >= wall_deadline or (cancel_event is not None and cancel_event.is_set()):
            raise lab.LabError("capture keyframe collection cancelled or exceeded wall limit", "fail")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence not in by_sequence:
            raise lab.LabError("keyframe has no corresponding rendered observation")
        png, width, height = _keyframe(identity, trace_id, sequence)
        frame = by_sequence[sequence]
        if (width, height) != (frame.get("framebufferWidth"), frame.get("framebufferHeight")):
            raise lab.LabError("keyframe dimensions disagree with render observation")
        total += len(png)
        if total > 32 * 1024 * 1024:
            raise lab.LabError("trace PNG budget exceeded")
        name = "frame-" + str(sequence) + ".png"
        (destination / name).write_bytes(png)
        payload["keyframes"].append({"sequence": sequence, "file": name,
                                      "sha256": hashlib.sha256(png).hexdigest()})
        lab.write_json(trace_file, payload)
    return {"trace_file": destination.name + "/trace.json", "frame_count": len(frames),
            "keyframe_count": len(keys), "visual_status": "not_reviewed"}
