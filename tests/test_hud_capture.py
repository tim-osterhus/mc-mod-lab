import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import hud_capture
import lab


class HudCaptureTests(unittest.TestCase):
    def test_keyframe_requires_png_and_bounded_dimensions(self):
        for content_type, size, accepted in (("image/png", (1280, 720), True),
                                              ("application/json", (1280, 720), False),
                                              ("image/png", (4096, 2160), False)):
            with self.subTest(content_type=content_type, size=size):
                connection = MagicMock()
                response = connection.getresponse.return_value
                response.status = 200
                response.getheader.return_value = content_type
                response.read.return_value = b"\x89PNG\r\n\x1a\n" + bytes(8) + struct.pack(">II", *size)
                with patch.dict(os.environ, {"MC_MOD_LAB_TOKEN": "x" * 32}), \
                     patch.object(lab, "listening_socket"), \
                     patch.object(hud_capture.http.client, "HTTPConnection", return_value=connection):
                    if accepted:
                        self.assertEqual(hud_capture._keyframe({"pid": 1, "port": 9875}, "trace", 1)[1:], size)
                    else:
                        with self.assertRaises(lab.LabError):
                            hud_capture._keyframe({"pid": 1, "port": 9875}, "trace", 1)
                connection.close.assert_called_once()

    def test_samples_bracket_confirmed_start_stop_and_no_visual_verdict(self):
        events = []
        trace_id = "00000000-0000-0000-0000-000000000001"
        frame = {"sequence": 1, "framebufferWidth": 1280, "framebufferHeight": 720}
        def request(identity, kind, name, params):
            events.append(name)
            if name in {"hud_start", "hud_stop"}:
                return {"result": {"traceId": trace_id}}
            return {"result": {"traceId": trace_id, "active": False, "reason": "stopped", "frameCount": 1,
                               "keyframeSequences": [1], "frames": [frame] if params["after_sequence"] == 0 else []}}
        def sample(*args):
            events.append("sample")
            return {"server_tick_after": 200}, {"serverAuthoritative": True}
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(hud_capture.scenario_v2, "scenario_request", side_effect=request), \
             patch.object(hud_capture.scenario_v2, "_scenario_observation", side_effect=sample), \
             patch.object(hud_capture.scenario_v2, "_wait_ticks", side_effect=lambda *args: events.append("wait")), \
             patch.object(hud_capture, "_keyframe", return_value=(b"fixture", 1280, 720)):
            result = hud_capture.capture({}, {"seconds": 12, "x": 0, "y": 161, "z": 0},
                                         Path(temp) / "capture", float("inf"))
        self.assertEqual(events[:5], ["sample", "hud_start", "wait", "hud_stop", "sample"])
        self.assertEqual(result["visual_status"], "not_reviewed")

    def test_wait_failure_still_stops_capture(self):
        events = []
        def request(identity, kind, name, params):
            events.append(name)
            return {"result": {"traceId": "id"}}
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(hud_capture.scenario_v2, "scenario_request", side_effect=request), \
             patch.object(hud_capture.scenario_v2, "_scenario_observation", return_value=({"server_tick_after": 1}, {})), \
             patch.object(hud_capture.scenario_v2, "_wait_ticks", side_effect=lab.LabError("cancelled", "fail")):
            with self.assertRaises(lab.LabError):
                hud_capture.capture({}, {"seconds": 12, "x": 0, "y": 161, "z": 0}, Path(temp) / "capture", float("inf"))
        self.assertEqual(events, ["hud_start", "hud_stop"])
