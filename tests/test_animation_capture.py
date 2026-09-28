import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image, PngImagePlugin

import animation_capture
import animation_trace
import contracts
import scenario_v2


class AnimationCaptureTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        frames = []
        keys = []
        for sequence, color in ((11, "red"), (15, "blue")):
            path = self.root / f"frame-{sequence}.png"
            Image.new("RGB", (32, 24), color).save(path)
            keys.append({"sequence": sequence, "file": path.name,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for sequence in range(11, 16):
            frames.append({"sequence": sequence, "elapsedNanos": (sequence - 11) * 500_000_000 + 100_000_000,
                           "framebufferWidth": 32, "framebufferHeight": 24,
                           "target": None, "panelRoi": None, "valueRoi": None})
        self.capture = {"schema_version": 1, "metadata": {
            "traceId": "fixture", "mode": "animation", "active": False, "reason": "stopped",
            "failure": None, "frameCount": 5, "startSequence": 10,
            "elapsedNanos": 2_200_000_000, "keyframeSequences": [11, 15]},
            "frames": frames, "keyframes": keys, "visual_status": "not_reviewed",
            "requested_seconds": 2, "sample_every": 20}

    def tearDown(self):
        self.folder.cleanup()

    def test_distinct_pngs_have_motion_but_not_visual_approval(self):
        result = animation_trace.validate_capture(self.capture, self.root, require_motion=True)
        self.assertEqual(result["keyframe_count"], 2)
        self.assertTrue(result["motion_observed"])
        self.assertEqual(result["visual_status"], "not_reviewed")
        sheet = animation_capture._sheet(self.root, self.capture["keyframes"])
        with Image.open(sheet) as image:
            self.assertEqual(image.size, (640, 180))
        animation_trace.validate_capture(self.capture, self.root, verify_sheet=True)
        Image.new("RGB", (640, 180), "green").save(sheet)
        with self.assertRaises(ValueError):
            animation_trace.validate_capture(self.capture, self.root, verify_sheet=True)

    def test_static_control_is_structural_only(self):
        static = copy.deepcopy(self.capture)
        static["keyframes"][1]["sha256"] = static["keyframes"][0]["sha256"]
        (self.root / "frame-15.png").write_bytes((self.root / "frame-11.png").read_bytes())
        self.assertFalse(animation_trace.validate_capture(static, self.root)["motion_observed"])
        with self.assertRaises(ValueError):
            animation_trace.validate_capture(static, self.root, require_motion=True)

    def test_different_png_encodings_of_same_pixels_are_not_motion(self):
        static = copy.deepcopy(self.capture)
        note = PngImagePlugin.PngInfo()
        note.add_text("encoder-note", "same pixels, different bytes")
        path = self.root / "frame-15.png"
        Image.new("RGB", (32, 24), "red").save(path, pnginfo=note)
        self.assertNotEqual(path.read_bytes(), (self.root / "frame-11.png").read_bytes())
        static["keyframes"][1]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertFalse(animation_trace.validate_capture(static, self.root)["motion_observed"])
        with self.assertRaises(ValueError):
            animation_trace.validate_capture(static, self.root, require_motion=True)

    def test_missing_tampered_and_noncontiguous_frames_fail(self):
        with self.assertRaises(ValueError):
            animation_trace.validate_capture(None, self.root)
        bad = copy.deepcopy(self.capture)
        bad["frames"][1]["sequence"] = 13
        with self.assertRaises(ValueError):
            animation_trace.validate_capture(bad, self.root)
        bad = copy.deepcopy(self.capture)
        bad["metadata"]["keyframeSequences"] = [15]
        with self.assertRaises(ValueError):
            animation_trace.validate_capture(bad, self.root)
        bad = copy.deepcopy(self.capture)
        bad["keyframes"][0] = False
        with self.assertRaises(ValueError):
            animation_trace.validate_capture(bad, self.root)
        bad = copy.deepcopy(self.capture)
        bad["metadata"]["keyframeSequences"] = [{}]
        with self.assertRaises(ValueError):
            animation_trace.validate_capture(bad, self.root)
        (self.root / "frame-15.png").write_bytes(b"altered")
        with self.assertRaises(ValueError):
            animation_trace.validate_capture(self.capture, self.root)

    def test_schema_rejects_unbounded_or_unknown_action(self):
        scenario = contracts.load(Path(__file__).resolve().parents[1] / "examples/scenario-v2.json")
        scenario["steps"] = [{"id": "animation", "action": {"type": "capture_animation",
            "seconds": 2, "sample_every": 20, "require_motion": True}}]
        scenario_v2.validate_scenario(scenario)
        for change in ({"sample_every": 1}, {"seconds": 11}, {"command": "say hi"}):
            bad = copy.deepcopy(scenario)
            bad["steps"][0]["action"].update(change)
            with self.assertRaises(contracts.ContractError):
                scenario_v2.validate_scenario(bad)


if __name__ == "__main__":
    unittest.main()
