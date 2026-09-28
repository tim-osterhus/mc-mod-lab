"""Synthetic contract fixtures; these tests never claim that Minecraft ran."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import contracts
import gametest_import as subject
import gametest_runtime
import lab


class GameTestImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.adapter = "a" * 64
        profile = contracts.load(gametest_runtime.PROFILE)
        self.loaded = deepcopy(profile["loaded_mods"])
        self.loaded["mc-mod-lab-gametest"] = {"version": "0.1.0", "origin_sha256": [self.adapter]}
        for identity in self.loaded.values():
            identity.setdefault("origin_sha256", ["b" * 64])
            identity.setdefault("origin_content_sha256", ["c" * 64])
        profile["artifacts"] = []
        self.profile = self.root / "reviewed-profile.json"
        lab.write_json(self.profile, profile)
        self.addCleanup(patch.stopall)
        patch.object(gametest_runtime, "PROFILE", self.profile).start()
        # Only archive lookup is synthetic; all evidence hashes and contents stay real.
        original = contracts.artifact_path
        patch.object(contracts, "artifact_path", side_effect=lambda root, item:
                     self.root if item["file"] == "mods/lab-gametest.jar" else original(root, item)).start()
        self.samples = [{"tick": t, "source": 1000 if t == 0 else 500,
                         "target": 0 if t == 0 else 500, "sourcePower": 0, "targetPower": 0}
                        for t in range(81)]
        self.observations = {"schema_version": 1, "test": subject.TEST, "minecraft": "1.21.1",
                             "blocked": False, "artifact_sha256": gametest_runtime.AURA_SHA,
                             "samples": self.samples, "loaded_mods": self.loaded,
                             "fixture_injection": subject.FIXTURE_INJECTION}
        self.lifecycle = {"schema_version": 1, "kind": "fabric-gametest", "status": "completed",
                          "artifact_sha256": gametest_runtime.AURA_SHA, "blocked": False,
                          "exit_code": 0, "forced_cleanup": False, "memory_limit_mib": 3800,
                          "memory_samples": 40, "peak_private_mib": 900, "peak_working_set_mib": 800,
                          "wall_limit_seconds": 180, "elapsed_seconds": 20,
                          "client_check": "not_run", "visual_check": "not_run"}
        (self.root / "evidence").mkdir()
        self.xml = self.root / "evidence/gametest.xml"
        self.write_xml()

    def write_xml(self, failure="", extra=""):
        self.xml.write_text('<testsuite><testsuite><testcase name="' + subject.SMOKE +
                            '" time="0"/><testcase name="' + subject.TEST + '" time="0.1">' +
                            failure + '</testcase>' + extra + '</testsuite></testsuite>')

    def refresh(self):
        lab.write_json(self.root / "gametest-observations.json", self.observations)
        lab.write_json(self.root / "runtime-inputs.json", {
            "schema_version": 1, "profile_sha256": lab.sha256(self.profile),
            "artifacts": [{"file": "mods/lab-gametest.jar", "sha256": self.adapter}]})
        self.lifecycle["artifacts"] = [{"file": name, "sha256": lab.sha256(self.root / name)} for name in
                                       ("runtime-inputs.json", "evidence/gametest.xml", "gametest-observations.json")]
        lab.write_json(self.root / "lifecycle.json", self.lifecycle)

    def run_import(self):
        self.refresh()
        return subject.import_run(self.root, self.adapter)

    def test_positive_exports_only_deterministic_dimension(self):
        self.refresh()
        result = subject.export_run(self.root, self.adapter)
        self.assertEqual(result["status"], "pass")
        parity = contracts.load(self.root / "parity.json")
        self.assertEqual(parity["client_check"]["status"], "not_run")
        self.assertEqual(parity["visual_check"]["status"], "not_run")
        contracts.validate_parity(parity, self.root, portable=True)

    def test_expected_broken_control_stays_failed(self):
        self.lifecycle.update(blocked=True, exit_code=1)
        self.observations["blocked"] = True
        for sample in self.samples:
            sample.update(source=1000, target=0)
        self.write_xml('<failure message="' + subject.EXPECTED_FAILURE + '"/>')
        result = self.run_import()
        self.assertEqual(result["status"], "fail")
        self.assertTrue(result["expected_outcome_verified"])

    def test_crash_not_accepted_as_known_broken_control(self):
        self.lifecycle.update(blocked=True, exit_code=1)
        self.observations["blocked"] = True
        for sample in self.samples:
            sample.update(source=1000, target=0)
        self.write_xml('<error message="' + subject.EXPECTED_FAILURE + '"/>')
        with self.assertRaisesRegex(contracts.ContractError, "intended blocked"):
            self.run_import()

    def test_wrong_loaded_version_hash_or_adapter_refused(self):
        original = deepcopy(self.loaded)
        for mod, field, value in (("minecraft", "version", "1.21.11"),
                                  ("minecraft", "origin_content_sha256", ["d" * 64]),
                                  ("fabricloader", "origin_sha256", ["d" * 64]),
                                  ("fabric-api", "version", "wrong"),
                                  ("patchouli", "origin_sha256", ["d" * 64]),
                                  ("mc-mod-lab-gametest", "origin_sha256", ["d" * 64])):
            with self.subTest(mod=mod, field=field):
                self.loaded.clear()
                self.loaded.update(deepcopy(original))
                self.loaded[mod][field] = value
                with self.assertRaises(contracts.ContractError):
                    self.run_import()

    def test_missing_duplicate_skipped_and_auxiliary_failure_refused(self):
        for xml in ('<testsuite/>', '<testsuite><testcase name="x" time="0"/><testcase name="x" time="0"/></testsuite>',
                    '<testsuite><failure message="bad"/></testsuite>'):
            self.xml.write_text(xml)
            with self.assertRaises(contracts.ContractError):
                self.run_import()
        self.write_xml('<skipped/>')
        with self.assertRaises(contracts.ContractError):
            self.run_import()
        self.write_xml(extra='<testcase name="extra" time="0"><failure/></testcase>')
        with self.assertRaises(contracts.ContractError):
            self.run_import()

    def test_xml_entities_nonfinite_and_malformed_refused(self):
        for xml in ('<!DOCTYPE x [<!ENTITY y "bad">]><testsuite/>', '<testsuite>',
                    '<testsuite><testcase name="x" time="NaN"/></testsuite>'):
            self.xml.write_text(xml)
            with self.assertRaises(contracts.ContractError):
                subject.read_xml(self.xml)

    def test_changed_xml_hash_refused(self):
        self.refresh()
        self.xml.write_text('<testsuite/>')
        with self.assertRaisesRegex(contracts.ContractError, "hash mismatch"):
            subject.import_run(self.root, self.adapter)

    def test_declared_xml_totals_must_match(self):
        self.write_xml()
        original = self.xml.read_text()
        for key, value in (("tests", "3"), ("failures", "1"), ("errors", "1"), ("skipped", "1")):
            self.xml.write_text(original.replace('<testsuite>', '<testsuite ' + key + '="' + value + '">', 1))
            with self.assertRaisesRegex(contracts.ContractError, "totals"):
                self.run_import()
        self.xml.write_text(original.replace('<testsuite>', '<testsuite tests="2" failures="0" errors="0" skipped="0">', 1))
        self.assertEqual(self.run_import()["status"], "pass")

    def test_fixture_disclosure_and_elapsed_bound_are_required(self):
        for disclosure in (None, "", "seeded final result"):
            self.observations["fixture_injection"] = disclosure
            with self.assertRaisesRegex(contracts.ContractError, "disclosure"):
                self.run_import()
        self.observations["fixture_injection"] = subject.FIXTURE_INJECTION
        for elapsed in (None, False, 0, -1, 181):
            self.lifecycle["elapsed_seconds"] = elapsed
            with self.assertRaisesRegex(contracts.ContractError, "duration"):
                self.run_import()

    def test_missing_tick_wrong_total_boolean_and_no_transfer_refused(self):
        originals = deepcopy(self.samples)
        variants = [originals[:-1], deepcopy(originals), deepcopy(originals), deepcopy(originals)]
        variants[1][40]["target"] += 1
        variants[2][0]["tick"] = False
        for s in variants[3]:
            s.update(source=1000, target=0)
        for variant in variants:
            self.observations["samples"] = variant
            with self.assertRaises(contracts.ContractError):
                self.run_import()

    def test_forced_cleanup_wrong_exit_or_memory_refused(self):
        original = deepcopy(self.lifecycle)
        for field, value in (("forced_cleanup", True), ("exit_code", 1), ("memory_samples", 0),
                             ("peak_private_mib", 3801), ("client_check", "pass")):
            self.lifecycle = {**original, field: value}
            with self.assertRaises(contracts.ContractError):
                self.run_import()

    def test_parity_cannot_promote_negative_or_client_visual(self):
        self.refresh()
        subject.export_run(self.root, self.adapter)
        parity = contracts.load(self.root / "parity.json")
        parity["deterministic_test"]["status"] = "fail"
        with self.assertRaises(contracts.ContractError):
            contracts.validate_parity(parity, self.root)

    def test_gametest_feature_cannot_bypass_import_with_unrelated_artifact(self):
        self.refresh()
        subject.export_run(self.root, self.adapter)
        parity = contracts.load(self.root / "parity.json")
        for name, content in (("unrelated.json", '{}'), ("array.json", '[]'),
                              ("wrong-kind.json", '{"kind":"synthetic"}'),
                              ("assertions.txt", "all tests pass")):
            with self.subTest(name=name):
                path = self.root / name
                path.write_text(content)
                parity["deterministic_test"]["artifact"] = {"file": name, "sha256": lab.sha256(path)}
                with self.assertRaisesRegex(contracts.ContractError, "typed GameTest"):
                    contracts.validate_parity(parity, self.root)
        parity["feature"] = "example.generic-deterministic"
        contracts.validate_parity(parity, self.root)


if __name__ == "__main__":
    unittest.main()
