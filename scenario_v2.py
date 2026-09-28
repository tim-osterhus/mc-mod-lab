"""Bounded real-client scenarios; unsupported capabilities never become passes."""

import json
import math
import hashlib
import http.client
import os
from pathlib import Path
import re
import time
from uuid import UUID, uuid4
import zipfile

import contracts
import lab


SUPPORTED_OBSERVATIONS = {"world", "player", "screen", "frame"}
SUPPORTED_ACTIONS = {"press_key", "click", "click_button_index", "use_item"}
SCENARIO_OBSERVATIONS = {"server_tick", "player_inventory", "aura_block", "aura_block_server", "aura_pump_pair", "aura_storage_fixture", "aura_accessories", "ground_entities", "screen_slots", "block_entity_inventory", "hud_batch"}
SCENARIO_ACTIONS = {"select_hotbar", "drop_selected", "aim_at_block", "use_item_at_block", "use_selected_item", "set_crouch", "set_forward", "hud_start", "hud_stop", "animation_start", "animation_stop"}
SUPPORTED_REQUIREMENTS = {"screen_class", "world_name", "aura_increase", "inventory_conservation", "pump_accounting", "player_crouching", "storage_transfer", "stationary_entity_impulse", "accessory_slots"}
MAX_SCENARIO_RESPONSE_BYTES = 64 * 1024
UNCERTAIN_MARKER = ".mc-mod-lab-uncertain"
REGISTRY_ID = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")
HASH = re.compile(r"^[0-9a-f]{64}$")


def validate_scenario(value):
    contracts.schema_check(value, "scenario-v2")
    ids = [step["id"] for step in value["steps"]]
    if len(ids) != len(set(ids)):
        raise contracts.ContractError("duplicate scenario step id")
    if len(ids) > value.get("limits", {}).get("max_steps", 64):
        raise contracts.ContractError("scenario exceeds declared step limit")
    positions = {step["id"]: index for index, step in enumerate(value["steps"])}
    observations = {step["id"]: _typed_observations(step) for step in value["steps"]}
    for index, step in enumerate(value["steps"]):
        requirement = step.get("require")
        if requirement and requirement["type"] == "stationary_entity_impulse":
            refs = [requirement[k] for k in ("before", "after")]
            if any(ref not in positions for ref in refs) or not positions[refs[0]] < positions[refs[1]] < index:
                raise contracts.ContractError("entity observations must precede assertion in order")
            specs = [[s for s in observations[ref] if s["type"] == "ground_entities"] for ref in refs]
            if any(len(s) != 1 for s in specs) or specs[0] != specs[1]:
                raise contracts.ContractError("entity assertion requires the same bounded query")
            if requirement["minimum_speed"] > requirement["maximum_speed"]:
                raise contracts.ContractError("entity speed range is reversed")
            continue
        if requirement and requirement["type"] == "storage_transfer":
            refs = [requirement[key] for key in ("before", "after")]
            if any(ref not in positions for ref in refs) or not positions[refs[0]] < positions[refs[1]] < index:
                raise contracts.ContractError("storage observations must precede assertion in order")
            specs = [[s for s in observations[ref] if s["type"] == "aura_storage_fixture"] for ref in refs]
            if any(len(s) != 1 for s in specs) or specs[0] != specs[1]:
                raise contracts.ContractError("storage transfer requires identical fixture coordinates")
            target = specs[0][0]
            uses = [s["action"] for s in value["steps"][positions[refs[0]] + 1:positions[refs[1]]]
                    if s.get("action", {}).get("type") == "use_item_at_block"]
            matching = [a for a in uses if a.get("block_id") == "aura:bookshelf_coordinator"
                        and all(a.get(k) == target[k] for k in ("x", "y", "z"))]
            if len(matching) < max(1, requirement["transactions"]):
                raise contracts.ContractError("storage proof needs actual coordinator USE attempts between observations")
            continue
        if requirement and requirement["type"] == "pump_accounting":
            refs = [requirement[key] for key in ("before", "after", "end")]
            if any(ref not in positions for ref in refs) or not positions[refs[0]] < positions[refs[1]] < positions[refs[2]] < index:
                raise contracts.ContractError("pump accounting observations must precede it in order")
            specs = [[spec for spec in observations[ref] if spec["type"] == "aura_pump_pair"] for ref in refs]
            if any(len(items) != 1 for items in specs) or not specs[0] == specs[1] == specs[2]:
                raise contracts.ContractError("pump accounting requires one identical pair coordinate per observation")
            continue
        if not requirement or requirement["type"] not in {"aura_increase", "inventory_conservation"}:
            continue
        before_id, after_id = requirement["before"], requirement["after"]
        if before_id not in positions or after_id not in positions:
            raise contracts.ContractError("assertion refers to an unknown observation step")
        if not positions[before_id] < positions[after_id] < index:
            raise contracts.ContractError("assertion observations must precede it in order")
        expected_type = "aura_block_server" if requirement["type"] == "aura_increase" else "player_inventory"
        if not any(item["type"] == expected_type for item in observations[before_id]):
            raise contracts.ContractError("assertion before step lacks its typed observation")
        if not any(item["type"] == expected_type for item in observations[after_id]):
            raise contracts.ContractError("assertion after step lacks its typed observation")
        if expected_type == "aura_block_server":
            before = next(item for item in observations[before_id] if item["type"] == expected_type)
            after = next(item for item in observations[after_id] if item["type"] == expected_type)
            if (before["x"], before["y"], before["z"]) != (after["x"], after["y"], after["z"]):
                raise contracts.ContractError("aura assertion observations must target the same block")
    return value


def _typed_observations(step):
    return [item for item in step.get("observe", []) if isinstance(item, dict)]


def _observation_key(spec):
    if spec["type"] == "ground_entities":
        return (spec["type"], spec["radius"])
    result = (spec["type"], spec.get("x"), spec.get("y"), spec.get("z"))
    return (*result, spec["target_y"]) if spec["type"] == "aura_pump_pair" else result


def verify_packaged_artifact(identity, scenario, artifact):
    artifact = Path(artifact)
    if not artifact.is_absolute() or artifact.is_symlink() or not artifact.is_file():
        raise lab.LabError("packaged artifact must be a local regular file")
    game_dir = Path(identity["game_dir"])
    if game_dir.is_symlink() or (game_dir / "mods").is_symlink():
        raise lab.LabError("packaged profile and mods directory must not be symlinks")
    try:
        mods = (game_dir / "mods").resolve(strict=True)
    except OSError as exc:
        raise lab.LabError("packaged profile mods directory is unavailable") from exc
    if artifact.resolve(strict=True).parent != mods or artifact.suffix.lower() != ".jar":
        raise lab.LabError("packaged artifact must be in the isolated profile mods directory")
    expected = scenario["runtime"]
    actual_hash = lab.sha256(artifact)
    if actual_hash != expected["artifact_sha256"]:
        raise lab.LabError("packaged artifact hash differs from scenario")
    matches = []
    for jar in mods.glob("*.jar"):
        if jar.is_symlink():
            raise lab.LabError("mods directory contains a symlink")
        try:
            with zipfile.ZipFile(jar) as archive:
                meta = json.loads(archive.read("fabric.mod.json"))
        except (OSError, zipfile.BadZipFile, KeyError, ValueError):
            raise lab.LabError("mods directory contains an unreadable Fabric JAR")
        if meta.get("id") == expected["mod_id"]:
            matches.append((jar.resolve(), meta.get("version")))
    if matches != [(artifact.resolve(), expected["mod_version"])]:
        raise lab.LabError("loaded mod ID/version is ambiguous or differs from packaged artifact")
    log = Path(identity["launch_log"]).read_text(encoding="utf-8", errors="replace")[:1024 * 1024]
    mod_line = re.compile(r"^\s*-\s+" + re.escape(expected["mod_id"]) + r"\s+" +
                          re.escape(expected["mod_version"]) + r"(?:\s|$)", re.MULTILINE)
    if not re.search(r"Loading\s+\d+\s+mods?:", log) or not mod_line.search(log):
        raise lab.LabError("fresh Fabric log does not identify packaged mod ID/version")
    return actual_hash


