"""Closed-save NBT preflight controls for fresh no-cheat Survival."""

import gzip
from pathlib import Path
import struct
import tempfile
import unittest

import survival_seed


def tag(kind, name, payload):
    encoded = name.encode("utf-8")
    return bytes([kind]) + struct.pack(">H", len(encoded)) + encoded + payload


def seed_bytes(cheats=0, gamemode=0, inventory=0, ender=0, inventory_type=10, ender_type=10):
    player = (tag(9, "Inventory", bytes([inventory_type]) + struct.pack(">i", inventory) + b"\x00" * inventory) +
              tag(9, "EnderItems", bytes([ender_type]) + struct.pack(">i", ender) + b"\x00" * ender) + b"\x00")
    data = (tag(1, "allowCommands", struct.pack(">b", cheats)) +
            tag(3, "GameType", struct.pack(">i", gamemode)) +
            tag(10, "Player", player) + b"\x00")
    return tag(10, "", tag(10, "Data", data) + b"\x00")


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.world = Path(self.temporary.name)

    def write(self, **kwargs):
        (self.world / "level.dat").write_bytes(gzip.compress(seed_bytes(**kwargs)))

    def test_fresh_no_cheat_empty_start(self):
        self.write()
        self.assertEqual(survival_seed.inspect_seed(self.world)["status"], "pass")

    def test_cheats_creative_and_seeded_inventory_refused(self):
        for values in ({"cheats": 1}, {"gamemode": 1}, {"inventory": 1}, {"ender": 1}):
            with self.subTest(values=values):
                self.write(**values)
                with self.assertRaises(survival_seed.SeedError):
                    survival_seed.inspect_seed(self.world)

    def test_vanilla_empty_end_tag_lists(self):
        for values in ({"inventory_type": 0}, {"ender_type": 0},
                       {"inventory_type": 0, "ender_type": 0}):
            with self.subTest(values=values):
                self.write(**values)
                self.assertEqual(survival_seed.inspect_seed(self.world)["status"], "pass")

    def test_end_tag_nonempty_and_wrong_inventory_types_refused(self):
        for values in ({"inventory_type": 0, "inventory": 1},
                       {"ender_type": 0, "ender": 1},
                       {"inventory_type": 1}, {"ender_type": 1}):
            with self.subTest(values=values):
                self.write(**values)
                with self.assertRaises(survival_seed.SeedError):
                    survival_seed.inspect_seed(self.world)

    def test_truncated_or_extra_data_refused(self):
        self.write()
        level = self.world / "level.dat"
        level.write_bytes(gzip.compress(gzip.decompress(level.read_bytes())[:-1]))
        with self.assertRaises(survival_seed.SeedError):
            survival_seed.inspect_seed(self.world)
        level.write_bytes(gzip.compress(seed_bytes() + b"extra"))
        with self.assertRaises(survival_seed.SeedError):
            survival_seed.inspect_seed(self.world)


if __name__ == "__main__":
    unittest.main()
