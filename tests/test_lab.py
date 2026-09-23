import base64
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from unittest.mock import patch

import lab


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "level.dat").write_bytes(b"seed")
        self.game_dir = self.root / "game"
        self.world = lab.fixture_create(self.seed, self.game_dir / "saves", "guide-baseline", "LabFixture")
        self.launch_log = self.game_dir / "logs" / "latest.log"
        self.launch_log.parent.mkdir()
        self.launch_log.write_text("Loading Minecraft 1.21.1 with Fabric Loader 0.19.1", encoding="utf-8")
        self.jar = self.root / "hardened.jar"
        self.jar.write_bytes(b"derivative")
        self.identity = {
            "schema_version": 1, "minecraft_version": "1.21.1", "loader": "fabric",
            "pid": 123, "port": 9876, "world_name": "LabFixture", "world_path": str(self.world),
            "expected_gamemode": "creative",
            "fixture_id": "guide-baseline", "bridge_release": "0.3.0",
            "bridge_jar": str(self.jar), "upstream_sha256": lab.UPSTREAM_SHA256,
            "derivative_sha256": lab.sha256(self.jar), "max_group_mb": 500,
            "tracked_pids": [123], "informational_pids": [],
            "min_capture_width": 1, "min_capture_height": 1,
            "game_dir": str(self.game_dir), "launch_log": str(self.launch_log),
        }
        self.identity_path = self.root / "identity.json"
        self.scenario_path = self.root / "scenario.json"
        self.scenario = {"schema_version": 1, "id": "guide-open",
                         "action": {"tool": "click", "params": {"x": 0, "y": 0}},
                         "expect": {"world_name": "LabFixture", "after_screen": "GuideScreen"}}
        self.save_inputs()

    def save_inputs(self):
        lab.write_json(self.identity_path, self.identity)
        lab.write_json(self.scenario_path, self.scenario)

    def fake_http(self, port, endpoint, payload=None):
        if endpoint == "/api/status":
            return {"type": "minecraft-mod", "pid": 123, "port": 9876,
                    "loader": "unknown", "version": "unknown"}
        if endpoint == "/api/screenshot":
            return {"original": "data:image/png;base64," + base64.b64encode(PNG).decode()}
        command = payload["cmd"]
        if command == "get_world_info":
            return {"world_name": "LabFixture", "world_path": str(self.world),
                    "gametype": "CREATIVE", "time": 200}
        if command == "get_player_info":
            return {"name": "private", "pos": "0 64 0", "dimension": "overworld",
                    "gamemode": "creative"}
        if command == "get_screen_buttons":
            return {"screen": "GuideScreen", "buttons": [{"label": ""}, {"label": ""}]}
        if command == "click":
            return {"clicked": True, "method": "screen-event"}
        if command == "use_item":
            return {"result": "used"}
        if command == "enter_control_mode":
            return {"control_mode": True}
        if command == "exit_control_mode":
            return {"control_mode": False}
        raise AssertionError(command)

    def run_capture(self, http=None, memory=100):
        with patch.object(lab, "listening_socket", return_value=True), \
             patch.object(lab, "launch_check", return_value=True), \
             patch.object(lab, "verify_security", return_value=True), \
             patch.object(lab, "process_mb", side_effect=lambda pid: memory(pid) if callable(memory) else memory), \
             patch.object(lab, "available_mb", return_value=1000), \
             patch.object(lab, "http_json", side_effect=http or self.fake_http):
            return lab.capture(self.identity_path, self.scenario_path, self.root / "report")

    def test_fresh_fixture_never_overwrites_seed(self):
        second = lab.fixture_create(self.seed, self.root / "fixtures", "guide-baseline", "LabFixture")
        self.assertNotEqual(second, self.world)
        self.assertEqual((second / "level.dat").read_bytes(), b"seed")
        self.assertFalse((self.seed / lab.MARKER).exists())

    def test_fixture_rejects_recursive_copy_and_symlink(self):
        with self.assertRaises(lab.LabError):
            lab.fixture_create(self.seed, self.seed / "nested", "bad", "LabFixture")
        try:
            (self.seed / "link").symlink_to(self.seed / "level.dat")
        except OSError:
            self.skipTest("symlink creation is not permitted on this host")
        with self.assertRaises(lab.LabError):
            lab.fixture_create(self.seed, self.root / "another", "bad", "LabFixture")

    def test_unmodified_jar_rejected(self):
        self.identity["upstream_sha256"] = self.identity["derivative_sha256"]
        self.save_inputs()
        result = self.run_capture()
        self.assertEqual(result["status"], "unsupported")
        self.assertIn("upstream", result["reason"])

    def test_original_asset_rejected_even_with_matching_digest(self):
        self.jar.write_bytes(b"upstream")
        self.identity["derivative_sha256"] = lab.UPSTREAM_SHA256
        self.save_inputs()
        self.assertEqual(self.run_capture()["status"], "unsupported")

    def test_wrong_fixture_marker_rejected(self):
        self.identity["fixture_id"] = "other"
        self.save_inputs()
        self.assertEqual(self.run_capture()["status"], "unsupported")

    def test_launch_check_requires_matching_game_dir(self):
        wrong = self.root / "wrong"
        wrong.mkdir()
        class Result:
            returncode = 0
            stdout = json.dumps({"ProcessId": 123,
                                 "CommandLine": "java --gameDir " + str(wrong) + " --note " + str(self.game_dir),
                                 "Created": lab.now()})
        with patch.object(lab.platform, "system", return_value="Windows"), \
             patch.object(lab.shutil, "which", return_value="powershell"), \
             patch.object(lab.subprocess, "run", return_value=Result()):
            with self.assertRaisesRegex(lab.LabError, "game_dir"):
                lab.launch_check(self.identity)

    def test_launch_check_accepts_fresh_matching_process_and_log(self):
        class Result:
            returncode = 0
            stdout = json.dumps({"ProcessId": 123,
                                 "CommandLine": "java --gameDir " + str(self.game_dir),
                                 "Created": lab.now()})
        with patch.object(lab.platform, "system", return_value="Windows"), \
             patch.object(lab.shutil, "which", return_value="powershell"), \
             patch.object(lab.subprocess, "run", return_value=Result()):
            self.assertTrue(lab.launch_check(self.identity))

    def launch_with_argfile(self, content, *, created=None, process_id=123):
        folder = self.root / "Java Args"
        folder.mkdir(exist_ok=True)
        argfile = folder / "java.args"
        argfile.write_text(content, encoding="utf-8")
        command_line = '"C:\\Program Files\\Java\\bin\\java.exe" @"' + str(argfile) + '"'
        class Result:
            returncode = 0
            stdout = json.dumps({"ProcessId": process_id, "CommandLine": command_line,
                                 "Created": created or (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()})
        with patch.object(lab.platform, "system", return_value="Windows"), \
             patch.object(lab.shutil, "which", return_value="powershell"), \
             patch.object(lab.subprocess, "run", return_value=Result()):
            return lab.launch_check(self.identity)

    def test_quoted_java_argfile_accepts_exact_game_dir(self):
        game_dir = str(self.game_dir).replace("\\", "\\\\")
        self.assertTrue(self.launch_with_argfile('"--gameDir"\n"' + game_dir + '"\n'))

    def test_java_argfile_wrong_world_not_hidden_by_other_path(self):
        wrong = self.root / "wrong"
        wrong.mkdir()
        content = ('--note "' + str(self.game_dir).replace("\\", "\\\\") + '"\n'
                   '--gameDir "' + str(wrong).replace("\\", "\\\\") + '"\n')
        with self.assertRaisesRegex(lab.LabError, "game_dir"):
            self.launch_with_argfile(content)

    def test_java_argfile_modified_after_launch_rejected(self):
        created = datetime.now(timezone.utc) - timedelta(minutes=1)
        with self.assertRaisesRegex(lab.LabError, "unreadable or untrusted"):
            self.launch_with_argfile('--gameDir "' + str(self.game_dir).replace("\\", "\\\\") + '"',
                                     created=created.isoformat())

    def test_java_argfile_unreadable_rejected(self):
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(lab.LabError, "unreadable or untrusted"):
                self.launch_with_argfile('--gameDir "' + str(self.game_dir) + '"')

    def test_java_argfile_repeated_game_dir_rejected(self):
        value = str(self.game_dir).replace("\\", "\\\\")
        with self.assertRaisesRegex(lab.LabError, "exactly one --gameDir"):
            self.launch_with_argfile('--gameDir "' + value + '" --gameDir "' + value + '"')

    def test_java_argfile_rejects_wrong_pid_metadata(self):
        with self.assertRaisesRegex(lab.LabError, "process metadata"):
            self.launch_with_argfile('--gameDir "' + str(self.game_dir) + '"', process_id=456)

    def test_java_argfile_rejects_second_reference(self):
        folder = self.root / "Java Args"
        folder.mkdir(exist_ok=True)
        argfile = folder / "java.args"
        argfile.write_text('--gameDir "' + str(self.game_dir) + '"', encoding="utf-8")
        command_line = 'java @"' + str(argfile) + '" @"' + str(argfile) + '"'
        with self.assertRaisesRegex(lab.LabError, "at most one"):
            lab._launch_game_dir(command_line, datetime.now(timezone.utc))

    def test_bad_binding_rejected(self):
        class Result:
            returncode = 0
            stdout = json.dumps({"LocalAddress": "0.0.0.0", "LocalPort": 9876, "OwningProcess": 123})
        with patch.object(lab.platform, "system", return_value="Windows"), \
             patch.object(lab.shutil, "which", return_value="powershell"), \
             patch.object(lab.subprocess, "run", return_value=Result()):
            with self.assertRaisesRegex(lab.LabError, "127.0.0.1"):
                lab.listening_socket(123, 9876)

    def test_security_probe_rejects_unauthenticated_success(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch.dict(lab.os.environ, {"MC_MOD_LAB_TOKEN": "x" * 32}), \
             patch.object(lab, "urlopen", return_value=Response()):
            with self.assertRaisesRegex(lab.LabError, "unauthenticated"):
                lab.verify_security(self.identity)

    def test_security_probe_accepts_auth_and_origin_rejection(self):
        with patch.dict(lab.os.environ, {"MC_MOD_LAB_TOKEN": "x" * 32}), \
             patch.object(lab, "urlopen", side_effect=[HTTPError("local", 401, "no auth", {}, None),
                                                        HTTPError("local", 403, "origin", {}, None)]):
            lab.verify_security(self.identity)

    def test_capture_records_both_screens_without_visual_pass(self):
        result = self.run_capture()
        self.assertEqual(result["status"], "captured")
        self.assertEqual(result["visual_check"], "not_reviewed")
        self.assertEqual(result["control_mode_exit"], "acknowledged")
        self.assertEqual(result["before"]["blank_button_labels"], 2)
        self.assertEqual(result["before"]["duplicate_widgets"], 1)
        self.assertTrue((self.root / "report" / "before.png").exists())
        self.assertTrue((self.root / "report" / "after.png").exists())
        saved = lab.read_json(self.root / "report" / "report.json")
        self.assertNotIn("private", json.dumps(saved))
        self.assertNotIn(str(self.root), json.dumps(saved))

    def test_wrong_world_is_not_captured(self):
        def wrong_world(port, endpoint, payload=None):
            if endpoint == "/api/cmd" and payload["cmd"] == "get_world_info":
                return {"world_name": "ValuedWorld"}
            return self.fake_http(port, endpoint, payload)
        result = self.run_capture(http=wrong_world)
        self.assertEqual(result["status"], "unsupported")
        self.assertFalse((self.root / "report" / "before.png").exists())

    def test_duplicate_world_name_with_wrong_path_is_unsupported(self):
        other = lab.fixture_create(self.seed, self.game_dir / "saves", "other", "LabFixture")

        def wrong_path(port, endpoint, payload=None):
            if endpoint == "/api/cmd" and payload["cmd"] == "get_world_info":
                return {"world_name": "LabFixture", "world_path": str(other),
                        "gametype": "CREATIVE"}
            return self.fake_http(port, endpoint, payload)

        self.assertEqual(self.run_capture(http=wrong_path)["status"], "unsupported")

    def test_placeholder_world_and_player_fields_are_unsupported(self):
        def placeholder_world(port, endpoint, payload=None):
            if endpoint == "/api/cmd" and payload["cmd"] == "get_world_info":
                return {"world_name": "unknown", "gametype": "survival"}
            return self.fake_http(port, endpoint, payload)
        self.assertEqual(self.run_capture(http=placeholder_world)["status"], "unsupported")

        def placeholder_player(port, endpoint, payload=None):
            if endpoint == "/api/cmd" and payload["cmd"] == "get_player_info":
                return {"name": "", "gamemode": "survival"}
            return self.fake_http(port, endpoint, payload)
        self.assertEqual(self.run_capture(http=placeholder_player)["status"], "unsupported")

    def test_click_false_is_failure(self):
        def false_click(port, endpoint, payload=None):
            if endpoint == "/api/cmd" and payload["cmd"] == "click":
                return {"clicked": False, "method": "screen-event"}
            return self.fake_http(port, endpoint, payload)
        self.assertEqual(self.run_capture(http=false_click)["status"], "fail")

    def test_missing_screenshot_is_failure(self):
        def no_screenshot(port, endpoint, payload=None):
            if endpoint == "/api/screenshot":
                return {"error": "capture failed"}
            return self.fake_http(port, endpoint, payload)
        result = self.run_capture(http=no_screenshot)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["client_check"], "failed")

    def test_cropped_screenshot_is_failure_with_artifact(self):
        self.identity["min_capture_width"] = 1280
        self.save_inputs()
        result = self.run_capture()
        self.assertEqual(result["status"], "fail")
        self.assertIn("cropped", result["reason"])
        self.assertEqual(result["artifacts"][0]["file"], "before.png")

    def test_screen_expectation_detects_failure_and_corrected_case(self):
        self.scenario["expect"]["after_screen"] = "OtherScreen"
        self.save_inputs()
        self.assertEqual(self.run_capture()["status"], "fail")
        self.scenario["expect"]["after_screen"] = "GuideScreen"
        self.save_inputs()
        self.assertEqual(self.run_capture()["status"], "captured")

    def test_memory_excess_is_failure(self):
        self.assertEqual(self.run_capture(memory=501)["status"], "fail")

    def test_desktop_telemetry_does_not_fail_tool_group_guard(self):
        self.identity["informational_pids"] = [456]
        self.save_inputs()
        result = self.run_capture(memory=lambda pid: 100 if pid == 123 else 5000)
        self.assertEqual(result["status"], "captured")
        self.assertEqual(result["before"]["tool_group_working_set_mb"], 100)
        self.assertEqual(result["before"]["combined_telemetry_mb"], 5100)

    def test_tool_group_limit_cannot_exceed_checkpoint_guard(self):
        self.identity["max_group_mb"] = 4000
        self.save_inputs()
        self.assertEqual(self.run_capture()["status"], "unsupported")

    def test_unknown_action_rejected_before_bridge(self):
        self.scenario["action"] = {"tool": "execute_command", "params": {"command": "say hi"}}
        self.save_inputs()
        self.assertEqual(self.run_capture()["status"], "unsupported")

    def test_use_item_is_bounded_and_reported(self):
        self.scenario["action"] = {"tool": "use_item", "params": {}}
        self.save_inputs()
        result = self.run_capture()
        self.assertEqual(result["status"], "captured")
        self.assertEqual(result["action"], self.scenario["action"])

    def test_use_item_rejects_parameters(self):
        self.scenario["action"] = {"tool": "use_item", "params": {"command": "say hi"}}
        self.save_inputs()
        self.assertEqual(self.run_capture()["status"], "unsupported")

    def test_use_item_screen_assertion_failure(self):
        self.scenario["action"] = {"tool": "use_item", "params": {}}
        self.scenario["expect"]["after_screen"] = "ExpectedBookScreen"
        self.save_inputs()
        self.assertEqual(self.run_capture()["status"], "fail")

    def test_missing_screen_assertion_is_unsupported(self):
        del self.scenario["expect"]["after_screen"]
        self.save_inputs()
        self.assertEqual(self.run_capture()["status"], "unsupported")

    def test_action_failure_still_exits_control_mode(self):
        seen = []

        def failing_action(port, endpoint, payload=None):
            if endpoint == "/api/cmd":
                seen.append(payload["cmd"])
                if payload["cmd"] == "click":
                    return {"error": "not available"}
            return self.fake_http(port, endpoint, payload)

        result = self.run_capture(http=failing_action)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["control_mode_exit"], "acknowledged")
        self.assertIn("exit_control_mode", seen)


if __name__ == "__main__":
    unittest.main()