class ControlLease:
    def __init__(self, identity):
        self.identity = identity
        self.path = Path(identity["game_dir"]) / ".mc-mod-lab-control.lock"
        self.nonce = uuid4().hex
        self.acquired = False
        self.entered = False

    def enter(self):
        if self.acquired:
            return
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise lab.LabError("another control lease exists for this profile") from exc
        except OSError as exc:
            raise lab.LabError("control lease could not be acquired") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"pid": self.identity["pid"], "nonce": self.nonce}, stream)
        self.acquired = True
        result = lab.command(self.identity, "enter_control_mode")
        if not isinstance(result, dict) or result.get("control_mode") is not True:
            raise lab.LabError("bridge did not enter control mode", "fail")
        self.entered = True

    def release(self):
        status = "pass"
        reason = None
        if self.acquired:
            try:
                result = lab.command(self.identity, "exit_control_mode")
                if not isinstance(result, dict) or result.get("control_mode") is not False:
                    raise lab.LabError("bridge did not release control", "fail")
            except lab.LabError:
                status, reason = "fail", "bridge did not confirm neutral manual control"
                _mark_uncertain(self.identity)
        if self.acquired and status == "pass":
            try:
                contents = json.loads(self.path.read_text(encoding="utf-8"))
                if contents.get("nonce") != self.nonce:
                    raise ValueError("lease changed")
                self.path.unlink()
            except (OSError, ValueError, KeyError, TypeError):
                status, reason = "fail", "control lease could not be safely released"
        return {"status": status, **({"reason": reason} if reason else {})}


def scenario_request(identity, kind, name, params):
    """Send one fixed authenticated scenario operation to the selected bridge."""
    if "game_dir" in identity and (Path(identity["game_dir"]) / UNCERTAIN_MARKER).exists():
        raise lab.LabError("profile has an uncertain action outcome; use a clean seed", "fail")
    if kind not in {"observe", "action"}:
        raise lab.LabError("scenario request kind is unavailable")
    if kind == "observe" and name not in SCENARIO_OBSERVATIONS:
        raise lab.LabError("scenario observer capability is unavailable")
    if kind == "action" and name not in SCENARIO_ACTIONS:
        raise lab.LabError("scenario action capability is unavailable")
    token = os.environ.get("MC_MOD_LAB_TOKEN", "")
    if len(token) < 32 or "\n" in token or "\r" in token:
        raise lab.LabError("MC_MOD_LAB_TOKEN must be a 32+ character per-session secret")
    lab.listening_socket(identity["pid"], identity["port"])
    request = {"schema_version": 2, "kind": kind, "name": name, "params": params}
    body = json.dumps(request, separators=(",", ":")).encode("utf-8")
    connection = http.client.HTTPConnection("127.0.0.1", identity["port"], timeout=8)
    try:
        connection.request("POST", "/api/scenario/v2",
                           body=body,
                           headers={"Content-Type": "application/json",
                                    "Authorization": "Bearer " + token})
        response = connection.getresponse()
        raw = response.read(MAX_SCENARIO_RESPONSE_BYTES + 1)
        status_code = response.status
        if len(raw) > MAX_SCENARIO_RESPONSE_BYTES:
            raise lab.LabError("scenario bridge response exceeds the fixed output limit", "unsupported")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise lab.LabError("scenario bridge response is invalid", "fail") from exc
        if status_code != 200:
            if status_code in {503, 504} or (status_code == 422 and isinstance(result, dict)
                                              and result.get("status") == "unsupported"):
                raise lab.LabError("scenario bridge capability is unavailable")
            raise lab.LabError("scenario bridge rejected the typed request", "fail")
        if not isinstance(result, dict) or result.get("schema_version") != 2:
            raise lab.LabError("scenario bridge response envelope is invalid", "fail")
        if result.get("status") == "unsupported":
            raise lab.LabError("scenario bridge capability is unavailable")
        if (result.get("status") != "ok" or result.get("kind") != kind
                or result.get("name") != name or "result" not in result):
            raise lab.LabError("scenario bridge response does not match the typed request", "fail")
        for key in ("server_tick_before", "server_tick_after"):
            if key in result and (isinstance(result[key], bool) or not isinstance(result[key], int)
                                  or result[key] < 0):
                raise lab.LabError("scenario bridge returned an invalid server tick", "unsupported")
        if ("server_tick_before" in result and "server_tick_after" in result
                and result["server_tick_after"] < result["server_tick_before"]):
            raise lab.LabError("scenario bridge server tick moved backwards", "unsupported")
        if kind == "action":
            _validate_action_ack(result["result"], name)
        return result
    except (lab.LabError, OSError, http.client.HTTPException, ValueError) as exc:
        # Once sending starts, any unvalidated outcome may have changed the save.
        if kind == "action":
            _mark_uncertain(identity)
        if isinstance(exc, lab.LabError):
            raise
        raise lab.LabError("scenario bridge request failed", "fail") from exc
    finally:
        connection.close()


def _mark_uncertain(identity):
    # Dispatch may already have started when its response times out. Never retry this save.
    (Path(identity["game_dir"]) / UNCERTAIN_MARKER).write_text(
        "Typed action outcome uncertain; discard this profile and recreate from a clean seed.\n",
        encoding="utf-8")


