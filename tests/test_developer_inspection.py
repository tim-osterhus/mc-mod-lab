import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import contracts
import developer_inspection as inspect
import lab
import scenario_v2


ROOT = Path(__file__).resolve().parents[1]


class DeveloperInspectionTests(unittest.TestCase):
    def screen(self):
        return {"screenClass": "net.minecraft.class_490", "stateSource": "client_menu_cache",
                "serverAuthoritative": False, "slotCount": 2, "hoveredIndex": 1,
                "slots": [{"index": 0, "x": 10, "y": 12, "item": None},
                          {"index": 1, "x": 28, "y": 12,
                           "item": {"itemId": "minecraft:coal", "count": 2,
                                    "componentDigestComplete": True, "componentSha256": "a" * 64}}]}

    def block(self):
        return {"serverTick": 42, "stateSource": "integrated_server_block_entity_inventory",
                "serverAuthoritative": True, "dimension": "minecraft:overworld",
                "x": 0, "y": 64, "z": 0, "blockId": "minecraft:chest",
                "blockEntityId": "minecraft:chest", "hasInventory": True, "slotCount": 27,
                "slots": [{"index": 3, "item": {"itemId": "minecraft:coal", "count": 2,
                          "componentDigestComplete": True, "componentSha256": "b" * 64}}]}

    def test_screen_cache_and_hover_are_bounded_not_authoritative(self):
        value = self.screen()
        self.assertIs(inspect.screen_slots(value, {"observation_source": "client_or_integrated_server_pointer"}), value)
        for mutate in (lambda v: v.update(serverAuthoritative=True),
                       lambda v: v.update(hoveredIndex=2),
                       lambda v: v.update(slotCount=129),
                       lambda v: v["slots"][1].update(index=0),
                       lambda v: v["slots"][0].update(index=False),
                       lambda v: v["slots"][1]["item"].update(componentSha256=None)):
            wrong = copy.deepcopy(value)
            mutate(wrong)
            with self.subTest(wrong=wrong), self.assertRaises(lab.LabError):
                inspect.screen_slots(wrong, {"observation_source": "client_or_integrated_server_pointer"})
        with self.assertRaises(lab.LabError):
            inspect.screen_slots(value, {"observation_source": "integrated_server_block_entity"})

    def test_gson_omitted_nulls_normalize_without_accepting_extra_fields(self):
        value = self.screen()
        value.pop("hoveredIndex")
        value["slots"][0].pop("item")
        value["slots"][1]["item"].update(componentDigestComplete=False)
        value["slots"][1]["item"].pop("componentSha256")
        inspect.screen_slots(value, {"observation_source": "client_or_integrated_server_pointer"})
        self.assertIsNone(value["hoveredIndex"])
        self.assertIsNone(value["slots"][0]["item"])
        self.assertIsNone(value["slots"][1]["item"]["componentSha256"])
        value["slots"][0]["unexpected"] = 1
        with self.assertRaises(lab.LabError):
            inspect.screen_slots(value, {"observation_source": "client_or_integrated_server_pointer"})

    def test_block_entity_requires_exact_tick_coordinates_and_slots(self):
        value = self.block()
        envelope = {"observation_source": "integrated_server_block_entity",
                    "server_tick_before": 42, "server_tick_after": 42}
        spec = {"type": "block_entity_inventory", "x": 0, "y": 64, "z": 0}
        self.assertIs(inspect.block_entity_inventory(value, envelope, spec), value)
        for mutate in (lambda v: v.update(serverTick=41),
                       lambda v: v.update(x=1),
                       lambda v: v.update(x=False),
                       lambda v: v.update(x=0.0),
                       lambda v: v.update(y=64.0),
                       lambda v: v.update(slotCount=65),
                       lambda v: v["slots"][0].update(index=27),
                       lambda v: v.update(hasInventory=False)):
            wrong = copy.deepcopy(value)
            mutate(wrong)
            with self.subTest(wrong=wrong), self.assertRaises(lab.LabError):
                inspect.block_entity_inventory(wrong, envelope, spec)
        wrong = copy.deepcopy(value)
        wrong.update(hasInventory=False, slotCount=0, slots=[])
        self.assertIs(inspect.block_entity_inventory(wrong, envelope, spec), wrong)
        for field in ("server_tick_before", "server_tick_after"):
            for malformed_tick in (42.0, True):
                bad_envelope = dict(envelope, **{field: malformed_tick})
                with self.assertRaises(lab.LabError):
                    inspect.block_entity_inventory(value, bad_envelope, spec)

    def test_state_dependent_observers_are_not_probed_before_gui_opens(self):
        scenario = contracts.load(ROOT / "examples/scenario-v2.json")
        scenario["steps"] = [{"id": "gui", "observe": [{"type": "screen_slots"}]},
                             {"id": "container", "observe": [{"type": "block_entity_inventory",
                                "x": 0, "y": 64, "z": 0}]}]
        scenario_v2.validate_scenario(scenario)
        with patch.object(scenario_v2, "_scenario_observation") as observer:
            scenario_v2._preflight_route_observations({}, scenario, {"steps": [{}, {}]})
        observer.assert_not_called()

    def test_unknown_inspection_fields_and_commands_are_rejected(self):
        scenario = contracts.load(ROOT / "examples/scenario-v2.json")
        scenario["steps"] = [{"id": "gui", "observe": [{"type": "screen_slots", "path": "nbt"}]}]
        with self.assertRaises(contracts.ContractError):
            scenario_v2.validate_scenario(scenario)
        scenario["steps"] = [{"id": "gui", "action": {"type": "execute_command", "command": "give"}}]
        with self.assertRaises(contracts.ContractError):
            scenario_v2.validate_scenario(scenario)


if __name__ == "__main__":
    unittest.main()
