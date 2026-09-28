"""Import the bounded Fabric 1.21.1 conservation case without promoting UI coverage."""

import argparse
import json
import math
from pathlib import Path
import re
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import contracts
import gametest_runtime
import lab

TEST = "auratransfertests.conservedtransfer"
SMOKE = "patchoulismoketest.doesitrun"
EXPECTED_FAILURE = "Expected earned source-to-target transfer by tick 80"
FIXTURE_INJECTION = "two placed nodes; source.feedCrystal(WHITE,1000) before ticking; optional stone obstruction"


def read_xml(path):
    if path.stat().st_size > 1024 * 1024:
        raise contracts.ContractError("GameTest XML is oversized")
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise contracts.ContractError("GameTest XML must be UTF-8") from exc
    if "\0" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise contracts.ContractError("GameTest XML declarations are unsupported")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise contracts.ContractError("GameTest XML is malformed") from exc
    if root.tag not in {"testsuite", "testsuites"}:
        raise contracts.ContractError("Missing GameTest suite")
    cases = {}
    for node in root.iter():
        if node.tag not in {"testsuite", "testsuites", "testcase", "failure", "error", "skipped"}:
            raise contracts.ContractError("Unexpected GameTest XML element")
        if node.tag in {"testsuite", "testsuites"} and any(
                child.tag not in {"testsuite", "testcase"} for child in node):
            raise contracts.ContractError("GameTest failure outside a testcase")
        if node.tag != "testcase":
            continue
        name = node.get("name", "")
        if not re.fullmatch(r"[a-z0-9._-]{1,160}", name) or name in cases:
            raise contracts.ContractError("Missing or duplicate GameTest case")
        try:
            seconds = float(node.get("time", "nan"))
        except ValueError as exc:
            raise contracts.ContractError("Invalid GameTest case duration") from exc
        if not math.isfinite(seconds) or seconds < 0:
            raise contracts.ContractError("Invalid GameTest case duration")
        children = list(node)
        if len(children) > 1 or any(child.tag not in {"failure", "error", "skipped"} for child in children):
            raise contracts.ContractError("Ambiguous GameTest result")
        state = children[0].tag if children else "pass"
        cases[name] = {"status": "fail" if state in {"failure", "error"} else state,
                       "failure_kind": state,
                       "message": children[0].get("message", "") if children else ""}
    if not cases or len(cases) > 256:
        raise contracts.ContractError("GameTest report is empty or oversized")
    for suite in root.iter():
        if suite.tag not in {"testsuite", "testsuites"}:
            continue
        descendants = list(suite.iter("testcase"))
        counts = {"tests": len(descendants), "failures": sum(c.find("failure") is not None for c in descendants),
                  "errors": sum(c.find("error") is not None for c in descendants),
                  "skipped": sum(c.find("skipped") is not None for c in descendants)}
        for key, expected in counts.items():
            value = suite.get(key)
            if value is not None and (not re.fullmatch(r"[0-9]{1,6}", value) or int(value) != expected):
                raise contracts.ContractError("Declared GameTest totals contradict parsed cases")
    return cases


def validate_loaded(value, profile, adapter_sha256):
    expected = {**profile["loaded_mods"], "mc-mod-lab-gametest": {
        "version": "0.1.0", "origin_sha256": [adapter_sha256]}}
    if not isinstance(value, dict) or set(value) != set(expected):
        raise contracts.ContractError("Incomplete loaded GameTest identities")
    for name, identity in expected.items():
        actual = value[name]
        if not isinstance(actual, dict) or actual.get("version") != identity["version"]:
            raise contracts.ContractError("Loaded GameTest version differs from reviewed profile")
        for key in ("origin_sha256", "origin_content_sha256"):
            hashes = actual.get(key)
            if not isinstance(hashes, list) or len(hashes) != 1 or not re.fullmatch(r"[a-f0-9]{64}", str(hashes[0])):
                raise contracts.ContractError("Loaded GameTest origin is not one complete packaged JAR")
            if key in identity and hashes != identity[key]:
                raise contracts.ContractError("Loaded GameTest origin differs from reviewed profile")