def _scenario_observation(identity, spec):
    name = spec["type"]
    if name in {"aura_block", "aura_block_server", "aura_pump_pair", "aura_storage_fixture", "block_entity_inventory"}:
        params = {key: spec[key] for key in ("x", "y", "z")}
        if name == "aura_pump_pair":
            params["target_y"] = spec["target_y"]
    elif name == "ground_entities":
        params = {"radius": spec["radius"]}
    else:
        params = {}
    envelope = scenario_request(identity, "observe", name, params)
    value = envelope["result"]
    if name == "aura_accessories":
        value = _accessory_snapshot(value, envelope)
    if name == "ground_entities":
        value = _ground_entities_snapshot(value, envelope, spec)
    if name == "aura_storage_fixture":
        value = _storage_fixture_snapshot(value, envelope, spec)
    if name == "aura_pump_pair":
        value = _pump_pair_snapshot(value, envelope, spec)
    if name in {"screen_slots", "block_entity_inventory"}:
        import developer_inspection
        value = (developer_inspection.screen_slots(value, envelope) if name == "screen_slots"
                 else developer_inspection.block_entity_inventory(value, envelope, spec))
    if name == "server_tick":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise lab.LabError("server tick observation is unavailable")
    elif name == "player_inventory":
        if (not isinstance(value, dict) or not isinstance(value.get("stacks"), list)
                or not isinstance(value.get("truncated"), bool)):
            raise lab.LabError("player inventory observation has an unsupported shape")
        if (value.get("serverAuthoritative") is not True
                or value.get("stateSource") != "integrated_server_inventory"):
            raise lab.LabError("inventory conservation requires a server-authoritative snapshot")
        ticks = (envelope.get("server_tick_before"), value.get("serverTick"),
                 envelope.get("server_tick_after"))
        if (any(isinstance(t, bool) or not isinstance(t, int) for t in ticks)
                or not ticks[0] <= ticks[1] <= ticks[2]):
            raise lab.LabError("inventory snapshot tick is not bound to its observation")
    elif name in {"aura_block", "aura_block_server"}:
        if (not isinstance(value, dict) or any(value.get(key) != spec[key] for key in ("x", "y", "z"))
                or not isinstance(value.get("serverAuthoritative"), bool)):
            raise lab.LabError("Aura block observation has an unsupported shape")
        if name == "aura_block_server" and (value["serverAuthoritative"] is not True
                                             or value.get("stateSource") != "integrated_server_block_entity"):
            raise lab.LabError("server Aura block observation is not authoritative")
        if name == "aura_block_server":
            tick = value.get("serverTick")
            before, after = envelope.get("server_tick_before"), envelope.get("server_tick_after")
            if (any(isinstance(v, bool) or not isinstance(v, int) for v in (tick, before, after))
                    or not before <= tick <= after):
                raise lab.LabError("server Aura snapshot tick is not bound to its observation")
    return envelope, value


def _accessory_snapshot(value, envelope):
    if (not isinstance(value, dict) or value.get("serverAuthoritative") is not True
            or value.get("stateSource") != "integrated_server_aura_accessories"):
        raise lab.LabError("accessory snapshot is not server-authoritative")
    tick = value.get("serverTick")
    if (isinstance(tick, bool) or not isinstance(tick, int) or tick < 0
            or envelope.get("server_tick_before") != tick or envelope.get("server_tick_after") != tick):
        raise lab.LabError("accessory snapshot must be atomic within one server tick")
    try:
        uid = str(UUID(value["playerUuid"]))
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise lab.LabError("accessory player identity unavailable") from exc
    slots = {}
    for name, index in (("amulet", 0), ("ring1", 1), ("ring2", 2), ("belt", 3), ("cursor", -1)):
        slot = value.get(name)
        if (not isinstance(slot, dict) or slot.get("slot") != name
                or isinstance(slot.get("index"), bool) or slot.get("index") != index
                or not isinstance(slot.get("empty"), bool)):
            raise lab.LabError("accessory slot identity unavailable")
        item = slot.get("item")
        if slot["empty"]:
            if item is not None or slot.get("exactItem") is not False:
                raise lab.LabError("empty accessory slot contradicts item data")
            slots[name] = None
        else:
            section = "menu_cursor" if name == "cursor" else "accessory"
            if (slot.get("exactItem") is not True or not _component_complete(item)
                    or item.get("section") != section or isinstance(item.get("slot"), bool)
                    or item.get("slot") != index):
                raise lab.LabError("accessory item components or slot are incomplete")
            slots[name] = {"item_id": item["itemId"], "count": item["count"],
                           "component_sha256": item["componentSetSha256"]}
    return {"type": "aura_accessories", "server_authoritative": True, "server_tick": tick,
            "player_key": hashlib.sha256(uid.encode("ascii")).hexdigest(), "slots": slots}


def _ground_entities_snapshot(value, envelope, spec):
    if (not isinstance(value, dict) or value.get("serverAuthoritative") is not True
            or value.get("stateSource") != "integrated_server_ground_entities"
            or value.get("radius") != spec["radius"]):
        raise lab.LabError("ground entity authority or radius unavailable")
    tick = value.get("serverTick")
    if (isinstance(tick, bool) or not isinstance(tick, int) or tick < 0
            or envelope.get("server_tick_before") != tick or envelope.get("server_tick_after") != tick):
        raise lab.LabError("ground entities must be atomic within one server tick")
    dimension = value.get("dimensionId")
    if not isinstance(dimension, str) or not REGISTRY_ID.fullmatch(dimension):
        raise lab.LabError("ground entity dimension unavailable")
    def vector(v):
        if not isinstance(v, dict) or set(v) != {"x", "y", "z"}:
            raise lab.LabError("entity vector unavailable")
        if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in v.values()):
            raise lab.LabError("entity vector must be finite")
        return dict(v)
    rows = value.get("entities")
    if not isinstance(rows, list) or len(rows) > 64:
        raise lab.LabError("ground entity coverage unavailable")
    output, seen = [], set()
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("entityId"), str)
                or not REGISTRY_ID.fullmatch(row["entityId"]) or not isinstance(row.get("alive"), bool)):
            raise lab.LabError("entity identity unavailable")
        try:
            uid = str(UUID(row["uuid"]))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise lab.LabError("entity UUID unavailable") from exc
        if uid in seen:
            raise lab.LabError("duplicate entity identity")
        seen.add(uid)
        entry = {"entity_id": row["entityId"], "entity_key": hashlib.sha256(uid.encode("ascii")).hexdigest(),
                 "alive": row["alive"], "position": vector(row.get("position")), "velocity": vector(row.get("velocity"))}
        health = row.get("health")
        if health is not None:
            if isinstance(health, bool) or not isinstance(health, (int, float)) or not math.isfinite(health) or health < 0:
                raise lab.LabError("entity health unavailable")
            entry["health"] = health
        item = row.get("item")
        if item is not None:
            entry["item_components_complete"] = _component_complete(item)
            if entry["item_components_complete"]:
                entry["item"] = {"item_id": item["itemId"], "count": item["count"], "component_sha256": item["componentSetSha256"]}
        output.append(entry)
    return {"type": "ground_entities", "server_authoritative": True, "server_tick": tick,
            "radius": spec["radius"], "dimension": dimension, "player_position": vector(value.get("playerPosition")),
            "entities": output}


