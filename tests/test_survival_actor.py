"""Offline isolation and broker controls; never starts Minecraft."""

import base64
from pathlib import Path
import shutil
import socket
import threading
import unittest
from unittest.mock import Mock, patch

import survival_actor as subject


PNG = b"\x89PNG\r\n\x1a\nmock-pixels"


class SurvivalActorTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.session._expected_frame = (1280, 720)
        self.session.frame.return_value = PNG
        self.session.close.return_value = True
        self.model = Mock()
        self.model.choose.return_value = {"type": "look", "yaw_delta": 2, "pitch_delta": 0}
        self.broker = subject.ActorBroker(self.session, self.model)

    def test_forbidden_requests_and_action_substitution_never_dispatch(self):
        for request in ({"op": "observe", "name": "chunk_presence"},
                        {"op": "execute_command", "command": "say denied"},
                        {"op": "pulse", "key": "forward", "milliseconds": True}):
            self.assertEqual(self.broker.handle(request), {"accepted": False})
        self.session.assert_not_called()
        self.assertEqual(self.broker.handle({"op": "frame"}),
                         {"png": base64.b64encode(PNG).decode("ascii")})
        self.assertEqual(self.broker.handle({"op": "vision"}),
                         {"action": self.model.choose.return_value})
        for request in ({"op": "look", "yaw_delta": 3, "pitch_delta": 0},
                        {"op": "observe", "type": "look", "yaw_delta": 2, "pitch_delta": 0},
                        {"op": "look", "yaw_delta": 2, "pitch_delta": 0, "secret": True}):
            self.assertEqual(self.broker.handle(request), {"accepted": False})
        self.session.input.assert_not_called()
        self.assertEqual(self.broker.handle({"op": "look", "yaw_delta": 2, "pitch_delta": 0}),
                         {"accepted": True})
        self.session.input.assert_called_once_with(self.model.choose.return_value)
        self.assertEqual(self.broker.handle({"op": "look", "yaw_delta": 2, "pitch_delta": 0}),
                         {"accepted": False})

    def test_cancel_is_terminal_and_neutral(self):
        self.model.choose.return_value = {"type": "cancel"}
        self.broker.handle({"op": "frame"})
        self.broker.handle({"op": "vision"})
        self.assertEqual(self.broker.handle({"op": "cancel"}), {"accepted": True})
        self.session.cancel.assert_called_once()
        self.assertEqual(self.broker.handle({"op": "frame"}), {"accepted": False})

    def test_guide_capture_uses_only_actor_requested_frame_after_gui_action(self):
        self.model.choose.return_value = {"type": "pulse", "key": "use", "milliseconds": 100}
        capture = Mock(side_effect=lambda frame: frame())
        broker = subject.ActorBroker(self.session, self.model, guide_capture=capture)
        self.assertEqual(broker.handle({"op": "frame"}),
                         {"png": base64.b64encode(PNG).decode("ascii")})
        capture.assert_not_called()
        broker.handle({"op": "vision"})
        broker.handle({"op": "pulse", "key": "use", "milliseconds": 100})
        self.assertEqual(broker.handle({"op": "frame"}),
                         {"png": base64.b64encode(PNG).decode("ascii")})
        capture.assert_called_once()
        self.assertEqual(broker.history, [{"type": "pulse", "key": "use", "milliseconds": 100}])
        broker.handle({"op": "vision"})
        self.model.choose.assert_called_with(PNG, broker.history, (1280, 720))

    def test_broker_rejects_malformed_model_actions(self):
        for action in ({"type": "cancel", "extra": True},
                       {"type": "pulse", "key": "forward", "milliseconds": True},
                       {"type": "execute_command"}):
            with self.subTest(action=action):
                broker = subject.ActorBroker(self.session, self.model)
                self.model.choose.return_value = action
                broker.handle({"op": "frame"})
                with self.assertRaises(subject.ActorError):
                    broker.handle({"op": "vision"})
        self.session.input.assert_not_called()
        self.session.cancel.assert_not_called()

    def test_late_cancel_before_dispatch_denies_action(self):
        stopped = Mock(side_effect=[False, False, False, True])
        broker = subject.ActorBroker(self.session, self.model, stopped=stopped)
        self.model.choose.return_value = {"type": "look", "yaw_delta": 2, "pitch_delta": 0}
        broker.handle({"op": "frame"})
        broker.handle({"op": "vision"})
        with self.assertRaises(subject.ActorError):
            broker.handle({"op": "look", "yaw_delta": 2, "pitch_delta": 0})
        self.session.input.assert_not_called()

    def test_probe_refuses_missing_host_evidence_before_child(self):
        with patch.object(subject, "sandbox_command") as child:
            with self.assertRaises(subject.ActorError):
                subject.isolation_probe([Path(__file__).parent / "missing-level.dat"], 9)
        child.assert_not_called()

    def test_sandbox_command_drops_capabilities(self):
        with patch.object(subject, "_wslpath", return_value="/mnt/f/actor.py"):
            command = subject.sandbox_command("act")
        self.assertIn("--unshare-all", command)
        self.assertIn("--new-session", command)
        self.assertEqual(command[command.index("--cap-drop") + 1], "ALL")

    def test_model_preflight_requires_installed_vision_capability(self):
        with patch.object(subject, "_http_json", side_effect=[{"models": [{"name": "vision:local"}]},
                                                          {"capabilities": ["vision"]}]):
            self.assertEqual(subject.OllamaVisionModel("vision:local").name, "vision:local")
        with patch.object(subject, "_http_json", return_value={"models": []}):
            with self.assertRaises(subject.ActorError):
                subject.OllamaVisionModel("absent")
        with patch.object(subject, "_http_json", side_effect=[{"models": [{"name": "embed"}]},
                                                          {"capabilities": ["embedding"]}]):
            with self.assertRaises(subject.ActorError):
                subject.OllamaVisionModel("embed")

    def test_model_retains_only_first_and_current_pixels_and_rejects_tools(self):
        with patch.object(subject, "_http_json", side_effect=[{"models": [{"name": "vision:local"}]},
                                                          {"capabilities": ["vision"]},
                                                          {"message": {"content": '{"type":"cancel"}'}},
                                                          {"message": {"content": '{"type":"cancel"}'}}]) as api:
            model = subject.OllamaVisionModel("vision:local")
            model.choose(PNG, [], (1280, 720))
            model.choose(PNG + b"next", [{"type": "look", "yaw_delta": 1, "pitch_delta": 0}],
                         (1280, 720))
        self.assertEqual(len(api.call_args_list[2].args[2]["messages"][0]["images"]), 1)
        self.assertEqual(len(api.call_args_list[3].args[2]["messages"][0]["images"]), 2)
        with patch.object(subject, "_http_json", return_value={"message": {
                "content": '{"type":"execute_command"}', "tool_calls": [{"name": "shell"}]}}):
            with self.assertRaises(subject.ActorError):
                model.choose(PNG, [], (1280, 720))
        with patch.object(subject, "_http_json", return_value={"message": {
                "content": '{"type":"execute_command"}'}}):
            with self.assertRaises(subject.ActorError):
                model.choose(PNG, [], (1280, 720))
        with patch.object(subject, "_http_json", return_value={"message": []}):
            with self.assertRaises(subject.ActorError):
                model.choose(PNG, [], (1280, 720))

    @unittest.skipUnless(shutil.which("wsl"), "WSL Ubuntu sandbox unavailable")
    def test_real_sandbox_denies_source_token_and_network(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            with patch.dict("os.environ", {"MC_MOD_LAB_TOKEN": "test-only"}):
                result = subject.isolation_probe([Path(subject.__file__),
                                                  Path(subject.__file__).parent / ".git" / "HEAD"],
                                                 listener.getsockname()[1])
        self.assertEqual(result["status"], "pass")

    @unittest.skipUnless(shutil.which("wsl"), "WSL Ubuntu sandbox unavailable")
    def test_real_child_exchanges_only_png_action_and_ack(self):
        self.model.choose.side_effect = [{"type": "look", "yaw_delta": 2, "pitch_delta": 0},
                                         {"type": "cancel"}]
        self.assertEqual(subject.broker_probe(self.session, self.model)["status"], "pass")
        self.session.input.assert_not_called()
        result = subject.run_actor(self.session, self.model, threading.Event(), wall_seconds=20)
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(result["actor_actions"], 2)
        self.session.input.assert_called_once_with({"type": "look", "yaw_delta": 2, "pitch_delta": 0})
        self.session.cancel.assert_called_once()
        self.session.close.assert_called_once()

    @unittest.skipUnless(shutil.which("wsl"), "WSL Ubuntu sandbox unavailable")
    def test_deadline_ends_child_before_new_input(self):
        cancel = threading.Event()
        with self.assertRaises(subject.ActorError):
            subject.run_actor(self.session, self.model, cancel, wall_seconds=0.01)
        self.assertTrue(cancel.is_set())
        self.session.input.assert_not_called()
        self.session.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
