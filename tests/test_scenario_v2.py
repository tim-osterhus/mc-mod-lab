import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import contracts
import lab
import scenario_v2


class ScenarioV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        seed = self.root / "seed"
        seed.mkdir()
        (seed / "level.dat").write_bytes(b"world")
        self.game = self.root / "game"
        self.world = lab.fixture_create(seed, self.game / "saves", "fixture", "LabFixture")
        log = self.game / "logs" / "latest.log"
        log.parent.mkdir()
        log.write_text("Loading Minecraft 1.21.1 with Fabric Loader 0.16.0\n"
                       "Loading 2 mods:\n\t- auracascade 0.2.1+1.21.1\n", encoding="utf-8")
        mods = self.game / "mods"
        mods.mkdir()
        self.artifact = mods / "aura.jar"
        with zipfile.ZipFile(self.artifact, "w") as archive:
            archive.writestr("fabric.mod.json", json.dumps({"id": "auracascade", "version": "0.2.1+1.21.1"}))
        bridge = self.root / "bridge.jar"
        bridge.write_bytes(b"bridge")
        self.identity = {"schema_version": 1, "minecraft_version": "1.21.1", "loader": "fabric",
                         "pid": 123, "port": 9875, "world_name": "LabFixture",
                         "world_path": str(self.world), "expected_gamemode": "creative",
                         "fixture_id": "fixture", "bridge_release": "0.3.0",
                         "bridge_jar": str(bridge), "upstream_sha256": lab.UPSTREAM_SHA256,
                         "derivative_sha256": lab.sha256(bridge), "max_group_mb": 3800,
                         "tracked_pids": [123], "min_capture_width": 1, "min_capture_height": 1,
                         "game_dir": str(self.game), "launch_log": str(log)}
        self.scenario = {"schema_version": 2, "id": "world-smoke", "fixture": "fixture",
                         "runtime": {"kind": "prepared-packaged-client", "mod_id": "auracascade",
                                     "mod_version": "0.2.1+1.21.1", "artifact_sha256": lab.sha256(self.artifact)},
                         "steps": [{"id": "look", "observe": ["world", "screen"]},
                                   {"id": "assert", "require": {"type": "screen_class", "equals": "GuideScreen"}}],
                         "cleanup": "release-control"}
        self.identity_file = self.root / "identity.json"
        self.scenario_file = self.root / "scenario.json"
        self.save()

    def save(self):
        lab.write_json(self.identity_file, self.identity)
        lab.write_json(self.scenario_file, self.scenario)

    def command(self, identity, name, params=None):
        if name == "get_screen_buttons":
            return {"screen": "GuideScreen", "buttons": []}
        if name == "enter_control_mode":
            return {"control_mode": True}
        if name == "exit_control_mode":
            return {"control_mode": False}
        if name == "press_key":
            return {"result": "dispatched"}
        raise AssertionError(name)

    def run_case(self):
        output = self.root / "output"
        with patch.object(lab, "launch_check", return_value={}), \
             patch.object(lab, "status_check", return_value={}), \
             patch.object(lab, "world_check", return_value={"world_name": "LabFixture"}), \
             patch.object(lab, "player_check", return_value={}), \
             patch.object(lab, "check_derivative", return_value=self.identity["derivative_sha256"]), \
             patch.object(lab, "group_mb", return_value=400.0), \
             patch.object(lab, "process_private_mb", return_value=500.0), \
             patch.object(lab, "command", side_effect=self.command):
            result = scenario_v2.run(self.identity_file, self.scenario_file, self.artifact, output)
        return result, output

    def test_observed_screen_pass_requires_assertion(self):
        result, output = self.run_case()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["runtime"]["status"], "verified")
        self.assertEqual(result["visual_check"], "not_reviewed")
        self.assertEqual(result["memory"]["peak_private_mib"], 500)
        self.assertEqual(contracts.validate_file(output / "report.json", "scenario-report-v2", True)["status"], "valid")
        self.assertNotIn(str(self.root), (output / "report.json").read_text(encoding="utf-8"))

    def test_unknown_action_rejected_before_runtime(self):
        self.scenario["steps"][0] = {"id": "unsafe", "action": {"type": "execute_command", "command": "say hi"}}
        self.save()
        with self.assertRaises(contracts.ContractError):
            scenario_v2.run(self.identity_file, self.scenario_file, self.artifact, self.root / "output")
        self.assertFalse((self.root / "output").exists())

    def test_duplicate_step_ids_rejected(self):
        self.scenario["steps"][1]["id"] = "look"
        with self.assertRaisesRegex(contracts.ContractError, "duplicate"):
            scenario_v2.validate_scenario(self.scenario)

    def test_wrong_artifact_hash_is_unsupported_without_control(self):
        self.scenario["runtime"]["artifact_sha256"] = "0" * 64
        self.save()
        result, output = self.run_case()
        self.assertEqual(result["status"], "unsupported")
        self.assertTrue(all(row["status"] == "not_run" for row in result["steps"]))
        self.assertFalse((self.game / ".mc-mod-lab-control.lock").exists())
        contracts.validate_file(output / "report.json", "scenario-report-v2", True)

    def test_missing_mod_log_line_is_unsupported(self):
        (self.game / "logs" / "latest.log").write_text(
            "Loading Minecraft 1.21.1 with Fabric Loader 0.16.0\nLoading 1 mods:\n", encoding="utf-8")
        result, _ = self.run_case()
        self.assertEqual(result["status"], "unsupported")

    def test_unsupported_observer_stops_future_assertion(self):
        self.scenario["steps"][0] = {"id": "look", "observe": ["inventory"]}
        self.save()
        result, _ = self.run_case()
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual([row["status"] for row in result["steps"]], ["unsupported", "not_run"])

    def test_future_capability_rejected_before_earlier_action(self):
        self.scenario["steps"].insert(1, {"id": "open", "action": {"type": "press_key", "key": "E"}})
        self.scenario["steps"].insert(2, {"id": "read-items", "observe": ["inventory"]})
        self.save()
        result, _ = self.run_case()
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["steps"][1]["status"], "not_run")
        self.assertEqual(result["steps"][2]["status"], "unsupported")
        self.assertFalse((self.game / ".mc-mod-lab-control.lock").exists())

    def test_action_lease_released_after_success(self):
        self.scenario["steps"].insert(1, {"id": "open", "action": {"type": "press_key", "key": "E"}})
        self.save()
        result, _ = self.run_case()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["cleanup"]["status"], "pass")
        self.assertFalse((self.game / ".mc-mod-lab-control.lock").exists())

    def test_existing_lease_rejects_action_and_remains(self):
        self.scenario["steps"].insert(1, {"id": "open", "action": {"type": "press_key", "key": "E"}})
        self.save()
        lock = self.game / ".mc-mod-lab-control.lock"
        lock.write_text("someone else", encoding="utf-8")
        result, _ = self.run_case()
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(lock.read_text(encoding="utf-8"), "someone else")

    def test_save_exit_never_claims_success(self):
        self.scenario["cleanup"] = "save-exit"
        self.save()
        result, _ = self.run_case()
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["cleanup"]["status"], "unsupported")

    def test_failed_control_exit_is_failure_and_keeps_lease(self):
        self.scenario["steps"].insert(1, {"id": "open", "action": {"type": "press_key", "key": "E"}})
        self.save()
        original = self.command

        def bad_exit(identity, name, params=None):
            if name == "exit_control_mode":
                return {"control_mode": True}
            return original(identity, name, params)

        with patch.object(self, "command", side_effect=bad_exit):
            result, _ = self.run_case()
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["cleanup"]["status"], "fail")
        self.assertTrue((self.game / ".mc-mod-lab-control.lock").exists())

    def test_duplicate_json_key_is_rejected(self):
        self.scenario_file.write_text('{"id":"a","id":"b"}', encoding="utf-8")
        with self.assertRaisesRegex(contracts.ContractError, "duplicate JSON key"):
            scenario_v2.run(self.identity_file, self.scenario_file, self.artifact, self.root / "output")

    def test_symlinked_mods_directory_is_unsupported(self):
        alias = self.root / "mods-alias"
        try:
            alias.symlink_to(self.game / "mods", target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation is not permitted on this host")
        self.identity["game_dir"] = str(alias)
        with self.assertRaises(lab.LabError):
            scenario_v2.verify_packaged_artifact(self.identity, self.scenario, self.artifact)

    def test_report_validator_rejects_fake_pass(self):
        result, output = self.run_case()
        result["runtime"]["status"] = "unsupported"
        lab.write_json(output / "report.json", result)
        with self.assertRaisesRegex(contracts.ContractError, "lacks verified"):
            contracts.validate_file(output / "report.json", "scenario-report-v2", True)


if __name__ == "__main__":
    unittest.main()
