"""Validate bounded developer inspection without promoting it to gameplay proof."""

import re

import lab


REGISTRY_ID = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")
HASH = re.compile(r"^[0-9a-f]{64}$")


def _integer(value, minimum, maximum):
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _item(value):
    if not isinstance(value, dict) or not {"itemId", "count", "componentDigestComplete"} <= set(value) or not set(value) <= {
            "itemId", "count", "componentDigestComplete", "componentSha256"}:
        raise lab.LabError("inspection item shape is unavailable")
    value.setdefault("componentSha256", None)
    digest = value["componentSha256"]
    complete = value["componentDigestComplete"]
    if (not isinstance(value["itemId"], str) or len(value["itemId"]) > 128
            or not REGISTRY_ID.fullmatch(value["itemId"])
            or not _integer(value["count"], 1, 4096) or not isinstance(complete, bool)
            or (complete and (not isinstance(digest, str) or not HASH.fullmatch(digest)))
            or (not complete and digest is not None)):
        raise lab.LabError("inspection item identity is unavailable")


def screen_slots(value, envelope):
    required = {"screenClass", "stateSource", "serverAuthoritative", "slotCount", "slots"}
    if (not isinstance(value, dict) or not required <= set(value) or not set(value) <= required | {"hoveredIndex"}
            or value["stateSource"] != "client_menu_cache" or value["serverAuthoritative"] is not False
            or not isinstance(value["screenClass"], str) or not 1 <= len(value["screenClass"]) <= 160
            or not _integer(value["slotCount"], 0, 128) or not isinstance(value["slots"], list)
            or len(value["slots"]) != value["slotCount"]):
        raise lab.LabError("screen slot observation is not a bounded client menu")
    value.setdefault("hoveredIndex", None)
    hover = value["hoveredIndex"]
    if hover is not None and not _integer(hover, 0, value["slotCount"] - 1):
        raise lab.LabError("screen hovered slot is invalid")
    for index, slot in enumerate(value["slots"]):
        if (not isinstance(slot, dict) or not {"index", "x", "y"} <= set(slot)
                or not set(slot) <= {"index", "x", "y", "item"}
                or not _integer(slot["index"], index, index) or not _integer(slot["x"], -256, 8192)
                or not _integer(slot["y"], -256, 8192)):
            raise lab.LabError("screen slot geometry is invalid")
        slot.setdefault("item", None)
        if slot["item"] is not None:
            _item(slot["item"])
    if envelope.get("observation_source") != "client_or_integrated_server_pointer":
        raise lab.LabError("screen slot source is unavailable")
    return value


def block_entity_inventory(value, envelope, spec):
    if (not isinstance(value, dict) or set(value) != {
            "serverTick", "stateSource", "serverAuthoritative", "dimension", "x", "y", "z",
            "blockId", "blockEntityId", "hasInventory", "slotCount", "slots"}
            or value["stateSource"] != "integrated_server_block_entity_inventory"
            or value["serverAuthoritative"] is not True
            or envelope.get("observation_source") != "integrated_server_block_entity"
            or any(not _integer(value[k], -30000000 if k != "y" else -64,
                                30000000 if k != "y" else 319) or value[k] != spec[k]
                   for k in ("x", "y", "z"))
            or not isinstance(value["dimension"], str) or not REGISTRY_ID.fullmatch(value["dimension"])
            or any(not isinstance(value[k], str) or len(value[k]) > 128
                   or not REGISTRY_ID.fullmatch(value[k]) for k in ("blockId", "blockEntityId"))
            or not isinstance(value["hasInventory"], bool)
            or not _integer(value["slotCount"], 0, 64) or not isinstance(value["slots"], list)
            or len(value["slots"]) > value["slotCount"]):
        raise lab.LabError("block entity inspection is not a bounded server observation")
    tick = value["serverTick"]
    if (not _integer(tick, 0, 2 ** 63 - 1)
            or not _integer(envelope.get("server_tick_before"), 0, 2 ** 63 - 1)
            or not _integer(envelope.get("server_tick_after"), 0, 2 ** 63 - 1)
            or envelope.get("server_tick_before") != tick or envelope.get("server_tick_after") != tick):
        raise lab.LabError("block entity inspection is not from one server tick")
    if not value["hasInventory"] and (value["slotCount"] != 0 or value["slots"]):
        raise lab.LabError("non-inventory block entity has invented slots")
    previous = -1
    for slot in value["slots"]:
        if (not isinstance(slot, dict) or set(slot) != {"index", "item"}
                or not _integer(slot["index"], previous + 1, value["slotCount"] - 1)):
            raise lab.LabError("block entity slot index is invalid")
        _item(slot["item"])
        previous = slot["index"]
    return value


def chunk_presence(value, envelope, spec):
    if (not isinstance(value, dict) or set(value) != {
            "serverTick", "stateSource", "serverAuthoritative", "dimension",
            "x", "y", "z", "hasChunkAt", "entityTicking"}
            or value["stateSource"] != "integrated_server_chunk_presence"
            or value["serverAuthoritative"] is not True
            or envelope.get("observation_source") != "integrated_server_chunk_presence"
            or not isinstance(value["dimension"], str)
            or not REGISTRY_ID.fullmatch(value["dimension"])
            or len(value["dimension"]) > 128
            or any(not _integer(value[k], -30000000 if k != "y" else -64,
                                30000000 if k != "y" else 319) or value[k] != spec[k]
                   for k in ("x", "y", "z"))
            or type(value["hasChunkAt"]) is not bool
            or type(value["entityTicking"]) is not bool):
        raise lab.LabError("chunk presence is not a bounded server observation")
    tick = value["serverTick"]
    if (not _integer(tick, 0, 2 ** 63 - 1)
            or not _integer(envelope.get("server_tick_before"), 0, 2 ** 63 - 1)
            or not _integer(envelope.get("server_tick_after"), 0, 2 ** 63 - 1)
            or envelope["server_tick_before"] != tick or envelope["server_tick_after"] != tick):
        raise lab.LabError("chunk presence is not from one server tick")
    return value