def _storage_fixture_snapshot(value, envelope, spec):
    if (not isinstance(value, dict) or value.get("serverAuthoritative") is not True
            or value.get("stateSource") != "integrated_server_storage_fixture"
            or any(value.get(key) != spec[key] for key in ("x", "y", "z"))):
        raise lab.LabError("storage fixture identity or authority unavailable")
    tick = value.get("serverTick")
    if (isinstance(tick, bool) or not isinstance(tick, int) or tick < 0
            or envelope.get("server_tick_before") != tick or envelope.get("server_tick_after") != tick):
        raise lab.LabError("storage fixture must be atomic within one server tick")
    for name, dx, kind, block in (("shelf", 1, "STORAGE_BOOKSHELF", "aura:storage_bookshelf"),
                                  ("powerNode", -1, "NODE", "aura:aura_node")):
        member = value.get(name, {})
        if (member.get("serverTick") != tick or member.get("serverAuthoritative") is not True
                or member.get("stateSource") != "integrated_server_block_entity"
                or (member.get("x"), member.get("y"), member.get("z")) != (spec["x"] + dx, spec["y"], spec["z"])
                or member.get("kind") != kind or member.get("blockId") != block):
            raise lab.LabError("storage fixture member identity or timing unavailable")
    inventory = value.get("inventory", {})
    if (inventory.get("serverTick") != tick or inventory.get("serverAuthoritative") is not True
            or inventory.get("stateSource") != "integrated_server_inventory"):
        raise lab.LabError("storage fixture inventory must be atomic and authoritative")
    parsed = _inventory_snapshot(inventory)
    shelf = value["shelf"].get("bookshelf", {})
    entries = shelf.get("entries")
    if (not parsed["complete"] or shelf.get("hasBook") is not True
            or shelf.get("entriesTruncated") is not False or shelf.get("entryDigestStatus") != "COMPLETE"
            or not isinstance(entries, list) or len(entries) > 64
            or any(not _component_complete(entry) for entry in entries)
            or shelf.get("storedTypes") != len(entries)
            or shelf.get("storedItemCount") != sum(entry["count"] for entry in entries)):
        raise lab.LabError("storage fixture requires complete component identities and counts")
    power = value.get("availablePower")
    if (isinstance(power, bool) or not isinstance(power, int) or power < 0
            or value.get("requiredPower") != 5 or value["powerNode"].get("node", {}).get("storedPower") != power):
        raise lab.LabError("storage fixture power accounting unavailable")
    def portable(stacks):
        return sorted(({"item_id": s["itemId"], "count": s["count"], "component_sha256": s["componentSetSha256"]}
                       for s in stacks), key=lambda s: (s["item_id"], s["component_sha256"], s["count"]))
    return {"type": "aura_storage_fixture", "server_authoritative": True, "server_tick": tick,
            "x": spec["x"], "y": spec["y"], "z": spec["z"], "power": power, "transaction_cost": 5,
            "inventory": portable(parsed["stacks"]), "storage": portable(entries)}


def _pump_pair_snapshot(value, envelope, spec):
    if (not isinstance(value, dict) or value.get("serverAuthoritative") is not True
            or value.get("stateSource") != "integrated_server_pump_pair"):
        raise lab.LabError("pump pair must be server authoritative")
    tick = value.get("serverTick")
    if (isinstance(tick, bool) or not isinstance(tick, int)
            or envelope.get("server_tick_before") != tick or envelope.get("server_tick_after") != tick):
        raise lab.LabError("pump pair must be atomic within one server tick")
    for name, y, kind, block in (("pump", spec["y"], "PUMP", "aura:aura_node_pump"),
                                  ("target", spec["target_y"], "NODE", "aura:aura_node")):
        snapshot = value.get(name, {})
        if (snapshot.get("serverTick") != tick or snapshot.get("serverAuthoritative") is not True
                or snapshot.get("stateSource") != "integrated_server_block_entity"
                or (snapshot.get("x"), snapshot.get("y"), snapshot.get("z")) != (spec["x"], y, spec["z"])
                or snapshot.get("kind") != kind or snapshot.get("blockId") != block
                or snapshot.get("serverWorldGameTime") != value.get("worldGameTime")):
            raise lab.LabError("pump pair member identity or timing is unsupported")
    inventory = value.get("inventory", {})
    if inventory.get("serverTick") != tick:
        raise lab.LabError("pump pair inventory is not atomic")
    inventory = _inventory_snapshot(inventory)
    if not inventory["complete"] or not inventory["server_authoritative"]:
        raise lab.LabError("pump pair needs complete authoritative inventory")
    pump, target = value["pump"]["pump"], value["target"]["node"]
    for state in (pump, target):
        amounts = state.get("auraByColor", {})
        if not amounts or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in amounts.values()):
            raise lab.LabError("pump pair aura components unavailable")
        if sum(amounts.values()) != state.get("totalAura") or sum(v for k, v in amounts.items() if k != "white"):
            raise lab.LabError("core pump fixture requires only White aura")
    result = {"type": "aura_pump_pair", "server_authoritative": True, "server_tick": tick,
              "world_time": value.get("worldGameTime"), "x": spec["x"], "y": spec["y"],
              "z": spec["z"], "target_y": spec["target_y"], "pump_aura": pump["totalAura"],
              "target_aura": target["totalAura"], "power": pump.get("power"), "speed": pump.get("speed"),
              "blocked": value.get("routeBlocked"), "inhibited": pump.get("inhibited"),
              "ground_coal": value.get("nearbyCoalCount"),
              "inventory_coal": sum(s["count"] for s in inventory["stacks"] if s["itemId"] == "minecraft:coal")}
    for key in ("world_time", "pump_aura", "target_aura", "power", "speed", "ground_coal", "inventory_coal"):
        if isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0:
            raise lab.LabError("pump pair numeric field is unavailable")
    if not isinstance(result["blocked"], bool) or not isinstance(result["inhibited"], bool):
        raise lab.LabError("pump pair route state is unavailable")
    return result


def _component_complete(stack):
    return (isinstance(stack, dict) and stack.get("itemIdTruncated") is False
            and stack.get("componentBasis") == "patch_against_pinned_registry_defaults"
            and stack.get("componentsTruncated") is False
            and stack.get("componentDigestStatus") == "COMPLETE"
            and isinstance(stack.get("itemId"), str) and REGISTRY_ID.fullmatch(stack["itemId"]) is not None
            and isinstance(stack.get("count"), int) and not isinstance(stack.get("count"), bool)
            and stack["count"] > 0
            and isinstance(stack.get("componentSetSha256"), str)
            and HASH.fullmatch(stack["componentSetSha256"]) is not None)


def _inventory_snapshot(value):
    stacks = value["stacks"]
    complete = not value["truncated"] and all(_component_complete(stack) for stack in stacks)
    if len(stacks) > 41:
        complete = False
    if complete:
        entries = sorted((stack["itemId"], stack["componentSetSha256"], stack["count"])
                         for stack in stacks)
        canonical = json.dumps(entries, separators=(",", ":"), ensure_ascii=True)
        digest = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    else:
        digest = None
    authoritative = (value.get("serverAuthoritative") is True
                     and value.get("stateSource") == "integrated_server_inventory")
    return {"complete": complete, "stack_count": len(stacks), "digest": digest, "stacks": stacks,
            "server_authoritative": authoritative}


def _aura_snapshot_digest(value):
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _kind(step):
    return next(key for key in ("observe", "action", "wait", "require") if key in step)


def missing_capability(step):
    kind = _kind(step)
    if kind == "observe":
        missing = {item for item in step["observe"]
                   if isinstance(item, str) and item not in SUPPORTED_OBSERVATIONS}
        return "observer capability unavailable: " + ", ".join(sorted(missing)) if missing else None
    if kind == "action":
        action = step["action"]["type"]
        return ("action capability unavailable: " + action
                if action not in SUPPORTED_ACTIONS | SCENARIO_ACTIONS | {"capture_hud_trace", "capture_animation"} else None)
    if kind == "wait":
        return ("server game-tick wait capability unavailable"
                if step["wait"]["type"] != "ticks" else None)
    requirement = step["require"]["type"]
    return ("assertion observer unavailable: " + requirement
            if requirement not in SUPPORTED_REQUIREMENTS else None)


