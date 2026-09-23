import copy
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys

import contracts
import lab
from example_replay import replay_example


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "evidence"
        self.result = replay_example(self.root)

    def test_replay_detects_regression_and_keeps_live_dimensions_unrun(self):
        self.assertEqual(self.result["baseline"], "fail")
        self.assertEqual(self.result["corrected"], "captured")
        for case in ("baseline", "corrected"):
            result = contracts.validate_file(self.root / case / "report.json", "report", portable=True)
            self.assertEqual(result["evidence_kind"], "synthetic")
        result = contracts.validate_file(self.root / "parity.json", "parity", portable=True)
        self.assertEqual(result["dimensions"], {"deterministic_test": "pass", "client_check": "not_run", "visual_check": "not_run"})

    def test_tampered_artifact_rejected(self):
        (self.root / "corrected" / "after.png").write_bytes(b"tampered")
        with self.assertRaisesRegex(contracts.ContractError, "hash mismatch"):
            contracts.validate_file(self.root / "corrected" / "report.json", "report")

    def test_traversal_and_absolute_artifacts_rejected(self):
        value = contracts.load(self.root / "parity.json")
        for name in ("../assertions.txt", "/assertions.txt", "C:/assertions.txt", "..\\assertions.txt"):
            with self.subTest(name=name):
                value["deterministic_test"]["artifact"]["file"] = name
                with self.assertRaises(contracts.ContractError):
                    contracts.validate_parity(value, self.root)

    def test_synthetic_report_cannot_back_live_pass(self):
        value = contracts.load(self.root / "parity.json")
        path = self.root / "corrected" / "report.json"
        value["client_check"] = {"status": "pass", "checked_at": lab.now(), "reviewer": None,
                                  "artifact": {"file": "corrected/report.json", "sha256": lab.sha256(path)}}
        with self.assertRaisesRegex(contracts.ContractError, "matching live evidence"):
            contracts.validate_parity(value, self.root)

    def test_pass_cannot_hide_failed_client_report(self):
        report_path = self.root / "baseline" / "report.json"
        report = contracts.load(report_path)
        report["evidence_kind"] = "live"
        lab.write_json(report_path, report)
        value = contracts.load(self.root / "parity.json")
        value["client_check"] = {"status": "pass", "checked_at": lab.now(), "reviewer": None,
                                  "artifact": {"file": "baseline/report.json", "sha256": lab.sha256(report_path)}}
        with self.assertRaisesRegex(contracts.ContractError, "matching live evidence"):
            contracts.validate_parity(value, self.root)
        value["client_check"]["status"] = "fail"
        result = contracts.validate_parity(value, self.root)
        self.assertEqual(result["dimensions"]["client_check"], "fail")
        self.assertEqual(result["dimensions"]["deterministic_test"], "pass")

    def test_false_capture_and_visual_promotion_rejected(self):
        value = contracts.load(self.root / "corrected" / "report.json")
        changed = copy.deepcopy(value)
        changed["after"]["screen_class"] = None
        with self.assertRaisesRegex(contracts.ContractError, "contradicts"):
            contracts.validate_report(changed, self.root / "corrected")
        value["visual_check"] = "pass"
        with self.assertRaises(contracts.ContractError):
            contracts.validate_report(value, self.root / "corrected")

    def test_dates_and_visual_reviewer_required(self):
        value = contracts.load(self.root / "parity.json")
        value["visual_check"] = copy.deepcopy(value["deterministic_test"])
        with self.assertRaisesRegex(contracts.ContractError, "reviewer"):
            contracts.validate_parity(value, self.root)
        value["visual_check"]["reviewer"] = "Independent reviewer"
        value["reference"]["observed_at"] = "yesterday"
        with self.assertRaises(contracts.ContractError):
            contracts.validate_parity(value, self.root)

    def test_local_fields_and_paths_rejected_for_portable_evidence(self):
        for value in ({"token": "hidden"}, {"world_path": "hidden"}, {"reason": "C:/Users/example/save"}):
            with self.assertRaises(contracts.ContractError):
                contracts.portable_check(value)

    def test_duplicate_json_key_rejected(self):
        path = self.root / "duplicate.json"
        path.write_text('{"status":"fail","status":"captured"}', encoding="utf-8")
        with self.assertRaises(contracts.ContractError):
            contracts.load(path)

    def test_identity_template_has_all_required_fields(self):
        template = contracts.load(Path(lab.__file__).parent / "examples" / "identity.example.json")
        self.assertFalse(set(lab.IDENTITY_REQUIRED) - set(template))
        self.assertEqual(template["port"], 9876)

    def test_replay_refuses_existing_output(self):
        with self.assertRaises(FileExistsError):
            replay_example(self.root)

    def test_cli_and_replay_are_reproducible_from_another_directory(self):
        script = Path(lab.__file__).resolve()
        other = self.root.parent / "other"
        run = subprocess.run([sys.executable, str(script), "replay", "--out", str(other)],
                             cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout)
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertEqual(path.read_bytes(), (other / path.relative_to(self.root)).read_bytes())
        run = subprocess.run([sys.executable, str(script), "validate", "parity", str(other / "parity.json"), "--portable"],
                             cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout)

    def test_live_capture_refuses_old_artifacts_without_touching_them(self):
        with self.assertRaises(lab.LabError):
            lab.capture(Path("missing"), Path("missing"), self.root)
        self.assertTrue((self.root / "corrected" / "after.png").is_file())


if __name__ == "__main__":
    unittest.main()
