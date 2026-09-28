"""Launcher staging and lifecycle tests; Minecraft is never started."""

from copy import deepcopy
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

import contracts
import gametest_runtime as subject
import lab


class FakeStdin:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, value):
        self.writes.append(value)
        return len(value)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakeProcess:
    pid = 4242

    def __init__(self, returncode=None, timeout_on_graceful_stop=False):
        self.returncode = returncode
        self.timeout_on_graceful_stop = timeout_on_graceful_stop
        self.stdin = FakeStdin()
        self.waits = []
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.waits.append(timeout)
        if timeout == 5 and self.timeout_on_graceful_stop:
            raise subprocess.TimeoutExpired("fake-java", timeout)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


class GameTestRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()

        java_home = self.root / "jdk21"
        (java_home / "bin").mkdir(parents=True)
        self.java = java_home / "bin" / "java.exe"
        self.java.write_bytes(b"fake Java launcher; never executed")
        (java_home / "release").write_text('JAVA_VERSION="21.0.1"\n', encoding="utf-8")

        library = self.runtime / "libraries/example/pinned.jar"
        library.parent.mkdir(parents=True)
        library.write_bytes(b"reviewed runtime library")
        self.write_launcher("libraries/example/pinned.jar")
        server = self.runtime / "server.jar"
        server.write_bytes(b"reviewed server")

        self.inputs = {}
        for name in ("aura", "fabric-api", "patchouli", "fabric-gametest", "lab-gametest"):
            path = self.root / (name + ".jar")
            path.write_bytes(("reviewed " + name).encode())
            self.inputs[name] = path

        profile = deepcopy(contracts.load(subject.PROFILE))
        profile["artifacts"] = [
            {"file": name, "sha256": lab.sha256(path)}
            for name, path in (
                ("fabric-server-launch.jar", self.runtime / "fabric-server-launch.jar"),
                ("server.jar", server),
                ("libraries/example/pinned.jar", library),
                ("mods/aura.jar", self.inputs["aura"]),
                ("mods/fabric-api.jar", self.inputs["fabric-api"]),
                ("mods/patchouli.jar", self.inputs["patchouli"]),
                ("mods/fabric-gametest.jar", self.inputs["fabric-gametest"]),
            )
        ]
        self.profile = self.root / "reviewed-profile.json"
        lab.write_json(self.profile, profile)
        self.addCleanup(patch.stopall)
        patch.object(subject, "PROFILE", self.profile).start()

        self.args = types.SimpleNamespace(
            runtime=self.runtime,
            out=self.root / "out",
            java=self.java,
            aura=self.inputs["aura"],
            fabric_api=self.inputs["fabric-api"],
            patchouli=self.inputs["patchouli"],
            gametest=self.inputs["fabric-gametest"],
            adapter=self.inputs["lab-gametest"],
            adapter_sha256=lab.sha256(self.inputs["lab-gametest"]),
            blocked=False,
        )

    def write_launcher(self, classpath):
        launcher = self.runtime / "fabric-server-launch.jar"
        manifest = (
            "Manifest-Version: 1.0\r\n"
            "Main-Class: net.fabricmc.loader.impl.launch.server.FabricServerLauncher\r\n"
            "Class-Path: " + classpath + "\r\n\r\n"
        )
        with zipfile.ZipFile(launcher, "w") as archive:
            archive.writestr("META-INF/MANIFEST.MF", manifest)

    def refresh_launcher_pin(self):
        profile = contracts.load(self.profile)
        launcher = self.runtime / "fabric-server-launch.jar"
        entry = next(item for item in profile["artifacts"]
                     if item["file"] == "fabric-server-launch.jar")
        entry["sha256"] = lab.sha256(launcher)
        lab.write_json(self.profile, profile)

    def test_changed_pinned_input_is_refused_before_output_creation(self):
        (self.runtime / "server.jar").write_bytes(b"replacement server")

        with self.assertRaisesRegex(lab.LabError, "differs from reviewed"):
            subject.prepare(self.args)
        self.assertFalse(self.args.out.exists())

    def test_staging_uses_only_the_reviewed_inventory_not_recursive_jars(self):
        extra = self.runtime / "mods/nested/unreviewed.jar"
        extra.parent.mkdir(parents=True)
        extra.write_bytes(b"unreviewed extra")

        subject.prepare(self.args)

        expected = {item["file"] for item in contracts.load(self.profile)["artifacts"]}
        expected.add("mods/lab-gametest.jar")
        staged = {path.relative_to(self.args.out).as_posix()
                  for path in self.args.out.rglob("*.jar")}
        self.assertEqual(staged, expected)
        self.assertFalse((self.args.out / "mods/nested/unreviewed.jar").exists())

    def test_manifest_cannot_expand_the_reviewed_classpath(self):
        extra = self.runtime / "libraries/example/unreviewed.jar"
        extra.write_bytes(b"unreviewed classpath entry")
        self.write_launcher("libraries/example/pinned.jar libraries/example/unreviewed.jar")
        self.refresh_launcher_pin()

        with self.assertRaisesRegex(lab.LabError, "unreviewed libraries"):
            subject.prepare(self.args)
        self.assertFalse(self.args.out.exists())

    def test_output_must_be_fresh(self):
        subject.prepare(self.args)

        with self.assertRaisesRegex(lab.LabError, "must be fresh"):
            subject.prepare(self.args)

    def test_symlink_ancestor_is_refused(self):
        target = self.root / "real-parent"
        target.mkdir()
        link = self.root / "linked-parent"
        try:
            os.symlink(target, link, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest("directory symlinks are unavailable: " + str(exc))
        self.args.out = link / "out"

        with self.assertRaisesRegex(lab.LabError, "symlink or reparse"):
            subject.prepare(self.args)
        self.assertFalse((target / "out").exists())

    def test_reparse_ancestor_metadata_is_refused(self):
        path_type = type(self.args.out)
        original_lstat = path_type.lstat
        cases = (
            ("symlink", types.SimpleNamespace(st_mode=stat.S_IFLNK | 0o777,
                                               st_file_attributes=0)),
            ("reparse", types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o755,
                                               st_file_attributes=0x400)),
        )
        for name, metadata in cases:
            with self.subTest(kind=name):
                parent = self.root / (name + "-metadata-parent")
                parent.mkdir()
                self.args.out = parent / "out"

                def lstat(path):
                    if path == parent:
                        return metadata
                    return original_lstat(path)

                with patch.object(path_type, "lstat", autospec=True, side_effect=lstat):
                    with self.assertRaisesRegex(lab.LabError, "symlink or reparse"):
                        subject.prepare(self.args)
                self.assertFalse((parent / "out").exists())

    def run_with_process(self, process, extra_env=None, memory_private=0, memory_working=0,
                         monotonic=None):
        env = {"MC_MOD_LAB_TEST_SECRET": "host-secret"}
        if extra_env:
            env.update(extra_env)
        time_values = iter(monotonic or ())

        def clock():
            try:
                return next(time_values)
            except StopIteration:
                return 200.0

        with patch.dict(os.environ, env), \
             patch.object(subject.subprocess, "Popen", return_value=process) as popen, \
             patch.object(subject.platform, "system", return_value="Linux"), \
             patch.object(lab, "process_private_mb", return_value=memory_private), \
             patch.object(lab, "process_mb", return_value=memory_working), \
             patch.object(subject.time, "monotonic", side_effect=clock), \
             patch.object(subject.time, "sleep"):
            report = subject.run(self.args)
        return report, popen

    def test_launcher_environment_is_filtered(self):
        process = FakeProcess(returncode=0)

        report, popen = self.run_with_process(
            process, {"PATH": "fixture-path", "TEMP": "fixture-temp"})

        child_env = popen.call_args.kwargs["env"]
        self.assertNotIn("MC_MOD_LAB_TEST_SECRET", child_env)
        self.assertEqual(child_env["PATH"], "fixture-path")
        self.assertEqual(child_env["TEMP"], "fixture-temp")
        self.assertEqual(report["status"], "completed")
        self.assertTrue(process.stdin.closed)

    def test_memory_limit_marks_run_incomplete_and_requests_graceful_stop(self):
        process = FakeProcess()

        report, _popen = self.run_with_process(process, memory_private=2000,
                                               monotonic=[10.0, 10.1, 10.1])

        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["peak_private_mib"], 4000)
        self.assertEqual(report["memory_samples"], 1)
        self.assertEqual(process.stdin.writes, [b"stop\n"])
        self.assertEqual(process.waits, [5])
        self.assertFalse(process.killed)
        self.assertTrue(process.stdin.closed)

    def test_wall_timeout_forces_kill_after_graceful_stop_expires(self):
        process = FakeProcess(timeout_on_graceful_stop=True)

        report, _popen = self.run_with_process(
            process, monotonic=[10.0, 190.1, 190.1])

        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(report["forced_cleanup"])
        self.assertEqual(process.stdin.writes, [b"stop\n"])
        self.assertEqual(process.waits, [5, 10])
        self.assertTrue(process.killed)
        self.assertEqual(report["exit_code"], -9)
        self.assertTrue(process.stdin.closed)


if __name__ == "__main__":
    unittest.main()
