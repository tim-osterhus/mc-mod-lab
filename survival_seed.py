"""Read only the no-cheat and empty-start fields of a closed level.dat."""

import gzip
from pathlib import Path
import struct
import zlib


MAX_NBT_BYTES = 16 * 1024 * 1024
FIELDS = {("Data", "allowCommands"), ("Data", "GameType"),
          ("Data", "Player", "Inventory"), ("Data", "Player", "EnderItems")}


class SeedError(ValueError):
    pass


class Reader:
    def __init__(self, data):
        self.data = data
        self.offset = 0
        self.fields = {}

    def take(self, length):
        if length < 0 or self.offset + length > len(self.data):
            raise SeedError("level.dat contains an invalid NBT length")
        start = self.offset
        self.offset += length
        return self.data[start:self.offset]

    def number(self, kind):
        return struct.unpack(">" + kind, self.take(struct.calcsize(kind)))[0]

    def string(self):
        try:
            return self.take(self.number("H")).decode("utf-8")
        except UnicodeError as exc:
            raise SeedError("level.dat contains invalid NBT text") from exc

    def payload(self, tag, path, depth=0):
        if depth > 32:
            raise SeedError("level.dat NBT nesting exceeds the bound")
        if tag in {1, 2, 3, 4, 5, 6}:
            kind = {1: "b", 2: "h", 3: "i", 4: "q", 5: "f", 6: "d"}[tag]
            value = self.number(kind)
            if path in FIELDS:
                if path in self.fields:
                    raise SeedError("level.dat contains duplicate required fields")
                self.fields[path] = (tag, value)
        elif tag == 7:
            self.take(self.number("i"))
        elif tag == 8:
            self.string()
        elif tag == 9:
            element = self.number("B")
            length = self.number("i")
            if length < 0 or length > MAX_NBT_BYTES or (element == 0 and length):
                raise SeedError("level.dat contains an invalid NBT list")
            if path in FIELDS:
                if path in self.fields or (element != 10 and not (element == 0 and length == 0)):
                    raise SeedError("level.dat contains an invalid inventory list")
                self.fields[path] = (tag, length)
            for _ in range(length):
                self.payload(element, path, depth + 1)
        elif tag == 10:
            while True:
                element = self.number("B")
                if element == 0:
                    break
                name = self.string()
                self.payload(element, path + (name,), depth + 1)
        elif tag in {11, 12}:
            length = self.number("i")
            self.take(length * (4 if tag == 11 else 8))
        else:
            raise SeedError("level.dat contains an unsupported NBT tag")


def inspect_seed(world):
    level = Path(world) / "level.dat"
    if level.is_symlink() or not level.is_file():
        raise SeedError("closed Survival seed is unavailable")
    try:
        with gzip.open(level, "rb") as source:
            data = source.read(MAX_NBT_BYTES + 1)
    except (OSError, EOFError, zlib.error) as exc:
        raise SeedError("closed Survival seed is unreadable") from exc
    if len(data) > MAX_NBT_BYTES:
        raise SeedError("closed Survival seed exceeds the NBT bound")
    reader = Reader(data)
    if reader.number("B") != 10:
        raise SeedError("level.dat root must be a compound")
    reader.string()
    reader.payload(10, ())
    if reader.offset != len(data):
        raise SeedError("level.dat contains trailing NBT data")
    fields = reader.fields
    if fields.get(("Data", "allowCommands")) != (1, 0):
        raise SeedError("Survival seed must have cheats disabled")
    if fields.get(("Data", "GameType")) != (3, 0):
        raise SeedError("Survival seed must have world game mode Survival")
    if fields.get(("Data", "Player", "Inventory")) != (9, 0):
        raise SeedError("Survival seed must have empty starting inventory")
    ender = fields.get(("Data", "Player", "EnderItems"))
    if ender is not None and ender != (9, 0):
        raise SeedError("Survival seed must have empty starting ender inventory")
    return {"status": "pass", "cheats_disabled": True, "world_survival": True,
            "starting_inventory_empty": True}
