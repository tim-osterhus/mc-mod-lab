import copy
import unittest

import lab
import scenario_v2


class GroundEntitiesTests(unittest.TestCase):
    def setUp(self):
        self.spec = {"type": "ground_entities", "radius": 6}
        self.envelope = {"server_tick_before": 7, "server_tick_after": 7}
        self.value = {"serverAuthoritative": True, "stateSource": "integrated_server_ground_entities",
                      "serverTick": 7, "radius": 6, "dimensionId": "minecraft:overworld",
                      "playerPosition": {"x": 0.5, "y": 161, "z": 2.5},
                      "entities": [{"entityId": "minecraft:pig", "uuid": "00000000-0000-0000-0000-000000000001",
                                    "alive": True, "position": {"x": 1, "y": 161, "z": 2},
                                    "velocity": {"x": 0.7, "y": 0, "z": 0}, "health": 10}]}

    def parse(self):
        return scenario_v2._ground_entities_snapshot(self.value, self.envelope, self.spec)

    def test_motion_snapshot_retains_measured_velocity(self):
        result = self.parse()
        self.assertEqual(result["entities"][0]["velocity"]["x"], 0.7)
        self.assertNotIn("00000000", str(result))

    def test_duplicate_identity_refused(self):
        self.value["entities"].append(copy.deepcopy(self.value["entities"][0]))
        with self.assertRaises(lab.LabError):
            self.parse()

    def test_nonfinite_velocity_refused(self):
        self.value["entities"][0]["velocity"]["x"] = float("nan")
        with self.assertRaises(lab.LabError):
            self.parse()

    def test_incomplete_item_does_not_claim_exact_digest(self):
        self.value["entities"][0]["item"] = {"componentDigestStatus": "UNSUPPORTED"}
        row = self.parse()["entities"][0]
        self.assertFalse(row["item_components_complete"])
        self.assertNotIn("item", row)

    def test_snapshot_overflow_refused(self):
        self.value["entities"] *= 65
        with self.assertRaises(lab.LabError):
            self.parse()

    def test_wrong_tick_refused(self):
        self.envelope["server_tick_after"] = 8
        with self.assertRaises(lab.LabError):
            self.parse()

    def test_client_only_refused(self):
        self.value["serverAuthoritative"] = False
        with self.assertRaises(lab.LabError):
            self.parse()

    def impulse(self, mutate=None, minimum=0.5, maximum=1.0):
        before = self.parse()
        before["entities"][0]["velocity"] = {"x": 0, "y": 0, "z": 0}
        after = self.parse()
        after["server_tick"] = 67
        if mutate:
            mutate(after)
        observations = {name: {("ground_entities", 6): {"value": value}}
                        for name, value in (("before", before), ("after", after))}
        return scenario_v2._assert_entity_impulse({"before": "before", "after": "after",
                    "entity_id": "minecraft:pig", "minimum_speed": minimum, "maximum_speed": maximum}, observations)

    def test_stationary_outward_impulse(self):
        self.assertAlmostEqual(self.impulse()["observed"], 0.7)

    def test_zero_control_cannot_pass_positive(self):
        with self.assertRaises(lab.LabError):
            self.impulse(lambda value: value["entities"][0]["velocity"].update(x=0))
        result = self.impulse(lambda value: value["entities"][0]["velocity"].update(x=0), 0, 0.001)
        self.assertEqual(result["observed"], 0)

    def test_inward_motion_is_not_pusher_effect(self):
        with self.assertRaises(lab.LabError):
            self.impulse(lambda value: value["entities"][0]["velocity"].update(x=-0.7))

    def test_changed_player_position_refuses_constant_distance_claim(self):
        with self.assertRaises(lab.LabError):
            self.impulse(lambda value: value["player_position"].update(x=0.6))

    def test_changed_target_refuses_impulse_comparison(self):
        with self.assertRaises(lab.LabError):
            self.impulse(lambda value: value["entities"][0].update(entity_key="f" * 64))


if __name__ == "__main__":
    unittest.main()
