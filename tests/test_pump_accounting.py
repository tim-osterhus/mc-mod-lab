import unittest

import lab
import scenario_v2 as runner


class PumpAccountingTests(unittest.TestCase):
    def fixture(self, mode):
        before = {"type": "aura_pump_pair", "server_authoritative": True,
                  "server_tick": 100, "world_time": 100, "x": 0, "y": 161, "z": 0, "target_y": 164,
                  "pump_aura": 1000, "target_aura": 0, "power": 0, "speed": 0,
                  "blocked": mode == "blocked", "inhibited": False, "ground_coal": 0, "inventory_coal": 1}
        after = {**before, "server_tick": 400, "world_time": 400}
        end = {**after, "server_tick": 460, "world_time": 460}
        if mode != "unfueled":
            after.update(inventory_coal=0, power=320 if mode == "blocked" else 305, speed=300)
            end.update(inventory_coal=0, power=320 if mode == "blocked" else 302, speed=300)
        if mode == "flow":
            after.update(pump_aura=0, target_aura=1000)
            end.update(pump_aura=0, target_aura=1000)
        values = {"before": before, "after": after, "end": end}
        observations = {name: {("aura_pump_pair", 0, 161, 0, 164): {"value": value}}
                        for name, value in values.items()}
        requirement = {"type": "pump_accounting", "before": "before", "after": "after", "end": "end",
                       "mode": mode, "expected_aura": 1000}
        return requirement, observations, values

    def test_flow_and_both_controls_pass_only_their_declared_outcome(self):
        for mode in ("flow", "unfueled", "blocked"):
            requirement, observations, _ = self.fixture(mode)
            runner._assert_typed({}, requirement, observations)
            if mode != "flow":
                requirement["mode"] = "flow"
                with self.assertRaises(lab.LabError):
                    runner._assert_typed({}, requirement, observations)

    def test_accounting_fuel_and_clock_mutations_fail_with_evidence(self):
        for key, value in (("pump_aura", 1), ("power", 301), ("inventory_coal", 1),
                           ("ground_coal", 1), ("speed", 301), ("inhibited", True),
                           ("server_tick", 100), ("world_time", 400), ("target_y", 165)):
            requirement, observations, values = self.fixture("flow")
            values["end"][key] = value
            with self.subTest(key=key), self.assertRaises(lab.LabError) as raised:
                runner._assert_typed({}, requirement, observations)
            self.assertIn("pump_accounting", raised.exception.evidence)

    def test_non_atomic_pair_rejected_before_comparison(self):
        value = {"serverAuthoritative": True, "stateSource": "integrated_server_pump_pair", "serverTick": 10}
        with self.assertRaisesRegex(lab.LabError, "atomic"):
            runner._pump_pair_snapshot(value, {"server_tick_before": 10, "server_tick_after": 11}, {})


if __name__ == "__main__":
    unittest.main()
