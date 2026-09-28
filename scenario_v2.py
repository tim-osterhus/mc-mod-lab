"""Bounded real-client scenarios; unsupported capabilities never become passes."""

import json
import math
import hashlib
import http.client
import os
from pathlib import Path
import re
import time
from uuid import uuid4
import zipfile

import contracts
import lab


SUPPORTED_OBSERVATIONS = {"world", "player", "screen", "frame"}
SUPPORTED_ACTIONS = {"press_key", "click", "click_button_index", "use_item"}
SCENARIO_OBSERVATIONS = {"server_tick", "player_inventory", "aura_block", "aura_block_server"}
SCENARIO_ACTIONS = {"select_hotbar", "drop_selected", "aim_at_block", "use_item_at_block"}
SUPPORTED_REQUIREMENTS = {"screen_class", "world_name", "aura_increase", "inventory_conservation"}
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
    return (spec["type"], spec.get("x"), spec.get("y"), spec.get("z"))


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
    connection = http.client.HTTPConnection("127.0.0.1", identity["port"], timeout=8)
    try:
        connection.request("POST", "/api/scenario/v2",
                           body=json.dumps(request, separators=(",", ":")).encode("utf-8"),
                           headers={"Content-Type": "application/json",
                                    "Authorization": "Bearer " + token})
        response = connection.getresponse()
        raw = response.read(MAX_SCENARIO_RESPONSE_BYTES + 1)
        status_code = response.status
    except (OSError, http.client.HTTPException, ValueError) as exc:
        if kind == "action":
            _mark_uncertain(identity)
        raise lab.LabError("scenario bridge request failed", "fail") from exc
    finally:
        connection.close()
    if len(raw) > MAX_SCENARIO_RESPONSE_BYTES:
        raise lab.LabError("scenario bridge response exceeds the fixed output limit", "unsupported")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise lab.LabError("scenario bridge response is invalid", "fail") from exc
    if status_code != 200:
        if kind == "action" and status_code in {503, 504}:
            _mark_uncertain(identity)
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
    return result


def _mark_uncertain(identity):
    # Dispatch may already have started when its response times out. Never retry this save.
    (Path(identity["game_dir"]) / UNCERTAIN_MARKER).write_text(
        "Typed action outcome uncertain; discard this profile and recreate from a clean seed.\n",
        encoding="utf-8")


def _scenario_observation(identity, spec):
    name = spec["type"]
    if name in {"aura_block", "aura_block_server"}:
        params = {key: spec[key] for key in ("x", "y", "z")}
    else:
        params = {}
    envelope = scenario_request(identity, "observe", name, params)
    value = envelope["result"]
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
                if action not in SUPPORTED_ACTIONS | SCENARIO_ACTIONS else None)
    if kind == "wait":
        return ("server game-tick wait capability unavailable"
                if step["wait"]["type"] != "ticks" else None)
    requirement = step["require"]["type"]
    return ("assertion observer unavailable: " + requirement
            if requirement not in SUPPORTED_REQUIREMENTS else None)


def _route_action(identity, action):
    name = action["type"]
    params = {key: value for key, value in action.items() if key != "type"}
    if name == "select_hotbar":
        params["item_id"] = params.pop("item")
    envelope = scenario_request(identity, "action", name, params)
    result = envelope["result"]
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


def _assert_typed(identity, requirement, observations):
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
    changed_target_groups = []
    actual_delta = 0
    for key in set(before_groups) | set(after_groups):
        change = after_groups.get(key, 0) - before_groups.get(key, 0)
        if key[0] == requirement["item_id"]:
            if change:
                changed_target_groups.append(change)
                actual_delta += change
        elif change:
            raise lab.LabError("unrelated inventory stack count or components changed", "fail")
    if len(changed_target_groups) > 1 or actual_delta != requirement["expected_count_delta"]:
        raise lab.LabError("inventory count change contradicted the exact conservation assertion", "fail")
    return {"assertion": "inventory_conservation", "before_inventory_sha256": left["digest"],
            "after_inventory_sha256": right["digest"], "component_digests_complete": True,
            "server_authoritative": True,
            "expected_count_delta": requirement["expected_count_delta"],
            "actual_count_delta": actual_delta}


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
                elif name == "player_inventory":
                    snapshot = _inventory_snapshot(value)
                    record["value"] = snapshot
                    summary = {"type": name, "stack_count": snapshot["stack_count"],
                               "component_digests_complete": snapshot["complete"],
                               "server_authoritative": snapshot["server_authoritative"],
                               "state_source": value.get("stateSource"),
                               "server_tick_before": envelope.get("server_tick_before"),
                               "server_tick_after": envelope.get("server_tick_after")}
                    if snapshot["digest"]:
                        summary["inventory_sha256"] = snapshot["digest"]
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
        report["artifacts"] = [{"file": path.name, "sha256": lab.sha256(path)}
                               for path in sorted(out.glob("frame-*.png"))]
        lab.write_json(out / "report.json", report)
    return report
