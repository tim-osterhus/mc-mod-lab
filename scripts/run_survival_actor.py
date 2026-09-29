"""Owned-launch first Survival actor trial; explicit model and lease required."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import contracts
import lab
import runtime_launch
import runtime_profile
import scenario_v2
import survival_actor
from survival_input import PolicyError, PolicySession
from survival_seed import SeedError, inspect_seed
from scripts.smoke_survival_input import AURA_SHA256, FRAME_SIZE, MOVEMENT_PULSE_BRIDGE_SHA256


ROOT = Path(__file__).resolve().parents[1]
GUIDE_SCREEN = "GuiBookLanding"


def guide_frame_capture(identity, out, report):
    path = out / "guide-open.png"

    def screen():
        value = lab.command(identity, "get_screen_buttons")
        if (not isinstance(value, dict) or "screen" not in value
                or (value.get("screen") is not None and not isinstance(value["screen"], str))):
            raise lab.LabError("guide screen observation is unavailable", "fail")
        return value["screen"]

    def capture(frame):
        evidence = report["guide_frame"]
        if evidence["status"] == "candidate":
            return frame()
        evidence["probe_count"] += 1
        before = screen()
        png = frame()
        after = screen()
        if before == after == GUIDE_SCREEN:
            path.write_bytes(png)
            evidence.update(status="candidate", file=path.name,
                            sha256=lab.sha256(path),
                            screen_class=GUIDE_SCREEN, visual_status="not_reviewed")
        return png

    return capture


def preflight(args):
    manifest = contracts.load(args.manifest)
    contracts.schema_check(manifest, "runtime-profile")
    mods = {entry["role"]: entry for entry in manifest["mods"]}
    if (manifest["bridge_classification"] != "public_reviewed"
            or manifest["expected_gamemode"] != "survival"
            or mods["target"]["mod_id"] != "aura"
            or mods["target"]["mod_version"] != "0.2.1+1.21.1"
            or mods["target"]["sha256"] != AURA_SHA256
            or mods["bridge"]["sha256"] != MOVEMENT_PULSE_BRIDGE_SHA256):
        raise lab.LabError("isolated actor requires the pinned Aura and public bridge artifacts")
    if not args.aura_source.is_absolute() or not args.aura_source.is_file():
        raise lab.LabError("Aura source path for the actor denial probe is unavailable")
    seed = Path(manifest["seed_save"])
    inspect_seed(seed)
    profile = contracts.load(args.profile / "profile.json")
    copy = args.profile / "game" / "saves" / profile["world_directory"]
    inspect_seed(copy)
    if (lab.sha256(seed / "level.dat") != lab.sha256(copy / "level.dat")
            or runtime_profile._fixture_hash(copy) != profile["fixture_sha256"]):
        raise lab.LabError("prepared world differs from closed seed or profile")
    model = survival_actor.OllamaVisionModel(args.model)
    return model


def trial(identity, artifact, run, cancel, model, aura_source):
    report = {"status": "fail", "reason": "isolated actor did not start",
              "actor_isolation": {"status": "not_run"},
              "broker_denials": {"status": "not_run"},
              "model_name": model.name, "action_trace": [],
              "guide_frame": {"status": "not_observed", "probe_count": 0}}
    out = run / "survival-actor"
    out.mkdir(exist_ok=True)
    try:
        if cancel.is_set() or lab.sha256(artifact) != AURA_SHA256:
            raise lab.LabError("runtime guard or Aura artifact changed", "fail")
        _, inventory = scenario_v2._scenario_observation(identity, {"type": "player_inventory"})
        snapshot = scenario_v2._inventory_snapshot(inventory)
        if not snapshot["complete"] or not snapshot["server_authoritative"] or snapshot["stacks"]:
            raise lab.LabError("fresh-world starting inventory is not empty and authoritative", "fail")
        report["initial_inventory_digest"] = snapshot["digest"]
        lab.listening_socket(identity["pid"], identity["port"])
        report["actor_isolation"] = survival_actor.isolation_probe(
            [ROOT / "survival_input.py", aura_source, Path(identity["world_path"]) / "level.dat"],
            identity["port"])
        source_hash = report["actor_isolation"]["actor_source_sha256"]
        first_frame = out / "first-frame.png"
        session = PolicySession(identity, FRAME_SIZE)
        try:
            with session:
                report["broker_denials"] = survival_actor.broker_probe(session, model, source_hash)
                report.update(survival_actor.run_actor(
                    session, model, cancel, first_frame=lambda png: first_frame.write_bytes(png),
                    expected_source_hash=source_hash, trace_out=report["action_trace"],
                    guide_capture=guide_frame_capture(identity, out, report)))
        finally:
            report["neutral_release"] = session.cleanup_status
            report["actor_source_after_sha256"] = survival_actor.actor_source_hash()
            if first_frame.is_file():
                report["first_frame_sha256"] = hashlib.sha256(first_frame.read_bytes()).hexdigest()
    except (survival_actor.ActorError, PolicyError, SeedError, lab.LabError, OSError, ValueError) as exc:
        report["status"] = "fail"
        report["reason"] = str(exc)[:180]
    lab.write_json(out / "report.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--model", required=True, help="already-installed local Ollama vision model")
    parser.add_argument("--aura-source", type=Path, required=True,
                        help="existing Aura source file used only for actor denial probe")
    args = parser.parse_args(argv)
    try:
        model = preflight(args)
        result = runtime_launch.launch(
            args.manifest, args.profile, args.scenario,
            technical_smoke=lambda identity, artifact, run, cancel:
                trial(identity, artifact, run, cancel, model, args.aura_source))
    except (survival_actor.ActorError, SeedError, lab.LabError, OSError, ValueError, KeyError) as exc:
        result = {"status": "fail", "reason": str(exc)[:180], "client_launched": False}
    print(json.dumps(result))
    return 0 if result["status"] == "inconclusive" else 2


if __name__ == "__main__":
    sys.exit(main())
