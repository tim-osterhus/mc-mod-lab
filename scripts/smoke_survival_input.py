"""Trusted, attach-only technical smoke for one already-leased Survival client."""

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import subprocess
import time

from PIL import Image

import lab
import scenario_v2
from survival_input import PolicyError, PolicySession


AURA_SHA256 = "2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8"
LONG_HOLD_BRIDGE_SHA256 = "fa97fbee19beb09c1a1becde8f5a91a7b40d77ae5eb2923dfe6fa6f37f3fa177"
MOVEMENT_PULSE_BRIDGE_SHA256 = "89897fc5e93ac101fd2bd20cff5ed5cb3885bb58a4f3e98040d6cfa58ace9518"
LONG_HOLD_BRIDGE_SHA256S = frozenset({LONG_HOLD_BRIDGE_SHA256, MOVEMENT_PULSE_BRIDGE_SHA256})
BRIDGE_SHA256S = frozenset({
    "99beb5e04c5dfb27e1e7cff2d3c614e89f170b3b92b2c180dd1ad4295c5b4e11",
    *LONG_HOLD_BRIDGE_SHA256S,
})
FRAME_SIZE = (1280, 720)


def checked_identity(identity_path, artifact):
    identity = lab.read_json(identity_path)
    lab.validate_identity(identity)
    if identity["expected_gamemode"] != "survival":
        raise lab.LabError("technical smoke requires Survival")
    if lab.check_derivative(identity) not in BRIDGE_SHA256S:
        raise lab.LabError("technical smoke bridge candidate differs")
    lab.launch_check(identity)
    scenario_v2.verify_packaged_artifact(identity, {"runtime": {
        "mod_id": "aura", "mod_version": "0.2.1+1.21.1",
        "artifact_sha256": AURA_SHA256}}, artifact)
    lab.status_check(identity)
    lab.world_check(identity)
    lab.player_check(identity)
    return identity


def verify_window(identity):
    title = f"MC Mod Lab Minecraft PID {identity['pid']}"
    command = ("Get-Process | Where-Object { $_.ProcessName -eq 'java' -or "
               "$_.ProcessName -eq 'javaw' } | "
               "Select-Object Id,MainWindowTitle | ConvertTo-Json -Compress")
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                            capture_output=True, text=True, timeout=10, check=False)
    if result.returncode != 0:
        raise lab.LabError("window process inventory unavailable")
    rows = json.loads(result.stdout or "[]")
    rows = [rows] if isinstance(rows, dict) else rows
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise lab.LabError("window process inventory is invalid")
    matches = [row for row in rows if row.get("MainWindowTitle") == title]
    if len(matches) != 1 or type(matches[0].get("Id")) is not int or matches[0]["Id"] != identity["pid"]:
        raise lab.LabError("capture window title or PID is ambiguous")
    return title


def fresh_output(path):
    path.mkdir(parents=True, exist_ok=False)
    return path


def prepare(args):
    identity = checked_identity(args.identity, args.artifact)
    out = fresh_output(args.out)
    lease = scenario_v2.ControlLease(identity)
    try:
        lease.enter()
        title = scenario_v2.label_capture_window(identity)
        scenario_v2.scenario_request(identity, "action", "aim_at_block", {
            "x": args.x, "y": args.y, "z": args.z, "block_id": args.block})
        crosshair_verified = False
        if args.block in {"minecraft:glass", "minecraft:stone", "minecraft:oak_log",
                          "minecraft:iron_block"}:
            scenario_v2.scenario_request(identity, "action", "select_hotbar", {
                "slot": 8, "item_id": "minecraft:air"})
            time.sleep(0.3)
            scenario_v2.scenario_request(identity, "action", "use_item_at_block", {
                "x": args.x, "y": args.y, "z": args.z, "block_id": args.block})
            screen = lab.command(identity, "get_screen_buttons")
            if not isinstance(screen, dict) or screen.get("screen") is not None:
                raise lab.LabError("block crosshair check opened a screen", "fail")
            crosshair_verified = True
    finally:
        if lease.acquired and lease.release()["status"] != "pass":
            raise lab.LabError("technical setup did not release control", "fail")
    if verify_window(identity) != title:
        raise lab.LabError("capture window title changed after labeling", "fail")
    shot = lab.screenshot(identity, out / "prepared.png")
    if (shot["width"], shot["height"]) != FRAME_SIZE:
        raise lab.LabError("prepared frame size differs from reviewed OBS canvas", "fail")
    report = {"status": "prepared_not_accepted", "client_pid": identity["pid"],
              "window_title": title, "target": {"x": args.x, "y": args.y, "z": args.z,
                                                   "block_id": args.block},
              "crosshair_verified": crosshair_verified,
              "prepared_frame": shot, "visual_status": "not_reviewed"}
    lab.write_json(out / "report.json", report)
    return report


