import json
import os
import threading
import time
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import lab
import scenario_v2 as runner


class TypedScenarioTests(unittest.TestCase):
    def test_client_predicted_inventory_refused(self):
        client = {"stacks": [], "truncated": False, "serverAuthoritative": False,
                  "stateSource": "client_inventory_cache"}
        with patch.object(runner, "scenario_request", return_value={"result": client}):
            with self.assertRaisesRegex(lab.LabError, "server-authoritative"):
                runner._scenario_observation({}, {"type": "player_inventory"})

    def test_server_inventory_tick_bound_and_conservation(self):
        value = {"stacks": [], "truncated": False, "serverAuthoritative": True,
                 "stateSource": "integrated_server_inventory", "serverTick": 9}
        envelope = {"result": value, "server_tick_before": 9, "server_tick_after": 9}
        with patch.object(runner, "scenario_request", return_value=envelope):
            self.assertEqual(runner._scenario_observation({}, {"type": "player_inventory"})[1], value)
            value["serverTick"] = 8
            with self.assertRaisesRegex(lab.LabError, "snapshot tick"):
                runner._scenario_observation({}, {"type": "player_inventory"})
        snapshot = runner._inventory_snapshot(value)
        observations = {key: {("player_inventory", None, None, None): {"value": snapshot}}
                        for key in ("before", "after")}
        requirement = {"type": "inventory_conservation", "before": "before", "after": "after",
                       "item_id": "minecraft:coal", "expected_count_delta": 0}
        runner._assert_typed({}, requirement, observations)
        snapshot["server_authoritative"] = False
        with self.assertRaisesRegex(lab.LabError, "authoritative inventory"):
            runner._assert_typed({}, requirement, observations)

    def test_timed_out_dispatch_quarantines_profile_and_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary) / "game"
            seed = game / "saves" / "fixture"
            seed.mkdir(parents=True)
            identity = {"pid": 12, "port": 9875, "game_dir": str(game)}
            connection = Mock()
            connection.getresponse.return_value.status = 504
            connection.getresponse.return_value.read.return_value = b'{"status":"error"}'
            with patch.dict(os.environ, {"MC_MOD_LAB_TOKEN": "x" * 32}), \
                    patch.object(lab, "listening_socket"), \
                    patch.object(runner.http.client, "HTTPConnection", return_value=connection):
                with self.assertRaises(lab.LabError):
                    runner.scenario_request(identity, "action", "drop_selected", {"count": 1})
                self.assertTrue((game / runner.UNCERTAIN_MARKER).exists())
                connection.reset_mock()
                with self.assertRaisesRegex(lab.LabError, "uncertain action"):
                    runner.scenario_request(identity, "action", "drop_selected", {"count": 1})
                connection.request.assert_not_called()
                with self.assertRaisesRegex(lab.LabError, "uncertain action"):
                    lab.fixture_create(seed, Path(temporary) / "copies", "new-fixture", "New")

    def test_nonfinite_aura_values_cannot_pass_increase(self):
        for value in (float("nan"), float("inf"), -float("inf"), True):
            with self.subTest(value=value), self.assertRaises(lab.LabError):
                runner._aura_numeric_value({"kind": "NODE", "node": {"totalAura": value}}, "total_aura")

    def test_unsupported_http_response_is_never_a_pass(self):
        connection = Mock()
        connection.getresponse.return_value.status = 422
        connection.getresponse.return_value.read.return_value = b'{"schema_version":2,"status":"unsupported"}'
        with patch.dict(os.environ, {"MC_MOD_LAB_TOKEN": "x" * 32}), \
                patch.object(lab, "listening_socket"), \
                patch.object(runner.http.client, "HTTPConnection", return_value=connection):
            with self.assertRaises(lab.LabError) as raised:
                runner.scenario_request({"pid": 12, "port": 9875}, "observe", "server_tick", {})
        self.assertEqual(raised.exception.status, "unsupported")
        connection.close.assert_called_once()

    def test_action_ack_requires_matching_successful_dispatch(self):
        action = {"type": "drop_selected", "count": 1}
        cases = [{}, {"status": "rejected"}, {"status": "unexpected"},
                 {"status": "input_dispatched", "action": "select_hotbar", "inputCalls": 1},
                 {"status": "input_dispatched", "action": "drop_selected", "inputCalls": True}]
        for result in cases:
            with self.subTest(result=result), patch.object(runner, "scenario_request", return_value={"result": result}):
                with self.assertRaises(lab.LabError):
                    runner._route_action({}, action)
        with patch.object(runner, "scenario_request", return_value={"result": {
                "status": "input_dispatched", "action": "drop_selected", "inputCalls": 1}}):
            evidence = runner._route_action({}, action)
        self.assertTrue(evidence["acknowledged"])
        self.assertNotIn("assertion", evidence)

    def test_cancelled_wait_does_not_read_or_sleep(self):
        event = threading.Event()
        event.set()
        with patch.object(runner, "_scenario_observation") as read:
            with self.assertRaisesRegex(lab.LabError, "cancellation"):
                runner._wait_ticks({}, 20, time.monotonic() + 10, event)
        read.assert_not_called()

    def test_backward_tick_fails_wait(self):
        with patch.object(runner, "_scenario_observation", side_effect=[({}, 100), ({}, 99)]), \
                patch.object(runner.time, "sleep"):
            with self.assertRaisesRegex(lab.LabError, "backwards"):
                runner._wait_ticks({}, 20, time.monotonic() + 10, None)

    def test_authoritative_snapshot_tick_must_match_envelope(self):
        spec = {"type": "aura_block_server", "x": 0, "y": 161, "z": 0}
        value = {"x": 0, "y": 161, "z": 0, "serverAuthoritative": True,
                 "stateSource": "integrated_server_block_entity", "serverTick": 14}
        envelope = {"result": value, "server_tick_before": 15, "server_tick_after": 15}
        with patch.object(runner, "scenario_request", return_value=envelope):
            with self.assertRaisesRegex(lab.LabError, "snapshot tick"):
                runner._scenario_observation({}, spec)
        value["serverTick"] = 15
        with patch.object(runner, "scenario_request", return_value=envelope):
            self.assertEqual(runner._scenario_observation({}, spec)[1], value)
        value["serverAuthoritative"] = False
        with patch.object(runner, "scenario_request", return_value=envelope):
            with self.assertRaises(lab.LabError):
                runner._scenario_observation({}, spec)

    def test_incomplete_components_refuse_exact_digest(self):
        stack = {"itemId": "minecraft:diamond", "count": 7,
                 "itemIdTruncated": False, "componentsTruncated": False,
                 "componentDigestStatus": "COMPLETE", "componentSetSha256": "a" * 64,
                 "componentBasis": "patch_against_pinned_registry_defaults"}
        self.assertTrue(runner._inventory_snapshot({"stacks": [stack], "truncated": False})["complete"])
        for status in ("UNSUPPORTED", "TRUNCATED"):
            stack["componentDigestStatus"] = status
            result = runner._inventory_snapshot({"stacks": [stack], "truncated": False})
            self.assertFalse(result["complete"])
            self.assertIsNone(result["digest"])

    def test_unfueled_transfer_control_retains_observed_zero(self):
        value = {"x": 0, "y": 164, "z": 0, "blockId": "aura:aura_node", "kind": "NODE",
                 "stateSource": "integrated_server_block_entity", "serverAuthoritative": True,
                 "node": {"totalAura": 0}}
        observations = {step: {("aura_block_server", 0, 164, 0): {"value": value}}
                        for step in ("before", "after")}
        requirement = {"type": "aura_increase", "before": "before", "after": "after",
                       "metric": "total_aura", "minimum_delta": 1}
        with self.assertRaises(lab.LabError) as raised:
            runner._assert_typed({}, requirement, observations)
        self.assertEqual(raised.exception.status, "fail")
        self.assertEqual(raised.exception.evidence["before_value"], 0)
        self.assertEqual(raised.exception.evidence["after_value"], 0)


if __name__ == "__main__":
    unittest.main()
