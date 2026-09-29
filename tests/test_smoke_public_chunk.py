"""Offline controls for the owned public chunk probe; no client is launched."""

from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts import smoke_public_chunk as probe


class PublicChunkSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.identity = {"pid": 123, "port": 9876, "expected_gamemode": "survival"}

    @staticmethod
    def observations():
        values = []
        for spec, loaded, ticking in ((probe.LOCAL, True, False), (probe.FAR, False, False),
                                      (probe.LOCAL, True, True), (probe.FAR, False, False),
                                      (probe.FAR, False, False)):
            value = {"dimension": "minecraft:overworld", "hasChunkAt": loaded,
                     "entityTicking": ticking, "x": spec["x"], "y": spec["y"], "z": spec["z"]}
            values.append(({"result": value}, value))
        return values

    def test_independent_flags_far_stability_and_negative_controls(self):
        statuses = [401, 403, 403, 405, 400, 400, 400, 400]
        with patch.object(probe.lab, "check_derivative", return_value=probe.BRIDGE_SHA256), \
             patch.object(probe.scenario_v2, "_scenario_observation",
                          side_effect=self.observations()) as observed, \
             patch.object(probe, "raw_status", side_effect=statuses) as raw, \
             patch.object(probe.time, "sleep"):
            report = probe.run_probe(self.identity, None, self.root, threading.Event())
        self.assertEqual(report["status"], "inconclusive")
        self.assertTrue(report["entity_ticking_positive_observed"])
        self.assertEqual(observed.call_count, 5)
        self.assertEqual(raw.call_count, 8)
        self.assertEqual([row["request"] for row in report["observations"]],
                         [probe.LOCAL, probe.FAR, probe.LOCAL, probe.FAR])
        self.assertTrue((self.root / "public-chunk-presence-report.json").is_file())

    def test_bad_origin_status_fails_closed(self):
        with patch.object(probe.lab, "check_derivative", return_value=probe.BRIDGE_SHA256), \
             patch.object(probe.scenario_v2, "_scenario_observation",
                          side_effect=self.observations()), \
             patch.object(probe, "raw_status", side_effect=[401, 403, 200]), \
             patch.object(probe.time, "sleep"):
            report = probe.run_probe(self.identity, None, self.root, threading.Event())
        self.assertEqual(report["status"], "fail")
        self.assertIn("security or parser", report["reason"])


if __name__ == "__main__":
    unittest.main()