def pixels_changed(before, after):
    with Image.open(BytesIO(before)) as first, Image.open(BytesIO(after)) as second:
        return first.size != second.size or first.convert("RGBA").tobytes() != second.convert("RGBA").tobytes()


def log_count(inventory):
    snapshot = scenario_v2._inventory_snapshot(inventory)
    if not snapshot["complete"] or not snapshot["server_authoritative"]:
        raise lab.LabError("complete server-authoritative inventory is required", "fail")
    return sum(stack["count"] for stack in snapshot["stacks"]
               if stack["itemId"] == "minecraft:oak_log"), snapshot["digest"]


def ground_log_count(snapshot):
    count = 0
    for entity in snapshot["entities"]:
        if entity["entity_id"] == "minecraft:item":
            if entity.get("item_components_complete") is not True:
                raise lab.LabError("ground item components are incomplete", "fail")
            if entity["item"]["item_id"] == "minecraft:oak_log":
                count += entity["item"]["count"]
    return count


def require_collection_platform(snapshot):
    position = snapshot["player_position"]
    if not (-3 <= position["x"] <= 7 and 160 <= position["y"] <= 164
            and -3 <= position["z"] <= 7):
        raise lab.LabError("player left the disclosed collection platform", "fail")
    return position


def expired_repress_denied(identity):
    lab.listening_socket(identity["pid"], identity["port"])
    envelope = lab.http_json(identity["port"], "/api/scenario/v2", {
        "schema_version": 2, "kind": "action", "name": "visible_key",
        "params": {"key": "attack", "pressed": True}})
    ack = envelope.get("result") if isinstance(envelope, dict) else None
    if (not isinstance(envelope, dict) or envelope.get("schema_version") != 2
            or envelope.get("kind") != "action" or envelope.get("name") != "visible_key"
            or envelope.get("status") != "ok" or not isinstance(ack, dict)
            or ack.get("action") != "visible_key" or ack.get("status") != "rejected"
            or type(ack.get("inputCalls")) is not int or ack["inputCalls"] != 0
            or ack.get("detail") != "attack hold expired; release before pressing again"):
        raise lab.LabError("expired attack renewal was not denied", "fail")
    return {"status": "rejected", "input_calls": 0}


