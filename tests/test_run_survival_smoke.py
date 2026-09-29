import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import lab
from scripts import run_survival_smoke as runner


class RunSurvivalSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_obs_call_keeps_bridge_token_out_of_recorder_environment(self):
        completed = subprocess.CompletedProcess([], 0, '{"outputActive":false}', "")
        with patch.dict(os.environ, {"MC_MOD_LAB_TOKEN": "private", "MC_MCP_PORT": "1234"}), \
             patch.object(runner.subprocess, "run", return_value=completed) as call:
            self.assertEqual(runner.obs_call(self.root / "obs_control.py", "GetRecordStatus"),
                             {"outputActive": False})
        self.assertNotIn("MC_MOD_LAB_TOKEN", call.call_args.kwargs["env"])
        self.assertNotIn("MC_MCP_PORT", call.call_args.kwargs["env"])

    def test_capture_target_requires_one_exact_enabled_pid_title(self):
        title = "MC Mod Lab Minecraft PID 1234"
        good = title + ":GLFW30:java.exe"
        items = [{"itemEnabled": True, "itemValue": good},
                 {"itemEnabled": True, "itemValue": "MC Mod Lab Minecraft PID 5678:GLFW30:java.exe"}]
        replies = [{"propertyItems": items}, {}, {"inputSettings": {"window": good}}]
        with patch.object(runner, "obs_call", side_effect=replies) as call:
            self.assertEqual(runner.select_capture_window("control", title), good)
        self.assertEqual(call.call_args_list[1].args[1], "SetInputSettings")
        self.assertEqual(call.call_args_list[1].args[2]["inputSettings"]["window"], good)
        with patch.object(runner, "obs_call", return_value={"propertyItems": items + [items[0]]}):
            with self.assertRaisesRegex(lab.LabError, "ambiguous"):
                runner.select_capture_window("control", title)

    def test_optional_durable_target_is_exact_stone(self):
        args = argparse.Namespace(use_target=("2", "161", "0", "minecraft:chest"),
                                  attack_target=("3", "161", "2", "minecraft:glass"),
                                  mine_target=("3", "161", "1", "minecraft:glass"),
                                  durable_target=("1", "160", "2", "minecraft:stone"),
                                  log_target=None, expiry_target=None)
        targets = runner.checked_targets(args)
        self.assertEqual(targets[runner.DURABLE_PHASE], (1, 160, 2, "minecraft:stone"))
        args.durable_target = ("1", "160", "2", "minecraft:obsidian")
        with self.assertRaisesRegex(lab.LabError, "exact stone"):
            runner.checked_targets(args)

    def test_placed_log_is_sole_exact_target(self):
        args = argparse.Namespace(use_target=None, attack_target=None, mine_target=None,
                                  durable_target=None,
                                  log_target=("2", "161", "2", "minecraft:oak_log"),
                                  expiry_target=None)
        self.assertEqual(runner.checked_targets(args),
                         {runner.LOG_PHASE: (2, 161, 2, "minecraft:oak_log")})
        args.log_target = ("2", "161", "2", "minecraft:oak_planks")
        with self.assertRaisesRegex(lab.LabError, "exact oak log"):
            runner.checked_targets(args)
        args.log_target = ("2", "161", "2", "minecraft:oak_log")
        args.use_target = ("2", "161", "0", "minecraft:chest")
        with self.assertRaisesRegex(lab.LabError, "own profile"):
            runner.checked_targets(args)

    def test_expiry_is_single_exact_iron_block_target(self):
        args = argparse.Namespace(use_target=None, attack_target=None, mine_target=None,
                                  durable_target=None, log_target=None,
                                  expiry_target=("1", "161", "2", "minecraft:iron_block"))
        self.assertEqual(runner.checked_targets(args),
                         {runner.EXPIRY_PHASE: (1, 161, 2, "minecraft:iron_block")})
        args.expiry_target = ("1", "161", "2", "minecraft:stone")
        with self.assertRaisesRegex(lab.LabError, "exact iron block"):
            runner.checked_targets(args)

    def test_outer_reconcile_stops_only_own_recording_and_verifies_both_outputs(self):
        replies = [{"outputActive": True}, {}, {"outputActive": False},
                   {"outputActive": False}]
        with patch.object(runner, "obs_call", side_effect=replies) as call:
            report = runner.reconcile_obs("control", True)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["forced_stop"])
        self.assertEqual(call.call_args_list[1].args[1], "StopRecord")
        with patch.object(runner, "obs_call", return_value={"outputActive": True}) as call, \
             patch.object(runner.time, "sleep"):
            report = runner.reconcile_obs("control", False)
        self.assertEqual(report["status"], "fail")
        self.assertNotIn("StopRecord", [item.args[1] for item in call.call_args_list])

    def test_three_phases_keep_one_identity_and_validate_recorder(self):
        args = argparse.Namespace(obs_control=self.root / "obs_control.py",
                                  obs_record=self.root / "obs_record.py")
        targets = {phase: (index, 70, 0, "minecraft:glass")
                   for index, phase in enumerate(runner.PHASES)}
        identity = {"pid": 1234}
        artifact = self.root / "aura.jar"
        recorder_started = [False]
        calls = []

        def prepare(phase_args):
            phase_args.out.mkdir()
            calls.append(("prepare", phase_args.out.name, phase_args.x))
            return {"window_title": "MC Mod Lab Minecraft PID 1234"}

        def act(phase_args, on_armed):
            phase_args.out.mkdir()
            calls.append(("act", phase_args.phase, phase_args.test_id))
            on_armed()
            return {"status": "inconclusive"}

        class Recorder:
            returncode = 0

            def __init__(self, command, **kwargs):
                self.command = command
                self.env = kwargs["env"]
                calls.append(("recorder", command[4], command[-1]))
                calls.append(("limit", command[command.index("--max-seconds") + 1]))

            def communicate(self, timeout):
                test_id = self.command[self.command.index("--test-id") + 1]
                return (json.dumps({"test_id": test_id, "client_pid": 1234,
                                    "artifact_sha256": runner.smoke.AURA_SHA256,
                                    "stop_reason": "test_finished"}), "")

        with patch.object(runner.smoke, "prepare", side_effect=prepare), \
             patch.object(runner.smoke, "act", side_effect=act), \
             patch.object(runner, "select_capture_window", return_value="selected"), \
             patch.object(runner.subprocess, "Popen", side_effect=Recorder):
            report = runner.run_phases(args, targets, identity, artifact, self.root,
                                       threading.Event(), recorder_started)
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual(len(report["phases"]), 3)
        self.assertEqual([row[1] for row in calls if row[0] == "act"], list(runner.PHASES))
        self.assertEqual([row[1] for row in calls if row[0] == "limit"], ["30"] * 3)
        self.assertTrue(recorder_started[0])

    def test_log_recorder_has_45_second_cap_and_stops_after_cleanup(self):
        args = argparse.Namespace(obs_control=self.root / "obs_control.py",
                                  obs_record=self.root / "obs_record.py")
        targets = {runner.LOG_PHASE: (2, 161, 2, "minecraft:oak_log")}
        commands = []
        stop_path = self.root / "technical-smoke" / "log_mining.stop"

        def prepare(phase_args):
            phase_args.out.mkdir()
            return {"window_title": "MC Mod Lab Minecraft PID 1234"}

        def act(phase_args, on_armed):
            phase_args.out.mkdir()
            on_armed()
            return {"status": "inconclusive", "explicit_release": True,
                    "cancel": {"input_released": True}, "post_cancel_denied": True,
                    "cleanup_status": "pass"}

        class Recorder:
            returncode = 0

            def __init__(self, command, **_kwargs):
                commands.append(command)

            def communicate(self, timeout):
                if not stop_path.exists():
                    raise AssertionError("action completion did not signal recorder stop")
                return (json.dumps({"test_id": "m5a-log_mining-1234", "client_pid": 1234,
                                    "artifact_sha256": runner.smoke.AURA_SHA256,
                                    "stop_reason": "test_finished"}), "")
        with patch.object(runner.smoke, "prepare", side_effect=prepare), \
             patch.object(runner.smoke, "act", side_effect=act), \
             patch.object(runner, "select_capture_window", return_value="selected"), \
             patch.object(runner.subprocess, "Popen", side_effect=Recorder):
            report = runner.run_phases(args, targets, {"pid": 1234}, self.root / "aura.jar",
                                       self.root, threading.Event(), [False])
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual(commands[0][commands[0].index("--max-seconds") + 1], "45")

    def test_log_recorder_rejects_missing_release_ack(self):
        args = argparse.Namespace(obs_control=self.root / "obs_control.py",
                                  obs_record=self.root / "obs_record.py")
        targets = {runner.LOG_PHASE: (2, 161, 2, "minecraft:oak_log")}

        def prepare(phase_args):
            phase_args.out.mkdir()
            return {"window_title": "MC Mod Lab Minecraft PID 1234"}

        def act(phase_args, on_armed):
            phase_args.out.mkdir()
            on_armed()
            return {"status": "inconclusive", "cancel": {"input_released": True},
                    "post_cancel_denied": True, "cleanup_status": "pass"}

        class Recorder:
            returncode = 0

            def __init__(self, *_args, **_kwargs):
                pass

            def communicate(self, timeout):
                return (json.dumps({"test_id": "m5a-log_mining-1234", "client_pid": 1234,
                                    "artifact_sha256": runner.smoke.AURA_SHA256,
                                    "stop_reason": "test_finished"}), "")

        with patch.object(runner.smoke, "prepare", side_effect=prepare), \
             patch.object(runner.smoke, "act", side_effect=act), \
             patch.object(runner, "select_capture_window", return_value="selected"), \
             patch.object(runner.subprocess, "Popen", side_effect=Recorder):
            with self.assertRaisesRegex(lab.LabError, "not validated"):
                runner.run_phases(args, targets, {"pid": 1234}, self.root / "aura.jar",
                                  self.root, threading.Event(), [False])

    def test_recorder_failure_stops_action_and_fails_phase(self):
        args = argparse.Namespace(obs_control=self.root / "obs_control.py",
                                  obs_record=self.root / "obs_record.py")
        targets = {phase: (0, 70, 0, "minecraft:glass") for phase in runner.PHASES}
        communicated = []

        def prepare(phase_args):
            phase_args.out.mkdir()
            return {"window_title": "MC Mod Lab Minecraft PID 1234"}

        def act(phase_args, on_armed):
            phase_args.out.mkdir()
            on_armed()
            return {"status": "fail"}

        class FailedRecorder:
            returncode = 2

            def __init__(self, *_args, **_kwargs):
                pass

            def communicate(self, timeout):
                communicated.append(timeout)
                return ("", "recorder failed")

        with patch.object(runner.smoke, "prepare", side_effect=prepare), \
             patch.object(runner.smoke, "act", side_effect=act), \
             patch.object(runner, "select_capture_window", return_value="selected"), \
             patch.object(runner.subprocess, "Popen", side_effect=FailedRecorder):
            with self.assertRaisesRegex(lab.LabError, "not validated"):
                runner.run_phases(args, targets, {"pid": 1234}, self.root / "aura.jar",
                                  self.root, threading.Event(), [False])
        self.assertEqual(communicated, [120])
        self.assertTrue((self.root / "technical-smoke" / "use.stop").exists())
        self.assertEqual(json.loads((self.root / "technical-smoke" / "report.json").read_text())
                         ["status"], "fail")

    def test_missing_setup_block_fails_before_any_recorder(self):
        args = argparse.Namespace(obs_control=self.root / "obs_control.py",
                                  obs_record=self.root / "obs_record.py")
        targets = {phase: (0, 70, 0, "minecraft:glass") for phase in runner.PHASES}

        def prepare(phase_args):
            if phase_args.out.name == "held_mining-fixture-check":
                raise lab.LabError("fixture block did not load", "fail")
            return {"window_title": "MC Mod Lab Minecraft PID 1234"}

        with patch.object(runner.smoke, "prepare", side_effect=prepare), \
             patch.object(runner.smoke, "act") as action, \
             patch.object(runner.subprocess, "Popen") as recorder:
            with self.assertRaisesRegex(lab.LabError, "did not load"):
                runner.run_phases(args, targets, {"pid": 1234}, self.root / "aura.jar",
                                  self.root, threading.Event(), [False])
        action.assert_not_called()
        recorder.assert_not_called()

    def test_durable_phase_requires_intact_postcheck(self):
        args = argparse.Namespace(obs_control=self.root / "obs_control.py",
                                  obs_record=self.root / "obs_record.py")
        targets = {runner.DURABLE_PHASE: (1, 160, 2, "minecraft:stone")}
        identity = {"pid": 1234}
        calls = []

        def prepare(phase_args):
            calls.append(phase_args.out.name)
            phase_args.out.mkdir()
            if phase_args.out.name == "durable-postcheck":
                raise lab.LabError("durable target was broken", "fail")
            return {"window_title": "MC Mod Lab Minecraft PID 1234"}

        def act(phase_args, on_armed):
            phase_args.out.mkdir()
            on_armed()
            return {"status": "inconclusive"}

        class Recorder:
            returncode = 0

            def __init__(self, *_args, **_kwargs):
                pass

            def communicate(self, timeout):
                return (json.dumps({"test_id": "m5a-durable_mining-1234",
                                    "client_pid": 1234,
                                    "artifact_sha256": runner.smoke.AURA_SHA256,
                                    "stop_reason": "test_finished"}), "")

        with patch.object(runner.smoke, "prepare", side_effect=prepare), \
             patch.object(runner.smoke, "act", side_effect=act), \
             patch.object(runner, "select_capture_window", return_value="selected"), \
             patch.object(runner.subprocess, "Popen", side_effect=Recorder):
            with self.assertRaisesRegex(lab.LabError, "durable target was broken"):
                runner.run_phases(args, targets, identity, self.root / "aura.jar",
                                  self.root, threading.Event(), [False])
        self.assertIn("durable-postcheck", calls)

    def test_supervisor_checks_obs_in_outer_finally_after_launch_error(self):
        control = self.root / "obs_control.py"
        record = self.root / "obs_record.py"
        control.touch()
        record.touch()
        argv = ["run_survival_smoke", "--manifest", "manifest", "--profile", "profile",
                "--scenario", "scenario", "--obs-control", str(control),
                "--obs-record", str(record), "--use-target", "0", "70", "0", "minecraft:chest",
                "--attack-target", "1", "70", "0", "minecraft:glass",
                "--mine-target", "2", "70", "0", "minecraft:glass"]
        with patch.object(runner.sys, "argv", argv), \
             patch.object(runner, "check_manifest"), \
             patch.object(runner, "obs_inactive", return_value=True), \
             patch.object(runner.runtime_launch, "launch", side_effect=lab.LabError("startup failed")), \
             patch.object(runner, "reconcile_obs", return_value={"status": "pass",
                                                               "forced_stop": False}) as cleanup:
            self.assertEqual(runner.main(), 2)
        cleanup.assert_called_once_with(control, False)


if __name__ == "__main__":
    unittest.main()
