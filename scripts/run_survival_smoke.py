"""Trusted, disposable launch for bounded visible-input technical smoke."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import contracts
import lab
import runtime_launch
from scripts import smoke_survival_input as smoke


PHASES = ("use", "initial_attack", "held_mining")
DURABLE_PHASE = "durable_mining"
LOG_PHASE = "log_mining"
EXPIRY_PHASE = "expiry_mining"
BLOCK_ID = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")


def obs_call(script, operation, data=None):
    command = [sys.executable, str(script), operation]
    if data is not None:
        command.append(json.dumps(data, separators=(",", ":")))
    env = os.environ.copy()
    env.pop("MC_MOD_LAB_TOKEN", None)
    env.pop("MC_MCP_PORT", None)
    completed = subprocess.run(command, capture_output=True, text=True, timeout=25,
                               env=env, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        raise lab.LabError(f"OBS {operation} failed", "fail")
    try:
        reply = json.loads(completed.stdout)
    except (ValueError, TypeError) as exc:
        raise lab.LabError(f"OBS {operation} returned invalid JSON", "fail") from exc
    if not isinstance(reply, dict):
        raise lab.LabError(f"OBS {operation} returned invalid data", "fail")
    return reply


def obs_inactive(script):
    record = obs_call(script, "GetRecordStatus")
    stream = obs_call(script, "GetStreamStatus")
    if type(record.get("outputActive")) is not bool or type(stream.get("outputActive")) is not bool:
        raise lab.LabError("OBS active status is invalid", "fail")
    return not record["outputActive"] and not stream["outputActive"]


def select_capture_window(script, title):
    query = {"inputName": "Aura QA - Minecraft", "propertyName": "window"}
    items = obs_call(script, "GetInputPropertiesListPropertyItems", query).get("propertyItems")
    if not isinstance(items, list):
        raise lab.LabError("OBS capture window list is invalid", "fail")
    choices = [item["itemValue"] for item in items if isinstance(item, dict)
               and item.get("itemEnabled") is True
               and isinstance(item.get("itemValue"), str)
               and item["itemValue"].startswith(title + ":")
               and item["itemValue"].endswith(":java.exe")]
    if len(choices) != 1:
        raise lab.LabError("OBS capture target for selected client is absent or ambiguous", "fail")
    obs_call(script, "SetInputSettings", {"inputName": "Aura QA - Minecraft",
                                          "inputSettings": {"window": choices[0]}, "overlay": True})
    selected = obs_call(script, "GetInputSettings", {"inputName": "Aura QA - Minecraft"})
    if selected.get("inputSettings", {}).get("window") != choices[0]:
        raise lab.LabError("OBS did not select the verified client window", "fail")
    return choices[0]


def checked_targets(args):
    targets = {}
    ordinary = (args.use_target, args.attack_target, args.mine_target)
    if args.log_target is not None:
        if (any(raw is not None for raw in ordinary) or args.durable_target is not None
                or args.expiry_target is not None):
            raise lab.LabError("placed-log technical gate must run in its own profile")
        x, y, z = map(int, args.log_target[:3])
        if (not (-30000000 <= x <= 30000000 and -64 <= y <= 319
                 and -30000000 <= z <= 30000000)
                or args.log_target[3] != "minecraft:oak_log"):
            raise lab.LabError("placed-log fixture target must be exact oak log")
        return {LOG_PHASE: (x, y, z, "minecraft:oak_log")}
    if args.expiry_target is not None:
        if any(raw is not None for raw in ordinary) or args.durable_target is not None:
            raise lab.LabError("expiry technical gate must run in its own profile")
        x, y, z = map(int, args.expiry_target[:3])
        if (not (-30000000 <= x <= 30000000 and -64 <= y <= 319
                 and -30000000 <= z <= 30000000)
                or args.expiry_target[3] != "minecraft:iron_block"):
            raise lab.LabError("expiry fixture target must be exact iron block")
        return {EXPIRY_PHASE: (x, y, z, "minecraft:iron_block")}
    if any(raw is None for raw in ordinary):
        raise lab.LabError("the three base technical targets are required")
    for phase, raw in zip(PHASES, ordinary):
        x, y, z = map(int, raw[:3])
        block = raw[3]
        if not (-30000000 <= x <= 30000000 and -64 <= y <= 319
                and -30000000 <= z <= 30000000 and BLOCK_ID.fullmatch(block)):
            raise lab.LabError(f"invalid {phase} fixture target")
        targets[phase] = (x, y, z, block)
    if args.durable_target is not None:
        x, y, z = map(int, args.durable_target[:3])
        block = args.durable_target[3]
        if not (-30000000 <= x <= 30000000 and -64 <= y <= 319
                and -30000000 <= z <= 30000000 and block == "minecraft:stone"):
            raise lab.LabError("durable fixture target must be an exact stone block")
        targets[DURABLE_PHASE] = (x, y, z, block)
    return targets


def check_manifest(path):
    manifest = contracts.load(path)
    contracts.schema_check(manifest, "runtime-profile")
    mods = {item["role"]: item for item in manifest["mods"]}
    if (manifest["bridge_classification"] != "public_reviewed"
            or manifest["expected_gamemode"] != "survival"
            or mods["target"]["mod_id"] != "aura"
            or mods["target"]["mod_version"] != "0.2.1+1.21.1"
            or mods["target"]["sha256"] != smoke.AURA_SHA256
            or mods["bridge"]["sha256"] not in smoke.BRIDGE_SHA256S):
        raise lab.LabError("technical smoke requires the pinned Survival Aura and bridge artifacts")
    return mods["bridge"]["sha256"]


def reconcile_obs(script, recorder_started):
    try:
        record = obs_call(script, "GetRecordStatus")
        forced_stop = record.get("outputActive") is True and recorder_started
        if forced_stop:
            obs_call(script, "StopRecord")
        for _ in range(50):
            record = obs_call(script, "GetRecordStatus")
            stream = obs_call(script, "GetStreamStatus")
            if (type(record.get("outputActive")) is not bool
                    or type(stream.get("outputActive")) is not bool):
                raise lab.LabError("OBS active status is invalid", "fail")
            if not record["outputActive"] and not stream["outputActive"]:
                return {"status": "pass", "recording_inactive": True,
                        "streaming_inactive": True, "forced_stop": forced_stop}
            time.sleep(0.2)
        return {"status": "fail", "recording_inactive": not record["outputActive"],
                "streaming_inactive": not stream["outputActive"], "forced_stop": forced_stop}
    except (lab.LabError, OSError, subprocess.SubprocessError) as exc:
        return {"status": "fail", "reason": str(exc)[:180]}


def run_phases(args, targets, identity, artifact, run, cancel, recorder_started):
    out = run / "technical-smoke"
    out.mkdir(exist_ok=False)
    report = {"status": "fail", "kind": "developer_technical_smoke",
              "client_pid": identity["pid"], "visual_status": "not_reviewed",
              "gameplay_result": "not_evaluated", "phases": []}
    identity_path = run / "identity.json"
    for phase in targets:
        x, y, z, block = targets[phase]
        smoke.prepare(argparse.Namespace(identity=identity_path, artifact=artifact,
                                         out=out / (phase + "-fixture-check"),
                                         x=x, y=y, z=z, block=block))
    for phase in targets:
        if cancel.is_set():
            raise lab.LabError("runtime memory guard cancelled technical smoke", "fail")
        x, y, z, block = targets[phase]
        prepared = smoke.prepare(argparse.Namespace(identity=identity_path, artifact=artifact,
                                                     out=out / (phase + "-prepared"),
                                                     x=x, y=y, z=z, block=block))
        target = select_capture_window(args.obs_control, prepared["window_title"])
        test_id = f"m5a-{phase}-{identity['pid']}"
        phase_out = out / phase
        action = argparse.Namespace(identity=identity_path, artifact=artifact, out=phase_out,
                                    phase=phase, test_id=test_id,
                                    ready_file=out / (phase + ".ready"),
                                    stop_file=out / (phase + ".stop"))
        recorder = None

        def start_recorder():
            nonlocal recorder
            env = os.environ.copy()
            env.pop("MC_MOD_LAB_TOKEN", None)
            env.pop("MC_MCP_PORT", None)
            max_seconds = 45 if phase == LOG_PHASE else 30
            command = [sys.executable, str(args.obs_record), "--test-id", test_id,
                       "--artifact-sha256", smoke.AURA_SHA256,
                       "--purpose", "capture_preflight", "--max-seconds", str(max_seconds),
                       "--stop-file", str(action.stop_file), "--ready-file", str(action.ready_file),
                       "--expected-pid", str(identity["pid"])]
            recorder = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, env=env,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            recorder_started[0] = True

        stdout = stderr = ""
        try:
            action_report = smoke.act(action, on_armed=start_recorder)
        finally:
            action.stop_file.touch(exist_ok=True)
            if recorder is not None:
                try:
                    stdout, stderr = recorder.communicate(timeout=120)
                except subprocess.TimeoutExpired as exc:
                    recorder.kill()
                    recorder.communicate(timeout=10)
                    raise lab.LabError("OBS recorder exceeded the bounded phase", "fail") from exc
        if recorder is None:
            raise lab.LabError("OBS recorder did not start", "fail")
        (phase_out / "recorder.stdout.txt").write_text(stdout, encoding="utf-8")
        (phase_out / "recorder.stderr.txt").write_text(stderr, encoding="utf-8")
        clip = None
        try:
            clip = json.loads(stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            pass
        phase_report = {"phase": phase, "test_id": test_id, "capture_target": target,
                        "prepared": prepared, "action": action_report,
                        "recorder_exit_code": recorder.returncode, "clip": clip}
        if phase in {DURABLE_PHASE, EXPIRY_PHASE} and action_report["status"] == "inconclusive":
            phase_report["durable_postcheck"] = smoke.prepare(argparse.Namespace(
                identity=identity_path, artifact=artifact,
                out=out / ("durable-postcheck" if phase == DURABLE_PHASE
                           else "expiry-postcheck"), x=x, y=y, z=z, block=block))
        report["phases"].append(phase_report)
        lab.write_json(out / "report.json", report)
        log_cleanup = (phase != LOG_PHASE or (
            action_report.get("explicit_release") is True
            and action_report.get("cancel", {}).get("input_released") is True
            and action_report.get("post_cancel_denied") is True
            and action_report.get("cleanup_status") == "pass"))
        if (action_report["status"] != "inconclusive" or not log_cleanup or recorder.returncode != 0
                or not isinstance(clip, dict) or clip.get("test_id") != test_id
                or clip.get("client_pid") != identity["pid"]
                or clip.get("artifact_sha256") != smoke.AURA_SHA256
                or clip.get("stop_reason") != "test_finished"):
            raise lab.LabError(f"{phase} action or OBS clip was not validated", "fail")
        if cancel.is_set():
            raise lab.LabError("runtime memory guard cancelled technical smoke", "fail")
    report["status"] = "inconclusive"
    report["reason"] = "raw clips and frames require independent visual review"
    lab.write_json(out / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description="Owned-launch technical Survival input smoke")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--obs-control", type=Path, required=True)
    parser.add_argument("--obs-record", type=Path, required=True)
    parser.add_argument("--use-target", nargs=4, metavar=("X", "Y", "Z", "BLOCK"))
    parser.add_argument("--attack-target", nargs=4, metavar=("X", "Y", "Z", "BLOCK"))
    parser.add_argument("--mine-target", nargs=4, metavar=("X", "Y", "Z", "BLOCK"))
    parser.add_argument("--durable-target", nargs=4, metavar=("X", "Y", "Z", "BLOCK"))
    parser.add_argument("--log-target", nargs=4, metavar=("X", "Y", "Z", "BLOCK"))
    parser.add_argument("--expiry-target", nargs=4, metavar=("X", "Y", "Z", "BLOCK"))
    args = parser.parse_args()
    result = None
    recorder_started = [False]
    supervisor = {"status": "fail", "reason": "technical smoke did not start"}
    try:
        targets = checked_targets(args)
        bridge_sha256 = check_manifest(args.manifest)
        if (args.log_target is not None or args.expiry_target is not None) \
                and bridge_sha256 not in smoke.LONG_HOLD_BRIDGE_SHA256S:
            raise lab.LabError("long-hold gate requires the pinned long-hold candidate")
        if not args.obs_control.is_file() or not args.obs_record.is_file():
            raise lab.LabError("reviewed private OBS helpers are unavailable")
        if not obs_inactive(args.obs_control):
            raise lab.LabError("OBS recording or streaming is already active", "fail")
        result = runtime_launch.launch(
            args.manifest, args.profile, args.scenario,
            technical_smoke=lambda identity, artifact, run, cancel:
                run_phases(args, targets, identity, artifact, run, cancel, recorder_started))
        supervisor = {"status": result["status"], "lifecycle": result}
    except (lab.LabError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        supervisor = {"status": "fail", "reason": str(exc)[:180]}
    finally:
        obs_cleanup = reconcile_obs(args.obs_control, recorder_started[0])
        supervisor["obs_cleanup"] = obs_cleanup
        if obs_cleanup["status"] != "pass" or obs_cleanup["forced_stop"]:
            supervisor["status"] = "fail"
        print(json.dumps(supervisor))
    return 0 if supervisor["status"] == "inconclusive" else 2


if __name__ == "__main__":
    raise SystemExit(main())