def import_run(root, adapter_sha256):
    root = Path(root)
    gametest_runtime.reject_links(root)
    if not re.fullmatch(r"[a-f0-9]{64}", adapter_sha256):
        raise contracts.ContractError("Reviewed adapter SHA-256 is required")
    lifecycle = contracts.load(root / "lifecycle.json")
    if (lifecycle.get("schema_version") != 1 or lifecycle.get("kind") != "fabric-gametest"
            or lifecycle.get("status") != "completed" or lifecycle.get("forced_cleanup") is not False
            or lifecycle.get("artifact_sha256") != gametest_runtime.AURA_SHA
            or type(lifecycle.get("blocked")) is not bool
            or lifecycle.get("client_check") != "not_run" or lifecycle.get("visual_check") != "not_run"):
        raise contracts.ContractError("Incomplete or mismatched GameTest lifecycle")
    blocked = lifecycle["blocked"]
    if type(lifecycle.get("exit_code")) is not int or lifecycle["exit_code"] != (1 if blocked else 0):
        raise contracts.ContractError("GameTest exit disagrees with expected outcome")
    elapsed = lifecycle.get("elapsed_seconds")
    if (lifecycle.get("wall_limit_seconds") != 180 or type(elapsed) not in (int, float)
            or not math.isfinite(elapsed) or not 0 < elapsed <= 180):
        raise contracts.ContractError("GameTest duration is missing or outside its bound")
    for key in ("peak_private_mib", "peak_working_set_mib", "memory_samples"):
        value = lifecycle.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise contracts.ContractError("Missing memory evidence")
    if (lifecycle.get("memory_limit_mib") != 3800 or
            max(lifecycle["peak_private_mib"], lifecycle["peak_working_set_mib"]) > 3800):
        raise contracts.ContractError("GameTest exceeded workload memory guard")
    required = {"runtime-inputs.json", "evidence/gametest.xml", "gametest-observations.json"}
    artifacts = lifecycle.get("artifacts", [])
    if len(artifacts) != 3 or {a.get("file") for a in artifacts} != required:
        raise contracts.ContractError("Incomplete GameTest artifacts")
    for artifact in artifacts:
        gametest_runtime.reject_links(root / artifact["file"])
        contracts.artifact_path(root, artifact)
    profile = contracts.load(gametest_runtime.PROFILE)
    inputs = contracts.load(root / "runtime-inputs.json")
    expected_inputs = profile["artifacts"] + [{"file": "mods/lab-gametest.jar", "sha256": adapter_sha256}]
    if inputs != {"schema_version": 1, "profile_sha256": lab.sha256(gametest_runtime.PROFILE),
                  "artifacts": expected_inputs}:
        raise contracts.ContractError("GameTest executable inventory differs from reviewed profile")
    for artifact in expected_inputs:
        gametest_runtime.reject_links(root / artifact["file"])
        contracts.artifact_path(root, artifact)
    observations = contracts.load(root / "gametest-observations.json")
    if (observations.get("schema_version") != 1 or observations.get("test") != TEST
            or observations.get("minecraft") != "1.21.1" or observations.get("blocked") is not blocked
            or observations.get("artifact_sha256") != gametest_runtime.AURA_SHA):
        raise contracts.ContractError("GameTest observations identify a different trial")
    if observations.get("fixture_injection") != FIXTURE_INJECTION:
        raise contracts.ContractError("GameTest fixture injection disclosure is missing or changed")
    validate_loaded(observations.get("loaded_mods"), profile, adapter_sha256)
    samples = observations.get("samples")
    if not isinstance(samples, list) or len(samples) != 81:
        raise contracts.ContractError("GameTest needs all 81 fixed tick samples")
    for tick, sample in enumerate(samples):
        if (not isinstance(sample, dict) or set(sample) != {"tick", "source", "target", "sourcePower", "targetPower"}
                or any(type(number) is not int or number < 0 for number in sample.values())
                or sample["tick"] != tick or sample["source"] + sample["target"] != 1000):
            raise contracts.ContractError("GameTest tick sequence or exact conservation failed")
    if samples[0] != {"tick": 0, "source": 1000, "target": 0, "sourcePower": 0, "targetPower": 0}:
        raise contracts.ContractError("GameTest initial inputs differ")
    cases = read_xml(root / "evidence/gametest.xml")
    if set(cases) != {TEST, SMOKE} or cases[SMOKE]["status"] != "pass":
        raise contracts.ContractError("Unexpected/missing/skipped/failed auxiliary GameTest cases")
    final = samples[-1]
    if blocked:
        if (cases[TEST]["failure_kind"] != "failure" or not cases[TEST]["message"].endswith(EXPECTED_FAILURE)
                or any(s["source"] != 1000 or s["target"] != 0 for s in samples)):
            raise contracts.ContractError("Control did not demonstrate the intended blocked transfer failure")
    elif cases[TEST]["status"] != "pass" or final["source"] >= 1000 or final["target"] <= 0:
        raise contracts.ContractError("Positive GameTest did not demonstrate conserved transfer")
    result = {"schema_version": 1, "kind": "fabric-gametest", "test": TEST,
              "status": cases[TEST]["status"], "artifact_sha256": gametest_runtime.AURA_SHA,
              "adapter_sha256": adapter_sha256, "known_broken_control": blocked,
              "expected_outcome_verified": True, "samples": len(samples), "final": final,
              "fixture_injection": observations.get("fixture_injection"),
              "client_check": "not_run", "visual_check": "not_run",
              "artifacts": artifacts + [{"file": "lifecycle.json", "sha256": lab.sha256(root / "lifecycle.json")}]}
    contracts.portable_check(result)
    return result


def export_run(root, adapter_sha256):
    root = Path(root)
    result = import_run(root, adapter_sha256)
    report_path = root / "deterministic-report.json"
    # Re-export only the identical derived report; never replace different evidence.
    if report_path.exists() and contracts.load(report_path) != result:
        raise contracts.ContractError("Existing deterministic report differs")
    lab.write_json(report_path, result)
    checked = datetime.now(timezone.utc).isoformat()
    not_run = {"status": "not_run", "artifact": None, "checked_at": None, "reviewer": None}
    parity = {"schema_version": 1, "feature": "aura.conserved-transfer.gametest",
              "requirement": "Two ordinary nodes conserve 1000 initial White aura and transfer within 80 server ticks.",
              "reference": {"source": "bundle:aura-44cc057-conserved-transfer", "timestamp": None,
                            "observed_at": checked},
              "implementation": {"status": "implemented", "revision": gametest_runtime.AURA_SHA},
              "deterministic_test": {"status": result["status"], "artifact": {
                  "file": report_path.name, "sha256": lab.sha256(report_path)},
                  "checked_at": checked, "reviewer": None},
              "client_check": not_run.copy(), "visual_check": not_run.copy(), "exceptions": []}
    contracts.validate_parity(parity, root, portable=True)
    lab.write_json(root / "parity.json", parity)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--adapter-sha256", required=True)
    args = parser.parse_args()
    result = export_run(args.profile, args.adapter_sha256)
    print(json.dumps(result))
