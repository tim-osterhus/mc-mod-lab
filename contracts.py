"""Portable evidence contracts; validation never approves a gameplay claim."""

import hashlib
import json
from datetime import datetime
from pathlib import Path, PurePosixPath
import re
import struct


class ContractError(ValueError):
    pass


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ContractError("duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ContractError("nonfinite JSON number")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("evidence JSON could not be read") from exc


def schema_check(value, kind):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise ContractError("install requirements.txt to validate evidence") from exc
    schema = load(Path(__file__).parent / "schemas" / (kind + ".schema.json"))
    checker = FormatChecker()
    def dated(value):
        if not isinstance(value, str):
            return True
        return "T" in value and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    checker.checkers["date-time"] = (dated, (ValueError, TypeError))
    validator = Draft202012Validator(schema, format_checker=checker)
    error = next(validator.iter_errors(value), None)
    if error:
        # Do not echo untrusted evidence values, paths, or credentials in errors.
        raise ContractError(kind + " schema violation: " + error.validator)


def portable_check(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.casefold() in {"token", "password", "authorization", "game_dir", "world_path", "launch_log"}:
                raise ContractError("private field in portable evidence")
            portable_check(item)
    elif isinstance(value, list):
        for item in value:
            portable_check(item)
    elif isinstance(value, str):
        if re.search(r"(?i)([a-z]:[\\/]|\\\\|file://|/(?:home|users|mnt|tmp)/|bearer\s+\S+|ghp_[a-z0-9]{20,})", value):
            raise ContractError("local path or credential in portable evidence")


def artifact_path(root, artifact):
    name = artifact["file"]
    path = PurePosixPath(name)
    if (path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
            or not path.parts or str(path) != name):
        raise ContractError("artifact path must be portable and relative")
    root = Path(root).resolve()
    target = root.joinpath(*path.parts)
    if any(part.is_symlink() for part in [target, *target.parents] if part != root and part.is_relative_to(root)):
        raise ContractError("artifact symlinks are unsupported")
    try:
        resolved = target.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ContractError("artifact escapes evidence root")
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ContractError("artifact hash mismatch")
    except OSError as exc:
        raise ContractError("artifact is unavailable") from exc
    return resolved


def validate_report(value, root, portable=False):
    schema_check(value, "report")
    if portable:
        portable_check(value)
    artifacts = value["artifacts"]
    names = [item["file"] for item in artifacts]
    if len(names) != len(set(names)):
        raise ContractError("duplicate report artifact")
    for artifact in artifacts:
        artifact_path(root, artifact)
    for label in ("before", "after"):
        if label not in value:
            continue
        shot = value[label]["screenshot"]
        if {"file": shot["file"], "sha256": shot["sha256"]} not in artifacts:
            raise ContractError("screenshot missing from artifact inventory")
        data = artifact_path(root, shot).read_bytes()
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", data[16:24]) != (shot["width"], shot["height"]):
            raise ContractError("screenshot dimensions or format disagree")
    if value["status"] == "captured" and "expect" in value:
        expected = value["expect"]
        if value["after"]["screen_class"] != expected["after_screen"]:
            raise ContractError("captured report contradicts screen assertion")
        if "world_name" in expected and value["after"]["world"]["world_name"] != expected["world_name"]:
            raise ContractError("captured report contradicts world assertion")
    return {"status": "valid", "capture_status": value["status"],
            "evidence_kind": value.get("evidence_kind", "unspecified_legacy"),
            "visual_check": value["visual_check"]}


def validate_parity(value, root, portable=False):
    schema_check(value, "parity")
    if portable:
        portable_check(value)
    for dimension in ("deterministic_test", "client_check", "visual_check"):
        check = value[dimension]
        status = check["status"]
        if status in {"pass", "fail"} and (not check["artifact"] or not check["checked_at"]):
            raise ContractError("completed check needs dated artifact")
        if status == "not_run" and any(check[key] is not None for key in ("artifact", "checked_at", "reviewer")):
            raise ContractError("not_run check cannot carry completed evidence")
        if dimension == "visual_check" and status in {"pass", "fail"} and not check["reviewer"]:
            raise ContractError("visual assessment needs an independent reviewer")
        if check["artifact"]:
            path = artifact_path(root, check["artifact"])
            if dimension == "client_check":
                report = load(path)
                validate_report(report, path.parent, portable)
                expected = {"pass": "captured", "fail": "fail", "unsupported": "unsupported"}.get(status)
                if report.get("evidence_kind") != "live" or report["status"] != expected:
                    raise ContractError("client check is not backed by matching live evidence")
    return {"status": "valid", "feature": value["feature"],
            "dimensions": {name: value[name]["status"] for name in ("deterministic_test", "client_check", "visual_check")}}


def validate_scenario_v2(value):
    from scenario_v2 import validate_scenario
    validate_scenario(value)
    return {"status": "valid", "scenario": value["id"], "steps": len(value["steps"])}


def validate_scenario_report_v2(value, root, portable=False):
    schema_check(value, "scenario-report-v2")
    if portable:
        portable_check(value)
    artifacts = value["artifacts"]
    names = [item["file"] for item in artifacts]
    if len(names) != len(set(names)):
        raise ContractError("duplicate scenario artifact")
    for artifact in artifacts:
        artifact_path(root, artifact)
    for step in value["steps"]:
        shot = step.get("evidence", {}).get("screenshot")
        if shot:
            if shot not in names:
                raise ContractError("scenario screenshot missing from artifact inventory")
            png = artifact_path(root, artifacts[names.index(shot)]).read_bytes()
            if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
                raise ContractError("scenario screenshot is not PNG")
    if value["status"] == "pass":
        if (value["runtime"]["status"] != "verified" or value["cleanup"]["status"] != "pass"
                or not value["steps"] or any(step["status"] != "pass" for step in value["steps"])
                or not any(step["kind"] == "require" for step in value["steps"])):
            raise ContractError("scenario pass lacks verified runtime, assertions, steps, or cleanup")
    if any(step["status"] == "not_run" for step in value["steps"]):
        if value["status"] == "pass":
            raise ContractError("scenario pass contains a skipped step")
    return {"status": "valid", "scenario_status": value["status"],
            "evidence_kind": value["evidence_kind"], "visual_check": value["visual_check"]}


def validate_file(path, kind, portable=False):
    value = load(path)
    root = Path(path).parent
    if kind == "scenario-v2":
        return validate_scenario_v2(value)
    validators = {"report": validate_report, "parity": validate_parity,
                  "scenario-report-v2": validate_scenario_report_v2}
    if kind not in validators:
        raise ContractError("unknown evidence contract")
    return validators[kind](value, root, portable)
