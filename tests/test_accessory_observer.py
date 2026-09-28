import copy
import hashlib
import unittest
from unittest.mock import patch
from uuid import UUID

import lab
import scenario_v2


class AccessoryObserverTests(unittest.TestCase):
    player_uuid = "12345678-1234-5678-1234-567812345678"
    custom_data_marker = "raw-accessory-custom-data-must-not-escape"

    def setUp(self):
        self.envelope = {"server_tick_before": 73, "server_tick_after": 73}

    def item(self, *, section="accessory", slot=1):
        return {
            "itemIdTruncated": False,
            "componentBasis": "patch_against_pinned_registry_defaults",
            "componentsTruncated": False,
            "componentDigestStatus": "COMPLETE",
            "itemId": "aura:crystal_ring",
            "count": 1,
            "componentSetSha256": "a" * 64,
            "section": section,
            "slot": slot,
            "customData": {"private": self.custom_data_marker},
        }

    @staticmethod
    def slot(name, index, item=None):
        return {"slot": name, "index": index, "empty": item is None,
                "exactItem": item is not None, "item": copy.deepcopy(item)}

    def snapshot(self, *, ring=False):
        value = {
            "serverAuthoritative": True,
            "stateSource": "integrated_server_aura_accessories",
            "serverTick": 73,
            "playerUuid": self.player_uuid,
            "amulet": self.slot("amulet", 0),
            "ring1": self.slot("ring1", 1, self.item() if ring else None),
            "ring2": self.slot("ring2", 2),
            "belt": self.slot("belt", 3),
            "cursor": self.slot("cursor", -1),
        }
        return value

    def parse(self, value=None, envelope=None):
        return scenario_v2._accessory_snapshot(
            self.snapshot() if value is None else value,
            self.envelope if envelope is None else envelope,
        )

    def test_explicit_empty_slots_and_neutral_cursor_are_preserved(self):
        result = self.parse()
        expected_key = hashlib.sha256(str(UUID(self.player_uuid)).encode("ascii")).hexdigest()
        self.assertEqual(result, {
            "type": "aura_accessories",
            "server_authoritative": True,
            "server_tick": 73,
            "player_key": expected_key,
            "slots": {"amulet": None, "ring1": None, "ring2": None,
                      "belt": None, "cursor": None},
        })
        self.assertNotIn(self.player_uuid, repr(result))
        self.assertNotIn(self.custom_data_marker, repr(result))

    def test_complete_bound_ring_is_exact_and_custom_data_is_not_exported(self):
        result = self.parse(self.snapshot(ring=True))
        self.assertEqual(result["slots"]["ring1"], {
            "item_id": "aura:crystal_ring", "count": 1, "component_sha256": "a" * 64,
        })
        self.assertNotIn("customData", repr(result))
        self.assertNotIn(self.custom_data_marker, repr(result))

    def test_snapshot_requires_authority_and_one_atomic_server_tick(self):
        cases = (
            (lambda v: v.update(serverAuthoritative=False), self.envelope),
            (lambda v: v.update(serverAuthoritative=1), self.envelope),
            (lambda v: v.update(stateSource="client_accessory_cache"), self.envelope),
            (lambda v: v.update(serverTick=True), self.envelope),
            (lambda v: v.update(serverTick=74), self.envelope),
            (lambda v: v, {"server_tick_before": 72, "server_tick_after": 73}),
            (lambda v: v, {"server_tick_before": 73, "server_tick_after": 74}),
        )
        for mutate, envelope in cases:
            value = self.snapshot()
            mutate(value)
            with self.subTest(value=value, envelope=envelope), self.assertRaises(lab.LabError):
                self.parse(value, envelope)

    def test_uuid_and_slot_set_must_be_complete(self):
        value = self.snapshot()
        value["playerUuid"] = "not-a-uuid"
        with self.assertRaises(lab.LabError):
            self.parse(value)

        value = self.snapshot()
        del value["belt"]
        with self.assertRaises(lab.LabError):
            self.parse(value)

    def test_slot_name_index_and_section_are_enforced(self):
        cases = (
            lambda v: v["ring1"].update(slot="ring2"),
            lambda v: v["ring1"].update(index=0),
            lambda v: v["ring1"].update(index=True),
            lambda v: v["ring1"]["item"].update(section="menu_cursor"),
            lambda v: v["ring1"]["item"].update(slot=0),
            lambda v: v["ring1"]["item"].update(slot=True),
        )
        for mutate in cases:
            value = self.snapshot(ring=True)
            mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(lab.LabError):
                self.parse(value)

    def test_empty_and_exact_item_flags_cannot_contradict_item_data(self):
        cases = (
            lambda v: v["amulet"].update(exactItem=True),
            lambda v: v["amulet"].update(item=self.item()),
            lambda v: v["amulet"].update(empty=False),
            lambda v: v["ring1"].update(exactItem=False),
        )
        for mutate in cases:
            value = self.snapshot(ring=True)
            mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(lab.LabError):
                self.parse(value)

    def test_truncated_or_noncomplete_component_evidence_is_rejected(self):
        cases = (
            lambda item: item.update(itemIdTruncated=True),
            lambda item: item.update(componentsTruncated=True),
            lambda item: item.update(componentDigestStatus="TRUNCATED"),
            lambda item: item.update(componentDigestStatus="UNSUPPORTED"),
        )
        for mutate in cases:
            value = self.snapshot(ring=True)
            mutate(value["ring1"]["item"])
            with self.subTest(mutate=mutate), self.assertRaises(lab.LabError):
                self.parse(value)

    def test_malformed_item_count_id_and_component_hash_are_rejected(self):
        cases = (
            lambda item: item.update(count=True),
            lambda item: item.update(count=0),
            lambda item: item.update(count=-1),
            lambda item: item.update(count="one"),
            lambda item: item.update(count=1.0),
            lambda item: item.update(itemId="Crystal Ring"),
            lambda item: item.update(itemId="aura:"),
            lambda item: item.update(componentSetSha256="A" * 64),
            lambda item: item.update(componentSetSha256="short"),
        )
        for mutate in cases:
            value = self.snapshot(ring=True)
            mutate(value["ring1"]["item"])
            with self.subTest(mutate=mutate), self.assertRaises(lab.LabError):
                self.parse(value)

    def test_accessory_requirement_accepts_empty_state_and_exact_ring_state(self):
        for value in (self.parse(), self.parse(self.snapshot(ring=True))):
            requirement = {"type": "accessory_slots", "slots": copy.deepcopy(value["slots"])}
            with patch.object(scenario_v2, "_scenario_observation", return_value=({}, value)):
                evidence = scenario_v2._assert_typed({}, requirement, {})
            self.assertEqual(evidence["assertion"], "accessory_slots")
            self.assertEqual(evidence["typed_observations"], [value])

    def test_accessory_requirement_rejects_a_different_exact_slot_state(self):
        value = self.parse(self.snapshot(ring=True))
        expected = copy.deepcopy(value["slots"])
        expected["ring1"]["count"] = 2
        requirement = {"type": "accessory_slots", "slots": expected}
        with patch.object(scenario_v2, "_scenario_observation", return_value=({}, value)):
            with self.assertRaises(lab.LabError) as raised:
                scenario_v2._assert_typed({}, requirement, {})
        self.assertEqual(raised.exception.evidence["typed_observations"], [value])


if __name__ == "__main__":
    unittest.main()