def act(args, on_armed=None):
    identity = checked_identity(args.identity, args.artifact)
    if args.phase in {"log_mining", "expiry_mining"} \
            and lab.check_derivative(identity) not in LONG_HOLD_BRIDGE_SHA256S:
        raise lab.LabError("long-hold gate requires the pinned candidate", "fail")
    out = fresh_output(args.out)
    title = verify_window(identity)
    if args.stop_file.exists() or args.ready_file.exists():
        raise lab.LabError("fresh recorder stop and ready paths required")
    report = {"status": "fail", "reason": "technical smoke did not complete",
              "phase": args.phase, "test_id": args.test_id, "client_pid": identity["pid"],
              "window_title": title, "visual_status": "not_reviewed",
              "gameplay_result": "not_evaluated"}
    lab.write_json(out / "armed.json", {"test_id": args.test_id, "client_pid": identity["pid"],
                                        "phase": args.phase})
    try:
        if on_armed is not None:
            on_armed()
        deadline = time.monotonic() + 30
        while not args.ready_file.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        ready = lab.read_json(args.ready_file) if args.ready_file.exists() else {}
        if ready.get("recording") is not True or ready.get("test_id") != args.test_id:
            raise lab.LabError("matching recorder readiness unavailable", "fail")
        with PolicySession(identity, FRAME_SIZE) as session:
            before = session.frame()
            (out / "before.png").write_bytes(before)
            try:
                session.input({"type": "execute_command", "command": "say denied"})
            except PolicyError:
                report["denied_request"] = True
            else:
                raise lab.LabError("forbidden request was accepted", "fail")
            time.sleep(0.11)
            if args.phase == "log_mining":
                _, baseline = scenario_v2._scenario_observation(identity, {"type": "player_inventory"})
                before_count, before_digest = log_count(baseline)
                if before_count != 0:
                    raise lab.LabError("placed-log output was already in inventory", "fail")
                report["inventory_before"] = {"oak_log_count": before_count,
                                              "sha256": before_digest}
                _, ground_before = scenario_v2._scenario_observation(
                    identity, {"type": "ground_entities", "radius": 6})
                if ground_log_count(ground_before) != 0:
                    raise lab.LabError("oak-log output was already on the ground", "fail")
                report["ground_before"] = {"oak_log_count": 0,
                                           "server_tick": ground_before["server_tick"]}
                session.input({"type": "pulse", "key": "attack", "milliseconds": 5000})
                report["explicit_release"] = True
                time.sleep(0.25)
                _, after_inventory = scenario_v2._scenario_observation(
                    identity, {"type": "player_inventory"})
                after_count, after_digest = log_count(after_inventory)
                _, ground_after = scenario_v2._scenario_observation(
                    identity, {"type": "ground_entities", "radius": 6})
                require_collection_platform(ground_after)
                report["ground_after_break"] = {
                    "oak_log_count": ground_log_count(ground_after),
                    "server_tick": ground_after["server_tick"]}
                report["collection_pulses"] = 0
                if after_count == 0:
                    if ground_log_count(ground_after) != 1:
                        raise lab.LabError("placed-log ground drop not proven", "fail")
                    session.input({"type": "look", "yaw_delta": 0, "pitch_delta": -15})
                    time.sleep(0.15)
                    for attempt in range(5):
                        session.input({"type": "pulse", "key": "forward", "milliseconds": 100})
                        report["collection_pulses"] = attempt + 1
                        time.sleep(0.2)
                        _, after_inventory = scenario_v2._scenario_observation(
                            identity, {"type": "player_inventory"})
                        after_count, after_digest = log_count(after_inventory)
                        _, ground_after = scenario_v2._scenario_observation(
                            identity, {"type": "ground_entities", "radius": 6})
                        require_collection_platform(ground_after)
                        if after_count == 1:
                            break
                        if ground_log_count(ground_after) != 1:
                            raise lab.LabError("placed-log ground drop changed without pickup", "fail")
                report["inventory_after"] = {"oak_log_count": after_count,
                                             "sha256": after_digest}
                report["ground_after_collection"] = {
                    "oak_log_count": ground_log_count(ground_after),
                    "server_tick": ground_after["server_tick"],
                    "player_position": ground_after["player_position"]}
                if after_count == 1 and ground_log_count(ground_after) != 0:
                    raise lab.LabError("placed-log output was duplicated", "fail")
                report["pickup_observed"] = after_count == 1
                if after_count != 1:
                    raise lab.LabError("placed-log pickup not proven", "fail")
            elif args.phase == "expiry_mining":
                timeline = report["timeline"] = []

                def mark(event):
                    timeline.append({"event": event,
                                     "utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                                     "monotonic_ns": time.monotonic_ns()})

                def attack(pressed, event):
                    mark(event + "_request")
                    scenario_v2.scenario_request(identity, "action", "visible_key", {
                        "key": "attack", "pressed": pressed})
                    mark(event + "_ack")

                attack(True, "initial_press")
                try:
                    time.sleep(4.5)
                    mark("held_frame_request")
                    (out / "held.png").write_bytes(session.frame())
                    mark("held_frame_saved")
                    time.sleep(2.0)
                    mark("expired_frame_request")
                    (out / "expired.png").write_bytes(session.frame())
                    mark("expired_frame_saved")
                    mark("expired_repress_request")
                    report["expired_repress"] = expired_repress_denied(identity)
                    mark("expired_repress_ack")
                finally:
                    attack(False, "initial_release")
                report["explicit_release"] = True
                time.sleep(0.7)
                mark("neutral_frame_request")
                (out / "neutral.png").write_bytes(session.frame())
                mark("neutral_frame_saved")
                attack(True, "second_press")
                try:
                    time.sleep(0.7)
                finally:
                    attack(False, "second_release")
                report["release_repress_exercised"] = True
            elif args.phase in {"held_mining", "durable_mining"}:
                def attack(pressed):
                    scenario_v2.scenario_request(identity, "action", "visible_key", {
                        "key": "attack", "pressed": pressed})

                attack(True)
                try:
                    if args.phase == "held_mining":
                        time.sleep(0.2)
                        attack(True)
                        report["repeat_press_exercised"] = True
                        time.sleep(0.3)
                    else:
                        time.sleep(1.2)
                finally:
                    attack(False)
                report["explicit_release"] = True
                time.sleep(0.5 if args.phase == "durable_mining" else 0.15)
                if args.phase == "durable_mining":
                    neutral = session.frame()
                    (out / "neutral.png").write_bytes(neutral)
                    report["neutral_frame_sha256"] = lab.sha256(out / "neutral.png")
                attack(True)
                try:
                    time.sleep(0.3 if args.phase == "durable_mining" else 0.15)
                finally:
                    attack(False)
                report["release_repress_exercised"] = True
            else:
                duration = 100 if args.phase == "use" else 150
                key = "use" if args.phase == "use" else "attack"
                session.input({"type": "pulse", "key": key, "milliseconds": duration})
            if args.phase == "use":
                screen = lab.command(identity, "get_screen_buttons")
                if not isinstance(screen, dict) or not isinstance(screen.get("screen"), str):
                    raise lab.LabError("use did not open the declared fixture screen", "fail")
                report["screen_opened"] = screen["screen"]
                report["window_title_during_gui"] = verify_window(identity)
            time.sleep(0.5)
            after = session.frame()
            (out / "after.png").write_bytes(after)
            report["frames"] = {"before_sha256": lab.sha256(out / "before.png"),
                                "after_sha256": lab.sha256(out / "after.png")}
            report["pixel_changed"] = pixels_changed(before, after)
            if args.phase == "use":
                session.input({"type": "press", "key": "Escape"})
                time.sleep(0.5)
                closed = lab.command(identity, "get_screen_buttons")
                if not isinstance(closed, dict) or closed.get("screen") is not None:
                    raise lab.LabError("fixture screen did not close", "fail")
                (out / "closed.png").write_bytes(session.frame())
                report["screen_closed"] = True
                report["window_title_after_gui"] = verify_window(identity)
            report["cancel"] = session.cancel()
            try:
                session.input({"type": "look", "yaw_delta": 1, "pitch_delta": 0})
            except PolicyError:
                report["post_cancel_denied"] = True
            else:
                raise lab.LabError("input remained available after cancel", "fail")
            report["cleanup_status"] = session.cleanup_status
        report["status"] = "inconclusive"
        report["reason"] = "rendered action requires independent clip and frame review"
    except (lab.LabError, PolicyError, OSError, ValueError, subprocess.SubprocessError) as exc:
        report["reason"] = str(exc)[:180]
    finally:
        args.stop_file.touch(exist_ok=True)
        lab.write_json(out / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description="Attach-only developer Survival input smoke")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "act"):
        command = commands.add_parser(name)
        command.add_argument("--identity", type=Path, required=True)
        command.add_argument("--artifact", type=Path, required=True)
        command.add_argument("--out", type=Path, required=True)
        if name == "prepare":
            command.add_argument("--x", type=int, required=True)
            command.add_argument("--y", type=int, required=True)
            command.add_argument("--z", type=int, required=True)
            command.add_argument("--block", required=True)
        else:
            command.add_argument("--phase", choices=("use", "initial_attack", "held_mining",
                                                     "durable_mining", "log_mining",
                                                     "expiry_mining"), required=True)
            command.add_argument("--test-id", required=True)
            command.add_argument("--ready-file", type=Path, required=True)
            command.add_argument("--stop-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args) if args.command == "prepare" else act(args)
        print(json.dumps(result))
        return 0 if result["status"] in {"prepared_not_accepted", "inconclusive"} else 2
    except (lab.LabError, PolicyError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "fail", "reason": str(exc)[:180]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