def _validate_action_ack(result, name):
    if not isinstance(result, dict):
        raise lab.LabError("scenario action acknowledgement has an unsupported shape", "fail")
    outcome = result.get("status")
    if isinstance(outcome, str) and outcome.casefold() == "unsupported":
        raise lab.LabError("scenario action capability is unavailable")
    if isinstance(outcome, str) and outcome.casefold() in {"rejected", "error", "failed"}:
        raise lab.LabError("scenario action was rejected", "fail")
    if result.get("accepted") is False or result.get("dispatched") is False:
        raise lab.LabError("scenario action was not dispatched", "fail")
    if result.get("action") != name or outcome not in {"input_dispatched", "already_satisfied"}:
        raise lab.LabError("scenario action acknowledgement is invalid", "fail")
    calls = result.get("inputCalls")
    if isinstance(calls, bool) or not isinstance(calls, int) or not 0 <= calls <= 64:
        raise lab.LabError("scenario action input count is invalid", "fail")
    if name in {"hud_start", "hud_stop", "animation_start", "animation_stop"}:
        try:
            if str(UUID(result["traceId"])) != result["traceId"]:
                raise ValueError("noncanonical trace")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise lab.LabError("capture acknowledgement lacks a canonical trace ID", "fail") from exc


def _route_action(identity, action):
    name = action["type"]
    params = {key: value for key, value in action.items() if key != "type"}
    if name in {"select_hotbar", "use_selected_item"}:
        params["item_id"] = params.pop("item")
    envelope = scenario_request(identity, "action", name, params)
    result = envelope["result"]
    _validate_action_ack(result, name)
    outcome = result["status"]
    evidence = {"action_type": name, "acknowledged": True}
    if isinstance(outcome, str):
        evidence["acknowledgement_status"] = outcome[:32]
    for source, target in (("server_tick_before", "server_tick_before"),
                           ("server_tick_after", "server_tick_after")):
        if source in envelope:
            evidence[target] = envelope[source]
    return evidence


def _wait_ticks(identity, count, wall_deadline, cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise lab.LabError("runtime memory guard or cancellation triggered", "fail")
    _envelope, start_tick = _scenario_observation(identity, {"type": "server_tick"})
    current_tick = start_tick
    while current_tick - start_tick < count:
        if cancel_event is not None and cancel_event.is_set():
            raise lab.LabError("runtime memory guard or cancellation triggered", "fail")
        remaining = wall_deadline - time.monotonic()
        if remaining <= 0:
            raise lab.LabError("scenario wall-time limit exceeded while waiting for server ticks", "fail")
        time.sleep(min(0.1, remaining))
        _envelope, observed_tick = _scenario_observation(identity, {"type": "server_tick"})
        if observed_tick < current_tick:
            raise lab.LabError("observed server tick moved backwards", "unsupported")
        current_tick = observed_tick
    return {"server_tick_before": start_tick, "server_tick_after": current_tick,
            "ticks_elapsed": current_tick - start_tick, "ticks_requested": count}


def _find_observation(observations, step_id, name):
    records = observations.get(step_id, {})
    matches = [record for key, record in records.items() if key[0] == name]
    if len(matches) != 1:
        raise lab.LabError("required typed observation is unavailable")
    return matches[0]


def _aura_numeric_value(snapshot, metric, color=None):
    kind = snapshot.get("kind")
    state_key = "pump" if kind == "PUMP" else "node" if kind == "NODE" else None
    state = snapshot.get(state_key) if state_key else None
    if not isinstance(state, dict):
        raise lab.LabError("Aura block kind does not provide the requested field")
    if metric == "aura_by_color":
        values = state.get("auraByColor")
        if not isinstance(values, dict):
            raise lab.LabError("Aura color values are unavailable")
        value = next((candidate for key, candidate in values.items()
                      if isinstance(key, str) and key.casefold() == color), None)
    elif metric == "total_aura":
        value = state.get("totalAura")
    elif metric == "stored_power":
        value = state.get("storedPower")
    elif metric in {"power", "speed"} and kind == "PUMP":
        value = state.get(metric)
    else:
        raise lab.LabError("Aura block kind does not provide the requested field")
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value)):
        raise lab.LabError("Aura field value is unavailable")
    return value


def _inventory_groups(snapshot):
    groups = {}
    for stack in snapshot["stacks"]:
        key = (stack["itemId"], stack["componentSetSha256"])
        groups[key] = groups.get(key, 0) + stack["count"]
    return groups


def _assert_entity_impulse(requirement, observations):
    before, after = [_find_observation(observations, requirement[k], "ground_entities")["value"]
                     for k in ("before", "after")]
    targets = [[row for row in snapshot["entities"] if row["entity_id"] == requirement["entity_id"]]
               for snapshot in (before, after)]
    if any(len(rows) != 1 for rows in targets):
        raise lab.LabError("impulse proof requires one unambiguous target", "fail")
    left, right = targets[0][0], targets[1][0]
    speed = math.sqrt(sum(v * v for v in right["velocity"].values()))
    initial_speed = math.sqrt(sum(v * v for v in left["velocity"].values()))
    outward = sum(right["velocity"][axis] * (right["position"][axis] - after["player_position"][axis])
                  for axis in ("x", "y", "z"))
    distance = math.sqrt(sum((right["position"][axis] - after["player_position"][axis]) ** 2
                             for axis in ("x", "y", "z")))
    evidence = {"assertion": "stationary_entity_impulse", "entity_key": right["entity_key"],
                "before_value": initial_speed, "after_value": speed, "observed": speed,
                "minimum_speed": requirement["minimum_speed"], "maximum_speed": requirement["maximum_speed"],
                "server_authoritative": True}
    if "expected_distance" in requirement:
        evidence["observed_distance"] = distance
    valid = (before["server_tick"] < after["server_tick"] and before["dimension"] == after["dimension"]
             and before["player_position"] == after["player_position"]
             and left["entity_key"] == right["entity_key"] and left["alive"] and right["alive"]
             and left.get("health") is not None and left["health"] == right.get("health")
             and left["position"] == right["position"] and initial_speed <= 0.001
             and ("expected_distance" not in requirement or abs(distance - requirement["expected_distance"]) <= 0.001)
             and requirement["minimum_speed"] <= speed <= requirement["maximum_speed"]
             and (requirement["minimum_speed"] == 0 or outward > 0))
    if not valid:
        error = lab.LabError("controlled entity identity, fixed positions or outward impulse contradicted expectation", "fail")
        error.evidence = evidence
        raise error
    return evidence


