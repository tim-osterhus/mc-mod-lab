import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import contracts
import lab
import runtime_profile
import runtime_launch


class RuntimeProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        java_home = self.root / "jdk21"
        (java_home / "bin").mkdir(parents=True)
        self.java = java_home / "bin" / "java.exe"
        self.java.write_bytes(b"fake java launcher")
        (java_home / "release").write_text('JAVA_VERSION="21.0.1"\n', encoding="utf-8")
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "level.dat").write_bytes(b"level")
        (self.seed / "session.lock").write_bytes(b"12345678")
        self.args = self.root / "launcher.args"
        args = ["-Xmx1280m", "-Daura.qa.observer.dir=OLD_PRIVATE_OUTPUT",
                "-cp", str(self.root / "fabric-loader-0.19.1.jar"),
                "net.fabricmc.loader.impl.launch.knot.KnotClient", "--accessToken", "CANARY_CREDENTIAL",
                "--gameDir", "OLD_GAME", "--quickPlayPath", "OLD_QUICKPLAY",
                "--quickPlaySingleplayer", "OLD_WORLD"]
        self.args.write_text("\n".join(json.dumps(item) for item in args) + "\n", encoding="utf-8")
        self.target = self.make_mod("aura.jar", "auracascade", "0.2.1+1.21.1")
        self.bridge = self.make_mod("bridge.jar", "minecraft-mod-mcp", "0.3.0")
        self.manifest = {"schema_version": 1, "java_exe": str(self.java),
                         "launcher_args": str(self.args), "launcher_args_sha256": lab.sha256(self.args),
                         "seed_save": str(self.seed), "fixture_id": "first-circuit",
                         "world_name": "LabFixture", "expected_gamemode": "creative",
                         "bridge_classification": "private_diagnostic", "mods": [
                             {"role": "target", "path": str(self.target), "sha256": lab.sha256(self.target),
                              "mod_id": "auracascade", "mod_version": "0.2.1+1.21.1"},
                             {"role": "bridge", "path": str(self.bridge), "sha256": lab.sha256(self.bridge),
                              "mod_id": "minecraft-mod-mcp", "mod_version": "0.3.0"}]}
        self.manifest_file = self.root / "manifest.json"
        self.save()

    def make_mod(self, filename, mod_id, version):
        path = self.root / filename
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("fabric.mod.json", json.dumps({"id": mod_id, "version": version}))
        return path

    def save(self):
        lab.write_json(self.manifest_file, self.manifest)

    def test_prepare_exact_mods_and_private_args(self):
        result = runtime_profile.prepare(self.manifest_file, self.root / "prepared")
        self.assertEqual(result["status"], "prepared_not_launched")
        self.assertEqual(len(result["mods"]), 2)
        profile = self.root / "prepared"
        world = profile / "game" / "saves" / result["world_directory"]
        self.assertTrue((world / "level.dat").exists())
        self.assertFalse((world / "session.lock").exists())
        self.assertEqual(lab.sha256(profile / "game" / "mods" / "aura.jar"), lab.sha256(self.target))
        prepared = [json.loads(line) for line in (profile / "java.args").read_text(encoding="utf-8").splitlines()]
        self.assertNotIn("-Daura.qa.observer.dir=OLD_PRIVATE_OUTPUT", prepared)
        self.assertEqual(prepared[prepared.index("--gameDir") + 1], str(profile / "game"))
        self.assertEqual(prepared[prepared.index("--quickPlaySingleplayer") + 1], world.name)
        self.assertIn("CANARY_CREDENTIAL", prepared)
        portable = (profile / "profile.json").read_text(encoding="utf-8")
        self.assertNotIn("CANARY_CREDENTIAL", portable)
        self.assertNotIn(str(self.root), portable)
        contracts.portable_check(result)

    def test_hash_mismatch_refuses_before_output(self):
        self.manifest["mods"][0]["sha256"] = "0" * 64
        self.save()
        with self.assertRaisesRegex(lab.LabError, "hash"):
            runtime_profile.prepare(self.manifest_file, self.root / "prepared")
        self.assertFalse((self.root / "prepared").exists())

    def test_bad_launcher_hash_refuses_before_output(self):
        self.manifest["launcher_args_sha256"] = "0" * 64
        self.save()
        with self.assertRaisesRegex(lab.LabError, "template hash"):
            runtime_profile.prepare(self.manifest_file, self.root / "prepared")
        self.assertFalse((self.root / "prepared").exists())

    def test_duplicate_mod_id_refuses_before_output(self):
        self.manifest["mods"][1]["mod_id"] = "auracascade"
        self.save()
        with self.assertRaisesRegex(lab.LabError, "duplicate"):
            runtime_profile.prepare(self.manifest_file, self.root / "prepared")
        self.assertFalse((self.root / "prepared").exists())

    def test_bad_argfile_refuses_without_leaking_contents(self):
        self.args.write_text('"--gameDir"\n"MALFORMED\\q"\n', encoding="utf-8")
        self.manifest["launcher_args_sha256"] = lab.sha256(self.args)
        self.save()
        with self.assertRaisesRegex(lab.LabError, "launcher argument template"):
            runtime_profile.prepare(self.manifest_file, self.root / "prepared")

    def test_launch_preflight_rejects_wrong_scenario_before_spawn(self):
        runtime_profile.prepare(self.manifest_file, self.root / "prepared")
        scenario = {"schema_version": 2, "id": "smoke", "fixture": "wrong-fixture",
                    "runtime": {"kind": "prepared-packaged-client", "mod_id": "auracascade",
                                "mod_version": "0.2.1+1.21.1", "artifact_sha256": lab.sha256(self.target)},
                    "steps": [{"id": "world", "require": {"type": "world_name", "equals": "LabFixture"}}],
                    "cleanup": "release-control"}
        scenario_file = self.root / "scenario.json"
        lab.write_json(scenario_file, scenario)
        with patch.object(runtime_launch.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(lab.LabError, "scenario does not match"):
                runtime_launch.launch(self.manifest_file, self.root / "prepared", scenario_file)
            spawn.assert_not_called()

    def test_diagnostic_launch_report_cannot_claim_public_backend(self):
        runtime_profile.prepare(self.manifest_file, self.root / "prepared")
        scenario = {"schema_version": 2, "id": "smoke", "fixture": "first-circuit",
                    "runtime": {"kind": "prepared-packaged-client", "mod_id": "auracascade",
                                "mod_version": "0.2.1+1.21.1", "artifact_sha256": lab.sha256(self.target)},
                    "steps": [{"id": "world", "require": {"type": "world_name", "equals": "LabFixture"}}],
                    "cleanup": "release-control"}
        scenario_file = self.root / "scenario.json"
        lab.write_json(scenario_file, scenario)

        class FakeProcess:
            pid = 123

            def poll(self):
                return 0

        with patch.object(runtime_launch.subprocess, "Popen", return_value=FakeProcess()), \
             patch.object(runtime_launch, "_choose_port", return_value=9875), \
             patch.object(runtime_launch, "_wait_ready", return_value={"pid": 123}), \
             patch.object(runtime_launch.scenario_v2, "run", return_value={"status": "pass"}), \
             patch.object(runtime_launch, "_close_owned", return_value={"status": "pass", "exit_code": 0}):
            result = runtime_launch.launch(self.manifest_file, self.root / "prepared", scenario_file)
        self.assertEqual(result["status"], "diagnostic_only")
        self.assertEqual(result["scenario_status"], "pass")
        saved = (self.root / "prepared" / "lifecycle-report.json").read_text(encoding="utf-8")
        self.assertNotIn("CANARY_CREDENTIAL", saved)
        self.assertNotIn(str(self.root), saved)


if __name__ == "__main__":
    unittest.main()
