import json
from contextlib import nullcontext
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

import contracts
import lab
import runtime_launch
import runtime_profile


class RuntimeLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        java_home = self.root / "jdk21"
        (java_home / "bin").mkdir(parents=True)
        self.java = java_home / "bin" / "java.exe"
        self.java.write_bytes(b"offline fake Java launcher")
        (java_home / "release").write_text('JAVA_VERSION="21.0.1"\n', encoding="utf-8")
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "level.dat").write_bytes(b"closed fixture seed")
        (self.seed / "session.lock").write_bytes(b"seed lock")
        self.args = self.root / "launcher.args"
        args = ["-Xmx1280m", "-cp", str(self.root / "fabric-loader-0.19.1.jar"),
                "net.fabricmc.loader.impl.launch.knot.KnotClient",
                "--accessToken", "CANARY_CREDENTIAL", "--gameDir", "OLD_GAME",
                "--quickPlayPath", "OLD_QUICKPLAY", "--quickPlaySingleplayer", "OLD_WORLD"]
        self.args.write_text("\n".join(json.dumps(item) for item in args) + "\n", encoding="utf-8")
        self.target = self.make_mod("aura.jar", "auracascade", "0.2.1+1.21.1")
        self.bridge = self.make_mod("bridge.jar", "minecraft-mod-mcp", "0.3.0")
        self.manifest = {
            "schema_version": 1,
            "java_exe": str(self.java),
            "launcher_args": str(self.args),
            "launcher_args_sha256": lab.sha256(self.args),
            "seed_save": str(self.seed),
            "fixture_id": "first-circuit",
            "world_name": "LabFixture",
            "expected_gamemode": "creative",
            "bridge_classification": "private_diagnostic",
            "mods": [
                {"role": "target", "path": str(self.target), "sha256": lab.sha256(self.target),
                 "mod_id": "auracascade", "mod_version": "0.2.1+1.21.1"},
                {"role": "bridge", "path": str(self.bridge), "sha256": lab.sha256(self.bridge),
                 "mod_id": "minecraft-mod-mcp", "mod_version": "0.3.0"},
            ],
        }
        self.manifest_file = self.root / "manifest.json"
        lab.write_json(self.manifest_file, self.manifest)
        self.profile = self.make_profile("prepared")
        self.scenario_file = self.write_scenario(self.profile)

    def make_mod(self, filename, mod_id, version, payload=b""):
        path = self.root / filename
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("fabric.mod.json", json.dumps({"id": mod_id, "version": version}))
            if payload:
                archive.writestr("payload.bin", payload)
        return path

    def make_profile(self, name):
        profile = self.root / name
        runtime_profile.prepare(self.manifest_file, profile)
        return profile

    def write_scenario(self, profile, artifact_hash=None):
        scenario = {
            "schema_version": 2,
            "id": "launch-preflight",
            "fixture": "first-circuit",
            "runtime": {
                "kind": "prepared-packaged-client",
                "mod_id": "auracascade",
                "mod_version": "0.2.1+1.21.1",
                "artifact_sha256": artifact_hash or lab.sha256(self.target),
            },
            "steps": [{"id": "world", "require": {"type": "world_name", "equals": "LabFixture"}}],
            "cleanup": "release-control",
        }
        path = self.root / (profile.name + "-scenario.json")
        lab.write_json(path, scenario)
        return path

    def launch_with_stubs(self, profile=None, scenario_file=None, port=9875,
                          scenario_status="pass", monitor_cancel=False,
                          cleanup_status="pass", scenario_error=None):
        profile = profile or self.profile
        scenario_file = scenario_file or self.write_scenario(profile)
        observed = {}

        class FakeProcess:
            pid = 65432

            def poll(self):
                return 0

        process = FakeProcess()

        def spawn(command, **kwargs):
            observed["command"] = command
            observed["popen_kwargs"] = kwargs
            return process

        def ready(_profile, _data, _manifest, selected, expected_port, _deadline, _cancel):
            observed["expected_port"] = expected_port
            return {"pid": selected.pid}

        def run_scenario(*_args, cancel_event=None, **_kwargs):
            observed["cancel_seen"] = cancel_event.is_set()
            if scenario_error is not None:
                raise scenario_error
            return {"status": scenario_status}

        def monitor(_process, _stop, cancel, _memory):
            if monitor_cancel:
                cancel.set()

        class InlineThread:
            def __init__(self, target, args=(), daemon=False):
                self.target = target
                self.args = args

            def start(self):
                self.target(*self.args)

            def join(self, timeout=None):
                pass

        with patch.object(runtime_launch.subprocess, "Popen", side_effect=spawn), \
             patch.object(runtime_launch, "_choose_port", return_value=port), \
             patch.object(runtime_launch, "_wait_ready", side_effect=ready), \
             patch.object(runtime_launch.scenario_v2, "run", side_effect=run_scenario), \
             patch.object(runtime_launch, "_close_owned",
                          return_value={"status": cleanup_status}), \
             patch.object(runtime_launch, "_monitor", side_effect=monitor), \
             patch.object(runtime_launch.threading, "Thread", InlineThread), \
             patch.object(runtime_launch.platform, "system", return_value="Windows"):
            result = runtime_launch.launch(self.manifest_file, profile, scenario_file)
        return result, observed

    def test_modified_args_or_jar_are_refused_before_spawning(self):
        cases = [
            ("args", "arguments changed"),
            ("jar", "prepared mod changed"),
        ]
        for mutation, message in cases:
            with self.subTest(mutation=mutation):
                profile = self.make_profile("prepared-" + mutation)
                if mutation == "args":
                    with (profile / "java.args").open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps("--unexpected") + "\n")
                else:
                    jar = profile / "game" / "mods" / "aura.jar"
                    jar.write_bytes(jar.read_bytes() + b"mutated")
                scenario = self.write_scenario(profile)
                with patch.object(runtime_launch.subprocess, "Popen") as spawn:
                    with self.assertRaisesRegex(lab.LabError, message):
                        runtime_launch.launch(self.manifest_file, profile, scenario)
                    spawn.assert_not_called()

    def test_rewritten_profile_metadata_cannot_authorize_a_replacement_jar(self):
        """The prepared profile's metadata must remain bound to the reviewed manifest."""
        profile = self.make_profile("prepared-rebound")
        staged = profile / "game" / "mods" / "aura.jar"
        replacement = self.make_mod("replacement.jar", "auracascade", "0.2.1+1.21.1", b"replacement")
        staged.write_bytes(replacement.read_bytes())
        profile_json = profile / "profile.json"
        data = contracts.load(profile_json)
        target = next(item for item in data["mods"] if item["role"] == "target")
        target["sha256"] = lab.sha256(staged)
        lab.write_json(profile_json, data)
        scenario = self.write_scenario(profile, artifact_hash=target["sha256"])

        with patch.object(runtime_launch.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(lab.LabError, "reviewed runtime manifest"):
                runtime_launch.launch(self.manifest_file, profile, scenario)
            spawn.assert_not_called()

    def test_private_diagnostic_pass_is_not_reported_as_public_pass(self):
        result, observed = self.launch_with_stubs()
        self.assertEqual(result["scenario_status"], "pass")
        self.assertEqual(result["status"], "diagnostic_only")
        self.assertEqual(observed["expected_port"], 9875)
        self.assertEqual(observed["popen_kwargs"]["env"]["MC_MCP_PORT"], "9875")
        self.assertIn("CANARY_CREDENTIAL", (self.profile / "java.args").read_text(encoding="utf-8"))

    def test_child_environment_does_not_inherit_host_secrets(self):
        with patch.dict(os.environ, {"MC_MOD_LAB_TEST_SECRET": "CANARY_HOST_SECRET"}):
            _result, observed = self.launch_with_stubs()
        child = observed["popen_kwargs"]["env"]
        self.assertNotIn("MC_MOD_LAB_TEST_SECRET", child)
        self.assertEqual(len(child["MC_MOD_LAB_TOKEN"]), 64)

    def test_startup_memory_breach_cancels_readiness_and_closes_owned_client(self):
        class Process:
            pid = 65432

            def poll(self):
                return None

        class InlineThread:
            def __init__(self, target, args=(), daemon=False):
                self.target = target
                self.args = args

            def start(self):
                self.args[2].set()

            def join(self, timeout=None):
                pass

        with patch.object(runtime_launch.subprocess, "Popen", return_value=Process()), \
             patch.object(runtime_launch, "_choose_port", return_value=9875), \
             patch.object(runtime_launch.threading, "Thread", InlineThread), \
             patch.object(runtime_launch, "_owned_loopback_ports") as listeners, \
             patch.object(runtime_launch, "_close_owned",
                          return_value={"status": "pass", "exit_code": 0}) as close, \
             patch.object(runtime_launch.scenario_v2, "run") as scenario:
            result = runtime_launch.launch(self.manifest_file, self.profile, self.scenario_file)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["scenario_status"], "not_run")
        self.assertIn("startup cancelled", result["reason"])
        close.assert_called_once()
        listeners.assert_not_called()
        scenario.assert_not_called()
        self.assert_portable_lifecycle_report(self.profile)

    def test_two_profiles_receive_distinct_ports(self):
        second = self.make_profile("prepared-second")
        first_result, first = self.launch_with_stubs(port=9875)
        second_result, second_observed = self.launch_with_stubs(profile=second, port=9874)
        self.assertEqual(first_result["status"], "diagnostic_only")
        self.assertEqual(second_result["status"], "diagnostic_only")
        self.assertEqual(first["popen_kwargs"]["env"]["MC_MCP_PORT"], "9875")
        self.assertEqual(second_observed["popen_kwargs"]["env"]["MC_MCP_PORT"], "9874")

    def test_choose_port_skips_a_listener_held_by_another_profile(self):
        active_ports = set()

        class ProbeSocket:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def bind(self, address):
                if address[1] in active_ports:
                    raise OSError("port already bound")

        with patch.object(runtime_launch.socket, "socket", side_effect=lambda *_args: ProbeSocket()):
            first = runtime_launch._choose_port()
            active_ports.add(first)  # Simulate the first profile's live bridge listener.
            second = runtime_launch._choose_port()
        self.assertEqual(first, 9875)
        self.assertEqual(second, 9874)

    def test_owned_listener_query_is_scoped_to_pid_and_loopback(self):
        completed = subprocess.CompletedProcess([], 0, stdout="[9875,9874,0,65536]", stderr="")
        with patch.object(runtime_launch.platform, "system", return_value="Windows"), \
             patch.object(runtime_launch.shutil, "which", return_value="powershell"), \
             patch.object(runtime_launch.subprocess, "run", return_value=completed) as query:
            ports = runtime_launch._owned_loopback_ports(4242)
        self.assertEqual(ports, [9875, 9874])
        command = query.call_args.args[0][-1]
        self.assertIn("$_.OwningProcess -eq 4242", command)
        self.assertIn("$_.LocalAddress -eq '127.0.0.1'", command)

    def test_readiness_uses_only_the_expected_owned_listener_port(self):
        class LiveProcess:
            pid = 4242

            def poll(self):
                return None

        seen = []
        identity = {"pid": 4242, "port": 9875}
        with patch.object(runtime_launch, "_owned_loopback_ports", return_value=[9874, 9875]), \
             patch.object(runtime_launch, "_identity", side_effect=lambda *_args: (seen.append(_args[-1]), identity)[1]), \
             patch.object(lab, "validate_identity"), patch.object(lab, "check_derivative"), \
             patch.object(lab, "launch_check"), patch.object(lab, "status_check"), \
             patch.object(lab, "world_check"), patch.object(lab, "player_check"):
            result = runtime_launch._wait_ready(self.profile, {}, {}, LiveProcess(), 9875,
                                                runtime_launch.time.monotonic() + 30,
                                                threading.Event())
        self.assertIs(result, identity)
        self.assertEqual(seen, [9875])

    def test_memory_guard_sets_cancellation(self):
        class OneSampleStop:
            stopped = False

            def is_set(self):
                return self.stopped

            def wait(self, _seconds):
                self.stopped = True

        class LiveProcess:
            pid = 123

            def poll(self):
                return None

        cancel = threading.Event()
        memory = {"peak_working_set_mib": 0, "peak_private_mib": 0, "samples": 0}
        with patch.object(lab, "process_mb", return_value=1901), \
             patch.object(lab, "process_private_mb", return_value=300):
            runtime_launch._monitor(LiveProcess(), OneSampleStop(), cancel, memory)
        self.assertTrue(cancel.is_set())
        self.assertEqual(memory["samples"], 1)
        self.assertEqual(memory["peak_working_set_mib"], 3802)

    def test_guard_cancellation_fails_lifecycle_and_restores_prior_token(self):
        with patch.dict("os.environ", {"MC_MOD_LAB_TOKEN": "PREEXISTING_TOKEN"}, clear=False):
            result, observed = self.launch_with_stubs(monitor_cancel=True)
            self.assertEqual(os.environ["MC_MOD_LAB_TOKEN"], "PREEXISTING_TOKEN")
        self.assertTrue(observed["cancel_seen"])
        self.assertEqual(result["status"], "fail")
        self.assert_portable_lifecycle_report(self.profile)

    def test_scenario_failure_evidence_does_not_include_credentials_or_local_paths(self):
        result, _observed = self.launch_with_stubs(
            scenario_error=lab.LabError("runtime memory guard or cancellation triggered", "fail"))
        self.assertEqual(result["status"], "fail")
        self.assert_portable_lifecycle_report(self.profile)

    def assert_portable_lifecycle_report(self, profile):
        report = (profile / "lifecycle-report.json").read_text(encoding="utf-8")
        self.assertNotIn("CANARY_CREDENTIAL", report)
        self.assertNotIn(str(self.root), report)

    def test_close_owned_confirms_normal_exit_and_closed_save(self):
        class Process:
            pid = 77
            terminated = False

            def poll(self):
                return None

            def wait(self, timeout):
                self.timeout = timeout
                return 0

            def terminate(self):
                self.terminated = True

        process = Process()
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with patch.object(runtime_launch.shutil, "which", return_value="powershell"), \
             patch.object(runtime_launch.subprocess, "run", return_value=completed) as close, \
             patch.object(lab, "closed_seed_lock", return_value=nullcontext()) as lock:
            result = runtime_launch._close_owned(process, self.seed)
        self.assertEqual(result, {"status": "pass", "exit_code": 0})
        self.assertFalse(process.terminated)
        self.assertEqual(process.timeout, 30)
        self.assertIn("CloseMainWindow", close.call_args.args[0][-1])
        lock.assert_called_once_with(self.seed)

    def test_close_owned_terminates_after_close_failure_or_timeout(self):
        class Process:
            pid = 77

            def __init__(self, timeout_first=False):
                self.timeout_first = timeout_first
                self.waits = []
                self.terminated = False

            def poll(self):
                return None

            def wait(self, timeout):
                self.waits.append(timeout)
                if timeout == 30 and self.timeout_first:
                    raise subprocess.TimeoutExpired("fake-java", timeout)
                return 0

            def terminate(self):
                self.terminated = True

        with patch.object(runtime_launch.shutil, "which", return_value="powershell"), \
             patch.object(runtime_launch.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 2, stdout="", stderr="")):
            close_failed = Process()
            result = runtime_launch._close_owned(close_failed, self.seed)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(close_failed.terminated)
        self.assertEqual(close_failed.waits, [10])

        with patch.object(runtime_launch.shutil, "which", return_value="powershell"), \
             patch.object(runtime_launch.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, stdout="", stderr="")):
            timed_out = Process(timeout_first=True)
            result = runtime_launch._close_owned(timed_out, self.seed)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(timed_out.terminated)
        self.assertEqual(timed_out.waits, [30, 10])

    def test_close_owned_terminates_when_powershell_is_unavailable(self):
        class Process:
            pid = 77
            terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout):
                return 0

        process = Process()
        with patch.object(runtime_launch.shutil, "which", return_value=None):
            result = runtime_launch._close_owned(process, self.seed)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(process.terminated,
                        "a failed graceful-close path must still stop the owned process")


if __name__ == "__main__":
    unittest.main()