def _assert_storage_transfer(requirement, observations):
    left, right = [_find_observation(observations, requirement[k], "aura_storage_fixture")["value"]
                   for k in ("before", "after")]
    def groups(rows):
        result = {}
        for row in rows:
            key = row["item_id"], row["component_sha256"]
            result[key] = result.get(key, 0) + row["count"]
        return result
    li, ri, ls, rs = [groups(rows) for rows in (left["inventory"], right["inventory"], left["storage"], right["storage"])]
    keys = li.keys() | ri.keys() | ls.keys() | rs.keys()
    deltas = {k: rs.get(k, 0) - ls.get(k, 0) for k in keys}
    actual = sum(deltas.values())
    expected = requirement["count"] * (-1 if requirement["direction"] == "withdraw" else 1)
    evidence = {"assertion": "storage_transfer", "server_authoritative": True,
                "before_value": left["power"], "after_value": right["power"],
                "actual_count_delta": actual, "expected_count_delta": expected}
    valid = (all(left[k] == right[k] for k in ("x", "y", "z", "transaction_cost"))
             and right["server_tick"] > left["server_tick"]
             and all(li.get(k, 0) + ls.get(k, 0) == ri.get(k, 0) + rs.get(k, 0) for k in keys)
             and actual == expected and sum(v != 0 for v in deltas.values()) == requirement["component_types"]
             and all(v <= 0 if expected < 0 else v >= 0 for v in deltas.values())
             and left["power"] - right["power"] == 5 * requirement["transactions"])
    if not valid:
        error = lab.LabError("storage count/component conservation or transaction power contradicted expectation", "fail")
        error.evidence = evidence
        raise error
    return evidence


def _assert_typed(identity, requirement, observations):
    if requirement["type"] == "accessory_slots":
        _, value = _scenario_observation(identity, {"type": "aura_accessories"})
        evidence = {"assertion": "accessory_slots", "typed_observations": [value]}
        if value["slots"] != requirement["slots"]:
            error = lab.LabError("server accessory slots contradict expected exact state", "fail")
            error.evidence = evidence
            raise error
        return evidence
    if requirement["type"] == "stationary_entity_impulse":
        return _assert_entity_impulse(requirement, observations)
    if requirement["type"] == "storage_transfer":
        return _assert_storage_transfer(requirement, observations)
    if requirement["type"] == "pump_accounting":
        return _assert_pump_accounting(requirement, observations)
    if requirement["type"] == "aura_increase":
        before = _find_observation(observations, requirement["before"], "aura_block_server")
        after = _find_observation(observations, requirement["after"], "aura_block_server")
        left, right = before["value"], after["value"]
        if (left.get("serverAuthoritative") is not True or right.get("serverAuthoritative") is not True
                or left.get("stateSource") != "integrated_server_block_entity"
                or right.get("stateSource") != "integrated_server_block_entity"):
            raise lab.LabError("exact Aura assertion needs authoritative block observations")
        if (left.get("x"), left.get("y"), left.get("z"), left.get("blockId"), left.get("kind")) != (
                right.get("x"), right.get("y"), right.get("z"), right.get("blockId"), right.get("kind")):
            raise lab.LabError("Aura block identity changed between required observations", "fail")
        metric = requirement["metric"]
        color = requirement.get("color")
        before_value = _aura_numeric_value(left, metric, color)
        after_value = _aura_numeric_value(right, metric, color)
        delta = after_value - before_value
        evidence = {"assertion": "aura_increase", "metric": metric,
                    "before_value": before_value, "after_value": after_value,
                    "delta": delta, "minimum_delta": requirement["minimum_delta"],
                    "server_authoritative": True,
                    "x": left["x"], "y": left["y"], "z": left["z"],
                    "block_id": left["blockId"], "aura_kind": left["kind"]}
        if color is not None:
            evidence["color"] = color
        if delta < requirement["minimum_delta"]:
            error = lab.LabError("observed Aura value did not increase by the required amount", "fail")
            error.evidence = evidence
            raise error
        return evidence

    before = _find_observation(observations, requirement["before"], "player_inventory")
    after = _find_observation(observations, requirement["after"], "player_inventory")
    left, right = before["value"], after["value"]
    if not left.get("server_authoritative") or not right.get("server_authoritative"):
        raise lab.LabError("exact inventory conservation needs authoritative inventory observations")
    if not left["complete"] or not right["complete"]:
        raise lab.LabError("exact inventory conservation needs complete component digests")
    before_groups = _inventory_groups(left)
    after_groups = _inventory_groups(right)
    before_count = sum(count for (item, _), count in before_groups.items() if item == requirement["item_id"])
    after_count = sum(count for (item, _), count in after_groups.items() if item == requirement["item_id"])
    changed_target_groups = []
    pickup = requirement.get("pickup_item_id")
    if pickup == requirement["item_id"]:
        raise lab.LabError("pickup and consumed item must differ")
    pickup_changes = []
    actual_delta = 0
    for key in set(before_groups) | set(after_groups):
        change = after_groups.get(key, 0) - before_groups.get(key, 0)
        if key[0] == requirement["item_id"]:
            if "expected_component_sha256" in requirement and key[1] != requirement["expected_component_sha256"]:
                raise lab.LabError("target inventory components differ from the declared exact item", "fail")
            if change:
                changed_target_groups.append(change)
                actual_delta += change
        elif key[0] == pickup:
            if before_groups.get(key, 0):
                raise lab.LabError("expected pickup was already in the baseline inventory", "fail")
            if change:
                pickup_changes.append(change)
        elif change:
            raise lab.LabError("unrelated inventory stack count or components changed", "fail")
    if pickup is not None and pickup_changes != [1]:
        raise lab.LabError("expected one newly picked-up item", "fail")
    evidence = {"assertion": "inventory_conservation", "before_inventory_sha256": left["digest"],
            "after_inventory_sha256": right["digest"], "component_digests_complete": True,
            "server_authoritative": True,
            "expected_count_delta": requirement["expected_count_delta"],
            "actual_count_delta": actual_delta,
            "before_count": before_count, "after_count": after_count,
            **({"expected_component_sha256": requirement["expected_component_sha256"]}
               if "expected_component_sha256" in requirement else {}),
            **({"pickup_item_id": pickup, "pickup_count_delta": 1} if pickup is not None else {})}
    if (len(changed_target_groups) > 1 or actual_delta != requirement["expected_count_delta"]
            or ("expected_before_count" in requirement and before_count != requirement["expected_before_count"])
            or ("expected_after_count" in requirement and after_count != requirement["expected_after_count"])):
        error = lab.LabError("inventory count change contradicted the exact conservation assertion", "fail")
        error.evidence = evidence
        raise error
    return evidence


def _assert_pump_accounting(requirement, observations):
    before, after, end = [_find_observation(observations, requirement[key], "aura_pump_pair")["value"]
                          for key in ("before", "after", "end")]
    mode, amount = requirement["mode"], requirement["expected_aura"]
    evidence = {"assertion": "pump_accounting", "pump_accounting": {
        "mode": mode, "before": before, "after": after, "end": end, "expected_aura": amount}}
    def require(condition, reason):
        if not condition:
            error = lab.LabError(reason, "fail")
            error.evidence = evidence
            raise error
    coords = lambda v: (v["x"], v["y"], v["z"], v["target_y"])
    require(coords(before) == coords(after) == coords(end), "pump pair coordinate changed")
    require(before["server_tick"] < after["server_tick"] < end["server_tick"], "pump pair snapshots are not ordered")
    for state in (before, after, end):
        require(state["server_authoritative"] is True, "pump pair snapshot is not authoritative")
        require(state["pump_aura"] + state["target_aura"] == amount, "pump pair aura conservation failed")
        require(state["ground_coal"] == 0 and not state["inhibited"], "pump fixture has nearby coal or redstone inhibition")
        require(state["blocked"] == (mode == "blocked"), "pump route differs from control mode")
    require(before["pump_aura"] == amount and before["target_aura"] == 0
            and before["power"] == 0 and before["speed"] == 0 and before["inventory_coal"] == 1,
            "pump fixture must begin charged but unfueled with one coal held")
    pulses = (end["world_time"] - 2) // 20 - (after["world_time"] - 2) // 20
    require(pulses >= 2 and end["world_time"] > after["world_time"], "pump runtime observation window too short")
    for state in (after, end):
        require(state["pump_aura"] == (0 if mode == "flow" else amount)
                and state["target_aura"] == (amount if mode == "flow" else 0), "pump transfer outcome differs from control mode")
        require(state["inventory_coal"] == (1 if mode == "unfueled" else 0), "coal inventory accounting failed")
        if mode == "unfueled":
            require(state["power"] == 0 and state["speed"] == 0, "unfueled pump acquired fuel")
        else:
            require(state["speed"] == 300 and 0 < state["power"] <= 320, "coal fuel power or speed is incorrect")
            if mode == "blocked":
                require(state["power"] == 320, "blocked pump spent fuel without reaching target")
    if mode == "flow":
        require(after["power"] - end["power"] == pulses, "pump runtime spend differs from normal target-attempt pulses")
    return evidence


