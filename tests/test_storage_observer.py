import copy
import unittest

import lab
import scenario_v2


class StorageObserverTests(unittest.TestCase):
    def setUp(self):
        self.spec = {"type": "aura_storage_fixture", "x": 0, "y": 161, "z": 0}
        self.envelope = {"server_tick_before": 42, "server_tick_after": 42}
        self.stack = {"itemId": "minecraft:diamond", "count": 7, "itemIdTruncated": False,
                      "componentBasis": "patch_against_pinned_registry_defaults",
                      "componentsTruncated": False, "componentDigestStatus": "COMPLETE",
                      "componentSetSha256": "a" * 64}
        common = {"serverTick": 42, "serverAuthoritative": True,
                  "stateSource": "integrated_server_block_entity", "y": 161, "z": 0}
        self.value = {"serverTick": 42, "serverAuthoritative": True,
                      "stateSource": "integrated_server_storage_fixture", "x": 0, "y": 161, "z": 0,
                      "requiredPower": 5, "availablePower": 1000,
                      "inventory": {"serverTick": 42, "serverAuthoritative": True,
                                    "stateSource": "integrated_server_inventory", "truncated": False,
                                    "stacks": [copy.deepcopy(self.stack)]},
                      "shelf": {**common, "x": 1, "kind": "STORAGE_BOOKSHELF", "blockId": "aura:storage_bookshelf",
                                "bookshelf": {"hasBook": True, "entriesTruncated": False,
                                              "entryDigestStatus": "COMPLETE", "storedTypes": 0,
                                              "storedItemCount": 0, "entries": []}},
                      "powerNode": {**common, "x": -1, "kind": "NODE", "blockId": "aura:aura_node",
                                    "node": {"storedPower": 1000}}}

    def parse(self):
        return scenario_v2._storage_fixture_snapshot(self.value, self.envelope, self.spec)

    def test_complete_snapshot_is_portable(self):
        result = self.parse()
        self.assertEqual(result["inventory"][0]["count"], 7)
        self.assertEqual(result["storage"], [])
        self.assertEqual(result["power"], 1000)
        self.assertNotIn("custom_data", str(result))

    def test_cached_inventory_refused(self):
        self.value["inventory"]["serverAuthoritative"] = False
        with self.assertRaises(lab.LabError):
            self.parse()

    def test_mixed_ticks_refused(self):
        self.value["shelf"]["serverTick"] = 41
        with self.assertRaises(lab.LabError):
            self.parse()

    def test_wrong_member_coordinate_refused(self):
        self.value["powerNode"]["x"] = 2
        with self.assertRaises(lab.LabError):
            self.parse()

    def test_unsupported_components_refused(self):
        self.value["inventory"]["stacks"][0]["componentDigestStatus"] = "UNSUPPORTED"
        with self.assertRaises(lab.LabError):
            self.parse()

    def test_truncated_storage_refused(self):
        self.value["shelf"]["bookshelf"]["entriesTruncated"] = True
        with self.assertRaises(lab.LabError):
            self.parse()

    def test_inconsistent_power_refused(self):
        self.value["availablePower"] = 999
        with self.assertRaises(lab.LabError):
            self.parse()

    def test_same_item_components_remain_distinct(self):
        beta = {**self.stack, "count": 3, "componentSetSha256": "b" * 64}
        shelf = self.value["shelf"]["bookshelf"]
        shelf.update(entries=[self.stack, beta], storedTypes=2, storedItemCount=10)
        result = self.parse()
        self.assertEqual([row["count"] for row in result["storage"]], [7, 3])
        self.assertNotEqual(result["storage"][0]["component_sha256"], result["storage"][1]["component_sha256"])

    def transfer(self, mutate=None):
        before = self.parse()
        before["inventory"].append({"item_id": "minecraft:diamond", "count": 3, "component_sha256": "b" * 64})
        after = copy.deepcopy(before)
        after.update(server_tick=52, power=990, storage=after["inventory"], inventory=[])
        if mutate:
            mutate(after)
        observations = {name: {("aura_storage_fixture", 0, 161, 0): {"value": value}}
                        for name, value in (("before", before), ("after", after))}
        requirement = {"type": "storage_transfer", "before": "before", "after": "after", "direction": "deposit",
                       "count": 10, "component_types": 2, "transactions": 2}
        return scenario_v2._assert_storage_transfer(requirement, observations)

    def test_exact_component_transfer_and_power(self):
        self.assertEqual(self.transfer()["actual_count_delta"], 10)

    def test_component_swap_cannot_pass_total_count(self):
        with self.assertRaises(lab.LabError):
            self.transfer(lambda after: after["storage"][1].update(component_sha256="c" * 64))

    def test_duplicate_inventory_output_refused(self):
        with self.assertRaises(lab.LabError):
            self.transfer(lambda after: after["inventory"].append(copy.deepcopy(after["storage"][0])))

    def test_wrong_transaction_power_refused(self):
        with self.assertRaises(lab.LabError):
            self.transfer(lambda after: after.update(power=995))

    def test_missing_stack_refused(self):
        with self.assertRaises(lab.LabError):
            self.transfer(lambda after: after["storage"].pop())


if __name__ == "__main__":
    unittest.main()
