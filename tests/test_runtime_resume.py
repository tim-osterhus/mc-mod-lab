from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import lab
import runtime_launch


class RuntimeResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.profile = Path(self.temp.name)
        self.world = self.profile / "game/saves/fixture"
        self.world.mkdir(parents=True)
        (self.world / "level.dat").write_bytes(b"saved world")
        (self.world / "session.lock").write_bytes(b"lock")
        report = self.profile / "scenario-evidence/report.json"
        report.parent.mkdir()
        lab.write_json(report, {"status": "pass"})
        self.lifecycle = {"status": "pass", "bridge_classification": "public_reviewed",
                          "cleanup": {"status": "pass", "exit_code": 0}}
        self.seal()

    def seal(self):
        lab.write_json(self.profile / "lifecycle-report.json", self.lifecycle)
        runtime_launch._save_checkpoint(self.profile, self.world, ".", "a" * 64)

    def test_closed_unchanged_save_receipt_is_valid(self):
        path, receipt = runtime_launch._resume_checkpoint(self.profile, self.world, "a" * 64)
        self.assertEqual(path.name, "saved-world.json")
        self.assertEqual(receipt["run_directory"], ".")
        (self.world / "session.lock").write_bytes(b"different lock timestamp")
        runtime_launch._resume_checkpoint(self.profile, self.world, "a" * 64)

    def test_storage_resume_verifies_latest_exact_state(self):
        snapshot = {"type": "aura_storage_fixture", "x": 0, "y": 161, "z": 0,
                    "power": 990, "transaction_cost": 5, "inventory": [],
                    "storage": [{"item_id": "minecraft:diamond", "count": 7, "component_sha256": "a" * 64}],
                    "server_tick": 200}
        previous = {"steps": [{"status": "pass", "evidence": {"typed_observations": [snapshot]}}]}
        observed = {**snapshot, "server_tick": 20}
        with patch.object(runtime_launch.scenario_v2, "_scenario_observation", return_value=({}, observed)):
            result = runtime_launch._verify_storage_resume({}, previous, self.profile / "continuity.json")
        self.assertEqual(result, {"status": "pass", "fixtures": 1})
        for key, changed in (("power", 995), ("storage", []), ("inventory", snapshot["storage"])):
            with self.subTest(key=key), patch.object(runtime_launch.scenario_v2, "_scenario_observation",
                                                   return_value=({}, {**observed, key: changed})):
                with self.assertRaisesRegex(lab.LabError, "across reopen"):
                    runtime_launch._verify_storage_resume({}, previous, self.profile / "continuity.json")

    def test_changed_save_and_report_are_refused(self):
        (self.world / "level.dat").write_bytes(b"changed")
        with self.assertRaisesRegex(lab.LabError, "world changed"):
            runtime_launch._resume_checkpoint(self.profile, self.world, "a" * 64)
        self.seal()
        (self.profile / "scenario-evidence/report.json").write_text('{}', encoding="utf-8")
        with self.assertRaisesRegex(lab.LabError, "evidence changed"):
            runtime_launch._resume_checkpoint(self.profile, self.world, "a" * 64)

    def test_failure_cleanup_or_uncertain_save_is_not_resumable(self):
        for change in ({"status": "fail"}, {"cleanup": {"status": "fail"}},
                       {"bridge_classification": "private_diagnostic"}):
            original = self.lifecycle.copy()
            self.lifecycle.update(change)
            self.seal()
            with self.assertRaisesRegex(lab.LabError, "successful normally closed"):
                runtime_launch._resume_checkpoint(self.profile, self.world, "a" * 64)
            self.lifecycle = original
        self.seal()
        (self.profile / "game/.mc-mod-lab-uncertain").write_text("uncertain", encoding="utf-8")
        with self.assertRaisesRegex(lab.LabError, "uncertain"):
            runtime_launch._resume_checkpoint(self.profile, self.world, "a" * 64)

    def test_missing_lock_and_wrong_artifact_are_refused(self):
        with self.assertRaisesRegex(lab.LabError, "evidence changed"):
            runtime_launch._resume_checkpoint(self.profile, self.world, "b" * 64)
        (self.world / "session.lock").unlink()
        with self.assertRaisesRegex(lab.LabError, "session lock is missing"):
            runtime_launch._resume_checkpoint(self.profile, self.world, "a" * 64)


if __name__ == "__main__":
    unittest.main()