def _step(identity, step, out, keyframes_left, observations, wall_deadline, cancel_event=None):
    kind = _kind(step)
    evidence = {}
    if kind == "observe":
        typed_evidence = []
        step_observations = {}
        for observation in step["observe"]:
            if isinstance(observation, dict):
                envelope, value = _scenario_observation(identity, observation)
                name = observation["type"]
                record = {"spec": observation, "value": value,
                          "server_tick_before": envelope.get("server_tick_before"),
                          "server_tick_after": envelope.get("server_tick_after")}
                if name == "server_tick":
                    typed_evidence.append({"type": name, "server_tick": value,
                                           "server_tick_before": envelope.get("server_tick_before"),
                                           "server_tick_after": envelope.get("server_tick_after")})
                elif name in {"screen_slots", "block_entity_inventory"}:
                    typed_evidence.append({"type": name, **value})
                elif name in {"aura_pump_pair", "aura_storage_fixture", "ground_entities", "aura_accessories"}:
                    typed_evidence.append(value)
                elif name == "player_inventory":
                    snapshot = _inventory_snapshot(value)
                    record["value"] = snapshot
                    summary = {"type": name, "stack_count": snapshot["stack_count"],
                               "component_digests_complete": snapshot["complete"],
                               "server_authoritative": snapshot["server_authoritative"],
                               "state_source": value.get("stateSource"),
                               "server_tick_before": envelope.get("server_tick_before"),
                               "server_tick_after": envelope.get("server_tick_after")}
                    if isinstance(value.get("crouching"), bool):
                        summary["crouching"] = value["crouching"]
                    if snapshot["digest"]:
                        summary["inventory_sha256"] = snapshot["digest"]
                        summary["items"] = [{"item_id": stack["itemId"], "count": stack["count"],
                                             "component_sha256": stack["componentSetSha256"]}
                                            for stack in snapshot["stacks"]]
                    typed_evidence.append(summary)
                else:
                    summary = {"type": name, "x": value["x"], "y": value["y"], "z": value["z"],
                               "block_id": value.get("blockId", "unknown"),
                               "aura_kind": value.get("kind", "UNKNOWN"),
                               "server_authoritative": value["serverAuthoritative"],
                               "server_tick_before": envelope.get("server_tick_before"),
                               "server_tick_after": envelope.get("server_tick_after"),
                               "snapshot_sha256": _aura_snapshot_digest(value)}
                    if isinstance(value.get("stateSource"), str):
                        summary["state_source"] = value["stateSource"]
                    typed_evidence.append(summary)
                step_observations[_observation_key(observation)] = record
                continue
            name = observation
            if name == "world":
                evidence["world_name"] = lab.world_check(identity)["world_name"]
            elif name == "player":
                player = lab.player_check(identity)
                evidence["player_gamemode"] = player["gamemode"]
                if isinstance(player.get("dimension"), str):
                    evidence["player_dimension"] = player["dimension"][:160]
            elif name == "screen":
                buttons = lab.command(identity, "get_screen_buttons")
                if not isinstance(buttons, dict):
                    raise lab.LabError("screen observer returned unsupported shape")
                evidence["screen_class"] = buttons.get("screen")
            elif name == "frame":
                if keyframes_left < 1:
                    raise lab.LabError("keyframe limit reached", "fail")
                name = "frame-" + step["id"] + ".png"
                lab.screenshot(identity, out / name)
                evidence["screenshot"] = name
                keyframes_left -= 1
        if step_observations:
            observations[step["id"]] = step_observations
            evidence["typed_observations"] = typed_evidence
    elif kind == "action":
        action = step["action"]
        if action["type"] == "capture_hud_trace":
            import hud_capture
            result = hud_capture.capture(identity, action, out / ("hud-" + step["id"]), wall_deadline, cancel_event)
            return {"action_type": "capture_hud_trace", "acknowledged": True,
                    "hud_capture": result}, keyframes_left
        if action["type"] == "capture_animation":
            import animation_capture
            result = animation_capture.capture(identity, action, out / ("animation-" + step["id"]),
                                               wall_deadline, cancel_event)
            return {"action_type": "capture_animation", "acknowledged": True,
                    "animation_capture": result}, keyframes_left
        if action["type"] in SCENARIO_ACTIONS:
            evidence = _route_action(identity, action)
            return evidence, keyframes_left
        params = {key: value for key, value in action.items() if key != "type"}
        if action["type"] == "click":
            if keyframes_left < 1:
                raise lab.LabError("keyframe limit reached", "fail")
            name = "frame-" + step["id"] + ".png"
            shot = lab.screenshot(identity, out / name)
            evidence["screenshot"] = name
            keyframes_left -= 1
            if action["x"] >= shot["width"] or action["y"] >= shot["height"]:
                raise lab.LabError("click is outside verified framebuffer", "fail")
        result = lab.command(identity, action["type"], params)
        if result is None:
            raise lab.LabError("action acknowledgement is absent", "fail")
        evidence["action_type"] = action["type"]
        evidence["acknowledged"] = True
    elif kind == "wait":
        evidence = _wait_ticks(identity, step["wait"]["count"], wall_deadline, cancel_event)
    else:
        requirement = step["require"]
        if requirement["type"] == "screen_class":
            deadline = time.monotonic() + 2.0
            while True:
                buttons = lab.command(identity, "get_screen_buttons")
                if not isinstance(buttons, dict):
                    raise lab.LabError("screen observer returned unsupported shape")
                observed = buttons.get("screen")
                if observed == requirement["equals"] or time.monotonic() >= deadline:
                    break
                time.sleep(0.1)
            evidence = {"assertion": requirement["type"], "observed": observed}
        elif requirement["type"] == "player_crouching":
            _, inventory = _scenario_observation(identity, {"type": "player_inventory"})
            observed = inventory.get("crouching")
            if not isinstance(observed, bool):
                raise lab.LabError("server crouch state is unavailable")
            evidence = {"assertion": "player_crouching", "observed": observed, "server_authoritative": True}
        elif requirement["type"] == "world_name":
            observed = lab.world_check(identity)["world_name"]
            evidence = {"assertion": requirement["type"], "observed": observed}
        else:
            evidence = _assert_typed(identity, requirement, observations)
            return evidence, keyframes_left
        if observed != requirement["equals"]:
            raise lab.LabError("observed state contradicted declared assertion", "fail")
    return evidence, keyframes_left


