"""Bounded real-client scenarios; unsupported capabilities never become passes."""

import json
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
SUPPORTED_REQUIREMENTS = {"screen_class", "world_name"}


def validate_scenario(value):
    contracts.schema_check(value, "scenario-v2")
    ids = [step["id"] for step in value["steps"]]
    if len(ids) != len(set(ids)):
        raise contracts.ContractError("duplicate scenario step id")
    if len(ids) > value.get("limits", {}).get("max_steps", 64):
        raise contracts.ContractError("scenario exceeds declared step limit")
    return value


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


def _kind(step):
    return next(key for key in ("observe", "action", "wait", "require") if key in step)


def missing_capability(step):
    kind = _kind(step)
    if kind == "observe":
        missing = set(step["observe"]) - SUPPORTED_OBSERVATIONS
        return "observer capability unavailable: " + ", ".join(sorted(missing)) if missing else None
    if kind == "action":
        action = step["action"]["type"]
        return "action capability unavailable: " + action if action not in SUPPORTED_ACTIONS else None
    if kind == "wait":
        return "server game-tick/event wait capability unavailable"
    requirement = step["require"]["type"]
    return "assertion observer unavailable: " + requirement if requirement not in SUPPORTED_REQUIREMENTS else None


def _step(identity, step, out, keyframes_left):
    kind = _kind(step)
    evidence = {}
    if kind == "observe":
        for name in step["observe"]:
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
    elif kind == "action":
        action = step["action"]
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
        raise lab.LabError("server game-tick/event wait capability unavailable")
    else:
        requirement = step["require"]
        if requirement["type"] == "screen_class":
            buttons = lab.command(identity, "get_screen_buttons")
            if not isinstance(buttons, dict):
                raise lab.LabError("screen observer returned unsupported shape")
            observed = buttons.get("screen")
        else:
            observed = lab.world_check(identity)["world_name"]
        evidence = {"assertion": requirement["type"], "observed": observed}
        if observed != requirement["equals"]:
            raise lab.LabError("observed state contradicted declared assertion", "fail")
    return evidence, keyframes_left


def run(identity_path, scenario_path, artifact_path, out):
    out = Path(out)
    if out.exists():
        raise lab.LabError("scenario output already exists; choose a fresh directory")
    scenario_path = Path(scenario_path)
    scenario = validate_scenario(contracts.load(scenario_path))
    identity = contracts.load(identity_path)
    out.mkdir(parents=True)
    runtime = scenario["runtime"]
    report = {"schema_version": 2, "created_at": lab.now(), "scenario": scenario["id"],
              "scenario_sha256": lab.sha256(scenario_path), "status": "unsupported",
              "evidence_kind": "live", "fixture_id": scenario["fixture"],
              "runtime": {"status": "unsupported", "mod_id": runtime["mod_id"],
                          "mod_version": runtime["mod_version"],
                          "artifact_sha256": runtime["artifact_sha256"],
                          "bridge_sha256": str(identity.get("derivative_sha256", "0" * 64)).lower(),
                          "profile_kind": "prepared-packaged-client"},
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
    keyframes_left = scenario.get("limits", {}).get("max_keyframes", 64)
    try:
        lab.validate_identity(identity)
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
        if scenario["cleanup"] == "save-exit":
            raise lab.LabError("normal save-exit lifecycle is unavailable")
        lease = ControlLease(identity)
        for index, item in enumerate(scenario["steps"]):
            if time.monotonic() - started > scenario.get("limits", {}).get("wall_seconds", 600):
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
                evidence, keyframes_left = _step(identity, item, out, keyframes_left)
                row["status"] = "pass"
                if evidence:
                    row["evidence"] = evidence
            except lab.LabError as exc:
                row["status"] = exc.status
                row["reason"] = str(exc)[:240]
                raise
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
