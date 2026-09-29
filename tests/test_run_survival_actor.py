"""Offline launcher gates for the isolated Survival actor."""

from pathlib import Path
from types import SimpleNamespace
import gzip
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

import survival_actor
import runtime_profile
from tests.test_survival_seed import seed_bytes
from scripts import run_survival_actor as subject


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.aura = self.root / "Aura.java"
        self.aura.write_text("// probe", encoding="utf-8")
        self.profile = self.root / "profile"
        self.profile.mkdir()
        self.args = SimpleNamespace(manifest=self.root / "manifest.json", profile=self.profile,
                                    scenario=self.root / "scenario.json", model="vision:local",
                                    aura_source=self.aura)
        self.manifest = {"bridge_classification": "public_reviewed",
                         "expected_gamemode": "survival", "seed_save": str(self.root / "seed"),
                         "mods": [
                             {"role": "target", "mod_id": "aura", "mod_version": "0.2.1+1.21.1",
                              "sha256": subject.AURA_SHA256},
                             {"role": "bridge", "sha256": subject.MOVEMENT_PULSE_BRIDGE_SHA256}]}

    def valid_worlds(self):
        seed = self.root / "seed"
        copy = self.profile / "game" / "saves" / "w"
        seed.mkdir()
        copy.mkdir(parents=True)
        data = gzip.compress(seed_bytes())
        (seed / "level.dat").write_bytes(data)
        (copy / "level.dat").write_bytes(data)
        return seed, copy

    def test_seed_and_model_are_preflight_before_client_launch(self):
        _, copy = self.valid_worlds()
        profile = {"world_directory": "w", "fixture_sha256": runtime_profile._fixture_hash(copy)}
        with patch.object(subject.contracts, "load", side_effect=[self.manifest, profile]), \
             patch.object(subject.contracts, "schema_check"), \
             patch.object(subject.survival_actor, "OllamaVisionModel", return_value=Mock()) as model:
            self.assertIsNotNone(subject.preflight(self.args))
        model.assert_called_once_with("vision:local")
        with patch.object(subject, "preflight", side_effect=survival_actor.ActorError("not installed")), \
             patch.object(subject.runtime_launch, "launch") as launch, \
             patch("builtins.print"):
            self.assertEqual(subject.main(["--manifest", str(self.args.manifest),
                                           "--profile", str(self.args.profile),
                                           "--scenario", str(self.args.scenario),
                                           "--model", "vision:local",
                                           "--aura-source", str(self.aura)]), 2)
        launch.assert_not_called()

    def test_preflight_rejects_valid_but_different_copied_world(self):
        _, copy = self.valid_worlds()
        profile = {"world_directory": "w", "fixture_sha256": runtime_profile._fixture_hash(copy)}
        (copy / "level.dat").write_bytes(gzip.compress(seed_bytes(), mtime=1))
        with patch.object(subject.contracts, "load", side_effect=[self.manifest, profile]), \
             patch.object(subject.contracts, "schema_check"), \
             patch.object(subject.survival_actor, "OllamaVisionModel") as model:
            with self.assertRaises(subject.lab.LabError):
                subject.preflight(self.args)
        model.assert_not_called()

    def test_preflight_rejects_profile_hash_mismatch(self):
        self.valid_worlds()
        profile = {"world_directory": "w", "fixture_sha256": "0" * 64}
        with patch.object(subject.contracts, "load", side_effect=[self.manifest, profile]), \
             patch.object(subject.contracts, "schema_check"):
            with self.assertRaises(subject.lab.LabError):
                subject.preflight(self.args)

    def test_nonempty_authoritative_inventory_never_starts_actor(self):
        identity = {"world_path": str(self.root / "save"), "port": 9875}
        with patch.object(subject.lab, "sha256", return_value=subject.AURA_SHA256), \
             patch.object(subject.scenario_v2, "_scenario_observation", return_value=(None, {})), \
             patch.object(subject.scenario_v2, "_inventory_snapshot", return_value={
                 "complete": True, "server_authoritative": True, "stacks": [{"itemId": "minecraft:log"}],
                 "digest": "x"}), \
             patch.object(subject.survival_actor, "isolation_probe") as probe, \
             patch.object(subject.survival_actor, "run_actor") as actor:
            result = subject.trial(identity, self.root / "aura.jar", self.root, Mock(is_set=lambda: False),
                                   SimpleNamespace(name="vision:local"), self.aura)
        self.assertEqual(result["status"], "fail")
        probe.assert_not_called()
        actor.assert_not_called()

    def test_actor_failure_retains_release_and_first_frame_hash(self):
        import hashlib
        identity = {"pid": 5, "world_path": str(self.root / "save"), "port": 9875}
        source_hash = survival_actor.actor_source_hash()
        session = MagicMock()
        session.__enter__.return_value = session
        session.cleanup_status = "pass"

        def fail_actor(*args, **kwargs):
            kwargs["first_frame"](b"frame")
            kwargs["trace_out"].append({"at_utc": 1.0, "action": {"type": "cancel"}})
            raise survival_actor.ActorError("expected failure")

        with patch.object(subject.lab, "sha256", return_value=subject.AURA_SHA256), \
             patch.object(subject.lab, "listening_socket"), \
             patch.object(subject.scenario_v2, "_scenario_observation", return_value=(None, {})), \
             patch.object(subject.scenario_v2, "_inventory_snapshot", return_value={
                 "complete": True, "server_authoritative": True, "stacks": [], "digest": "x"}), \
             patch.object(subject.survival_actor, "isolation_probe", return_value={
                 "status": "pass", "actor_source_sha256": source_hash}), \
             patch.object(subject.survival_actor, "broker_probe", return_value={"status": "pass"}), \
             patch.object(subject.survival_actor, "run_actor", side_effect=fail_actor), \
             patch.object(subject, "PolicySession", return_value=session):
            result = subject.trial(identity, self.root / "aura.jar", self.root,
                                   Mock(is_set=lambda: False),
                                   SimpleNamespace(name="vision:local"), self.aura)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["neutral_release"], "pass")
        self.assertEqual(result["first_frame_sha256"], hashlib.sha256(b"frame").hexdigest())
        self.assertEqual(len(result["action_trace"]), 1)

    def test_later_guide_candidate_is_evaluator_only_and_hash_bound(self):
        import hashlib
        report = {"guide_frame": {"status": "not_observed", "probe_count": 0}}
        capture = subject.guide_frame_capture({"pid": 5, "port": 9875}, self.root, report)
        with patch.object(subject.lab, "command", side_effect=[
                {"screen": "InventoryScreen"}, {"screen": "GuiBookLanding"},
                {"screen": "GuiBookLanding"}, {"screen": "GuiBookLanding"}]) as command:
            self.assertEqual(capture(lambda: b"not-yet"), b"not-yet")
            self.assertEqual(report["guide_frame"]["status"], "not_observed")
            self.assertEqual(capture(lambda: b"guide-pixels"), b"guide-pixels")
        self.assertEqual(command.call_count, 4)
        self.assertEqual((self.root / "guide-open.png").read_bytes(), b"guide-pixels")
        self.assertEqual(report["guide_frame"]["sha256"],
                         hashlib.sha256(b"guide-pixels").hexdigest())
        self.assertEqual(report["guide_frame"]["probe_count"], 2)
        self.assertEqual(report["guide_frame"]["visual_status"], "not_reviewed")
        with patch.object(subject.lab, "command") as command:
            self.assertEqual(capture(lambda: b"later"), b"later")
        command.assert_not_called()

    def test_guide_capture_remains_active_after_ordinary_gui_frames(self):
        report = {"guide_frame": {"status": "not_observed", "probe_count": 0}}
        capture = subject.guide_frame_capture({"pid": 5, "port": 9875}, self.root, report)
        with patch.object(subject.lab, "command", return_value={"screen": None}) as command:
            for _ in range(20):
                self.assertEqual(capture(lambda: b"world"), b"world")
        self.assertEqual(command.call_count, 40)
        self.assertEqual(report["guide_frame"]["status"], "not_observed")
        with patch.object(subject.lab, "command", return_value={"screen": "GuiBookLanding"}):
            self.assertEqual(capture(lambda: b"later-guide"), b"later-guide")
        self.assertEqual(report["guide_frame"]["status"], "candidate")
        self.assertEqual(report["guide_frame"]["probe_count"], 21)
        self.assertEqual(report["guide_frame"]["visual_status"], "not_reviewed")
        self.assertEqual((self.root / "guide-open.png").read_bytes(), b"later-guide")
        with patch.object(subject.lab, "command") as command:
            self.assertEqual(capture(lambda: b"after-candidate"), b"after-candidate")
        command.assert_not_called()

    def test_guide_probe_malformed_screen_fails_closed(self):
        report = {"guide_frame": {"status": "not_observed", "probe_count": 0}}
        capture = subject.guide_frame_capture({"pid": 5, "port": 9875}, self.root, report)
        with patch.object(subject.lab, "command", return_value={"buttons": []}):
            with self.assertRaises(subject.lab.LabError):
                capture(lambda: b"world")


if __name__ == "__main__":
    unittest.main()