def _preflight_route_observations(identity, scenario, report):
    probes = {}
    for index, step in enumerate(scenario["steps"]):
        specs = _typed_observations(step)
        if "wait" in step and step["wait"]["type"] == "ticks":
            specs = [*specs, {"type": "server_tick"}]
        for spec in specs:
            if spec["type"] in {"screen_slots", "block_entity_inventory"}:
                continue  # Availability depends on the step's current GUI/world state.
            key = _observation_key(spec)
            probes.setdefault(key, (index, spec))
    for index, spec in probes.values():
        try:
            _scenario_observation(identity, spec)
        except lab.LabError as exc:
            row = report["steps"][index]
            row["status"] = exc.status
            row["reason"] = str(exc)[:240]
            raise


def run(identity_path, scenario_path, artifact_path, out, cancel_event=None):
    out = Path(out)
    if out.exists():
        raise lab.LabError("scenario output already exists; choose a fresh directory")
    scenario_path = Path(scenario_path)
    scenario = validate_scenario(contracts.load(scenario_path))
    identity = contracts.load(identity_path)
    out.mkdir(parents=True)
    runtime = scenario["runtime"]
    bridge_classification = identity.get("bridge_classification", "unreviewed")
    report = {"schema_version": 2, "created_at": lab.now(), "scenario": scenario["id"],
              "scenario_sha256": lab.sha256(scenario_path), "status": "unsupported",
              "evidence_kind": "diagnostic_live" if bridge_classification == "private_diagnostic" else "live",
              "fixture_id": scenario["fixture"],
              "runtime": {"status": "unsupported", "mod_id": runtime["mod_id"],
                          "mod_version": runtime["mod_version"],
                          "artifact_sha256": runtime["artifact_sha256"],
                          "bridge_sha256": str(identity.get("derivative_sha256", "0" * 64)).lower(),
                          "profile_kind": "prepared-packaged-client",
                          "bridge_classification": bridge_classification},
              "steps": [{"id": item["id"], "kind": _kind(item), "status": "not_run", "at": lab.now()}
                        for item in scenario["steps"]],
              "cleanup": {"status": "not_run"}, "visual_check": "not_reviewed",
              "artifacts": [],
              "memory": {"working_set_limit_mib": max(1, min(identity.get("max_group_mb", 3800), 3800))
                         if isinstance(identity.get("max_group_mb", 3800), (int, float)) else 3800,
                         "peak_working_set_mib": None, "peak_private_mib": None,
                         "samples": 0, "hard_cap": False}}
    lease = None
    started = time.monotonic()
    wall_deadline = started + scenario.get("limits", {}).get("wall_seconds", 600)
    keyframes_left = scenario.get("limits", {}).get("max_keyframes", 64)
    observations = {}
    try:
        lab.validate_identity(identity)
        if (Path(identity["game_dir"]) / UNCERTAIN_MARKER).exists():
            raise lab.LabError("profile has an uncertain action outcome; recreate from a clean seed", "fail")
        if identity["fixture_id"] != scenario["fixture"]:
            raise lab.LabError("scenario fixture differs from selected disposable world")
        report["runtime"]["bridge_sha256"] = lab.check_derivative(identity)
        lab.launch_check(identity)
        verify_packaged_artifact(identity, scenario, artifact_path)
        lab.status_check(identity)
        lab.world_check(identity)
        lab.player_check(identity)
        report["runtime"]["status"] = "verified"
        for index, item in enumerate(scenario["steps"]):
            missing = missing_capability(item)
            if missing:
                report["steps"][index]["status"] = "unsupported"
                report["steps"][index]["reason"] = missing
                raise lab.LabError(missing)
        _preflight_route_observations(identity, scenario, report)
        if scenario["cleanup"] == "save-exit":
            raise lab.LabError("normal save-exit lifecycle is unavailable")
        lease = ControlLease(identity)
        for index, item in enumerate(scenario["steps"]):
            if cancel_event is not None and cancel_event.is_set():
                raise lab.LabError("runtime memory guard or cancellation triggered", "fail")
            if time.monotonic() > wall_deadline:
                raise lab.LabError("scenario wall-time limit exceeded", "fail")
            used = lab.group_mb(identity)
            private = sum(lab.process_private_mb(pid) for pid in set(identity["tracked_pids"]))
            memory = report["memory"]
            memory["peak_working_set_mib"] = max(memory["peak_working_set_mib"] or 0, used)
            memory["peak_private_mib"] = max(memory["peak_private_mib"] or 0, round(private, 1))
            memory["samples"] += 1
            lab.status_check(identity)
            lab.world_check(identity)
            row = report["steps"][index]
            row["at"] = lab.now()
            try:
                if "action" in item:
                    lab.launch_check(identity)
                    lease.enter()
                evidence, keyframes_left = _step(identity, item, out, keyframes_left,
                                                 observations, wall_deadline, cancel_event)
                row["status"] = "pass"
                if evidence:
                    row["evidence"] = evidence
            except lab.LabError as exc:
                row["status"] = exc.status
                row["reason"] = str(exc)[:240]
                if isinstance(getattr(exc, "evidence", None), dict):
                    row["evidence"] = exc.evidence
                raise
            finally:
                # Persist completed bounded steps without claiming the unfinished run passed.
                lab.write_json(out / "report.json", report)
        report["status"] = "pass" if any("require" in item for item in scenario["steps"]) else "inconclusive"
        if report["status"] == "inconclusive":
            report["reason"] = "no behavioral assertion was declared"
    except lab.LabError as exc:
        report["status"] = exc.status
        report["reason"] = str(exc)[:240]
    except (OSError, ValueError, KeyError, TypeError):
        report["status"] = "unsupported"
        report["reason"] = "runtime observation or fixture could not be read"
    except KeyboardInterrupt:
        report["status"] = "inconclusive"
        report["reason"] = "scenario cancelled"
    finally:
        report["cleanup"] = lease.release() if lease else {"status": "pass"}
        if scenario["cleanup"] == "save-exit" and report["cleanup"]["status"] == "pass":
            report["cleanup"] = {"status": "unsupported", "reason": "normal save-exit lifecycle is unavailable"}
        if report["cleanup"]["status"] == "fail":
            report["status"] = "fail"
        elif report["cleanup"]["status"] != "pass" and report["status"] == "pass":
            report["status"] = "unsupported"
        report["artifacts"] = [{"file": path.relative_to(out).as_posix(), "sha256": lab.sha256(path)}
                               for path in sorted(out.glob("frame-*.png"))]
        report["artifacts"] += [{"file": path.relative_to(out).as_posix(), "sha256": lab.sha256(path)}
                                for path in sorted(out.glob("animation-*/capture.json"))]
        report["artifacts"] += [{"file": path.relative_to(out).as_posix(), "sha256": lab.sha256(path)}
                                for path in sorted(out.glob("animation-*/contact-sheet.png"))]
        lab.write_json(out / "report.json", report)
    return report
