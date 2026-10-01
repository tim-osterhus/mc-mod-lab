"""Offline policy-boundary tests; no Minecraft or actor is started."""

from io import BytesIO
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

import contracts
import lab
import survival_input as subject


class SurvivalInputTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.identity = {"expected_gamemode": "survival", "pid": 123, "port": 456,
                         "game_dir": "private-game"}
        self.lease = Mock()
        self.lease.release.return_value = {"status": "pass"}
        for name in ("status_check", "world_check", "player_check"):
            self.addCleanup(patch.stopall)
            patch.object(subject.lab, name).start()
        patch.object(subject.scenario_v2, "ControlLease", return_value=self.lease).start()
        patch.object(subject.time, "monotonic", side_effect=lambda: self.now).start()
        patch.object(subject.time, "sleep", side_effect=lambda seconds: setattr(self, "now", self.now + seconds)).start()
        image = Image.new("RGB", (640, 360), "red")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        self.png = buffer.getvalue()

    def session(self):
        session = subject.PolicySession(self.identity, (640, 360))
        session.start()
        return session

    def test_frame_returns_only_png_and_enforces_rate(self):
        session = self.session()
        with patch.object(subject, "_request_png", return_value=(self.png, 640, 360)):
            self.assertEqual(session.frame(), self.png)
            with self.assertRaises(subject.PolicyError):
                session.frame()
            self.now += 0.5
            self.assertEqual(session.frame(), self.png)
        self.assertTrue(session.close())
        self.lease.release.assert_called_once()

    def test_default_duration_remains_ten_minutes(self):
        session = self.session()
        self.assertEqual(session._deadline, self.now + 600)
        session.close()

    def test_trusted_duration_is_fixed_and_expires_at_exact_bound(self):
        session = subject.PolicySession(self.identity, (640, 360), wall_seconds=1800)
        session.start()
        self.now += 600
        session._ready()
        self.now += 1200
        with self.assertRaisesRegex(subject.PolicyError, "deadline reached"):
            session._ready()
        self.assertEqual(session.cleanup_status, "pass")
        self.lease.release.assert_called_once()

    def test_invalid_duration_rejected_before_acquiring_control(self):
        for value in (True, False, 0, -1, 1801, 600.0, "600", None):
            with self.subTest(value=value), self.assertRaises(subject.PolicyError):
                subject.PolicySession(self.identity, (640, 360), wall_seconds=value)
        self.lease.enter.assert_not_called()

    def test_actor_cannot_change_duration(self):
        session = self.session()
        deadline = session._deadline
        with patch.object(session, "_action") as action:
            with self.assertRaises(subject.PolicyError):
                session.input({"type": "look", "yaw_delta": 1, "pitch_delta": 0, "wall_seconds": 1800})
            action.assert_not_called()
        self.assertEqual(session._deadline, deadline)
        session.close()

    def test_visible_requests_are_fixed_and_strict(self):
        session = self.session()
        with patch.object(session, "_action") as action, patch.object(subject.lab, "command", return_value={}):
            self.assertEqual(session.input({"type": "look", "yaw_delta": 10, "pitch_delta": -4}),
                             {"accepted": True})
            action.assert_called_with("visible_look", {"yaw_delta": 10, "pitch_delta": -4})
            self.now += 0.11
            self.assertEqual(session.input({"type": "pulse", "key": "forward", "milliseconds": 100}),
                             {"accepted": True})
            self.assertEqual(action.call_args_list[-1].args,
                             ("visible_pulse", {"key": "forward", "milliseconds": 100}))
            self.now += 0.11
            self.assertEqual(session.input({"type": "pulse", "key": "attack", "milliseconds": 5000}),
                             {"accepted": True})
            self.assertEqual(action.call_args_list[-2].args,
                             ("visible_key", {"key": "attack", "pressed": True}))
            self.assertEqual(action.call_args_list[-1].args,
                             ("visible_key", {"key": "attack", "pressed": False}))
            self.now += 0.11
            self.assertEqual(session.input({"type": "press", "key": "E"}), {"accepted": True})
            subject.lab.command.assert_called_with(self.identity, "press_key", {"key": "E"})
            self.now += 0.11
            self.assertEqual(session.input({"type": "press", "key": "Q"}), {"accepted": True})
            self.now += 0.11
            self.assertEqual(session.input({"type": "press", "key": "9"}), {"accepted": True})
        session.close()

    def test_hidden_actions_and_malformed_values_never_dispatch(self):
        session = self.session()
        bad = ({"type": "look", "yaw_delta": True, "pitch_delta": 0},
               {"type": "look", "yaw_delta": 0.5, "pitch_delta": 0},
               {"type": "look", "yaw_delta": 0, "pitch_delta": 0},
               {"type": "pulse", "key": ["forward"], "milliseconds": 100},
               {"type": "pulse", "key": "forward", "milliseconds": 501},
               {"type": "pulse", "key": "use", "milliseconds": 501},
               {"type": "pulse", "key": "attack", "milliseconds": 5001},
               {"type": "pulse", "key": "attack", "milliseconds": True},
               {"type": "pulse", "key": "attack", "milliseconds": 500.0},
               {"type": "press", "key": "T"},
               {"type": "press", "key": ["E"]},
               {"type": "look", "yaw_delta": 1, "pitch_delta": 0, "x": 12},
               {"type": "block_entity_inventory", "x": 0, "y": 64, "z": 0},
               {"type": "click", "x": 0, "y": 0})
        with patch.object(session, "_action") as action, patch.object(subject.lab, "command") as command:
            for request in bad:
                with self.subTest(request=request), self.assertRaises(subject.PolicyError):
                    session.input(request)
                self.now += 0.11
            action.assert_not_called()
            command.assert_not_called()
        self.assertEqual(session._inputs, len(bad))
        session.close()

    def test_click_requires_recent_full_frame_bounds(self):
        session = self.session()
        with patch.object(subject, "_request_png", return_value=(self.png, 640, 360)), \
                patch.object(subject.lab, "command", return_value={"clicked": True}) as command:
            session.frame()
            self.assertEqual(session.input({"type": "click", "x": 639, "y": 359}), {"accepted": True})
            command.assert_called_with(self.identity, "click", {"x": 639, "y": 359})
            self.now += 0.11
            with self.assertRaises(subject.PolicyError):
                session.input({"type": "click", "x": 640, "y": 0})
            self.now += 0.11
            with self.assertRaises(subject.PolicyError):
                session.input({"type": "click", "x": False, "y": 0})
            self.now += 2.1
            with self.assertRaisesRegex(subject.PolicyError, "stale"):
                session.input({"type": "click", "x": 100, "y": 100})
        session.close()

    def test_failed_attack_pulse_releases_key_and_terminates(self):
        session = self.session()
        with patch.object(session, "_action") as action, patch.object(subject.time, "sleep", side_effect=ValueError("interrupted")):
            with self.assertRaises(subject.PolicyError):
                session.input({"type": "pulse", "key": "attack", "milliseconds": 50})
            self.assertEqual(action.call_count, 2)
            self.assertEqual(action.call_args_list[-1].args,
                             ("visible_key", {"key": "attack", "pressed": False}))
        self.assertEqual(session.cleanup_status, "pass")
        self.lease.release.assert_called_once()
        with self.assertRaises(subject.PolicyError):
            session.input({"type": "look", "yaw_delta": 1, "pitch_delta": 0})

    def test_failed_action_or_deadline_closes_session(self):
        session = self.session()
        with patch.object(session, "_action", side_effect=lab.LabError("private path", "fail")):
            with self.assertRaisesRegex(subject.PolicyError, "client must close") as raised:
                session.input({"type": "look", "yaw_delta": 1, "pitch_delta": 0})
        self.assertNotIn("private path", str(raised.exception))
        self.lease.release.assert_called_once()
        expired = self.session()
        self.now += subject.MAX_WALL_SECONDS
        with self.assertRaises(subject.PolicyError):
            expired.frame()
        self.assertEqual(expired.cleanup_status, "pass")

    def test_movement_pulse_is_one_client_timed_request(self):
        session = self.session()
        with patch.object(session, "_action") as action, patch.object(subject.time, "sleep") as sleep:
            self.assertEqual(session.input({"type": "pulse", "key": "forward", "milliseconds": 100}),
                             {"accepted": True})
        action.assert_called_once_with("visible_pulse", {"key": "forward", "milliseconds": 100})
        sleep.assert_not_called()
        session.close()

    def test_unexpected_dispatch_failure_closes_and_sanitizes(self):
        session = self.session()
        with patch.object(session, "_action", side_effect=RuntimeError("private token")):
            with self.assertRaisesRegex(subject.PolicyError, "client must close") as raised:
                session.input({"type": "look", "yaw_delta": 1, "pitch_delta": 0})
        self.assertNotIn("private token", str(raised.exception))
        self.lease.release.assert_called_once()

    def test_failed_start_release_reports_client_close(self):
        self.lease.enter.side_effect = lab.LabError("private path", "fail")
        self.lease.release.return_value = {"status": "fail"}
        with self.assertRaisesRegex(subject.PolicyError, "client must close") as raised:
            self.session()
        self.assertNotIn("private path", str(raised.exception))

    def test_invalid_png_closes_and_cannot_be_actor_evidence(self):
        session = self.session()
        with patch.object(subject, "_request_png", return_value=(self.png, 641, 360)):
            with self.assertRaises(subject.PolicyError):
                session.frame()
        self.assertEqual(session.cleanup_status, "pass")
        for png in (b"not-png", b"x" * (subject.MAX_PNG_BYTES + 1)):
            with self.assertRaises(subject.PolicyError):
                subject._pixels(png, None, None)
        with self.assertRaises(subject.PolicyError):
            subject._pixels(self.png, 640.0, 360)
        cropped = subject.PolicySession(self.identity, (1280, 720))
        cropped.start()
        with patch.object(subject, "_request_png", return_value=(self.png, 640, 360)):
            with self.assertRaises(subject.PolicyError):
                cropped.frame()

    def test_failed_frame_release_requires_client_close(self):
        self.lease.release.return_value = {"status": "fail"}
        session = self.session()
        with patch.object(subject, "_request_png", return_value=(b"not-png", 640, 360)):
            with self.assertRaisesRegex(subject.PolicyError, "client must close"):
                session.frame()
        self.assertEqual(session.cleanup_status, "fail")

    def test_cancel_and_failed_release_are_terminal(self):
        session = self.session()
        self.assertEqual(session.cancel(), {"input_released": True})
        with self.assertRaises(subject.PolicyError):
            session.frame()
        self.lease.release.return_value = {"status": "fail"}
        failed = self.session()
        with self.assertRaisesRegex(subject.PolicyError, "release failed"):
            failed.cancel()
        self.assertEqual(failed.cleanup_status, "fail")

    def test_attempt_and_frame_hard_caps_close(self):
        session = self.session()
        session._inputs = subject.MAX_INPUTS
        with self.assertRaisesRegex(subject.PolicyError, "exhausted"):
            session.input({"type": "look", "yaw_delta": 1, "pitch_delta": 0})
        self.assertEqual(session.cleanup_status, "pass")
        frames = self.session()
        frames._frames = subject.MAX_FRAMES
        with self.assertRaisesRegex(subject.PolicyError, "exhausted"):
            frames.frame()
        self.assertEqual(frames.cleanup_status, "pass")

    def test_not_survival_and_scripted_scenario_policy_action_rejected(self):
        self.identity["expected_gamemode"] = "creative"
        with self.assertRaises(subject.PolicyError):
            subject.PolicySession(self.identity, (640, 360)).start()
        for size in ((640.0, 360), (True, 360), (320, 180)):
            with self.assertRaises(subject.PolicyError):
                subject.PolicySession(self.identity, size)
        scenario = contracts.load("examples/scenario-v2.json")
        scenario["steps"][0] = {"id": "policy-command", "action": {"type": "visible_look",
                                                              "yaw_delta": 1, "pitch_delta": 0}}
        with self.assertRaises(contracts.ContractError):
            contracts.validate_scenario_v2(scenario)

    def test_bridge_release_is_allowed_after_use_opens_a_screen(self):
        source = (Path(__file__).resolve().parents[1] / "bridge-src" / "ScenarioActions.java").read_text(
            encoding="utf-8")
        method = source.split("public static ActionAck visibleKey", 1)[1].split(
            "public static ActionAck visiblePulse", 1)[0]
        self.assertIn("if (pressed && client.field_1755 != null)", method)
        self.assertIn("binding.method_23481(pressed);", method)
        self.assertNotIn("if (client.field_1755 != null)", method)

    def test_attack_has_one_vanilla_click_edge_and_cancel_drains_it(self):
        source = (Path(__file__).resolve().parents[1] / "bridge-src" / "ScenarioActions.java").read_text(
            encoding="utf-8")
        method = source.split("public static ActionAck visibleKey", 1)[1].split(
            "public static ActionAck visiblePulse", 1)[0]
        release = source.split("public static void releaseHeldInputs", 1)[1]
        self.assertIn('attackEdge = !visibleAttackRequested;', method)
        self.assertIn("class_304.method_1420(class_3675.method_15981(binding.method_1428()))", method)
        self.assertIn('if (!pressed && "attack".equals(key))', method)
        self.assertIn("while (binding.method_1436()) { }", method)
        self.assertIn("while (client.field_1690.field_1886.method_1436()) { }", release)
        self.assertNotIn('"use".equals(key)', method)


if __name__ == "__main__":
    unittest.main()
