"""Offline controls for the attach-only technical smoke; no client is launched."""

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import lab
from scripts import smoke_survival_input as subject
from survival_input import PolicyError


class SmokeSurvivalInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.identity = {"pid": 123}

    def test_prepare_releases_acquired_lease_on_failed_enter(self):
        args = SimpleNamespace(identity=self.root / "identity.json", artifact=self.root / "aura.jar",
                               out=self.root / "prepare", x=2, y=64, z=0, block="minecraft:chest")
        lease = MagicMock(acquired=True)
        lease.enter.side_effect = lab.LabError("enter failed")
        lease.release.return_value = {"status": "pass"}
        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject.scenario_v2, "ControlLease", return_value=lease):
            with self.assertRaises(lab.LabError):
                subject.prepare(args)
        lease.release.assert_called_once()

    def test_glass_prepare_requires_empty_hand_and_exact_crosshair(self):
        args = SimpleNamespace(identity=self.root / "identity.json", artifact=self.root / "aura.jar",
                               out=self.root / "prepare", x=3, y=161, z=1,
                               block="minecraft:glass")
        lease = MagicMock(acquired=True)
        lease.release.return_value = {"status": "pass"}
        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject.scenario_v2, "ControlLease", return_value=lease), \
                patch.object(subject.scenario_v2, "label_capture_window",
                             return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject.scenario_v2, "scenario_request") as request, \
                patch.object(subject.lab, "command", return_value={"screen": None}), \
                patch.object(subject.lab, "screenshot", return_value={"width": 1280,
                                                                       "height": 720}), \
                patch.object(subject, "verify_window", return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject.time, "sleep"):
            report = subject.prepare(args)
        self.assertTrue(report["crosshair_verified"])
        self.assertEqual([call.args[2] for call in request.call_args_list],
                         ["aim_at_block", "select_hotbar", "use_item_at_block"])
        self.assertEqual(request.call_args_list[1].args[3],
                         {"slot": 8, "item_id": "minecraft:air"})
        self.assertEqual(request.call_args_list[2].args[3],
                         {"x": 3, "y": 161, "z": 1, "block_id": "minecraft:glass"})
        lease.release.assert_called_once()

    def test_glass_prepare_rejects_crosshair_mismatch(self):
        args = SimpleNamespace(identity=self.root / "identity.json", artifact=self.root / "aura.jar",
                               out=self.root / "prepare", x=3, y=161, z=1,
                               block="minecraft:glass")
        lease = MagicMock(acquired=True)
        lease.release.return_value = {"status": "pass"}
        def action(_identity, _kind, name, _params):
            if name == "use_item_at_block":
                raise lab.LabError("current block hit does not match fixture", "fail")
        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject.scenario_v2, "ControlLease", return_value=lease), \
                patch.object(subject.scenario_v2, "label_capture_window",
                             return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject.scenario_v2, "scenario_request", side_effect=action), \
                patch.object(subject.time, "sleep"):
            with self.assertRaisesRegex(lab.LabError, "block hit"):
                subject.prepare(args)
        lease.release.assert_called_once()

    def test_log_prepare_requires_empty_hand_and_exact_crosshair(self):
        args = SimpleNamespace(identity=self.root / "identity.json", artifact=self.root / "aura.jar",
                               out=self.root / "prepare", x=2, y=161, z=2,
                               block="minecraft:oak_log")
        lease = MagicMock(acquired=True)
        lease.release.return_value = {"status": "pass"}
        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject.scenario_v2, "ControlLease", return_value=lease), \
                patch.object(subject.scenario_v2, "label_capture_window",
                             return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject.scenario_v2, "scenario_request") as request, \
                patch.object(subject.lab, "command", return_value={"screen": None}), \
                patch.object(subject.lab, "screenshot", return_value={"width": 1280,
                                                                       "height": 720}), \
                patch.object(subject, "verify_window", return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject.time, "sleep"):
            report = subject.prepare(args)
        self.assertTrue(report["crosshair_verified"])
        self.assertEqual([call.args[2] for call in request.call_args_list],
                         ["aim_at_block", "select_hotbar", "use_item_at_block"])

    def test_placed_log_count_requires_complete_authoritative_inventory(self):
        stack = {"itemId": "minecraft:oak_log", "componentSetSha256": "a" * 64,
                 "count": 1, "itemIdTruncated": False, "componentsTruncated": False,
                 "componentBasis": "patch_against_pinned_registry_defaults",
                 "componentDigestStatus": "COMPLETE"}
        inventory = {"stacks": [stack], "truncated": False,
                     "serverAuthoritative": True,
                     "stateSource": "integrated_server_inventory"}
        self.assertEqual(subject.log_count(inventory)[0], 1)
        inventory["serverAuthoritative"] = False
        with self.assertRaisesRegex(lab.LabError, "server-authoritative"):
            subject.log_count(inventory)

    def test_collection_requires_exact_ground_item_and_platform_position(self):
        dropped = {"entity_id": "minecraft:item", "item_components_complete": True,
                   "item": {"item_id": "minecraft:oak_log", "count": 1}}
        ground = {"entities": [dropped], "player_position": {"x": 0, "y": 161, "z": 0}}
        self.assertEqual(subject.ground_log_count(ground), 1)
        self.assertEqual(subject.require_collection_platform(ground), ground["player_position"])
        with self.assertRaisesRegex(lab.LabError, "incomplete"):
            subject.ground_log_count({**ground, "entities": [{**dropped,
                                                              "item_components_complete": False}]})
        with self.assertRaisesRegex(lab.LabError, "left"):
            subject.require_collection_platform({**ground, "player_position": {"x": 9,
                                                                                "y": 161, "z": 0}})

    def test_expired_repress_requires_exact_rejection_without_dispatch(self):
        valid = {"schema_version": 2, "kind": "action", "name": "visible_key",
                 "status": "ok", "result": {"action": "visible_key", "status": "rejected",
                                          "inputCalls": 0,
                                          "detail": "attack hold expired; release before pressing again"}}
        with patch.object(subject.lab, "listening_socket") as socket, \
                patch.object(subject.lab, "http_json", return_value=valid) as request:
            self.assertEqual(subject.expired_repress_denied({"pid": 123, "port": 9876}),
                             {"status": "rejected", "input_calls": 0})
        socket.assert_called_once_with(123, 9876)
        self.assertEqual(request.call_args.args[2]["params"],
                         {"key": "attack", "pressed": True})
        for result in ({**valid, "result": {**valid["result"], "status": "input_dispatched"}},
                       {**valid, "result": {**valid["result"], "inputCalls": True}},
                       {**valid, "result": {**valid["result"], "detail": "other refusal"}}):
            with patch.object(subject.lab, "listening_socket"), \
                    patch.object(subject.lab, "http_json", return_value=result):
                with self.assertRaisesRegex(lab.LabError, "not denied"):
                    subject.expired_repress_denied({"pid": 123, "port": 9876})

    def test_log_action_needs_zero_baseline_and_one_authoritative_pickup(self):
        ready = self.root / "ready.json"
        args = SimpleNamespace(identity=self.root / "identity.json", artifact=self.root / "aura.jar",
                               out=self.root / "action", phase="log_mining", test_id="log-01",
                               ready_file=ready, stop_file=self.root / "stop")
        stack = {"itemId": "minecraft:oak_log", "componentSetSha256": "a" * 64,
                 "count": 1, "itemIdTruncated": False, "componentsTruncated": False,
                 "componentBasis": "patch_against_pinned_registry_defaults",
                 "componentDigestStatus": "COMPLETE"}
        baseline = {"stacks": [], "truncated": False, "serverAuthoritative": True,
                    "stateSource": "integrated_server_inventory"}
        picked_up = {**baseline, "stacks": [stack]}
        ground_empty = {"entities": [], "player_position": {"x": 0, "y": 161, "z": 0},
                        "server_tick": 10}
        ground_drop = {**ground_empty, "server_tick": 12,
                       "entities": [{"entity_id": "minecraft:item",
                                     "item_components_complete": True,
                                     "item": {"item_id": "minecraft:oak_log", "count": 1}}]}
        ground_picked = {**ground_empty, "server_tick": 13,
                         "player_position": {"x": 1, "y": 161, "z": 1}}
        session = MagicMock()
        session.frame.side_effect = [b"before", b"after"]
        session.input.side_effect = [PolicyError("denied"), {"accepted": True},
                                     {"accepted": True}, {"accepted": True},
                                     PolicyError("closed")]
        session.cancel.return_value = {"input_released": True}
        session.cleanup_status = "pass"
        context = MagicMock()
        context.__enter__.return_value = session

        def ready_after_armed(_seconds):
            ready.write_text(json.dumps({"recording": True, "test_id": args.test_id}))

        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject.lab, "check_derivative",
                             return_value=subject.LONG_HOLD_BRIDGE_SHA256), \
                patch.object(subject, "verify_window", return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject, "PolicySession", return_value=context), \
                patch.object(subject.scenario_v2, "_scenario_observation",
                             side_effect=[({}, baseline), ({}, ground_empty),
                                          ({}, baseline), ({}, ground_drop),
                                          ({}, picked_up), ({}, ground_picked)]), \
                patch.object(subject, "pixels_changed", return_value=True), \
                patch.object(subject.time, "sleep", side_effect=ready_after_armed):
            report = subject.act(args)
        self.assertEqual(report["status"], "inconclusive")
        self.assertTrue(report["pickup_observed"])
        self.assertEqual(report["inventory_before"]["oak_log_count"], 0)
        self.assertEqual(report["inventory_after"]["oak_log_count"], 1)
        self.assertEqual(report["collection_pulses"], 1)
        self.assertEqual(report["ground_after_break"]["oak_log_count"], 1)
        self.assertEqual(report["ground_after_collection"]["oak_log_count"], 0)
        self.assertEqual([call.args[0] for call in session.input.call_args_list[1:4]], [
            {"type": "pulse", "key": "attack", "milliseconds": 5000},
            {"type": "look", "yaw_delta": 0, "pitch_delta": -15},
            {"type": "pulse", "key": "forward", "milliseconds": 100}])
        self.assertTrue(report["post_cancel_denied"])

        refused_args = SimpleNamespace(**{**vars(args), "out": self.root / "refused",
                                         "ready_file": self.root / "refused.ready",
                                         "stop_file": self.root / "refused.stop"})
        session.frame.side_effect = [b"before"]
        session.input.side_effect = [PolicyError("denied")]

        def ready_for_refusal(_seconds):
            refused_args.ready_file.write_text(json.dumps({"recording": True,
                                                            "test_id": args.test_id}))

        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject.lab, "check_derivative",
                             return_value=subject.LONG_HOLD_BRIDGE_SHA256), \
                patch.object(subject, "verify_window", return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject, "PolicySession", return_value=context), \
                patch.object(subject.scenario_v2, "_scenario_observation",
                             return_value=({}, picked_up)), \
                patch.object(subject.time, "sleep", side_effect=ready_for_refusal):
            report = subject.act(refused_args)
        self.assertEqual(report["status"], "fail")
        self.assertIn("already in inventory", report["reason"])

    def test_expiry_action_records_held_expired_neutral_and_release_repress(self):
        ready = self.root / "ready.json"
        args = SimpleNamespace(identity=self.root / "identity.json", artifact=self.root / "aura.jar",
                               out=self.root / "action", phase="expiry_mining", test_id="expiry-01",
                               ready_file=ready, stop_file=self.root / "stop")
        session = MagicMock()
        session.frame.side_effect = [b"before", b"held", b"expired", b"neutral", b"after"]
        session.input.side_effect = [PolicyError("denied"), PolicyError("closed")]
        session.cancel.return_value = {"input_released": True}
        session.cleanup_status = "pass"
        context = MagicMock()
        context.__enter__.return_value = session

        def ready_after_armed(_seconds):
            ready.write_text(json.dumps({"recording": True, "test_id": args.test_id}))

        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject.lab, "check_derivative",
                             return_value=subject.LONG_HOLD_BRIDGE_SHA256), \
                patch.object(subject, "verify_window", return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject, "PolicySession", return_value=context), \
                patch.object(subject.scenario_v2, "scenario_request") as action, \
                patch.object(subject, "expired_repress_denied",
                             return_value={"status": "rejected", "input_calls": 0}) as renewal, \
                patch.object(subject, "pixels_changed", return_value=True), \
                patch.object(subject.time, "sleep", side_effect=ready_after_armed):
            report = subject.act(args)
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual([call.args[3]["pressed"] for call in action.call_args_list],
                         [True, False, True, False])
        renewal.assert_called_once_with(self.identity)
        self.assertEqual((args.out / "held.png").read_bytes(), b"held")
        self.assertEqual((args.out / "expired.png").read_bytes(), b"expired")
        self.assertEqual((args.out / "neutral.png").read_bytes(), b"neutral")
        self.assertTrue(report["explicit_release"])
        self.assertTrue(report["release_repress_exercised"])
        self.assertTrue(report["post_cancel_denied"])
        events = [entry["event"] for entry in report["timeline"]]
        self.assertLess(events.index("initial_press_ack"), events.index("expired_frame_request"))
        self.assertLess(events.index("expired_frame_saved"), events.index("initial_release_request"))
        self.assertLess(events.index("initial_release_ack"), events.index("neutral_frame_request"))
        self.assertLess(events.index("neutral_frame_saved"), events.index("second_press_request"))
        self.assertLess(events.index("second_press_ack"), events.index("second_release_request"))
        self.assertTrue(all(entry["utc"].endswith("+00:00") for entry in report["timeline"]))
        ticks = [entry["monotonic_ns"] for entry in report["timeline"]]
        self.assertEqual(ticks, sorted(ticks))

    def test_act_waits_for_matching_recording_and_stops_after_cancel(self):
        ready = self.root / "ready.json"
        stop = self.root / "stop"
        args = SimpleNamespace(identity=self.root / "identity.json", artifact=self.root / "aura.jar",
                               out=self.root / "action", phase="initial_attack", test_id="attack-01",
                               ready_file=ready, stop_file=stop)
        session = MagicMock()
        session.frame.side_effect = [b"first", b"second"]
        session.input.side_effect = [PolicyError("denied"), {"accepted": True}, PolicyError("closed")]
        session.cancel.return_value = {"input_released": True}
        session.cleanup_status = "pass"
        context = MagicMock()
        context.__enter__.return_value = session

        def ready_after_armed(_seconds):
            self.assertTrue((args.out / "armed.json").is_file())
            ready.write_text(json.dumps({"recording": True, "test_id": args.test_id}))

        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject, "verify_window", return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject, "PolicySession", return_value=context), \
                patch.object(subject, "pixels_changed", return_value=True), \
                patch.object(subject.time, "sleep", side_effect=ready_after_armed):
            report = subject.act(args)
        self.assertEqual(report["status"], "inconclusive")
        self.assertTrue(report["denied_request"])
        self.assertTrue(report["post_cancel_denied"])
        self.assertEqual(report["cleanup_status"], "pass")
        self.assertTrue(stop.is_file())
        self.assertEqual((args.out / "before.png").read_bytes(), b"first")
        self.assertEqual((args.out / "after.png").read_bytes(), b"second")

    def test_failed_readiness_still_signals_recorder_stop(self):
        ready = self.root / "ready.json"
        stop = self.root / "stop"
        args = SimpleNamespace(identity=self.root / "identity.json", artifact=self.root / "aura.jar",
                               out=self.root / "action", phase="use", test_id="use-01",
                               ready_file=ready, stop_file=stop)
        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject, "verify_window", return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject.time, "monotonic", side_effect=[0, 31]):
            report = subject.act(args)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(stop.is_file())

    def test_use_requires_screen_transition_and_closes_it(self):
        ready = self.root / "ready.json"
        stop = self.root / "stop"
        args = SimpleNamespace(identity=self.root / "identity.json", artifact=self.root / "aura.jar",
                               out=self.root / "action", phase="use", test_id="use-01",
                               ready_file=ready, stop_file=stop)
        session = MagicMock()
        session.frame.side_effect = [b"before", b"menu", b"closed"]
        session.input.side_effect = [PolicyError("denied"), {"accepted": True},
                                     {"accepted": True}, PolicyError("closed")]
        session.cancel.return_value = {"input_released": True}
        session.cleanup_status = "pass"
        context = MagicMock()
        context.__enter__.return_value = session

        def ready_after_armed(_seconds):
            ready.write_text(json.dumps({"recording": True, "test_id": args.test_id}))

        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject, "verify_window", return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject, "PolicySession", return_value=context), \
                patch.object(subject.lab, "command", side_effect=[{"screen": "ChestScreen"},
                                                                  {"screen": None}]), \
                patch.object(subject, "pixels_changed", return_value=True), \
                patch.object(subject.time, "sleep", side_effect=ready_after_armed):
            report = subject.act(args)
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual(report["screen_opened"], "ChestScreen")
        self.assertTrue(report["screen_closed"])
        self.assertEqual(report["window_title_during_gui"], "MC Mod Lab Minecraft PID 123")
        self.assertEqual(report["window_title_after_gui"], "MC Mod Lab Minecraft PID 123")
        self.assertEqual((args.out / "closed.png").read_bytes(), b"closed")
        self.assertTrue(stop.is_file())

    def test_held_mining_repeats_press_then_releases_and_represses(self):
        ready = self.root / "ready.json"
        stop = self.root / "stop"
        args = SimpleNamespace(identity=self.root / "identity.json", artifact=self.root / "aura.jar",
                               out=self.root / "action", phase="held_mining", test_id="mining-01",
                               ready_file=ready, stop_file=stop)
        session = MagicMock()
        session.frame.side_effect = [b"before", b"after"]
        session.input.side_effect = [PolicyError("denied"), PolicyError("closed")]
        session.cancel.return_value = {"input_released": True}
        session.cleanup_status = "pass"
        context = MagicMock()
        context.__enter__.return_value = session

        def ready_after_armed(_seconds):
            ready.write_text(json.dumps({"recording": True, "test_id": args.test_id}))

        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject, "verify_window", return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject, "PolicySession", return_value=context), \
                patch.object(subject.scenario_v2, "scenario_request") as request, \
                patch.object(subject, "pixels_changed", return_value=True), \
                patch.object(subject.time, "sleep", side_effect=ready_after_armed):
            report = subject.act(args)
        self.assertEqual(report["status"], "inconclusive")
        self.assertTrue(report["repeat_press_exercised"])
        self.assertTrue(report["explicit_release"])
        self.assertTrue(report["release_repress_exercised"])
        self.assertEqual([call.args[3]["pressed"] for call in request.call_args_list],
                         [True, True, False, True, False])
        self.assertEqual(report["cleanup_status"], "pass")
        self.assertTrue(stop.is_file())

    def test_durable_mining_records_neutral_interval_and_release_repress(self):
        ready = self.root / "ready.json"
        stop = self.root / "stop"
        args = SimpleNamespace(identity=self.root / "identity.json", artifact=self.root / "aura.jar",
                               out=self.root / "action", phase="durable_mining", test_id="durable-01",
                               ready_file=ready, stop_file=stop)
        session = MagicMock()
        session.frame.side_effect = [b"before", b"neutral", b"after"]
        session.input.side_effect = [PolicyError("denied"), PolicyError("closed")]
        session.cancel.return_value = {"input_released": True}
        session.cleanup_status = "pass"
        context = MagicMock()
        context.__enter__.return_value = session

        def ready_after_armed(_seconds):
            ready.write_text(json.dumps({"recording": True, "test_id": args.test_id}))

        with patch.object(subject, "checked_identity", return_value=self.identity), \
                patch.object(subject, "verify_window", return_value="MC Mod Lab Minecraft PID 123"), \
                patch.object(subject, "PolicySession", return_value=context), \
                patch.object(subject.scenario_v2, "scenario_request") as request, \
                patch.object(subject, "pixels_changed", return_value=True), \
                patch.object(subject.time, "sleep", side_effect=ready_after_armed):
            report = subject.act(args)
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual([call.args[3]["pressed"] for call in request.call_args_list],
                         [True, False, True, False])
        self.assertEqual((args.out / "neutral.png").read_bytes(), b"neutral")
        self.assertTrue(report["explicit_release"])
        self.assertTrue(report["release_repress_exercised"])
        self.assertEqual(report["cleanup_status"], "pass")
        self.assertTrue(stop.is_file())

    def test_window_pid_must_be_unique(self):
        row = {"Id": 123, "MainWindowTitle": "MC Mod Lab Minecraft PID 123"}
        result = SimpleNamespace(returncode=0, stdout=json.dumps([row, {**row, "Id": 999}]))
        with patch.object(subject.subprocess, "run", return_value=result):
            with self.assertRaises(lab.LabError):
                subject.verify_window(self.identity)
        result.stdout = json.dumps([row])
        with patch.object(subject.subprocess, "run", return_value=result):
            self.assertEqual(subject.verify_window(self.identity), row["MainWindowTitle"])

    def test_window_inventory_does_not_fail_when_javaw_is_absent(self):
        row = {"Id": 123, "MainWindowTitle": "MC Mod Lab Minecraft PID 123"}
        result = SimpleNamespace(returncode=0, stdout=json.dumps(row))
        with patch.object(subject.subprocess, "run", return_value=result) as query:
            self.assertEqual(subject.verify_window(self.identity), row["MainWindowTitle"])
        command = query.call_args.args[0][-1]
        self.assertIn("Get-Process | Where-Object", command)
        self.assertNotIn("Get-Process java,javaw", command)


if __name__ == "__main__":
    unittest.main()
